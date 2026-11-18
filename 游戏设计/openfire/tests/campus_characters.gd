extends Node

const Trial = preload("res://scripts/campus/campus_character_trial.gd")
const Walker = preload("res://scripts/campus/campus_character_walker.gd")
const MENU := "res://scenes/main_menu.tscn"

var scene: Node3D
var trial: Trial
var walker: Walker
var failed := false
var footsteps: Array[float] = []

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file(MENU)
	await tree.scene_changed
	print("CHARACTERS main menu loaded")
	tree.current_scene.get_node("%CharacterTrialButton").pressed.emit()
	await tree.scene_changed
	print("CHARACTERS trial scene loaded")
	scene = tree.current_scene
	trial = scene.get_node("CharacterTrial")
	walker = trial.walker
	await _wait(24)
	if "--capture" in OS.get_cmdline_user_args():
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/campus-characters.png")
		tree.quit()
		return
	_check(walker.is_on_floor(), "grounded campus spawn")
	_check(trial.humans.size() == 5 and trial.infected.size() == 5, "five paired appearances")
	_check(walker.identity in [2, 3] and walker.identity == trial.special_role, "one special role assigned")
	trial._toggle_inspection()
	_check(trial.inspect_camera.current, "character close-up camera opens")
	trial._toggle_inspection()
	_check(walker.camera.current, "closing inspection restores the walker camera")
	for index in trial.humans.size():
		var human := trial.humans[index]
		var infected := trial.infected[index]
		_check(human.is_on_floor() and infected.is_on_floor(), "both forms on campus paving")
		_check(human.look.identity == index and infected.look.identity == index, "paired identity")
		_check(human.look.model.find_children("*", "Skeleton3D", true, false).size() == 1,
			"original skinned human rig loaded")
		_check(infected.look.animation.has_animation(&"Chase")
			and infected.look.animation.has_animation(&"Bite"), "retargeted zombie clips loaded")
		var human_colors := _vertex_colors(human.look.model)
		var infected_colors := _vertex_colors(infected.look.model)
		_check(not human_colors.is_empty() and human_colors.size() == infected_colors.size()
			and hash(human_colors) != hash(infected_colors), "matching character meshes with separate vertex colors")
		for form in [Walker.HUMAN, Walker.INFECTED, Walker.KING]:
			_select(index, form)
			_check(walker.identity == index and walker.role == form, "control transfers to each role")
			_check(walker.look.infected == (form != Walker.HUMAN), "controllable appearance follows form")
		_select(index, Walker.HUMAN)
		trial.perform_demo(&"walk")
		await _wait(16)
		_check(human.look.animation.current_animation == &"campus/walk", "human walking clip")
		_check(human.global_position.z < human.home.z - 0.15, "human physically moves")
		trial.perform_demo(&"stop")
		await _wait(3)
		_check(human.look.animation.current_animation == &"campus/idle", "idle after interrupt")
		_select(index, Walker.INFECTED)
		trial.perform_demo(&"walk")
		await _wait(17)
		_check(infected.look.animation.current_animation == &"campus/walk", "infected walking clip")
		trial.perform_demo(&"run")
		await _wait(17)
		_check(infected.look.animation.current_animation == &"campus/sprint", "infected chase clip")
		trial.perform_demo(&"home")
		await _wait(90)
		_check(absf(infected.global_position.z - infected.home.z) < 0.08, "infected returns to position")
	print("CHARACTERS appearances and five pairs of moving demos checked")
	trial._reset_trial()
	_select(4, Walker.HUMAN)
	trial.perform_demo(&"guide")
	await _wait(92)
	_check(absf(trial.humans[4].global_position.z - Trial.LINE_Z + Trial.MOVE_DISTANCE) < 0.08
		and trial.humans[4].move_speed == 0.0 and "跟我走" in trial.status.text, "guide arrives, stops and prompts")
	_select(3, Walker.HUMAN)
	trial.perform_demo(&"stun")
	_check(trial.infected[3].stun_remaining > 0.0, "strong role stuns the target")
	await _wait(125)
	_check(trial.infected[3].stun_remaining == 0.0, "stunned target recovers")
	_select(1, Walker.INFECTED)
	for pair in [[&"knock", &"interact-right"], [&"bite", &"attack-melee-right"]]:
		trial.perform_demo(pair[0])
		_check(trial.infected[1].look.gesture == pair[1], "infected gesture begins")
		var animation := trial.infected[1].look.animation
		var seconds := animation.get_animation(animation.current_animation).length / animation.speed_scale
		await _wait(ceili(seconds * 60.0) + 12)
		_check(trial.infected[1].look.animation.current_animation == &"campus/idle", "infected gesture completes")
	_select(4, Walker.KING)
	trial.perform_demo(&"signal")
	var moving := trial.infected.filter(func(actor): return actor.move_speed > 0.0)
	_check(moving.size() == 2, "king commands two distinct zombies")
	await _wait(18)
	for actor in moving:
		_check(actor.global_position.z < actor.home.z - 0.2, "command moves the follower")
	print("CHARACTERS guide, stun, recovery, knock, bite and command checked")
	await _check_player()
	trial._reset_trial()
	var escape := InputEventAction.new()
	escape.action = &"ui_cancel"
	escape.pressed = true
	walker._unhandled_input(escape)
	await tree.scene_changed
	_check(tree.current_scene.scene_file_path == MENU, "return to main menu")
	print("CAMPUS CHARACTERS ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)

func _check_player() -> void:
	trial._reset_trial()
	_select(2, Walker.HUMAN)
	walker.footstep.connect(func(_at: Vector3, strength: float): footsteps.append(strength))
	_key(KEY_TAB)
	var start := walker.global_position
	Input.action_press(&"move_forward")
	await _wait(18)
	Input.action_release(&"move_forward")
	_check(walker.global_position.distance_to(start) > 0.72 and 1.0 in footsteps, "walk and footstep")
	footsteps.clear()
	_key(KEY_C)
	start = walker.global_position
	Input.action_press(&"move_forward")
	await _wait(18)
	Input.action_release(&"move_forward")
	_check(walker.global_position.distance_to(start) > 0.30 and footsteps.is_empty(), "quiet motion emits no footsteps")
	_key(KEY_C)
	_key(KEY_V)
	_check(walker.follow_camera.current and walker.look.visible, "third-person camera and body")
	_key(KEY_V)
	_check(walker.camera.current and not walker.look.visible, "first-person camera and hidden body")
	Input.action_press(&"crouch")
	for frame in 30:
		if is_equal_approx(walker.capsule.height, Walker.CROUCH_HEIGHT):
			break
		await _wait(1)
	_check(walker.crouched and is_equal_approx(walker.capsule.height, Walker.CROUCH_HEIGHT), "crouch reduces collision height")
	Input.action_release(&"crouch")
	for frame in 30:
		if not walker.crouched:
			break
		await _wait(1)
	_check(not walker.crouched and walker.capsule.height > Walker.CROUCH_HEIGHT, "standing restores height")
	Input.action_press(&"sprint")
	_check(walker._movement_speed() > 6.0, "tall role sprint is faster")
	Input.action_press(&"move_forward")
	await _wait(14)
	Input.action_release(&"move_forward")
	Input.action_release(&"sprint")
	_check(1.75 in footsteps, "sprint emits stronger footstep")

	_select(0, Walker.HUMAN)
	_place(Trial.BOOK_START + Vector3(0, -0.65, 1.05))
	walker.camera.look_at(trial.book.global_position)
	await _wait(6)
	_key(KEY_E)
	_check(trial.holding_book, "E picks up the physical book")
	_key(KEY_Q)
	var launch := trial.book.global_position
	await _wait(8)
	_check(not trial.holding_book and not trial.book.freeze
		and trial.book.global_position.distance_to(launch) > 0.45, "Q releases and moves rigid book")

	_place(Trial.DOOR_CENTER + Vector3(0, 0.10, 1.63))
	await _wait(10)
	var door: Dictionary = trial.doors.doors[trial.door_index]
	_check(walker.test_move(walker.global_transform, Vector3.FORWARD * 2.1), "closed test door blocks player")
	_key(KEY_E)
	await _wait(26)
	_check(door.open and not door.moving and not walker.test_move(walker.global_transform, Vector3.FORWARD * 2.1),
		"opened test door allows passage")
	_key(KEY_E)
	await _wait(26)
	_check(not door.open and walker.test_move(walker.global_transform, Vector3.FORWARD * 2.1), "door closes again")
	_select(0, Walker.INFECTED)
	_place(trial.humans[0].global_position + Vector3(0, 0.08, 1.1))
	await _wait(8)
	_key(KEY_G)
	_check(trial.humans[0].bite_count == 1, "controlled infected bite reaches test target")
	print("CHARACTERS player locomotion, stealth, camera, crouch, book, door and bite checked")

func _place(point: Vector3) -> void:
	walker.global_position = point
	walker.rotation = Vector3.ZERO
	walker.camera.rotation = Vector3.ZERO
	walker.velocity = Vector3.ZERO
	scene.refresh_collision()

func _select(index: int, form: int) -> void:
	trial.selected_role.select(index)
	trial.selected_role.item_selected.emit(index)
	trial.selected_form.select(form)
	trial.selected_form.item_selected.emit(form)
	trial._take_control()

func _key(code: Key) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.pressed = true
	walker._input(event)

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _vertex_colors(model: Node3D) -> PackedColorArray:
	var instance := model.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	return instance.mesh.surface_get_arrays(0)[Mesh.ARRAY_COLOR]

func _check(condition: bool, detail: String) -> void:
	if not condition:
		failed = true
		push_error("CHARACTER CHECK FAIL " + detail)
