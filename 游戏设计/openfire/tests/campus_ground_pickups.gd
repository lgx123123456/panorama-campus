extends Node
var failed := false
var world: Node3D
var level: Node3D
var campaign: Node3D
var walker: CharacterBody3D
const OUTPUT := "C:/CampusReconstructionRuntime/floor-pickup-repair/"
func _ready() -> void:
	if "--capture" in OS.get_cmdline_user_args():
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)
	call_deferred("run")
func run() -> void:
	reparent(get_tree().root)
	get_tree().change_scene_to_file("res://scenes/campus/survival_admin.tscn")
	await get_tree().scene_changed
	world = get_tree().current_scene
	level = world.get_node("CharacterTrial")
	campaign = level.campaign
	walker = level.walker
	walker.set_physics_process(false)
	level.set_physics_process(false)
	level.spawner.set_physics_process(false)
	campaign.set_physics_process(false)
	level.set_debug_invincible(true)
	walker.global_position = campaign.upper_landing + Vector3.UP * .03
	walker.velocity = Vector3.ZERO
	world.refresh_collision()
	await wait_frames(8)
	campaign._ground_supplies_near_player()
	var roof: Array = campaign.supplies.filter(func(item): return item.encounter == &"roof")
	check(roof.size() == 1, "solo keeps one highest-floor random gun")
	for item: Dictionary in roof:
		check(item.point.distance_to(campaign.upper_landing) < 4.0, "gun is directly ahead of the west-stair landing")
		check(item.has("model") and item.model is Node3D and item.model.get_parent() == campaign,
			"random gun uses a real ground model independent of its billboard")
		check(clear_standing_space(item.point), "highest-floor gun has clear standing space")
		check(level.clear_line(campaign.upper_landing + Vector3.UP * 1.5, item.point + Vector3.UP * .15),
			"highest-floor gun is visible from the landing")
		var floor_hit := floor_at(item.point)
		check(not floor_hit.is_empty() and absf(floor_hit.position.y - item.point.y) < .04,
			"highest-floor gun rests on the actual fifth-floor slab")
		print("GROUND PICKUP POSITION ",item.point," FLOOR ",floor_hit.get("collider"))
		check_ground_model(item)
		var reached := await walk_to(item.point)
		check(reached, "player can physically walk from the landing to the gun")
		if reached:
			var grant: Array = item.grants[0]
			check(press_pickup_key() and level.firearms.owned.has(grant[0]), "real E input grants the ground gun")
			check(int(level.firearms.ammo[grant[0]].mag) + int(level.firearms.ammo[grant[0]].reserve) == int(grant[1]),
				"ground pickup grants the configured random-weapon ammunition")
			check(not campaign.interact(), "ground gun can only be collected once")
	await check_party_placement()
	await check_weapon_models()
	await check_field_grounding()
	if "--capture" in OS.get_cmdline_user_args():
		await capture_gallery()
	print("GROUND PICKUPS ","FAIL" if failed else "PASS")
	get_tree().quit(1 if failed else 0)
func floor_at(at: Vector3) -> Dictionary:
	return world.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(at+Vector3.UP*.7,at-Vector3.UP*.5,1))
func clear_standing_space(at: Vector3) -> bool:
	var shape := CapsuleShape3D.new()
	shape.height = 1.73
	shape.radius = .30
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.collision_mask = 1
	query.transform.origin = at + Vector3.UP * .89
	return world.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()
func walk_to(target: Vector3) -> bool:
	walker._capture_mouse(true)
	for frame in 400:
		var direction := target - walker.global_position
		direction.y = 0
		if direction.length() < .75:
			Input.action_release("move_forward")
			return absf(walker.global_position.y-target.y) < .15
		walker.look_at(walker.global_position+direction)
		Input.action_press("move_forward")
		walker._physics_process(get_physics_process_delta_time())
		await get_tree().physics_frame
	Input.action_release("move_forward")
	print("WALK BLOCKED ",walker.global_position, " target ",target)
	return false
func capture_gallery() -> void:
	walker._capture_mouse(false)
	level.firearms.holstered = true
	level.firearms.refresh_visibility()
	walker.camera.make_current()
	campaign.roof_count = 0
	for id: String in campaign.RANDOM_WEAPONS:
		walker.global_position = campaign.upper_landing + Vector3.UP * .03
		walker.velocity = Vector3.ZERO
		world.refresh_collision()
		await wait_frames(4)
		campaign._add_supply("五层 · " + campaign.WEAPON_NAMES[id],campaign.top_floor_supply,
			[[id,campaign.SUPPLY_ROUNDS[id],true]],&"capture")
		campaign._ground_supplies_near_player()
		var item: Dictionary = campaign.supplies[-1]
		walker.look_at(Vector3(item.point.x,walker.global_position.y,item.point.z))
		walker.camera.look_at(item.point + Vector3.UP * .20)
		campaign._update_objective(walker.global_position)
		await wait_frames(20)
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(OUTPUT + "west-landing-" + id + ".png")
		if id == "rifle":
			walker.global_position = item.point + Vector3(-1.5,.03,0)
			walker.camera.look_at(item.point + Vector3.UP * .05)
			await wait_frames(12)
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(OUTPUT + "ground-rifle-close.png")
		item.marker.queue_free()
		item.model.queue_free()
		campaign.supplies.pop_back()
		await wait_frames(2)
	print("GROUND CAPTURES ",OUTPUT)

