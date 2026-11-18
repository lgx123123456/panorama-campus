extends Node

const Level = preload("res://scripts/campus/campus_zombie_level.gd")
const Walker = preload("res://scripts/campus/campus_character_walker.gd")
const Zombie = preload("res://scripts/campus/campus_zombie.gd")
const Spawner = preload("res://scripts/campus/campus_zombie_spawner.gd")
const Actor = preload("res://scripts/campus/campus_character_actor.gd")
const MENU := "res://scenes/main_menu.tscn"
const TRIAL := "res://scenes/campus/zombie_trial.tscn"

var failed := false
var level: Level

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	var capture := "--capture" in OS.get_cmdline_user_args()
	reparent(tree.root)
	await tree.process_frame
	tree.change_scene_to_file(TRIAL)
	await tree.scene_changed
	level = tree.current_scene.get_node("CharacterTrial")
	await _wait(35)
	if capture:
		_place(Vector3(-14.7, 0.05, -5.3), -PI / 2.0)
		await _wait(4)
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/zombie-trial-classroom.png")
		level.doors.set_open(0, true)
		await _wait(27)
		_place(Vector3(-18.5, 0.05, 0.6), -PI / 2.0)
		level.spawner._spawn(Vector3(-14, 0, 0))
		level.spawner._spawn(Vector3(-9.6, 0, -0.65))
		await _wait(30)
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/zombie-trial-hallway.png")
		tree.quit()
		return
	_check(level.walker.is_on_floor() and level.walker.identity in [2, 3], "classroom spawn and special role")
	_check(level.guide.look.identity == 4 and not level.guide.look.infected, "AI classmate starts human")
	await _check_spawns()
	await _check_simulation_steps()
	await _check_paths_and_door()
	await _check_hearing_and_items()
	await _check_grabs()
	await _check_bites_and_turn()
	await _check_outcomes()
	print("CAMPUS ZOMBIES ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)

func _check_spawns() -> void:
	seed(82)
	level.elapsed = 4.0
	_check(level.spawner.zombies.is_empty(), "first minute starts without a wave")
	_check(Spawner.CHECK_INTERVAL == 60.0 and Spawner.ACTIVE_LIMIT == 200, "one-minute cadence and 200 cap")
	level.spawner.remaining = INF
	level.spawner.set_spawn_range(1.5, Spawner.MAX_DISTANCE)
	_check(level.spawner.min_spawn_distance == Spawner.MIN_DISTANCE and Spawner.MIN_DISTANCE == 15.0,
		"debug ranges cannot shrink the fifteen metre exclusion")
	var player_position := level.walker.global_position
	_check(not level.spawner._within_spawn_range(player_position + Vector3(0, 18, 0), player_position),
		"vertical separation does not allow a spawn next to the player")
	var requested := level.spawner.try_group()
	_check(requested >= 2 and requested <= 10, "batch requests 2 to 10 zombies")
	for frame in 400:
		if level.spawner.batch_remaining == 0:
			break
		await _wait(1)
	_check(level.spawner.zombies.size() == requested, "queued batch completes across frames")
	for zombie in level.spawner.zombies:
		var distance := zombie.global_position.distance_to(level.walker.global_position)
		_check(distance >= Spawner.MIN_DISTANCE and distance <= Spawner.MAX_DISTANCE + 0.01, "spawn respects player distance band")
		var head := zombie.global_position + Vector3.UP * 1.5
		_check(not level.walker.camera.is_position_in_frustum(head) or not level.clear_line(level.walker.camera.global_position, head), "spawn is hidden or outside camera")
	var remote := level.spawner._spawn(level.walker.global_position + Vector3(70, 0, 0))
	remote.state = Zombie.State.CHASE
	remote.far_time = Spawner.DESPAWN_AFTER - 1.0
	await _wait(2)
	_check(is_instance_valid(remote), "far zombie stays until its timeout")
	remote.far_time = Spawner.DESPAWN_AFTER
	await _wait(2)
	_check(not is_instance_valid(remote), "far chasing zombie is removed after timeout")
	await _clear_zombies()
	level.spawner.remaining = 0.001
	await _wait(2)
	_check(level.spawner.remaining > 59.0, "expired cadence resets to a minute")
	level.spawner.remaining = INF
	await _clear_zombies()
	print("CHECK timed batches, view exclusion and distant cleanup")

func _check_simulation_steps() -> void:
	var normal := Actor.new()
	var reduced := Actor.new()
	normal.position = Vector3(-18, 0.02, 0.6)
	reduced.position = Vector3(-18, 0.02, -0.6)
	level.add_child(normal)
	level.add_child(reduced)
	await _wait(5)
	normal.set_physics_process(false)
	reduced.set_physics_process(false)
	normal.go_to(Vector3(-10, 0, 0.6), 1.35)
	reduced.go_to(Vector3(-10, 0, -0.6), 1.35)
	var normal_start := normal.position
	var reduced_start := reduced.position
	for frame in 90:
		await _wait(1)
		var tick := normal.get_physics_process_delta_time()
		normal._physics_process(tick)
		if frame % 3 == 2:
			reduced._physics_process(tick * 3.0)
	var normal_travel := normal.position.x - normal_start.x
	var reduced_travel := reduced.position.x - reduced_start.x
	_check(normal_travel > 1.8 and absf(normal_travel - reduced_travel) < 0.08,
		"reduced-frequency simulation preserves travel speed")
	normal.queue_free()
	reduced.queue_free()
	var stopped := level.spawner._spawn(Vector3(-15, 0, 0))
	var waiting := level.spawner._spawn(Vector3(-11, 0, 0))
	stopped.goal = Vector3(-8, 0, 0)
	stopped.set_physics_process(false)
	waiting._investigate(Vector3(-5, 0, 0), 6.0)
	level.path_queue.assign([stopped, waiting])
	await _wait(3)
	_check(not level.path_queue.has(stopped) and waiting.last_path != Vector3.INF,
		"stopped queue head leaves navigation slots available")
	stopped.set_physics_process(true)
	stopped.global_position = level.walker.global_position + Vector3(40, 0, 0)
	stopped.goal = stopped.global_position + Vector3(4, 0, 0)
	stopped.last_path = Vector3.INF
	stopped.simulation_elapsed = 0.0
	waiting.goal = Vector3(-4, 0, 0)
	waiting.last_path = Vector3.INF
	level.path_queue.assign([stopped, waiting])
	await _wait(2)
	_check(stopped.last_path != Vector3.INF and waiting.last_path != Vector3.INF,
		"level services requests while a distant actor skips simulation")
	await _clear_zombies()

func _check_paths_and_door() -> void:
	var map := level.get_world_3d().navigation_map
	var inside := Vector3(-12, 0, -5.5)
	var hall := Vector3(-12, 0, 0)
	var upstairs := Vector3(24, 3, 0)
	var closed_path := NavigationServer3D.map_get_path(map, hall, inside, true)
	_check(closed_path.is_empty() or closed_path[-1].distance_to(inside) > 1.0, "closed door disconnects navmesh")
	var stair_path := NavigationServer3D.map_get_path(map, hall, upstairs, true)
	print("PATH stairs ", stair_path)
	_check(stair_path.size() >= 3 and stair_path[-1].distance_to(upstairs) < 0.15, "stair route changes floors")
	_check(level.doors.set_open(0, true), "door can open")
	_check(not level.layout.passages[0].link.enabled, "door link waits for leaf")
	await _wait(23)
	var open_path := NavigationServer3D.map_get_path(map, hall, inside, true)
	print("PATH room ", open_path)
	_check(open_path.size() >= 3 and open_path[-1].distance_to(inside) < 0.15, "opened door connects both meshes")
	_place(Vector3(-12.4, 0.04, -4.0), PI)
	var zombie := level.spawner._spawn(Vector3(-12.0, 0.02, -0.25))
	zombie.rotation.y = 0.0
	await _wait(28)
	_check(zombie.state == Zombie.State.CHASE and zombie.memory != Vector3.INF, "visible player causes chase")
	_check(level.doors.set_open(0, false), "door can close during chase")
	_check(not level.layout.passages[0].link.enabled, "closing disables link immediately")
	_place(Vector3(-12.6, 0.04, -5.25), PI)
	await _wait(83)
	_check(zombie.state == Zombie.State.KNOCK and zombie.global_position.z > -2.08, "chasing zombie hits closed door from hall")
	_check(level.door_cycles.has(0), "first knock creates a grouping event")
	if zombie.state == Zombie.State.KNOCK:
		zombie.state_time = 0.01
	await _wait(29)
	_check(zombie.state in [Zombie.State.DISPERSE, Zombie.State.WANDER], "quiet door group disperses")
	_place(Vector3(-12, 0.04, -3.83), PI)
	await _wait(2)
	level.lock_door()
	_check(level.doors.doors[0].locked and not level.doors.set_open(0, true), "locked door refuses open")
	level.lock_door()
	_check(not level.doors.doors[0].locked, "player can unlock from inside")
	await _clear_zombies()
	_place(Vector3(-11, 0.03, -6.5), PI / 2.0)
	var climber := level.spawner._spawn(Vector3(13, 0.02, -1.0))
	climber.command(upstairs)
	await _wait(630)
	print("PATH climber position ", climber.global_position)
	_check(climber.global_position.y > 2.80, "zombie physically walks upstairs")
	await _clear_zombies()
	print("CHECK door blocking, door pressure and multilevel AI")

func _check_hearing_and_items() -> void:
	_place(Vector3(0, 0.03, 0), PI)
	var zombie := level.spawner._spawn(Vector3(9.3, 0.02, 0.8))
	zombie.rotation.y = -PI / 2
	var sound := level.sound_id
	level.walker.quiet = true
	level.walker._update_footsteps(1.0, 1.65, false)
	_check(level.sound_id == sound, "quiet foot movement emits no sound")
	level.walker.quiet = false
	level.walker._update_footsteps(1.0, 3.2, false)
	_check(level.sound_id == sound + 1 and zombie.state == Zombie.State.INVESTIGATE, "walking reaches listener within visual distance")
	level.walker._update_footsteps(1.0, 5.0, true)
	_check(zombie.state == Zombie.State.INVESTIGATE and zombie.memory.distance_to(level.walker.global_position) < 0.06, "running reaches listener")
	await _clear_zombies()
	_place(Vector3(-12.4, 0.03, -6.10), 0)
	var item: RigidBody3D = level.props[&"book"]
	level.walker.camera.look_at(item.global_position)
	_check(level.interact_book() and level.held == &"book", "book can be picked up")
	var listener := level.spawner._spawn(Vector3(-9.7, 0.02, -8))
	listener.rotation.y = -PI / 2
	level.throw_book()
	await _wait(95)
	_check(level.held == &"" and not level.thrown.has(&"book") and listener.heard_id > 0, "physical book landing emits investigation noise")
	await _clear_zombies()
	print("CHECK stealth, distance-based hearing and physical book")

func _check_grabs() -> void:
	_place(Vector3(0, 0.03, 0), PI)
	level.infection = -1.0
	level.armor = 1
	var zombie := level.spawner._spawn(Vector3(0, 0.02, 1.2))
	zombie.rotation.y = PI # Player is behind the zombie.
	zombie.think_in = 4.0
	await _wait(3)
	_check(level.is_player_grabbed() and zombie.state == Zombie.State.BITE, "close rear contact grabs immediately without think or FOV delay")
	var rival := level.spawner._spawn(Vector3(1.1, 0.02, 0))
	_check(not level.reserve_bite(rival), "group shares a single grab and bite owner")
	var start := level.walker.global_position
	await _wait(7)
	_check(level.walker.global_position.z > start.z + 0.03 and level.walker.global_position.z < start.z + 0.22, "grab physically pulls with bounded collision motion")
	_check(level.armor == 1, "short windup remains readable before damage")
	await _wait(6)
	_check(level.armor == 0 and zombie.state == Zombie.State.GRAB, "bite damages within a quarter second then holds briefly")
	level.struggle_grab()
	_check(level.is_player_grabbed(), "first struggle weakens the hold")
	level.struggle_grab()
	_check(not level.is_player_grabbed() and zombie.stun_remaining > 0, "second struggle releases and briefly stuns grabber")
	await _clear_zombies()
	_place(Vector3(-12, 0.03, -2.64), 0)
	zombie = level.spawner._spawn(Vector3(-12, 0.02, -1.48))
	_check(not level.can_grab(zombie) and not level.reserve_bite(zombie), "closed classroom door blocks close grabbing")
	await _clear_zombies()
	_place(Vector3(0, 0.03, 0), 0)
	zombie = level.spawner._spawn(Vector3(0, 0.02, 1.2))
	_check(level.reserve_bite(zombie), "clear arm reach reserves grab")
	level._door_changed(0, false)
	_check(level.is_player_grabbed(), "unrelated door closure preserves a clear physical hold")
	level.use_ability()
	_check(not level.is_player_grabbed() and zombie.stun_remaining > 0, "G breaks grab for either human role")
	zombie.stun_remaining = 0.0
	_check(level.reserve_bite(zombie), "released slot is reusable")
	zombie.queue_free()
	level.spawner.zombies.erase(zombie)
	await _wait(2)
	_check(not level.is_player_grabbed() and not level.walker.get_meta(&"campus_grabbed", false), "freed grabber cleans player hold state")
	_place(Vector3(0, 0.03, 0), 0)
	zombie = level.spawner._spawn(Vector3(0, 0.02, 1.2))
	zombie.set_physics_process(false)
	var obstacle := StaticBody3D.new()
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(2.0, 0.30, 0.12)
	collider.shape = shape
	obstacle.add_child(collider)
	obstacle.position = Vector3(0, 0.15, 0.53)
	level.add_child(obstacle)
	await _wait(2)
	_check(level.can_grab(zombie) and level.reserve_bite(zombie), "low obstacle leaves arm reach clear")
	level._update_grab(0.5)
	_check(level.walker.global_position.z < 0.3, "physical pull stops player capsule at low obstacle")
	level.release_bite(zombie)
	obstacle.queue_free()
	await _clear_zombies()
	level.armor = 0
	print("CHECK immediate close bite, physical drag, shared slot, struggle, shove, door and freed-owner cleanup")

func _check_bites_and_turn() -> void:
	level.infection = -1.0
	level.walker.stagger_remaining = 0.0
	_place(Vector3(0, 0.03, 0), PI)
	var zombie := level.spawner._spawn(Vector3(0, 0.02, 1.2))
	zombie.rotation.y = 0
	level.armor = 1
	await _wait(4)
	_check(zombie.state == Zombie.State.BITE and level.armor == 1, "bite shows startup before applying damage")
	zombie.stun(2.0)
	_check(level.bite_owner == null and level.armor == 1, "stun releases single attack slot without consuming tape")
	for frame in 250:
		if level.armor == 0:
			break
		await get_tree().physics_frame
	_check(level.armor == 0 and level.infection < 0, "first effective bite consumes one tape")
	for frame in 225:
		if level.infection >= 0.0:
			break
		await get_tree().physics_frame
	_check(level.infection > 29.9 and level.infection <= 30.0, "next confirmed bite starts the thirty second timer")
	var remaining := level.infection
	level._player_bitten()
	_check(is_equal_approx(remaining, level.infection), "additional bite preserves existing timer")
	var identity := level.walker.identity
	level.infection = 0.08
	await _wait(8)
	_check(level.walker.role == Walker.KING and level.walker.identity == identity and level.walker.look.infected,
		"turn keeps player identity")
	_check(is_instance_valid(level.guide) and not level.guide.look.infected, "guide remains immune after player turns")
	await _clear_zombies()
	var first := level.spawner._spawn(Vector3(4, 0.02, 0.7))
	var second := level.spawner._spawn(Vector3(5, 0.02, -0.65))
	level.spawner._spawn(Vector3(7, 0.02, 0.7))
	await _wait(2)
	_check(level.command_at(Vector3(2, 0, 0)) == 2 and first.command_owner and second.command_owner, "king orders only two nearby wanderers")
	_check(level.command_at(Vector3(1, 0, 0)) == 0, "active followers retain limit")
	print("CHECK bites, stun, infection, immune guide and king command")

func _check_outcomes() -> void:
	var tree := get_tree()
	tree.change_scene_to_file(TRIAL)
	await tree.scene_changed
	level = tree.current_scene.get_node("CharacterTrial")
	_place(Level.EXIT_WEST + Vector3.UP * 0.02, 0)
	await _wait(2)
	_check(level.round_finished and "成功撤离" in level.result.text and "西侧" in level.result.text, "west exit records clean escape")
	tree.reload_current_scene()
	await tree.scene_changed
	level = tree.current_scene.get_node("CharacterTrial")
	_place(Level.EXIT_EAST + Vector3.UP * 0.02, 0)
	level.infection = 23
	await _wait(2)
	_check(level.round_finished and "感染离开" in level.result.text and "东侧" in level.result.text, "east exit records infection")
	print("CHECK separate exits and fresh round state")

func _clear_zombies() -> void:
	level.spawner.batch_remaining = 0
	for zombie in level.spawner.zombies:
		level.release_bite(zombie)
		zombie.queue_free()
	level.spawner.zombies.clear()
	await _wait(2)

func _place(point: Vector3, yaw: float) -> void:
	level.walker.global_position = point
	level.walker.rotation.y = yaw
	level.walker.camera.rotation = Vector3.ZERO
	level.walker.velocity = Vector3.ZERO

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _check(condition: bool, label: String) -> void:
	if not condition:
		failed = true
		push_error("ZOMBIE CHECK FAIL " + label)
