extends "res://scripts/campus/campus_zombie_layout.gd"

const Points = preload("res://scripts/campus/campus_survival_points.gd")
const FieldPassages = preload("res://scripts/campus/campus_field_passages.gd")
const DormAccess = preload("res://scripts/campus/campus_dorm_access_repairs.gd")
const NAVIGATION := "res://assets/campus/campus_survival_navigation.res"
const OUTSIDE := 5
const FIRST_CLASSROOM := 6
const ROOM_COUNT := 7
const SECOND_CORRIDOR := FIRST_CLASSROOM + 2 * 5 * ROOM_COUNT
const DORM_FLOOR_ONE := SECOND_CORRIDOR + 5
const DORM_FLOOR_TWO := DORM_FLOOR_ONE + 1

var anchor: Vector3
var along: Vector3
var across: Vector3
var stair_routes: Array[Dictionary] = []
var stair_flights: Array[Dictionary] = []
var room_regions: Array[Dictionary] = []
var building_regions: Array[Dictionary] = []
var floor_one_exit := Vector3(-58, 0.35, -118)
var west_stair_lobby: Vector3
var dorm_start: Vector3
var dorm_axis: Vector3
var dorm_length: float
var dorm_buildings: Array[Dictionary] = []

func build(doors: Node) -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(doors.DOOR_DATA))
	var west: Dictionary = data.teaching_west_stairs.buildings[0]
	var east: Dictionary = data.teaching_east_stairs.buildings[0]
	for staircase in data.teaching_west_stairs.buildings + data.teaching_east_stairs.buildings:
		for route in staircase.routes:
			_add_stair_flights(route.points)
	var corner := Points.point(west.corridor_path[0])
	along = (Points.point(west.corridor_path[1]) - corner).normalized()
	across = Vector3(-along.z, 0.0, along.x)
	anchor = corner - along * 2.50 - across * 2.45
	anchor.y = 0
	west_stair_lobby = Points.point(west.corridor_points[0])
	var region := NavigationRegion3D.new()
	var mesh := _without_old_dorm_stairs(load(NAVIGATION) as NavigationMesh, data)
	var map := get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(map, mesh.cell_size)
	NavigationServer3D.map_set_cell_height(map, mesh.cell_height)
	NavigationServer3D.map_set_merge_rasterizer_cell_scale(map, Points.MERGE_SCALE)
	NavigationServer3D.map_set_link_connection_radius(map, 0.85)
	region.navigation_mesh = mesh
	add_child(region)
	for zone in DORM_FLOOR_TWO + 13:
		areas.append({"spawnable": true})
	var dorm: Dictionary = data.dorm_layouts.filter(func(item): return item.building == "B25")[0]
	var first: Array = dorm.levels[0].corridor
	dorm_start = Points.point(first[0])
	var opposite := Points.point(first[-1])
	dorm_length = dorm_start.distance_to(opposite)
	dorm_axis = (opposite - dorm_start).normalized()
	for building: Dictionary in data.teaching_west_stairs.buildings:
		var start := Points.point(building.corridor_path[0])
		var direction := (Points.point(building.corridor_path[1]) - start).normalized()
		var side := Vector3(-direction.z, 0, direction.x)
		building_regions.append({"anchor": start - direction * 2.5 - side * 2.45,
			"along": direction, "across": side, "base": 0 if building.building == "B15" else SECOND_CORRIDOR})
	var existing := Points.external_doors(data)
	for index in existing.size():
		var record: Dictionary = existing[index]
		var door: Dictionary = doors.doors[index]
		door.outward = record.outward
		if record.locked:
			continue
		var story_room := -1
		if record.id in ["B15_1", "B15_2", "B15_bridge"]:
			story_room = 0
		elif str(record.id).begins_with("B21_"):
			story_room = SECOND_CORRIDOR
		elif record.id in ["B25", "B25_west_end", "B25_east_end"]:
			story_room = DORM_FLOOR_ONE
		elif record.id == "B28":
			story_room = _dorm_zone("B28", 1)
		_register_door(index, door, story_room, OUTSIDE)
	var classrooms := Points.classroom_doors(data)
	for record in classrooms:
		var building_offset := 0 if record.building == "B15" else 5 * ROOM_COUNT
		var zone := FIRST_CLASSROOM + building_offset + int(record.floor) * ROOM_COUNT + int(record.room)
		_add_classroom_door(doors, record, zone)
		if str(record.id).ends_with("_0"):
			var rear: Dictionary = classrooms.filter(func(other: Dictionary):
				return other.id == str(record.id).trim_suffix("_0") + "_8")[0]
			var axis: Vector3 = (rear.point - record.point).normalized()
			room_regions.append({"start": record.point, "axis": axis, "outward": record.outward,
				"length": (rear.point as Vector3).distance_to(record.point), "zone": zone})

	for floor in range(Points.FLOOR_HEIGHTS.size() - 1):
		for staircase: Dictionary in [west, east]:
			var points: Array = staircase.routes[floor].points
			var origin := Points.point(staircase.corridor_points[floor])
			var destination := Points.point(staircase.corridor_points[floor + 1])
			var route := PackedVector3Array([origin])
			for values: Array in points:
				route.append(Points.point(values))
			route.append(destination)
			stair_routes.append({"from": origin, "to": destination, "points": route})
			_link(origin, destination)
			var point := Points.point(points[2])
			passages.append({"from": floor, "to": floor + 1, "point": point, "door": -1})
	var bridge: Dictionary = data.doors.filter(func(door: Dictionary): return door.id == "B15_bridge")[0]
	floor_one_exit = Points.point(bridge.center) + Points.outward(bridge.outward) * 3.1
	for building: Dictionary in data.dorm_layouts:
		dorm_buildings.append(building)
		for name: String in ["west", "east", "mid"]:
			var stair: Dictionary = building.stairs[name]
			for route: Dictionary in stair.routes:
				_add_stair_flights(route.points)
				var lower: Array = stair.corridor_paths[int(route.from_floor) - 1]
				var upper: Array = stair.corridor_paths[int(route.to_floor) - 1].duplicate()
				upper.reverse()
				var points := PackedVector3Array()
				for value: Array in lower + route.points + upper:
					var point := Points.point(value)
					if points.is_empty() or points[-1].distance_to(point) > 0.01:
						points.append(point)
				stair_routes.append({"from": points[0], "to": points[-1], "points": points,
					"building": building.building, "side": name,
					"from_floor": route.from_floor, "to_floor": route.to_floor})
				_link(points[0], points[-1])
				passages.append({"from": _dorm_zone(building.building, int(route.from_floor)),
					"to": _dorm_zone(building.building, int(route.to_floor)),
					"point": Points.point(route.points[2]), "door": -1})
	_connect_field_navigation.call_deferred()

