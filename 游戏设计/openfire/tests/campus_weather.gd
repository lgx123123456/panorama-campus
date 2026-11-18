extends Node3D

const Weather = preload("res://scripts/campus/campus_night_weather.gd")
var failed := false

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var ground := _box(Vector3(0,-0.5,0), Vector3(100,1,100))
	var roof := _box(Vector3(0,5,0), Vector3(12,0.4,12))
	add_child(ground)
	add_child(roof)
	var level := Node3D.new()
	add_child(level)
	var walker := Node3D.new()
	add_child(walker)
	var weather := Weather.new()
	weather.walker = walker
	level.add_child(weather)
	for frame in 40:
		await get_tree().physics_frame
	_check(weather.seconds_remaining >= 59.0 and weather.seconds_remaining <= 180.0, "initial randomized dry interval")
	_check(absf(weather.surface_height_at(Vector2.ZERO) - 5.26) < 0.02, "rain ceiling stops above roof")
	_check(absf(weather.surface_height_at(Vector2(20,20)) - 0.06) < 0.02, "outdoor rain reaches ground")
	_check(weather.shelter_amount > 0.8, "indoors is sheltered")
	_check(weather._next_column == 0, "dry weather skips rain column sampling")
	weather.begin_rain(12.0)
	weather._process(4.1)
	_check(weather.is_raining and is_equal_approx(weather.rain_intensity,1.0), "forced rain fades in")
	_check(weather.seconds_remaining > 7.0 and weather.seconds_remaining < 8.0, "rain countdown")
	await get_tree().physics_frame
	await get_tree().physics_frame
	_check(weather._next_column != 0, "roof sampling advances in bounded batches")
	walker.position = Vector3(20,0,20)
	for frame in 45:
		await get_tree().physics_frame
	_check(weather.shelter_amount < 0.1, "outside clears shelter state")
	weather.end_rain()
	weather._process(4.1)
	_check(not weather.is_raining and is_zero_approx(weather.rain_intensity), "rain fades out")
	_check(weather.seconds_remaining >= 55.0 and weather.seconds_remaining <= 180.0, "next dry interval randomized")
	weather.seconds_remaining = 0.01
	weather._process(0.02)
	_check(weather.is_raining and weather.seconds_remaining >= 20.0 and weather.seconds_remaining <= 45.0, "timer starts a short randomized shower")
	weather._process(46.0)
	_check(not weather.is_raining, "short shower ends automatically")
	print("CAMPUS_WEATHER ", "FAIL" if failed else "PASS")
	get_tree().quit(1 if failed else 0)

func _box(position_value: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = position_value
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	return body

func _check(condition: bool, label: String) -> void:
	if not condition:
		failed = true
		push_error("WEATHER FAIL " + label)
