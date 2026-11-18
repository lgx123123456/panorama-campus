extends Node

const Firearms = preload("res://scripts/campus/campus_firearms.gd")
var failed := false
var walker: CharacterBody3D
var level: Node3D
var guns: Node3D

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	reparent(get_tree().root)
	get_tree().change_scene_to_file("res://scenes/campus/zombie_trial.tscn")
	await get_tree().scene_changed
	level = get_tree().current_scene.get_node("CharacterTrial")
	walker = level.walker
	guns = level.firearms
	walker.set_physics_process(false)
	level.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.guide.set_physics_process(false)
	walker._capture_mouse(true)
	walker.identity = 0
	for id: String in ["pistol", "rifle", "smg", "shotgun", "sniper", "minigun"]:
		var stats := Firearms.campus_weapon_stats(id)
		guns.weapon_stats[id] = stats
		guns.ammo[id] = {"mag": 20, "reserve": 100}
		guns.owned[id] = true
		if not guns.loadout.has(id):
			guns.loadout.append(id)
	guns._attach_minigun()
	for source: Dictionary in WeaponDB.WEAPONS + [Firearms.MINIGUN_STATS]:
		if source.id == "shotgun":
			continue
		for region: StringName in [&"胸部", &"腹部", &"手臂", &"腿部"]:
			for distance: float in [2.0, 100.0, 500.0]:
				_check(is_equal_approx(guns._body_damage(source, region, distance), 50.0),
					"%s %s at %.0fm deals 50 body damage" % [source.id, region, distance])
	var shotgun: Dictionary = WeaponDB.get_weapon("shotgun")
	_check(is_equal_approx(guns._body_damage(shotgun, &"胸部", 6), 9.0)
		and is_equal_approx(guns._body_damage(shotgun, &"胸部", 30), 2.25), "shotgun keeps pellet falloff")
	guns.switch_weapon(guns.loadout.find("pistol"))
	var pistol_speed: float = walker._movement_speed()
	_check(is_equal_approx(pistol_speed, walker.WALK_SPEED), "pistol preserves original walking pace")
	guns.switch_weapon(guns.loadout.find("rifle"))
	_check(walker._movement_speed() < pistol_speed, "rifle slows walking")
	guns.holstered = true
	_check(walker._movement_speed() > pistol_speed, "unarmed walking is faster than pistol")
	guns.holstered = false
	walker.quiet = true
	_check(walker._movement_speed() < 1.65, "quiet rifle stays slower than quiet pistol")
	walker.quiet = false
	for id: String in ["pistol", "rifle", "smg", "shotgun", "sniper", "minigun"]:
		guns.switch_weapon(guns.loadout.find(id))
		var factor: float = Firearms.WEAPON_SPEED_SCALES[id]
		_check(is_equal_approx(walker._movement_speed(), walker.WALK_SPEED * factor), id + " walking uses its load factor")
		Input.action_press("sprint")
		_check(is_equal_approx(walker._movement_speed(), walker.base_human_sprint_speed() * factor), id + " sprint uses its load factor")
		Input.action_release("sprint")
	_check(is_equal_approx(WeaponDB.get_weapon("rifle").damage, 17.0), "campus balance preserves the shared weapon database")
	await _hitscan_checks()
	await _stairs()
	await _step_blockers()
	print("COMBAT MOVEMENT ", "FAIL" if failed else "PASS")
	for player in get_tree().root.find_children("*", "AudioStreamPlayer3D", true, false):
		player.stop()
	get_tree().current_scene.queue_free()
	await get_tree().process_frame
	get_tree().quit(1 if failed else 0)

func _hitscan_checks() -> void:
	walker.quiet = false

	walker.global_position = Vector3(0, 150, 0)
	walker.rotation = Vector3.ZERO
	walker.camera.rotation = Vector3.ZERO
	for id: String in ["pistol", "rifle", "smg", "sniper", "minigun"]:
		guns.switch_weapon(guns.loadout.find(id))
		var source: Dictionary = guns.weapon_stats[id]
		var deterministic := source.duplicate()
		deterministic.spread_deg = 0.0
		deterministic.aim_spread_deg = 0.0
		guns.weapon_stats[id] = deterministic
		for distance: float in [5.0, 180.0, 500.0]:
			for part: StringName in [&"胸部", &"头部"]:
				var zombie: Node3D = level.spawner._spawn(Vector3(0, 150, -distance))
				zombie.set_physics_process(false)
				zombie.rotation.y = PI
				await _wait(2)
				var eye: Vector3 = walker.camera.global_position
				var candidates := Firearms.Hitboxes.collect([zombie], eye, Vector3.FORWARD, 10000.0, 0.0)
				var point := Vector3.INF
				for volume: Dictionary in candidates[0].regions:
					if volume.region != part:
						continue
					var bounds: AABB = volume.bounds
					var pose: Transform3D = volume.inverse.affine_inverse()
					for height: float in [0.5, 0.25, 0.75, 0.9, 0.1]:
						var middle := pose * (bounds.position + bounds.size * Vector3(0.5, height, 0.5))
						var hit := Firearms.Hitboxes.intersect(eye, eye + eye.direction_to(middle) * 10000.0, candidates)
						if hit.get("region") == part:
							point = middle
							break
					if point != Vector3.INF:
						break
				_check(point != Vector3.INF, "%s %.0fm has a reachable %s hitbox" % [id, distance, part])
				if point != Vector3.INF:
					walker.camera.look_at(point)
					guns.cooldown = 0.0
					guns.ammo[id].mag = 3
					_check(guns.try_fire(), "%s fires at %.0fm" % [id, distance])
					if part == &"头部":
						_check(zombie.defeated, "%s headshot kills in one at %.0fm" % [id, distance])
					else:
						_check(is_equal_approx(zombie.health, 50.0) and not zombie.defeated,
							"%s body shot leaves 50 health at %.0fm" % [id, distance])
						guns.cooldown = 0.0
						guns.try_fire()
						_check(zombie.defeated, "%s second body shot kills at %.0fm" % [id, distance])
				zombie.queue_free()
				await _wait(1)
		guns.weapon_stats[id] = source
	guns.switch_weapon(guns.loadout.find("rifle"))

