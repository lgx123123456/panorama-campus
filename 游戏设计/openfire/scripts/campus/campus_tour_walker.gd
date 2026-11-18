extends "res://scripts/campus/campus_walker.gd"

const Scooter = preload("res://scripts/campus/campus_tour_scooter.gd")
const Look = preload("res://scripts/campus/campus_character_look.gd")
const SCENE := "res://scenes/campus/free_tour.tscn"
const MAP_REVISION := "C1"
const WORLD_MASK := 1 | CampusDoors.CLOSED_BUILDING_LAYER
const MAX_FLIGHT_HEIGHT := 90.0

enum Mode { WALK, JETPACK, SCOOTER }

var mode := Mode.WALK
var prefer_third_person := true
var interact_requested := false
var photo_requested := false
var steer_camera_delay := 0.0
var riding_pose_y := 0.0
var riding_ik: TwoBoneIK3D

@onready var ui = $"../TourInterface"
@onready var scooter: Scooter = $"../Scooter"
@onready var follow_arm: SpringArm3D = $Camera3D/FollowArm
@onready var follow_camera: Camera3D = $Camera3D/FollowArm/FollowCamera
@onready var capsule: CollisionShape3D = $Capsule
@onready var look: Look = $Look
@onready var jetpack: Node3D = $Look/Jetpack


func _ready() -> void:
	super._ready()
	collision_mask = WORLD_MASK
	$"../Interface".hide()
	follow_arm.add_excluded_object(get_rid())
	follow_arm.add_excluded_object(scooter.get_rid())
	follow_camera.fov = camera.fov
	_set_view()
	print("Campus free tour ready: main gate, map ", MAP_REVISION)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	var key: Key = event.physical_keycode
	if ui.modal_visible():
		if key == KEY_ESCAPE or key == KEY_P:
			ui.close_modal()
		else:
			return
	elif key == KEY_ESCAPE:
		ui.open_pause()
	elif key == KEY_P:
		request_photo()
	elif key == KEY_TAB:
		_capture_mouse(not mouse_captured)
	elif not mouse_captured:
		return
	elif key == KEY_E:
		interact_requested = true
	elif key == KEY_F and mode != Mode.SCOOTER:
		_set_jetpack(mode != Mode.JETPACK)
	elif key == KEY_G and mode == Mode.SCOOTER:
		if not scooter.toggle_climbing():
			ui.notify("到达楼顶或倒回地面后，可关闭攀墙")
	elif key == KEY_V:
		prefer_third_person = not prefer_third_person
		_set_view()
	elif key == KEY_R:
		_return_to_gate()
	else:
		return
	get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if ui.modal_visible():
		return
	if event is InputEventMouseMotion and mouse_captured:
		steer_camera_delay = 1.6
		super._unhandled_input(event)
	elif event is InputEventMouseButton:
		super._unhandled_input(event)


func _physics_process(delta: float) -> void:
	if ui.modal_visible():
		return
	if photo_requested:
		photo_requested = false
		interact_requested = false
		ui.open_photo(make_photo_location())
		return
	if interact_requested:
		interact_requested = false
		_interact()
	match mode:
		Mode.WALK:
			super._physics_process(delta)
		Mode.JETPACK:
			_fly_jetpack(delta)
		Mode.SCOOTER:
			_ride_scooter(delta)
	if global_position.y < -2.0:
		_return_to_gate()
	_update_character(delta)
	ui.update_controls(mode, _can_mount(), scooter.climb_enabled, scooter.is_climbing())


func _movement_speed() -> float:
	return RUN_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED


func _interact() -> void:
	if mode == Mode.SCOOTER:
		_dismount()
	elif _can_mount():
		_mount()
	else:
		get_parent().get_node("Doors").interact()


func _can_mount() -> bool:
	if mode != Mode.WALK or not is_on_floor() or global_position.distance_squared_to(scooter.global_position) > 2.25 * 2.25:
		return false
	var to_scooter := scooter.global_position + Vector3.UP * 0.66 - camera.global_position
	var eye_forward := -camera.global_basis.z
	return eye_forward.dot(to_scooter.normalized()) > 0.15 and _ray(camera.global_position, camera.global_position + to_scooter).is_empty()


