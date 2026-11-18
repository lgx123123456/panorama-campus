"""Align Kongde Square and its gardens to the owner's aerial and ground photographs."""

import json
import math
import random
from pathlib import Path

import bpy
import bmesh
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import 思远志远连廊与孔德广场 as prior_square
from 三处庭院实拍细化 import foliage_cards, panel, unwrap_textured_boxes
from 公寓与运动区实拍细化 import OUT as PREVIOUS, STEM as PREVIOUS_STEM, rod, segment
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 四栋教学楼实景细化 import reference
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 地面街道实景细化 import Ground
from 尚德广场实拍细化 import photo_material
from 楼间过道实拍细化 import camera, clean_generated_meshes


SOURCE = PREVIOUS / (PREVIOUS_STEM + ".blend")
OUT = PREVIOUS.parent / "孔德广场与两侧花园实拍细化"
STEM = "校园室外_孔德广场与两侧花园"
SCREENSHOT_DIR = Path(
    "D:/缓存/wexin/xwechat_files/wxid_6bn0wgbigo1j22_1400/temp/RWTemp/2026-11/9e20f478899dc29eb19741386f9343c8"
)
PHOTOS = (
    ("afbdee77","02航拍配准"), ("eba24e42","秋季银杏树阵与石坐凳"),
    ("51bfff1d","22/225、180"), ("1a131f12","22/180、225"),
    ("442304af","22/135、090"), ("91cc8ab3","24/180、135"),
    ("2ffba579","24/135、180"), ("2eb40284","24/135、090"),
    ("9df04432","21/180、135"), ("afb6c875","21/180、135"),
    ("365a099f","餐厅侧春季花树与浅色立面"),
)
HOMOGRAPHY = [
    [.018222235758,.277638971862,139.072287765],
    [-.171132524174,.069436616566,367.724714914],
    [-.000000122322,.000163600247,1],
]
WEST, EAST = (429.8,310.9),(508.9,293.3)
PAVILION = (425,232)
NORTH = ((410,216),(426,211),(454,213),(475,219),(487,232),(493,253),
         (498,273),(487,284),(468,290),(447,288),(424,284),(414,272),(412,251))
SOUTH = ((424,319),(443,317),(465,319),(484,319),(502,313),(518,312),
         (527,327),(526,349),(512,362),(487,366),(460,362),(442,354),(429,340))
STRIP = ((309,239),(334,234),(372,235),(404,242),(409,260),(395,274),(367,273),
         (346,269),(322,260),(305,252))
ROAD = ((386,183),(401,194),(427,198),(460,201),(485,206),(500,217),
        (501,237),(500,251),(505,261),(519,275),(528,293),(539,316),(547,341),(566,371))
WALLS = (((451,321),(456,309)),((469,326),(474,309)),((487,324),(489,307)),((505,320),(501,306)))
TRAILS = (
    ((415,209),(422,226),(423,240),(417,255),(423,270),(437,279),(446,286)),
    ((485,228),(470,231),(454,241),(447,255),(456,270),(472,281)),
    ((437,321),(446,338),(461,347),(484,351),(507,349),(525,338)),
    ((462,349),(463,333),(470,320)),((508,350),(510,333),(505,315)),
    ((305,257),(331,267),(365,271),(398,270),(414,264)),
)
ROWS = [(x,y) for x,y in (
    (474,229),(485,230),(476,241),(486,242),(478,251),(487,252),
    (481,261),(490,263),(485,271),(494,273),(490,280),(499,281),
)]
VIEWS = (
    ("01_两座圆坛与花园俯瞰","", "",(606,327),(429,279),0,34,100),
    ("02_日晷与文化墙","07","000",(509,274),(493,309),1.9,19,1.62),
    ("03_文化墙与广场铺装","08","000",(451,294),(482,314),1.65,18,1.63),
    ("04_餐厅入口看木亭","22","135",(446,200),(426,233),2.05,20,1.64),
    ("05_餐厅出口看树阵","24","135",(493,179),(475,232),1.85,18,1.66),
    ("06_思远楼侧看南园","21","180",(537,341),(508,322),1.72,18,1.65),
    ("07_花园内木亭","08","090",(434,248),(424,232),2.0,20,1.64),
    ("08_银杏树阵沿广场","07","180",(483,282),(481,235),1.95,19,1.65),
    ("09_体育馆与篮球场步道","", "",(374,286),(381,239),1.8,20,1.65),
)
CROPS = {
    "广场石板":("08","000",[(340,731),(658,691),(910,940),(256,941)],(720,560),4.1),
    "叠石":("08","000",[(619,452),(644,449),(644,528),(618,537)],(160,400),1.25),
    "铭刻近墙":("08","000",[(696,455),(754,452),(754,507),(696,517)],(320,240),1),
    "铭刻远墙":("08","000",[(298,474),(352,474),(353,492),(298,491)],(440,165),1),
    "铭刻仁":("07","000",[(693,476),(783,480),(783,534),(692,515)],(580,320),1),
    "环坛砖":("07","000",[(369,660),(530,658),(624,753),(275,769)],(520,420),2.7),
    "林下草土":("08","090",[(72,550),(244,552),(247,583),(70,608)],(498,300),2.3),
    "校园道路":("22","135",[(368,660),(619,607),(789,780),(274,872)],(660,476),4.0),
    "旗帜红":("24","135",[(673,373),(693,371),(693,420),(673,422)],(200,430),1),
    "旗帜黄":("24","135",[(703,367),(725,367),(724,419),(702,420)],(200,430),1),
}


