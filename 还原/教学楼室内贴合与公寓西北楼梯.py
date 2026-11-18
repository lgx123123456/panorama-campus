"""Fit teaching interiors to the shell and the user's corrected circulation directions."""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

import 公寓大厅右侧楼梯 as dorm
import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
import 教室与男女生公寓室内 as interior
from 校园透明玻璃 import prepare_web_glass


SOURCE = dorm.OUT / (dorm.STEM + ".blend")
OUT = doors.ROOT / "成果/教学楼室内贴合与公寓西北楼梯"
STEM = "校园_教学楼贴合与公寓西北楼梯"


def side_room(mesh, x0, x1, y0, y1, z, south_door=False):
    b = mesh.box
    interior.slab(b, "东端侧室地面", "school_floor", x0, x1, y0, y1, z)
    interior.slab(b, "东端侧室天花", "ceiling", x0, x1, y0, y1, z+3.08, .08)
    for x in ((x0,) if south_door else (x0, x1)):
        interior.wall(b, "plaster", x, y0, y1, z, 3.08)
    interior.endwall(b, "plaster", y1, x0, x1, z, 3.08)
    if south_door:
        center = (y0+y1)/2
        interior.endwall(b, "plaster", y0, x0, x1, z, 3.08)
        interior.wall(b, "plaster", x1, y0, center-.68, z, 3.08)
        interior.wall(b, "plaster", x1, center+.68, y1, z, 3.08)
        interior.wall(b, "plaster", x1, center-.68, center+.68, z+2.35, .73)
        return
    center = (x0+x1)/2
    interior.endwall(b, "plaster", y0, x0, center-.55, z, 3.08)
    interior.endwall(b, "plaster", y0, center+.55, x1, z, 3.08)
    interior.endwall(b, "plaster", y0, center-.55, center+.55, z+2.3, .78)


