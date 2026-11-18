extends Node3D

const CampusTour = preload("res://scripts/campus/campus_tour_walker.gd")

const Layout = preload("res://scripts/campus/campus_zombie_layout.gd")
const SurvivalLayout = preload("res://scripts/campus/campus_survival_layout.gd")
const SurvivalPoints = preload("res://scripts/campus/campus_survival_points.gd")
const FieldPassages = preload("res://scripts/campus/campus_field_passages.gd")

@export var use_full_campus := false
@export var enable_debug_tools := false
@export var armed_campaign := false
const Actor = preload("res://scripts/campus/campus_character_actor.gd")
const Walker = preload("res://scripts/campus/campus_character_walker.gd")
const Zombie = preload("res://scripts/campus/campus_zombie.gd")
const Spawner = preload("res://scripts/campus/campus_zombie_spawner.gd")
const Firearms = preload("res://scripts/campus/campus_firearms.gd")
const NightWeather = preload("res://scripts/campus/campus_night_weather.gd")
const NightAudio = preload("res://scripts/campus/campus_night_audio.gd")
const PlayerHealth = preload("res://scripts/campus/campus_player_health.gd")
const Campaign = preload("res://scripts/campus/campus_armed_campaign.gd")

const INFECTION_SECONDS := 30.0
const PLAYER_MAX_HEALTH := 100
const ZOMBIE_BITE_DAMAGE := 25
const DEFAULT_ZOMBIE_CHASE_DISTANCE := 12.0
const HEARING_PATHS_PER_FRAME := 2
const HEARING_BUDGET_USEC := 1500
const GRAB_DURATION := 1.05
const GRAB_PULL_SPEED := 0.8
const GRAB_SEPARATION := 0.78
const GRAB_ESCAPE_PRESSES := 2
const GUIDE_ID := 4
const EXIT_WEST := Vector3(-21.0, 0.0, 0.0)
const EXIT_EAST := Vector3(27.0, 3.0, 0.0)
const PROP_INFO := {
	&"book": ["书本", Vector3(-12.4, 0.18, -6.9), Vector3(0.23, 0.08, 0.31), Color("#be5540")],
	&"brick": ["砖头", Vector3(5.0, 0.18, -5.4), Vector3(0.24, 0.12, 0.14), Color("#a26c53")],
	&"tape": ["护臂胶布", Vector3(-11.0, 0.18, -6.55), Vector3(0.14, 0.12, 0.14), Color("#d9c46b")],
}

@onready var walker: Walker = $"../Walker"
@onready var doors: Node = $"../Doors"
@onready var interface: CanvasLayer = $"../Interface"

var layout: Layout
var spawner: Spawner
var weather: NightWeather
var night_audio: NightAudio
var guide: Actor
var props: Dictionary = {}
var held: StringName = &""
var thrown: Dictionary = {}
var bite_owner: Zombie
var grab_remaining := 0.0
var grab_struggles := 0
var grab_damaged := false
var armor := 0
var player_health := PLAYER_MAX_HEALTH
var infection := -1.0
var debug_invincible := false
var ability_cooldown := 0.0
var king_bite_remaining := 0.0
var king_bite_cooldown := 0.0
var elapsed := 0.0
var round_finished := false
var sound_id := 0
var door_cycles: Dictionary = {}
var path_queue: Array[Zombie] = []
var pending_step_sounds: Dictionary = {}
var controls: Label
var controls_panel: PanelContainer
var objective_panel: PanelContainer
var debug_toggle: Button
var health_hud: PlayerHealth
var briefing: Label
var feedback: Label
var result_panel: PanelContainer
var result: Label
var feedback_until := 0.0
var guide_update := 0.0
var guide_heading_out := false
var left_classroom := false
var left_building := false
var escape_points: Dictionary
var guide_exit: Vector3
var firearms: Firearms
var campaign: Campaign
var coop_session: Node
var zombie_chase_distance := DEFAULT_ZOMBIE_CHASE_DISTANCE
var zombie_attack_range := Zombie.BITE_RANGE
var zombie_run_speed := Zombie.RUN

func _ready() -> void:
	enable_debug_tools = enable_debug_tools and (OS.has_feature("editor") or OS.has_feature("campus_admin"))
	layout = SurvivalLayout.new() if use_full_campus else Layout.new()
	add_child(layout)
	layout.build(doors)
	escape_points = {"正门": SurvivalPoints.FRONT_GATE, "西门": SurvivalPoints.WEST_GATE} if use_full_campus \
		else {"西侧": EXIT_WEST, "东侧": EXIT_EAST}
	guide_exit = layout.floor_one_exit if use_full_campus else EXIT_WEST
	doors.passage_changed.connect(_door_changed)
	spawner = Spawner.new()
	spawner.level = self
	add_child(spawner)
	if use_full_campus:
		weather = NightWeather.new()
		weather.walker = walker
		add_child(weather)
		night_audio = NightAudio.new()
		night_audio.walker = walker
		night_audio.weather = weather
		add_child(night_audio)
	NavigationServer3D.map_changed.connect(_navigation_changed)
	if not armed_campaign:
		guide = Actor.new()
		guide.terrain_steps = use_full_campus
		guide.position = (walker.spawn.position + Vector3(0.22, 0.0, -1.54)) if use_full_campus \
			else Vector3(-13.0, 0.05, -5.1)
		guide.rotation.y = PI
		add_child(guide)
		guide.look.set_appearance(GUIDE_ID, false)
		var badge := Label3D.new()
		badge.position.y = 2.02
		badge.text = "AI同学"
		badge.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		badge.font_size = 33
		badge.pixel_size = 0.0027
		guide.add_child(badge)
	for kind: StringName in PROP_INFO:
		if not armed_campaign or kind not in [&"tape", &"book"]:
			_make_prop(kind)
	walker.set_role([2, 3].pick_random(), Walker.HUMAN)
	walker._capture_mouse(true)
	walker.footstep.connect(_footstep)
	_build_hud()
	firearms = Firearms.new()
	walker.camera.add_child(firearms)
	walker.firearm = firearms
	firearms.setup(walker, self)
	firearms.shot_fired.connect(func(at: Vector3): _emit_sound(at, 45.0, &"gunshot"))
	if armed_campaign:
		escape_points.clear()
		campaign = Campaign.new()
		campaign.level = self
		add_child(campaign)
	if enable_debug_tools:
		var debug_menu: Node = load("res://scripts/campus/campus_combat_debug.gd").new()
		debug_menu.level = self
		interface.add_child(debug_menu)
		for child in debug_menu.get_children():
			if child is Button:
				debug_toggle = child
				break
		_layout_objective_panel()
	if use_full_campus:
		print("Campus survival ready: full campus, B15 classroom spawn")

