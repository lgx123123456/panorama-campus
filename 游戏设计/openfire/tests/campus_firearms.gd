extends Node

var failed := false
var level: Node3D
var walker: CharacterBody3D
var guns: Node3D

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	var full := "--full-campus" in OS.get_cmdline_user_args()
	tree.change_scene_to_file("res://scenes/campus/survival_admin.tscn" if full else "res://scenes/campus/zombie_trial.tscn")
	await tree.scene_changed
	level = tree.current_scene.get_node("CharacterTrial")
	walker = level.walker
	guns = level.firearms
	level.spawner.set_physics_process(false)
	level.set_physics_process(false)
	if full:
		_sprint_checks()
		_check(guns.owned.is_empty() and guns.holstered and not guns.try_fire(),
			"administrator campaign starts unarmed")
		for id: String in guns.loadout:
			guns.grant_supply(id, 960 if id == "minigun" else 120, true)
		_check(guns.ammo.minigun.mag == 240 and guns.ammo.minigun.reserve == 720,
			"finale pickup gives 960 rounds including a loaded magazine")
		guns.switch_weapon(0)
	await _wait(35)
	_check(guns.is_presented() and not walker.hands.visible, "authored arms replace idle hands while a gun is held")
	var expected_loadout := ["pistol", "rifle", "smg", "shotgun", "minigun"] if full else ["rifle", "shotgun", "pistol"]
	_check(guns.loadout == expected_loadout, "loadout matches the selected campus mode")
	for index in expected_loadout.size():
		gun_input(KEY_1 + index)
		await _wait(15)
		var id: String = guns.weapon_id()
		var profile: Dictionary = guns.PROFILES[id]
		_check(id == expected_loadout[index], "number key selects " + expected_loadout[index])
		_check(guns.animation.has_animation(String(profile.get("animation", profile.mesh)) + "_reload"),
			"authored reload clip for " + id)
		_check(guns.rig.find_child(profile.mesh, true, false).is_visible_in_tree(), "correct visible weapon mesh")
		var before: int = guns.ammo[id].mag
		guns.cooldown = 0.0
		_check(guns.try_fire() and guns.ammo[id].mag == before - 1, "firing consumes one magazine round")
		_check(not guns.try_fire(), "fire-rate cooldown blocks duplicate shots")
		_check(guns.reload_weapon(), "reload starts after a shot")
		guns.reload_left = 0.01
		await _wait(3)
		_check(guns.ammo[id].mag == before, "reload restores magazine")
	guns.switch_weapon(guns.loadout.find("rifle"))
	guns.ammo.rifle.mag = 5
	guns.ammo.rifle.reserve = 0
	_check(not guns.reload_weapon(), "empty reserve prevents reloading")
	guns.ammo.rifle.reserve = 2
	_check(guns.reload_weapon(), "reload starts with rounds in reserve")
	guns.reload_left = 0.01
	await _wait(3)
	_check(guns.ammo.rifle.mag == 7 and guns.ammo.rifle.reserve == 0, "reload consumes the available reserve")
	guns.ammo.rifle.mag = 5
	guns.ammo.rifle.reserve = 20
	guns.reload_weapon()
	guns.switch_weapon(guns.loadout.find("pistol"))
	await _wait(5)
	_check(guns.reload_left == 0.0 and guns.ammo.rifle.mag == 5, "switch cancels reload without granting ammo")
	guns.ammo.pistol.mag = 1
	guns.reload_weapon()
	gun_input(KEY_X)
	_check(guns.reload_left == 0.0 and not guns.animation.is_playing(), "holster cancels reload animation")
	gun_input(KEY_X)
	guns.reload_weapon()
	guns.interrupt_action()
	_check(guns.reload_left == 0.0 and not guns.animation.is_playing(), "interaction cancels reload animation")
	await _wait(45)
	gun_input(KEY_X)
	await _wait(2)
	_check(guns.holstered and walker.hands.visible and not guns.try_fire(), "X holsters and blocks shooting")
	gun_input(KEY_1)
	await _wait(15)
	Input.action_press("aim")
	await _wait(20)
	_check(guns.aiming and walker.camera.fov < guns.base_fov - 10.0, "ADS changes actual camera FOV")
	Input.action_release("aim")
	walker._toggle_camera()
	await _wait(4)
	_check(not guns.rig.visible and guns.third_person_model.is_visible_in_tree(), "third-person switch uses one world weapon")
	_check(guns.arm_ik.active and guns.arm_ik.setting_count == 2, "third-person arms reach both weapon grips")
	walker.camera.rotation.x = 1.3
	await _wait(2)
	_check(is_equal_approx(guns.weapon_anchor.rotation.x, walker.camera.rotation.x), "world gun follows steep camera pitch")
	walker.camera.rotation.x = 0.0
	walker._toggle_camera()
	await _wait(3)
	_check(guns.rig.visible and not guns.third_person_model.is_visible_in_tree(), "first-person restores authored rig")
	walker.play_hand_action(&"pickup")
	await _wait(1)
	_check(not guns.is_presented() and not guns.try_fire(), "pickup interrupts gun and reload")
	await _wait(50)
	_check(guns.is_presented(), "gun returns after hand action")
	if "--capture" in OS.get_cmdline_user_args():
		await _capture(full)
	if not full:
		await _damage_checks()
		await _movement_checks()
	await _input_checks()
	level._turn_player()
	await _wait(3)
	if full:
		_check(level.round_finished and level.result_panel.visible and walker.movement_locked
			and not guns.try_fire(), "campaign infection ends combat and offers results")
		# Resume an isolated combat fixture for the remaining weapon checks.
		level.round_finished = false
		level.result_panel.hide()
		level.infection = -1.0
		walker.movement_locked = false
		walker._capture_mouse(true)
	else:
		_check(not guns.is_presented() and not guns.try_fire(), "infected role uses original melee actions")
		_check(is_equal_approx(walker.camera.fov, minf(Settings.fov, 65.0)), "infection preserves role-specific FOV")
	walker.set_role(2, walker.HUMAN)
	await _wait(3)
	_check(guns.is_presented(), "human role restores weapon")
	walker._toggle_camera()
	await _wait(3)
	_check(guns.arm_ik.active and guns.arm_skeleton == walker.look.model.find_children("*", "Skeleton3D", true, false)[0], "appearance change rebuilds armed pose on current skeleton")
	walker._toggle_camera()
	walker._capture_mouse(false)
	_check(not guns.try_fire(), "released cursor blocks shooting")
	if full:
		gun_input(KEY_KP_3)
		_check(guns.weapon_id() == "smg", "numpad selects a gun with the cursor released")
		gun_input(KEY_4)
		_check(guns.weapon_id() == "shotgun", "top-row keys select a gun with the cursor released")
		gun_input(KEY_KP_5)
		_check(guns.weapon_id() == "minigun" and "5 加特林" in guns.loadout_hint,
			"finale weapon remains selectable in slot 5")
		level.held = &"brick"
		walker.hands.set_holding(true)
		walker.play_hand_action(&"pickup")
		gun_input(KEY_1)
		_check(level.held == &"" and not level.props[&"brick"].freeze and guns.is_presented(),
			"switching puts down the carried item and presents the gun immediately")
		await _hitbox_checks()
		await _debug_health_checks()
	print("CAMPUS FIREARMS ", "FAIL" if failed else "PASS")
	# Let impact timers finish and stop real-time audio before fast test shutdown.
	await _wait(65)
	for player in tree.root.find_children("*", "AudioStreamPlayer3D", true, false):
		player.stop()
	for player in tree.root.find_children("*", "AudioStreamPlayer", true, false):
		player.stop()
	tree.current_scene.queue_free()
	await tree.process_frame
	await tree.create_timer(0.1, true, false, true).timeout
	tree.quit(1 if failed else 0)