func _without_old_dorm_stairs(source: NavigationMesh, data: Dictionary) -> NavigationMesh:
	# The retained global bake describes the former ascending direction. Remove
	# those stair polygons; corridor-to-corridor links follow the repaired mesh.
	var frames: Array[Transform3D] = []
	for building: Dictionary in data.dorm_layouts:
		for key: String in ["west", "east"]:
			frames.append(DormAccess.source_frame(building.stairs[key].stair_frame).affine_inverse())
	var mesh := source.duplicate() as NavigationMesh
	mesh.clear_polygons()
	var vertices := source.vertices
	var removed := 0
	for index in source.get_polygon_count():
		var polygon := source.get_polygon(index)
		var intersects := false
		for inverse: Transform3D in frames:
			for vertex in polygon:
				var local := inverse * vertices[vertex]
				if absf(local.x) < 1.65 and local.y > 0.25 and local.y < 5.25 and local.z > 0.3 and local.z < 21.5:
					intersects = true
					break
			if intersects:
				break
		if intersects:
			removed += 1
		else:
			mesh.add_polygon(polygon)
	print("DORM NAV removed former stair polygons=", removed)
	return mesh

func _dorm_zone(building: String, floor_number: int) -> int:
	if building == "B25":
		return DORM_FLOOR_ONE + floor_number - 1
	return DORM_FLOOR_TWO + 5 + floor_number

