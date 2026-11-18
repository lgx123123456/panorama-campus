"""Refine the B15 end, C2 garden walk, and field-facing grandstand."""

import json
import math
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import LineString, Polygon

from 三处庭院实拍细化 import foliage_cards, panel, unwrap_textured_boxes
from 公寓与运动区实拍细化 import STAND, front_panel, rod, segment
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 图书馆照片还原 import CAL, material, open_campus, world
from 地面街道实景细化 import Ground
from 尚德广场实拍细化 import photo_material
from 楼间过道实拍细化 import camera, clean_generated_meshes


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/西门至孔德广场沿线实拍细化/校园室外_西门至孔德广场.blend"
OUT = ROOT / "成果/致远楼林荫步道与看台"
STEM = "校园室外_致远楼林荫步道与看台"
PHOTOS = Path("D:/缓存/wexin/xwechat_files/wxid_6bn0wgbigo1j22_1400/temp/RWTemp/2026-11/9e20f478899dc29eb19741386f9343c8")
FILES = ("567d2f97dbc8e48835bb73dcf920e39f.jpg", "d03efa12cbb29246238c6d5feb42beec.jpg",
         "53f08b88782665835b05a8e17ff40dab.jpg", "1d74e9598959dbd753e2ae3d6012550c.jpg")
CROPS = ((0, 808, 1280, 1988), (0, 925, 1280, 1882), None, None)
PLAQUE = ((1183, 904), (1443, 890), (1458, 998), (1194, 1034))
SCALE = CAL["metres_per_pixel"]
WALK = ((546, 290), (574, 288), (606, 287), (630, 289), (652, 289), (678, 287),
        (699, 289), (721, 307))
VIEWS = (
    ("01_林荫步道", (638, 289), (710, 297), 2.62, 23, 1.67),
    ("02_跑道看主席台", (255, 248), (274, 296), 5.05, 22, 1.65),
    ("03_致远楼及两侧衔接", (738, 283), (698, 251), 7.6, 25, 1.64),
    ("04_致远楼近景", (720, 269), (701, 251), 8.5, 19, 1.64),
    ("05_区域鸟瞰", (847, 654), (541, 276), .8, 37, 225),
)


def remove_collection(name):
    collection = bpy.data.collections[name]
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def materials():
    colors = {
        "cream": (.72, .66, .53), "beam": (.25, .146, .112), "terracotta": (.49, .109, .038),
        "shade": (.07, .075, .072), "frame": (.091, .110, .119), "glass": (.18, .31, .40),
        "deep_glass": (.086, .154, .194), "silver": (.53, .56, .56), "warm": (.50, .38, .23),
        "stone": (.36, .34, .30), "blue": (.021, .16, .38), "grate": (.043, .158, .107),
        "lamp": (.037, .042, .034), "diffuser": (.63, .60, .43), "roof_blue": (.105, .27, .43),
        "under": (.235, .255, .264), "truss": (.15, .153, .14), "red": (.43, .088, .062),
        "field_wall": (.035, .184, .048), "stage_white": (.76, .74, .66),
    }
    mats = {key: material("致远与看台 · " + key, rgb, .74) for key, rgb in colors.items()}
    for key in ("deep_glass", "glass"):
        shader = mats[key].node_tree.nodes["Principled BSDF"]
        shader.inputs["Roughness"].default_value = .23
        shader.inputs["Coat Weight"].default_value = .45
    mats["sign"] = bpy.data.materials["公寓与运动区实拍 · 主席台校训"]
    with Image.open(PHOTOS / FILES[3]) as photo:
        source = np.asarray(photo.convert("RGB"))
    width, height = 704, 280
    matrix = cv2.getPerspectiveTransform(np.float32(PLAQUE), np.float32(
        ((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1))))
    plaque = cv2.warpPerspective(source, matrix, (width, height))
    path = OUT / "实拍贴图" / "致远楼首层展板.jpg"
    Image.fromarray(plaque).save(path, quality=96)
    image = bpy.data.images.load(str(path))
    image.pack()
    mats["plaque"] = photo_material("致远楼首层展板", image, (.54, .58, .58), .83)
    return mats


