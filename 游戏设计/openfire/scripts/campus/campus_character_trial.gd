extends Node3D

const Look = preload("res://scripts/campus/campus_character_look.gd")
const Actor = preload("res://scripts/campus/campus_character_actor.gd")
const Walker = preload("res://scripts/campus/campus_character_walker.gd")
const LINE_Z := -15.8
const MOVE_DISTANCE := 3.4
const BOOK_START := Vector3(4.9, 0.84, -9.1)
const DOOR_CENTER := Vector3(-4.9, 0.06, -9.1)

var humans: Array[Actor] = []
var infected: Array[Actor] = []
var selection := 0
var form := Walker.HUMAN
var special_role := 2
var holding_book := false
var book: RigidBody3D
var door_index: int

var panel: PanelContainer
var selected_role: OptionButton
var selected_form: OptionButton
var action_rows: VBoxContainer
var status: Label
var controls: Label
var round_label: Label
var feedback: Label
var inspect_camera: Camera3D
var inspect_button: Button
var previous_camera: Camera3D

@onready var walker: Walker = $"../Walker"
@onready var doors: Node = $"../Doors"
@onready var interface: CanvasLayer = $"../Interface"

func _ready() -> void:
	for index in Look.NAMES.size():
		humans.append(_spawn_actor(index, false, -5.9 + index * 1.23))
		infected.append(_spawn_actor(index, true, 0.98 + index * 1.23))
	_create_practice_door()
	_create_book()
	inspect_camera = Camera3D.new()
	inspect_camera.fov = 43.0
	add_child(inspect_camera)
	_build_interface()
	_start_round()
	print("Campus character trial ready: ", humans.size(), " humans, ", infected.size(), " infected")

func _process(_delta: float) -> void:
	if inspect_camera.current:
		if walker.mouse_captured:
			_end_inspection()
		else:
			_aim_inspection_camera()
	panel.visible = not walker.mouse_captured
	feedback.visible = walker.mouse_captured and not feedback.text.is_empty()
	controls.text = (
		"%s · %s\nWASD 移动  Shift 加速  Space 跳跃\nCtrl 蹲伏  C 静步  E 拾书／开关门\nQ 扔书  G 能力  V 视角\nTab 测试面板  R 回起点  Esc 返回" %
		[_role_name(walker.identity, walker.role), "静步" if walker.quiet else "行走"]
	) if walker.mouse_captured else "Tab 捕获鼠标 · WASD 移动"

func _physics_process(_delta: float) -> void:
	if holding_book:
		book.global_transform = walker.hand_attachment.global_transform

func _spawn_actor(index: int, is_infected: bool, x: float) -> Actor:
	var actor := Actor.new()
	actor.position = Vector3(x, 0.15, LINE_Z)
	actor.rotation.y = PI
	add_child(actor)
	actor.look.set_appearance(index, is_infected)
	var caption := Label3D.new()
	caption.position.y = float(Look.HEIGHTS[index]) + 0.20
	caption.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	caption.font_size = 38
	caption.pixel_size = 0.0043
	caption.modulate = Color("#f0cf9c") if is_infected else Color("#e1f5ff")
	var short_name: String = ["白校服", "蓝校服", Look.NAMES[2], Look.NAMES[3], "AI同学"][index]
	caption.text = short_name + ("感染" if is_infected else "")
	actor.add_child(caption)
	return actor

