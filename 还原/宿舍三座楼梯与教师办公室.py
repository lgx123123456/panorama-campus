"""Continue the shared campus master with the user's stair and office corrections."""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

import 宿舍整栋贴合与北侧楼梯 as dorm
import 教学楼室内贴合与公寓西北楼梯 as school
import 教室与男女生公寓室内 as interior
import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
from 校园透明玻璃 import prepare_web_glass


OUT = doors.ROOT / "成果/宿舍三梯厕所与教师办公室"
STEM = "校园_宿舍三梯厕所与教师办公室"
END_BAYS = (("west", -42.70, -35.40, -39.30, 1),
            ("east", 40.90, 48.20, 44.50, -1))
TOILET_BAYS = (("west", -35.40, -28.80), ("east", 34.30, 40.90))


def materials():
    result = {key: bpy.data.materials["校园室内 · "+key] for key in
              ("plaster", "ceiling", "base", "silver", "metal", "lamp", "grid",
               "blue", "dark", "plastic", "wood", "paper", "marble")}
    result["hall_floor"] = bpy.data.materials["公寓灰色地砖"]
    result["wall_tile"] = bpy.data.materials["大厅米色墙砖"]
    result["school_floor"] = bpy.data.materials["教学楼道浅灰地砖"]
    return result


def mark_collision(group, prefix):
    for obj in group.all_objects:
        if not obj.name.startswith("CampusDoor") and not obj.name.startswith(prefix):
            obj.name = prefix+obj.name
        if obj.type == "MESH" and len(obj.data.uv_layers) < 2:
            obj.data.uv_layers.new(name="WalkableCollision")


def point(matrix, xyz):
    return list(matrix @ Vector(xyz))


def stair_layout(frame):
    central = (Matrix.Translation(frame @ Vector((-22.20, 6.10, 0)))
               @ Matrix.Rotation(-math.pi/2, 4, "Z")
               @ Matrix.Diagonal((1.20, 1.12, 1, 1)))
    end_stairs = []
    for side, start, end, y, approach in END_BAYS:
        stair = (Matrix.Translation(frame @ Vector((-8.10, y, 0)))
                 @ Matrix.Diagonal((1.15, 1.05, 1, 1)))
        end_stairs.append((side, start, end, approach, stair))
    return {"central_stair": central, "central_door_y": 5.20,
            "south_rooms": ((-28.80, -5.30), (5.30, 34.30)),
            "extra_shafts": [(frame.inverted() @ stair, (-1.34, .50), (1.34, 4.85))
                             for _, _, _, _, stair in end_stairs]}, end_stairs


def add_end_stairs(scene, frame, outline, definitions, mats):
    root = next(c for c in bpy.data.collections if c.name.startswith("B25 绅远楼（男生公寓）"))
    records = []
    for side, start, end, approach, transform in definitions:
        group = interior.collection("B25 宿舍贴合室内 南侧"+side+"端楼梯", root)
        mesh = interior.new_mesh(scene, group, mats)
        b = mesh.box
        local = frame.inverted() @ transform
        routes, paths = [], []
        for floor, z in enumerate(interior.FLOOR_Z):
            mesh.section(f"B25 宿舍贴合室内 {side}端楼梯 {floor+1:02d}F")
            # The well's first approach faces south. Its side aisle joins the long corridor.
            for x in (-1.43, 1.43):
                interior.wall(b, "wall_tile", x, -.25, 4.98, z, interior.DORM_HEIGHT)
            interior.endwall(b, "wall_tile", 4.98, -1.43, 1.43, z, interior.DORM_HEIGHT)
            interior.endwall(b, "wall_tile", -.25, -1.43, -1.28, z, interior.DORM_HEIGHT)
            interior.endwall(b, "wall_tile", -.25, 1.28, 1.43, z, interior.DORM_HEIGHT)
            interior.endwall(b, "wall_tile", -.25, -1.28, 1.28, z+2.40, .23)
            b("楼梯间吸顶灯", "lamp", 0, -.55, z+2.52, 1.0, .24, .04)
            b("楼梯南向入口标志", "blue", 0, -.29, z+2.50, .85, .03, .12)
            side_x = approach*2.10
            join = local @ Vector((side_x, 5.35, z))
            paths.append([point(frame, (dorm.CENTER, join.y, z)),
                          point(transform, (side_x, 5.35, z)),
                          point(transform, (side_x, -.90, z)),
                          point(transform, (-.62, -.75, z))])
            if floor == len(interior.FLOOR_Z)-1:
                continue
            rise = interior.FLOOR_Z[floor+1]-z
            interior.stair(mesh, 0, 0, z, rise)
            depth = .280 if rise > 3 else .268
            mid = .50+math.ceil(rise/.34)*depth+.60
            points = ((-.62,-.75,z),(-.62,.38,z),(-.62,mid,z+rise/2),
                      (.62,mid,z+rise/2),(.62,.38,z+rise),(.62,-.75,z+rise),(-.62,-.75,z+rise))
            routes.append({"from_floor": floor+1, "to_floor": floor+2,
                           "points": [point(transform, p) for p in points]})
        mesh.finish()
        interior.move_collection(group, transform)
        ends = interior.new_mesh(scene, group, mats)
        for floor, z in enumerate(interior.FLOOR_Z):
            ends.section(f"B25 宿舍贴合室内 {side}梯间与宿舍分界 {floor+1:02d}F")
            for y in (start, end):
                outer = dorm.width_at(outline, y)[1]
                interior.endwall(ends.box, "wall_tile", y, dorm.SOUTH, outer, z, interior.DORM_HEIGHT)
        before = set(group.all_objects)
        ends.finish()
        for obj in set(group.all_objects)-before:
            obj.matrix_world = frame @ obj.matrix_world
        mark_collision(group, "B25 宿舍贴合室内 ")
        records.append({"building": "B25", "side": side, "levels": list(interior.FLOOR_Z),
                        "routes": routes, "corridor_paths": paths,
                        "entrance_side": "south", "first_flight_direction": [0,1,0],
                        "flight_clear_width": 1.17*1.15,
                        "bay": [start, end], "stair_frame": [list(row) for row in transform]})
    return records


