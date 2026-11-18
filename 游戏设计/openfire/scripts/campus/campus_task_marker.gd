extends MeshInstance3D

const SURFACE := preload("res://scripts/campus/campus_task_marker.gdshader")
const HEIGHT_TOLERANCE := 0.85
const FLOOR_OFFSET := Vector3(0.0, 0.037, 0.0)

var radius := 0.0


func place(center: Vector3, reach: float) -> void:
	var plane := mesh as PlaneMesh
	if plane == null:
		plane = PlaneMesh.new()
		mesh = plane
		var surface := ShaderMaterial.new()
		surface.shader = SURFACE
		material_override = surface
		cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if reach != radius:
		radius = reach
		plane.size = Vector2.ONE * reach * 2.0
	position = center + FLOOR_OFFSET


func contains(feet: Vector3) -> bool:
	return covers(feet, global_position - FLOOR_OFFSET, radius)


static func covers(feet: Vector3, center: Vector3, reach: float) -> bool:
	var offset := feet - center
	var flat := Vector2(offset.x, offset.z)
	return absf(offset.y) <= HEIGHT_TOLERANCE and flat.length_squared() <= reach * reach