def guard(item, start, end, z, height=.92, pitch=.145):
    ax, ay = start
    bx, by = end
    for offset, radius in ((.12, .022), (height, .031)):
        rod(item, "银色栏杆扶手", "silver", (ax, ay, z+offset), (bx, by, z+offset), radius)
    count = max(1, round(math.dist(start, end)/pitch))
    for i in range(count+1):
        t = i/count
        x, y = ax+(bx-ax)*t, ay+(by-ay)*t
        rod(item, "银色栏杆竖条", "silver", (x, y, z), (x, y, z+height), .013 if i%7 else .025, 6)


def glazing(item, x, y, z, width, height, nx, nz, tint="glass"):
    b = item.box
    dx, dz = width/nx, height/nz
    b("窗洞暗色框衬", "frame", x, y+.031, z, width+.11, .15, height+.11)
    for i in range(nx):
        for j in range(nz):
            key = "deep_glass" if (i+2*j)%7==0 else tint
            b("分格蓝灰玻璃", key, x-width/2+(i+.5)*dx, y-.055,
              z-height/2+(j+.5)*dz, dx-.047, .048, dz-.051)


def tower(site):
    item = site.zone("B15 致远楼 · 白色端框、玻璃与外廊", (699, 245))
    item.collection["照片校对"] = "用户提供第3、4张。B15沿用母版位置，楼名采用用户本轮确认的致远楼。"
    b = item.box
    b("退进的塔楼围护内墙", "cream", -1.22, 1.20, 10.11, 8.97, 11.95, 20.15)
    b("梯间背面窗暗衬", "shade", 2.30, 1.05, 10.11, 5.80, 10.10, 20.10)
    b("橙红退台屋顶机械间", "terracotta", .37, -.75, 21.25, 10.40, 10.82, 2.43)
    b("顶层浅色厚檐", "cream", 0, 0, 19.94, 11.86, 14.62, .86)
    b("端框西边墩", "cream", -5.54, -.10, 11.71, .66, 14.29, 16.40)
    b("端框东角通高浅墙柱", "cream", 5.50, -6.89, 11.47, .65, .77, 16.91)
    b("东端通高窄墙肢", "cream", 5.61, -3.25, 11.54, .48, 1.22, 16.82)
    b("东端斜向可见的后侧墙肢", "cream", 5.56, 6.35, 11.57, .53, 1.75, 16.77)
    b("通高褐色幕墙中柱", "beam", .14, -7.04, 11.42, .47, .34, 16.00)
    b("褐色幕墙外边柱", "beam", -5.13, -7.02, 11.42, .36, .33, 16.00)
    for level in range(4):
        floor = 3.97+level*3.91
        b("围廊及折返梯平台", "cream", 1.42, -3.75, floor-.16, 8.70, 7.35, .34)
        b("各层褐色横梁", "beam", .07, -7.22, floor-.14, 10.55, .42, .45)
        b("外廊内侧橙红墙", "terracotta", 3.07, -4.15, floor+1.60, 4.26, .32, 3.30)
        b("横窗下浅色实墙", "cream", 5.62, 1.48, floor+.43, .48, 8.23, .85)
        b("横窗上浅色实墙", "cream", 5.62, 1.48, floor+3.20, .48, 8.23, .88)
        if level:
            b("短侧双狭缝间浅墙", "cream", 5.62, 1.48, floor+1.79, .48, 8.23, .73)
            for z in (floor+1.14, floor+2.46):
                b("深退的条形窗玻璃", "deep_glass", 5.23, 1.48, z, .064, 7.60, .53)
        else:
            b("东侧大开口边的浅色墙面", "cream", 5.62, -.76, floor+1.88, .48, 3.76, 2.15)
            b("低层东侧开敞红橙退深墙", "terracotta", 4.88, 1.11, floor+1.65, .15, 6.83, 2.76)
            guard(item, (5.59,1.15), (5.59,5.54), floor+.40)
        rod(item, "外廊暖灰圆柱", "warm", (4.51, -6.60, floor), (4.51, -6.60, floor+3.32), .142, 14)
        glazing(item, -2.48, -7.04, floor+1.66, 4.73, 3.04, 5, 3)
        guard(item, (.48, -7.15), (5.15, -7.15), floor)
        guard(item, (5.69, -6.46), (5.69, -3.85), floor)
    b("浅色外挑底梁", "cream", 0, -7.09, 3.66, 11.86, .53, .63)
    b("首层灰褐承柱", "beam", 1.12, -6.84, 1.80, .58, .65, 3.53)
    b("基座东侧橙红门面", "terracotta", 4.67, .03, 1.81, 1.08, 11.90, 3.46)
    b("橙红凹面双扇门", "terracotta", 5.233, -4.85, 1.43, .055, 3.20, 2.61)
    for y in (-5.03, -4.68):
        b("东侧橙红门拉手", "frame", 5.29, y, 1.38, .050, .060, .28)
    glazing(item, -2.92, -6.62, 1.91, 4.16, 3.10, 4, 2, "deep_glass")
    glazing(item, 2.11, -6.77, 1.80, 2.33, 3.12, 2, 2, "deep_glass")
    for x in (-3.96, -2.94):
        b("入口玻璃门蓝色横条", "blue", x, -6.76, 1.32, .92, .026, .083)
        b("入口玻璃门立拉手", "silver", x+.36, -6.80, 1.31, .032, .055, .46)
    b("玻璃入口灰色门槛", "stone", -2.92, -7.13, .15, 4.40, 1.22, .14)
    for x in (1.88, 2.55, 3.22):
        b("首层蓝色垃圾桶", "blue", x, -6.67, .51, .55, .62, .74)
        b("蓝桶翻盖", "blue", x, -6.69, .90, .59, .65, .12)
    b("东侧低矮展板及白石基座", "cream", 5.42, 2.64, .82, .32, 7.36, 1.52)
    corners = [item.point(5.589, y, z) for y,z in ((-.80,.66),(6.11,.66),(6.11,2.47),(-.80,2.47))]
    plaque = item.link("实拍蓝白展板", corners, [(0,1,2,3)], item.materials["plaque"])
    layer = plaque.data.uv_layers.new()
    for loop in plaque.data.loops:
        layer.data[loop.index].uv = ((0,0),(1,0),(1,1),(0,1))[loop.vertex_index]
    item.finish()

    flank, length = segment(site, "B15 致远楼 · 临庭院浅色翼墙", (651, 261.45), (686.55, 261.22))
    flank.box("浅色长墙板", "cream", 0, -.015, 11.88, length, .31, 15.97)
    flank.box("楼翼挑出檐线", "cream", 0, -.17, 19.59, length, .72, .43)
    for x in np.linspace(-length*.39, length*.39, 5):
        for floor in range(4):
            glazing(flank, float(x), -.21, 5.79+floor*3.90, 1.67, 2.17, 2, 2)
    flank.finish()
    bridge_endpoint(site)


