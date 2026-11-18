extends Node

const Level = preload("res://scripts/campus/campus_zombie_level.gd")
const Spawner = preload("res://scripts/campus/campus_zombie_spawner.gd")
var failed := false
var level: Level

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	await tree.process_frame
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await tree.scene_changed
	tree.current_scene.get_node("%ZombieTrialButton").pressed.emit()
	await tree.scene_changed
	level = tree.current_scene.get_node("CharacterTrial")
	await _wait(90)
	_check(is_instance_valid(level.weather) and is_instance_valid(level.night_audio), "night systems connected through menu")
	_check(level.night_audio._music.playing and level.night_audio._rain.playing, "instrumental and rain players running")
	_check(level.spawner.zombies.is_empty() and level.spawner.remaining > 0, "first wave waits a minute")
	level.spawner.remaining = INF
	if "--capture" in OS.get_cmdline_user_args():
		await _capture("night-classroom")
	level.walker.global_position = Vector3(-69.9, 0.30, -112.6)
	level.walker.rotation.y = -1.68
	level.walker.set_physics_process(false)
	level.armor = 10000
	tree.current_scene.refresh_collision()
	await _wait(60)
	if "--capture" in OS.get_cmdline_user_args():
		level.walker.camera.rotation.x = 0.65
		await _capture("night-sky")
		level.walker.camera.rotation.x = 0.0
	level.weather.begin_rain(30.0)
	await _wait(270)
	_check(level.weather.rain_intensity > 0.95 and level.night_audio.rain_gain > 0.4, "rain becomes visible and audible outside")
	if "--capture" in OS.get_cmdline_user_args():
		await _capture("night-rain-outside")
	var map := level.get_world_3d().navigation_map
	for index in Spawner.ACTIVE_LIMIT:
		var sample := Vector3(-90.0 + (index % 20) * 2.1, 0.25, -108.0 + floori(index / 20.0) * 2.1)
		var point := NavigationServer3D.map_get_closest_point(map, sample)
		level.spawner._spawn(point)
		await _wait(1)
	_check(level.spawner.zombies.size() == 200 and level.spawner.try_group() == 0, "200 live actors prevent another batch")
	await _wait(90)
	var frames: Array[float] = []
	var previous := Time.get_ticks_usec()
	for frame in 180:
		await tree.process_frame
		var now := Time.get_ticks_usec()
		frames.append(float(now - previous) / 1000.0)
		previous = now
	frames.sort()
	print("NIGHT 200 actors frame ms median=", frames[90], " p95=", frames[171], " max=", frames[-1],
		" physics_ms=", Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0,
		" memory_MB=", Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0)
	if "--capture" in OS.get_cmdline_user_args():
		await _capture("night-200-zombies")
	if "--profile" in OS.get_cmdline_user_args():
		for zombie in level.spawner.zombies:
			zombie.look.process_mode = Node.PROCESS_MODE_DISABLED
		await _profile("animation paused")
		for zombie in level.spawner.zombies:
			zombie.set_physics_process(false)
		await _profile("physics paused")
		for zombie in level.spawner.zombies:
			zombie.look.hide()
		await _profile("characters hidden")
		tree.quit(1 if failed else 0)
		return
	var remote = level.spawner.zombies[-1]
	remote.global_position = level.walker.global_position + Vector3(80, 0, 0)
	remote.far_time = 89.0
	await _wait(2)
	_check(remote.dormant, "distant zombie sleeps without falling through streamed campus")
	remote.global_position = level.walker.global_position + Vector3(20, 0, 0)
	await _wait(2)
	_check(remote.far_time == 0 and not remote.dormant, "returning nearby resets timeout and wakes actor")
	remote.global_position = level.walker.global_position + Vector3(80, 0, 0)
	remote.far_time = 90.0
	await _wait(2)
	_check(not is_instance_valid(remote), "90 seconds far away recycles actor")
	while level.spawner.zombies.size() < 199:
		level.spawner._spawn(level.walker.global_position + Vector3(20, 0, 0))
	_check(level.spawner.try_group() == 0, "one available slot preserves two-zombie batch minimum")
	for zombie in level.spawner.zombies:
		zombie.queue_free()
	level.spawner.zombies.clear()
	level.spawner.batch_remaining = 2
	level.spawner.batch_attempts = 0
	await _wait(2)
	_check(level.spawner.batch_remaining == 0 and level.spawner.zombies.is_empty(),
		"exhausted sampling stops issuing navigation queries for the wave")
	var weather_ref: WeakRef = weakref(level.weather)
	var audio_ref: WeakRef = weakref(level.night_audio)
	tree.change_scene_to_file("res://scenes/main_menu.tscn")
	await tree.scene_changed
	await _wait(2)
	_check(weather_ref.get_ref() == null and audio_ref.get_ref() == null, "leaving campus releases weather and audio")
	print("CAMPUS NIGHT ", "FAIL" if failed else "PASS")
	tree.quit(1 if failed else 0)

func _capture(filename: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("C:/CampusReconstructionRuntime/" + filename + ".png")

func _profile(label: String) -> void:
	await _wait(30)
	var began := Time.get_ticks_usec()
	for frame in 90:
		await get_tree().process_frame
	print("PROFILE ", label, " average_ms=", float(Time.get_ticks_usec() - began) / 90000.0,
		" physics_ms=", Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame

func _check(condition: bool, message: String) -> void:
	if not condition:
		failed = true
		push_error(message)
