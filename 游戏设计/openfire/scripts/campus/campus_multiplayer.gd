extends Node

const CampusLook := preload("res://scripts/campus/campus_character_look.gd")
const ScooterModel := preload("res://assets/campus/tour/campus_e_scooter.glb")
const Combat := preload("res://scripts/campus/campus_room_combat.gd")
const SNAPSHOT_INTERVAL := 1.0 / 20.0
const INTERPOLATION_RATE := 16.0
const READY_TIMEOUT := 60.0
# Clear standing positions in the B15 second-floor classroom aisle.
const CLASSROOM_SPAWNS := [
	Vector2(0, 0), Vector2(-0.68, 0), Vector2(0, -0.68), Vector2(0, 0.68),
	Vector2(-0.68, -0.68), Vector2(-0.68, 0.68), Vector2(0, 1.36),
	Vector2(-0.68, 1.36), Vector2(-2.04, 0.68), Vector2(-0.68, 2.04),
]

var remote_states := {}
var avatars := {}
var active := false
var _leaving := false
var _send_time := 0.0
var _sequence := 0
var _next_door_request := {}
var _status: Label
var combat: Node
var _survival: Node
var _tour: bool

@onready var walker = $"../Walker"
@onready var world = get_parent()
@onready var doors = $"../Doors"


func _ready() -> void:
	if not Net.campus_started:
		_leave.call_deferred("请从校园房间开始联机。")
		return
	_tour = Net.campus_mode == Net.CampusMode.EXPLORE
	_survival = world.get_node_or_null("CharacterTrial")
	walker.leave_session = _leave
	walker.set_physics_process(false)
	_status = Label.new()
	_status.add_theme_color_override("font_shadow_color", Color.BLACK)
	_status.add_theme_constant_override("shadow_offset_y", 2)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var interface: CanvasLayer = world.get_node("TourInterface" if _tour else "Interface")
	interface.add_child(_status)
	_status.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_status.offset_left = -304
	_status.offset_right = -22
	_status.offset_top = 24
	if _tour:
		var scooter = walker.scooter
		scooter.parked_transform.origin += _spawn_offset()
		scooter.reset_to_gate()
	else:
		combat = Combat.new()
		combat.name = "CoopCombat"
		combat.session = self
		combat.level = _survival
		add_child(combat)
	_status.text = "校园联机 · 等待玩家加载"

	walker.spawn.position += _spawn_offset()
	walker._reset_position()
	doors.room_interaction = request_door
	if Net.is_host():
		world.additional_collision_positions = _remote_positions
		doors.additional_occupants = _remote_positions
	Net.players_changed.connect(_reconcile_roster)
	Net.campus_ready.connect(_begin)
	Net.server_disconnected.connect(_host_left)
	Net.campus_mode_changed.connect(_change_mode)
	Net.report_campus_loaded.call_deferred()
	get_tree().create_timer(READY_TIMEOUT).timeout.connect(_load_timeout)

func _spawn_offset() -> Vector3:
	var roster: Array = Net.players.keys()
	roster.sort()
	var slot := maxi(0, roster.find(Net.local_id()))
	if _tour:
		return Vector3(1.4 * float(slot % 4), 0, 1.4 * floorf(float(slot) / 4.0))
	var spot: Vector2 = CLASSROOM_SPAWNS[slot]
	return walker.spawn.basis * Vector3(spot.x, 0, spot.y)


func _change_mode() -> void:
	if _leaving:
		return
	active = false
	walker.set_physics_process(false)
	get_tree().change_scene_to_file.call_deferred(Net.campus_scene())

func _begin() -> void:
	active = true
	walker.set_physics_process(true)
	if combat != null:
		combat.begin()
	_reconcile_roster()

func _load_timeout() -> void:
	if not active:
		_leave("等待校园加载超时，请重新开房。")

func _host_left() -> void:
	_leave(Net.leave_message)

