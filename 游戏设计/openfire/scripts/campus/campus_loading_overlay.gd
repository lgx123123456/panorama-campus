extends CanvasLayer

const FRAME_BUDGET_USEC := 32000
const SETTLE_LIMIT_USEC := 650000

@onready var status: Label = %Status
@onready var progress: ProgressBar = %Progress

func show_resource_progress(fraction: float) -> void:
	progress.value = fraction * 100.0

func show_stage(message: String) -> void:
	status.text = message
	progress.indeterminate = true

func warm_spawn() -> void:
	var viewport := get_viewport()
	var camera := viewport.get_camera_3d()
	var walker := get_tree().current_scene.get_node_or_null("Walker")
	if camera == null or walker == null:
		queue_free()
		return

	var captured: bool = walker.mouse_captured
	var processes_input: bool = walker.is_processing_input()
	var processes_unhandled: bool = walker.is_processing_unhandled_input()
	walker._capture_mouse(false)
	walker.set_process_input(false)
	walker.set_process_unhandled_input(false)
	show_stage("正在预绘出生点周围…")

	# Use the real camera and output settings. The canvas covers the warm-up views.
	var spawn_yaw := camera.rotation.y
	for turn: float in [0.0, -PI / 2.0, PI / 2.0, PI]:
		camera.rotation.y = spawn_yaw + turn
		await RenderingServer.frame_post_draw
	camera.rotation.y = spawn_yaw

	var previous := Time.get_ticks_usec()
	var deadline := previous + SETTLE_LIMIT_USEC
	var stable_frames := 0
	while stable_frames < 3:
		await RenderingServer.frame_post_draw
		var now := Time.get_ticks_usec()
		stable_frames = stable_frames + 1 if now - previous <= FRAME_BUDGET_USEC else 0
		if now >= deadline:
			break
		previous = now

	walker.set_process_input(processes_input)
	walker.set_process_unhandled_input(processes_unhandled)
	walker._capture_mouse(captured)
	queue_free()
