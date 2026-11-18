extends SceneTree

var failed := false
var world: Node3D
var level: Node3D
var campaign: Node3D

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	create_timer(110.0).timeout.connect(func(): quit(1))
	change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await scene_changed
	world = current_scene
	level = world.get_node("CharacterTrial")
	campaign = level.campaign
	level.walker.set_physics_process(false)
	campaign.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.debug_invincible = true
	await wait_navigation(level.layout.west_stair_lobby)
	for id in ["B15_1", "B15_2", "B21_bridge_north", "B21_bridge_south", "B22_1", "B22_2"]:
		var index: int = level.doors._index_for_id(id)
		var door: Dictionary = level.doors.doors[index]
		var outside: Vector3 = door.center + door.outward * 1.5
		check(not campaign._approaches_plaza(outside) and not campaign._on_direct_plaza_approach(outside),
			"unrelated building exit does not trigger Shangde crowd: " + id)
	var field = load("res://scripts/campus/campus_field_passages.gd")
	for index in field.EXIT.size():
		await place(field.EXIT[index] + Vector3.RIGHT * 1.0)
		check(not level.spawner.encounters.has(&"plaza"), "stand exit %d leaves the plaza encounter idle" % (index + 1))
	check(not campaign._approaches_plaza(campaign.top_floor_supply), "indoor upper floor never starts outdoor crowd")
	await place(campaign.PLAZA_APPROACH)
	var wave: Dictionary = level.spawner.encounters.get(&"plaza", {})
	check(not wave.is_empty() and not wave.has("direct_peer"), "the marked library approach starts the detour encounter")
	if wave.is_empty():
		quit(1)
		return
	var west_area := Rect2(-43.0, -152.0, 30.0, 52.0)
	await spawn_frames(115)
	var crowd := plaza_crowd()
	check(crowd.size() >= 12, "the library approach creates a navigable crowd")
	check(in_area(crowd, west_area), "the detour crowd stays on the west side of the library")
	check(not crowd.is_empty() and crowd.all(func(zombie): return investigation_covers_route(zombie, campaign.PLAZA_APPROACH)),
		"the detour crowd investigates long enough to walk its actual navigation route")

	# Exhaust the library allocation. Arriving through the intended route
	# must still start a local opening using the remaining shared budget.
	wave.remaining = level.spawner.SHANGDE_RESERVE
	campaign.left_track = true
	campaign.dorm_left = true
	campaign.went_east = true
	var visible_old_enemy = level.spawner._spawn(Vector3(-8, 0.2, -65))
	visible_old_enemy.set_physics_process(false)
	var before := int(wave.spawned)
	await place(campaign.PLAZA)
	check(campaign.direct_plaza_wave and wave.has("direct_peer") and wave.opening_start == before,
		"the intended route also triggers a local opening on arrival")
	check(int(wave.remaining) == level.spawner.SHANGDE_RESERVE, "arrival continues the same budget")
	await spawn_frames(110)
	var arrivals := plaza_crowd().filter(func(zombie): return zombie not in crowd)
	var plaza_area := Rect2(-24.0, -38.0, 48.0, 35.0)
	check(arrivals.size() >= 12 and in_area(arrivals, plaza_area),
		"the reserved crowd appears inside Shangde Plaza")
	check(int(wave.remaining) + arrivals.size() == level.spawner.SHANGDE_RESERVE, "arrival uses only the reserved budget")
	var viewed := Vector3(0, 0.2, -30)
	level.walker.camera.look_at(viewed + Vector3.UP)
	wave.spawned = int(wave.opening_start) + level.spawner.PLAZA_OPENING_COUNT
	check(not level.spawner._encounter_point_allowed(&"plaza", viewed, level.walker, wave),
		"later reinforcements do not visibly appear on the plaza floor")
	campaign.finale_countdown = -1.0
	await place(Vector3(0, 0.2, -77))
	check(is_instance_valid(visible_old_enemy) and level.spawner.zombies.has(visible_old_enemy),
		"preparing miniguns preserves the existing enemies")
	check(campaign.get("finale_supplies_ready") == true and not campaign.finale_started,
		"entering final approach creates supplies before the final wave")
	var final_supplies: Array = campaign.supplies.filter(func(item): return item.encounter == &"final_gate")
	check(final_supplies.size() == 3 and final_supplies.all(func(item): return item.point.z < -55.0 \
		and item.grants == [["minigun", 960, true]]), "three 960-round miniguns stand at the forward preparation area")
	if final_supplies.size() == 3 and final_supplies[0].point.z < -55.0:
		for supply: Dictionary in final_supplies:
			check(standing_clear(supply.point), "minigun pickup has a real standing capsule clearance")
		check(not level.spawner.encounters.has(&"final_gate"), "approaching supplies leaves the final wave idle")
		await place(final_supplies[0].point)
		check(campaign.final_weapon_count == 1 and level.firearms.owned.has("minigun"), "first minigun can be picked up before the wave")
		check(not campaign.finale_started, "first pickup grants preparation time")
		campaign._physics_process(5.0)
		check(not campaign.finale_started, "five seconds of preparation remain free of the final wave")
		campaign._physics_process(1.1)
		check(campaign.finale_started and level.spawner.encounters.has(&"final_gate"), "six seconds after pickup starts the final horde")
		for frame in 65:
			await physics_frame
			level.spawner._continue_encounters(level.walker)
			for zombie in level.spawner.zombies:
				zombie.set_physics_process(false)
		var final_crowd: Array = level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"final_gate")
		check(not final_crowd.is_empty() and final_crowd.all(func(zombie): \
			return investigation_covers_route(zombie, level.walker.global_position)),
			"final horde investigation also covers its full actual navigation route")
	else:
		check(false, "first minigun is accessible before the horde")
	await check_warning_without_pickup()
	# A player who walks past the optional supplies still receives the same
	# warning delay, with the actual gate crossing remaining the final exit.
	await place(campaign.MAIN_GATE_OUTSIDE + Vector3(0, 0, 1))
	check(level.round_finished, "walking beyond the actual gate still completes evacuation")
	print("ENCOUNTER SPACING ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func check_warning_without_pickup() -> void:
	var script = load("res://scripts/campus/campus_armed_campaign.gd")
	var trial: Node3D = script.new()
	trial.level = level
	level.add_child(trial)
	trial.set_physics_process(false)
	level.walker.global_position = Vector3(0, 0.2, -77)
	trial._physics_process(0.016)
	level.walker.global_position.z = -39.0
	trial._physics_process(0.016)
	check(trial.final_weapon_count == 0 and trial.finale_countdown > 5.9 and not trial.finale_started,
		"crossing the warning line without a gun starts a full six-second warning")
	trial._physics_process(5.0)
	check(not trial.finale_started and trial.supplies.filter(func(item): return item.encounter == &"final_gate").size() == 3,
		"warning leaves all three miniguns available before the horde")
	trial._physics_process(1.1)
	check(trial.finale_started, "walking past supplies eventually starts the wave after warning")
	trial.queue_free()
	await process_frame

func spawn_frames(count: int) -> void:
	for frame in count:
		await physics_frame
		level.spawner._continue_encounters(level.walker)
		for zombie in level.spawner.zombies:
			zombie.set_physics_process(false)

func plaza_crowd() -> Array:
	return level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"plaza")

