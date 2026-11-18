extends Node3D

const Points = preload("res://scripts/campus/campus_survival_points.gd")
const FieldPassages = preload("res://scripts/campus/campus_field_passages.gd")
const TaskMarker = preload("res://scripts/campus/campus_task_marker.gd")
const ROUTE_REACH := 1.7
const FIELD_EXIT_REACH := 1.65
const LIBRARY_REACH := 3.0
const PLAZA_PREPARATION_POINT := Vector3(0, 0.15, -78.2)
const FIELD := Vector3(-294, 0.2, -120)
const PLAZA_APPROACH := Vector3(-33, 0.2, -133)
const PLAZA := Vector3(0, 0.2, -12)
const LIBRARY_WEST_TRIGGER := Rect2(-58, -152, 33, 30)
const SHANGDE_ARRIVAL := Rect2(-26, -49, 52, 55)
const MAIN_GATE_OUTSIDE := Vector3(0, 0.20, 10.5)
const MAIN_GATE_HALF_WIDTH := 9.4
const FINAL_SUPPLIES := [Vector3(-4.0, 0.20, -62.0), Vector3(0, 0.20, -63.0), Vector3(4.0, 0.20, -62.0)]
const FINAL_APPROACH_Z := -80.0
const FINAL_WARNING_Z := -40.0
const FINAL_PREPARATION_SECONDS := 6.0
const LIBRARY_EAST := Vector3(65, 0.2, -153)
const RANDOM_WEAPONS := ["pistol", "rifle", "smg", "shotgun"]
const SUPPLY_ROUNDS := {"pistol": 24, "rifle": 48, "smg": 60, "shotgun": 16}
const WEAPON_NAMES := {"pistol": "手枪", "rifle": "步枪", "smg": "冲锋枪", "shotgun": "霰弹枪"}

var level: Node3D
var upper_landing: Vector3
var top_floor_supply: Vector3
var roof_quota := 1
var field_quota := 1
var dorm_start: Vector3
var dorm_exit: Vector3
var dorm_supply: Vector3
var dorm_west_stairs: Vector3
var dorm_east_stairs: Vector3
var dorm_east_down: Vector3
var dorm_entries: Array[Dictionary] = []
var supplies: Array[Dictionary] = []
var roof_wave := false
var roof_count := 0
var field_wave := false
var plaza_wave := false
var direct_plaza_wave := false
var field_count := 0
var left_track := false
var field_passage := -1
var dorm_entered := false
var dorm_upper := false
var dorm_crossed_upper := false
var dorm_descended := false
var dorm_left := false
var went_east := false
var finale_started := false
var finale_supplies_ready := false
var finale_countdown := -1.0
var final_weapon_count := 0
var last_position := Vector3.INF
var mission := ""
var grounding_retry := 0.0
var route_marker: TaskMarker
var field_exit_markers: Array[TaskMarker] = []

