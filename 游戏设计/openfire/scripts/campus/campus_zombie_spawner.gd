extends Node

const Zombie = preload("res://scripts/campus/campus_zombie.gd")
const INFECTED_MODELS: Array[PackedScene] = [
	preload("res://assets/campus/characters/realistic/white_infected.glb"),
	preload("res://assets/campus/characters/realistic/blue_infected.glb"),
	preload("res://assets/campus/characters/realistic/tall_infected.glb"),
	preload("res://assets/campus/characters/realistic/strong_infected.glb"),
]
const MIN_DISTANCE := 15.0
const MAX_DISTANCE := 32.0
const RANGE_STEP := 0.5
const ACTIVE_LIMIT := 200
const GROUP_MIN := 2
const GROUP_MAX := 10
const CHECK_INTERVAL := 60.0
const DESPAWN_DISTANCE := 60.0
const DESPAWN_AFTER := 90.0
const ATTEMPTS_PER_FRAME := 4
const ATTEMPTS_PER_ZOMBIE := 64
const SEARCH_BUDGET_USEC := 1800
const PLAZA_OPENING_COUNT := 24
const SHANGDE_RESERVE := 56
const LIBRARY_WEST_SPAWN := Rect2(-43, -152, 30, 52)
const SHANGDE_SPAWN := Rect2(-24, -38, 48, 35)
const OUTDOOR_REINFORCEMENT_DISTANCE := 28.0

var level: Node3D
var zombies: Array[Zombie] = []
var group_size := 0
var spawn_interval := CHECK_INTERVAL
var min_spawn_distance := MIN_DISTANCE
var max_spawn_distance := MAX_DISTANCE
var remaining := CHECK_INTERVAL
var batch_remaining := 0
var batch_attempts := 0
var batch_checked := 0
var batch_debug := false
var batch_spawned := 0
var group_anchor := Vector3.INF
var clearance := CapsuleShape3D.new()
var lobby_zombies := 0
var checked_navigation_iteration := 0
var navigation_has_surface := false
var last_spawn_work_frame := -1
var infected_libraries: Dictionary[int, AnimationLibrary] = {}
var encounters: Dictionary = {}
var gate_preparation := false

func _ready() -> void:
	clearance.radius = 0.31
	clearance.height = 1.83

func set_spawn_interval(seconds: float) -> void:
	spawn_interval = seconds
	remaining = seconds

func spawn_distance_floor() -> float:
	return 7.5 if level.armed_campaign else MIN_DISTANCE

func set_spawn_range(minimum: float, maximum: float) -> void:
	var floor := spawn_distance_floor()
	max_spawn_distance = clampf(maximum, floor + RANGE_STEP, DESPAWN_DISTANCE - 1.0)
	min_spawn_distance = clampf(minimum, floor, max_spawn_distance - RANGE_STEP)
	group_anchor = Vector3.INF

func _physics_process(delta: float) -> void:
	if not is_multiplayer_authority() or level.round_finished:
		batch_remaining = 0
		return
	var player: CharacterBody3D = level.walker
	for zombie in zombies.duplicate():
		if not is_instance_valid(zombie):
			zombies.erase(zombie)
			continue
		var distance := sqrt(float(level.nearest_survivor_distance_squared(zombie.global_position)))
		zombie.far_time = zombie.far_time + delta if distance >= DESPAWN_DISTANCE else 0.0
		if zombie.far_time >= DESPAWN_AFTER:
			_remove_zombie(zombie)
	if player.role != player.HUMAN:
		batch_remaining = 0
		return
	if gate_preparation:
		batch_remaining = 0
		_continue_encounters(player)
		return
	remaining -= delta
	if remaining <= 0.0:
		if batch_remaining == 0:
			remaining = spawn_interval
			try_group()
	# A difficult ambient search must leave frames available for scripted waves.
	var scripted_first: bool = level.armed_campaign and not batch_debug and Engine.get_physics_frames() % 2 == 0
	if scripted_first:
		_continue_encounters(player)
	if batch_remaining > 0:
		_continue_group()
	if level.armed_campaign and not scripted_first:
		_continue_encounters(player)

