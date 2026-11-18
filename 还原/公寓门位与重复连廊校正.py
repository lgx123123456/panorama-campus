"""Correct the boys' ground footprint and replace sealed entrance panes with hinged doors."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

import 地面补铺与预览优化 as preview
from 图书馆照片还原 import PLAN, world
from 校园透明玻璃 import prepare_web_glass
from 公寓与运动区实拍细化 import Planting, tree, foliage_cards


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/地面补铺与预览优化/校园_地面细化.blend"
OUT = ROOT / "成果/公寓门位与重复连廊校正"
STEM = "校园_公寓门位与楼门校正"
UP = Vector((0, 0, 1))
FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def frame(center, outward):
    outward = outward.normalized()
    result = Matrix((outward.cross(UP), outward, UP)).transposed().to_4x4()
    result.translation = Vector(center)
    return result


def object_center(name):
    obj = bpy.data.objects[name]
    return sum((obj.matrix_world @ Vector(p) for p in obj.bound_box), Vector()) / 8


def boys_transform(scene):
    # The early polygon mixes roof edges with projected façade feet. The ground
    # entrance is estimated at (685,149), beside the northbound arcade route.
    old = world((672.5, 142.5))
    new = world((685, 149))
    angle = math.radians(preview.CAL["rotation_degrees"])
    rotation = Matrix.Rotation(angle, 4, "Z")
    scale = Matrix.Diagonal((0.92, 0.74, 1.0, 1.0))
    transform = Matrix.Translation(new) @ rotation @ scale @ rotation.inverted() @ Matrix.Translation(-old)
    members = {obj for c in bpy.data.collections
               if c.name.startswith(("B25 ", "绅远楼靠餐厅端面")) for obj in c.all_objects}
    members.update(obj for obj in scene.objects if obj.name.startswith("B25 "))
    changed = sorted(obj.name for obj in members)
    for obj in members:
        if obj.parent not in members:
            obj.matrix_world = transform @ obj.matrix_world
    return transform, {"旧入口像素": [672.5, 142.5], "校正入口像素": [685, 149],
                       "东西比例": 0.92, "南北比例": 0.74, "同步对象数": len(changed),
                       "依据": "02航拍屋面与墙脚差异、25/000与180；地面落点及尺寸仍为照片估测"}


def split_polygon(points, axis, boundary):
    """Return the two half-polygons, interpolating every UV channel at cuts."""
    low, high = [], []
    for previous, current in zip(points[-1:] + points[:-1], points):
        a, b = previous[0][axis] - boundary, current[0][axis] - boundary
        if (a < -1e-8 and b > 1e-8) or (a > 1e-8 and b < -1e-8):
            t = a / (a - b)
            cross = (previous[0].lerp(current[0], t),
                     [u.lerp(v, t) for u, v in zip(previous[1], current[1])])
            low.append(cross)
            high.append(cross)
        if b <= 1e-8:
            low.append(current)
        if b >= -1e-8:
            high.append(current)
    return low, high


def cut_portal(scene, transform, width, height, building, depth=2.8, outside=0.65, extra_objects=()):
    inverse = transform.inverted()
    low = Vector((-width / 2, -depth, 0.015))
    high = Vector((width / 2, outside, height + 0.025))
    changed = []
    allowed = {obj for c in bpy.data.collections
               if c.name.startswith(building + " ") or
               (building == "B22" and c.name == "餐厅入口及出口实拍外立面")
               for obj in c.all_objects}
    if building in bpy.data.objects:
        allowed.add(bpy.data.objects[building])
    allowed.update(extra_objects)
    for obj in allowed:
        if obj.type != "MESH" or obj.name.startswith("CampusDoor"):
            continue
        if obj not in extra_objects and any(word in obj.name for word in ("分类桶", "绿篱", "树干", "树枝", "花池")):
            continue
        local = inverse @ obj.matrix_world
        bounds = [local @ Vector(p) for p in obj.bound_box]
        if any(max(p[a] for p in bounds) <= low[a] or min(p[a] for p in bounds) >= high[a] for a in range(3)):
            continue
        mesh = obj.data
        vertices, polygons, slots, smooth, uv_faces = [], [], [], [], []
        removed = False
        restore = local.inverted()
        for face in mesh.polygons:
            points = [(local @ mesh.vertices[mesh.loops[i].vertex_index].co,
                       [layer.data[i].uv.copy() for layer in mesh.uv_layers]) for i in face.loop_indices]
            # A horizontal or wall face can have a zero-thickness extent.
            intersects = all(max(p[0][a] for p in points) >= low[a] and min(p[0][a] for p in points) <= high[a] for a in range(3))
            outside = []
            if intersects:
                inside = points
                for axis in range(3):
                    part, inside = split_polygon(inside, axis, low[axis])
                    if len(part) >= 3:
                        outside.append(part)
                    if len(inside) < 3:
                        break
                    inside, part = split_polygon(inside, axis, high[axis])
                    if len(part) >= 3:
                        outside.append(part)
                    if len(inside) < 3:
                        break
                removed |= len(inside) >= 3
            else:
                outside = [points]
            for part in outside:
                indices = []
                clean = []
                for point in part:
                    if not clean or (point[0] - clean[-1][0]).length > 1e-7:
                        clean.append(point)
                if len(clean) > 2 and (clean[0][0] - clean[-1][0]).length < 1e-7:
                    clean.pop()
                if len(clean) < 3:
                    continue
                for point, uv in clean:
                    indices.append(len(vertices))
                    vertices.append(restore @ point)
                polygons.append(indices)
                slots.append(face.material_index)
                smooth.append(face.use_smooth)
                uv_faces.append([uv for _, uv in clean])
        if not removed:
            continue
        replacement = bpy.data.meshes.new(mesh.name + " · 通行门洞")
        replacement.from_pydata(vertices, [], polygons)
        for material in mesh.materials:
            replacement.materials.append(material)
        for face, slot, shading in zip(replacement.polygons, slots, smooth):
            face.material_index, face.use_smooth = slot, shading
        for channel, layer in enumerate(mesh.uv_layers):
            target = replacement.uv_layers.new(name=layer.name)
            for face, coords in zip(replacement.polygons, uv_faces):
                for index, uv in zip(face.loop_indices, coords):
                    target.data[index].uv = uv[channel]
        obj.data = replacement
        changed.append(obj.name)
    return changed


def boxes(name, parent, transform, parts):
    vertices, faces, slots = [], [], []
    materials = []
    for position, size, material in parts:
        if material not in materials:
            materials.append(material)
        offset = len(vertices)
        x, y, z = position
        w, d, h = (v / 2 for v in size)
        vertices.extend((x + a * w, y + b * d, z + c * h) for a, b, c in
                        ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                         (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)))
        faces.extend(tuple(offset + i for i in face) for face in FACES)
        slots.extend([materials.index(material)] * 6)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    for material in materials:
        mesh.materials.append(material)
    for face, slot in zip(mesh.polygons, slots):
        face.material_index = slot
    mesh.uv_layers.new()
    # A second UV layer preserves the interactive objects in existing preview batching.
    mesh.uv_layers.new(name="DoorIdentity")
    obj = bpy.data.objects.new(name, mesh)
    parent.objects.link(obj)
    obj.matrix_world = transform
    return obj


def add_door(scene, collection, record, mats):
    transform = frame(record["center"], Vector(record["outward"]))
    transform.translation.z = record["base"]
    width, height = record["width"], record["height"]
    record["cut_objects"] = cut_portal(scene, transform, width + 0.06, height, record["building"])
    frame_parts = [((side * (width / 2 + 0.045), 0, height / 2), (.09, .16, height + .08), mats["metal"]) for side in (-1, 1)]
    frame_parts.append(((0, 0, height + .045), (width + .18, .16, .09), mats["metal"]))
    boxes("CampusDoorFrame_" + record["id"], collection, transform, frame_parts)
    # Bridge only the threshold and entrance landing. Existing rooms retain their layouts.
    boxes("CampusEntryLanding_" + record["id"], collection, transform,
          [((0, -2.5, -.10), (width + .16, 5.4, .20), mats["floor"])])
    record["pivots"] = []
    half = width / 2
    for side, suffix in ((-1, "L"), (1, "R")):
        pivot = bpy.data.objects.new("CampusDoorPivot_" + record["id"] + "_" + suffix, None)
        collection.objects.link(pivot)
        angle = -side * math.pi / 2
        pivot.matrix_world = transform @ Matrix.Translation((side * width / 2, 0, 0)) @ Matrix.Rotation(angle, 4, "Z")
        center = -side * half / 2
        parts = [((center, 0, height / 2), (half - .065, .045, height - .10), mats["glass"])]
        for x in (0, -side * half):
            parts.append(((x, 0, height / 2), (.045, .075, height), mats["metal"]))
        for z in (.025, height - .025):
            parts.append(((center, 0, z), (half, .075, .05), mats["metal"]))
        parts.append(((center, .025, .99), (half - .04, .014, .065), mats["blue"]))
        for y in (-.105, .105):
            parts.append(((-side * (half - .15), y, 1.10), (.035, .035, .42), mats["metal"]))
        leaf = boxes("CampusDoorLeaf_" + record["id"] + "_" + suffix, collection, Matrix.Identity(4), parts)
        leaf.parent = pivot
        leaf.matrix_parent_inverse = Matrix.Identity(4)
        leaf.matrix_basis = Matrix.Identity(4)
        record["pivots"].append({"name": pivot.name, "side": side})
    record["center"] = list(transform.translation)


def entrances(scene, boys):
    records = []
    buildings = {b["id"]: b for b in PLAN["buildings"]}

    def add(bid, suffix, label, center, outward, width=2.2, base=.30, height=2.45):
        records.append({"id": bid + suffix, "building": bid, "label": label,
                        "center": list(center), "outward": list(outward.normalized()),
                        "width": width, "height": height, "base": base})

    for bid, count, base in (("B15", 2, .48), ("B21", 1, .64)):
        points = [world(p) for p in buildings[bid]["outline"]]
        tangent = (points[-1] - points[0]).normalized()
        outward = Vector((tangent.y, -tangent.x, 0))
        center = object_center(bid + " 门洞两侧门框")
        across = outward.cross(UP)
        for index, offset in enumerate((-1.84, 1.84) if count == 2 else (0,)):
            add(bid, "_" + str(index + 1), "致远楼" if bid == "B15" else "思远楼", center + across * offset, outward, 1.75 if count == 2 else 2.2, base)
        for name in ("门扇玻璃", "门扇细金属边", "门扇蓝色安全横条", "玻璃门拉手"):
            bpy.data.objects.remove(bpy.data.objects[bid + " " + name], do_unlink=True)

    for bid in ("B25", "B28"):
        points = [world(p) for p in buildings[bid]["outline"]]
        if bid == "B25":
            points = [boys @ point for point in points]
        tangent = (points[4] - points[3]).normalized()
        outward = Vector((tangent.y, -tangent.x, 0))
        center = object_center(bid + " 门框横梃")
        add(bid, "", "男生公寓·绅远楼" if bid == "B25" else "女生公寓·蕙远楼", center, outward, 1.50, .57)
        for name in ("开启的玻璃门扇", "开门扶手"):
            bpy.data.objects.remove(bpy.data.objects[bid + " " + name], do_unlink=True)

    library = buildings["B32"]["outline"]
    across = (world(library[7]) - world(library[8])).normalized()
    outward = Vector((across.y, -across.x, 0))
    center = object_center("入口深色门带")
    for index, offset in enumerate((-2.0, 2.0)):
        add("B32", "_" + str(index + 1), "图书馆", center + across * offset, outward, 2.2, 3.40)

    for bid in ("B36", "B45"):
        ring = buildings[bid]["outline"]
        a, b = world(ring[0]), world(ring[-1])
        across = (b - a).normalized()
        outward = Vector((across.y, -across.x, 0))
        add(bid, "", buildings[bid]["name"], (a + b) / 2 + outward * .22, outward, 2.2, .13)

    for name, bid, label in (("B40 入口玻璃门洞", "B40W", "艺远楼识远楼·西翼"),
                             ("B40 入口玻璃门洞.001", "B40E", "艺远楼识远楼·东翼"),
                             ("B09 入口玻璃门洞", "B09A", "体育建筑·西侧"),
                             ("B09 入口玻璃门洞.001", "B09B", "体育建筑·南侧")):
        center = object_center(name)
        if bid == "B09A":
            # The old west-facing placeholder opens into the spectator stand.
            # Use the open north-side path until a photographed door is available.
            add(bid, "", "体育建筑·北侧入口（估排）", world((325, 318)),
                world((325, 317)) - world((325, 318)), 2.3, .13)
            continue
        building_center = sum((world(p) for p in buildings[bid]["outline"]), Vector()) / len(buildings[bid]["outline"])
        outward = (center - building_center); outward.z = 0
        # The face normal comes from the thin axis of the existing entrance pane.
        mesh = bpy.data.objects[name]
        normal = mesh.matrix_world.to_3x3() @ mesh.data.polygons[0].normal
        normal.z = 0
        if normal.length < .5 or abs(normal.normalized().dot(outward.normalized())) < .7:
            ring = buildings[bid]["outline"]
            indices = (3, 2) if bid.startswith("B40") else ((0, 3) if bid == "B09A" else (1, 0))
            tangent = (world(ring[indices[1]]) - world(ring[indices[0]])).normalized()
            normal = Vector((tangent.y, -tangent.x, 0))
        if normal.dot(outward) < 0:
            normal = -normal
        add(bid, "", label, center, normal, 2.3, .30)

    a, b = world((567, 159.6)), world((392, 154.6))
    across = (b - a).normalized()
    outward = Vector((-across.y, across.x, 0))
    if outward.y > 0:
        across, outward = -across, -outward
    center = (a + b) / 2
    for index, offset in enumerate((-.31, .32)):
        add("B22", "_" + str(index + 1), "餐厅入口" if index == 0 else "餐厅出口", center + across * ((b - a).length * offset) + outward * .23, outward, 2.4, .545, 2.8)
    return records


def relocate_entrance_landscape(scene, records):
    """Rebuild the shared tree meshes with one whole tree and hedge relocated."""
    group = bpy.data.collections["公寓与运动区 · 树阵、菜株、圆篱"]
    white = next(obj.data.materials[0] for obj in group.objects if obj.name.startswith("树干刷白段"))
    for obj in list(group.objects):
        if obj.name.startswith(("庭院", "树干刷白段", "公寓与球场实拍树叶", "修剪绿篱")):
            bpy.data.objects.remove(obj, do_unlink=True)
    plant = Planting(scene)
    plant.group.name = "公寓门前 · 完整树篱移位"
    plant.palette["white"] = white
    leaves = []
    tree_points = ((653,151),(686,152),(718,151),(814,147),(856,147),(901,146),
                   (924,151),(968,146),(994,152),(974,78),(941,79),(898,78),
                   (849,78),(812,77),(708,77),(671,78),(563,170),(422,171),
                   (393,170),(393,215),(315,241),(335,241),(354,241),(380,241),
                   (302,108),(302,128),(302,148),(59,471),(82,476),(113,477),
                   (146,476),(178,476),(210,476),(237,476),(266,477),(62,96),
                   (95,93),(127,94),(163,92),(194,95))
    for x, y in tree_points:
        point = (699,156) if (x,y) == (686,152) else (x,y)
        tree(plant, point, 5.6 + (x % 6) * .32, "leaf", [], leaves)
    foliage_cards(plant.group, bpy.data.materials["三处庭院实拍 · 树叶"],
                  [(p,s*1.59,a) for p,s,a in leaves], "公寓与球场实拍树叶")
    for point in ((646,153),(687,151),(817,149),(899,149),(923,153),
                  (977,153),(398,164),(401,231),(306,246),(328,245),(354,244)):
        center = world((700,156) if point == (687,151) else point)
        for k in range(10):
            angle = k * 2.39996
            offset = Vector((math.cos(angle)*.60, math.sin(angle)*.62, .39+k%4*.09))
            plant.crown("修剪绿篱", "deep", center + offset, .46, .44, .47)
    plant.finish()
    moved = []
    hedges = []
    for record in records:
        if record["building"] not in {"B36", "B45"}:
            continue
        right = Vector(record["outward"]).cross(UP)
        for obj in scene.objects:
            if obj.name.startswith(record["building"] + " 分类桶"):
                obj.location += right * 4.0
                moved.append(obj.name)
        portal = frame(record["center"], Vector(record["outward"])).inverted()
        for obj in scene.objects:
            if obj.type != "MESH" or not obj.name.startswith("修剪绿篱"):
                continue
            mesh = obj.data
            adjacency = [set() for _ in mesh.vertices]
            for edge in mesh.edges:
                a, b = edge.vertices
                adjacency[a].add(b)
                adjacency[b].add(a)
            pending = set(range(len(mesh.vertices)))
            count = 0
            while pending:
                component = {pending.pop()}
                stack = list(component)
                while stack:
                    for neighbor in adjacency[stack.pop()]:
                        if neighbor in pending:
                            pending.remove(neighbor)
                            component.add(neighbor)
                            stack.append(neighbor)
                points = [portal @ obj.matrix_world @ mesh.vertices[i].co for i in component]
                if (min(p.x for p in points) < record["width"]/2 + .45
                        and max(p.x for p in points) > -record["width"]/2 - .45
                        and min(p.y for p in points) < 1.8 and max(p.y for p in points) > -3.0):
                    delta = obj.matrix_world.to_3x3().inverted() @ (right * 3.5)
                    for i in component:
                        mesh.vertices[i].co += delta
                    count += 1
            if count:
                mesh.update()
                hedges.append({"门": record["id"], "对象": obj.name, "整簇数": count})
    return {"整树像素移位": [[686,152],[699,156]], "绿篱像素移位": [[687,151],[700,156]],
            "完整垃圾桶移位对象": moved, "门侧整簇绿篱移位": hedges}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    scene = bpy.context.scene
    removed = []
    for collection in list(bpy.data.collections):
        if collection.name.startswith("绅远楼对面 · 黄梁玻璃连廊"):
            for obj in list(collection.objects):
                removed.append(obj.name)
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(collection)
    boys, correction = boys_transform(scene)
    bpy.context.view_layer.update()
    records = entrances(scene, boys)
    landscape = relocate_entrance_landscape(scene, records)
    bpy.context.view_layer.update()
    doors = bpy.data.collections.new("楼门 · 独立门轴与通行门洞")
    scene.collection.children.link(doors)
    mats = {"metal": bpy.data.materials["栏杆"], "glass": bpy.data.materials["浅灰蓝玻璃"],
            "blue": bpy.data.materials["蓝色公告栏与垃圾桶"], "floor": bpy.data.materials["灰色入口台阶"]}
    for record in records:
        add_door(scene, doors, record, mats)
        print("ENTRANCE", record["id"], "cuts", len(record["cut_objects"]), flush=True)
    bpy.context.view_layer.update()
    payload = {"source": str(SOURCE.relative_to(ROOT.parent)), "boys_correction": correction,
               "removed_duplicate_objects": removed, "doors": records, "landscape": landscape,
               "notes": "门轴默认打开90度；门洞与碰撞同步。B25地面位置和比例由照片估测，其他楼栋保留现有位置。"}
    (OUT / "楼门与公寓校正.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / (STEM + ".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT / (STEM + ".glb"))
    preview.OUT = OUT
    preview.publish_preview(scene)


if __name__ == "__main__":
    main()