func _ready() -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(level.doors.DOOR_DATA))
	upper_landing = Points.point(data.teaching_west_stairs.buildings[0].corridor_points[-1])
	var teaching: Dictionary = data.teaching_west_stairs.buildings[0]
	var corner := Points.point(teaching.corridor_path[0])
	var along := (Points.point(teaching.corridor_path[1]) - corner).normalized()
	# Keep all five possible pickups in the open west-stair corridor, before
	# its first turn. The former side offset put them beyond an interior wall.
	top_floor_supply = upper_landing + along * 2.8
	top_floor_supply.y = float(teaching.levels[-1])
	var quota := weapon_quota(Net.players.size() if Net.campus_room else 1)
	roof_quota = quota.x
	field_quota = quota.y
	var dorm: Dictionary = data.dorm_layouts.filter(func(item): return item.building == "B25")[0]
	dorm_start = Points.point(data.dorm_end_doors[0].points[1])
	dorm_exit = Points.point(data.dorm_end_doors[1].points[0])
	dorm_west_stairs = Points.point(dorm.stairs.west.corridor_paths[0][0])
	dorm_east_stairs = Points.point(dorm.stairs.east.corridor_paths[1][0])
	dorm_east_down = Points.point(dorm.stairs.east.corridor_paths[0][0])
	dorm_supply = Points.point(dorm.stairs.west.routes[0].points[-1])
	for record: Dictionary in data.doors:
		if record.building != "B25":
			continue
		var point := Points.point(record.center)
		var corridor: Vector3 = level.layout.dorm_start + level.layout.dorm_axis * clampf(
			(point - level.layout.dorm_start).dot(level.layout.dorm_axis), 0.0, level.layout.dorm_length)
		var inward := (corridor - point).slide(Vector3.UP).normalized()
		dorm_entries.append({"point": point, "inward": inward, "width": float(record.width)})
	for index in roof_quota:
		_add_random_weapon(top_floor_supply + along * (1.2 * index), &"roof", "五层")
	for index in field_quota:
		_add_random_weapon(FIELD + Vector3(3.4 * index, 0, -1.4 * (index % 2)), &"field", "操场")
	_add_supply("二层弹药补给", dorm_supply,
		[["pistol", 24, false], ["rifle", 48, false], ["smg", 60, false], ["shotgun", 12, false]], &"dorm")
	route_marker = TaskMarker.new()
	route_marker.hide()
	add_child(route_marker)
	for exit: Vector3 in FieldPassages.EXIT:
		var area := _make_area(exit + Vector3(0.65, 0, 0), FIELD_EXIT_REACH)
		area.hide()
		field_exit_markers.append(area)
	level.spawner.set_spawn_interval(2.2)
	level.spawner.group_size = 2
	level.spawner.set_spawn_range(7.5, 24.0)

static func weapon_quota(player_count: int) -> Vector2i:
	var total := maxi(2, clampi(player_count, 1, 10))
	return Vector2i((total + 1) / 2, total / 2)

func _add_random_weapon(point: Vector3, encounter: StringName, location: String) -> void:
	var id: String = RANDOM_WEAPONS.pick_random()
	var rounds: int = SUPPLY_ROUNDS[id]
	_add_supply("%s · %s · %d发" % [location, WEAPON_NAMES[id], rounds], point,
		[[id, rounds, true]], encounter)

func _physics_process(delta: float) -> void:
	if level.round_finished or level.walker.role != level.walker.HUMAN:
		return
	grounding_retry -= delta
	if grounding_retry <= 0.0:
		grounding_retry = 0.25
		_ground_supplies_near_player()
	var at: Vector3 = level.walker.global_position
	for index in supplies.size():
		var supply := supplies[index]
		if supply.area.contains(at) and _can_collect(supply, at):
			_collect(index, at)
			break
	if not left_track:
		_check_field_crossing(at)
	_update_plaza_encounter(at)
	if not dorm_entered and _entered_dorm(at):
		dorm_entered = true
		level.spawner.start_dorm_ambush(at)
		level._report("一楼走廊有尸群，从西楼梯上二层绕行。", 7.0)
	if dorm_entered and level.layout.zone_at(at) == level.layout.DORM_FLOOR_TWO \
			and TaskMarker.covers(at, dorm_supply, ROUTE_REACH):
		dorm_upper = true
	if dorm_upper and level.layout.zone_at(at) == level.layout.DORM_FLOOR_TWO \
			and TaskMarker.covers(at, dorm_east_stairs, ROUTE_REACH):
		dorm_crossed_upper = true
	if dorm_crossed_upper and level.layout.zone_at(at) == level.layout.DORM_FLOOR_ONE \
			and TaskMarker.covers(at, dorm_east_down, ROUTE_REACH):
		dorm_descended = true
	if dorm_descended and TaskMarker.covers(at, dorm_exit, ROUTE_REACH) and level.layout.zone_at(at) == level.layout.OUTSIDE:
		dorm_left = true
	if dorm_left and TaskMarker.covers(at, LIBRARY_EAST, LIBRARY_REACH):
		went_east = true
	# Entering the final stretch is the trigger. Optional pickups and route
	# flags must not suppress the supplies or prevent an actual gate exit.
	if not finale_supplies_ready and at.y < 2.0 and level.layout.zone_at(at) == level.layout.OUTSIDE \
			and absf(at.x) < 30.0 and at.z > FINAL_APPROACH_Z and at.z < 13.0:
		_prepare_finale()
	if finale_supplies_ready and not finale_started:
		if finale_countdown >= 0.0:
			finale_countdown = maxf(0.0, finale_countdown - delta)
			if finale_countdown == 0.0:
				_start_finale()
		elif at.y < 2.0 and absf(at.x) < 30.0 and at.z >= FINAL_WARNING_Z:
			_arm_finale()
	if _crossed_main_gate(at):
		route_marker.hide()
		for area in field_exit_markers:
			area.hide()
		for supply in supplies:
			supply.area.hide()
		level._finish("成功撤离 · 已走出正门" if level.infection < 0.0 else "感染离校 · 已走出正门")
		return
	last_position = at
	_update_objective(at)