func _mount() -> void:
	mode = Mode.SCOOTER
	collision_layer = 0
	collision_mask = 0
	velocity = Vector3.ZERO
	rotation.y = scooter.rotation.y
	camera.rotation.x = -0.10
	steer_camera_delay = 0.0
	look.set_crouched(true)
	look.locomotion(0.0)
	look.animation.advance(0.0)
	var hip_bone := look.skeleton.find_bone("Body")
	var hip := look.skeleton.get_bone_global_pose(hip_bone).origin
	var hip_height := look.to_local(look.skeleton.to_global(hip)).y
	riding_pose_y = 0.89 - hip_height
	_sync_rider()
	if riding_ik == null:
		_setup_riding_pose()
	riding_ik.active = true
	_set_view()


func _setup_riding_pose() -> void:
	riding_ik = TwoBoneIK3D.new()
	riding_ik.setting_count = 4
	look.skeleton.add_child(riding_ik)
	for side in 2:
		var suffix := ".R" if side == 0 else ".L"
		var direction := 1.0 if side == 0 else -1.0
		_set_riding_chain(side, ["UpperArm", "LowerArm", "Hand"], suffix,
			Vector3(direction * 0.24, 1.02, -0.43), Vector3(direction * 0.44, 0.67, 0.13))
		_set_riding_chain(side + 2, ["UpperLeg", "LowerLeg", "Foot"], suffix,
			Vector3(direction * 0.13, 0.26, -0.07), Vector3(direction * 0.31, 0.58, -0.72))


func _set_riding_chain(index: int, bones: Array[String], suffix: String, target: Vector3, pole: Vector3) -> void:
	riding_ik.set_root_bone_name(index, bones[0] + suffix)
	riding_ik.set_middle_bone_name(index, bones[1] + suffix)
	riding_ik.set_end_bone_name(index, bones[2] + suffix)
	var grip := Marker3D.new()
	var bend := Marker3D.new()
	scooter.chassis.add_child(grip)
	scooter.chassis.add_child(bend)
	grip.position = target
	bend.position = pole
	riding_ik.set_target_node(index, riding_ik.get_path_to(grip))
	riding_ik.set_pole_node(index, riding_ik.get_path_to(bend))


func _dismount() -> void:
	if scooter.is_climbing():
		ui.notify("到达楼顶或倒回地面后，可下车")
		return
	var right := scooter.global_basis.x
	var back := scooter.global_basis.z
	for offset: Vector3 in [right, -right, right + back * 0.55, -right + back * 0.55, back * 1.47]:
		var side := scooter.global_position + offset
		var origin := scooter.global_position + Vector3.UP * 0.70
		if not _ray(origin, side + Vector3.UP * 0.70).is_empty():
			continue
		var floor_hit := _ray(side + Vector3.UP * 0.65, side + Vector3.DOWN * 0.65)
		if floor_hit.is_empty() or Vector3(floor_hit.normal).y < 0.6:
			continue
		var feet: Vector3 = floor_hit.position + Vector3.UP * 0.035
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = capsule.shape
		query.transform.origin = feet + capsule.position
		query.collision_mask = WORLD_MASK
		query.exclude = [get_rid()]
		if not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty():
			continue
		scooter.stop()
		_leave_transport()
		global_position = feet
		_refresh_collision()
		return
	ui.notify("旁边空间不足，请移动电动车后再下车")


func _ride_scooter(delta: float) -> void:
	var throttle := 0.0
	var steering := 0.0
	if mouse_captured:
		throttle = Input.get_axis("move_back", "move_forward")
		steering = Input.get_axis("move_left", "move_right")
	scooter.drive(delta, throttle, steering, not mouse_captured or Input.is_action_pressed("jump"))
	steer_camera_delay = maxf(0.0, steer_camera_delay - delta)
	if steer_camera_delay == 0.0:
		var blend := 1.0 - exp(-4.0 * delta)
		if scooter.is_climbing():
			var normal := scooter.wall_normal
			var yaw := atan2(normal.x, normal.z)
			rotation.y = lerp_angle(rotation.y, yaw, blend)
			camera.rotation.x = lerpf(camera.rotation.x, 0.49, blend)
		elif absf(scooter.drive_speed) > 0.8:
			rotation.y = lerp_angle(rotation.y, scooter.rotation.y, blend)
			camera.rotation.x = lerpf(camera.rotation.x, -0.08, blend)
	_sync_rider()


