extends Node

const DOOR_DATA := "res://assets/campus/campus_entrances.json"
const REACH := 3.5
const CLOSED_BUILDING_LAYER := 4
const DOOR_SWEEP_CLEARANCE := 0.32
const DOOR_SWEEP_STEP := PI / 36.0
const CLOSE_INTERACTION_DISTANCE := 0.85
const SWING_BLOCKED := -1
const AUTHORED_SWING := 0
const REVERSED_SWING := 1

signal passage_changed(index: int, opened: bool)

@export var use_campus_data := true

var doors: Array[Dictionary] = []
var nearby := -1
var message_time := 0.0
var room_interaction: Callable
var additional_occupants: Callable

@onready var walker: CharacterBody3D = $"../Walker"
@onready var hint: Label = $"../Interface/DebugControls/Rows/DoorHint"

func _ready() -> void:
	if not use_campus_data:
		return
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DOOR_DATA))
	var visuals := get_parent().get_node("CampusVisuals")
	var pivots_by_name := {}
	for node in visuals.find_children("Campus*Pivot_*", "Node3D", true, false):
		pivots_by_name[String(node.name)] = node
	var locked_buildings := {}
	for record: Dictionary in data.doors:
		var locked := bool(record.get("locked", false))
		var asset_closed := bool(record.get("asset_closed", false))
		if locked:
			locked_buildings[record.building] = true
		var pivots: Array[Dictionary] = []
		for leaf: Dictionary in record.pivots:
			var pivot := pivots_by_name.get(leaf.name) as Node3D
			if pivot == null:
				push_error("Missing campus door pivot: " + str(leaf.name))
				continue
			var width := float(record.width) / 2.0
			var body := StaticBody3D.new()
			body.name = "DoorCollision"
			if locked:
				body.collision_layer |= CLOSED_BUILDING_LAYER
			body.position = Vector3(-float(leaf.side) * width / 2.0, float(record.height) / 2.0, 0)
			pivot.add_child(body)
			var collider := CollisionShape3D.new()
			var box := BoxShape3D.new()
			box.size = Vector3(width, float(record.height), 0.09)
			collider.shape = box
			body.add_child(collider)
			var swing := float(leaf.side) * PI / 2.0
			if record.get("swing_inward", false):
				swing = -swing
			var open_angle := pivot.rotation.y - swing if asset_closed else pivot.rotation.y
			var closed_angle := open_angle + swing
			if locked:
				pivot.rotation.y = closed_angle
			pivots.append({"node": pivot, "open_angle": open_angle, "closed_angle": closed_angle,
				"sweep_tip": -float(leaf.side) * width})
		var point: Array = record.center
		doors.append({"id": record.id, "label": record.label,
			"center": Vector3(float(point[0]), float(point[2]), -float(point[1])),
			"width": float(record.width), "height": float(record.height),
			"pivots": pivots, "locked": locked, "open": not (locked or asset_closed), "moving": false,
			"teaching_sweep": record.building in ["B15", "B21"],
			"allow_opposite_swing": not record.get("swing_inward", false)})
	_bind_native_classroom_doors(pivots_by_name)
	for building: Dictionary in data.get("closed_buildings", []):
		if locked_buildings.has(building.id):
			_block_building_interior(building)

func _bind_native_classroom_doors(pivots_by_name: Dictionary) -> void:
	var points = preload("res://scripts/campus/campus_survival_points.gd")
	for record in points.classroom_doors({}):
		var pivot := pivots_by_name.get(str(record.pivot)) as Node3D
		if pivot == null:
			push_error("Missing native classroom door: " + str(record.pivot))
			continue
		var body := StaticBody3D.new()
		body.name = "NativeDoorCollision"
		body.position = Vector3(0.467, 1.08, 0)
		pivot.add_child(body)
		var collider := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = Vector3(0.933, 2.16, 0.044)
		collider.shape = shape
		body.add_child(collider)
		pivot.rotation.y = float(record.open_angle)
		var label := "致远楼" if record.building == "B15" else "思远楼"
		doors.append({"id": record.id, "label": "%s%d层教室" % [label, int(record.floor) + 1],
			"center": record.point, "outward": record.outward, "width": record.width, "height": record.height,
			"open": true, "locked": false, "moving": false, "lockable": true,
			"swing_outward": record.swing_outward, "teaching_sweep": true, "allow_opposite_swing": true,
			"pivots": [{"node": pivot, "open_angle": record.open_angle, "closed_angle": record.closed_angle,
				"sweep_tip": shape.size.x}]})

