extends Node3D

# Game coordinates estimated from 09/090, 045, 000, 315, 270 and 11/045, 090, 135.
# The measured passage widths are from the existing campus model scale.
const APPROACH := [
	Vector3(-266.8, 0.12, -174.0),
	Vector3(-260.2, 0.12, -126.75),
	Vector3(-262.2, 0.12, -78.85),
	Vector3(-262.6, 0.12, -34.0),
]
const EXIT := [
	Vector3(-251.8, 0.12, -174.0),
	Vector3(-245.8, 0.12, -126.75),
	Vector3(-253.25, 0.12, -78.85),
	Vector3(-253.25, 0.12, -34.0),
]
const FRONTS := [-263.6, -257.4, -258.8, -259.9]
const REARS := [-254.2, -248.85, -254.85, -254.85]
const OPENING_WIDTH := 3.65
const CLEAR_HEIGHT := 2.46
# Visual and baked collision are cut by the same volumes in the re-bake tool.
const OPENINGS := [
	AABB(Vector3(-266.1, 0.102, -175.825), Vector3(14.0, 2.66, 3.65)),
	AABB(Vector3(-259.2, 0.102, -128.575), Vector3(13.0, 2.66, 3.65)),
	AABB(Vector3(-261.6, 0.102, -80.675), Vector3(9.7, 2.66, 3.65)),
	AABB(Vector3(-262.0, 0.102, -35.825), Vector3(10.1, 2.66, 3.65)),
	# Gates 3 and 4 take the sheltered strip along the stand to its end.
	AABB(Vector3(-255.1, 0.102, -92.5), Vector3(3.25, 2.66, 74.5)),
]
const DATA_PATH := "res://assets/campus/campus_field_passages.res"

var concrete := StandardMaterial3D.new()
var walkway := StandardMaterial3D.new()
var green := StandardMaterial3D.new()
var blue := StandardMaterial3D.new()


func _ready() -> void:
	if not ResourceLoader.exists(DATA_PATH):
		push_warning("Missing stand passage patch. Run the stand passage bake tool.")
		return
	var data: Resource = load(DATA_PATH)
	var campus := get_parent()
	for mesh: MeshInstance3D in campus.get_node("CampusVisuals").find_children("*", "MeshInstance3D", true, false):
		if data.visual_meshes.has(mesh.name):
			mesh.mesh = data.visual_meshes[mesh.name]
	for body: StaticBody3D in campus.get_node("CampusCollision").get_children():
		if data.collision_shapes.has(body.name):
			body.get_child(0).shape = data.collision_shapes[body.name]
	concrete.albedo_color = Color("#c9c9c1")
	walkway.albedo_color = Color("#9b9a91")
	green.albedo_color = Color("#356044")
	blue.albedo_color = Color("#304c76")
	for gate in APPROACH.size():
		_build_passage(gate)
	_box("ShelteredRearWalkway", Vector3(-253.46, 0.067, -55.25),
		Vector3(3.13, 0.10, 74.2), walkway)


func _build_passage(gate: int) -> void:
	var front: float = FRONTS[gate]
	var rear: float = REARS[gate]
	var z: float = APPROACH[gate].z
	var middle := (front + rear) * 0.5
	var length := rear - front
	var depth: float = EXIT[gate].x - APPROACH[gate].x
	var x: float = APPROACH[gate].x + depth * 0.5
	if gate >= 2:
		depth = rear - APPROACH[gate].x + 0.3
		x = APPROACH[gate].x + depth * 0.5
	var label := "Passage%d" % (gate + 1)
	_box(label + "Floor", Vector3(x, 0.07, z), Vector3(depth, 0.11, OPENING_WIDTH), walkway)
	_box(label + "Ceiling", Vector3(middle, 2.60, z), Vector3(length, 0.24, OPENING_WIDTH), concrete)
	for side in [-1, 1]:
		var offset: float = float(side) * (OPENING_WIDTH * 0.5 - 0.10)
		_box(label + "Side", Vector3(middle, 1.30, z + offset), Vector3(length, 2.43, 0.20), concrete)
		_box(label + "Cheek", Vector3(front - 0.31, 0.49, z + offset),
			Vector3(0.68, 0.91, 0.32), green)
		_open_leaf(rear, z + offset - side * 0.13)
	_box(label + "Header", Vector3(front - 0.12, CLEAR_HEIGHT + 0.12, z),
		Vector3(0.28, 0.32, OPENING_WIDTH + 0.25), concrete)
	_sign(label + "FrontNumber", gate + 1, front - 0.275, z, false)
	_sign(label + "RearNumber", gate + 1, rear + 0.055, z, true)


func _open_leaf(rear: float, z: float) -> void:
	# The metal grille leaves fold flat along the passage sidewalls.
	var unit := BoxMesh.new()
	unit.size = Vector3.ONE
	unit.material = green
	var bars := MultiMesh.new()
	bars.transform_format = MultiMesh.TRANSFORM_3D
	bars.mesh = unit
	bars.instance_count = 13
	var stile := Basis.from_scale(Vector3(0.020, 1.94, 0.022))
	var rail := Basis.from_scale(Vector3(1.33, 0.036, 0.042))
	for i in 10:
		bars.set_instance_transform(i, Transform3D(stile, Vector3(rear - 0.11 - 0.144 * i, 1.10, z)))
	for i in 3:
		var height: float = [0.15, 1.02, 2.05][i]
		bars.set_instance_transform(10 + i, Transform3D(rail, Vector3(rear - 0.75, height, z)))
	var leaf := MultiMeshInstance3D.new()
	leaf.multimesh = bars
	add_child(leaf)


func _sign(label: String, number: int, x: float, z: float, rear: bool) -> void:
	_box(label + "Plate", Vector3(x, 2.63, z), Vector3(0.035, 0.31, 0.33), blue, false)
	var digit := Label3D.new()
	digit.name = label
	digit.text = str(number)
	digit.font_size = 42
	digit.pixel_size = 0.0058
	digit.outline_size = 0
	digit.position = Vector3(x + (0.026 if rear else -0.026), 2.63, z)
	digit.rotation.y = PI * (0.5 if rear else -0.5)
	add_child(digit)


func _box(label: String, at: Vector3, size: Vector3, material: Material, solid := true) -> void:
	var geometry := BoxMesh.new()
	geometry.size = size
	geometry.material = material
	var visual := MeshInstance3D.new()
	visual.mesh = geometry
	if solid:
		var body := StaticBody3D.new()
		body.name = label
		var collider := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = size
		collider.shape = shape
		add_child(body, true)
		body.position = at
		body.add_child(visual)
		body.add_child(collider)
	else:
		visual.position = at
		add_child(visual)
