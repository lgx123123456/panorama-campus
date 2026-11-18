extends "res://scripts/campus/bake_field_passages.gd"

const Repair = preload("res://scripts/campus/campus_dorm_access_repairs.gd")
var stair_cases: Array[Dictionary] = []

func _bake() -> void:
	var records: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Repair.ENTRANCES))
	for building: Dictionary in records.dorm_layouts:
		for key: String in ["west", "east"]:
			stair_cases.append({"building": building.building, "side": key,
				"frame": Repair.source_frame(building.stairs[key].stair_frame), "levels": building.levels})
	var visual := (load(MASTER_VISUAL) as PackedScene).instantiate()
	var collision := (load(MASTER_COLLISION) as PackedScene).instantiate()
	root.add_child(visual)
	root.add_child(collision)
	var existing: Resource = load(Passage.DATA_PATH)
	var collision_names := {}
	for body: StaticBody3D in collision.get_children():
		collision_names[body.name] = true
	var data := PassageData.new()
	var mirrored := 0
	var opened := 0
	for node: MeshInstance3D in visual.find_children("*", "MeshInstance3D", true, false):
		# Compose after the stand patch, matching campus_world's installation order.
		if existing.visual_meshes.has(node.name):
			node.mesh = existing.visual_meshes[node.name]
		if not str(node.name).begins_with("B25 宿舍贴合室内 ") and not str(node.name).begins_with("B28 宿舍贴合室内 "):
			continue
		var stair := _stair_mesh(node)
		var replacement: ArrayMesh
		if not stair.is_empty():
			replacement = _reflect_mesh(node, stair.frame)
			mirrored += 1
		else:
			replacement = _clip_mesh(node)
			if replacement != null:
				opened += 1
		if replacement == null:
			continue
		data.visual_meshes[node.name] = replacement
		var collider_name := StringName(str(node.name) + "Collision")
		if collision_names.has(collider_name):
			data.collision_shapes[collider_name] = replacement.create_trimesh_shape()
	var result := ResourceSaver.save(data, Repair.DATA_PATH, ResourceSaver.FLAG_COMPRESS)
	print("DORM ACCESS BAKE mirrored=", mirrored, " opened=", opened,
		" visual=", data.visual_meshes.size(), " collision=", data.collision_shapes.size(), " result=", result)
	visual.free()
	collision.free()
	quit(0 if result == OK and mirrored > 100 and opened >= 2 else 1)

func _stair_mesh(node: MeshInstance3D) -> Dictionary:
	for stair: Dictionary in stair_cases:
		if not str(node.name).begins_with(str(stair.building) + " "):
			continue
		var transform: Transform3D = (stair.frame as Transform3D).affine_inverse() * node.global_transform
		var bounds := transform * node.get_aabb()
		if bounds.position.x > -1.66 and bounds.end.x < 1.66 and bounds.position.y > 0.30 and bounds.end.y < 5.05:
			return stair
	return {}

func _reflect_mesh(node: MeshInstance3D, frame: Transform3D) -> ArrayMesh:
	var transform := node.global_transform.affine_inverse() * Repair.stair_mirror(frame) * node.global_transform
	var normal_transform := transform.basis.inverse().transposed()
	var result := ArrayMesh.new()
	for surface in node.mesh.get_surface_count():
		var arrays := node.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for i in vertices.size():
			vertices[i] = transform * vertices[i]
		arrays[Mesh.ARRAY_VERTEX] = vertices
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		for i in normals.size():
			normals[i] = (normal_transform * normals[i]).normalized()
		arrays[Mesh.ARRAY_NORMAL] = normals
		if arrays[Mesh.ARRAY_TANGENT] != null:
			var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
			for i in range(0, tangents.size(), 4):
				var tangent := (transform.basis * Vector3(tangents[i], tangents[i + 1], tangents[i + 2])).normalized()
				tangents[i] = tangent.x
				tangents[i + 1] = tangent.y
				tangents[i + 2] = tangent.z
				tangents[i + 3] = -tangents[i + 3]
			arrays[Mesh.ARRAY_TANGENT] = tangents
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if indices.is_empty():
			indices.resize(vertices.size())
			for i in vertices.size():
				indices[i] = i
		for i in range(0, indices.size(), 3):
			var saved := indices[i + 1]
			indices[i + 1] = indices[i + 2]
			indices[i + 2] = saved
		arrays[Mesh.ARRAY_INDEX] = indices
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		result.surface_set_material(surface, node.mesh.surface_get_material(surface))
	return result

func _fragments(points: Array, transform: Transform3D) -> Array:
	var world := [transform * points[0], transform * points[1], transform * points[2]]
	var polygons := [ORIGINAL_VERTICES]
	for stair: Dictionary in stair_cases:
		var inverse: Transform3D = (stair.frame as Transform3D).affine_inverse()
		var local := [inverse * world[0], inverse * world[1], inverse * world[2]]
		var lower: Vector3 = local[0].min(local[1]).min(local[2])
		var upper: Vector3 = local[0].max(local[1]).max(local[2])
		for level: Dictionary in stair.levels:
			var opening := AABB(Vector3(-0.62 - 0.875 / 1.20, 5.58, float(level.z) - 0.008),
				Vector3(1.24 + 1.75 / 1.20, 0.44, 2.238))
			if not _overlaps(lower, upper, opening):
				continue
			var outside: Array = []
			for polygon: Array in polygons:
				_subtract_box(polygon, local, opening, outside)
			polygons = outside
	return polygons
