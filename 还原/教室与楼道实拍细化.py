"""Build an editable classroom and connected corridor from the campus references."""

import json
import math
import random
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

from 第二轮室内 import Room


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "成果/教室与楼道实拍细化"
STEM = "教室与楼道"
PANOS = ROOT.parent / "数据/04_建模参考/02_八方向"
PHOTOS = Path("D:/缓存/wexin/xwechat_files/wxid_6bn0wgbigo1j22_1400/temp/RWTemp/2026-11/9e20f478899dc29eb19741386f9343c8")
WALL_X, HALL_X = -4.15, -7.38
ROOM_Y, TOP, HALL_TOP = 9.82, 3.48, 2.99
HALL_START, HALL_END = -4.2, 27.1
DOORS = (.83, 8.93)
DESK_X = (-3.35,-2.72,-1.39,-.76,-.13,1.30,1.93,2.56)
DESK_Y = (2.05,3.08,4.10,5.13,6.16,7.18,8.20)
VIEWS = (
    ("01_后排看讲台",(.47,9.52,1.65),(.05,1.3,1.63),22),
    ("02_讲台侧看向窗边和后墙",(-3.50,.53,1.72),(1.13,5.35,1.41),19),
    ("03_窗边看后排", (3.67,1.10,1.79),(-.19,6.53,1.24),21),
    ("04_楼道沿线",(-5.84,-2.71,1.62),(-5.71,15,1.42),25),
    ("05_楼道走进教室",(-5.43,.65,1.62),(1.79,1.95,1.36),18),
)

PALETTE = {
    "plaster":(.78,.758,.695), "ceiling":(.83,.821,.754), "frame":(.64,.65,.62),
    "darkframe":(.248,.238,.216), "grid":(.295,.283,.246), "skirt":(.156,.356,.274),
    "base":(.19,.212,.189), "blue":(.032,.232,.36), "brass":(.46,.311,.122),
    "door":(.079,.024,.018), "door_edge":(.038,.013,.012), "steel":(.30,.319,.28),
    "box":(.38,.404,.374), "desk_green":(.115,.282,.154), "rubber":(.037,.038,.033),
    "ply":(.382,.194,.073), "chalk":(.034,.106,.094), "screen":(.715,.748,.727),
    "black":(.025,.029,.031), "plastic":(.66,.673,.635), "radiator":(.73,.704,.625),
    "locker":(.644,.661,.613), "locker_edge":(.133,.168,.175), "wood_trim":(.219,.132,.058),
    "fabric":(.101,.125,.146), "red":(.52,.052,.061), "royal":(.022,.155,.474),
    "green":(.035,.337,.205), "paper":(.82,.816,.729), "pale":(.75,.706,.548),
    "yellow":(.83,.553,.09), "leaf":(.103,.235,.061), "bark":(.25,.154,.080),
    "silver":(.56,.594,.589), "vent":(.087,.106,.108),
}


