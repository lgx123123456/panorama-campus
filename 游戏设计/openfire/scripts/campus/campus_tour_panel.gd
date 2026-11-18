extends CanvasLayer

const CampusTextMenu := preload("res://scripts/ui/campus_text_menu.gd")
const INTRO_SHOWN := &"campus_photo_intro_shown"
const SURVEY_URL := "https://wj.qq.com/s2/28723469/bcqi/"
const SURVEY_CODE := preload("res://assets/campus/tour/photo_survey_code.png")
const PAPER := Color("#f2ede2")
const AMBER := Color("#f0bf77")

var modal: CenterContainer
var shade: ColorRect
var hud: Control
var controls: Label
var toast: Label
var marker: Label
var modal_rows: VBoxContainer
var code: LineEdit
var coordinates: Label
var photo_status: Label
var photo_rows: VBoxContainer
var pause_rows: VBoxContainer
var intro_rows: VBoxContainer
var start_tour: Button
var photo_close: Button
var resume: Button
var caption: PanelContainer
var caption_text: Label
var toast_timer: Timer
var modal_kind := ""
var mouse_was_captured := true
var saving := false

@onready var walker = $"../Walker"


func _ready() -> void:
	hud = Control.new()
	hud.name = "HUD"
	hud.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(hud)

	var top := PanelContainer.new()
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top.position = Vector2(24, 24)
	top.add_theme_stylebox_override("panel", _panel_style(Color("#152024dc"), 12, 8))
	hud.add_child(top)
	var top_rows := VBoxContainer.new()
	top_rows.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top.add_child(top_rows)
	top_rows.add_child(_label("自由探索", 21, AMBER))
	controls = _label("", 16)
	top_rows.add_child(controls)

	marker = _label("+", 19)
	marker.add_theme_color_override("font_shadow_color", Color("#081418"))
	marker.add_theme_constant_override("shadow_offset_y", 1)
	marker.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	marker.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	hud.add_child(marker)
	marker.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	marker.grow_horizontal = Control.GROW_DIRECTION_BOTH
	marker.grow_vertical = Control.GROW_DIRECTION_BOTH

	var photo_button := _button("补充实景照片  [P]")
	hud.add_child(photo_button)
	photo_button.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	photo_button.offset_right = -24
	photo_button.offset_bottom = -24
	photo_button.offset_left = -210
	photo_button.offset_top = -65
	photo_button.pressed.connect(walker.request_photo)

	var door_hint: Label = $"../Interface/DebugControls/Rows/DoorHint"
	door_hint.reparent(hud, false)
	door_hint.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	door_hint.offset_top = -68
	door_hint.offset_bottom = -34
	door_hint.grow_horizontal = Control.GROW_DIRECTION_BOTH
	door_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	door_hint.add_theme_color_override("font_shadow_color", Color.BLACK)
	door_hint.add_theme_constant_override("shadow_offset_y", 2)

	toast = _label("", 16, AMBER)
	top_rows.add_child(toast)
	toast.hide()
	toast_timer = Timer.new()
	toast_timer.one_shot = true
	add_child(toast_timer)
	toast_timer.timeout.connect(toast.hide)

	caption = PanelContainer.new()
	caption.add_theme_stylebox_override("panel", _panel_style(Color("#172023ed"), 18, 11))
	add_child(caption)
	caption.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	caption.offset_left = 24
	caption.offset_bottom = -24
	caption.grow_vertical = Control.GROW_DIRECTION_BEGIN
	caption_text = _label("", 22)
	caption.add_child(caption_text)
	caption.hide()

	shade = ColorRect.new()
	shade.color = Color(0.015, 0.028, 0.031, 0.68)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	shade.hide()

	modal = CenterContainer.new()
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(modal)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _panel_style(Color("#172326"), 22, 19))
	modal.add_child(panel)
	modal_rows = VBoxContainer.new()
	modal_rows.add_theme_constant_override("separation", 12)
	panel.add_child(modal_rows)
	_build_photo()
	_build_pause()
	_build_intro()
	modal.hide()
	_show_intro_once.call_deferred()


