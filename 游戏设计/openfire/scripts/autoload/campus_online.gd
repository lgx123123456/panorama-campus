extends Node

const BUCKET := "openfire-campus"
const CODE_KEY := "campus_room_code"
const CODE_CHARS := "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
const CODE_LENGTH := 8
const CONFIG_PATH := "user://campus-eos.cfg"
const CONFIG_KEYS := ["product_id", "sandbox_id", "deployment_id", "client_id", "client_secret"]

var room_peer: EOSGMultiplayerPeer
var room_code := ""
var _lobby: HLobby
var _platform_created := false
var _busy := false

func configured() -> bool:
	return not _read_settings().is_empty()

func open_room(code: String, host: bool) -> String:
	if _busy or _lobby != null:
		return "正在处理上一个房间，请稍后再试。"
	code = code.strip_edges().to_upper()
	if not host and not _valid_code(code):
		return "请输入 8 位房间码。"
	_busy = true
	var message := await _connect_services()
	if message.is_empty():
		message = await _host_room() if host else await _join_room(code)
	_busy = false
	if not message.is_empty():
		close_room()
	return message

func _connect_services() -> String:
	if not _platform_created:
		var settings := _read_settings()
		if settings.is_empty():
			return "此版本尚未配置 EOS。可先使用局域网联机。"

		var init := EOS.Platform.InitializeOptions.new()
		init.product_name = "OpenFire"
		init.product_version = str(ProjectSettings.get_setting("application/config/version"))
		var result := EOS.Platform.PlatformInterface.initialize(init)
		if result != EOS.Result.Success and result != EOS.Result.AlreadyConfigured:
			return "EOS 初始化失败（错误代码 %d）。" % int(result)

		var platform := EOS.Platform.CreateOptions.new()
		for key: String in CONFIG_KEYS:
			platform.set(key, settings[key])
		platform.flags = EOS.Platform.PlatformFlags.DisableOverlay | EOS.Platform.PlatformFlags.DisableSocialOverlay
		platform.task_network_timeout_seconds = 15.0
		platform.tick_budget_in_milliseconds = 3
		if not EOS.Platform.PlatformInterface.create(platform):
			return "无法创建 EOS 平台，请检查产品和客户端配置。"

		var relay := EOS.P2P.RelayControl.AllowRelays
		var args := OS.get_cmdline_user_args()
		if "--campus-force-relay" in args:
			relay = EOS.P2P.RelayControl.ForceRelays
		elif "--campus-direct-only" in args:
			relay = EOS.P2P.RelayControl.NoRelays
		var relay_result := EOS.P2P.P2PInterface.set_relay_control(relay)
		if not EOS.is_success(relay_result):
			push_warning("Campus EOS relay control: %s" % EOS.result_str(relay_result))
		_platform_created = true

	if not EOSGMultiplayerPeer.get_local_user_id().is_empty():
		return ""
	var device := EOS.Connect.CreateDeviceIdOptions.new()
	device.device_model = OS.get_name()
	EOS.Connect.ConnectInterface.create_device_id(device)
	var created: Dictionary = await IEOS.connect_interface_create_device_id_callback
	var code := int(created.result_code)
	if code != EOS.Result.Success and code != EOS.Result.DuplicateNotAllowed:
		return "EOS 游客设备登录失败（错误代码 %d）。" % int(code)

	var login := EOS.Connect.LoginOptions.new()
	login.credentials = EOS.Connect.Credentials.new()
	login.credentials.type = EOS.ExternalCredentialType.DeviceidAccessToken
	login.user_login_info = EOS.Connect.UserLoginInfo.new()
	login.user_login_info.display_name = Game.player_name
	if not await HAuth.login_game_services_async(login):
		return "EOS 游客登录失败，请检查网络和客户端权限。"
	# The plugin initializes P2P on successful Connect login, not on CreateUser.
	if EOSGMultiplayerPeer.get_local_user_id().is_empty():
		if not await HAuth.login_game_services_async(login) or EOSGMultiplayerPeer.get_local_user_id().is_empty():
			return "EOS 游客身份已创建，P2P 登录失败，请重试。"
	EOSGRuntime.local_product_user_id = HAuth.product_user_id
	return ""

