"""Place reusable interior rooms and walkable circulation in the campus master."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps

from 图书馆照片还原 import CAL, PLAN, world
from 教室与楼道实拍细化 import (
    ROOM_Y, VIEWS, Interior, aimed, material, surface_tile, tiles,
)

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/致远楼林荫步道与看台/校园室外_致远楼林荫步道与看台.blend"
CLASS_SOURCE = ROOT / "成果/教室与楼道实拍细化/教室与楼道.blend"
REFS = ROOT.parent / "数据/04_建模参考/02_八方向"
OUT = ROOT / "成果/教室与男女生公寓室内"
STEM = "校园_教室与男女生公寓室内"
BUILDINGS = {row["id"]: row for row in PLAN["buildings"]}
CLASS_STEP = 10.02
DORM_WIDTH = 3.25
DORM_DEPTH = 6.12
DORM_HEIGHT = 2.63
HALL_HALF = 1.36
FLOOR_Z = (.57, 4.20, 7.07, 9.94, 12.81, 15.68, 18.55)


def collection(name, parent):
    result = bpy.data.collections.new(name)
    parent.children.link(result)
    return result


def new_mesh(scene, parent, mats):
    mesh = Interior(scene, mats)
    mesh.collection = parent
    return mesh


def photo(sid, angle="000"):
    return next(REFS.glob(f"{sid}_*")) / f"{angle}.jpg"


def image_material(name, source, repeat=(1, 1)):
    path = OUT / "贴图" / (name + ".png")
    source.save(path)
    mat = material(name, (.38, .38, .38), .63)
    mat["repeat_metres"] = repeat
    nodes = mat.node_tree.nodes
    image = nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(str(path), check_existing=True)
    mat.node_tree.links.new(image.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def palette():
    colors = {
        "plaster": (.73, .75, .75), "ceiling": (.81, .82, .81),
        "grid": (.59, .61, .60), "marble": (.51, .45, .35),
        "base": (.068, .069, .061), "metal": (.34, .35, .31),
        "silver": (.45, .47, .47), "glass": (.34, .54, .61),
        "wood": (.225, .073, .031), "boy_door": (.142, .041, .026),
        "locker": (.35, .37, .34), "dark": (.038, .048, .048),
        "plastic": (.83, .84, .80), "vent": (.21, .21, .19),
        "lamp": (.90, .94, .96), "blue": (.035, .24, .45),
        "green": (.10, .32, .11), "red": (.54, .032, .019),
        "paper": (.69, .66, .52), "plant": (.12, .24, .048),
    }
    mats = {key: material("校园室内 · "+key, color) for key, color in colors.items()}
    for key in ("metal", "silver"):
        mats[key].node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = .35
    emitter = mats["lamp"].node_tree.nodes.get("Principled BSDF")
    emitter.inputs["Emission Color"].default_value = (.8, .89, 1.0, 1)
    emitter.inputs["Emission Strength"].default_value = 2.2
    for key,name,color,repeat,form in (
        ("hall_floor","公寓灰色地砖",(109,114,114),.62,"stone"),
        ("school_floor","教学楼道浅灰地砖",(172,169,159),.64,"marble"),
        ("dorm_floor","宿舍米白地砖",(198,191,172),.59,"marble"),
        ("wall_tile","大厅米色墙砖",(210,203,182),.33,"marble"),
    ):
        tile=surface_tile(color,form)
        ImageDraw.Draw(tile).rectangle((0,0,511,511),outline=tuple(v-29 for v in color),width=2)
        mats[key]=image_material(name,tile,(repeat,repeat))
    mats["hall_floor"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value=.31
    mats["wall_tile"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value=.47
    gingham = Image.new("RGB", (128, 128))
    pixels = gingham.load()
    colors = ((169, 196, 207), (92, 133, 166), (50, 82, 121))
    for y in range(128):
        for x in range(128):
            tone = colors[int(x >= 64) + int(y >= 64)]
            thread = (x % 4 in (0, 1)) * 5 - (y % 4 in (0, 1)) * 4
            pixels[x, y] = tuple(v+thread for v in tone)
    mats["gingham"] = image_material("宿舍蓝格床品", gingham, (.105, .105))
    for sid, box in (("26", (43, 51, 325, 79)), ("29", (33, 42, 330, 72))):
        ref = reference(sid)
        mats[sid] = image_material("公寓大厅实拍横幅"+sid, ref.crop(tuple(3*v for v in box)))
        ref=reference(sid,"090")
        poster_box=(207,144,245,258)
        mats["notice"+sid]=image_material("公寓大厅实拍卡片"+sid,ref.crop(tuple(3*v for v in poster_box)))
    for sid,box in (("27",(145,167,225,245)),("30",(141,175,225,255))):
        mats["balcony"+sid]=image_material("宿舍窗外实拍"+sid,reference(sid).crop(tuple(3*v for v in box)))
    return mats


def reference(sid, angle="000"):
    with Image.open(photo(sid,angle)) as source:
        return source.convert("RGB").resize((1080,1080),Image.Resampling.LANCZOS)


def glass_panel(b, label, x, y, lo, hi, width):
    b(label+"浅蓝灰玻璃", "glass", x, y, (lo+hi)/2, width, .028, hi-lo)
    for xx in (x-width/2, x+width/2):
        b(label+"竖框", "silver", xx, y, (lo+hi)/2, .047, .068, hi-lo)
    for zz in (lo, hi):
        b(label+"横框", "silver", x, y, zz, width, .068, .047)


def radiator(b, x, y, width):
    for i in range(round(width/.064)):
        b("暖气立片", "metal", x-width/2+.064*i, y, .38, .035, .12, .53)
    for z in (.18, .59):
        b("暖气横管", "metal", x, y, z, width, .07, .055)


def dorm_sample(scene, parent, mats, girls):
    root = collection("女生宿舍样板" if girls else "男生宿舍样板", parent)
    m = new_mesh(scene, root, mats)
    b = m.box
    w = DORM_WIDTH
    h = DORM_HEIGHT
    vestibule = .37 if girls else .16
    door = "wood" if girls else "boy_door"
    m.section("宿舍隔墙、门窗与地坪")
    tiles(m,"宿舍米白瓷砖","dorm_floor",-w/2,w/2,0,DORM_DEPTH,.59)
    b("乳白天花","ceiling",0,DORM_DEPTH/2,h+.06,w,DORM_DEPTH,.12)
    for sign in (-1,1):
        side = sign*(w/2-.042)
        b("侧隔墙","plaster",side,DORM_DEPTH/2,h/2,.084,DORM_DEPTH,h)
        b("深灰踢脚线","base",side-sign*.05,DORM_DEPTH/2,.047,.024,DORM_DEPTH,.094)
        b("门口两侧墙","plaster",sign*(w/4+.25),.075,h/2,(w-1)/2,.15,h)
        b("门洞进深包边","plaster",sign*.543,vestibule/2,1.13,.108,vestibule,2.26)
        b("木门竖框",door,sign*.485,vestibule,1.12,.065,.127,2.24)
    b("门洞上方过梁","plaster",0,vestibule/2,2.52,1.03,vestibule,.22)
    b("玻璃门楣","glass",0,vestibule,2.345,.92,.055,.245)
    for z in (2.216,2.475):
        b("门楣横档",door,0,vestibule,z,.98,.105,.055)
    hinge = .445 if girls else -.445
    b("常开实木门扇",door,hinge,vestibule+.44,1.105,.048,.88,2.19)
    b("门扇收边",door,hinge,vestibule+.865,1.15,.061,.044,2.14)
    b("金属把手","silver",hinge,vestibule+.799,1.02,.136,.045,.047)
    balcony=DORM_DEPTH-.70
    b("阳台口窗下暖白墙","plaster",.525,balcony,.46,1.05,.10,.92)
    b("窗洞上方灰白墙","plaster",0,balcony,2.46,w,.10,.34)
    for sign in (-1,1):
        b("窗洞两侧白墙","plaster",sign*1.337,balcony,1.15,.576,.10,2.30)
    for x in (-1.04,0,.49,1.04):
        b("阳台门和窗竖框","silver",x,balcony,1.60 if x>0 else 1.154,.049,.076,1.33 if x>0 else 2.26)
    for z in (.94,1.94,2.26):
        b("阳台门窗横框","silver",0 if z>.95 else .52,balcony,z,2.09 if z>.95 else 1.05,.068,.044)
    b("窗台石板","plastic",.52,balcony,.924,1.08,.27,.064)
    radiator(b,.58,balcony-.105,.73)
    b("窗上壁挂空调","plastic",0,balcony-.15,2.42,.78,.23,.205)
    b("空调下出风口","vent",0,balcony-.277,2.354,.64,.024,.045)
    m.rod("顶侧空调管","metal",(.28,balcony-.132,2.42),(1.46,balcony-.132,2.42),.023)
    m.rod("顶侧空调管","metal",(1.46,balcony-.132,2.42),(1.46,.75,2.42),.023)
    b("阳台白色栏板","plaster",0,DORM_DEPTH-.035,.44,w,.09,.88)
    b("外窗顶封边","plaster",0,DORM_DEPTH-.035,2.40,w,.09,.46)
    m.panel_group="样板宿舍实拍阳台窗景"+("30" if girls else "27")
    m.panel("阳台实拍窗景", "balcony"+("30" if girls else "27"),
            (0,DORM_DEPTH-.023,1.55),(1,0,0),(0,0,1),3.18,1.38)
    b("吸顶日光灯背架","silver",0,3.10,h-.055,.25,1.14,.075)
    for x in (-.061,.061):
        m.rod("双管日光灯","lamp",(x,2.56,h-.111),(x,3.64,h-.111),.021)

    m.section("钢制双层床、蓝格床品和叠被")
    for side in (-1,1):
        x = side*1.13
        for idx,y in enumerate((2.20,4.30)):
            for z in (.45,1.60):
                b("上下铺钢床板底框","metal",x,y,z,.97,1.98,.082)
                m.rounded("蓝格床垫","gingham",x,y,z+.079,.90,1.90,.102,.044)
                m.rounded("蓝格枕头","gingham",x,y+.70,z+.17,.80,.32,.105,.10)
                if (idx == 1) == (z > 1):
                    for level in range(3):
                        m.rounded("折叠的蓝格棉被","gingham",x,y+.56,z+.23+.083*level,.78,.53,.095,.11)
            for xx in (x-.47,x+.47):
                for yy in (y-.96,y+.96):
                    b("上下铺钢立柱","metal",xx,yy,1.00,.047,.047,2.00)
            inside = x-side*.46
            m.rod("上床防坠护栏","metal",(inside,y-.51,1.942),(inside,y+.89,1.942),.023)
            for yy in (y-.51,y+.20,y+.89):
                m.rod("护栏支撑","metal",(inside,yy,1.62),(inside,yy,1.94),.019)
            ladder = x-side*.49
            for yy in (y-.91,y-.60):
                b("床梯侧杆","metal",ladder,yy,.89,.038,.038,1.78)
            for level in range(5):
                m.rod("床梯梯级","metal",(ladder,y-.91,.30+.295*level),(ladder,y-.60,.30+.295*level),.018)
            if idx == 0:
                b("床底分色收纳箱","blue" if side==1 else "green",x,y-.38,.16,.56,.54,.30)

    m.section("进门两组钢柜和叠放物品")
    for side in (-1,1):
        x=side*1.072
        b("浅灰钢柜柜体","locker",x,.39, .93,.90,.46,1.82)
        for row,z in enumerate((.49,1.40)):
            for col in (-1,1):
                xx=x+.217*col
                b("分格柜门","silver",xx,.633,z,.418,.031,.879)
                b("柜门拉手","dark",xx-.10,.66,z+.005,.034,.045,.095)
                b("柜门小号码牌","red",xx+.134,.652,z+.394,.076,.01,.038)
                for q in range(3):
                    b("柜门散热缝","vent",xx+.104,.652,z-.24-.046*q,.097,.008,.009)
        for row in range(4):
            b("柜顶叠放纸盒","paper",x-.09,.42,1.87+row*.038,.47-.02*row,.30,.035)
    m.finish()
    return root


def joined_templates(root, objects, name):
    """Bake each group to one mesh while keeping UVs, material slots and the local origin."""
    if not objects:
        return []
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    target = objects[0]
    for obj in objects:
        if obj.name not in bpy.context.scene.objects:
            root.objects.link(obj)
    bpy.context.view_layer.update()
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = target
    if len(objects)>1:
        bpy.ops.object.join()
    target.name = name
    for old in tuple(target.users_collection):
        if old != root:
            old.objects.unlink(target)
    if target.name not in root.objects:
        root.objects.link(target)
    return [target]


def classroom_sample(root):
    import bmesh
    with bpy.data.libraries.load(str(CLASS_SOURCE), link=False) as (source, loaded):
        loaded.collections = [name for name in source.collections
                              if name.startswith(("01 教室","02 教室","03 教室","04 教室",
                                                  "07 顶部","08 教室","06 楼道","09 楼道"))]
    fixtures = {}
    meshes = []
    for group in loaded.collections:
        for obj in group.objects:
            if obj.type != "MESH":
                continue
            if group.name.startswith(("06 楼道", "09 楼道")):
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                bmesh.ops.delete(bm, geom=[face for face in bm.faces
                                          if not -.01<=face.calc_center_median().y<=ROOM_Y-.05],
                                 context='FACES')
                if bm.faces:
                    bm.to_mesh(obj.data)
                    fixtures.setdefault(group.name, []).append(obj)
                bm.free()
                continue
            if group.name.startswith("07 顶部") and ("楼道" in obj.name or min(v.co.x for v in obj.data.vertices)<-4.2):
                continue
            meshes.append(obj)
    classroom = joined_templates(root, meshes, "实拍教室共享网格")
    corridor = joined_templates(root, [o for items in fixtures.values() for o in items],
                                 "实拍楼道柜、暖气与门牌共享网格")
    return classroom+corridor


def place(parent, templates, transform, name):
    for index, source in enumerate(templates):
        obj = bpy.data.objects.new(name if not index else f"{name} · {index+1}", source.data)
        parent.objects.link(obj)
        obj.matrix_world = transform @ source.matrix_local


def move_collection(root, transform):
    for item in root.all_objects:
        item.matrix_world = transform @ item.matrix_world


def translate(x,y,z):
    return Matrix.Translation((x,y,z))


def rotation(angle):
    return Matrix.Rotation(angle, 4, 'Z')


class Frame:
    def __init__(self, bid, dorm):
        self.points = [world(p) for p in BUILDINGS[bid]["outline"]]
        if dorm:
            self.anchor = (self.points[3]+self.points[4])/2
            self.y = (self.points[3]-self.points[4]).normalized()
        else:
            self.anchor = (self.points[0]+self.points[-1])/2
            self.y = ((self.points[1]+self.points[2])/2-self.anchor).normalized()
        self.x = Vector((self.y.y,-self.y.x,0))
        if dorm:
            # The original entry façade uses this segment's outward perpendicular.
            assert (self.anchor - sum(self.points, Vector())/len(self.points)).dot(self.x) > 0
        self.matrix = Matrix((self.x,self.y,Vector((0,0,1)))).transposed().to_4x4()
        self.matrix.translation = self.anchor
        self.corners = [self.matrix.inverted() @ p for p in self.points]

    def width_at(self, y):
        intersections = []
        for a,b in zip(self.corners,self.corners[1:]+self.corners[:1]):
            if min(a.y,b.y) <= y < max(a.y,b.y):
                intersections.append(a.x+(b.x-a.x)*(y-a.y)/(b.y-a.y))
        return min(intersections),max(intersections)

    def at(self, p):
        return self.matrix @ Vector(p)


def stair(m, x, y, base, rise, flip=False):
    """Two flights share a half landing. The main corridor skirts the open well."""
    b = m.box
    d = .280 if rise>3 else .268
    n = math.ceil(rise/.34)
    r = rise/(2*n)
    sign = -1 if flip else 1
    width = 1.17
    def block(label, key, xx, yy, zz, w, dep, h):
        b(label,key,x+xx,y+sign*yy,base+zz,w,dep,h)
    for j in range(n):
        for column, index in ((-.62,j),(.62,n-1-j)):
            upper = column>0
            top=(j+1)*r+(rise/2 if upper else 0)
            bottom=top-.19
            pos=.5+(index+.5)*d
            block("楼梯石踏步","hall_floor",column,pos,(top+bottom)/2,width,d+.02,top-bottom)
            block("防滑踏步前缘","base",column,pos+(-1 if not upper else 1)*d*.47,top-.005,width,.016,.013)
    end=.5+n*d
    block("楼梯中间平台","hall_floor",0,end+.60,rise/2-.11,2.50,1.20,.22)
    for column,hi in ((-1.26,False),(-.04,False),(.04,True),(1.26,True)):
        z0,z1=(rise+.94,rise/2+.94) if hi else (.94,rise/2+.94)
        m.rod("楼梯金属扶手","silver",(x+column,y+sign*.47,base+z0),
              (x+column,y+sign*end,base+z1),.032)
        for step in range(n+1):
            t=step/n
            zz=(z0+(z1-z0)*t)-.455
            block("楼梯栏杆","silver",column,.50+t*(end-.50),zz,.028,.028,.91)
    block("楼梯平台护栏","silver",0,end+1.186,rise/2+.91,2.46,.046,.046)
    for dx in (-1.2,-.6,0,.6,1.2):
        block("平台栏杆","silver",dx,end+1.18,rise/2+.475,.028,.028,.95)
    return end+1.20


def slab(b, label, key, x0,x1,y0,y1,z,depth=.16):
    b(label,key,(x0+x1)/2,(y0+y1)/2,z-depth/2,x1-x0,y1-y0,depth)


def line_lamps(m, x, ys, z, along_y=True):
    for y in ys:
        m.box("楼道吸顶灯罩","lamp",x,y,z,.26 if along_y else 1.18,1.18 if along_y else .26,.045)
        m.box("楼道吸顶灯边框","silver",x,y,z+.028,.305 if along_y else 1.22,1.22 if along_y else .305,.042)


def corridor_floor(m, key,x0,x1,y0,y1,z,height):
    b = m.box
    slab(b,"连续楼道楼板",key,x0,x1,y0,y1,z)
    slab(b,"楼道吊顶","ceiling",x0,x1,y0,y1,z+height+.08,.08)
    for y in range(math.ceil(y0+.3),math.floor(y1-.3),4):
        line_lamps(m,(x0+x1)/2,(y,),z+height-.025)
    step=.62 if key=="school_floor" else 1.22
    splits=round((y1-y0)/step)
    for i in range(1,splits):
        b("吊顶横向分格","grid",(x0+x1)/2,y0+(y1-y0)*i/splits,z+height,x1-x0,.012,.016)
    for i in (1,2,3,4):
        b("吊顶纵向分格","grid",x0+(x1-x0)*i/5,(y0+y1)/2,z+height,.012,y1-y0,.016)


def wall(b, key, x, ya,yb,z,h, thick=.13):
    b("楼道纵墙",key,x,(ya+yb)/2,z+h/2,thick,yb-ya,h)


def endwall(b, key, y, xa,xb,z,h, thick=.13):
    b("楼道横墙",key,(xa+xb)/2,y,z+h/2,xb-xa,thick,h)


def rails(m, xa, xb, y, z):
    m.rod("挑空栏杆扶手","silver",(xa,y,z+.99),(xb,y,z+.99),.033)
    m.rod("挑空栏杆下横档","silver",(xa,y,z+.12),(xb,y,z+.12),.024)
    for i in range(round((xb-xa)/.16)+1):
        x=min(xb,xa+.16*i)
        m.rod("防坠竖杆","silver",(x,y,z+.09),(x,y,z+.99),.015)


def wall_mesh_cut(obj, frame, opening):
    """Clip only the box mesh spanning an existing modeled entry."""
    import bmesh
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    inverse = frame.matrix.inverted() @ obj.matrix_world
    forward = inverse.inverted()
    bm.transform(inverse)
    for axis, low, high in ((0, opening[0], opening[1]),(2, opening[2],opening[3])):
        direction=Vector((int(axis==0),0,int(axis==2)))
        for plane in (low,high):
            point=direction*plane
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                   dist=.00001,plane_co=point,plane_no=direction)
    x0,x1,z0,z1=opening
    delete=[]
    for face in bm.faces:
        c=face.calc_center_median()
        if x0+1e-5<c.x<x1-1e-5 and z0+1e-5<c.z<z1-1e-5:
            delete.append(face)
    bmesh.ops.delete(bm,geom=delete,context='FACES')
    bm.transform(forward)
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def open_school_doors(bid, frame):
    # The legacy entrance has all glass leaves in the closed position.
    across=(frame.points[-1]-frame.points[0]).normalized()
    depth=Vector((-across.y,across.x,0))
    doorway=Matrix((across,depth,Vector((0,0,1)))).transposed().to_4x4()
    doorway.translation=frame.anchor
    centers=(-1.84,1.84) if bid=="B15" else (.72,)
    for part in ("门扇玻璃","门扇细金属边","门扇蓝色安全横条","玻璃门拉手"):
        obj=bpy.data.objects[bid+" "+part]
        to_local=doorway.inverted() @ obj.matrix_world
        from_local=to_local.inverted()
        vertices=list(obj.data.vertices)
        for start in range(0,len(vertices),8):
            corners=[to_local @ v.co for v in vertices[start:start+8]]
            mid=sum(v.x for v in corners)/len(corners)
            center=min(centers,key=lambda x:abs(x-mid))
            sign=1 if mid>center else -1
            hinge_x=center+sign*1.074
            swing=rotation(sign*math.pi/2)
            pivot=Vector((hinge_x,.04,0))
            for vertex,right in zip(vertices[start:start+8],corners):
                vertex.co=from_local @ (pivot+swing @ (right-pivot))
        obj.data.update()


def camera(scene, name, frame, eye, target, lens):
    data=bpy.data.cameras.new(name)
    obj=bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location=frame.at(eye)
    aimed(obj,frame.at(target))
    data.lens=lens
    data.clip_start=.055
    return obj


def overhead(scene, lights, frame, name, x,y,z, power, size):
    data=bpy.data.lights.new(name,"AREA")
    data.energy=power
    data.shape="DISK"
    data.size=size
    obj=bpy.data.objects.new(name,data)
    lights.objects.link(obj)
    obj.location=frame.at((x,y,z))


def school(scene, parent, mats, bid, template, views, records):
    name="致远楼" if bid=="B15" else "思远楼"
    root=collection(bid+" "+name+" · 教室、楼道与楼梯",parent)
    lights=collection("室内灯光 · "+name,root)
    frame=Frame(bid,False)
    max_y=min(frame.corners[1].y,frame.corners[2].y)
    start=10.55
    count=int((max_y-start-3)/CLASS_STEP)
    end=start+count*CLASS_STEP
    shift=1.06
    hall_left=-6.31
    hall_right=shift-4.15
    hall=(hall_left+hall_right)/2
    ground=.48 if bid=="B15" else .64
    levels=(ground,4.32,8.04,11.76,15.48)
    existing=bpy.data.objects.get(bid+" 首层退后墙")
    opening=(-1.45,1.56) if bid=="B15" else (-.52,1.91)
    wall_mesh_cut(existing,frame,(*opening,ground-.013,ground+2.30))
    bpy.data.objects.remove(bpy.data.objects[bid+" 门洞进深"],do_unlink=True)
    open_school_doors(bid,frame)
    construction=collection(bid+" 楼道和交通构件",root)
    m=new_mesh(scene,construction,mats)
    for f,z in enumerate(levels,1):
        floor_collection=collection(f"{f:02d}F 教室 · {count}间",root)
        for i in range(count):
            y=start+i*CLASS_STEP
            place(floor_collection,template,frame.matrix @ translate(shift,y,z),f"{name} {f:02d}-{i+1:02d} 教室样板")
            for yy in (y+2.5,y+7.1):
                overhead(scene,lights,frame,"教室顶灯",shift,yy,z+3.35,110,2.3)
            overhead(scene,lights,frame,"教室窗漫射光",shift+3.62,y+4.8,z+2.75,72,2.8)
        m.section(f"{f:02d}F 连续楼道、窗、门厅及楼梯")
        b=m.box
        corridor_floor(m,"school_floor",hall_left,hall_right,1.45,end,z,2.99)
        for i in range(count):
            y=start+i*CLASS_STEP
            # Bridge the narrow joint between adjacent sample rooms.
            wall(b,"plaster",hall_right,y+ROOM_Y,y+CLASS_STEP,z,3.23)
        m.section(f"{f:02d}F 楼道外窗与墙裙")
        for i in range(1, math.floor((end-2)/3.2)+1):
            y=1.7+(i-.5)*3.2
            wall(b,"plaster",hall_left,y-1.6,y+1.6,z,1.29)
            wall(b,"marble",hall_left+.078,y-1.6,y+1.6,z,1.09,.024)
            wall(b,"plaster",hall_left,y-1.6,y+1.6,z+2.68,.39)
            wall(b,"plaster",hall_left,y-1.6,y-1.08,z+1.29,1.39)
            wall(b,"plaster",hall_left,y+1.08,y+1.6,z+1.29,1.39)
            glass_panel(b,"教学走廊侧窗",hall_left,y,z+1.29,z+2.68,2.16)
            # This frame is in the y-z plane.
            for label in ("教学走廊侧窗浅蓝灰玻璃","教学走廊侧窗竖框","教学走廊侧窗横框"):
                verts=m.groups[label][0]
                num=16 if label.endswith(("竖框","横框")) else 8
                for j in range(len(verts)-num,len(verts)):
                    xx,yy,zz=verts[j]
                    verts[j]=(hall_left-(yy-y),y+(xx-hall_left),zz)
            overhead(scene,lights,frame,"教学楼道顶灯",hall,y,z+2.86,52,1.35)
        far=1.7+math.floor((end-2)/3.2)*3.2
        if far<end:
            wall(b,"plaster",hall_left,far,end,z,3.04)
        endwall(b,"plaster",end,hall_left,hall_right+.12,z,3.04)
        m.section(f"{f:02d}F 平层门厅及双跑楼梯")
        top=levels[f] if f<len(levels) else None
        slab(b,"门厅和楼梯间地面","school_floor",hall_left,2.59,1.44,3.38,z)
        if f==1:
            slab(b,"楼梯后方平台","school_floor",hall_right,2.59,8.36,start,z)
        if top:
            stair(m,-.17,2.88,z,top-z)
        wall(b,"plaster",2.60,1.45,start,z,3.63)
        wall(b,"plaster",hall_right,3.38,start,z,3.38)
        endwall(b,"plaster",start,hall_right,2.61,z,3.48)
        if f == 1:
            slab(b,"校道与首层门槛内侧接板","school_floor",opening[0]-.10,opening[1]+.10,-.05,1.48,z)
            for start_x,end_x in ((hall_left,opening[0]),(opening[1],2.59)):
                endwall(b,"plaster",1.43,start_x,end_x,z,2.21)
            endwall(b,"plaster",1.43,hall_left,2.59,z+2.21,1.28)
        else:
            endwall(b,"plaster",1.43,hall_left,2.59,z,3.50)
        overhead(scene,lights,frame,"教学楼梯与门厅灯",-.20,2.30,z+3.1,95,1.7)
    m.finish()
    move_collection(construction,frame.matrix)
    z=levels[1]
    if bid=="B15":
        for label, eye, target, lens in (VIEWS[0],VIEWS[4]):
            eye=(eye[0]+shift,eye[1]+start,eye[2]+z)
            target=(target[0]+shift,target[1]+start,target[2]+z)
            views.append(camera(scene, "教学_"+label,frame,eye,target,lens))
        views.append(camera(scene,"教学_整层走廊",frame,(hall,6.1,z+1.62),(hall,28,z+1.42),22))
    records[bid]={"名称":name,"房间数":count*len(levels),"每层":count,"楼层标高":levels,
                  "首层门洞":opening,"轴向范围":[start,end],"楼层与教室归属":"复制布置，16/17站的实际楼栋、门牌与楼层待核"}
    return frame
def lobby(m, x, z, sid):
    """x is the corridor-side opening of the double-height lobby."""
    b=m.box
    # The entrance faces +x. Keep the center pair of exterior doors and the internal passage clear.
    slab(b,"大厅灰色抛光石板","hall_floor",x,.19,-3.70,3.70,z,.24)
    slab(b,"门厅二层挑空顶板","ceiling",x,-.05,-3.70,3.70,z+6.38)
    for y in (-3.69,3.69):
        endwall(b,"wall_tile",y,x,0,z,6.25,.14)
        endwall(b,"base",y-math.copysign(.074,y),x,0,z,.115,.023)
        for k in range(7):
            xx=x+.69+k*.82
            inside=y-math.copysign(.12,y)
            b("壁挂蓝色终端","blue",xx,inside,1.37+z,.23,.105,.25)
            b("终端玻璃显示面","dark",xx,inside-math.copysign(.056,y),1.387+z,.175,.011,.116)
            b("终端下方黑色刷卡器","dark",xx,inside,1.09+z,.193,.09,.12)
            m.rod("终端竖向线管","silver",(xx,inside,z+1.50),(xx,inside,z+2.02),.011)
        for i in range(33):
            b("大厅长暖气立片","metal",x+2.16+i*.086,y-math.copysign(.17,y),z+.39,.035,.12,.62)
        b("大厅暖气横管","metal",x+3.52,y-math.copysign(.17,y),z+.67,2.81,.073,.060)
        b("智慧公寓信息屏黑框","dark",x+3.48,y-math.copysign(.085,y),z+2.82,1.36,.084,.69)
        b("智慧公寓信息屏","lamp",x+3.48,y-math.copysign(.13,y),z+2.82,1.29,.012,.61)
        b("信息屏蓝色表头","blue",x+3.48,y-math.copysign(.14,y),z+3.065,1.29,.008,.085)
        for row in range(5):
            b("信息屏表格横线","silver",x+3.48,y-math.copysign(.142,y),z+2.60+row*.074,1.13,.008,.009)
    wall(b,"wall_tile",x,-3.67,-1.20,z,3.61,.14)
    wall(b,"wall_tile",x,1.20,3.67,z,3.61,.14)
    wall(b,"wall_tile",x,-3.67,3.67,z+2.61,1.02,.14)
    # Upper-floor railing faces the double-height entrance.
    for yy in (-3.50,3.50):
        b("门厅二层结构柱","wall_tile",x+.12,yy,z+3.10,.36,.36,6.18)
    m.rod("大厅挑台不锈钢通长扶手","silver",(x+.05,-3.57,4.20+.98),(x+.05,3.57,4.20+.98),.042)
    m.rod("大厅挑台不锈钢下档","silver",(x+.05,-3.57,4.20+.12),(x+.05,3.57,4.20+.12),.024)
    for y in (i*.18 for i in range(-19,20)):
        m.rod("大厅挑台细竖栏","silver",(x+.05,y,4.20+.08),(x+.05,y,4.20+.96),.015)
    m.panel_group="大厅实拍墙面图文 "+sid
    m.panel("大厅实拍迎新横幅",sid,(x+.092,0,4.20+.54),(0,1,0),(0,0,1),5.64,.66)
    m.panel("大厅实拍公示卡", "notice"+sid,(x+1.43,3.606,z+1.78),(1,0,0),(0,0,1),.42,1.26)
    b("值班台桌面","paper",x+1.23,-2.76,z+.78,.92,.55,.067)
    for dx in (-.39,.39):
        for dy in (-.22,.22):
            b("值班台桌脚","wood",x+1.23+dx,-2.76+dy,z+.38,.055,.055,.76)
    b("大厅石台花池","marble",-.96,2.67,z+.23,.70,1.44,.46)
    for i in range(8):
        m.rounded("花池中的绿植","plant",-.97+.095*math.sin(i),2.11+.157*i,z+.47,.31,.32,.22,.12)


def relocate_entry_tree(frame):
    """Move the first tree in the west-gate planting group away from the glass entry."""
    group=bpy.data.collections["西门沿线 · 行道树冠、绿篱和宿舍花树"]
    trunks=next(obj for obj in group.objects if obj.name.startswith("自然分叉树干"))
    base=sum((v.co for v in list(trunks.data.vertices)[:7]),Vector())/7
    assert (base.xy-world((886,143)).xy).length<.02
    parts={"自然分叉树干":14,"冠内延伸主枝":14,"刷白树干段":14,
           "冠内斜枝":168,"西门行道树 · green":2160}
    shift=frame.x*2.0-frame.y*2.3
    for stem,count in parts.items():
        obj=next(obj for obj in group.objects if obj.name.startswith(stem))
        for vertex in list(obj.data.vertices)[:count]:
            vertex.co+=shift
        obj.data.update()


def dormitory(scene, parent, mats, bid, template, views, records):
    girls=bid=="B28"
    name="蕙远楼（女生公寓）" if girls else "绅远楼（男生公寓）"
    root=collection(bid+" "+name+" · 宿舍、大厅、楼道与楼梯",parent)
    lights=collection("室内灯光 · "+name,root)
    frame=Frame(bid,True)
    center=-9.25
    north=center-HALL_HALF
    south=center+HALL_HALF
    edge=sorted((frame.corners[3].y,frame.corners[4].y))
    end=min(abs(edge[0]),abs(edge[1]))-2.5
    near=-end
    core=near+1.18
    left_rooms=[]
    right_rooms=[]
    for side,positions in ((-1,left_rooms),(1,right_rooms)):
        for i in range(1,math.floor((end-1.7)/DORM_WIDTH)+1):
            for y in (-i*DORM_WIDTH,i*DORM_WIDTH):
                if abs(y)<4.8 or y-DORM_WIDTH/2<core+5.8 or y+DORM_WIDTH/2>end-.3:
                    continue
                span=[frame.width_at(y+off) for off in (-DORM_WIDTH/2,DORM_WIDTH/2)]
                if side<0 and max(inner for inner,_ in span)>north-DORM_DEPTH-.06:
                    continue
                if side>0 and min(outer for _,outer in span)<south+DORM_DEPTH+.06:
                    continue
                positions.append(y)
        positions.sort()
    assert left_rooms and right_rooms
    dark=bpy.data.objects[bid+" 内门厅作用面"]
    bpy.data.objects.remove(dark,do_unlink=True)
    if girls:
        relocate_entry_tree(frame)
    construction=collection(bid+" 楼道、大厅和交通构件",root)
    m=new_mesh(scene,construction,mats)
    for f,z in enumerate(FLOOR_Z,1):
        units=collection(f"{f:02d}F 宿舍 · {len(left_rooms)+len(right_rooms)}间",root)
        for side,positions in ((-1,left_rooms),(1,right_rooms)):
            for i,y in enumerate(positions,1):
                x=center+side*HALL_HALF
                school_name=f"{bid} {f:02d}-{('N' if side<0 else 'S')}{i:02d} 宿舍样板"
                transform=frame.matrix @ translate(x,y,z) @ rotation(-side*math.pi/2)
                place(units,template,transform,school_name)
                overhead(scene,lights,frame,"宿舍日光灯",x+side*2.91,y,z+2.46,78,2.0)
                if i%3==1 or y==6.5:
                    overhead(scene,lights,frame,"宿舍外窗漫射",x+side*5.70,y,z+2.17,54,1.3)
        m.section(f"{f:02d}F 公寓通长楼道与双跑楼梯")
        b=m.box
        corridor_floor(m,"hall_floor",north,south,near,end,z,2.56)
        endwall(b,"plaster",near,north,south+2.66,z,2.63)
        endwall(b,"plaster",end,north,south,z,2.63)
        for side,positions in ((-1,left_rooms),(1,right_rooms)):
            x=center+side*HALL_HALF
            openings=[(y-DORM_WIDTH/2+.075,y+DORM_WIDTH/2-.075) for y in positions]
            for y in positions:
                xx=x-side*.014
                b("宿舍门上蓝白标牌","blue",xx,y,z+2.519,.035,.28,.092)
                for j in (-1,0,1):
                    b("蓝牌浅色字样","plastic",xx-side*.020,y+j*.043,z+2.52,.005,.016,.038)
            if side==1:
                openings.append((core-.90,core+.49))
                if f in (1,2):
                    openings.append((-3.70,3.70))
            walk=near
            for lo,hi in sorted(openings):
                if lo>walk+.004:
                    wall(b,"plaster",x,walk,lo,z,2.63)
                    wall(b,"base",x-side*.077,walk,lo,z,.095,.025)
                walk=max(walk,hi)
            wall(b,"plaster",x,walk,end,z,2.63)
        slab(b,"楼梯楼层平台","hall_floor",south,south+2.64,near,core+.50,z)
        if f<len(FLOOR_Z):
            stair(m,south+1.32,core,z,FLOOR_Z[f]-z)
        wall(b,"plaster",south+2.62,near,core+5.16,z,2.8)
        endwall(b,"plaster",core+5.15,south,south+2.66,z,2.8)
        for y in range(math.ceil(near+1),math.floor(end-1),5):
            overhead(scene,lights,frame,"公寓楼道顶灯",center,y,z+2.45,63,1.4)
        for y in (near+.19,end-.19):
            b("楼道安全出口绿底牌","green",center,y,z+2.31,.48,.052,.155)
        b("公寓楼道红色消防箱","red",north+.146,-.32,z+.64,.16,.60,.82)
        b("消防箱浅色玻璃面","silver",north+.234,-.32,z+.71,.019,.478,.505)
        overhead(scene,lights,frame,"公寓楼梯平台灯",south+1.3,core+.1,z+2.45,110,1.35)
    m.section("首层实拍挑空大厅")
    lobby(m,south,FLOOR_Z[0],"29" if girls else "26")
    for x in (south+2.15,-2.05):
        overhead(scene,lights,frame,"挑空大厅灯",x,0,6.68,535,3.1)
    overhead(scene,lights,frame,"公寓入口采光",-.68,0,2.86,180,2.5)
    m.finish()
    move_collection(construction,frame.matrix)
    prefix="女生公寓" if girls else "男生公寓"
    z=FLOOR_Z[1]
    room=min(right_rooms,key=abs)
    views.append(camera(scene,prefix+"_宿舍样板",frame,(south+1.00,room,z+1.42),(south+5.90,room+.07,z+1.29),21))
    views.append(camera(scene,prefix+"_楼道",frame,(center,room-2.26,z+1.58),(center+.3,room+12,z+1.35),23))
    views.append(camera(scene,prefix+"_首层大厅",frame,(-.72,-1.82,2.14),(south+.95,.15,3.25),19))
    records[bid]={"名称":name,"房间数":(len(left_rooms)+len(right_rooms))*len(FLOOR_Z),
                  "每层":[len(left_rooms),len(right_rooms)],"内外楼层标高":FLOOR_Z,
                  "大厅、宿舍来源":["29","30"] if girls else ["26","27"],
                  "标准间估测尺寸":[DORM_WIDTH,DORM_DEPTH,DORM_HEIGHT],
                  "楼道净宽":HALL_HALF*2-.13,"走廊范围":[near,end],
                  "中央通道中心":center,"楼梯起点":core,"房间轴线":{"北":left_rooms,"南":right_rooms}}
    return frame


def export(scene, filepath, interiors_only):
    selection=[]
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    if interiors_only:
        selection=[o for o in bpy.data.collections["楼内还原"].all_objects if o.type=="MESH"]
        for o in selection:
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(filepath),export_format="GLB",
                              use_selection=interiors_only,export_cameras=False,export_lights=False)
    for obj in selection:
        obj.select_set(False)


def evidence(record):
    regular="C:/Windows/Fonts/msyh.ttc"
    title=ImageFont.truetype(regular,34)
    heading=ImageFont.truetype(regular,25)
    body=ImageFont.truetype(regular,19)
    small=ImageFont.truetype(regular,15)
    ink="#233a46"
    canvas=Image.new("RGB",(1550,1585),"#f7f6f0")
    draw=ImageDraw.Draw(canvas)
    draw.text((72,36),"教室与男女生公寓 · 典型楼层布置",font=title,fill=ink)
    draw.text((72,88),"房间、楼道和楼梯按校园母版坐标绘制。楼层与房间数量为本轮复制布置。",font=body,fill=ink)
    for index,(bid,data) in enumerate(record["楼栋"].items()):
        dorm=bid in ("B25","B28")
        frame=Frame(bid,dorm)
        row=(155,405,655,1045)[index]
        baseline=row+(347 if dorm else 138)
        x_shift=775 if dorm else 295
        scale=10.3
        def project(x,y):
            return (x_shift+y*scale,baseline+x*scale)
        def rect(x0,x1,y0,y1,color,outline=ink):
            draw.rectangle((*project(x0,y0),*project(x1,y1)),fill=color,outline=outline,width=1)
        def label(x,y,t):
            draw.text(project(x,y),t,font=small,fill=ink,anchor="mm")
        draw.text((72,row),f'{data["名称"]}  {bid}',font=heading,fill=ink)
        count=sum(data["每层"]) if dorm else data["每层"]
        floor_count=len(data["内外楼层标高"] if dorm else data["楼层标高"])
        draw.text((1480,row+4),f'{count} 间/层 × {floor_count} 层 = {data["房间数"]} 间',
                  font=body,fill=ink,anchor="ra")
        draw.polygon([project(v.x,v.y) for v in frame.corners],fill="#ebe9e1",outline="#667881",width=2)
        if dorm:
            center=data["中央通道中心"]
            y0,y1=data["走廊范围"]
            rect(center-HALL_HALF,center+HALL_HALF,y0,y1,"#c1d4db")
            for side,key in ((-1,"北"),(1,"南")):
                edge=center+side*HALL_HALF
                xa,xb=sorted((edge,edge+side*DORM_DEPTH))
                for y in data["房间轴线"][key]:
                    rect(xa,xb,y-DORM_WIDTH/2,y+DORM_WIDTH/2,"#bed3c6")
            rect(center+HALL_HALF,0,-3.7,3.7,"#ead6a7")
            label(-3.8,0,"门厅")
            stair_y=data["楼梯起点"]
            rect(center+HALL_HALF,center+HALL_HALF+2.65,stair_y-.4,stair_y+4.1,"#d9b791")
            label(-2.0,stair_y+1.8,"楼梯")
        else:
            start,end=data["轴向范围"]
            rect(-6.31,-3.09,1.45,end,"#c1d4db")
            for i in range(data["每层"]):
                offset=start+i*CLASS_STEP
                rect(-3.09,5.21,offset,offset+ROOM_Y,"#d4dcb5")
                label(.9,offset+ROOM_Y/2,f"教室 {i+1:02d}")
            rect(-3.09,2.59,1.45,3.38,"#ead6a7")
            rect(-1.49,1.16,3.38,8.1,"#d9b791")
            label(3.5,5.5,"楼梯")
    legend=(("教室","#d4dcb5"),("宿舍","#bed3c6"),("主楼道","#c1d4db"),("门厅","#ead6a7"),("楼梯","#d9b791"))
    for i,(label,color) in enumerate(legend):
        x=72+i*132
        draw.rectangle((x,1500,x+26,1523),fill=color,outline=ink)
        draw.text((x+36,1497),label,font=body,fill=ink)
    canvas.save(OUT/"楼层布置图.png")
    comparisons=(
        ("教室","17","315","教学_01_后排看讲台"),
        ("教学楼楼道","16","000","教学_整层走廊"),
        ("男生公寓宿舍","27","000","男生公寓_宿舍样板"),
        ("女生公寓宿舍","30","000","女生公寓_宿舍样板"),
        ("男生公寓首层大厅","26","000","男生公寓_首层大厅"),
        ("女生公寓首层大厅","29","000","女生公寓_首层大厅"),
    )
    for label,sid,angle,view in comparisons:
        image=Image.new("RGB",(1580,812),"#f7f6f0")
        draw=ImageDraw.Draw(image)
        draw.text((25,24),label,font=title,fill=ink)
        draw.text((25,82),f"实拍全景 {sid} / {angle}°",font=body,fill=ink)
        draw.text((818,82),"校园母版模型视角",font=body,fill=ink)
        with Image.open(photo(sid,angle)) as original:
            image.paste(ImageOps.contain(original.convert("RGB"),(730,660)),(25,126))
        with Image.open(OUT/"模型视角"/(view+".png")) as model:
            image.paste(ImageOps.contain(model.convert("RGB"),(735,660)),(818,126))
        image.save(OUT/"实景对照"/(label+".jpg"),quality=94)


def build():
    for name in ("模型视角","实景对照","贴图"):
        (OUT/name).mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE),load_ui=False)
    scene=bpy.context.scene
    scene.name="校园 · 教室与男女生公寓室内"
    scene.unit_settings.system="METRIC"
    root=collection("楼内还原",scene.collection)
    staging=collection("房间共享模板 · 构件来源",scene.collection)
    mats=palette()
    class_template=classroom_sample(staging)
    dorm_templates={}
    for girls in (False,True):
        sample=dorm_sample(scene,staging,mats,girls)
        bpy.context.view_layer.update()
        dorm_templates[girls]=joined_templates(staging,list(sample.all_objects),sample.name+"共享网格")
    views=[]
    records={}
    for bid in ("B15","B21"):
        school(scene,root,mats,bid,class_template,views,records)
    for bid in ("B25","B28"):
        dormitory(scene,root,mats,bid,dorm_templates[bid=="B28"],views,records)
    scene.collection.children.unlink(staging)
    bpy.data.collections.remove(staging)
    scene.camera=views[0]
    scene.view_settings.view_transform="AgX"
    scene.render.engine="CYCLES"
    scene.cycles.samples=16
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1080
    scene.render.resolution_y=765
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    bpy.context.preferences.filepaths.save_version=0
    for area in (bpy.context.screen.areas if bpy.context.screen else ()):
        if area.type=="VIEW_3D":
            area.spaces.active.region_3d.view_perspective='CAMERA'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" not in sys.argv:
        export(scene,OUT/(STEM+".glb"),False)
        export(scene,OUT/"教室与男女生公寓室内.glb",True)
    record={"校园母版":str(SOURCE.relative_to(ROOT.parent)),
            "教室样板":str(CLASS_SOURCE.relative_to(ROOT.parent)),
            "楼栋":records,"相机":[obj.name for obj in views],
            "估排说明":"教室引用16/17站和用户补图，配置于致远楼、思远楼。公寓以25–30站外景、门厅和宿舍为依据。房间数、隔墙、楼层标高与楼梯位置按现有母版排布。外立面窗格沿用母版，室内外窗尚未逐开间对位。楼内其余房型和功能室待素材补齐。",
            "室外接入改动":"清空四栋楼原入口背板，打开教学楼西侧玻璃门，蕙远楼门前一株行道树外移到门侧。",
            "编辑":"复制房间使用共享网格。修改某一间前可把该房间的网格改为独立副本。四栋楼位于 Blender 的「楼内还原」集合下。",
            "导出":"校园GLB含室内外。室内GLB按同一原点导出室内网格，适合与原校园坐标叠放。两份GLB均为外观网格。"}
    (OUT/"定位与来源.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if "--models-only" in sys.argv:
        return
    for obj in views:
        if "--draft" in sys.argv and not any(name in obj.name for name in ("后排","整层","男生公寓_宿舍","女生公寓_首层")):
            continue
        scene.camera=obj
        if "--draft" in sys.argv:
            scene.render.resolution_percentage=65
            scene.cycles.samples=8
        scene.render.filepath=str(OUT/"模型视角"/(obj.name+".png"))
        bpy.ops.render.render(write_still=True)
    if "--draft" not in sys.argv:
        evidence(record)


if __name__=="__main__":
    if "--evidence-only" in sys.argv:
        evidence(json.loads((OUT/"定位与来源.json").read_text(encoding="utf-8")))
    else:
        build()
