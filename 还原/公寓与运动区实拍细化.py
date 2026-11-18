"""Reconstruct the dormitory exteriors and western sports grounds from campus panoramas."""

import json
import math

import bpy
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, Point, Polygon, box

from 三处庭院实拍细化 import foliage_cards, panel, tree, unwrap_textured_boxes
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 四栋教学楼实景细化 import reference
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 地面街道实景细化 import Ground
from 尚德广场实拍细化 import photo_material
from 思远志远连廊与孔德广场 import OUT as PREVIOUS, STEM as PREVIOUS_STEM
from 楼间过道实拍细化 import camera, clean_generated_meshes, orient


SOURCE = PREVIOUS / (PREVIOUS_STEM + ".blend")
OUT = PREVIOUS.parent / "公寓与运动区实拍细化"
STEM = "校园室外_公寓与运动区"
SCALE = CAL["metres_per_pixel"]
BLOCKS = {b["id"]:b for b in PLAN["buildings"]}
PITCH = (96,184,243,410)
COURTS = ((322,94,352.1,157),(356.9,94,387,157),
          (322,167,352.1,230),(356.9,167,387,230))
STAND = ((238,105),(253,119),(267,139),(277,160),(281,182),(282,208),
         (282,249),(278,260),(276,326),(275,401),(274,469))
COURTYARD = ((582,155),(644,152),(688,146),(733,152),(782,157),
             (840,150),(898,150),(944,153),(984,161),(1019,156))
VIEWS = (
    ("01_绅远楼门厅","25","000",(673,170),(673,143),2.0,18,1.64),
    ("02_蕙远楼门厅与坡道","28","000",(893,157),(886,143),2.1,16,1.64),
    ("03_公寓北侧劳动基地","14","000",(875,68),(875,82),2.1,18,1.64),
    ("04_攀桂轩木廊","12","000",(606,173),(653,153),2.0,18,1.64),
    ("05_篮球场与红色看台背面","11","090",(354.5,198.5),(280,198.5),1.85,18,1.64),
    ("06_篮球场蓝色通道","11","000",(354.5,212),(354.5,105),1.8,18,1.64),
    ("07_操场中线与主席台","09","000",(169.5,297),(259,297),1.95,18,1.64),
    ("08_乒乓球区与跑道","10","090",(44,377),(155,355),1.35,19,1.64),
    ("09_公寓带俯瞰","","",(792,246),(794,109),0,29,169),
    ("10_运动区俯瞰","","",(104,448),(213,283),0,30,190),
)

# Control points are measured on the direction photographs scaled to 850 by 850.
CROPS = {
    "公寓反光窗":("14","000",[(573,81),(647,83),(647,126),(573,122)],(320,196),1),
    "公寓窗帘":("25","000",[(352,197),(431,201),(431,234),(352,228)],(420,155),1),
    "灰色板墙":("14","000",[(561,138),(648,142),(647,188),(561,184)],(360,240),1.8),
    "浅色路面":("28","000",[(296,640),(597,640),(691,820),(226,820)],(560,390),3.8),
    "灰石坡道":("28","000",[(357,503),(514,505),(562,554),(329,554)],(550,330),2.7),
    "男生公寓":("25","000",[(339,236),(453,239),(453,274),(339,274)],(584,172),1),
    "女生公寓":("28","000",[(340,150),(515,148),(515,190),(340,196)],(700,176),1),
    "宿舍公告栏":("28","000",[(69,392),(97,388),(98,449),(70,454)],(320,580),1),
    "攀桂轩刻石":("12","000",[(447,505),(542,477),(582,534),(447,546)],(580,330),1),
    "草皮深色":("09","000",[(289,642),(350,642),(358,818),(232,818)],(440,440),2.8),
    "草皮浅色":("09","315",[(457,665),(604,665),(660,820),(398,820)],(440,440),2.8),
    "主席台校训":("09","000",[(374,377),(490,377),(490,408),(374,408)],(928,248),1),
    "红色看台墙":("11","090",[(321,341),(485,341),(485,370),(321,370)],(560,240),3.7),
}


