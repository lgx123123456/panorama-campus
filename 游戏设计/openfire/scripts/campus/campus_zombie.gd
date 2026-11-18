extends "res://scripts/campus/campus_character_actor.gd"

enum State { WANDER, INVESTIGATE, CHASE, SEARCH, KNOCK, DISPERSE, BITE, GRAB, STUNNED }

const BITE_RANGE := 1.32
const BITE_WINDUP := 0.20
const CLOSE_AWARENESS := 2.4
const WALK := 1.35
const RUN := 2.75
const MAX_HEALTH := 100.0
const PURSUIT_SECONDS := 14.0

var level: Node3D
var agent: NavigationAgent3D
var state := State.WANDER
var think_in := 0.0
var state_time := 0.0
var memory := Vector3.INF
var sight_direction := Vector3.ZERO
var pursuit_goal := Vector3.INF
var goal := Vector3.INF
var last_path := Vector3.INF
var next_bite := 0.0
var attack_peer := 1
var room_snapshot_id := 0
var door_index := -1
var door_side := 1.0
var heard_id := 0
var last_seen_zone := -1
var far_time := 0.0
var encounter: StringName = &""
var command_owner := false
var searching := false
var patrol_center := Vector3.INF
var health := MAX_HEALTH
var defeated := false

func take_weapon_hit(damage: float, headshot := false) -> bool:
	if defeated or (damage <= 0.0 and not headshot):
		return false
	health = 0.0 if headshot else maxf(0.0, health - damage)
	if health > 0.0:
		stun(0.18)
		return false
	defeated = true
	level.release_bite(self)
	level.spawner.zombies.erase(self)
	set_physics_process(false)
	collision_layer = 0
	collision_mask = 0
	look.animation.pause()
	look.set_process(false)
	var fall := create_tween()
	fall.tween_property(look, "rotation:z", -PI / 2.0, 0.32)
	fall.tween_interval(4.0)
	fall.tween_property(look, "position:y", -1.2, 1.0)
	fall.tween_callback(queue_free)
	return true
var dormant := false
var simulation_elapsed := 0.0
var simulation_phase := 0

func _ready() -> void:
	super._ready()
	look.configure_crowd_animation(level.walker)
	skip_stationary_collision = true
	simulation_phase = int(get_instance_id() % 60)
	max_slides = 3
	agent = NavigationAgent3D.new()
	agent.path_desired_distance = 0.30
	agent.target_desired_distance = 0.38
	agent.path_max_distance = 0.9
	add_child(agent)
	think_in = randf_range(0.14, 0.36)

func place(identity: int) -> void:
	look.set_appearance(identity, true)
	rotation.y = randf_range(-PI, PI)
	state_time = randf_range(0.1, 0.7)

func approach_noise(point: Vector3, source_id: int, kind: StringName) -> void:
	if source_id <= heard_id or state in [State.BITE, State.GRAB, State.STUNNED] or command_owner:
		return
	if state == State.KNOCK and kind == &"knock":
		return
	heard_id = source_id
	if state == State.CHASE and level.can_see(self, level.walker):
		return
	if state == State.CHASE and kind == &"step":
		# A footfall updates the evidence without slowing an active pursuit.
		memory = point
		last_seen_zone = level.layout.zone_at(point)
		pursuit_goal = Vector3.INF
		goal = point
		state_time = PURSUIT_SECONDS
		return
	if state == State.KNOCK:
		state_time = randf_range(4.8, 7.8)
		if kind != &"book":
			return
	_investigate(point, 6.0)

func join_door(index: int) -> void:
	door_index = index
	door_side = level.door_side(index, global_position)
	if memory == Vector3.INF:
		memory = level.door_point(index, -door_side)
	_set_state(State.KNOCK, randf_range(5.0, 8.0))

func command(point: Vector3) -> void:
	_investigate(point, 10.0)
	command_owner = true