func _connect_field_navigation() -> void:
	# The stand openings are a live geometry patch newer than the campus bake.
	# Give each measured, physically open corridor its own navigation surface.
	if not is_inside_tree():
		return
	await get_tree().physics_frame
	if not is_inside_tree():
		return
	await get_tree().physics_frame
	if not is_inside_tree():
		return
	var map := get_world_3d().navigation_map
	while NavigationServer3D.map_get_iteration_id(map) == 0:
		await get_tree().physics_frame
		if not is_inside_tree():
			return
	# The large imported region can synchronize after the first empty map
	# iteration. Keep connector anchors off partial maps containing only links.
	while NavigationServer3D.map_get_closest_point(map, west_stair_lobby).distance_to(west_stair_lobby) > 2.0:
		await get_tree().physics_frame
		if not is_inside_tree():
			return
	var entrances: Array[Vector3] = []
	var exits: Array[Vector3] = []
	for index in FieldPassages.APPROACH.size():
		entrances.append(NavigationServer3D.map_get_closest_point(map,
			FieldPassages.APPROACH[index] + Vector3.LEFT * 1.0))
		exits.append(NavigationServer3D.map_get_closest_point(map,
			FieldPassages.EXIT[index] + Vector3.RIGHT * 1.0))
	var rear_join := NavigationServer3D.map_get_closest_point(map, Vector3(-253.25, 0.13, -18.8))
	for index in FieldPassages.APPROACH.size():
		var entry: Vector3 = FieldPassages.APPROACH[index]
		var exit: Vector3 = FieldPassages.EXIT[index]
		_field_navigation_rect(Rect2(entry.x - 0.45, entry.z - 1.12,
			exit.x - entry.x + 0.90, 2.24))
		_link(entrances[index], Vector3(entry.x + 0.15, 0.13, entry.z))
		if index < 2:
			_link(Vector3(exit.x - 0.15, 0.13, exit.z), exits[index])
		else:
			_link(Vector3(exit.x - 0.3, 0.13, exit.z), Vector3(-253.25, 0.13, exit.z + 1.6))
	_field_navigation_rect(Rect2(-254.2, -92.0, 1.8, 74.0))
	_link(Vector3(-253.25, 0.13, -19.0), rear_join)

func _field_navigation_rect(rect: Rect2) -> void:
	var mesh := NavigationMesh.new()
	mesh.vertices = PackedVector3Array([
		Vector3(rect.position.x, 0.13, rect.position.y),
		Vector3(rect.end.x, 0.13, rect.position.y),
		Vector3(rect.end.x, 0.13, rect.end.y),
		Vector3(rect.position.x, 0.13, rect.end.y)])
	mesh.add_polygon(PackedInt32Array([0, 3, 2, 1]))
	var region := NavigationRegion3D.new()
	region.name = "StandPassageNavigation"
	region.navigation_mesh = mesh
	add_child(region, true)

func _add_stair_flights(points: Array) -> void:
	for index in range(1, points.size()):
		var start := Points.point(points[index - 1])
		var end := Points.point(points[index])
		if end.y - start.y < 0.5:
			continue
		var direction := Vector3(end.x - start.x, 0, end.z - start.z).normalized()
		var area := AABB(start, Vector3.ZERO).expand(end).grow(0.62)
		stair_flights.append({"area": area, "direction": direction})

func is_ascending_stair(at: Vector3, direction: Vector3) -> bool:
	for flight in stair_flights:
		if (flight.area as AABB).has_point(at) and direction.dot(flight.direction) > 0.55:
			return true
	return false

func is_dorm_zone(zone: int) -> bool:
	return zone >= DORM_FLOOR_ONE and zone <= DORM_FLOOR_TWO + 12

