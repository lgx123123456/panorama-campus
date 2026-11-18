"""Fit both dormitory layouts to the verified exterior footprints and the supplied sketch."""
import json
import math
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

import 公寓大厅右侧楼梯 as prior
import 公寓门位与重复连廊校正 as doors
import 地面补铺与预览优化 as preview
import 宿舍三座楼梯与教师办公室 as previous
import 宿舍整栋贴合与北侧楼梯 as fit
import 教室与男女生公寓室内 as interior
import 楼门封闭与广场球台 as latest
from 校园透明玻璃 import prepare_web_glass

OUT = latest.ROOT / "成果/男女宿舍布局重排"
STEM = "校园_男女宿舍布局重排"
LEVELS = interior.FLOOR_Z
HEIGHT = interior.DORM_HEIGHT
LOBBY = (-3.70, 3.70)


def range_on(shape, axis, value):
    line = ((value, -200), (value, 200)) if axis == "x" else ((-200, value), (200, value))
    cut = shape.intersection(LineString(line))
    if cut.is_empty:
        raise ValueError((axis, value, shape.bounds))
    x0,y0,x1,y1 = cut.bounds
    return (y0,y1) if axis == "x" else (x0,x1)


def frame_for(bid):
    model = interior.Frame(bid, True)
    source = prior.current_frame() if bid == "B25" else model.matrix
    y = source.to_3x3().col[1].normalized()
    x = Vector((y.y, -y.x, 0))
    frame = Matrix((x, y, Vector((0,0,1)))).transposed().to_4x4()
    frame.translation = source.translation
    shell = [frame.inverted() @ source @ p for p in model.corners]
    return frame, fit.inset_outline(shell,.09)


def special_bays(shape, north, south):
    # End flights face north. Set their positions from the usable depth of each
    # tapered end rather than copying the coordinates from the other building.
    xs = south+5.8
    west_limit,east_limit = range_on(shape,"x",xs+1.48)
    west,east = west_limit+2.08,east_limit-2.08
    west_inner,east_inner = west+3.52,east-3.52
    central = interior.translate(north-3.0,2.65,0) @ Matrix.Diagonal((1.2,1.1,1,1))
    stairs = {
        "mid": (central,(-1.20,8.60),1.55),
        "west": (interior.translate(xs,west,0) @ interior.rotation(math.pi/2)
                 @ Matrix.Diagonal((1.20,1.0,1,1)),(-200,west_inner),west+2.25),
        "east": (interior.translate(xs,east,0) @ interior.rotation(math.pi/2)
                 @ Matrix.Diagonal((1.20,1.0,1,1)),(east_inner,200),east-2.25),
    }
    return stairs, {"west": (west_inner,west_inner+6.35),"east": (east_inner-6.35,east_inner)}


