extends Node3D
## Fit the interior reveals to the existing B15/B21 facade. Measurements use the
## teaching floor frames in campus_entrances.json and the campus GLB window grid.

const Points := preload("res://scripts/campus/campus_survival_points.gd")
const DOOR_DATA := "res://assets/campus/campus_entrances.json"
const WINDOW_START := 14.0
const WINDOW_END := 78.0
const WALL_HEIGHT := 3.08
const REVEAL_ACROSS := 7.49

var plaster := StandardMaterial3D.new()
var sill := StandardMaterial3D.new()
var frame := StandardMaterial3D.new()
var threshold := StandardMaterial3D.new()
var glazing := StandardMaterial3D.new()
var liner := StandardMaterial3D.new()
var west_glass := StandardMaterial3D.new()

func _ready() -> void:
	plaster.albedo_color = Color(0.86, 0.87, 0.86)
	plaster.roughness = 0.88
	sill.albedo_color = Color(0.72, 0.75, 0.76)
	sill.roughness = 0.44
	frame.albedo_color = Color(0.39, 0.43, 0.45)
	frame.metallic = 0.3
	frame.roughness = 0.5
	threshold.albedo_color = Color(0.40, 0.42, 0.42)
	threshold.roughness = 0.76
	_setup_glass(glazing, 0.27)
	_setup_glass(liner, 0.09)
	_setup_glass(west_glass, 0.17)
	west_glass.albedo_color = Color(0.58, 0.73, 0.81, 0.17)
	west_glass.roughness = 0.075

	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DOOR_DATA))
	for record: Dictionary in data.teaching_west_stairs.buildings:
		_add_building(record)

func _setup_glass(material: StandardMaterial3D, opacity: float) -> void:
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = Color(0.64, 0.76, 0.79, opacity)
	material.roughness = 0.23

func _add_building(record: Dictionary) -> void:
	var corner := Points.point(record.corridor_path[0])
	var along := (Points.point(record.corridor_path[1]) - corner).normalized()
	var across := Vector3(-along.z, 0.0, along.x)
	var origin := corner - along * 2.5 - across * 2.45
	origin.y = 0
	var building := Node3D.new()
	building.name = record.building
	building.transform = Transform3D(Basis(across, Vector3.UP, -along), origin)
	add_child(building)

	var long_center := (WINDOW_START + WINDOW_END) * 0.5
	var long_width := WINDOW_END - WINDOW_START
	for index in record.levels.size():
		var floor_height := float(record.levels[index])
		var floor := Node3D.new()
		floor.name = "Floor%d" % (index + 1)
		floor.position.y = floor_height
		building.add_child(floor)
		_add_floor_joints(floor, record.building, index)
		if index >= 1:
			_add_west_hall_glazing(floor, record.building)
		# Face the two ledges inwards so the raw facade cut is out of view.
		_box(floor, "CorridorWindowHead", Vector3(REVEAL_ACROSS, 2.71, -long_center),
			Vector3(0.83, 0.31, long_width + 0.12), plaster)
		_box(floor, "CorridorWindowSill", Vector3(REVEAL_ACROSS, 1.065, -long_center),
			Vector3(0.87, 0.074, long_width + 0.12), sill)
		# A lightly tinted inner face spans this continuous window band. The
		# original exterior divisions and opaque pilasters remain visible.
		_pane(floor, "CorridorWindowLiner", 7.28, long_center, 1.824, long_width, 1.51, liner)
		_barrier(floor, "CorridorWindowCollision", Vector3(7.28, 1.824, -long_center),
			Vector3(0.035, 1.51, long_width))
		_box(floor, "WestCorridorJoint", Vector3(5.41, 0.001, -14.0),
			Vector3(3.41, 0.018, 0.085), threshold)
		_box(floor, "EastCorridorJoint", Vector3(5.41, 0.001, -78.0),
			Vector3(3.41, 0.018, 0.085), threshold)
		if index >= 2:
			if record.building == "B15":
				_add_zhiyuan_tower_glazing(floor)
			else:
				_add_siyuan_tower_jambs(floor)