func _leave(message := "") -> void:
	if _leaving:
		return
	_leaving = true
	active = false
	if not message.is_empty():
		Net.leave_message = message
	Net.disconnect_net()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	get_tree().change_scene_to_file.call_deferred("res://scenes/main_menu.tscn")

func _reconcile_roster() -> void:
	if not active:
		return
	_status.text = "%s · %d/%d 人" % [Net.CAMPUS_MODE_NAMES[Net.campus_mode], Net.players.size(), Net.CAMPUS_MAX_PLAYERS]
	for id: int in remote_states.keys():
		if not Net.players.has(id):
			remote_states.erase(id)
			_next_door_request.erase(id)
			if avatars.has(id):
				avatars[id].get_parent().queue_free()
				avatars.erase(id)

func _physics_process(delta: float) -> void:
	if not active or Net.players.size() < 2:
		return
	_send_time -= delta
	if _send_time > 0.0:
		return
	_send_time = SNAPSHOT_INTERVAL
	_sequence += 1
	var position: Vector3 = walker.global_position
	var yaw: float = walker.global_rotation.y
	var speed: float = Vector2(walker.velocity.x, walker.velocity.z).length()
	var transport: int = walker.mode if _tour else 0
	var form := 0 if _tour else int(walker.role)
	var finished := false if _tour else bool(_survival.round_finished)
	var bike_pose := Transform3D.IDENTITY
	if transport == 2:
		bike_pose = walker.scooter.chassis.global_transform
	var data := [position, yaw, speed, transport, bike_pose, form, finished]
	if Net.is_host():
		_receive_snapshot.rpc(1, _sequence, data)
	else:
		_submit_snapshot.rpc_id(1, _sequence, data)

@rpc("any_peer", "call_remote", "unreliable", 1)
func _submit_snapshot(sequence: int, data: Array) -> void:
	if not active or not is_inside_tree() or not Net.is_host():
		return
	var sender := multiplayer.get_remote_sender_id()
	if not _record_snapshot(sender, sequence, data):
		return
	for id: int in Net.players:
		if id != 1 and id != sender:
			_receive_snapshot.rpc_id(id, sender, sequence, data)

@rpc("authority", "call_remote", "unreliable", 1)
func _receive_snapshot(id: int, sequence: int, data: Array) -> void:
	_record_snapshot(id, sequence, data)

func _record_snapshot(id: int, sequence: int, data: Array) -> bool:
	if not active or not Net.players.has(id) or id == Net.local_id() or data.size() != 7:
		return false
	if typeof(data[0]) != TYPE_VECTOR3 or typeof(data[1]) != TYPE_FLOAT or typeof(data[2]) != TYPE_FLOAT \
			or typeof(data[3]) != TYPE_INT or typeof(data[4]) != TYPE_TRANSFORM3D \
			or typeof(data[5]) != TYPE_INT or typeof(data[6]) != TYPE_BOOL:
		return false
	var position: Vector3 = data[0]
	var yaw: float = data[1]
	var speed: float = data[2]
	var bike: Transform3D = data[4]
	if not position.is_finite() or not is_finite(yaw) or not is_finite(speed) or not bike.is_finite():
		return false
	if maxf(maxf(absf(position.x), absf(position.y)), absf(position.z)) > 4096.0:
		return false
	if data[3] not in [0, 1, 2] or data[5] not in [0, 1, 2]:
		return false
	if data[3] == 2 and (bike.origin.distance_squared_to(position) > 4.0 or not is_equal_approx(bike.basis.determinant(), 1.0)):
		return false
	var previous: Dictionary = remote_states.get(id, {})
	if sequence <= int(previous.get("sequence", 0)):
		return false
	remote_states[id] = {"sequence": sequence, "position": position, "yaw": yaw,
		"speed": clampf(speed, 0.0, 16.0), "transport": data[3], "bike": bike,
		"infected": int(data[5]) != 0, "finished": data[6]}
	return true