func _block_building_interior(building: Dictionary) -> void:
	var vertices := PackedVector3Array()
	for point: Array in building.outline:
		for height: float in [-0.5, float(building.height)]:
			vertices.append(Vector3(float(point[0]), height, -float(point[1])))
	var shape := ConvexPolygonShape3D.new()
	shape.points = vertices
	var collider := CollisionShape3D.new()
	collider.shape = shape
	var body := StaticBody3D.new()
	body.name = "ClosedBuilding_" + str(building.id)
	body.collision_mask = 0
	body.collision_layer = 1 | CLOSED_BUILDING_LAYER
	body.add_child(collider)
	add_child(body)

func _process(delta: float) -> void:
	message_time = maxf(0.0, message_time - delta)
	for door in doors:
		if door.moving:
			if _occupied(door, bool(door.open), int(door.get("swing", AUTHORED_SWING))):
				door.tween.pause()
			else:
				door.tween.play()
	nearby = _interaction_door()
	if message_time > 0.0:
		return
	hint.visible = nearby >= 0
	if nearby >= 0:
		var door := doors[nearby]
		if door.locked:
			hint.text = "%s · %s" % [door.label, "暂未开放" if use_campus_data else "已锁"]
		else:
			var label: String = door.label if door.get("lockable", false) else "%s楼门" % door.label
			hint.text = "E %s%s" % ["关闭" if door.open else "打开", label]

func _interaction_door() -> int:
	var position := walker.global_position
	var camera: Camera3D = walker.get_node("Camera3D")
	var look := -camera.global_basis.z
	var forward := Vector2(look.x, look.z).normalized()
	var nearest := REACH * REACH
	var nearest_index := -1
	var aimed_score := INF
	var aimed_index := -1
	for index in doors.size():
		var door := doors[index]
		var offset: Vector3 = door.center - position
		var distance := offset.length_squared()
		if distance >= REACH * REACH:
			continue
		var teaching := bool(door.get("teaching_sweep", false))
		if teaching and absf(offset.y) > 1.10:
			continue
		if distance < nearest:
			nearest = distance
			nearest_index = index
		if teaching:
			var alignment := forward.dot(Vector2(offset.x, offset.z).normalized())
			var score := distance + (1.0 - alignment) * 9.0
			if alignment >= 0.76 and score < aimed_score:
				aimed_score = score
				aimed_index = index
	if nearest < CLOSE_INTERACTION_DISTANCE * CLOSE_INTERACTION_DISTANCE:
		return nearest_index
	return aimed_index if aimed_index >= 0 else nearest_index

func interact() -> void:
	nearby = _interaction_door()
	if nearby < 0:
		return
	if room_interaction.is_valid():
		room_interaction.call(String(doors[nearby].id))
	else:
		set_open(nearby, not bool(doors[nearby].open))

func set_open(index: int, opened: bool) -> bool:
	var door := doors[index]
	if door.locked or door.moving or door.open == opened:
		return false
	var swing := _available_swing(door, opened)
	if swing == SWING_BLOCKED:
		show_swing_blocked()
		return false
	door.moving = true
	door.open = opened
	door.swing = swing
	if not opened:
		passage_changed.emit(index, false)
	var tween := create_tween().set_parallel(true)
	door.tween = tween
	for leaf: Dictionary in door.pivots:
		tween.tween_property(leaf.node, "rotation:y", _leaf_target(leaf, opened, swing), 0.28)
	tween.finished.connect(func():
		door.moving = false
		door.erase("tween")
		if opened:
			passage_changed.emit(index, true)
	)
	return true

func _exit_tree() -> void:
	for door in doors:
		if door.has("tween"):
			door.tween.kill()
			door.erase("tween")
	doors.clear()

func show_swing_blocked() -> void:
	hint.text = "门扇转动范围内有人，请稍微让开"
	hint.visible = true
	message_time = 2.0