def materials():
    colors = {
        "slate":(.101,.121,.133),"dark":(.049,.062,.069),"ink":(.025,.036,.042),
        "metal":(.115,.149,.164),"silver":(.54,.56,.54),"light":(.69,.70,.67),
        "ochre":(.72,.383,.071),"stone":(.44,.43,.39),"glass":(.102,.211,.279),
        "wood":(.48,.254,.065),"soil":(.15,.117,.066),"leaf":(.091,.187,.043),
        "red":(.61,.048,.030),"seat_red":(.68,.105,.142),"seat_blue":(.051,.40,.62),
        "stand_red":(.40,.105,.095),"track":(.435,.102,.060),
        "white":(.84,.84,.77),"yellow":(.82,.474,.068),"blue":(.013,.116,.264),
        "playing_green":(.091,.30,.052),"orange":(.88,.159,.022),
        "fence":(.042,.082,.068),"roof":(.10,.30,.43),"birch":(.64,.54,.43),
    }
    result = {name:material("公寓与运动区 · "+name,rgb,.43 if name in {"glass","silver"} else .84)
              for name,rgb in colors.items()}
    result["canopy"] = material("篮球篮板及门厅雨棚玻璃",(.24,.61,.71),.25)
    result["canopy"].diffuse_color = (.24,.61,.71,.24)
    result["canopy"].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = .24
    result["canopy"].surface_render_method = "DITHERED"
    for name,(sid,heading,quad,size,period) in CROPS.items():
        with Image.open(reference(sid,heading)) as photo:
            rgb = np.asarray(photo.convert("RGB"))
        source = np.float32(quad)*np.float32((rgb.shape[1]/850,rgb.shape[0]/850))
        w,h = size
        target = np.float32([(0,0),(w-1,0),(w-1,h-1),(0,h-1)])
        pixels = cv2.warpPerspective(rgb,cv2.getPerspectiveTransform(source,target),size)
        if period>1:
            blur = cv2.GaussianBlur(pixels.astype(np.float32),(0,0),max(15,min(size)/9))
            pixels = np.clip(pixels+.72*(np.median(blur,axis=(0,1))-blur),0,255).astype(np.uint8)
        if name == "浅色路面":
            yy,xx = np.mgrid[0:h,0:w]
            distance = np.minimum.reduce((xx,yy,w-1-xx,h-1-yy))
            blend = np.clip(distance/37,0,1)[:,:,None]
            pixels = (pixels*blend+np.median(pixels,axis=(0,1))*(1-blend)).astype(np.uint8)
        if name in {"男生公寓","女生公寓"}:
            hsv = cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV)
            mask = (((hsv[:,:,0]<12)|(hsv[:,:,0]>149)) & (hsv[:,:,1]>70)).astype(np.uint8)*255
            pixels = np.dstack((pixels,mask))
        path = OUT/"实拍贴图"/(name+".png")
        Image.fromarray(pixels).save(path)
        texture = bpy.data.images.load(str(path))
        texture.pack()
        mat = photo_material(name,texture,(.32,.36,.36),.47 if "窗" in name else .91,period)
        mat.name = "公寓与运动区实拍 · "+name
        if pixels.shape[2]==4:
            node = next(n for n in mat.node_tree.nodes if n.type=="TEX_IMAGE")
            mat.node_tree.links.new(node.outputs["Alpha"],mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"])
            mat.surface_render_method = "DITHERED"
        result[name] = mat
    return result


def remove_previous(scene):
    prefixes = ("B25 绅远楼 · 外立面","B28 蕙远楼 · 外立面","绅远楼正门侧坡道",
                "蕙远楼正门侧坡道","北侧攀桂轩 · 砖径木廊架","劳动基地 · 种植畦与支架")
    replacements = {"道路设施 · 宣传栏与分类桶 4","道路设施 · 宣传栏与分类桶 5"}
    removed = []
    for collection in list(scene.collection.children):
        if collection.name.startswith(prefixes) or collection.name in replacements:
            for obj in list(collection.objects):
                removed.append(obj.name)
                bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.collections.remove(collection)
    for obj in list(scene.objects):
        if obj.name in {"B25","B28","P11"} or obj.name.startswith(("P09_","P10_","P11_")):
            removed.append(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    return removed


def segment(site,label,a,b):
    item = site.zone(label,tuple((i+j)/2 for i,j in zip(a,b)))
    orient(item,a,b)
    return item,(world(b)-world(a)).length


def rod(item,label,key,a,b,radius,sides=8):
    start,end = (item.point(*p) for p in (a,b))
    axis = (end-start).normalized()
    across = axis.cross(Vector((0,0,1)))
    if across.length<1e-5:
        across = axis.cross(Vector((1,0,0)))
    across.normalize()
    depth = axis.cross(across)
    verts,faces = item.groups.setdefault((label,key),([],[]))
    index = len(verts)
    for center in (start,end):
        for angle in np.linspace(0,math.tau,sides,endpoint=False):
            verts.append(center+radius*(math.cos(angle)*across+math.sin(angle)*depth))
    faces.extend((index+i,index+(i+1)%sides,index+sides+(i+1)%sides,index+sides+i) for i in range(sides))
    faces.extend((tuple(index+i for i in reversed(range(sides))),
                  tuple(index+sides+i for i in range(sides))))


def air_conditioner(item,x,z):
    b = item.box
    b("窗旁空调外机","light",x,.32,z,.68,.35,.47)
    b("空调风扇凹面","dark",x,.503,z,.46,.012,.30)
    for i in range(6):
        b("外机百叶","silver",x,.517,z+(i-2.5)*.046,.47,.023,.013)
    for dx in (-.23,.23):
        b("外机托架","slate",x+dx,.28,z-.29,.043,.35,.065)


def front_panel(item,label,key,x,y,z,width,height):
    obj = panel(item,label,key,x,y,z,width,height)
    for loop in obj.data.uv_layers.active.data:
        loop.uv.x = 1-loop.uv.x
    return obj


def dorm_entry(item,label):
    b = item.box
    width = 4.70
    b("凹进门厅侧面","ochre",-2.46,-.53,1.86,.27,1.02,3.56)
    b("凹进门厅侧面","ochre",2.46,-.53,1.86,.27,1.02,3.56)
    b("内门厅作用面","dark",0,-1.23,1.81,width,.19,3.40)
    for side in (-1,1):
        x = side*1.56
        b("门侧反光固定玻璃","glass",x,-.58,1.81,1.51,.085,2.67)
        for k in (-1,0,1):
            b("门框不锈钢窄边","silver",x+k*.71,-.526,1.80,.035,.069,2.74)
        b("玻璃蓝色防撞条","blue",x,-.531,1.62,1.46,.017,.071)
        b("开启的玻璃门扇","canopy",side*.78,-.23,1.78,.080,.72,2.57)
        b("开门扶手","silver",side*.78,.135,1.55,.064,.045,.43)
    b("门上透明气窗","glass",0,-.59,3.09,width,.094,.40)
    b("门框横梃","silver",0,-.525,2.88,width,.093,.07)
    for i in range(3):
        step = (i+1)*.15
        b("入门石踏步","灰石坡道",0,1.77-i*.34,.12+step/2,4.89,.36,step)
    b("门前整块石平台","灰石坡道",0,.325,.343,4.94,1.96,.45)
    b("透光雨棚","canopy",0,1.23,3.81,5.75,2.82,.067)
    for i in range(7):
        x = (i-3)*.86
        rod(item,"雨棚挑梁","metal",(x,-.10,3.73),(x,2.61,3.75),.045)
        rod(item,"雨棚吊杆","silver",(x,-.05,4.35),(x,1.83,3.76),.016,6)
    front_panel(item,"全景实拍门楣红字",label,0,.179,6.77,3.62,.92)
    if label=="女生公寓":
        start,end = 1.12,7.17
        x0,x1 = -4.35,-2.57
    else:
        start,end = 1.08,5.13
        x0,x1 = -4.16,-2.61
    slope = (start,end,.57,.13)
    y0,y1,z0,z1 = slope
    corners = ((x0,y0,z0),(x1,y0,z0),(x1,y1,z1),(x0,y1,z1))
    item.link("门旁一体石板坡道",[item.point(*p) for p in corners],[(0,1,2,3)],item.materials["灰石坡道"])
    for side in (x0,x1):
        for z in (.95,.12):
            rod(item,"坡道连续不锈钢扶手","silver",(side,y0,z0+z),(side,y1,z1+z),.031)
        for t in np.linspace(0,1,24):
            y,z = (1-t)*y0+t*y1,(1-t)*z0+t*z1
            rod(item,"坡道竖向栏杆","silver",(side,y,z),(side,y,z+.94),.018,6)
    for i in range(3):
        x = 4.40+i*.86
        b("公告栏红立杆","red",x-.39,2.21,1.03,.085,.09,1.86)
        b("公告栏白框","light",x,2.25,1.25,.82,.12,1.16)
        front_panel(item,"蓝色实拍公告面","宿舍公告栏",x,2.318,1.25,.70,1.06)
    b("公告栏末端红立杆","red",6.53,2.21,1.03,.085,.09,1.86)
    b("公告栏连体檐","blue",5.26,2.23,1.89,2.67,.33,.076)
    if label=="女生公寓":
        for k,key in enumerate(("blue","red","dark","leaf")):
            x = -6.85-k*.57
            b("四分类垃圾桶",key,x,1.47,.543,.487,.49,.84)
            b("分类箱盖",key,x,1.47,.994,.52,.52,.075)
            b("分类桶标识","white",x,1.722,.655,.178,.016,.183)


def dormitories(scene,site,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("公寓屋顶、检修围边与入口铺地")
    for sid,label in (("25","男生公寓"),("28","女生公寓")):
        building = BLOCKS["B"+sid]
        ring = building["outline"]
        outline = Polygon(ring)
        top = 22.9
        g.raised("B"+sid+" 完整屋顶楼板","stone",outline,top-.21,top)
        border = outline.buffer(-.10).difference(outline.buffer(-.91))
        g.raised("B"+sid+" 连续屋面女儿墙","ochre",border,top,top+.50)
        g.surface("B"+sid+" 女儿墙浅灰压顶","light",border,top+.51)
        for index,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
            item,span = segment(site,f"B{sid} {building['name']} · 外墙 {index+1}",a,b)
            item.sid = sid
            bld = item.box
            count = max(1,round(span/2.95))
            pitch = span/count
            entry = index==3
            bld("实拍灰色墙板内衬","灰色板墙",0,-.159,13.44,span,.29,18.92)
            bld("灰墙起落交界","slate",0,.026,4.13,span,.33,.16)
            bld("黄色檐缘","ochre",0,.016,top-.28,span+.06,.43,.54)
            if entry:
                for side in (-1,1):
                    w=(span-4.70)/2
                    bld("首层橙黄色实墙","ochre",side*(2.35+w/2),-.09,2.1,w,.34,4.04)
                bld("入口橙黄过梁","ochre",0,-.13,3.83,4.74,.30,.52)
                dorm_entry(item,label)
                apron = [item.point(x,y,0) for x,y in ((-5.4,0),(5.4,0),(6.2,12.1),(-6.2,12.1))]
                origin = np.array(PLAN["origin"])
                rot = math.radians(CAL["rotation_degrees"])
                inverse = np.array(((math.cos(rot),math.sin(rot)),(math.sin(rot),-math.cos(rot))))/SCALE
                local = Polygon([origin+inverse@p.xy for p in apron])
                g.surface("B"+sid+" 门前实拍浅色车道","浅色路面",local.difference(outline),.116)
                if sid=="25":
                    for y in (4.3,5.95,7.78,9.63,11.44):
                        bld("男生公寓门前黄色短标线","yellow",0,y,.119,3.70,.16,.006)
                for direction in (-1,1):
                    bld("门厅通高深色凹槽","dark",direction*2.63,.073,13.3,.37,.22,18.3)
                    bld("门厅侧灰色进深竖边","slate",direction*2.91,.28,13.3,.37,.47,18.3)
                bld("门厅边角整条橙黄立柱","ochre",-3.12,.32,13.20,.20,.28,18.4)
            else:
                bld("首层橙黄色实墙","ochre",0,-.105,2.09,span,.34,4.10)
            for i in range(count):
                x = (i+.5)*pitch-span/2
                w = pitch*.78
                if not entry or abs(x)>3.2:
                    bld("底层窗洞暗框","dark",x,.103,2.27,w+.11,.104,1.50)
                    panel(item,"底层反光窗内衬","公寓反光窗",x,.173,2.27,w,1.44)
                    for k in range(10):
                        bld("首层细金属防护栏","silver",x+((k/9)-.5)*w,.232,2.27,.020,.023,1.50)
                    for z in (1.52,2.99):
                        bld("防护栏横压条","silver",x,.242,z,w+.07,.031,.031)
                for floor in range(6):
                    z = 5.39+floor*2.87
                    if entry and abs(x)<2.15:
                        continue
                    bld("凹窗边框及外窗台","dark",x,.036,z,w+.12,.19,1.42)
                    panel(item,"实拍玻璃窗与窗帘","公寓窗帘" if (i+floor)%3 else "公寓反光窗",
                          x,.142,z,w,1.28)
                    for k in (-.5,-.24,.19,.5):
                        bld("宿舍窗竖框","metal",x+k*w,.165,z,.047,.059,1.33)
                    bld("外窗横梃","metal",x,.169,z+.38,w,.052,.042)
                    bld("窄灰石窗台","slate",x,.137,z-.69,w+.17,.32,.078)
                    if i%2==0 and span>9:
                        air_conditioner(item,x+w*.49,z-.57)
            if entry:
                for f in range(6):
                    z = 5.31+f*2.87
                    panel(item,"门厅上方连续窗组","公寓窗帘",0,.165,z,4.68,1.34)
                    for x in np.linspace(-2.32,2.32,7):
                        bld("门厅连续窗竖框","metal",x,.193,z,.050,.061,1.40)
                for x in (-2.12,2.08):
                    air_conditioner(item,x,7.46)
            for i in range(1,count):
                x=i*pitch-span/2
                if not entry or abs(x)>2.56:
                    bld("灰墙薄竖肋","slate",x,.11,13.42,.147,.30,18.72)
            for f in range(6):
                z=4.20+f*2.87
                bld("灰墙窗与墙板之间横肋","slate",0,.12,z,span,.29,.095)
            # The view from the square shows rainwater downpipes beside full-height joints.
            for x in np.linspace(-span*.42,span*.42,max(2,round(span/14))):
                if not entry or abs(x)>3.25:
                    rod(item,"灰色落水管","slate",(x,.36,.18),(x,.36,top-.4),.054,10)
            item.finish()
            item.collection["来源"] = f"{sid}/000与近角度、14/000及12/000；侧后遮挡开间按航拍轮廓估计"
        for k,(x,y) in enumerate(((ring[0][0]+12,106),(ring[1][0]-17,104))):
            item = site.zone(f"B{sid} 屋面设备间 {k+1}",(x,y))
            item.box("灰色检修设备间","slate",0,0,24.20,5.1,6.2,2.42)
            item.box("屋顶浅色金属帽","light",0,0,25.44,5.30,6.41,.12)
            item.finish()
    g.build()


def arcline(center,radius,start=0,end=math.tau,steps=84):
    x,y=center
    return [(x+radius*math.cos(t),y+radius*math.sin(t)) for t in np.linspace(start,end,steps)]


def football(scene,site,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("运动场 · 实拍条纹草坪及独立标线")
    pitch = box(*PITCH)
    left,top,right,bottom = PITCH
    cx,cy = (left+right)/2,(top+bottom)/2
    apron = Polygon(((60,105),(224,102),(248,120),(281,159),(284,210),
                     (282,468),(259,484),(59,481),(58,140)))
    g.surface("红色塑胶跑道与起跑区","track",apron.difference(pitch),.085)
    for i in range(18):
        y0 = top+i*(bottom-top)/18
        y1 = top+(i+1)*(bottom-top)/18
        g.surface("实拍双深度草坪","草皮浅色" if i%2 else "草皮深色",box(left,y0,right,y1),.097)
    lanes = LineString(((164.5,207),(164.5,377)))
    mask = apron.buffer(-.14).difference(pitch)
    for i in range(9):
        boundary = lanes.buffer(84.7+2.33*i,quad_segs=48).exterior
        line = boundary.buffer(.068).intersection(mask)
        g.surface(f"第{i+1}条跑道分隔线","white",line,.091)
    for y in (196,214,358,377,399,433):
        g.line("直道横向起跑标线","white",(249,y),(267.8,y),.072,.093)
    for panel_outline in (
        [(125,159),(139,146),(154,141),(159,161)],
        [(170,160),(177,139),(193,145),(215,160)],
    ):
        g.surface("北端草坪岛","草皮深色",Polygon(panel_outline),.096)
    for edge_y,sign in ((top,1),(bottom,-1)):
        for depth,span,label in ((16.50,40.32,"罚球区"),(5.5,18.32,"球门区")):
            x0,x1=cx-span/(2*SCALE),cx+span/(2*SCALE)
            back=edge_y+sign*depth/SCALE
            g.polyline(label+"划线","white",((x0,edge_y),(x0,back),(x1,back),(x1,edge_y)),.10,.105)
        pc=(cx,edge_y+sign*11/SCALE)
        g.surface("点球点","white",Point(pc).buffer(.20/SCALE),.107)
        partial = LineString(arcline(pc,9.15/SCALE)).difference(
            box(left,min(edge_y,edge_y+sign*16.5/SCALE),right,max(edge_y,edge_y+sign*16.5/SCALE)))
        g.surface("禁区外罚球弧","white",partial.buffer(.11),.105)
        for x in (left,right):
            a = 0 if x==left else math.pi/2
            if sign==-1:
                a = 1.5*math.pi if x==left else math.pi
            g.polyline("角球弧","white",arcline((x,edge_y),1/SCALE,a,a+math.pi/2,12),.10,.106)
            flag = site.zone("四角角旗",(x,edge_y))
            flag.box("角旗立杆","white",0,0,.79,.031,.031,1.48)
            flag.box("红角旗面","red",.16,0,1.38,.32,.018,.23)
            flag.finish()
        item = site.zone("足球球门及网绳",(cx,edge_y-sign*.6))
        # Frame and net face into the pitch; the back is offset outside the end line.
        orient(item,(right,edge_y) if sign==1 else (left,edge_y),
               (left,edge_y) if sign==1 else (right,edge_y))
        for x in (-3.66,3.66):
            rod(item,"球门金属框","white",(x,0,.111),(x,0,2.55),.058,12)
            rod(item,"后撑斜杆","white",(x,-1.85,.112),(x,-.11,2.51),.032)
        rod(item,"球门横梁","white",(-3.66,0,2.55),(3.66,0,2.55),.058,12)
        for x in np.linspace(-3.62,3.62,41):
            rod(item,"后网竖绳","light",(x,-1.84,.12),(x,-.07,2.54),.0048,4)
        for t in np.linspace(.02,.99,17):
            y,z=-1.85+1.78*t,.112+2.428*t
            rod(item,"后网横绳","light",(-3.64,y,z),(3.64,y,z),.0048,4)
        item.finish()
    g.polyline("足球场白色边界","white",[(left,top),(right,top),(right,bottom),(left,bottom),(left,top)],.115,.105)
    g.line("球场中线","white",(left,cy),(right,cy),.115,.105)
    g.polyline("球场中圈","white",arcline((cx,cy),9.15/SCALE),.115,.106)
    g.surface("中圈开球点","white",Point((cx,cy)).buffer(.23/SCALE),.107)
    g.build()


def basketball(scene,site,mats):
    g = Ground(scene)
    g.materials.update(mats)
    g.region("篮球区 · 蓝色缓冲带与4片球场")
    blocks = (box(317,90,390,160),box(317,163,390,234))
    for plot in blocks:
        g.surface("蓝色缓冲和中间通道","blue",plot,.088)
    for index,(left,top,right,bottom) in enumerate(COURTS,1):
        pitch = box(left,top,right,bottom)
        cx,cy=(left+right)/2,(top+bottom)/2
        g.surface(f"{index}号绿球场","playing_green",pitch,.094)
        g.polyline("篮球场四周白线","white",list(pitch.exterior.coords),.055,.102)
        g.line("篮球中线","white",(left,cy),(right,cy),.055,.104)
        g.surface("篮球橙中圈","orange",Point((cx,cy)).buffer(1.8/SCALE),.100)
        g.polyline("篮球中圈白边","white",arcline((cx,cy),1.8/SCALE),.05,.104)
        for y,sign in ((top,1),(bottom,-1)):
            free=y+sign*5.8/SCALE
            hw=2.45/SCALE
            key=box(cx-hw,min(y,free),cx+hw,max(y,free))
            g.surface("橙色限制区","orange",key,.100)
            g.polyline("限制区边线","white",list(key.exterior.coords),.050,.106)
            start,end=(0,math.pi) if sign==1 else (math.pi,math.tau)
            g.polyline("罚球半圆","white",arcline((cx,free),1.80/SCALE,start,end,40),.051,.105)
            center_y=y+sign*1.575/SCALE
            side_x=6.45/SCALE
            corner_y=center_y+sign*math.sqrt(6.75**2-6.45**2)/SCALE
            a=math.acos(6.45/6.75)
            outer=arcline((cx,center_y),6.75/SCALE,a,math.pi-a,50) if sign==1 else arcline(
                (cx,center_y),6.75/SCALE,math.pi+a,math.tau-a,50)
            g.polyline("三分弧与底角直线","white",outer,.050,.106)
            for end_x in (cx-side_x,cx+side_x):
                g.line("底角三分线","white",(end_x,y),(end_x,corner_y),.05,.106)
            g.polyline("篮下半圆","white",arcline((cx,center_y),1.25/SCALE,start,end,24),.048,.106)
            hoop(site,index,(cx,y),sign)
    for i,plot in enumerate(blocks,1):
        left,top,right,bottom=plot.bounds
        for a,b in (((left,top),(left,bottom)),((right,top),(right,bottom)),((left,top),(352,top)),
                    ((357,top),(right,top)),((left,bottom),(352,bottom)),((357,bottom),(right,bottom))):
            fence(site,f"篮球场{ i }护网",a,b)
    for x in (315,390):
        for y in (111,155,197,230):
            floodlight(site,(x,y))
    g.build()


def hoop(site,index,point,sign):
    item = site.zone(f"篮球场{index}蓝色悬臂篮球架",point)
    if sign == 1:
        orient(item,(1,0),(0,0))
    b=item.box
    b("蓝色移动基座","blue",0,-.94,.233,1.31,1.53,.26)
    rod(item,"蓝漆箱式立臂","blue",(0,-1.10,.31),(0,-.74,2.52),.115,4)
    rod(item,"球架上悬臂","blue",(0,-.74,2.52),(0,1.16,3.26),.102,4)
    for x in (-.36,.36):
        rod(item,"球架斜撑","blue",(x,-1.54,.33),(0,-.48,2.39),.052)
    b("透明钢化篮板","canopy",0,1.14,3.47,1.80,.072,1.02)
    for x in (-.91,.91):
        b("篮板边框","blue",x,1.14,3.47,.035,.090,1.05)
    for z in (2.96,3.99):
        b("篮板边框","blue",0,1.14,z,1.83,.090,.035)
    for x in (-.28,.28):
        b("篮板瞄准矩形竖边","white",x,1.183,3.28,.028,.010,.42)
    for z in (3.07,3.49):
        b("篮板瞄准矩形横边","white",0,1.183,z,.58,.010,.026)
    circle = arcline((0,1.53),.226,steps=24)
    for a,c in zip(circle,circle[1:]):
        rod(item,"橙色精细篮圈","orange",(*a,3.15),(*c,3.15),.016)
    for t in np.linspace(0,math.tau,13)[:-1]:
        for sign in (-1,1):
            rod(item,"锥形篮网绳","white",(.222*math.cos(t),1.53+.222*math.sin(t),3.143),
                (.122*math.cos(t+sign*.225),1.53+.122*math.sin(t+sign*.225),2.76),.005,5)
    item.finish()


def fence(site,name,a,b,height=3.05):
    item,span = segment(site,name,a,b)
    item.box("黑绿围网顶杆","fence",0,0,height,span,.054,.058)
    item.box("黑绿围网底杆","fence",0,0,.26,span,.051,.046)
    for x in np.linspace(-span/2,span/2,max(2,round(span/2.35)+1)):
        item.box("围网粗立柱","fence",x,0,(height+.11)/2,.056,.060,height-.11)
    for x in np.linspace(-span/2,span/2,max(2,round(span/.115)+1)):
        item.box("围网细竖丝","fence",x,0,(height+.26)/2,.009,.010,height-.26)
    for z in np.arange(.36,height,.116):
        item.box("围网细横丝","fence",0,0,z,span,.010,.009)
    item.finish()


def floodlight(site,pixel):
    item = site.zone("活动区双层体育照明",pixel)
    rod(item,"镀锌灯杆","silver",(0,0,.10),(0,0,8.2),.070,10)
    for z in (6.90,8.12):
        item.box("灯头横臂","silver",0,0,z,1.44,.041,.044)
        for x in (-.69,.69):
            item.box("深灰投光灯外壳","dark",x,0,z-.045,.28,.24,.13)
            item.box("投光灯面板","light",x,-.128,z-.05,.25,.019,.109)
    item.finish()


def grandstand(site):
    # The northern tiers follow the curve visible on both the aerial and basketball panorama.
    aisles = {0,3,5,7,11,14,17}
    sections = []
    rim = [(x-9.1,y) for x,y in STAND]
    for a,b in zip(rim,rim[1:]):
        n=max(1,round(math.dist(a,b)/17))
        for i in range(n):
            sections.append(tuple(tuple(p+(q-p)*t/n for p,q in zip(a,b)) for t in (i,i+1)))
    for index,(a,b) in enumerate(sections):
        item,span=segment(site,f"运动场看台 · 第{index+1:02}段",b,a)
        build=item.box
        stairs = index in aisles
        for tier in range(11):
            z=.19+tier*.31
            y=-.32-tier*.52
            color = "seat_blue" if tier<3 else "light" if tier<6 else "seat_red"
            build("逐级看台踏板","stone",0,y,z/2+.05,span+.11,.55,z)
            stair_width = 1.55 if stairs else 0
            seat_width = span-stair_width
            build("红白蓝看台座阶",color,stair_width/2,y-.025,z+.064,seat_width+.02,.49,.055)
            build("红白蓝座阶竖立面",color,stair_width/2,y+.255,z-.06,seat_width+.02,.045,.21)
            if stairs:
                x = (stair_width-span)/2
                build("楼梯半级踏步","light",x,y+.32,z-.037,stair_width,.34,.077)
                build("黄色安全沿","yellow",x,y+.48,z+.017,stair_width,.031,.014)
        build("球场侧绿腰墙","leaf",0,.17,.51,span+.12,.30,.84)
        build("看台后弧形深红横梁","stand_red",0,-5.99,4.06,span+.28,.76,.80)
        build("看台后检修走道","stone",0,-6.12,3.59,span+.05,1.02,.20)
        build("看台后上沿栏杆","fence",0,-6.80,4.59,span+.09,.05,.043)
        if index%4:
            build("看台背侧红墙","红色看台墙",0,-6.12,1.98,span+.18,.49,3.59)
            panel(item,"后墙高窗","公寓反光窗",0,-6.38,2.63,min(span*.54,2.4),.50)
            build("背侧检修门","slate",0,-6.41,1.13,.92,.085,1.94)
        else:
            for x in (-span*.44,span*.44):
                build("红色敞开廊下方柱","stand_red",x,-6.12,1.92,.39,.60,3.60)
        for x in np.linspace(-span*.48,span*.48,4):
            build("看台后栏杆立柱","fence",x,-6.80,4.32,.030,.040,.57)
        item.finish()
    stage,span = segment(site,"运动场主席台与校训雨棚",(275,327),(274,263))
    b=stage.box
    b("主席台红色平台","seat_red",0,1.08,1.14,span,3.58,1.95)
    b("主席台白色校训墙","white",0,-2.44,4.19,span*.66,.44,2.51)
    front_panel(stage,"实拍校训与校徽","主席台校训",0,-2.204,4.24,span*.64,2.19)
    for side in (-1,1):
        for step in range(7):
            z=.21*(step+1)
            b("主席台两侧石踏步","light",side*span*.44,3.48-step*.40,z/2+.07,2.05,.42,z)
    for x in (-span*.43,span*.43):
        b("钢棚落地支柱","metal",x,-3.31,4.29,.33,.40,8.33)
    b("大跨蓝色金属雨棚","roof",0,-.23,8.60,span+.60,9.82,.16)
    b("雨棚正面深灰檐口","dark",0,4.70,8.54,span+.72,.25,.20)
    for x in np.linspace(-span*.49,span*.49,18):
        b("雨棚主次梁","slate",x,-.24,8.389,.116,9.77,.24)
        rod(stage,"雨棚三角钢拉撑","metal",(x,-3.27,7.81),(x,4.15,8.37),.037)
    for y in np.linspace(-4.85,4.55,15):
        b("可见金属檩条","metal",0,y,8.31,span,.076,.11)
    stage.finish()
    for i,y in enumerate((245,348),1):
        tunnel=site.zone(f"运动场看台门洞 {i}",(270,y))
        orient(tunnel,(270,y-1),(270,y+1))
        tunnel.box("门洞深处阴影","dark",0,1.01,1.27,2.65,.15,2.33)
        for x in (-1.57,1.57):
            tunnel.box("门洞侧混凝土墙","light",x,-.10,1.32,.31,2.31,2.40)
        tunnel.box("门洞挑出檐梁","light",0,-.13,2.58,3.51,2.38,.27)
        tunnel.box("门洞脚下水泥平台","stone",0,-.41,.15,2.82,1.84,.12)
        tunnel.box("蓝色门洞号牌","blue",0,-1.329,2.60,.30,.037,.17)
        tunnel.finish()
    for i,pixel in enumerate(((263,340),(263,348),(263,356))):
        item=site.zone("主席台边独立旗杆",pixel)
        rod(item,"旗杆银柱","silver",(0,0,.10),(0,0,9.1-i*.41),.040,10)
        item.box("旗台方石底座","light",0,0,.24,.55,.55,.29)
        item.box("红旗布","red",0,.50,8.71-i*.41,.019,.99,.56)
        item.finish()
    for a,b in (((279,327),(280,469)),):
        item,span=segment(site,"运动馆面向跑道的长条蓝窗与白柱",a,b)
        item.box("蓝窗深色墙衬","dark",0,-.84,9.84,span,.83,4.61)
        item.box("浅色体育馆檐边","light",0,-.45,12.44,span+.2,.58,.70)
        for x in np.linspace(-span*.49,span*.49,21):
            panel(item,"体育馆窗间反光","公寓反光窗",x,-.404,10.03,span/22,3.44)
            item.box("高廊白色立柱","light",x-span/46,-.225,10.12,.19,.55,4.58)
        for z in (7.42,7.68,7.94,8.20):
            item.box("体育馆下沿通长薄百叶","slate",0,-.15,z,span,.19,.091)
        item.finish()


def ping_pong(scene,site,mats):
    g=Ground(scene)
    g.materials.update(mats)
    g.region("乒乓球台与操场西侧边界")
    g.surface("西侧乒乓区混凝土带","浅色路面",box(42,322,60,437),.112)
    for x,y in ((50,340),(51,357),(50,374),(51,391),(50,408),(51,425)):
        item=site.zone("蓝面红架室外乒乓球台",(x,y))
        b=item.box
        b("双扇蓝色桌面","blue",0,0,.89,1.53,2.74,.058)
        for side in (-1,1):
            b("白色桌面边线","white",side*.751,0,.923,.022,2.74,.008)
            b("白色桌面端线","white",0,side*1.357,.923,1.53,.023,.008)
            for yy in (-.81,.81):
                rod(item,"红色弧线桌腿","red",(side*.50,yy,.86),(side*.12,yy,.34),.034)
                rod(item,"红色弧线桌腿","red",(side*.12,yy,.34),(side*.63,yy*1.39,.12),.034)
        b("穿孔中央球网","dark",0,0,1.000,1.75,.018,.133)
        b("球网上缘白边","white",0,0,1.072,1.76,.025,.026)
        item.finish()
    fence(site,"运动场西侧围网",(42,114),(42,442),2.1)
    fence(site,"运动场南侧围网",(43,486),(272,486),1.95)
    g.build()


def site_landscape(scene,site,mats):
    g=Ground(scene)
    g.materials.update(mats)
    g.region("公寓门前车道、攀桂轩与运动区外围")
    path=LineString(COURTYARD)
    g.surface("公寓南侧连续步道","浅色路面",path.buffer(5.4,cap_style="flat"),.099)
    for offset in (-5.35,5.35):
        g.raised("公寓道路连续道牙","stone",path.offset_curve(offset).buffer(.27,cap_style="flat"),.068,.136)
    for a,b in (((388,174),(438,176)),((299,240),(302,278)),((291,287),(374,303)),
                ((249,102),(311,81)),((54,482),(270,480))):
        g.surface("球场边通路和看台入口","浅色路面",LineString((a,b)).buffer(4.2,cap_style="flat"),.098)
    g.surface("北侧围墙内侧步行带","brick",box(574,65,1021,71),.127)
    beds=[]
    for x in range(599,1010,17):
        if 771 < x < 792:
            continue
        bed=box(x-6.4,75.1,x+6.1,80.2)
        beds.append(bed)
        border=bed.buffer(.21).difference(bed.buffer(-.15))
        g.raised("劳作小块种植畦缘","stone",border,.09,.192)
        g.surface("分班种植畦表土","soil",bed,.158)
    garden=LineString(((582,172),(603,168),(622,162),(638,157),(650,154),(658,153)))
    g.surface("沿公寓方向弯曲的攀桂轩砖路","brick",garden.buffer(3.0,cap_style="flat"),.139)
    g.surface("攀桂轩环向浅草地","草皮浅色",Polygon(
        ((581,174),(622,165),(649,155),(662,154),(660,173),(642,179),(607,185))
    ).difference(garden.buffer(3.04)),.132)
    g.build()
    plant = Planting(scene)
    plant.group.name="公寓与运动区 · 树阵、菜株、圆篱"
    plant.palette["white"]=mats["white"]
    leaves=[]
    for x,y in ((653,151),(686,152),(718,151),(814,147),(856,147),(901,146),
                (924,151),(968,146),(994,152),(974,78),(941,79),(898,78),
                (849,78),(812,77),(708,77),(671,78),(563,170),(422,171),
                (393,170),(393,215),(315,241),(335,241),(354,241),(380,241),
                (302,108),(302,128),(302,148),(59,471),(82,476),(113,477),
                (146,476),(178,476),(210,476),(237,476),(266,477),(62,96),
                (95,93),(127,94),(163,92),(194,95)):
        tree(plant,(x,y),5.6+(x%6)*.32,"leaf",[],leaves)
    foliage_cards(plant.group,bpy.data.materials["三处庭院实拍 · 树叶"],
                  [(p,s*1.59,a) for p,s,a in leaves],"公寓与球场实拍树叶")
    for x,y in ((646,153),(687,151),(817,149),(899,149),(923,153),
                (977,153),(398,164),(401,231),(306,246),(328,245),(354,244)):
        center=world((x,y))
        for k in range(10):
            ang=k*2.39996
            offset=Vector((math.cos(ang)*.60,math.sin(ang)*.62,.39+k%4*.09))
            plant.crown("修剪绿篱","deep",center+offset,.46,.44,.47)
    for i,bed in enumerate(beds):
        left,top,right,bottom=bed.bounds
        item=site.zone("劳动基地种植支架",((left+right)/2,(top+bottom)/2))
        for dx in np.linspace(-2.46,2.46,11):
            for y in (-.56,.56):
                rod(item,"交叉竹架","wood",(dx,y,.15),(dx,-y*.28,1.63),.011,5)
                offset=item.point(dx,y,.30)
                plant.crown("地被灌木","leaf",offset,.23,.20,.19)
        rod(item,"竹架长横杆","wood",(-2.5,0,1.28),(2.5,0,1.28),.016,6)
        if i%3==0:
            item.box("绿色作物班牌柱","leaf",-2.2,.88,.32,.04,.042,.40)
            item.box("绿色作物班牌","leaf",-2.2,.91,.55,.41,.038,.21)
        item.finish()
    for a,b in zip(list(garden.coords),list(garden.coords)[1:]):
        item,span=segment(site,"攀桂轩 · 木架与长椅",a,b)
        for x in np.linspace(-span/2+.22,span/2-.22,max(2,round(span/1.9)+1)):
            for y in (-1.04,1.04):
                item.box("暖黄木廊柱","wood",x,y,1.48,.139,.144,2.68)
                item.box("木廊石基础","stone",x,y,.185,.235,.237,.157)
            item.box("木架横梁","wood",x,0,2.81,.114,2.45,.17)
        for y in (-1.0,1.0):
            item.box("木廊纵梁","wood",0,y,2.89,span,.12,.17)
        for x in np.linspace(-span/2+.12,span/2-.12,round(span/.26)):
            item.box("攀援植物木椽","wood",x,0,2.99,.065,2.43,.075)
        for z in (.58,.34):
            item.box("廊内沿线木坐凳","wood",0,-.84,z,span*.74,.25,.103)
        item.finish()
    label=site.zone("攀桂轩题字景石",(622,175))
    label.box("浅石底","stone",0,0,.394,1.53,.65,.56)
    panel(label,"实拍攀桂轩题字","攀桂轩刻石",0,-.331,.44,1.48,.57)
    label.finish()
    sign_materials = dict(mats,ochre=mats["yellow"])
    lighting = SiteDetails(scene,sign_materials)
    for xy in ((641,157),(853,151),(910,152),(974,79),(918,73),(835,73),(392,176),(391,229)):
        lamp=lighting.zone("公寓道路旗帜灯杆",xy)
        SiteDetails.lamp(lamp,0,0,True)
        lamp.finish()
    plant.finish()


def render_evidence(scene,cameras):
    scene.render.resolution_percentage=100
    scene.render.engine="CYCLES"
    scene.cycles.samples=14
    scene.cycles.use_denoising=True
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",20)
    for tag,sid,heading,*_ in VIEWS:
        scene.camera=cameras[tag]
        scene.render.resolution_x,scene.render.resolution_y=(770,770) if sid else (1290,930)
        path=OUT/"模型视角"/(tag+".png")
        scene.render.filepath=str(path)
        bpy.ops.render.render(write_still=True)
        if not sid:
            continue
        with Image.open(reference(sid,heading)) as photo, Image.open(path) as render:
            canvas=Image.new("RGB",(1564,845),"#ebe9df")
            draw=ImageDraw.Draw(canvas)
            draw.text((8,10),tag[3:],fill="#202822",font=font)
            draw.text((8,42),f"实景全景 {sid}/{heading}°",fill="#202822",font=font)
            draw.text((786,42),"Blender视角（站位按航拍及实景估算）",fill="#202822",font=font)
            canvas.paste(photo.convert("RGB").resize((770,770),Image.Resampling.LANCZOS),(8,69))
            canvas.paste(render.convert("RGB"),(786,69))
            canvas.save(OUT/"实景对照"/(tag+".jpg"),quality=94)


def main():
    for folder in ("模型视角","实景对照","实拍贴图"):
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    original=set(scene.objects.keys())
    removed=remove_previous(scene)
    mats=materials()
    site=SiteDetails(scene,mats)
    dormitories(scene,site,mats)
    football(scene,site,mats)
    basketball(scene,site,mats)
    grandstand(site)
    ping_pong(scene,site,mats)
    site_landscape(scene,site,mats)
    meshes=[obj for obj in scene.objects if obj.type=="MESH" and obj.name not in original.difference(removed)]
    unwrap_textured_boxes(meshes)
    clean_generated_meshes(meshes)
    for obj in meshes:
        assert all(math.isfinite(v) for vertex in obj.data.vertices for v in vertex.co),obj.name
        assert all(face.area>=1e-9 for face in obj.data.polygons),obj.name
        if any(m and m.name.startswith("公寓与运动区实拍") for m in obj.data.materials):
            assert obj.data.uv_layers,obj.name
    cameras = {tag:camera(scene,tag,eye,target,aim,lens,height)
               for tag,_,_,eye,target,aim,lens,height in VIEWS}
    scene.camera=cameras["10_运动区俯瞰"]
    scene.render.resolution_x,scene.render.resolution_y=1290,930
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB",
                             export_cameras=False,export_lights=False)
    record={"源文件":str(SOURCE),"新增网格":len(meshes),"替换对象":removed,
            "足球场像素范围":PITCH,"篮球场像素范围":COURTS,"看台航拍描线":STAND,
            "公寓路像素描线":COURTYARD,"相机":VIEWS,"实拍贴图取样":CROPS,
            "说明":"楼高、入口精确位置、坡道、看台排数和分段、球架和球台数量按全景及航拍估算；本轮覆盖室外。"}
    (OUT/"定位与验收.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    render_evidence(scene,cameras)


if __name__=="__main__":
    main()