func _physics_process(delta: float) -> void:
	for index in range(path_queue.size() - 1, -1, -1):
		var zombie = path_queue[index]
		if not is_instance_valid(zombie) or not zombie.is_physics_processing() \
				or zombie.goal == Vector3.INF or not zombie.route.is_empty() \
				or nearest_survivor_distance_squared(zombie.global_position) >= 60.0 * 60.0 \
				or (zombie.last_path != Vector3.INF and zombie.goal.distance_to(zombie.last_path) <= 0.5) \
				or zombie._near(zombie.goal, zombie.agent.target_desired_distance):
			path_queue.remove_at(index)
	if round_finished:
		return
	_service_step_sounds()
	for request in mini(2, path_queue.size()):
		var zombie: Zombie = path_queue.pop_front()
		zombie.agent.target_position = zombie.goal
		zombie.last_path = zombie.goal
	if elapsed < 1.25 and elapsed + delta >= 1.25:
		var noise := walker.spawn.global_position + Vector3(9, 0.4, 0) if use_full_campus else Vector3(5, 0.4, -6)
		Audio.play_3d("res://assets/audio/impact.ogg", noise, -8.0, 0.18, 35.0)
	elapsed += delta
	_update_grab(delta)
	ability_cooldown = maxf(0.0, ability_cooldown - delta)
	king_bite_cooldown = maxf(0.0, king_bite_cooldown - delta)
	if king_bite_remaining > 0.0:
		king_bite_remaining = maxf(0.0, king_bite_remaining - delta)
		if king_bite_remaining == 0.0:
			_resolve_king_bite()
	_follow_held_prop()
	if infection > 0.0:
		infection = maxf(0.0, infection - delta)
		if infection == 0.0:
			_turn_player()
	for exit_name: String in escape_points:
		var exit_point: Vector3 = escape_points[exit_name]
		var radius := 3.2 if use_full_campus else 0.94
		if walker.role == Walker.HUMAN and walker.global_position.distance_to(exit_point) < radius:
			var outcome := "感染离校" if use_full_campus else "感染离开"
			if infection < 0.0:
				outcome = "成功撤离"
			_finish("%s · %s撤离点" % [outcome, exit_name])
			return
	guide_update -= delta
	if guide_update <= 0.0:
		guide_update = 0.45
		if not armed_campaign:
			_update_guide()
	for index in door_cycles.keys():
		if not spawner.zombies.any(func(zombie: Zombie): return zombie.door_index == index):
			door_cycles.erase(index)
	_update_hud()

func _update_guide() -> void:
	if not is_instance_valid(guide) or not guide.route.is_empty():
		return
	if walker.role == Walker.KING:
		guide_heading_out = true
		if guide.global_position.distance_to(guide_exit) < 1.5:
			guide.queue_free()
			guide = null
			_finish("AI同学已离开致远楼" if use_full_campus else "AI同学已从西侧撤离")
		elif guide.stun_remaining <= 0.0:
			_guide_toward(guide_exit, 3.5)
		return
	if elapsed < 3.6:
		return
	var zone := layout.zone_at(walker.global_position)
	var in_corridor := zone in [0, 1, 2, 3, 4] if use_full_campus else zone in [2, 3, 4]
	if not left_classroom and in_corridor:
		left_classroom = true
		var hint := "AI同学：先听西楼梯有没有动静。堵住的话，沿走廊去东楼梯。" if use_full_campus \
			else "AI同学：西边能直接撤离，东边可以走楼梯。先听脚步再出发。"
		_report(hint, 6.0)
	if use_full_campus and not left_building and zone == SurvivalLayout.OUTSIDE:
		left_building = true
		_report("AI同学：正门走尚德广场，西门走孔德广场和公寓方向。", 7.5)
	var offset := walker.global_position - guide.global_position
	if offset.length() > 4.5 and offset.length() < 18.0:
		var follow_point := walker.global_position - Vector3(offset.x, 0, offset.z).normalized() * 2.0
		_guide_toward(follow_point, 2.55)
	elif guide.move_speed > 0.0:
		guide.halt()

func _guide_toward(point: Vector3, speed: float, can_open_door := true) -> void:
	var path := NavigationServer3D.map_get_path(get_world_3d().navigation_map, guide.global_position, point, true)
	if path.size() < 2 or path[-1].distance_to(point) > 1.3:
		if guide_heading_out and can_open_door:
			var index := _closest_lockable_door(guide.global_position, 10.0)
			if index >= 0 and not doors.doors[index].open and not doors.doors[index].moving:
				if guide.global_position.distance_to(doors.doors[index].center) > 2.45:
					_guide_toward(door_point(index, -1.0), speed, false)
				else:
					doors.doors[index].locked = false
					doors.set_open(index, true)
		return
	var waypoint := path[1]
	if try_stairs(guide, waypoint, speed):
		return
	if guide.global_position.distance_to(waypoint) > 0.14:
		guide.go_to(waypoint, speed, speed > 3.0)

