extends PanelContainer

const HEALTHY_COLOR := Color("#cf4f59")
const INFECTED_COLOR := Color("#64cb78")
const TAPE_COLOR := Color("#ecc58c")
const FRAME_COLOR := Color("#59626b")

var amount: Label
var status: Label
var bar: ProgressBar
var fill_style: StyleBoxFlat
var frame_style: StyleBoxFlat
var last_infection_seconds := -1
var last_armored := false

func _ready() -> void:
	name = "PlayerHealth"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	custom_minimum_size.x = 310
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.055, 0.075, 0.09, 0.9)
	panel_style.set_corner_radius_all(8)
	panel_style.content_margin_left = 12.0
	panel_style.content_margin_right = 12.0
	panel_style.content_margin_top = 8.0
	panel_style.content_margin_bottom = 10.0
	add_theme_stylebox_override("panel", panel_style)
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT, Control.PRESET_MODE_MINSIZE, 20)
	grow_vertical = Control.GROW_DIRECTION_BEGIN

	var rows := VBoxContainer.new()
	rows.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rows.add_theme_constant_override("separation", 5)
	add_child(rows)
	var header := HBoxContainer.new()
	header.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rows.add_child(header)
	amount = Label.new()
	amount.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	amount.add_theme_font_size_override("font_size", 18)
	header.add_child(amount)
	status = Label.new()
	status.add_theme_font_size_override("font_size", 16)
	header.add_child(status)

	var frame := PanelContainer.new()
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rows.add_child(frame)
	frame_style = StyleBoxFlat.new()
	frame_style.bg_color = Color("#202931")
	frame_style.border_color = FRAME_COLOR
	frame_style.set_border_width_all(2)
	frame_style.set_corner_radius_all(5)
	frame.add_theme_stylebox_override("panel", frame_style)
	bar = ProgressBar.new()
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.custom_minimum_size.y = 12.0
	bar.show_percentage = false
	var track := StyleBoxFlat.new()
	track.bg_color = Color("#202931")
	track.set_corner_radius_all(3)
	fill_style = StyleBoxFlat.new()
	fill_style.bg_color = HEALTHY_COLOR
	fill_style.set_corner_radius_all(3)
	bar.add_theme_stylebox_override("background", track)
	bar.add_theme_stylebox_override("fill", fill_style)
	frame.add_child(bar)

func update_status(health: int, max_health: int, infection_seconds: int, armored: bool) -> void:
	if bar.value == health and bar.max_value == max_health \
			and last_infection_seconds == infection_seconds and last_armored == armored:
		return
	last_infection_seconds = infection_seconds
	last_armored = armored
	bar.max_value = max_health
	bar.value = health
	amount.text = "生命 %d / %d" % [health, max_health]
	var messages := PackedStringArray()
	if infection_seconds > 0:
		messages.append("感染 %d 秒" % infection_seconds)
	if armored:
		messages.append("胶布挡咬 ×1")
	status.text = " · ".join(messages)
	status.modulate = INFECTED_COLOR if infection_seconds > 0 else TAPE_COLOR
	fill_style.bg_color = INFECTED_COLOR if infection_seconds > 0 else HEALTHY_COLOR
	frame_style.border_color = TAPE_COLOR if armored else FRAME_COLOR
