extends "res://tests/campus_bridge.gd"

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	var scene := tree.current_scene
	walker = scene.get_node("Walker")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	for building: Dictionary in data.teaching_east_stairs.buildings:
		walker.global_position = _point(building.corridor_join) + Vector3.UP * .04
		walker.velocity = Vector3.ZERO
		scene.refresh_collision()
		for frame in 12:
			walker._physics_process(1.0/60.0)
			await tree.physics_frame
		if not await _walk_route([building.corridor_points[0]], building.building):
			return
		for route: Dictionary in building.routes:
			if not await _walk_route(route.points, building.building):
				return
			var join: Vector3 = _point(building.corridor_join)
			join.y = float(building.levels[int(route.to_floor)-1])
			var corner: Array = building.corridor_points[int(route.to_floor)-1]
			if not await _walk_route([corner, _array(join), corner, route.points[-1]], building.building):
				return
		var descending: Array = building.routes.duplicate()
		descending.reverse()
		for route: Dictionary in descending:
			var points: Array = route.points.duplicate()
			points.reverse()
			if not await _walk_route(points, building.building):
				return
		if not await _walk_route([building.corridor_points[0], building.corridor_join], building.building):
			return
		print("EAST STAIRS PASS ", building.building, " five floors, corridor connections, ascent and descent")
	tree.quit()

func _array(point: Vector3) -> Array:
	return [point.x, -point.z, point.y]

func _walk_route(points: Array, building: String) -> bool:
	for point: Array in points:
		var target := _point(point)
		var reached := await _go(target)
		for frame in 20:
			walker._physics_process(1.0/60.0)
			await get_tree().physics_frame
		if not reached or absf(walker.global_position.y-target.y) > .24:
			print("EAST STAIRS FAIL ", building, " at ", walker.global_position, " target ", target)
			var ray := PhysicsRayQueryParameters3D.create(walker.global_position + Vector3.UP * .1, walker.global_position - Vector3.UP, 1)
			print("EAST STAIRS FLOOR ", walker.get_world_3d().direct_space_state.intersect_ray(ray))
			var above := KinematicCollision3D.new()
			if walker.test_move(walker.global_transform, Vector3.UP * .20, above):
				print("STAIR HEADROOM ", above.get_collider(), " at ", above.get_position())
			var direction := target-walker.global_position
			direction.y = 0
			if walker.test_move(walker.global_transform.translated(Vector3.UP*.19), direction.normalized()*.12, above):
				print("STAIR RAISED CONTACT ", above.get_collider(), " at ", above.get_position())
			if has_method("_capture"):
				await call("_capture", walker.global_position+Vector3.UP*1.59,
					target+Vector3.UP*1.20, building+"-stair-block.png")
			get_tree().quit(1)
			return false
	return true
