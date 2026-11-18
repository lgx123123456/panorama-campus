extends "res://tests/campus_east_stairs.gd"

const OUTPUT := "C:/CampusReconstructionRuntime/flow-access-repair"
var world: Node3D
var baseline := false

class NavigationTrial extends Node3D:
	var walker: CharacterBody3D
	var layout: Node3D
	var round_finished := false
	var zombie_attack_range := 0.05
	var zombie_run_speed := 2.75
	func queue_path(zombie: Node3D) -> void:
		zombie.agent.target_position = zombie.goal
		zombie.last_path = zombie.goal
	func try_stairs(actor: Node3D, waypoint: Vector3, speed: float) -> bool:
		var route: PackedVector3Array = layout.stair_route(actor.global_position, waypoint)
		if route.is_empty():
			return false
		actor.start_route(route, minf(speed, 2.15))
		return true
	func release_bite(_actor: Node3D) -> void:
		pass

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file("res://scenes/campus/survival_admin.tscn" if "--survival-check" in OS.get_cmdline_user_args() else "res://scenes/campus/gate_plaza.tscn")
	await tree.scene_changed
	world = tree.current_scene
	walker = world.get_node("Walker")
	walker.set_physics_process(false)
	baseline = "--baseline" in OS.get_cmdline_user_args()
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_entrances.json"))
	if "--survival-check" in OS.get_cmdline_user_args():
		var level: Node = world.get_node("CharacterTrial")
		level.set_physics_process(false)
		level.spawner.set_physics_process(false)
		level.set_debug_invincible(true)
		var selected_identity := 0
		var selected_modes: Array[String] = ["normal", "quiet", "sprint"]
		for argument: String in OS.get_cmdline_user_args():
			if argument.begins_with("--identity="):
				selected_identity = int(argument.get_slice("=", 1))
			if argument.begins_with("--mode="):
				selected_modes.assign([argument.get_slice("=", 1)])
		if selected_identity < 0 or selected_identity >= 5 or selected_modes.any(func(mode: String): return mode not in ["normal", "quiet", "sprint"]):
			push_error("Invalid dorm survival identity or movement mode")
			tree.quit(1)
			return
		walker.set_role(selected_identity, 0)
		walker._capture_mouse(true)
		for mode: String in selected_modes:
			walker.quiet = mode == "quiet"
			Input.action_release("sprint")
			if mode == "sprint":
				Input.action_press("sprint")
			print("DORM SURVIVAL MODE ", mode, " flat_speed=", walker._movement_speed(),
				" identity=", walker.identity, " capsule_height=", walker.capsule.height,
				" stair_multiplier=", walker.stair_speed_multiplier,
				" controller=", walker.get_script().resource_path)
			for building: Dictionary in data.dorm_layouts:
				for key: String in ["west", "east"]:
					if not await _check_stair(building, key, data):
						print("DORM SURVIVAL FAIL mode=", mode)
						tree.quit(1)
						return
			print("DORM SURVIVAL MODE PASS ", mode, " four stairs upward/downward and corridor/exterior returns")
		Input.action_release("sprint")
		print("DORM SURVIVAL PASS movement_modes=", selected_modes, " identity=", walker.identity, " four new stairs")
		tree.quit()
		return
	if baseline:
		await _baseline(data)
		return
	if "--npc-only" in OS.get_cmdline_user_args():
		tree.quit(0 if await _check_navigation_and_zombies(data) else 1)
		return
	if "--capture-only" in OS.get_cmdline_user_args():
		for building: Dictionary in data.dorm_layouts:
			for key: String in ["west", "east"]:
				var stair: Dictionary = building.stairs[key]
				var path: Array = stair.corridor_paths[0]
				var first: Array = stair.routes[0].points
				await _place_at(_point(path[0]))
				await _picture(_point(path[0]) + Vector3.UP * 1.60,
					_point(first[2]) + Vector3.UP * 0.95,
					"dorm-after-" + str(building.building) + "-" + key + ".png")
				await _picture(_point(first[1]) + Vector3.UP * 1.60,
					_point(path[0]) + Vector3.UP * 1.40,
					"dorm-exit-" + str(building.building) + "-" + key + ".png")
		print("DORM ACCESS CAPTURE PASS four entry and four ground-floor exit views")
		tree.quit()
		return
	for layout: Dictionary in data.dorm_layouts:
		for key: String in ["west", "east"]:
			if not await _check_stair(layout, key, data):
				tree.quit(1)
				return
	print("DORM ACCESS WALK PASS four aligned entrances, ",
		"two" if "--quick" in OS.get_cmdline_user_args() else "seven", " floors and exterior returns")
	tree.quit()