func _input_checks() -> void:
	guns.switch_weapon(guns.loadout.find("rifle"))
	guns.ammo.rifle.mag = 30
	await _wait(16)
	Input.action_press("fire")
	await _wait(25)
	_check(guns.ammo.rifle.mag < 28, "held trigger repeatedly fires automatic rifle")
	walker._capture_mouse(false)
	await _wait(4)
	var rounds: int = guns.ammo.rifle.mag
	walker._capture_mouse(true)
	await _wait(20)
	_check(guns.ammo.rifle.mag == rounds, "held trigger across cursor release and recapture stays blocked")
	Input.action_release("fire")
	await _wait(3)
	Input.action_press("fire")
	await _wait(2)
	_check(guns.ammo.rifle.mag == rounds - 1, "fresh trigger after recapture fires normally")
	Input.action_release("fire")
	guns.switch_weapon(guns.loadout.find("pistol"))
	guns.ammo.pistol.mag = 12
	await _wait(16)
	Input.action_press("fire")
	await _wait(35)
	_check(guns.ammo.pistol.mag == 11, "held trigger fires semi-automatic pistol once")
	Input.action_release("fire")

func gun_input(key: Key) -> void:
	var event := InputEventKey.new()
	event.pressed = true
	event.physical_keycode = key
	guns._input(event)

