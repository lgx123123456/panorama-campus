extends RefCounted
## Character-specific view meshes share the authored FPS animation skeleton.

const SCENES := [
	preload("res://assets/campus/characters/arms/white.glb"),
	preload("res://assets/campus/characters/arms/blue.glb"),
	preload("res://assets/campus/characters/arms/tall.glb"),
	preload("res://assets/campus/characters/arms/strong.glb"),
	preload("res://assets/campus/characters/arms/guide.glb"),
]
const VIEW_LAYER := 1 << 19

static func prepare(root: Node3D, infected: bool) -> void:
	for mesh: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		mesh.layers = VIEW_LAYER
		mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		for surface in mesh.mesh.get_surface_count():
			var original := mesh.get_active_material(surface) as StandardMaterial3D
			if original == null:
				continue
			var mat := original.duplicate() as StandardMaterial3D
			if infected and ("Skin" in mat.resource_name or "Nails" in mat.resource_name):
				mat.albedo_color = Color(0.43, 0.49, 0.38) if "Skin" in mat.resource_name else Color(0.40, 0.42, 0.28)
			mesh.set_surface_override_material(surface, mat)

static func attach(skeleton: Skeleton3D, identity: int) -> Node3D:
	var source := SCENES[clampi(identity, 0, SCENES.size() - 1)].instantiate() as Node3D
	var source_skeleton: Skeleton3D = source.find_children("*", "Skeleton3D", true, false)[0]
	var result := Node3D.new()
	result.name = "UniformArms"
	skeleton.add_child(result)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var visual := mesh.duplicate() as MeshInstance3D
		result.add_child(visual)
		visual.transform = source_skeleton.transform.affine_inverse() * mesh.transform
		visual.skeleton = visual.get_path_to(skeleton)
		visual.skin = mesh.skin.duplicate()
		for bind_index in visual.skin.get_bind_count():
			var bone_name := visual.skin.get_bind_name(bind_index)
			if bone_name == &"":
				bone_name = source_skeleton.get_bone_name(visual.skin.get_bind_bone(bind_index))
			visual.skin.set_bind_name(bind_index, bone_name)
			visual.skin.set_bind_bone(bind_index, skeleton.find_bone(bone_name))
	prepare(result, false)
	source.free()
	return result
