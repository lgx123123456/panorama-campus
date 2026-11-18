extends Node3D
## Campus adapter for bukkbeek's MIT FPS arms, meshes and authored animations.
## Ballistics and weapon balance share OpenFire's WeaponDB.

const ARMS := preload("res://assets/campus/weapons/fps_demo_arms.glb")
const ArmAppearance = preload("res://scripts/campus/campus_arm_appearance.gd")
const Hitboxes = preload("res://scripts/campus/campus_hitboxes.gd")
const IMPACT := preload("res://scenes/fx/impact.tscn")
const MINIGUN := preload("res://assets/campus/weapons/minigun.tscn")
const IDS := ["rifle", "shotgun", "pistol"]
const CAMPAIGN_IDS := ["pistol", "rifle", "smg", "shotgun", "minigun"]
const MINIGUN_STATS := {
	"id": "minigun",
	"sfx": "res://assets/audio/fire_smg.ogg",
	"damage": 18.0,
	"fire_rate": 18.0,
	"automatic": true,
	"mag_size": 240,
	"reserve": 0,
	"reload_time": 2.4,
	"spread_deg": 3.4,
	"aim_spread_deg": 1.5,
	"range": 72.0,
	"pellets": 1,
	"zoom_fov": 64.0,
}
const PROFILES := {
	"rifle": {"mesh": "assualt", "label": "步枪", "hip": Vector3(0.22, -0.10, -0.14), "ads": Vector3(0, -0.008, -0.08)},
	"shotgun": {"mesh": "shotgun", "label": "霰弹枪", "hip": Vector3(0.20, -0.12, -0.12), "ads": Vector3(0, 0.008, -0.08)},
	"pistol": {"mesh": "pistol", "label": "手枪", "hip": Vector3(0.16, -0.07, -0.18), "ads": Vector3(0, -0.025, -0.12)},
	"smg": {"mesh": "smg", "label": "冲锋枪", "hip": Vector3(0.22, -0.10, -0.14), "ads": Vector3(0, 0.007, -0.08)},
	"sniper": {"mesh": "sniper", "label": "狙击枪", "hip": Vector3(0.23, -0.115, -0.18), "ads": Vector3(0, -0.006, -0.12)},
	"minigun": {"mesh": "Minigun", "animation": "smg", "label": "加特林", "hip": Vector3(0.25, -0.16, -0.19), "ads": Vector3(0.06, -0.08, -0.12)},
}
const VIEW_LAYER := 1 << 19
const STANDARD_BODY_DAMAGE := 50.0
const CAMPUS_HITSCAN_RANGE := 10000.0
const UNARMED_SPEED_SCALE := 1.15
const WEAPON_SPEED_SCALES := {
	"pistol": 1.0, "rifle": 0.85, "smg": 0.90,
	"shotgun": 0.85, "sniper": 0.80, "minigun": 0.70,
}
const SHOTGUN_FALLOFF_START := 6.0
const SHOTGUN_FALLOFF_END := 30.0
const SHOTGUN_MIN_DAMAGE_SCALE := 0.25

signal shot_fired(at: Vector3)
signal target_hit(killed: bool)

var walker: CharacterBody3D
var level: Node3D
var rig: Node3D
var animation: AnimationPlayer
var muzzle: OmniLight3D
var view_fill: OmniLight3D
var ammo: Dictionary = {}
var owned: Dictionary = {}
var weapon_stats: Dictionary = {}
var loadout: Array[String] = []
var loadout_hint := ""
var current_index := 0
var holstered := false
var aiming := false
var cooldown := 0.0
var reload_left := 0.0
var interaction_left := 0.0
var flash_left := 0.0
var recoil := 0.0
var phase := 0.0
var base_fov := 75.0
var ammo_label: Label
var hit_marker: Label
var hit_left := 0.0
var damage_feedback_left := 0.0
var damage_feedback := ""
var third_person_model: Node3D
var third_person_magazine: Node3D
var magazine_position := Vector3.ZERO
var world_muzzle: OmniLight3D
var weapon_anchor: Node3D
var arm_skeleton: Skeleton3D
var arm_ik: TwoBoneIK3D
var hand_targets: Array[Node3D] = []
var elbow_targets: Array[Node3D] = []
var trigger_blocked := false
var view_skeleton: Skeleton3D
var uniform_arms: Node3D
var arm_identity := -1
var minigun_barrels: Node3D
var world_minigun_barrels: Node3D
var minigun_spin_speed := 0.0

