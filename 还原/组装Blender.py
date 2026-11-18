"""Fit selected objects from the gate study to the traced exterior model."""

import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "校门还原小样" / "校门与尚德广场.blend"
OUTPUT = ROOT / "成果" / os.environ.get("CAMPUS_BUILD_FOLDER", "第1轮")
PLAN = json.loads((ROOT / "总图标注.json").read_text(encoding="utf-8"))
CALIBRATION = json.loads((OUTPUT / "底图校准记录.json").read_text(encoding="utf-8"))


def ground(pixel):
    x, y = Vector(pixel) - Vector(PLAN["origin"])
    angle = math.radians(CALIBRATION["rotation_degrees"])
    scale = CALIBRATION["metres_per_pixel"]
    return Vector(((x * math.cos(angle) + y * math.sin(angle)) * scale,
                   (x * math.sin(angle) - y * math.cos(angle)) * scale))


def bounds(obj):
    points = [obj.matrix_world @ Vector(point) for point in obj.bound_box]
    return [Vector(tuple(func(point[i] for point in points) for i in range(3)))
            for func in (min, max)]


def fit(source_anchor, target_center, target_width, objects, target_depth=None):
    low, high = bounds(source_anchor)
    center = (low + high) / 2
    center.z = 0
    scale = target_width / (high - low).x
    depth_scale = scale if target_depth is None else target_depth / (high - low).y
    dest = Vector((*ground(target_center), .025))
    stretch = Matrix.Diagonal((scale, depth_scale, depth_scale, 1))
    transform = Matrix.Translation(dest - stretch.to_3x3() @ center) @ stretch
    instances = {obj: obj.matrix_world.copy() for obj in objects}
    for obj, original in instances.items():
        obj.parent = None
        obj.matrix_world = transform @ original
    return scale


def camera_at(name, eye, target, lens=37):
    camera = bpy.data.cameras.new(name)
    camera.lens = lens
    camera.clip_end = 1600
    obj = bpy.data.objects.new(name, camera)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = eye
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def compose_comparison(view_folder, entries, title_text, filename):
    reference = ROOT.parent / "数据" / "04_建模参考" / "02_八方向"
    font_path = "C:/Windows/Fonts/msyh.ttc"
    title = ImageFont.truetype(font_path, 28)
    label = ImageFont.truetype(font_path, 20)
    canvas = Image.new("RGB", (1304, 108 + 357 * math.ceil(len(entries) / 2)), "#f4f0e5")
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 15), title_text, fill="#202923", font=title)
    draw.text((18, 56), "左为全景方向参考，右为 Blender 模型。相机位置、朝向和视场为估算。",
              fill="#394639", font=label)
    for i, entry in enumerate(entries):
        scene_id = entry["id"]
        x, y = 18 + i % 2 * 646, 93 + i // 2 * 357
        draw.text((x, y), f'{scene_id}  {entry["name"]}', fill="#202923", font=label)
        photo = next(reference.glob(scene_id + "_*")) / "000.jpg"
        for j, path in enumerate((photo, view_folder / f"{scene_id}.png")):
            with Image.open(path) as image:
                canvas.paste(ImageOps.fit(image.convert("RGB"), (306, 306)), (x + j * 314, y + 34))
    canvas.save(OUTPUT / filename)


