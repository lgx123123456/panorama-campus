extends "res://tests/campus_east_stairs.gd"

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	var scene := tree.current_scene
	walker = scene.get_node("Walker")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	if data.has("dorm_layouts"):
		if "--capture-only" in OS.get_cmdline_user_args():
			await _capture_new_layouts(scene, data.dorm_layouts)
		elif "--end-doors-only" in OS.get_cmdline_user_args():
			if not await _check_new_end_doors(scene, data):
				return
		elif not await _check_new_layouts(scene, data):
			return
		tree.quit()
		return
	var stairs: Dictionary = data.dorm_lobby_stairs
	if "--capture-only" in OS.get_cmdline_user_args():
		await _capture_layout(scene, stairs)
		if data.has("dorm_end_stairs"):
			await _capture_additions(scene, data)
		tree.quit()
		return
	walker.global_position = _point(stairs.lobby_route[0]) + Vector3.UP * .04
	walker.velocity = Vector3.ZERO
	scene.refresh_collision()
	await _capture(_point(stairs.lobby_route[0]) + Vector3.UP * 1.59,
		_point(stairs.lobby_route[1]) + Vector3.UP * 1.59, "dorm-lobby-front.png")
	for frame in 12:
		walker._physics_process(1.0/60.0)
		await tree.physics_frame
	if not await _walk_route(stairs.lobby_route.slice(1), stairs.building):
		return
	print("DORM LOBBY PASS entrance, north dormitory row doorway, stair landing")
	await _capture(walker.global_position + Vector3.UP * 1.59,
		_point(stairs.routes[0].points[2]) + Vector3.UP * 1.1, "dorm-right-stairs.png")
	if stairs.has("corridor_end_routes"):
		if not await _check_floor(stairs, 0):
			return
	for route: Dictionary in stairs.routes:
		if not await _walk_route(route.points, stairs.building):
			return
		var path: Array = stairs.corridor_paths[int(route.to_floor)-1].duplicate()
		if not await _walk_route(path, stairs.building):
			return
		if stairs.has("corridor_end_routes") and int(route.to_floor) == stairs.levels.size():
			if not await _check_floor(stairs, int(route.to_floor)-1):
				return
		path.reverse()
		if not await _walk_route(path, stairs.building):
			return
	var descending: Array = stairs.routes.duplicate()
	descending.reverse()
	for route: Dictionary in descending:
		var points: Array = route.points.duplicate()
		points.reverse()
		if not await _walk_route(points, stairs.building):
			return
	var exit_route: Array = stairs.lobby_route.duplicate()
	exit_route.reverse()
	if not await _walk_route(exit_route, stairs.building):
		return
	print("DORM STAIRS PASS seven floors, corridor connections, ascent, descent and lobby return")
	if data.has("dorm_end_stairs"):
		if not await _check_additions(scene, data):
			return
	tree.quit()

func _check_new_layouts(scene: Node, data: Dictionary) -> bool:
	for layout: Dictionary in data.dorm_layouts:
		var building: String = layout.building
		await _place(scene, layout.lobby_route[0])
		if not await _walk_route(layout.lobby_route, building + " lobby"):
			return false
		for key in ["mid", "west", "east"]:
			var stair: Dictionary = layout.stairs[key]
			await _place(scene, stair.corridor_paths[0][0])
			if not await _walk_route(stair.corridor_paths[0], building + " " + key):
				return false
			for route: Dictionary in stair.routes:
				if not await _walk_route(route.points, building + " " + key):
					return false
				var exit_path: Array = stair.corridor_paths[int(route.to_floor)-1].duplicate()
				exit_path.reverse()
				if not await _walk_route(exit_path, building + " " + key + " floor exit"):
					return false
				exit_path.reverse()
				if not await _walk_route(exit_path, building + " " + key + " floor entry"):
					return false
			var descending: Array = stair.routes.duplicate()
			descending.reverse()
			for route: Dictionary in descending:
				var path: Array = route.points.duplicate()
				path.reverse()
				if not await _walk_route(path, building + " " + key + " descent"):
					return false
			print("DORM THREE-STAIR PASS ", building, " ", key, " seven floors")
		for floor in [0, layout.levels.size()-1]:
			var level: Dictionary = layout.levels[floor]
			await _place(scene, level.corridor[0])
			if not await _walk_route(level.corridor, building + " full corridor"):
				return false
			for side in [-1, 1]:
				var rooms: Array = level.rooms.filter(func(room): return room.side == side)
				for index in [0, rooms.size()/2, rooms.size()-1]:
					var path: Array = rooms[index].path
					await _place(scene, path[0])
					if not await _walk_route(path, building + " room"):
						return false
			for toilet: Dictionary in layout.toilets.values():
				var path: Array = toilet.paths[floor]
				await _place(scene, path[0])
				if not await _walk_route(path, building + " toilet"):
					return false
		print("DORM FIT PASS ", building, " lobby, full corridor, rooms and toilets")
	return await _check_new_end_doors(scene, data)