def photo_file(index):
    return next(SCREENSHOT_DIR.glob(PHOTOS[index][0]+"*.jpg"))


def make_photo(name,pixels,period=1):
    path = OUT/"实拍贴图"/(name+".png")
    Image.fromarray(pixels).save(path)
    texture = bpy.data.images.load(str(path))
    texture.pack()
    mat = photo_material(name,texture,(.4,.41,.35),.86,period)
    mat.name = "孔德广场实拍 · "+name
    if pixels.shape[2]==4:
        texture_node = next(n for n in mat.node_tree.nodes if n.type=="TEX_IMAGE")
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        mat.node_tree.links.new(texture_node.outputs["Alpha"],bsdf.inputs["Alpha"])
        mat.surface_render_method = "DITHERED"
    return mat


def materials():
    palette = {
        "stone":(.52,.52,.46),"white":(.76,.75,.68),"metal":(.119,.136,.142),
        "black":(.034,.045,.037),"slate":(.11,.123,.127),"ochre":(.70,.408,.102),
        "curb":(.42,.41,.36),"blue":(.044,.135,.325),"green":(.074,.166,.101),
        "wood":(.152,.071,.031),"woodwarm":(.244,.118,.047),"roof":(.113,.098,.087),
        "tile":(.184,.156,.129),"stripe":(.46,.259,.205),"yellow":(.71,.414,.076),
        "glass":(.086,.255,.374),"louver":(.30,.207,.172),"cream":(.59,.55,.46),
    }
    mats = {k:material("孔德广场 · "+k,rgb,.79) for k,rgb in palette.items()}
    for key,(sid,direction,quad,size,period) in CROPS.items():
        with Image.open(reference(sid,direction)) as photo:
            rgb = np.asarray(photo.convert("RGB"))
        src = np.float32(quad)*np.float32((rgb.shape[1]/950,rgb.shape[0]/950))
        w,h = size
        dst = np.float32(((0,0),(w-1,0),(w-1,h-1),(0,h-1)))
        pixels = cv2.warpPerspective(rgb,cv2.getPerspectiveTransform(src,dst),size)
        if period>1:
            f = pixels.astype(np.float32)
            low = cv2.GaussianBlur(f,(0,0),max(10,min(size)/10))
            pixels = np.clip(f+.69*(np.median(low,axis=(0,1))-low),0,255).astype(np.uint8)
        mats[key] = make_photo(key,pixels,period)
    mats["日晷刻盘"] = bpy.data.materials["教学楼与孔德广场实拍 · 日晷刻盘"]
    with Image.open(photo_file(7)) as detail:
        mats["真字题石"] = make_photo("真字题石",np.asarray(detail.convert("RGB"))[1677:1730,791:842])
    for key,sid,direction,crop in (
        ("浅绿叶簇","24","135",(274,262,340,334)),
        ("绿叶簇","22","135",(577,269,659,356)),
        ("紫叶簇","22","180",(321,202,434,309)),
        ("春花枝","22","135",(686,302,784,390)),
    ):
        im = Image.open(reference(sid,direction)).resize((950,950))
        mats[key] = leaf_sample(key,np.asarray(im.crop(crop).convert("RGB")))
    with Image.open(photo_file(1)) as autumn:
        rgb = np.asarray(autumn.convert("RGB"))[1055:1315,510:800]
    mats["秋季金叶"] = leaf_sample("秋季金叶",rgb)
    mats["秋季金叶"].use_fake_user = True
    return mats


def leaf_sample(name,rgb):
    hsv = cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    h,s,v = hsv.transpose(2,0,1)
    if name=="秋季金叶":
        keep = (h<39)&(h>6)&(s>51)&(v>108)
    elif name in ("紫叶簇","春花枝"):
        keep = (s>26)&(v>36)&((h<42)|(h>135)|((h<76)&(v<176)))
    else:
        keep = (h>17)&(h<93)&(s>39)&(v>50)
    yy,xx = np.mgrid[-1:1:complex(rgb.shape[0]),-1:1:complex(rgb.shape[1])]
    alpha = (255*np.clip((.98-xx*xx-yy*yy)/.30,0,1)*keep).astype(np.uint8)
    color = np.clip(255*(rgb/255)**.84,0,255).astype(np.uint8)
    return make_photo(name,np.dstack((color,alpha)))