def create_furniture(scene, root, bid, mats):
    stage = interior.collection(bid+" 家具制样",root)
    sample = interior.dorm_sample(scene,stage,mats,bid=="B28")
    objects = [o for c in sample.children if c.name.startswith(("钢制双层床","进门两组钢柜"))
               for o in c.objects]
    source = interior.joined_templates(stage,objects,bid+" 共享宿舍家具")[0]
    data = source.data
    for obj in list(stage.all_objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    for child in list(stage.children):
        for grandchild in list(child.children):
            bpy.data.collections.remove(grandchild)
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(stage)
    data.uv_layers.new(name="WalkableCollision")
    return data


def front_wall(b, x, a, c, middle, z, door=1.10, key="plaster"):
    if middle is None:
        if c-a>.02:
            interior.wall(b,key,x,a,c,z,HEIGHT)
        return
    left,right=middle-door/2,middle+door/2
    if left>a+.018:
        interior.wall(b,key,x,a,left,z,HEIGHT)
    if right<c-.018:
        interior.wall(b,key,x,right,c,z,HEIGHT)
    interior.wall(b,key,x,max(a,left),min(c,right),z+2.23,HEIGHT-2.23)


def partition(b, shape, inner, side, y, z, height=HEIGHT):
    a,c = range_on(shape,"y",y)
    start,end = (a,inner) if side<0 else (inner,c)
    if end-start>.04:
        interior.endwall(b,"plaster",y,start,end,z,height)


def floor_surface(m, label, key, polygon, z):
    from shapely import constrained_delaunay_triangles
    from shapely.geometry.polygon import orient
    for tri in constrained_delaunay_triangles(polygon).geoms:
        pts=[(x,y,z) for x,y in list(orient(tri,sign=1.0).exterior.coords)[:3]]
        m.polygons(label,key,pts,[(0,1,2)])


def row_rooms(shape, edge, side, special):
    y0,y1=range_on(shape,"x",edge)
    limits = sorted([y0,y1,*[max(y0,min(y1,n)) for lo,hi in special for n in (lo,hi)]])
    room_spans=[]
    for a,b in zip(limits,limits[1:]):
        if b-a<.025 or any(lo < (a+b)/2 < hi for lo,hi in special):
            continue
        if b-a<1.5:
            continue
        n=max(1,round((b-a)/3.6))
        room_spans.extend((a+(b-a)*i/n,a+(b-a)*(i+1)/n) for i in range(n))
    return room_spans


def room_details(mesh, shape, room, side, edge, a, b, z, leaf):
    box_fn=mesh.box
    y=(a+b)/2
    for sign in (-1,1):
        box_fn("宿舍木门竖框",leaf,edge+side*.075,y+sign*.556,z+1.125,.18,.045,2.25)
    box_fn("常开宿舍木门",leaf,edge+side*.54,y+.51,z+1.08,.99,.045,2.16)
    box_fn("宿舍门上标牌","blue",edge-side*.073,y+.71,z+2.40,.016,.26,.10)
    outside=range_on(shape,"y",y)[0 if side<0 else 1]
    far=outside-side*.65
    if abs(far-edge)>6.4 and b-a>2.4:
        # A deep room has a window-side study surface with usable floor between it and the beds.
        for yy in (y-.65,y+.65):
            side_edges=[range_on(shape,"y",p)[0 if side<0 else 1] for p in (yy-.62,yy+.62)]
            table=(max(side_edges) if side<0 else min(side_edges))-side*.56
            if not room.covers(box(table-.275,yy-.62,table+.275,yy+.62)):
                continue
            box_fn("窗边学习桌台面","paper",table,yy,z+.75,.55,1.24,.07)
            for dx in (-.22,.22):
                for dy in (-.50,.50):
                    box_fn("学习桌桌腿","metal",table+dx,yy+dy,z+.36,.045,.045,.72)
    interior.line_lamps(mesh,(edge+outside)/2,(y,),z+HEIGHT-.09)


def furniture_scale(room, bounds, edge, y, side, width):
    xmin,ymin,xmax,ymax=bounds
    for d in (1,.96,.92,.88,.84,.80,.76,.72,.68,.64):
        for w in (width,width*.94,width*.88,width*.82,width*.76):
            x0,x1=sorted((edge+side*ymin*d,edge+side*ymax*d))
            yy0,yy1=sorted((y-side*xmin*w,y-side*xmax*w))
            if room.covers(box(x0,yy0,x1,yy1)):
                return w,d
    return None


def furniture_bounds(data):
    coordinates=[v.co for v in data.vertices]
    return (min(v.x for v in coordinates),min(v.y for v in coordinates),
            max(v.x for v in coordinates),max(v.y for v in coordinates))


def compact_furniture(data):
    compact=data.copy()
    compact.name=data.name+" · 端部房间"
    removed={i for indices,_,center,_,_ in fit.connected_parts(data)
             if center.y>3.20 for i in indices}
    bm=bmesh.new()
    bm.from_mesh(compact)
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.index in removed],context="VERTS")
    bm.to_mesh(compact)
    bm.free()
    compact.update()
    return compact


def sanitary(mesh, shape, south, bounds, z):
    b=mesh.box
    a,c=bounds
    center=(a+c)/2
    front_wall(b,south,a,c,center,z,1.44,"wall_tile")
    for index in range(4):
        y=a+(index+.5)*(c-a)/4
        edge=range_on(shape,"y",y)[1]-.16
        x=max(south+2.75,edge-2.1)
        b("卫生间厕位侧隔板","plastic",x+.91,a+index*(c-a)/4,z+1.07,1.82,.055,1.90)
        b("半敞开厕位小门","plastic",x+.35,y-.45,z+1.07,.73,.05,1.90)
        b("坐便器陶瓷底座","plastic",x+1.10,y,z+.25,.62,.45,.42)
        b("坐便器座面","marble",x+1.03,y,z+.46,.67,.53,.12)
        b("水箱","plastic",x+1.39,y,z+.63,.28,.43,.48)
    for y in (a+.75,a+1.75,c-.75):
        b("洗手台","marble",south+1.05,y,z+.82,.71,.76,.12)
        b("洗手盆","plastic",south+1.03,y,z+.88,.45,.51,.04)
        b("水龙头","silver",south+.78,y,z+1.00,.05,.05,.22)


def mark(group, prefix):
    previous.mark_collision(group,prefix)