def export_zones(scene):
    folder = OUTPUT / "室外分区"
    folder.mkdir(exist_ok=True)
    groups = {
        "校门广场与主轴": ("P03", "P05", "P06", "P07", "P40", "B40", "R05", "Honor", "Garden", "Trees"),
        "教学实验与图书馆": ("B15", "B21", "B32", "B36", "B45"),
        "餐厅公寓与西门": ("B22", "B25", "B28", "P12", "P13", "P14", "R03", "R06"),
        "体育区": ("P09", "P10", "P11", "B09"),
        "共用地面与道路": ("Campus_ground", "R01", "R02", "R04"),
    }
    gate_collections = {"01 校门门楼", "02 左右门房", "04 尚德广场与喷泉"}
    for label, prefixes in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for obj in scene.objects:
            in_gate = label == "校门广场与主轴" and any(
                col.name in gate_collections for col in obj.users_collection
            )
            if obj.type in {"MESH", "CURVE", "SURFACE", "FONT"} and (
                obj.name.startswith(prefixes) or in_gate
            ):
                obj.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(folder / (label + ".glb")),
                                 export_format="GLB", use_selection=True)
    bpy.ops.object.select_all(action="DESELECT")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    bpy.ops.import_scene.gltf(filepath=str(OUTPUT / "校园室外体块.glb"))
    imported = list(scene.objects)
    source_names = ("01 校门门楼", "02 左右门房", "04 尚德广场与喷泉")
    with bpy.data.libraries.load(str(SOURCE), link=False) as (available, appended):
        appended.collections = [name for name in source_names if name in available.collections]
    collections = {collection.name: collection for collection in appended.collections}
    assert set(collections) == set(source_names), collections.keys()
    for collection in collections.values():
        scene.collection.children.link(collection)
    bpy.context.view_layer.update()

    gate = tuple(collections[source_names[0]].all_objects) + tuple(
        collections[source_names[1]].all_objects
    )
    gate_anchor = next(obj for obj in gate if obj.name == "横向石门楣")
    pool_collection = collections[source_names[2]]
    pool_parts = [obj for obj in pool_collection.all_objects
                  if any(word in obj.name for word in
                         ("水池", "水柱", "水面", "景观石", "景石", "石景"))]
    pool_anchor = next(obj for obj in pool_parts if obj.name == "水池黑石边沿")
    for obj in list(pool_collection.objects):
        if obj not in pool_parts:
            pool_collection.objects.unlink(obj)
    metres_per_pixel = CALIBRATION["metres_per_pixel"]
    gate_scale = fit(gate_anchor, [821, 521], 40 * metres_per_pixel, gate)
    pool_scale = fit(pool_anchor, [822, 471], 14 * metres_per_pixel, pool_parts,
                     target_depth=30 * metres_per_pixel)
    for obj in imported:
        if obj.name.startswith(("Gate_", "P05_pool_", "P05_water")):
            bpy.data.objects.remove(obj, do_unlink=True)
    scene["校门小样缩放"] = gate_scale
    scene["喷泉小样缩放"] = pool_scale
    scene["比例来源"] = "场景02航拍初描，105米足球场长度估算"

    site_views = [
        {"id": "09", "name": "运动场与看台", "eye": [167, 304], "target": [261, 301]},
        {"id": "07", "name": "孔德广场日晷", "eye": [402, 324], "target": [441, 306]},
        {"id": "06", "name": "樱花园", "eye": [663, 389], "target": [694, 378]},
        {"id": "11", "name": "篮球场", "eye": [355, 211], "target": [351, 144]},
    ]
    exterior_views = [
        {"id": "13", "name": "西门景观", "eye": [921, 189], "target": [923, 153]},
        {"id": "22", "name": "餐厅入口", "eye": [468, 191], "target": [469, 149]},
        {"id": "25", "name": "绅远楼", "eye": [682, 182], "target": [684, 144]},
        {"id": "28", "name": "蕙远楼", "eye": [903, 176], "target": [899, 145]},
        {"id": "32", "name": "图书馆", "eye": [816, 259], "target": [815, 213]},
        {"id": "15", "name": "志远楼", "eye": [609, 296], "target": [607, 260]},
    ] if OUTPUT.name == "第2轮" else []
    comparisons = []
    for entry in PLAN["cameras"] + site_views + exterior_views:
        eye, target = ground(entry["eye"]), ground(entry["target"])
        height = 5 if entry["id"] == "03" else 1.6
        comparisons.append(camera_at(entry["id"] + " " + entry["name"],
                                     (*eye, 1.6), (*target, height), lens=18))
    center = ground((570, 315))
    overview = camera_at("校园鸟瞰", (center.x, center.y - 220, 460),
                         (*center, 0), 32)
    overview.data.type = "ORTHO"
    overview.data.ortho_scale = 580
    scene.camera = overview
    bpy.ops.object.select_all(action="DESELECT")
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.type = "MATERIAL"
    bpy.ops.file.pack_all()
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1440, 850
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("背景")
    scene.world.use_nodes = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.52, .64, .78, 1)
    background.inputs["Strength"].default_value = .38
    sun = bpy.data.lights.new("日光", type="SUN")
    sun.energy = 2.6
    sun.angle = math.radians(12)
    sun_object = bpy.data.objects.new("日光", sun)
    scene.collection.objects.link(sun_object)
    sun_object.rotation_euler = tuple(map(math.radians, (28, -27, -23)))
    for mat in bpy.data.materials:
        if mat.use_nodes:
            shader = next((node for node in mat.node_tree.nodes
                           if node.type == "BSDF_PRINCIPLED"), None)
            if shader is not None:
                mat.diffuse_color = shader.inputs["Base Color"].default_value
    scene.render.filepath = str(OUTPUT / "校园体块鸟瞰.png")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "校园室外还原.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "校园室外还原.glb"),
                             export_format="GLB", export_cameras=False, export_lights=False)
    if exterior_views:
        export_zones(scene)
    bpy.ops.render.render(write_still=True)
    scene.render.resolution_x = scene.render.resolution_y = 780
    view_folder = OUTPUT / "沿线视角"
    view_folder.mkdir(exist_ok=True)
    for camera in comparisons:
        scene.camera = camera
        scene.render.filepath = str(view_folder / (camera.name[:2] + ".png"))
        bpy.ops.render.render(write_still=True)
    compose_comparison(view_folder, PLAN["cameras"], "首段步行路线 · 实景对照", "沿线实景对照.png")
    compose_comparison(view_folder, site_views, "体育与景观区 · 实景对照", "体育与景观实景对照.png")
    if exterior_views:
        compose_comparison(view_folder, exterior_views, "第二轮建筑与西门 · 实景对照", "楼栋及西门实景对照.png")
    print("Reused", len(gate), "gate objects and", len(pool_parts), "pool objects")


if __name__ == "__main__":
    main()