def rebuild_school(scene, payload, bid, enlarge=False, offices=False):
    frame = interior.Frame(bid, False)
    root = next(c for c in bpy.data.collections if c.name.startswith(bid+" ")
                and "教室、楼道与楼梯" in c.name)
    old_rooms = [o for o in root.all_objects if "01-01 教室样板" in o.name and o.type == "MESH"]
    old_rooms.sort(key=lambda obj: obj.name)
    assert old_rooms, bid
    templates = [(o.data, frame.matrix.inverted() @ o.matrix_world) for o in old_rooms]
    # Retain mesh-local offsets, including the separate corridor fixtures.
    source_origin = interior.translate(1.06, 10.55, .48 if bid == "B15" else .64)
    templates = [(data, source_origin.inverted() @ matrix) for data, matrix in templates]
    fixture_bounds = [(min((offset @ vertex.co).x for vertex in data.vertices),
                       max((offset @ vertex.co).x for vertex in data.vertices))
                      for data, offset in templates]
    for obj in tuple(root.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    old_link = bpy.data.objects.get(bid+" 连廊下门厅与楼道")
    if old_link:
        bpy.data.objects.remove(old_link, do_unlink=True)
    interiors = set(bpy.data.collections["楼内还原"].all_objects)
    # Exterior fixtures and bridge meshes can carry earlier estimated positions.
    # Clear their intersections with the usable interior at the same time as the shell.
    extras = {obj for obj in scene.objects if obj.type == "MESH" and obj not in interiors}
    base = .48 if bid == "B15" else .64
    levels = (base, 4.32, 8.04, 11.76, 15.48)
    east_end = 91.90 if bid == "B15" else 89.35
    # Hollow the shell through its usable interior while preserving the façade skin.
    lowest_entry = min(r["base"] for r in payload["doors"] if r["building"] == bid)
    aperture = frame.matrix @ interior.translate(0, east_end, lowest_entry-.04)
    cut_objects = doors.cut_portal(scene, aperture, 14.40, 19.14-lowest_entry, bid,
                                   depth=east_end-1.0, outside=0, extra_objects=extras)
    construction = interior.collection(bid+" 贴合楼体室内与双侧楼梯", root)
    rooms = interior.collection(bid+" 北侧实拍教室共享网格", root)
    mats = {key: bpy.data.materials["校园室内 · "+key] for key in
            ("plaster", "ceiling", "base", "silver", "lamp", "grid")}
    mats["school_floor"] = bpy.data.materials["教学楼道浅灰地砖"]
    mats["hall_floor"] = bpy.data.materials["公寓灰色地砖"]
    mesh = interior.new_mesh(scene, construction, mats)
    b = mesh.box
    slab = interior.slab
    local_entries = [(r, frame.matrix.inverted() @ Vector(r["center"])) for r in payload["doors"]
                     if r["building"] == bid and "bridge" in r]
    south_entry = next(p for r, p in local_entries if r["outward"][1] < 0)
    east_y = south_entry.y+2.80
    east_front = east_y-1.55
    entry_low = min(p.y for _, p in local_entries)-.35
    entry_high = max(p.y for _, p in local_entries)+.35
    entry_z = local_entries[0][0]["base"]
    east_stair = interior.translate(4.60, east_y, 0) @ interior.rotation(math.pi/2)
    west_stair = interior.translate(5.62, 3.0, 0)
    west_back = 8.85 if enlarge else 8.35
    east_back = -1.15 if enlarge else -.70
    if enlarge:
        scale = Matrix.Diagonal((1.15, 1.10, 1, 1))
        east_stair = east_stair @ scale
        west_stair = west_stair @ scale
    stairs = []
    for side, stair_matrix in (("西", west_stair), ("东", east_stair)):
        stairs.append({"building": bid, "side": side, "levels": list(levels), "routes": [],
                       "corridor_join": list(frame.matrix @ Vector((5.45, 76.5, base))),
                       "corridor_points": [], "first_flight_direction":
                       list((frame.matrix @ stair_matrix).to_3x3() @ Vector((0,1,0)))})

    def point(x, y, z):
        return list(frame.matrix @ Vector((x,y,z)))

    for floor, z in enumerate(levels):
        mesh.section(f"{bid} 贴合室内 {floor+1:02d}F 连续地坪与南侧楼道")
        # Every classroom reaches the façade and its corridor partition.
        spans = [(3.50, 14.0, -7.12, .80)]
        spans.extend((14.0+i*(64/6), 14.0+(i+1)*(64/6), -7.12, 3.70) for i in range(6))
        for index, (y0,y1,x0,x1) in enumerate(spans, 1):
            placement = (frame.matrix @ interior.translate((x0+x1)/2,y0,z)
                         @ Matrix.Diagonal((-(x1-x0)/8.3, (y1-y0)/interior.ROOM_Y, 1, 1)))
            for part, (data, offset) in enumerate(templates):
                obj = bpy.data.objects.new(f"{bid} {floor+1:02d}-{index:02d} 北侧教室 {part+1}", data)
                rooms.objects.link(obj)
                if part:
                    corridor_right = 4.10 if index == 1 else 7.15
                    low, high = fixture_bounds[part]
                    depth_scale = (corridor_right-x1-.30)/(high-low)
                    fixtures = (frame.matrix @ interior.translate(x1+.15+high*depth_scale,y0,z)
                                @ Matrix.Diagonal((-depth_scale,(y1-y0)/interior.ROOM_Y,1,1)))
                    obj.matrix_world = fixtures @ offset
                else:
                    obj.matrix_world = placement @ offset
        interior.corridor_floor(mesh, "school_floor", .80, 4.10, 3.50, 14.0, z, 3.04)
        interior.corridor_floor(mesh, "school_floor", 3.70, 7.15, 14.0, 78.0, z, 3.04)
        slab(b, "西端入口横向门厅", "school_floor", -7.12, 7.15, 1.0, 3.50, z)
        slab(b, "西端入口门厅顶棚", "ceiling", -7.12, 7.15, 1.0, 3.50, z+3.08, .08)
        slab(b, "西楼梯后接连续楼道", "school_floor", .80, 7.15, west_back, 14.0, z)
        slab(b, "西楼梯后通道顶棚", "ceiling", .80, 7.15, west_back, 14.0, z+3.08, .08)
        if floor == 0:
            knots = ((78.0,z),(entry_low,entry_z),(entry_high,entry_z),(east_front,z))
            for (y0,z0),(y1,z1) in zip(knots,knots[1:]):
                mesh.polygons("东门连续平缓门厅地面", "school_floor",
                              [(-7.12,y0,z0),(7.15,y0,z0),(7.15,y1,z1),(-7.12,y1,z1)],[(0,1,2,3)])
        else:
            slab(b, "东门贴合塔楼横向门厅", "school_floor", -7.12, 7.15, 78.0, east_front, z)
        slab(b, "东门横向门厅顶棚", "ceiling", -7.12, 7.15, 78.0, east_front, z+3.08, .08)
        slab(b, "东门右侧楼梯前平台", "school_floor", 4.10, 7.15, east_front, east_end, z)
        slab(b, "东楼梯前平台顶棚", "ceiling", 4.10, 7.15, east_front, east_end, z+3.08, .08)
        # Occupy the north-west tower bay, leaving a compact transverse entrance hall.
        side_room(mesh, -7.12, 3.70, 78.0, entry_low-.10, z, south_door=offices)
        side_room(mesh, -7.12, east_back, east_front, east_end, z)
        if east_y+1.55 < east_end-.20:
            slab(b, "东梯后封边平台", "school_floor", east_back, 4.10, east_y+1.55, east_end, z)
            slab(b, "东梯后封边顶棚", "ceiling", east_back, 4.10, east_y+1.55, east_end, z+3.08, .08)
        for xx in (4.09, 7.18):
            interior.wall(b, "plaster", xx, 3.50, west_back, z, 3.08)
        interior.endwall(b, "plaster", west_back, 4.09, 7.18, z, 3.08)
        # The east staircase occupies the right-hand bay when facing north at its door.
        for yy in (east_y-1.55, east_y+1.55):
            interior.endwall(b, "plaster", yy, east_back, 4.10, z, 3.08)
        interior.wall(b, "plaster", east_back, east_y-1.55, east_y+1.55, z, 3.08)
        for y in range(15, 78, 4):
            interior.wall(b, "plaster", 7.20, y-2, y+2, z, 1.05)
            interior.wall(b, "plaster", 7.20, y-2, y+2, z+2.68, .40)
        for side_index, stair_matrix in enumerate((west_stair, east_stair)):
            corner = (2.45, 2.50, z) if side_index == 0 else (5.65, east_y, z)
            stairs[side_index]["corridor_points"].append(point(*corner))
            if floor == len(levels)-1:
                continue
            rise = levels[floor+1]-z
            mesh.section(f"{bid} {'西' if side_index == 0 else '东'}侧楼梯 {floor+1:02d}F 双跑梯")
            # Transform only this section's vertices into the common building frame.
            interior.stair(mesh, 0, 0, z, rise)
            for vertices, _, _ in mesh.groups.values():
                for i, vertex in enumerate(vertices):
                    vertices[i] = stair_matrix @ Vector(vertex)
            mid = .5+math.ceil(rise/.34)*.280+.60
            route = ((-.62,-.50,z),(-.62,.38,z),(-.62,mid,z+rise/2),
                     (.62,mid,z+rise/2),(.62,.38,z+rise),(.62,-.50,z+rise))
            stairs[side_index]["routes"].append({"from_floor": floor+1, "to_floor": floor+2,
                "points": [list(frame.matrix @ stair_matrix @ Vector(p)) for p in route]})
    stairs[0]["corridor_path"] = [point(2.45,2.50,base),point(2.45,11.0,base),
                                   point(5.45,11.0,base),point(5.45,76.5,base),
                                   stairs[1]["corridor_points"][0]]
    mesh.finish()
    interior.move_collection(construction, frame.matrix)
    paths = []
    for record, local in local_entries:
        cut_objects.extend(doors.cut_portal(scene, doors.frame(record["center"], Vector(record["outward"])),
                                             record["width"]+.08, 2.60, bid, depth=.85,
                                             extra_objects=extras))
        exterior = Vector(record["center"])+Vector(record["outward"])*.35
        paths.append([list(exterior),point(5.45,local.y,entry_z),point(5.45,entry_low,entry_z),
                      point(5.45,78.0,base)])
    link = {"building": bid, "join": point(5.45,76.5,base), "base": entry_z,
            "paths": paths, "width": 2.8, "cut_objects": cut_objects}
    # West entrance thresholds meet the same foyer floor.
    for record in (r for r in payload["doors"] if r["building"] == bid and "bridge" not in r):
        opening = doors.frame(record["center"], Vector(record["outward"]))
        doors.cut_portal(scene, opening, record["width"]+.08, 2.60, bid, depth=1.6)
    for obj in construction.all_objects:
        obj.name = bid+" 贴合室内 "+obj.name
        if obj.type == "MESH" and len(obj.data.uv_layers) < 2:
            obj.data.uv_layers.new(name="WalkableCollision")
    return link, stairs, {"building": bid, "classrooms_per_floor": 7,
                         "classroom_side": "north", "corridor_side": "south",
                         "interior_bounds": [-7.12,7.15,1.0,east_end], "cut_objects": cut_objects,
                         "stair_horizontal_scale": [1.15,1.10] if enlarge else [1,1],
                         "office_spaces": ([{"bounds": [-7.12,3.70,78.0,entry_low-.10], "door_side": "south"},
                                             {"bounds": [-7.12,east_back,east_front,east_end], "door_side": "west"}]
                                            if offices else []),
                         "basis": "用户确认从西向东看教室在左、楼梯在右；东门向北看楼道在左、楼梯在右。按现有外壳重排贯通楼层，教室深度与长度贴合外墙和楼道，东西梯均接平台。教室数量、开间与东端侧室用途按现有壳体估排。"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    payload = json.loads((dorm.OUT / "楼门与公寓校正.json").read_text(encoding="utf8"))
    if "西北" not in payload["dorm_lobby_stairs"]["basis"]:
        payload["dorm_lobby_stairs"]["basis"] += " 2026-11-16用户确认首跑上楼朝西北。"
    links, east, west, records = [], [], [], []
    for bid in ("B15", "B21"):
        link, stairs, record = rebuild_school(bpy.context.scene, payload, bid)
        links.append(link)
        west.append(stairs[0])
        east.append(stairs[1])
        records.append(record)
    payload["teaching_bridge_entries"]["corridors"] = links
    payload["teaching_east_stairs"] = {"buildings": east}
    payload["teaching_west_stairs"] = {"buildings": west}
    payload["teaching_interior_fit"] = records
    (OUT/"楼门与公寓校正.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT/(STEM+".glb"))
    preview.OUT = OUT
    preview.publish_preview(bpy.context.scene)


if __name__ == "__main__":
    main()
