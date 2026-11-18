extends "res://scripts/campus/campus_walker.gd"

const Look = preload("res://scripts/campus/campus_character_look.gd")
const Actor = preload("res://scripts/campus/campus_character_actor.gd")
const FirstPersonHands = preload("res://scripts/campus/campus_first_person_hands.gd")
const HUMAN := 0
const INFECTED := 1
const KING := 2
const CROUCH_HEIGHT := 1.20

signal footstep(at: Vector3, strength: float)

var look: Look
var role := HUMAN
var identity := 0
var quiet := false
var crouched := false
var capsule: CapsuleShape3D
var standing_height := 1.73
var standing_eye := 1.59
var step_time := 0.0
var stagger_remaining := 0.0
var movement_locked := false
var grab_jump_consumed := false
var hands: FirstPersonHands
var hand_attachment: Node3D
var firearm: Node3D
var human_sprint_speed_override := 0.0
var stair_speed_multiplier := 1.24
var stair_support_left := 0.0
var stair_frame_origin := Vector3.ZERO
var stair_stepped_this_frame := false

@onready var collider: CollisionShape3D = $Capsule
@onready var follow_arm: SpringArm3D = $Camera3D/FollowArm
@onready var follow_camera: Camera3D = $Camera3D/FollowArm/ThirdPerson
@onready var trial: Node = $"../CharacterTrial"

func _ready() -> void:
	allow_jump = true
	super._ready()
	collision_mask |= Actor.ACTOR_LAYER
	capsule = collider.shape.duplicate()
	collider.shape = capsule
	follow_arm.add_excluded_object(get_rid())
	# SpringArm3D extends along +Z, behind the -Z-facing walker.
	follow_arm.rotation = Vector3.ZERO
	follow_arm.position = Vector3(0.32, -0.12, 0.0)
	follow_camera.rotation = Vector3.ZERO
	follow_camera.fov = camera.fov
	look = Look.new()
	add_child(look)
	look.hide()
	hands = FirstPersonHands.new()
	camera.add_child(hands)
	hand_attachment = hands.hand_attachment
	hands.set_appearance(identity, role != HUMAN)
	_capture_mouse(false)

func set_role(index: int, form: int) -> void:
	identity = index
	role = form
	quiet = false
	look.cancel_gesture()
	look.set_appearance(index, form != HUMAN)
	hands.set_appearance(index, form != HUMAN)
	standing_height = Look.HEIGHTS[index]
	standing_eye = standing_height - 0.14
	_update_stance(0.0)

func _movement_speed() -> float:
	if movement_locked or stagger_remaining > 0.0 or _is_grabbed():
		return 0.0
	if role == INFECTED:
		return 2.8 if Input.is_action_pressed("sprint") else 1.35
	if role == KING:
		return 4.1 if Input.is_action_pressed("sprint") else 2.75
	var load_scale := 1.15
	if is_instance_valid(firearm):
		load_scale = firearm.movement_speed_scale()
	if crouched:
		return 1.45 * load_scale
	if quiet:
		return 1.65 * load_scale
	if is_instance_valid(firearm) and firearm.aiming:
		return WALK_SPEED * 0.65 * load_scale
	var sprinting := Input.is_action_pressed("sprint")
	var speed := base_human_sprint_speed() if sprinting else WALK_SPEED
	if sprinting and human_sprint_speed_override > 0.0:
		speed = human_sprint_speed_override
	speed *= load_scale
	if not flying and trial.has_method("is_ascending_stair"):
		var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
		var direction := global_basis * Vector3(input.x, 0, input.y)
		if trial.is_ascending_stair(global_position, direction):
			speed *= stair_speed_multiplier
	return speed

func base_human_sprint_speed() -> float:
	return 6.35 if identity == 2 else RUN_SPEED

func _is_grabbed() -> bool:
	return bool(get_meta(&"campus_grabbed", false)) or (trial.has_method("is_player_grabbed") and trial.is_player_grabbed())

func _can_jump() -> bool:
	return super._can_jump() and not crouched and not movement_locked and stagger_remaining <= 0.0 and not _is_grabbed() and not grab_jump_consumed

func play_hand_action(action: StringName) -> void:
	hands.play_action(action)
	if is_instance_valid(firearm):
		firearm.interrupt_action()

func _physics_process(delta: float) -> void:
	stair_support_left = 0.20 if is_on_floor() else maxf(0.0, stair_support_left - delta)
	if not Input.is_action_pressed("jump"):
		grab_jump_consumed = false
	stagger_remaining = maxf(0.0, stagger_remaining - delta)
	_update_stance(delta)
	stair_frame_origin = global_position
	stair_stepped_this_frame = false
	super._physics_process(delta)
	# Capsule contacts at a tread's edge briefly count as walls. Continue the
	# checked step sweep while supported, even when that contact lost floor state.
	if mouse_captured and not flying and not stair_stepped_this_frame and velocity.y <= 0.0 and is_on_wall() and stair_support_left > 0.0:
		var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
		_step_up(global_basis * Vector3(input.x, 0, input.y) * _movement_speed() * delta)
	var motion := get_real_velocity()
	var speed := Vector2(motion.x, motion.z).length()
	var running: bool = Input.is_action_pressed("sprint") and not crouched and not quiet \
		and (not is_instance_valid(firearm) or not firearm.aiming)
	look.locomotion(speed, running)
	hands.visible = camera.current and (not is_instance_valid(firearm) or not firearm.is_presented())
	hands.locomotion(speed, running, is_on_floor())
	_update_footsteps(delta, speed, running)