func _investigate(point: Vector3, duration: float) -> void:
	_set_state(State.INVESTIGATE, duration)
	goal = point
	memory = point

func can_receive_order() -> bool:
	return state in [State.WANDER, State.SEARCH, State.DISPERSE] and not command_owner and stun_remaining <= 0.0

func stun(duration: float) -> void:
	level.release_bite(self)
	_set_state(State.STUNNED)
	super.stun(duration)

func door_changed(index: int) -> void:
	last_path = Vector3.INF
	if state == State.KNOCK and door_index == index and level.door_is_open(index):
		_investigate(memory, 4.5)

func _exit_tree() -> void:
	if is_instance_valid(level):
		level.release_bite(self)

func _physics_process(delta: float) -> void:
	# Campus collision bodies stream within 65m. Keep distant actors on their
	# last valid floor until the player returns or the spawner recycles them.
	var distance_squared := float(level.nearest_survivor_distance_squared(global_position))
	if distance_squared >= 60.0 * 60.0:
		velocity = Vector3.ZERO
		simulation_elapsed = 0.0
		if not dormant:
			dormant = true
			look.process_mode = Node.PROCESS_MODE_DISABLED
		return
	if dormant:
		dormant = false
		look.process_mode = Node.PROCESS_MODE_INHERIT
	simulation_elapsed += delta
	var tick_stride := 1
	if distance_squared > 30.0 * 30.0:
		tick_stride = 8
	elif distance_squared > 14.0 * 14.0:
		tick_stride = 5
	elif distance_squared > 8.0 * 8.0:
		tick_stride = 3
	elif distance_squared > 1.8 * 1.8:
		tick_stride = 2
	if tick_stride > 1 and (Engine.get_physics_frames() + simulation_phase) % tick_stride != 0:
		return
	delta = simulation_elapsed
	simulation_elapsed = 0.0
	if level.round_finished:
		if move_speed > 0.0:
			halt()
		super._physics_process(delta)
		return
	state_time -= delta
	next_bite = maxf(0.0, next_bite - delta)
	var attack_range: float = level.zombie_attack_range
	if stun_remaining <= 0.0 and state not in [State.BITE, State.GRAB] and next_bite <= 0.0 \
			and distance_squared <= attack_range * attack_range:
		_think()
	if not route.is_empty():
		super._physics_process(delta)
		if route.is_empty():
			last_path = Vector3.INF
		return
	if stun_remaining > 0.0:
		super._physics_process(delta)
		return
	if state == State.STUNNED:
		_set_state(State.SEARCH, 2.5)
	if state == State.BITE:
		if state_time <= 0.0:
			level.resolve_zombie_attack(self, attack_peer)
			next_bite = 1.55
			_set_state(State.GRAB if level.bite_owner == self else State.SEARCH, 1.1)
	elif state == State.GRAB:
		if level.bite_owner != self:
			next_bite = maxf(next_bite, 0.85)
			_set_state(State.SEARCH, 1.1)
	else:
		think_in -= delta
		if think_in <= 0.0:
			think_in = randf_range(0.18, 0.32)
			_think()
		_follow()
	super._physics_process(delta)