static func campus_weapon_stats(id: String) -> Dictionary:
	var source: Dictionary = MINIGUN_STATS if id == "minigun" else WeaponDB.get_weapon(id)
	var weapon := source.duplicate()
	if id != "shotgun":
		weapon.damage = STANDARD_BODY_DAMAGE
		weapon.range = CAMPUS_HITSCAN_RANGE
	return weapon

func setup(owner_walker: CharacterBody3D, owner_level: Node3D) -> void:
	walker = owner_walker
	level = owner_level
	base_fov = walker.camera.fov
	loadout.assign(CAMPAIGN_IDS if level.armed_campaign else IDS)
	var shortcuts := PackedStringArray()
	for index in loadout.size():
		var id := loadout[index]
		var weapon := campus_weapon_stats(id)
		weapon_stats[id] = weapon
		ammo[id] = {"mag": int(weapon.mag_size), "reserve": int(weapon.reserve)}
		owned[id] = true
		shortcuts.append("%d %s" % [index + 1, PROFILES[id].label])
	loadout_hint = "  ".join(shortcuts)
	rig = ARMS.instantiate()
	add_child(rig)
	animation = rig.find_children("*", "AnimationPlayer", true, false)[0]
	_configure_visuals(rig)
	if level.armed_campaign:
		_attach_minigun()
	view_skeleton = rig.find_children("*", "Skeleton3D", true, false)[0]
	_update_arm_appearance()
	muzzle = OmniLight3D.new()
	muzzle.position = Vector3(0.18, -0.12, -0.8)
	muzzle.light_color = Color(1.0, 0.72, 0.32)
	muzzle.light_energy = 2.5
	muzzle.omni_range = 2.0
	muzzle.hide()
	add_child(muzzle)
	view_fill = OmniLight3D.new()
	view_fill.position = Vector3(-0.25, 0.35, 0.1)
	view_fill.light_cull_mask = VIEW_LAYER
	view_fill.omni_range = 2.0
	view_fill.light_energy = 0.8
	add_child(view_fill)
	_build_hud()
	weapon_anchor = Node3D.new()
	walker.look.add_child(weapon_anchor)
	world_muzzle = OmniLight3D.new()
	world_muzzle.position = Vector3(0, 0, -0.65)
	world_muzzle.light_color = muzzle.light_color
	world_muzzle.light_energy = 3.0
	world_muzzle.omni_range = 2.0
	world_muzzle.hide()
	weapon_anchor.add_child(world_muzzle)
	for side in 2:
		var hand := Node3D.new()
		weapon_anchor.add_child(hand)
		hand_targets.append(hand)
		var elbow := Node3D.new()
		walker.look.add_child(elbow)
		elbow_targets.append(elbow)
	switch_weapon(0)
	if level.armed_campaign:
		owned.clear()
		for id in loadout:
			ammo[id] = {"mag": 0, "reserve": 0}
		holstered = true
		_refresh_shortcuts()
		refresh_visibility()
		_update_hud()

func grant_supply(id: String, rounds: int, is_weapon: bool) -> void:
	if not ammo.has(id):
		return
	if is_weapon and not owned.has(id):
		var magazine := mini(rounds, int(weapon_stats[id].mag_size))
		owned[id] = true
		ammo[id].mag = magazine
		rounds -= magazine
		_refresh_shortcuts()
		switch_weapon(loadout.find(id))
	ammo[id].reserve += rounds
	_update_hud()

func _refresh_shortcuts() -> void:
	var keys := PackedStringArray()
	for index in loadout.size():
		if owned.has(loadout[index]):
			keys.append("%d %s" % [index + 1, PROFILES[loadout[index]].label])
	loadout_hint = "  ".join(keys)

func _configure_visuals(node: Node) -> void:
	if node is MeshInstance3D:
		node.layers = VIEW_LAYER
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material := StandardMaterial3D.new()
		material.albedo_color = Color(0.10, 0.13, 0.16)
		material.metallic = 0.65
		material.roughness = 0.4
		if "arms" in String(node.name):
			node.hide()
			material.albedo_color = Color(0.63, 0.43, 0.32)
			material.metallic = 0.0
			material.roughness = 0.85
		node.material_override = material
	for child in node.get_children():
		_configure_visuals(child)