func _add_floor_joints(floor: Node3D, building_id: String, index: int) -> void:
	# The interior slab stops short of the facade's inner stone faces. Extend
	# only these perimeter strips; the west stairwell remains open at 3.50..8.85.
	var edge := 7.40 if building_id == "B15" else 7.35
	_floor_strip(floor, "WestHallSouthFloorJoint", 7.13, edge, 1.0, 3.50)
	_floor_strip(floor, "WestHallNorthFloorJoint", -edge, -7.10, 1.0, 3.50)
	_floor_strip(floor, "WestLandingFloorJoint", 7.13, edge, 8.85, WINDOW_START)
	_floor_strip(floor, "CorridorFacadeFloorJoint", 7.13, edge, WINDOW_START, WINDOW_END)
	if index == 0:
		return
	# The upper east tower continues the same slab edge. At level two this
	# meets the existing bridge floor; the ground-floor entrance keeps its slope.
	var east_end := 91.90 if building_id == "B15" else 89.35
	_floor_strip(floor, "EastTowerFloorJoint", 7.13, edge, WINDOW_END - 0.02, east_end)
	# Match the slanted west facade on upper levels. The ground floor keeps
	# its existing two entrance landings and their ramp/threshold geometry.
	var slope := 0.06350 if building_id == "B15" else 0.02548
	var front_left := 0.691 + slope * edge - 0.05
	var front_right := 0.691 - slope * edge - 0.05
	var vertices := PackedVector3Array([
		Vector3(-edge, 0.002, -front_left), Vector3(edge, 0.002, -front_right),
		Vector3(edge, 0.002, -1.20), Vector3(-edge, 0.002, -1.20),
		Vector3(-edge, -0.158, -front_left), Vector3(edge, -0.158, -front_right),
		Vector3(edge, -0.158, -1.20), Vector3(-edge, -0.158, -1.20)])
	var indices := PackedInt32Array([0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6,
		0, 4, 5, 0, 5, 1, 1, 5, 6, 1, 6, 2,
		2, 6, 7, 2, 7, 3, 3, 7, 4, 3, 4, 0])
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	surface.set_material(threshold)
	for index_offset in range(0, indices.size(), 3):
		for vertex in [indices[index_offset], indices[index_offset + 2], indices[index_offset + 1]]:
			surface.add_vertex(vertices[vertex])
	surface.generate_normals()
	var mesh := surface.commit()
	_visual(floor, "WestFacadeFloorJoint", Vector3.ZERO, mesh)
	var body := StaticBody3D.new()
	body.name = "WestFacadeFloorJointCollision"
	body.collision_mask = 0
	var collider := CollisionShape3D.new()
	collider.shape = mesh.create_trimesh_shape()
	body.add_child(collider)
	floor.add_child(body)

func _floor_strip(floor: Node3D, label: String, from_x: float, to_x: float,
		from_along: float, to_along: float) -> void:
	var center := Vector3((from_x + to_x) * 0.5, -0.078, -(from_along + to_along) * 0.5)
	var size := Vector3(to_x - from_x, 0.16, to_along - from_along)
	_box(floor, label, center, size, threshold)
	_barrier(floor, label + "Collision", center, size)

func _add_west_hall_glazing(floor: Node3D, building_id: String) -> void:
	# The source facade repeats the ground-floor doorway on every level.
	# Fill only that central opening above ground, matching the sloped glass
	# plane and tint of the neighbouring source panes.
	var slope := 0.06350 if building_id == "B15" else 0.02548
	var center_x := 0.044 if building_id == "B15" else 0.018
	var width := 2.96 if building_id == "B15" else 2.90
	var pane_frame := Node3D.new()
	pane_frame.name = "WestHallWindow"
	pane_frame.position = Vector3(center_x, 1.30, -(0.691 - slope * center_x))
	pane_frame.rotation.y = -atan(slope)
	floor.add_child(pane_frame)
	_box(pane_frame, "WestHallGlazing", Vector3.ZERO, Vector3(width, 2.16, 0.12), west_glass)
	# The original B15 side pane also lacks collision near its outside edge.
	# Use one continuous barrier across this upper-floor window wall.
	_barrier(pane_frame, "WestHallGlazingCollision", Vector3.ZERO, Vector3(10.50, 2.16, 0.12))

