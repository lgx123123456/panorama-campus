extends Node

const Level = preload("res://scripts/campus/campus_zombie_level.gd")
const Points = preload("res://scripts/campus/campus_survival_points.gd")
const Spawner = preload("res://scripts/campus/campus_zombie_spawner.gd")
const Walker = preload("res://scripts/campus/campus_character_walker.gd")
const MENU := "res://scenes/main_menu.tscn"
const PLAY := "res://scenes/campus/survival.tscn"

var failed := false
var level: Level
var scene: Node3D
var map: RID

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	await tree.process_frame
	tree.change_scene_to_file(MENU)
	await tree.scene_changed
	tree.current_scene.get_node("%ZombieTrialButton").pressed.emit()
	await tree.scene_changed
	_bind_scene()
	level.spawner.remaining = INF
	var overlay := tree.root.get_node_or_null("CampusLoadingOverlay")
	if overlay != null:
		await overlay.tree_exited
	level.walker.set_process_unhandled_input(false)
	await _wait_navigation()
	_check_native_doors()
	_check(scene.scene_file_path == PLAY and level.use_full_campus and scene.has_node("CampusVisuals"),
		"menu loads the original full campus model")
	_check(not scene.get_node("Interface/DebugControls").visible, "survival mode hides roaming controls")
	_check(level.walker.is_on_floor() and level.walker.global_position.y > 4.1 and level.walker.global_position.y < 4.6,
		"walker stands on the real second-floor classroom floor")
	_check(level.guide.is_on_floor() and not level.guide.look.infected, "AI classmate starts safely grounded and immune")
	if "--capture" in OS.get_cmdline_user_args():
		await _capture()
		tree.quit(1 if failed else 0)
		return
	var tape: RigidBody3D = level.props[&"tape"]
	var health := level.health_hud
	_check(health.visible and health.bar.value == 100.0 and health.bar.max_value == 100.0
		and health.fill_style.bg_color == health.HEALTHY_COLOR, "player starts with a full red health bar")
	level.walker.camera.look_at(tape.global_position)
	_check(level.interact_book() and level.armor == 1, "initial tape can be picked up in the existing classroom")
	_check("挡咬 ×1" in health.status.text and health.frame_style.border_color == health.TAPE_COLOR,
		"wrapping tape reinforces the health bar")
	level.walker.camera.rotation = Vector3.ZERO
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(level.doors.DOOR_DATA))
	var west: Dictionary = data.teaching_west_stairs.buildings[0]
	var east: Dictionary = data.teaching_east_stairs.buildings[0]
	await _check_initial_exit()
	await _check_spawn()
	await _check_class_door()
	await _check_stairs(west)
	await _check_stairs(east)
	await _check_gates(Points.point(east.corridor_join))
	print("CAMPUS SURVIVAL ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)

func _check_native_doors() -> void:
	var native: Array = level.doors.doors.filter(func(door: Dictionary): return "_class_" in str(door.id))
	_check(native.size() == 140, "all 140 classroom leaves use the existing campus model")
	for door: Dictionary in native:
		var pivot: Node3D = door.pivots[0].node
		_check(str(pivot.name).begins_with("CampusClassroomPivot_"), "door binds to original mesh pivot")
		_check(pivot.has_node("NativeDoorCollision"), "native leaf has moving collision")
		var inside: Vector3 = door.center - door.outward * 0.6
		var outside: Vector3 = door.center + door.outward * 0.6
		_check(level.layout.zone_at(inside) == int(door.inside_zone), "native door has its actual classroom region")
		_check(level._closest_lockable_door(outside, 1.0) < 0, "classroom locks operate from inside")

func _bind_scene() -> void:
	scene = get_tree().current_scene
	level = scene.get_node("CharacterTrial")
	map = scene.get_world_3d().navigation_map

func _wait_navigation() -> void:
	for frame in 400:
		await get_tree().physics_frame
		if frame >= 30 and _nav_endpoint(level.walker.global_position, level.walker.global_position).distance_to(level.walker.global_position) < 1.0:
			return
	_check(false, "campus navigation synchronizes")

func _check_initial_exit() -> void:
	var index: int = level.doors.doors.find_custom(func(door: Dictionary): return door.id == "B15_class_1_0_0")
	var door: Dictionary = level.doors.doors[index]
	var inside: Vector3 = door.center - door.outward * 0.85
	Input.action_press("move_forward")
	await _wait(90)
	Input.action_release("move_forward")
	_check(Vector2(level.walker.position.x - door.center.x, level.walker.position.z - door.center.z).length() < 0.70,
		"walking forward from the original spawn reaches the classroom door")
	level.walker.look_at(level.walker.position + door.outward)
	level.walker.camera.rotation = Vector3.ZERO
	var key := InputEventKey.new()
	key.physical_keycode = KEY_E
	key.pressed = true
	level.walker._input(key)
	await _wait(30)
	_check(door.open and not door.moving, "E opens the classroom door while standing near its safe inside face")
	var beyond: Vector3 = door.center + door.outward * 1.45
	await _walk_to(beyond, 150)
	_check(level.walker.position.distance_to(beyond) < 0.35, "walk from the initial spawn into the corridor without relocation")
	await _walk_to(inside, 150)
	_check(level.doors.set_open(index, false), "classroom door closes from its safe inside face")
	await _wait(30)
	for frame in 180:
		var endpoint := _nav_endpoint(door.center - door.outward * 1.45, beyond)
		if endpoint.distance_to(beyond) > 1.25:
			break
		await get_tree().physics_frame
	level.walker._reset_position()
	await _wait(10)
	print("CAMPUS initial movement and E interaction checked")

func _check_spawn() -> void:
	seed(1988)
	level.elapsed = 5.0
	level.spawner.remaining = INF
	var requested := level.spawner.try_group()
	for frame in 400:
		if level.spawner.batch_remaining == 0:
			break
		await _wait(1)
	_check(level.spawner.zombies.size() == requested and requested >= 2 and requested <= 10,
		"valid randomized zombies spawn near the original classroom")
	for zombie in level.spawner.zombies:
		var offset := zombie.global_position - level.walker.global_position
		_check(Vector2(offset.x, offset.z).length() >= level.spawner.min_spawn_distance
			and offset.length() < level.spawner.max_spawn_distance + 0.02, "spawn respects the horizontal exclusion")
		var reference := level.spawn_reference(level.walker.global_position)
		_check(_nav_endpoint(zombie.global_position, reference).distance_to(reference) < 1.0, "spawns are connected to playable route")
		print("CAMPUS zombie spawned at ", zombie.global_position)
	await _clear_zombies()

func _check_class_door() -> void:
	var index: int = level.doors.doors.find_custom(func(door: Dictionary): return door.id == "B15_class_1_0_0")
	var door: Dictionary = level.doors.doors[index]
	var center: Vector3 = door.center
	var outward: Vector3 = door.outward
	var behind := center - outward * 1.45
	var beyond := center + outward * 1.15
	_check(_nav_endpoint(behind, beyond).distance_to(beyond) > 1.25, "closed real classroom door breaks navigation")
	_place(behind + Vector3.UP * 0.20)
	await _wait(14)
	_check(level.walker.test_move(level.walker.global_transform, outward * 2.40), "closed classroom door blocks the actual capsule")
	level.lock_door()
	_check(door.locked and not level.doors.set_open(index, true), "lock applies from inside")
	level.lock_door()
	_check(level.doors.set_open(index, true), "unlocked real door opens")
	for frame in 150:
		if _nav_endpoint(behind, beyond).distance_to(beyond) < 0.50:
			break
		await get_tree().physics_frame
	print("CAMPUS classroom open endpoint=", _nav_endpoint(behind, beyond), " expected=", beyond)
	_check(_nav_endpoint(behind, beyond).distance_to(beyond) < 0.50, "opening restores the classroom navigation link")
	await _walk_to(beyond, 120)
	_check(level.walker.global_position.distance_to(beyond) < 0.40, "walk through the real door into the corridor")
	print("CAMPUS B15 classroom door and lock checked")

func _check_stairs(stair: Dictionary) -> void:
	var start := Points.point(stair.corridor_points[0])
	var goal := Points.point(stair.corridor_points[1])
	var corridor_direction := Vector3.BACK if stair.side == "西" else Vector3.LEFT
	_check(_nav_endpoint(start, goal).distance_to(goal) < 0.45, "second-floor stair route is linked")
	_place(start + Vector3.UP * 0.03)
	var walker_physics := level.walker
	walker_physics.set_physics_process(false)
	walker_physics.collision_layer = 0
	level.guide.collision_layer = 0
	level.walker.set_role(2, Walker.KING)
	level.guide_update = INF
	var zombie := level.spawner._spawn(start - corridor_direction * 0.08)
	zombie.command(goal)
	for frame in 900:
		if absf(zombie.global_position.y - goal.y) < 0.39 and zombie.global_position.distance_to(goal) < 1.0:
			break
		await get_tree().physics_frame
		# The command competes with vision in gameplay. Keep the test's player out of sight.
		if frame == 0:
			level.walker.look_at(level.walker.global_position + Vector3.UP + corridor_direction)
		zombie.think_in = 50.0
		# Collision is streamed around the player; both floors of the staircase remain inside that range.
		if frame == 1:
			level.walker.set_role(2, Walker.KING)
			level.guide_update = INF
	var reached := zombie.global_position
	print("CAMPUS staircase ", stair.side, " physical end=", reached, " expected=", goal)
	_check(absf(reached.y - goal.y) < 0.36, "zombie physically climbs the " + str(stair.side) + " staircase")
	await _clear_zombies()
	level.walker.set_role(2, Walker.HUMAN)
	level.walker.collision_layer = 2
	level.walker.set_physics_process(true)
	level.guide.collision_layer = 32

func _check_gates(from: Vector3) -> void:
	_check(_nav_endpoint(from, Points.FRONT_GATE).distance_to(Points.FRONT_GATE) < 0.65, "B15 connects to the front gate")
	_check(_nav_endpoint(from, Points.WEST_GATE).distance_to(Points.WEST_GATE) < 0.65, "B15 connects to the west gate")
	_place(Points.FRONT_GATE + Vector3.UP * 0.10)
	await _wait(3)
	_check(not level.round_finished, "new mission cannot be skipped through the original front gate")
	_place(Points.WEST_GATE + Vector3.UP * 0.10)
	await _wait(3)
	_check(not level.round_finished, "new mission cannot be skipped through the original west gate")
	get_tree().change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await get_tree().scene_changed
	_bind_scene()
	_place(Points.FRONT_GATE + Vector3.UP * 0.10)
	await _wait(3)
	_check(level.round_finished and "正门" in level.result.text and "成功撤离" in level.result.text, "front gate settles healthy player")
	get_tree().reload_current_scene()
	await get_tree().scene_changed
	_bind_scene()
	_place(Points.WEST_GATE + Vector3.UP * 0.10)
	level.infection = 17.0
	await _wait(3)
	_check(level.round_finished and "西门" in level.result.text and "感染离校" in level.result.text, "west gate settles infected player")
	print("CAMPUS both real gate checkpoints checked")

func _capture() -> void:
	_place(Vector3(-139.55, 4.50, -129.70))
	level.walker.rotation.y = -1.55
	await _wait(8)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/campus-survival-classroom.png")
	_place(Vector3(-69.9, 0.30, -112.6))
	level.walker.rotation.y = -1.68
	level.spawner._spawn(Vector3(-62.1, 0.32, -116.0))
	level.spawner._spawn(Vector3(-60.5, 0.32, -112.7))
	await _wait(20)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/campus-survival-outside.png")

func _place(point: Vector3) -> void:
	level.walker.global_position = point
	level.walker.velocity = Vector3.ZERO
	level.walker.rotation = Vector3.ZERO
	level.walker.camera.rotation = Vector3.ZERO
	scene.refresh_collision()

func _walk_to(point: Vector3, frame_limit: int) -> void:
	Input.action_press("move_forward")
	for frame in frame_limit:
		var diff := point - level.walker.global_position
		diff.y = 0.0
		if diff.length() < 0.15:
			break
		level.walker.look_at(level.walker.global_position + diff)
		await get_tree().physics_frame
	Input.action_release("move_forward")

func _nav_endpoint(from: Vector3, to: Vector3) -> Vector3:
	var path := NavigationServer3D.map_get_path(map, from, to, true)
	return path[-1] if not path.is_empty() else Vector3.INF

func _clear_zombies() -> void:
	level.spawner.batch_remaining = 0
	for zombie in level.spawner.zombies:
		level.release_bite(zombie)
		zombie.queue_free()
	level.spawner.zombies.clear()
	await _wait(2)

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _check(condition: bool, label: String) -> void:
	if not condition:
		failed = true
		push_error("SURVIVAL CHECK FAIL " + label)

