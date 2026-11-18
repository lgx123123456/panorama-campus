"""Connect three bridge-aligned ground entrances to the teaching corridors."""
import json
import sys

import bpy
from mathutils import Vector
from shapely.geometry import LineString, Point
from shapely.ops import split, triangulate, unary_union

import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
from 图书馆照片还原 import CAL, world
from 教室与男女生公寓室内 import CLASS_STEP, Frame
from 校园透明玻璃 import prepare_web_glass


SOURCE = doors.OUT / (doors.STEM + ".blend")
OUT = doors.ROOT / "成果/教学楼连廊下入口校正"
STEM = "校园_教学楼连廊下入口"


def bridge_point(pixel, adjusted=False):
    point = world(pixel)
    if adjusted:
        origin = world((699,260))
        south = (world((699,261)) - origin).normalized()
        west = (world((698,260)) - origin).normalized()
        distance = (point - origin).dot(south) / CAL["metres_per_pixel"]
        offset = max(0, min(1, (38-distance)/32)) * 9.5 * CAL["metres_per_pixel"]
        point += west * offset
    return point


def intersect_facade(a, b, y):
    return a.lerp(b, (y-a.y)/(b.y-a.y))


def new_entries():
    # Use the present bridge centre lines and the actual tower facade planes.
    zhi_y = doors.object_center("B场地 玻璃入口灰色门槛").y
    north_y = world((738,337)).y + 7.43
    south_y = world((738,337)).y - 7.43
    zhi = intersect_facade(bridge_point((701,256), True), bridge_point((710,278), True), zhi_y)
    si_north = intersect_facade(world((733,320)), world((737,327)), north_y)
    si_south = intersect_facade(world((737,352)), world((762,408)), south_y)
    result = []
    for bid, suffix, label, point, sign, base, bridge in (
        ("B15", "_bridge", "致远楼·连廊下入口", zhi, -1, .22, "A03"),
        ("B21", "_bridge_north", "思远楼·北连廊下入口", si_north, 1, .15, "A03"),
        ("B21", "_bridge_south", "思远楼·南连廊下入口", si_south, -1, .15, "A02"),
    ):
        result.append({"id": bid+suffix, "building": bid, "label": label,
                       "center": [point.x, point.y, base], "outward": [0,sign,0],
                       "width": 2.4, "height": 2.45, "base": base,
                       "bridge": bridge, "basis": "用户确认门数、位置及连廊对齐关系；门宽与标高沿现有模型估测"})
    return result