func _attach_minigun() -> void:
	# The open asset reuses the authored two-hand pose and recoil clips in the FPS rig.
	var smg := rig.find_child("smg", true, false) as Node3D
	var model := MINIGUN.instantiate() as Node3D
	model.transform = smg.transform
	model.hide()
	for geometry: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		geometry.layers = VIEW_LAYER
		geometry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	smg.get_parent().add_child(model)
	minigun_barrels = model.find_child("BarrelGroup", true, false) as Node3D

func _update_arm_appearance() -> void:
	if arm_identity == walker.identity:
		return
	arm_identity = walker.identity
	if is_instance_valid(uniform_arms):
		uniform_arms.get_parent().remove_child(uniform_arms)
		uniform_arms.queue_free()
	uniform_arms = ArmAppearance.attach(view_skeleton, arm_identity)

func _build_hud() -> void:
	ammo_label = Label.new()
	ammo_label.name = "WeaponAmmo"
	ammo_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	level.interface.add_child(ammo_label)
	ammo_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	ammo_label.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	ammo_label.grow_vertical = Control.GROW_DIRECTION_BEGIN
	ammo_label.offset_left = -310.0
	ammo_label.offset_top = -95.0
	ammo_label.offset_right = -25.0
	ammo_label.offset_bottom = -23.0
	ammo_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	ammo_label.add_theme_font_size_override("font_size", 23)
	ammo_label.add_theme_color_override("font_outline_color", Color(0.05, 0.06, 0.08))
	ammo_label.add_theme_constant_override("outline_size", 7)
	hit_marker = Label.new()
	hit_marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	level.interface.add_child(hit_marker)
	hit_marker.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	hit_marker.offset_left = -9.0
	hit_marker.offset_top = -19.0
	hit_marker.offset_right = 14.0
	hit_marker.offset_bottom = 19.0
	hit_marker.text = "×"
	hit_marker.add_theme_font_size_override("font_size", 30)
	hit_marker.hide()

func weapon_id() -> String:
	return loadout[current_index]

func is_available() -> bool:
	return walker.role == walker.HUMAN and not level.round_finished and not holstered \
		and (not level.armed_campaign or owned.has(weapon_id())) \
		and level.held == &"" and interaction_left <= 0.0 and walker.hands.action == &""

func movement_speed_scale() -> float:
	if not is_available():
		return UNARMED_SPEED_SCALE
	return float(WEAPON_SPEED_SCALES.get(weapon_id(), 0.85))

func is_presented() -> bool:
	return is_available() and walker.camera.current

func refresh_visibility() -> void:
	_update_arm_appearance()
	rig.visible = is_presented()
	view_fill.visible = rig.visible
	if is_instance_valid(third_person_model):
		third_person_model.visible = is_available() and walker.follow_camera.current
	walker.hands.visible = walker.camera.current and not rig.visible

func switch_weapon(index: int) -> void:
	if index < 0 or index >= loadout.size() or (level.armed_campaign and not owned.has(loadout[index])):
		return
	if level.held != &"":
		level.put_down_held_prop()
		interaction_left = 0.0
	current_index = index
	reload_left = 0.0
	aiming = false
	holstered = false
	cooldown = maxf(cooldown, 0.20)
	var profile: Dictionary = PROFILES[weapon_id()]
	for attachment in rig.find_children("*", "BoneAttachment3D", true, false):
		for child in attachment.get_children():
			child.visible = String(child.name) in [profile.mesh, String(profile.mesh) + "_ammo"]
	_reset_animation()
	rig.position = profile.hip
	if is_instance_valid(third_person_model):
		third_person_model.queue_free()
	var mesh: Node3D = rig.find_child(profile.mesh, true, false)
	third_person_model = mesh.duplicate() as Node3D
	weapon_anchor.add_child(third_person_model)
	third_person_model.position = Vector3.ZERO
	third_person_model.rotation = Vector3.ZERO
	third_person_model.scale = Vector3.ONE * 0.7
	world_minigun_barrels = third_person_model.find_child("BarrelGroup", true, false) as Node3D
	if weapon_id() != "minigun":
		minigun_spin_speed = 0.0
	third_person_magazine = null
	var magazine: Node3D = rig.find_child(String(profile.mesh) + "_ammo", true, false)
	if magazine != null:
		third_person_magazine = magazine.duplicate() as Node3D
		third_person_model.add_child(third_person_magazine)
		third_person_magazine.transform = mesh.global_transform.affine_inverse() * magazine.global_transform
		magazine_position = third_person_magazine.position
	for geometry in third_person_model.find_children("*", "MeshInstance3D", true, false):
		geometry.layers = 1
	if third_person_model is MeshInstance3D:
		third_person_model.layers = 1
	refresh_visibility()
	_update_hud()

