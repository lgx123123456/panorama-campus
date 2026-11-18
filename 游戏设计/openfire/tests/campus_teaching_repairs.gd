extends SceneTree


const Points := preload("res://scripts/campus/campus_survival_points.gd")

var failed := false

func _initialize() -> void:
	Engine.physics_ticks_per_second = 180
	Engine.time_scale = 3.0
	run.call_deferred()

func run() -> void:
	change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await scene_changed
	var world = current_scene
	var walker = world.get_node("Walker")
	var doors = world.get_node("Doors")
	walker.set_physics_process(false)
	walker._capture_mouse(true)
	var key := InputEventKey.new()
	key.physical_keycode = KEY_E
	key.pressed = true
	for door_record: Dictionary in Points.classroom_doors({}):
		var id: String = door_record.id
		var index: int = doors._index_for_id(id)
		var door: Dictionary = doors.doors[index]
		var outward: Vector3 = door.outward
		var center: Vector3 = door.center
		var inside := center + Vector3.UP * 0.12 - outward * 0.52
		var outside := center + Vector3.UP * 0.12 + outward * 0.52
		var target := center + Vector3.UP * 0.12 + outward * 1.90
		await place(world, walker, target, center)
		walker._input(key)
		await create_timer(0.42).timeout
		check(doors.nearby == index and not door.open and not door.moving, "%s closes from the corridor with E" % id)
		await place(world, walker, inside, center)
		var hit := KinematicCollision3D.new()
		var blocked: bool = await walk_motion(walker, outside - inside, hit)
		check(blocked and hit.get_collider().name == &"NativeDoorCollision", "%s closed leaf blocks capsule (%s)" % [id, hit.get_collider().name if blocked else "clear"])
		await place(world, walker, target, center)
		walker._input(key)
		await create_timer(0.42).timeout
		check(door.open and not door.moving, "%s opens from the corridor with E" % id)
		await place(world, walker, inside, center)
		hit = KinematicCollision3D.new()
		blocked = await walk_motion(walker, outside - inside, hit)
		check(not blocked, "%s open doorway passes capsule (%s)" % [id, hit.get_collider().name if blocked else "clear"])
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	for record: Dictionary in data.teaching_west_stairs.buildings:
		var corner := Points.point(record.corridor_path[0])
		var along := (Points.point(record.corridor_path[1]) - corner).normalized()
		var across := Vector3(-along.z, 0, along.x)
		var origin := corner - along * 2.5 - across * 2.45
		for floor in record.levels.size():
			var p := origin + along * 42.0 + across * 7.0
			p.y = float(record.levels[floor]) + 1.48
			await place(world, walker, p - Vector3.UP * 1.48, p + across)
			var query := PhysicsRayQueryParameters3D.create(p, p + across * 0.32, 1)
			var window: Dictionary = walker.get_world_3d().direct_space_state.intersect_ray(query)
			check(not window.is_empty() and window.collider.name == &"CorridorWindowCollision",
				"%s F%d has closed corridor glazing" % [record.building, floor + 1])
			if record.building == "B15" and floor >= 2:
				p += along * 44.0
				await place(world, walker, p - Vector3.UP * 1.48, p + across)
				query = PhysicsRayQueryParameters3D.create(p, p + across * 0.45, 1)
				window = walker.get_world_3d().direct_space_state.intersect_ray(query)
				check(not window.is_empty() and window.collider.name == &"TowerGlazingCollision", "B15 F%d has new tower glazing" % (floor + 1))
	print("TEACHING REPAIR ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func place(world: Node, walker: CharacterBody3D, position: Vector3, direction: Vector3) -> void:
	walker.global_position = position
	walker.look_at(Vector3(direction.x, position.y, direction.z))
	world.refresh_collision()
	await physics_frame
	await physics_frame

func check(ok: bool, what: String) -> void:
	print("PASS " if ok else "FAIL ", what)
	failed = failed or not ok

func walk_motion(walker: CharacterBody3D, motion: Vector3, collision: KinematicCollision3D) -> bool:
	for step in 34:
		if walker.test_move(walker.global_transform, motion / 34.0, collision):
			return true
		walker.move_and_collide(motion / 34.0)
		await physics_frame
	return false