def toilet_fixtures(mesh, outline, y0, y1, z):
    b = mesh.box
    center = (y0+y1)/2
    # Each enlarged bay has four cubicles and a separate row of washbasins.
    for y in (y0, y1):
        interior.endwall(b, "wall_tile", y, dorm.SOUTH, dorm.width_at(outline,y)[1], z, interior.DORM_HEIGHT)
    interior.wall(b, "wall_tile", dorm.SOUTH, y0, center-.75, z, interior.DORM_HEIGHT)
    interior.wall(b, "wall_tile", dorm.SOUTH, center+.75, y1, z, interior.DORM_HEIGHT)
    interior.wall(b, "wall_tile", dorm.SOUTH, center-.75, center+.75, z+2.35, .28)
    b("卫生间入口标志", "blue", dorm.SOUTH-.08, center, z+2.47, .04, .80, .16)
    for index in range(4):
        a = y0+.30+index*(y1-y0-.60)/4
        c = y0+.30+(index+1)*(y1-y0-.60)/4
        y = (a+c)/2
        outer = min(dorm.width_at(outline,a)[1],dorm.width_at(outline,c)[1])-.20
        front = outer-3.05
        for edge in (a,c):
            interior.endwall(b, "plastic", edge, front, dorm.width_at(outline,edge)[1]-.15, z+.15, 2.0, .07)
        interior.wall(b, "plastic", front, a, y-.48, z+.15, 2.0, .07)
        interior.wall(b, "plastic", front, y+.48, c, z+.15, 2.0, .07)
        # Door leaves are recessed into cubicles with a clear central aisle.
        b("厕位门扇", "plastic", front+.58, y-.47, z+1.12, 1.05, .065, 1.94)
        b("洁具水箱", "marble", outer-.42, y, z+.72, .30, .58, .56)
        b("洁具底座", "marble", outer-.84, y, z+.20, .56, .43, .40)
        b("坐便器陶瓷边", "marble", outer-.90, y, z+.43, .72, .54, .13)
        b("坐便器内槽", "dark", outer-.90, y, z+.50, .40, .30, .01)
    for y in (y0+1.10, y0+2.15, y1-1.10):
        b("洗手台石台面", "marble", -11.45, y, z+.82, 1.05, .86, .12)
        b("洗手盆内槽", "dark", -11.45, y, z+.885, .60, .53, .015)
        b("洗手盆陶瓷底", "marble", -11.45, y, z+.895, .46, .39, .012)
        b("水龙头", "silver", -11.10, y, z+1.01, .045, .045, .25)
    b("卫生间吸顶灯", "lamp", -10.5, center, z+2.55, 1.40, .30, .04)