func check_ground_model(item: Dictionary) -> void:
	check(item.get("grounded", false), "pickup passes floor-ray and standing-capsule grounding")
	if not item.has("model"):
		return
	var gun: MeshInstance3D = item.model.get_node_or_null("WeaponMesh")
	check(gun != null and gun.visible and gun.layers == 1, "pickup displays the authored weapon mesh on the world layer")
	if gun == null:
		return
	var bounds := gun.global_transform * gun.get_aabb()
	check(bounds.position.y > item.point.y + .015 and bounds.end.y < item.point.y + .25,
		"weapon lies flat just above the floor")
	var before: Basis = item.model.global_basis
	walker.camera.rotate_y(PI * .5)
	check(item.model.global_basis.is_equal_approx(before), "turning the camera leaves the ground weapon orientation fixed")
	walker.camera.rotate_y(-PI * .5)

func check_party_placement() -> void:
	var net := get_tree().root.get_node("Net")
	var saved_players: Dictionary = net.players.duplicate(true)
	var saved_room: bool = net.campus_room
	var script = load("res://scripts/campus/campus_armed_campaign.gd")
	walker.global_position = campaign.upper_landing + Vector3.UP * .03
	world.refresh_collision()
	await wait_frames(4)
	for count in range(1, 11):
		net.campus_room = true
		net.players.clear()
		for index in count:
			net.players[index + 1] = {"name": "Test"}
		var trial: Node3D = script.new()
		trial.level = level
		level.add_child(trial)
		trial.set_physics_process(false)
		trial._ground_supplies_near_player()
		var roof: Array = trial.supplies.filter(func(item): return item.encounter == &"roof")
		var field: Array = trial.supplies.filter(func(item): return item.encounter == &"field")
		check(roof.size()+field.size() == maxi(2,count), "%d-player random gun quota is preserved" % count)
		var clear := true
		for item: Dictionary in roof:
			clear = clear and item.get("grounded", false) and clear_standing_space(item.point) \
				and absf(item.point.y-15.48) < .04 \
				and level.clear_line(campaign.upper_landing + Vector3.UP * 1.5,item.point + Vector3.UP * .15)
		check(clear, "%d-player highest-floor guns have a floor, clearance and landing sightline" % count)
		trial.queue_free()
		await wait_frames(1)
	net.players = saved_players
	net.campus_room = saved_room

func check_weapon_models() -> void:
	for id: String in campaign.RANDOM_WEAPONS:
		campaign._add_supply("测试 · " + id,campaign.top_floor_supply,[[id, campaign.SUPPLY_ROUNDS[id],true]],&"model_test")
		campaign._ground_supplies_near_player()
		var item: Dictionary = campaign.supplies[-1]
		check_ground_model(item)
		var before_mag: int = level.firearms.ammo[id].mag
		var before_reserve: int = level.firearms.ammo[id].reserve
		var already_owned: bool = level.firearms.owned.has(id)
		check(await walk_to(item.point), id + " model is reachable")
		check(press_pickup_key(), id + " ground model can be collected with E")
		var total: int = int(level.firearms.ammo[id].mag) + int(level.firearms.ammo[id].reserve)
		check(total == int(campaign.SUPPLY_ROUNDS[id]) + (before_mag+before_reserve if already_owned else 0),
			id + " grants the correct ammunition")
		await wait_frames(2)

func check_field_grounding() -> void:
	walker.global_position = campaign.FIELD + Vector3.UP * .03
	world.refresh_collision()
	await wait_frames(5)
	campaign._ground_supplies_near_player()
	var field: Array = campaign.supplies.filter(func(item): return item.encounter == &"field")
	for item: Dictionary in field:
		check_ground_model(item)
		check(not floor_at(item.point).is_empty(), "field gun rests on the streamed ground collision")

func press_pickup_key() -> bool:
	var count: int = campaign.supplies.size()
	var event := InputEventKey.new()
	event.physical_keycode = KEY_E
	event.pressed = true
	walker._input(event)
	return campaign.supplies.size() == count - 1
func wait_frames(count: int) -> void:
	for frame in count:
		await get_tree().physics_frame
func check(ok: bool, title: String) -> void:
	print("GROUND ","PASS " if ok else "FAIL ",title)
	failed = failed or not ok
