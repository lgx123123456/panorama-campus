extends SceneTree

const Passages := preload("res://scripts/campus/campus_field_passages.gd")

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await scene_changed
	var campus := current_scene
	var walker: CharacterBody3D = campus.get_node("Walker")
	walker._set_speed(1.0)
	var ok := campus.has_node("FieldPassages")
	for index in Passages.APPROACH.size():
		walker.global_position = Passages.APPROACH[index]
		walker.velocity = Vector3.ZERO
		campus.refresh_collision()
		for settle in 6:
			await physics_frame
		ok = await walk(walker, Passages.EXIT[index], "gate %d outward" % (index + 1)) and ok
		ok = await walk(walker, Passages.APPROACH[index], "gate %d return" % (index + 1)) and ok
		if index >= 2:
			ok = await walk(walker, Passages.EXIT[index], "gate %d repeat" % (index + 1)) and ok
			ok = await walk(walker, Vector3(Passages.EXIT[index].x, 0.12, -18.8),
				"gate %d sheltered exit" % (index + 1)) and ok
	print("FIELD PASSAGES ", "PASS" if ok else "FAIL")
	quit(0 if ok else 1)

func walk(walker: CharacterBody3D, target: Vector3, label: String) -> bool:
	var direction := target - walker.global_position
	direction.y = 0.0
	walker.rotation.y = atan2(-direction.x, -direction.z)
	Input.action_press("move_forward")
	var complete := false
	for frame in 1700:
		await physics_frame
		var remaining := target - walker.global_position
		remaining.y = 0.0
		if remaining.length() < 0.14:
			complete = true
			break
	Input.action_release("move_forward")
	walker.velocity = Vector3.ZERO
	print("FIELD ", label, " ", "PASS" if complete else "FAIL", " at ", walker.global_position)
	return complete
