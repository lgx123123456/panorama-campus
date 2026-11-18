"""Refine the two west teaching wings and the square across their service road."""

import json
import math
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, Point, Polygon, box

from 三处庭院实拍细化 import (
    OUT as COURT_OUT, STEM as COURT_STEM, foliage_cards, panel, tree, unwrap_textured_boxes,
)
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 四栋教学楼实景细化 import Building, reference
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 地面街道实景细化 import Ground
from 尚德广场实拍细化 import photo_material
from 楼间过道实拍细化 import camera, clean_generated_meshes, orient


OUT = COURT_OUT.parent / "思远志远连廊与孔德广场"
SOURCE = COURT_OUT / (COURT_STEM + ".blend")
STEM = "校园室外_思远志远连廊与孔德广场"
SCALE = CAL["metres_per_pixel"]
BRIDGE = ((701, 256), (710, 278), (733, 320), (737, 327))
ROAD = ((495, 215), (488, 247), (487, 271), (493, 292), (500, 309), (529, 325), (549, 353))
PERGOLA = ((499, 253), (495, 270), (500, 287))
DIAL = (429, 310)
VIEWS = (
    ("01_图书馆前树阵与连廊", "32", "090", (811, 260), (715, 288), 2.50, 18),
    ("02_主轴斜看思远楼塔楼", "40", "045", (825, 413), (740, 324), 5.70, 19),
    ("03_志远楼旁木廊架", "15", "270", (501, 242), (491, 307), 1.64, 18),
    ("04_临路日晷和文化墙", "15", "225", (501, 242), (454, 299), 1.64, 18),
    ("05_道路与石坐凳", "15", "180", (501, 242), (443, 212), 1.64, 18),
    ("06_思远楼志远楼连廊近景", "32", "135", (763, 303), (714, 292), 5.40, 22),
    ("07_日晷刻盘与文化墙", "07", "000", (440, 291), (437, 309), 1.15, 18),
)

# Quad coordinates refer to the direction images scaled to 950 by 950.
CROPS = {
    "玻璃塔楼": ("40", "045", [(412,312),(451,298),(451,385),(412,410)], (300,600), 1),
    "桥窗": ("40", "045", [(369,400),(408,411),(408,433),(369,422)], (420,200), 4.4),
    "石板": ("40", "045", [(422,660),(615,663),(770,840),(409,854)], (520,520), 3.9),
    "叠砌石": ("07", "000", [(800,483),(853,478),(852,558),(800,545)], (300,360), 1.3),
    "文化墙仁": ("07", "000", [(691,475),(785,481),(785,534),(692,515)], (580,310), 1),
    "文化墙侧板": ("07", "000", [(886,498),(930,496),(930,529),(886,525)], (400,250), 1),
    "日晷刻盘": ("07", "000", [(162,435),(215,400),(289,487),(226,528)], (520,520), 1),
    "红砖": ("07", "000", [(332,676),(510,674),(591,784),(240,803)], (500,420), 2.6),
    "混凝土": ("15", "225", [(346,640),(511,652),(560,775),(290,747)], (490,470), 3.2),
}


