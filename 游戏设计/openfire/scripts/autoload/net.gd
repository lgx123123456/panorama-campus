extends Node
## ENet for LAN and direct IP, Iroh or EOS for campus invitations.
##
## The host is always peer id 1 and is authoritative for game logic and bots.
## "Solo vs bots" is just a host on localhost that starts immediately, so there
## is a single code path for offline and networked play.

signal players_changed
signal connection_succeeded
signal connection_failed
signal server_disconnected
signal match_started
signal campus_ready
signal campus_mode_changed

const DEFAULT_PORT := 27015
const MAX_PLAYERS := 8
const CAMPUS_MAX_PLAYERS := 10
const CAMPUS_PROTOCOL := 3
const CAMPUS_SCENE := "res://scenes/campus/multiplayer.tscn"
const CAMPUS_SURVIVAL_SCENE := "res://scenes/campus/multiplayer_survival.tscn"
enum CampusMode { EXPLORE, SURVIVAL }
const CAMPUS_MODE_NAMES := ["自由探索", "丧尸模式"]
const IROH_INVITE_PREFIX := "OF-"
const IROH_ID_LENGTH := 43
const IROH_DISCOVERY_RETRY_MS := 16000

var peer: MultiplayerPeer
var campus_room := false
var campus_started := false
var campus_mode: int = CampusMode.EXPLORE
var room_code := ""
var leave_message := ""
var _campus_loaded: Dictionary = {}
var _campus_running := false
var _awaiting_campus_registration := false
var _iroh_discovery_deadline := 0
# peer_id -> { "name": String }
var players: Dictionary = {}

func _ready() -> void:
	multiplayer.peer_connected.connect(_on_peer_connected)
	multiplayer.peer_disconnected.connect(_on_peer_disconnected)
	multiplayer.connected_to_server.connect(_on_connected_to_server)
	multiplayer.connection_failed.connect(_on_connection_failed)
	multiplayer.server_disconnected.connect(_on_server_disconnected)

func host_game(port: int = DEFAULT_PORT, campus := false, mode: int = CampusMode.EXPLORE) -> bool:
	var enet := ENetMultiplayerPeer.new()
	var limit := CAMPUS_MAX_PLAYERS - 1 if campus else MAX_PLAYERS
	var err := enet.create_server(port, limit)
	if err != OK:
		push_error("Net: failed to create server on port %d (err %d)" % [port, err])
		return false
	_host_with_peer(enet, campus, mode)
	return true

func _host_with_peer(connection: MultiplayerPeer, campus: bool, mode: int = CampusMode.EXPLORE) -> void:
	campus_room = campus
	campus_mode = clampi(mode, CampusMode.EXPLORE, CampusMode.SURVIVAL)
	peer = connection
	multiplayer.multiplayer_peer = connection
	players.clear()
	players[1] = {"name": clean_campus_name(Game.player_name) if campus else Game.player_name}
	players_changed.emit()

func join_game(ip: String, port: int = DEFAULT_PORT, campus := false) -> bool:
	var enet := ENetMultiplayerPeer.new()
	var err := enet.create_client(ip, port)
	if err != OK:
		push_error("Net: failed to create client to %s:%d (err %d)" % [ip, port, err])
		return false
	_join_with_peer(enet, campus)
	return true

func _join_with_peer(connection: MultiplayerPeer, campus: bool) -> void:
	campus_room = campus
	peer = connection
	multiplayer.multiplayer_peer = connection
	if campus:
		_awaiting_campus_registration = true
		get_tree().create_timer(20.0).timeout.connect(func():
			if peer == connection and _awaiting_campus_registration:
				leave_message = "连接房间超时，请检查版本和房主是否在线。"
				_on_connection_failed()
		)

func open_online_campus(code: String, host: bool, mode: int = CampusMode.EXPLORE) -> String:
	if peer != null:
		return "请先退出当前房间。"
	code = code.strip_edges()
	if host and not CampusOnline.configured():
		return _host_campus_iroh(mode)
	if not host and code.begins_with(IROH_INVITE_PREFIX):
		return _join_campus_iroh(code)
	var message: String = await CampusOnline.open_room(code, host)
	if not message.is_empty():
		return message
	room_code = CampusOnline.room_code
	if host:
		_host_with_peer(CampusOnline.room_peer, true, mode)
	else:
		_join_with_peer(CampusOnline.room_peer, true)
	return ""

func _host_campus_iroh(mode: int) -> String:
	var connection := IrohServer.start()
	if connection == null or connection.get_connection_status() != MultiplayerPeer.CONNECTION_CONNECTED:
		return "异地房间启动失败，请检查网络后重试。"
	room_code = IROH_INVITE_PREFIX + connection.connection_string()
	_host_with_peer(connection, true, mode)
	return ""

