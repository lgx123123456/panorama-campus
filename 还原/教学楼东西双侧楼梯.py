"""Place east stairs in the reserved space inside each teaching building."""
import json
import math
import sys

import bpy
from mathutils import Vector
from shapely.geometry import Polygon, box

import 公寓门位与重复连廊校正 as doors
import 教学楼连廊下入口校正 as bridge
import 地面补铺与预览优化 as preview
from 教室与男女生公寓室内 import CLASS_STEP, Frame, collection, move_collection, new_mesh, slab, stair
from 校园透明玻璃 import prepare_web_glass


SOURCE = bridge.OUT / (bridge.STEM + ".blend")
OUT = doors.ROOT / "成果/教学楼东梯归位"
STEM = "校园_教学楼东梯归位"


def east_stairs(scene, payload, previous_link):
    bid = previous_link["building"]
    school = Frame(bid, False)
    parent = next(c for c in bpy.data.collections if c.name.startswith(bid+" ") and "教室、楼道与楼梯" in c.name)
    root = collection(bid+" 楼内东侧预留区五层楼梯", parent)
    far = min(school.corners[1].y, school.corners[2].y)
    rooms_end = 10.55 + int((far-10.55-3)/CLASS_STEP)*CLASS_STEP
    # The classrooms stop about nine metres before the east wall in both buildings.
    x = -.17
    front = far-.80
    y = front-1.50
    cross_y = y+.65
    corridor_start = rooms_end-1.5
    footprint = Polygon([(point.x,point.y) for point in school.corners])
    assert footprint.covers(box(x-1.75,rooms_end+.50,x+1.75,front+.15)), bid+" 东梯超出楼内预留区"
    base = .48 if bid == "B15" else .64
    levels = (base, 4.32, 8.04, 11.76, 15.48)
    entries = [record for record in payload["doors"] if record["building"] == bid and "bridge" in record]
    bpy.data.objects.remove(bpy.data.objects[bid+" 连廊下门厅与楼道"], do_unlink=True)
    door_mats = {"floor": bpy.data.materials["灰色入口台阶"]}
    # Keep the reserved interior at its existing ground-floor level, then descend to the doors.
    ramp_end = (school.matrix @ Vector((-4.7, front+.02, 0))).x
    link = bridge.connect_corridor(scene, parent, bid, entries, door_mats,
                                   ramp_start=min(record["center"][0] for record in entries)-.10,
                                   ramp_end=ramp_end)
    cuts = set()
    bridge_prefixes = ("A02 思远楼—近门西翼", "A03 连廊", "A03 思远楼", "A04 图书馆西侧弧廊")
    bridge_parts = {obj for c in bpy.data.collections if c.name.startswith(bridge_prefixes)
                    for obj in c.all_objects}

    def cut(x0, x1, y0, y1, z0, z1):
        origin = school.matrix @ Vector(((x0+x1)/2,y1,z0-.20))
        outward = school.matrix.to_3x3() @ Vector((0,1,0))
        cuts.update(doors.cut_portal(scene, doors.frame(origin,outward),x1-x0,z1-z0+.20,
                                    bid,depth=y1-y0,outside=0,extra_objects=bridge_parts))

    cut(x-1.44,x+1.44,rooms_end+.65,front,base,18.4)
    for z in levels:
        cut(-6.32,-3.08,corridor_start,front,z,z+3.06)
        cut(-6.32,x+1.44,y-.50,front,z,z+3.06)
    bpy.data.objects[bid+" 连廊下门厅与楼道"].data.uv_layers.new(name="WalkableCollision")
    mats = {key: bpy.data.materials["校园室内 · "+key]
            for key in ("base", "silver", "plaster", "ceiling", "lamp")}
    mats["hall_floor"] = bpy.data.materials["公寓灰色地砖"]
    mats["school_floor"] = bpy.data.materials["教学楼道浅灰地砖"]
    mesh = new_mesh(scene, root, mats)
    routes = []
    corridor_points = []
    for floor, z in enumerate(levels):
        mesh.section(f"{bid} 东楼梯 {floor+1:02d}F 平台与走廊")
        b = mesh.box
        slab(b,"预留区连续楼道","school_floor",-6.31,-3.09,corridor_start,front,z)
        slab(b,"东楼梯前平台","school_floor",-6.31,x+1.40,y-.48,front,z)
        slab(b,"预留区楼道顶棚","ceiling",-6.31,-3.09,corridor_start,front,z+3.04,.08)
        slab(b,"东平台顶棚","ceiling",-6.31,x+1.40,y-.48,front,z+3.04,.08)
        for xx in (-6.40,-3.00):
            b("楼内东端楼道侧墙","plaster",xx,(rooms_end+y-.50)/2,z+1.52,
              .14,y-.50-rooms_end,3.04)
        b("东平台前墙","plaster",(-3.00+x+1.40)/2,front+.08,z+1.52,
          x+1.40+3.00,.14,3.04)
        b("东平台灯","lamp",-2.50,cross_y,z+2.97,1.15,.28,.045)
        corridor_points.append(list(school.matrix @ Vector((-4.7,cross_y,z))))
        if floor == len(levels)-1:
            continue
        rise = levels[floor+1]-z
        mesh.section(f"{bid} 东楼梯 {floor+1:02d}F 至 {floor+2:02d}F 双跑梯")
        stair(mesh,x,y,z,rise,flip=True)
        n = math.ceil(rise/.34)
        mid = y-(.5+n*.280)-.60
        local_points = ((x-.62,cross_y,z),(x-.62,y-.38,z),(x-.62,mid,z+rise/2),
                        (x+.62,mid,z+rise/2),(x+.62,y-.38,z+rise),(x+.62,cross_y,z+rise))
        routes.append({"from_floor":floor+1,"to_floor":floor+2,
                       "points":[list(school.matrix @ Vector(point)) for point in local_points]})
    mesh.section(bid+" 楼内东梯井墙与顶部")
    back = rooms_end+.70
    for xx in (x-1.51,x+1.51):
        mesh.box("东梯井侧墙","plaster",xx,(back+y-.50)/2,(base+18.40)/2,
                 .14,y-.50-back,18.40-base)
    mesh.box("东平台外侧墙","plaster",x+1.51,(y-.50+front)/2,(base+18.40)/2,
             .14,front-y+.50,18.40-base)
    mesh.box("东梯井背墙","plaster",x,back-.08,(base+18.40)/2,3.16,.14,18.40-base)
    slab(mesh.box,"东梯井顶板","ceiling",x-1.58,x+1.58,back-.15,front,18.40)
    mesh.finish()
    move_collection(root,school.matrix)
    for obj in root.all_objects:
        obj.name = bid+" 东楼梯 "+obj.name
        obj.data.uv_layers.new(name="WalkableCollision")
    join = school.matrix @ Vector((-4.7,corridor_start,base))
    return link, {"building":bid,"levels":list(levels),"center":list(school.matrix @ Vector((x,y,0))),
                  "corridor_join":list(join),"corridor_points":corridor_points,"routes":routes,
                  "reserved_local_bounds":[-6.31,5.35,rooms_end,far],
                  "stair_local_bounds":[x-1.58,x+1.58,back-.15,front],
                  "cut_objects":sorted(cuts)}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE),load_ui=False)
    payload = json.loads((bridge.OUT/"楼门与公寓校正.json").read_text(encoding="utf8"))
    records, links = [], []
    for previous_link in payload["teaching_bridge_entries"]["corridors"]:
        link, record = east_stairs(bpy.context.scene,payload,previous_link)
        links.append(link)
        records.append(record)
    payload["teaching_bridge_entries"]["corridors"] = links
    payload["teaching_east_stairs"] = {"source":str(SOURCE),"buildings":records,
        "basis":"用户指定东梯位于两楼内部空区。按第六间教室东侧至东外墙之间约9米预留区布置，沿楼栋轴线接五层走廊；梯段形制与尺寸按预留区及原西梯估排。"}
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
