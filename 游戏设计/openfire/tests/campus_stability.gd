extends Node

const MENU := "res://scenes/main_menu.tscn"
const CAMPUS := ["res://scenes/campus/interior.tscn", "res://scenes/campus/gate_plaza.tscn"]

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var tree := get_tree()
	reparent(tree.root)
	tree.change_scene_to_file(MENU)
	await tree.scene_changed
	var menu_rendering := _rendering_settings(tree.root)
	var warmed_nodes := 0
	var warmed_orphans := 0
	for cycle in 4:
		for path in CAMPUS:
			print("CAMPUS loading ", cycle, " ", path)
			tree.change_scene_to_file(path)
			await tree.scene_changed
			var scene := tree.current_scene
			if scene.has_node("Boundary") or not tree.root.use_occlusion_culling:
				push_error("Campus boundary or occlusion settings regressed")
				tree.quit(1)
				return
			var walker := scene.get_node("Walker") as CharacterBody3D
			for frame in 90:
				walker.rotate_y(0.025)
				await tree.process_frame
			tree.change_scene_to_file(MENU)
			await tree.scene_changed
			if _rendering_settings(tree.root) != menu_rendering:
				push_error("Campus rendering settings leaked into the main menu")
				tree.quit(1)
				return
			for frame in 4:
				await tree.process_frame
		var nodes := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
		var orphans := int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT))
		print("CAMPUS STABILITY cycle=", cycle, " memory=", OS.get_static_memory_usage(), " nodes=", nodes, " orphans=", orphans)
		if cycle == 0:
			warmed_nodes = nodes
			warmed_orphans = orphans
		elif nodes > warmed_nodes + 4 or orphans > warmed_orphans:
			push_error("Campus scene nodes survive repeated menu transitions")
			tree.quit(1)
			return
	print("CAMPUS STABILITY PASS repeated interior/exterior loading and cleanup")
	tree.quit()

func _rendering_settings(viewport: Viewport) -> Array:
	return [viewport.use_occlusion_culling, viewport.mesh_lod_threshold,
		viewport.msaa_3d, viewport.scaling_3d_scale]