func _damage_checks() -> void:
	level.guide.set_physics_process(false)
	level.guide.position = Vector3(5, 0.05, -6)
	walker.position = Vector3(-15, 0.05, -5)
	walker.velocity = Vector3.ZERO
	walker.look_at(Vector3(-8, walker.position.y, -5))
	walker.camera.rotation = Vector3.ZERO
	await _wait(5)
	var zombie: Node3D = level.spawner._spawn(Vector3(-10, 0.05, -5))
	zombie.set_physics_process(false)
	await _wait(3)
	guns.switch_weapon(2)
	guns.cooldown = 0.0
	walker.camera.look_at(zombie.global_position + Vector3.UP * 1.0)
	guns.aiming = true
	_check(guns.try_fire(), "aimed shot executes")
	_check(zombie.health < 100.0, "hitscan damages campus zombie")
	var health_before: float = zombie.health
	var wall := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.3, 3.0, 3.0)
	shape.shape = box
	wall.add_child(shape)
	level.add_child(wall)
	wall.position = Vector3(-12.5, 1.5, -5)
	await _wait(3)
	guns.cooldown = 0.0
	guns.try_fire()
	_check(zombie.health == health_before, "solid wall occludes hitscan")
	walker._toggle_camera()
	await _wait(3)
	# Place the follow camera past the wall while the player's eye stays behind it.
	var follow_transform: Transform3D = walker.follow_camera.transform
	walker.follow_camera.top_level = true
	walker.follow_camera.global_position = Vector3(-11.5, 1.3, -5)
	walker.follow_camera.look_at(zombie.global_position + Vector3.UP)
	guns.cooldown = 0.0
	guns.aiming = true
	guns.try_fire()
	_check(zombie.health == health_before, "third-person camera past a corner cannot bypass eye-level wall")
	walker.follow_camera.top_level = false
	walker.follow_camera.transform = follow_transform
	walker._toggle_camera()
	wall.queue_free()
	await _wait(3)
	zombie.take_weapon_hit(100.0)
	_check(zombie.defeated and not level.spawner.zombies.has(zombie) and zombie.collision_layer == 0, "defeat clears AI, collision and spawner tracking")

