extends Node3D

const WALL := Color("#d3d9d6")
const TRIM := Color("#41646b")
const FLOOR := Color("#aabbbd")
const WOOD := Color("#af805e")
const RISE := 3.0

var areas: Array[Dictionary] = []
var passages: Array[Dictionary] = []

func build(doors: Node) -> void:
	_room(Vector2(-12, -6), 0, "高二 · 教室 A", doors)
	_room(Vector2(5, -6), 1, "高二 · 教室 B", doors)
	box(Vector3(-4, -0.13, 0), Vector3(36, 0.26, 4.2), FLOOR)
	box(Vector3(-4, 1.15, 2.08), Vector3(36.4, 2.3, 0.16), WALL)
	for interval in [Vector2(-22, -17), Vector2(-7, 0)]:
		_wall_x(interval.x, interval.y, -2.08)
	_area(Rect2(-21.58, -1.70, 35.58, 3.40), 0.0, 0.0)
	box(Vector3(-22, 1.15, 0), Vector3(0.18, 2.3, 4.2), WALL)
	_sign("西侧撤离点", Vector3(-21.72, 2.0, 0), PI / 2.0)
	_stairs()
	_courtyard()
	_sign("楼梯 →", Vector3(11.2, 2.0, 1.98), PI)
	for x in [-20.0, -15.0, -6.0, 3.0, 12.0]:
		box(Vector3(x, 0.48, 1.991), Vector3(3.0, 0.12, 0.04), TRIM, false)

func _room(center: Vector2, index: int, title: String, doors: Node) -> void:
	var x := center.x
	box(Vector3(x, -0.13, -6), Vector3(10.0, 0.26, 8.0), Color("#c4c0ab"))
	box(Vector3(x, 2.88, -6), Vector3(10.0, 0.16, 8.0), WALL)
	if index == 1:
		_wall_x(x - 5.0, x - 1.25, -10.0)
		_wall_x(x + 1.25, x + 5.0, -10.0)
		box(Vector3(x, 0.55, -10.0), Vector3(2.5, 1.1, 0.18), WALL)
		box(Vector3(x, 2.57, -10.0), Vector3(2.5, 0.65, 0.18), WALL)
		box(Vector3(x, 1.11, -10.02), Vector3(2.5, 0.08, 0.30), TRIM)
	else:
		_wall_x(x - 5.0, x + 5.0, -10.0)
	for side in [-1.0, 1.0]:
		box(Vector3(x + 5.0 * side, 1.45, -6), Vector3(0.15, 2.9, 8.0), WALL)
	_wall_x(x - 5.0, x - 0.76, -2.08)
	_wall_x(x + 0.76, x + 5.0, -2.08)
	box(Vector3(x, 2.52, -2.08), Vector3(1.52, 0.78, 0.18), WALL)
	_sign(title, Vector3(x, 2.48, -1.96))
	box(Vector3(x + 2.8, 1.55, -9.88), Vector3(2.3, 0.95, 0.08), TRIM)
	for desk_x in [x - 3.8, x + 3.8]:
		for desk_z in [-8.1, -6.1, -4.1]:
			box(Vector3(desk_x, 0.70, desk_z), Vector3(1.08, 0.12, 0.76), WOOD)
			for leg in [-0.41, 0.41]:
				box(Vector3(desk_x + leg, 0.33, desk_z), Vector3(0.10, 0.66, 0.60), TRIM)
	_area(Rect2(x - 2.96, -9.47, 5.92, 7.0), 0.0, 0.0)
	var center3 := Vector3(x, 0, -2.08)
	var pivot := Node3D.new()
	pivot.position = center3 + Vector3.LEFT * 0.75
	add_child(pivot)
	var leaf := StaticBody3D.new()
	leaf.position = Vector3(0.75, 1.08, 0)
	pivot.add_child(leaf)
	_box_on(leaf, Vector3(1.50, 2.16, 0.09), TRIM, true)
	var rail := NavigationLink3D.new()
	rail.start_position = Vector3(x, 0, -2.60)
	rail.end_position = Vector3(x, 0, -1.55)
	rail.enabled = false
	add_child(rail)
	doors.doors.append({"id": "room_%d" % index, "label": title, "center": center3,
		"width": 1.50, "height": 2.16, "open": false, "locked": false, "moving": false,
		"pivots": [{"node": pivot, "open_angle": PI / 2, "closed_angle": 0.0}]})
	passages.append({"from": index, "to": 2, "point": center3, "door": index, "link": rail})

