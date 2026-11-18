extends Node

var failed := false

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	print("CAMPUS DOORS loading")
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	print("CAMPUS DOORS scene ready")
	var scene := tree.current_scene
	var walker: CharacterBody3D = scene.get_node("Walker")
	var controller := scene.get_node("Doors")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	_check(controller.doors.size() == data.doors.size() + 140, "all external and native classroom doors loaded")
	var expected_locked := ["B22_1", "B22_2", "B36", "B40E", "B40W", "B45"]
	var checked_locked: Array = []
	for index in data.doors.size():
		print("CAMPUS DOOR starting ", index)
		var door: Dictionary = controller.doors[index]
		var record: Dictionary = data.doors[index]
		var axis: Array = record.outward
		var outward := Vector3(float(axis[0]), 0, -float(axis[1]))
		var center: Vector3 = door.center
		if door.locked:
			checked_locked.append(door.id)
			await _check_locked(scene, walker, controller, index, center, outward)
			continue
		var probe := center + outward * 0.85
		var crossing := -outward * 1.7
		for route: Dictionary in data.get("dorm_end_doors", []):
			if route.id == record.id and route.has("basis"):
				# The east door now has a turning landing between two façades.
				var from: Array = route.points[-3]
				var to: Array = route.points[-1]
				probe = Vector3(float(from[0]), float(from[2]), -float(from[1]))
				crossing = Vector3(float(to[0]), float(to[2]), -float(to[1])) - probe
		walker.global_position = center + outward * 2.8 + Vector3.UP * 0.04
		scene.refresh_collision()
		await tree.physics_frame
		_check(controller.set_open(index, false), str(door.id) + " starts closing")
		await tree.create_timer(0.4).timeout
		walker.global_position = probe + Vector3.UP * 0.04
		await tree.physics_frame
		var result := KinematicCollision3D.new()
		var blocked := walker.test_move(walker.global_transform, crossing, result)
		_check(blocked and result.get_collider().name == "DoorCollision", str(door.id) + " closed door blocks capsule")
		walker.global_position = center + outward * 2.8 + Vector3.UP * 0.04
		_check(controller.set_open(index, true), str(door.id) + " starts opening")
		await tree.create_timer(0.4).timeout
		walker.global_position = probe + Vector3.UP * 0.04
		await tree.physics_frame
		result = KinematicCollision3D.new()
		blocked = walker.test_move(walker.global_transform, crossing, result)
		_check(not blocked, str(door.id) + " open capsule passage")
		print("CAMPUS DOOR ", door.id, " open_pass=", not blocked)
	checked_locked.sort()
	_check(checked_locked == expected_locked, "all six entrances are locked")
	var closed_buildings: Array = data.closed_buildings
	_check(closed_buildings.size() == 5, "all five building footprints restricted")
	walker._set_flying(true)
	for building: Dictionary in closed_buildings:
		var above := Vector3(0.0, float(building.height) + 2.0, 0.0)
		for point: Array in building.outline:
			above.x += float(point[0]) / building.outline.size()
			above.z -= float(point[1]) / building.outline.size()
		walker.global_position = above
		await tree.physics_frame
		var hit := KinematicCollision3D.new()
		var blocked := walker.test_move(walker.global_transform, Vector3.DOWN * 4.0, hit)
		_check(blocked and hit.get_collider().name == "ClosedBuilding_" + str(building.id),
			str(building.id) + " flight entry is blocked")
	walker._set_flying(false)
	await _check_close_range(scene, walker, controller, data, "B28")
	await _check_close_range(scene, walker, controller, data, "B15_1")
	# Start with E, move into the sweep during animation, then leave it.
	var first: Dictionary = controller.doors[0]
	var axis: Array = data.doors[0].outward
	var outward := Vector3(float(axis[0]), 0, -float(axis[1]))
	walker.global_position = first.center + outward * 2.8
	await tree.process_frame
	controller._process(0.0)
	var key := InputEventKey.new()
	key.physical_keycode = KEY_E
	key.pressed = true
	walker._input(key)
	_check(first.moving, "E starts nearest door")
	var leaf: Dictionary = first.pivots[0]
	var pivot: Node3D = leaf.node
	var target_angle: float = leaf.open_angle if first.open else leaf.closed_angle
	var middle_angle := (pivot.rotation.y + target_angle) * 0.5
	var sweep_direction := Basis(Vector3.UP, middle_angle - pivot.rotation.y) * pivot.transform.basis.x
	walker.global_position = pivot.get_parent().global_transform * (pivot.position + sweep_direction * float(leaf.sweep_tip) * 0.55)
	walker.global_position.y = first.center.y
	await tree.create_timer(0.4).timeout
	_check(first.moving and not first.tween.is_running(), "door pauses for approaching player")
	walker.global_position = first.center + outward * 2.8
	await tree.create_timer(0.4).timeout
	_check(not first.moving, "door resumes after player leaves sweep")
	if DisplayServer.get_name() != "headless":
		var camera: Camera3D = walker.get_node("Camera3D")
		var boys: Dictionary = controller.doors[3]
		camera.global_position = boys.center + Vector3(-13, 22, 32)
		camera.look_at(boys.center + Vector3(0, 2, 12))
		for frame in 12:
			await tree.process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("res://.tools/validation/campus-corrected-dorm.png")
	walker.global_position = first.center + outward * 2.8
	_check(controller.set_open(0, true), "start door animation before scene exit")
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await tree.scene_changed
	_check(not first.has("tween"), "scene exit releases active door tween")
	print("CAMPUS DOORS ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)

func _check_close_range(scene: Node, walker: CharacterBody3D, controller: Node, data: Dictionary, id: String) -> void:
	var index: int = controller._index_for_id(id)
	var door: Dictionary = controller.doors[index]
	var direction: Array = data.doors[index].outward
	var outward := Vector3(float(direction[0]), 0, -float(direction[1]))
	for side: float in [1.0, -1.0]:
		walker.global_position = door.center + outward * 2.8 + Vector3.UP * 0.04
		scene.refresh_collision()
		await get_tree().physics_frame
		_check(controller.set_open(index, false), id + " closes for approach test")
		await get_tree().create_timer(0.35).timeout
		walker.global_position = door.center + outward * side * 0.37 + Vector3.UP * 0.04
		await get_tree().physics_frame
		var input := InputEventKey.new()
		input.physical_keycode = KEY_E
		input.pressed = true
		walker._input(input)
		await get_tree().create_timer(0.35).timeout
		_check(door.open and not door.moving, id + " E opens when standing 37 cm from either side")


func _check_locked(scene: Node, walker: CharacterBody3D, controller: Node, index: int,
		center: Vector3, outward: Vector3) -> void:
	var door: Dictionary = controller.doors[index]
	walker.global_position = center + outward * 2.1 + Vector3.UP * 0.04
	scene.refresh_collision()
	await get_tree().physics_frame
	controller._process(0.0)
	var key := InputEventKey.new()
	key.physical_keycode = KEY_E
	key.pressed = true
	walker._input(key)
	_check(controller.nearby == index and "暂未开放" in controller.hint.text,
		str(door.id) + " shows locked entrance status")
	_check(not door.open and not door.moving and not controller.set_open(index, true),
		str(door.id) + " rejects both E and direct open requests")
	walker.global_position = center + outward * 0.80 + Vector3.UP * 0.04
	await get_tree().physics_frame
	var hit := KinematicCollision3D.new()
	var blocked := walker.test_move(walker.global_transform, -outward * 1.35, hit)
	_check(blocked and hit.get_collider().name == "DoorCollision",
		str(door.id) + " locked leaf blocks the capsule")

func _check(condition: bool, description: String) -> void:
	if not condition:
		failed = true
		push_error(description)
