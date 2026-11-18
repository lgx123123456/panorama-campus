extends Control

var campus_loading_path := ""
var campus_loading_overlay: CanvasLayer
var campus_handoff := false
var campus_preload_task: Node
var campus_base_scene: PackedScene
var campus_progress := 0.0
var campus_dialog: AcceptDialog
var campus_room_input: LineEdit
var campus_nickname_input: LineEdit
var campus_mode_input: OptionButton
var lobby_nickname_row: HBoxContainer
var lobby_nickname_input: LineEdit
var campus_dialog_status: RichTextLabel
var campus_dialog_buttons: Array[Button] = []
const CAMPUS_LOADING_OVERLAY := preload("res://scenes/campus/loading_overlay.tscn")
const CampusPreloader := preload("res://scripts/campus/campus_preloader.gd")
const CAMPUS_SURVIVAL := "res://scenes/campus/survival.tscn"
const CampusTextMenu := preload("res://scripts/ui/campus_text_menu.gd")
const CampusTitle := preload("res://scripts/ui/campus_title.gd")
const ADMIN_SURVIVAL := "res://scenes/campus/survival_admin.tscn"
var campus_title: CampusTitle
var legacy_menu := false
var quitting := false

func _is_admin_build() -> bool:
	return OS.has_feature("editor") or OS.has_feature("campus_admin")

const CHARACTER_TRIAL := "res://scenes/campus/character_trial.tscn"
## Main menu + lobby. Configure a match, then Host / Join (by IP) / Solo-vs-bots.
## The host captures settings into Game.config; Net replicates them to clients.

const MAPS := [
	{ "name": "竞技场", "path": "res://maps/arena.tscn" },
	{ "name": "设施区", "path": "res://maps/facility.tscn" },
	{ "name": "高地", "path": "res://maps/highlands.tscn" },
	{ "name": "仓库", "path": "res://maps/warehouse.tscn" },
	{ "name": "遗迹", "path": "res://maps/ruins.tscn" },
	{ "name": "院落", "path": "res://maps/compound.tscn" },
	{ "name": "前哨站（超大，有载具）", "path": "res://maps/outpost.tscn" },
	{ "name": "荒原（超大，有载具）", "path": "res://maps/badlands.tscn" },
	{ "name": "废土（超大，生存竞技）", "path": "res://maps/wasteland.tscn" },
]
const SKILLS := [
	{ "name": "简单", "value": 0.6 },
	{ "name": "普通", "value": 1.0 },
	{ "name": "困难", "value": 1.4 },
]
# Adventure uses one procedurally-generated terrain map, sized by map_size + seed.
const ADVENTURE_MAP := "res://maps/terrain.tscn"

# Saved map templates: each is a fixed (seed + size + theme + climate) that regenerates
# the exact same world every time. "自定义" uses the fields below instead. size:
# 0 Tiny, 1 Small, 2 Medium, 3 Large.
const MAP_PRESETS := [
	{"name": "自定义（填写下方参数）", "preset": false},
	{"name": "大山谷（超大）", "preset": true, "seed": 820447, "size": 3,
		"theme": "a majestic valley of snow-capped peaks, winding rivers, lakes and deep forests", "climate": "verdant"},
	{"name": "冰封北境", "preset": true, "seed": 30211, "size": 2, "theme": "frozen arctic tundra", "climate": "frozen"},
	{"name": "Test — Desert Wastes", "preset": true, "seed": 30222, "size": 2, "theme": "scorching desert wasteland", "climate": "desert"},
	{"name": "Test — Tropic Isles", "preset": true, "seed": 30233, "size": 2, "theme": "tropical island archipelago", "climate": "isles"},
	{"name": "火山灰原", "preset": true, "seed": 30244, "size": 2, "theme": "volcanic ashlands", "climate": "volcanic"},
	{"name": "Test — Verdant Lowlands", "preset": true, "seed": 30255, "size": 2, "theme": "lush green wilderness", "climate": "verdant"},
]

@onready var setup_panel: Control = %SetupPanel
@onready var lobby_panel: Control = %LobbyPanel
@onready var name_edit: LineEdit = %NameEdit
@onready var mode_option: OptionButton = %ModeOption
@onready var map_row: Control = %MapRow
@onready var map_option: OptionButton = %MapOption
@onready var mission_row: Control = %MissionRow
@onready var mission_option: OptionButton = %MissionOption
@onready var frag_row: Control = %FragRow
@onready var frag_spin: SpinBox = %FragSpin
@onready var bots_spin: SpinBox = %BotsSpin
@onready var skill_option: OptionButton = %SkillOption
@onready var ip_edit: LineEdit = %IpEdit
@onready var status_label: Label = %StatusLabel
@onready var lobby_players: VBoxContainer = %LobbyPlayers
@onready var lobby_summary: Label = %LobbySummary
@onready var start_button: Button = %StartButton
@onready var options_panel: Control = %OptionsPanel
@onready var mission_points_row: Control = %MissionPointsRow
@onready var mission_points_spin: SpinBox = %MissionPointsSpin
@onready var seed_row: Control = %SeedRow
@onready var seed_edit: LineEdit = %SeedEdit
@onready var theme_row: Control = %ThemeRow
@onready var theme_edit: LineEdit = %ThemeEdit
@onready var map_size_row: Control = %MapSizeRow
@onready var map_size_option: OptionButton = %MapSizeOption
@onready var template_row: Control = %TemplateRow
@onready var template_option: OptionButton = %TemplateOption
@onready var inv_key_option: OptionButton = %InvKeyOption
@onready var character_row: Control = %CharacterRow
@onready var char_label: Label = %CharLabel
@onready var character_panel: Control = %CharacterPanel
@onready var create_panel: Control = %CreatePanel
@onready var char_list: VBoxContainer = %CharList

# Selectable inventory keys for Adventure (label + keycode).
const INV_KEYS := [
	{ "name": "Tab", "code": KEY_TAB },
	{ "name": "I", "code": KEY_I },
	{ "name": "B", "code": KEY_B },
	{ "name": "C", "code": KEY_C },
]

