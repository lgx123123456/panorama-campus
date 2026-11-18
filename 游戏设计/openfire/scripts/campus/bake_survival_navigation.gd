extends SceneTree

const Points = preload("res://scripts/campus/campus_survival_points.gd")
const COLLISION := "res://assets/campus/campus_full_collision.scn"
const NAVIGATION := "res://assets/campus/campus_survival_navigation.res"
const DOORS := "res://assets/campus/campus_entrances.json"

func _initialize() -> void:
	call_deferred("_bake")

func _bake() -> void:
	var collision := (load(COLLISION) as PackedScene).instantiate()
	var source := NavigationMeshSourceGeometryData3D.new()
	for body: StaticBody3D in collision.get_children():
		var collider: CollisionShape3D = body.get_child(0)
		var shape := collider.shape as ConcavePolygonShape3D
		source.add_faces(shape.get_faces(), body.transform * collider.transform)
	collision.free()
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DOORS))
	for record: Dictionary in Points.external_doors(data) + Points.classroom_doors(data):
		_block_door(source, record)
	for record: Dictionary in data.get("closed_buildings", []):
		var outline := PackedVector3Array()
		for vertex: Array in record.outline:
			outline.append(Vector3(float(vertex[0]), 0.0, -float(vertex[1])))
		source.add_projected_obstruction(outline, -0.5, float(record.height), true)
	var mesh := NavigationMesh.new()
	mesh.cell_size = 0.15
	mesh.cell_height = 0.08
	mesh.agent_radius = 0.30
	mesh.agent_height = 1.60
	mesh.agent_max_climb = 0.24
	mesh.agent_max_slope = 49.0
	mesh.region_min_size = 1.0
	mesh.region_merge_size = 3.0
	mesh.detail_sample_distance = 3.0
	mesh.filter_walkable_low_height_spans = true
	mesh.filter_ledge_spans = true
	mesh.filter_low_hanging_obstacles = true
	print("Baking navigation from the existing campus collision mesh")
	NavigationServer3D.bake_from_source_geometry_data(mesh, source)
	_clean_raster_edges(mesh)
	var error := ResourceSaver.save(mesh, NAVIGATION, ResourceSaver.FLAG_COMPRESS)
	print("Campus navigation polygons=", mesh.get_polygon_count(), " error=", error)
	quit(0 if error == OK and mesh.get_polygon_count() > 0 else 1)

func _clean_raster_edges(mesh: NavigationMesh) -> void:
	var vertices := mesh.vertices
	var scale := Vector3(mesh.cell_size, mesh.cell_height, mesh.cell_size) * Points.MERGE_SCALE
	var keys: Array[PackedInt32Array] = []
	for offset in [Vector3.ZERO, Vector3.ONE * 0.5]:
		var ids := {}
		var indices := PackedInt32Array()
		for vertex in vertices:
			var cell := Vector3i((vertex / scale + offset).floor())
			if not ids.has(cell):
				ids[cell] = ids.size()
			indices.append(ids[cell])
		keys.append(indices)
	var polygons: Array[Dictionary] = []
	for index in mesh.get_polygon_count():
		var polygon := mesh.get_polygon(index)
		var area := 0.0
		for corner in range(1, polygon.size() - 1):
			area += (vertices[polygon[corner]] - vertices[polygon[0]]).cross(
				vertices[polygon[corner + 1]] - vertices[polygon[0]]).length()
		polygons.append({"polygon": polygon, "area": area})
	polygons.sort_custom(func(a: Dictionary, b: Dictionary): return a.area > b.area)
	mesh.clear_polygons()
	var occupancy: Array[Dictionary] = [{}, {}]
	for entry in polygons:
		var polygon: PackedInt32Array = entry.polygon
		var edges: Array[Dictionary] = [{}, {}]
		var valid := true
		for key in keys.size():
			for corner in polygon.size():
				var a := keys[key][polygon[corner]]
				var b := keys[key][polygon[(corner + 1) % polygon.size()]]
				var edge := Vector2i(mini(a, b), maxi(a, b))
				if a == b or edges[key].has(edge) or int(occupancy[key].get(edge, 0)) == 2:
					valid = false
					break
				edges[key][edge] = true
			if not valid:
				break
		if valid:
			mesh.add_polygon(polygon)
			for key in keys.size():
				for edge in edges[key]:
					occupancy[key][edge] = int(occupancy[key].get(edge, 0)) + 1

func _block_door(source: NavigationMeshSourceGeometryData3D, record: Dictionary) -> void:
	var at: Vector3 = record.point
	var direction: Vector3 = record.outward
	var across := Vector3(-direction.z, 0, direction.x) * (float(record.width) / 2.0 + 0.30)
	var depth := direction * 0.29
	var polygon := PackedVector3Array([at - across - depth, at + across - depth,
		at + across + depth, at - across + depth])
	source.add_projected_obstruction(polygon, at.y - 0.35, 1.85, true)
