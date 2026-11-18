extends Node

const DOOR := "B15_1"
const LOCKED_DOOR := "B45"

var host := false
var failed := false
var first_guest_name := ""

func _ready() -> void:
	_run.call_deferred()

func _run() -> void:
	var tree := get_tree()
	host = "--campus-host-test" in OS.get_cmdline_user_args()
	var survival := "--campus-survival-test" in OS.get_cmdline_user_args()
	var selected: int = Net.CampusMode.SURVIVAL if survival else Net.CampusMode.EXPLORE
	var invite_path := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--campus-invite-path="):
			invite_path = arg.trim_prefix("--campus-invite-path=")
	reparent(tree.root)
	if tree.current_scene == self:
		tree.current_scene = null
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await tree.scene_changed
	var menu = tree.current_scene
	if host:
		Net.players_changed.connect(_remember_first_guest)
	var nickname := "房主测试" if host else "加入前昵称"
	Settings.campus_nickname = nickname
	menu._show_campus_online()
	menu.campus_nickname_input.text = nickname
	menu.campus_mode_input.select(selected if host else 1 - selected)
	if invite_path.is_empty():
		menu._open_campus_room(2 if host else 3)
	elif host:
		await menu._open_campus_room(0)
		if not Net.room_code.begins_with(Net.IROH_INVITE_PREFIX):
			_finish(false, "Iroh invitation creation")
			return
		var output := FileAccess.open(invite_path, FileAccess.WRITE)
		if output == null:
			_finish(false, "Iroh invitation test file")
			return
		output.store_string(Net.room_code)
		output.close()
	else:
		if not await _wait(func(): return FileAccess.file_exists(invite_path)):
			_finish(false, "wait for Iroh invitation")
			return
		menu.campus_room_input.text = FileAccess.get_file_as_string(invite_path)
		await menu._open_campus_room(1)
	if host:
		print("CAMPUS LAN waiting for client")
	if not await _wait(func(): return Net.players.size() == 2 and menu.lobby_panel.visible):
		_finish(false, "campus lobby registration")
		return
	_check(Net.campus_mode == selected and menu.lobby_summary.text.begins_with(Net.CAMPUS_MODE_NAMES[selected]),
		"host's selected room mode appears on both peers")
	var initial_name := first_guest_name if host else Net.get_player_name(Net.local_id())
	_check(Net.get_player_name(1) == "房主测试" and initial_name == "加入前昵称",
		"nickname entered before joining is registered")
	if not host:
		Settings.campus_nickname = "房间内改名"
		menu.lobby_nickname_input.text = "房间内改名"
		menu._rename_in_lobby()
	if not await _wait(func(): return Net.players.values().any(func(row): return row.name == "房间内改名")):
		_finish(false, "nickname changed after joining")
		return
	if host:
		menu.start_button.pressed.emit()
	var expected: StringName = &"CampusMultiplayerSurvival" if survival else &"CampusMultiplayer"
	if not await _wait(func(): return tree.current_scene != null and tree.current_scene.name == expected):
		_finish(false, "campus scene load")
		return
	var campus := tree.current_scene
	var walker: CharacterBody3D = campus.get_node("Walker")
	var session = campus.get_node("Session")
	var doors = campus.get_node("Doors")
	if not await _wait(func(): return session.active and session.avatars.size() == 1):
		_finish(false, "ready barrier and remote avatar")
		return
	var other: int = session.avatars.keys()[0]
	if survival:
		_finish(await _survival_test(campus, session) and not failed, "shared zombies, shot, bite, and team exploration transition")
		return
	_check(walker.global_position.distance_to(session.avatars[other].global_position) > 0.7, "distinct gate spawns")

	var door: Dictionary = doors.doors[0]
	_check(door.id == DOOR and doors.room_open(DOOR), "initial teaching building door")
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	var outward: Array = data.doors[0].outward
	var approach := Vector3(float(outward[0]), 0.0, -float(outward[1]))
	var interaction_point: Vector3 = door.center + approach * 2.8 + Vector3.UP * 0.02
	if host:
		await tree.create_timer(1.2).timeout
		_check(doors.room_open(DOOR), "remote request from the gate did not close the teaching building")
		Input.action_press("move_forward")
		await tree.create_timer(0.6).timeout
		Input.action_release("move_forward")
		await tree.create_timer(0.6).timeout
		walker.position = interaction_point
		campus.refresh_collision()
		_press_interact(walker, doors)
		_check(await _wait(func(): return not doors.room_open(DOOR)), "host E closes teaching building door")
		_check(not doors.room_open(LOCKED_DOOR), "locked entrance stays closed")
		walker.position = walker.get_node("../Spawn").position
		campus.refresh_collision()
		_check(await _wait(func(): return doors.room_open(DOOR)), "remote E reopens door on host")
		walker._return_to_gate()
		await tree.create_timer(0.25).timeout
		walker._set_jetpack(true)
		Input.action_press("jump")
		await tree.create_timer(1.0).timeout
		Input.action_release("jump")
		await tree.create_timer(0.55).timeout
		walker._return_to_gate()
		walker._mount()
		Input.action_press("move_forward")
		await tree.create_timer(0.8).timeout
		Input.action_release("move_forward")
		await tree.create_timer(0.9).timeout
		session._leave()
	else:
		var original: Vector3 = session.avatars[other].global_position
		session.request_door(DOOR)
		_check(await _wait(func(): return session.avatars[other].global_position.distance_to(original) > 1.0), "remote walking snapshot")
		_check(await _wait(func(): return not doors.room_open(DOOR)), "host door state replicated")
		walker.position = door.center + approach * 0.36 + Vector3.UP * 0.02
		campus.refresh_collision()
		await tree.create_timer(0.5).timeout
		_press_interact(walker, doors)
		_check(await _wait(func(): return doors.room_open(DOOR)), "peer sees its door request confirmed")
		_check(await _wait(func(): return (is_instance_valid(session) and session.avatars.has(other)
			and session.avatars[other].get_node("RemotePack").visible
			and session.avatars[other].global_position.y > 2.0)), "jetpack transport replicated")
		_check(await _wait(func(): return (is_instance_valid(session) and session.avatars.has(other)
			and session.avatars[other].get_parent().get_node("Motorcycle").visible)), "scooter transport replicated")
		_check(await _wait(func(): return tree.current_scene != null and tree.current_scene.name == &"MainMenu"), "host exit returns client to menu")
	_finish(not failed, "lobby, players, door state and teardown")


