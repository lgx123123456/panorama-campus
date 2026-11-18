extends SceneTree

# Clip the merged stand meshes and matching collision surfaces in campus space.
# godot --headless --path . --script res://scripts/campus/bake_field_passages.gd
const Passage := preload("res://scripts/campus/campus_field_passages.gd")
const PassageData := preload("res://scripts/campus/campus_field_passage_data.gd")
const MASTER_VISUAL := "res://assets/campus/campus_full.glb"
const MASTER_COLLISION := "res://assets/campus/campus_full_collision.scn"
const ORIGINAL_VERTICES := [Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1)]


func _initialize() -> void:
	_bake.call_deferred()


func _bake() -> void:
	var visual := (load(MASTER_VISUAL) as PackedScene).instantiate()
	var collision := (load(MASTER_COLLISION) as PackedScene).instantiate()
	root.add_child(visual)
	root.add_child(collision)
	var data := PassageData.new()
	for node: MeshInstance3D in visual.find_children("*", "MeshInstance3D", true, false):
		if not _matches(node, node.global_transform * node.get_aabb()):
			continue
		var replacement := _clip_mesh(node)
		if replacement != null:
			data.visual_meshes[node.name] = replacement
			print("Opened visual: ", node.name)
	for body: StaticBody3D in collision.get_children():
		if not _matches(body, body.get_meta("bounds")):
			continue
		var collider := body.get_child(0) as CollisionShape3D
		var source := collider.shape as ConcavePolygonShape3D
		var faces := source.get_faces()
		var result := PackedVector3Array()
		var changed := false
		for i in range(0, faces.size(), 3):
			var points := [faces[i], faces[i + 1], faces[i + 2]]
			var fragments := _fragments(points, body.global_transform)
			if fragments.size() == 1 and fragments[0] == ORIGINAL_VERTICES:
				result.append_array(points)
			else:
				changed = true
				for polygon: Array in fragments:
					for k in range(1, polygon.size() - 1):
						for weight: Vector3 in [polygon[0], polygon[k], polygon[k + 1]]:
							result.append(_blend(points, weight))
		if changed:
			var replacement := ConcavePolygonShape3D.new()
			replacement.backface_collision = source.backface_collision
			replacement.set_faces(result)
			data.collision_shapes[body.name] = replacement
			print("Opened collision: ", body.name)
	var error := ResourceSaver.save(data, Passage.DATA_PATH, ResourceSaver.FLAG_COMPRESS)
	print("Stand passage bake: ", data.visual_meshes.size(), " meshes, ",
		data.collision_shapes.size(), " colliders, result ", error)
	visual.free()
	collision.free()
	quit(0 if error == OK and not data.visual_meshes.is_empty() and not data.collision_shapes.is_empty() else 1)


func _matches(node: Node, bounds: AABB) -> bool:
	# Only published stand structures and exceptionally merged building elements.
	# The pitch, grounds, vegetation and sports-hall shell remain undisturbed.
	var tag := String(node.name)
	if not (tag.begins_with("室外 构件 -9 ") or tag.begins_with("室外 构件 -10 ")
		or tag.begins_with("B场地 ") or tag.begins_with("室外 玻璃 -9 ")):
		return false
	for opening: AABB in Passage.OPENINGS:
		if _overlaps(bounds.position, bounds.end, opening):
			return true
	return false


func _clip_mesh(node: MeshInstance3D) -> ArrayMesh:
	var rebuilt := ArrayMesh.new()
	var changed := false
	for surface in node.mesh.get_surface_count():
		var attributes := node.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = attributes[Mesh.ARRAY_VERTEX]
		var original_indices: PackedInt32Array = attributes[Mesh.ARRAY_INDEX]
		if original_indices.is_empty():
			original_indices.resize(vertices.size())
			for i in vertices.size():
				original_indices[i] = i
		var updated := PackedInt32Array()
		var transform := node.global_transform
		for i in range(0, original_indices.size(), 3):
			var ids := [original_indices[i], original_indices[i + 1], original_indices[i + 2]]
			var fragments := _fragments([vertices[ids[0]], vertices[ids[1]], vertices[ids[2]]], transform)
			if fragments.size() == 1 and fragments[0] == ORIGINAL_VERTICES:
				updated.append_array(ids)
			else:
				changed = true
				for polygon: Array in fragments:
					var fan := PackedInt32Array()
					for w: Vector3 in polygon:
						fan.append(_append_vertex(attributes, ids, w))
					for k in range(1, fan.size() - 1):
						updated.append_array([fan[0], fan[k], fan[k + 1]])
		if not updated.is_empty():
			attributes[Mesh.ARRAY_INDEX] = updated
			rebuilt.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, attributes)
			rebuilt.surface_set_material(rebuilt.get_surface_count() - 1, node.mesh.surface_get_material(surface))
	return rebuilt if changed else null