func _build_interface() -> void:
	var roamer: PanelContainer = interface.get_node("DebugControls")
	roamer.hide()
	panel = PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	panel.offset_left = -348
	panel.offset_right = -20
	panel.offset_top = 20
	panel.add_theme_stylebox_override("panel", roamer.get_theme_stylebox("panel"))
	interface.add_child(panel)
	var rows := VBoxContainer.new()
	rows.add_theme_constant_override("separation", 8)
	panel.add_child(rows)
	var title := Label.new()
	title.text = "校园人物测试"
	title.add_theme_font_size_override("font_size", 22)
	rows.add_child(title)
	selected_role = OptionButton.new()
	for character_name: String in Look.NAMES:
		selected_role.add_item(character_name)
	selected_role.item_selected.connect(func(index: int):
		selection = index
		_update_actions()
	)
	rows.add_child(selected_role)
	selected_form = OptionButton.new()
	for label in ["人类", "普通丧尸", "僵尸王"]:
		selected_form.add_item(label)
	selected_form.item_selected.connect(func(index: int):
		form = index
		_update_actions()
	)
	rows.add_child(selected_form)
	_add_button(rows, "切换为所选角色", _take_control)
	inspect_button = Button.new()
	inspect_button.text = "近看所选角色"
	inspect_button.pressed.connect(_toggle_inspection)
	rows.add_child(inspect_button)
	round_label = Label.new()
	rows.add_child(round_label)
	_add_button(rows, "重抽并操控特殊角色", _start_round)
	rows.add_child(HSeparator.new())
	action_rows = VBoxContainer.new()
	rows.add_child(action_rows)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.custom_minimum_size.x = 275
	rows.add_child(status)
	_add_button(rows, "人物、起点和道具复位", _reset_trial)

	var hud := PanelContainer.new()
	hud.position = Vector2(20, 20)
	hud.add_theme_stylebox_override("panel", roamer.get_theme_stylebox("panel"))
	interface.add_child(hud)
	var hud_rows := VBoxContainer.new()
	hud.add_child(hud_rows)
	controls = Label.new()
	hud_rows.add_child(controls)
	feedback = Label.new()
	feedback.add_theme_color_override("font_color", Color("#f0cf9c"))
	hud_rows.add_child(feedback)
	var hint := doors.hint as Label
	hint.reparent(hud_rows, false)
	_update_actions()

func _add_button(rows: VBoxContainer, label: String, action: Callable) -> void:
	var button := Button.new()
	button.text = label
	button.pressed.connect(action)
	rows.add_child(button)

func _update_actions() -> void:
	for child in action_rows.get_children():
		action_rows.remove_child(child)
		child.queue_free()
	var actions: Dictionary
	match form:
		Walker.HUMAN:
			actions = {&"walk": "走到测试点", &"run": "跑到测试点", &"stop": "中止动作"}
			if selection == 4:
				actions[&"guide"] = "AI 带路并提示"
			elif selection == 3:
				actions[&"stun"] = Look.NAMES[3] + " · 打晕测试丧尸"
			else:
				actions[&"pickup"] = "拾取动作"
		Walker.INFECTED:
			actions = {&"walk": "游荡", &"run": "追击测试点", &"knock": "拍门动作",
				&"bite": "咬击动作", &"dazed": "眩晕并恢复", &"home": "散去并返回", &"stop": "中止动作"}
		_:
			actions = {&"signal": "指挥两只丧尸", &"bite": "咬击动作", &"stop": "中止动作"}
	for command: StringName in actions:
		_add_button(action_rows, "演示 · " + actions[command], perform_demo.bind(command))

func _role_name(index: int, role: int) -> String:
	var role_label: String = Look.NAMES[index]
	match role:
		Walker.INFECTED:
			return "普通丧尸（%s）" % role_label
		Walker.KING:
			return "僵尸王（%s）" % role_label
	return role_label

func _start_round() -> void:
	special_role = [2, 3].pick_random()
	round_label.text = "单人试局抽中 · %s" % Look.NAMES[special_role]
	selected_role.select(special_role)
	selected_form.select(Walker.HUMAN)
	selection = special_role
	form = Walker.HUMAN
	_take_control()
	_update_actions()

func _take_control() -> void:
	_return_book()
	walker.set_role(selection, form)
	_report("操控%s。按 Tab 进入移动测试。" % _role_name(selection, form))

func _toggle_inspection() -> void:
	if inspect_camera.current:
		_end_inspection()
	else:
		previous_camera = get_viewport().get_camera_3d()
		_aim_inspection_camera()
		inspect_camera.make_current()
		inspect_button.text = "回到人物总览"

func _end_inspection() -> void:
	if is_instance_valid(previous_camera):
		previous_camera.make_current()
	else:
		walker.camera.make_current()
	inspect_button.text = "近看所选角色"

func _aim_inspection_camera() -> void:
	var actor := humans[selection] if form == Walker.HUMAN else infected[selection]
	var height: float = Look.HEIGHTS[selection]
	var target := actor.global_position + Vector3.UP * (height * 0.51)
	inspect_camera.global_position = target - actor.global_basis.z * 3.0 + Vector3.UP * 0.30
	inspect_camera.look_at(target)