func _step_up(motion: Vector3) -> void:
	if motion.length_squared() < 0.0000000001:
		return
	var direction := motion.normalized()
	var moved := (global_position - stair_frame_origin).dot(direction)
	motion = direction * maxf(0.0, motion.length() - maxf(0.0, moved))
	if motion.length_squared() < 0.0000000001:
		return
	var raise_by := Vector3.UP * (STEP_HEIGHT + safe_margin * 2.0)
	if test_move(global_transform, raise_by):
		return
	var raised := global_transform.translated(raise_by)
	if test_move(raised, motion):
		return
	var landing := KinematicCollision3D.new()
	if not test_move(raised.translated(motion), -raise_by - Vector3.UP * 0.06, landing):
		return
	if landing.get_normal().dot(Vector3.UP) <= 0.1:
		return
	var rise := raise_by.y + landing.get_travel().y
	if rise <= 0.00001 or rise > STEP_HEIGHT + safe_margin * 3.0:
		return
	# Commit the swept displacement and its actual supported height. Merely
	# lifting by a whole riser let floor snapping undo slow, short frame motions.
	global_position += motion + Vector3.UP * rise
	velocity.y = 0.0
	stair_support_left = 0.20
	stair_stepped_this_frame = true
	step_retry_time = 0.0

func _update_footsteps(delta: float, speed: float, running: bool) -> void:
	if quiet or not is_on_floor() or speed < 0.40:
		step_time = 0.0
		return
	step_time -= delta
	if step_time <= 0.0:
		step_time = 0.30 if running else (0.68 if crouched else 0.46)
		footstep.emit(global_position, 1.75 if running else 1.0)
		var volume := -8.0 if running else (-22.0 if crouched else -15.0)
		Audio.play_3d("res://assets/audio/footstep_%d.ogg" % randi_range(1, 4), global_position, volume, 0.08, 18.0)

func _update_stance(delta: float) -> void:
	var wants_crouch := role == HUMAN and mouse_captured and Input.is_action_pressed("crouch")
	var target_height := CROUCH_HEIGHT if wants_crouch else standing_height
	var height := move_toward(capsule.height, target_height, 5.5 * delta) if delta > 0.0 else target_height
	if height > capsule.height + 0.001 and test_move(global_transform, Vector3.UP * (height - capsule.height)):
		return
	crouched = wants_crouch or height < standing_height - 0.02
	capsule.height = height
	collider.position.y = height / 2.0
	var eye := minf(standing_eye, height - 0.14)
	camera.position.y = lerpf(camera.position.y, eye, 1.0 - exp(-20.0 * delta)) if delta > 0.0 else eye
	look.set_crouched(crouched)

func _input(event: InputEvent) -> void:
	if mouse_captured and role == KING and event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_LEFT and trial.has_method("king_bite"):
		trial.king_bite()
		get_viewport().set_input_as_handled()
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var key: Key = event.physical_keycode
		if key == KEY_SPACE and mouse_captured and _is_grabbed():
			grab_jump_consumed = true
			if trial.has_method("struggle_grab"):
				trial.struggle_grab()
			get_viewport().set_input_as_handled()
			return
		if key == KEY_F:
			return
		if mouse_captured and key in [KEY_E, KEY_Q, KEY_G, KEY_C, KEY_V, KEY_L]:
			match key:
				KEY_E:
					if role == HUMAN and trial.get("campaign") != null and trial.campaign.interact():
						get_viewport().set_input_as_handled()
						return
					if role == HUMAN and not trial.interact_book():
						get_parent().get_node("Doors").interact()
						# A brief first-person reach keeps the camera and door interaction aligned.
						play_hand_action(&"interact-right")
				KEY_Q:
					if role == HUMAN:
						trial.throw_book()
				KEY_G:
					trial.use_ability()
				KEY_C:
					if role == HUMAN:
						quiet = not quiet
				KEY_L:
					if role == HUMAN and trial.has_method("lock_door"):
						trial.lock_door()
				KEY_V:
					_toggle_camera()
			get_viewport().set_input_as_handled()
			return
	super._input(event)

func _toggle_camera() -> void:
	var third_person := not follow_camera.current
	follow_camera.current = third_person
	camera.current = not third_person
	look.visible = third_person
	hands.visible = not third_person
	if is_instance_valid(firearm):
		firearm.refresh_visibility()
