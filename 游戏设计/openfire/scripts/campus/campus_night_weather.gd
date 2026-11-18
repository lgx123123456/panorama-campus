extends Node3D
## Local night lighting and roof-clipped rain for the full-campus survival mode.

signal rain_changed(raining: bool)

const GRID_SIZE := 24
const CELL_SIZE := 1.8
const COLUMN_COUNT := GRID_SIZE * GRID_SIZE
const DROPS_PER_COLUMN := 3
const QUERIES_PER_TICK := 20
const RAIN_HEIGHT := 24.0

@export var dry_seconds := Vector2(60.0, 180.0)
@export var rain_seconds := Vector2(20.0, 45.0)
@export var transition_seconds := 4.0
var walker: Node3D
var rain_intensity := 0.0
var is_raining := false
var daylight := false
var seconds_remaining := 0.0
## Smoothed overhead coverage at the player's head, available to rain audio.
var shelter_amount := 0.0

var _random := RandomNumberGenerator.new()
var _environment: Environment
var _world_environment: WorldEnvironment
var _day_environment: Environment
var _day_sun_rotation := Vector3(-53.0, -35.0, 0.0)
var _day_sun_color := Color.WHITE
var _day_sun_energy := 1.02
var _day_sun_shadows := true
var _moonlight: DirectionalLight3D
var _sky_material: ShaderMaterial
var _rain_material: ShaderMaterial
var _rain: MultiMeshInstance3D
var _columns: Array[Vector2i] = []
var _next_column := 0
var _clock := 0.0
var _shelter_timer := 0.0
var _sheltered := false

func _ready() -> void:
	_random.randomize()
	seconds_remaining = _random.randf_range(dry_seconds.x, dry_seconds.y)
	_setup_night()
	_setup_rain()

func begin_rain(duration: float = -1.0) -> void:
	if daylight:
		return
	var changed := not is_raining
	is_raining = true
	seconds_remaining = duration if duration > 0.0 else _random.randf_range(rain_seconds.x, rain_seconds.y)
	if changed:
		rain_changed.emit(true)

func end_rain() -> void:
	var changed := is_raining
	is_raining = false
	seconds_remaining = _random.randf_range(dry_seconds.x, dry_seconds.y)
	if changed:
		rain_changed.emit(false)

func begin_daylight() -> void:
	if daylight:
		return
	daylight = true
	var was_raining := is_raining
	is_raining = false
	rain_intensity = 0.0
	seconds_remaining = INF
	shelter_amount = 0.0
	_rain.visible = false
	_rain_material.set_shader_parameter("rain_amount", 0.0)
	_world_environment.environment = _day_environment
	_environment = _day_environment
	_moonlight.rotation_degrees = _day_sun_rotation
	_moonlight.light_color = _day_sun_color
	_moonlight.light_energy = _day_sun_energy
	_moonlight.shadow_enabled = _day_sun_shadows
	if was_raining:
		rain_changed.emit(false)

func _process(delta: float) -> void:
	if daylight:
		return
	seconds_remaining -= delta
	if seconds_remaining <= 0.0:
		if is_raining:
			end_rain()
		else:
			begin_rain()
	var target := 1.0 if is_raining else 0.0
	var previous_intensity := rain_intensity
	rain_intensity = move_toward(rain_intensity, target, delta / maxf(transition_seconds, 0.05))
	shelter_amount = move_toward(shelter_amount, 1.0 if _sheltered else 0.0, delta * 2.0)
	if rain_intensity > 0.001:
		_clock = fmod(_clock + delta, 3600.0)
		_rain_material.set_shader_parameter("weather_time", _clock)
	if previous_intensity != rain_intensity:
		_rain.visible = rain_intensity > 0.001
		_rain_material.set_shader_parameter("rain_amount", rain_intensity)
		_sky_material.set_shader_parameter("rain_amount", rain_intensity)
		_environment.ambient_light_energy = lerpf(0.47, 0.39, rain_intensity)
		_moonlight.light_energy = lerpf(0.48, 0.27, rain_intensity)

