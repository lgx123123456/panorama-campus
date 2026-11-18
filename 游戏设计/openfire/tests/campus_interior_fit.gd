extends "res://tests/campus_dorm_stairs.gd"

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	var scene := tree.current_scene
	walker = scene.get_node("Walker")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	var capture_only := "--capture-only" in OS.get_cmdline_user_args()
	for stairs: Dictionary in data.teaching_west_stairs.buildings:
		var base := _point(stairs.corridor_points[0])
		walker.global_position = base + Vector3.UP * .04
		walker.velocity = Vector3.ZERO
		scene.refresh_collision()
		for frame in 12:
			walker._physics_process(1.0/60.0)
			await tree.physics_frame
		# The west door view looks east, with the north-side classrooms on the left.
		await _capture(base + Vector3.UP * 1.59, base + Vector3(18,1.59,0), stairs.building+"-west-interior.png")
		if capture_only:
			var door: Dictionary = data.doors.filter(func(item): return item.building == stairs.building and item.has("bridge") and float(item.outward[1]) < 0)[0]
			var capture_eye := _point(door.center) + Vector3(0,1.59,1.25)
			await _capture(capture_eye, capture_eye+Vector3(0,0,-8), stairs.building+"-east-interior.png")
			continue
		var route: Dictionary = stairs.routes[0]
		if not await _walk_route(route.points, stairs.building):
			return
		var reverse: Array = route.points.duplicate()
		reverse.reverse()
		if not await _walk_route(reverse, stairs.building):
			return
		print("WEST FIT PASS ", stairs.building, " right-hand stair ascent and descent")
		var east: Dictionary = data.teaching_east_stairs.buildings.filter(func(item): return item.building == stairs.building)[0]
		# Skirt the west stairwell before joining the south-side main corridor.
		if not await _walk_route(stairs.corridor_path, stairs.building):
			return
		var entry: Dictionary = data.doors.filter(func(item): return item.building == stairs.building and item.has("bridge") and float(item.outward[1]) < 0)[0]
		var eye := _point(entry.center) + Vector3(0,1.59,1.25)
		await _capture(eye, eye+Vector3(0,0,-8), stairs.building+"-east-interior.png")
		print("INTERIOR FIT PASS ", stairs.building, " west foyer to south corridor and east stair")
	if data.has("teaching_offices"):
		for building: Dictionary in data.teaching_offices:
			for office: Dictionary in building.offices:
				if int(office.floor) not in [1, 5]:
					continue
				var path: Array = office.path.duplicate()
				await _place(scene, path[0])
				if not capture_only and not await _walk_route(path, office.door_id):
					return
				if int(office.floor) == 1:
					await _capture(_point(path[-1])+Vector3.UP*1.59,
						_point(path[-1])+Vector3(0,1.59,-5),office.door_id+".png")
				if not capture_only:
					path.reverse()
					if not await _walk_route(path, office.door_id):
						return
			print("TEACHER OFFICES PASS ", building.building, " both spaces, first and top floors")
	tree.quit()