def bridge_endpoint(site):
    # The join is hidden by the tower in the aerial; the ground photo places it beside the glazing.
    origin = world((699,260))
    south = (world((699,261))-origin).normalized()
    west = (world((698,260))-origin).normalized()
    for name in ("A03 连廊连续楼板与屋面", "A03 思远楼与志远楼封闭连廊 1",
                 "A03 思远楼与志远楼封闭连廊 2"):
        for obj in bpy.data.collections[name].objects:
            label = obj.name.removeprefix("B15–21 ").removeprefix("B场地 ")
            if label.startswith(("黄色层间边梁", "连续深灰包边檐带", "桥下方形柱与石脚")):
                obj.data.materials[0] = site.materials["cream"]
            matrix = obj.matrix_world
            local_west = matrix.to_3x3().inverted() @ west
            for point in obj.data.vertices:
                position = matrix @ point.co
                distance = (position-origin).dot(south)/SCALE
                offset = max(0,min(1,(38-distance)/32))*9.5*SCALE
                point.co += offset*local_west
            obj.data.update()


def branching_tree(plant, pixel, height, cards, bare=False):
    rng = plant.rng
    ground = world(pixel)+Vector((0, 0, .16))
    fork = ground+Vector((rng.uniform(-.23,.23), rng.uniform(-.27,.27), height*.42))
    plant.limb("乔木主干与斜枝", "lightbark", ground, fork, height*.025, height*.014)
    for i in range(7):
        angle = i*2.39996 + rng.uniform(-.32, .32)
        u = Vector((math.cos(angle), math.sin(angle), 0))
        elbow = fork + u*(height*rng.uniform(.105,.159)) + Vector((0,0,height*.12))
        end = elbow + u*(height*rng.uniform(.08,.17)) + Vector((0,0,height*rng.uniform(.15,.31)))
        plant.limb("乔木主干与斜枝", "lightbark", fork, elbow, height*.012, height*.007)
        plant.limb("乔木主干与斜枝", "lightbark", elbow, end, height*.007, height*.003)
        for _ in range(7):
            tip = end+Vector((rng.uniform(-1.17,1.17),rng.uniform(-1.17,1.17),rng.uniform(.12,1.42)))
            plant.limb("冠上细枝", "bark", end, tip, .026, .004)
            if bare:
                for j in range(3):
                    twig = tip+Vector((rng.uniform(-.45,.45),rng.uniform(-.45,.45),rng.uniform(.15,.60)))
                    plant.limb("冬季细梢", "bark", tip, twig, .005, .0018)
                    if j==0:
                        plant.crown("枝梢残留褐叶", "dry", twig, .086, .055, .047)
                continue
            for _ in range(9):
                center = tip+Vector((rng.uniform(-.72,.72),rng.uniform(-.72,.72),rng.uniform(-.73,.51)))
                key = rng.choice(("green","green","light"))
                cards[key].append((center, rng.uniform(.19,.42), rng.random()*math.tau))