func _check_stair(layout: Dictionary, key: String, data: Dictionary) -> bool:
	var stair: Dictionary = layout.stairs[key]
	var label: String = str(layout.building) + " " + key
	var path: Array = stair.corridor_paths[0]
	var exterior: Array = []
	if layout.building == "B25":
		var record: Dictionary = data.dorm_end_doors.filter(func(item: Dictionary):
			return item.id == "B25_" + key + "_end")[0]
		exterior = record.points
		await _place_at(_point(exterior[0]))
		if not await _route(exterior, label + " external entry"):
			return false
	else:
		await _place_at(_point(path[0]))
	if not await _route(path, label + " straight doorway"):
		return false
	var first: Array = stair.routes[0].points
	await _picture(_point(path[0]) + Vector3.UP * 1.60,
		_point(first[2]) + Vector3.UP * 0.95,
		"dorm-after-" + str(layout.building) + "-" + key + ".png")
	var routes: Array = stair.routes.slice(0, 1) if "--quick" in OS.get_cmdline_user_args() else stair.routes
	for route: Dictionary in routes:
		if not await _route(route.points, label + " ascent " + str(route.to_floor)):
			return false
		var to_corridor: Array = stair.corridor_paths[int(route.to_floor) - 1].duplicate()
		to_corridor.reverse()
		if not await _route(to_corridor, label + " floor corridor"):
			return false
		to_corridor.reverse()
		if not await _route(to_corridor, label + " corridor return"):
			return false
	var descending := routes.duplicate()
	descending.reverse()
	for route: Dictionary in descending:
		var down: Array = route.points.duplicate()
		down.reverse()
		if not await _route(down, label + " descent " + str(route.from_floor)):
			return false
	var to_hall: Array = path.duplicate()
	to_hall.reverse()
	if not await _route(to_hall, label + " ground corridor"):
		return false
	await _picture(_point(first[1]) + Vector3.UP * 1.6,
		_point(path[0]) + Vector3.UP * 1.4,
		"dorm-exit-" + str(layout.building) + "-" + key + ".png")
	if not exterior.is_empty():
		var exit_path := exterior.duplicate()
		exit_path.reverse()
		if not await _route(exit_path, label + " exterior return"):
			return false
	print("DORM ACCESS PASS ", label, " floor_count=", routes.size() + 1)
	var old_path: Array = stair.access_repair.original_corridor_paths[0]
	await _place_at(_point(old_path[0]))
	var building := _frame(layout.frame)
	var local := building.affine_inverse() * _point(old_path[0])
	local.x = -9.50 if layout.building == "B25" else -13.10
	var ray := PhysicsRayQueryParameters3D.create(walker.global_position + Vector3.UP,
		building * local + Vector3.UP, 1)
	var hit := walker.get_world_3d().direct_space_state.intersect_ray(ray)
	if hit.is_empty() or not str(hit.collider.name).begins_with("DormFormerOpeningWall"):
		print("DORM OLD DOOR FAIL ", label, " hit=", hit)
		return false
	print("DORM OLD DOOR CLOSED ", label)
	return true