def connect_corridor(scene, collection, bid, entries, mats, ramp_start=None, ramp_end=None):
    school = Frame(bid, False)
    far = min(school.corners[1].y, school.corners[2].y)
    end = 10.55 + int((far-10.55-3)/CLASS_STEP) * CLASS_STEP
    join = school.matrix @ Vector((-4.7, end-1.5, 0))
    height = .48 if bid == "B15" else .64
    base = entries[0]["base"]
    junction_x = sum(record["center"][0] for record in entries) / len(entries)
    junction = Vector((junction_x, join.y, 0))
    paths = []
    for record in entries:
        point = Vector(record["center"])
        point.z = 0
        exterior = point + Vector(record["outward"]) * .35
        # The short transverse hall preserves the centre of each bridge doorway.
        paths.append([exterior, Vector((point.x, join.y, 0)), junction])
    paths.append([junction, join])
    cuts = set()
    regions = []
    joints = [junction]
    for path in paths:
        for point in path[1:-1]:
            regions.append(Point(point.xy).buffer(1.40))
            joints.append(point)
        for a, b in zip(path, path[1:]):
            if (b-a).length < .01:
                continue
            direction = (b-a).normalized()
            origin = a.copy()
            origin.z = base
            cuts.update(doors.cut_portal(scene, doors.frame(origin, -direction),
                                        2.82, 3.06, bid, depth=(b-a).length+.12, outside=.12))
            regions.append(LineString((a.xy, b.xy)).buffer(1.40, cap_style="flat", join_style="mitre"))
    regions.append(Point(junction.xy).buffer(1.40))
    for point in joints:
        origin = Vector((point.x, point.y+1.41, base))
        cuts.update(doors.cut_portal(scene, doors.frame(origin, Vector((0,1,0))),
                                    2.82, 3.06, bid, depth=2.82, outside=0))
    outline = unary_union(regions)
    if ramp_start is None:
        ramp_start = min(record["center"][0] for record in entries) - 1.55
    if ramp_end is None:
        ramp_end = join.x + 1.0

    def floor_z(x):
        fraction = max(0, min(1, (ramp_start-x)/(ramp_start-ramp_end)))
        return base + fraction*(height-base)

    vertices, faces, slots = [], [], []

    def face(points, material):
        start = len(vertices)
        vertices.extend(points)
        faces.append(tuple(range(start, len(vertices))))
        slots.append(material)

    regions = [outline]
    for boundary in (ramp_start, ramp_end):
        cutter = LineString(((boundary,outline.bounds[1]-1),(boundary,outline.bounds[3]+1)))
        regions = [part for region in regions for part in split(region,cutter).geoms]
    for region in regions:
        for triangle in triangulate(region):
            if not region.covers(triangle):
                continue
            points = list(triangle.exterior.coords)[:-1]
            face([(x,y,floor_z(x)) for x,y in points], 0)
            face([(x,y,floor_z(x)+3.04) for x,y in reversed(points)], 1)
    openings = [Vector(record["center"]) for record in entries] + [join]
    for a, b in zip(list(outline.exterior.coords), list(outline.exterior.coords)[1:]):
        fractions = [0.0,1.0]
        if abs(b[0]-a[0]) > 1e-8:
            for boundary in (ramp_start,ramp_end):
                fraction = (boundary-a[0])/(b[0]-a[0])
                if 0 < fraction < 1:
                    fractions.append(fraction)
        fractions.sort()
        for lo, hi in zip(fractions,fractions[1:]):
            x, y = (a[i]+lo*(b[i]-a[i]) for i in (0,1))
            xx, yy = (a[i]+hi*(b[i]-a[i]) for i in (0,1))
            middle = Vector(((x+xx)/2,(y+yy)/2,0))
            if any(Vector((middle.x-p.x,middle.y-p.y,0)).length < 1.55 for p in openings):
                continue
            face([(x,y,floor_z(x)),(xx,yy,floor_z(xx)),
                  (xx,yy,floor_z(xx)+3.04),(x,y,floor_z(x)+3.04)],1)
    mesh = bpy.data.meshes.new(bid+" 连廊下门厅与楼道")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mats["floor"])
    mesh.materials.append(bpy.data.materials["浅色公告栏边框"])
    for polygon, slot in zip(mesh.polygons, slots):
        polygon.material_index = slot
    uv = mesh.uv_layers.new()
    for loop in mesh.loops:
        point = mesh.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = (point.x, point.y+point.z)
    obj = bpy.data.objects.new(bid+" 连廊下门厅与楼道", mesh)
    collection.objects.link(obj)
    return {"building": bid, "join": [join.x,join.y,height], "base": base,
            "paths": [[[p.x,p.y,floor_z(p.x)] for p in path] for path in paths],
            "width": 2.8, "cut_objects": sorted(cuts)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    scene = bpy.context.scene
    payload = json.loads((doors.OUT/"楼门与公寓校正.json").read_text(encoding="utf8"))
    records = new_entries()
    collection = bpy.data.collections.new("教学楼东端 · 连廊下三处入口与通长楼道连接")
    scene.collection.children.link(collection)
    mats = {"metal": bpy.data.materials["栏杆"], "glass": bpy.data.materials["浅灰蓝玻璃"],
            "blue": bpy.data.materials["蓝色公告栏与垃圾桶"], "floor": bpy.data.materials["灰色入口台阶"]}
    links = []
    for bid in ("B15", "B21"):
        entries = [record for record in records if record["building"] == bid]
        links.append(connect_corridor(scene, collection, bid, entries, mats))
    for record in records:
        doors.add_door(scene, collection, record, mats)
        bpy.data.objects.remove(bpy.data.objects["CampusEntryLanding_"+record["id"]], do_unlink=True)
        print("BRIDGE ENTRY", record["id"], record["center"], flush=True)
    bpy.context.view_layer.update()
    payload["doors"].extend(records)
    payload["teaching_bridge_entries"] = {"source": str(SOURCE), "corridors": links,
        "confirmed": "致远楼东端连廊下一处，思远楼北连廊下及南连廊下各一处；门洞与连廊中心、室内通道对齐"}
    (OUT/"楼门与公寓校正.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT/(STEM+".glb"))
    preview.OUT = OUT
    preview.publish_preview(scene)


if __name__ == "__main__":
    main()
