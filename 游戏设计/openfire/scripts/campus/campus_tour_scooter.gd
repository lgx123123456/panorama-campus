extends CharacterBody3D

const MAX_SPEED := 10.5
const REVERSE_SPEED := 2.8
const WHEEL_RADIUS := 0.243
const ROLL_CLIP := &"wheel-roll"
const STEP_HEIGHT := 0.38
const WALL_SPEED := 5.4
const WALL_SIDE_SPEED := 2.6
const WALL_OFFSET := 0.14
const EXIT_INSET := 1.05
const FLOOR_NORMAL_Y := 0.70

var drive_speed := 0.0
var wheel_distance := 0.0
var parked_transform: Transform3D
var climb_enabled := false
var wall_normal := Vector3.ZERO

@onready var chassis: Node3D = $Chassis
@onready var wheel_motion: AnimationPlayer = $Chassis/Model.find_child("AnimationPlayer", true, false)
@onready var collision: CollisionShape3D = $CollisionShape3D


func _ready() -> void:
	parked_transform = global_transform
	wheel_motion.play(ROLL_CLIP)
	wheel_motion.pause()


func reset_to_gate() -> void:
	climb_enabled = false
	wall_normal = Vector3.ZERO
	global_transform = parked_transform
	stop()
	wheel_distance = 0.0
	wheel_motion.seek(0.0, true)


func stop() -> void:
	drive_speed = 0.0
	velocity = Vector3.ZERO
	chassis.rotation.z = 0.0


func drive(delta: float, throttle: float, steering: float, brake: bool) -> void:
	if is_climbing():
		_drive_wall(delta, throttle, steering, brake)
		return
	var target := throttle * (MAX_SPEED if throttle >= 0 else REVERSE_SPEED)
	var slowing := not is_zero_approx(drive_speed) and target * drive_speed <= 0.0
	if brake or (slowing and not is_zero_approx(throttle)):
		target = 0.0
	var rate := 12.0 if brake or slowing else 4.6
	drive_speed = move_toward(drive_speed, target, rate * delta)

	var speed_fraction := absf(drive_speed) / MAX_SPEED
	if absf(drive_speed) > 0.12:
		var turn_rate := lerpf(2.10, 0.95, speed_fraction) * minf(absf(drive_speed), 1.0)
		var old_yaw := rotation.y
		rotate_y(-steering * signf(drive_speed) * turn_rate * delta)
		if _turn_overlaps_wall():
			rotation.y = old_yaw

	# The turn/speed lean follows Kenney's MIT Starter Kit Racing motorcycle.
	var tilt := steering * speed_fraction * 0.32 * signf(drive_speed)
	chassis.rotation.z = lerpf(chassis.rotation.z, tilt, 1.0 - exp(-7.0 * delta))
	var forward := -global_basis.z
	var before := global_position
	var on_floor := is_on_floor() or test_move(global_transform, Vector3.DOWN * 0.08)
	velocity.x = forward.x * drive_speed
	velocity.z = forward.z * drive_speed
	velocity.y = -0.5 if on_floor else velocity.y - get_gravity().length() * delta
	move_and_slide()
	var distance := (global_position - before).dot(forward)
	if is_on_wall() and absf(distance) < absf(drive_speed) * delta * 0.55:
		var motion := forward * (drive_speed * delta - distance)
		if on_floor and _try_step(motion):
			distance = (global_position - before).dot(forward)
		elif climb_enabled and on_floor and throttle > 0.0 and _try_attach(forward):
			return
		else:
			drive_speed = 0.0
	_spin_wheels(distance)


func _turn_overlaps_wall() -> bool:
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = collision.shape
	query.transform = collision.global_transform.translated(Vector3.UP * 0.08)
	query.collision_mask = collision_mask
	query.exclude = [get_rid()]
	return not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func toggle_climbing() -> bool:
	if is_climbing():
		return false
	climb_enabled = not climb_enabled
	return true


func is_climbing() -> bool:
	return wall_normal != Vector3.ZERO


func _try_step(motion: Vector3) -> bool:
	var lift := Vector3.UP * (STEP_HEIGHT + 0.04)
	if test_move(global_transform, lift):
		return false
	var raised := global_transform.translated(lift)
	var advance := motion.normalized() * maxf(motion.length() + 0.015, 0.055)
	if test_move(raised, advance):
		return false
	var over_step := raised.translated(advance)
	var landing := KinematicCollision3D.new()
	if not test_move(over_step, Vector3.DOWN * lift.y, landing) or landing.get_normal().y < FLOOR_NORMAL_Y:
		return false
	var step := lift.y + landing.get_travel().y
	if step <= 0.003 or step > STEP_HEIGHT:
		return false
	global_position = over_step.origin + landing.get_travel()
	velocity.y = -0.5
	apply_floor_snap()
	return true


func _try_attach(forward: Vector3) -> bool:
	var origin := global_position + Vector3.UP * 1.14
	var hit := _ray(origin, origin + forward * 1.27)
	if hit.is_empty():
		return false
	var normal: Vector3 = hit.normal
	if absf(normal.y) > 0.27 or forward.dot(-normal) < 0.58:
		return false
	var point: Vector3 = hit.position
	var pose := _wall_pose(point, normal)
	if not _clear(pose):
		return false
	wall_normal = normal
	global_transform = pose
	stop()
	return true