func _update_plaza_encounter(at: Vector3) -> void:
	if not plaza_wave and _approaches_plaza(at):
		plaza_wave = true
		level.spawner.start_plaza_encounter(at)
		level._report("图书馆西侧有尸群。可以继续突围，也可以进绅远楼，从二层绕行。", 9.0)
	if direct_plaza_wave or finale_started:
		return
	if _on_direct_plaza_approach(at):
		_begin_direct_plaza(at, 1)
		return
	if is_instance_valid(level.coop_session) and Net.is_host():
		var teammates: Dictionary = level.coop_session.remote_survivors()
		for id: int in teammates:
			var position: Vector3 = teammates[id]
			if _on_direct_plaza_approach(position):
				_begin_direct_plaza(position, id)
				return


func _on_direct_plaza_approach(at: Vector3) -> bool:
	return absf(at.y) < 2.0 and SHANGDE_ARRIVAL.has_point(Vector2(at.x, at.z)) \
		and level.layout.zone_at(at) == level.layout.OUTSIDE


func _begin_direct_plaza(at: Vector3, peer: int) -> void:
	plaza_wave = true
	direct_plaza_wave = true
	level.spawner.start_direct_plaza_encounter(at, peer)
	level._report("尚德广场附近有尸群正在靠近。沿主路走，准备从正门撤离。", 7.0)


func _entered_dorm(at: Vector3) -> bool:
	if level.layout.zone_at(at) != level.layout.DORM_FLOOR_ONE:
		return false
	var offset: Vector3 = at - level.layout.dorm_start
	var side := Vector3(-level.layout.dorm_axis.z, 0, level.layout.dorm_axis.x)
	if absf(offset.dot(side)) < 1.1:
		return true
	for entry: Dictionary in dorm_entries:
		var delta: Vector3 = at - entry.point
		var forward: float = delta.dot(entry.inward)
		var lateral: Vector3 = delta.slide(Vector3.UP) - entry.inward * forward
		if forward > 0.25 and forward < 3.2 and absf(delta.y) < 0.75 \
				and lateral.length() < entry.width * 0.5 + 0.25:
			return true
	return false

func _check_field_crossing(at: Vector3) -> void:
	for area in field_exit_markers:
		if area.contains(at):
			left_track = true
			return
	for index in FieldPassages.APPROACH.size():
		var approach: Vector3 = FieldPassages.APPROACH[index]
		var exit: Vector3 = FieldPassages.EXIT[index]
		if absf(at.y - approach.y) > 1.35 or absf(at.z - approach.z) > 2.4:
			continue
		if at.x >= approach.x - 3.0 and at.x <= approach.x + 3.0:
			field_passage = index
		if field_passage == index and last_position != Vector3.INF \
				and last_position.x < exit.x and at.x >= exit.x:
			left_track = true
			return

func _prepare_finale() -> void:
	finale_supplies_ready = true
	level.spawner.prepare_gate_supplies()
	var asset := load("res://assets/campus/weapons/minigun.tscn") as PackedScene
	for point in FINAL_SUPPLIES:
		_add_supply("加特林 · 960发", point, [["minigun", 960, true]], &"final_gate", asset)
	level._report("前方备有三把加特林，每把960发。先取枪，做好准备再迎战。", 8.0)