# Queue a batch. The search and one new actor share a rendered frame.
func try_group(debug := false) -> int:
	if level.round_finished or level.walker.role != level.walker.HUMAN:
		return 0
	if batch_remaining > 0:
		if not debug:
			return 0
		batch_remaining = 0
		batch_debug = false
	var capacity := ACTIVE_LIMIT - zombies.size()
	if level.armed_campaign and not debug:
		var regular := 0
		var near := 0
		var player_zone: int = level.layout.zone_at(level.walker.global_position)
		var indoors: bool = level.layout.is_dorm_zone(player_zone)
		for zombie in zombies:
			if zombie.encounter != &"":
				continue
			var zone: int = level.layout.zone_at(zombie.global_position)
			if indoors != level.layout.is_dorm_zone(zone):
				continue
			var offset: Vector3 = zombie.global_position - level.walker.global_position
			if absf(offset.y) > 2.0 or offset.length() > max_spawn_distance + 8.0:
				continue
			regular += 1
			if (not indoors or zone == player_zone) and zombie.global_position.distance_to(level.walker.global_position) < 19.0:
				near += 1
		if near >= 5:
			return 0
		capacity = mini(capacity, mini(8 - regular, 5 - near))
	if group_size > 0:
		batch_remaining = mini(group_size, capacity)
	elif capacity >= GROUP_MIN:
		batch_remaining = randi_range(GROUP_MIN, mini(GROUP_MAX, capacity))
	elif debug and capacity == 1:
		batch_remaining = 1
	if batch_remaining <= 0:
		return 0
	batch_debug = debug
	batch_spawned = 0
	batch_attempts = batch_remaining * ATTEMPTS_PER_ZOMBIE
	batch_checked = 0
	group_anchor = Vector3.INF
	return batch_remaining

func _finish_group() -> void:
	batch_remaining = 0
	if batch_debug:
		var message := "已刷新 %d 只丧尸。" % batch_spawned
		if batch_spawned == 0:
			message = "附近没有可通行的刷新点。请到平层走廊或室外重试。"
		level._report(message, 5.0)
	batch_debug = false

func _continue_group() -> void:
	if zombies.size() >= ACTIVE_LIMIT:
		_finish_group()
		return
	if batch_attempts <= 0:
		_finish_group()
		return
	var frame := Engine.get_process_frames()
	if last_spawn_work_frame == frame:
		return
	last_spawn_work_frame = frame
	var map := level.get_world_3d().navigation_map as RID
	var player: CharacterBody3D = level.walker
	var iteration := NavigationServer3D.map_get_iteration_id(map)
	if iteration != checked_navigation_iteration:
		checked_navigation_iteration = iteration
		navigation_has_surface = iteration > 0 \
			and NavigationServer3D.map_get_closest_point_owner(map, player.global_position).is_valid()
	if not navigation_has_surface:
		return
	if group_anchor != Vector3.INF and not _within_spawn_range(group_anchor, player.global_position):
		group_anchor = Vector3.INF
	var at := player.global_position
	var player_zone: int = level.layout.zone_at(at)
	var in_dorm: bool = level.armed_campaign and level.layout.is_dorm_zone(player_zone)
	var reference: Vector3 = at if in_dorm else level.spawn_reference(at)
	var projected_reference := NavigationServer3D.map_get_closest_point(map, reference)
	var lobby := Vector3.INF
	if level.use_full_campus and lobby_zombies < 2:
		var stair: Vector3 = level.layout.west_stair_lobby
		if stair.distance_to(player.global_position) < 20.0:
			lobby = stair
	var deadline := Time.get_ticks_usec() + SEARCH_BUDGET_USEC
	for attempt in mini(ATTEMPTS_PER_FRAME, batch_attempts):
		if attempt > 0 and Time.get_ticks_usec() >= deadline:
			break
		batch_attempts -= 1
		batch_checked += 1
		if batch_checked % 24 == 0:
			group_anchor = Vector3.INF
		var point: Vector3
		if group_anchor == Vector3.INF and lobby != Vector3.INF and lobby_zombies < 2 and batch_checked <= 12:
			point = lobby + Vector3(randf_range(-3.6, 5.4), 0.0, randf_range(-4.5, 4.5))
		elif group_anchor == Vector3.INF:
			var angle := randf_range(-PI, PI)
			var sample_distance := sqrt(randf_range(min_spawn_distance * min_spawn_distance,
				max_spawn_distance * max_spawn_distance))
			if in_dorm and batch_checked % 3 != 0:
				var along: Vector3 = level.layout.dorm_axis
				var side := Vector3(-along.z, 0, along.x)
				var center: Vector3 = level.layout.dorm_start
				center.y = at.y
				var distance := (at - center).dot(along) + sample_distance * (-1.0 if batch_checked % 2 == 0 else 1.0)
				point = center + along * distance + side * randf_range(-0.65, 0.65)
			else:
				point = reference + Vector3(cos(angle), 0, sin(angle)) * sample_distance
		else:
			point = group_anchor + Vector3(randf_range(-3, 3), 0.0, randf_range(-3, 3))
		var projected := NavigationServer3D.map_get_closest_point(map, point)
		if projected.distance_to(point) > 3.3 or absf(projected.y - reference.y) > 1.25 \
				or not _within_spawn_range(projected, at) or not _valid_point(projected, player, [], batch_debug):
			continue
		if in_dorm and level.layout.zone_at(projected) != player_zone:
			continue
		if group_anchor != Vector3.INF and level.layout.zone_at(group_anchor) != level.layout.zone_at(projected):
			continue
		if level.use_full_campus:
			var path := NavigationServer3D.map_get_path(map, projected, projected_reference, true)
			if path.is_empty() or path[-1].distance_to(projected_reference) > 1.0:
				continue
		group_anchor = projected
		var zombie := _spawn(projected)
		if lobby_zombies < 2 and lobby != Vector3.INF and level.layout.zone_at(projected) == 0 and projected.distance_to(lobby) <= 6.0:
			zombie.patrol_center = lobby
			lobby_zombies += 1
		batch_remaining -= 1
		batch_spawned += 1
		if batch_remaining == 0:
			_finish_group()
		return

