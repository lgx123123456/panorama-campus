extends Node
## Original offline-synthesised instrumental D-minor score and layered rain.
## Players belong to this scene. This node never starts/stops global Music.

const MUSIC_PATH := "res://assets/audio/campus_night_music.wav"
const RAIN_PATH := "res://assets/audio/campus_rain.wav"
const MUSIC_DB := -18.0
const RAIN_DB := -20.0
const SHELTER_GAIN := 0.20
const ROOF_SAMPLE_SECONDS := 0.35

var weather: Node
var walker: Node3D
var shelter := 0.0
var rain_gain := 0.0
var daylight := false

var _music: AudioStreamPlayer
var _rain: AudioStreamPlayer
var _shelter_target := 0.0
var _roof_timer := 0.0
var _fade := 0.0


func _ready() -> void:
	var music_bus := &"Music" if AudioServer.get_bus_index(&"Music") >= 0 else &"Master"
	_music = _make_player(MUSIC_PATH, music_bus)
	_rain = _make_player(RAIN_PATH, &"Master")
	if _music.stream != null:
		_music.play()
	if _rain.stream != null:
		_rain.play()


func _make_player(path: String, bus: StringName) -> AudioStreamPlayer:
	var player := AudioStreamPlayer.new()
	player.bus = bus
	player.volume_linear = 0.0
	if ResourceLoader.exists(path):
		var source := load(path) as AudioStreamWAV
		if source != null:
			# Private resource copy keeps loop settings local to the night scene.
			var stream := source.duplicate() as AudioStreamWAV
			stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
			stream.loop_begin = 0
			stream.loop_end = roundi(stream.get_length() * stream.mix_rate)
			player.stream = stream
	add_child(player)
	return player


func begin_daylight() -> void:
	daylight = true
	rain_gain = 0.0
	_music.volume_linear = 0.0
	_rain.volume_linear = 0.0
	_music.stop()
	_rain.stop()


func _physics_process(delta: float) -> void:
	if daylight:
		return
	if not is_instance_valid(walker):
		_music.stop()
		_rain.stop()
		set_physics_process(false)
		return
	_roof_timer -= delta
	if _roof_timer <= 0.0:
		_roof_timer = ROOF_SAMPLE_SECONDS
		_sample_roof()
	var smoothing := 1.0 - exp(-delta * 1.7)
	shelter = lerpf(shelter, _shelter_target, smoothing)
	_fade = minf(1.0, _fade + delta / 4.0)
	var intensity := 0.0
	if is_instance_valid(weather):
		intensity = clampf(float(weather.get("rain_intensity")), 0.0, 1.0)
	var target_gain := pow(intensity, 0.7) * lerpf(1.0, SHELTER_GAIN, shelter)
	rain_gain = lerpf(rain_gain, target_gain, smoothing)
	_music.volume_linear = db_to_linear(MUSIC_DB) * _fade
	_rain.volume_linear = db_to_linear(RAIN_DB) * rain_gain * _fade


func _sample_roof() -> void:
	var camera := get_viewport().get_camera_3d()
	if camera == null:
		return
	var origin := camera.global_position + Vector3.UP * 0.12
	var excluded: Array[RID] = []
	if walker is CollisionObject3D:
		excluded.append((walker as CollisionObject3D).get_rid())
	var blocked := 0
	var space := walker.get_world_3d().direct_space_state
	for offset: Vector3 in [Vector3.ZERO, Vector3(0.4, 0, 0), Vector3(-0.4, 0, 0),
			Vector3(0, 0, 0.4), Vector3(0, 0, -0.4)]:
		var start := origin + offset
		var query := PhysicsRayQueryParameters3D.create(start, start + Vector3.UP * 24.0, 1, excluded)
		query.hit_from_inside = true
		query.hit_back_faces = true
		if not space.intersect_ray(query).is_empty():
			blocked += 1
	_shelter_target = float(blocked) / 5.0


func _exit_tree() -> void:
	if is_instance_valid(_music):
		_music.stop()
	if is_instance_valid(_rain):
		_rain.stop()