func _check_new_end_doors(scene: Node, data: Dictionary) -> bool:
	for door: Dictionary in data.get("dorm_end_doors", []):
		await _place(scene, door.points[0])
		if not await _walk_route(door.points, door.id):
			return false
		var back: Array = door.points.duplicate()
		back.reverse()
		if not await _walk_route(back, door.id + " return"):
			return false
	print("DORM END DOORS PASS exterior thresholds and main corridor")
	return true

func _capture_new_layouts(scene: Node, layouts: Array) -> void:
	for layout: Dictionary in layouts:
		var bid: String = layout.building
		for key in ["mid", "west", "east"]:
			var points: Array = layout.stairs[key].routes[0].points
			await _place(scene, points[0])
			await _capture(_point(points[0])+Vector3.UP*1.55,
				_point(points[2])+Vector3.UP*1.05, "dorm-layout-"+bid+"-"+key+".png")
		var path: Array = layout.levels[0].corridor
		await _place(scene, path[1])
		await _capture(_point(path[1])+Vector3.UP*1.59,
			_point(path[-1])+Vector3.UP*1.59, "dorm-layout-"+bid+"-corridor.png")
		var room: Dictionary = layout.levels[0].rooms[layout.levels[0].rooms.size()/2]
		await _place(scene, room.path[1])
		var inside := _point(room.path[1])
		var direction := (inside - _point(room.path[0])).normalized()
		await _capture(inside+Vector3.UP*1.57, inside+direction*4.0+Vector3.UP*1.50,
			"dorm-layout-"+bid+"-room.png")

func _place(scene: Node, position: Array) -> void:
	walker.global_position = _point(position)+Vector3.UP*.04
	walker.velocity = Vector3.ZERO
	scene.refresh_collision()
	for frame in 12:
		walker._physics_process(1.0/60.0)
		await get_tree().physics_frame

func _check_additions(scene: Node, data: Dictionary) -> bool:
	for stairs: Dictionary in data.dorm_end_stairs:
		await _place(scene, stairs.corridor_paths[0][0])
		if not await _walk_route(stairs.corridor_paths[0], stairs.side):
			return false
		for route: Dictionary in stairs.routes:
			if not await _walk_route(route.points, stairs.side):
				return false
			var path: Array = stairs.corridor_paths[int(route.to_floor)-1].duplicate()
			path.reverse()
			if not await _walk_route(path, stairs.side):
				return false
			path.reverse()
			if not await _walk_route(path, stairs.side):
				return false
		var descending: Array = stairs.routes.duplicate()
		descending.reverse()
		for route: Dictionary in descending:
			var path: Array = route.points.duplicate()
			path.reverse()
			if not await _walk_route(path, stairs.side):
				return false
		print("DORM END STAIRS PASS ", stairs.side, " seven floors and south entry")
	for toilet: Dictionary in data.dorm_toilets:
		for floor in [0, 6]:
			var path: Array = toilet.paths[floor].duplicate()
			await _place(scene, path[0])
			if not await _walk_route(path, toilet.side+" toilet"):
				return false
			path.reverse()
			if not await _walk_route(path, toilet.side+" toilet"):
				return false
		print("DORM TOILET PASS ", toilet.side)
	for door: Dictionary in data.dorm_end_doors:
		await _place(scene, door.points[0])
		if not await _walk_route(door.points, door.id):
			return false
	print("DORM END DOORS PASS both entrances and outside ramps")
	if not await _check_door_states(scene, data):
		return false
	return true