# Embedded llama.cpp models (Qwen2.5 Instruct, Q4_K_M GGUF). Downloaded on first
# Adventure start into user://models/. Bigger = better stories, larger download.
const AI_MODELS := [
	{
		"name": "Tiny — Qwen2.5 0.5B (~0.4 GB)",
		"file": "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
		"url": "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
	},
	{
		"name": "Small — Qwen2.5 1.5B (~1 GB)",
		"file": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
		"url": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
	},
	{
		"name": "Medium — Qwen2.5 3B (~2 GB)",
		"file": "Qwen2.5-3B-Instruct-Q4_K_M.gguf",
		"url": "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
	},
	{
		"name": "Huge — Qwen2.5 7B (~4.7 GB)",
		"file": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
		"url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
	},
]

func _ready() -> void:
	get_tree().auto_accept_quit = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	Net.players_changed.connect(_refresh_lobby)
	Net.connection_succeeded.connect(_on_connected)
	Net.connection_failed.connect(_on_failed)
	Net.server_disconnected.connect(_on_server_disconnected)
	Net.match_started.connect(_on_match_started)

	name_edit.text = Game.player_name
	for widget in find_children("*", "LineEdit"):
		CampusTextMenu.apply(widget.get_menu())
	for widget in find_children("*", "TextEdit"):
		CampusTextMenu.apply(widget.get_menu())
	%VersionLabel.text = "v" + str(ProjectSettings.get_setting("application/config/version", "0.0.0"))
	mode_option.clear()
	mode_option.add_item("个人对战")
	mode_option.add_item("协作模式")
	mode_option.add_item("团队对战")
	mode_option.add_item("据点争夺")
	mode_option.add_item("生存竞技")
	mode_option.add_item("冒险模式")
	mode_option.selected = Game.Mode.ADVENTURE  # Adventure is the default mode
	template_option.clear()
	for p in MAP_PRESETS:
		template_option.add_item(String(p["name"]))
	template_option.selected = 0
	template_option.item_selected.connect(func(_i): _on_mode_changed(mode_option.selected))
	map_size_option.clear()
	for size_name in ["极小", "小", "中", "大"]:
		map_size_option.add_item(size_name)
	map_size_option.selected = 2   # Medium
	map_option.clear()
	for m in MAPS:
		map_option.add_item(m["name"])
	skill_option.clear()
	for s in SKILLS:
		skill_option.add_item(s["name"])
	skill_option.selected = 1
	mission_option.clear()
	for mission in Missions.get_all():
		mission_option.add_item(mission["name"])

	%HostButton.pressed.connect(_on_host)
	%JoinButton.pressed.connect(_on_join)
	%SoloButton.pressed.connect(_on_solo)
	%GatePlazaButton.pressed.connect(_on_campus.bind("res://scenes/campus/gate_plaza.tscn"))
	%CampusButton.pressed.connect(_on_campus.bind("res://scenes/campus/interior.tscn"))
	%CharacterTrialButton.pressed.connect(_on_campus.bind(CHARACTER_TRIAL))
	%ZombieTrialButton.pressed.connect(_on_campus.bind(CAMPUS_SURVIVAL))
	%CampusOnlineButton.pressed.connect(_show_campus_online)
	%CopyRoomCodeButton.pressed.connect(func(): DisplayServer.clipboard_set(Net.room_code))
	%QuitButton.pressed.connect(func(): get_tree().quit())
	mode_option.item_selected.connect(_on_mode_changed)
	start_button.pressed.connect(func(): Net.start_match())
	%BackButton.pressed.connect(_on_back)

	# Character screens (Adventure).
	%CreateKit.clear()
	for kit_id in Characters.KIT_IDS:
		%CreateKit.add_item(Characters.kit_name(kit_id))
	%CharBtn.pressed.connect(_show_characters)
	%ContinueBtn.pressed.connect(_on_continue)
	%CharBackBtn.pressed.connect(_show_setup)
	%NewCharBtn.pressed.connect(_show_create)
	%DeleteCharBtn.pressed.connect(_on_delete_character)
	%CreateConfirm.pressed.connect(_on_create_confirm)
	%CreateCancel.pressed.connect(_show_characters)
	_update_char_label()

	# Click sound on every button.
	for b in find_children("*", "Button", true):
		b.pressed.connect(func(): Audio.play_ui("res://assets/audio/ui_click.ogg", -4.0))

	campus_title = CampusTitle.new()
	campus_title.name = "CampusTitle"
	add_child(campus_title)
	campus_title.route_requested.connect(_on_campus)
	campus_title.online_requested.connect(_show_campus_online)
	campus_title.options_requested.connect(_show_options)
	campus_title.legacy_requested.connect(_open_legacy_menu)
	campus_title.quit_requested.connect(_confirm_quit)
	_setup_options()
	_configure_campus_options()
	_on_mode_changed(mode_option.selected)
	_show_setup()
	if not Net.leave_message.is_empty():
		_set_menu_status(Net.leave_message)
		Net.leave_message = ""

	# Gate play on the AI download: the game generates world assets via ComfyUI, so don't let
	# anyone start until the bundle + models are downloaded and ComfyUI is answering.
	if not ComfyUI.server_checked.is_connected(_on_ai_ready_changed):
		ComfyUI.server_checked.connect(_on_ai_ready_changed)
		ComfyUI.setup_status.connect(_on_ai_ready_changed_s)
	_update_play_gate()
	if "--campus-survival" in OS.get_cmdline_user_args() and not get_tree().root.has_meta("opened_zombie_trial"):
		get_tree().root.set_meta("opened_zombie_trial", true)
		_on_campus.call_deferred(CAMPUS_SURVIVAL)
	elif "--campus-free-tour" in OS.get_cmdline_user_args() and not get_tree().root.has_meta("opened_free_tour"):
		get_tree().root.set_meta("opened_free_tour", true)
		_on_campus.call_deferred(CampusTitle.CampusTour.SCENE)
	elif _is_admin_build() and "--campus-character-test" in OS.get_cmdline_user_args() and not get_tree().root.has_meta("opened_character_trial"):
		get_tree().root.set_meta("opened_character_trial", true)
		_on_campus.call_deferred(CHARACTER_TRIAL)
	elif _is_admin_build() and "--campus-admin-test" in OS.get_cmdline_user_args() and not get_tree().root.has_meta("opened_admin_trial"):
		get_tree().root.set_meta("opened_admin_trial", true)
		_on_campus.call_deferred(ADMIN_SURVIVAL)
	elif DisplayServer.get_name() != "headless":
		_prefetch_campus.call_deferred()