func _available_swing(door: Dictionary, opening: bool, opener := Vector3.INF) -> int:
	if not _occupied(door, opening, AUTHORED_SWING, opener):
		return AUTHORED_SWING
	if opening and door.get("allow_opposite_swing", false) and not _occupied(door, true, REVERSED_SWING, opener):
		return REVERSED_SWING
	return SWING_BLOCKED


func _leaf_target(leaf: Dictionary, opening: bool, swing: int) -> float:
	if not opening:
		return float(leaf.closed_angle)
	return float(leaf.closed_angle) * 2.0 - float(leaf.open_angle) if swing == REVERSED_SWING else float(leaf.open_angle)


func _occupied(door: Dictionary, opening: bool, swing: int, opener := Vector3.INF) -> bool:
	if opener != Vector3.INF and _feet_in_swing(opener, door, opening, swing):
		return true
	if _feet_in_swing(walker.global_position, door, opening, swing):
		return true
	if additional_occupants.is_valid():
		for position: Vector3 in additional_occupants.call():
			if _feet_in_swing(position, door, opening, swing):
				return true
	return false


func _feet_in_swing(feet: Vector3, door: Dictionary, opening: bool, swing: int) -> bool:
	var center: Vector3 = door.center
	if feet.y >= center.y + float(door.height) or feet.y + 1.73 <= center.y:
		return false
	var horizontal := Vector2(feet.x - center.x, feet.z - center.z).length()
	if horizontal >= sqrt(2.0) * float(door.width) / 2.0 + 0.55:
		return false
	for leaf: Dictionary in door.pivots:
		if not leaf.has("sweep_tip") or _leaf_crosses_player(feet, leaf, opening, swing):
			return true
	return false


func _leaf_crosses_player(feet: Vector3, leaf: Dictionary, opening: bool, swing: int) -> bool:
	var pivot: Node3D = leaf.node
	var target := _leaf_target(leaf, opening, swing)
	var start := pivot.rotation.y
	var samples := maxi(1, ceili(absf(target - start) / DOOR_SWEEP_STEP))
	var parent_transform := (pivot.get_parent() as Node3D).global_transform
	var hinge := Vector2(pivot.global_position.x, pivot.global_position.z)
	var point := Vector2(feet.x, feet.z)
	var previous_distance := INF
	var moving_away_from_contact := false
	for sample in samples + 1:
		var angle := lerpf(start, target, float(sample) / samples)
		var direction := Basis(Vector3.UP, angle - start) * pivot.transform.basis.x
		var tip := parent_transform * (pivot.position + direction * float(leaf.sweep_tip))
		var nearest := Geometry2D.get_closest_point_to_segment(point, hinge, Vector2(tip.x, tip.z))
		var distance := point.distance_to(nearest)
		if sample == 0:
			moving_away_from_contact = opening and distance >= 0.25 and distance < DOOR_SWEEP_CLEARANCE
		elif distance >= DOOR_SWEEP_CLEARANCE:
			moving_away_from_contact = false
		elif not moving_away_from_contact or distance <= previous_distance:
			return true
		previous_distance = distance
	return false


func room_swing(door_id: String, position: Vector3) -> int:
	var index := _index_for_id(door_id)
	if index < 0:
		return SWING_BLOCKED
	var door := doors[index]
	if door.locked or door.moving or position.distance_squared_to(door.center) >= REACH * REACH:
		return SWING_BLOCKED
	return _available_swing(door, not bool(door.open), position)

func room_open(door_id: String) -> bool:
	var index := _index_for_id(door_id)
	return index >= 0 and bool(doors[index].open)

func apply_room_state(door_id: String, opened: bool, swing: int) -> void:
	var index := _index_for_id(door_id)
	if index < 0:
		return
	var door := doors[index]
	if door.locked or door.open == opened:
		return
	door.open = opened
	for leaf: Dictionary in door.pivots:
		leaf.node.rotation.y = _leaf_target(leaf, opened, swing)
	passage_changed.emit(index, opened)

func _index_for_id(door_id: String) -> int:
	for index in doors.size():
		if doors[index].id == door_id:
			return index
	return -1
