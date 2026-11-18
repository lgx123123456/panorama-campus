extends SceneTree

const SOURCE := "res://assets/campus/campus_full.glb"
const TARGET := "res://assets/campus/campus_occluder.res"
const STRUCTURAL_MATERIALS := [
	"ochre", "三处庭院 · ochre", "楼间过道 ochre", "暖黄色墙板", "暖黄色墙板.001",
	"公寓与运动区 · ochre", "公寓与运动区 · ochre.001", "教学楼与孔德广场 · ochre",
	"roof", "校园室内 · ceiling", "校园室内 · plaster", "ceiling", "plaster",
	"教学楼道浅灰地砖", "公寓灰色地砖", "class_tile", "宿舍米白地砖",
]
const MIN_DOUBLE_AREA := 1.0

func _initialize() -> void:
	call_deferred("_bake")

func _bake() -> void:
	var campus := (load(SOURCE) as PackedScene).instantiate()
	root.add_child(campus)
	var vertices := PackedVector3Array()
	var indices := PackedInt32Array()
	for child in campus.find_children("*", "MeshInstance3D", true, false):
		var instance := child as MeshInstance3D
		var mesh := instance.mesh
		if mesh == null:
			continue
		var transform := instance.global_transform
		for surface in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			if material == null or material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED \
					or material.resource_name not in STRUCTURAL_MATERIALS:
				continue
			var arrays := mesh.surface_get_arrays(surface)
			var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var source_indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if source_indices.is_empty():
				continue
			for index in range(0, source_indices.size(), 3):
				var a := transform * positions[source_indices[index]]
				var b := transform * positions[source_indices[index + 1]]
				var c := transform * positions[source_indices[index + 2]]
				var normal := (b - a).cross(c - a)
				if normal.length_squared() < MIN_DOUBLE_AREA * MIN_DOUBLE_AREA:
					continue
				var vertical := absf(normal.normalized().y)
				if vertical > 0.05 and vertical < 0.98:
					continue
				# Keep the actual opening boundaries from the source mesh.
				var offset := vertices.size()
				vertices.append_array(PackedVector3Array([a, b, c]))
				indices.append_array(PackedInt32Array([offset, offset + 1, offset + 2]))
	var occluder := ArrayOccluder3D.new()
	occluder.set_arrays(vertices, indices)
	var error := ResourceSaver.save(occluder, TARGET) if not indices.is_empty() else ERR_INVALID_DATA
	print("CAMPUS OCCLUDER triangles=", indices.size() / 3, " error=", error)
	campus.free()
	quit(0 if error == OK else 1)
