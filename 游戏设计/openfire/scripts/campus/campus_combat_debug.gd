extends Control

const TOGGLE_KEY := KEY_F6

var level: Node
var overlay: ColorRect
var fields: Dictionary[StringName, SpinBox] = {}
var previous_pause := false
var previous_capture := false
var active := false

func _ready() -> void:
	name = "CombatDebug"
	process_mode = Node.PROCESS_MODE_ALWAYS
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var toggle := Button.new()
	toggle.text = "F6  调试"
	add_child(toggle)
	toggle.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	toggle.offset_left = -136
	toggle.offset_right = -20
	toggle.offset_top = 56
	toggle.offset_bottom = 92
	toggle.pressed.connect(_open)
	_build_panel()

func _build_panel() -> void:
	overlay = ColorRect.new()
	overlay.color = Color(0.04, 0.06, 0.09, 0.74)
	add_child(overlay)
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	overlay.add_child(center)
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var panel := PanelContainer.new()
	center.add_child(panel)
	panel.custom_minimum_size.x = 410
	var margin := MarginContainer.new()
	panel.add_child(margin)
	for edge in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + edge, 20)
	var rows := VBoxContainer.new()
	rows.add_theme_constant_override("separation", 12)
	margin.add_child(rows)
	var title := Label.new()
	title.text = "对局调试"
	title.add_theme_font_size_override("font_size", 22)
	rows.add_child(title)

	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 18)
	grid.add_theme_constant_override("v_separation", 6)
	rows.add_child(grid)
	var spawner = level.spawner
	var max_range: float = spawner.DESPAWN_DISTANCE - 1.0
	_add_field(grid, &"group_size", "每波数量（0 = 随机 2–10）", spawner.group_size, 0, spawner.ACTIVE_LIMIT, 1,
		func(value: float): spawner.group_size = int(value))
	_add_field(grid, &"interval", "刷新间隔（秒）", spawner.spawn_interval, 0.5, 600, 0.1,
		spawner.set_spawn_interval)
	_add_field(grid, &"spawn_min", "最近水平刷新距离（米）", spawner.min_spawn_distance,
		spawner.spawn_distance_floor(), spawner.max_spawn_distance - spawner.RANGE_STEP, spawner.RANGE_STEP,
		func(_value: float): _update_spawn_range())
	_add_field(grid, &"spawn_max", "最远刷新距离（米）", spawner.max_spawn_distance,
		spawner.min_spawn_distance + spawner.RANGE_STEP, max_range, spawner.RANGE_STEP,
		func(_value: float): _update_spawn_range())
	_add_field(grid, &"chase_distance", "追击距离（米）", level.zombie_chase_distance, 1, max_range, 0.5,
		func(value: float): level.zombie_chase_distance = value)
	_add_field(grid, &"attack_range", "攻击范围（米）", level.zombie_attack_range, 0.6, 6, 0.01,
		func(value: float): level.zombie_attack_range = value)
	_add_field(grid, &"run_speed", "丧尸跑速（米/秒）", level.zombie_run_speed, 0.5, 12, 0.05,
		func(value: float): level.zombie_run_speed = value)
	var walker = level.walker
	_add_field(grid, &"player_sprint_speed", "人物 Shift 跑速（米/秒）",
		walker.base_human_sprint_speed(), walker.WALK_SPEED, 15.0, 0.05,
		func(value: float): walker.human_sprint_speed_override = value)

	var options := HBoxContainer.new()
	options.add_theme_constant_override("separation", 18)
	rows.add_child(options)
	var invincible := CheckButton.new()
	invincible.name = "Invincible"
	invincible.text = "无敌"
	invincible.button_pressed = level.debug_invincible
	invincible.toggled.connect(level.set_debug_invincible)
	options.add_child(invincible)
	var flight := CheckButton.new()
	flight.name = "Flight"
	flight.text = "飞行"
	flight.button_pressed = level.walker.flying
	flight.toggled.connect(level.set_debug_flight)
	options.add_child(flight)
	var reset_speed := Button.new()
	reset_speed.text = "恢复人物跑速"
	reset_speed.pressed.connect(func():
		fields[&"player_sprint_speed"].set_value_no_signal(walker.base_human_sprint_speed())
		walker.human_sprint_speed_override = 0.0)
	options.add_child(reset_speed)

	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_END
	buttons.add_theme_constant_override("separation", 8)
	rows.add_child(buttons)
	var spawn_button := Button.new()
	spawn_button.text = "立即刷新一波"
	buttons.add_child(spawn_button)
	spawn_button.pressed.connect(_spawn_wave)
	var resume := Button.new()
	resume.text = "继续对局"
	buttons.add_child(resume)
	resume.pressed.connect(_close)
	overlay.hide()

func _add_field(grid: GridContainer, key: StringName, title: String, value: float,
		minimum: float, maximum: float, step: float, apply: Callable) -> void:
	var label := Label.new()
	label.text = title
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(label)
	var spin := SpinBox.new()
	spin.custom_minimum_size.x = 104
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = step
	spin.value = value
	grid.add_child(spin)
	fields[key] = spin
	spin.value_changed.connect(apply)

func _update_spawn_range() -> void:
	var minimum := fields[&"spawn_min"].value
	var maximum := fields[&"spawn_max"].value
	var spawner = level.spawner
	fields[&"spawn_min"].max_value = maximum - spawner.RANGE_STEP
	fields[&"spawn_max"].min_value = minimum + spawner.RANGE_STEP
	spawner.set_spawn_range(minimum, maximum)

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if active and event.physical_keycode in [TOGGLE_KEY, KEY_ESCAPE]:
			_close()
		elif not active and event.physical_keycode == TOGGLE_KEY:
			_open()
		else:
			return
		get_viewport().set_input_as_handled()

func _open() -> void:
	if active or level.round_finished or not level.walker.is_processing_input():
		return
	active = true
	previous_pause = get_tree().paused
	previous_capture = level.walker.mouse_captured
	level.walker._capture_mouse(false)
	level.firearms.trigger_blocked = true
	get_tree().paused = true
	overlay.show()

func _close() -> void:
	if not active:
		return
	get_viewport().gui_release_focus()
	overlay.hide()
	active = false
	get_tree().paused = previous_pause
	level.walker._capture_mouse(previous_capture)

func _spawn_wave() -> void:
	_close()
	var requested: int = level.spawner.try_group(true)
	if requested > 0:
		level.spawner.remaining = level.spawner.spawn_interval
		level._report("正在寻找刷新点，计划生成 %d 只丧尸。" % requested)
	else:
		if level.spawner.zombies.size() >= level.spawner.ACTIVE_LIMIT:
			level._report("丧尸已达场景上限，清理一部分后再刷新。")
		else:
			level._report("当前角色状态无法刷新丧尸。")

func _exit_tree() -> void:
	if active:
		get_tree().paused = previous_pause
