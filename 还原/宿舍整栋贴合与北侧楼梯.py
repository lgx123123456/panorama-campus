"""Fit the boys' dormitory to its complete shell and enter its stairs from the north row."""
import json
import math
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

import 公寓大厅右侧楼梯 as previous
import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
import 教室与男女生公寓室内 as interior
from 校园透明玻璃 import prepare_web_glass


SOURCE = doors.ROOT / "成果/教学楼室内贴合与公寓西北楼梯/校园_教学楼贴合与公寓西北楼梯.blend"
CLEAN = doors.OUT / (doors.STEM + ".blend")
OUT = doors.ROOT / "成果/宿舍整栋贴合与北侧楼梯"
STEM = "校园_宿舍整栋贴合与北侧楼梯"
BID = "B25"
NORTH, SOUTH = -17.80, -15.00
CENTER = (NORTH + SOUTH) / 2
STAIR_BAND = (3.80, 13.20)
LOBBY_BACK = -7.80


def restore_shell(scene):
    with bpy.data.libraries.load(str(CLEAN), link=False) as (available, loaded):
        names = [name for name in available.collections
                 if name.startswith(("B25 绅远楼 · 外墙", "B25 屋面设备间"))]
    for name in names:
        old = bpy.data.collections.get(name)
        if old:
            for obj in tuple(old.all_objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(old)
    with bpy.data.libraries.load(str(CLEAN), link=False) as (available, loaded):
        loaded.collections = names
    for group in loaded.collections:
        scene.collection.children.link(group)
    # Loaded façade objects need evaluated world transforms before portal clipping.
    bpy.context.view_layer.update()


def width_at(outline, y):
    xs = [a.x+(b.x-a.x)*(y-a.y)/(b.y-a.y)
          for a, b in zip(outline, outline[1:]+outline[:1])
          if min(a.y, b.y) <= y < max(a.y, b.y)]
    return min(xs), max(xs)


def inset_outline(points, distance):
    centroid = sum(points, Vector()) / len(points)
    edges = []
    for a, b in zip(points, points[1:]+points[:1]):
        direction = (b-a).normalized()
        normal = Vector((-direction.y, direction.x, 0))
        if normal.dot(centroid-a) < 0:
            normal = -normal
        edges.append((a+normal*distance, direction))
    result = []
    for (a, u), (b, v) in zip(edges[-1:]+edges[:-1], edges):
        delta = b-a
        t = (delta.x*v.y-delta.y*v.x)/(u.x*v.y-u.y*v.x)
        result.append(a+u*t)
    return result


def subtract_rectangle(polygon, transform, low, high):
    """Keep the polygon fragments outside a rectangle, including rotated stair openings."""
    inverse = transform.inverted()
    inside = [(inverse @ p, []) for p in polygon]
    outside = []
    for axis in range(2):
        part, inside = doors.split_polygon(inside, axis, low[axis])
        if len(part) >= 3:
            outside.append([transform @ p for p, _ in part])
        if len(inside) < 3:
            break
        inside, part = doors.split_polygon(inside, axis, high[axis])
        if len(part) >= 3:
            outside.append([transform @ p for p, _ in part])
        if len(inside) < 3:
            break
    return outside


def floor_plate(mesh, outline, z, thickness, holes, key="hall_floor"):
    polygons = [[Vector((p.x, p.y, z)) for p in outline]]
    for transform, low, high in holes:
        polygons = [piece for polygon in polygons
                    for piece in subtract_rectangle(polygon, transform, low, high)]
    for polygon in polygons:
        count = len(polygon)
        points = polygon + [p-Vector((0, 0, thickness)) for p in polygon]
        # Outlines are clockwise. Reverse the top so collision normals face upward.
        area = sum(a.x*b.y-b.x*a.y for a,b in zip(polygon,polygon[1:]+polygon[:1]))
        top = tuple(range(count)) if area > 0 else tuple(reversed(range(count)))
        faces = [top]
        faces.extend((i, (i+1)%count, (i+1)%count+count, i+count) for i in range(count))
        mesh.polygons("完整贴壳楼板", key, points, faces)
        mesh.polygons("连续白色顶棚", "ceiling", points,
                      [tuple(i+count for i in reversed(top))])


def connected_parts(data):
    """Classify connected furniture pieces so room-depth fitting preserves furniture sizes."""
    parents = list(range(len(data.vertices)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for edge in data.edges:
        a, b = (root(index) for index in edge.vertices)
        parents[b] = a
    parts = {}
    for vertex in data.vertices:
        parts.setdefault(root(vertex.index), []).append(vertex.index)
    materials = {}
    for face in data.polygons:
        materials[root(face.vertices[0])] = data.materials[face.material_index].name
    result = []
    for indices in parts.values():
        coords = [data.vertices[index].co.copy() for index in indices]
        lo = Vector(tuple(min(p[axis] for p in coords) for axis in range(3)))
        hi = Vector(tuple(max(p[axis] for p in coords) for axis in range(3)))
        center = (lo+hi)/2
        floor = hi.z < .03
        mode = "span" if hi.y-lo.y > 5.5 or floor else "rear" if center.y > 5.0 else "front" if center.y < .9 else "furniture"
        material = materials.get(root(indices[0]), "")
        bed = ("床品" in material or
               (material == "校园室内 · metal" and hi.z < 2.1 and abs(center.x) > .6) or
               (material in ("校园室内 · blue", "校园室内 · green") and center.y > 1))
        if bed:
            mode = "bed1" if center.y < 3.25 else "bed2"
        result.append((indices, coords, center, mode, hi.x-lo.x > 2.75 or floor))
    return result


def fitted_room(template, parts, outline, y0, y1, inner, side, name, outer=None):
    data = template.copy()
    data.name = name
    span = y1-y0
    for indices, coords, center, mode, span_width in parts:
        for index, point in zip(indices, coords):
            width_coord = point.x*span/interior.DORM_WIDTH if span_width else center.x*span/interior.DORM_WIDTH+point.x-center.x
            if mode.startswith("bed"):
                anchor = math.copysign(1.13, center.x)
                width_coord = anchor*span/interior.DORM_WIDTH+point.x-anchor
            y = (y0+y1)/2-side*width_coord
            edge = outer if outer is not None else width_at(outline, min(y1-.001, max(y0+.001,y)))[0 if side < 0 else 1]
            depth = abs(edge-inner)
            if mode == "span":
                distance = point.y/interior.DORM_DEPTH*depth
            elif mode == "rear":
                distance = depth+point.y-interior.DORM_DEPTH
            elif mode == "front":
                distance = point.y
            elif mode.startswith("bed"):
                anchor = 2.20 if mode == "bed1" else 4.30
                distance = point.y+(depth-interior.DORM_DEPTH)*(anchor-.9)/4.1
            else:
                distance = point.y+(depth-interior.DORM_DEPTH)*(center.y-.9)/4.1
            data.vertices[index].co = (inner+side*distance, y, point.z)
    if len(data.uv_layers) < 2:
        data.uv_layers.new(name="WalkableCollision")
    data.update()
    return data


def bands(start, end):
    count = max(1, round((end-start)/interior.DORM_WIDTH))
    return [(start+(end-start)*i/count, start+(end-start)*(i+1)/count) for i in range(count)]


def rebuild(scene, payload, layout=None):
    transform = previous.current_frame()
    outline = inset_outline(interior.Frame(BID, True).corners, .12)
    template = bpy.data.objects[BID+" 01-N01 宿舍样板"].data.copy()
    editable = bmesh.new()
    editable.from_mesh(template)
    bmesh.ops.delete(editable, geom=[face for face in editable.faces
                                   if template.materials[face.material_index].name == "校园室内 · ceiling"],
                     context="FACES")
    editable.to_mesh(template)
    editable.free()
    parts = connected_parts(template)
    root = next(c for c in bpy.data.collections if c.name.startswith(BID+" 绅远楼（男生公寓）"))
    for obj in tuple(root.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for group in tuple(root.children):
        bpy.data.collections.remove(group)
    restore_shell(scene)
    construction = interior.collection(BID+" 宿舍贴合室内 · 连续楼板与北侧楼梯", root)
    rooms = interior.collection(BID+" 宿舍贴合室内 · 贴壳房间", root)
    lights = interior.collection(BID+" 宿舍贴合室内 · 灯光", root)
    mats = {key: bpy.data.materials["校园室内 · "+key] for key in
            ("plaster","ceiling","base","silver","metal","lamp","grid","blue","dark",
             "plastic","wood","paper","plant","marble")}
    mats.update(hall_floor=bpy.data.materials["公寓灰色地砖"],wall_tile=bpy.data.materials["大厅米色墙砖"],
                **{"26":bpy.data.materials["公寓大厅实拍横幅26"],"notice26":bpy.data.materials["公寓大厅实拍卡片26"]})
    mesh = interior.new_mesh(scene, construction, mats)
    b = mesh.box
    levels = interior.FLOOR_Z
    near, end = -42.70, 48.20
    stair_world = (layout["central_stair"] if layout else
                   Matrix.Translation(transform @ Vector((-20.70,9.80,0)))
                   @ Matrix.Rotation(math.pi/4,4,"Z"))
    stair_local = transform.inverted() @ stair_world
    shaft = (stair_local, (-1.34,.50), (1.34,4.85)) if layout else (stair_local, (-1.29,.50), (1.29,4.78))
    shafts = [shaft] + (layout["extra_shafts"] if layout else [])
    door_y = layout["central_door_y"] if layout else 11.50
    gallery_hole = (Matrix.Identity(4), (-5.60,-3.50), (.10,3.50))
    normal_rooms = []
    for side, inner in ((-1,NORTH),(1,SOUTH)):
        south_ranges = layout["south_rooms"] if layout else ((near,-5.30),(5.30,end))
        ranges = ((near,STAIR_BAND[0]),(STAIR_BAND[1],end)) if side < 0 else south_ranges
        for start, stop in ranges:
            for y0,y1 in bands(start,stop):
                normal_rooms.append((side,inner,y0,y1))
    room_meshes = []
    for index,(side,inner,y0,y1) in enumerate(normal_rooms):
        data = fitted_room(template,parts,outline,y0,y1,inner,side,f"宿舍贴壳共享房间 {index+1}")
        room_meshes.append((data,side,(y0+y1)/2))
    front_rooms = [fitted_room(template,parts,outline,y0,y1,LOBBY_BACK,-1,
                              f"大厅正面贴合宿舍 {index+1}",outer=SOUTH)
                   for index,(y0,y1) in enumerate(((-3.5,0),(0,3.5)))]
    upper_rooms = [fitted_room(template,parts,outline,y0,y1,SOUTH,1,
                              f"高层中央贴合宿舍 {index+1}")
                   for index,(y0,y1) in enumerate(((-3.5,0),(0,3.5)))]
    routes, joins, corridor_paths, room_checks = [], [], [], []
    stair_objects = set()

    def point(x,y,z):
        return list(transform @ Vector((x,y,z)))

    def stair_point(x,y,z):
        return list(stair_world @ Vector((x,y,z)))

    def north_door(z):
        return [point(CENTER,door_y,z),point(NORTH-.25,door_y,z),stair_point(-.62,-.75,z)]

    for floor,z in enumerate(levels):
        mesh.section(f"{BID} 宿舍贴合室内 {floor+1:02d}F 整栋连续楼板")
        depth = .24 if floor == 0 else z-(levels[floor-1]+interior.DORM_HEIGHT)
        holes = list(shafts) if floor else []
        if floor == 1:
            holes.append(gallery_hole)
        floor_plate(mesh,outline,z,depth,holes)
        if floor == len(levels)-1:
            floor_plate(mesh,outline,z+interior.DORM_HEIGHT+.04,.04,[],"ceiling")
        # Close the tapered ends around the full-width corridor.
        for y in (near,end):
            lo,hi = width_at(outline,y)
            interior.endwall(b,"plaster",y,lo,hi,z,interior.DORM_HEIGHT)
        for data,side,y in room_meshes:
            obj = bpy.data.objects.new(f"{BID} 宿舍贴合室内 {floor+1:02d}F {'北' if side < 0 else '南'}侧宿舍 {y:.2f}",data)
            rooms.objects.link(obj)
            obj.matrix_world = transform @ interior.translate(0,0,z)
        for index,data in enumerate(front_rooms if floor < 2 else upper_rooms):
            obj = bpy.data.objects.new(f"{BID} 宿舍贴合室内 {floor+1:02d}F 中央宿舍 {index+1}",data)
            rooms.objects.link(obj)
            obj.matrix_world = transform @ interior.translate(0,0,z)
        # Side passages tightly wrap the two lobby-facing dorms and reach the main corridor.
        for y in (-5.30,5.30):
            exterior = width_at(outline,y)[1]
            interior.endwall(b,"plaster",y,SOUTH,exterior,z,interior.DORM_HEIGHT)
        if floor < 2:
            interior.wall(b,"plaster",SOUTH,-3.50,3.50,z,interior.DORM_HEIGHT)
        # Northern stair entrance is a real opening in the north dormitory row.
        interior.wall(b,"wall_tile",NORTH,STAIR_BAND[0],door_y-1.20,z,interior.DORM_HEIGHT)
        interior.wall(b,"wall_tile",NORTH,door_y+1.20,STAIR_BAND[1],z,interior.DORM_HEIGHT)
        interior.wall(b,"wall_tile",NORTH,door_y-1.20,door_y+1.20,z+2.40,.23)
        for y in STAIR_BAND:
            exterior = width_at(outline,y)[0]
            interior.endwall(b,"wall_tile",y,exterior,NORTH,z,interior.DORM_HEIGHT)
        for yy in range(-40,48,5):
            b("连续楼道吸顶灯","lamp",CENTER,yy,z+2.56,.30,1.10,.05)
            interior.overhead(scene,lights,interior.Frame(BID,True),"贴合楼道灯",CENTER,yy,z+2.45,75,1.5)
        b("北侧楼梯入口绿标","blue",NORTH+.08,door_y,z+2.51,.04,.85,.14)
        joins.append(point(CENTER,door_y,z))
        corridor_paths.append(list(reversed(north_door(z))))
        room = next(item for item in normal_rooms if item[0] == -1 and item[2] > 13.2)
        south_room = next(item for item in normal_rooms if item[0] == 1 and item[2] > 5.3)
        checks = []
        for side,inner,y0,y1 in (room,south_room):
            y=(y0+y1)/2
            checks.append([point(CENTER,y,z),point(inner+side*1.2,y,z),point(CENTER,y,z)])
        room_checks.append(checks)
        if floor < len(levels)-1:
            stair_mesh = interior.new_mesh(scene,construction,mats)
            stair_mesh.section(f"{BID} 宿舍贴合室内 北侧楼梯 {floor+1:02d}F 至 {floor+2:02d}F")
            rise=levels[floor+1]-z
            interior.stair(stair_mesh,0,0,z,rise)
            before = set(construction.all_objects)
            stair_mesh.finish()
            for obj in set(construction.all_objects)-before:
                obj.matrix_world = stair_world @ obj.matrix_world
                stair_objects.add(obj)
            step_depth=.280 if rise>3 else .268
            mid=.5+math.ceil(rise/.34)*step_depth+.60
            route=((- .62,-.75,z),(-.62,.38,z),(-.62,mid,z+rise/2),
                   (.62,mid,z+rise/2),(.62,.38,z+rise),(.62,-.75,z+rise),(-.62,-.75,z+rise))
            routes.append({"from_floor":floor+1,"to_floor":floor+2,
                           "points":[stair_point(*p) for p in route]})
    mesh.finish()
    # Transform shared floor and wall geometry once. Stairs were authored in physical metres.
    for obj in tuple(construction.all_objects):
        if obj not in stair_objects:
            obj.matrix_world = transform @ obj.matrix_world
        obj.name = BID+" 宿舍贴合室内 "+obj.name
        if obj.type == "MESH" and len(obj.data.uv_layers) < 2:
            obj.data.uv_layers.new(name="WalkableCollision")
    # The photo-based lobby remains double height, with two complete rooms in front.
    lobby = interior.new_mesh(scene,construction,mats)
    before=set(construction.all_objects)
    lobby.section(BID+" 宿舍贴合室内 实拍挑空大厅")
    interior.lobby(lobby,LOBBY_BACK,levels[0],"26")
    lobby.groups.pop("楼道纵墙",None)
    lobby.groups.pop("门厅二层挑空顶板",None)
    lobby.finish()
    for obj in set(construction.all_objects)-before:
        if "大厅挑台" in obj.name or "大厅实拍迎新横幅" in obj.name:
            for vertex in obj.data.vertices:
                vertex.co.x += 2.20
        obj.matrix_world=transform @ obj.matrix_world
        obj.name=BID+" 宿舍贴合室内 "+obj.name
        if obj.type == "MESH" and len(obj.data.uv_layers)<2:
            obj.data.uv_layers.new(name="WalkableCollision")
    notice = bpy.data.materials.get("男公寓大厅正面实拍公示板")
    if notice:
        detail = interior.new_mesh(scene,construction,{"notice":notice})
        detail.panel_group = BID+" 宿舍贴合室内 两门之间公示板"
        obj = detail.panel("两间宿舍之间的实拍公示板","notice",(LOBBY_BACK+.015,0,2.12),
                           (0,1,0),(0,0,1),1.5,1.6)
        obj.matrix_world=transform
        obj.data.uv_layers.new(name="WalkableCollision")
    # Open side passages through the photo lobby's side walls on both gallery levels.
    for z in levels[:2]:
        for y in (-3.70,3.70):
            opening=transform @ interior.translate(-6.55,y+.18,z-.025)
            doors.cut_portal(scene,opening,2.20,2.65,BID,depth=.38,outside=0)
    # Reopen the existing exterior doorway after restoring the façade.
    for record in (r for r in payload["doors"] if r["building"]==BID):
        doors.cut_portal(scene,doors.frame(record["center"],Vector(record["outward"])),
                         record["width"]+.08,2.60,BID,depth=1.0)
    # Lights share the same footprint correction as the exterior shell.
    correction=transform @ interior.Frame(BID,True).matrix.inverted()
    for obj in lights.all_objects:
        obj.matrix_world=correction @ obj.matrix_world
    lobby_route=[point(-.60,0,levels[0]),point(-6.55,0,levels[0]),
                 point(-6.55,4.40,levels[0]),point(CENTER,4.40,levels[0])]
    lobby_route.extend(north_door(levels[0]))
    return {"building":BID,"levels":list(levels),"routes":routes,"corridor_points":joins,
            "corridor_paths":corridor_paths,"lobby_route":lobby_route,
            "corridor_end_routes":[[point(CENTER,y,z) for y in (near+1,0,end-1)] for z in levels],
            "room_checks":room_checks,"outline":[list(p) for p in outline],
            "building_frame":[list(row) for row in transform],"stair_frame":[list(row) for row in stair_world],
            "first_flight_direction":[-.70710678,.70710678,0],"entrance_side":"north",
            "rooms_per_floor":len(normal_rooms)+2,
            "basis":"2026-11-16用户指出宿舍未贴楼壳、有中空和楼梯入口错乱，确认楼梯从北侧宿舍一侧进入。按整栋外墙轮廓重排连续房间和全覆盖楼板；北侧楼梯留出独立门洞，首跑朝西北。保留大厅正面两间宿舍及绕行通道。房间数、房深、梯间尺寸依现有外壳估排。"}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE),load_ui=False)
    payload=json.loads((SOURCE.parent/"楼门与公寓校正.json").read_text(encoding="utf8"))
    payload["dorm_lobby_stairs"]=rebuild(bpy.context.scene,payload)
    (OUT/"楼门与公寓校正.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf8")
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT/(STEM+".glb"))
    preview.OUT=OUT
    preview.publish_preview(bpy.context.scene)


if __name__=="__main__":
    main()
