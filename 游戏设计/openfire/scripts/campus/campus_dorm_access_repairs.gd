extends Node3D

const DATA_PATH := "res://assets/campus/campus_dorm_access.res"
const ENTRANCES := "res://assets/campus/campus_entrances.json"
const Points = preload("res://scripts/campus/campus_survival_points.gd")

static func source_frame(rows: Array) -> Transform3D:
	return Transform3D(Basis(Points.point([rows[0][0], rows[1][0], rows[2][0]]),
		Points.point([rows[0][1], rows[1][1], rows[2][1]]),
		Points.point([rows[0][2], rows[1][2], rows[2][2]])),
		Points.point([rows[0][3], rows[1][3], rows[2][3]]))

static func stair_mirror(frame: Transform3D) -> Transform3D:
	return frame * Transform3D(Basis(Vector3.RIGHT, Vector3.DOWN, Vector3.BACK),
		Vector3(0, 5.30, 0)) * frame.affine_inverse()

func _ready() -> void:
	if not ResourceLoader.exists(DATA_PATH):
		push_error("Dormitory access repair resource is missing")
		return
	var data: Resource = load(DATA_PATH)
	var campus := get_parent()
	for mesh: MeshInstance3D in campus.get_node("CampusVisuals").find_children("*", "MeshInstance3D", true, false):
		if data.visual_meshes.has(mesh.name):
			mesh.mesh = data.visual_meshes[mesh.name]
	for body: StaticBody3D in campus.get_node("CampusCollision").get_children():
		if data.collision_shapes.has(body.name):
			var shape: ConcavePolygonShape3D = data.collision_shapes[body.name]
			body.get_child(0).shape = shape
			var points := shape.get_faces()
			var bounds := AABB(points[0], Vector3.ZERO)
			for point: Vector3 in points:
				bounds = bounds.expand(point)
			bounds = body.transform * bounds
			body.set_meta("bounds", bounds)
			var index: int = campus.bodies.find(body)
			if index >= 0:
				campus.bounds[index] = bounds
	var records: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ENTRANCES))
	var wall := StandardMaterial3D.new()
	wall.albedo_color = Color("#bcb5a2")
	wall.roughness = 0.82
	for building: Dictionary in records.dorm_layouts:
		var frame := source_frame(building.frame)
		var edge := -10.55 if building.building == "B25" else -14.15
		for key: String in ["west", "east"]:
			var stair: Dictionary = building.stairs[key]
			var old_y := float(stair.access_repair.original_door_building_y)
			var new_low := float(stair.access_repair.opening_low_building_y)
			var new_high := float(stair.access_repair.opening_high_building_y)
			# Fill the old doorway, retaining any portion shared by the new opening.
			var old_low := old_y - 0.875
			var old_high := old_y + 0.875
			var intervals := [[old_low, minf(old_high, new_low)],
				[maxf(old_low, new_high), old_high]]
			for level: Dictionary in building.levels:
				for interval: Array in intervals:
					var width := float(interval[1]) - float(interval[0])
					if width <= 0.001:
						continue
					var at := Vector3(edge, (float(interval[0]) + float(interval[1])) * 0.5,
						float(level.z) + 1.115)
					_close_old_opening(frame, at, Vector3(0.13, width, 2.23), wall)
				var middle := (new_low + new_high) * 0.5
				var floor_number := int(level.floor)
				_header(frame, Vector3(edge - 0.095, middle, float(level.z) + 2.43),
					-frame.basis.x.normalized(), "%dF  楼梯 ↑" % floor_number)
				var message := "%dF  楼道" % floor_number
				if floor_number == 1:
					var direction := -1.0 if key == "west" else 1.0
					if building.building == "B28":
						direction = -direction
					var right := Vector3.UP.cross(frame.basis.x.normalized())
					var arrow := "→" if right.dot(frame.basis.y * direction) > 0 else "←"
					message = "1F  出口 " + arrow + (" 端门" if building.building == "B25" else " 大厅")
				_header(frame, Vector3(edge + 0.095, middle, float(level.z) + 2.43),
					frame.basis.x.normalized(), message)
				if floor_number == 1:
					_header(frame, Vector3(edge - 1.50, middle, float(level.z) + 2.26),
						frame.basis.x.normalized(), message)

func _header(frame: Transform3D, local: Vector3, normal: Vector3, message: String) -> void:
	var board := MeshInstance3D.new()
	board.name = "DormFloorExitSign"
	board.position = frame * local
	board.basis = Basis.looking_at(-normal, Vector3.UP)
	var plane := QuadMesh.new()
	plane.size = Vector2(2.95, 0.34)
	var paint := StandardMaterial3D.new()
	paint.albedo_color = Color("#195f4c")
	paint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	plane.material = paint
	board.mesh = plane
	add_child(board, true)
	var text := Label3D.new()
	text.text = message
	text.font_size = 48
	text.pixel_size = 0.0046
	text.outline_size = 0
	text.no_depth_test = false
	text.position.z = 0.018
	board.add_child(text)

func _close_old_opening(frame: Transform3D, at: Vector3, size: Vector3, material: Material) -> void:
	var body := StaticBody3D.new()
	body.name = "DormFormerOpeningWall"
	body.transform = frame * Transform3D(Basis.IDENTITY, at)
	var box := BoxMesh.new()
	box.size = size
	box.material = material
	var visual := MeshInstance3D.new()
	visual.mesh = box
	body.add_child(visual)
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collider.shape = shape
	body.add_child(collider)
	add_child(body, true)