func _arm_finale() -> void:
	if finale_started or finale_countdown >= 0.0:
		return
	finale_countdown = FINAL_PREPARATION_SECONDS
	level._report("最后一波将在6秒后到达。加特林仍可拾取，准备后向正门前进。", 6.0)

func _start_finale() -> void:
	finale_started = true
	level.spawner.start_gate_encounter(PLAZA)
	level._report("最后一波尸群正在向校门靠近，穿过正门撤离！", 8.0)

func _crossed_main_gate(at: Vector3) -> bool:
	if at.z < MAIN_GATE_OUTSIDE.z:
		return false
	# Also accept a player already in the exterior exit area, so a missed
	# update or a doorway-sized leap cannot leave the run unfinished.
	if at.z <= MAIN_GATE_OUTSIDE.z + 8.0 and absf(at.x - MAIN_GATE_OUTSIDE.x) < MAIN_GATE_HALF_WIDTH \
			and absf(at.y - MAIN_GATE_OUTSIDE.y) < 1.65:
		return true
	if last_position == Vector3.INF or last_position.z >= MAIN_GATE_OUTSIDE.z:
		return false
	var crossing := last_position.lerp(at, inverse_lerp(last_position.z, at.z, MAIN_GATE_OUTSIDE.z))
	return absf(crossing.x - MAIN_GATE_OUTSIDE.x) < MAIN_GATE_HALF_WIDTH and absf(crossing.y - MAIN_GATE_OUTSIDE.y) < 1.65

func _approaches_plaza(at: Vector3) -> bool:
	return absf(at.y) < 2.0 and LIBRARY_WEST_TRIGGER.has_point(Vector2(at.x, at.z)) \
		and level.layout.zone_at(at) == level.layout.OUTSIDE

func _add_supply(title: String, point: Vector3, grants: Array, encounter: StringName, model: PackedScene = null) -> void:
	var marker := _sign("进入黄圈 · " + title, point, Color("#ffe681"))
	var area := _make_area(point, 1.15 if encounter == &"roof" else 1.45)
	if model != null:
		var pickup := model.instantiate() as Node3D
		pickup.position.y = 0.21
		pickup.rotation.y = 0.4
		add_child(pickup)
		pickup.global_position += point
		supplies.append({"point": point, "marker": marker, "area": area, "model": pickup, "grants": grants, "encounter": encounter})
		return
	var pickup := Node3D.new()
	pickup.name = "GroundSupply"
	add_child(pickup)
	pickup.global_position = point
	if grants.size() == 1 and grants[0][2] and grants[0][0] in RANDOM_WEAPONS:
		_add_ground_weapon(pickup, grants[0][0])
	else:
		_add_ammo_box(pickup)
	supplies.append({"point": point, "marker": marker, "area": area, "model": pickup, "grants": grants,
		"encounter": encounter, "grounded": false})

func _add_ground_weapon(pickup: Node3D, id: String) -> void:
	pickup.name = "GroundWeapon_" + id
	var mesh_name: String = level.firearms.PROFILES[id].mesh
	var source: MeshInstance3D = level.firearms.rig.find_child(mesh_name, true, false)
	var gun := source.duplicate() as MeshInstance3D
	gun.name = "WeaponMesh"
	gun.transform = Transform3D.IDENTITY
	gun.visible = true
	gun.layers = 1
	gun.rotation = Vector3(0, -PI * 0.5, PI * 0.5)
	pickup.add_child(gun)
	var magazine: Node3D = level.firearms.rig.find_child(mesh_name + "_ammo", true, false)
	if magazine != null:
		var spare := magazine.duplicate() as Node3D
		gun.add_child(spare)
		spare.transform = source.global_transform.affine_inverse() * magazine.global_transform
		spare.visible = true
		if spare is MeshInstance3D:
			spare.layers = 1
	var bounds := gun.transform * gun.get_aabb()
	gun.position -= bounds.get_center()
	gun.position.y += bounds.size.y * 0.5 + 0.025
	var light := OmniLight3D.new()
	light.name = "PickupLight"
	light.position.y = 0.75
	light.light_color = Color("#ffdf9c")
	light.light_energy = 1.4
	light.omni_range = 2.4
	pickup.add_child(light)

