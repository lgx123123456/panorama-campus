extends Node3D
## Skinned school-uniform arms shared by empty-hand actions and firearms.

const Appearance = preload("res://scripts/campus/campus_arm_appearance.gd")
const REST_RIGHT := Vector3(0.24, -0.42, -0.28)
const REST_LEFT := Vector3(-0.24, -0.43, -0.27)
const ARM_BASIS := Basis(Vector3.RIGHT, -1.16)

var right_arm := Node3D.new()
var left_arm := Node3D.new()
var hand_attachment := Node3D.new()
var model: Node3D
var skeleton: Skeleton3D
var identity := 0
var action: StringName = &""
var action_time := 0.0
var action_length := 0.55
var phase := 0.0
var motion_speed := 0.0
var running := false
var grounded := true
var infected := false
var holding := false
var size_factor := 1.0

func _ready() -> void:
	name = "FirstPersonHands"
	hand_attachment.name = "HandAttachment"
	add_child(right_arm)
	add_child(left_arm)
	add_child(hand_attachment)
	var fill := OmniLight3D.new()
	fill.name = "HandFillLight"
	fill.position = Vector3(-0.15, 0.20, -0.15)
	fill.omni_range = 1.8
	fill.light_energy = 0.45
	fill.light_cull_mask = 1 << 19
	add_child(fill)
	set_appearance(identity, infected)

func set_appearance(index: int, is_infected: bool) -> void:
	identity = clampi(index, 0, Appearance.SCENES.size() - 1)
	infected = is_infected
	if is_instance_valid(model):
		remove_child(model)
		model.queue_free()
	model = Appearance.SCENES[identity].instantiate()
	add_child(model)
	skeleton = model.find_children("*", "Skeleton3D", true, false)[0]
	Appearance.prepare(model, infected)
	size_factor = 1.04 if identity == 2 else 1.0
	action = &""
	_pose(0.0)

func set_holding(enabled: bool) -> void:
	holding = enabled

func locomotion(speed: float, is_running: bool, is_grounded: bool) -> void:
	motion_speed = speed
	running = is_running
	grounded = is_grounded

func play_action(gesture: StringName) -> void:
	action = gesture
	action_time = 0.0
	action_length = 0.68 if gesture in [&"pick-up", &"pickup", &"grab"] else 0.50
	if gesture == &"throw":
		action_length = 0.62

func _process(delta: float) -> void:
	phase += delta * (10.5 if running else 7.0)
	if action != &"":
		action_time += delta
		if action_time >= action_length:
			action = &""
	_pose(delta)

func _pose(_delta: float) -> void:
	var amplitude := clampf(motion_speed / 3.2, 0.0, 1.5) * (0.014 if grounded else 0.003)
	var bob := Vector3(sin(phase) * amplitude, cos(phase * 2.0) * amplitude * 0.7, 0.0)
	var breathing := sin(Time.get_ticks_msec() * 0.0018) * 0.003
	right_arm.position = REST_RIGHT + bob + Vector3(0, breathing, 0)
	left_arm.position = REST_LEFT + Vector3(-bob.x, -bob.y, 0) + Vector3(0, breathing, 0)
	right_arm.basis = ARM_BASIS.rotated(Vector3.FORWARD, -0.12).scaled(Vector3.ONE * size_factor)
	left_arm.basis = ARM_BASIS.rotated(Vector3.FORWARD, 0.12).scaled(Vector3.ONE * size_factor)
	if infected:
		right_arm.position += Vector3(0, 0, -0.035)
		left_arm.position += Vector3(0, 0, -0.035)
	if holding:
		right_arm.position += Vector3(0, 0.07, -0.10)
		left_arm.position += Vector3(0, 0.025, 0)
	if action != &"":
		var progress := clampf(action_time / action_length, 0.0, 1.0)
		var reach := sin(progress * PI)
		right_arm.position.y += 0.15 * reach
		left_arm.position.y += 0.15 * reach
		match action:
			&"throw":
				var windup := sin(clampf(progress / 0.35, 0.0, 1.0) * PI)
				right_arm.position += Vector3(-0.045 * reach, 0.15 * reach, -0.28 * reach + 0.15 * windup)
				right_arm.basis = right_arm.basis.rotated(Vector3.RIGHT, -0.65 * reach + 0.8 * windup)
			&"pick-up", &"pickup":
				right_arm.position += Vector3(-0.12 * reach, -0.05 * reach, -0.23 * reach)
				left_arm.position += Vector3(0.075 * reach, 0.035 * reach, -0.10 * reach)
			&"grab":
				right_arm.position += Vector3(-0.075 * reach, 0.18 * reach, -0.17 * reach)
				left_arm.position += Vector3(0.075 * reach, 0.18 * reach, -0.17 * reach)
				right_arm.basis = right_arm.basis.rotated(Vector3.FORWARD, -0.45 * reach)
				left_arm.basis = left_arm.basis.rotated(Vector3.FORWARD, 0.45 * reach)
			&"hit", &"attack-melee-right":
				right_arm.position += Vector3(-0.13 * reach, 0.09 * reach, -0.32 * reach)
				left_arm.position += Vector3(0.025 * reach, 0.045 * reach, 0.035 * reach)
				right_arm.basis = right_arm.basis.rotated(Vector3.UP, -0.42 * reach)
			_:
				right_arm.position += Vector3(-0.11 * reach, 0.09 * reach, -0.23 * reach)
				right_arm.basis = right_arm.basis.rotated(Vector3.UP, -0.25 * reach)
	hand_attachment.position = right_arm.position + right_arm.basis * Vector3(0.0, 0.34, -0.018)
	hand_attachment.rotation = Vector3.ZERO

	var curl := 0.20 if infected else 0.12
	if holding:
		curl = 0.95
	if action in [&"hit", &"attack-melee-right"]:
		curl = 1.35
	elif action in [&"grab", &"pick-up", &"pickup"]:
		curl = 0.15 + sin(clampf(action_time / action_length, 0.0, 1.0) * PI) * 0.7
	_pose_skeleton(right_arm, "R", 1.0, curl)
	_pose_skeleton(left_arm, "L", -1.0, curl)

func _pose_skeleton(arm: Node3D, suffix: String, side: float, curl: float) -> void:
	if skeleton == null:
		return
	var rotation_basis := arm.basis.orthonormalized()
	var along := rotation_basis.y * side
	var thumb := -rotation_basis.x * side
	var swing := Basis(along, thumb, along.cross(thumb)).orthonormalized()
	var wrist := arm.position + arm.basis * Vector3(0, 0.235, 0)
	var elbow := wrist - rotation_basis.y * 0.303
	var shoulder := elbow - rotation_basis.y * 0.323
	_set_bone("upper_arm." + suffix, shoulder, swing)
	_set_bone("lower_arm." + suffix, elbow, swing)
	_set_bone("hand." + suffix, wrist, swing)
	for digit in ["index", "middle", "ring", "pink", "thumb"]:
		for segment in [1, 2]:
			var bone := skeleton.find_bone("%s%d.%s" % [digit, segment, suffix])
			var rest := skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
			var bend := curl * (0.65 if digit == "thumb" else 1.0)
			skeleton.set_bone_pose_rotation(bone, rest * Quaternion(Vector3.RIGHT, -bend))

func _set_bone(bone_name: String, origin: Vector3, swing: Basis) -> void:
	var bone := skeleton.find_bone(bone_name)
	var rest := skeleton.get_bone_global_rest(bone)
	skeleton.set_bone_global_pose(bone, Transform3D(swing * rest.basis, origin))
