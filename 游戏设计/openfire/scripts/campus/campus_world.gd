extends Node3D

const FieldPassages := preload("res://scripts/campus/campus_field_passages.gd")
const DormAccessRepairs := preload("res://scripts/campus/campus_dorm_access_repairs.gd")

const COLLISION_DISTANCE := 65.0
const UPDATE_INTERVAL := 0.2
const ROOM_DRAW_DISTANCE := 48.0
const ROOM_DRAW_MARGIN := 8.0

var bodies: Array[StaticBody3D] = []
var bounds: Array[AABB] = []
var update_remaining := 0.0
var collision_position := Vector3.INF
var additional_collision_positions: Callable
var last_remote_positions := PackedVector3Array()
var previous_occlusion: bool
var previous_lod_threshold: float
var previous_msaa: Viewport.MSAA
var previous_render_scale: float

@onready var walker: CharacterBody3D = $Walker
@onready var sun: DirectionalLight3D = $Sun

func _enter_tree() -> void:
	var spawn_position: Vector3 = $Spawn.position
	bodies.clear()
	bounds.clear()
	for body_node in $CampusCollision.get_children():
		var body := body_node as StaticBody3D
		if body == null:
			continue
		var box: AABB = body.get_meta("bounds")
		bodies.append(body)
		bounds.append(box)
		# Disabled bodies stay out of the physics space until they are needed.
		_set_collision_active(body, _within_collision_distance(box, spawn_position))
	collision_position = spawn_position

func _ready() -> void:
	var field_passages := FieldPassages.new()
	field_passages.name = "FieldPassages"
	add_child(field_passages)
	var dorm_access := DormAccessRepairs.new()
	dorm_access.name = "DormAccessRepairs"
	add_child(dorm_access)
	var viewport := get_viewport()
	previous_occlusion = viewport.use_occlusion_culling
	previous_lod_threshold = viewport.mesh_lod_threshold
	previous_msaa = viewport.msaa_3d
	previous_render_scale = viewport.scaling_3d_scale
	viewport.use_occlusion_culling = true
	Settings.changed.connect(_apply_campus_quality)
	_apply_campus_quality()
	for node in $CampusVisuals.find_children("*", "MeshInstance3D", true, false):
		var name_string := String(node.name)
		if name_string.begins_with("共享房间批次") or "北侧教室" in name_string:
			var mesh_node := node as MeshInstance3D
			mesh_node.visibility_range_end = ROOM_DRAW_DISTANCE
			mesh_node.visibility_range_end_margin = ROOM_DRAW_MARGIN
	refresh_collision()

func _apply_campus_quality() -> void:
	var viewport := get_viewport()
	var quality := Settings.quality
	viewport.mesh_lod_threshold = [5.0, 3.0, 2.0][quality]
	viewport.msaa_3d = Viewport.MSAA_2X if quality == 2 else Viewport.MSAA_DISABLED
	viewport.scaling_3d_scale = [0.75, 0.9, 1.0][quality]
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL if quality == 0 \
		else DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	sun.directional_shadow_split_1 = 0.24
	sun.directional_shadow_max_distance = [26.0, 44.0, 60.0][quality]

func _exit_tree() -> void:
	if not is_node_ready():
		return
	var viewport := get_viewport()
	viewport.use_occlusion_culling = previous_occlusion
	viewport.mesh_lod_threshold = previous_lod_threshold
	viewport.msaa_3d = previous_msaa
	viewport.scaling_3d_scale = previous_render_scale

func _physics_process(delta: float) -> void:
	update_remaining -= delta
	if update_remaining <= 0.0:
		update_remaining = UPDATE_INTERVAL
		refresh_collision()

func refresh_collision() -> void:
	var position := walker.global_position
	var remote_positions := PackedVector3Array()
	if additional_collision_positions.is_valid():
		remote_positions = additional_collision_positions.call()
	if position == collision_position and remote_positions == last_remote_positions:
		return
	collision_position = position
	last_remote_positions = remote_positions
	for index in bodies.size():
		var active := _within_collision_distance(bounds[index], position)
		if not active:
			for remote_position in remote_positions:
				if _within_collision_distance(bounds[index], remote_position):
					active = true
					break
		if (bodies[index].collision_layer != 0) != active:
			_set_collision_active(bodies[index], active)

func _within_collision_distance(box: AABB, position: Vector3) -> bool:
	return position.clamp(box.position, box.end).distance_squared_to(position) <= COLLISION_DISTANCE * COLLISION_DISTANCE

func _set_collision_active(body: StaticBody3D, active: bool) -> void:
	if active:
		body.collision_layer = 1
		body.process_mode = Node.PROCESS_MODE_INHERIT
	else:
		body.process_mode = Node.PROCESS_MODE_DISABLED
		body.collision_layer = 0
