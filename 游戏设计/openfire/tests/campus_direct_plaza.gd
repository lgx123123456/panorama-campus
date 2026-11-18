extends SceneTree

var failed := false
var world: Node3D
var level: Node3D


func _initialize() -> void:
	run.call_deferred()


func run() -> void:
	create_timer(45.0).timeout.connect(func(): quit(1))
	change_scene_to_file("res://scenes/campus/survival.tscn")
	await scene_changed
	world = current_scene
	level = world.get_node("CharacterTrial")
	level.walker.set_physics_process(false)
	level.campaign.set_physics_process(false)
	level.spawner.set_physics_process(false)
	var map := world.get_world_3d().navigation_map
	for frame in 480:
		if NavigationServer3D.map_get_iteration_id(map) > 0:
			break
		await physics_frame

	var exit: Dictionary = level.doors.doors[level.doors._index_for_id("B15_1")]
	var early: Vector3 = exit.center + exit.outward * 1.5
	await place(early)
	check(not level.spawner.encounters.has(&"plaza"), "teaching exit cannot start the Shangde Plaza crowd")
	var canteen: Dictionary = level.doors.doors[level.doors._index_for_id("B22_1")]
	await place(canteen.center + canteen.outward * 2.0)
	check(not level.spawner.encounters.has(&"plaza"), "canteen frontage cannot start the Shangde Plaza crowd")
	await place(Vector3(0, 0.15, -72))
	check(not level.spawner.encounters.has(&"plaza"), "the distant preparation stretch cannot start the plaza crowd")

	var plaza: Vector3 = level.campaign.PLAZA
	await place(plaza)
	await spawn_frames(95)
	var wave: Dictionary = level.spawner.encounters.get(&"plaza", {})
	check(not level.campaign.left_track and not level.campaign.field_wave,
		"the direct route never triggers the sports field")
	check(wave.get("origin") == plaza and wave.has("direct_peer"), "arriving at the plaza starts it on the direct route")
	var crowd := plaza_zombies()
	check(crowd.size() >= 10, "arrival spawns a real navigable crowd in the plaza")
	check(crowd.all(func(zombie):
		var point: Vector3 = zombie.patrol_center
		return absf(point.x) <= 24.0 and point.z >= -38.0 and point.z <= -3.0),
		"every plaza spawn is at Shangde Plaza rather than another campus block")
	check(level.spawner.gate_preparation, "the plaza encounter can run during minigun preparation")
	var opening: int = wave.get("opening_start", -1)
	await place(plaza + Vector3(2.0, 0, -1.0))
	check(wave.get("opening_start", -2) == opening, "walking around the plaza does not restart the wave")
	check(not level.spawner.encounters.has(&"final_gate"), "the plaza encounter leaves the final warning countdown intact")
	print("DIRECT PLAZA ", "FAIL" if failed else "PASS", " · crowd: ", crowd.size())
	quit(1 if failed else 0)


func place(at: Vector3) -> void:
	level.walker.global_position = at
	world.refresh_collision()
	for frame in 5:
		await physics_frame
	level.campaign._physics_process(1.0 / 60.0)


func spawn_frames(count: int) -> void:
	for frame in count:
		await physics_frame
		level.spawner._continue_encounters(level.walker)
		for zombie in level.spawner.zombies:
			zombie.set_physics_process(false)


func plaza_zombies() -> Array:
	return level.spawner.zombies.filter(func(zombie): return zombie.encounter == &"plaza")


func check(ok: bool, label: String) -> void:
	print("PASS " if ok else "FAIL ", label)
	failed = failed or not ok