func perform_demo(command: StringName) -> void:
	var actor := humans[selection] if form == Walker.HUMAN else infected[selection]
	if actor.stun_remaining > 0.0 and command not in [&"stop", &"dazed"]:
		_report("角色正在眩晕。")
		return
	match command:
		&"walk":
			_move_actor(actor, 1.35 if form != Walker.HUMAN else 3.2)
			_report("前往指定点。")
		&"run":
			var speed := 2.8 if form != Walker.HUMAN else (6.35 if selection == 2 else 5.0)
			_move_actor(actor, speed, true)
			_report("移动速度 %.2f 米/秒。" % speed)
		&"guide":
			_move_actor(actor, 2.5)
			_report("AI同学说：跟我走，到前面等大家。")
		&"home":
			actor.go_to(to_global(actor.home), 1.25)
			_report("丧尸散去，返回原位。")
		&"pickup":
			_gesture(actor, &"pick-up")
			_report("拾取动作。实物书本在右侧台上，靠近后按 E。")
		&"knock":
			_gesture(actor, &"interact-right", 0.8)
			_report("拍门动作。")
		&"bite":
			_gesture(actor, &"attack-melee-right", 0.65)
			_report("咬击动作。")
		&"dazed":
			actor.stun(2.0)
			_report("眩晕 2 秒后恢复。")
		&"stun":
			_gesture(actor, &"attack-melee-right")
			infected[selection].stun(2.0)
			_report("对应的感染测试目标眩晕 2 秒。")
		&"signal":
			_gesture(actor, &"emote-yes", 0.8)
			_send_infected(actor.global_position, actor)
		&"stop":
			actor.halt()
			actor.stun_remaining = 0.0
			_report("动作已中止。")

func _move_actor(actor: Actor, speed: float, run := false) -> void:
	var destination := to_global(actor.home + Vector3.FORWARD * MOVE_DISTANCE)
	if actor.global_position.distance_to(destination) < 0.2:
		destination = to_global(actor.home)
	actor.go_to(destination, speed, run)

func _gesture(actor: Actor, clip: StringName, rate := 1.0) -> void:
	actor.halt()
	actor.look.perform(clip, rate)

func use_ability() -> void:
	if walker.role == Walker.KING:
		walker.look.perform(&"emote-yes", 0.8)
		walker.play_hand_action(&"interact-right")
		_send_infected(walker.global_position)
	elif walker.role == Walker.INFECTED:
		walker.look.perform(&"attack-melee-right", 0.65)
		var target := _target(humans)
		if target:
			walker.play_hand_action(&"hit")
			target.bite_count += 1
			target.stun(0.6)
			_report("测试目标受到咬击 %d 次。" % target.bite_count)
		else:
			_report("靠近并面向目标后按 G。")
	elif walker.identity == 3:
		walker.look.perform(&"attack-melee-right")
		var target := _target(infected)
		if target:
			walker.play_hand_action(&"hit")
			target.stun(2.0)
			_report("测试丧尸眩晕 2 秒。")
		else:
			_report("靠近并面向丧尸后按 G。")
	elif walker.identity == 4:
		walker.look.perform(&"emote-yes")
		walker.play_hand_action(&"interact-right")
		_report("AI同学说：到前面的空地会合。")
	elif walker.identity == 2:
		_report("按住 Shift 移动，让%s冲刺。" % Look.NAMES[2])

func _target(group: Array[Actor]) -> Actor:
	var closest: Actor
	var distance := 2.1
	for actor in group:
		if not actor.look.infected and actor.look.identity == 4:
			continue
		var offset := actor.global_position - walker.global_position
		var target_distance := offset.length()
		if target_distance >= distance or (-walker.global_basis.z).dot(offset.normalized()) < 0.67:
			continue
		var query := PhysicsRayQueryParameters3D.create(
			walker.global_position + Vector3.UP, actor.global_position + Vector3.UP, 1)
		if get_world_3d().direct_space_state.intersect_ray(query).is_empty():
			distance = target_distance
			closest = actor
	return closest

func _send_infected(origin: Vector3, caster: Actor = null) -> void:
	var candidates := infected.filter(func(actor: Actor):
		return actor != caster and actor.stun_remaining == 0 and actor.global_position.distance_to(origin) <= 12.0
	)
	candidates.sort_custom(func(a: Actor, b: Actor):
		return a.global_position.distance_squared_to(origin) < b.global_position.distance_squared_to(origin)
	)
	var count := mini(candidates.size(), 2)
	for index in count:
		_move_actor(candidates[index], 2.2)
	_report("指挥 %d 只丧尸前往测试点。" % count if count > 0 else "附近没有可指挥的丧尸。")