func _prefetch_campus() -> void:
	await RenderingServer.frame_post_draw
	if not is_inside_tree() or quitting or not campus_loading_path.is_empty():
		return
	var root := get_tree().root
	campus_preload_task = root.get_node_or_null(CampusPreloader.TASK_NAME)
	if campus_preload_task == null:
		campus_preload_task = CampusPreloader.new()
		campus_preload_task.name = CampusPreloader.TASK_NAME
		root.add_child(campus_preload_task)
	campus_preload_task.finished.connect(_campus_prefetch_finished, CONNECT_ONE_SHOT)

func _campus_prefetch_finished(base_scene: PackedScene) -> void:
	campus_preload_task = null
	campus_base_scene = base_scene
	if is_inside_tree() and not campus_loading_path.is_empty():
		_request_selected_campus()

func _setup_options() -> void:
	%SensSlider.value = Settings.mouse_sensitivity
	%VolSlider.value = Settings.master_volume
	%FovSlider.value = Settings.fov
	inv_key_option.clear()
	var sel := 0
	for i in INV_KEYS.size():
		inv_key_option.add_item(INV_KEYS[i]["name"])
		if int(INV_KEYS[i]["code"]) == Settings.inventory_keycode:
			sel = i
	inv_key_option.selected = sel
	# Graphics quality preset.
	%QualityOption.clear()
	for qn in Settings.QUALITY_NAMES:
		%QualityOption.add_item(qn)
	%QualityOption.selected = clampi(Settings.quality, 0, 2)
	%QualityOption.item_selected.connect(_on_quality_changed)
	# Embedded AI model preset: match the saved file to a preset (default Small).
	%LlmEmbedOption.clear()
	var msel := 1
	for i in AI_MODELS.size():
		%LlmEmbedOption.add_item(String(AI_MODELS[i]["name"]))
		if String(AI_MODELS[i]["file"]) == Settings.llm_model_file:
			msel = i
	%LlmEmbedOption.selected = msel
	%LlmEmbedOption.item_selected.connect(_on_llm_embed_changed)
	_update_option_labels()
	%SensSlider.value_changed.connect(_on_sens_changed)
	%VolSlider.value_changed.connect(_on_vol_changed)
	%FovSlider.value_changed.connect(_on_fov_changed)
	inv_key_option.item_selected.connect(_on_inv_key_changed)
	%LlmEndpointEdit.text = Settings.llm_endpoint
	%LlmModelEdit.text = Settings.llm_model
	%LlmEndpointEdit.text_changed.connect(_on_llm_endpoint_changed)
	%LlmModelEdit.text_changed.connect(_on_llm_model_changed)
	# Debug mode toggle: enables the in-game [0] cheat menu (solo games only).
	var dbg := CheckButton.new()
	dbg.text = "调试模式 · 单人游戏按 0 打开"
	dbg.button_pressed = Settings.debug_mode
	dbg.toggled.connect(_on_debug_toggled)
	var vbox: Node = %OptionsBackButton.get_parent()
	vbox.add_child(dbg)
	vbox.move_child(dbg, %OptionsBackButton.get_index())   # sit just above the Back button
	if _is_admin_build():
		_build_comfyui_options(vbox)
	%OptionsButton.pressed.connect(_show_options)
	%OptionsBackButton.pressed.connect(_show_setup)

func _on_debug_toggled(on: bool) -> void:
	Settings.debug_mode = on
	Settings.save()

var _comfy_status: Label = null
var _comfy_dl_bar: ProgressBar = null

## Opt-in ComfyUI asset bridge controls: enable, server endpoint, checkpoint, and a button
## to pre-bake a sample themed prop library into user://generated/ (needs a running ComfyUI).
func _build_comfyui_options(vbox: Node) -> void:
	var head := Label.new()
	head.text = "模型与素材（ComfyUI）"
	vbox.add_child(head)
	var ep := LineEdit.new()
	ep.placeholder_text = "ComfyUI 服务地址"
	ep.text = Settings.comfyui_endpoint
	ep.text_changed.connect(func(t): Settings.comfyui_endpoint = t.strip_edges(); Settings.save())
	vbox.add_child(ep)
	# The model auto-downloads into the bundled checkpoints folder (next to the game).
	var dl := Button.new()
	dl.text = "下载模型（首次约 4 GB）"
	dl.pressed.connect(_on_download_model)
	vbox.add_child(dl)
	_comfy_dl_bar = ProgressBar.new()
	_comfy_dl_bar.min_value = 0.0
	_comfy_dl_bar.max_value = 100.0
	_comfy_dl_bar.custom_minimum_size = Vector2(420, 18)
	_comfy_dl_bar.visible = false
	vbox.add_child(_comfy_dl_bar)
	_comfy_status = Label.new()
	_comfy_status.text = ""
	_comfy_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_comfy_status.custom_minimum_size.x = 420
	vbox.add_child(_comfy_status)
	for n in [head, ep, dl, _comfy_dl_bar, _comfy_status]:
		vbox.move_child(n, %OptionsBackButton.get_index())
	# Reflect the automatic first-run setup (bundle download, model downloads, "starting…")
	# without the user clicking anything.
	if not ComfyUI.setup_status.is_connected(_on_comfy_setup_status):
		ComfyUI.setup_status.connect(_on_comfy_setup_status)
	if ComfyUI.setup_message != "":
		_on_comfy_setup_status(ComfyUI.setup_message, ComfyUI.setup_fraction)

var _ai_gate_label: Label = null
var _ai_prepare_button: Button