func _host_room() -> String:
	room_code = _make_code()
	room_peer = _make_peer()
	var listen := room_peer.create_server(room_code)
	if listen != OK:
		return "无法启动在线房间（错误代码 %d）。" % listen

	var options := EOS.Lobby.CreateLobbyOptions.new()
	options.bucket_id = BUCKET
	options.max_lobby_members = Net.CAMPUS_MAX_PLAYERS
	options.disable_host_migration = true
	options.enable_join_by_id = false
	options.allow_invites = false
	options.presence_enabled = false
	options.enable_rtc_room = false
	_lobby = await HLobbies.create_lobby_async(options)
	if _lobby == null:
		return "EOS 创建房间失败，请检查客户端的 Lobbies 权限。"
	_lobby.add_attribute(CODE_KEY, room_code)
	if not await _lobby.update_async():
		return "EOS 房间码发布失败，请重新开房。"
	return ""

func _join_room(code: String) -> String:
	var found = await HLobbies.search_by_attribute_async([
		{"key": EOS.Lobby.SEARCH_BUCKET_ID, "value": BUCKET},
		{"key": CODE_KEY, "value": code},
	])
	if found == null:
		return "EOS 房间查询失败，请检查网络后重试。"
	if found.size() != 1:
		return "未找到该房间，请核对房间码或请房主重新开房。"
	HLobbies.presence_enabled = false
	_lobby = await HLobbies.join_async(found[0])
	if _lobby == null:
		return "加入房间失败，房间可能已经关闭或已满。"
	room_code = code
	room_peer = _make_peer()
	var connect_result := room_peer.create_client(code, _lobby.owner_product_user_id)
	if connect_result != OK:
		return "无法连接房主（错误代码 %d）。" % connect_result
	return ""

func _make_peer() -> EOSGMultiplayerPeer:
	var result := EOSGMultiplayerPeer.new()
	result.peer_connection_established.connect(func(data: Dictionary):
		var route := int(data.get("network_type", 0))
		print("Campus EOS P2P route: ", EOS.P2P.NetworkType.find_key(route))
	)
	return result

func room_has_peer(id: int) -> bool:
	return is_instance_valid(_lobby) and is_instance_valid(room_peer) \
		and _lobby.get_member_by_product_user_id(room_peer.get_peer_user_id(id)) != null

func close_room() -> void:
	if room_peer != null:
		room_peer.close()
		room_peer = null
	room_code = ""
	var lobby := _lobby
	_lobby = null
	if lobby == null:
		return
	_busy = true
	if lobby.is_owner():
		await lobby.destroy_async()
	else:
		await lobby.leave_async()
	_busy = false

func _read_settings() -> Dictionary:
	var settings := ConfigFile.new()
	if settings.load(CONFIG_PATH) != OK:
		settings.load(OS.get_executable_path().get_base_dir().path_join("campus-eos.cfg"))
	var result := {}
	for key: String in CONFIG_KEYS:
		var value := OS.get_environment("OPENFIRE_EOS_" + key.to_upper()).strip_edges()
		if value.is_empty():
			value = str(settings.get_value("eos", key, "")).strip_edges()
		if value.is_empty():
			return {}
		result[key] = value
	return result

func _make_code() -> String:
	var code := ""
	for value in Crypto.new().generate_random_bytes(CODE_LENGTH):
		code += CODE_CHARS[value % CODE_CHARS.length()]
	return code

func _valid_code(code: String) -> bool:
	if code.length() != CODE_LENGTH:
		return false
	for letter in code:
		if not CODE_CHARS.contains(letter):
			return false
	return true