func _hitbox_checks() -> void:
	const Hitboxes = preload("res://scripts/campus/campus_hitboxes.gd")
	walker.set_physics_process(false)
	walker.global_position = Vector3(0, 150, 0)
	walker.rotation = Vector3.ZERO
	walker.camera.rotation = Vector3.ZERO
	walker._capture_mouse(true)
	seed(1988)
	for index in guns.loadout.size():
		guns.switch_weapon(index)
		var id: String = guns.weapon_id()
		var original_weapon: Dictionary = guns.weapon_stats[id]
		var weapon := original_weapon.duplicate()
		weapon.spread_deg = 0.0 # Aim deterministically at a specific animated body part.
		guns.weapon_stats[id] = weapon
		var zombie: Node3D = level.spawner._spawn(Vector3(0, 150, -5))
		zombie.set_physics_process(false)
		zombie.rotation.y = PI
		await _wait(2)
		var eye: Vector3 = walker.camera.global_position
		var candidates := Hitboxes.collect([zombie], eye, Vector3.FORWARD, 40.0, 0.0)
		for part in [&"胸部", &"头部"]:
			var point := Vector3.INF
			for volume: Dictionary in candidates[0].regions:
				if volume.region != part:
					continue
				var bounds: AABB = volume.bounds
				var pose: Transform3D = volume.inverse.affine_inverse()
				for height: float in [0.5, 0.25, 0.75, 0.9, 0.1]:
					var middle := pose * (bounds.position + bounds.size * Vector3(0.5, height, 0.5))
					var hit := Hitboxes.intersect(eye, eye + eye.direction_to(middle) * 40.0, candidates)
					if hit.get("region") == part:
						point = middle
						break
				if point != Vector3.INF:
					break
			_check(point != Vector3.INF, "%s has a reachable %s box" % [id, part])
			if point == Vector3.INF:
				continue
			walker.camera.look_at(point)
			guns.cooldown = 0.0
			guns.ammo[id].mag = 2
			_check(guns.try_fire(), id + " fires during hitbox test")
			if part == &"胸部":
				_check(is_equal_approx(zombie.health, 100.0 - float(weapon.damage) * int(weapon.pellets))
					and not zombie.defeated, id + " chest hit uses body damage and requires another shot")
			else:
				_check(zombie.defeated and zombie.health == 0.0 and "爆头" in guns.damage_feedback,
					id + " kills with a single animated head hit")
		if not zombie.defeated:
			zombie.take_weapon_hit(100.0)
		zombie.queue_free()
		guns.weapon_stats[id] = original_weapon
	var shotgun: Dictionary = guns.weapon_stats.shotgun
	_check(is_equal_approx(guns._body_damage(shotgun, &"胸部", 6.0), 9.0)
		and is_equal_approx(guns._body_damage(shotgun, &"胸部", 18.0), 5.625)
		and is_equal_approx(guns._body_damage(shotgun, &"胸部", 30.0), 2.25),
		"shotgun body damage falls off from 6 to 30 metres")
	_check(guns._body_damage(shotgun, &"胸部", 3.0) > guns._body_damage(shotgun, &"腹部", 3.0)
		and guns._body_damage(shotgun, &"腹部", 3.0) > guns._body_damage(shotgun, &"手臂", 3.0)
		and guns._body_damage(shotgun, &"手臂", 3.0) > guns._body_damage(shotgun, &"腿部", 3.0),
		"chest, abdomen, arms and legs use different damage")
	var spread := tan(deg_to_rad(6.0))
	var directions: PackedVector3Array = guns._shot_directions(Basis.IDENTITY, 9, spread)
	var in_cone := directions.size() == 9 and directions[0].is_equal_approx(Vector3.FORWARD)
	var unique := {}
	for direction in directions:
		unique[direction] = true
		in_cone = in_cone and direction.dot(Vector3.FORWARD) >= cos(deg_to_rad(6.0))
	_check(in_cone and unique.size() == 9, "shotgun sends nine separate pellets within the spread cone")

func _sprint_checks() -> void:
	var menu: Control = level.interface.get_node("CombatDebug")
	menu._open()
	_check(is_equal_approx(menu.fields[&"interval"].value, level.spawner.spawn_interval)
		and is_equal_approx(menu.fields[&"spawn_min"].value, level.spawner.min_spawn_distance),
		"debug fields display the campaign's exact spawn settings")
	var sprint_field: SpinBox = menu.fields[&"player_sprint_speed"]
	var default_sprint: float = walker.base_human_sprint_speed()
	_check(is_equal_approx(sprint_field.value, default_sprint), "debug field displays the same default sprint speed")
	sprint_field.value = 8.5
	var load_scale: float = guns.movement_speed_scale()
	Input.action_press("sprint")
	_check(is_equal_approx(walker._movement_speed(), 8.5 * load_scale), "debug value changes Shift sprint with equipped load")
	Input.action_release("sprint")
	_check(is_equal_approx(walker._movement_speed(), walker.WALK_SPEED * load_scale), "debug value preserves the walking load factor")
	var reset: Button = menu.find_children("*", "Button", true, false).filter(
		func(button: Button): return button.text == "恢复人物跑速")[0]
	reset.pressed.emit()
	Input.action_press("sprint")
	_check(is_equal_approx(sprint_field.value, default_sprint)
		and is_equal_approx(walker._movement_speed(), default_sprint * load_scale), "reset restores the role's default sprint speed with equipped load")
	Input.action_release("sprint")
	menu._close()

