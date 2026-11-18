extends Control

const CampusTextMenu := preload("res://scripts/ui/campus_text_menu.gd")
const CampusTour = preload("res://scripts/campus/campus_tour_walker.gd")
const EAST_GATE := preload("res://assets/ui/campus_east_gate.webp")
const INK := Color("#101619")
const PAPER := Color("#f0ede2")
const MUTED := Color("#aeb8b7")
const AMBER := Color("#e2ad63")

signal route_requested(path: String)
signal online_requested
signal options_requested
signal legacy_requested
signal quit_requested

var main_actions: VBoxContainer
var test_actions: VBoxContainer
var status: Label
var play_button: Button
var admin_button: Button
var test_button: Button
var return_button: Button


func _ready() -> void:
	set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	var photo := TextureRect.new()
	photo.texture = EAST_GATE
	photo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	photo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	photo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	photo.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	photo.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	photo.anchor_left = 0.30
	add_child(photo)

	var shade := TextureRect.new()
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.36, 0.61, 1.0])
	gradient.colors = PackedColorArray([INK, INK, Color(0.06, 0.09, 0.1, 0.16), Color(0.06, 0.09, 0.1, 0.06)])
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.width = 512
	texture.height = 2
	shade.texture = texture
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	shade.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	shade.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	add_child(shade)

	var area := MarginContainer.new()
	area.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	area.offset_left = 68
	area.offset_top = 42
	area.offset_right = -48
	area.offset_bottom = -30
	add_child(area)
	var layout := VBoxContainer.new()
	area.add_child(layout)
	var chapter := _label("石家庄一中东校区", 17, AMBER)
	layout.add_child(chapter)
	var center := CenterContainer.new()
	center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	layout.add_child(center)
	main_actions = _column(center)
	main_actions.add_child(_label("余铃", 104, PAPER))
	main_actions.add_child(_label("上楼顶取枪，经操场补给，突围前往尚德广场。", 21, MUTED))
	var gap := Control.new()
	gap.custom_minimum_size.y = 19
	main_actions.add_child(gap)

	play_button = _button(main_actions, "丧尸模式   ›", true)
	play_button.pressed.connect(func(): route_requested.emit("res://scenes/campus/survival.tscn"))
	_button(main_actions, "自由探索").pressed.connect(func(): route_requested.emit(CampusTour.SCENE))
	_button(main_actions, "多人联机").pressed.connect(func(): online_requested.emit())
	_button(main_actions, "设置").pressed.connect(func(): options_requested.emit())
	_button(main_actions, "退出游戏").pressed.connect(func(): quit_requested.emit())

	test_actions = _column(center)
	test_actions.add_child(_label("管理员测试", 46, PAPER))
	test_actions.add_child(_label("测试模式", 17, AMBER))
	test_button = _button(test_actions, "逃生关卡测试   ›", true)
	test_button.pressed.connect(func(): route_requested.emit("res://scenes/campus/survival_admin.tscn"))
	_button(test_actions, "人物测试").pressed.connect(func(): route_requested.emit("res://scenes/campus/character_trial.tscn"))
	_button(test_actions, "校园漫游 · 校门").pressed.connect(func(): route_requested.emit("res://scenes/campus/gate_plaza.tscn"))
	_button(test_actions, "校园漫游 · 致远楼").pressed.connect(func(): route_requested.emit("res://scenes/campus/interior.tscn"))
	_button(test_actions, "OpenFire 开发菜单").pressed.connect(func(): legacy_requested.emit())
	return_button = _button(test_actions, "返回主菜单")
	return_button.pressed.connect(show_page.bind(false))
	test_actions.hide()

	status = _label("", 17, AMBER)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.hide()
	layout.add_child(status)
	var footer := HBoxContainer.new()
	layout.add_child(footer)
	var credits := _button(footer, "制作人员与开源鸣谢")
	credits.pressed.connect(_show_credits)
	footer.add_child(_label("v" + str(ProjectSettings.get_setting("application/config/version")), 15, PAPER))
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(spacer)
	admin_button = _button(footer, "管理员测试")
	admin_button.pressed.connect(show_page.bind(true))
	admin_button.visible = OS.has_feature("editor") or OS.has_feature("campus_admin")


