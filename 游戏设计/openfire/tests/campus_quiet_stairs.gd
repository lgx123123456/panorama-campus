extends Node
var walker: CharacterBody3D
var failed := false
func _ready() -> void:
	call_deferred("_run")
func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await tree.scene_changed
	var world := tree.current_scene
	var level := world.get_node("CharacterTrial")
	walker = level.walker
	walker.set_physics_process(false)
	level.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.set_debug_invincible(true)
	level.firearms.grant_supply("rifle", 100, true)
	level.firearms.switch_weapon(level.firearms.loadout.find("rifle"))
	walker.quiet = true
	walker._capture_mouse(true)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	var cases: Array[Dictionary] = []
	for group: String in ["teaching_west_stairs", "teaching_east_stairs"]:
		for building: Dictionary in data[group].buildings:
			cases.append({"label": building.building + " " + group, "points": building.routes[0].points})
	for dorm: Dictionary in data.dorm_layouts:
		for key: String in ["mid", "west", "east"]:
			cases.append({"label": dorm.building + " " + key, "points": dorm.stairs[key].routes[0].points})
	for record: Dictionary in cases:
		var points: Array = record.points
		walker.global_position = _point(points[0]) + Vector3.UP * 0.04
		walker.velocity = Vector3.ZERO
		world.refresh_collision()
		for frame in 18:
			walker._physics_process(get_physics_process_delta_time())
			await tree.physics_frame
		var passed := await _route(points)
		if passed:
			var descending := points.duplicate()
			descending.reverse()
			passed = await _route(descending)
		print("QUIET CAMPUS ", "PASS " if passed else "FAIL ", record.label, " ascent and descent at ", walker.global_position)
		failed = failed or not passed
	print("QUIET CAMPUS ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)
func _point(point: Array) -> Vector3:
	return Vector3(float(point[0]), float(point[2]), -float(point[1]))
func _route(points: Array) -> bool:
	for value: Array in points:
		var target := _point(value)
		var reached := false
		for frame in 1400:
			var direction := target - walker.global_position
			direction.y = 0
			if direction.length() < 0.12:
				reached = absf(walker.global_position.y - target.y) < 0.24
				break
			walker.look_at(walker.global_position + direction)
			Input.action_press("move_forward")
			walker._physics_process(get_physics_process_delta_time())
			await get_tree().physics_frame
		Input.action_release("move_forward")
		if not reached:
			print("QUIET TARGET ", target, " from ", walker.global_position, " floor=",walker.is_on_floor(), " wall=",walker.is_on_wall())
			for index in walker.get_slide_collision_count():
				var hit := walker.get_slide_collision(index)
				print("QUIET CONTACT ", hit.get_collider(), " ", hit.get_position(), " ", hit.get_normal())
			return false
	return true
