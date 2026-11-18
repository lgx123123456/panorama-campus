extends Node

const SNAPSHOT_PERIOD := 0.10
# Leaves room for RPC headers within Iroh's 1162-byte datagram budget.
const MAX_VISIBLE := 54
const RENDER_DISTANCE := 55.0

var session: Node
var level: Node3D
var replicas := {}
var _remaining := 0.0
var _round_announced := false
var _last_shot := {}
var _last_bite := {}
var _last_snapshot := 0
var _snapshot_number := 0
var _next_zombie_id := 1
var _survivor_frame := -1
var _survivors := {}


func _ready() -> void:
	level.coop_session = self
	level.set_physics_process(false)
	level.campaign.set_physics_process(false)
	level.spawner.set_physics_process(false)
	set_process(false)
	set_physics_process(false)


func begin() -> void:
	level.set_physics_process(true)
	level.campaign.set_physics_process(true)
	level.spawner.set_physics_process(Net.is_host())
	set_process(not Net.is_host())
	set_physics_process(Net.is_host())


func _physics_process(delta: float) -> void:
	if not session.active:
		return
	if level.round_finished and not _round_announced:
		_round_announced = true
		_finish_team.rpc(level.result.text)
	_remaining -= delta
	if _remaining > 0.0:
		return
	_remaining = SNAPSHOT_PERIOD
	_snapshot_number += 1
	for id: int in session.remote_states:
		_send_zombies(id, session.remote_states[id].position)


func _send_zombies(peer_id: int, at: Vector3) -> void:
	var visible: Array = []
	for zombie in level.spawner.zombies:
		if not is_instance_valid(zombie):
			continue
		var distance: float = zombie.global_position.distance_squared_to(at)
		if distance <= RENDER_DISTANCE * RENDER_DISTANCE:
			visible.append([distance, zombie])
	if visible.size() > MAX_VISIBLE:
		visible.sort_custom(func(a: Array, b: Array): return a[0] < b[0])
		visible.resize(MAX_VISIBLE)
	# A full crowd snapshot fits in one ENet packet.
	var ids := PackedInt32Array()
	var points := PackedVector3Array()
	var poses := PackedInt32Array()
	for entry: Array in visible:
		var zombie: Node3D = entry[1]
		if zombie.room_snapshot_id == 0:
			zombie.room_snapshot_id = _next_zombie_id
			_next_zombie_id += 1
		ids.append(zombie.room_snapshot_id)
		points.append(zombie.global_position)
		var yaw := roundi(fposmod(zombie.rotation.y, TAU) * (65535.0 / TAU))
		var speed := clampi(roundi(zombie.move_speed * 32.0), 0, 255)
		var flags: int = int(zombie.appearance_identity) * 2 + int(zombie.state == zombie.State.BITE)
		poses.append((yaw << 16) | (speed << 8) | flags)
	_receive_zombies.rpc_id(peer_id, _snapshot_number, ids, points, poses)


@rpc("authority", "call_remote", "unreliable", 1)
func _receive_zombies(sequence: int, ids: PackedInt32Array, points: PackedVector3Array, poses: PackedInt32Array) -> void:
	if not session.active or sequence <= _last_snapshot or ids.size() > MAX_VISIBLE \
			or ids.size() != points.size() or ids.size() != poses.size():
		return
	_last_snapshot = sequence
	var present := {}
	for index in ids.size():
		var id := ids[index]
		present[id] = true
		var packed_pose := poses[index]
		var flags := packed_pose & 0xff
		var pose := Vector3(float((packed_pose >> 16) & 0xffff) * (TAU / 65535.0),
			float((packed_pose >> 8) & 0xff) / 32.0, float(flags))
		if not replicas.has(id):
			var identity := clampi(flags >> 1, 0, 3)
			var zombie: Node3D = level.spawner._spawn(points[index], identity)
			replicas[id] = {"node": zombie, "position": points[index], "pose": pose}
		else:
			replicas[id].position = points[index]
			replicas[id].pose = pose
	for id: int in replicas.keys():
		if not present.has(id):
			var zombie: Node3D = replicas[id].node
			level.spawner.zombies.erase(zombie)
			zombie.queue_free()
			replicas.erase(id)


func _process(delta: float) -> void:
	var blend := 1.0 - exp(-16.0 * delta)
	for state: Dictionary in replicas.values():
		var zombie: Node3D = state.node
		var pose: Vector3 = state.pose
		var at: Vector3 = state.position
		zombie.global_position = at if zombie.global_position.distance_squared_to(at) > 16.0 \
			else zombie.global_position.lerp(at, blend)
		zombie.rotation.y = lerp_angle(zombie.rotation.y, pose.x, blend)
		if posmod(int(pose.z), 2) == 1 and zombie.look.gesture == &"":
			zombie.look.perform(&"attack-melee-right")
		else:
			zombie.look.locomotion(pose.y, pose.y > 1.7)