func try_stairs(actor: Actor, waypoint: Vector3, speed: float) -> bool:
	if not use_full_campus:
		return false
	var points: PackedVector3Array = layout.stair_route(actor.global_position, waypoint)
	if points.is_empty():
		return false
	actor.start_route(points, minf(speed, 2.15))
	return true

func is_ascending_stair(at: Vector3, direction: Vector3) -> bool:
	return armed_campaign and layout.is_ascending_stair(at, direction)

func spawn_reference(at: Vector3) -> Vector3:
	var zone := layout.zone_at(at)
	if use_full_campus and zone >= SurvivalLayout.FIRST_CLASSROOM:
		var closest := INF
		var point := at
		for passage: Dictionary in layout.passages:
			if passage.from == zone and passage.door >= 0:
				var distance := at.distance_squared_to(passage.point)
				if distance < closest:
					closest = distance
					point = door_point(passage.door, 1.0)
		return point
	return at

func _navigation_changed(map: RID) -> void:
	if not is_inside_tree() or map != get_world_3d().navigation_map:
		return
	for zombie in spawner.zombies:
		zombie.last_path = Vector3.INF

func queue_path(zombie: Zombie) -> void:
	if not path_queue.has(zombie):
		path_queue.append(zombie)

func clear_line(from: Vector3, to: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(from, to, 1)
	return get_world_3d().direct_space_state.intersect_ray(query).is_empty()

func can_see(zombie: Zombie, target: Walker) -> bool:
	return target.role == Walker.HUMAN and not round_finished \
		and _can_see_position(zombie, target.global_position, target.crouched)


func _can_see_position(zombie: Zombie, at: Vector3, crouched: bool) -> bool:
	var offset := at - zombie.global_position
	if offset.length_squared() > zombie_chase_distance * zombie_chase_distance or absf(offset.y) > 1.9:
		return false
	var flat := Vector3(offset.x, 0.0, offset.z)
	if flat.length() > Zombie.CLOSE_AWARENESS and (-zombie.global_basis.z).dot(flat.normalized()) < 0.42:
		return false
	return clear_line(zombie.global_position + Vector3.UP * 1.55,
		at + Vector3.UP * (0.69 if crouched else 1.13))


func nearest_survivor_distance_squared(at: Vector3) -> float:
	var nearest := at.distance_squared_to(walker.global_position)
	if is_instance_valid(coop_session) and Net.is_host():
		for point: Vector3 in coop_session.remote_survivors().values():
			nearest = minf(nearest, at.distance_squared_to(point))
	return nearest


func visible_zombie_target(zombie: Zombie) -> Dictionary:
	var visible := {}
	var best := INF
	if can_see(zombie, walker):
		visible = {"id": 1, "position": walker.global_position}
		best = zombie.global_position.distance_squared_to(walker.global_position)
	if not is_instance_valid(coop_session) or not Net.is_host():
		return visible
	var nearby: Dictionary = coop_session.remote_survivors()
	for id: int in nearby:
		var point: Vector3 = nearby[id]
		var distance := zombie.global_position.distance_squared_to(point)
		if distance < best and _can_see_position(zombie, point, false):
			best = distance
			visible = {"id": id, "position": point}
	return visible


func reserve_zombie_attack(zombie: Zombie, id: int) -> bool:
	return reserve_bite(zombie) if id == 1 else coop_session.can_bite(id, zombie)


func resolve_zombie_attack(zombie: Zombie, id: int) -> void:
	if id == 1:
		resolve_bite(zombie)
	elif is_instance_valid(coop_session):
		coop_session.bite_remote(id, zombie)

func pursuit_point(origin: Vector3, seen: Vector3, direction: Vector3) -> Vector3:
	# Only observed movement and known door geometry extend a last sighting.
	# The concealed player's current transform is deliberately never consulted.
	if direction.length_squared() < 0.1:
		direction = seen - origin
		direction.y = 0.0
		direction = direction.normalized()
	if use_full_campus:
		for index in FieldPassages.APPROACH.size():
			var entry: Vector3 = FieldPassages.APPROACH[index]
			var exit: Vector3 = FieldPassages.EXIT[index]
			if absf(seen.y - entry.y) > 1.5 or absf(seen.z - entry.z) > 1.8:
				continue
			if seen.x < entry.x - 2.0 or seen.x > exit.x + 2.0:
				continue
			if direction.x > 0.45 and origin.x < exit.x:
				return exit
			if direction.x < -0.45 and origin.x > entry.x:
				return entry
	for door: Dictionary in doors.doors:
		if not door.open or door.moving:
			continue
		var center: Vector3 = door.center
		if seen.distance_to(center) > 2.6:
			continue
		var outward: Vector3 = door.get("outward", Vector3.BACK)
		var crossing := direction.dot(outward)
		if absf(crossing) < 0.5:
			continue
		var probe := center + outward * signf(crossing) * 1.6
		if clear_line(seen + Vector3.UP * 0.8, probe + Vector3.UP * 0.8):
			return probe
	return seen

func wander_point(origin: Vector3, center: Vector3, radius: float) -> Vector3:
	var zone := layout.zone_at(origin)
	if zone < 0:
		return origin
	var map := get_world_3d().navigation_map
	for attempt in range(5):
		var sample := center + Vector3(randf_range(-radius, radius), 0, randf_range(-radius, radius))
		var point := NavigationServer3D.map_get_closest_point(map, sample)
		if layout.zone_at(point) == zone and point.distance_to(origin) > 0.8:
			return point
	return origin

func chase_position(zombie: Zombie, target: Vector3) -> Vector3:
	var offset := zombie.global_position - target
	var flat := Vector3(offset.x, 0, offset.z)
	return target + flat.normalized() * 1.6

func can_grab(zombie: Zombie) -> bool:
	if round_finished or debug_invincible or walker.role != Walker.HUMAN or zombie.stun_remaining > 0.0:
		return false
	var offset := walker.global_position - zombie.global_position
	if offset.length_squared() > zombie_attack_range * zombie_attack_range or absf(offset.y) > 0.72:
		return false
	return clear_line(zombie.global_position + Vector3.UP * 1.0, walker.global_position + Vector3.UP * 1.0) \
		and clear_line(zombie.global_position + Vector3.UP * 0.45, walker.global_position + Vector3.UP * 0.45)

func reserve_bite(zombie: Zombie) -> bool:
	if not is_multiplayer_authority() or is_instance_valid(bite_owner) or not can_grab(zombie):
		return false
	bite_owner = zombie
	grab_remaining = GRAB_DURATION
	grab_struggles = 0
	grab_damaged = false
	walker.set_meta(&"campus_grabbed", true)
	if walker.has_method("play_hand_action"):
		walker.play_hand_action(&"grab")
	_report("丧尸抓住了你！连按两次空格挣脱，或按 G 推开。", 2.0)
	return true

func is_player_grabbed() -> bool:
	return is_instance_valid(bite_owner) and grab_remaining > 0.0 and not round_finished and walker.role == Walker.HUMAN

func release_bite(zombie: Zombie) -> void:
	if bite_owner != zombie:
		return
	bite_owner = null
	grab_remaining = 0.0
	grab_struggles = 0
	grab_damaged = false
	if is_instance_valid(walker):
		walker.set_meta(&"campus_grabbed", false)

func struggle_grab() -> void:
	if not is_player_grabbed():
		return
	grab_struggles += 1
	if walker.has_method("play_hand_action"):
		walker.play_hand_action(&"hit")
	if grab_struggles >= GRAB_ESCAPE_PRESSES:
		var zombie := bite_owner
		release_bite(zombie)
		zombie.stun(0.65)
		_report("你挣脱了抓握。", 1.5)
	else:
		_report("再按一次空格挣脱！", 1.0)

func _update_grab(delta: float) -> void:
	if not is_instance_valid(bite_owner):
		grab_remaining = 0.0
		walker.set_meta(&"campus_grabbed", false)
		return
	if not can_grab(bite_owner):
		release_bite(bite_owner)
		return
	grab_remaining = maxf(0.0, grab_remaining - delta)
	if grab_remaining <= 0.0:
		release_bite(bite_owner)
		return
	var offset := bite_owner.global_position - walker.global_position
	offset.y = 0.0
	var distance := offset.length()
	if distance > GRAB_SEPARATION:
		var motion := offset.normalized() * minf(GRAB_PULL_SPEED * delta, distance - GRAB_SEPARATION)
		walker.move_and_collide(motion)

func resolve_bite(zombie: Zombie) -> void:
	if bite_owner != zombie or grab_damaged:
		return
	if not can_grab(zombie):
		release_bite(zombie)
		return
	grab_damaged = true
	_player_bitten()

func _player_bitten(from_room_host := false) -> void:
	if (not is_multiplayer_authority() and not from_room_host) or round_finished or debug_invincible or walker.role != Walker.HUMAN:
		return
	walker.stagger_remaining = 0.42
	if armor > 0:
		armor -= 1
		_report("胶布挡住了一次咬击。", 2.5)
	else:
		player_health = maxi(0, player_health - ZOMBIE_BITE_DAMAGE)
		if player_health == 0:
			_turn_player()
		elif infection < 0.0:
			infection = INFECTION_SECONDS
			_report("你被咬伤了。转化前仍可撤离。", 4.0)
	_update_hud()
	Audio.play_3d("res://assets/audio/hurt.ogg", walker.global_position, -10.0, 0.05, 12.0)

func set_debug_invincible(enabled: bool) -> void:
	if not enable_debug_tools:
		return
	debug_invincible = enabled
	if enabled:
		infection = -1.0
		release_bite(bite_owner)
		walker.stagger_remaining = 0.0
	_update_hud()

func set_debug_flight(enabled: bool) -> void:
	if not enable_debug_tools:
		return
	release_bite(bite_owner)
	walker._set_flying(enabled)
	if not enabled:
		walker.collision_mask |= Actor.ACTOR_LAYER
	_update_hud()

func _turn_player() -> void:
	infection = 0.0
	release_bite(bite_owner)
	if armed_campaign:
		_finish("撤离失败 · 已被感染")
		return
	if held != &"":
		var body: RigidBody3D = props[held]
		body.freeze = false
		body.sleeping = false
		held = &""
		walker.hands.set_holding(false)
	walker.set_role(walker.identity, Walker.KING)
	walker.camera.fov = minf(Settings.fov, 65.0)
	walker.follow_camera.fov = walker.camera.fov
	walker.camera.far = 18.0
	walker.follow_camera.far = 18.0
	ability_cooldown = 0.0
	var message := "已转化为僵尸王。G 标记地面。" if armed_campaign \
		else "已转化为僵尸王。G 标记地面，AI同学正在撤离。"
	_report(message, 6.0)

func _footstep(at: Vector3, _strength: float) -> void:
	if walker.role == Walker.HUMAN:
		_emit_sound(at, zombie_chase_distance, &"step")

func _emit_sound(point: Vector3, strength: float, kind: StringName, door_index := -1) -> void:
	if is_instance_valid(coop_session) and not Net.is_host():
		return
	var source := layout.zone_at(point)
	if source < 0:
		return
	sound_id += 1
	var energy: Dictionary = {source: strength}
	var arrivals: Dictionary = {source: point}
	var relays: Dictionary = {}
	var settled: Dictionary = {}
	while true:
		var area := -1
		var remaining := 0.0
		for candidate: int in energy:
			if not settled.has(candidate) and energy[candidate] > remaining:
				area = candidate
				remaining = energy[candidate]
		if area < 0:
			break
		settled[area] = true
		for passage in layout.passages:
			if area not in [passage.from, passage.to]:
				continue
			var next: int = passage.to if passage.from == area else passage.from
			if settled.has(next):
				continue
			var door: int = passage.door
			var closed := door >= 0 and not door_is_open(door)
			var entry: Vector3 = passage.point
			var origin: Vector3 = arrivals[area]
			var new_energy := remaining - origin.distance_to(entry) - (6.0 if closed else 0.8)
			if new_energy <= float(energy.get(next, 0.0)):
				continue
			energy[next] = new_energy
			arrivals[next] = entry
			relays[next] = door_point(door, -1.0 if next == passage.from else 1.0) if closed else relays.get(area, point)
	for zombie in spawner.zombies:
		if kind == &"step" and zombie.global_position.distance_to(point) > zombie_chase_distance:
			continue
		var area := layout.zone_at(zombie.global_position)
		if not energy.has(area):
			continue
		var arrival: Vector3 = arrivals[area]
		if zombie.global_position.distance_to(arrival) <= float(energy[area]):
			if kind == &"step" and area == source:
				if absf(point.y - zombie.global_position.y) > 1.9:
					continue
				if not clear_line(point + Vector3.UP * 0.7, zombie.global_position + Vector3.UP * 0.7):
					# Replace older pending footfalls for this listener. A horde
					# receives bounded path work across frames, not one spike.
					pending_step_sounds[zombie] = {"point": point, "radius": strength,
						"id": sound_id, "time": elapsed}
					continue
			var same_side := area == source
			if door_index >= 0 and same_side and zombie.can_receive_order():
				zombie.join_door(door_index)
			else:
				zombie.approach_noise(relays.get(area, point), sound_id, kind)

func _service_step_sounds() -> void:
	var requests := 0
	var deadline := Time.get_ticks_usec() + HEARING_BUDGET_USEC
	for actor in pending_step_sounds.keys():
		var event: Dictionary = pending_step_sounds[actor]
		pending_step_sounds.erase(actor)
		if not is_instance_valid(actor) or actor.defeated or elapsed - float(event.time) > 1.5:
			continue
		if int(event.id) <= actor.heard_id:
			continue
		requests += 1
		if _step_can_reach(event.point, actor.global_position, event.radius):
			actor.approach_noise(event.point, event.id, &"step")
		if requests >= HEARING_PATHS_PER_FRAME or Time.get_ticks_usec() >= deadline:
			break

func _step_can_reach(source: Vector3, listener: Vector3, radius: float) -> bool:
	# Broad outside zones include stacked slabs and enclosed courtyards. Trace
	# blocked sounds along the navigation surface, bounded to this sound event.
	if source.distance_to(listener) > radius or absf(source.y - listener.y) > 1.9:
		return false
	if clear_line(source + Vector3.UP * 0.7, listener + Vector3.UP * 0.7):
		return true
	var path := NavigationServer3D.map_get_path(get_world_3d().navigation_map, listener, source, true)
	if path.size() < 2 or path[-1].distance_to(source) > 0.8 or path[0].distance_to(listener) > 0.8:
		return false
	var travelled := 0.0
	for index in range(1, path.size()):
		travelled += path[index - 1].distance_to(path[index])
		if travelled > radius:
			return false
		if not clear_line(path[index - 1] + Vector3.UP * 0.7, path[index] + Vector3.UP * 0.7):
			return false
	return true

func door_is_open(index: int) -> bool:
	return doors.doors[index].open and not doors.doors[index].moving

func closed_door_between(at: Vector3, destination_zone: int) -> int:
	var start := layout.zone_at(at)
	if start < 0 or destination_zone < 0 or start == destination_zone:
		return -1
	var closest := -1
	var best := 14.0
	for passage: Dictionary in layout.passages:
		var index: int = passage.door
		if index < 0 or start not in [passage.from, passage.to]:
			continue
		var leads_to_target := destination_zone in [passage.from, passage.to]
		var leaves_room: bool = start == passage.from and bool(doors.doors[index].get("lockable", not use_full_campus))
		if not leads_to_target and not leaves_room:
			continue
		if door_is_open(index):
			if doors.doors[index].get("lockable", not use_full_campus):
				return -1
			continue
		var distance := at.distance_to(passage.point)
		if distance < best:
			best = distance
			closest = index
	return closest

func door_side(index: int, at: Vector3) -> float:
	var door: Dictionary = doors.doors[index]
	var outward: Vector3 = door.get("outward", Vector3.BACK)
	return -1.0 if outward.dot(at - (door.center as Vector3)) < 0.0 else 1.0

func door_point(index: int, side: float) -> Vector3:
	var door: Dictionary = doors.doors[index]
	var outward: Vector3 = door.get("outward", Vector3.BACK)
	return door.center + outward * side * 0.91

func door_wait_point(zombie: Zombie) -> Vector3:
	var slot := maxi(0, _door_group(zombie).find(zombie))
	var lane := 0.54 if slot % 2 == 0 else -0.54
	var point := door_point(zombie.door_index, zombie.door_side)
	var outward: Vector3 = doors.doors[zombie.door_index].get("outward", Vector3.BACK)
	var tangent := Vector3(outward.z, 0, -outward.x)
	if slot < 2:
		return point + tangent * lane
	return point + tangent * (slot - 3) * 1.12 + outward * zombie.door_side * 0.60

func _door_group(zombie: Zombie) -> Array[Zombie]:
	return spawner.zombies.filter(func(other: Zombie):
		return other.door_index == zombie.door_index and other.door_side == zombie.door_side)

func can_knock(zombie: Zombie) -> bool:
	return _door_group(zombie).find(zombie) in [0, 1]

func knock(zombie: Zombie) -> void:
	Audio.play_3d("res://assets/audio/impact.ogg", doors.doors[zombie.door_index].center, -12.0, 0.14, 21.0)
	if door_cycles.has(zombie.door_index):
		return
	door_cycles[zombie.door_index] = true
	_emit_sound(door_point(zombie.door_index, zombie.door_side), 10.7, &"knock", zombie.door_index)

func _door_changed(index: int, opened: bool) -> void:
	for passage: Dictionary in layout.passages:
		if passage.door == index:
			passage.link.enabled = opened
			break
	if opened:
		door_cycles.erase(index)
	for zombie in spawner.zombies:
		zombie.door_changed(index)
	_emit_sound(doors.doors[index].center, 8.0, &"door")
	Audio.play_3d("res://assets/audio/ui_click.ogg", doors.doors[index].center + Vector3.UP, -15.0, 0.05, 20.0)

func lock_door() -> void:
	if round_finished:
		return
	var index := _closest_lockable_door(walker.global_position, 2.45)
	if index < 0:
		_report("从教室内靠近门按 L 上锁或解锁。")
		return
	var door: Dictionary = doors.doors[index]
	if door.open or door.moving:
		_report("先关门，再按 L 上锁。")
		return
	door.locked = not door.locked
	_report("教室门已上锁。" if door.locked else "教室门已解锁。")

func _closest_lockable_door(at: Vector3, limit: float) -> int:
	var index := -1
	var zone := layout.zone_at(at)
	for candidate in doors.doors.size():
		var door: Dictionary = doors.doors[candidate]
		if not door.get("lockable", not use_full_campus) or zone != int(door.get("inside_zone", candidate)):
			continue
		if use_full_campus and (at - (door.center as Vector3)).dot(door.outward) >= 0.0:
			continue
		var distance := at.distance_to(door.center)
		if distance < limit:
			limit = distance
			index = candidate
	return index

func _make_prop(kind: StringName) -> void:
	var info: Array = PROP_INFO[kind]
	var body := RigidBody3D.new()
	body.position = info[1]
	if use_full_campus:
		var offset: Vector3 = {&"book": Vector3(0.10, 0.02, 1.09), &"tape": Vector3(0.12, 0.02, 0.52),
			&"brick": Vector3(11.7, 0.08, 8.0)}[kind]
		body.position = walker.spawn.position + offset
	body.freeze = true
	body.collision_layer = 0
	body.collision_mask = 1 | (Actor.ACTOR_LAYER if kind == &"brick" else 0)
	body.contact_monitor = true
	body.max_contacts_reported = 4
	add_child(body)
	layout._box_on(body, info[2], info[3], true)
	body.body_entered.connect(_prop_hit.bind(kind))
	props[kind] = body

func interact_book() -> bool:
	if round_finished:
		return true
	var picked: StringName = &""
	var distance := 2.35
	for kind: StringName in props:
		var item: RigidBody3D = props[kind]
		var offset := item.global_position - walker.camera.global_position
		if kind == held or offset.length() >= distance or (-walker.camera.global_basis.z).dot(offset.normalized()) < 0.52:
			continue
		if clear_line(walker.camera.global_position, item.global_position):
			picked = kind
			distance = offset.length()
	if picked == &"":
		return false
	if picked == &"tape":
		if armor == 0:
			armor = 1
			walker.play_hand_action(&"pickup")
			props[picked].queue_free()
			props.erase(picked)
			_report("已缠护臂胶布，可挡一次咬击。")
			_update_hud()
		return true
	if held != &"":
		_report("按 Q 投出道具，或切枪放下。")
		return true
	held = picked
	walker.hands.set_holding(true)
	walker.play_hand_action(&"pickup")
	thrown.erase(picked)
	var body: RigidBody3D = props[picked]
	body.freeze = true
	body.linear_velocity = Vector3.ZERO
	body.angular_velocity = Vector3.ZERO
	_report("拾取%s。按 Q 投掷，切枪可放下。" % PROP_INFO[picked][0])
	walker.look.perform(&"pick-up")
	return true

func _follow_held_prop() -> void:
	if held != &"":
		props[held].global_transform = walker.hand_attachment.global_transform

func put_down_held_prop() -> void:
	var body: RigidBody3D = props[held]
	body.global_position = walker.global_position + Vector3.UP * 0.35
	body.linear_velocity = Vector3.ZERO
	body.angular_velocity = Vector3.ZERO
	body.freeze = false
	body.sleeping = false
	held = &""
	walker.hands.set_holding(false)
	if walker.hands.action in [&"pickup", &"pick-up"]:
		walker.hands.action = &""
	if walker.look.gesture in [&"pickup", &"pick-up"]:
		walker.look.cancel_gesture()

func throw_book() -> void:
	if held == &"" or round_finished:
		return
	var body: RigidBody3D = props[held]
	body.global_position = walker.camera.global_position
	body.freeze = false
	body.sleeping = false
	body.linear_velocity = -walker.camera.global_basis.z * 8.5 + Vector3.UP * 1.9
	body.angular_velocity = walker.global_basis.x * 8.0
	thrown[held] = true
	held = &""
	walker.hands.set_holding(false)
	walker.play_hand_action(&"throw")
	walker.look.perform(&"interact-right", 1.3)

func _prop_hit(body: Node, kind: StringName) -> void:
	if not thrown.has(kind):
		return
	if not body is Zombie and not body is StaticBody3D:
		return
	thrown.erase(kind)
	var item: RigidBody3D = props[kind]
	if kind == &"brick" and body is Zombie:
		body.stun(2.7)
		_report("砖头打晕了丧尸。")
	_emit_sound(item.global_position, 17.0 if kind == &"book" else 13.5, kind)
	Audio.play_3d("res://assets/audio/impact.ogg", item.global_position, -9.0, 0.12, 22.0)

func use_ability() -> void:
	if is_player_grabbed():
		var zombie := bite_owner
		release_bite(zombie)
		zombie.stun(0.65)
		if walker.has_method("play_hand_action"):
			walker.play_hand_action(&"hit")
		_report("你推开了丧尸。", 1.5)
		return
	if round_finished or ability_cooldown > 0.0:
		return
	if walker.role == Walker.KING:
		_king_order()
	elif walker.identity == 3:
		var victim := _near_facing_zombie()
		if victim:
			ability_cooldown = 5.5
			walker.look.perform(&"attack-melee-right")
			walker.play_hand_action(&"hit")
			victim.stun(2.7)
			_report("%s打晕一只丧尸。" % Walker.Look.NAMES[3])
		else:
			_report("靠近并面向丧尸后按 G。")
	else:
		_report("%s按住 Shift 加速，可引开丧尸。" % Walker.Look.NAMES[2])

func _near_facing_zombie() -> Zombie:
	var victim: Zombie
	var nearest := 1.95
	for zombie in spawner.zombies:
		var offset := zombie.global_position - walker.global_position
		if offset.length() < nearest and (-walker.global_basis.z).dot(offset.normalized()) > 0.48:
			if clear_line(walker.camera.global_position, zombie.global_position + Vector3.UP):
				nearest = offset.length()
				victim = zombie
	return victim

func king_bite() -> void:
	if round_finished or walker.role != Walker.KING or king_bite_cooldown > 0.0:
		return
	king_bite_remaining = 0.54
	king_bite_cooldown = 1.8
	walker.stagger_remaining = 0.28
	walker.look.perform(&"attack-melee-right")
	walker.play_hand_action(&"hit")

func _resolve_king_bite() -> void:
	if not is_instance_valid(guide):
		return
	var offset := guide.global_position - walker.global_position
	if offset.length() > Zombie.BITE_RANGE or (-walker.global_basis.z).dot(offset.normalized()) < 0.60:
		return
	if clear_line(walker.global_position + Vector3.UP * 1.4, guide.global_position + Vector3.UP):
		guide.stun(1.15)
		_report("AI同学踉跄了一下，仍可继续撤离。")

func _king_order() -> void:
	var eye := walker.camera.global_position
	var ray := PhysicsRayQueryParameters3D.create(eye, eye - walker.camera.global_basis.z * 12.0, 1)
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	if hit.is_empty() or hit.normal.y < 0.65:
		_report("朝可通行的地面按 G 标记。")
		return
	var map := get_world_3d().navigation_map
	var point := NavigationServer3D.map_get_closest_point(map, hit.position)
	if point.distance_to(hit.position) > 0.68 or command_at(point) == 0:
		_report("附近无可接令的丧尸，或标记点被门隔开。")
		return
	ability_cooldown = 8.0
	walker.look.perform(&"emote-yes")

func command_at(point: Vector3) -> int:
	var occupied := spawner.zombies.filter(func(zombie: Zombie): return zombie.command_owner).size()
	var candidates := spawner.zombies.filter(func(zombie: Zombie):
		return zombie.can_receive_order() and zombie.global_position.distance_to(walker.global_position) <= 12.0)
	candidates.sort_custom(func(a: Zombie, b: Zombie):
		return a.global_position.distance_squared_to(walker.global_position) < b.global_position.distance_squared_to(walker.global_position))
	var sent := 0
	for zombie: Zombie in candidates:
		if sent + occupied >= 2:
			break
		var path := NavigationServer3D.map_get_path(get_world_3d().navigation_map, zombie.global_position, point, true)
		if path.size() < 2 or path[-1].distance_to(point) > 0.5:
			continue
		zombie.command(point)
		sent += 1
	if sent:
		_report("已指挥 %d 只丧尸前往标记点。" % sent)
	return sent

func _build_hud() -> void:
	var panel := PanelContainer.new()
	controls_panel = panel
	panel.name = "ControlInstructions"
	panel.position = Vector2(20, 20)
	var debug_panel: Control = interface.get_node("DebugControls")
	debug_panel.hide()
	panel.add_theme_stylebox_override("panel", debug_panel.get_theme_stylebox("panel"))
	interface.add_child(panel)
	var rows := VBoxContainer.new()
	panel.add_child(rows)
	briefing = Label.new()
	if armed_campaign:
		objective_panel = PanelContainer.new()
		objective_panel.name = "CurrentObjective"
		objective_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
		interface.add_child(objective_panel)
		objective_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
		var objective_style := StyleBoxFlat.new()
		objective_style.bg_color = Color(0.055, 0.075, 0.10, 0.95)
		objective_style.border_color = Color("#e9bc63")
		objective_style.set_border_width_all(2)
		objective_style.set_corner_radius_all(10)
		objective_style.content_margin_left = 20
		objective_style.content_margin_right = 20
		objective_style.content_margin_top = 12
		objective_style.content_margin_bottom = 12
		objective_panel.add_theme_stylebox_override("panel", objective_style)
		objective_panel.add_child(briefing)
		briefing.mouse_filter = Control.MOUSE_FILTER_IGNORE
		briefing.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		briefing.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		briefing.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		briefing.add_theme_font_size_override("font_size", 22)
		briefing.add_theme_color_override("font_shadow_color", Color.BLACK)
		briefing.add_theme_constant_override("shadow_offset_y", 2)
		briefing.text = "当前目标 · 沿西梯上最高五层，在室内走廊寻找武器"
		briefing.resized.connect(func(): briefing.pivot_offset = briefing.size * 0.5)
		var pulse := create_tween().set_loops().set_parallel().set_trans(Tween.TRANS_SINE)
		briefing.self_modulate = Color("#f9f4db")
		pulse.tween_property(briefing, "self_modulate", Color("#ffd070"), 0.80)
		pulse.parallel().tween_property(briefing, "scale", Vector2(1.02, 1.02), 0.80)
		pulse.parallel().tween_property(objective_panel, "modulate:a", 0.88, 0.80)
		pulse.chain().tween_property(briefing, "self_modulate", Color("#f9f4db"), 0.80)
		pulse.parallel().tween_property(briefing, "scale", Vector2.ONE, 0.80)
		pulse.parallel().tween_property(objective_panel, "modulate:a", 1.0, 0.80)
		get_viewport().size_changed.connect(_layout_objective_panel)
		panel.resized.connect(_layout_objective_panel)
		objective_panel.minimum_size_changed.connect(_layout_objective_panel)
	controls = Label.new()
	rows.add_child(controls)
	if not armed_campaign:
		briefing.text = "AI同学：隔壁有动静。先拿脚边的胶布，按 C 静步，再去看走廊。"
		rows.add_child(briefing)
	feedback = Label.new()
	feedback.add_theme_color_override("font_color", Color("#ffd196"))
	rows.add_child(feedback)
	doors.hint.reparent(rows, false)
	doors.hint.hide()
	health_hud = PlayerHealth.new()
	interface.add_child(health_hud)
	var crosshair := Label.new()
	interface.add_child(crosshair)
	crosshair.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	crosshair.offset_left = -6.0
	crosshair.offset_top = -14.0
	crosshair.text = "+"
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	result_panel = PanelContainer.new()
	interface.add_child(result_panel)
	result_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	result_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	result_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	var result_rows := VBoxContainer.new()
	result_panel.add_child(result_rows)
	result = Label.new()
	result.custom_minimum_size = Vector2(340, 54)
	result.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	result.add_theme_font_size_override("font_size", 24)
	result.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	result_rows.add_child(result)
	if armed_campaign and (not Net.campus_room or Net.is_host()):
		var explore := Button.new()
		explore.text = "全队进入自由探索" if Net.campus_room else "自由探索"
		explore.pressed.connect(_begin_free_roam)
		result_rows.add_child(explore)
	if not Net.campus_room:
		var restart := Button.new()
		restart.text = "再玩一局"
		restart.pressed.connect(func(): get_tree().reload_current_scene())
		result_rows.add_child(restart)
	var home := Button.new()
	home.text = "退出房间" if Net.campus_room else "返回主菜单"
	home.pressed.connect(_leave_result)
	result_rows.add_child(home)
	result_panel.hide()
	_update_hud()
	if armed_campaign:
		_layout_objective_panel.call_deferred()

func _layout_objective_panel() -> void:
	if not is_inside_tree() or not is_instance_valid(objective_panel):
		return
	var viewport_size := get_viewport().get_visible_rect().size
	var width := minf(820.0, viewport_size.x - 32.0)
	var height := maxf(74.0, objective_panel.get_combined_minimum_size().y)
	objective_panel.offset_left = -width * 0.5
	objective_panel.offset_right = width * 0.5
	objective_panel.offset_top = 16.0
	objective_panel.offset_bottom = 16.0 + height
	# Reserve the top band for the mission. The control reference moves down
	# only when its horizontal span would overlap this centered panel.
	controls_panel.position = Vector2(20, 20)
	if objective_panel.visible and controls_panel.get_rect().intersects(objective_panel.get_rect()):
		controls_panel.position.y = objective_panel.get_rect().end.y + 12
	if is_instance_valid(debug_toggle):
		debug_toggle.offset_top = 56
		debug_toggle.offset_bottom = 92
		if objective_panel.visible and debug_toggle.get_global_rect().intersects(objective_panel.get_global_rect()):
			debug_toggle.offset_top = objective_panel.get_rect().end.y + 12
			debug_toggle.offset_bottom = debug_toggle.offset_top + 36

func _update_hud() -> void:
	var identity: String = Walker.Look.NAMES[walker.identity]
	var status := identity
	if walker.role == Walker.KING:
		status += " · 僵尸王" + ("（标记冷却 %.0f 秒）" % ceilf(ability_cooldown) if ability_cooldown > 0 else "")
	var weapon_keys := "1–5" if armed_campaign else "1–3"
	var controls_hint := "WASD 移动  Shift 跑  空格 跳跃／挣脱  Ctrl 蹲  C 静步\n左键 射击  右键 瞄准  R 换弹  %s 切枪  X 收枪\nE 拾取／开门  L 上锁  Q 投掷  G 能力  V 视角  Esc 返回" % weapon_keys
	if walker.role == Walker.KING:
		controls_hint = "WASD 移动  Shift 加速  左键咬击  G 标记地面  Esc 返回"
		if armed_campaign:
			controls_hint = "WASD 移动  Shift 加速  G 标记地面  Esc 返回"
	if debug_invincible:
		status += " · 无敌"
	if walker.flying:
		status += " · 飞行（空格上升／Ctrl下降）"
	controls.text = "%s   |   丧尸 %d/%d\n%s" % [status, spawner.zombies.size(), Spawner.ACTIVE_LIMIT, controls_hint]
	controls_panel.reset_size()
	health_hud.visible = walker.role == Walker.HUMAN
	if health_hud.visible:
		health_hud.update_status(player_health, PLAYER_MAX_HEALTH, maxi(0, ceili(infection)), armor > 0)
	briefing.visible = (armed_campaign or not left_classroom) and walker.role == Walker.HUMAN
	if is_instance_valid(objective_panel):
		objective_panel.visible = briefing.visible and not round_finished
		_layout_objective_panel()
	feedback.visible = elapsed < feedback_until

func _report(message: String, duration := 3.0) -> void:
	feedback.text = message
	feedback_until = elapsed + duration
	feedback.show()

func _finish(message: String) -> void:
	if round_finished:
		return
	release_bite(bite_owner)
	round_finished = true
	if is_instance_valid(guide):
		guide.halt()
	result.text = message
	result_panel.show()
	if is_instance_valid(objective_panel):
		objective_panel.hide()
	walker.movement_locked = true
	walker._capture_mouse(false)


func _leave_result() -> void:
	if walker.leave_session.is_valid():
		walker.leave_session.call()
	else:
		get_tree().change_scene_to_file("res://scenes/main_menu.tscn")


func _begin_free_roam() -> void:
	if Net.campus_room:
		Net.start_campus_exploration()
		return
	var error := get_tree().change_scene_to_file(CampusTour.SCENE)
	if error != OK:
		result.text = "自由探索加载失败，请重试"
