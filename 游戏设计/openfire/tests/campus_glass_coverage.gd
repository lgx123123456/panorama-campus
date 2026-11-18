extends SceneTree

const Points = preload("res://scripts/campus/campus_survival_points.gd")
var failed := false

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await scene_changed
	var world = current_scene
	var walker = world.get_node("Walker")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	for record in data.teaching_west_stairs.buildings:
		var c := Points.point(record.corridor_path[0])
		var along := (Points.point(record.corridor_path[1]) - c).normalized()
		var across := Vector3(-along.z, 0, along.x)
		var origin := c - along * 2.5 - across * 2.45
		origin.y = 0
		var faces := _glass_faces(world, origin + along * 0.7 + Vector3.UP * 10.0, 19.0)
		for floor in range(1, record.levels.size()):
			walker.position = origin + along * 2.5
			walker.position.y = float(record.levels[floor])
			world.refresh_collision()
			await physics_frame
			await physics_frame
			var missing_visual := 0
			var missing_collision := 0
			for x: float in [-4.7, -3.2, -1.0, 0.0, 1.0, 3.2, 4.7]:
				for y: float in [0.42, 1.3, 2.1]:
					var center := origin + across * x + Vector3.UP * (float(record.levels[floor]) + y)
					var inside := center + along * 1.7
					var outside := center - along * 0.6
					if not _intersects_glass(inside, outside, faces):
						missing_visual += 1
					if world.get_world_3d().direct_space_state.intersect_ray(
							PhysicsRayQueryParameters3D.create(inside, outside, 1)).is_empty():
						missing_collision += 1
						print("COLLISION GAP ", record.building, " F", floor + 1, " x=", x, " y=", y)
			_check(missing_visual == 0 and missing_collision == 0,
				"%s F%d west window grid: visible gaps %d, collision gaps %d / 21" % [record.building, floor + 1, missing_visual, missing_collision])
		# Audit the full corridor band on every floor, and the tower windows
		# above the bridge level. Genuine bridge openings stay outside these grids.
		var side_faces := _glass_faces(world, origin + along * 48.0 + Vector3.UP * 10.0, 52.0)
		for floor in record.levels.size():
			var level := float(record.levels[floor])
			walker.position = origin + along * 46.0 + across * 5.0 + Vector3.UP * level
			world.refresh_collision()
			await physics_frame
			await physics_frame
			var misses := Vector2i.ZERO
			var count := 0
			for step in 65:
				for height: float in [1.12, 1.82, 2.52]:
					var center := origin + along * (14.1 + step * 0.995) + across * 7.28 + Vector3.UP * (level + height)
					misses += _probe(world, center - across * 0.3, center + across * 0.3, side_faces)
					count += 1
			_check(misses == Vector2i.ZERO, "%s F%d corridor: visual/collision gaps %s / %d" % [record.building, floor + 1, misses, count])
			if floor < 2:
				continue
			walker.position = origin + along * 86.0 + across * 5.0 + Vector3.UP * level
			world.refresh_collision()
			await physics_frame
			await physics_frame
			misses = Vector2i.ZERO
			count = 0
			# B21's opaque structural pier ends at longitudinal 84.40.
			var start := 81.3 if record.building == "B15" else 84.5
			var spacing := 0.86 if record.building == "B15" else 0.37
			for step in 12:
				for height: float in [1.12, 1.82, 2.52]:
					var center := origin + along * (start + step * spacing) + across * 7.28 + Vector3.UP * (level + height)
					misses += _probe(world, center - across * 0.3, center + across * 0.5, side_faces)
					count += 1
			_check(misses == Vector2i.ZERO, "%s F%d east tower: visual/collision gaps %s / %d" % [record.building, floor + 1, misses, count])
	print("CAMPUS GLASS COVERAGE ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func _probe(world: Node3D, from: Vector3, to: Vector3, faces: PackedVector3Array) -> Vector2i:
	return Vector2i(0 if _intersects_glass(from, to, faces) else 1,
		1 if world.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(from, to, 1)).is_empty() else 0)

func _glass_faces(world: Node, center: Vector3, radius: float) -> PackedVector3Array:
	var result := PackedVector3Array()
	for node: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null or not node.is_visible_in_tree():
			continue
		var bounds: AABB = node.global_transform * node.get_aabb()
		if bounds.get_center().distance_to(center) > radius + bounds.size.length() * 0.5:
			continue
		for surface in node.mesh.get_surface_count():
			var material := node.get_active_material(surface) as BaseMaterial3D
			if material == null or material.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED:
				continue
			if "玻璃" not in material.resource_name and "Glaz" not in node.name and "Liner" not in node.name:
				continue
			var arrays: Array = node.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty():
				for point in vertices:
					result.append(node.global_transform * point)
			else:
				for index in indices:
					result.append(node.global_transform * vertices[index])
	return result

func _intersects_glass(from: Vector3, to: Vector3, faces: PackedVector3Array) -> bool:
	for n in range(0, faces.size(), 3):
		if Geometry3D.segment_intersects_triangle(from, to, faces[n], faces[n + 1], faces[n + 2]) != null:
			return true
	return false

func _check(ok: bool, message: String) -> void:
	print("PASS " if ok else "FAIL ", message)
	failed = failed or not ok