## Disable Host/Join/Solo until the AI stack is downloaded and ComfyUI is answering, with a
## status line above the buttons explaining the wait.
func _update_play_gate() -> void:
	var ready := ComfyUI.is_ready()
	for b in [%HostButton, %JoinButton, %SoloButton]:
		if b != null:
			b.disabled = not ready or not campus_loading_path.is_empty()
	%ContinueBtn.disabled = not campus_loading_path.is_empty()
	if _ai_gate_label == null:
		_ai_gate_label = Label.new()
		_ai_gate_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_ai_gate_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_ai_gate_label.custom_minimum_size = Vector2(360, 0)   # else it collapses to a 1-char column
		_ai_gate_label.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		_ai_gate_label.modulate = Color(1, 0.85, 0.4)
		# Add to the VBox ABOVE the button row (HostButton's parent is the Buttons HBox — adding
		# there would put the label on the same line as the buttons).
		var row := %HostButton.get_parent()
		var container := row.get_parent()
		container.add_child(_ai_gate_label)
		container.move_child(_ai_gate_label, row.get_index())
		_ai_prepare_button = Button.new()
		_ai_prepare_button.text = "准备 AI 组件"
		_ai_prepare_button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		_ai_prepare_button.pressed.connect(ComfyUI.prepare)
		container.add_child(_ai_prepare_button)
		container.move_child(_ai_prepare_button, row.get_index())
	_ai_gate_label.visible = not ready
	_ai_prepare_button.visible = not ready
	_ai_prepare_button.disabled = ComfyUI.is_preparing() or not campus_loading_path.is_empty()
	if not ready:
		_ai_gate_label.text = ComfyUI.setup_message if ComfyUI.setup_message != "" else "通用地图的 Host、Join 和 Solo 需要准备 AI 组件。"

func _on_ai_ready_changed(_ok: bool) -> void:
	_update_play_gate()

func _on_ai_ready_changed_s(_message: String, _fraction: float) -> void:
	_update_play_gate()

func _on_comfy_setup_status(message: String, fraction: float) -> void:
	if _comfy_status == null:
		return
	if message == "":
		_comfy_status.text = "模型已就绪。"
		if _comfy_dl_bar != null:
			_comfy_dl_bar.visible = false
		return
	_comfy_status.text = message
	if _comfy_dl_bar != null:
		if fraction >= 0.0:
			_comfy_dl_bar.visible = true
			_comfy_dl_bar.value = fraction * 100.0
		else:
			_comfy_dl_bar.visible = false

func _on_download_model() -> void:
	if ComfyUI.is_preparing():
		return
	if not ComfyUI.model_ready.is_connected(_on_model_ready_status):
		ComfyUI.model_ready.connect(_on_model_ready_status)
		ComfyUI.model_progress.connect(_on_model_progress)
	if ComfyUI.has_local_model():
		_comfy_status.text = "模型已就绪。"
		return
	_comfy_status.text = "正在下载模型，仅首次需要下载。"
	if _comfy_dl_bar != null:
		_comfy_dl_bar.visible = true
		_comfy_dl_bar.value = 0.0
	ComfyUI.download_model()

func _on_model_progress(_frac: float, downloaded: int, total: int) -> void:
	var mb := func(n: int) -> String: return "%.0f MB" % (float(n) / 1048576.0)
	# HuggingFace's LFS redirects make the HTTP Content-Length (`total`) unreliable — often a
	# fraction of the real size. Only trust it when it's clearly the whole file; otherwise use
	# the known model size. `downloaded` (actual bytes written) is always correct.
	var real_total := total if (total > downloaded and total > 1073741824) else int(Settings.comfyui_model_size)
	if real_total > 0:
		var pct := clampf(float(downloaded) / float(real_total) * 100.0, 0.0, 99.0)
		if _comfy_dl_bar != null:
			_comfy_dl_bar.value = pct
		_comfy_status.text = "正在下载模型… %d%%（%s / %s）" % [int(pct), mb.call(downloaded), mb.call(real_total)]
	else:
		if _comfy_dl_bar != null:
			_comfy_dl_bar.value = fmod(float(downloaded) / 1048576.0, 100.0)
		_comfy_status.text = "正在下载模型… %s" % mb.call(downloaded)

func _on_model_ready_status(_ok: bool, message: String) -> void:
	if _comfy_dl_bar != null:
		_comfy_dl_bar.visible = false
	_comfy_status.text = message

func _on_llm_embed_changed(idx: int) -> void:
	var m: Dictionary = AI_MODELS[clampi(idx, 0, AI_MODELS.size() - 1)]
	Settings.llm_model_url = String(m["url"])
	Settings.llm_model_file = String(m["file"])
	Settings.save()

func _on_llm_endpoint_changed(t: String) -> void:
	Settings.llm_endpoint = t.strip_edges()
	Settings.save()

func _on_llm_model_changed(t: String) -> void:
	Settings.llm_model = t.strip_edges()
	Settings.save()

func _on_inv_key_changed(idx: int) -> void:
	Settings.inventory_keycode = int(INV_KEYS[clampi(idx, 0, INV_KEYS.size() - 1)]["code"])
	Settings.save()

func _on_sens_changed(v: float) -> void:
	Settings.mouse_sensitivity = v
	_apply_and_save()

func _on_vol_changed(v: float) -> void:
	Settings.master_volume = v
	_apply_and_save()

func _on_fov_changed(v: float) -> void:
	Settings.fov = v
	_apply_and_save()

func _on_quality_changed(idx: int) -> void:
	Settings.quality = clampi(idx, 0, 2)
	_apply_and_save()   # takes effect on the next match (environment built on load)

func _apply_and_save() -> void:
	_update_option_labels()
	Settings.apply()
	Settings.save()

func _update_option_labels() -> void:
	%SensValue.text = "%.2f" % Settings.mouse_sensitivity
	%VolValue.text = "%d%%" % int(round(Settings.master_volume * 100))
	%FovValue.text = "%d" % int(Settings.fov)