func _add_zhiyuan_tower_glazing(floor: Node3D) -> void:
	# The second floor opens to the existing glass bridge. The same bay on
	# levels three to five has no bridge and needs its own glazed wall.
	var x := 7.27
	var start := 81.00
	var end := 91.68
	var span := end - start
	var middle := (start + end) * 0.5
	_box(floor, "TowerParapet", Vector3(x, 0.41, -middle), Vector3(0.18, 0.82, span), plaster)
	_box(floor, "TowerSill", Vector3(x, 0.83, -middle), Vector3(0.23, 0.07, span), sill)
	_box(floor, "TowerWindowHead", Vector3(x, WALL_HEIGHT - 0.09, -middle),
		Vector3(0.18, 0.18, span), plaster)
	_box(floor, "TowerTransom", Vector3(x, 2.34, -middle), Vector3(0.09, 0.06, span), frame)
	var bay := span / 5.0
	for index in 6:
		_box(floor, "TowerMullion%d" % index, Vector3(x, 1.88, -(start + bay * index)),
			Vector3(0.11, 2.18, 0.068), frame)
	_pane(floor, "TowerGlazing", x, middle, 1.89, span, 2.12, glazing)
	_barrier(floor, "TowerGlazingCollision", Vector3(x, 1.54, -middle), Vector3(0.13, 3.08, span))

func _add_siyuan_tower_jambs(floor: Node3D) -> void:
	# The tower already has its own panes. Close the exposed frame joints
	# where the lower bridge reveal does not meet the upper wall.
	for longitudinal: float in [83.30, 89.09]:
		_box(floor, "TowerJamb", Vector3(7.31, WALL_HEIGHT * 0.5, -longitudinal),
			Vector3(0.20, WALL_HEIGHT, 0.59), plaster)
		_barrier(floor, "TowerJambCollision", Vector3(7.31, WALL_HEIGHT * 0.5, -longitudinal),
			Vector3(0.20, WALL_HEIGHT, 0.59))
	# The visible upper tower panes are present in the source model, but their
	# thin surfaces were dropped from the baked collision mesh.
	_barrier(floor, "TowerGlazingCollision", Vector3(7.304, WALL_HEIGHT * 0.5, -86.07),
		Vector3(0.13, WALL_HEIGHT, 5.21))

func _box(parent: Node3D, label: String, center: Vector3, size: Vector3, material: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = material
	_visual(parent, label, center, mesh)

func _pane(parent: Node3D, label: String, across: float, along: float,
		height: float, width: float, tall: float, material: Material) -> void:
	var mesh := QuadMesh.new()
	mesh.size = Vector2(width, tall)
	mesh.material = material
	var pane := _visual(parent, label, Vector3(across, height, -along), mesh)
	pane.rotation.y = PI * 0.5
	pane.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF

func _visual(parent: Node3D, label: String, center: Vector3, mesh: Mesh) -> MeshInstance3D:
	var rendered := MeshInstance3D.new()
	rendered.name = label
	rendered.position = center
	rendered.mesh = mesh
	parent.add_child(rendered)
	return rendered

func _barrier(parent: Node3D, label: String, center: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	body.collision_mask = 0
	var collider := CollisionShape3D.new()
	var bounds := BoxShape3D.new()
	bounds.size = size
	collider.shape = bounds
	body.add_child(collider)
	parent.add_child(body)