func _check_door_states(scene: Node, data: Dictionary) -> bool:
	var controller := scene.get_node("Doors")
	for index in data.doors.size():
		var record: Dictionary = data.doors[index]
		if record.id not in ["B25", "B25_west_end", "B25_east_end", "B15_office_1_1", "B15_office_2_1", "B21_office_1_1", "B21_office_2_1"]:
			continue
		var center := _point(record.center)
		var outward := Vector3(float(record.outward[0]), 0, -float(record.outward[1]))
		walker.global_position = center+outward*3.0+Vector3.UP*.04
		controller.set_open(index, false)
		await get_tree().create_timer(.4).timeout
		walker.global_position = center+outward*.85+Vector3.UP*.04
		scene.refresh_collision()
		await get_tree().physics_frame
		var contact := KinematicCollision3D.new()
		if not walker.test_move(walker.global_transform, -outward*1.7, contact) or contact.get_collider().name != "DoorCollision":
			print("DOOR CLOSE FAIL ", record.id)
			get_tree().quit(1)
			return false
		walker.global_position = center+outward*3.0+Vector3.UP*.04
		controller.set_open(index, true)
		await get_tree().create_timer(.4).timeout
		walker.global_position = center+outward*.85+Vector3.UP*.04
		await get_tree().physics_frame
		if walker.test_move(walker.global_transform, -outward*1.7, contact):
			print("DOOR OPEN FAIL ", record.id, " ", contact.get_collider())
			get_tree().quit(1)
			return false
	print("ADDED DOORS PASS open passage and closed blocking")
	return true

func _capture_additions(scene: Node, data: Dictionary) -> void:
	for door: Dictionary in data.dorm_end_doors:
		await _place(scene, door.points[0])
		await _capture(_point(door.points[0])+Vector3.UP*1.59,
			_point(door.points[-1])+Vector3.UP*1.59,door.id+".png")
	for stairs: Dictionary in data.dorm_end_stairs:
		await _place(scene, stairs.routes[0].points[0])
		await _capture(walker.global_position+Vector3.UP*1.59,
			_point(stairs.routes[0].points[2])+Vector3.UP*1.10,"dorm-"+stairs.side+"-end-stair.png")
	for toilet: Dictionary in data.dorm_toilets:
		await _place(scene, toilet.paths[0][1])
		var direction := (_point(toilet.paths[0][1])-_point(toilet.paths[0][0])).normalized()
		await _capture(walker.global_position+Vector3.UP*1.59,
			walker.global_position+direction*5+Vector3.UP*1.59,"dorm-"+toilet.side+"-toilet.png")

func _capture_layout(scene: Node, stairs: Dictionary) -> void:
	var lobby_eye := _point(stairs.lobby_route[0])
	var corridor_eye := _point(stairs.corridor_points[0])
	var stair_eye := _point(stairs.routes[0].points[0])
	var room: Array = stairs.room_checks[0][0]
	var room_eye := _point(room[1])
	var room_direction := (room_eye-_point(room[0])).normalized()
	var views: Array = [
		[lobby_eye, _point(stairs.lobby_route[1]), "dorm-lobby-front.png"],
		[corridor_eye, stair_eye, "dorm-north-stair-entry.png"],
		[stair_eye, _point(stairs.routes[0].points[2]), "dorm-eastward-stair.png"],
		[corridor_eye, _point(stairs.corridor_end_routes[0][-1]), "dorm-fitted-corridor.png"],
		[room_eye, room_eye+room_direction*6, "dorm-fitted-room.png"]
	]
	for view: Array in views:
		walker.global_position = view[0]+Vector3.UP*.04
		scene.refresh_collision()
		await _capture(view[0]+Vector3.UP*1.59,view[1]+Vector3.UP*1.59,view[2])

func _check_floor(stairs: Dictionary, floor: int) -> bool:
	var to_corridor: Array = stairs.corridor_paths[floor].duplicate()
	if not await _walk_route(to_corridor, stairs.building):
		return false
	var ends: Array = stairs.corridor_end_routes[floor]
	await _capture(_point(to_corridor[-1])+Vector3.UP*1.59,
		_point(ends[-1])+Vector3.UP*1.59, "dorm-fitted-corridor-%d.png" % floor)
	if not await _walk_route(ends, stairs.building):
		return false
	for room: Array in stairs.room_checks[floor]:
		if not await _walk_route(room, stairs.building):
			return false
		await _capture(_point(room[1])+Vector3.UP*1.59,
			_point(room[0])+Vector3.UP*1.59, "dorm-fitted-room-%d.png" % floor)
	to_corridor.reverse()
	if not await _walk_route(to_corridor, stairs.building):
		return false
	print("DORM FIT PASS floor ", floor+1, " continuous corridor and north/south room entries")
	return true

func _capture(eye: Vector3, target: Vector3, filename: String) -> void:
	if DisplayServer.get_name() == "headless":
		return
	var camera: Camera3D = walker.get_node("Camera3D")
	var original := camera.transform
	camera.global_position = eye
	camera.look_at(target)
	for frame in 8:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("res://.tools/validation/" + filename)
	camera.transform = original