func _build_intro() -> void:
	intro_rows = VBoxContainer.new()
	intro_rows.custom_minimum_size.x = 465
	intro_rows.add_theme_constant_override("separation", 14)
	modal_rows.add_child(intro_rows)
	intro_rows.add_child(_label("帮我补充校园实景照片", 27, AMBER))

	var invitation := _label("由于作者手里的学校照片素材有限，如果你逛到一处熟悉的地方，发现和记忆里有出入，欢迎上传你相册里的照片。我会根据你上传的照片对具体场景进行还原。", 18)
	invitation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro_rows.add_child(invitation)
	var instructions := _label("在游戏里的自由探索模式里对准那处位置，按 P，再打开问卷上传。", 18)
	instructions.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro_rows.add_child(instructions)

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	intro_rows.add_child(actions)
	start_tour = _button("开始游览")
	start_tour.pressed.connect(close_modal)
	actions.add_child(start_tour)
	var see_how := _button("看看怎么投稿")
	see_how.pressed.connect(_preview_photo_submission)
	actions.add_child(see_how)


func _show_intro_once() -> void:
	var root := get_tree().root
	if DisplayServer.get_name() == "headless" or root.has_meta(INTRO_SHOWN):
		return
	for child in root.get_children():
		if child.scene_file_path == "res://scenes/campus/loading_overlay.tscn":
			await child.tree_exited
			break
	if not is_inside_tree() or modal_visible() or root.has_meta(INTRO_SHOWN):
		return
	root.set_meta(INTRO_SHOWN, true)
	_open_modal("intro")
	start_tour.grab_focus()


func _preview_photo_submission() -> void:
	close_modal()
	walker.request_photo()


func _build_photo() -> void:
	photo_rows = VBoxContainer.new()
	photo_rows.add_theme_constant_override("separation", 12)
	modal_rows.add_child(photo_rows)
	photo_rows.add_child(_label("补充实景照片", 28, AMBER))

	var content := HBoxContainer.new()
	content.add_theme_constant_override("separation", 20)
	photo_rows.add_child(content)
	var qr_rows := VBoxContainer.new()
	content.add_child(qr_rows)
	var qr := TextureRect.new()
	qr.texture = SURVEY_CODE
	qr.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	qr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	qr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	qr.custom_minimum_size = Vector2(190, 190)
	qr_rows.add_child(qr)
	var scan := _label("微信扫码打开问卷", 15)
	scan.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	qr_rows.add_child(scan)

	var details := VBoxContainer.new()
	details.custom_minimum_size.x = 344
	details.add_theme_constant_override("separation", 7)
	content.add_child(details)
	details.add_child(_label("点位码", 16, AMBER))
	code = LineEdit.new()
	CampusTextMenu.apply(code.get_menu())
	code.editable = false
	code.add_theme_font_size_override("font_size", 23)
	code.add_theme_color_override("font_uneditable_color", PAPER)
	details.add_child(code)
	coordinates = _label("", 15)
	details.add_child(coordinates)
	var help := _label("把点位图和实拍一起上传。用手机时，可拍下屏幕上的点位码，再和实拍一起提交。", 16)
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.add_child(help)
	photo_status = _label("", 15, AMBER)
	details.add_child(photo_status)
	photo_status.hide()

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	photo_rows.add_child(actions)
	var copy := _button("复制点位码")
	copy.pressed.connect(_copy_code)
	actions.add_child(copy)
	var open := _button("打开腾讯问卷")
	open.pressed.connect(_open_survey)
	actions.add_child(open)
	var save := _button("保存点位图")
	save.pressed.connect(_save_position_image)
	actions.add_child(save)
	photo_close = _button("返回游览")
	photo_close.pressed.connect(close_modal)
	actions.add_child(photo_close)


func _build_pause() -> void:
	pause_rows = VBoxContainer.new()
	pause_rows.custom_minimum_size.x = 252
	pause_rows.add_theme_constant_override("separation", 12)
	modal_rows.add_child(pause_rows)
	pause_rows.add_child(_label("自由探索", 27, AMBER))
	resume = _button("继续游览")
	resume.pressed.connect(close_modal)
	pause_rows.add_child(resume)
	var home := _button("退出房间" if Net.campus_room else "返回主菜单")
	home.pressed.connect(_return_to_menu)
	pause_rows.add_child(home)


func _label(value: String, size: int, color := PAPER) -> Label:
	var result := Label.new()
	result.text = value
	result.add_theme_font_size_override("font_size", size)
	result.add_theme_color_override("font_color", color)
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return result