func show_page(admin: bool) -> void:
	var testing := admin and admin_button.visible
	get_tree().root.set_meta("campus_admin_return", testing)
	main_actions.visible = not testing
	test_actions.visible = testing
	admin_button.disabled = testing
	show()
	if testing:
		test_button.grab_focus()
	else:
		play_button.grab_focus()


func set_status(message: String) -> void:
	status.text = message
	status.visible = not message.is_empty()


func set_loading(loading: bool) -> void:
	if loading:
		# The loading overlay covers the menu. Suspend both mouse and keyboard input.
		process_mode = Node.PROCESS_MODE_DISABLED
	else:
		process_mode = Node.PROCESS_MODE_INHERIT
		if visible:
			(test_button if test_actions.visible else play_button).grab_focus()


func _unhandled_input(event: InputEvent) -> void:
	if visible and test_actions.visible and event.is_action_pressed("ui_cancel"):
		show_page(false)
		get_viewport().set_input_as_handled()


func _column(parent: Control) -> VBoxContainer:
	var rows := VBoxContainer.new()
	rows.custom_minimum_size.x = 335
	rows.add_theme_constant_override("separation", 7)
	parent.add_child(rows)
	return rows


func _label(copy: String, size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = copy
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	return label


func _style(fill: Color, edge: Color, left: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = edge
	style.border_width_left = left
	style.content_margin_left = 15
	style.content_margin_right = 15
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	return style


func _button(parent: Container, copy: String, primary := false) -> Button:
	var button := Button.new()
	button.text = copy
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.custom_minimum_size.y = 47 if primary else 39
	button.add_theme_font_size_override("font_size", 22 if primary else 18)
	var normal := Color("#e2ad63") if primary else Color(0.06, 0.09, 0.10, 0.88)
	var hover := Color("#f0c185") if primary else Color("#304044")
	var ink := INK if primary else PAPER
	for state in ["font_color", "font_hover_color", "font_focus_color", "font_pressed_color"]:
		button.add_theme_color_override(state, ink)
	button.add_theme_stylebox_override("normal", _style(normal, AMBER, 3 if primary else 0))
	button.add_theme_stylebox_override("hover", _style(hover, AMBER, 3))
	button.add_theme_stylebox_override("pressed", _style(hover.darkened(0.12), AMBER, 3))
	var focus := _style(Color.TRANSPARENT, PAPER, 2)
	focus.draw_center = false
	focus.set_border_width_all(2)
	button.add_theme_stylebox_override("focus", focus)
	parent.add_child(button)
	return button


func _show_credits() -> void:
	var dialog := AcceptDialog.new()
	dialog.title = "制作人员与开源鸣谢"
	dialog.dialog_text = "《一中东·余铃》 · 校园重建与游戏制作\n\n基于 OpenFire（MIT）与 Godot Engine（MIT）。\n感谢 Kenney、Quaternius 以及联机组件的开发者。\n开源许可与署名随游戏提供。"
	dialog.ok_button_text = "返回"
	dialog.add_button("查看开源许可", true).pressed.connect(_show_licenses)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered(Vector2i(505, 205))


func _show_licenses() -> void:
	var dialog := AcceptDialog.new()
	dialog.title = "开源许可与署名"
	dialog.ok_button_text = "返回"
	var notice := TextEdit.new()
	CampusTextMenu.apply(notice.get_menu())
	notice.editable = false
	notice.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	notice.custom_minimum_size = Vector2(690, 410)
	var files := ["CREDITS.md", "LICENSE", "addons/epic-online-services-godot/LICENSE.md",
		"addons/godot_iroh/LICENSE", "assets/campus/tour/LICENSE-kenney-racing.txt",
		"assets/campus/weapons/LICENSE-expressobits.txt", "assets/campus/weapons/LICENSE-bukkbeek.txt"]
	for path: String in files:
		var license := FileAccess.get_file_as_string("res://" + path)
		if not license.is_empty():
			notice.text += license + "\n\n"
	dialog.add_child(notice)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered()