func _configure_campus_options() -> void:
	var rows: VBoxContainer = %OptionsBackButton.get_parent()
	for node in rows.get_children():
		var official := node == %OptionsBackButton or node.name in [
			"Title", "SensRow", "VolRow", "FovRow", "QualityRow", "DisplayRow"]
		node.visible = official or legacy_menu
	rows.get_node("Title").text = "设置" if not legacy_menu else "设置"
	rows.get_node("SensRow/L").text = "鼠标灵敏度"
	rows.get_node("VolRow/L").text = "总音量"
	rows.get_node("FovRow/L").text = "视野"
	rows.get_node("QualityRow/L").text = "画质"
	%OptionsBackButton.text = "返回"
	for index in 3:
		%QualityOption.set_item_text(index, ["低", "中", "高"][index])
	if rows.has_node("DisplayRow"):
		return
	var card := StyleBoxFlat.new()
	card.bg_color = Color("#202a2d")
	card.border_color = Color("#e2ad63")
	card.border_width_top = 2
	card.content_margin_left = 28
	card.content_margin_right = 28
	card.content_margin_top = 22
	card.content_margin_bottom = 22
	rows.get_parent().add_theme_stylebox_override("panel", card)
	rows.add_theme_constant_override("separation", 12)
	rows.get_node("Title").add_theme_font_size_override("font_size", 27)
	var display_row := HBoxContainer.new()
	display_row.name = "DisplayRow"
	rows.add_child(display_row)
	rows.move_child(display_row, %QualityOption.get_parent().get_index() + 1)
	var caption := Label.new()
	caption.text = "显示模式"
	caption.custom_minimum_size.x = %QualityOption.get_parent().get_node("L").custom_minimum_size.x
	display_row.add_child(caption)
	var display := OptionButton.new()
	display.add_item("窗口")
	display.add_item("全屏")
	display.custom_minimum_size.x = %QualityOption.custom_minimum_size.x
	display.selected = int(Settings.fullscreen)
	display.item_selected.connect(func(index: int):
		Settings.fullscreen = index == 1
		Settings.apply_display()
		Settings.save())
	display_row.add_child(display)


func _open_legacy_menu() -> void:
	if _is_admin_build():
		legacy_menu = true
		_show_setup()


func _confirm_quit() -> void:
	var dialog := ConfirmationDialog.new()
	dialog.title = "退出游戏"
	dialog.dialog_text = "确定退出《一中东·余铃》？"
	dialog.ok_button_text = "退出"
	dialog.cancel_button_text = "取消"
	dialog.confirmed.connect(_quit_menu)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_quit_menu()


func _exit_tree() -> void:
	get_tree().auto_accept_quit = true


func _quit_menu() -> void:
	if quitting:
		return
	quitting = true
	if is_instance_valid(campus_preload_task):
		await campus_preload_task.finished
	get_tree().quit()


func _set_menu_status(message: String) -> void:
	status_label.text = message
	campus_title.set_status(message)


func _unhandled_input(event: InputEvent) -> void:
	if not event.is_action_pressed("ui_cancel") or not campus_loading_path.is_empty():
		return
	if options_panel.visible or (legacy_menu and setup_panel.visible):
		if setup_panel.visible:
			legacy_menu = false
		_show_setup()
		get_viewport().set_input_as_handled()


func _show_options() -> void:
	campus_title.hide()
	_configure_campus_options()
	setup_panel.visible = false
	lobby_panel.visible = false
	options_panel.visible = true
	character_panel.visible = false
	create_panel.visible = false
	%SensSlider.grab_focus()

func _on_mode_changed(_idx: int) -> void:
	var coop := mode_option.selected == 1
	var br := mode_option.selected == 4  # Battle Royale: no frag limit, last one alive wins
	var adventure := mode_option.selected == 5
	map_row.visible = not coop and not adventure      # Adventure picks a size, not a map
	frag_row.visible = not coop and not br and not adventure
	mission_row.visible = coop
	mission_points_row.visible = adventure
	# A chosen template pins seed/size/theme, so hide those fields then.
	var custom: bool = adventure and template_option.selected == 0
	template_row.visible = adventure
	seed_row.visible = custom
	map_size_row.visible = custom
	theme_row.visible = custom
	character_row.visible = adventure
	# Adventure hides the manual NPC count, but keeps the difficulty (Bot skill) selector.
	bots_spin.get_parent().visible = not adventure
	if coop and Missions.get_all().is_empty():
		status_label.text = "暂无可用任务。"

func _capture_config() -> void:
	Game.player_name = name_edit.text.strip_edges()
	if Game.player_name == "":
		Game.player_name = "同学"
	var coop := mode_option.selected == 1
	var adventure := mode_option.selected == 5
	# Option order matches the Mode enum (0=Deathmatch … 5=Adventure).
	Game.config["mode"] = mode_option.selected
	Game.config["bot_count"] = int(bots_spin.value)
	Game.config["bot_skill"] = SKILLS[skill_option.selected]["value"]
	if coop:
		var missions := Missions.get_all()
		if not missions.is_empty():
			var m: Dictionary = missions[clampi(mission_option.selected, 0, missions.size() - 1)]
			Game.config["mission_id"] = m["id"]
			Game.config["map"] = m["map"]
	elif adventure:
		Game.config.erase("climate")        # fresh world -> re-resolve from the theme
		Game.continue_data = {}
		Game.config["mission_points"] = int(mission_points_spin.value)
		Game.config["map"] = ADVENTURE_MAP   # terrain.gd reads map_size + seed
		Game.config["frag_limit"] = 0
		var preset: Dictionary = MAP_PRESETS[clampi(template_option.selected, 0, MAP_PRESETS.size() - 1)]
		if bool(preset.get("preset", false)):
			# A saved template: load its exact world (seed + size + theme + pinned climate).
			Game.config["seed"] = int(preset["seed"])
			Game.config["map_size"] = int(preset["size"])
			Game.config["theme"] = String(preset["theme"])
			Game.config["climate"] = String(preset["climate"])
		else:
			Game.config["map_size"] = map_size_option.selected
			Game.config["seed"] = _parse_seed(seed_edit.text.strip_edges())
			Game.config["theme"] = theme_edit.text.strip_edges()
		# NPC count is fixed (scaled by the world); difficulty comes from the skill
		# selector (bot_skill is already set from skill_option above).
		Game.config["bot_count"] = 12
	else:
		Game.config["map"] = MAPS[map_option.selected]["path"]
		Game.config["frag_limit"] = int(frag_spin.value)