func _process(delta: float) -> void:
	if not active:
		return
	var blend := 1.0 - exp(-INTERPOLATION_RATE * delta)
	for id: int in remote_states:
		var state: Dictionary = remote_states[id]
		if not avatars.has(id):
			_add_avatar(id, state.position, state.yaw)
		var avatar: Node3D = avatars[id]
		var marker: Node3D = avatar.get_parent()
		var target: Vector3 = state.position
		marker.position = target if marker.position.distance_squared_to(target) > 36.0 \
			else marker.position.lerp(target, blend)
		var scooter: Node3D = marker.get_node_or_null("Motorcycle")
		var pack: Node3D = avatar.get_node_or_null("RemotePack")
		if avatar.infected != state.infected:
			avatar.set_appearance(avatar.identity, state.infected)
		if is_instance_valid(pack):
			pack.visible = state.transport == 1
		if is_instance_valid(scooter):
			scooter.visible = state.transport == 2
		if state.transport == 2 and scooter != null:
			var bike: Transform3D = state.bike
			scooter.global_transform = Transform3D(bike.basis.orthonormalized() * Basis(Vector3.UP, PI), marker.position)
			avatar.global_basis = bike.basis.orthonormalized()
			avatar.position = (bike.basis * Vector3(0, 0.28, 0.18))
			avatar.set_crouched(true)
			avatar.locomotion(0.0)
		else:
			avatar.position = Vector3.ZERO
			avatar.rotation = Vector3(0.0, lerp_angle(avatar.rotation.y, state.yaw, blend), 0.0)
			avatar.set_crouched(false)
			avatar.locomotion(0.0 if state.transport == 1 else state.speed, state.speed > 4.0)

func _add_avatar(id: int, position: Vector3, yaw: float) -> void:
	var avatar := CampusLook.new()
	var marker := Node3D.new()
	marker.name = "Peer%d" % id
	marker.position = position
	avatar.identity = 0 if id == 1 else 1
	avatar.rotation.y = yaw
	if _tour:
		var scooter := ScooterModel.instantiate() as Node3D
		scooter.name = "Motorcycle"
		scooter.hide()
		marker.add_child(scooter)
		var pack: Node3D = walker.jetpack.duplicate()
		pack.name = "RemotePack"
		pack.hide()
		avatar.add_child(pack)
	var label := Label3D.new()
	label.text = Net.get_player_name(id)
	label.position.y = 1.92
	label.pixel_size = 0.004
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	marker.add_child(label)
	marker.add_child(avatar)
	add_child(marker)
	avatars[id] = avatar

func _remote_positions() -> PackedVector3Array:
	var positions := PackedVector3Array()
	for state: Dictionary in remote_states.values():
		positions.append(state.position)
	return positions

func request_door(door_id: String) -> void:
	if not active:
		return
	if Net.is_host():
		_toggle_door(1, door_id, walker.global_position)
	else:
		_request_host_door.rpc_id(1, door_id, walker.global_position)

@rpc("any_peer", "call_remote", "reliable")
func _request_host_door(door_id: String, position: Vector3) -> void:
	if not active or not is_inside_tree() or not Net.is_host() or not position.is_finite():
		return
	var sender := multiplayer.get_remote_sender_id()
	if remote_states.has(sender) and position.distance_squared_to(remote_states[sender].position) <= 1.0:
		_toggle_door(sender, door_id, position)

func _toggle_door(sender: int, door_id: String, position: Vector3) -> void:
	var now := Time.get_ticks_msec()
	if now < int(_next_door_request.get(sender, 0)) or door_id.length() > 96:
		return
	_next_door_request[sender] = now + 250
	var swing: int = doors.room_swing(door_id, position)
	if swing >= 0:
		_apply_door.rpc(door_id, not doors.room_open(door_id), swing)

@rpc("authority", "call_local", "reliable")
func _apply_door(door_id: String, opened: bool, swing: int) -> void:
	doors.apply_room_state(door_id, opened, swing)