func _join_campus_iroh(invite: String) -> String:
	var endpoint_id := invite.trim_prefix(IROH_INVITE_PREFIX)
	if endpoint_id.length() != IROH_ID_LENGTH:
		return "请粘贴房主复制的完整邀请码。"
	var base64 := endpoint_id.replace("-", "+").replace("_", "/") + "="
	var key := Marshalls.base64_to_raw(base64)
	if key.size() != 32 or Marshalls.raw_to_base64(key) != base64:
		return "邀请码格式有误，请向房主重新复制。"
	var connection := IrohClient.network_connect(endpoint_id)
	if connection == null:
		return "异地连接启动失败，请检查网络后重试。"
	room_code = invite
	_iroh_discovery_deadline = Time.get_ticks_msec() + IROH_DISCOVERY_RETRY_MS
	_join_with_peer(connection, true)
	return ""

func disconnect_net() -> void:
	var connection := peer
	multiplayer.multiplayer_peer = null
	peer = null
	if connection != null and connection != CampusOnline.room_peer:
		connection.close()
	players.clear()
	campus_room = false
	campus_started = false
	campus_mode = CampusMode.EXPLORE
	room_code = ""
	_campus_loaded.clear()
	_campus_running = false
	_awaiting_campus_registration = false
	_iroh_discovery_deadline = 0
	CampusOnline.close_room()
	players_changed.emit()

func is_host() -> bool:
	return multiplayer.multiplayer_peer != null and multiplayer.is_server()

func local_id() -> int:
	if multiplayer.multiplayer_peer == null:
		return 1
	return multiplayer.get_unique_id()

func get_player_name(id: int) -> String:
	if players.has(id):
		return players[id]["name"]
	return "同学 %d" % id

# ---------------------------------------------------------------- connection cb

func _on_peer_connected(_id: int) -> void:
	# Server waits for the newcomer to register its name (see _register_player).
	pass

func _on_peer_disconnected(id: int) -> void:
	if is_host():
		players.erase(id)
		_campus_loaded.erase(id)
		_sync_players.rpc(players)
		players_changed.emit()
		_try_begin_campus()

func _on_connected_to_server() -> void:
	# Client side: announce our chosen name to the host.
	if campus_room:
		_register_campus_player.rpc_id(1, Game.player_name, CAMPUS_PROTOCOL)
		return
	_register_player.rpc_id(1, Game.player_name)
	connection_succeeded.emit()

func _on_connection_failed() -> void:
	if peer is IrohClient:
		var detail: String = peer.connection_error()
		if detail.contains("No addressing information available") \
				and Time.get_ticks_msec() < _iroh_discovery_deadline:
			var failed_peer := peer
			get_tree().create_timer(1.0).timeout.connect(func():
				if peer == failed_peer and _awaiting_campus_registration:
					var connection := IrohClient.network_connect(room_code.trim_prefix(IROH_INVITE_PREFIX))
					_join_with_peer(connection, true)
			)
			return
		if not detail.is_empty():
			print("Campus Iroh connection failed: ", detail)
		if leave_message.is_empty():
			leave_message = "无法连接异地房间，请确认房主仍在线，并使用当前邀请码。"
	disconnect_net()
	connection_failed.emit()

func _on_server_disconnected() -> void:
	if campus_room:
		leave_message = "房主已退出，校园房间已结束。"
	disconnect_net()
	server_disconnected.emit()

# ---------------------------------------------------------------- rpcs

@rpc("any_peer", "reliable")
func _register_player(pname: String) -> void:
	if not is_host():
		return
	var id := multiplayer.get_remote_sender_id()
	if campus_room:
		_campus_rejected.rpc_id(id, "请从「校园联机」加入这个房间。")
		return
	players[id] = {"name": pname}
	# Bring the newcomer (and everyone) up to date.
	_sync_players.rpc(players)
	_sync_config.rpc(Game.config)
	players_changed.emit()