func interrupt_action() -> void:
	_cancel_reload()
	aiming = false
	interaction_left = 0.7

func _reset_animation() -> void:
	animation.stop()
	animation.play(_animation_clip("_fire"))
	animation.advance(0.0)
	animation.pause()

func _animation_clip(suffix: String) -> String:
	var profile: Dictionary = PROFILES[weapon_id()]
	return String(profile.get("animation", profile.mesh)) + suffix

func _cancel_reload() -> void:
	if reload_left > 0.0:
		reload_left = 0.0
		_reset_animation()

func _input(event: InputEvent) -> void:
	if walker == null or walker.role != walker.HUMAN or level.round_finished or not walker.is_processing_input():
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var index := _weapon_slot(event)
		if index >= 0 and index < loadout.size():
			switch_weapon(index)
			get_viewport().set_input_as_handled()
			return
		if not walker.mouse_captured:
			return
		match event.physical_keycode:
			KEY_X:
				holstered = not holstered
				_cancel_reload()
			KEY_R:
				reload_weapon()
			_:
				return
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and walker.mouse_captured:
		if event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			var step := 1 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -1
			for offset in range(1, loadout.size() + 1):
				var index := posmod(current_index + step * offset, loadout.size())
				if not level.armed_campaign or owned.has(loadout[index]):
					switch_weapon(index)
					break
			get_viewport().set_input_as_handled()

func _weapon_slot(event: InputEventKey) -> int:
	for code in [event.physical_keycode, event.keycode]:
		if code >= KEY_1 and code <= KEY_5:
			return code - KEY_1
		if code >= KEY_KP_1 and code <= KEY_KP_5:
			return code - KEY_KP_1
	return -1

func _physics_process(delta: float) -> void:
	if walker == null:
		return
	cooldown = maxf(0.0, cooldown - delta)
	interaction_left = maxf(0.0, interaction_left - delta)
	flash_left = maxf(0.0, flash_left - delta)
	hit_left = maxf(0.0, hit_left - delta)
	damage_feedback_left = maxf(0.0, damage_feedback_left - delta)
	var available := is_available()
	if not available or not walker.mouse_captured:
		trigger_blocked = true
	elif not Input.is_action_pressed("fire"):
		trigger_blocked = false
	if not available:
		_cancel_reload()
	if reload_left > 0.0:
		reload_left = maxf(0.0, reload_left - delta)
		if reload_left == 0.0:
			_finish_reload()
	var weapon: Dictionary = weapon_stats[weapon_id()]
	var focused: bool = available and walker.mouse_captured and Input.is_action_pressed("aim") and reload_left <= 0.0
	aiming = focused
	var active_camera: Camera3D = walker.follow_camera if walker.follow_camera.current else walker.camera
	var target_fov := float(weapon.zoom_fov) if focused else base_fov
	if walker.role == walker.HUMAN:
		active_camera.fov = lerpf(active_camera.fov, target_fov, 1.0 - exp(-14.0 * delta))
	if available and walker.mouse_captured and not trigger_blocked:
		var trigger := Input.is_action_pressed("fire") if bool(weapon.automatic) else Input.is_action_just_pressed("fire")
		if trigger:
			try_fire()
	if weapon_id() == "minigun" and is_instance_valid(minigun_barrels) and is_instance_valid(world_minigun_barrels):
		minigun_spin_speed = move_toward(minigun_spin_speed, 0.0, delta * 32.0)
		minigun_barrels.rotation.z = fposmod(minigun_barrels.rotation.z - minigun_spin_speed * delta, TAU)
		world_minigun_barrels.rotation.z = minigun_barrels.rotation.z
	_update_pose(delta)
	refresh_visibility()
	muzzle.visible = flash_left > 0.0 and rig.visible
	world_muzzle.visible = flash_left > 0.0 and third_person_model.is_visible_in_tree()
	hit_marker.visible = hit_left > 0.0
	_update_hud()