def add_toilets(scene, frame, outline, mats):
    root = next(c for c in bpy.data.collections if c.name.startswith("B25 绅远楼（男生公寓）"))
    group = interior.collection("B25 宿舍贴合室内 两端扩大卫生间", root)
    mesh = interior.new_mesh(scene, group, mats)
    records = []
    for side, y0, y1 in TOILET_BAYS:
        paths = []
        for floor,z in enumerate(interior.FLOOR_Z):
            mesh.section(f"B25 宿舍贴合室内 {floor+1:02d}F {side}侧卫生间")
            toilet_fixtures(mesh, outline, y0, y1, z)
            center = (y0+y1)/2
            paths.append([point(frame,(dorm.CENTER,center,z)),point(frame,(dorm.SOUTH+1.65,center,z))])
        records.append({"building":"B25","side":side,"bay":[y0,y1],
                        "width_metres":(y1-y0)*frame.to_3x3().col[1].length,
                        "cubicles_per_floor":4,"paths":paths})
    mesh.finish()
    interior.move_collection(group,frame)
    mark_collision(group,"B25 宿舍贴合室内 ")
    return records


def door_materials(mats):
    return {"metal":mats["metal"],"glass":bpy.data.materials["浅灰蓝玻璃"],
            "blue":mats["blue"],"floor":mats["hall_floor"]}


def clear_dorm_ramp_walls(scene, record):
    outward=Vector(record["outward"])
    opening=doors.frame(Vector(record["center"])+outward*3.10,outward)
    opening.translation.z=.10
    facades={obj for group in bpy.data.collections
             if group.name.startswith(("B25 ","B28 ")) and "外墙" in group.name
             for obj in group.all_objects if obj.type=="MESH"}
    changed=doors.cut_portal(scene,opening,record["width"]+.20,2.95,"端门坡道接地",
                             depth=2.90,outside=0,extra_objects=facades)
    for name in changed:
        obj=bpy.data.objects[name]
        if len(obj.data.uv_layers)<2:
            obj.data.uv_layers.new(name="WalkableCollision")
        if "贴合室内" not in obj.name:
            obj.name="B25 贴合室内 端门洞口 "+obj.name
    record["cut_objects"].extend(changed)


def add_dorm_end_doors(scene, payload, frame, outline, mats):
    bpy.context.view_layer.update()
    group = interior.collection("B25 两端出入口与门外坡道",scene.collection)
    center = sum(outline,Vector())/len(outline)
    intersections = []
    for a,b in zip(outline,outline[1:]+outline[:1]):
        if min(a.x,b.x) <= dorm.CENTER < max(a.x,b.x):
            t = (dorm.CENTER-a.x)/(b.x-a.x)
            local = a+(b-a)*t
            world_a,world_b = frame@a,frame@b
            tangent = (world_b-world_a).normalized()
            outward = Vector((tangent.y,-tangent.x,0))
            if outward.dot(frame@local-frame@center) < 0:
                outward = -outward
            intersections.append((local, outward.normalized()))
    intersections.sort(key=lambda item:item[0].y)
    records=[]
    for side,(local,outward) in zip(("west","east"),intersections):
        local.z=interior.FLOOR_Z[0]
        record={"id":"B25_"+side+"_end","building":"B25","label":"男生公寓"+("西" if side=="west" else "东")+"端门",
                "center":point(frame,local),"outward":list(outward),"width":1.75,"height":2.45,"base":local.z}
        doors.add_door(scene,group,record,door_materials(mats))
        opening=doors.frame(record["center"],outward)
        extras={obj for obj in scene.objects if obj.type=="MESH"}
        changed=doors.cut_portal(scene,opening,record["width"]+.10,record["height"],
                                 "B25",depth=3.20,outside=3.10,extra_objects=extras)
        record["cut_objects"].extend(changed)
        for name in changed:
            obj=bpy.data.objects[name]
            if len(obj.data.uv_layers)<2:
                obj.data.uv_layers.new(name="WalkableCollision")
            if "贴合室内" not in obj.name and not obj.name.startswith("Campus"):
                obj.name="B25 贴合室内 端门洞口 "+obj.name
        clear_dorm_ramp_walls(scene,record)
        payload["doors"].append(record)
        ramp=interior.new_mesh(scene,group,mats)
        ramp.section("B25 宿舍贴合室内 "+side+"端门接地坡道")
        ramp.polygons("入口连续缓坡","hall_floor",[(-1.05,.12,.57),(1.05,.12,.57),
                      (1.05,2.70,.13),(-1.05,2.70,.13)],[(0,1,2,3)])
        before=set(group.all_objects)
        ramp.finish()
        portal=doors.frame(record["center"],outward)
        portal.translation.z=0
        for obj in set(group.all_objects)-before:
            obj.matrix_world=portal
            obj.data.uv_layers.new(name="WalkableCollision")
        inside=Vector(record["center"])-outward*2
        outside=Vector(record["center"])+outward*2.50
        outside.z=.164
        records.append({"id":record["id"],"points":[list(outside),record["center"],list(inside)]})
    return records


