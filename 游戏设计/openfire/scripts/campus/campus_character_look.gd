extends Node3D

const ASSET_DIR := "res://assets/campus/characters/realistic/"
const ASSETS := ["white", "blue", "tall", "strong", "guide"]
const NAMES := ["普通同学·白校服", "普通同学·蓝校服", "林晨", "周航", "AI同学"]
const HEIGHTS := [1.70, 1.73, 1.86, 1.82, 1.75]
const WALK := &"walk"
const RUN := &"sprint"
const IDLE := &"idle"
const HUMAN_CLIPS := {
	IDLE: &"Idle", WALK: &"Walk", RUN: &"Run", &"duck": &"Duck",
	&"pick-up": &"Duck", &"interact-right": &"Wave",
	&"attack-melee-right": &"Punch", &"emote-yes": &"Wave", &"emote-no": &"HitReact",
}
const INFECTED_CLIPS := {
	IDLE: &"Idle", WALK: &"Shamble", RUN: &"Chase", &"interact-right": &"Knock",
	&"attack-melee-right": &"Bite", &"emote-yes": &"Command", &"emote-no": &"Stagger",
}

var model: Node3D
var skeleton: Skeleton3D
var animation: AnimationPlayer
var identity := 0
var infected := false
var gesture := &""
var model_path := ""
var crouched := false
var _crowd_viewer: Node3D
var _crowd_visibility: VisibleOnScreenNotifier3D
var _pose_elapsed := 0.0
var _pose_wait := 0.0
var prepared_model: PackedScene
var shared_infected_library: AnimationLibrary

func _ready() -> void:
	set_appearance(identity, infected)
	set_process(_crowd_viewer != null)

func configure_crowd_animation(viewer: Node3D) -> void:
	_crowd_viewer = viewer
	if DisplayServer.get_name() != "headless":
		_crowd_visibility = VisibleOnScreenNotifier3D.new()
		_crowd_visibility.aabb = AABB(Vector3(-0.8, -0.2, -0.8), Vector3(1.6, 2.6, 1.6))
		add_child(_crowd_visibility)
	_pose_wait = float(get_instance_id() % 11) / 120.0
	animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	animation.advance(0.0)
	set_process(true)

func _process(delta: float) -> void:
	var distance := global_position.distance_squared_to(_crowd_viewer.global_position)
	var interval := 0.0
	if distance > 4.0 * 4.0:
		var visible := _crowd_visibility == null or _crowd_visibility.is_on_screen()
		if not visible and gesture == &"":
			_pose_elapsed = 0.0
			_pose_wait = 0.0
			return
		interval = 1.0 / 8.0
		if distance <= 12.0 * 12.0:
			interval = 1.0 / 30.0
		elif distance <= 23.0 * 23.0:
			interval = 1.0 / 15.0
	_pose_elapsed += delta
	_pose_wait -= delta
	if _pose_wait <= 0.0 or interval == 0.0:
		animation.advance(_pose_elapsed)
		_pose_elapsed = 0.0
		_pose_wait = interval

func _load_model(path: String) -> void:
	if is_instance_valid(model):
		remove_child(model)
		model.queue_free()
	model_path = path
	var packed := prepared_model if prepared_model != null else load(path) as PackedScene
	prepared_model = null
	model = packed.instantiate()
	add_child(model)
	skeleton = model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	animation = model.find_children("*", "AnimationPlayer", true, false)[0]
	if _crowd_viewer != null:
		animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := shared_infected_library if infected else null
	shared_infected_library = null
	if library == null:
		library = AnimationLibrary.new()
		var clips := INFECTED_CLIPS if infected else HUMAN_CLIPS
		for clip: StringName in clips:
			var motion := animation.get_animation(clips[clip]).duplicate() as Animation
			motion.loop_mode = Animation.LOOP_LINEAR if clip in [IDLE, WALK, RUN] else Animation.LOOP_NONE
			library.add_animation(clip, motion)
	animation.add_animation_library(&"campus", library)
	if not infected:
		library.add_animation(&"crouch-walk", _make_crouch_walk())
	animation.animation_finished.connect(_finish_gesture)

func _make_crouch_walk() -> Animation:
	var walk := animation.get_animation(&"Walk")
	var duck := animation.get_animation(&"Duck")
	var motion := walk.duplicate() as Animation
	motion.loop_mode = Animation.LOOP_LINEAR
	# Keep the authored crouch posture and add the walk cycle's joint deltas.
	for track in motion.get_track_count():
		var type := motion.track_get_type(track)
		var source := duck.find_track(motion.track_get_path(track), type)
		if source < 0:
			continue
		for key in motion.track_get_key_count(track):
			if type == Animation.TYPE_ROTATION_3D:
				var base := walk.rotation_track_interpolate(track, 0.0)
				var pose := duck.rotation_track_interpolate(source, duck.length * 0.5)
				var step: Quaternion = walk.track_get_key_value(track, key)
				motion.track_set_key_value(track, key, (pose * base.inverse() * step).normalized())
			elif type == Animation.TYPE_POSITION_3D:
				var base := walk.position_track_interpolate(track, 0.0)
				var pose := duck.position_track_interpolate(source, duck.length * 0.5)
				var step: Vector3 = walk.track_get_key_value(track, key)
				motion.track_set_key_value(track, key, pose + (step - base) * 0.55)
	return motion

func set_appearance(index: int, is_infected: bool) -> void:
	identity = index
	infected = is_infected
	var path := appearance_path(index, infected)
	cancel_gesture()
	if path != model_path:
		_load_model(path)
	model.rotation.y = PI
	crouched = false
	locomotion(0.0)

static func appearance_path(index: int, is_infected: bool) -> String:
	return "%s%s%s.glb" % [ASSET_DIR, ASSETS[index], "_infected" if is_infected else ""]

func set_crouched(enabled: bool) -> void:
	crouched = enabled and not infected

func locomotion(speed: float, running := false) -> void:
	if gesture != &"":
		return
	if crouched:
		if speed >= 0.15:
			_play(&"crouch-walk", clampf(speed / 1.8, 0.35, 1.3))
			return
		var duck := &"campus/duck"
		if animation.current_animation != duck:
			_play(&"duck", 1.0)
			animation.seek(animation.get_animation(duck).length * 0.5, true)
			animation.speed_scale = 0.0
		return
	var clip := IDLE if speed < 0.15 else (RUN if running else WALK)
	var rate := 1.0 if clip == IDLE else clampf(speed / (4.7 if running else 3.2), 0.40, 1.45)
	_play(clip, rate)

func perform(clip: StringName, rate := 1.0) -> void:
	gesture = clip
	_play(clip, rate, true)

func cancel_gesture() -> void:
	gesture = &""

func _play(clip: StringName, rate: float, restart := false) -> void:
	var path := StringName("campus/" + String(clip))
	if restart:
		animation.stop(true)
	if animation.current_animation != path:
		animation.play(path, 0.1)
	animation.speed_scale = rate

func _finish_gesture(_clip: StringName) -> void:
	cancel_gesture()