@rpc("any_peer", "reliable")
func _register_campus_player(pname: String, protocol: int) -> void:
	if not is_host():
		return
	var id := multiplayer.get_remote_sender_id()
	if not campus_room or protocol != CAMPUS_PROTOCOL or campus_started:
		_campus_rejected.rpc_id(id, "房间已开局或版本不一致，请核对游戏版本并重新开房。")
		return
	if players.has(id):
		return
	if peer == CampusOnline.room_peer:
		var connection := peer
		for attempt in 12:
			if CampusOnline.room_has_peer(id):
				break
			await get_tree().create_timer(0.15).timeout
			if peer != connection or not multiplayer.get_peers().has(id):
				return
		if not CampusOnline.room_has_peer(id):
			_campus_rejected.rpc_id(id, "未找到你的房间成员记录，请重新加入。")
			return
		if campus_started or players.has(id):
			_campus_rejected.rpc_id(id, "房间已经开局，请等下一局。")
			return
	if players.size() >= CAMPUS_MAX_PLAYERS:
		_campus_rejected.rpc_id(id, "校园房间已满。")
		return
	players[id] = {"name": clean_campus_name(pname)}
	_sync_players.rpc(players)
	_campus_registered.rpc_id(id, campus_mode)
	players_changed.emit()

@rpc("authority", "reliable")
func _campus_registered(mode: int) -> void:
	if campus_room and mode in [CampusMode.EXPLORE, CampusMode.SURVIVAL]:
		campus_mode = mode
		_awaiting_campus_registration = false
		_iroh_discovery_deadline = 0
		connection_succeeded.emit()

@rpc("authority", "reliable")
func _campus_rejected(reason: String) -> void:
	leave_message = reason
	_on_connection_failed.call_deferred()

@rpc("authority", "reliable")
func _sync_players(p: Dictionary) -> void:
	players = p
	players_changed.emit()

@rpc("authority", "reliable")
func _sync_config(cfg: Dictionary) -> void:
	Game.config = cfg

## Host pushes the latest config to everyone (call when lobby settings change).
func push_config() -> void:
	if is_host():
		_sync_config.rpc(Game.config)

## Host starts the match: sync config one last time, then load the world on all peers.
func start_match() -> void:
	if not is_host():
		return
	if campus_room:
		if campus_started:
			return
		campus_started = true
		peer.refuse_new_connections = true
		for id: int in players:
			if id != 1:
				_load_campus.rpc_id(id, campus_mode)
		match_started.emit()
		return
	_sync_config.rpc(Game.config)
	_do_start.rpc()

@rpc("authority", "call_local", "reliable")
func _do_start() -> void:
	match_started.emit()

@rpc("authority", "reliable")
func _load_campus(mode: int) -> void:
	if campus_room and not campus_started and mode == campus_mode:
		campus_started = true
		match_started.emit()


func campus_scene() -> String:
	return CAMPUS_SURVIVAL_SCENE if campus_mode == CampusMode.SURVIVAL else CAMPUS_SCENE


static func clean_campus_name(value: String) -> String:
	var result := value.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip_edges().left(24)
	return result if not result.is_empty() else "同学"


func rename_campus_player(value: String) -> void:
	if not campus_room or campus_started:
		return
	var nickname := clean_campus_name(value)
	if is_host():
		_update_campus_name(1, nickname)
	elif players.has(local_id()):
		_request_campus_name.rpc_id(1, nickname)


@rpc("any_peer", "reliable")
func _request_campus_name(value: String) -> void:
	if is_host():
		_update_campus_name(multiplayer.get_remote_sender_id(), clean_campus_name(value))


func _update_campus_name(id: int, nickname: String) -> void:
	if not campus_room or campus_started or not players.has(id) or players[id].name == nickname:
		return
	players[id].name = nickname
	_sync_players.rpc(players)
	players_changed.emit()


func start_campus_exploration() -> void:
	if is_host() and campus_started and _campus_running and campus_mode == CampusMode.SURVIVAL:
		_switch_to_explore.rpc()


@rpc("authority", "call_local", "reliable")
func _switch_to_explore() -> void:
	if not campus_started or campus_mode != CampusMode.SURVIVAL:
		return
	campus_mode = CampusMode.EXPLORE
	_campus_loaded.clear()
	_campus_running = false
	campus_mode_changed.emit()

func report_campus_loaded() -> void:
	if not campus_started:
		return
	if is_host():
		_campus_loaded[1] = true
		_try_begin_campus()
	else:
		_campus_scene_loaded.rpc_id(1)

@rpc("any_peer", "reliable")
func _campus_scene_loaded() -> void:
	var id := multiplayer.get_remote_sender_id()
	if is_host() and campus_started and players.has(id):
		_campus_loaded[id] = true
		_try_begin_campus()

func _try_begin_campus() -> void:
	if not campus_started or _campus_running or _campus_loaded.size() != players.size():
		return
	for id: int in players:
		if id != 1:
			_begin_campus.rpc_id(id)
	_begin_campus()

@rpc("authority", "reliable")
func _begin_campus() -> void:
	_campus_running = true
	campus_ready.emit()
