extends RefCounted

const MERGE_SCALE := 0.25
const FLOOR_HEIGHTS := [0.48, 4.32, 8.04, 11.76, 15.48]
const FRONT_GATE := Vector3(0.0, 0.20, 5.5)
const WEST_GATE := Vector3(99.0, 0.13, -165.51)

static func point(values: Array) -> Vector3:
	return Vector3(float(values[0]), float(values[2]), -float(values[1]))

static func outward(values: Array) -> Vector3:
	return Vector3(float(values[0]), 0.0, -float(values[1])).normalized()

static func external_doors(data: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for record: Dictionary in data.doors:
		result.append({"id": record.id, "point": point(record.center), "outward": outward(record.outward),
			"width": float(record.width), "locked": bool(record.get("locked", false))})
	return result

static func classroom_doors(_data: Dictionary) -> Array[Dictionary]:
	var records: Array = JSON.parse_string(FileAccess.get_file_as_string("res://assets/campus/campus_classroom_doors.json"))
	var result: Array[Dictionary] = []
	for record: Dictionary in records:
		var center: Array = record.point
		var direction: Array = record.outward
		record.point = Vector3(float(center[0]), float(center[1]), float(center[2]))
		record.outward = Vector3(float(direction[0]), float(direction[1]), float(direction[2]))
		result.append(record)
	return result