func _check_navigation_and_zombies(data: Dictionary) -> bool:
	var layout: Node3D = load("res://scripts/campus/campus_survival_layout.gd").new()
	world.add_child(layout)
	layout.build(world.get_node("Doors"))
	var doors: Node = world.get_node("Doors")
	var dorm_door_index: int = doors.doors.find_custom(func(item: Dictionary): return item.id == "B28")
	var matching: Array = layout.passages.filter(func(item: Dictionary): return item.door == dorm_door_index)
	if matching.size() != 1 or int(matching[0].from) != layout._dorm_zone("B28", 1) or int(matching[0].to) != layout.OUTSIDE:
		print("DORM B28 EXTERNAL TOPOLOGY FAIL ", matching)
		return false
	if not matching[0].link.enabled or not matching[0].link.bidirectional:
		print("DORM B28 EXTERNAL LINK FAIL")
		return false
	print("DORM B28 EXTERNAL TOPOLOGY PASS inside_zone=", matching[0].from,
		" outside_zone=", matching[0].to, " bidirectional/open link")
	var level := NavigationTrial.new()
	level.walker = walker
	level.layout = layout
	world.add_child(level)
	for tick in 120:
		await get_tree().physics_frame
	var map := world.get_world_3d().navigation_map
	if not _check_b28_door_hearing_and_path(data, layout, level, doors, map):
		return false
	for building: Dictionary in data.dorm_layouts:
		for key: String in ["west", "east"]:
			var stair: Dictionary = building.stairs[key]
			var start := _point(stair.corridor_paths[0][0])
			var finish := _point(stair.corridor_paths[1][0])
			walker.global_position = start + Vector3.RIGHT * 5.0 + Vector3.UP * 0.05
			world.refresh_collision()
			var path := NavigationServer3D.map_get_path(map, start, finish, true)
			print("DORM NPC NAV ", building.building, " ", key, " path=", path)
			if path.size() < 2 or path[-1].distance_to(finish) > 0.5:
				return false
			var zombie: CharacterBody3D = load("res://scripts/campus/campus_zombie.gd").new()
			zombie.level = level
			zombie.appearance_infected = true
			zombie.terrain_steps = true
			zombie.position = start + Vector3.UP * 0.04
			level.add_child(zombie)
			zombie.set_physics_process(false)
			zombie.think_in = INF
			zombie.next_bite = INF
			zombie.state_time = INF
			zombie.state = zombie.State.INVESTIGATE
			var passed := await _zombie_to(zombie, finish)
			passed = await _zombie_to(zombie, start) and passed
			print("DORM NPC PHYSICS ", "PASS " if passed else "FAIL ", building.building,
				" ", key, " upward and downward at=", zombie.global_position)
			zombie.free()
			if not passed:
				return false
	print("DORM NPC PASS four new stairs navigation and physical ascent/descent")
	return true

func _check_b28_door_hearing_and_path(data: Dictionary, layout: Node3D,
		trial: NavigationTrial, doors: Node, map: RID) -> bool:
	var building: Dictionary = data.dorm_layouts.filter(func(item: Dictionary): return item.building == "B28")[0]
	var frame := _frame(building.frame)
	var outside := frame * Vector3(1.5, 0, 0.57)
	var inside := frame * Vector3(-3.0, 0, 0.57)
	var path := NavigationServer3D.map_get_path(map, outside, inside, true)
	if path.size() < 3 or path[-1].distance_to(inside) > 0.6:
		print("DORM B28 DOOR NAV FAIL ", path)
		return false
	var hearing: Node3D = load("res://scripts/campus/campus_zombie_level.gd").new()
	var spawner: Node = load("res://scripts/campus/campus_zombie_spawner.gd").new()
	hearing.layout = layout
	hearing.doors = doors
	hearing.spawner = spawner
	var listener: CharacterBody3D = load("res://scripts/campus/campus_zombie.gd").new()
	listener.level = trial
	listener.position = inside
	trial.add_child(listener)
	listener.set_physics_process(false)
	spawner.zombies.append(listener)
	hearing._emit_sound(outside, 20.0, &"door")
	var heard: bool = listener.heard_id == 1
	print("DORM B28 DOOR HEARING ", "PASS" if heard else "FAIL", " outside_zone=", layout.zone_at(outside),
		" inside_zone=", layout.zone_at(inside), " heard_id=", listener.heard_id, " nav_path=", path)
	spawner.zombies.clear()
	listener.free()
	spawner.free()
	hearing.free()
	return heard