class Interior(Room):
    def __init__(self, scene, mats):
        super().__init__(scene, 8.3, ROOM_Y, TOP)
        self.mats = mats
        self.collection = scene.collection
        self.sections = {}

    def section(self, label):
        self.groups = self.sections.setdefault(label,{})
        return self.groups

    def polygons(self, label, key, points, faces):
        verts, polys, keys = self.groups.setdefault(label, ([],[],[]))
        offset = len(verts)
        verts.extend(points)
        polys.extend(tuple(i+offset for i in face) for face in faces)
        keys.extend([key]*len(faces))

    def rod(self, label, key, a, b, radius, sides=10, other_radius=None):
        axis = (Vector(b)-Vector(a)).normalized()
        across = axis.cross(Vector((0,0,1)))
        if across.length<1e-6:
            across = axis.cross(Vector((1,0,0)))
        across.normalize()
        depth = axis.cross(across)
        points = [Vector(p)+r*(across*math.cos(i*math.tau/sides)+depth*math.sin(i*math.tau/sides))
                  for p,r in ((a,radius),(b,other_radius or radius)) for i in range(sides)]
        faces = [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
        faces.extend((tuple(reversed(range(sides))),tuple(range(sides,2*sides))))
        self.polygons(label,key,points,faces)

    def rounded(self, label, key, x, y, z, w, d, h, radius, angle=0):
        outline = []
        for sx,sy,start in ((1,1,0),(-1,1,90),(-1,-1,180),(1,-1,270)):
            for j in range(5):
                a = math.radians(start+j*22.5)
                u = sx*(w/2-radius)+radius*math.cos(a)
                v = sy*(d/2-radius)+radius*math.sin(a)
                outline.append((x+u*math.cos(angle)-v*math.sin(angle),
                                y+u*math.sin(angle)+v*math.cos(angle)))
        n = len(outline)
        self.polygons(label,key,[(u,v,z+offset) for offset in (-h/2,h/2) for u,v in outline],
                      [tuple(reversed(range(n))),tuple(range(n,2*n))]
                      +[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])

    def obj(self, collection, label, points, faces, keys, explicit_uv=None):
        data = bpy.data.meshes.new(label)
        data.from_pydata(points,[],faces)
        data.update()
        obj = bpy.data.objects.new(label,data)
        collection.objects.link(obj)
        indices = {}
        for key in dict.fromkeys(keys):
            indices[key] = len(indices)
            data.materials.append(self.mats[key])
        uv = data.uv_layers.new(name="Surface")
        for face,key in zip(data.polygons,keys):
            face.material_index = indices[key]
            axis = max(range(3), key=lambda i: abs(face.normal[i]))
            a,b = ((1,2),(0,2),(0,1))[axis]
            su,sv = self.mats[key].get("repeat_metres",(1,1))
            for i in face.loop_indices:
                vi = data.loops[i].vertex_index
                v = data.vertices[vi].co
                uv.data[i].uv = explicit_uv[vi] if explicit_uv else (v[a]/su,v[b]/sv)
        return obj

    def panel(self, label, key, center, u, v, width, height):
        center,u,v = Vector(center),Vector(u),Vector(v)
        points = [center+u*x*width/2+v*y*height/2 for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
        col = bpy.data.collections.get(self.panel_group)
        if col is None:
            col = bpy.data.collections.new(self.panel_group)
            self.collection.children.link(col)
        return self.obj(col,label,points,[(0,1,2,3)],[key],((0,0),(1,0),(1,1),(0,1)))

    def finish(self):
        for name,groups in self.sections.items():
            collection = bpy.data.collections.new(name)
            self.collection.children.link(collection)
            for label, (points,faces,keys) in groups.items():
                self.obj(collection,label,points,faces,keys)


def material(name, color, rough=.72, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color,1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color,1)
    shader.inputs["Roughness"].default_value = rough
    shader.inputs["Metallic"].default_value = metallic
    return mat


def texture(mat, image, repeat=(1,1)):
    path = OUT / "贴图" / (mat.name+".png")
    image.save(path)
    img = bpy.data.images.load(str(path))
    img.pack()
    mat["repeat_metres"] = repeat
    nt = mat.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.links.new(node.outputs["Color"],nt.nodes["Principled BSDF"].inputs["Base Color"])


def rectify(source, quad, size):
    with Image.open(source) as im:
        rgb = np.asarray(im.convert("RGB"))
    w,h = size
    dst = ((0,0),(w-1,0),(w-1,h-1),(0,h-1))
    warp = cv2.getPerspectiveTransform(np.float32(quad),np.float32(dst))
    return Image.fromarray(cv2.warpPerspective(rgb,warp,size))


def surface_tile(base, form):
    rng = np.random.default_rng(1789)
    coarse = rng.normal(0,1,(48,64)).astype(np.float32)
    coarse = cv2.resize(coarse,(512,512),interpolation=cv2.INTER_CUBIC)
    fine = rng.normal(0,1,(512,512))
    if form=="stone":
        grain = np.where(fine>1.20,30,np.where(fine<-1.08,-31,fine*6)) + coarse*5
    elif form=="wood":
        stripes = cv2.resize(rng.normal(0,1,(80,5)),(512,512),interpolation=cv2.INTER_LINEAR)
        grain = stripes*7 + fine*2.4 + coarse*2
    else:
        grain = coarse*3.3 + fine*2.7
    return Image.fromarray(np.clip(np.asarray(base)[None,None,:]+grain[:,:,None],0,255).astype(np.uint8))


def artwork(key):
    sizes = {"clock":(512,512),"front":(1024,360),"slide":(900,510),"banner":(1560,265),
             "notice":(640,850),"class_id":(500,230),"book":(512,700),"rules":(760,570),
             "desktop":(720,286),"exit":(430,190)}
    img = Image.new("RGB",sizes[key],"#e8e7db")
    d = ImageDraw.Draw(img)
    def font(size):
        return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",size)

    if key=="clock":
        d.ellipse((5,5,506,506),fill="#f1eee1")
        for i in range(60):
            a=i*math.tau/60
            u,v=math.sin(a),-math.cos(a)
            r=209 if i%5==0 else 220
            d.line((256+233*u,256+233*v,256+r*u,256+r*v),fill="#292f2e",width=4 if i%5==0 else 2)
        for i in range(1,13):
            a=i*math.tau/12
            d.text((256+173*math.sin(a),256-173*math.cos(a)),str(i),font=font(43),fill="#202824",anchor="mm")
        d.line((256,256,302,162),fill="#1e2322",width=11)
        d.line((256,256,264,87),fill="#29322f",width=7)
        d.line((256,286,210,423),fill="#942a27",width=3)
    elif key=="front":
        d.rectangle((0,0,*img.size),fill="#17342e")
    elif key=="slide":
        d.rectangle((20,22,880,488),fill="#e5eae7",outline="#aeb7b2",width=3)
    elif key=="banner":
        d.rectangle((0,0,*img.size),fill="#9a3540")
        d.text((780,125),"金榜题名日　还赖寒窗磨杵功",font=font(101),fill="#e5bb67",anchor="mm")
    elif key=="exit":
        d.rectangle((0,0,*img.size),fill="#1c634a")
        d.text((215,90),"安全出口 →",font=font(63),fill="white",anchor="mm")
    else:
        title = {"notice":"课程表","class_id":"教室","book":"学习笔记","rules":"班级公告","desktop":"练习与笔记"}[key]
        w,h=img.size
        fill = "#255c7d" if key in ("notice","book") else "#406066"
        d.rectangle((13,14,w-13,97),fill=fill)
        d.text((w/2,56),title,font=font(44),fill="white",anchor="mm")
        for row in range(114,h-19,28):
            d.line((35,row,w-35,row),fill="#bbc0b4",width=2)
        if key=="notice":
            for x in range(42,w-30,96):
                d.line((x,114,x,h-20),fill="#8daba7",width=2)
    return img


def materials():
    mats = {key: material(key,color,.41 if key in ("silver","steel","brass") else .74,
                          .48 if key in ("silver","steel") else 0) for key,color in PALETTE.items()}
    for key,base,form,repeat,rough in (
        ("class_tile",(154,148,134),"stone",(.62,.62),.43),
        ("hall_tile",(153,145,130),"stone",(.66,.66),.24),
        ("laminate",(194,137,65),"wood",(.60,.43),.38),
        ("curtain",(135,138,95),"wood",(.46,.79),.87),
        ("paint_green",(93,145,122),"paint",(1.05,.95),.83),
        ("blue_floor",(40,103,139),"paint",(.93,.93),.53),
    ):
        mats[key] = material(key,tuple((x/255)**2.2 for x in base),rough)
        texture(mats[key],surface_tile(base,form),repeat)
    for key, color, alpha in (("glass",(.55,.70,.72),.14),("frost",(.62,.67,.62),.70)):
        mat = material(key,color,.19 if key=="glass" else .43)
        mat.diffuse_color = (*color,alpha)
        mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "DITHERED"
        mats[key] = mat
    mats["light"] = material("light",(.95,.96,.86),.45)
    shader = mats["light"].node_tree.nodes["Principled BSDF"]
    shader.inputs["Emission Color"].default_value = (.94,.972,1,1)
    shader.inputs["Emission Strength"].default_value = 3.0
    for key in ("clock","front","slide","banner","notice","class_id","book","rules","desktop","exit"):
        mats[key] = material(key,(.5,.5,.5),.88)
        texture(mats[key],artwork(key))
    hall = PANOS / "16_直饮水"
    mats["marble"] = material("marble",(.50,.35,.21),.43)
    texture(mats["marble"],rectify(hall/"090.jpg",((318,839),(552,837),(556,1221),(320,1232)),(384,512)),(.64,1.08))
    mats["hall_view"] = material("hall_view",(.72,.74,.62),.85)
    texture(mats["hall_view"],rectify(hall/"180.jpg",((576,580),(810,580),(810,903),(576,903)),(480,640)))
    nt = mats["hall_view"].node_tree
    nt.links.new(next(node for node in nt.nodes if node.type=="TEX_IMAGE").outputs["Color"],
                 nt.nodes["Principled BSDF"].inputs["Emission Color"])
    nt.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = .77
    rear = PHOTOS / "d41760c1696cc42299985ff845f29312.jpg"
    mats["rear_chalk"] = material("rear_chalk",(.048,.125,.111),.88)
    if rear.is_file():
        texture(mats["rear_chalk"],rectify(rear,((913,275),(1549,174),(1560,371),(930,438)),(1280,390)))
    else:
        texture(mats["rear_chalk"],artwork("front"))
    board = PANOS / "17_教室/225.jpg"
    mats["erased_board"] = material("erased_board",(.049,.115,.098),.83)
    texture(mats["erased_board"],rectify(board,((52,198),(940,144),(944,714),(55,681)),(1000,550)))
    return mats


def intervals(a,b,holes):
    last = a
    for lo,hi in sorted(holes):
        if lo>last:
            yield last,lo
        last=hi
    if last<b:
        yield last,b


def wall_along_y(m, label, x, a, b, height, apertures, lower):
    m.box(label+"基层","plaster",x,(a+b)/2,height-.15,.21,b-a,.30)
    z_values = sorted({0,1.08,height-.30}|{z for _,_,z0,z1 in apertures for z in (z0,z1)})
    for z0,z1 in zip(z_values,z_values[1:]):
        openings = [(y0,y1) for y0,y1,low,high in apertures if low<=z0 and z1<=high]
        for y0,y1 in intervals(a,b,openings):
            dz=z1-z0
            m.box(label+"实墙","plaster",x,(y0+y1)/2,z0+dz/2,.21,y1-y0,dz)
            if z1<=1.08:
                for sign,key in lower:
                    m.box(label+"墙裙",key,x+sign*.111,(y0+y1)/2,z0+dz/2,.014,y1-y0,dz)
                    if z0==0:
                        m.box(label+"踢脚","base",x+sign*.125,(y0+y1)/2,.047,.020,y1-y0,.094)


def tiles(m,label,key,x0,x1,y0,y1,pitch):
    m.box(label+"底板","grid",(x0+x1)/2,(y0+y1)/2,-.066,x1-x0,y1-y0,.128)
    for x in np.arange(x0,x1-.001,pitch):
        for y in np.arange(y0,y1-.001,pitch):
            w=min(pitch,x1-x)
            d=min(pitch,y1-y)
            m.box(label,key,x+w/2,y+d/2,.002,w-.003,d-.003,.007)


def side_window(m,x,y,w,lo,hi,key="glass",parts=3):
    b=m.box
    for level in (lo,hi):
        b("铝合金窗横框","frame",x,y,level,.125,w+.07,.045)
    for k in range(parts+1):
        b("铝合金窗竖框","frame",x,y-w/2+k*w/parts,(lo+hi)/2,.117,.046,hi-lo)
    for k in range(parts):
        cy=y-w/2+(k+.5)*w/parts
        b("窗洞玻璃",key,x,cy,(lo+hi)/2,.015,w/parts-.041,hi-lo-.046)
    if hi-lo>1.2:
        b("侧窗上亮水平框","frame",x,y,hi-.52,.099,w,.047)
        b("滑窗银色执手","silver",x-.067,y-.30,(lo+hi)/2,.032,.040,.19)
    b("外挑灰白窗台板","plastic",x,y,lo-.052,.292,w+.11,.063)


def door(m,x,y,swing=None):
    b=m.box
    for off in (-.51,.51):
        b("门边深色木套线","door_edge",x,y+off,1.36,.23,.093,2.72)
    for z in (2.19,2.69):
        b("门楣及亮窗木横框","door",x,y,z,.235,1.10,.072)
    b("门顶磨砂亮窗","frost",x,y,2.44,.018,.94,.41)
    for intercept in np.arange(-.34,1.30,.139):
        for slope in (-.46,.46):
            near,far=sorted((-intercept/slope,(.92-intercept)/slope))
            a,bound=max(0,near),min(1,far)
            if bound-a>.02:
                for depth in (-.103,.103):
                    m.rod("菱格门顶铁艺","door_edge",
                          (x+depth,y-.46+intercept+slope*a,2.235+.411*a),
                          (x+depth,y-.46+intercept+slope*bound,2.235+.411*bound),.008,7)
    hinge=Vector((x-.063 if swing else x,y+.462,0))
    angle=math.radians(swing if swing is not None else -90)
    u=Vector((math.cos(angle),math.sin(angle),0))
    v=Vector((-u.y,u.x,0))
    def leaf(label,key,d,z,w,h,offset=0,thickness=.044):
        p=hinge+u*d+v*offset
        b(label,key,p.x,p.y,z,w,thickness,h,angle)
    leaf("门扇实木底段","door",.467,.40,.933,.767)
    leaf("门扇实木上段","door",.467,1.998,.933,.323)
    leaf("门扇大边梃","door",.248,1.32,.493,1.09)
    leaf("门扇窄边梃","door",.85,1.32,.168,1.09)
    leaf("门上狭长玻璃","glass",.631,1.32,.273,1.09,thickness=.012)
    for sign in (-1,1):
        for d in (.498,.764):
            leaf("门上窄玻璃四周压条","frame",d,1.32,.024,1.105,sign*.025,.020)
        for z in (.772,1.866):
            leaf("门上窄玻璃四周压条","frame",.631,z,.29,.027,sign*.025,.018)
        leaf("不锈钢门锁面板","silver",.856,1.028,.072,.243,sign*.031,.023)
        leaf("水平门把手","silver",.814,1.079,.121,.028,sign*.074,.083)
        for z in (.255,.575):
            leaf("木门下部槽板","door_edge",.47,z,.72,.222,sign*.023,.007)
            leaf("木门下部内芯","door",.47,z,.681,.19,sign*.028,.011)


def ceiling_and_shell(m):
    b=m.box
    m.section("01 教室 | 墙体、地面、门洞和侧窗")
    tiles(m,"水磨石地砖","class_tile",-4.15,4.15,0,ROOM_Y,.61)
    b("白色教室天花","ceiling",0,ROOM_Y/2,TOP+.08,8.48,ROOM_Y+.21,.16)
    for y in (0,ROOM_Y):
        b("前后抹灰墙","plaster",0,y,TOP/2,8.49,.208,TOP)
    b("前墙蓝绿墙裙","paint_green",0,.109,.54,8.25,.018,1.08)
    b("后墙暖色石纹墙裙","marble",0,ROOM_Y-.112,.54,8.26,.022,1.08)
    b("后墙深灰踢脚","base",0,ROOM_Y-.125,.043,8.22,.028,.086)
    b("讲台蓝色铺面","blue_floor",.02,.778,.069,8.04,1.332,.137)
    b("讲台沿口黄铜木色压条","brass",.02,1.451,.139,8.05,.025,.027)
    for x in (-.98,-.93,-.88,-.83,-.78,-.73,-.68,-.63):
        b("讲台黄黑角标","yellow" if round(x*100)%2 else "black",x,.46,.141,.051,.047,.008,-.34)
    inner = [(y-.51,y+.51,0,2.69) for y in DOORS]
    high = [(y-1.02,y+1.02,1.96,2.87) for y in (3.12,5.93)]
    wall_along_y(m,"教室与楼道共用墙",WALL_X,0,ROOM_Y,TOP,inner+high,((1,"paint_green"),(-1,"marble")))
    for y in (3.12,5.93):
        side_window(m,WALL_X,y,2.04,1.96,2.87,parts=2)
    door(m,WALL_X,DOORS[0],-169)
    door(m,WALL_X,DOORS[1],11)
    windows = ((1.84,2.72),(4.91,2.83),(7.95,2.76))
    outside = [(y-w/2,y+w/2,1.02,2.95) for y,w in windows]
    wall_along_y(m,"教室外窗墙",4.15,0,ROOM_Y,TOP,outside,((-1,"paint_green"),))
    for y,w in windows:
        side_window(m,4.15,y,w,1.02,2.95)
    m.section("02 教室 | 窗帘、窗下管件与角落设备")
    for number,(y,w) in enumerate(windows):
        m.rod("米色窗帘通长挂杆","brass",(3.90,y-w/2-.12,3.05),(3.90,y+w/2+.12,3.05),.021)
        for j,(start,end) in enumerate(((y-w/2-.09,y+w/2-w*(.35 if number==1 else .64)),
                                       (y+w/2-w*.16,y+w/2+.08))):
            n=102
            points=[]
            for k in range(n+1):
                t=k/n
                for l in range(8):
                    z=l/7
                    folds=2*math.pi*t*(10 if j==0 else 6)
                    x=3.867+.053*math.sin(folds+.33*z)+.016*math.sin(folds*2.1+.63*z)
                    yz=start+(end-start)*t+.017*math.sin(t*math.tau*2)*(1-z)
                    points.append((x,yz,1.067+(3.027-1.067)*z+.026*(1-z)*math.cos(folds)))
            faces=[(k*8+l,(k+1)*8+l,(k+1)*8+l+1,k*8+l+1) for k in range(n) for l in range(7)]
            m.polygons("浅橄榄绿褶皱窗帘","curtain",points,faces)
    m.rod("窗下白色供暖管","radiator",(3.97,.3,.23),(3.97,9.55,.23),.026)
    m.rod("外窗细立管","radiator",(3.98,6.44,.12),(3.98,6.44,3.39),.021)
    b("后窗边白色立式空调","plastic",3.68,9.39,.98,.525,.29,1.96)
    b("空调出风暗口","vent",3.68,9.238,1.714,.412,.016,.287)
    b("空调黑屏","black",3.68,9.231,1.376,.145,.018,.056)
    for i in range(7):
        b("空调水平叶片","plastic",3.68,9.222,1.592+i*.040,.414,.032,.012)
    b("后门边蓝色废纸桶","royal",-2.95,9.56,.36,.379,.31,.72)
    b("废纸桶蓝罩和投口","vent",-2.95,9.55,.749,.315,.242,.065)


def teaching_wall(m):
    m.section("03 教室 | 讲台、滑轨黑板与投影")
    m.panel_group = "08 教室 | 黑板、展板和印刷件"
    b=m.box
    b("滑轨黑板外铝框","darkframe",.04,.180,1.861,5.94,.116,1.47)
    b("黑板实板","chalk",.04,.248,1.861,5.82,.047,1.36)
    for x in (-1.45,1.46):
        b("双轨板的竖向铝框","silver",x,.28,1.86,.040,.041,1.41)
    for z in (1.153,2.563):
        b("双层银灰板轨","silver",.04,.287,z,5.96,.090,.048)
    m.panel("前板擦拭痕迹","erased_board",(2.179,.279,1.86),(-1,0,0),(0,0,1),1.44,1.261)
    m.panel("教室前黑板","front",(-2.19,.275,1.86),(-1,0,0),(0,0,1),1.38,1.32)
    b("投影幕白边","screen",.009,.297,1.866,2.83,.027,1.375)
    m.panel("幕布上的课堂课件","slide",(.009,.312,1.866),(-1,0,0),(0,0,1),2.75,1.297)
    m.rod("前黑板钟外圈","black",(.09,.112,2.99),(.09,.166,2.99),.191,48)
    n=72
    # The circular metal body remains editable, with a fitted printed dial.
    clock_vertices=[(.09,.169,2.99)]+[(.09+.178*math.cos(i*math.tau/n),.169,
                                       2.99+.178*math.sin(i*math.tau/n)) for i in range(n)]
    clock_uv=[(.50,.50)]+[(.5-.5*math.cos(i*math.tau/n),.5+.5*math.sin(i*math.tau/n)) for i in range(n)]
    m.obj(bpy.data.collections[m.panel_group],"黑框白底教室挂钟",clock_vertices,
          [(0,(i+1)%n+1,i+1) for i in range(n)],["clock"]*n,clock_uv)
    for x in (-3.22,3.23):
        b("黑板边扩音箱","plastic",x,.18,2.849,.236,.133,.278)
        b("音箱面网","vent",x,.255,2.847,.180,.028,.203)
        b("墙面插座与线槽","plastic",x,.124,.29,.101,.040,.105)
        b("沿墙竖线槽","plastic",x-.089,.122,1.63,.024,.021,2.66)
    b("投影悬架横臂","frame",.09,.78,3.014,.080,1.52,.078)
    b("灰白短焦投影机","plastic",.09,1.33,2.968,.340,.309,.116)
    m.rod("投影镜头","black",(.09,1.179,2.977),(.09,1.144,2.977),.044,18)
    b("灰白多媒体讲台立柜","plastic",.48,.888,.603,1.27,.636,.927)
    b("灰白金属讲台抽屉","box",.48,1.220,.771,1.13,.040,.164)
    b("拉手及讲台柜缝","steel",.48,1.247,.785,.237,.033,.022)
    b("讲台木纹上缘","ply",.48,.888,1.079,1.42,.714,.054)
    m.rounded("讲台木纹台面","laminate",.48,.888,1.100,1.405,.709,.019,.024)
    b("黑色讲台台控","black",.87,.88,1.124,.247,.164,.027)
    b("黑色话筒底座","black",.01,.82,1.124,.145,.114,.024)
    m.rod("讲台鹅颈话筒","black",(.01,.82,1.14),(.01,.88,1.38),.012)
    b("黑板擦与粉笔托","ply",2.32,.351,1.189,.182,.073,.032)
    for x in (.70,.79,.89,1.06):
        m.rod("落在粉笔槽里的粉笔","paper",(x,.319,1.194),(x+.054,.345,1.194),.006,8)

    b("后墙长黑板外框","wood_trim",.75,ROOM_Y-.146,1.852,5.76,.057,1.378)
    b("后墙课表布告板","chalk",-2.67,ROOM_Y-.151,1.86,1.02,.063,1.379)
    m.panel("实拍后黑板粉笔报","rear_chalk",(.75,ROOM_Y-.179,1.852),(1,0,0),(0,0,1),5.67,1.286)
    m.panel("后墙布告板课表","notice",(-2.71,ROOM_Y-.189,1.79),(1,0,0),(0,0,1),.527,.70)
    for i in range(3):
        b("后墙扫把拖把杆","wood_trim",-2.22+i*.125,9.55,.59,.027,.029,1.17)
        b("扫把与拖把头","steel",-2.22+i*.125,9.55,.088,.115,.082,.114)
    b("走廊窗下的磁贴板","darkframe",WALL_X+.139,5.36,1.44,.074,3.89,.96)
    b("绿底移板","chalk",WALL_X+.184,5.36,1.44,.029,3.77,.883)
    m.panel("走廊侧红底挂幅","banner",(WALL_X+.126,4.59,3.071),(0,1,0),(0,0,1),5.54,.423)
    for i in range(6):
        b("黑板磁贴小卡片","paper",WALL_X+.204,4.34+i*.27,1.54+(i%3)*.10,.011,.112,.144)


def open_book(m,x,y,angle):
    co,si=math.cos(angle),math.sin(angle)
    points,uv=[],[]
    for i in range(13):
        t=i/12
        s=t-.5
        u=s*.285
        for v in (-.115,.115):
            points.append((x+u*co-v*si,y+u*si+v*co,.786+.109*abs(s)**1.69
                           +.011*math.exp(-(s/.061)**2)))
            uv.append((1-t,.5-v/.23))
    faces=[(2*i,2*i+2,2*i+3,2*i+1) for i in range(12)]
    m.obj(bpy.data.collections[m.panel_group],"摊开练习册的立体书脊及翻页",points,faces,["desktop"]*12,uv)


def furniture(m):
    b=m.box
    rng = random.Random(680)
    m.panel_group = "08 教室 | 黑板、展板和印刷件"
    for row,y in enumerate(DESK_Y,1):
        for col,x in enumerate(DESK_X,1):
            m.section(f"04 教室 | 第{row}排分体课桌椅")
            x+=rng.uniform(-.014,.014)
            d_y=y+rng.uniform(-.034,.034)
            paint="desk_green" if (row*3+col)%8==0 else "box"
            m.rounded("木纹圆角课桌及封边","ply",x,d_y,.760,.591,.429,.029,.018)
            m.rounded("课桌耐磨木贴面","laminate",x,d_y,.777,.591,.429,.008,.018)
            for a in (-1,1):
                b("钢板书斗侧板",paint,x+a*.268,d_y,.684,.026,.356,.157)
                for side in (-1,1):
                    px,py=x+a*.25,d_y+side*.156
                    m.rod("钢制课桌四腿",paint,(px,py,.035),(px,py,.749),.021,8)
                    b("课桌腿脚垫","rubber",px,py,.021,.045,.045,.042)
                    m.rod("桌面四颗螺钉","steel",(px,py,.782),(px,py,.785),.006,9)
                b("侧边底部钢横撑",paint,x+a*.252,d_y,.21,.027,.354,.027)
            b("书斗朝讲台封板",paint,x,d_y-.178,.674,.532,.024,.169)
            b("开口钢板书斗底",paint,x,d_y,.596,.552,.369,.034)
            b("书斗开口折边","steel",x,d_y+.18,.617,.543,.018,.026)
            b("书桌后横向地脚撑",paint,x,d_y-.155,.193,.522,.029,.026)
            yy=d_y+.48+rng.uniform(-.057,.065)
            m.rounded("椅子木座板","laminate",x,yy,.434,.385,.369,.033,.041)
            b("椅背弧缘木板","ply",x,yy+.154,.674,.367,.031,.181)
            b("椅背木纹前面","laminate",x,yy+.133,.676,.340,.011,.166)
            for a in (-1,1):
                m.rod("椅后脚连椅背",paint,(x+a*.161,yy+.158,.022),(x+a*.159,yy+.160,.755),.017,8)
                m.rod("椅前脚",paint,(x+a*.162,yy-.155,.022),(x+a*.154,yy-.145,.428),.018,8)
                b("椅子侧撑管",paint,x+a*.16,yy,.218,.027,.322,.025)
                b("椅脚橡胶套","rubber",x+a*.16,yy+.155,.027,.040,.041,.052)
                b("椅脚橡胶套","rubber",x+a*.16,yy-.155,.027,.040,.041,.052)
            # A few loosely angled notes and mixed-height stacks complement the steel trays.
            for stack,xoff in enumerate((-.144,.122)):
                shelf = rng.randint(0,3)
                for i in range(shelf):
                    b("桌肚横叠书册","paper",x+xoff,d_y+.015,.628+i*.027,.209,.297,.022,rng.uniform(-.11,.11))
                    b("桌肚书皮",("royal","red","green")[(row+col+i)%3],
                      x+xoff,d_y+.022,.642+i*.027,.215,.302,.005,rng.uniform(-.07,.07))
            if rng.random()>.15:
                bx=x+rng.uniform(-.127,.014)
                book_depth=rng.uniform(.187,.253)
                angle=rng.uniform(-.25,.19)
                stack=rng.randint(1,4)
                for i in range(stack):
                    z=.791+i*.018
                    b("桌面练习册书页","paper",bx,d_y-.079,z,.177,book_depth,.012,angle)
                    b("桌面练习册封面",("royal","green","pale","red")[(i+col+row)%4],bx,d_y-.079,z+.008,.180,book_depth+.006,.004,angle)
                if (row+col)%3==0:
                    eye=(bx,d_y-.079,.803+(stack-1)*.018)
                    m.panel("封面的印刷标题","book",eye,(-math.cos(angle),-math.sin(angle),0),
                            (math.sin(angle),-math.cos(angle),0),.176,book_depth)
                elif (row+2*col)%4==0:
                    open_book(m,x+.135,d_y+.055,rng.uniform(-.30,.32))
                else:
                    m.panel("摊开的练习纸","desktop",(x+.157,d_y+.047,.784),(-1,0,0),(0,-1,0),.188,.227)
            if (row+col*2)%5==0:
                b("侧挂布质书包","fabric",x+.277,d_y+.030,.420,.097,.284,.329,-.11)
                m.rod("书包提带","rubber",(x+.283,d_y-.105,.56),(x+.290,d_y-.014,.710),.014)
            if (row*2+col)%7==0:
                p=(x+.189,d_y-.148)
                m.rod("有色保温水杯",("green","royal","red")[col%3],(*p,.785),(*p,.968),.041,16)
                m.rod("水杯旋盖","silver",(*p,.966),(*p,.991),.043,16)


def corridor(m):
    b=m.box
    m.section("05 楼道 | 相通墙体、窗边和吊顶")
    tiles(m,"楼道抛光浅灰地砖","hall_tile",HALL_X,WALL_X,HALL_START,HALL_END,.637)
    b("楼道整层吊顶基层","grid",(HALL_X+WALL_X)/2,(HALL_START+HALL_END)/2,
      HALL_TOP+.092,WALL_X-HALL_X,HALL_END-HALL_START,.136)
    for i,x in enumerate(np.linspace(HALL_X,WALL_X,6)[:-1]):
        for j,y in enumerate(np.arange(HALL_START,HALL_END,.62)):
            d=min(.62,HALL_END-y)
            b("矿棉格栅吊顶板","light" if i==2 and j%4==2 else "ceiling",
              x+.324,y+d/2,HALL_TOP+.019,.633,d-.013,.037)
    for x in np.linspace(HALL_X,WALL_X,6):
        b("吊顶纵向金属细龙骨","grid",x,(HALL_START+HALL_END)/2,HALL_TOP,.012,HALL_END-HALL_START,.014)
    for y in np.arange(HALL_START,HALL_END,.62):
        b("吊顶横向金属细龙骨","grid",(HALL_X+WALL_X)/2,y,HALL_TOP,WALL_X-HALL_X,.012,.014)
    openings=[(y-.50,y+.50,0,2.69) for y in (-2.63,11.51,18.85,24.93)]
    apertures=[(y-1.04,y+1.04,1.29,2.68) for y in (-2.46,1.02,4.12,7.31,10.66,14.05,17.51,20.89,24.14)]
    wall_along_y(m,"楼道外窗侧",HALL_X,HALL_START,HALL_END,HALL_TOP,apertures,((1,"marble"),))
    for y0,y1,z0,z1 in apertures:
        y=(y0+y1)/2
        side_window(m,HALL_X,y,y1-y0,z0,z1,"glass",2)
        b("窗边白灰方柱","plaster",HALL_X+.095,y1+.19,1.46,.38,.32,2.92)
        b("窗边方柱米色石脚","marble",HALL_X+.105,y1+.19,.541,.405,.342,1.074)
    for a,c in ((HALL_START,0),(ROOM_Y,HALL_END)):
        wall_along_y(m,"教室侧延伸楼道",WALL_X,a,c,TOP,
                     [hole for hole in openings if a<hole[0]<c],((-1,"marble"),))
    for y0,y1,_,_ in openings:
        door(m,WALL_X,(y0+y1)/2)
    for y in (HALL_START,HALL_END):
        b("楼道尽头白色侧墙","plaster",HALL_X+.23,y,1.49,.53,.195,2.99)
        b("楼道尽头白色侧墙","plaster",WALL_X-.23,y,1.49,.53,.195,2.99)
        b("楼道尽头明亮玻璃","glass",(HALL_X+WALL_X)/2,y,.0+1.50,2.22,.027,2.95)
        for x in (-6.84,-5.77,-4.70):
            b("楼道尽头玻璃门窗铝竖框","frame",x,y,1.49,.057,.133,2.99)
        for z in (.11,1.065,2.29,2.91):
            b("楼道尽头玻璃门窗铝横框","frame",-5.77,y,z,2.18,.124,.050)
    m.section("06 楼道 | 储物柜、暖气和门牌")
    m.panel_group = "09 楼道 | 门牌、课程表与指示"
    for center,side,n,style in ((2.87,-1,6,"open"),(7.21,1,5,"closed"),(14.43,1,7,"closed"),(20.24,-1,5,"open")):
        x=HALL_X+.28 if side<0 else WALL_X-.29
        face=x-side*.176
        width=n*.31
        b("灰色储物柜钢背板","locker_edge",x+side*.167,center,1.02,.034,width,1.95)
        for j in range(7):
            z=.10+j*.31
            b("储物柜钢层板","locker",x,center,z,.37,width,.025)
        for i in range(n+1):
            y=center-width/2+i*.31
            b("每列储物箱钢竖板","locker",x,y,1.033,.372,.022,1.88)
            if i==n:
                continue
            for j in range(6):
                yy=y+.155
                z=.254+j*.31
                if style=="closed":
                    b("带缝独立储物柜门","locker",face,yy,z,.038,.286,.284)
                    for t in range(4):
                        b("通风冲孔","locker_edge",face-side*.023,yy+.055,z-.056+t*.014,.008,.068,.005)
                    b("小柜门嵌合拉手","steel",face-side*.022,yy-.087,z,.011,.026,.111)
                b("柜门数字小贴片","royal" if style=="closed" else "paper",
                  face-side*.027,yy-.102,z+.094,.012,.044,.026)
    for y in (-.72,5.7,11.01,16.07,22.21,25.68):
        x=HALL_X+.165
        for i in range(16):
            b("窗下明装暖气片","radiator",x,y+(i-7.5)*.078,.541,.112,.055,.671)
        for z in (.265,.803):
            m.rod("暖气水管","radiator",(x,y-.67,z),(x,y+.67,z),.026)
    for y in (*DOORS,11.51,18.85):
        b("门边蓝白课程表浅底","plastic",WALL_X-.122,y-.78,1.615,.031,.364,.462)
        m.panel("门旁蓝白课程表","notice",(WALL_X-.143,y-.78,1.615),(0,-1,0),(0,0,1),.35,.447)
        m.panel("深木门上绿白教室标牌","class_id",(WALL_X-.15,y,2.86),(0,-1,0),(0,0,1),.293,.135)
    b("窗口下踢脚上小检修盒","locker",HALL_X+.106,12.37,.751,.056,.471,.894)
    for y in (HALL_START+.122,HALL_END-.122):
        b("出口指示薄灯箱","green",-5.78,y,2.682,.454,.066,.168)
        m.panel("安全出口指示","exit",(-5.78,y+(.038 if y<0 else -.038),2.682),
                (-1 if y<0 else 1,0,0),(0,0,1),.442,.16)


def fixtures(m):
    m.section("07 顶部 | 吊挂灯盘、吊扇与线槽")
    b=m.box
    for x in (-2.72,0,2.70):
        for y in (2.14,4.93,7.72):
            for off in (-.426,.426):
                m.rod("灯盘细钢吊杆","silver",(x,y+off,3.143),(x,y+off,TOP),.011)
            b("灰边矩形双管灯盘","darkframe",x,y,3.121,.336,1.205,.078)
            b("白色灯盘格栅底扩散片","light",x,y,3.079,.304,1.161,.013)
            for i in range(17):
                b("灯盘细横栅","frame",x,y+(i-8)*.063,3.071,.309,.011,.010)
            b("空中供电白管","plastic",x,y,TOP-.023,.023,2.74,.031)
    for x in (-1.48,1.49):
        for y in (3.22,6.64):
            m.rod("白色吊扇吊杆","plastic",(x,y,3.17),(x,y,TOP),.018,14)
            m.rod("灰白吊扇电机","frame",(x,y,3.10),(x,y,3.227),.111,20)
            for i in range(3):
                angle=.19+i*math.tau/3
                u=math.cos(angle)
                v=math.sin(angle)
                m.rounded("三叶扇叶","ceiling",x+.36*u,y+.36*v,3.125,.608,.093,.019,.033,angle)
    for x in (-1.49,1.49):
        for dx in (-.48,.48):
            m.rod("讲台板面灯两端吊杆","silver",(x+dx,.50,2.975),(x+dx,.50,3.445),.013)
        b("悬吊条形黑板灯","darkframe",x,.50,2.967,1.27,.167,.079)
        b("黑板灯扩散条","light",x,.475,2.928,1.17,.102,.012)
    for y in (1.9,12.33,21.5):
        m.rod("吊顶白色小圆壳","plastic",(-6.91,y,2.88),(-6.91,y,2.98),.065,14,.088)


def exterior_light_context(m):
    m.section("10 窗外 | 采光背景与相邻楼体轮廓")
    m.panel_group = "11 楼道窗外实拍背景"
    m.panel("玻璃尽头的窗外实拍景致","hall_view",(-5.77,HALL_END+1.10,1.49),(1,0,0),(0,0,1),3.7,3.6)
    b=m.box
    b("窗外远处地坪","base",0,6,-2.45,55,60,.30)
    for side in (-1,1):
        x=side*17
        b("窗外简化的邻楼墙面","marble",x,11,1.7,3.78,34,8.8)
        for y in np.arange(-4,27,2.85):
            for z in (-.4,2.4,5.2):
                b("窗外邻楼灰色窗格","glass",x-side*1.90,y,z,.035,1.41,1.22)
    for x,y,h in ((8.7,1.8,3.8),(10.2,5.5,5.4),(9,10,4.8),(-11.5,5,5.06),(-10,10,5.5),(-11,19,5.0)):
        m.rod("窗外乔木树干","bark",(x,y,-2.25),(x,y,h-1.8),.104,9)
        for a in range(7):
            direction=a*2.399
            u,v=math.cos(direction),math.sin(direction)
            m.rod("采光背景简化树冠","leaf",(x+u*.72,y+v*.72,h-2.9+a*.24),
                  (x+u*.53,y+v*.53,h-1.55+a*.24),.819,12,.37)


def aimed(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()


def light(scene,name,position,target,power,size,shape="DISK",short=None):
    data=bpy.data.lights.new(name,"AREA")
    data.energy=power
    data.shape=shape
    data.size=size
    if short is not None:
        data.size_y=short
    obj=bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location=position
    aimed(obj,target)


def lighting_and_views(scene):
    world_obj=bpy.data.worlds.new("校园阴晴间自然天光")
    world_obj.use_nodes=True
    world_obj.node_tree.nodes["Background"].inputs["Color"].default_value=(.72,.82,1.0,1)
    world_obj.node_tree.nodes["Background"].inputs["Strength"].default_value=.48
    scene.world=world_obj
    for y in (1.84,4.91,7.95):
        light(scene,"外窗天光",(4.68,y,2.42),(-1.6,y,1.31),310,2.34,"RECTANGLE",1.88)
    for y in (2.19,5.02,7.76):
        for x in (-2.40,.15,2.56):
            light(scene,"教室顶灯柔光",(x,y,3.045),(x,y,.99),39,.80)
    light(scene,"讲台黑板近区灯",(.12,1.03,2.941),(.12,.001,1.77),62,2.23,"RECTANGLE",.34)
    for y in np.arange(-2.7,HALL_END,2.35):
        light(scene,"走廊顶灯照明",(-5.76,y,2.945),(-5.76,y,.54),59,.56)
    for y in (1.02,7.31,14.05,20.89,24.14):
        light(scene,"楼道窗间漫射光",(-7.57,y,2.24),(-5.02,y,.97),111,1.71,"RECTANGLE",1.48)
    light(scene,"楼道尽端窗口漫射光",(-5.76,27.35,2.18),(-5.76,23.3,1.5),106,1.72)
    views={}
    for name,position,target,lens in VIEWS:
        data=bpy.data.cameras.new(name)
        data.lens=lens
        data.clip_start=.035
        camera=bpy.data.objects.new(name,data)
        scene.collection.objects.link(camera)
        camera.location=position
        aimed(camera,target)
        views[name]=camera
    return views


def main():
    for folder in ("贴图","模型视角"):
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.name = "教室与楼道实拍还原"
    scene.unit_settings.system="METRIC"
    mesh=Interior(scene,materials())
    ceiling_and_shell(mesh)
    teaching_wall(mesh)
    furniture(mesh)
    corridor(mesh)
    fixtures(mesh)
    exterior_light_context(mesh)
    mesh.finish()
    views=lighting_and_views(scene)
    scene.camera=views[VIEWS[0][0]]
    scene.view_settings.view_transform="AgX"
    scene.render.engine="CYCLES"
    scene.cycles.samples=28
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1200
    scene.render.resolution_y=840
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.film_transparent=False
    bpy.context.preferences.filepaths.save_version=0
    objects=[o for o in scene.objects if o.type=="MESH"]
    assert all(all(f.area>0 for f in o.data.polygons) for o in objects)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")), export_format="GLB",
                              export_cameras=False, export_lights=False)
    record={"参考":["用户6.3秒视频及教室、楼道补图","场景17教室全景各方向","场景16直饮水站沿楼道方向"],
            "教室尺寸米":[8.3,ROOM_Y,TOP],"楼道净宽与吊顶高度米":[WALL_X-HALL_X-.22,HALL_TOP],
            "走廊范围米":[HALL_START,HALL_END],"教室门洞中心米":DOORS,"课桌排布":[list(DESK_X),list(DESK_Y)],
            "相机":VIEWS,"实拍纹理":"后墙黑板报取自第4张；前黑板擦痕来自17站225°。",
            "估算与取舍":"不同批次的教室图兼用。室内以有蓝讲台和投影幕的版本为准，布告和课件依照片重绘。尺寸、56桌排布、楼道长度、两门在楼道中的位置均为估算。楼层、具体教室门号与室外母版的对接位置待核实。",
            "网格数":len(objects)}
    (OUT/"定位与来源.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for label,*_ in VIEWS:
        scene.camera=views[label]
        scene.render.filepath=str(OUT/"模型视角"/(label+".png"))
        bpy.ops.render.render(write_still=True)


if __name__=="__main__":
    main()