func _add_classroom_door(doors: Node, record: Dictionary, zone: int) -> void:
	var index: int = doors.doors.find_custom(func(door: Dictionary): return door.id == record.id)
	if index < 0:
		push_error("Missing native classroom door binding: " + str(record.id))
		return
	var door: Dictionary = doors.doors[index]
	var closed: bool = record.building == "B15" and int(record.floor) == 1 and int(record.room) == 0
	door.open = not closed
	door.inside_zone = zone
	for leaf: Dictionary in door.pivots:
		leaf.node.rotation.y = float(leaf.closed_angle) if closed else float(leaf.open_angle)
	var outside := int(record.floor) if record.building == "B15" else SECOND_CORRIDOR + int(record.floor)
	_register_door(index, door, zone, outside)

func _register_door(index: int, door: Dictionary, inside: int, outside: int) -> void:
	var point: Vector3 = door.center
	var direction: Vector3 = door.outward
	var link := NavigationLink3D.new()
	link.start_position = point - direction * 0.95
	link.end_position = point + direction * 0.95
	link.enabled = door.open
	add_child(link)
	passages.append({"from": inside, "to": outside, "point": point, "door": index, "link": link})

func stair_route(at: Vector3, next: Vector3) -> PackedVector3Array:
	if absf(at.y - next.y) < 2.0:
		return PackedVector3Array()
	for entry in stair_routes:
		var start: Vector3 = entry.from
		var finish: Vector3 = entry.to
		if at.distance_to(start) < 0.9 and next.distance_to(finish) < 1.1:
			return entry.points.duplicate()
		if at.distance_to(finish) < 0.9 and next.distance_to(start) < 1.1:
			var reverse: PackedVector3Array = entry.points.duplicate()
			reverse.reverse()
			return reverse
	return PackedVector3Array()

func zone_at(point: Vector3) -> int:
	for building: Dictionary in dorm_buildings:
		var local := DormAccess.source_frame(building.frame).affine_inverse() * point
		var outline := PackedVector2Array()
		for corner: Array in building.outline:
			outline.append(Vector2(float(corner[0]), float(corner[1])))
		if not Geometry2D.is_point_in_polygon(Vector2(local.x, local.y), outline):
			continue
		var closest := INF
		var floor_number := 0
		for level: Dictionary in building.levels:
			var distance := absf(local.z - float(level.z))
			if distance < closest:
				closest = distance
				floor_number = int(level.floor)
		if closest < 1.8:
			return _dorm_zone(building.building, floor_number)
	var dorm_offset := point - dorm_start
	var dorm_forward := dorm_offset.dot(dorm_axis)
	var dorm_cross := dorm_offset.dot(Vector3(-dorm_axis.z, 0.0, dorm_axis.x))
	if dorm_forward >= -0.5 and dorm_forward <= dorm_length + 0.3 and absf(dorm_cross) < 12.4:
		if absf(point.y - 0.57) < 1.7:
			return DORM_FLOOR_ONE
		if absf(point.y - 4.2) < 1.7:
			return DORM_FLOOR_TWO
	for room in room_regions:
		var offset: Vector3 = point - room.start
		var length: float = offset.dot(room.axis)
		var depth: float = offset.dot(room.outward)
		if absf(offset.y) < 2.15 and length > -0.85 and length < float(room.length) + 0.85 and depth < -0.06 and depth > -8.0:
			return int(room.zone)
	for building in building_regions:
		var flat: Vector3 = point - building.anchor
		var forward: float = flat.dot(building.along)
		var cross: float = flat.dot(building.across)
		if forward < 0.4 or forward > 92.0 or cross < -7.3 or cross > 7.3:
			continue
		for floor in Points.FLOOR_HEIGHTS.size():
			if absf(point.y - Points.FLOOR_HEIGHTS[floor]) < 2.15:
				return int(building.base) + floor
	return OUTSIDE