func _debug_health_checks() -> void:
	level.armor = 1
	level.infection = -1.0
	level._player_bitten()
	_check(level.armor == 0 and level.player_health == 100 and level.infection < 0.0, "armor blocks a bite")
	var health = level.health_hud
	_check(health.bar.value == 100.0 and health.status.text.is_empty()
		and health.frame_style.border_color == health.FRAME_COLOR, "blocked bite removes the reinforced frame only")
	level._player_bitten()
	_check(level.player_health == 75 and level.infection > 0.0, "unarmored bite removes health and starts infection")
	_check(health.bar.value == 75.0 and health.fill_style.bg_color == health.INFECTED_COLOR
		and health.status.text == "感染 30 秒", "unarmored bite turns the health bar green and starts at thirty")
	var menu: Control = level.interface.get_node("CombatDebug")
	var event := InputEventKey.new()
	event.physical_keycode = KEY_F6
	event.pressed = true
	menu._input(event)
	_check(menu.active and get_tree().paused and not walker.mouse_captured, "F6 opens and pauses live combat")
	var invincible: CheckButton = menu.find_child("Invincible", true, false)
	var flight: CheckButton = menu.find_child("Flight", true, false)
	var walking_mask := walker.collision_mask
	invincible.button_pressed = true
	flight.button_pressed = true
	_check(level.debug_invincible and level.infection < 0.0 and walker.flying, "F6 toggles invincibility and flight")
	level._player_bitten()
	_check(level.player_health == 75, "invincibility blocks bite damage")
	menu._input(event)
	_check(not get_tree().paused and walker.mouse_captured, "F6 resumes and recaptures the mouse")
	walker.set_physics_process(true)
	walker.camera.rotation = Vector3(0.35, 0, 0)
	var old_y := walker.global_position.y
	Input.action_press("move_forward")
	await _wait(18)
	Input.action_release("move_forward")
	_check(walker.global_position.y > old_y + 0.1, "flight moves upward with the camera")
	flight.button_pressed = false
	_check(not walker.flying and walker.collision_mask == walking_mask, "ending flight restores walking collisions")
	invincible.button_pressed = false
	for bite in 3:
		level._player_bitten()
	_check(level.player_health == 0 and level.round_finished and level.result_panel.visible
		and walker.movement_locked and level.infection == 0.0,
		"losing all health opens campaign defeat results and clears the countdown")

