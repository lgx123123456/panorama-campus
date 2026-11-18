extends Node

var failed := false
const OUT := "C:/CampusReconstructionRuntime/角色手臂/实机"

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	print("ARMS start")
	var tree := get_tree()
	reparent(tree.root)
	var full := "--full-campus" in OS.get_cmdline_user_args()
	tree.change_scene_to_file("res://scenes/campus/survival.tscn" if full else "res://scenes/campus/zombie_trial.tscn")
	await tree.scene_changed
	print("ARMS scene loaded")
	var level: Node3D = tree.current_scene.get_node("CharacterTrial")
	var walker: CharacterBody3D = level.walker
	var guns: Node3D = level.firearms
	if full:
		guns.grant_supply("rifle", 24, true)
	level.spawner.set_physics_process(false)
	level.set_physics_process(false)
	await _wait(30)
	var capture := "--capture" in OS.get_cmdline_user_args()
	DirAccess.make_dir_recursive_absolute(OUT)
	for identity in 5:
		walker.set_role(identity, walker.HUMAN)
		level._update_hud()
		guns.switch_weapon(guns.loadout.find("rifle"))
		await _wait(8)
		_check(guns.arm_identity == identity and walker.hands.identity == identity, "identity %d applies to armed and empty hands" % identity)
		_check(not guns.rig.find_child("fps_arms_extended", true, false).visible, "original bare arms hidden")
		for mesh: MeshInstance3D in guns.uniform_arms.get_children():
			_check(mesh.get_node(mesh.skeleton) == guns.view_skeleton, "mesh binds to animated gun skeleton")
			for bind in mesh.skin.get_bind_count():
				_check(guns.view_skeleton.find_bone(mesh.skin.get_bind_name(bind)) >= 0, "skin bind resolves")
		var meshes: Array[Node] = walker.hands.model.find_children("*", "MeshInstance3D", true, false)
		_check(meshes.size() >= 7, "character has separate skin sleeves and nails")
		if capture:
			await _capture("%d-rifle" % identity)
		guns.ammo.rifle.mag = 10
		guns.ammo.rifle.reserve = 30
		_check(guns.reload_weapon(), "new sleeves preserve original reload")
		await _wait(40)
		if capture:
			await _capture("%d-reload" % identity)
		guns.holstered = true
		await _wait(3)
		_check(walker.hands.visible and not guns.rig.visible, "holster displays corresponding empty arms")
		if capture:
			await _capture("%d-empty" % identity)
		var book: RigidBody3D = level.props[&"book"]
		book.freeze = true
		book.global_position = walker.camera.global_position - walker.camera.global_basis.z * 0.65
		_check(level.interact_book() and level.held == &"book", "normal pickup selects actual book")
		await _wait(18)
		level._follow_held_prop()
		_check(book.global_position.distance_to(walker.hand_attachment.global_position) < .001, "actual book follows posed hand attachment")
		if capture:
			await _capture("%d-pickup" % identity)
		level.throw_book()
		_check(level.held == &"" and not book.freeze and book.linear_velocity.length() > 1.0, "actual throw releases book with velocity")
		await _wait(16)
		if capture:
			await _capture("%d-throw" % identity)
		await _wait(40)
		walker.set_role(identity, walker.INFECTED)
		await _wait(3)
		_check(walker.hands.infected and not guns.is_available(), "infection retains character sleeve and melee")
		walker.play_hand_action(&"grab")
		await _wait(20)
		if capture:
			await _capture("%d-infected" % identity)
		await _wait(25)
	print("CAMPUS ARMS ", "FAIL" if failed else "PASS")
	await _wait(8)
	tree.current_scene.queue_free()
	await tree.process_frame
	tree.quit(1 if failed else 0)

func _capture(label: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(OUT.path_join(label + ".png"))

func _check(ok: bool, label: String) -> void:
	if not ok:
		print("ARMS FAIL ", label)
	failed = failed or not ok

func _wait(frames: int) -> void:
	for frame in frames:
		await get_tree().physics_frame
