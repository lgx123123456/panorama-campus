extends Node

const Tour = preload("res://scripts/campus/campus_tour_walker.gd")

var failed := false
var capture := false


func _ready() -> void:
	capture = "--capture" in OS.get_cmdline_user_args()
	_run.call_deferred()


func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	if tree.current_scene == self:
		tree.current_scene = null
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await get_tree().scene_changed
	var menu := get_tree().current_scene
	var menu_button := _button(menu.get_node("CampusTitle"), "自由探索")
	check(menu_button != null, "public menu offers free tour")
	if menu_button == null:
		get_tree().quit(1)
		return
	menu_button.pressed.emit()
	await get_tree().scene_changed
	check(get_tree().current_scene.scene_file_path == Tour.SCENE, "menu route loads free tour")
	var world := get_tree().current_scene
	var walker: Tour = world.get_node("Walker")
	var scooter: Tour.Scooter = world.get_node("Scooter")
	if DisplayServer.get_name() != "headless":
		for frame in 180:
			if walker.ui.modal_kind == "intro":
				_button(walker.ui.modal, "开始游览").pressed.emit()
				break
			await frames(1)
	await frames(30)
	check(walker.mode == Tour.Mode.WALK and walker.is_on_floor()
		and absf(walker.position.x) < 0.1 and walker.position.z > 10.5,
		"on foot outside the main gate, facing campus")
	check(not world.has_node("CharacterTrial") and not world.get_node("WorldEnvironment").environment.fog_enabled,
		"daylight campus with no campaign objects")
	await screenshot("gate")

	var start := walker.position
	Input.action_press("move_forward")
	await frames(38)
	check(walker.position.z < start.z - 1.0, "walk advances toward campus")
	var walk_speed := walker.velocity.length()
	Input.action_press("sprint")
	await frames(38)
	check(walker.velocity.length() > walk_speed + 1.0, "Shift runs")
	Input.action_release("move_forward")
	Input.action_release("sprint")

	tap(KEY_R)
	await frames(18)
	tap(KEY_F)
	await frames(4)
	Input.action_press("jump")
	await frames(68)
	Input.action_release("jump")
	check(walker.mode == Tour.Mode.JETPACK and walker.position.y > 5.0
		and walker.jetpack.visible and walker.collision_mask & 1 != 0,
		"jetpack climbs with solid campus collision")
	await screenshot("flight")
	var altitude := walker.position.y
	Input.action_press("crouch")
	await frames(28)
	Input.action_release("crouch")
	check(walker.position.y < altitude - 1.0, "Ctrl descends")
	tap(KEY_P)
	await frames(8)
	var frozen := walker.position
	check(walker.ui.modal_visible() and walker.ui.code.text.begins_with("C1/")
		and walker.ui.code.text.split("/").size() == 5 and walker.ui.SURVEY_URL.ends_with("/28723469/bcqi/"),
		"photo window includes current location and the survey")
	Input.action_press("jump")
	await frames(12)
	Input.action_release("jump")
	check(walker.position.is_equal_approx(frozen), "photo window freezes transport")
	await screenshot("report")
	tap(KEY_ESCAPE)
	await frames(2)
	check(not walker.ui.modal_visible() and walker.mouse_captured, "closing photo restores flight controls")
	tap(KEY_R)
	await frames(20)
	check(walker.mode == Tour.Mode.WALK and not walker.jetpack.visible, "R returns to gate on foot")

	walker.global_position = scooter.global_position + Vector3(-1.25, 0.08, 0.25)
	var toward := scooter.global_position - walker.global_position
	walker.rotation.y = atan2(-toward.x, -toward.z)
	await frames(15)
	tap(KEY_E)
	await frames(9)
	check(walker.mode == Tour.Mode.SCOOTER and walker.collision_layer == 0, "E mounts the nearby scooter")
	await screenshot("scooter")
	var parked := scooter.position
	Input.action_press("move_forward")
	await frames(60)
	check(scooter.position.distance_to(parked) > 1.8 and walker.position.distance_to(scooter.position) < 0.08,
		"scooter accelerates and camera follows rider")
	var old_yaw := scooter.rotation.y
	Input.action_press("move_left")
	await frames(26)
	Input.action_release("move_left")
	check(absf(angle_difference(old_yaw, scooter.rotation.y)) > 0.2, "scooter steers")
	Input.action_release("move_forward")
	Input.action_press("jump")
	await frames(65)
	Input.action_release("jump")
	check(absf(scooter.drive_speed) < 0.05, "Space brakes scooter")
	Input.action_press("move_back")
	await frames(24)
	check(scooter.drive_speed < -0.4, "S reverses scooter")
	Input.action_release("move_back")
	await frames(25)
	tap(KEY_E)
	await frames(14)
	check(walker.mode == Tour.Mode.WALK and walker.is_on_floor()
		and walker.position.distance_to(scooter.position) > 0.75, "E dismounts onto clear ground")
	await exercise_scooter_terrain(world, walker, scooter)
	await exercise_teaching_wall(world, walker, scooter)
	tap(KEY_V)
	await frames(2)
	check(walker.camera.current and not walker.look.visible, "V changes to first-person")
	tap(KEY_ESCAPE)
	await frames(2)
	check(walker.ui.modal_visible(), "Esc opens the pause menu")
	_button(walker.ui.modal, "返回主菜单").pressed.emit()
	await get_tree().scene_changed
	check(get_tree().current_scene.scene_file_path == "res://scenes/main_menu.tscn", "pause menu returns to main title")
	get_tree().quit(1 if failed else 0)