## Resolve the seed field: blank = random, a plain integer = itself, else hashed.
func _parse_seed(txt: String) -> int:
	if txt == "":
		return randi()
	if txt.is_valid_int():
		return int(txt)
	return hash(txt)

# ---------------------------------------------------------------- buttons

func _on_host() -> void:
	_capture_config()
	if Net.host_game():
		status_label.text = "已开房。请把局域网 IP 地址和端口 %d 发给队友。" % Net.DEFAULT_PORT
		_show_lobby()
	else:
		status_label.text = "开房失败，请检查端口是否已被占用。"

func _on_campus(scene_path: String) -> void:
	if not campus_loading_path.is_empty():
		return
	var official := scene_path in [CAMPUS_SURVIVAL, Net.CAMPUS_SCENE, Net.CAMPUS_SURVIVAL_SCENE, CampusTitle.CampusTour.SCENE]
	if not official and not _is_admin_build():
		return
	var tree_root := get_tree().root
	tree_root.set_meta("campus_admin_return", not official)
	_set_menu_status("")
	campus_loading_path = scene_path
	campus_progress = 0.0
	_set_campus_loading(true)
	status_label.text = "正在加载场景…"
	if DisplayServer.get_name() != "headless":
		campus_loading_overlay = CAMPUS_LOADING_OVERLAY.instantiate()
		add_child(campus_loading_overlay)
	if campus_preload_task == null:
		_request_selected_campus()

func _request_selected_campus() -> void:
	var err := ResourceLoader.load_threaded_request(campus_loading_path, "PackedScene", true)
	if err != OK:
		_campus_loading_failed("校园场景加载失败（错误代码 %d）" % err)

func _show_campus_progress(fraction: float) -> void:
	campus_progress = maxf(campus_progress, fraction)
	status_label.text = "正在加载场景… %d%%" % int(campus_progress * 100.0)
	if campus_loading_overlay != null:
		campus_loading_overlay.show_resource_progress(campus_progress)

func _process(_delta: float) -> void:
	if campus_loading_path.is_empty() or campus_handoff:
		return
	if campus_preload_task != null:
		_show_campus_progress(campus_preload_task.fraction * 0.85)
		return
	var progress: Array = []
	var status := ResourceLoader.load_threaded_get_status(campus_loading_path, progress)
	if status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		if not progress.is_empty():
			var fraction := float(progress[0])
			_show_campus_progress(lerpf(0.85, 1.0, fraction) if campus_base_scene != null else fraction)
		return
	if status != ResourceLoader.THREAD_LOAD_LOADED:
		_campus_loading_failed("校园场景加载失败，请重新进入。")
		return
	campus_handoff = true
	var packed := ResourceLoader.load_threaded_get(campus_loading_path) as PackedScene
	var tree := get_tree()
	if campus_loading_overlay != null and not Net.campus_room:
		campus_loading_overlay.show_stage("正在准备场景和碰撞…")
		await RenderingServer.frame_post_draw
		await tree.process_frame
		campus_loading_overlay.reparent(tree.root)
		tree.scene_changed.connect(campus_loading_overlay.warm_spawn, CONNECT_ONE_SHOT)
	var err := tree.change_scene_to_packed(packed)
	if err != OK:
		if campus_loading_overlay != null and tree.scene_changed.is_connected(campus_loading_overlay.warm_spawn):
			tree.scene_changed.disconnect(campus_loading_overlay.warm_spawn)
		_campus_loading_failed("校园场景加载失败（错误代码 %d）" % err)

func _campus_loading_failed(message: String) -> void:
	campus_handoff = false
	campus_loading_path = ""
	if campus_loading_overlay != null:
		campus_loading_overlay.queue_free()
		campus_loading_overlay = null
	_set_campus_loading(false)
	if Net.campus_room:
		Net.disconnect_net()
		_show_setup()
	_set_menu_status(message)

func _set_campus_loading(loading: bool) -> void:
	campus_title.set_loading(loading)
	for button in [%GatePlazaButton, %CampusButton, %CharacterTrialButton, %ZombieTrialButton, %CampusOnlineButton]:
		button.disabled = loading
	_update_play_gate()

func _on_solo() -> void:
	_capture_config()
	if not Game.is_adventure():
		Game.config["bot_count"] = maxi(1, int(bots_spin.value))
	if Net.host_game():
		Net.start_match()
	else:
		status_label.text = "单人游戏启动失败。"

func _on_join() -> void:
	Game.player_name = name_edit.text.strip_edges()
	if Game.player_name == "":
		Game.player_name = "同学"
	var ip := ip_edit.text.strip_edges()
	if ip == "":
		ip = "127.0.0.1"
	if Net.join_game(ip):
		status_label.text = "正在连接 %s…" % ip
	else:
		status_label.text = "连接启动失败。"

func _on_back() -> void:
	Net.disconnect_net()
	_show_setup()
	status_label.text = ""

func _show_campus_online() -> void:
	if campus_dialog == null:
		campus_dialog = AcceptDialog.new()
		campus_dialog.title = "多人联机"
		campus_dialog.ok_button_text = "返回"
		campus_dialog.exclusive = true
		add_child(campus_dialog)
		var fields := VBoxContainer.new()
		fields.custom_minimum_size.x = 440
		fields.add_theme_constant_override("separation", 10)
		campus_dialog.add_child(fields)
		campus_room_input = LineEdit.new()
		CampusTextMenu.apply(campus_room_input.get_menu())
		campus_room_input.placeholder_text = "粘贴房主的邀请码，或填写局域网 IP 地址"
		campus_nickname_input = LineEdit.new()
		CampusTextMenu.apply(campus_nickname_input.get_menu())
		campus_nickname_input.placeholder_text = "输入自己的昵称"
		campus_nickname_input.max_length = 24
		fields.add_child(campus_nickname_input)
		var mode_row := HBoxContainer.new()
		var mode_label := Label.new()
		mode_label.text = "开房模式"
		mode_row.add_child(mode_label)
		campus_mode_input = OptionButton.new()
		for mode_name: String in Net.CAMPUS_MODE_NAMES:
			campus_mode_input.add_item(mode_name)
		campus_mode_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		campus_mode_input.item_selected.connect(func(_mode: int): _describe_campus_modes())
		mode_row.add_child(campus_mode_input)
		fields.add_child(mode_row)
		fields.add_child(campus_room_input)
		var row := HBoxContainer.new()
		fields.add_child(row)
		var labels := ["异地开房", "用邀请码加入", "局域网开房", "按 IP 地址加入"]
		for index in labels.size():
			var button := Button.new()
			button.text = labels[index]
			button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			button.pressed.connect(_open_campus_room.bind(index))
			row.add_child(button)
			campus_dialog_buttons.append(button)
		campus_dialog_status = RichTextLabel.new()
		campus_dialog_status.custom_minimum_size.y = 45
		fields.add_child(campus_dialog_status)
	_update_campus_connection(false)
	campus_nickname_input.text = Settings.campus_nickname
	_describe_campus_modes()
	campus_dialog.popup_centered(Vector2i(510, 280))
	campus_nickname_input.grab_focus()