func _append_vertex(arrays: Array, ids: Array, weight: Vector3) -> int:
	var index: int = arrays[Mesh.ARRAY_VERTEX].size()
	for channel in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_COLOR,
		Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2]:
		if arrays[channel] == null or arrays[channel].is_empty():
			continue
		var values := [arrays[channel][ids[0]], arrays[channel][ids[1]], arrays[channel][ids[2]]]
		var interpolated = _blend(values, weight)
		if channel == Mesh.ARRAY_NORMAL:
			interpolated = interpolated.normalized()
		arrays[channel].append(interpolated)
	if arrays[Mesh.ARRAY_TANGENT] != null and not arrays[Mesh.ARRAY_TANGENT].is_empty():
		for coordinate in 4:
			var values := [
				arrays[Mesh.ARRAY_TANGENT][ids[0] * 4 + coordinate],
				arrays[Mesh.ARRAY_TANGENT][ids[1] * 4 + coordinate],
				arrays[Mesh.ARRAY_TANGENT][ids[2] * 4 + coordinate],
			]
			arrays[Mesh.ARRAY_TANGENT].append(_blend(values, weight))
	return index


func _fragments(points: Array, transform: Transform3D) -> Array:
	var world := [transform * points[0], transform * points[1], transform * points[2]]
	var lower: Vector3 = world[0].min(world[1]).min(world[2])
	var upper: Vector3 = world[0].max(world[1]).max(world[2])
	var polygons := [ORIGINAL_VERTICES]
	for opening: AABB in Passage.OPENINGS:
		if not _overlaps(lower, upper, opening):
			continue
		var outside: Array = []
		for polygon in polygons:
			_subtract_box(polygon, world, opening, outside)
		polygons = outside
		if polygons.is_empty():
			break
	return polygons


func _overlaps(lower: Vector3, upper: Vector3, opening: AABB) -> bool:
	var minimum := opening.position
	var maximum := opening.end
	return lower.x < maximum.x and upper.x > minimum.x and lower.y < maximum.y \
		and upper.y > minimum.y and lower.z < maximum.z and upper.z > minimum.z


func _subtract_box(polygon: Array, points: Array, opening: AABB, output: Array) -> void:
	# Retain every portion outside one box plane, then clip the remaining portion
	# against the next plane. The last remainder is the part inside the opening.
	for plane in 6:
		var axis := int(plane / 2.0)
		var far_side := plane % 2 != 0
		var edge: float = opening.end[axis] if far_side else opening.position[axis]
		var inside: Array = []
		var outside: Array = []
		var previous: Vector3 = polygon.back()
		var p := _distance_to_edge(points, previous, axis, edge, far_side)
		for current: Vector3 in polygon:
			var c := _distance_to_edge(points, current, axis, edge, far_side)
			if (p >= 0.0) != (c >= 0.0):
				var cut := previous.lerp(current, p / (p - c))
				inside.append(cut)
				outside.append(cut)
			if c >= 0.0:
				inside.append(current)
			else:
				outside.append(current)
			previous = current
			p = c
		if outside.size() >= 3:
			output.append(outside)
		if inside.size() < 3:
			return
		polygon = inside


func _distance_to_edge(points: Array, weight: Vector3, axis: int, edge: float, far_side: bool) -> float:
	var coordinate: float = _blend(points, weight)[axis]
	return edge - coordinate if far_side else coordinate - edge


func _blend(values: Array, weight: Vector3) -> Variant:
	return values[0] * weight.x + values[1] * weight.y + values[2] * weight.z