func _physics_process(delta: float) -> void:
	if daylight or not is_instance_valid(walker):
		return
	_shelter_timer -= delta
	if _shelter_timer <= 0.0:
		_shelter_timer = 0.25
		var head := walker.global_position + Vector3.UP * 1.6
		var query := PhysicsRayQueryParameters3D.create(head, head + Vector3.UP * 160.0, 1)
		query.hit_back_faces = true
		_sheltered = not get_world_3d().direct_space_state.intersect_ray(query).is_empty()
	if not is_raining and rain_intensity <= 0.001:
		return
	# Fixed columns persist in world space. Refreshing only a bounded batch keeps
	# roof queries independent of rain density and avoids a moving rain volume.
	var center := Vector2i(floori(walker.global_position.x / CELL_SIZE), floori(walker.global_position.z / CELL_SIZE))
	var moved_columns := false
	for step in QUERIES_PER_TICK:
		var index := _next_column
		_next_column = (_next_column + 1) % COLUMN_COUNT
		var slot := Vector2i(index % GRID_SIZE, index / GRID_SIZE)
		var cell := Vector2i(
			center.x - GRID_SIZE / 2 + posmod(slot.x - center.x + GRID_SIZE / 2, GRID_SIZE),
			center.y - GRID_SIZE / 2 + posmod(slot.y - center.y + GRID_SIZE / 2, GRID_SIZE))
		if _columns[index] != cell:
			_update_column(index, cell)
			moved_columns = true
	if moved_columns:
		var radius := CELL_SIZE * (GRID_SIZE + 2)
		_rain.custom_aabb = AABB(walker.global_position - Vector3(radius, 190.0, radius),
			Vector3(radius * 2, 380.0, radius * 2))

func _update_column(index: int, cell: Vector2i) -> void:
	_columns[index] = cell
	# Stable jitter breaks the visible grid while every drop in the column shares
	# the exact ray-tested horizontal coordinate.
	var hash_value := absi(cell.x * 73856093 ^ cell.y * 19349663)
	var x := (float(cell.x) + 0.15 + float(hash_value % 701) / 1000.0) * CELL_SIZE
	var z := (float(cell.y) + 0.15 + float((hash_value / 701) % 701) / 1000.0) * CELL_SIZE
	var roof := surface_height_at(Vector2(x, z))
	for drop in DROPS_PER_COLUMN:
		var instance := index * DROPS_PER_COLUMN + drop
		_rain.multimesh.set_instance_transform(instance, Transform3D(Basis.IDENTITY, Vector3(x, roof, z)))
		_rain.multimesh.set_instance_custom_data(instance,
			Color(RAIN_HEIGHT, float(drop) / DROPS_PER_COLUMN + float(hash_value % 97) / 291.0, 0.7 + float(hash_value % 31) / 100.0, 1.0))

## Topmost world collision at this exact x/z. Rain stops above roofs and floors.
func surface_height_at(point: Vector2) -> float:
	var ray := PhysicsRayQueryParameters3D.create(Vector3(point.x, 180.0, point.y), Vector3(point.x, -30.0, point.y), 1)
	ray.hit_back_faces = true
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	return float(hit.position.y) + 0.06 if not hit.is_empty() else -0.1