def courtyard(scene, site):
    plant = Planting(scene)
    plant.group.name = "C2 致远楼至思远楼 · 林荫步道"
    plant.palette["dry"] = material("冬季枝梢残留褐叶",(.182,.081,.040),.95)
    center = LineString(WALK)
    g = Ground.__new__(Ground)
    g.scene, g.batches = scene, {}
    g.materials = {"walk": bpy.data.materials.get("人行步道 · 红灰错缝砖")
                   or site.materials["stone"]}
    g.region("C2 林荫步道砖铺与致远楼入口前地坪")
    g.surface("连通两端的林下砖路", "walk", center.buffer(1.57/SCALE, cap_style="flat"), .158)
    trees = ((723, 264), (731, 253))
    apron = Polygon(((711,251),(733,250),(740,272),(725,280),(712,273)))
    for x, y in trees:
        apron = apron.difference(Polygon(((x-1.1,y-1.1),(x+1.1,y-1.1),(x+1.1,y+1.1),(x-1.1,y+1.1))))
    g.materials["concrete"] = bpy.data.materials.get("校内车道 · 浅灰混凝土") or site.materials["cream"]
    g.surface("致远楼端部浅灰混凝土", "concrete", apron, .167)
    g.build()
    cards = {"green": [], "light": []}
    for side in (-1, 1):
        row = center.offset_curve(side*6.25)
        for i in range(14):
            p = row.interpolate(6+i*11.25+(3 if side==1 else 0)+plant.rng.uniform(-1.8,1.8))
            branching_tree(plant, (p.x,p.y), 7.4+.52*((i+side)%4), cards)
        for s0,s1 in ((9,48),(53,96),(104,141),(146,169)):
            offset = center.offset_curve(side*4.47)
            hedge = [offset.interpolate(s) for s in np.linspace(s0,s1,7)]
            plant.hedge([(p.x,p.y) for p in hedge], .42)
        for distance in (16, 47, 77, 110, 145):
            p = row.interpolate(distance+(8 if side==1 else 0))
            lamp = site.zone("C2 黑色小路庭院灯", (p.x,p.y))
            rod(lamp,"园灯细立柱","lamp",(0,0,.16),(0,0,2.23),.043,12)
            rod(lamp,"园灯柱脚","lamp",(0,0,.16),(0,0,.45),.085,12)
            for z, radius in ((2.23,.115),(2.29,.146),(2.35,.169)):
                rod(lamp,"上宽下窄暗色灯托","lamp",(0,0,z-.032),(0,0,z+.032),radius,10)
            rod(lamp,"灯罩磨砂面","diffuser",(0,0,2.38),(0,0,2.49),.156,10)
            rod(lamp,"遮雨上盖","lamp",(0,0,2.50),(0,0,2.56),.191,10)
            lamp.finish()
    for i, point in enumerate(trees):
        branching_tree(plant, point, 8.1+i*.71, cards, bare=True)
        grate = site.zone("致远楼前方形绿色树池格栅", point)
        grate.box("树池内回填深色土","stone",0,0,.085,1.04,1.04,.10)
        for o in np.linspace(-.49,.49,21):
            grate.box("绿色格栅横条","grate",0,o,.161,1.06,.021,.031)
            grate.box("绿色格栅竖条","grate",o,0,.162,.021,1.06,.032)
        grate.finish()
    for key, positions in cards.items():
        name = "绿叶簇" if key=="green" else "浅绿叶簇"
        foliage_cards(plant.group, bpy.data.materials["孔德广场实拍 · "+name], positions, "林荫树冠 · "+name)
    plant.finish()
    for obj in plant.group.objects:
        if obj.name.startswith(("乔木主干与斜枝","冠上细枝","冬季细梢")):
            for face in obj.data.polygons:
                face.use_smooth = len(face.vertices)==4


