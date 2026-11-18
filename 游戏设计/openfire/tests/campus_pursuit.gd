extends Node

const Zombie = preload("res://scripts/campus/campus_zombie.gd")
const Field = preload("res://scripts/campus/campus_field_passages.gd")
var failed := false
var level: Node3D

func _ready() -> void:
	_run.call_deferred()

func _run() -> void:
	reparent(get_tree().root)
	get_tree().change_scene_to_file("res://scenes/campus/zombie_trial.tscn")
	await get_tree().scene_changed
	level = get_tree().current_scene.get_node("CharacterTrial")
	level.walker.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.guide.set_physics_process(false)
	await _wait(35)
	level.walker.global_position = Vector3(0, 0.03, 0)
	var zombie = level.spawner._spawn(Vector3(11.3, 0.03, 0))
	zombie.set_physics_process(false)
	zombie.rotation.y = -PI / 2.0
	level._footstep(level.walker.global_position, 1.0)
	_check(zombie.state == Zombie.State.INVESTIGATE, "walking heard at visual radius")
	zombie._set_state(Zombie.State.WANDER)
	level._footstep(level.walker.global_position, 1.5)
	_check(zombie.state == Zombie.State.INVESTIGATE, "running heard at visual radius")
	zombie._set_state(Zombie.State.WANDER)
	zombie.global_position.x = 12.6
	level._footstep(level.walker.global_position, 1.5)
	_check(zombie.state == Zombie.State.WANDER, "running does not extend beyond visual radius")
	level.zombie_chase_distance = 10.0
	zombie.global_position = Vector3(9, 0.03, 0)
	zombie.rotation.y = PI / 2.0
	zombie._think()
	_check(zombie.state == Zombie.State.CHASE, "visible player acquired")
	var remembered: Vector3 = zombie.memory
	level.walker.global_position = Vector3(-9, 0.03, 0)
	zombie._think()
	_check(zombie.state == Zombie.State.CHASE and zombie.goal == remembered,
		"loss outside custom radius keeps last sight pursuit")
	level.spawner.zombies.erase(zombie)
	zombie.queue_free()
	await _wait(2)
	level.zombie_chase_distance = 12.0
	level.doors.set_open(0, true)
	await _wait(25)
	level.debug_invincible = true
	var door_hunter = level.spawner._spawn(Vector3(-12, 0.03, 0.6))
	door_hunter.set_physics_process(false)
	door_hunter.rotation.y = 0.0
	level.walker.global_position = Vector3(-12, 0.03, -1.6)
	door_hunter._think()
	level.walker.global_position = Vector3(-12, 0.03, -2.4)
	door_hunter._think()
	var doorway_sighting: Vector3 = door_hunter.memory
	level.walker.global_position = Vector3(-9.2, 0.03, -4.1)
	_check(not level.can_see(door_hunter, level.walker), "room corner physically occludes player")
	door_hunter._think()
	_check(door_hunter.state == Zombie.State.CHASE and door_hunter.memory == doorway_sighting
		and door_hunter.goal.z < -3.0, "doorway memory continues through the open door")
	door_hunter.set_physics_process(true)
	for frame in 250:
		await get_tree().physics_frame
		if door_hunter.global_position.z < -2.9:
			break
	_check(door_hunter.global_position.z < -2.9, "occluded pursuit physically enters room")
	level.spawner.zombies.erase(door_hunter)
	door_hunter.queue_free()
	await _wait(2)
	level.walker.global_position = Vector3(0, 0.03, 0)
	var upper_listener = level.spawner._spawn(Vector3(0, 3.03, 0))
	upper_listener.set_physics_process(false)
	level._footstep(level.walker.global_position, 1.0)
	_check(upper_listener.state == Zombie.State.WANDER, "footsteps do not pinpoint another floor")
	level.spawner.zombies.erase(upper_listener)
	upper_listener.queue_free()
	await _wait(2)
	var barrier := StaticBody3D.new()
	var barrier_shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.2, 2.6, 4.16)
	barrier_shape.shape = box
	barrier.add_child(barrier_shape)
	level.add_child(barrier)
	barrier.global_position = Vector3(2, 1.3, 0)
	var listeners: Array = []
	for index in 6:
		var listener = level.spawner._spawn(Vector3(4.0 + index * 0.4, 0.03, 0))
		listener.set_physics_process(false)
		listeners.append(listener)
	await _wait(3)
	level._footstep(level.walker.global_position, 1.0)
	_check(level.pending_step_sounds.size() == listeners.size(), "wall-occluded hearing queues bounded navigation work")
	level._service_step_sounds()
	_check(level.pending_step_sounds.size() >= listeners.size() - level.HEARING_PATHS_PER_FRAME
		and level.pending_step_sounds.size() < listeners.size(),
		"hearing processes at most two blocked paths per frame")
	await _wait(4)
	for listener in listeners:
		_check(listener.state == Zombie.State.WANDER, "blocked wall does not supply a player location")
		level.spawner.zombies.erase(listener)
		listener.queue_free()
	barrier.queue_free()
	await _wait(2)
	get_tree().change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await get_tree().scene_changed
	level = get_tree().current_scene.get_node("CharacterTrial")
	level.walker.set_physics_process(false)
	level.campaign.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.spawner.remaining = INF
	level.debug_invincible = true
	for actor in level.spawner.zombies.duplicate():
		actor.queue_free()
	level.spawner.zombies.clear()
	await _wait(30)
	var map: RID = level.get_world_3d().navigation_map
	var gate_center: Vector3 = (Field.APPROACH[0] + Field.EXIT[0]) * 0.5
	for frame in 600:
		if NavigationServer3D.map_get_iteration_id(map) > 0 \
				and NavigationServer3D.map_get_closest_point(map, gate_center).distance_to(gate_center) < 0.4:
			break
		await get_tree().physics_frame
	for index in Field.APPROACH.size():
		level.walker.global_position = Field.EXIT[index]
		get_tree().current_scene.refresh_collision()
		await _wait(12)
		var path := NavigationServer3D.map_get_path(map, Field.APPROACH[index], Field.EXIT[index], true)
		print("GATE PATH ", index + 1, " ", path)
		_check(path.size() >= 2 and path[-1].distance_to(Field.EXIT[index]) < 1.0,
			"stand gate %d has complete navigation" % (index + 1))
		var field_start: Vector3 = Field.APPROACH[index] + Vector3.LEFT * 2.0
		var connected := NavigationServer3D.map_get_path(map, field_start, Field.EXIT[index], true)
		_check(connected.size() >= 2 and connected[-1].distance_to(Field.EXIT[index]) < 0.8
			and _path_length(connected) < field_start.distance_to(Field.EXIT[index]) + 5.0,
			"stand gate %d connects directly to the original field navmesh" % (index + 1))
		var hunter = level.spawner._spawn(field_start)
		hunter.set_physics_process(false)
		hunter.rotation.y = -PI / 2.0
		level.walker.global_position = Field.APPROACH[index] + Vector3.RIGHT * 2.2
		hunter._think()
		level.walker.global_position += Vector3.RIGHT * 0.6
		hunter._think()
		var sighting: Vector3 = hunter.memory
		level.walker.global_position = Field.EXIT[index] + Vector3(0, 0, 4.0)
		_check(not level.can_see(hunter, level.walker), "stand gate %d corner occludes player" % (index + 1))
		hunter._think()
		_check(hunter.state == Zombie.State.CHASE and hunter.memory == sighting
			and hunter.goal.distance_to(Field.EXIT[index]) < 0.2,
			"stand gate %d remembers entry and pursues far side" % (index + 1))
		hunter.set_physics_process(true)
		for frame in 850:
			await get_tree().physics_frame
			if hunter.global_position.x >= Field.EXIT[index].x - 0.8:
				break
		print("GATE MOVE ", index + 1, " ", hunter.global_position, " state=", hunter.state)
		_check(hunter.global_position.x >= Field.EXIT[index].x - 1.2,
			"stand gate %d zombie physically crosses" % (index + 1))
		if index >= 2:
			var turn: Vector3 = Field.EXIT[index] + Vector3(0, 0, 5.0)
			level.walker.global_position = turn + Vector3(0, 0, 3.0)
			hunter._investigate(turn, 12.0)
			for frame in 350:
				await get_tree().physics_frame
				if hunter.global_position.z > turn.z - 0.7:
					break
			_check(hunter.global_position.z > turn.z - 0.9,
				"stand gate %d zombie turns into sheltered walkway" % (index + 1))
			var sheltered := NavigationServer3D.map_get_path(map, Field.EXIT[index], Vector3(-253.25, 0.13, -18.8), true)
			_check(sheltered.size() >= 2 and sheltered[-1].distance_to(Vector3(-253.25, 0.13, -18.8)) < 0.7,
				"stand gate %d sheltered walkway joins the campus" % (index + 1))
		level.spawner.zombies.erase(hunter)
		hunter.queue_free()
		await _wait(2)
	print("CAMPUS PURSUIT ", "FAIL" if failed else "PASS")
	get_tree().quit(1 if failed else 0)

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _path_length(points: PackedVector3Array) -> float:
	var distance := 0.0
	for index in range(1, points.size()):
		distance += points[index - 1].distance_to(points[index])
	return distance

func _check(ok: bool, message: String) -> void:
	print("PURSUIT ", "PASS " if ok else "FAIL ", message)
	failed = failed or not ok

