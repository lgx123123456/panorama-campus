extends SceneTree

# Bake collision resources once. Repeated rooms share the same local-space
# shape resource and keep their individual campus transforms.
const SOURCE := "res://assets/campus/campus_full.glb"
const DECORATION := ["树叶", "叶冠", "叶片", "花瓣", "细枝", "苏铁叶", "喷泉白水", "水面", "题字", "横幅", "灯笼", "挂绳", "curtain", "paper"]

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var visuals := (load(SOURCE) as PackedScene).instantiate()
	root.add_child(visuals)
	var collision_root := Node3D.new()
	collision_root.name = "CampusCollision"
	var shapes: Dictionary = {}
	var bodies := 0
	for node in visuals.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.mesh == null or str(instance.name).begins_with("CampusDoorLeaf_") or _decorative(str(instance.name)):
			continue
		if not shapes.has(instance.mesh):
			var precise := (
				"东楼梯" in str(instance.name)
				or "连廊下门厅与楼道" in str(instance.name)
				or "公寓右侧楼梯" in str(instance.name)
				or "贴合室内" in str(instance.name)
				or "北侧教室" in str(instance.name)
				or "大厅正面宿舍" in str(instance.name)
			)
			shapes[instance.mesh] = _collision_shape(instance.mesh, precise)
		var shape: ConcavePolygonShape3D = shapes[instance.mesh]
		if shape == null:
			continue
		var body := StaticBody3D.new()
		body.name = str(instance.name) + "Collision"
		body.transform = instance.global_transform
		body.collision_layer = 0
		body.set_meta("bounds", instance.global_transform * instance.get_aabb())
		collision_root.add_child(body)
		body.owner = collision_root
		var collider := CollisionShape3D.new()
		collider.shape = shape
		body.add_child(collider)
		collider.owner = collision_root
		bodies += 1
	var packed := PackedScene.new()
	var error := packed.pack(collision_root)
	if error == OK:
		error = ResourceSaver.save(packed, "res://assets/campus/campus_full_collision.scn")
	print("CAMPUS FULL BAKE bodies=", bodies, " unique_meshes=", shapes.size(), " error=", error)
	collision_root.free()
	visuals.free()
	quit(0 if error == OK else 1)

func _collision_shape(mesh: Mesh, preserve_detail: bool = false) -> ConcavePolygonShape3D:
	var simplified: ImporterMesh
	if not preserve_detail:
		simplified = ImporterMesh.from_mesh(mesh)
		simplified.generate_lods(60.0, 0.0, [])
	var faces := PackedVector3Array()
	for surface in mesh.get_surface_count():
		var material := mesh.surface_get_material(surface)
		if material != null and _decorative(material.resource_name):
			continue
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var minimum_indices := int(indices.size() * 0.2)
		if not preserve_detail:
			for lod in simplified.get_surface_lod_count(surface):
				var candidate := simplified.get_surface_lod_indices(surface, lod)
				if candidate.size() >= minimum_indices and candidate.size() < indices.size():
					indices = candidate
		var count := indices.size() if not indices.is_empty() else vertices.size()
		for offset in range(0, count - 2, 3):
			var a := vertices[indices[offset] if not indices.is_empty() else offset]
			var b := vertices[indices[offset + 1] if not indices.is_empty() else offset + 1]
			var c := vertices[indices[offset + 2] if not indices.is_empty() else offset + 2]
			if a.is_finite() and b.is_finite() and c.is_finite() and (b - a).cross(c - a).length_squared() >= 0.00000001:
				faces.append_array(PackedVector3Array([a, b, c]))
	if faces.is_empty():
		return null
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(faces)
	return shape

func _decorative(label: String) -> bool:
	for keyword in DECORATION:
		if keyword in label:
			return true
	return false
