extends RefCounted

const Data = preload("res://scripts/campus/campus_hitbox_data.gd")
const BROAD_RADIUS := 1.4

const DAMAGE_SCALE := {
	&"胸部": 1.0,
	&"腹部": 0.85,
	&"手臂": 0.60,
	&"腿部": 0.55,
}

static func collect(zombies: Array, origin: Vector3, forward: Vector3,
		max_distance: float, spread: float) -> Array[Dictionary]:
	var candidates: Array[Dictionary] = []
	for zombie in zombies:
		if not is_instance_valid(zombie) or zombie.defeated:
			continue
		var center: Vector3 = zombie.global_position + Vector3.UP
		var offset := center - origin
		var along := offset.dot(forward)
		var radius := BROAD_RADIUS + maxf(0.0, along) * spread
		if along < -BROAD_RADIUS or along > max_distance + BROAD_RADIUS \
				or (offset - forward * along).length_squared() > radius * radius:
			continue
		var skeleton: Skeleton3D = zombie.look.skeleton
		var regions: Array[Dictionary] = []
		var world := skeleton.global_transform
		for spec: Array in Data.VOLUMES[zombie.appearance_identity]:
			var bone := skeleton.find_bone(spec[0])
			if bone >= 0:
				var transform := world * skeleton.get_bone_global_pose(bone)
				regions.append({"inverse": transform.affine_inverse(), "bounds": spec[2], "region": spec[1]})
		candidates.append({"target": zombie, "center": center, "regions": regions})
	return candidates

static func intersect(from: Vector3, to: Vector3, candidates: Array[Dictionary]) -> Dictionary:
	var nearest := from.distance_squared_to(to)
	var hit := {}
	for candidate: Dictionary in candidates:
		var center: Vector3 = candidate.center
		var closest := Geometry3D.get_closest_point_to_segment(center, from, to)
		if closest.distance_squared_to(center) > BROAD_RADIUS * BROAD_RADIUS:
			continue
		for region: Dictionary in candidate.regions:
			var inverse: Transform3D = region.inverse
			var bounds: AABB = region.bounds
			var local_hit: Variant = bounds.intersects_segment(inverse * from, inverse * to)
			if local_hit == null:
				continue
			var position := inverse.affine_inverse() * (local_hit as Vector3)
			var distance := from.distance_squared_to(position)
			if distance < nearest:
				nearest = distance
				hit = {"target": candidate.target, "position": position, "region": region.region}
	return hit
