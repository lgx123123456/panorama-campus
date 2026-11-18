"""Update the editable campus and its game assets from the latest master."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from shapely.geometry import Polygon, box

import 地面补铺与预览优化 as preview
from 剩余楼栋与校园景观 import Planting, material, world
from 地面街道实景细化 import Ground
from 校园透明玻璃 import prepare_web_glass
from 组装Blender import PLAN


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/宿舍三梯厕所与教师办公室"
OUT = ROOT / "成果/楼门封闭与广场球台"
STEM = "校园_楼门封闭与广场球台"
LOCKED_BUILDINGS = {"B22", "B36", "B40W", "B40E", "B45"}
TABLE_GROUP = "蓝面红架室外乒乓球台"
TABLES = (
    (45.0, 318.0), (44.5, 331.0), (44.3, 344.0), (44.1, 356.5),
    (43.8, 369.0), (43.6, 381.8), (43.2, 394.6), (43.0, 407.1),
    (42.8, 419.7), (42.5, 432.3),
)
GARDENS = (
    ("西侧宣传栏后", [(751, 451), (772, 451), (776, 461), (773, 475), (762, 475), (751, 466)],
     [(756, 456, 5.6, "green"), (766, 459, 6.8, "conifer"), (768, 470, 4.6, "green")]),
    ("东侧宣传栏后", [(880, 451), (896, 451), (896, 469), (884, 470), (879, 462)],
     [(885, 455, 6.9, "conifer"), (892, 461, 5.4, "green")]),
    ("东侧南段种植岛", [(880, 476), (892, 475), (903, 481), (896, 489), (882, 488)],
     [(891, 482, 4.5, "green")]),
)


def keep_mesh_names(objects):
    # Retain individual names for inspection and for collision material filtering.
    for obj in objects:
        if obj.type == "MESH":
            while len(obj.data.uv_layers) < 2:
                obj.data.uv_layers.new(name="DetailCoordinates")


def close_doors(payload):
    locked = []
    for record in payload["doors"]:
        if record["building"] not in LOCKED_BUILDINGS:
            continue
        for leaf in record["pivots"]:
            pivot = bpy.data.objects[leaf["name"]]
            pivot.matrix_world = pivot.matrix_world @ Matrix.Rotation(leaf["side"] * math.pi / 2, 4, "Z")
        record.update(locked=True, asset_closed=True)
        locked.append(record["id"])
    assert len(locked) == 6, locked
    return locked


def reset_tables(scene):
    old_groups = [group for group in bpy.data.collections if group.name.startswith(TABLE_GROUP)]
    template = [(obj.name, obj.data, obj.matrix_world.copy()) for obj in bpy.data.collections[TABLE_GROUP].objects]
    reference = world((50, 340))
    rotation = Matrix.Rotation(math.pi / 2, 4, "Z")
    for index, pixel in enumerate(TABLES, 1):
        group = bpy.data.collections.new(f"操场西侧乒乓球台 {index:02d}")
        scene.collection.children.link(group)
        target = world(pixel) + Vector((0, 0, -.047))
        transform = Matrix.Translation(target) @ rotation @ Matrix.Translation(-reference)
        for name, mesh, matrix in template:
            detail = name.removeprefix("B场地 ")
            obj = bpy.data.objects.new(f"乒乓球台{index:02d} {detail}", mesh.copy())
            group.objects.link(obj)
            obj.matrix_world = transform @ matrix
        keep_mesh_names(group.objects)
    for group in old_groups:
        for obj in list(group.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(group)

    old_paving = bpy.data.objects["西侧乒乓区混凝土带"]
    bpy.data.objects.remove(old_paving, do_unlink=True)
    paving = Ground(scene, {
        "concrete": material("乒乓球区暖灰混凝土", (.48, .444, .381), .92),
        "joint": material("乒乓球区混凝土缩缝", (.31, .289, .25), .95),
    })
    paving.region("操场西侧球台带")
    paving.surface("球台混凝土铺地", "concrete", box(33, 309, 60, 452), .112)
    for y in range(317, 452, 9):
        paving.line("球台铺地缩缝", "joint", (33, y), (60, y), .014, .113)
    paving.build()
    keep_mesh_names(paving.zone.objects)

    offset = world((33, 322)) - world((42, 322))
    fence = bpy.data.collections["运动场西侧围网"]
    for obj in fence.objects:
        obj.location += offset
    keep_mesh_names(fence.objects)


def conifer(plant, pixel, height):
    ground = world(pixel) + Vector((0, 0, .19))
    plant.limb("广场花园常绿树干", "bark", ground, ground + Vector((0, 0, height)), .15, .028)
    for tier in range(7):
        z = height * (.28 + tier * .105)
        radius = height * (.28 - tier * .036)
        origin = ground + Vector((0, 0, z))
        for branch in range(8):
            angle = branch * math.tau / 8 + tier * .44
            reach = radius * plant.rng.uniform(.76, 1.12)
            tip = origin + Vector((math.cos(angle) * reach, math.sin(angle) * reach, -.18))
            plant.limb("常绿细枝", "bark", origin, tip, .027, .007)
            for fraction in (.40, .68, .92):
                center = origin.lerp(tip, fraction)
                plant.crown("常绿叶冠", "conifer", center, radius * .27, radius * .23, .24)


def flower(plant, pixel, color):
    base = world(pixel) + Vector((0, 0, .215))
    height = plant.rng.uniform(.20, .43)
    bloom = base + Vector((0, 0, height))
    plant.limb("花丛茎叶", "flower_leaf", base, bloom, .014, .009)
    for side in (-1, 1):
        leaf = base + Vector((side * .055, side * .04, height * .45))
        plant.crown("花丛茎叶", "flower_leaf", leaf, .09, .035, .02)
    for index in range(5):
        angle = index * math.tau / 5
        petal = bloom + Vector((.044 * math.cos(angle), .044 * math.sin(angle), .012))
        plant.crown("花瓣", color, petal, .043, .043, .022)
    plant.crown("花瓣中心", "flower_center", bloom + Vector((0, 0, .025)), .038, .038, .021)


def add_gardens(scene):
    ground = Ground(scene, {
        "garden_soil": material("尚德花园表土", (.105, .077, .043), .95),
        "garden_edge": material("尚德花园浅灰收边", (.29, .29, .27), .89),
    })
    for label, outline, trees in GARDENS:
        bed = Polygon(outline)
        ground.region(f"尚德广场花园 · {label}")
        ground.surface("种植岛表土", "garden_soil", bed, .124)
        ground.raised("种植岛浅灰收边", "garden_edge", bed.difference(bed.buffer(-.42)), .106, .191)

        plant = Planting(scene)
        plant.group.name = f"尚德广场花园 · {label}乔灌花卉"
        plant.rng.seed(sum(outline[0]))
        plant.palette.update({
            "conifer": material("尚德常绿叶冠", (.032, .105, .045), .92),
            "flower_leaf": material("尚德花瓣配叶", (.072, .21, .026), .86),
            "rose": material("尚德花瓣粉红", (.69, .08, .18), .64),
            "cream": material("尚德花瓣浅白", (.87, .76, .61), .67),
            "flower_center": material("尚德花瓣金黄花心", (.92, .61, .08), .76),
        })
        for x, y, height, kind in trees:
            if kind == "conifer":
                conifer(plant, (x, y), height)
            else:
                plant.tree((x, y), height, kind)
        edge = bed.buffer(-1.05).exterior
        for index in range(math.floor(edge.length / 2.3)):
            x, y = edge.interpolate(index * 2.3).coords[0]
            center = world((x, y)) + Vector((0, 0, .29))
            plant.crown("花坛修剪绿篱", "deep", center, .47, .43, .35)
        for index in range(math.floor(edge.length / 3.1)):
            x, y = edge.interpolate(index * 3.1).coords[0]
            for dx, dy in ((-.36, -.22), (.35, .29), (-.13, .42)):
                flower(plant, (x + dx, y + dy), "cream" if index % 3 == 0 else "rose")
        plant.finish()
        keep_mesh_names(plant.group.objects)
    ground.build()
    for zone, _, _ in ground.batches:
        keep_mesh_names(zone.objects)


def main():
    model = SOURCE / "校园_宿舍三梯厕所与教师办公室.blend"
    bpy.ops.wm.open_mainfile(filepath=str(model), load_ui=False)
    scene = bpy.context.scene
    payload = json.loads((SOURCE / "楼门与公寓校正.json").read_text(encoding="utf8"))
    locked = close_doors(payload)
    reset_tables(scene)
    add_gardens(scene)
    payload["source"] = str(OUT / f"{STEM}.blend")
    payload["closed_buildings"] = [
        {
            "id": building["id"],
            "outline": [list(world(pixel))[:2] for pixel in
                        Polygon(building["outline"]).buffer(-3.5, join_style=2).convex_hull.exterior.coords[:-1]],
            "height": building["height"],
        }
        for building in PLAN["buildings"] if building["id"] in LOCKED_BUILDINGS
    ]
    payload["outdoor_update"] = {
        "locked_doors": locked,
        "administration_basis": "按现有总图暂将知远楼B45对应行政楼，待用户核实。",
        "table_centers_aerial_px": TABLES,
        "table_basis": "02号航拍重投影可辨10张桌面，10/000、090、180核对桌面朝向、颜色和红色支架；球台中心按像素估读。",
        "gardens_aerial_px": GARDENS,
        "garden_basis": "02号航拍重投影描种植区，05/090、270核对宣传栏后树带和常绿树形；具体花种与株位按种植岛补配。",
    }
    bpy.context.view_layer.update()
    (OUT / "楼门与公寓校正.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{STEM}.blend"))
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT / f"{STEM}.glb")
    preview.OUT = OUT
    preview.publish_preview(scene)


if __name__ == "__main__":
    main()