func _update_pose(delta: float) -> void:
	phase += delta * 9.0
	recoil = move_toward(recoil, 0.0, delta * 8.0)
	var speed := Vector2(walker.velocity.x, walker.velocity.z).length()
	var amount := clampf(speed / 5.0, 0.0, 1.0) * (0.25 if aiming else 1.0)
	var profile: Dictionary = PROFILES[weapon_id()]
	var target: Vector3 = profile.ads if aiming else profile.hip
	if walker.is_on_floor():
		target += Vector3(sin(phase) * 0.008, -absf(cos(phase)) * 0.007, 0) * amount
	target.z += recoil * 0.045
	rig.position = rig.position.lerp(target, 1.0 - exp(-18.0 * delta))
	rig.rotation.x = recoil * 0.025
	_update_world_pose(delta)

func _update_world_pose(delta: float) -> void:
	# Rebuild after appearance changes because set_role replaces the skeleton.
	var skeleton: Skeleton3D = walker.look.skeleton
	if skeleton != arm_skeleton:
		arm_skeleton = skeleton
		arm_ik = TwoBoneIK3D.new()
		arm_ik.setting_count = 2
		skeleton.add_child(arm_ik)
		for side in 2:
			var suffix := ".R" if side == 0 else ".L"
			arm_ik.set_root_bone_name(side, "UpperArm" + suffix)
			arm_ik.set_middle_bone_name(side, "LowerArm" + suffix)
			arm_ik.set_end_bone_name(side, "Hand" + suffix)
			arm_ik.set_target_node(side, arm_ik.get_path_to(hand_targets[side]))
			arm_ik.set_pole_node(side, arm_ik.get_path_to(elbow_targets[side]))
	arm_ik.active = is_available() and walker.follow_camera.current
	var height: float = walker.camera.position.y - 0.21
	weapon_anchor.position = Vector3(0.17, height, -0.36 + recoil * 0.035)
	var pitch: float = walker.camera.rotation.x
	var reload_motion := 0.0
	if reload_left > 0.0:
		var duration: float = weapon_stats[weapon_id()].reload_time
		reload_motion = sin(PI * (1.0 - reload_left / duration))
	weapon_anchor.rotation = Vector3(pitch + recoil * 0.05, 0, -reload_motion * 0.28)
	if is_instance_valid(third_person_magazine):
		third_person_magazine.position = magazine_position + Vector3.DOWN * reload_motion * 0.3
	hand_targets[0].position = Vector3(0.0, -0.05, 0.06)
	hand_targets[1].position = Vector3(-0.05, -0.06 - reload_motion * 0.25, -0.24 + reload_motion * 0.28)
	if weapon_id() == "pistol":
		hand_targets[1].position = Vector3(-0.055, -0.05 - reload_motion * 0.2, 0.01)
	elbow_targets[0].position = Vector3(0.65, height - 0.35, 0.05)
	elbow_targets[1].position = Vector3(-0.6, height - 0.35, -0.05)
	arm_ik.influence = move_toward(arm_ik.influence, 1.0, delta * 8.0)

func reload_weapon() -> bool:
	if not is_available() or reload_left > 0.0:
		return false
	var weapon: Dictionary = weapon_stats[weapon_id()]
	var rounds: Dictionary = ammo[weapon_id()]
	if rounds.mag >= int(weapon.mag_size) or (rounds.reserve <= 0 and not bool(weapon.get("infinite", false))):
		return false
	reload_left = float(weapon.reload_time)
	aiming = false
	var clip := _animation_clip("_reload")
	var duration := animation.get_animation(clip).length
	animation.play(clip, 0.08, duration / reload_left)
	Audio.play_3d("res://assets/audio/reload.ogg", walker.global_position, -5.0, 0.03)
	return true

func _finish_reload() -> void:
	var weapon: Dictionary = weapon_stats[weapon_id()]
	var rounds: Dictionary = ammo[weapon_id()]
	var needed := int(weapon.mag_size) - int(rounds.mag)
	var supplied := needed if bool(weapon.get("infinite", false)) else mini(needed, int(rounds.reserve))
	rounds.mag += supplied
	if not bool(weapon.get("infinite", false)):
		rounds.reserve -= supplied

