extends CharacterBody3D

const Look = preload("res://scripts/campus/campus_character_look.gd")
const ACTOR_LAYER := 32
const CampusWalker = preload("res://scripts/campus/campus_walker.gd")
const STATIONARY_FLOOR_CHECK_INTERVAL := 0.3

var appearance_identity := 0
var appearance_infected := false
var appearance_scene: PackedScene
var appearance_library: AnimationLibrary
var look: Look
var home: Vector3
var destination: Vector3
var move_speed := 0.0
var running := false
var stun_remaining := 0.0
var bite_count := 0
var blocked_time := 0.0
var terrain_steps := false
var step_retry := 0.0
var route := PackedVector3Array()
var route_speed := 0.0
var route_index := 0
var skip_stationary_collision := false
var _stationary_floor := Vector3.INF
var _stationary_floor_check := 0.0

func _ready() -> void:
	home = position
	collision_layer = ACTOR_LAYER
	collision_mask = 1 | 2 | ACTOR_LAYER
	floor_snap_length = 0.25
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.27
	capsule.height = 1.73
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	collision.position.y = capsule.height / 2.0
	add_child(collision)
	look = Look.new()
	look.identity = appearance_identity
	look.infected = appearance_infected
	look.prepared_model = appearance_scene
	look.shared_infected_library = appearance_library
	add_child(look)

func go_to(point: Vector3, speed: float, run := false) -> void:
	if stun_remaining > 0.0:
		return
	destination = point
	move_speed = speed
	running = run
	blocked_time = 0.0
	look.cancel_gesture()

func halt() -> void:
	move_speed = 0.0
	look.cancel_gesture()
	look.locomotion(0.0)

func stun(duration: float) -> void:
	halt()
	stun_remaining = duration
	look.perform(&"emote-no")

func reset_actor() -> void:
	halt()
	route.clear()
	stun_remaining = 0.0
	bite_count = 0
	position = home
	rotation.y = PI
	velocity = Vector3.ZERO

func start_route(points: PackedVector3Array, speed: float) -> void:
	route = points
	route_speed = speed
	route_index = 0

func _physics_process(delta: float) -> void:
	step_retry = maxf(0.0, step_retry - delta)
	if not route.is_empty() and stun_remaining <= 0.0:
		var offset := route[route_index] - global_position
		if Vector2(offset.x, offset.z).length() <= 0.19 and absf(offset.y) < 0.46:
			route_index += 1
		if route_index == route.size():
			route.clear()
			move_speed = 0.0
		else:
			destination = route[route_index]
			move_speed = route_speed
			running = false
	if stun_remaining > 0.0:
		stun_remaining = maxf(0.0, stun_remaining - delta)
		if stun_remaining == 0.0:
			look.cancel_gesture()
	var offset := destination - global_position
	offset.y = 0.0
	var motion := Vector3.ZERO
	var moving := move_speed > 0.0 and offset.length_squared() > 0.0025
	if moving:
		var direction := offset.normalized()
		rotation.y = atan2(-direction.x, -direction.z)
		motion = direction * minf(move_speed, offset.length() / delta)
	elif move_speed > 0.0:
		halt()
	var was_on_floor := is_on_floor()
	if skip_stationary_collision and not moving and was_on_floor and global_position == _stationary_floor:
		_stationary_floor_check -= delta
		if _stationary_floor_check > 0.0:
			velocity = Vector3.ZERO
			look.locomotion(0.0)
			return
	velocity = Vector3(motion.x, 0.0 if was_on_floor else velocity.y - get_gravity().length() * delta, motion.z)
	# move_and_slide integrates the engine tick. Account for accumulated time
	# when a distant zombie performs its simulation at a lower frequency.
	var tick_scale := delta / maxf(get_physics_process_delta_time(), 0.00001)
	velocity *= tick_scale
	move_and_slide()
	velocity /= tick_scale
	if skip_stationary_collision:
		_stationary_floor = global_position if not moving and is_on_floor() else Vector3.INF
		_stationary_floor_check = STATIONARY_FLOOR_CHECK_INTERVAL
	if terrain_steps and was_on_floor and moving and is_on_wall() and step_retry <= 0.0:
		step_retry = CampusWalker.STEP_RETRY_INTERVAL
		CampusWalker.step_up_body(self, motion * delta)
	var actual := get_real_velocity() / tick_scale
	var speed := Vector2(actual.x, actual.z).length()
	blocked_time = blocked_time + delta if moving and speed < 0.15 else 0.0
	if blocked_time >= 0.5:
		halt()
	look.locomotion(speed, running)