func _setup_night() -> void:
	var campus := get_parent().get_parent()
	var world := campus.get_node_or_null("WorldEnvironment") as WorldEnvironment
	if world:
		_day_environment = world.environment
		_environment = world.environment.duplicate() if world.environment else Environment.new()
		world.environment = _environment
	else:
		world = WorldEnvironment.new()
		_environment = Environment.new()
		world.environment = _environment
		add_child(world)
	_world_environment = world
	if _day_environment == null:
		_day_environment = Environment.new()
		_day_environment.background_mode = Environment.BG_SKY
		_day_environment.sky = Sky.new()
		_day_environment.sky.sky_material = ProceduralSkyMaterial.new()
		_day_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		_day_environment.ambient_light_color = Color(0.83, 0.90, 1.0)
		_day_environment.ambient_light_energy = 0.58
	_environment.background_mode = Environment.BG_SKY
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_environment.ambient_light_color = Color(0.51, 0.61, 0.84)
	_environment.ambient_light_energy = 0.47
	_environment.ambient_light_sky_contribution = 0.0
	_environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	_environment.fog_enabled = false
	var sky := Sky.new()
	_sky_material = ShaderMaterial.new()
	var sky_shader := Shader.new()
	sky_shader.code = """shader_type sky;
uniform float rain_amount = 0.0;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
void sky() {
	vec3 direction = normalize(EYEDIR);
	float elevation = max(direction.y, 0.0);
	vec3 color = mix(vec3(0.038,0.052,0.094), vec3(0.005,0.009,0.025), sqrt(elevation));
	vec2 p = SKY_COORDS * vec2(650.0,325.0);
	vec2 cell = floor(p);
	float star = 1.0-smoothstep(0.025,0.11,length(fract(p)-vec2(hash(cell),hash(cell+17.0))));
	star *= step(0.986,hash(cell+7.0)) * smoothstep(0.03,0.3,elevation);
	vec3 moon_direction = normalize(vec3(-0.4,0.63,-0.66));
	float moon_distance = length(direction-moon_direction);
	float moon = 1.0-smoothstep(0.021,0.024,moon_distance);
	float glow = exp(-moon_distance*25.0)*0.08;
	color += (vec3(star*0.8)+vec3(0.64,0.73,0.9)*(moon*1.7+glow))*(1.0-rain_amount*0.92);
	color = mix(color, vec3(0.023,0.031,0.052), rain_amount*0.67);
	COLOR = color;
}"""
	_sky_material.shader = sky_shader
	sky.sky_material = _sky_material
	_environment.sky = sky
	_moonlight = campus.get_node_or_null("Sun") as DirectionalLight3D
	if _moonlight:
		_day_sun_rotation = _moonlight.rotation_degrees
		_day_sun_color = _moonlight.light_color
		_day_sun_energy = _moonlight.light_energy
		_day_sun_shadows = _moonlight.shadow_enabled
	else:
		_moonlight = DirectionalLight3D.new()
		add_child(_moonlight)
	_moonlight.rotation_degrees = Vector3(-42.0, -32.0, 0.0)
	_moonlight.light_color = Color(0.60, 0.72, 1.0)
	_moonlight.light_energy = 0.48
	_moonlight.shadow_enabled = true

func _setup_rain() -> void:
	_rain = MultiMeshInstance3D.new()
	_rain.name = "RoofClippedRain"
	_rain.visible = false
	_rain.top_level = true
	_rain.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_rain)
	_rain.global_transform = Transform3D.IDENTITY
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for turn in 2:
		var right := Vector3.RIGHT if turn == 0 else Vector3.BACK
		for corner in [Vector2(-1,-1),Vector2(1,-1),Vector2(1,1),Vector2(-1,-1),Vector2(1,1),Vector2(-1,1)]:
			mesh.surface_add_vertex(right * corner.x * 0.013 + Vector3.UP * corner.y * 0.23)
	mesh.surface_end()
	var instances := MultiMesh.new()
	instances.transform_format = MultiMesh.TRANSFORM_3D
	instances.use_custom_data = true
	instances.mesh = mesh
	instances.instance_count = COLUMN_COUNT * DROPS_PER_COLUMN
	_rain.multimesh = instances
	_columns.resize(COLUMN_COUNT)
	_columns.fill(Vector2i(2147483647,2147483647))
	# Hide unsampled instances until their roof height is known.
	for index in instances.instance_count:
		instances.set_instance_transform(index, Transform3D(Basis.IDENTITY, Vector3(0,-1000,0)))
	_rain_material = ShaderMaterial.new()
	var shader := Shader.new()
	shader.code = """shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;
uniform float rain_amount = 0.0;
uniform float weather_time = 0.0;
varying float brightness;
void vertex() {
	float height = max(INSTANCE_CUSTOM.r, 0.5);
	VERTEX.y += mod(INSTANCE_CUSTOM.g*height-weather_time*19.0,height)+0.3;
	brightness = INSTANCE_CUSTOM.b;
}
void fragment() {
	ALBEDO = vec3(0.54,0.66,0.84);
	ALPHA = rain_amount*brightness*0.43;
}"""
	_rain_material.shader = shader
	_rain.material_override = _rain_material