func _drive_wall(delta: float, throttle: float, steering: float, brake: bool) -> void:
	drive_speed = move_toward(drive_speed, throttle * WALL_SPEED if not brake else 0.0, 18.0 * delta)
	var forward := -global_basis.z
	var motion := (forward * drive_speed + global_basis.x * steering * WALL_SIDE_SPEED * float(not brake)) * delta
	if motion.is_zero_approx():
		return
	var next := global_position + motion
	# The rear wheel can still have support while the front wheel clears the roof edge.
	var hit := _wall_support(next)
	if hit.is_empty():
		if drive_speed > 0.0 and _try_land(-wall_normal, true):
			return
		var rear_hit := _wall_support(next - forward * 0.70)
		if not rear_hit.is_empty():
			var rear: Vector3 = rear_hit.position
			hit = {"position": rear + forward * 0.70, "normal": rear_hit.normal}
	if drive_speed < 0.0 and _try_land(wall_normal, false):
		return
	if hit.is_empty():
		drive_speed = 0.0
		return
	var point: Vector3 = hit.position
	var normal: Vector3 = hit.normal
	var pose := _wall_pose(point, normal)
	pose.origin += normal * _wall_clearance(pose, point, normal)
	var distance := _advance_wall_pose(pose, normal, forward)
	if is_zero_approx(distance) and absf(steering) < 0.05:
		if drive_speed > 0.0 and _try_land(-wall_normal, true):
			return
		drive_speed = 0.0
	_spin_wheels(distance)


func _advance_wall_pose(contact_pose: Transform3D, normal: Vector3, forward: Vector3) -> float:
	# Window sills and eaves can hit the nose before the wall's center ray sees them.
	# Find a clear out-and-up path and move outward first if needed.
	for push_out: float in [0.0, 0.17, 0.35, 0.58, 0.84, 1.12, 1.42]:
		var pose := contact_pose.translated(normal * push_out)
		var displacement := pose.origin - global_position
		var outward := normal * maxf(0.0, displacement.dot(normal))
		var offset_pose := global_transform.translated(outward)
		if not _clear(pose):
			continue
		if not outward.is_zero_approx() and test_move(global_transform, outward):
			return 0.0
		if test_move(offset_pose, displacement - outward):
			continue
		if outward.length() > 0.17:
			global_position += outward.limit_length(0.17)
			return 0.0
		global_transform = pose
		wall_normal = normal
		return displacement.dot(forward)
	return 0.0


func _wall_support(at: Vector3) -> Dictionary:
	var hit := _ray(at + wall_normal * 0.95, at - wall_normal * 2.05)
	if hit.is_empty() or wall_normal.dot(hit.normal) < 0.87:
		return {}
	return hit


func _wall_clearance(pose: Transform3D, contact: Vector3, normal: Vector3) -> float:
	var clearance := 0.0
	# The bike's nose and tail can reach protrusions before its center does.
	for length: float in [-0.92, 0.0, 0.97]:
		for width: float in [-0.28, 0.0, 0.28]:
			var sample := pose.origin - pose.basis.z * length + pose.basis.x * width
			var hit := _wall_support(sample)
			if not hit.is_empty():
				var point: Vector3 = hit.position
				clearance = maxf(clearance, (point - contact).dot(normal))
	return clearance


func _wall_pose(contact: Vector3, normal: Vector3) -> Transform3D:
	var uphill := Vector3.UP.slide(normal).normalized()
	return Transform3D(Basis.looking_at(uphill, normal), contact + normal * WALL_OFFSET)


func _try_land(direction: Vector3, roof: bool) -> bool:
	var across := direction.slide(Vector3.UP).normalized()
	var insets := [EXIT_INSET, 1.35, 1.70, 2.05] if roof else [EXIT_INSET]
	for inset: float in insets:
		if _try_landing_at(across, inset, roof):
			return true
	return false


func _try_landing_at(across: Vector3, inset: float, roof: bool) -> bool:
	var landing_center := global_position + across * inset
	var floor_hit := _ray(landing_center + Vector3.UP * 0.25,
		landing_center - Vector3.UP * 1.34)
	if floor_hit.is_empty() or Vector3(floor_hit.normal).y < FLOOR_NORMAL_Y:
		return false
	var point: Vector3 = floor_hit.position
	var drop := global_position.y - point.y
	if (roof and drop < 0.51) or (not roof and drop < 0.82):
		return false
	var edge_height := Vector3.UP * 0.12
	if roof and not _ray(global_position + edge_height, landing_center + edge_height).is_empty():
		return false
	var heading := across if roof else -across
	var pose := Transform3D(Basis.looking_at(heading, Vector3.UP), point + Vector3.UP * 0.055)
	if not _clear(pose):
		return false
	# Both wheel positions must have support before transferring onto a landing.
	for offset: float in [-0.65, 0.65]:
		var wheel := pose.origin + heading * offset
		var wheel_hit := _ray(wheel + Vector3.UP * 0.12, wheel - Vector3.UP * 0.26)
		if wheel_hit.is_empty() or Vector3(wheel_hit.normal).y < FLOOR_NORMAL_Y:
			return false
	wall_normal = Vector3.ZERO
	global_transform = pose
	velocity = Vector3.ZERO
	return true


func _ray(from: Vector3, to: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(from, to, collision_mask, [get_rid()])
	return get_world_3d().direct_space_state.intersect_ray(query)


func _clear(pose: Transform3D) -> bool:
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = collision.shape
	query.transform = pose * collision.transform
	query.collision_mask = collision_mask
	query.exclude = [get_rid()]
	return get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func _spin_wheels(distance: float) -> void:
	wheel_distance += distance
	var cycle := fposmod(wheel_distance / (TAU * WHEEL_RADIUS), 1.0)
	wheel_motion.seek(cycle * wheel_motion.get_animation(ROLL_CLIP).length, true)
