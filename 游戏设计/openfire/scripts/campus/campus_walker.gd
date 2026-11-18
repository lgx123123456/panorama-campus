extends CharacterBody3D

const WALK_SPEED := 3.2
const RUN_SPEED := 5.0
const LOOK_SENSITIVITY := 0.0024
const STEP_HEIGHT := 0.19
const STEP_RETRY_INTERVAL := 0.12
const CampusDoors = preload("res://scripts/campus/campus_doors.gd")

@export var allow_position_reset := true
@export var allow_jump := false
@export var allow_flight := true

const JUMP_SPEED := 4.6
const JUMP_BUFFER := 0.12
const COYOTE_TIME := 0.10

# Horizontal inertia adapted from expressobits/character-controller (MIT).
@export var step_retry_interval := STEP_RETRY_INTERVAL
@export var acceleration := 12.0
@export var deceleration := 18.0
@export var air_control := 0.35

static var speed_multiplier := 2.0
var flying := false
var step_retry_time := 0.0
var mouse_captured := true
var jump_buffer_left := 0.0
var coyote_left := 0.0
var leave_session: Callable

@onready var camera: Camera3D = $Camera3D
@onready var spawn: Marker3D = %Spawn
@onready var speed_slider: HSlider = $"../Interface/DebugControls/Rows/Speed"
@onready var speed_label: Label = $"../Interface/DebugControls/Rows/SpeedLabel"
@onready var flight_button: CheckButton = $"../Interface/DebugControls/Rows/Flight"

func _ready() -> void:
	camera.fov = Settings.fov
	speed_slider.value = speed_multiplier
	speed_slider.value_changed.connect(_set_speed)
	flight_button.toggled.connect(_set_flying)
	_set_speed(speed_multiplier)
	_capture_mouse(true)
	_reset_position()
	if bool(get_tree().root.get_meta("campus_admin_return", false)):
		var mark := Label.new()
		mark.text = "测试模式"
		mark.add_theme_font_size_override("font_size", 18)
		mark.add_theme_color_override("font_color", Color("#f2ba72"))
		mark.add_theme_color_override("font_shadow_color", Color.BLACK)
		mark.add_theme_constant_override("shadow_offset_y", 2)
		mark.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
		mark.offset_left = -124
		mark.offset_top = 22
		$"../Interface".add_child(mark)

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.physical_keycode == KEY_TAB:
			_capture_mouse(not mouse_captured)
			get_viewport().set_input_as_handled()
		elif allow_flight and event.physical_keycode == KEY_F:
			flight_button.button_pressed = not flying
			get_viewport().set_input_as_handled()
		elif event.physical_keycode == KEY_E and mouse_captured:
			get_parent().get_node("Doors").interact()
			get_viewport().set_input_as_handled()

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		if leave_session.is_valid():
			leave_session.call()
		else:
			get_tree().change_scene_to_file("res://scenes/main_menu.tscn")
	elif allow_position_reset and event.is_action_pressed("reload"):
		_reset_position()
	elif event is InputEventMouseMotion and mouse_captured:
		var sensitivity := LOOK_SENSITIVITY * Settings.mouse_sensitivity
		rotate_y(-event.screen_relative.x * sensitivity)
		camera.rotation.x = clampf(camera.rotation.x - event.screen_relative.y * sensitivity, -1.48, 1.48)
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_capture_mouse(true)

func _physics_process(delta: float) -> void:
	step_retry_time = maxf(0.0, step_retry_time - delta)
	jump_buffer_left = maxf(0.0, jump_buffer_left - delta)
	coyote_left = COYOTE_TIME if is_on_floor() else maxf(0.0, coyote_left - delta)
	if mouse_captured and Input.is_action_just_pressed("jump"):
		jump_buffer_left = JUMP_BUFFER
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	if not mouse_captured:
		input = Vector2.ZERO
	var direction := global_basis * Vector3(input.x, 0, input.y)
	var speed := _movement_speed()
	if flying:
		direction = camera.global_basis * Vector3(input.x, 0, input.y)
		if mouse_captured:
			direction.y += float(Input.is_physical_key_pressed(KEY_SPACE)) - float(Input.is_physical_key_pressed(KEY_CTRL))
		move_and_collide(direction.limit_length() * speed * delta)
		velocity = Vector3.ZERO
		return
	var horizontal := Vector3(velocity.x, 0, velocity.z)
	var rate := acceleration if direction.dot(horizontal) > 0.0 else deceleration
	if not is_on_floor():
		rate *= air_control
	horizontal = horizontal.lerp(direction * speed, 1.0 - exp(-rate * delta))
	if not mouse_captured or speed <= 0.0:
		horizontal = Vector3.ZERO
	velocity.x = horizontal.x
	velocity.z = horizontal.z
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= get_gravity().length() * delta
	if coyote_left > 0.0 and jump_buffer_left > 0.0 and _can_jump():
		velocity.y = JUMP_SPEED
		jump_buffer_left = 0.0
		coyote_left = 0.0
	var was_on_floor := is_on_floor()
	var motion := Vector3(velocity.x, 0, velocity.z) * delta
	move_and_slide()
	if was_on_floor and velocity.y <= 0.0 and is_on_wall() and step_retry_time <= 0.0:
		_step_up(motion)
	if global_position.y < -2.0:
		_reset_position()

func _movement_speed() -> float:
	return (RUN_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED) * speed_multiplier

func _can_jump() -> bool:
	return allow_jump and mouse_captured

func _step_up(motion: Vector3) -> void:
	if motion.length_squared() < 0.000001:
		return
	step_retry_time = step_retry_interval
	step_up_body(self, motion)

static func step_up_body(body: CharacterBody3D, motion: Vector3) -> void:
	var low_obstacle := false
	for index in body.get_slide_collision_count():
		var hit := body.get_slide_collision(index)
		var height := hit.get_position().y - body.global_position.y
		if absf(hit.get_normal().y) < 0.7 and height > 0.015 and height <= STEP_HEIGHT + 0.03:
			low_obstacle = true
	if not low_obstacle:
		return
	var raise_by := Vector3.UP * STEP_HEIGHT
	if body.test_move(body.global_transform, raise_by):
		return
	var raised := body.global_transform.translated(raise_by)
	if body.test_move(raised, motion):
		return
	var landing := KinematicCollision3D.new()
	if body.test_move(raised.translated(motion), Vector3.DOWN * (STEP_HEIGHT + 0.06), landing):
		if landing.get_normal().dot(Vector3.UP) > 0.1:
			body.global_position.y += STEP_HEIGHT

func _set_speed(value: float) -> void:
	speed_multiplier = value
	speed_label.text = "速度 ×%.1f  ·  %.1f 米/秒" % [value, value * WALK_SPEED]

func _capture_mouse(capture: bool) -> void:
	mouse_captured = capture
	if not capture:
		jump_buffer_left = 0.0
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if capture else Input.MOUSE_MODE_VISIBLE
	get_viewport().gui_release_focus()

func _set_flying(enabled: bool) -> void:
	flying = enabled
	velocity = Vector3.ZERO
	collision_layer = 0 if enabled else 2
	collision_mask = CampusDoors.CLOSED_BUILDING_LAYER if enabled else 1
	if not enabled:
		_refresh_collision()

func _reset_position() -> void:
	global_transform = spawn.global_transform
	camera.rotation.x = 0.0
	velocity = Vector3.ZERO
	jump_buffer_left = 0.0
	coyote_left = 0.0
	_refresh_collision()

func _refresh_collision() -> void:
	var world := get_parent()
	if world.is_node_ready() and world.has_method("refresh_collision"):
		world.call("refresh_collision")

