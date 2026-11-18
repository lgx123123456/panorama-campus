extends Node

var walker: CharacterBody3D

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	var scene := tree.current_scene
	walker = scene.get_node("Walker")
	walker.set_physics_process(false)
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	for link: Dictionary in data.teaching_bridge_entries.corridors:
		var entries: Array = data.doors.filter(func(record): return record.has("bridge") and record.building == link.building)
		for index in entries.size():
			var record: Dictionary = entries[index]
			var center := _point(record.center)
			var axis: Array = record.outward
			var outward := Vector3(float(axis[0]), 0, -float(axis[1]))
			walker.global_position = center + outward * 1.5 + Vector3.UP * .04
			walker.velocity = Vector3.ZERO
			scene.refresh_collision()
			for frame in 12:
				walker._physics_process(1.0/60.0)
				await tree.physics_frame
			var path: Array = link.paths[index]
			var targets: Array[Vector3] = [center]
			for point: Array in path.slice(1):
				targets.append(_point(point))
			targets.append(_point(link.join))
			for target in targets:
				if not await _go(target):
					print("BRIDGE WALK FAIL ", record.id, " at ", walker.global_position, " target ", target)
					tree.quit(1)
					return
			print("BRIDGE WALK PASS ", record.id, " into existing corridor")
	print("BRIDGE ENTRANCES PASS three aligned doors and corridors")
	tree.quit()

func _point(point: Array) -> Vector3:
	return Vector3(float(point[0]), float(point[2]), -float(point[1]))

func _go(target: Vector3) -> bool:
	for frame in 700:
		var delta := target - walker.global_position
		delta.y = 0
		if delta.length() < .13:
			Input.action_release("move_forward")
			return true
		walker.look_at(walker.global_position + delta)
		Input.action_press("move_forward")
		walker._physics_process(1.0/60.0)
		await get_tree().physics_frame
	Input.action_release("move_forward")
	for index in walker.get_slide_collision_count():
		var hit := walker.get_slide_collision(index)
		print("BRIDGE CONTACT ", hit.get_collider(), " at ", hit.get_position())
	return false