func _valid_point(point: Vector3, player: CharacterBody3D, pending: Array[Vector3], scripted := false) -> bool:
	var zone: int = level.layout.zone_at(point)
	if zone < 0 or not level.layout.areas[zone].spawnable \
			or (not scripted and not _within_spawn_range(point, player.global_position)):
		return false
	var camera: Camera3D = level.get_viewport().get_camera_3d()
	var head := point + Vector3.UP * 1.5
	if not scripted and camera and camera.is_position_in_frustum(head) and level.clear_line(camera.global_position, head):
		return false
	var world := level.get_world_3d() as World3D
	var floor_ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.4, point - Vector3.UP * 0.2, 1)
	var floor_hit := world.direct_space_state.intersect_ray(floor_ray)
	if floor_hit.is_empty() or floor_hit.normal.y < 0.75 or absf(floor_hit.position.y - point.y) > 0.18:
		return false
	var check := PhysicsShapeQueryParameters3D.new()
	check.shape = clearance
	check.transform.origin = point + Vector3.UP * 0.98
	check.collision_mask = 1 | 2 | Zombie.ACTOR_LAYER
	if not world.direct_space_state.intersect_shape(check, 1).is_empty():
		return false
	for zombie in zombies:
		if zombie.global_position.distance_squared_to(point) < 1.44:
			return false
	for other in pending:
		if other.distance_to(point) < 1.2:
			return false
	return true

func start_encounter(id: StringName, total: int, active: int, at: Vector3) -> void:
	if not encounters.has(id):
		encounters[id] = {"remaining": total, "cap": active, "origin": at}

func start_plaza_encounter(at: Vector3) -> void:
	if encounters.has(&"plaza"):
		return
	start_encounter(&"plaza", 420, 108, at)
	encounters[&"plaza"].spawned = 0

func start_direct_plaza_encounter(at: Vector3, peer: int) -> void:
	start_plaza_encounter(at)
	var wave: Dictionary = encounters[&"plaza"]
	if wave.has("direct_peer"):
		return
	wave.origin = at
	wave.direct_peer = peer
	wave.opening_start = int(wave.get("spawned", 0))


func prepare_gate_supplies() -> void:
	gate_preparation = true
	batch_remaining = 0
	# Existing actors keep pursuing. A shortcut approach continues its plaza
	# encounter during preparation, independently of the gate wave.

func start_dorm_ambush(entered_at: Vector3) -> void:
	if encounters.has(&"dorm_corridor"):
		return
	var offset: Vector3 = entered_at - level.layout.dorm_start
	var distance: float = clampf(offset.dot(level.layout.dorm_axis), 0.0, level.layout.dorm_length)
	var origin: Vector3 = level.layout.dorm_start + level.layout.dorm_axis * distance
	var direction := -1.0 if distance > level.layout.dorm_length - 24.0 else 1.0
	start_encounter(&"dorm_corridor", 14, 14, origin)
	encounters[&"dorm_corridor"].direction = direction
	# Reserve room for the nearby ambush even after large outdoor encounters.
	for zombie in zombies.duplicate():
		if zombies.size() <= ACTIVE_LIMIT - 14:
			break
		if zombie.global_position.distance_to(entered_at) > 30.0:
			_remove_zombie(zombie)