func try_fire() -> bool:
	if not is_available() or not walker.mouse_captured or cooldown > 0.0 or reload_left > 0.0:
		return false
	var rounds: Dictionary = ammo[weapon_id()]
	if rounds.mag <= 0:
		reload_weapon()
		return false
	var weapon: Dictionary = weapon_stats[weapon_id()]
	rounds.mag -= 1
	cooldown = 1.0 / float(weapon.fire_rate)
	recoil = 1.0
	flash_left = 0.055
	if weapon_id() == "minigun":
		minigun_spin_speed = 36.0
	animation.play(_animation_clip("_fire"), 0.025)
	Audio.play_3d(weapon.sfx, walker.global_position, -4.0, 0.05, 85.0)
	var active_camera: Camera3D = walker.follow_camera if walker.follow_camera.current else walker.camera
	var from := active_camera.global_position
	var forward := -active_camera.global_basis.z
	var spread := tan(deg_to_rad(float(weapon.aim_spread_deg) if aiming else float(weapon.spread_deg)))
	if is_instance_valid(level.coop_session) and not Net.is_host():
		level.coop_session.send_shot(walker.camera.global_position, forward, weapon_id(), aiming)
		_update_hud()
		return true
	var hits := _collect_hits(from, walker.camera.global_position, active_camera.global_basis, weapon,
		spread, walker.follow_camera.current, true)
	for target: Node3D in hits:
		var entry: Dictionary = hits[target]
		var before: float = target.health
		var killed: bool = target.take_weapon_hit(entry.damage, entry.headshot)
		hit_left = 0.22
		hit_marker.modulate = Color(1.0, 0.38, 0.22) if killed else Color(1.0, 0.88, 0.5)
		damage_feedback_left = 1.3
		var label := "爆头" if entry.headshot else String(entry.region)
		damage_feedback = "%s −%d · 丧尸 %d/100" % [label, roundi(before - target.health), ceili(target.health)]
		target_hit.emit(killed)
	if not hits.is_empty():
		Audio.play_ui("res://assets/audio/hitmarker.wav", -8.0)
	shot_fired.emit(walker.global_position)
	_update_hud()
	return true


func _collect_hits(from: Vector3, eye: Vector3, basis: Basis, weapon: Dictionary,
		spread: float, check_muzzle: bool, show_impacts: bool) -> Dictionary:
	var forward := -basis.z
	var candidates := Hitboxes.collect(level.spawner.zombies, from, forward, float(weapon.range),
		spread + (0.03 if check_muzzle else 0.0))
	var ray := PhysicsRayQueryParameters3D.new()
	ray.collision_mask = 1 | 32
	var exclude: Array[RID] = [walker.get_rid()]
	for zombie in level.spawner.zombies:
		if is_instance_valid(zombie):
			exclude.append(zombie.get_rid())
	ray.exclude = exclude
	var hits: Dictionary = {}
	var directions := _shot_directions(basis, int(weapon.pellets), spread)
	for direction: Vector3 in directions:
		var hit := _trace_shot(from, from + direction * float(weapon.range), ray, candidates)
		if hit.is_empty():
			continue
		# A follow camera can see around a corner. Trace back from the player's eye
		# so the held gun remains blocked by the wall in front of the character.
		if check_muzzle:
			var near_hit := _trace_shot(eye, hit.position, ray, candidates)
			if not near_hit.is_empty():
				hit = near_hit
		if hit.has("target"):
			var target: Node3D = hit.target
			var region: StringName = hit.region
			if not hits.has(target):
				hits[target] = {"damage": 0.0, "region": region, "headshot": false, "strongest": 0.0}
			var entry: Dictionary = hits[target]
			if region == &"头部":
				entry.headshot = true
			else:
				var distance: float = eye.distance_to(hit.position)
				var damage := _body_damage(weapon, region, distance)
				entry.damage += damage
				if damage > float(entry.strongest):
					entry.strongest = damage
					entry.region = region
		elif show_impacts:
			_show_impact(hit.position, hit.normal)
	return hits


func resolve_room_shot(eye: Vector3, forward: Vector3, id: String, sighted: bool) -> Dictionary:
	if not weapon_stats.has(id):
		return {}
	var weapon: Dictionary = weapon_stats[id]
	var spread := tan(deg_to_rad(float(weapon.aim_spread_deg) if sighted else float(weapon.spread_deg)))
	var up := Vector3.RIGHT if absf(forward.y) > 0.995 else Vector3.UP
	var hits := _collect_hits(eye, eye, Basis.looking_at(forward, up), weapon, spread, false, false)
	var feedback := {}
	for target: Node3D in hits:
		var entry: Dictionary = hits[target]
		var before: float = target.health
		var killed: bool = target.take_weapon_hit(entry.damage, entry.headshot)
		feedback = {"killed": killed, "damage": roundi(before - target.health), "health": ceili(target.health),
			"region": "爆头" if entry.headshot else String(entry.region)}
	return feedback