func _button(value: String) -> Button:
	var button := Button.new()
	button.text = value
	button.custom_minimum_size.y = 41
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_color_override("font_color", PAPER)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_stylebox_override("normal", _panel_style(Color("#304347"), 10, 6))
	button.add_theme_stylebox_override("hover", _panel_style(Color("#456064"), 10, 6))
	button.add_theme_stylebox_override("pressed", _panel_style(Color("#253538"), 10, 6))
	return button


func _panel_style(fill: Color, x: int, y: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.set_corner_radius_all(7)
	style.content_margin_left = x
	style.content_margin_right = x
	style.content_margin_top = y
	style.content_margin_bottom = y
	return style


func update_controls(mode: int, near_scooter: bool, climb_enabled: bool, climbing: bool) -> void:
	var text := ""
	match mode:
		walker.Mode.WALK:
			text = "WASD 移动 · Shift 跑 · 空格 跳\nE %s · F 喷气背包 · V 视角" % ("骑电动车" if near_scooter else "开门")
		walker.Mode.JETPACK:
			text = "WASD 飞行 · Shift 加速\n空格 上升 · Ctrl 下降 · F 收起背包"
		walker.Mode.SCOOTER:
			if climbing:
				text = "W 上爬 · S 下爬 · A/D 横移\n空格 停在墙面"
			else:
				text = "W 加速 · S 倒车 · A/D 转向\n空格 刹车 · E 下车\nG %s" % ("关闭攀墙" if climb_enabled else "开启攀墙")
	text += "\nR 回校门 · Tab 鼠标 · Esc 暂停"
	if text != controls.text:
		controls.text = text


func notify(message: String) -> void:
	toast.text = message
	toast.show()
	toast_timer.start(3.5)


func modal_visible() -> bool:
	return not modal_kind.is_empty()


func open_pause() -> void:
	_open_modal("pause")
	resume.grab_focus()


func open_photo(location: Dictionary) -> void:
	var point: Vector3 = location.point
	code.text = location.code
	photo_status.hide()
	var label := "镜头指向" if location.aim_hit else "玩家位置"
	coordinates.text = "%s  %.1f / %.1f / %.1f 米  ·  朝向 %03d°" % [
		label, point.x, point.y, point.z, location.heading,
	]
	caption_text.text = "校园实景补图   %s\n%s" % [code.text, coordinates.text]
	_open_modal("photo")
	photo_close.grab_focus()


func _open_modal(kind: String) -> void:
	if not modal_visible():
		mouse_was_captured = walker.mouse_captured
	modal_kind = kind
	walker._capture_mouse(false)
	photo_rows.visible = kind == "photo"
	pause_rows.visible = kind == "pause"
	intro_rows.visible = kind == "intro"
	shade.show()
	modal.show()
	hud.hide()


func close_modal() -> void:
	if saving:
		return
	modal_kind = ""
	modal.hide()
	shade.hide()
	hud.show()
	walker._capture_mouse(mouse_was_captured)


func _return_to_menu() -> void:
	if walker.leave_session.is_valid():
		walker.leave_session.call()
		return
	if get_tree().change_scene_to_file("res://scenes/main_menu.tscn") != OK:
		close_modal()
		notify("主菜单载入失败，请重试")


func _copy_code() -> void:
	DisplayServer.clipboard_set(code.text)
	code.select_all()
	_set_photo_status("点位码已复制")


func _open_survey() -> void:
	_copy_code()
	var error := OS.shell_open(SURVEY_URL)
	if error != OK:
		_set_photo_status("浏览器打开失败，可用微信扫码。")


func _save_position_image() -> void:
	if saving or DisplayServer.get_name() == "headless":
		return
	saving = true
	modal.hide()
	shade.hide()
	caption.show()
	await RenderingServer.frame_post_draw
	var picture := get_viewport().get_texture().get_image()
	caption.hide()
	shade.show()
	modal.show()
	var filename := "OpenFire_%s.png" % code.text.replace("/", "_")
	var path := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES).path_join(filename)
	if picture.save_png(path) != OK:
		path = ProjectSettings.globalize_path("user://" + filename)
		if picture.save_png(path) != OK:
			_set_photo_status("点位图保存失败，请复制点位码。")
			saving = false
			return
	_set_photo_status("点位图已保存，可与实拍一同上传。")
	OS.shell_show_in_file_manager(path)
	saving = false


func _set_photo_status(message: String) -> void:
	photo_status.text = message
	photo_status.show()