func _zombie_to(zombie: CharacterBody3D, target: Vector3) -> bool:
	zombie.goal = target
	zombie.last_path = Vector3.INF
	var used_route := false
	for tick in 2200:
		zombie._physics_process(1.0 / 60.0)
		used_route = used_route or not zombie.route.is_empty()
		await get_tree().physics_frame
		if zombie.global_position.distance_to(target) < 0.42:
			return used_route
	print("DORM NPC BLOCKED at=", zombie.global_position, " target=", target,
		" route=", zombie.route, " route_index=", zombie.route_index)
	for index in zombie.get_slide_collision_count():
		var hit := zombie.get_slide_collision(index)
		print("DORM NPC CONTACT ", hit.get_collider(), " ", hit.get_position())
	return false

func _route(points: Array, label: String) -> bool:
	for value: Array in points:
		var target := _point(value)
		if not await _go(target):
			print("DORM ACCESS FAIL ", label, " at=", walker.global_position, " target=", target)
			await _picture(walker.global_position + Vector3.UP * 1.59,
				target + Vector3.UP * 1.1, "dorm-failure.png")
			return false
		for tick in 8:
			walker._physics_process(1.0 / 60.0)
			await get_tree().physics_frame
		if absf(walker.global_position.y - target.y) > 0.24:
			print("DORM HEIGHT FAIL ", label, " at=", walker.global_position, " target=", target)
			return false
	return true

func _frame(rows: Array) -> Transform3D:
	return Transform3D(Basis(_point([rows[0][0], rows[1][0], rows[2][0]]),
		_point([rows[0][1], rows[1][1], rows[2][1]]),
		_point([rows[0][2], rows[1][2], rows[2][2]])),
		_point([rows[0][3], rows[1][3], rows[2][3]]))

func _place_at(at: Vector3) -> void:
	walker.global_position = at + Vector3.UP * 0.04
	walker.velocity = Vector3.ZERO
	world.refresh_collision()
	for tick in 15:
		walker._physics_process(1.0 / 60.0)
		await get_tree().physics_frame

func _baseline(data: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	var blocked := 0
	for layout: Dictionary in data.dorm_layouts:
		for key: String in ["west", "east"]:
			var stair: Dictionary = layout.stairs[key]
			var t := _frame(stair.stair_frame)
			var building := _frame(layout.frame)
			var foot := t * Vector3(-0.62, 5.85, float(layout.levels[0].z))
			var local := building.affine_inverse() * foot
			local.x = -12.05 if layout.building == "B25" else -15.65
			var start := building * local
			await _place_at(start)
			var target := t * Vector3(-0.62, 4.20, float(layout.levels[0].z))
			var reached := await _go(target)
			print("DORM ACCESS BASELINE ", layout.building, " ", key,
				" straight_entry=", reached, " at=", walker.global_position, " expected=", target)
			if not reached:
				blocked += 1
			await _picture(start + Vector3.UP * 1.6, target + Vector3.UP * 1.0,
				"dorm-before-" + str(layout.building) + "-" + key + ".png")
		print("DORM BASELINE STAIR MESHES ", layout.building)
		for visual: MeshInstance3D in world.get_node("CampusVisuals").find_children("*", "MeshInstance3D", true, false):
			if not str(visual.name).begins_with(str(layout.building) + " 宿舍贴合室内 "):
				continue
			var box := visual.global_transform * visual.get_aabb()
			var center := box.get_center()
			var s := _frame(layout.stairs.west.stair_frame).affine_inverse() * center
			if absf(s.x) < 2.0 and s.y > -0.2 and s.y < 5.2 and center.y < 4.1:
				print("DORM MESH ", visual.name, " stair_center=", s, " bounds=", box)
	print("DORM ACCESS BASELINE blocked=", blocked, "/4")
	get_tree().quit(0 if blocked == 4 else 1)

func _picture(eye: Vector3, target: Vector3, filename: String) -> void:
	if DisplayServer.get_name() == "headless" or "--survival-check" in OS.get_cmdline_user_args():
		return
	var camera: Camera3D = walker.get_node("Camera3D")
	var original := camera.transform
	var interface: CanvasLayer = world.get_node("Interface")
	var interface_visible := interface.visible
	interface.hide()
	camera.global_position = eye
	camera.look_at(target)
	for tick in 8:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(OUTPUT.path_join(filename))
	camera.transform = original
	interface.visible = interface_visible