def office_desk(mesh, x, y, z):
    b=mesh.box
    b("教师办公桌桌面","wood",x,y,z+.77,1.48,.76,.07)
    for dx in (-.64,.64):
        for dy in (-.29,.29):
            b("办公桌支腿","metal",x+dx,y+dy,z+.37,.05,.05,.74)
    b("办公电脑底座","dark",x,y+.12,z+.825,.34,.24,.04)
    b("办公电脑支架","metal",x,y+.16,z+1.0,.05,.05,.32)
    b("办公电脑屏幕","dark",x,y+.18,z+1.20,.62,.055,.39)
    b("显示器屏面","blue",x,y+.148,z+1.20,.57,.012,.33)
    b("办公键盘","dark",x,y-.17,z+.82,.43,.16,.025)
    b("桌面文件","paper",x+.49,y,z+.83,.23,.32,.07)
    b("办公椅座面","plastic",x,y-.82,z+.47,.48,.48,.09)
    b("办公椅靠背","plastic",x,y-1.04,z+.80,.48,.07,.58)
    for dx in (-.19,.19):
        for dy in (-1.01,-.63):
            b("办公椅椅腿","metal",x+dx,y+dy,z+.22,.035,.035,.44)


def add_offices(scene,payload,bid,spaces,mats):
    frame=interior.Frame(bid,False).matrix
    root=next(c for c in bpy.data.collections if c.name.startswith(bid+" ") and "贴合楼体室内" in c.name)
    group=interior.collection(bid+" 贴合室内 教师办公室",root)
    mesh=interior.new_mesh(scene,group,mats)
    records=[]
    base=.48 if bid=="B15" else .64
    levels=(base,4.32,8.04,11.76,15.48)
    bridge=[r for r in payload["doors"] if r["building"]==bid and "bridge" in r]
    entry_low=min((frame.inverted()@Vector(r["center"])).y for r in bridge)-.35
    entry_high=max((frame.inverted()@Vector(r["center"])).y for r in bridge)+.35
    entry_z=bridge[0]["base"]
    for index,space in enumerate(spaces):
        x0,x1,y0,y1=space["bounds"]
        for floor,z in enumerate(levels):
            mesh.section(f"{bid} 贴合室内 {floor+1:02d}F 教师办公室 {index+1}")
            # Desks face a central circulation aisle. Furniture stays clear of each door.
            if space["door_side"]=="south":
                for x in (x0+1.30,x0+3.50,x0+5.70,x0+7.90):
                    office_desk(mesh,x,y1-.70,z)
                local=(x1,(y0+y1)/2,z)
                normal=(1,0,0)
                hall_z=z if floor else base+(entry_z-base)*(local[1]-78)/(entry_low-78)
                path=[(5.45,local[1],hall_z),(4.60,local[1],hall_z),local,(x1-1.25,local[1],z)]
                if not floor:
                    mesh.polygons("办公室门前缓坡","school_floor",
                                  [(x1,local[1]-.72,z),(4.60,local[1]-.72,hall_z),
                                   (4.60,local[1]+.72,hall_z),(x1,local[1]+.72,z)],[(0,1,2,3)])
            else:
                for x in (x0+1.25,x0+3.65):
                    for y in (y0+2.30,y1-.75):
                        office_desk(mesh,x,y,z)
                local=((x0+x1)/2,y0,z)
                normal=(0,-1,0)
                approach_z=z
                if not floor:
                    knots=((78.0,base),(entry_low,entry_z),(entry_high,entry_z),(y0,base))
                    approach_y=y0-1.10
                    for (a,za),(b,zb) in zip(knots,knots[1:]):
                        if a <= approach_y <= b:
                            approach_z=za+(zb-za)*(approach_y-a)/(b-a)
                            break
                    mesh.polygons("办公室门外连续缓坡","school_floor",
                                  [(local[0]-.64,approach_y,approach_z),(local[0]+.64,approach_y,approach_z),
                                   (local[0]+.64,y0,z),(local[0]-.64,y0,z)],[(0,1,2,3)])
                path=[(local[0],y0-1.1,approach_z),local,(local[0],y0+1.1,z)]
            mesh.box("办公室吸顶灯","lamp",(x0+x1)/2,(y0+y1)/2,z+2.98,1.20,.30,.05)
            mesh.box("办公室资料柜","wood",x0+.42,y0+1.5,z+1.0,.60,1.0,2.0)
            record={"id":f"{bid}_office_{index+1}_{floor+1}","building":bid,
                    "label":("致远楼" if bid=="B15" else "思远楼")+f"{floor+1}层教师办公室{index+1}",
                    "center":point(frame,local),"outward":list((frame.to_3x3()@Vector(normal)).normalized()),
                    "width":1.22 if index==0 else 1.04,"height":2.30,"base":z,"office":True}
            records.append({"door":record,"path":[point(frame,p) for p in path],
                            "floor":floor+1,"space":index+1,"desk_count":4,"bounds":space["bounds"]})
    for office in records:
        record=office["door"]
        doors.add_door(scene,group,record,door_materials(mats))
        landing=bpy.data.objects.get("CampusEntryLanding_"+record["id"])
        if landing:
            bpy.data.objects.remove(landing,do_unlink=True)
        payload["doors"].append(record)
        office["door_id"]=record["id"]
        del office["door"]
    before=set(group.all_objects)
    mesh.finish()
    for obj in set(group.all_objects)-before:
        obj.matrix_world=frame @ obj.matrix_world
        if len(obj.data.uv_layers)<2:
            obj.data.uv_layers.new(name="WalkableCollision")
    return {"building":bid,"offices":records,"basis":"用户确认东侧楼梯左侧空区为教师办公室，房间隔墙贴合楼体，门接楼道，办公桌与尺寸按现有空区估排。"}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(school.SOURCE),load_ui=False)
    payload=json.loads((school.SOURCE.parent/"楼门与公寓校正.json").read_text(encoding="utf8"))
    scene=bpy.context.scene
    frame=dorm.previous.current_frame()
    layout,definitions=stair_layout(frame)
    record=dorm.rebuild(scene,payload,layout)
    record["first_flight_direction"]=[1,0,0]
    record["flight_clear_width"]=1.17*1.20
    record["basis"]="2026-11-16用户最新确认北侧中梯首跑朝东，南侧两端各有南北向楼梯、南向入口及内侧扩大卫生间，楼栋最西端与最东端补门。按整栋楼壳贴合排布，梯宽、房间数量和洁具布置按现有空间估排。"
    payload["dorm_lobby_stairs"]=record
    outline=[Vector(p) for p in record["outline"]]
    mats=materials()
    payload["dorm_end_stairs"]=add_end_stairs(scene,frame,outline,definitions,mats)
    payload["dorm_toilets"]=add_toilets(scene,frame,outline,mats)
    payload["dorm_end_doors"]=add_dorm_end_doors(scene,payload,frame,outline,mats)
    links,east,west,fits,offices=[],[],[],[],[]
    for bid in ("B15","B21"):
        link,stairs,fit=school.rebuild_school(scene,payload,bid,enlarge=True,offices=True)
        links.append(link)
        west.append(stairs[0])
        east.append(stairs[1])
        fits.append(fit)
        fit["basis"]="用户确认北侧教室、南侧楼道，东西两端楼梯加宽；东梯左侧空区为教师办公室。教室数量、楼梯尺寸、办公室分隔与家具按现有楼壳估排。"
        offices.append(add_offices(scene,payload,bid,fit["office_spaces"],mats))
    payload["teaching_bridge_entries"]["corridors"]=links
    payload["teaching_west_stairs"]={"buildings":west}
    payload["teaching_east_stairs"]={"buildings":east}
    payload["teaching_interior_fit"]=fits
    payload["teaching_offices"]=offices
    payload["source"]=str(OUT/(STEM+".blend"))
    (OUT/"楼门与公寓校正.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf8")
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" in sys.argv:
        return
    prepare_web_glass(preview.active_glass())
    preview.export_asset(OUT/(STEM+".glb"))
    preview.OUT=OUT
    preview.publish_preview(scene)


if __name__=="__main__":
    main()