func _stairs() -> void:
	const START := 14.0
	const END := 20.0
	const RUN := END - START
	var incline := atan2(RISE, RUN)
	var support := box(Vector3((START + END) / 2, RISE / 2, 0), Vector3(Vector2(RUN, RISE).length(), 0.18, 3.6), TRIM, true, false)
	support.rotation.z = incline
	support.position -= Vector3(-sin(incline), cos(incline), 0) * 0.09
	for index in range(20):
		var height := RISE * index / 20
		box(Vector3(START + 0.30 * index + 0.15, height - 0.095, 0),
			Vector3(0.30, 0.19, 3.6), FLOOR, false)
	for side in [-1.0, 1.0]:
		var guard := box(Vector3(17, 2.0, 1.8 * side), Vector3(Vector2(RUN, RISE).length(), 1, 0.13), TRIM)
		guard.rotation.z = incline
		box(Vector3(24, 3.54, 1.8 * side), Vector3(8, 1.1, 0.13), TRIM)
	box(Vector3(24, 2.87, 0), Vector3(8, 0.26, 3.6), FLOOR)
	box(Vector3(28, 4.08, 0), Vector3(0.16, 2.16, 3.6), WALL)
	_sign("东侧撤离点", Vector3(27.87, 4.90, 0), -PI / 2)
	_area(Rect2(14.0, -1.70, 6.0, 3.40), 0.0, RISE, false)
	_area(Rect2(20.0, -1.70, 7.55, 3.40), RISE, RISE)
	passages.append({"from": 2, "to": 3, "point": Vector3(14, 0, 0), "door": -1})
	passages.append({"from": 3, "to": 4, "point": Vector3(20, 3, 0), "door": -1})

func _courtyard() -> void:
	box(Vector3(12, -0.13, -6.1), Vector3(4.0, 0.26, 8.2), Color("#a7b4aa"))
	box(Vector3(7, -0.13, -13.0), Vector3(14.0, 0.26, 6.0), Color("#a7b4aa"))
	box(Vector3(0, 0.52, -13), Vector3(0.18, 1.3, 6.0), TRIM)
	box(Vector3(7, 0.52, -16), Vector3(14.0, 1.3, 0.18), TRIM)
	box(Vector3(14.0, 0.74, -9), Vector3(0.18, 1.74, 14.0), TRIM)
	_area(Rect2(10.43, -9.9, 3.13, 7.92), 0.0, 0.0)
	_area(Rect2(0.43, -15.55, 13.13, 5.17), 0.0, 0.0)
	_link(Vector3(12, 0, -1.60), Vector3(12, 0, -2.10))
	_link(Vector3(12, 0, -9.70), Vector3(12, 0, -10.56))
	passages.append({"from": 2, "to": 5, "point": Vector3(12, 0, -2), "door": -1})
	passages.append({"from": 5, "to": 6, "point": Vector3(12, 0, -10), "door": -1})
	passages.append({"from": 1, "to": 6, "point": Vector3(5, 1.4, -10), "door": -1})

func _link(from: Vector3, to: Vector3) -> void:
	var link := NavigationLink3D.new()
	link.start_position = from
	link.end_position = to
	add_child(link)

func _area(rect: Rect2, start_y: float, end_y: float, spawnable := true) -> void:
	var zone := NavigationRegion3D.new()
	var mesh := NavigationMesh.new()
	mesh.vertices = PackedVector3Array([
		Vector3(rect.position.x, start_y, rect.position.y),
		Vector3(rect.end.x, end_y, rect.position.y),
		Vector3(rect.end.x, end_y, rect.end.y),
		Vector3(rect.position.x, start_y, rect.end.y)])
	mesh.add_polygon(PackedInt32Array([0, 1, 2, 3]))
	zone.navigation_mesh = mesh
	add_child(zone)
	areas.append({"rect": rect, "height": start_y, "end_height": end_y, "spawnable": spawnable})

func zone_at(point: Vector3) -> int:
	var flat := Vector2(point.x, point.z)
	for index in areas.size():
		var zone := areas[index]
		var rect: Rect2 = zone.rect
		if not rect.grow(0.55).has_point(flat):
			continue
		var portion := clampf((point.x - rect.position.x) / rect.size.x, 0, 1)
		if absf(point.y - lerpf(zone.height, zone.end_height, portion)) < 1.35:
			return index
	return -1

func _wall_x(start: float, end: float, z: float) -> void:
	box(Vector3((start + end) / 2, 1.45, z), Vector3(end - start, 2.9, 0.16), WALL)

func _sign(message: String, at: Vector3, yaw := 0.0) -> void:
	var sign := Label3D.new()
	sign.text = message
	sign.position = at
	sign.rotation.y = yaw
	sign.pixel_size = 0.007
	sign.font_size = 36
	sign.modulate = Color("#244951")
	sign.outline_size = 0
	add_child(sign)

func box(at: Vector3, size: Vector3, color: Color, solid := true, visible_mesh := true) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = at
	add_child(body)
	_box_on(body, size, color, solid, visible_mesh)
	return body

func _box_on(body: PhysicsBody3D, size: Vector3, color: Color, solid: bool, visible_mesh := true) -> void:
	if solid:
		var shape := BoxShape3D.new()
		shape.size = size
		var collider := CollisionShape3D.new()
		collider.shape = shape
		body.add_child(collider)
	if visible_mesh:
		var mesh := BoxMesh.new()
		mesh.size = size
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		var view := MeshInstance3D.new()
		view.mesh = mesh
		view.material_override = material
		body.add_child(view)