func _describe_campus_modes() -> void:
	var description := "从正门外集合，可骑车、飞行和投稿。"
	if campus_mode_input.selected == Net.CampusMode.SURVIVAL:
		description = "从致远楼教室出发，合力突围。"
	campus_dialog_status.text = "%s\n最多 %d 人。加入房间时沿用房主选择的模式。" % [description, Net.CAMPUS_MAX_PLAYERS]

func _update_campus_connection(pending: bool) -> void:
	if campus_dialog == null:
		return
	campus_nickname_input.editable = not pending
	campus_room_input.editable = not pending
	campus_mode_input.disabled = pending
	for button in campus_dialog_buttons:
		button.disabled = pending
	campus_dialog.get_ok_button().disabled = pending
	campus_dialog.dialog_close_on_escape = not pending

func _open_campus_room(action: int) -> void:
	if Net.peer != null or campus_dialog.get_ok_button().disabled:
		return
	_save_campus_nickname(campus_nickname_input.text)
	var selected_mode := campus_mode_input.selected
	var address := campus_room_input.text.strip_edges()
	_update_campus_connection(true)
	campus_dialog_status.text = "正在连接…"
	var message := ""
	match action:
		0:
			message = await Net.open_online_campus("", true, selected_mode)
		1:
			message = await Net.open_online_campus(address, false)
		2:
			if not Net.host_game(Net.DEFAULT_PORT, true, selected_mode):
				message = "开房失败，请检查 UDP 27015 是否已被占用。"
		3:
			if not Net.join_game("127.0.0.1" if address.is_empty() else address, Net.DEFAULT_PORT, true):
				message = "连接失败，请检查房主的 IP 地址。"
	if not message.is_empty():
		_update_campus_connection(false)
		campus_dialog_status.text = message
		return
	if Net.is_host():
		campus_dialog.hide()
		_show_lobby()

func _take_leave_message(fallback: String) -> String:
	var message := Net.leave_message
	Net.leave_message = ""
	return fallback if message.is_empty() else message

# ---------------------------------------------------------------- net callbacks

func _on_connected() -> void:
	if Net.campus_room and campus_dialog != null:
		campus_dialog.hide()
	status_label.text = "已加入房间，等待房主开始。"
	_show_lobby()

func _on_failed() -> void:
	var from_campus := campus_dialog != null and campus_dialog.visible
	_set_menu_status(_take_leave_message("连接失败，请检查房主是否在线。" if from_campus else "连接失败，请检查网络后重试。"))
	if from_campus:
		_update_campus_connection(false)
		campus_dialog_status.text = status_label.text
	_show_setup()

func _on_server_disconnected() -> void:
	var message := _take_leave_message("已断开与房主的连接。")
	if campus_loading_path in [Net.CAMPUS_SCENE, Net.CAMPUS_SURVIVAL_SCENE]:
		_campus_loading_failed(message)
	_set_menu_status(message)
	_show_setup()

func _on_match_started() -> void:
	if Net.campus_room:
		_on_campus(Net.campus_scene())
		return
	get_tree().change_scene_to_file("res://scenes/world.tscn")

# ---------------------------------------------------------------- screens

func _show_setup() -> void:
	setup_panel.visible = legacy_menu
	%VersionLabel.visible = legacy_menu
	if legacy_menu:
		campus_title.hide()
	else:
		campus_title.show_page(bool(get_tree().root.get_meta("campus_admin_return", false)))
	lobby_panel.visible = false
	options_panel.visible = false
	character_panel.visible = false
	create_panel.visible = false
	_update_char_label()

func _show_lobby() -> void:
	campus_title.hide()
	setup_panel.visible = false
	options_panel.visible = false
	character_panel.visible = false
	create_panel.visible = false
	lobby_panel.visible = true
	start_button.visible = Net.is_host()
	start_button.text = "开始游戏"
	%Title.text = "校园房间" if Net.campus_room else "联机大厅"
	%BackButton.text = "退出房间"
	%CopyRoomCodeButton.visible = Net.campus_room and not Net.room_code.is_empty() and Net.is_host()
	if lobby_nickname_row == null:
		_build_lobby_nickname()
	lobby_nickname_row.visible = Net.campus_room
	if Net.campus_room:
		lobby_nickname_input.text = Net.get_player_name(Net.local_id())
	_refresh_lobby()


func _save_campus_nickname(value: String) -> void:
	Game.player_name = Net.clean_campus_name(value)
	if Settings.campus_nickname != Game.player_name:
		Settings.campus_nickname = Game.player_name
		Settings.save()


func _build_lobby_nickname() -> void:
	var rows := lobby_players.get_parent()
	lobby_nickname_row = HBoxContainer.new()
	rows.add_child(lobby_nickname_row)
	rows.move_child(lobby_nickname_row, lobby_players.get_index())
	lobby_nickname_input = LineEdit.new()
	CampusTextMenu.apply(lobby_nickname_input.get_menu())
	lobby_nickname_input.placeholder_text = "自己的昵称"
	lobby_nickname_input.max_length = 24
	lobby_nickname_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lobby_nickname_row.add_child(lobby_nickname_input)
	var rename := Button.new()
	rename.text = "保存昵称"
	rename.pressed.connect(_rename_in_lobby)
	lobby_nickname_input.text_submitted.connect(func(_value: String): _rename_in_lobby())
	lobby_nickname_row.add_child(rename)