func remote_survivors() -> Dictionary:
	var frame := Engine.get_physics_frames()
	if _survivor_frame != frame:
		_survivor_frame = frame
		_survivors.clear()
		for id: int in session.remote_states:
			var state: Dictionary = session.remote_states[id]
			if not state.finished and not state.infected:
				_survivors[id] = state.position
	return _survivors


func can_bite(id: int, zombie: Node3D) -> bool:
	var remote: Dictionary = session.remote_states.get(id, {})
	if remote.is_empty() or remote.infected or remote.finished or level.round_finished:
		return false
	if Time.get_ticks_msec() < int(_last_bite.get(id, 0)):
		return false
	var at: Vector3 = remote.position
	var separation := at - zombie.global_position
	if separation.length_squared() > level.zombie_attack_range * level.zombie_attack_range or absf(separation.y) > 0.72:
		return false
	return level.clear_line(zombie.global_position + Vector3.UP, at + Vector3.UP) \
		and level.clear_line(zombie.global_position + Vector3.UP * 0.45, at + Vector3.UP * 0.45)


func bite_remote(id: int, zombie: Node3D) -> void:
	if Net.is_host() and can_bite(id, zombie):
		_last_bite[id] = Time.get_ticks_msec() + 850
		_receive_bite.rpc_id(id)


@rpc("authority", "call_remote", "reliable")
func _receive_bite() -> void:
	level._player_bitten(true)


func send_shot(eye: Vector3, direction: Vector3, weapon: String, aiming: bool) -> void:
	if session.active and not Net.is_host():
		_request_shot.rpc_id(1, eye, direction, weapon, aiming)


@rpc("any_peer", "call_remote", "reliable")
func _request_shot(eye: Vector3, direction: Vector3, weapon: String, aiming: bool) -> void:
	if not Net.is_host() or not session.active or level.round_finished or not eye.is_finite() or not direction.is_finite():
		return
	var id := multiplayer.get_remote_sender_id()
	var remote: Dictionary = session.remote_states.get(id, {})
	if remote.is_empty() or remote.infected or remote.finished or not level.firearms.weapon_stats.has(weapon):
		return
	var at: Vector3 = remote.position
	if not is_equal_approx(direction.length_squared(), 1.0) or at.distance_squared_to(eye) > 6.25:
		return
	var now := Time.get_ticks_msec()
	if now < int(_last_shot.get(id, 0)) or not level.clear_line(at + Vector3.UP * 0.9, eye):
		return
	var fire_rate: float = level.firearms.weapon_stats[weapon].fire_rate
	_last_shot[id] = now + int(650.0 / fire_rate)
	var feedback: Dictionary = level.firearms.resolve_room_shot(eye, direction.normalized(), weapon, aiming)
	level._emit_sound(at, 45.0, &"gunshot")
	_remote_gunshot.rpc(id, at, weapon)
	if not feedback.is_empty():
		_confirm_hit.rpc_id(id, feedback)


@rpc("authority", "call_local", "unreliable", 1)
func _remote_gunshot(shooter: int, at: Vector3, weapon: String) -> void:
	if shooter != Net.local_id() and level.firearms.weapon_stats.has(weapon):
		Audio.play_3d(level.firearms.weapon_stats[weapon].sfx, at, -8.0, 0.05, 65.0)


@rpc("authority", "call_remote", "reliable")
func _confirm_hit(feedback: Dictionary) -> void:
	level.firearms.show_room_hit(feedback)


func report_supply(kind: StringName) -> void:
	if session.active and not Net.is_host() and kind in [&"roof", &"field"]:
		_supply_encounter.rpc_id(1, kind)


@rpc("any_peer", "call_remote", "reliable")
func _supply_encounter(kind: StringName) -> void:
	if not Net.is_host() or not session.active or level.round_finished:
		return
	var id := multiplayer.get_remote_sender_id()
	var remote: Dictionary = session.remote_states.get(id, {})
	if remote.is_empty() or remote.infected or remote.finished:
		return
	level.campaign.start_room_pickup_encounter(kind, remote.position)


@rpc("authority", "call_remote", "reliable")
func _finish_team(message: String) -> void:
	if not level.round_finished:
		level._finish("队伍结算 · %s" % message)