func start_gate_encounter(at: Vector3) -> void:
	gate_preparation = false
	encounters.clear()
	for zombie in zombies.duplicate():
		if is_instance_valid(zombie) and zombie.global_position.distance_squared_to(at) > 42.0 * 42.0 \
				and not _visible_spawn_point(zombie.global_position):
			_remove_zombie(zombie)
	start_encounter(&"final_gate", 92, 48, at)
	encounters[&"final_gate"].spawned = 0

func _remove_zombie(zombie: Zombie) -> void:
	level.release_bite(zombie)
	zombies.erase(zombie)
	zombie.queue_free()

func _continue_encounters(player: CharacterBody3D) -> void:
	var frame := Engine.get_process_frames()
	if last_spawn_work_frame == frame or zombies.size() >= ACTIVE_LIMIT:
		return
	var map: RID = level.get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(map) == 0:
		return
	for id in [&"final_gate", &"dorm_corridor", &"plaza", &"field", &"roof"]:
		if not encounters.has(id):
			continue
		var wave: Dictionary = encounters[id]
		var direct := wave.has("direct_peer")
		if gate_preparation and not direct:
			continue
		var at := player.global_position
		if direct and int(wave.direct_peer) != 1 and is_instance_valid(level.coop_session):
			at = level.coop_session.remote_survivors().get(wave.direct_peer, at)
		var reserve := SHANGDE_RESERVE if id == &"plaza" and not direct else 0
		if int(wave.remaining) <= reserve:
			continue
		var distance_from_origin := Vector2(at.x - wave.origin.x, at.z - wave.origin.z).length()
		if distance_from_origin > 65.0:
			continue
		if id in [&"roof", &"dorm_corridor"] and absf(at.y - wave.origin.y) > 2.5:
			continue
		if zombies.size() >= int(wave.cap):
			var active := zombies.filter(func(zombie: Zombie):
				return zombie.encounter == id and (not direct or _inside_spawn_area(SHANGDE_SPAWN, zombie.patrol_center)))
			if active.size() >= int(wave.cap):
				continue
		var deadline := Time.get_ticks_usec() + SEARCH_BUDGET_USEC
		for attempt in range(7):
			if attempt > 0 and Time.get_ticks_usec() >= deadline:
				break
			var sample := _encounter_sample(id, at, wave.origin)
			var point := NavigationServer3D.map_get_closest_point(map, sample)
			var distance := point.distance_to(at)
			var close_wave: bool = id in [&"roof", &"dorm_corridor", &"final_gate"]
			if point.distance_to(sample) > 2.3 or distance < (5.5 if close_wave else 12.0) or distance > 57.0:
				continue
			if id == &"dorm_corridor" and level.layout.zone_at(point) != level.layout.DORM_FLOOR_ONE:
				continue
			if id == &"roof" and absf(point.y - wave.origin.y) > 0.35:
				continue
			if id == &"final_gate" and (point.z >= 5.0 or point.y > 1.5):
				continue
			if not _encounter_point_allowed(id, point, player, wave, at):
				continue
			if not _valid_point(point, player, [], true):
				continue
			var investigation_duration := 18.0
			if id in [&"plaza", &"final_gate"]:
				var path := NavigationServer3D.map_get_path(map, point, at, true)
				if path.size() < 2 or path[-1].distance_to(at) > 1.2:
					continue
				investigation_duration = _encounter_investigation_duration(id, path)
			var zombie := _spawn(point)
			zombie.encounter = id
			zombie.patrol_center = point
			# Start moving into the encounter while retaining ordinary sight and door behaviour.
			var destination := NavigationServer3D.map_get_closest_point(map, at)
			if id != &"roof" or absf(point.y - at.y) < 2.0:
				zombie._investigate(destination, investigation_duration)
			wave.remaining -= 1
			wave.spawned = int(wave.get("spawned", 0)) + 1
			last_spawn_work_frame = frame
			return

func _encounter_investigation_duration(id: StringName, path: PackedVector3Array) -> float:
	if id not in [&"plaza", &"final_gate"]:
		return 18.0
	var length := 0.0
	for index in range(1, path.size()):
		length += path[index - 1].distance_to(path[index])
	# Far crowds can follow a much longer route around buildings. Keep the
	# investigation alive for that walk, with time for turns and congestion.
	return maxf(18.0, length / Zombie.WALK + 8.0)

