extends Node

var failed := false

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await tree.scene_changed
	var menu := tree.current_scene
	menu.campus_loading_path = "pending-campus-load"
	menu._set_campus_loading(true)
	menu._update_play_gate()
	for name in ["HostButton", "JoinButton", "SoloButton", "ContinueBtn"]:
		_check(menu.get_node("%" + name).disabled, "menu stays gated during campus loading")
	menu.campus_loading_path = ""
	menu._set_campus_loading(false)
	var ai_ready: bool = tree.root.get_node("ComfyUI").is_ready()
	for name in ["HostButton", "JoinButton", "SoloButton"]:
		_check(menu.get_node("%" + name).disabled == not ai_ready, "menu restores AI readiness after campus loading")
	_check(not menu.get_node("%ContinueBtn").disabled, "continue is restored after campus loading")
	menu.get_node("%GatePlazaButton").pressed.emit()
	await tree.scene_changed
	var scene := tree.current_scene
	if DisplayServer.get_name() != "headless":
		var overlay := tree.root.get_node_or_null("CampusLoadingOverlay")
		_check(overlay != null, "loading overlay survives the scene handoff")
		if overlay != null:
			await RenderingServer.frame_post_draw
			var entering_walker := scene.get_node("Walker") as CharacterBody3D
			_check(not entering_walker.is_processing_input(), "gameplay waits for rendering warmup")
			await overlay.tree_exited
			_check(entering_walker.is_processing_input() and entering_walker.mouse_captured,
				"camera input resumes after the overlay")
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_full_manifest.json"))
	var instances := 0
	var triangles := 0
	var envelope := AABB()
	for node in scene.get_node("CampusVisuals").find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var box := mesh_node.global_transform * mesh_node.get_aabb()
		envelope = box if instances == 0 else envelope.merge(box)
		instances += 1
		for surface in mesh_node.mesh.get_surface_count():
			var arrays: Array = mesh_node.mesh.surface_get_arrays(surface)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var count := indices.size()
			if count == 0:
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				count = vertices.size()
			triangles += count / 3
	_check(instances == int(manifest.game_mesh_instances), "all campus mesh instances imported")
	_check(triangles == int(manifest.master_triangles), "complete master geometry imported")
	print("CAMPUS FULL COVERAGE instances=", instances, " triangles=", triangles, " bounds=", envelope)
	var walker := scene.get_node("Walker") as CharacterBody3D
	walker._set_flying(true)
	var center := envelope.get_center()
	for direction in [Vector3(-1, 0, -1), Vector3(1, 0, -1), Vector3(1, 0, 1)]:
		walker.global_position = center + direction * envelope.size * 0.3
		walker.global_position.y = 2.0
		for frame in 15:
			await tree.physics_frame
		_check_collision(scene, walker.global_position)
	# A distant R reset and F landing must refresh the collision immediately.
	walker._reset_position()
	_check_collision(scene, walker.global_position)
	walker.global_position = center + Vector3(40, 3, -40)
	walker._set_flying(false)
	_check_collision(scene, walker.global_position)
	walker._reset_position()
	for frame in 15:
		await tree.physics_frame
	_check(walker.is_on_floor(), "full-campus spawn stays on its floor")
	if DisplayServer.get_name() != "headless":
		var camera := walker.get_node("Camera3D") as Camera3D
		var aspect := float(get_viewport().get_visible_rect().size.x) / get_viewport().get_visible_rect().size.y
		var height := maxf(envelope.size.x / aspect, envelope.size.z) / (2.0 * tan(deg_to_rad(camera.fov) / 2.0)) * 1.12
		camera.global_position = center + Vector3(0, height, 0)
		camera.look_at(center, Vector3.FORWARD)
		for frame in 10:
			await tree.process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("res://.tools/validation/campus-full-overview.png")
	print("CAMPUS FULL ", "FAIL" if failed else "PASS", " coverage, remote collision activation, reset and landing")
	tree.quit(1 if failed else 0)

func _check_collision(scene: Node, position: Vector3) -> void:
	for body in scene.get_node("CampusCollision").get_children():
		var box: AABB = body.get_meta("bounds")
		var active := position.clamp(box.position, box.end).distance_squared_to(position) <= 65.0 * 65.0
		var registered := PhysicsServer3D.body_get_space(body.get_rid()).is_valid()
		if (body.collision_layer == 1) != active or registered != active:
			_check(false, "collision activation mismatch at " + str(position))
			return

func _check(condition: bool, message: String) -> void:
	if not condition:
		failed = true
		push_error("CAMPUS FULL FAIL " + message)