func show_room_hit(feedback: Dictionary) -> void:
	hit_left = 0.22
	hit_marker.modulate = Color(1.0, 0.38, 0.22) if feedback.killed else Color(1.0, 0.88, 0.5)
	damage_feedback_left = 1.3
	damage_feedback = "%s −%d · 丧尸 %d/100" % [feedback.region, feedback.damage, feedback.health]
	Audio.play_ui("res://assets/audio/hitmarker.wav", -8.0)
	_update_hud()

static func _shot_directions(basis: Basis, count: int, spread: float) -> PackedVector3Array:
	var directions := PackedVector3Array()
	var forward := -basis.z
	if count > 1:
		directions.append(forward)
		# Rotate the spread each shot and distribute the remaining pellets across the cone.
		var rotation := randf() * TAU
		var rings: Array[int] = []
		for pellet in count - 1:
			rings.append(pellet)
		rings.shuffle()
		for pellet in rings.size():
			var angle := rotation + (float(pellet) + randf()) * TAU / rings.size()
			var radius := sqrt((float(rings[pellet]) + randf()) / rings.size()) * spread
			directions.append((forward + (basis.x * cos(angle) + basis.y * sin(angle)) * radius).normalized())
	else:
		var angle := randf() * TAU
		var radius := sqrt(randf()) * spread
		directions.append((forward + (basis.x * cos(angle) + basis.y * sin(angle)) * radius).normalized())
	return directions

static func _body_damage(weapon: Dictionary, region: StringName, distance: float) -> float:
	if weapon.id != "shotgun":
		return STANDARD_BODY_DAMAGE
	var scale: float = Hitboxes.DAMAGE_SCALE.get(region, 1.0)
	if weapon.id == "shotgun":
		var fraction := clampf(inverse_lerp(SHOTGUN_FALLOFF_START, SHOTGUN_FALLOFF_END, distance), 0.0, 1.0)
		scale *= lerpf(1.0, SHOTGUN_MIN_DAMAGE_SCALE, fraction)
	return float(weapon.damage) * scale

func _trace_shot(from: Vector3, to: Vector3, ray: PhysicsRayQueryParameters3D,
		candidates: Array[Dictionary]) -> Dictionary:
	ray.from = from
	ray.to = to
	var world_hit := get_world_3d().direct_space_state.intersect_ray(ray)
	var end: Vector3 = world_hit.get("position", to)
	var actor_hit := Hitboxes.intersect(from, end, candidates)
	return world_hit if actor_hit.is_empty() else actor_hit

func _show_impact(at: Vector3, normal: Vector3) -> void:
	var impact := IMPACT.instantiate() as Node3D
	level.add_child(impact)
	impact.global_position = at + normal * 0.01
	var up := Vector3.FORWARD if absf(normal.y) > 0.95 else Vector3.UP
	impact.look_at(impact.global_position + normal, up)

func _update_hud() -> void:
	var rounds: Dictionary = ammo[weapon_id()]
	var weapon: Dictionary = weapon_stats[weapon_id()]
	var reserve := "∞" if bool(weapon.get("infinite", false)) else str(rounds.reserve)
	var status := "换弹中" if reload_left > 0.0 else "%d / %s" % [rounds.mag, reserve]
	if holstered:
		status = "X 拔枪"
	ammo_label.text = "%s  %s\n%s" % [weapon.get("hud_label", PROFILES[weapon_id()].label), status, loadout_hint]
	if damage_feedback_left > 0.0:
		ammo_label.text += "\n" + damage_feedback
	ammo_label.visible = walker.role == walker.HUMAN and not level.round_finished
	if level.armed_campaign and not owned.has(weapon_id()):
		ammo_label.text = "没有武器"

func _exit_tree() -> void:
	if is_instance_valid(third_person_model):
		third_person_model.queue_free()
	if is_instance_valid(weapon_anchor):
		weapon_anchor.queue_free()
	if is_instance_valid(arm_ik):
		arm_ik.queue_free()
	for elbow in elbow_targets:
		if is_instance_valid(elbow):
			elbow.queue_free()