func _movement_checks() -> void:
	walker.position = Vector3(-15, 0.05, -5)
	walker.camera.rotation = Vector3.ZERO
	walker.rotation = Vector3.ZERO
	walker.velocity = Vector3.ZERO
	await _wait(8)
	Input.action_press("move_right")
	await _wait(1)
	var first_speed := absf(walker.velocity.x)
	await _wait(14)
	_check(first_speed > 0.0 and first_speed < walker.WALK_SPEED and absf(walker.velocity.x) > first_speed, "movement accelerates smoothly")
	Input.action_release("move_right")
	await _wait(24)
	_check(Vector2(walker.velocity.x, walker.velocity.z).length() < 0.03, "release decelerates to a stable stop")
	var standing: float = walker.camera.position.y
	Input.action_press("crouch")
	await _wait(2)
	_check(walker.camera.position.y < standing and walker.camera.position.y > walker.CROUCH_HEIGHT - 0.14, "crouch camera transitions gradually")
	await _wait(16)
	_check(walker.crouched and absf(walker.capsule.height - walker.CROUCH_HEIGHT) < 0.02, "crouched collider reaches target")
	Input.action_press("move_right")
	await _wait(12)
	_check(walker.look.animation.current_animation == "campus/crouch-walk" and walker.look.animation.speed_scale > 0.0, "crouch movement advances a bent-knee walk cycle")
	Input.action_release("move_right")
	await _wait(20)
	var ceiling := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2.5, 0.15, 2.5)
	shape.shape = box
	ceiling.add_child(shape)
	level.add_child(ceiling)
	ceiling.global_position = walker.global_position + Vector3.UP * 1.4
	await _wait(3)
	Input.action_release("crouch")
	await _wait(20)
	_check(walker.crouched and walker.capsule.height < 1.5, "overhead obstacle blocks standing")
	ceiling.queue_free()
	await _wait(20)
	_check(not walker.crouched and absf(walker.capsule.height - walker.standing_height) < 0.02, "standing resumes after overhead clearance")
	Input.action_press("jump")
	await _wait(3)
	_check(walker.velocity.y > 0.0, "jump works after stance transition")
	Input.action_release("jump")
	await _wait(50)
	_check(walker.is_on_floor(), "jump lands on actual floor")

func _capture(full: bool) -> void:
	for index in 3:
		guns.switch_weapon(index)
		await _wait(20)
		await RenderingServer.frame_post_draw
		var suffix := "campus" if full else "trial"
		get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/%s-%s.png" % [suffix, guns.weapon_id()])
	guns.switch_weapon(guns.loadout.find("rifle"))
	Input.action_press("aim")
	await _wait(25)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/aim.png")
	Input.action_release("aim")
	guns.ammo.rifle.mag = 10
	guns.ammo.rifle.reserve = 60
	_check(guns.reload_weapon(), "capture first-person reload actually starts")
	await _wait(45)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/reload.png")
	await _wait(85)
	walker._toggle_camera()
	await _wait(10)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/third-person.png")
	if full:
		walker.global_position = Vector3(-69.9, 0.30, -112.6)
		walker.velocity = Vector3.ZERO
		await _wait(20)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1280, 720)
	viewport.world_3d = get_viewport().world_3d
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	var side := Camera3D.new()
	viewport.add_child(side)
	side.global_position = walker.global_position + walker.global_basis * Vector3(2.2, 1.8, -1.7)
	side.look_at(walker.global_position + Vector3.UP * 1.2)
	side.make_current()
	await _wait(8)
	await RenderingServer.frame_post_draw
	viewport.get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/third-person-side.png")
	Input.action_press("aim")
	walker.camera.rotation.x = 0.35
	await _wait(8)
	await RenderingServer.frame_post_draw
	viewport.get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/third-person-aim.png")
	Input.action_release("aim")
	walker.camera.rotation.x = 0.0
	guns.cooldown = 0.0
	_check(guns.try_fire(), "capture third-person shot actually fires")
	await _wait(2)
	await RenderingServer.frame_post_draw
	viewport.get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/third-person-fire.png")
	guns.ammo.rifle.mag = 10
	guns.ammo.rifle.reserve = 60
	_check(guns.reload_weapon(), "capture third-person reload actually starts")
	await _wait(45)
	await RenderingServer.frame_post_draw
	viewport.get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/third-person-reload.png")
	await _wait(85)
	Input.action_press("crouch")
	Input.action_press("move_forward")
	await _wait(20)
	side.global_position = walker.global_position + walker.global_basis * Vector3(2.2, 1.8, -1.7)
	side.look_at(walker.global_position + Vector3.UP * 0.8)
	await RenderingServer.frame_post_draw
	viewport.get_texture().get_image().save_png("C:/CampusReconstructionRuntime/开源枪械接入/crouch-walk.png")
	Input.action_release("crouch")
	Input.action_release("move_forward")
	viewport.queue_free()
	walker._toggle_camera()

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _check(value: bool, label: String) -> void:
	print("FIREARMS ", "PASS " if value else "FAIL ", label)
	failed = failed or not value
