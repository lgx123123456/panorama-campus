"""Connect the boys' lobby to the stairwell confirmed by the user in scene 26."""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector
from PIL import Image

import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
import 教室与男女生公寓室内 as interior
from 校园透明玻璃 import prepare_web_glass


SOURCE = doors.ROOT / "成果/教学楼东梯归位/校园_教学楼东梯归位.blend"
OUT = doors.ROOT / "成果/公寓楼梯门厅归位"
STEM = "校园_公寓大厅右侧楼梯"
BID = "B25"


def current_frame():
    rotation = Matrix.Rotation(math.radians(preview.CAL["rotation_degrees"]), 4, "Z")
    correction = (Matrix.Translation(doors.world((685, 149))) @ rotation
                  @ Matrix.Diagonal((.92, .74, 1, 1)) @ rotation.inverted()
                  @ Matrix.Translation(-doors.world((672.5, 142.5))))
    return correction @ interior.Frame(BID, True).matrix


def rebuild(scene):
    transform = current_frame()
    inverse = transform.inverted()
    original = json.loads((interior.OUT / "定位与来源.json").read_text(encoding="utf8"))["楼栋"][BID]
    parent = bpy.data.collections[BID + " 楼道、大厅和交通构件"]
    for obj in tuple(parent.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # Replace the estimated rooms occupying the confirmed circulation space.
    removed = []
    template = bpy.data.objects[BID + " 01-N01 宿舍样板"]
    for obj in tuple(scene.objects):
        if not obj.name.startswith(BID + " ") or "宿舍样板" not in obj.name:
            continue
        local = inverse @ obj.matrix_world.translation
        if abs(local.x + 7.89) < .01 and any(abs(local.y-y) < .01 for y in (6.5, 9.75)):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

    cuts = set()
    planting = bpy.data.collections["西门沿线 · 行道树冠、绿篱和宿舍花树"]
    foliage = set(planting.all_objects)

    def cut(x0, x1, y0, y1, z0, z1):
        # Keep dimensions in the already corrected building frame.
        doorway = Matrix(((1, 0, 0, (x0+x1)/2), (0, 1, 0, y1),
                          (0, 0, 1, z0-.02), (0, 0, 0, 1)))
        cuts.update(doors.cut_portal(scene, transform @ doorway, x1-x0,
                                    z1-z0+.02, BID, depth=y1-y0, outside=0))

    levels = interior.FLOOR_Z
    stair_origin = transform @ Vector((-2.40, 9.70, 0))
    stair_frame = (Matrix.Translation(stair_origin) @ Matrix.Rotation(math.pi/4, 4, "Z")
                   @ Matrix.Diagonal((.82, .82, 1, 1)))
    # Remove legacy solid surfaces through the new open shaft and its approaches.
    shaft = stair_frame @ interior.translate(0, 5.2, levels[0]-.02)
    cuts.update(doors.cut_portal(scene, shaft, 2.94, 21.2-levels[0], BID,
                                depth=6.85, outside=0, extra_objects=foliage))
    for z in levels:
        cut(-10.70, -.12, 3.30, 5.50, z, z+2.58)
        cut(-1.75, -.12, 5.50, 10.90, z, z+2.58)
    # The corrected building footprint overlaps the old street-tree canopy.
    # Clip vegetation only inside the confirmed circulation volumes.
    for x0, x1, y0, y1 in ((-10.70, -.12, 3.20, 5.60), (-1.75, -.12, 5.50, 10.90)):
        doorway = Matrix(((1, 0, 0, (x0+x1)/2), (0, 1, 0, y1),
                          (0, 0, 1, levels[0]-.02), (0, 0, 0, 1)))
        cuts.update(doors.cut_portal(scene, transform @ doorway, x1-x0, 21.2-levels[0],
                                    "楼梯内侵入树冠", depth=y1-y0, outside=0, extra_objects=foliage))
    mats = {key: bpy.data.materials["校园室内 · " + key] for key in
            ("plaster", "ceiling", "base", "silver", "metal", "lamp", "grid",
             "blue", "dark", "plastic", "wood", "paper", "plant", "marble")}
    mats.update(hall_floor=bpy.data.materials["公寓灰色地砖"],
                wall_tile=bpy.data.materials["大厅米色墙砖"],
                **{"26": bpy.data.materials["公寓大厅实拍横幅26"],
                   "notice26": bpy.data.materials["公寓大厅实拍卡片26"]})
    mesh = interior.new_mesh(scene, parent, mats)
    b = mesh.box
    slab = interior.slab
    north, south, center = -10.61, -7.89, -9.25
    near, end = original["走廊范围"]
    positions = original["房间轴线"]
    routes, joins = [], []
    stair_root = interior.collection(BID + " 公寓右侧楼梯 西北向梯井", parent)
    flights = interior.new_mesh(scene, stair_root, mats)

    def point(x, y, z):
        return list(transform @ Vector((x, y, z)))

    def stair_point(x, y, z):
        return list(stair_frame @ Vector((x, y, z)))

    for floor, z in enumerate(levels):
        mesh.section(f"{BID} 公寓右侧楼梯 {floor+1:02d}F 楼道和前室")
        ranges = ((near, -3.30), (3.30, end)) if floor == 0 else ((near, end),)
        for y0, y1 in ranges:
            interior.corridor_floor(mesh, "hall_floor", north, south, y0, y1, z, 2.56)
        for side, axis in ((-1, positions["北"]), (1, positions["南"])):
            x = center + side * interior.HALL_HALF
            room_axes = [y for y in axis if side < 0 or y not in (6.5, 9.75)]
            openings = [(y-interior.DORM_WIDTH/2+.075, y+interior.DORM_WIDTH/2-.075)
                        for y in room_axes]
            openings.append((-4.80, 4.80))
            cursor = near
            for lo, hi in sorted(openings):
                if lo > cursor:
                    interior.wall(b, "plaster", x, cursor, lo, z, 2.63)
                    interior.wall(b, "base", x-side*.077, cursor, lo, z, .095, .025)
                cursor = max(cursor, hi)
            interior.wall(b, "plaster", x, cursor, end, z, 2.63)
        for y in (near, end):
            interior.endwall(b, "plaster", y, north, south, z, 2.63)
        # The front wall hides the stair flights. The side opening leads to their landing.
        slab(b, "右侧墙后横向通道", "hall_floor", north, -.12, 3.30, 5.50, z)
        slab(b, "右侧楼梯前室顶棚", "ceiling", north, -.12, 3.30, 5.50, z+2.64, .08)
        slab(b, "西北向梯井侧通道", "hall_floor", -1.75, -.12, 5.50, 10.90, z)
        slab(b, "梯井侧通道顶棚", "ceiling", -1.75, -.12, 5.50, 10.90, z+2.64, .08)
        if floor == 0:
            slab(b, "左侧绕过正面宿舍的通道", "hall_floor", north, -5.50, -4.80, -3.30, z)
        b("右侧前室灯", "lamp", -6.3, 4.1, z+2.55, .32, 1.15, .045)
        joins.append(point(center, 4.10, z))
        flights.section(f"{BID} 西北向楼梯 {floor+1:02d}F 前平台")
        slab(flights.box, "西北向楼梯层间前平台", "hall_floor", -1.40, 1.40, -1.60, .50, z)
        if floor < len(levels)-1:
            rise = levels[floor+1]-z
            flights.section(f"{BID} 西北向楼梯 {floor+1:02d}F 至 {floor+2:02d}F 双跑梯")
            interior.stair(flights, 0, 0, z, rise)
            depth = .280 if rise > 3 else .268
            mid = .5+math.ceil(rise/.34)*depth+.60
            route = ((-.62, -1.55, z), (-.62, .38, z),
                     (-.62, mid, z+rise/2), (.62, mid, z+rise/2),
                     (.62, .38, z+rise), (.62, -.80, z+rise), (-.62, -1.55, z+rise))
            routes.append({"from_floor": floor+1, "to_floor": floor+2,
                           "points": [stair_point(*p) for p in route]})

    mesh.section(BID + " 公寓右侧楼梯 首层挑空大厅")
    interior.lobby(mesh, south, levels[0], "26")
    # The two real dormitory fronts replace the old central corridor opening.
    del mesh.groups["楼道纵墙"]
    b("正面宿舍上方挑台封墙", "wall_tile", south, 0, 3.72, .14, 6.50, 1.04)
    mesh.finish()
    interior.move_collection(parent, transform)
    flights.section(BID + " 公寓右侧楼梯 西北向梯井围护")
    for x in (-1.47, 1.47):
        flights.box("西北向梯井侧墙", "wall_tile", x, 2.80, 10.86, .14, 4.60, 20.58)
    flights.box("西北向梯井后墙", "wall_tile", 0, 5.10, 10.86, 3.08, .14, 20.58)
    slab(flights.box, "西北向梯井顶板", "ceiling", -1.54, 1.54, .50, 5.17, 21.15)
    flights.finish()
    interior.move_collection(stair_root, stair_frame)
    # Open the right side wall while retaining the wall that occludes the stairs in scene 26.
    cut(-7.76, -5.45, 3.50, 3.85, levels[0]+.006, levels[0]+2.54)
    cut(-7.76, -5.45, -3.85, -3.50, levels[0]+.006, levels[0]+2.54)
    # Reuse complete, editable furnished dormitory meshes for the two lobby-facing rooms.
    dorm_root = next(c for c in bpy.data.collections if c.name.startswith(BID+" 绅远楼") and parent.name in c.children)
    ground = next(c for c in dorm_root.children if c.name.startswith("01F 宿舍"))
    for index, y in enumerate((-1.625, 1.625), 1):
        obj = bpy.data.objects.new(f"{BID} 大厅正面宿舍 {index}", template.data)
        ground.objects.link(obj)
        obj.matrix_world = transform @ interior.translate(south, y, levels[0]) @ interior.rotation(math.pi/2)

    # The management notice between the doors uses the same source photograph.
    texture = OUT / "大厅两门之间公示板.png"
    with Image.open(interior.photo("26")) as source:
        source.crop((550, 595, 844, 820)).save(texture)
    notice = interior.material("男公寓大厅正面实拍公示板", (.75, .71, .58), .6)
    node = notice.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(texture))
    notice.node_tree.links.new(node.outputs["Color"], notice.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    mats["notice"] = notice
    detail = interior.new_mesh(scene, parent, mats)
    detail.panel_group = BID + " 公寓右侧楼梯 正面两门公示板"
    detail.panel("两间宿舍之间的管理公示板", "notice", (south+.015, 0, 2.12),
                 (0, 1, 0), (0, 0, 1), 1.98, 1.95)
    # panel() creates its mesh immediately, so transform only this new group.
    interior.move_collection(bpy.data.collections[detail.panel_group], transform)
    for obj in parent.all_objects:
        obj.name = BID + " 公寓右侧楼梯 " + obj.name
        if obj.type == "MESH" and len(obj.data.uv_layers) < 2:
            obj.data.uv_layers.new(name="WalkableCollision")
    return {"building": BID, "levels": list(levels), "routes": routes, "corridor_points": joins,
            "corridor_paths": [[stair_point(-.62, -1.55, z), point(-.80, 4.10, z),
                                point(center, 4.10, z)] for z in levels],
            "lobby_route": [point(-.60, 0, levels[0]), point(-6.40, 0, levels[0]),
                            point(-6.40, 4.10, levels[0]), point(-.80, 4.10, levels[0]),
                            stair_point(-.62, -1.55, levels[0])],
            "removed_estimated_rooms": removed, "added_lobby_rooms": 2,
            "cut_objects": sorted(cuts), "first_flight_direction": [-.70710678, .70710678, 0],
            "stair_frame": [list(row) for row in stair_frame],
            "basis": "用户确认26站男生公寓进门正面两间宿舍，右侧宿舍再向右一段的墙后为楼梯，2026-11-16补充首跑上楼朝西北。按此关系连接右侧前室、双跑梯和现有各层楼道。梯段尺寸、墙后距离沿现有层高及楼栋比例估排；移出梯井内原估排宿舍，正面两间采用既有完整宿舍样板。"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    payload = json.loads((SOURCE.parent / "楼门与公寓校正.json").read_text(encoding="utf8"))
    payload["dorm_lobby_stairs"] = rebuild(bpy.context.scene)
    (OUT / "楼门与公寓校正.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / (STEM + ".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT / (STEM + ".glb"))
    preview.OUT = OUT
    preview.publish_preview(bpy.context.scene)


if __name__ == "__main__":
    main()
