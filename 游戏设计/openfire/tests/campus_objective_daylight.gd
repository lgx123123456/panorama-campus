extends Node

const OUTPUT := "C:/CampusReconstructionRuntime/flow-access-repair/"
var failed := false
var level: Node3D
var world: Node3D
var capture := false

func _ready() -> void:
	capture = "--capture" in OS.get_cmdline_user_args()
	if capture:
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)
	call_deferred("run")

func run() -> void:
	reparent(get_tree().root)
	get_tree().root.content_scale_mode = Window.CONTENT_SCALE_MODE_DISABLED
	await load_campus()
	var objective: PanelContainer = level.interface.get_node_or_null("CurrentObjective")
	check(objective != null, "current objective has an independent top-center panel")
	if objective == null:
		get_tree().quit(1)
		return
	var normal_text: String = level.briefing.text
	level.briefing.text = "当前目标 · 从宿舍东楼梯下到一层，沿教学楼之间的道路穿过尚德广场，再从正门门洞走出校园，完成本轮撤离  ·  128 米"
	for resolution: Vector2i in [Vector2i(800,600), Vector2i(1200,720), Vector2i(1600,900), Vector2i(2560,1440)]:
		get_tree().root.size = resolution
		await wait_frames(6)
		var rect: Rect2 = objective.get_global_rect()
		var viewport_size := get_viewport().get_visible_rect().size
		check(absf(rect.get_center().x - viewport_size.x * 0.5) < 1.1,
			"objective horizontally centered at %s" % resolution)
		check(rect.position.x >= 12 and rect.end.x <= viewport_size.x - 12,
			"objective stays within viewport at %s" % resolution)
		check(rect.end.y < viewport_size.y * 0.5 - 20,
			"objective stays above the crosshair at %s" % resolution)
		check(not rect.intersects(level.controls.get_parent().get_parent().get_global_rect()),
			"objective avoids control instructions at %s" % resolution)
		check(level.briefing.get_line_count() == level.briefing.get_visible_line_count()
			and level.briefing.size.y + 1 >= level.briefing.get_minimum_size().y,
			"long objective text is fully visible at %s" % resolution)
		var normal_scale: Vector2 = level.briefing.scale
		level.briefing.scale = Vector2(1.02,1.02)
		check(rect.encloses(level.briefing.get_global_rect()),
			"maximum breathing scale remains inside the padded panel at %s" % resolution)
		check(is_instance_valid(level.debug_toggle)
			and not rect.intersects(level.debug_toggle.get_global_rect()),
			"F6 debug button avoids the objective including maximum breathing at %s" % resolution)
		check(level.briefing.pivot_offset.is_equal_approx(level.briefing.size * .5),
			"breathing pivot is centered at %s" % resolution)
		level.briefing.scale = normal_scale
		if resolution.x == 800:
			check(level.briefing.get_line_count() >= 2, "small-window objective exercises actual text wrapping")
			if capture:
				await capture_view("night-long-objective-800")
		print("OBJECTIVE RECT ", resolution, " panel=", rect, " lines=", level.briefing.get_line_count())
	level.briefing.text = normal_text
	get_tree().root.size = Vector2i(1600,900)
	await wait_frames(8)
	check(not level.weather.get("daylight"), "campaign starts at night")
	check(level.night_audio._music.playing, "campaign retains night music before free roam")
	if capture:
		await capture_view("night-objective-1600")
	level.weather.begin_rain(30.0)
	level.weather._process(4.1)
	check(level.weather.is_raining and level.weather.rain_intensity > .95,
		"rain is active before the free-roam transition")
	level._finish("成功撤离 · 已走出正门")
	await wait_frames(3)
	check(not objective.visible, "result menu has no objective panel overlay")
	press_free_roam()
	await get_tree().scene_changed
	await verify_daylight("victory")
	if capture:
		await capture_view("daylight-free-roam-1600")
	await load_campus()
	level._turn_player()
	check(level.round_finished and level.result_panel.visible, "infection opens the result menu")
	press_free_roam()
	await get_tree().scene_changed
	await verify_daylight("infection")
	print("OBJECTIVE DAYLIGHT ", "FAIL" if failed else "PASS")
	get_tree().quit(1 if failed else 0)

func load_campus() -> void:
	get_tree().change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await get_tree().scene_changed
	world = get_tree().current_scene
	level = world.get_node("CharacterTrial")
	level.walker.set_physics_process(false)
	level.spawner.set_physics_process(false)
	level.campaign.set_physics_process(false)
	level.walker.global_position = Vector3(-69.9,0.30,-112.6)
	level.walker.rotation.y = -1.68
	level.walker.camera.rotation.x = -.05
	world.refresh_collision()
	await wait_frames(12)

func press_free_roam() -> void:
	var button: Button = level.result_panel.find_children("*", "Button", true, false).filter(
		func(item: Button): return item.text == "自由探索")[0]
	button.pressed.emit()

func verify_daylight(reason: String) -> void:
	world = get_tree().current_scene
	await wait_frames(20)
	check(world.scene_file_path == "res://scenes/campus/free_tour.tscn",
		reason + " loads the shared free tour scene")
	check(not world.has_node("CharacterTrial"), reason + " leaves the campaign and its weather/audio")
	var walker = world.get_node("Walker")
	var sun: DirectionalLight3D = world.get_node("Sun")
	var environment: Environment = world.get_node("WorldEnvironment").environment
	check(walker.mode == walker.Mode.WALK and walker.mouse_captured and walker.position.z > 10.5,
		reason + " starts on foot at the main gate")
	check(sun.light_energy > .9 and sun.light_color.r > .9 and sun.rotation_degrees.x < -45,
		reason + " uses the daylight sun")
	check(environment.sky.sky_material is ProceduralSkyMaterial and environment.ambient_light_energy > .5,
		reason + " restores the original daylight environment")

func capture_view(filename: String) -> void:
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	world.get_node("Walker")._capture_mouse(false)
	await wait_frames(5)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(OUTPUT + filename + ".png")

func wait_frames(count: int) -> void:
	for frame in count:
		await get_tree().physics_frame

func check(condition: bool, message: String) -> void:
	if not condition:
		failed = true
		push_error(message)