func exercise_scooter_terrain(world: Node3D, walker: Tour, scooter: Tour.Scooter) -> void:
	var origin := Vector3(0, 45, 20)
	_terrain_block(world, origin + Vector3(0, -0.25, -4), Vector3(12, 0.5, 24))
	_terrain_block(world, origin + Vector3(-3.0, 0.0125, -1.4), Vector3(2.8, 0.025, 0.55))
	for step in 4:
		var height := (step + 1) * 0.17
		_terrain_block(world, origin + Vector3(-3.0, height * 0.5, -2.0 - step * 0.33),
			Vector3(2.8, height, 0.33))
	_terrain_block(world, origin + Vector3(-3.0, 0.34, -5.6), Vector3(2.8, 0.68, 6.21))
	_terrain_block(world, origin + Vector3(3.0, 4.25, -5.5), Vector3(4.0, 8.5, 4.0))
	scooter.global_transform = Transform3D(Basis.IDENTITY, origin + Vector3(-3.0, 0.04, 0))
	walker._mount()
	await frames(8)
	Input.action_press("move_forward")
	await frames(108)
	Input.action_release("move_forward")
	check(scooter.position.y > origin.y + 0.60 and scooter.position.z < origin.z - 3.0,
		"scooter clears a 2.5 cm lip and four 17 cm stair risers")
	await screenshot("scooter-steps")

	scooter.stop()
	scooter.global_transform = Transform3D(Basis.IDENTITY, origin + Vector3(3.0, 0.04, 0))
	await frames(8)
	Input.action_press("move_forward")
	await frames(105)
	check(not scooter.is_climbing() and scooter.position.y < origin.y + 0.15,
		"vertical wall is solid in normal driving mode")
	tap(KEY_G)
	await frames(62)
	check(scooter.is_climbing() and scooter.position.y > origin.y + 4.0
		and absf(scooter.wall_normal.y) < 0.001, "G and W climb a vertical 90 degree wall")
	Input.action_release("move_forward")
	Input.action_press("jump")
	await frames(25)
	var wall_position := scooter.position
	await frames(24)
	check(scooter.position.distance_to(wall_position) < 0.08, "Space holds position on the wall")
	await screenshot("scooter-wall")
	Input.action_release("jump")
	Input.action_press("move_left")
	await frames(22)
	Input.action_release("move_left")
	check(scooter.is_climbing() and absf(scooter.position.x - wall_position.x) > 0.8,
		"A/D moves laterally across the wall")
	Input.action_press("move_back")
	await frames(42)
	Input.action_release("move_back")
	print("WALL REVERSE start=", wall_position, " after=", scooter.position, " grip=", scooter.is_climbing())
	check(scooter.is_climbing() and scooter.position.y < wall_position.y - 1.4,
		"S reverses down the wall")
	Input.action_press("move_forward")
	for frame in 160:
		if not scooter.is_climbing():
			break
		await frames(1)
	Input.action_release("move_forward")
	await frames(4)
	print("WALL ROOF position=", scooter.position, " grip=", scooter.is_climbing())
	check(not scooter.is_climbing() and scooter.position.y > origin.y + 8.4 and scooter.position.z < origin.z - 3.7,
		"wheels transfer from 90 degree wall onto a clear roof")
	await screenshot("scooter-roof")
	tap(KEY_R)
	await frames(24)
	check(walker.mode == Tour.Mode.WALK and not scooter.climb_enabled,
		"returning to gate resets wall-climb mode")


func exercise_teaching_wall(world: Node3D, walker: Tour, scooter: Tour.Scooter) -> void:
	var entrance := Vector3(-128.0, 0.0, -115.0)
	walker.global_position = entrance + Vector3.UP
	world.refresh_collision()
	await frames(3)
	var floor: Dictionary = scooter._ray(entrance + Vector3.UP * 2.2, entrance + Vector3.DOWN * 0.7)
	check(not floor.is_empty(), "B15 south test lane has ground")
	if floor.is_empty():
		return
	var start: Vector3 = floor.position + Vector3.UP * 0.045
	scooter.global_transform = Transform3D(Basis.looking_at(Vector3.FORWARD), start)
	walker._mount()
	await frames(5)
	tap(KEY_G)
	Input.action_press("move_forward")
	for frame in 400:
		if not scooter.is_climbing() and scooter.position.y > 16.0:
			break
		if capture and frame == 200:
			await screenshot("scooter-teaching-wall")
		await frames(1)
	Input.action_release("move_forward")
	await frames(5)
	print("B15 route start=", start, " finish=", scooter.position, " grip=", scooter.is_climbing())
	check(scooter.position.y > 19.5 and not scooter.is_climbing(),
		"scooter climbs the real B15 south wall and lands on the roof")
	if scooter.position.y > 19.5:
		await screenshot("scooter-teaching-roof")
	tap(KEY_R)
	await frames(18)


func _terrain_block(world: Node3D, center: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.position = center
	world.add_child(body)
	var shape := BoxShape3D.new()
	shape.size = size
	var collision := CollisionShape3D.new()
	collision.shape = shape
	body.add_child(collision)
	if capture:
		var mesh := BoxMesh.new()
		mesh.size = size
		var visual := MeshInstance3D.new()
		visual.mesh = mesh
		body.add_child(visual)


func tap(key: Key) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = key
	event.pressed = true
	Input.parse_input_event(event)
	var release := event.duplicate() as InputEventKey
	release.pressed = false
	Input.parse_input_event(release)


func frames(count: int) -> void:
	for index in count:
		await get_tree().physics_frame


func _button(root_node: Node, label: String) -> Button:
	for child in root_node.find_children("*", "Button", true, false):
		if child.text == label:
			return child
	return null


func screenshot(name: String) -> void:
	if not capture:
		return
	await frames(4)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("res://.tools/validation/tour-%s.png" % name)


func check(ok: bool, requirement: String) -> void:
	print("PASS " if ok else "FAIL ", requirement)
	failed = failed or not ok