func _rename_in_lobby() -> void:
	if not Net.campus_room or Net.campus_started:
		return
	_save_campus_nickname(lobby_nickname_input.text)
	lobby_nickname_input.text = Game.player_name
	Net.rename_campus_player(Game.player_name)

# ---------------------------------------------------------------- characters

func _update_char_label() -> void:
	char_label.text = String(Characters.current.get("name", "（未选择）")) if Characters.has_current() else "（未选择）"
	# Continue is only offered when the chosen character has a saved adventure.
	%ContinueBtn.visible = Characters.has_current() and not (Characters.current.get("adventure", {}) as Dictionary).is_empty()

## Resume the chosen character's saved adventure: rebuild the same world (seed +
## climate) solo and restore the dynamic state once it's populated.
func _on_continue() -> void:
	if not campus_loading_path.is_empty():
		return
	var snap: Dictionary = Characters.current.get("adventure", {})
	if snap.is_empty():
		return
	Game.player_name = String(Characters.current.get("name", "同学"))
	Game.config["mode"] = Game.Mode.ADVENTURE
	Game.config["map"] = ADVENTURE_MAP
	Game.config["seed"] = int(snap.get("seed", 0))
	Game.config["map_size"] = int(snap.get("map_size", 2))
	Game.config["mission_points"] = int(snap.get("mission_points", 10))
	Game.config["theme"] = String(snap.get("theme", ""))
	Game.config["bot_skill"] = float(snap.get("bot_skill", 1.0))
	Game.config["bot_count"] = 12
	Game.config["frag_limit"] = 0
	if String(snap.get("climate", "")) != "":
		Game.config["climate"] = String(snap["climate"])
	else:
		Game.config.erase("climate")
	Game.continue_data = snap
	if Net.host_game():
		Net.start_match()
	else:
		status_label.text = "启动失败，请检查端口是否已被占用。"

func _show_characters() -> void:
	setup_panel.visible = false
	create_panel.visible = false
	character_panel.visible = true
	_rebuild_char_list()

func _rebuild_char_list() -> void:
	for c in char_list.get_children():
		c.queue_free()
	if Characters.profiles.is_empty():
		var empty := Label.new()
		empty.text = "暂无角色，请先创建。"
		empty.modulate = Color(1, 1, 1, 0.5)
		char_list.add_child(empty)
		return
	for p in Characters.profiles:
		var pd: Dictionary = p
		var b := Button.new()
		var st: Dictionary = pd.get("stats", {})
		var chosen := String(pd.get("id", "")) == String(Characters.current.get("id", ""))
		b.text = "%s%s  ·  %s  ·  %d adv, %d pts" % [
			"▶ " if chosen else "", String(pd.get("name", "?")),
			Characters.kit_name(String(pd.get("kit", "scout"))),
			int(st.get("adventures", 0)), int(st.get("points", 0))]
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		var id := String(pd.get("id", ""))
		b.pressed.connect(func(): _choose_character(id))
		char_list.add_child(b)

func _choose_character(id: String) -> void:
	Characters.set_current(id)
	_update_char_label()
	_rebuild_char_list()

func _on_delete_character() -> void:
	if Characters.has_current():
		Characters.delete(String(Characters.current["id"]))
		_rebuild_char_list()
		_update_char_label()

func _show_create() -> void:
	%CreateName.text = ""
	%CreateBackstory.text = ""
	%CreateKit.selected = 0
	%CreateColor.color = Color(0.4, 0.6, 0.9)
	character_panel.visible = false
	create_panel.visible = true

func _on_create_confirm() -> void:
	var kit: String = Characters.KIT_IDS[clampi(%CreateKit.selected, 0, Characters.KIT_IDS.size() - 1)]
	Characters.create(%CreateName.text, %CreateColor.color, kit, %CreateBackstory.text)
	_show_characters()

func _refresh_lobby() -> void:
	if not lobby_panel.visible:
		return
	for c in lobby_players.get_children():
		lobby_players.remove_child(c)
		c.queue_free()
	for pid in Net.players.keys():
		var l := Label.new()
		var tag := ("  （房主）") if pid == 1 else ""
		l.text = "• %s%s" % [Net.players[pid]["name"], tag]
		lobby_players.add_child(l)
	if Net.campus_room:
		lobby_summary.text = "%s\n%d/%d 人" % [Net.CAMPUS_MODE_NAMES[Net.campus_mode], Net.players.size(), Net.CAMPUS_MAX_PLAYERS]
		if not Net.room_code.is_empty():
			lobby_summary.text += "\n邀请码 %s" % Net.room_code
		elif Net.is_host():
			var addresses := PackedStringArray()
			for ip in IP.get_local_addresses():
				if ":" not in ip and not ip.begins_with("127.") and not ip.begins_with("169.254."):
					addresses.append(ip)
			lobby_summary.text += "\n局域网 · UDP %d · %s" % [Net.DEFAULT_PORT, ", ".join(addresses)]
		return
	var summary := "%s" % Game.mode_name()
	if Game.is_coop():
		var m := Missions.get_mission(Game.config.get("mission_id", ""))
		summary += " — " + m.get("name", "?")
	elif Game.is_battle_royale():
		summary += " · 最后一人获胜"
	elif Game.is_adventure():
		summary += " · %d 任务积分" % int(Game.config.get("mission_points", 10))
	else:
		summary += " · 击败目标 %d" % int(Game.config["frag_limit"])
	summary += "\n电脑玩家 %d 名（%s）" % [int(Game.config["bot_count"]), _skill_name(Game.config["bot_skill"])]
	lobby_summary.text = summary

func _skill_name(v: float) -> String:
	for s in SKILLS:
		if abs(s["value"] - v) < 0.01:
			return s["name"]
	return "自定义"