func in_area(actors: Array, area: Rect2) -> bool:
	return not actors.is_empty() and actors.all(func(zombie):
		var at: Vector3 = zombie.patrol_center
		return area.has_point(Vector2(at.x, at.z)))

func investigation_covers_route(zombie: Node3D, target: Vector3) -> bool:
	var path := NavigationServer3D.map_get_path(world.get_world_3d().navigation_map, zombie.patrol_center, target, true)
	var length := 0.0
	for index in range(1, path.size()):
		length += path[index - 1].distance_to(path[index])
	return path.size() >= 2 and float(zombie.state_time) >= length / float(zombie.WALK) + 7.9

func standing_clear(at: Vector3) -> bool:
	var shape := CapsuleShape3D.new()
	shape.radius = 0.3
	shape.height = 1.73
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.collision_mask = 1
	query.transform.origin = at + Vector3.UP * 0.89
	return world.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()

func place(at: Vector3) -> void:
	level.walker.global_position = at
	world.refresh_collision()
	for frame in 5:
		await physics_frame
	campaign._physics_process(1.0 / 60.0)

func wait_navigation(at: Vector3) -> void:
	var map := world.get_world_3d().navigation_map
	for frame in 600:
		if NavigationServer3D.map_get_iteration_id(map) > 0 \
				and NavigationServer3D.map_get_closest_point(map, at).distance_to(at) < 1.0:
			return
		await physics_frame
	check(false, "campus navigation loads")

func check(ok: bool, label: String) -> void:
	print("PASS " if ok else "FAIL ", label)
	failed = failed or not ok
