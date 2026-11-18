extends SceneTree

var failed := false
var world: Node3D
var level: Node3D
var campaign: Node3D

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	create_timer(90.0).timeout.connect(func(): quit(1))
	change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await scene_changed
	world = current_scene
	level = world.get_node("CharacterTrial")
	campaign = level.campaign
	level.walker.set_physics_process(false)
	level.set_debug_invincible(true)
	campaign.set_physics_process(false)
	await wait_frames(8)
	await wait_navigation(level.layout.dorm_start + level.layout.dorm_axis * 28.0)
	await place(campaign.upper_landing)
	var top_pickups: Array = campaign.supplies.filter(func(item): return item.encounter == &"roof")
	var field_pickups: Array = campaign.supplies.filter(func(item): return item.encounter == &"field")
	check(top_pickups.size() == 1 and field_pickups.size() == 1, "solo receives one random gun in each of two scenes")
	check(not top_pickups.is_empty() and top_pickups.all(func(item): return absf(item.point.y - 15.48) < 0.15),
		"starting guns belong to the highest indoor floor")
	await check_party_supplies()
	campaign.roof_count = 1
	campaign.field_count = 1
	var passages = load("res://scripts/campus/campus_field_passages.gd")
	await place(passages.APPROACH[1])
	await place(passages.EXIT[1] + Vector3(0.2, 0, 0))
	check(campaign.left_track, "one field pickup does not lock the stand exit")
	campaign.plaza_wave = true
	await place(Vector3(-62.5991, 0.57, -194.4857))
	check(not campaign.dorm_entered, "walking outside the dorm north wall does not start the ambush")
	var entry: Dictionary = campaign.dorm_entries[0]
	var inside: Vector3 = entry.point + entry.inward * 1.8
	await place(inside)
	check(campaign.dorm_entered, "entering the dorm through the main hall starts the corridor ambush")
	await wait_frames(50)
	if not level.spawner.zombies.any(func(zombie): return zombie.encounter == &"dorm_corridor"):
		print("AMBUSH DIAGNOSTIC ", level.spawner.encounters.get(&"dorm_corridor"))
		for index in 5:
			var sample: Vector3 = level.spawner._encounter_sample(&"dorm_corridor", level.walker.global_position,
				level.spawner.encounters[&"dorm_corridor"].origin)
			var point := NavigationServer3D.map_get_closest_point(world.get_world_3d().navigation_map, sample)
			var pending: Array[Vector3] = []
			print("AMBUSH SAMPLE ", sample, " -> ", point, " zone ", level.layout.zone_at(point),
				" valid ", level.spawner._valid_point(point, level.walker, pending, true))
	var ambush: Array = level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"dorm_corridor")
	check(ambush.size() >= 8, "corridor ambush creates a crowd promptly")
	var origin: Vector3 = level.spawner.encounters[&"dorm_corridor"].origin
	check(not ambush.is_empty() and ambush.all(func(zombie): return \
		(zombie.patrol_center - origin).dot(level.layout.dorm_axis) > 7.0 \
		and absf(zombie.patrol_center.y - origin.y) < 0.5), "main-hall ambush spawns on the right side of the first-floor corridor")
	campaign.dorm_left = false
	campaign.left_track = false
	await place(campaign.PLAZA)
	check(campaign.finale_supplies_ready and not campaign.finale_started,
		"final route supplies appear before the horde without hidden route flags")
	var final_pickups: Array = campaign.supplies.filter(func(item): return item.encounter == &"final_gate")
	check(final_pickups.size() == 3, "three minigun pickups are present at the gate")
	await place(final_pickups[0].point)
	check(campaign.final_weapon_count == 1 and not campaign.finale_started, "player can take a minigun before the finale")
	campaign._physics_process(6.1)
	check(campaign.finale_started, "warning countdown starts the finale after preparation")
	await place(campaign.MAIN_GATE_OUTSIDE - Vector3(0, 0, 2.0))
	check(not level.round_finished, "inside the final exit does not complete the run")
	check(campaign._crossed_main_gate(Vector3(-8, 0.2, 11.5)) \
		and campaign._crossed_main_gate(Vector3(8, 0.2, 11.5)), "both side pedestrian gate exits count as evacuation")
	check(campaign._crossed_main_gate(Vector3(14, 0.2, 11.5)), "a diagonal step crossing within the gate still completes evacuation")
	var saved_position: Vector3 = campaign.last_position
	campaign.last_position = Vector3.INF
	check(not campaign._crossed_main_gate(Vector3(14, 0.2, 11.5)) \
		and not campaign._crossed_main_gate(Vector3(0, 8, 11.5)), "outside the gate width and upper floors do not finish the run")
	campaign.last_position = saved_position
	await place(campaign.MAIN_GATE_OUTSIDE + Vector3(8, 0, 1.0))
	check(level.round_finished, "walking beyond the gate completes the run")
	print("CAMPAIGN ROUTE ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func check_party_supplies() -> void:
	var net := root.get_node("Net")
	var saved_players: Dictionary = net.players.duplicate(true)
	var saved_room: bool = net.campus_room
	var campaign_script = load("res://scripts/campus/campus_armed_campaign.gd")
	for count in range(1, 11):
		net.campus_room = true
		net.players.clear()
		for id in count:
			net.players[id + 1] = {"name": "Test %d" % id}
		var trial: Node3D = campaign_script.new()
		trial.level = level
		level.add_child(trial)
		trial.set_physics_process(false)
		var top: Array = trial.supplies.filter(func(item): return item.encounter == &"roof")
		var field: Array = trial.supplies.filter(func(item): return item.encounter == &"field")
		check(top.size() + field.size() == maxi(2, count) and top.size() >= 1 and field.size() >= 1,
			"%d-player roster creates the shared gun quota across both scenes" % count)
		check((top + field).all(func(item): return item.grants.size() == 1 \
			and item.grants[0][0] in trial.RANDOM_WEAPONS and item.grants[0][2]), "quota pickups each grant one random gun")
		trial.queue_free()
		await process_frame
	net.players = saved_players
	net.campus_room = saved_room

func place(at: Vector3) -> void:
	level.walker.global_position = at
	world.refresh_collision()
	await wait_frames(3)
	campaign._physics_process(1.0 / 60.0)

func wait_frames(count: int) -> void:
	for frame in count:
		await physics_frame

func wait_navigation(at: Vector3) -> void:
	var map := world.get_world_3d().navigation_map
	for frame in 600:
		if NavigationServer3D.map_get_iteration_id(map) > 0 \
				and NavigationServer3D.map_get_closest_point(map, at).distance_to(at) < 1.0:
			return
		await physics_frame
	check(false, "campus navigation surface finishes loading")

func check(ok: bool, description: String) -> void:
	print("PASS " if ok else "FAIL ", description)
	failed = failed or not ok