def bleacher_sections():
    rim = [(x-9.1,y) for x,y in STAND]
    for a,b in zip(rim,rim[1:]):
        n = max(1,round(math.dist(a,b)/17))
        for i in range(n):
            yield tuple(tuple(p+(q-p)*t/n for p,q in zip(a,b)) for t in (i,i+1))


def grandstand(site):
    item, span = segment(site, "操场主席台 · 钢桁架蓝棚、校训墙与红台阶", (275,326), (274,260))
    opening = 6.9
    opening_world = item.point(opening,0,0)
    for i,(a,c) in enumerate(bleacher_sections(), 1):
        rail,length = segment(site,"看台跑道侧栏杆与腰墙",c,a)
        collection = bpy.data.collections[f"运动场看台 · 第{i:02d}段"]
        if 10 <= i <= 13:
            for obj in list(collection.objects):
                if obj.name.removeprefix("B场地 ").startswith(
                        ("逐级看台踏板","红白蓝","楼梯半级踏步","黄色安全沿","看台后弧形深红横梁")):
                    bpy.data.objects.remove(obj,do_unlink=True)
        r = (opening_world-rail.anchor).dot(rail.across)
        low, high = r-.94, r+.94
        bounds = [(-length/2,length/2)]
        if high > -length/2 and low < length/2:
            for obj in list(collection.objects):
                if obj.name.removeprefix("B场地 ").startswith("球场侧绿腰墙"):
                    bpy.data.objects.remove(obj,do_unlink=True)
            bounds = [(-length/2,min(low,length/2)),(max(high,-length/2),length/2)]
            for x1,x2 in bounds:
                if x2-x1>.04:
                    rail.box("检修入口两侧绿色墙","field_wall",(x1+x2)/2,.17,.50,x2-x1,.30,.84)
        for x1,x2 in bounds:
            if x2-x1>.04:
                guard(rail,(x1+.01,.17),(x2-.01,.17),.93,.67,.28)
        rail.finish()
    # The field-side toe is several metres ahead of the canopy centreline.
    canopy_anchor = item.anchor.copy()
    item.anchor += item.depth*3.05
    b = item.box
    for side in (-1,1):
        width = span*.113+.32
        for step in range(9):
            z = .31*(step+1)
            key = "stage_white" if 3<=step<6 else "blue" if step<3 else "red"
            b("主席台两翼蓝白红座阶",key,side*(span*.385+width/2),-.85-step*.51,
              .09+z/2,width,.55,z)
    for step in range(8):
        z = .31*(step+1)
        b("主席台面向跑道的红色长台阶","red",-.20,-.83-step*.49,
          .10+z/2,span*.77,.55,z)
    for step in range(5):
        z = .171*(step+1)
        b("绿漆台口下跑道踏步","field_wall",opening,1.75-step*.36,.07+z/2,1.86,.38,z)
    b("梯口与红看台之间的踏步平台","red",opening,-.80,.506,1.86,1.92,.838)
    for x in (opening-.90, opening+.90):
        rod(item,"绿色台口下行扶手","silver",(x,1.93,.80),(x,.055,1.61),.028)
        for j in range(4):
            y = 1.76-j*.52
            z = .17+j*.213
            rod(item,"台口斜扶手支柱","silver",(x,y,z),(x,y,z+.73),.023)
    b("白色校训主席台房","stage_white",-.57,-3.51,3.79,span*.53,3.31,3.20)
    b("白色校训房压顶","stage_white",-.57,-3.53,5.41,span*.54,3.45,.20)
    front_panel(item,"实拍校训与中央校徽","sign",-.58,-1.836,3.93,span*.504,1.90)
    x = -.56+span*.265+.02
    b("主席台侧面深色门洞","shade",x,-2.62,3.38,.033,1.10,1.93)
    b("主席台侧门金属框","frame",x+.032,-3.21,3.38,.064,.061,1.99)
    for side in (-1,1):
        u = side*span*.435
        for step in range(12):
            z = .157*(step+1)
            b("主席台两翼砖红踏步","red",u,-.67-step*.348,z/2+.10,1.65,.36,z)
        rod(item,"看台阶梯银色斜扶手","silver",(u+.77,-.53,1.02),(u+.77,-4.85,3.58),.029)
        for j in range(5):
            y = -.55-j*1.06
            z = .20+j*.635
            rod(item,"两翼楼梯扶手立杆","silver",(u+.77,y,z),(u+.77,y,z+.85),.025)
    item.anchor = canopy_anchor
    width = span+1.28
    for x in np.linspace(-width*.45,width*.45,5):
        b("浅灰棚架后排柱","stage_white",x,-5.91,4.21,.36,.46,8.38)
    b("后排柱顶连续承梁","truss",0,-5.91,8.33,width-.24,.29,.37)
    b("蓝色压型金属整片屋面","roof_blue",0,-.58,9.08,width,11.43,.117)
    b("可见灰色压型板底","under",0,-.58,8.999,width,11.43,.047)
    for x in np.linspace(-width/2+.10,width/2-.10,120):
        b("蓝色薄屋面连续压型肋","roof_blue",x,-.58,9.157,.053,11.43,.071)
    for y in np.linspace(-6.17,5.00,14):
        b("压型板下连续横向檩条","truss",0,y,8.89,width,.083,.134)
    for x in np.linspace(-width/2+.11,width/2-.11,10):
        for z,r in ((8.79,.058),(8.12,.047)):
            rod(item,"钢桁架上下弦","truss",(x,-6.17,z),(x,5,z),r)
        for j in range(8):
            y = -6.17+j*11.17/8
            mid, end = y+11.17/16, y+11.17/8
            rod(item,"钢桁架三角腹杆","truss",(x,y,8.76),(x,mid,8.14),.029)
            rod(item,"钢桁架三角腹杆","truss",(x,mid,8.14),(x,end,8.76),.029)
    for z in (8.14, 8.86):
        rod(item,"前檐可见钢桁架弦杆","truss",(-width/2,5,z),(width/2,5,z),.058)
    for i in range(20):
        x = -width/2+i*width/20
        rod(item,"前檐桁架三角腹杆","truss",(x,5,8.85),(x+width/40,5,8.15),.027)
        rod(item,"前檐桁架三角腹杆","truss",(x+width/40,5,8.15),(x+width/20,5,8.85),.027)
    item.finish()