func _visible_spawn_point(point: Vector3) -> bool:
	var camera: Camera3D = level.get_viewport().get_camera_3d()
	if camera == null:
		return false
	for height in [0.7, 1.5]:
		var sample: Vector3 = point + Vector3.UP * float(height)
		if camera.is_position_in_frustum(sample) and level.clear_line(camera.global_position, sample):
			return true
	return false

func _encounter_point_allowed(id: StringName, point: Vector3, player: CharacterBody3D,
		wave: Dictionary, focus := Vector3.INF) -> bool:
	if id not in [&"plaza", &"final_gate"]:
		return true
	var at := player.global_position if focus == Vector3.INF else focus
	if level.layout.zone_at(point) != level.layout.OUTSIDE or absf(point.y - at.y) > 1.6:
		return false
	var opening: bool = int(wave.get("spawned", 0)) - int(wave.get("opening_start", 0)) < PLAZA_OPENING_COUNT
	var minimum := OUTDOOR_REINFORCEMENT_DISTANCE
	if id == &"plaza":
		var in_shangde := wave.has("direct_peer")
		var area := SHANGDE_SPAWN if in_shangde else LIBRARY_WEST_SPAWN
		# Check the projected point too: a navigation snap can otherwise
		# move a valid sample out of the intended encounter area.
		if not _inside_spawn_area(area, point):
			return false
		minimum = (12.0 if opening else 16.0) if in_shangde else (17.0 if opening else 21.0)
	if point.distance_to(at) < minimum:
		return false
	# Reinforcements enter from concealed space after the first group.
	return opening or not _visible_spawn_point(point)

func _inside_spawn_area(area: Rect2, point: Vector3) -> bool:
	return area.has_point(Vector2(point.x, point.z))

func _encounter_sample(id: StringName, _at: Vector3, origin: Vector3) -> Vector3:
	match id:
		&"dorm_corridor":
			var direction: float = encounters.get(id, {}).get("direction", 1.0)
			var axis: Vector3 = level.layout.dorm_axis
			var side := Vector3(-axis.z, 0, axis.x)
			return origin + axis * (randf_range(8.0, 25.0) * direction) + side * randf_range(-0.58, 0.58)
		&"final_gate":
			return Vector3(randf_range(-24.0, 24.0), 0.20, randf_range(-32.0, 3.0))
		&"roof":
			# The encounter belongs to the highest indoor floor, regardless of
			# where the player subsequently moves on the stairs.
			return origin + level.layout.along * randf_range(8.0, 27.0) \
				+ level.layout.across * randf_range(-0.58, 0.58)
		&"field":
			return Vector3(randf_range(-351, -265), 0.2, randf_range(-188, -72))
		&"plaza":
			var wave: Dictionary = encounters.get(id, {})
			var area := SHANGDE_SPAWN if wave.has("direct_peer") else LIBRARY_WEST_SPAWN
			return Vector3(randf_range(area.position.x, area.end.x), 0.20,
				randf_range(area.position.y, area.end.y))
		_:
			return origin

func _within_spawn_range(point: Vector3, player_position: Vector3) -> bool:
	var offset := point - player_position
	var horizontal := offset.x * offset.x + offset.z * offset.z
	# A different floor must not make a point directly above or below the player eligible.
	return horizontal >= min_spawn_distance * min_spawn_distance \
		and offset.length_squared() <= max_spawn_distance * max_spawn_distance

func _spawn(point: Vector3, replica_identity := -1) -> Zombie:
	var zombie := Zombie.new()
	zombie.level = level
	zombie.terrain_steps = level.use_full_campus
	zombie.position = level.to_local(point + Vector3.UP * 0.02)
	zombie.appearance_identity = randi_range(0, INFECTED_MODELS.size() - 1) if replica_identity < 0 else replica_identity
	zombie.appearance_infected = true
	zombie.appearance_scene = INFECTED_MODELS[zombie.appearance_identity]
	zombie.appearance_library = infected_libraries.get(zombie.appearance_identity)
	level.add_child(zombie)
	if zombie.appearance_library == null:
		infected_libraries[zombie.appearance_identity] = zombie.look.animation.get_animation_library(&"campus")
	zombie.place(zombie.appearance_identity)
	zombies.append(zombie)
	if replica_identity >= 0:
		zombie.set_physics_process(false)
		zombie.collision_layer = 0
		zombie.collision_mask = 0
	return zombie