func _step_blockers() -> void:
	walker.quiet = true
	for low_ceiling in [false, true]:
		var obstacle := _add_box(Vector3(0, 100.09 if low_ceiling else 100.30, 1.2),
			Vector3(3, 0.18 if low_ceiling else 0.6, 0.32))
		var ceiling: StaticBody3D
		if low_ceiling:
			ceiling = _add_box(Vector3(0, 101.90, 1.6), Vector3(3, 0.1, 3))
		walker.global_position = Vector3(0, 100.04, 2.5)
		walker.rotation = Vector3.ZERO
		walker.velocity = Vector3.ZERO
		for frame in 20:
			walker._physics_process(get_physics_process_delta_time())
			await get_tree().physics_frame
		Input.action_press("move_forward")
		for frame in 180:
			walker._physics_process(get_physics_process_delta_time())
			await get_tree().physics_frame
		Input.action_release("move_forward")
		_check(walker.global_position.z > 1.3 and walker.global_position.y < 100.19,
			"step sweep respects low headroom" if low_ceiling else "step sweep blocks a 60cm wall")
		obstacle.queue_free()
		if is_instance_valid(ceiling):
			ceiling.queue_free()
		await _wait(3)
	walker.quiet = false

func _stairs() -> void:
	var origin := Vector3(0, 100, 0)
	_add_box(origin + Vector3(0, -0.5, -2.5), Vector3(8, 1, 12))
	for index in 14:
		var height := 0.18 * (index + 1)
		_add_box(origin + Vector3(0, height * 0.5, -1.2 - index * 0.32), Vector3(3, height, 0.32))
	await _wait(4)
	for mode in ["quiet", "crouch", "slow-analog"]:
		walker.quiet = mode == "quiet"
		walker.global_position = origin + Vector3(0, 0.04, 0)
		walker.rotation = Vector3.ZERO
		walker.velocity = Vector3.ZERO
		Input.action_release("move_forward")
		if mode == "crouch":
			Input.action_press("crouch")
		else:
			Input.action_release("crouch")
		for frame in 24:
			walker._physics_process(get_physics_process_delta_time())
			await get_tree().physics_frame
		Input.action_press("move_forward", 0.6 if mode == "slow-analog" else 1.0)
		var reached := false
		for frame in 1400:
			walker._physics_process(get_physics_process_delta_time())
			await get_tree().physics_frame
			if walker.global_position.z < -5.1:
				reached = walker.global_position.y > 102.3
				break
		Input.action_release("move_forward")
		print("STAIR POSITION ", mode, " ", walker.global_position, " floor=", walker.is_on_floor(), " wall=", walker.is_on_wall())
		for index in walker.get_slide_collision_count():
			var hit := walker.get_slide_collision(index)
			print("STAIR CONTACT ", hit.get_position() - walker.global_position, " normal=", hit.get_normal())
		_check(reached, mode + " climbs fourteen 18cm steps without a jump")
	Input.action_release("crouch")
	walker.quiet = false
	await _cursor_release_step_check(origin)

func _cursor_release_step_check(origin: Vector3) -> void:
	walker.global_position = origin + Vector3(0, 0.025, -0.79)
	walker.rotation = Vector3.ZERO
	walker.velocity = Vector3.ZERO
	walker.stair_support_left = 0.2
	walker._capture_mouse(false)
	Input.action_press("move_forward")
	var start := walker.global_position
	for frame in 12:
		walker._physics_process(get_physics_process_delta_time())
		await get_tree().physics_frame
	Input.action_release("move_forward")
	var traveled := walker.global_position - start
	_check(Vector2(traveled.x, traveled.z).length() < 0.003,
		"releasing the cursor blocks held movement beside a stair edge")
	walker._capture_mouse(true)

func _add_box(at: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	get_tree().current_scene.add_child(body)
	body.global_position = at
	return body

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _check(ok: bool, label: String) -> void:
	print("COMBAT MOVE ", "PASS " if ok else "FAIL ", label)
	failed = failed or not ok