def rebuild_building(scene, payload, bid):
    frame,outline=frame_for(bid)
    shape=Polygon([(p.x,p.y) for p in outline])
    old_root=next(c for c in bpy.data.collections if c.name.startswith(bid) and "公寓）" in c.name)
    root=interior.collection(bid+" 宿舍贴合室内 · 按草图重新分间",bpy.data.collections["楼内还原"])
    for obj in list(old_root.all_objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    for child in list(old_root.children_recursive)[::-1]:
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(old_root)

    mats=previous.materials()
    keys=("plant","green","red","locker","boy_door","vent")
    mats.update({key:bpy.data.materials["校园室内 · "+key] for key in keys})
    sid="26" if bid=="B25" else "29"
    mats.update({"glass":bpy.data.materials["透明平板玻璃"],
                 "gingham":bpy.data.materials["宿舍蓝格床品"],
                 "dorm_floor":bpy.data.materials["宿舍米白地砖"],
                 "balcony27":bpy.data.materials["透明平板玻璃"],
                 "balcony30":bpy.data.materials["透明平板玻璃"],
                 sid:bpy.data.materials["公寓大厅实拍横幅"+sid],
                 "notice"+sid:bpy.data.materials["公寓大厅实拍卡片"+sid]})
    mesh=interior.new_mesh(scene,root,mats)
    b=mesh.box
    furniture=create_furniture(scene,root,bid,mats)
    compact=compact_furniture(furniture)
    full_bounds=furniture_bounds(furniture)
    compact_bounds=furniture_bounds(compact)
    center=-12.05 if bid=="B25" else -15.65
    north,south=center-1.50,center+1.50
    stairs,toilets=special_bays(shape,north,south)
    shafts=[(pose,(-1.31,.50),(1.31,4.80)) for pose,_,_ in stairs.values()]
    rows={-1:shape.intersection(box(-200,-200,north,200)),
           1:shape.intersection(box(south,-200,200,200))}
    special_south=[stairs["west"][1],stairs["east"][1],*toilets.values()]
    hall=shape.difference(unary_union(list(rows.values())))
    records={key:{"building":bid,"side":key,"routes":[],"corridor_paths":[]}
             for key in stairs}
    san_records={key:{"building":bid,"side":key,"bay":list(val),"paths":[]}
                 for key,val in toilets.items()}
    levels=[]
    leaf="boy_door" if bid=="B25" else "wood"

    def world(x,y,z):
        return (frame @ Vector((x,y,z)))[:]

    for index,z in enumerate(LEVELS):
        floor_no=index+1
        sections=[]
        mesh.section(f"{floor_no:02d}F 连续整栋楼板")
        depth=.24 if not index else z-(LEVELS[index-1]+HEIGHT)
        holes=list(shafts) if index else []
        if floor_no==2:
            holes.append((Matrix.Identity(4),(south+.05,LOBBY[0]),(.05,LOBBY[1])))
        fit.floor_plate(mesh,outline,z,depth,holes)
        if floor_no==len(LEVELS):
            fit.floor_plate(mesh,outline,z+HEIGHT+.045,.045,[],"ceiling")

        floor_rooms=[]
        mesh.section(f"{floor_no:02d}F 宿舍与功能房")
        partitions=set()
        for side,edge,special in ((-1,north,[stairs["mid"][1]]),(1,south,
                                   special_south+([LOBBY] if floor_no<=2 else []))):
            row=rows[side]
            front_start,front_end=range_on(shape,"x",edge)
            for a,c in row_rooms(shape,edge,side,special):
                y=(a+c)/2
                # Tapered tails belong to the adjacent end compartment.
                extent_a=-200 if abs(a-front_start)<.002 else a
                extent_c=200 if abs(c-front_end)<.002 else c
                room=row.intersection(box(-200,extent_a,200,extent_c))
                sections.append(room)
                floor_surface(mesh,"宿舍贴壳瓷砖","dorm_floor",room,z+.007)
                front_wall(b,edge,a,c,y,z)
                room_details(mesh,shape,room,side,edge,a,c,z,leaf)
                nominal=min(1.30,(c-a)/interior.DORM_WIDTH)
                scaled=furniture_scale(room,full_bounds,edge,y,side,nominal)
                suite=furniture if scaled is not None else compact
                if scaled is None:
                    scaled=furniture_scale(room,compact_bounds,edge,y,side,nominal)
                assert scaled is not None,(bid,floor_no,y,compact_bounds)
                w,d=scaled
                obj=bpy.data.objects.new(f"{bid} 宿舍贴合室内 {floor_no:02d}F 宿舍家具 {len(floor_rooms)+1:02d}",suite)
                root.objects.link(obj)
                obj.matrix_world=(frame @ interior.translate(edge,y,z+.01) @ interior.rotation(-side*math.pi/2)
                                  @ Matrix.Diagonal((w,d,1,1)))
                floor_rooms.append({"side":side,"span":[a,c],"area":round(room.area,2),"door":world(edge,y,z),
                                    "path":[world(center,y,z),world(edge+side*1.05,y,z)]})
                for y0 in (a,c):
                    if front_start+.018<y0<front_end-.018:
                        partitions.add((edge,side,y0))
            for lo,hi in special:
                region=row.intersection(box(-200,lo,200,hi))
                if not region.is_empty:
                    sections.append(region)
                for y0 in (lo,hi):
                    if front_start+.018<y0<front_end-.018:
                        partitions.add((edge,side,y0))
        for edge,side,y in sorted(partitions):
            partition(b,shape,edge,side,y,z)
        coverage=unary_union([hall,*sections]).intersection(shape).area/shape.area
        assert coverage>.999, (bid,floor_no,coverage)
        for key,bounds in toilets.items():
            sanitary(mesh,shape,south,bounds,z)
            yy=sum(bounds)/2
            san_records[key]["paths"].append([world(center,yy,z),world(south+2.1,yy,z)])

        mesh.section(f"{floor_no:02d}F 贯通楼道")
        y0,y1=range_on(shape,"x",center)
        for j in range(math.ceil(y0+1),math.floor(y1-1),4):
            interior.line_lamps(mesh,center,(j,),z+HEIGHT-.07)
        levels.append({"floor":floor_no,"z":z,"coverage":round(coverage,6),"rooms":floor_rooms,
                       "corridor":[world(center,y0+1.0,z),world(center,0,z),world(center,y1-1.0,z)]})
        for key,(pose,(a,c),door_y) in stairs.items():
            outer_side=1 if key!="mid" else -1
            edge=south if outer_side>0 else north
            lo=max(a,range_on(shape,"x",edge)[0])
            hi=min(c,range_on(shape,"x",edge)[1])
            front_wall(b,edge,lo,hi,door_y,z,1.75,"wall_tile")
            group=interior.collection(f"{bid} {key} 楼梯 {floor_no:02d}F",root)
            sm=interior.new_mesh(scene,group,mats)
            sm.section("双跑楼梯井与水平入口")
            for x in (-1.38,1.38):
                interior.wall(sm.box,"wall_tile",x,.48,4.81,z,HEIGHT,.10)
            interior.endwall(sm.box,"wall_tile",4.80,-1.38,1.38,z,HEIGHT,.10)
            if floor_no==len(LEVELS):
                # The top platform has a guarded edge and no upward flight.
                interior.rails(sm,-1.31,-.04,.48,z)
            t=frame@pose
            local_point=lambda x,y,z: (t @ Vector((x,y,z)))[:]
            if key=="mid":
                path=[world(center,door_y,z),world(north-1.0,door_y,z),local_point(-.62,-1.0,z)]
            else:
                side=(1 if key=="west" else -1)
                join=pose @ Vector((side*1.875,-.90,z))
                path=[world(center,door_y,z),world(join.x,door_y,z),local_point(-.62,-.90,z)]
            path.append(local_point(-.62,-.55,z))
            records[key]["corridor_paths"].append(path)
            if index<len(LEVELS)-1:
                rise=LEVELS[index+1]-z
                end_y=interior.stair(sm,0,0,z,rise)
                mid=end_y-.60
                route=((- .62,-.55,z),(-.62,.38,z),(-.62,mid,z+rise/2),
                       (.62,mid,z+rise/2),(.62,.38,z+rise),(.62,-.55,z+rise),(-.62,-.55,z+rise))
                records[key]["routes"].append({"from_floor":floor_no,"to_floor":floor_no+1,
                                                "points":[local_point(*p) for p in route]})
            sm.finish()
            interior.move_collection(group,t)
    decor=interior.collection(bid+" 首层大厅与挑空栏杆",root)
    lobby=interior.new_mesh(scene,decor,mats)
    lobby.section("入口大厅连续通向主走廊")
    interior.lobby(lobby,south,LEVELS[0],sid)
    for label in ("楼道纵墙","楼道横墙","大厅灰色抛光石板","门厅二层挑空顶板"):
        lobby.groups.pop(label,None)
    lobby.finish()
    interior.move_collection(decor,frame)
    # The main doors from the preceding revision still serve the lobby.
    entry=next(d for d in payload["doors"] if d["id"]==bid)
    entry_local=frame.inverted() @ Vector(entry["center"])
    lobby_route=[world(entry_local.x-.85,entry_local.y,LEVELS[0]),world(south+1.0,0,LEVELS[0]),
                 world(center,0,LEVELS[0])]
    before=set(root.all_objects)
    mesh.finish()
    for obj in set(root.all_objects)-before:
        obj.matrix_world=frame@obj.matrix_world
    mark(root,bid+" 宿舍贴合室内 ")
    for key,(pose,bay,_) in stairs.items():
        directional=(frame@pose).to_3x3().col[1].normalized()
        records[key].update(bay=list(bay),stair_frame=[list(row) for row in frame@pose],
                            first_flight_direction=list(directional), levels=list(LEVELS))
    return {"building":bid,"outline":[list(p) for p in outline],"frame":[list(row) for row in frame],
            "levels":levels,"stairs":records,"toilets":san_records,"lobby_route":lobby_route,
            "basis":"2026-11-17用户草图。各栋外壳独立拟合，房间数量、墙厚、厕所内装沿楼壳估排。"}


def turn_east_ramp(scene, payload):
    """Route the existing B25 end door down the alley instead of toward B28."""
    prefix="B25 贴合室内 端门洞口 "
    edited={obj.name.removeprefix(prefix): obj for obj in scene.objects
            if obj.name.startswith(prefix+"B28 ")}
    with bpy.data.libraries.load(str(fit.OUT/(fit.STEM+".blend"))) as (source, target):
        assert set(edited).issubset(source.objects)
        target.objects=list(edited)
    for name, original in zip(edited,target.objects):
        obj=edited[name]
        obj.data=original.data
        bpy.data.objects.remove(original,do_unlink=True)
        obj.name=name
    record=next(item for item in payload["doors"] if item["id"]=="B25_east_end")
    transform=doors.frame(record["center"],Vector(record["outward"]))
    record["swing_inward"]=True
    for leaf in record["pivots"]:
        side=leaf["side"]
        pivot=bpy.data.objects[leaf["name"]]
        pivot.matrix_world=(transform @ interior.translate(side*record["width"]/2,0,0)
                            @ interior.rotation(side*math.pi/2))
    transform.translation.z=0
    group=bpy.data.collections["B25 两端出入口与门外坡道"]
    old=min((o for o in group.all_objects if o.name.startswith("入口连续缓坡")),
            key=lambda obj:(obj.matrix_world.translation-transform.translation).length)
    bpy.data.objects.remove(old,do_unlink=True)
    ramp=interior.new_mesh(scene,group,{"floor":bpy.data.materials["公寓灰色地砖"]})
    ramp.section("B25 贴合室内 东端门转向坡道")
    ramp.polygons("东门外平台","floor",[(-.93,-.04,.57),(1.10,-.04,.57),
                   (1.10,1.04,.57),(-.10,1.04,.57),(-.93,.68,.57)],
                  [(0,1,2,3,4)])
    ramp.polygons("沿楼间隙向南的坡面","floor",[(1.10,.11,.57),(3.95,.11,.13),
                   (3.95,1.04,.13),(1.10,1.04,.57)],[(0,1,2,3)])
    before=set(group.all_objects)
    ramp.finish()
    for obj in set(group.all_objects)-before:
        obj.matrix_world=transform
    for child in group.children:
        if child.name.startswith("B25 贴合室内 东端门转向坡道"):
            mark(child,"B25 贴合室内 ")
    for route in payload["dorm_end_doors"]:
        if route["id"]==record["id"]:
            route["points"]=[(transform@Vector(p))[:] for p in
                             ((3.87,.62,.14),(1.10,.62,.57),(.22,.62,.57),
                              (.22,0,.57),(.22,-1.75,.57))]
            route["basis"]="两楼间隙宽度按现有外墙估排，东端门出门转向南侧下坡。"


def main():
    filename=latest.OUT/(latest.STEM+".blend")
    bpy.ops.wm.open_mainfile(filepath=str(filename),load_ui=False)
    payload=json.loads((latest.OUT/"楼门与公寓校正.json").read_text(encoding="utf-8"))
    scene=bpy.context.scene
    missing=[name for name in ("公寓大厅实拍横幅26","公寓大厅实拍卡片26")
             if name not in bpy.data.materials]
    if missing:
        with bpy.data.libraries.load(str(interior.OUT/(interior.STEM+".blend"))) as (source, target):
            assert set(missing).issubset(source.materials)
            target.materials=missing
    payload["dorm_layouts"]=[rebuild_building(scene,payload,bid) for bid in ("B25","B28")]
    turn_east_ramp(scene,payload)
    for key in ("dorm_lobby_stairs","dorm_end_stairs","dorm_toilets"):
        payload.pop(key,None)
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