func _think() -> void:
	var target: Dictionary = level.visible_zombie_target(self)
	if not target.is_empty():
		var target_position: Vector3 = target.position
		if memory != Vector3.INF:
			var movement := target_position - memory
			movement.y = 0.0
			if movement.length_squared() > 0.01:
				sight_direction = movement.normalized()
		memory = target_position
		last_seen_zone = level.layout.zone_at(memory)
		if state != State.CHASE:
			_set_state(State.CHASE)
		state_time = PURSUIT_SECONDS
		pursuit_goal = Vector3.INF
		var distance := global_position.distance_to(memory)
		var attack_range: float = level.zombie_attack_range
		if distance <= attack_range and next_bite <= 0.0 and level.reserve_zombie_attack(self, target.id):
			attack_peer = target.id
			route.clear()
			_set_state(State.BITE, BITE_WINDUP)
			_face(memory)
			look.perform(&"attack-melee-right")
		elif distance < minf(1.15, attack_range * 0.9):
			goal = Vector3.INF
			_face(memory)
		else:
			goal = memory if level.bite_owner in [null, self] else level.chase_position(self, memory)
		return
	match state:
		State.CHASE:
			var obstruction: int = level.closed_door_between(global_position, last_seen_zone)
			if obstruction >= 0:
				join_door(obstruction)
			elif memory == Vector3.INF or state_time <= 0.0:
				_set_state(State.SEARCH, 5.0)
			else:
				if pursuit_goal == Vector3.INF:
					pursuit_goal = level.pursuit_point(global_position, memory, sight_direction)
				if _near(pursuit_goal, 0.55):
					_set_state(State.SEARCH, 5.0)
				else:
					goal = pursuit_goal
		State.KNOCK:
			if state_time <= 0.0:
				_set_state(State.DISPERSE, 4.0)
				return
			goal = level.door_wait_point(self)
			if _near(goal, 0.42):
				_face(level.doors.doors[door_index].center)
				if level.can_knock(self) and look.gesture == &"":
					look.perform(&"interact-right", 0.83)
					level.knock(self)
		State.INVESTIGATE:
			if state_time <= 0.0 or _near(goal, 0.62):
				_set_state(State.SEARCH, 3.0)
		State.SEARCH:
			if state_time <= 0.0:
				_set_state(State.DISPERSE, 4.0)
			elif not searching or (goal != Vector3.INF and _near(goal, 0.55)):
				var center := global_position if memory == Vector3.INF else memory
				goal = level.wander_point(global_position, center, 3.3)
				searching = true
		State.DISPERSE, State.WANDER:
			if state_time <= 0.0 or (goal != Vector3.INF and _near(goal, 0.50)):
				_set_state(State.WANDER, randf_range(2.3, 4.3))
				var patrol := global_position if patrol_center == Vector3.INF else patrol_center
				goal = level.wander_point(global_position, patrol, 5.5)
			elif goal == Vector3.INF and state == State.DISPERSE:
				goal = level.wander_point(global_position, global_position, 6.5)

func _follow() -> void:
	move_speed = 0.0
	if goal == Vector3.INF or _near(goal, agent.target_desired_distance):
		return
	if last_path == Vector3.INF or goal.distance_to(last_path) > 0.5:
		level.queue_path(self)
	if last_path == Vector3.INF:
		return
	var point := agent.get_next_path_position()
	if agent.is_navigation_finished():
		return
	var chase_speed: float = level.zombie_run_speed
	if level.try_stairs(self, point, chase_speed if state == State.CHASE else 2.05):
		return
	destination = point
	running = state == State.CHASE
	move_speed = chase_speed if running else WALK

func _set_state(next: State, duration := 0.0) -> void:
	if state in [State.BITE, State.GRAB] and next not in [State.BITE, State.GRAB]:
		level.release_bite(self)
	state = next
	state_time = duration
	goal = Vector3.INF
	last_path = Vector3.INF
	move_speed = 0.0
	searching = false
	if next != State.INVESTIGATE and next != State.SEARCH:
		command_owner = false
	if next != State.KNOCK:
		door_index = -1
	if next in [State.DISPERSE, State.WANDER]:
		memory = Vector3.INF
		last_seen_zone = -1
		sight_direction = Vector3.ZERO
		pursuit_goal = Vector3.INF
	look.cancel_gesture()

func _near(point: Vector3, radius: float) -> bool:
	return global_position.distance_to(point) <= radius

func _face(point: Vector3) -> void:
	var offset := point - global_position
	if Vector2(offset.x, offset.z).length_squared() > 0.001:
		rotation.y = atan2(-offset.x, -offset.z)