def render(scene, views):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 14
    scene.cycles.use_denoising = True
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    light = bpy.data.lights.new("林下对照漫射补光","AREA")
    light.energy, light.shape, light.size = 2050, "DISK", 7.0
    lamp = bpy.data.objects.new(light.name,light)
    scene.collection.objects.link(lamp)
    lamp.location = world((638,294))+Vector((0,0,5.6))
    lamp.rotation_euler = (world((657,285))+Vector((0,0,1.2))-lamp.location).to_track_quat("-Z","Y").to_euler()
    for i,(label,*_) in enumerate(VIEWS):
        lamp.hide_render = i!=0
        scene.camera = views[label]
        size = (1440, 930) if i==4 else (900, 720)
        scene.render.resolution_x,scene.render.resolution_y = size
        path = OUT/"模型视角"/(label+".png")
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        if i==4:
            continue
        canvas = Image.new("RGB",(1828,783),"#eceae0")
        draw = ImageDraw.Draw(canvas)
        draw.text((9,6),label[3:],font=font,fill="#24322b")
        draw.text((9,33),"实拍参考",font=font,fill="#24322b")
        draw.text((919,33),"Blender 模型视角（机位估算）",font=font,fill="#24322b")
        with Image.open(PHOTOS/FILES[i]) as source, Image.open(path) as model:
            source = source.convert("RGB")
            if CROPS[i]:
                source = source.crop(CROPS[i])
            for x,image in ((9,source),(919,model.convert("RGB"))):
                inset = ImageOps.contain(image,size)
                canvas.paste(inset,(x+(size[0]-inset.width)//2,59+(size[1]-inset.height)//2))
        canvas.save(OUT/"实景对照"/(label+".jpg"),quality=94)


def main():
    for folder in ("实拍贴图","模型视角","实景对照"):
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    open_campus(SOURCE)
    scene = bpy.context.scene
    remove_collection("B15 东端楼梯塔楼与高侧窗")
    remove_collection("C2 庭院分层乔灌木")
    remove_collection("运动场主席台与校训雨棚")
    before = set(scene.objects.keys())
    site = SiteDetails(scene, materials())
    tower(site)
    courtyard(scene,site)
    grandstand(site)
    new = [obj for obj in scene.objects if obj.type=="MESH" and obj.name not in before]
    unwrap_textured_boxes(new)
    clean_generated_meshes(new)
    for obj in new:
        assert all(math.isfinite(v) for point in obj.data.vertices for v in point.co), obj.name
        assert all(face.area>=1e-9 for face in obj.data.polygons), obj.name
    views = {label: camera(scene,label,eye,target,aim,lens,z) for label,eye,target,aim,lens,z in VIEWS}
    scene.camera = views[VIEWS[0][0]]
    scene.render.resolution_x,scene.render.resolution_y = 900,720
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB",export_cameras=False,export_lights=False)
    record = {
        "续作母版": str(SOURCE), "实拍": [str(PHOTOS/file) for file in FILES],
        "模型编号": "B15 致远楼（部分历史文件标作志远楼）；C2 致远楼与思远楼之间；操场主席台",
        "步道中心线": WALK, "看台与主席台": STAND, "展板取样四点": PLAQUE,
        "A03 连廊": "依致远楼入口照片，将航拍阴影里的桥头向西调整约4米，至连廊中段渐回原线。",
        "相机参数": VIEWS, "新增网格": len(new),
        "估算项": "步道宽度、树位、照片遮挡处的立面、端部窗格、连廊细部、看台阶高与雨棚跨度。",
    }
    (OUT/"定位与来源.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    render(scene,views)


if __name__=="__main__":
    main()