func _sync_rider() -> void:
	global_position = scooter.global_position
	look.global_transform = scooter.chassis.global_transform.translated_local(Vector3(0, riding_pose_y, 0.18))


func _set_jetpack(active: bool) -> void:
	if not active:
		_leave_transport()
		return
	mode = Mode.JETPACK
	jump_buffer_left = 0.0
	velocity.y = maxf(0.0, velocity.y)
	_set_view()


func _fly_jetpack(delta: float) -> void:
	var input := Vector2.ZERO
	var climb := 0.0
	if mouse_captured:
		input = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
		climb = Input.get_axis("crouch", "jump")
	var boost := mouse_captured and Input.is_action_pressed("sprint")
	var target := global_basis * Vector3(input.x, 0, input.y) * (15.0 if boost else 9.0)
	target.y = minf(climb * (8.0 if boost else 6.0), (MAX_FLIGHT_HEIGHT - global_position.y) / delta)
	var lateral := Vector2(velocity.x, velocity.z).move_toward(Vector2(target.x, target.z), 23.0 * delta)
	velocity = Vector3(lateral.x, move_toward(velocity.y, target.y, 44.0 * delta), lateral.y)
	if global_position.y + maxf(0.0, velocity.y) * delta > MAX_FLIGHT_HEIGHT:
		velocity.y = minf(velocity.y, (MAX_FLIGHT_HEIGHT - global_position.y) / delta)
	move_and_slide()
	var thrust := not is_on_floor() or climb > 0.0
	for exhaust: CPUParticles3D in [$Look/Jetpack/ExhaustLeft, $Look/Jetpack/ExhaustRight]:
		exhaust.emitting = thrust


func _leave_transport() -> void:
	mode = Mode.WALK
	if riding_ik != null:
		riding_ik.active = false
	collision_layer = 2
	collision_mask = WORLD_MASK
	velocity = Vector3.ZERO
	jump_buffer_left = 0.0
	coyote_left = 0.0
	look.position = Vector3.ZERO
	look.rotation = Vector3.ZERO
	look.set_crouched(false)
	look.locomotion(0.0)
	for exhaust: CPUParticles3D in [$Look/Jetpack/ExhaustLeft, $Look/Jetpack/ExhaustRight]:
		exhaust.emitting = false
	_set_view()


func _return_to_gate() -> void:
	_leave_transport()
	scooter.reset_to_gate()
	_reset_position()


func _set_view() -> void:
	var follow := prefer_third_person or mode != Mode.WALK
	if follow:
		follow_camera.make_current()
	else:
		camera.make_current()
	look.visible = follow
	jetpack.visible = mode == Mode.JETPACK


func _update_character(delta: float) -> void:
	if mode == Mode.SCOOTER:
		return
	var travel := get_real_velocity()
	travel.y = 0.0
	if mode == Mode.JETPACK:
		look.rotation.y = lerp_angle(look.rotation.y, 0.0, 1.0 - exp(-9.0 * delta))
		look.rotation.x = lerpf(look.rotation.x, minf(travel.length() * 0.024, 0.31), 1.0 - exp(-7.0 * delta))
		look.locomotion(0.0)
		return
	look.rotation.x = 0.0
	if travel.length_squared() > 0.04:
		var local_direction := global_basis.inverse() * travel
		var yaw := atan2(-local_direction.x, -local_direction.z)
		look.rotation.y = lerp_angle(look.rotation.y, yaw, 1.0 - exp(-15.0 * delta))
	look.locomotion(travel.length(), Input.is_action_pressed("sprint"))


func request_photo() -> void:
	photo_requested = true


func make_photo_location() -> Dictionary:
	var view := get_viewport().get_camera_3d()
	var forward := -view.global_basis.z
	var hit := _ray(view.global_position, view.global_position + forward * 48.0)
	var point: Vector3 = hit.get("position", global_position)
	var heading := posmod(roundi(rad_to_deg(atan2(forward.x, -forward.z))), 360)
	var code := "%s/%d/%d/%d/%03d" % [MAP_REVISION, roundi(point.x), roundi(point.y), roundi(point.z), heading]
	return {"point": point, "player": global_position, "heading": heading, "aim_hit": not hit.is_empty(), "code": code}


func _ray(from: Vector3, to: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(from, to, WORLD_MASK, [get_rid(), scooter.get_rid()])
	return get_world_3d().direct_space_state.intersect_ray(query)