def materials():
    palette = {
        "ochre": ((.68,.369,.077),.75), "gold": ((.76,.453,.101),.77),
        "slate": ((.101,.128,.147),.76), "joint": ((.056,.066,.072),.9),
        "black": ((.022,.031,.035),.87), "metal": ((.113,.150,.166),.46),
        "silver": ((.53,.55,.53),.37), "glass": ((.085,.185,.222),.28),
        "inside": ((.24,.234,.198),.78), "stone": ((.47,.455,.395),.86),
        "white": ((.73,.71,.64),.85), "red": ((.57,.039,.022),.78),
        "blue": ((.052,.156,.28),.71), "green": ((.051,.181,.115),.89),
        "wood": ((.205,.088,.050),.92), "soil": ((.155,.113,.073),.97),
        "yellow": ((.73,.435,.074),.88),
    }
    result = {key: material("教学楼与孔德广场 · " + key, rgb, roughness)
              for key, (rgb,roughness) in palette.items()}
    for key,(sid,angle,quad,size,period) in CROPS.items():
        with Image.open(reference(sid,angle)) as photo:
            rgb = np.asarray(photo.convert("RGB"))
        controls = np.float32(quad) * np.float32((rgb.shape[1]/950,rgb.shape[0]/950))
        w,h = size
        target = np.float32(((0,0),(w-1,0),(w-1,h-1),(0,h-1)))
        pixels = cv2.warpPerspective(rgb,cv2.getPerspectiveTransform(controls,target),size)
        if key in {"石板","混凝土","红砖","叠砌石"}:
            low = cv2.GaussianBlur(pixels.astype(np.float32),(0,0),max(11,min(size)/9))
            pixels = np.clip(pixels + .64*(np.median(low,axis=(0,1))-low),0,255).astype(np.uint8)
        if key == "日晷刻盘":
            mask = np.zeros((h,w),dtype=np.uint8)
            cv2.line(mask,(65,299),(282,288),255,6)
            pixels = cv2.inpaint(pixels,mask,3,cv2.INPAINT_TELEA)
        path = OUT/"实拍贴图"/(key+".png")
        Image.fromarray(pixels).save(path)
        texture = bpy.data.images.load(str(path))
        texture.pack()
        reflect = key in {"玻璃塔楼","桥窗"}
        result[key] = photo_material(key,texture,(.30,.32,.33),.38 if reflect else .88,period)
        result[key].name = "教学楼与孔德广场实拍 · " + key
        result[key]["来源"] = f"{sid}/{angle}，950像素基准四点 {quad}"
    return result