func _remember_first_guest() -> void:
	if first_guest_name.is_empty() and Net.players.size() == 2:
		for id: int in Net.players:
			if id != 1:
				first_guest_name = Net.get_player_name(id)


func _survival_test(world: Node, session: Node) -> bool:
	var tree := get_tree()
	var level = world.get_node("CharacterTrial")
	var walker = world.get_node("Walker")
	level.campaign.set_physics_process(false)
	level.spawner.set_physics_process(false)
	walker.global_position = Vector3(7.0 if host else 0.0, 0.14, 14.0)
	walker.rotation.y = 0.0
	world.refresh_collision()
	await tree.create_timer(0.8).timeout
	if host:
		var zombie = level.spawner._spawn(Vector3(0.0, 0.04, 10.8))
		zombie.set_physics_process(false)
		if not await _wait(func(): return zombie.health < zombie.MAX_HEALTH):
			return false
		print("CAMPUS SURVIVAL PASS remote shot lowers host enemy health")
		var id: int = session.remote_states.keys()[0]
		var at: Vector3 = session.remote_states[id].position
		zombie.global_position = at + Vector3.FORWARD * 0.7
		session.combat.bite_remote(id, zombie)
		if not await _wait(func(): return session.remote_states[id].position.z < -8.0):
			return false
		level.campaign._update_plaza_encounter(walker.global_position)
		var wave: Dictionary = level.spawner.encounters.get(&"plaza", {})
		_check(wave.get("direct_peer") == id and not level.campaign.field_wave,
			"guest can start the plaza encounter without visiting the sports field")
		for frame in 95:
			await tree.physics_frame
			level.spawner._continue_encounters(walker)
		_check(level.spawner.zombies.any(func(enemy): return enemy.encounter == &"plaza"),
			"host creates a crowd near the guest")
		level._finish("队伍已撤离")
		await tree.create_timer(0.8).timeout
		level._begin_free_roam()
	else:
		if not await _wait(func(): return session.combat.replicas.size() == 1):
			return false
		print("CAMPUS SURVIVAL PASS received host enemy")
		var actor: Node3D = session.combat.replicas.values()[0].node
		var direction: Vector3 = (actor.global_position + Vector3.UP * 1.30 - walker.camera.global_position).normalized()
		walker.rotation.y = atan2(-direction.x, -direction.z)
		walker.camera.rotation.x = asin(direction.y)
		level.firearms.grant_supply("pistol", 24, true)
		level.firearms.switch_weapon(0)
		await tree.create_timer(0.45).timeout
		if not level.firearms.try_fire():
			push_error("cannot fire after granting pistol")
			return false
		if not await _wait(func(): return is_instance_valid(level) and level.player_health < level.PLAYER_MAX_HEALTH):
			return false
		print("CAMPUS SURVIVAL PASS host attack damages guest")
		walker.global_position = Vector3(0, 0.15, -12)
		world.refresh_collision()
		if not await _wait(func(): return is_instance_valid(session) and session.combat.replicas.size() >= 5):
			return false
		print("CAMPUS SURVIVAL PASS guest received the plaza crowd")
		if not await _wait(func(): return not is_instance_valid(level) or level.round_finished):
			return false
	var switched := await _wait(func():
		return tree.current_scene != null and tree.current_scene.name == &"CampusMultiplayer" \
			and tree.current_scene.get_node("Session").active)
	if not switched:
		return false
	_check(Net.players.size() == 2 and Net.campus_mode == Net.CampusMode.EXPLORE, "room roster survives team mode change")
	if host:
		await tree.create_timer(0.9).timeout
		tree.current_scene.get_node("Session")._leave()
	else:
		return await _wait(func(): return tree.current_scene != null and tree.current_scene.name == &"MainMenu")
	return true


func _press_interact(walker: Node, doors: Node) -> void:
	doors._process(0.0)
	var event := InputEventKey.new()
	event.physical_keycode = KEY_E
	event.pressed = true
	walker._input(event)

func _wait(condition: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + 30000
	while not bool(condition.call()):
		if Time.get_ticks_msec() >= deadline:
			return false
		await get_tree().create_timer(0.05).timeout
	return true

func _check(ok: bool, requirement: String) -> void:
	if not ok:
		failed = true
		push_error(requirement)

func _finish(ok: bool, requirement: String) -> void:
	print("CAMPUS LAN ", "HOST" if host else "CLIENT", " ", "PASS" if ok else "FAIL", " · ", requirement)
	get_tree().quit(0 if ok else 1)