func _add_ammo_box(pickup: Node3D) -> void:
	var box := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.46, 0.24, 0.30)
	box.mesh = mesh
	box.position.y = 0.14
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("#59846a")
	box.material_override = material
	pickup.add_child(box)

func _ground_supplies_near_player() -> void:
	var space := get_world_3d().direct_space_state
	for supply: Dictionary in supplies:
		if supply.get("grounded", true) or supply.point.distance_to(level.walker.global_position) > 40.0:
			continue
		var point: Vector3 = supply.point
		var ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.6, point - Vector3.UP * 0.6, 1)
		var floor_hit := space.intersect_ray(ray)
		if floor_hit.is_empty() or floor_hit.normal.y < 0.8:
			continue
		var grounded: Vector3 = floor_hit.position
		var standing := CapsuleShape3D.new()
		standing.height = 1.73
		standing.radius = 0.30
		var clearance := PhysicsShapeQueryParameters3D.new()
		clearance.shape = standing
		clearance.collision_mask = 1
		clearance.transform.origin = grounded + Vector3.UP * 0.89
		if not space.intersect_shape(clearance, 1).is_empty():
			continue
		supply.point = grounded
		supply.model.global_position = grounded
		supply.marker.global_position = grounded + Vector3.UP * 0.72
		supply.area.place(grounded, supply.area.radius)
		supply.grounded = true

func _make_area(point: Vector3, radius: float) -> TaskMarker:
	var area := TaskMarker.new()
	area.place(point, radius)
	add_child(area)
	return area

func _can_collect(supply: Dictionary, at: Vector3) -> bool:
	var point: Vector3 = supply.point
	return absf(point.y - at.y) <= TaskMarker.HEIGHT_TOLERANCE \
		and level.clear_line(at + Vector3.UP * 0.75, point + Vector3.UP * 0.6)

func _sign(title: String, point: Vector3, color: Color) -> Label3D:
	var marker := Label3D.new()
	marker.text = title
	marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	marker.modulate = color
	marker.outline_size = 9
	marker.pixel_size = 0.004
	marker.position = point + Vector3.UP * 0.72
	add_child(marker)
	return marker

func interact() -> bool:
	if level.round_finished:
		return false
	var at: Vector3 = level.walker.global_position
	var chosen := -1
	var nearest := 2.25
	for index in supplies.size():
		var point: Vector3 = supplies[index].point
		var distance := point.distance_to(at)
		if distance < nearest and _can_collect(supplies[index], at):
			chosen = index
			nearest = distance
	if chosen < 0:
		return false
	_collect(chosen, at)
	return true

func _collect(index: int, at: Vector3) -> void:
	var supply: Dictionary = supplies.pop_at(index)
	for grant: Array in supply.grants:
		level.firearms.grant_supply(grant[0], grant[1], grant[2])
	supply.marker.queue_free()
	supply.area.hide()
	supply.area.queue_free()
	if supply.has("model"):
		supply.model.queue_free()
	level.walker.play_hand_action(&"pickup")
	if is_instance_valid(level.coop_session):
		level.coop_session.report_supply(supply.encounter)
	match supply.encounter:
		&"roof":
			roof_count += 1
			if not roof_wave:
				roof_wave = true
				level.spawner.start_encounter(&"roof", 30, 12, top_floor_supply)
				level._report("五层走廊出现丧尸！拿上枪，沿楼梯下楼。", 6.0)
		&"field":
			field_count += 1
			if not field_wave:
				field_wave = true
				level.spawner.start_encounter(&"field", 120, 52, at)
				level._report("操场尸群正在靠过来，从标记的通道出去！", 7.0)
		&"dorm":
			level._report("各型武器弹药已补充", 3.0)
		&"final_gate":
			final_weapon_count += 1
			_arm_finale()
			level._report("加特林 +960 发 · 按 5 切换", 4.0)

