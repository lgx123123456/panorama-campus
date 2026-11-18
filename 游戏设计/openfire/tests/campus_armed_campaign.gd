extends SceneTree

const FieldPassages = preload("res://scripts/campus/campus_field_passages.gd")

var level: Node3D
var world: Node3D
var walker: CharacterBody3D
var campaign: Node3D
var failed := false

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await scene_changed
	world = current_scene
	level = world.get_node("CharacterTrial")
	walker = level.walker
	walker.set_physics_process(false)
	level.set_debug_invincible(true)
	campaign = level.campaign
	await _wait(6)
	_check(level.firearms.owned.is_empty() and not level.firearms.try_fire(), "unarmed spawn")
	_check(not level.props.has(&"tape") and not is_instance_valid(level.guide), "no opening tape or AI classmate")
	_check(not level.props.has(&"book") and level.held == &"" and not walker.hands.holding,
		"campaign starts empty-handed without the legacy throwable book")
	await _wait(205)
	_check(level.spawner.zombies.any(func(zombie): return zombie.encounter == &""), "ambient director spawns on the teaching floor")
	var debug = level.interface.get_node("CombatDebug")
	debug._open()
	debug._spawn_wave()
	await _wait(120)
	_check(level.feedback.text.begins_with("已刷新 "), "debug spawn button reports reproduced zombies")
	await _place(campaign.PLAZA_APPROACH)
	await _wait(120)
	_check(campaign.plaza_wave and not campaign.field_wave and not campaign.roof_wave, "first plaza visit triggers before any pickup")
	var plaza: Dictionary = level.spawner.encounters.get(&"plaza", {})
	_check(plaza.has("remaining") and int(plaza.remaining) < 400, "early approach spawns a large active opening group")
	await _place(campaign.upper_landing)
	_check(not campaign.interact() and walker.global_position.y < 17.0, "highest floor keeps the player indoors without a roof teleport")
	var top_pickups: Array = campaign.supplies.filter(func(item): return item.encounter == &"roof")
	var field_pickups: Array = campaign.supplies.filter(func(item): return item.encounter == &"field")
	_check(top_pickups.size() == 1 and field_pickups.size() == 1, "solo has one random weapon per scene")
	var expected_ammo := int(top_pickups[0].grants[0][1])
	var gun_area: MeshInstance3D = top_pickups[0].area
	_check(gun_area.visible, "uncollected teaching gun is marked in yellow")
	await _place(top_pickups[0].point + Vector3.DOWN * 3.72)
	_check(campaign.roof_count == 0 and gun_area.visible, "the floor below cannot collect the highlighted gun")
	await _place(top_pickups[0].point)
	_check(campaign.roof_count == 1 and campaign.roof_wave, "walking into the highest-floor marker collects the gun and starts the encounter")
	_check(not is_instance_valid(gun_area), "completed gun marker disappears")
	await _wait(36)
	_check(level.spawner.encounters[&"roof"].remaining < 30, "opening encounter spawns agents")
	_check(level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"roof").all(
		func(zombie): return absf(zombie.global_position.y - 15.48) < 0.5), "opening horde stays on the highest indoor floor")
	_check(not campaign.interact() and _ammo() == expected_ammo, "highest-floor pickup is single use")
	await _place(field_pickups[0].point)
	_check(campaign.field_count == 1 and campaign.field_wave, "walking into the field marker starts the first outdoor horde")
	expected_ammo += int(field_pickups[0].grants[0][1])
	_check(not campaign.interact() and _ammo() == expected_ammo, "field weapon supplies are single use")
	await _wait(55)
	_check(level.spawner.encounters[&"field"].remaining < 95, "field horde spawns a large opening group")
	_check(campaign.field_exit_markers.all(func(area): return area.visible), "all four exits are highlighted")
	_check(campaign.field_passage == -1, "no approach detector has been entered")
	await _place(FieldPassages.EXIT[1] + Vector3(0.18, 0, 0))
	_check(campaign.left_track, "stepping into the exit marker advances the route without the old approach detector")
	_check(campaign.field_exit_markers.all(func(area): return not area.visible), "all field markers disappear once the exit is complete")
	_check(_clear_standing_space(), "field gate outside has standing clearance")
	await _place(campaign.PLAZA_APPROACH)
	_check(level.spawner.encounters[&"plaza"].remaining <= plaza.remaining, "advancing to plaza keeps the same encounter")
	var index: int = level.doors.doors.find_custom(func(door): return door.id == "B25_west_end")
	var passage: Dictionary = level.layout.passages.filter(func(record): return record.door == index)[0]
	await _place(campaign.dorm_start + Vector3(2.1, 0, 0))
	_check(campaign.dorm_entered and level.doors.set_open(index, false), "west dorm door closes from inside")
	await _wait(24)
	_check(level.spawner.zombies.any(func(zombie):
		return zombie.encounter == &"dorm_corridor" and level.layout.zone_at(zombie.global_position) == level.layout.DORM_FLOOR_ONE),
		"entering the dorm spawns a first-floor corridor horde")
	var near: Vector3 = level.door_point(index, 1)
	var far: Vector3 = level.door_point(index, -1)
	_check(not passage.link.enabled and not level.clear_line(near + Vector3.UP, far + Vector3.UP), "closed dorm door blocks collision and its navigation link")
	await _place(campaign.dorm_supply)
	expected_ammo += 144
	_check(campaign.dorm_upper and _ammo() == expected_ammo, "walking into the second floor marker replenishes every random weapon type")
	await _wait(165)
	_check(level.spawner.zombies.any(func(zombie):
		return zombie.encounter == &"" and level.layout.zone_at(zombie.global_position) == level.layout.DORM_FLOOR_TWO),
		"normal director spawns zombies on dorm second floor")
	await _place(campaign.dorm_exit)
	_check(not campaign.dorm_left, "east exit requires completing the upstairs detour")
	await _place(campaign.dorm_east_stairs)
	_check(campaign.dorm_crossed_upper, "second floor route reaches the east stairs")
	await _place(campaign.dorm_east_down)
	_check(campaign.dorm_descended, "east stairs descend to first floor")
	await _place(campaign.dorm_exit)
	_check(campaign.dorm_left, "east dorm exit advances objective")
	await _place(campaign.PLAZA)
	_check(campaign.finale_supplies_ready and not campaign.finale_started and not level.round_finished,
		"final approach provides miniguns ahead of the final horde")
	var before := _ammo()
	for pickup: Vector3 in campaign.FINAL_SUPPLIES:
		await _place(pickup)
	_check(campaign.final_weapon_count == 3, "all finale pickups can be collected by entering their markers")
	_check(level.firearms.owned.has("minigun") and _ammo() - before == 2880, "three finale pickups grant the minigun and ample ammunition")
	await _wait(375)
	_check(campaign.finale_started and level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"final_gate").size() >= 20,
		"the final horde arrives after the minigun preparation countdown")
	await _place(campaign.MAIN_GATE_OUTSIDE - Vector3(0, 0, 3))
	_check(not level.round_finished, "no completion inside the gate")
	await _place(campaign.MAIN_GATE_OUTSIDE + Vector3(0, 0, 1))
	_check(level.round_finished and level.result_panel.visible, "the main gate crossing opens the results")
	var tour_button: Button = level.result_panel.find_children("*", "Button", true, false).filter(
		func(button: Button): return button.text == "自由探索")[0]
	tour_button.pressed.emit()
	await scene_changed
	_check(current_scene.scene_file_path == "res://scenes/campus/free_tour.tscn"
		and current_scene.get_node("Walker").spawn.position.z > 10.5,
		"campaign exit enters the shared free tour outside the main gate")
	quit(1 if failed else 0)

func _place(at: Vector3) -> void:
	walker.global_position = at
	world.refresh_collision()
	await _wait(5)

func _wait(frames: int) -> void:
	for frame in frames:
		await physics_frame

func _ammo() -> int:
	var rounds := 0
	for record: Dictionary in level.firearms.ammo.values():
		rounds += int(record.mag) + int(record.reserve)
	return rounds

func _clear_standing_space() -> bool:
	var shape := CapsuleShape3D.new()
	shape.height = 1.58
	shape.radius = 0.27
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.collision_mask = 1
	query.transform.origin = walker.global_position + Vector3.UP * 0.86
	return walker.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()

func _check(passed: bool, description: String) -> void:
	print(("PASS " if passed else "FAIL ") + description)
	failed = failed or not passed
