extends SceneTree

const Points = preload("res://scripts/campus/campus_survival_points.gd")
var failed := false
var face_cache := {}
var meshes: Array[MeshInstance3D] = []

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await scene_changed
	var world: Node3D = current_scene
	var walker: CharacterBody3D = world.get_node("Walker")
	walker.set_physics_process(false)
	for mesh: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh != null and mesh.is_visible_in_tree():
			meshes.append(mesh)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	for record: Dictionary in data.teaching_west_stairs.buildings:
		var corner := Points.point(record.corridor_path[0])
		var along := (Points.point(record.corridor_path[1]) - corner).normalized()
		var across := Vector3(-along.z, 0, along.x)
		var origin := corner - along * 2.5 - across * 2.45
		origin.y = 0
		var slope := 0.06350 if record.building == "B15" else 0.02548
		for floor in record.levels.size():
			var height := float(record.levels[floor])
			walker.global_position = origin + along * 2.0 + Vector3.UP * height
			world.refresh_collision()
			await physics_frame
			await physics_frame
			var visual_gaps := 0
			var collision_gaps := 0
			var probes: Array[Vector2] = []
			if floor > 0:
				for cross: float in [-4.0, -2.0, 0.0, 2.0, 4.0, 6.0]:
					var facade := 0.691 - slope * cross
					for depth: float in [0.06, 0.16]:
						probes.append(Vector2(cross, facade + depth))
				var east_positions := [78.5, 80.5, 82.0, 86.0, 89.0, 91.4] if record.building == "B15" \
					else [78.5, 80.5, 82.0, 84.0, 86.0, 88.9]
				for longitudinal: float in east_positions:
					for cross: float in [7.18, 7.24]:
						probes.append(Vector2(cross, longitudinal))
			for cross: float in [-7.20, 7.22]:
				for longitudinal: float in [1.15, 2.2, 3.4]:
					probes.append(Vector2(cross, longitudinal))
			for longitudinal: float in [9.1, 12.5, 14.2, 20.0, 35.0, 50.0, 65.0, 77.8]:
				for cross: float in [7.18, 7.24]:
					probes.append(Vector2(cross, longitudinal))
			for probe in probes:
				var at := origin + across * probe.x + along * probe.y + Vector3.UP * height
				var from := at + Vector3.UP * 0.22
				var to := at - Vector3.UP * 0.28
				if not visual_surface(from, to):
					visual_gaps += 1
				# Probe the slab itself below window-base beams, which can project
				# above the walking surface without leaving any opening below them.
				var hit := world.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(
					at + Vector3.UP * 0.04, at - Vector3.UP * 0.06, 1))
				if hit.is_empty() or absf(hit.position.y - height) > 0.04:
					collision_gaps += 1
					print("FLOOR COLLISION ", record.building, " F", floor + 1, " ", probe, " ", hit.get("position"), " ", hit.get("collider"))
			check(visual_gaps == 0 and collision_gaps == 0, "%s F%d floor perimeter: visual gaps %d, collision gaps %d / %d" % [record.building, floor + 1, visual_gaps, collision_gaps, probes.size()])
	print("CAMPUS FLOOR SEAMS ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func visual_surface(from: Vector3, to: Vector3) -> bool:
	for rendered in meshes:
		var local_from := rendered.to_local(from)
		var local_to := rendered.to_local(to)
		if rendered.get_aabb().grow(0.001).intersects_segment(local_from, local_to) == null:
			continue
		var id := rendered.mesh.get_instance_id()
		if not face_cache.has(id):
			face_cache[id] = floor_faces(rendered)
		var faces: PackedVector3Array = face_cache[id]
		for index in range(0, faces.size(), 3):
			var intersection: Variant = Geometry3D.segment_intersects_triangle(local_from, local_to, faces[index], faces[index + 1], faces[index + 2])
			if intersection != null and absf((rendered.global_transform * intersection).y - (from.y - 0.22)) < 0.04:
				return true
	return false

func floor_faces(rendered: MeshInstance3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	for surface in rendered.mesh.get_surface_count():
		var material := rendered.get_active_material(surface) as BaseMaterial3D
		if material != null and material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			continue
		var arrays := rendered.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if indices.is_empty():
			result.append_array(vertices)
		else:
			for index in indices:
				result.append(vertices[index])
	return result

func check(ok: bool, message: String) -> void:
	print("PASS " if ok else "FAIL ", message)
	failed = failed or not ok