def remove_obsolete(scene):
    removed = []
    for collection in list(scene.collection.children):
        if collection.name.startswith(("A03 思远楼—志远楼低层连接","孔德广场 · 文化墙实景饰面")):
            for obj in list(collection.objects):
                removed.append(obj.name)
                bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.collections.remove(collection)
    prefixes = ("P07_sundial_", "B15 后墙占位", "B21 后墙占位")
    for obj in list(scene.objects):
        if obj.name.startswith(prefixes) or obj.name in {"Garden_curb_0","Garden_hedge_0"}:
            removed.append(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    return removed


def tower(site,sid,center):
    item = site.zone(f"B{sid} 东端楼梯塔楼与高侧窗",center)
    item.sid = sid
    b = item.box
    width, depth, top = 11.6, 14.4, 20.1
    b("塔楼通高暗灰内衬","slate",0,0,top/2,width-.58,depth-.56,top)
    b("黄墙屋顶框带","ochre",0,0,top-.33,width+.25,depth+.24,.68)
    b("屋顶女儿墙压顶","gold",0,0,top+.045,width+.34,depth+.34,.09)
    for sign in (-1,1):
        face = sign*(depth/2)
        b("通高玻璃窗边黄柱","ochre",-5.25,face,top/2,.74,.38,top)
        b("通高玻璃窗边黄柱","ochre",5.33,face,top/2,.94,.38,top)
        for x,w in ((-2.79,4.18),(2.72,4.37)):
            b("窗格深置衬框","black",x,face,10.55,w+.14,.21,17.1)
            for floor in range(5):
                z = 3.54+floor*3.40
                panel(item,"楼梯塔实拍窗格","玻璃塔楼",x,face+sign*.123,z,w,3.17)
                b("楼层横梁","slate",x,face+sign*.159,z-1.65,w+.08,.095,.23)
                for k in range(1,3):
                    b("楼梯玻璃横梃","metal",x,face+sign*.15,z+(k-1.5)*1.06,w,.062,.055)
            for k in range(5):
                b("楼梯玻璃竖梃","metal",x+(k-2)*w/4,face+sign*.17,10.33,.065,.073,16.94)
        b("窗间通高深灰柱","slate",0,face+sign*.20,10.31,.89,.43,17.0)
        b("基座深灰压裙","slate",0,face,1.23,width,.46,2.46)
    # The short elevation has paired horizontal slots and deep landing openings.
    z_edges = [0, top]
    for floor in range(4):
        lo = 4.91+floor*3.49
        z_edges.extend((lo,lo+.31,lo+.63,lo+.94))
        b("侧墙退深条窗","black",width/2-.11,.58,lo+.47,.09,5.58,1.02)
        b("侧墙挑台楼板","slate",width/2+.26,-5.58,lo-.36,1.08,2.15,.23)
        b("侧墙挑台背窗","glass",width/2-.18,-5.58,lo+.83,.09,1.71,2.13)
        for i in range(9):
            b("挑台细栏杆","silver",width/2+.76,-6.54+i*.24,lo+.13,.029,.029,.83)
        b("挑台栏杆扶手","silver",width/2+.76,-5.58,lo+.56,.048,2.00,.049)
    ordered = sorted(z_edges)
    apertures = {round(4.91+f*3.49+d,3) for f in range(4) for d in (0,.63)}
    for low,high in zip(ordered,ordered[1:]):
        intervals = ((-4.38,-2.24),(3.39,7.23)) if round(low,3) in apertures else ((-4.38,7.23),)
        for a,c in intervals:
            b("黄墙及条窗侧壁","ochre",width/2,(a+c)/2,(low+high)/2,.39,c-a,high-low)
    b("挑台窄侧黄柱","ochre",width/2,-6.92,top/2,.37,.62,top)
    for z in (3.8,7.24,10.72,14.25,17.72):
        b("东立面分层拼缝","joint",width/2+.202,1.43,z,.018,11.64,.023)
    b("屋顶机房玻璃腰带","glass",1.20,-.34,20.62,6.6,6.23,1.11)
    b("机房顶梁","ochre",1.45,-.43,24.03,7.13,6.98,.46)
    b("机房后墙","ochre",1.45,2.83,22.66,7.13,.37,2.71)
    b("机房暗部内衬","joint",2.12,-.39,22.57,5.11,5.12,2.89)
    b("顶层掏空平台楼板","gold",1.44,-.51,21.20,7.13,6.83,.27)
    b("屋顶掏空框柱","ochre",-1.91,-3.75,22.66,.46,.46,2.79)
    for j in range(5):
        for i in range(6):
            yy = -3.25+i*1.12
            b("机房穿孔黄板","ochre",4.84,yy,21.60+j*.49,.29,.93,.48)
        for i in range(5):
            b("机房穿孔横连板","ochre",4.84,-2.69+i*1.12,21.38+j*.49,.29,.35,.22)
    item.finish()
    item.collection["来源"] = "40/045、40/000、32/090、01/045；楼宽和屋顶轮廓结合02航拍估算"


def west_entries(scene,mats):
    for sid in ("15","21"):
        base = next(b for b in PLAN["buildings"] if b["id"]=="B"+sid)
        item = Building(scene,sid,base["name"]+"西入口门窗",base["outline"],base["height"],mats)
        positions = (-1.84,1.84) if sid=="15" else (.72,)
        floor = .48 if sid=="15" else .64
        for x in positions:
            for sign in (-1,1):
                dx = x+sign*.55
                item.box("门扇玻璃","glass",dx,.04,floor+1.11,1.07,.051,2.22)
                for off in (-.515,.515):
                    item.box("门扇细金属边","silver",dx+off,-.007,floor+1.11,.032,.042,2.22)
                item.box("门扇蓝色安全横条","blue",dx,-.012,floor+1.02,1.04,.022,.068)
                item.box("玻璃门拉手","silver",x+sign*.14,-.043,floor+1.15,.043,.057,.42)
        for z in (4.32,8.04,11.76,15.48):
            item.box("阳台挑板暗缝","joint",0,-.46,z-.09,item.width-.56,.033,.034)
            for side in (-1,1):
                x = side*item.width*.218
                item.box("阳台背景连续上窗","glass",x,.569,z+2.23,item.width*.235,.085,.41)
                for k in (-1,0,1):
                    item.box("退台玻璃竖框","metal",x+k*item.width*.074,.505,z+1.48,.056,.065,2.10)
        item.finish()


def roofs(scene,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("思远楼与志远楼 · 平屋面边缘及女儿墙")
    for building in PLAN["buildings"][:2]:
        outline = Polygon(building["outline"])
        g.surface(building["name"]+"平屋面","stone",outline.buffer(-.68),20.025)
        g.raised(building["name"]+"深色收边和女儿墙",
                 "slate",outline.buffer(-.10).difference(outline.buffer(-.65)),19.96,20.41)
        g.surface(building["name"]+"女儿墙压顶","ochre",
                  outline.buffer(-.088).difference(outline.buffer(-.654)),20.418)
    g.build()


def bridge(site):
    width = 6.15
    g = Ground(site.scene)
    g.materials.update(site.materials)
    g.region("A03 连廊连续楼板与屋面")
    footprint = LineString(BRIDGE).buffer(width/(2*SCALE),cap_style="flat",join_style="mitre")
    for z,h,key,label in (
        (3.81,.70,"ochre","黄色层间边梁"),(4.22,.16,"inside","连廊通行楼板及内踢脚"),
        (7.56,.73,"slate","连续深灰包边檐带"),(7.975,.14,"metal","连续屋面压条"),
    ):
        g.raised(label,key,footprint,z-h/2,z+h/2)
    g.build()
    for index,(a,c) in enumerate(zip(BRIDGE,BRIDGE[1:])):
        center = tuple((i+j)/2 for i,j in zip(a,c))
        item = site.zone(f"A03 思远楼与志远楼封闭连廊 {index+1}",center)
        item.sid = "15–21"
        orient(item,a,c)
        span = (world(c)-world(a)).length
        b = item.box
        count = max(2,round(span/1.31))
        pitch = span/count
        for sign in (-1,1):
            y = sign*(width/2-.13)
            b("钢化玻璃底衬","glass",0,y,5.77,span,.071,2.96)
            for i in range(count):
                x = -span/2+(i+.5)*pitch
                panel(item,"从40站校准的桥窗反射","桥窗",x,y+sign*.041,5.77,pitch-.045,2.89)
                b("玻璃窗竖梃","metal",x-pitch/2,y+sign*.073,5.76,.072,.13,3.02)
                b("檐口挂板竖向分缝","joint",x-pitch/2,sign*(width/2+.003),7.55,.016,.024,.70)
            for z in (4.29,4.77,5.37,5.97,6.57,7.25):
                b("窗带金属横梃","metal",0,y+sign*.071,z,span+.11,.13,.065)
        for x in np.linspace(-span/2+.2,span/2-.2,max(2,round(span/.8))):
            b("桥底横向板缝","joint",x,0,3.452,.022,width-.31,.020)
        if index < 2:
            b("桥下吸顶照明","white",0,0,3.42,.90,.20,.048)
            for side in (-1,1):
                b("桥下方形柱与石脚","slate",span*.28,side*(width/2-.42),1.76,.56,.66,3.49)
                b("桥柱石勒脚","stone",span*.28,side*(width/2-.42),.22,.63,.71,.43)
        if index==1:
            b("通高深灰桥头墙","slate",span*.39,width/2+.20,4.45,3.15,.62,8.86)
            for z in (.47,2.10,3.75,5.40,7.05,8.70):
                b("桥头灰板分缝","joint",span*.39,width/2+.521,z,3.10,.016,.023)
        item.finish()
        item.collection["来源"] = "02桥顶描线，32/090、32/135与40/045校核玻璃、包边、立柱；端标高估算"


def ground(scene,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("志远楼西侧 · 实拍铺地、道牙和标线")
    route = LineString(ROAD)
    road = route.buffer(7.0,cap_style="flat",join_style="round")
    sidewalk = route.buffer(12.7,cap_style="flat",join_style="round").difference(road)
    buildings = Polygon(PLAN["buildings"][0]["outline"]).union(Polygon(PLAN["buildings"][1]["outline"]))
    g.surface("临楼浅色混凝土车道","混凝土",road.difference(buildings),.105)
    g.surface("两侧人行砖和孔德广场交界","红砖",sidewalk.difference(buildings),.154)
    entrance = Polygon(((491,221),(514,224),(512,263),(505,293),(494,287),(492,266)))
    g.surface("志远楼西门连至木廊的红灰砖铺","brick",
              entrance.difference(buildings.union(road).union(sidewalk)),.151)
    pocket = Polygon(((500,252),(510,246),(513,264),(506,284),(501,282),(503,263)))
    g.surface("沿廊种植带表土","soil",pocket.difference(buildings),.168)
    for offset,side in ((-7.01,"西"),(7.01,"东")):
        edge = route.offset_curve(offset)
        g.raised(side+"侧连续石道路缘","石板",edge.buffer(.30,cap_style="flat").difference(buildings),.10,.164)
        inset = route.offset_curve(math.copysign(6.30,offset))
        g.surface(side+"侧黄色标线","yellow",inset.buffer(.10,cap_style="flat").difference(buildings),.108)
    for a,c in zip(ROAD,ROAD[1:]):
        g.dash("车行道白色虚线","white",a,c,.11,3.55,5.40,.109)
    g.cover("车行道铸铁检修盖",(488,261),.111,.31)
    g.region("图书馆前 · 过桥铺地与树阵格栅")
    g.surface("桥前及桥下灰色花岗岩实拍板","石板",Polygon(
        ((726,251),(791,230),(818,234),(822,313),(797,354),(746,356),
         (732,318),(719,313),(705,284),(698,267))
    ).difference(Polygon(PLAN["buildings"][1]["outline"])),.088)
    for x in (756,768,780,792):
        for y in (251,267,283):
            g.surface("树阵方形绿格栅","green",box(x-1.65,y-1.65,x+1.65,y+1.65),.093)
    g.region("孔德广场 · 日晷环砖与树池座椅台地")
    ring = Point(DIAL).buffer(15,quad_segs=24).difference(Point(DIAL).buffer(5.9,quad_segs=24))
    g.surface("日晷环形实拍红砖","红砖",ring,.089)
    g.surface("孔德广场石板铺地","石板",Polygon(
        ((397,244),(475,238),(479,261),(466,286),(461,301),(434,338),(386,320))
    ).difference(ring).difference(road).difference(sidewalk),.088)
    g.build()


def pergola(site):
    for index,(a,c) in enumerate(zip(PERGOLA,PERGOLA[1:])):
        center = tuple((i+j)/2 for i,j in zip(a,c))
        item = site.zone(f"志远楼西口临路木廊架 {index+1}",center)
        orient(item,a,c)
        span = (world(c)-world(a)).length
        b = item.box
        for x in np.linspace(-span/2+.19,span/2-.19,5):
            for y in (-.99,.99):
                b("木廊柱","wood",x,y,1.45,.145,.145,2.63)
                b("灰石柱础","叠砌石",x,y,.218,.29,.30,.15)
                b("钢连接套","metal",x,y,.33,.17,.17,.13)
                for dx in (-.19,.19):
                    b("梁柱斜撑","wood",x+dx,y,2.54,.39,.085,.094)
            b("廊顶承重横梁","wood",x,0,2.75,.126,2.39,.15)
        for y in (-1.03,1.03):
            b("廊顶纵梁","wood",0,y,2.84,span, .14,.18)
        for x in np.linspace(-span/2+.1,span/2-.1,max(4,round(span/.24))):
            b("连续遮阳短椽","wood",x,0,2.94,.070,2.36,.096)
        for x in (-span*.27,span*.25):
            b("廊侧木长凳","wood",x,.75,.61,1.54,.33,.095)
            for dx in (-.61,.61):
                b("长凳黑色支脚","metal",x+dx,.75,.36,.063,.24,.42)
        item.finish()
        item.collection["来源"] = "15/270、15/315；21/090用于比对同型木构"


def sundial(site):
    item = site.zone("孔德广场 · 倾斜刻纹日晷",DIAL)
    item.box("双层浅石方底座","stone",0,0,.73,1.94,1.54,.20)
    item.box("方底座浅色压边","white",0,0,.87,1.83,1.44,.11)
    item.box("晷盘支座","white",0,0,1.13,.50,.61,.48)
    item.finish()
    r = .88
    normal = Vector((.52,.48,.71)).normalized()
    axis = Vector((-normal.y,normal.x,0)).normalized()
    vertical = normal.cross(axis)
    center = item.point(0,0,1.94)
    samples = np.linspace(0,math.tau,80,endpoint=False)
    rim = [r*(axis*math.cos(t)+vertical*math.sin(t)) for t in samples]
    n = len(samples)
    vertices = [center+p+normal*h for h in (-.075,.075) for p in rim]
    wall = [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    item.link("晷盘石质厚边和背面",vertices,wall+[tuple(reversed(range(n)))],item.materials["white"])
    obj = item.link("晷面实拍刻纹",[center+p+normal*.076 for p in rim],
                    [tuple(range(n))],item.materials["日晷刻盘"])
    uv = obj.data.uv_layers.new()
    for loop in obj.data.loops:
        theta = samples[loop.vertex_index]
        uv.data[loop.index].uv = (.552+.393*math.cos(theta),.490+.394*math.sin(theta))
    bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.022,depth=.39,location=center+normal*.27)
    pin = bpy.context.object
    pin.name = "孔德广场日晷 · 晷针"
    pin.rotation_euler = normal.to_track_quat("Z","Y").to_euler()
    pin.data.materials.append(item.materials["metal"])
    for col in list(pin.users_collection):
        col.objects.unlink(pin)
    item.collection.objects.link(pin)


def square_fixtures(scene,site,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("孔德广场及主轴 · 树池地面与叠砌石")
    g.raised("日晷花坛环砌石","叠砌石",Point(DIAL).buffer(6.0,quad_segs=32).difference(
        Point(DIAL).buffer(5.4,quad_segs=32)),.083,.42)
    g.surface("日晷花坛内土","soil",Point(DIAL).buffer(5.45,quad_segs=32),.39)
    g.build()
    sundial(site)
    wall = site.zone("孔德广场 · 带实拍铭刻的石文化墙",(458,300))
    orient(wall,(437,299),(478,300))
    for i,x in enumerate(np.linspace(-7.1,7.1,5)):
        wall.box("厚叠石墙柱","叠砌石",x,0,1.06,.76,.76,1.94)
        wall.box("叠石浅色顶盖","stone",x,0,2.065,.81,.81,.075)
        if i<4:
            center = x+1.775
            wall.box("文化墙下部石墙","叠砌石",center,0,.67,2.82,.42,1.16)
            wall.box("铭刻石板金属槽","slate",center,.232,.81,2.52,.072,.77)
            panel(wall,"对应实拍文化墙刻板","文化墙仁" if i==1 else "文化墙侧板",
                  center,.277,.81,2.43,.68)
    wall.finish()
    plant = Planting(scene)
    plant.group.name = "孔德广场及桥前增补的绿篱、树阵与树池"
    plant.palette["white"] = mats["white"]
    plant.palette["burgundy"] = material("孔德广场 · 紫叶小乔木",(.135,.040,.041),.89)
    leaf_cards = []
    leaf_texture = bpy.data.materials["三处庭院实拍 · 树叶"]
    ring = [(DIAL[0]+5.12*math.cos(t),DIAL[1]+5.12*math.sin(t)) for t in np.linspace(0,math.tau,41)]
    for x,y in ring[:-1]:
        plant.crown("日晷修剪绿篱","deep",world((x,y))+Vector((0,0,.57)),.38,.43,.38)
    for x in (756,768,780,792):
        for y in (251,267,283):
            tree(plant,(x,y),7.7+((x+y)%5)*.29,"leaf",[],leaf_cards)
    for i,(x,y) in enumerate(((463,247),(454,254),(445,263),(432,271),(418,280),
                              (463,274),(447,285),(501,250))):
        tree(plant,(x,y),6.7+i%3*.72,"leaf",[],leaf_cards)
        if i==7:
            continue
        item = site.zone(f"孔德广场方形树池与石坐凳 {i+1}",(x,y))
        item.box("方池深绿色格盖","green",0,0,.123,1.30,1.30,.029)
        for sign in (-1,1):
            item.box("石坐凳叠砌基座","叠砌石",0,sign*1.01,.29,2.62,.43,.37)
            item.box("石坐凳平整座面","stone",0,sign*1.01,.498,2.69,.53,.104)
        item.finish()
    for points in (
        [(504,253),(504,260),(504,270),(502,282)],
        [(461,286),(463,291),(466,295)],
        [(444,308),(451,312),(454,316)],
        [(724,319),(732,320),(741,320)],
    ):
        plant.hedge(points,.74)
    for x,y in ((505,272),(444,319),(467,303)):
        position = world((x,y))
        plant.limb("紫叶小乔木枝干","bark",position,position+Vector((0,0,2.38)),.105,.028)
        for i in range(70):
            angle = i*2.39996
            radius = .27+.68*(i%6)/5
            center = position+Vector((math.cos(angle)*radius,math.sin(angle)*radius,2.05+(i%7)*.27))
            plant.crown("多簇叶冠或樱花","burgundy",center,.29,.31,.39)
    foliage_cards(plant.group,leaf_texture,[(p,r*1.55,a) for p,r,a in leaf_cards],"实拍树叶 · 主轴和孔德广场")
    for x,y in ((474,256),(477,282),(493,314),(449,288)):
        item = site.zone("孔德广场双面旗帜灯杆",(x,y))
        SiteDetails.lamp(item,0,0,True)
        item.box("背面校色旗幅","red",.24,.04,2.88,.39,.022,.58)
        item.finish()
    for x,y in ((745,283),(746,332),(780,313)):
        item = site.zone("连廊前场黑色庭院灯",(x,y))
        item.box("黑色灯杆","black",0,0,1.63,.078,.078,3.14)
        item.box("方形灯笼浅色罩","white",0,0,3.28,.22,.22,.29)
        item.box("四角黑色灯帽","black",0,0,3.456,.26,.26,.075)
        item.finish()
    plant.finish()


def evidence(scene,views):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",20)
    for tag,sid,heading,*_ in VIEWS:
        scene.camera = views[tag]
        result = OUT/"模型视角"/(tag+".png")
        scene.render.filepath = str(result)
        bpy.ops.render.render(write_still=True)
        if tag.startswith("06"):
            continue
        canvas = Image.new("RGB",(1548,824),"#edebe5")
        draw = ImageDraw.Draw(canvas)
        draw.text((9,8),f"{tag[3:]}  ·  全景 {sid}/{heading}°",fill="#18221f",font=font)
        draw.text((9,37),"全景素材",fill="#26332e",font=font)
        draw.text((779,37),"Blender地面视角（站位估算）",fill="#26332e",font=font)
        for x,path in ((9,reference(sid,heading)),(779,result)):
            with Image.open(path) as picture:
                canvas.paste(picture.convert("RGB").resize((760,760),Image.Resampling.LANCZOS),(x,62))
        canvas.save(OUT/"实景对照"/(tag+".jpg"),quality=94)
    scene.camera = views["08_两楼与连廊俯瞰"]
    scene.render.resolution_x,scene.render.resolution_y = 1280,900
    scene.render.filepath = str(OUT/"模型视角/08_两楼与连廊俯瞰.png")
    bpy.ops.render.render(write_still=True)


def main():
    for directory in ("实拍贴图","模型视角","实景对照"):
        (OUT/directory).mkdir(parents=True,exist_ok=True)
    open_campus(SOURCE)
    scene = bpy.context.scene
    before = set(scene.objects.keys())
    removed = remove_obsolete(scene)
    mats = materials()
    site = SiteDetails(scene,mats)
    tower(site,"15",(699,245))
    tower(site,"21",(738,337))
    west_entries(scene,mats)
    roofs(scene,mats)
    bridge(site)
    ground(scene,mats)
    pergola(site)
    square_fixtures(scene,site,mats)
    mesh = [obj for obj in scene.objects if obj.type=="MESH" and obj.name not in before.difference(removed)]
    unwrap_textured_boxes(mesh)
    clean_generated_meshes(mesh)
    for obj in mesh:
        assert all(math.isfinite(v) for p in obj.data.vertices for v in p.co),obj.name
        assert all(face.area>=1e-9 for face in obj.data.polygons),obj.name
        if any(m and m.name.startswith("教学楼与孔德广场实拍") for m in obj.data.materials):
            assert obj.data.uv_layers,obj.name
    views = {tag:camera(scene,tag,eye,target,aim,lens) for tag,_,_,eye,target,aim,lens in VIEWS}
    overview = "08_两楼与连廊俯瞰"
    views[overview] = camera(scene,overview,(756,418),(631,291),0,41,101)
    scene.camera = views["06_思远楼志远楼连廊近景"]
    scene.render.resolution_x = scene.render.resolution_y = 760
    scene.cycles.samples = 12
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB",
                             export_cameras=False,export_lights=False)
    record = {
        "母版":str(SOURCE), "站点":"32/090、32/135、40/045、15/270、15/225、15/180、07/000",
        "名称":"素材库B15站点标为志远楼，本轮沿用原清单名称",
        "连廊航拍走向":BRIDGE, "志远楼至思远楼西侧道路":ROAD, "木廊架":PERGOLA,
        "实拍贴图":CROPS, "相机":VIEWS, "新增网格":len(mesh), "换下的旧网格":removed,
        "精度":"楼高、桥端标高、窗格间距、遮挡构件、各对照相机位置及木廊架长度依照片和航拍估算。",
    }
    (OUT/"定位与验收.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    evidence(scene,views)


if __name__ == "__main__":
    main()