func start_room_pickup_encounter(kind: StringName, at: Vector3) -> void:
	match kind:
		&"roof":
			if not roof_wave and at.distance_to(top_floor_supply) <= 9.0:
				roof_wave = true
				level.spawner.start_encounter(&"roof", 30, 12, top_floor_supply)
		&"field":
			if not field_wave and at.distance_to(FIELD) <= 19.0:
				field_wave = true
				level.spawner.start_encounter(&"field", 120, 52, at)


func _update_objective(at: Vector3) -> void:
	var target := top_floor_supply
	var radius := 0.0
	var show_field_exits := false
	if finale_started:
		target = MAIN_GATE_OUTSIDE + Vector3(0, 0, ROUTE_REACH + 0.1)
		radius = ROUTE_REACH
		mission = "尚德广场 · 最后一波已到达，穿过正门撤离"
	elif finale_supplies_ready:
		target = FINAL_SUPPLIES[1]
		if finale_countdown >= 0.0:
			mission = "最后一波 %.0f秒后到达 · 先取加特林，准备迎战" % ceilf(finale_countdown)
		else:
			mission = "准备区 · 先取加特林与960发弹药，再向正门前进"
	elif dorm_entered and not dorm_left:
		if not dorm_upper:
			target = dorm_supply
			mission = "绅远楼 · 一楼右侧有尸群，走西梯上二层"
		elif not dorm_crossed_upper:
			target = dorm_east_stairs
			radius = ROUTE_REACH
			mission = "绅远楼 · 沿二层走廊向东，从东梯下楼"
		elif not dorm_descended:
			target = dorm_east_down
			radius = ROUTE_REACH
			mission = "绅远楼 · 从东梯下到一层"
		else:
			target = dorm_exit
			radius = ROUTE_REACH
			mission = "绅远楼 · 从东端门出去"
	elif direct_plaza_wave and _on_direct_plaza_approach(at):
		target = PLAZA_PREPARATION_POINT
		radius = ROUTE_REACH
		mission = "沿主路进入尚德广场，留意远处尸群"
	elif roof_count < 1:
		mission = "致远楼 · 上西梯到最高的五层，在室内走廊取枪"
	elif field_count < 1:
		target = FIELD
		mission = "操场 · 拾取随机武器与弹药"
	elif not left_track:
		show_field_exits = true
		var exit_index := field_passage
		if exit_index < 0:
			var nearest := INF
			for index in field_exit_markers.size():
				var distance := at.distance_squared_to(field_exit_markers[index].global_position)
				if distance < nearest:
					exit_index = index
					nearest = distance
		var exit_area := field_exit_markers[exit_index]
		target = exit_area.global_position
		mission = "操场 · 从任一敞开的看台通道走出去"
	elif not plaza_wave:
		target = PLAZA_APPROACH
		radius = ROUTE_REACH
		mission = "沿操场外的路去尚德广场"
	elif not dorm_entered:
		target = dorm_start
		for entry in dorm_entries:
			var inside: Vector3 = entry.point + entry.inward * 1.55
			if at.distance_squared_to(inside) < at.distance_squared_to(target):
				target = inside
		radius = 1.0
		mission = "前方尸群密集 · 进入绅远楼西端，从二层绕行"
	elif not went_east:
		target = LIBRARY_EAST
		radius = LIBRARY_REACH
		mission = "绕过图书馆东侧，再向尚德广场前进"
	else:
		target = PLAZA_PREPARATION_POINT
		radius = ROUTE_REACH
		mission = "沿校园中轴向南，进入尚德广场"
	for area in field_exit_markers:
		area.visible = show_field_exits
	if radius > 0.0:
		route_marker.place(target, radius)
		route_marker.show()
	else:
		route_marker.hide()
	level.briefing.text = "当前目标 · %s  ·  %.0f 米" % [mission, at.distance_to(target)]
