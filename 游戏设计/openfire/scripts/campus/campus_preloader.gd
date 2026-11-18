extends Node

signal finished(base_scene: PackedScene)

const BASE_SCENE := "res://scenes/campus/campus.tscn"
const TASK_NAME := "CampusPrefetch"

var fraction := 0.0

func _ready() -> void:
	var err := ResourceLoader.load_threaded_request(BASE_SCENE, "PackedScene", true)
	if err != OK:
		set_process(false)
		_finish.call_deferred(null)

func _process(_delta: float) -> void:
	var progress: Array = []
	var status := ResourceLoader.load_threaded_get_status(BASE_SCENE, progress)
	if status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		if not progress.is_empty():
			fraction = float(progress[0])
		return
	var base_scene: PackedScene
	if status in [ResourceLoader.THREAD_LOAD_LOADED, ResourceLoader.THREAD_LOAD_FAILED]:
		base_scene = ResourceLoader.load_threaded_get(BASE_SCENE) as PackedScene
	_finish(base_scene)

func _finish(base_scene: PackedScene) -> void:
	set_process(false)
	get_parent().remove_child(self)
	finished.emit(base_scene)
	queue_free()
