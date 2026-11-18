extends Node

const MENU := "res://scenes/main_menu.tscn"
var trial: Node3D
var frame: Node3D
var walker: CharacterBody3D

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file(MENU)
	await tree.scene_changed
	tree.current_scene.get_node("%CampusButton").pressed.emit()
	await tree.scene_changed
	trial = tree.current_scene
	frame = trial.get_node("CampusFrame")
	walker = trial.get_node("Walker")
	for i in 6:
		await tree.physics_frame
	if not walker.is_on_floor():
		_fail("spawn is not on the floor")
		return
	print("CAMPUS spawn ", _position())
	if not await _go(-5.15, -11.36) or not await _go(-2.65, -11.36):
		_fail("first classroom threshold")
		return
	print("CAMPUS classroom 1 ", _position())
	if not await _go(-5.10, -11.36) or not await _go(-5.10, -21.38) or not await _go(-2.65, -21.38):
		_fail("second classroom threshold")
		return
	print("CAMPUS classroom 2 ", _position())
	if not await _go(-5.10, -21.38) or not await _go(-5.10, -2.33) or not await _go(-0.79, -2.33):
		_fail("classroom to stairs")
		return
	if not await _go(-0.79, -7.37) or absf(_position().y - 2.4) > 0.18:
		_fail("first flight and half landing")
		return
	print("CAMPUS landing ", _position())
	if not await _go(0.45, -7.37) or not await _go(0.45, -2.78) or absf(_position().y - 4.32) > 0.18:
		_fail("second flight and upper landing")
		return
	print("CAMPUS upper floor ", _position())
	if not await _go(0.45, -7.37) or not await _go(-0.79, -7.37) or not await _go(-0.79, -2.33):
		_fail("walking back down the stairs")
		return
	if absf(_position().y - 0.48) > 0.18:
		_fail("return to ground floor elevation")
		return
	var reset := InputEventAction.new()
	reset.action = "reload"
	reset.pressed = true
	walker._unhandled_input(reset)
	if _position().distance_to(Vector3(-5.05, 0.54, -7.10)) > 0.05:
		_fail("reset did not return to spawn")
		return
	var escape := InputEventAction.new()
	escape.action = "ui_cancel"
	escape.pressed = true
	walker._unhandled_input(escape)
	await tree.scene_changed
	if tree.current_scene.scene_file_path != MENU:
		_fail("Escape did not return to menu")
		return
	print("CAMPUS PASS two classrooms, stairs in both directions, reset, menu")
	tree.current_scene.get_node("%GatePlazaButton").pressed.emit()
	await tree.scene_changed
	trial = tree.current_scene
	frame = trial
	walker = trial.get_node("Walker")
	for i in 18:
		await tree.physics_frame
	if not walker.is_on_floor():
		_fail("exterior spawn is not on the floor")
		return
	if not await _go(0.0, 2.0) or not await _go(0.0, -10.0) or not await _go(0.0, -18.45):
		_fail("gate to plaza walk")
		return
	print("CAMPUS plaza ", _position())
	if not await _go(0.0, -10.0) or not await _go(0.0, 4.0):
		_fail("walking back out through the gate")
		return
	walker._unhandled_input(escape)
	await tree.scene_changed
	if tree.current_scene.scene_file_path != MENU:
		_fail("exterior Escape did not return to menu")
		return
	print("CAMPUS PASS gate to plaza and return to menu")
	tree.quit()

func _position() -> Vector3:
	return frame.to_local(walker.global_position)

func _go(x: float, z: float) -> bool:
	var tree := get_tree()
	var target := Vector2(x, z)
	for i in 490:
		var p := _position()
		var move := target - Vector2(p.x, p.z)
		if move.length() < 0.09:
			_release()
			return true
		_release()
		if absf(move.x) > 0.041:
			Input.action_press("move_right" if move.x > 0.0 else "move_left")
		if absf(move.y) > 0.041:
			Input.action_press("move_back" if move.y > 0.0 else "move_forward")
		await tree.physics_frame
		if i == 480:
			for index in walker.get_slide_collision_count():
				var hit := walker.get_slide_collision(index)
				print("CAMPUS collider ", hit.get_collider().get_parent().name, " normal ", frame.global_basis.inverse() * hit.get_normal(), " pos ", frame.to_local(hit.get_position()))
	_release()
	print("CAMPUS blocked at ", _position(), " toward ", target)
	return false

func _release() -> void:
	for action in [&"move_right", &"move_left", &"move_back", &"move_forward"]:
		Input.action_release(action)

func _fail(message: String) -> void:
	print("CAMPUS FAIL ", message)
	get_tree().quit(1)