def clean(scene):
    prefixes = ("孔德广场 · ","孔德广场及主轴 ·","孔德广场方形树池与石坐凳",
                "孔德广场双面旗帜灯杆","志远楼西侧 · 实拍铺地",
                "志远楼西口临路木廊架","低石花池与坐凳 5","低石花池与坐凳 6")
    exact = {"日晷环形红褐砖带","弧形砖缝","文化墙前红色条带","Garden_curb_1","Garden_hedge_1",
             "孔德广场浅色石板","日晷修剪绿篱","紫叶小乔木枝干","多簇叶冠或樱花.013"}
    removed = set()
    for col in list(scene.collection.children):
        if col.name.startswith(prefixes):
            removed.update(col.objects.keys())
            for obj in list(col.objects):
                bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.collections.remove(col)
    for obj in list(scene.objects):
        if obj.name in exact:
            removed.add(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    return sorted(removed)


def trim_old_trees(scene):
    area=unary_union([Polygon(p).buffer(4) for p in (NORTH,SOUTH,STRIP)]).union(
        box(421,288,516,320)).union(LineString(ROAD).buffer(4))
    rotation=math.radians(CAL["rotation_degrees"])
    sin,cos=math.sin(rotation),math.cos(rotation)
    scale=CAL["metres_per_pixel"]
    edited={}
    for name in ("校园绿化 · 树、花池、草地","孔德广场及桥前增补的绿篱、树阵与树池"):
        group=scene.collection.children.get(name)
        for obj in group.objects if group else ():
            mesh=bmesh.new()
            mesh.from_mesh(obj.data)
            vertices=list(mesh.verts)
            positions=np.array([obj.matrix_world@v.co for v in vertices])
            if positions.size:
                x,y,_=positions.T
                mask=contains_xy(area,821+(x*cos+y*sin)/scale,521+(x*sin-y*cos)/scale)
                selected=[v for v,include in zip(vertices,mask) if include]
                if selected:
                    bmesh.ops.delete(mesh,geom=selected,context="VERTS")
                    mesh.to_mesh(obj.data)
                    edited[obj.name]=len(selected)
            mesh.free()
    return edited


def closed(shape):
    return shape.buffer(2.0,join_style="round").buffer(-2.0,join_style="round")


def raised(g,label,key,shape,bottom,top):
    for part in (shape.geoms if hasattr(shape,"geoms") else (shape,)):
        if part.geom_type=="Polygon" and part.area>1e-5:
            g.raised(label,key,part,bottom,top)


def terrain(scene,mats):
    g=Ground(scene)
    g.materials.update(mats)
    g.region("孔德广场 · 重描地坪与两侧花园")
    avenue=LineString(ROAD)
    road=avenue.buffer(6.65,cap_style="flat",join_style="round")
    borders=avenue.buffer(11.7,cap_style="flat",join_style="round").difference(road)
    buildings=unary_union([Polygon(b["outline"]) for b in PLAN["buildings"]])
    beds=[closed(Polygon(o)).difference(avenue.buffer(10.0)) for o in (NORTH,SOUTH,STRIP)]
    plaza=closed(Polygon(((304,275),(382,273),(409,270),(402,218),(415,206),(460,211),
        (490,224),(514,267),(530,294),(541,323),(536,347),(529,367),(472,377),
        (390,373),(375,338),(367,319),(317,316)))).union(borders)
    walks=unary_union([LineString(p).buffer(2.05,cap_style="round",join_style="round") for p in TRAILS])
    gazebo_pad=Point(PAVILION).buffer(8.3,quad_segs=32)
    terrace=closed(Polygon(((470,221),(487,224),(495,239),(492,251),(502,266),
                            (510,287),(481,288),(470,263),(469,246)))).difference(road)
    beds=[b.difference(walks.union(gazebo_pad).union(terrace)) for b in beds]
    circles=[Point(c).buffer(r,quad_segs=56) for c,r in ((WEST,13.25),(EAST,11.55))]
    square=plaza.difference(unary_union([road,buildings,walks,terrace,gazebo_pad,*beds,*circles]))
    g.surface("浅暖色广场石板","广场石板",square,.146)
    g.surface("花园间通道红灰联锁砖","brick",walks.difference(road.union(buildings).union(terrace)),.147)
    g.surface("银杏树阵和石凳台地","广场石板",terrace,.15)
    g.surface("木亭前环形砖铺","brick",gazebo_pad,.15)
    g.surface("混凝土环路接餐厅与教学楼","校园道路",road.difference(buildings),.119)
    for side in (-1,1):
        offset=avenue.offset_curve(6.66*side)
        raised(g,"环路分段石道牙","curb",offset.buffer(.26,cap_style="flat").difference(buildings),.113,.151)
        inner=avenue.offset_curve(6.02*side)
        g.surface("路边黄色细标线","yellow",inner.buffer(.086,cap_style="flat"),.121)
        for t in np.arange(4,offset.length,1.35):
            pt=offset.interpolate(t)
            near=offset.interpolate(t+.01)
            dx,dy=near.x-pt.x,near.y-pt.y
            magnitude=math.hypot(dx,dy)
            if magnitude>1e-8:
                px,py=-dy*.25/magnitude,dx*.25/magnitude
                g.line("石质道牙矩形拼缝","slate",(pt.x+px,pt.y+py),(pt.x-px,pt.y-py),.013,.153)
    for a,b in zip(ROAD,ROAD[1:]):
        g.dash("中线白色虚线","white",a,b,.09,4.2,5.6,.122)
    g.cover("广场环路井盖",(519,273),.123,.38)
    for index,bed in enumerate(beds,1):
        g.surface(f"花园{index}林下实拍草土","林下草土",bed,.151)
        edge=bed.difference(bed.buffer(-.36))
        raised(g,"低石侧缘","curb",edge,.143,.194)
    for a,b in (((412,288),(515,304)),((409,292),(514,308)),((411,298),(510,313))):
        strip=LineString((a,b)).buffer(.38,cap_style="flat")
        g.surface("广场红色嵌砖带","stripe",strip.intersection(square),.149)
    for center,outer,radius in ((WEST,13.25,7.35),(EAST,11.55,6.50)):
        disk=Point(center)
        g.surface("圆坛外环实拍砖","环坛砖",disk.buffer(outer,quad_segs=64).difference(
            disk.buffer(radius,quad_segs=64)),.148)
        curb=disk.buffer(radius,quad_segs=64).difference(disk.buffer(radius-.56,quad_segs=64))
        raised(g,"圆坛叠石立边","叠石",curb,.15,.41)
        g.surface("环坛花土","林下草土",disk.buffer(radius-.56,quad_segs=64),.382)
    for x,y in ROWS:
        g.surface("树阵绿色铸造格栅","green",box(x-1.6,y-1.6,x+1.6,y+1.6),.153)
    g.build()
    return beds


def masonry(scene,site):
    for i,(a,b) in enumerate(WALLS):
        item,length = segment(site,f"孔德广场文化墙第{i+1}段",a,b)
        height=(1.88,1.72,1.56,1.69)[i]
        for x in (-length/2+.25,length/2-.25):
            item.box("叠石短墙端柱","叠石",x,0,height/2+.15,.51,.59,height)
        item.box("石砌展墙","叠石",0,0,height*.46+.15,length-.59,.43,height*.92)
        item.box("薄石压顶","stone",0,0,height+.137,length+.05,.62,.10)
        for side in (-1,1):
            item.box("刻板凹口暗框","slate",0,side*.228,height*.55+.13,length*.62,.042,.70)
            keys=("铭刻近墙","铭刻仁","铭刻远墙","铭刻近墙")
            obj=panel(item,"实拍文化墙铭刻",keys[i],0,side*.254,height*.55+.13,length*.60,.62)
            if side>0:
                for uv in obj.data.uv_layers.active.data:
                    uv.uv.x=1-uv.uv.x
        item.finish()
    # Reuse the photographed dial face and existing editable stone-and-gnomon construction.
    prior_square.sundial(site)
    collection=next(c for c in scene.collection.children if c.name.startswith("孔德广场 · 倾斜刻纹日晷"))
    shift=world(EAST)-world(prior_square.DIAL)
    for obj in collection.objects:
        obj.location+=shift
    for i,(x,y) in enumerate(ROWS):
        item=site.zone(f"银杏下叠石坐凳 {i+1}",(x-2.8,y+1.8))
        w=2.42+(.70 if i%3==0 else 0)
        item.box("石座砌砖基身","叠石",0,0,.36,w,.48,.40)
        item.box("坐凳浅灰压面","stone",0,0,.587,w+.085,.54,.095)
        item.finish()
    item=site.zone("餐厅对面真字题石",(453,213))
    stone=bmesh.new()
    bmesh.ops.create_icosphere(stone,subdivisions=3,radius=1.0)
    for v in stone.verts:
        x,y,z=v.co
        v.co=item.point(x*.72+.07*z,y*.34,max(.15,.495+.46*z+.037*math.sin(7*x+4*y)))
    mesh=bpy.data.meshes.new("天然不规则题石")
    stone.to_mesh(mesh)
    stone.free()
    mesh.materials.append(item.materials["cream"])
    obj=bpy.data.objects.new("孔德广场 · 天然题石",mesh)
    item.collection.objects.link(obj)
    sign_face=panel(item,"实拍真字石面","真字题石",0,.355,.53,.48,.45)
    for uv in sign_face.data.uv_layers.active.data:
        uv.uv.x=1-uv.uv.x
    item.finish()
    sign=site.zone("花园路口斜面读牌",(475,221))
    sign.box("读牌石方脚","stone",0,0,.57,.46,.44,.83)
    verts=[sign.point(x,y,z) for x,y,z in ((-.51,-.24,1.38),(.51,-.24,1.38),(.51,.23,1.08),(-.51,.23,1.08))]
    sign.link("斜面浅石读牌",verts,[(0,1,2,3)],sign.materials["cream"])
    sign.finish()


def pavilion(site):
    item=site.zone("孔德广场北园木亭 · 翘檐灰瓦",PAVILION)
    for z,w,h,key in ((.22,4.48,.14,"叠石"),(.332,4.30,.104,"stone"),
                      (.20,4.79,.081,"stone")):
        item.box("亭台石踏基",key,0,0,z,w,w,h)
    for x in (-1.75,1.75):
        for y in (-1.75,1.75):
            item.box("红褐木柱","woodwarm",x,y,1.81,.20,.20,2.86)
            item.box("木柱覆盆石礎","stone",x,y,.446,.31,.31,.23)
        item.box("两侧榫接檐梁","wood",x,0,3.17,.205,3.67,.225)
        item.box("木亭坐凳","woodwarm",x,0,.787,.43,3.34,.125)
    for y in (-1.75,1.75):
        item.box("正背横梁","wood",0,y,3.16,3.70,.215,.223)
    for y in (-1.73,1.73):
        for x in (-1.15,1.15):
            rod(item,"雀替斜撑","woodwarm",(x,y,3.04),(math.copysign(1.72,x),y,2.62),.051)
    edges = ((-1,-1),(1,-1),(1,1),(-1,1))
    def roof_point(p,q,u,v):
        e=(1-v)*2.23
        x=((1-u)*p[0]+u*q[0])*e
        y=((1-u)*p[1]+u*q[1])*e
        h=3.29+1.51*v**1.64+.27*(abs(2*u-1)**5)*(1-v)**2
        return (x,y,h)
    for p,q in zip(edges,edges[1:]+edges[:1]):
        steps=19
        verts=[item.point(*roof_point(p,q,u,v)) for v in np.linspace(0,.985,13)
               for u in np.linspace(0,1,steps)]
        faces=[(a,a+1,a+1+steps,a+steps) for i in range(12) for j in range(steps-1)
               for a in (i*steps+j,)]
        item.link("曲面瓦屋面",verts,faces,item.materials["roof"])
        for u in np.linspace(.025,.975,28):
            path=[roof_point(p,q,u,v) for v in np.linspace(0,.94,12)]
            for a,b in zip(path,path[1:]):
                rod(item,"连续灰瓦垄","tile",a,b,.035,5)
        hip=[roof_point(p,q,0,v) for v in np.linspace(0,1,16)]
        for a,b in zip(hip,hip[1:]):
            rod(item,"四角翘檐瓦脊","roof",a,b,.085)
        for u in np.linspace(.025,.975,26):
            x,y,z=roof_point(p,q,u,0)
            item.box("可见木椽头","woodwarm",x,y,z-.11,.087,.083,.12)
    rod(item,"木亭顶宝顶","tile",(0,0,4.69),(0,0,5.15),.098,10)
    item.finish()


def tree_shape(plant,pixel,height,spread,key,cards,rng,white=True):
    ground=world(pixel)
    ground.z=.17
    branch=ground+Vector((rng.uniform(-.13,.13),rng.uniform(-.13,.13),height*.46))
    trunk_key="lightbark" if white else "bark"
    plant.limb("自然分叉树干",trunk_key,ground,branch,height*.022,height*.010)
    upper=branch+Vector((rng.uniform(-.33,.33),rng.uniform(-.25,.25),height*.31))
    plant.limb("冠内延伸主枝",trunk_key,branch,upper,height*.010,height*.004)
    if white:
        plant.limb("刷白树干段","white",ground,ground+Vector((0,0,.74)),height*.0225,height*.020)
    for i in range(12):
        a=i*2.39996+rng.uniform(-.19,.20)
        f=rng.uniform(.27,.97)
        reach=spread*(1-f*.51)
        base=branch.lerp(upper,f*.8)
        end=base+Vector((math.cos(a)*reach,math.sin(a)*reach,height*rng.uniform(.08,.21)))
        plant.limb("冠内斜枝",trunk_key,base,end,height*.0052,height*.0012)
        for j in range(15):
            theta=rng.random()*math.tau
            radius=rng.uniform(.05,spread*.48)
            pos=end+Vector((radius*math.cos(theta),radius*math.sin(theta),rng.uniform(-.46,.58)))
            cards[key].append((pos,rng.uniform(.31,.54)*min(1.45,max(.58,height/5.7)),theta))


def ginkgo_leaves(group,positions):
    rng=random.Random(25138)
    vertices,faces=[],[]
    for point,radius,angle in positions:
        for _ in range(22):
            theta=rng.random()*math.tau
            phi=rng.random()*math.tau
            center=point+Vector((
                rng.uniform(-radius,radius),rng.uniform(-radius,radius),rng.uniform(-radius,radius)))
            size=rng.uniform(.046,.105)
            axis=Vector((math.cos(theta),math.sin(theta),.15*math.sin(phi)))*size
            cross=Vector((-math.sin(theta)*math.cos(phi),math.cos(theta)*math.cos(phi),math.sin(phi)))*size
            index=len(vertices)
            vertices.extend(center+a*axis+b*cross for a,b in (
                (0,0),(.58,-.75),(.98,-.62),(1.06,-.20),(1.06,.22),(.97,.57),(.55,.74)))
            faces.append(tuple(range(index,index+7)))
    mesh=bpy.data.meshes.new("银杏扇形小叶")
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    colors=(
        ((.146,.290,.035),(.245,.431,.064),(.085,.201,.025)),
        ((.57,.288,.032),(.75,.428,.065),(.44,.194,.020)),
    )
    seasons=[[material(f"银杏{'绿叶' if i==0 else '金叶'} {j+1}",c,.85)
              for j,c in enumerate(palette)] for i,palette in enumerate(colors)]
    for mat in seasons[1]:
        mat.use_fake_user=True
    for mat in seasons[0]:
        mesh.materials.append(mat)
    for p in mesh.polygons:
        p.material_index=rng.randrange(3)
    obj=bpy.data.objects.new("孔德广场 · 银杏扇形叶组",mesh)
    group.objects.link(obj)
    return obj,seasons[1]


def landscaping(scene,site,mats,beds):
    plant=Planting(scene)
    plant.group.name="孔德广场及两园 · 乔木与低绿篱"
    plant.palette["white"]=mats["white"]
    rng=random.Random(14667)
    cards={key:[] for key in ("浅绿叶簇","绿叶簇","紫叶簇","春花枝","树阵银杏")}
    for i,p in enumerate(ROWS):
        tree_shape(plant,p,6.7+i%5*.48,1.24,"树阵银杏",cards,rng)
    trees=(
        ((418,222),5.6,1.6,"春花枝"),((429,217),6.1,1.8,"绿叶簇"),((442,218),6.6,2.1,"紫叶簇"),
        ((456,219),5.9,2.2,"紫叶簇"),((467,225),4.6,1.7,"绿叶簇"),((474,234),5.4,1.9,"紫叶簇"),
        ((415,239),5.4,1.6,"春花枝"),((435,242),6.9,2.1,"绿叶簇"),((449,244),5.2,1.7,"春花枝"),
        ((462,246),6.4,2.3,"紫叶簇"),((470,258),5.5,2.0,"绿叶簇"),((448,271),6.8,2.5,"紫叶簇"),
        ((437,261),6.8,2.1,"绿叶簇"),((425,276),5.9,2.1,"绿叶簇"),((469,279),5.5,1.8,"浅绿叶簇"),
        ((484,278),3.7,1.2,"绿叶簇"),((430,326),6.9,2.40,"绿叶簇"),((442,332),7.8,2.68,"绿叶簇"),
        ((448,338),6.5,2.17,"紫叶簇"),((456,355),5.3,1.49,"绿叶簇"),((468,342),6.3,1.94,"浅绿叶簇"),
        ((482,343),6.8,2.1,"绿叶簇"),((497,340),5.9,2.2,"紫叶簇"),((514,336),5.8,2.0,"绿叶簇"),
        ((521,347),5.3,1.7,"绿叶簇"),((508,359),5.6,2.1,"紫叶簇"),((486,360),5.1,1.4,"绿叶簇"),
        ((512,318),4.7,1.9,"紫叶簇"),((530,353),6.2,2.0,"绿叶簇"),
        ((440,202),5.0,1.4,"春花枝"),((455,204),5.9,1.6,"春花枝"),((474,205),4.8,1.6,"春花枝"),
    )
    for p,h,r,key in trees:
        tree_shape(plant,p,h,r,key,cards,rng)
    for i,x in enumerate((312,328,342,355,368,382,396)):
        for y in (241,262):
            tree_shape(plant,(x,y+(i%3-1)*2),6.1+i%3*.54,1.80,"绿叶簇",cards,rng)
    for c,r in ((WEST,6.4),(EAST,5.6)):
        for a in np.linspace(0,math.tau,62,endpoint=False):
            x,y=c[0]+r*math.cos(a),c[1]+r*math.sin(a)
            plant.crown("圆形花坛密剪绿篱","deep",world((x,y))+Vector((0,0,.54)),.35,.37,.37)
    for radius in (1.85,3.07,4.19):
        for a in np.linspace(0,math.tau,24,endpoint=False):
            x,y=WEST[0]+radius*math.cos(a),WEST[1]+radius*math.sin(a)
            plant.crown("西坛内层黄绿色剪球","olive",world((x,y))+Vector((0,0,.52)),.29,.33,.31)
    plant.hedge(((321,378),(377,377),(439,374),(501,374),(544,374)),.82)
    for x,y in ((444,227),(436,251),(451,258),(481,249),(426,265),(437,280),(481,284),
                (438,329),(467,347),(485,327),(499,322),(514,358),(520,338)):
        p=world((x,y))
        for i in range(18):
            a=rng.random()*math.tau
            r=rng.uniform(.03,.69)
            cards["绿叶簇"].append((p+Vector((r*math.cos(a),r*math.sin(a),rng.uniform(.4,1.24))),.47,a))
    for pt in ((419,218),(445,216),(467,223),(476,225),(432,211)):
        item=site.zone("路旁幼树斜撑与小牌",pt)
        for a in (0,2.1,4.2):
            rod(item,"三角撑杆","woodwarm",(.67*math.cos(a),.67*math.sin(a),.18),(0,0,1.39),.023)
        item.box("树种小铭牌","cream",.26,0,.87,.24,.034,.125)
        item.finish()
    for bed in beds:
        if bed.is_empty:
            continue
        x0,y0,x1,y1=bed.bounds
        for _ in range(round(bed.area/9)):
            x,y=rng.uniform(x0,x1),rng.uniform(y0,y1)
            if bed.contains(Point(x,y)):
                c=world((x,y))+Vector((0,0,.22))
                cards["绿叶簇"].append((c,rng.uniform(.08,.24),rng.random()*math.tau))
    ginkgo=ginkgo_leaves(plant.group,cards.pop("树阵银杏"))
    for key,points in cards.items():
        foliage_cards(plant.group,mats[key],points,"孔德广场 · "+key)
    plant.finish()
    return ginkgo


def street_details(site):
    for point in ((406,193),(460,200),(493,219),(492,259),(514,280),(531,319),(541,347)):
        item=site.zone("广场道路蓝白旗帜灯杆",point)
        rod(item,"白色灯杆","white",(0,0,.15),(0,0,5.02),.057,10)
        rod(item,"蓝色漆脚","blue",(0,0,.15),(0,0,1.01),.063,10)
        rod(item,"路灯弧形挑臂","metal",(0,0,4.81),(-.79,0,5.04),.037)
        rod(item,"灯臂三角撑","metal",(0,0,4.56),(-.56,0,4.99),.018)
        item.box("深蓝色灯罩","blue",-.92,0,5.04,.41,.20,.079)
        for x,key in ((-.29,"旗帜红"),(.29,"旗帜黄")):
            item.box("旗面底板","stripe",x,0,3.26,.50,.034,1.23)
            panel(item,"实拍旗帜",key,x,-.021,3.26,.49,1.22)
        item.finish()
    for pt in ((435,278),(447,264),(467,236),(500,344),(453,343),(473,353),(406,255)):
        item=site.zone("园路低位筒灯",pt)
        rod(item,"绿黑灯柱","black",(0,0,.17),(0,0,.84),.056)
        rod(item,"浅暖透光圈","cream",(0,0,.84),(0,0,.98),.064)
        rod(item,"顶盖","black",(0,0,.98),(0,0,1.01),.071)
        item.finish()


def neighboring_roads(scene,site,mats):
    # Photo 11 places the spring flowering trees opposite the canteen doors.
    for i,x in enumerate((428,451,474,496,518,540)):
        y=171+(i%2)*1.6
        item=site.zone("餐厅前浅石矩形花池",(x,y))
        item.box("餐厅前花池浅色石脚","cream",0,0,.249,3.78,1.29,.29)
        item.box("矩形修剪绿篱","green",0,0,.481,3.65,1.18,.32)
        item.finish()
    # The two white-framed sports-hall wings are the backdrop of the garden.
    for label,a,b,height in (("体育馆东面",(367,318),(368,467),13.1),
                             ("体育区北面",(372,389),(568,391),14.2)):
        item,length=segment(site,label+" · 白色檐带和蓝窗",a,b)
        top=height-.24
        item.box("突出浅灰金属框檐","white",0,.19,top,length+.24,.56,.84)
        item.box("窗带深灰内层","slate",0,.08,height-2.79,length,.32,4.04)
        n=round(length/3.0)
        for i in range(n):
            x=length*((i+.5)/n-.5)
            item.box("连续蓝玻璃幕墙","glass",x,.29,height-2.75,length/n-.23,.093,3.70)
            item.box("银灰幕墙柱","white",x-length/(2*n),.34,height-2.74,.23,.44,3.87)
            for dx in (-.55,.55):
                item.box("玻璃竖分格","metal",x+dx,.345,height-2.75,.052,.055,3.62)
            item.box("楼层幕墙横梃","metal",x,.357,height-2.56,length/n-.20,.062,.068)
        item.box("玻璃底部整面浅灰边","white",0,.24,height-4.91,length,.44,.41)
        for z in np.arange(height-7.14,height-5.19,.235):
            item.box("园侧水平棕色遮阳百叶","louver",0,.48,z,length,.16,.092)
        item.finish()
    screen=site.zone("体育区屋顶棕色设备百叶",(458,407))
    screen.box("设备隔屏背面","slate",0,0,16.34,24.0,6.41,3.76)
    for z in np.arange(14.74,18.54,.25):
        for sign in (-1,1):
            screen.box("长边连续横百叶","louver",0,sign*3.31,z,24.35,.25,.088)
            screen.box("短边连续横百叶","louver",sign*12.08,0,z,.25,6.76,.088)
    screen.finish()
    g=Ground(scene)
    g.materials.update(mats)
    g.region("体育馆与篮球场之间的人行接头")
    corridor=LineString(((306,284),(339,286),(365,288),(391,282),(414,272)))
    g.surface("体育馆侧贯通灰地面","广场石板",corridor.buffer(5.4),.143)
    g.surface("和球场围网并行的浅铺地","广场石板",LineString(((394,181),(395,213),(395,239),
        (400,261),(414,269))).buffer(2.7),.144)
    g.build()


def renders(scene,views,ginkgo,mats):
    scene.render.engine="CYCLES"
    scene.cycles.samples=12
    scene.cycles.use_denoising=True
    scene.render.resolution_percentage=100
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
    for tag,sid,angle,*_ in VIEWS:
        scene.camera=views[tag]
        scene.render.resolution_x,scene.render.resolution_y=(1330,1020) if tag[:2]=="01" else (780,780)
        output=OUT/"模型视角"/(tag+".png")
        scene.render.filepath=str(output)
        bpy.ops.render.render(write_still=True)
        if not sid:
            continue
        canvas=Image.new("RGB",(1582,850),"#edeae0")
        draw=ImageDraw.Draw(canvas)
        draw.text((8,9),tag[3:],fill="#202520",font=font)
        draw.text((8,39),f"原全景 {sid}/{angle}°",fill="#202520",font=font)
        draw.text((795,39),"模型视角（站位估算）",fill="#202520",font=font)
        for x,path in ((8,reference(sid,angle)),(794,output)):
            with Image.open(path) as im:
                canvas.paste(ImageOps.fit(im.convert("RGB"),(780,780)),(x,65))
        canvas.save(OUT/"实景对照"/(tag+".jpg"),quality=93)
    autumn_preview(scene,ginkgo,mats)


def autumn_preview(scene,ginkgo,mats):
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
    tree,autumn_mats=ginkgo
    for index,mat in enumerate(autumn_mats):
        tree.data.materials[index]=mat
    site=SiteDetails(scene,mats)
    leaves=site.zone("用于秋景对照的散落银杏叶",(490,254))
    rng=random.Random(5782)
    vertices=[]
    for x,y in ROWS:
        for i in range(230):
            r=rng.random()**.54*2.65
            a=rng.random()*math.tau
            b=rng.random()*math.tau
            pos=world((x,y))+Vector((r*math.cos(a),r*math.sin(a),.157+.002*(i%3)))
            vertices.extend(pos+Vector((.035*math.cos(b+d),.035*math.sin(b+d),0))
                            for d in (0,2.09,4.18))
    gold=material("散落黄银杏叶",(.65,.365,.057),.97)
    leaves.link("银杏树阵落叶",vertices,[(i,i+1,i+2) for i in range(0,len(vertices),3)],gold)
    scene.camera=camera(scene,"秋季 · 树阵回看日晷",(487.8,255.5),(494,286),2.25,18,1.65)
    scene.render.resolution_x=scene.render.resolution_y=780
    scene.render.filepath=str(OUT/"模型视角/10_银杏树阵秋景.png")
    bpy.ops.render.render(write_still=True)
    canvas=Image.new("RGB",(1582,850),"#edeae0")
    draw=ImageDraw.Draw(canvas)
    draw.text((8,20),"附件2 · 银杏秋色与树阵",fill="#202520",font=font)
    draw.text((794,20),"模型秋色对照",fill="#202520",font=font)
    with Image.open(photo_file(1)) as src, Image.open(scene.render.filepath) as result:
        crop=src.crop((0,src.height*.325,src.width,src.height*.664))
        canvas.paste(ImageOps.fit(crop,(780,780)),(8,65))
        canvas.paste(result,(794,65))
    canvas.save(OUT/"实景对照/10_银杏树阵秋景.jpg",quality=93)


def main():
    for name in ("实拍贴图","模型视角","实景对照"):
        (OUT/name).mkdir(parents=True,exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    before=set(scene.objects.keys())
    removed=clean(scene)
    trimmed=trim_old_trees(scene)
    mats=materials()
    site=SiteDetails(scene,mats)
    beds=terrain(scene,mats)
    masonry(scene,site)
    pavilion(site)
    ginkgo=landscaping(scene,site,mats,beds)
    street_details(site)
    neighboring_roads(scene,site,mats)
    new=[o for o in scene.objects if o.type=="MESH" and o.name not in before.difference(removed)]
    unwrap_textured_boxes(new)
    clean_generated_meshes(new)
    for o in new:
        assert all(math.isfinite(value) for v in o.data.vertices for value in v.co),o.name
        assert all(p.area>=1e-9 for p in o.data.polygons),o.name
    views={tag:camera(scene,tag,eye,target,aim,lens,height) for tag,_,_,eye,target,aim,lens,height in VIEWS}
    scene.camera=views["01_两座圆坛与花园俯瞰"]
    scene.render.resolution_x,scene.render.resolution_y=1330,1020
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB",
                             export_cameras=False,export_lights=False)
    record={"源母版":str(SOURCE),"附件对照":PHOTOS,"航拍配准内点数":68,"附件1到总图单应矩阵":HOMOGRAPHY,
            "西坛":WEST,"日晷东坛":EAST,"南园":SOUTH,"北园":NORTH,"体育侧树带":STRIP,"文化墙":WALLS,
            "亭位":PAVILION,"道路及园路":(ROAD,TRAILS),"对照相机":VIEWS,"贴图控制点":CROPS,
            "更换旧对象":removed,"局部清理旧绿化顶点":trimmed,"新增网格":len(new),
            "精度":"圆坛与文化墙位置经航拍配准调整；木亭具体落位、树种与尺寸、遮挡园路和相机站位按照片估算。"}
    (OUT/"定位与验收.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    renders(scene,views,ginkgo,mats)


if __name__=="__main__":
    main()