func _create_practice_door() -> void:
	var pivot := Node3D.new()
	pivot.position = DOOR_CENTER + Vector3.LEFT * 0.53
	add_child(pivot)
	var door := StaticBody3D.new()
	door.position = Vector3(0.53, 1.0, 0.0)
	pivot.add_child(door)
	_add_box(door, Vector3(1.06, 2.0, 0.09), Color("#487079"))
	for side in [-1, 1]:
		var jamb := StaticBody3D.new()
		jamb.position = DOOR_CENTER + Vector3(0.60 * side, 1.04, 0.0)
		add_child(jamb)
		_add_box(jamb, Vector3(0.12, 2.08, 0.20), Color("#b8c0bb"))
	var lintel := StaticBody3D.new()
	lintel.position = DOOR_CENTER + Vector3.UP * 2.08
	add_child(lintel)
	_add_box(lintel, Vector3(1.32, 0.12, 0.20), Color("#b8c0bb"))
	door_index = doors.doors.size()
	doors.doors.append({"id": "practice", "label": "测试", "center": to_global(DOOR_CENTER),
		"width": 1.06, "height": 2.0, "open": false, "locked": false, "moving": false,
		"pivots": [{"node": pivot, "open_angle": -PI / 2.0, "closed_angle": 0.0}]})

func _create_book() -> void:
	var pedestal := StaticBody3D.new()
	pedestal.position = BOOK_START - Vector3.UP * 0.40
	add_child(pedestal)
	_add_box(pedestal, Vector3(0.6, 0.76, 0.52), Color("#667581"))
	book = RigidBody3D.new()
	book.position = BOOK_START
	book.collision_layer = 0
	book.mass = 0.35
	book.freeze = true
	add_child(book)
	_add_box(book, Vector3(0.20, 0.045, 0.28), Color("#bd7843"))

func _add_box(body: PhysicsBody3D, size: Vector3, color: Color) -> void:
	var shape := BoxShape3D.new()
	shape.size = size
	var collider := CollisionShape3D.new()
	collider.shape = shape
	body.add_child(collider)
	var mesh := BoxMesh.new()
	mesh.size = size
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	var visible_mesh := MeshInstance3D.new()
	visible_mesh.mesh = mesh
	visible_mesh.material_override = material
	body.add_child(visible_mesh)

func interact_book() -> bool:
	var offset := book.global_position - walker.camera.global_position
	if holding_book or offset.length() > 2.15 or -walker.camera.global_basis.z.dot(offset.normalized()) < 0.30:
		return false
	var sight := PhysicsRayQueryParameters3D.create(walker.camera.global_position, book.global_position, 1)
	if not get_world_3d().direct_space_state.intersect_ray(sight).is_empty():
		return false
	book.freeze = true
	book.linear_velocity = Vector3.ZERO
	book.angular_velocity = Vector3.ZERO
	holding_book = true
	walker.look.perform(&"pick-up")
	walker.hands.set_holding(true)
	walker.play_hand_action(&"pick-up")
	_report("已拾取书本。按 Q 投出。")
	return true

func throw_book() -> void:
	if not holding_book:
		return
	holding_book = false
	walker.hands.set_holding(false)
	book.global_position = walker.camera.global_position
	book.freeze = false
	book.sleeping = false
	book.linear_velocity = -walker.camera.global_basis.z * 7.0 + Vector3.UP * 2.0
	book.angular_velocity = walker.global_basis.x * 10.0
	walker.look.perform(&"interact-right", 1.3)
	walker.play_hand_action(&"throw")
	_report("书本已投出。")

func _return_book() -> void:
	holding_book = false
	walker.hands.set_holding(false)
	book.freeze = true
	book.linear_velocity = Vector3.ZERO
	book.angular_velocity = Vector3.ZERO
	book.transform = Transform3D(Basis.IDENTITY, BOOK_START)

func _reset_trial() -> void:
	for actor in humans + infected:
		actor.reset_actor()
	_return_book()
	walker._reset_position()
	var record: Dictionary = doors.doors[door_index]
	if record.moving:
		record.tween.finished.connect(func(): doors.set_open(door_index, false), CONNECT_ONE_SHOT)
	else:
		doors.set_open(door_index, false)
	_report("已复位。")

func _report(message: String) -> void:
	status.text = message
	feedback.text = message
