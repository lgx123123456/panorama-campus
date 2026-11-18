extends Node

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/interior.tscn")
	await tree.scene_changed
	var scene := tree.current_scene
	var walker := scene.get_node("Walker") as CharacterBody3D
	var frame := scene.get_node("CampusFrame") as Node3D
	var slider := scene.get_node("Interface/DebugControls/Rows/Speed") as HSlider
	_key(walker, KEY_TAB)
	_check(not walker.mouse_captured, "Tab releases cursor")
	await tree.process_frame
	var rect := slider.get_global_rect()
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = rect.position + Vector2(rect.size.x * 0.25, rect.size.y / 2.0)
	get_viewport().push_input(press, true)
	var drag := InputEventMouseMotion.new()
	drag.position = rect.position + Vector2(rect.size.x * 0.8, rect.size.y / 2.0)
	drag.relative = drag.position - press.position
	drag.button_mask = MOUSE_BUTTON_MASK_LEFT
	get_viewport().push_input(drag, true)
	press.pressed = false
	press.position = drag.position
	get_viewport().push_input(press, true)
	_check(slider.value >= 14.0, "mouse drag changes speed slider")
	slider.value = 4.0
	_check(is_equal_approx(walker.speed_multiplier, 4.0), "slider updates movement speed")
	var start := walker.global_position
	Input.action_press("move_forward")
	for i in 12:
		await tree.physics_frame
	_check(Vector2(start.x, start.z).distance_to(Vector2(walker.global_position.x, walker.global_position.z)) < 0.01, "cursor mode pauses movement")
	_key(walker, KEY_TAB)
	_key(walker, KEY_F)
	_check(walker.flying and walker.collision_mask == 0, "flight disables collision")
	walker.camera.rotation.x = PI / 4.0
	start = walker.global_position
	for i in 60:
		await tree.physics_frame
	Input.action_release("move_forward")
	_check(walker.global_position.y > start.y + 5.0, "flight follows upward camera direction")
	_check(walker.global_position.distance_to(start) > 10.0, "flight movement uses speed slider")
	_key(walker, KEY_F)
	_check(not walker.flying and walker.collision_mask == 1, "walking restores collision")
	slider.value = 2.0
	var contact_frames := 0
	var slowest_us := 0
	var contact_times: Array[int] = []
	walker.set_physics_process(false)
	# Push into classroom walls and the furniture from several directions.
	for multiplier in [2.0, 20.0]:
		slider.value = multiplier
		for position in [Vector3(-3.5, 0.63, -14), Vector3(0, 0.63, -15), Vector3(2, 0.63, -19)]:
			walker.global_transform = frame.global_transform
			walker.global_position = frame.to_global(position)
			walker.velocity = Vector3.ZERO
			Input.action_press("move_right")
			for i in 180:
				var before := Time.get_ticks_usec()
				walker._physics_process(1.0 / 60.0)
				var elapsed := Time.get_ticks_usec() - before
				contact_times.append(elapsed)
				slowest_us = maxi(slowest_us, elapsed)
				for collision in walker.get_slide_collision_count():
					if absf(walker.get_slide_collision(collision).get_normal().y) < 0.7:
						contact_frames += 1
						break
				await tree.physics_frame
			Input.action_release("move_right")
	_check(contact_frames > 120, "collision contact workload actually ran")
	contact_times.sort()
	print("CAMPUS CONTACT frames=", contact_frames, " slowest_frame_us=", slowest_us, " p95_us=", contact_times[int(contact_times.size() * 0.95)])
	if DisplayServer.get_name() != "headless":
		walker._reset_position()
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("res://.tools/validation/debug-controls.png")
	print("CAMPUS DEBUG PASS speed, cursor, flight, collision restoration and sustained contact")
	tree.quit()

func _key(walker: CharacterBody3D, key: Key) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = key
	event.pressed = true
	walker._input(event)

func _check(condition: bool, message: String) -> void:
	if not condition:
		push_error("CAMPUS DEBUG FAIL " + message)
		get_tree().quit(1)
		assert(condition, message)

