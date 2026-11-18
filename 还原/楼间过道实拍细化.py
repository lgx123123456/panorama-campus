"""Rebuild outdoor connections from the orthographic map and ground panoramas."""

import json
import math
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

from 四栋教学楼实景细化 import reference
from 地面街道实景细化 import Ground
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 尚德广场实拍细化 import photo_material


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/尚德至图书馆实拍细化/校园室外_尚德至图书馆细化.blend"
OUT = ROOT / "成果/楼间过道实拍细化"
SCALE = CAL["metres_per_pixel"]
TOUR = "https://www.720yun.com/t/84vkb78yz8w"
ROUND_CENTER = (906, 190)
ROUND_RADIUS = 5.8
SAMPLES = {
    # Quadrilaterals are measured on 500-pixel proxies of the original direction views.
    "樱花园红绿联锁砖": ("06", "135", ((130,378),(290,379),(311,498),(21,498)), 1.62),
    "教学石板": ("45", "270", ((153,354),(263,354),(290,492),(92,492)), 2.35),
    "行远楼门前灰石板": ("36", "270", ((246,365),(345,361),(414,480),(229,485)), 2.40),
    "餐厅浅色混凝土": ("22", "270", ((254,347),(358,342),(408,475),(204,483)), 2.84),
    "图书馆北侧细纹混凝土": ("28", "180", ((135,326),(273,332),(309,472),(67,451)), 2.81),
    "公寓北侧暖灰混凝土": ("14", "270", ((278,352),(387,355),(461,470),(209,465)), 2.55),
    "桥头深灰饰面": ("06", "135", ((198,143),(243,147),(243,237),(198,237)), .86),
    "节气围墙彩绘": ("14", "180", ((231,192),(373,192),(384,301),(232,301)), 1.0),
}
ROUND_STRIPS = {
    # Curved glass boundaries measured on the 1400-pixel scene-28 direction view.
    "圆弧首层玻璃窗帘": {
        "x": (171,255,400,580,750,920,1069),
        "top": (563,543,525,516,519,537,560),
        "bottom": (749,763,776,781,776,766,754),
    },
    "圆弧二层玻璃窗帘": {
        "x": (171,255,400,580,750,920,1069),
        "top": (294,245,198,169,175,214,278),
        "bottom": (442,405,371,352,360,385,427),
    },
}

# Each centerline is traced in the reprojected aerial image, in route order.
# Narrow urban service paths without a nearby ground viewpoint retain an aerial-only status.
ROUTES = (
    ("A01","体育馆—艺远楼与识远楼西翼",((595,481),(592,440),(591,409),(579,380),(551,359)),3.35,
        "公寓北侧暖灰混凝土","02 / 07","航拍定位，体育馆侧出入口待图"),
    ("A02","靠大门西翼—思远楼（樱花园）",((607,391),(644,386),(678,386),(711,380),(746,373),(778,368)),5.15,
        "樱花园红绿联锁砖","06/090,135,270 / 40/045","楼栋关系经用户确认"),
    ("A03","思远楼—志远楼",((518,291),(546,288),(602,291),(657,291),(700,301),(729,294),(771,286)),4.05,
        "樱花园红绿联锁砖","06/270 / 15/315 / 21/135","庭院路径依航拍，路端细节见全景"),
    ("A04","志远楼—图书馆西侧",((688,240),(699,220),(718,200),(737,187),(753,179)),4.95,
        "教学石板","01 / 02 / 32/045,090","弧廊位置依航拍，门洞与内部待图"),
    ("A05","主轴东翼—知远楼",((876,416),(878,401),(877,380),(874,355)),5.45,
        "教学石板","40/315 / 45/270","灰檐玻璃廊、黄梁和低绿篱见全景"),
    ("A06","知远楼—行远楼",((874,327),(875,315),(876,294),(874,277),(877,265)),5.85,
        "行远楼门前灰石板","36/225,270 / 45/315","沿用原标语贴图，补柱间通道和侧院"),
    ("A07","行远楼—图书馆东侧",((882,231),(895,214),(915,214),(933,210),(929,194),(927,177),(913,168),(892,170)),4.85,
        "行远楼门前灰石板","32/315 / 02","黄梁连接可见，弧度和桥下走线按航拍估算"),
    ("A08","理科楼外侧—东侧花园",((956,446),(979,418),(995,391),(1006,362),(1009,326),(1001,293),
        (988,263),(972,233),(949,207),(915,181),(889,168)),2.75,
        "教学石板","01 / 02 / 32/315","航拍可见弧形路径，林下段落按航拍估算"),
    ("A09","篮球场—餐厅—绅远楼",((389,175),(438,175),(485,176),(534,175),(578,175),(616,169),(665,166)),6.35,
        "餐厅浅色混凝土","22/090,270 / 24/270 / 25/180","浅混凝土路、短划线和路边方花池"),
    ("A10","绅远楼—蕙远楼—图书馆背面",((654,167),(706,164),(754,156),(789,151),(835,149),(877,149),
        (922,158),(973,160),(1033,153)),5.70,
        "图书馆北侧细纹混凝土","25/180 / 28/090,180,225","公寓门前坡道、井盖与花池；圆弧玻璃建筑经用户确认为图书馆右侧"),
    ("A11","公寓北侧—劳动课程基地",((577,73),(655,72),(727,72),(794,72),(871,72),(947,72),(1015,74),
        (1031,94),(1035,130),(1033,154)),3.6,
        "公寓北侧暖灰混凝土","14/045,225,270 / 02","混凝土路、墙侧砖道和种植畦"),
    ("A12","孔德广场—志远楼与思远楼西端",((435,323),(473,329),(502,320),(525,302),(541,295),(551,320),(565,365),(594,386)),
        3.3,"樱花园红绿联锁砖","07 / 15/135,270 / 21/090,135","沿路树池与木廊，砖道接入樱花园"),
    ("A13","绅远楼—蕙远楼楼间支路",((781,74),(782,105),(783,126),(782,143),(784,152)),2.05,
        "图书馆北侧细纹混凝土","02 / 25/045 / 28/225","两楼间支路按航拍描边，沿路出入口待核"),
    ("A14","餐厅—绅远楼楼间支路",((573,88),(573,111),(573,140),(576,158),(578,175)),2.65,
        "餐厅浅色混凝土","02 / 24/270 / 25/180","楼间狭长支路按航拍定位，侧门待核"),
)

VIEWS = (
    ("cherry","A02","06","135",(697,384),(748,382),3.20,19),
    ("west","A02","06","270",(719,383),(607,383),2.1,19),
    ("librarywest","A04","32","045",(797,253),(729,197),2.9,19),
    ("eastsouth","A05","45","270",(825,376),(880,382),4.15,20),
    ("eastnorth","A06","36","270",(823,296),(878,297),4.18,20),
    ("libraryeast","A07","32","315",(820,253),(902,215),3.62,19),
    ("canteen","A09","22","270",(483,175),(631,169),2.75,19),
    ("libraryround","A10","28","180",(906,163),ROUND_CENTER,3.62,18),
    ("garden","A11","14","270",(947,72),(767,72),2.35,20),
)


def photo_materials():
    materials = {}
    for name,(sid,angle,quad,period) in SAMPLES.items():
        path = reference(sid,angle)
        with Image.open(path) as picture:
            pixels = np.asarray(picture.convert("RGB"))
        points = np.float32(quad)*np.float32((pixels.shape[1]/500,pixels.shape[0]/500))
        size = 512
        target = np.float32(((0,0),(size-1,0),(size-1,size-1),(0,size-1)))
        crop = cv2.warpPerspective(pixels,cv2.getPerspectiveTransform(points,target),(size,size),
                                   flags=cv2.INTER_CUBIC)
        if name not in {"桥头深灰饰面","节气围墙彩绘"}:
            low = cv2.GaussianBlur(crop.astype(np.float32),(0,0),43)
            normalized = crop+(.63*(np.median(low,axis=(0,1))-low))
            crop = np.clip(normalized,0,255).astype(np.uint8)
        texture = OUT/"实拍贴图"/(name+".png")
        Image.fromarray(crop).save(texture)
        image = bpy.data.images.load(str(texture))
        image.pack()
        mat = photo_material(name,image,(.33,.32,.30),.87,period)
        mat.name = "楼间过道实拍 · "+name
        mat["原图"] = path.relative_to(ROOT.parent).as_posix()
        materials[name] = mat
    path = reference("28","180")
    with Image.open(path) as picture:
        pixels = np.asarray(picture.convert("RGB"))
    for name,control in ROUND_STRIPS.items():
        xs = np.linspace(control["x"][0],control["x"][-1],1280)
        tops = np.interp(xs,control["x"],control["top"])
        bottoms = np.interp(xs,control["x"],control["bottom"])
        fraction = np.linspace(0,1,384)[:,None]
        map_x = np.broadcast_to(xs,(384,1280))*pixels.shape[1]/1400
        map_y = (tops+(bottoms-tops)*fraction)*pixels.shape[0]/1400
        strip = cv2.remap(pixels,map_x.astype(np.float32),map_y.astype(np.float32),cv2.INTER_CUBIC)
        texture = OUT/"实拍贴图"/(name+".png")
        Image.fromarray(strip).save(texture)
        image = bpy.data.images.load(str(texture))
        image.pack()
        mat = photo_material(name,image,(.28,.38,.36),.37)
        mat.name = "楼间过道实拍 · "+name
        mat["原图"] = path.relative_to(ROOT.parent).as_posix()
        mat["曲面取样控制点"] = json.dumps(control,ensure_ascii=False)
        materials[name] = mat
    return materials


def make_ground(scene,materials):
    ground = Ground.__new__(Ground)
    ground.scene = scene
    ground.batches = {}
    ground.materials = materials
    round_footprint = Point(ROUND_CENTER).buffer(ROUND_RADIUS/SCALE)
    solids = unary_union([Polygon(rec["outline"]) for rec in PLAN["buildings"]]+[round_footprint])
    footprints = {}
    claimed = Polygon()
    garden_beds = (
        Polygon(((625,359),(659,357),(672,361),(669,369),(641,369),(628,366))),
        Polygon(((677,359),(717,358),(731,362),(730,369),(710,370),(684,368))),
        Polygon(((615,399),(638,397),(660,397),(677,400),(676,405),(613,405))),
        Polygon(((680,400),(697,397),(717,396),(734,398),(736,403),(685,403))),
    )
    courtyard = Polygon(((609,355),(733,354),(752,363),(772,402),(611,406)))
    ground.region("A02 樱花园砖铺庭院与平地绿篱")
    brick_area = courtyard.difference(unary_union(garden_beds)).difference(solids)
    ground.surface("樱花庭院完整砖铺面","樱花园红绿联锁砖",brick_area,.091)
    claimed = claimed.union(courtyard)
    round_court = Polygon(((888,163),(925,164),(939,183),(935,205),(922,210),(893,206),(889,188)))
    ground.region("A10 图书馆右侧圆弧玻璃建筑前地坪")
    ground.surface("圆弧建筑周围实拍混凝土","图书馆北侧细纹混凝土",round_court.difference(solids),.091)
    claimed = claimed.union(round_court)
    for bed in garden_beds:
        ground.surface("樱花园花篱内表土","soil",bed,.095)
        ground.surface("樱花园矮绿篱顶面","green",bed.boundary.buffer(.48/SCALE),.43)
    for code,label,points,width,key,refs,_ in ROUTES:
        ground.region(f"{code} {label} · 地坪")
        path = LineString(points)
        footprint = path.buffer(width/(2*SCALE),cap_style="flat",join_style="round")
        area = footprint.difference(solids).difference(claimed)
        footprints[code] = path
        ground.surface("实拍铺地 "+code,key,area,.082)
        claimed = claimed.union(footprint)
        if code not in {"A02","A03","A12"}:
            edge = path.buffer((width/2+.13)/SCALE,cap_style="flat",join_style="round")
            edge = edge.difference(footprint).difference(solids).difference(claimed)
            ground.surface("浅灰道牙 "+code,"curb",edge,.118)
        if code in {"A01","A08","A09","A10","A11"}:
            for along in np.arange(6.0/SCALE,path.length-2,5.8/SCALE):
                cross = tangent(path,along)
                xy = path.interpolate(along).coords[0]
                sides = tuple((xy[0]+cross[1]*width/(2*SCALE)*s,xy[1]-cross[0]*width/(2*SCALE)*s)
                              for s in (-1,1))
                seam = LineString(sides).buffer(.011/SCALE,cap_style="flat").intersection(area)
                ground.surface("横向缩缝 "+code,"joint",seam,.084)
        for fraction in {"A01":(.55,), "A05":(.51,), "A06":(.29,.75),"A07":(.27,),
                         "A09":(.43,.72),"A10":(.35,.67),"A11":(.45,),"A12":(.61,)}.get(code,()):
            position = path.interpolate(fraction,normalized=True)
            if area.contains(position):
                ground.cover("铸铁井盖 "+code,position.coords[0],.088,.32)
    ground.region("连廊端头与连续人行道")
    for pts,width,key in (
        (((732,399),(739,409),(744,431),(743,449),(743,466)),2.0,"樱花园红绿联锁砖"),
        (((790,393),(802,396),(818,397)),3.9,"教学石板"),
        (((867,382),(878,382),(891,383)),3.8,"教学石板"),
        (((852,295),(872,295),(895,296)),4.1,"行远楼门前灰石板"),
        (((852,232),(873,231),(891,224)),4.4,"行远楼门前灰石板"),
        (((469,169),(503,168),(545,169),(563,166)),1.8,"教学石板"),
        (((585,157),(610,156),(633,154),(649,155)),1.9,"樱花园红绿联锁砖"),
        (((971,78),(914,77),(858,77),(801,77),(750,77)),1.0,"樱花园红绿联锁砖"),
    ):
        patch = LineString(pts).buffer(width/(2*SCALE),cap_style="flat",join_style="round")
        ground.surface("接通转角及门前铺地",key,patch.difference(solids).difference(claimed),.079)
    ground.build()
    for code,label,*_,refs,status in ROUTES:
        collection = bpy.data.collections[f"{code} {label} · 地坪"]
        collection["对照资料"] = refs
        collection["定位依据"] = status
        for obj in collection.objects:
            obj["对照"] = refs
    remove_obsolete_landscape(scene,courtyard)
    remove_obsolete_landscape(scene,round_court)
    trim_replaced_ground(scene,courtyard.union(round_court))
    return footprints


def remove_obsolete_landscape(scene,paving):
    for name in ("Garden_curb_2","Garden_curb_3","Garden_hedge_2","Garden_hedge_3"):
        obj = scene.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj,do_unlink=True)
    for obj in scene.objects:
        if obj.type!="MESH" or not obj.name.startswith(("草叶","树干与分枝","细枝","多簇叶冠或樱花","修剪绿篱")):
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        # Split the broad court into its original polygons to preserve the island holes.
        polygons = (paving,) if paving.geom_type=="Polygon" else paving.geoms
        delete = []
        for part in polygons:
            outer = [world(p) for p in part.exterior.coords]
            holes = [[world(p) for p in ring.coords] for ring in part.interiors]
            mask = Polygon([(p.x,p.y) for p in outer], [[(p.x,p.y) for p in ring] for ring in holes])
            delete.extend(v for v in mesh.verts if contains_xy(mask,v.co.x,v.co.y))
        bmesh.ops.delete(mesh,geom=list(set(delete)),context="VERTS")
        mesh.to_mesh(obj.data)
        mesh.free()


def tangent(path,along):
    a,b = (path.interpolate(along+offset) for offset in (-.12,.12))
    length = a.distance(b)
    return (b.x-a.x)/length,(b.y-a.y)/length


def trim_replaced_ground(scene,paving):
    # Bisect old curb faces at the new paving boundary, preserving their UVs outside it.
    for obj in scene.objects:
        if obj.type!="MESH" or not obj.name.startswith(("校内低路缘","西门支路减速垄")):
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        for part in paving.geoms:
            ring = [obj.matrix_world.inverted()@world(p) for p in part.exterior.coords]
            mask = Polygon([(p.x,p.y) for p in ring])
            for a,b in zip(ring,ring[1:]):
                normal = Vector((a.y-b.y,b.x-a.x,0)).normalized()
                bmesh.ops.bisect_plane(mesh,geom=list(mesh.verts)+list(mesh.edges)+list(mesh.faces),
                    plane_co=a,plane_no=normal,dist=.00001,clear_outer=False,clear_inner=False)
            faces = [face for face in mesh.faces if contains_xy(mask,*face.calc_center_median().xy)]
            bmesh.ops.delete(mesh,geom=faces,context="FACES")
        loose = [vertex for vertex in mesh.verts if not vertex.link_faces]
        bmesh.ops.delete(mesh,geom=loose,context="VERTS")
        mesh.to_mesh(obj.data)
        mesh.free()


def orient(item,a,b):
    item.across = (world(b)-world(a)).normalized()
    item.depth = Vector((-item.across.y,item.across.x,0))


def bridge(site,label,points,kind,sid):
    path = LineString(points)
    size = path.length*SCALE
    width = 3.85 if kind=="curved" else 3.25
    pitch = 1.2
    garden_route = LineString([world(p).xy for p in ROUTES[1][2]])
    for k in range(len(points)-1):
        a,b = points[k:k+2]
        at = tuple((x+y)/2 for x,y in zip(a,b))
        span = (world(b)-world(a)).length
        item = site.zone(label+(f" · {k+1:02}" if len(points)>2 else ""),at)
        item.sid = sid
        orient(item,a,b)
        for z,h,mat,name in ((3.78,.77,"ochre","黄色外梁及楼板"),
                             (4.21,.105,"metal","桥底封板边条"),
                             (7.07,.39,"cement","灰色檐口"),
                             (7.32,.12,"metal","屋面压顶")):
            item.box(name,mat,0,0,z,span+.20,width,h)
        for y in (-width/2+.11,width/2-.11):
            item.box("连续玻璃","glass",0,y,5.48,span+.06,.073,2.41)
            for z in (4.28,4.90,5.53,6.18,6.70):
                item.box("铝合金横梃","metal",0,y,z,span+.10,.10,.065)
            count = max(1,round(span/pitch))
            for i in range(count+1):
                x = span*(i/count-.5)
                item.box("分格竖梃","metal",x,y,5.48,.070,.114,2.47)
        for x in np.arange(-span/2+.40,span/2,.95):
            item.box("吊顶板分缝","metal",x,0,3.395,.021,width-.23,.022)
        for x in np.arange(-span/2+2.0,span/2,4.55):
            if kind=="portal" and abs(x)<2.6:
                continue
            for y in (-width/2+.33,width/2-.33):
                if kind=="portal" and garden_route.distance(Point(item.point(x,y,0).xy))<.80:
                    continue
                item.box("桥下柱","curb",x,y,1.74,.36,.40,3.48)
                item.box("柱墩石套","metal",x,y,.22,.48,.50,.44)
            item.box("桥下条形灯","white",x,0,3.40,1.05,.135,.065)
        if kind=="portal":
            for x in (-.6,.6):
                item.box("通高灰色桥头墩","桥头深灰饰面",x,0,3.76,1.16,width+.50,7.43)
            # Entry pockets sit beside the portal, keeping the central walking route open.
            for x in (-span*.32,span*.31):
                for n in range(3):
                    item.box("地面入口三步石阶","curb",x,-width/2-.56-n*.28,
                             .078+(3-n)*.073,min(2.75,size/6),.30,(3-n)*.145)
        item.finish()
        for obj in item.collection.objects:
            if obj.type!="MESH" or not any(mat.get("原图") for mat in obj.data.materials):
                continue
            uv = obj.data.uv_layers.new()
            for face in obj.data.polygons:
                for loop_index in face.loop_indices:
                    point = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co-item.anchor
                    uv.data[loop_index].uv = (point.dot(item.across)/.86,point.z/.86)


def grill(site,label,path,fraction):
    along = path.length*fraction
    center = path.interpolate(along).coords[0]
    dx,dy = tangent(path,along)
    item = site.zone(label,center)
    orient(item,center,(center[0]+dx,center[1]+dy))
    item.box("排水沟底","iron",0,0,.087,.35,2.06,.035)
    for y in np.linspace(-.97,.97,20):
        item.box("横向铸铁栅","metal",0,y,.108,.34,.028,.022)
    item.finish()


def library_round_building(scene,site,materials):
    for obj in list(scene.objects):
        if obj.name.startswith(("B28 圆形裙房环形分格","B28 裙房竖梃")) or obj.name in {
            "R05_arc_14","R05_arc_15","R05_post_14","R05_post_15",
        }:
            bpy.data.objects.remove(obj,do_unlink=True)
    item = site.zone("图书馆右侧圆弧玻璃建筑 · 用户确认位置",ROUND_CENTER)
    item.sid = "32R"
    orient(item,ROUND_CENTER,(ROUND_CENTER[0]+1,ROUND_CENTER[1]))
    item.collection["位置依据"] = "用户确认场景28/180建筑在图书馆右边；中心与半径按航拍估算"
    item.collection["参考"] = "28/180；01、02航拍"
    angles = np.linspace(0,math.pi,97)

    def band(label,key,z0,z1,radius=ROUND_RADIUS):
        vertices = [item.point(radius*math.cos(t),radius*math.sin(t),z)
                    for t in angles for z in (z0,z1)]
        faces = [(2*i,2*i+2,2*i+3,2*i+1) for i in range(len(angles)-1)]
        obj = item.link(label,vertices,faces,materials[key])
        uv = obj.data.uv_layers.new()
        for face in obj.data.polygons:
            face.use_smooth = True
            for loop_index in face.loop_indices:
                index = obj.data.loops[loop_index].vertex_index
                uv.data[loop_index].uv = (index//2/(len(angles)-1),index%2)
        return obj

    for label,key,z0,z1,radius in (
        ("灰色弧形墙脚","cement",.09,.48,ROUND_RADIUS+.10),
        ("首层实拍玻璃及绿色腰线","圆弧首层玻璃窗帘",.48,3.18,ROUND_RADIUS),
        ("黄色层间弧形带","ochre",3.18,4.38,ROUND_RADIUS+.035),
        ("二层实拍玻璃窗帘","圆弧二层玻璃窗帘",4.38,6.83,ROUND_RADIUS),
        ("深灰弧形屋面檐带","cement",6.83,7.73,ROUND_RADIUS+.06),
    ):
        band(label,key,z0,z1,radius)
    for z in (.49,3.16,4.39,6.81):
        band("弧形窗带水平压条","silver",z-.025,z+.025,ROUND_RADIUS+.025)
    for t in np.linspace(0,math.pi,19):
        x,y = (ROUND_RADIUS+.025)*math.cos(t),(ROUND_RADIUS+.025)*math.sin(t)
        for z,h in ((1.83,2.70),(5.605,2.45)):
            item.box("弧形窗带竖梃","silver",x,y,z,.054,.054,h)
        item.box("屋顶栏杆立柱","silver",x,y,8.11,.035,.035,.77)
    for z in (7.92,8.17,8.48):
        band("屋顶弧形栏杆横杆","silver",z-.018,z+.018,ROUND_RADIUS+.025)
    ring = [item.point(ROUND_RADIUS*math.cos(t),ROUND_RADIUS*math.sin(t),7.70) for t in angles]
    vertices = [item.point(0,0,7.70)]+ring
    item.link("圆弧屋顶平台",vertices,[(0,i,i+1) for i in range(1,len(ring))],materials["cement"])
    item.box("后部连接体灰墙","cement",0,-.10,3.90,ROUND_RADIUS*2,.20,7.60)
    item.box("后部平顶连接平台","cement",0,-1.52,7.70,ROUND_RADIUS*2,3.04,.15)
    # The ground-level side passage follows the visible bridge opening.
    for x in (-4.3,4.3):
        item.box("侧连廊地面柱","curb",x,-2.2,1.73,.33,.35,3.46)
    item.finish()


def planting_and_fixtures(scene,materials,paths):
    site = SiteDetails(scene,materials)
    bridge(site,"A02 思远楼—近门西翼深灰门框连廊",((737,352),(762,408)),"portal","06")
    bridge(site,"A03 思远楼—志远楼低层连接",((705,253),(713,280),(733,320)),"low","06")
    bridge(site,"A04 图书馆西侧弧廊",((686,239),(696,222),(709,210),(725,196),(748,183)),"curved","32")
    bridge(site,"A05 知远楼—近门东翼玻璃连廊",((875,355),(881,414)),"low","45")
    bridge(site,"A07 图书馆右侧圆弧建筑西接桥",((885,178),(895,184)),"curved","32")
    bridge(site,"A07 图书馆东侧弧廊",((915,200),(930,212),(945,226),(953,235)),"curved","32")
    library_round_building(scene,site,materials)

    plant = Planting(scene)
    plant.group.name = "楼间过道 · 低篱与入口树池"
    for center,height in (((640,364),4.1),((665,365),4.6),((693,365),4.3),((718,364),4.6),
                          ((636,400),4.0),((672,400),4.4),((704,400),4.1),((729,400),4.5)):
        cherry_tree(plant,center,height)
    hedge_lines = (
        ((657,379),(678,378),(703,375)),((660,396),(683,394),(705,391)),
        ((568,281),(595,282),(619,283)),((605,300),(628,300),(647,299)),
        ((888,397),(889,385),(889,368)),((894,315),(894,300),(895,286)),
        ((887,239),(895,235),(902,226)),((729,166),(744,163),(762,160)),
        ((831,140),(846,140),(860,140)),((904,150),(927,150),(949,150)),
        ((506,164),(512,164),(518,165)),
    )
    for points in hedge_lines:
        plant.hedge(points,.43)
    plant.finish()
    for code,fractions in (("A02",(.71,)),("A05",(.77,)),("A06",(.37,)),("A07",(.24,)),("A10",(.55,))):
        for f in fractions:
            grill(site,code+" 路侧金属排水栅",paths[code],f)

    item = site.zone("思远楼临路木格廊 · 场景21",(536,339))
    orient(item,(542,350),(530,325))
    for x in np.arange(-5.8,5.9,1.65):
        for y in (-.82,.82):
            item.box("木廊柱","wood",x,y,1.33,.115,.115,2.64)
            item.box("金属柱脚","iron",x,y,.12,.16,.16,.23)
        item.box("顶棚横梁","wood",x,0,2.64,.12,2.26,.15)
    for y in np.linspace(-.99,.99,7):
        item.box("顶棚纵梁","wood",0,y,2.74,12.35,.081,.116)
    item.finish()

    for x,y in ((475,166),(507,166),(540,166),(571,171)):
        item = site.zone("餐厅路旁方花池",(x,y))
        item.box("矮混凝土池壁","curb",0,0,.16,2.75,1.10,.29)
        item.box("修剪过的绿篱","green",0,0,.45,2.64,.98,.40)
        item.finish()
    item = site.zone("行远楼连廊下 · 通行分区",(879,295))
    orient(item,(880,268),(878,328))
    for x in np.arange(-11.5,12.2,1.73):
        item.box("桥下石板吊顶接缝","metal",x,0,3.656,.023,2.82,.029)
    for x in (-9,-3,3,9):
        item.box("桥下灯具","white",x,0,3.625,.78,.11,.058)
    item.finish()

    for name,pixel,w,d,high in (
        ("绅远楼正门侧坡道",(655,148),1.40,3.65,.37),
        ("蕙远楼正门侧坡道",(839,146),1.62,4.02,.43),
    ):
        item = site.zone(name,pixel)
        a,b = -d/2,d/2
        vertices = [item.point(x,y,z) for x,y,z in ((-w/2,a,.08),(w/2,a,.08),
            (w/2,b,.08),(-w/2,b,.08),(-w/2,b,high),(w/2,b,high))]
        item.link("混凝土坡面",vertices,[(0,3,2,1),(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)],materials["curb"])
        for x in (-w/2,w/2):
            for q in np.linspace(0,1,6):
                z = .08+(high-.08)*q
                item.box("不锈钢扶手立杆","metal",x,a+d*q,z+.39,.037,.037,.77)
            start,end = item.point(x,a,.89),item.point(x,b,high+.81)
            # Blender's mesh coordinates follow the actual slope, including the rail ends.
            rail = SiteDetails(scene,materials)
            part = rail.zone(name+"扶手",pixel)
            part.anchor = (start+end)/2
            part.depth = (end-start).normalized()
            part.across = item.across
            side = Vector((1,0,0))*.022
            up = Vector((0,0,.022))
            corners = [p+s*side+t*up for p in (start,end) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
            part.link("斜坡扶手",corners,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],materials["metal"])
        item.finish()
    north_service_lane(scene,site,materials)


def cherry_tree(plant,pixel,height):
    rng = plant.rng
    ground = world(pixel)+Vector((0,0,.105))
    fork = ground+Vector((0,0,height*.43))
    plant.limb("樱花树干","bark",ground,fork,.10,.049)
    for i in range(8):
        angle = i*2.39996
        tip = fork+Vector((math.cos(angle)*.84,math.sin(angle)*.84,height*.43+rng.uniform(-.25,.38)))
        plant.limb("樱花细枝","bark",fork,tip,.035,.009)
        for _ in range(27):
            pos = tip+Vector((rng.uniform(-.62,.62),rng.uniform(-.62,.62),rng.uniform(-.18,.38)))
            radius = rng.uniform(.08,.18)
            plant.crown("樱花花簇",rng.choice(("pink","pink_light","pink_shade")),
                        pos,radius*1.1,radius,radius*.83)


def north_service_lane(scene,site,materials):
    ground = Ground.__new__(Ground)
    ground.scene,ground.batches,ground.materials = scene,{},materials
    ground.region("A11 北侧围墙与种植带 · 地面")
    footpath = LineString(((579,65),(1015,66))).buffer(.56/SCALE,cap_style="flat")
    ground.surface("围墙下红灰砖道","樱花园红绿联锁砖",footpath,.10)
    bed = box(581,77,1008,80)
    ground.surface("沿楼种植表土","soil",bed,.11)
    for y in (76.7,80.3):
        ground.line("种植畦低路缘","curb",(581,y),(1008,y),.12,.19)
    ground.build()

    plants = Planting(scene)
    plants.group.name = "A11 北侧沿楼树列与课程种植畦"
    for i,x in enumerate(range(589,1008,17)):
        ground_point = world((x,78))
        fork = ground_point+Vector((0,0,1.55))
        plants.limb("树干与分枝","lightbark",ground_point,fork,.092,.052)
        for j in range(4):
            tip = fork+Vector((((j%2)*2-1)*.45,((j//2)*2-1)*.40,1.02+(i%3)*.13))
            plants.limb("细枝","lightbark",fork,tip,.035,.010)
            plants.crown("多簇叶冠或樱花","leaf",tip,.44,.35,.55)
        item = site.zone("A11 沿楼种植畦",(x,78))
        for dx in (-2.7,-1.6,-.5,.6,1.7,2.8):
            for dy in (-.31,.27):
                item.box("矮菜株","green",dx,dy,.17,.18,.17,.18)
            item.box("畦间竹支架","wood",dx,0,.70,.021,.021,1.13)
        item.finish()
    plants.finish()
    wall = site.zone("A11 北侧节气彩绘围墙",(796,62))
    orient(wall,(580,62),(1013,62))
    length = (world((1013,62))-world((580,62))).length
    wall.box("米黄色围墙","cream",0,0,1.05,length,.26,2.10)
    wall.box("深灰墙脚","cement",0,-.025,.245,length,.32,.49)
    wall.box("深灰墙顶","metal",0,0,2.13,length+.12,.52,.13)
    for x in np.arange(-length/2+.45,length/2,4.3):
        wall.box("围墙扶壁","cream",x,-.15,.95,.22,.38,1.89)
        wall.box("扶壁墙脚","cement",x,-.19,.25,.29,.44,.50)
        # A photographed wall panel is mounted between each pair of buttresses.
        w,h = 3.83,1.34
        points = [wall.point(px,-.144,pz) for px,pz in
                  ((x+.20,1.91),(x+.20+w,1.91),(x+.20+w,1.91-h),(x+.20,1.91-h))]
        if x+.20+w > length/2:
            continue
        panel = wall.link("原图节气彩绘",points,[(3,2,1,0)],materials["节气围墙彩绘"])
        uv = panel.data.uv_layers.new()
        for loop in panel.data.loops:
            uv.data[loop.index].uv = ((0,1),(1,1),(1,0),(0,0))[loop.vertex_index]
    wall.finish()
    for x in range(604,1010,37):
        item = site.zone("A11 白蓝路灯及红旗",(x,76))
        item.box("蓝色杆脚","blue",0,0,.52,.09,.09,1.04)
        item.box("白色灯杆","white",0,0,2.35,.075,.075,3.95)
        item.box("挑臂","white",.26,0,4.28,.60,.068,.068)
        item.box("灯头","white",.58,0,4.25,.38,.14,.058)
        item.box("红色道旗","red",-.25,0,2.98,.44,.032,.67)
        item.finish()


def camera(scene,name,eye,target,aim,lens,height=1.64):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    obj = bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location = world(eye)+Vector((0,0,height))
    obj.rotation_euler = (world(target)+Vector((0,0,aim))-obj.location).to_track_quat("-Z","Y").to_euler()
    return obj


def render_previews(scene,cameras):
    scene.render.resolution_x = scene.render.resolution_y = 720
    scene.cycles.samples = 16
    for tag,view in cameras.items():
        scene.camera = view
        scene.render.filepath = str(OUT/"模型视角"/(tag+".png"))
        bpy.ops.render.render(write_still=True)
    overview = camera(scene,"楼间过道总览",(904,642),(719,285),0,37,233)
    scene.camera = overview
    scene.render.resolution_x,scene.render.resolution_y = 1300,860
    scene.render.filepath = str(OUT/"楼间过道总览.png")
    bpy.ops.render.render(write_still=True)


def clean_generated_meshes(objects):
    for obj in objects:
        if obj.type!="MESH":
            continue
        indices = [face.index for face in obj.data.polygons if face.area<1e-9]
        if not indices:
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        mesh.faces.ensure_lookup_table()
        faces = [mesh.faces[index] for index in indices]
        bmesh.ops.delete(mesh,geom=faces,context="FACES")
        mesh.to_mesh(obj.data)
        mesh.free()


def evidence():
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    labels = {r[0]:r[1] for r in ROUTES}
    for index in range(0,len(VIEWS),3):
        canvas = Image.new("RGB",(1110,1081),"#f1eee5")
        draw = ImageDraw.Draw(canvas)
        draw.text((12,10),"楼间过道 · 左为全景方向图，右为模型估算视角",fill="#24312b",font=font)
        for i,(tag,code,sid,heading,*_) in enumerate(VIEWS[index:index+3]):
            y = 41+i*345
            draw.text((12,y),f"{code}  {labels[code]}  ·  {sid}/{heading}",fill="#24312b",font=font)
            for j,path in enumerate((reference(sid,heading),OUT/"模型视角"/(tag+".png"))):
                with Image.open(path) as image:
                    canvas.paste(ImageOps.fit(image.convert("RGB"),(540,320)),(11+j*549,y+24))
        canvas.save(OUT/f"楼间过道实景对照_{1+index//3}.png")
    route_map = Image.open(ROOT/"成果/第2轮/航拍重投影.png").convert("RGB")
    draw = ImageDraw.Draw(route_map)
    for code,_,points,*_ in ROUTES:
        draw.line(points,fill="#34fcf0",width=3,joint="curve")
        x,y = points[len(points)//2]
        draw.text((x+4,y-17),code,fill="white",stroke_width=2,stroke_fill="#113736",font=font)
    route_map.save(OUT/"楼间过道航拍定位.png")
    record = {
        "站点网站": TOUR,"场景40与28网页核对": (93018141,93018146),
        "地面来源": SAMPLES,"裁切坐标": "以500×500方向参考图为基准",
        "圆弧玻璃贴图控制点": ROUND_STRIPS,
        "圆弧贴图控制点基准": "场景28/180，1400×1400方向图；每列按上下玻璃边界展开",
        "用户确认": {
            "场景06深灰门框连廊": "连接思远楼与靠大门的西翼教学楼",
            "场景28圆弧玻璃建筑": "图书馆右边",
        },
        "圆弧玻璃建筑定位": {"航拍中心像素": ROUND_CENTER,"半径估算米": ROUND_RADIUS,
            "立面来源": "28/180","原错误位置": "已移除蕙远楼旁B28圆形裙房环形分格与竖梃"},
        "路线": [dict(zip(("编号","楼间位置","航拍像素点","宽度估算米","铺装","参考","依据"),r)) for r in ROUTES],
        "浏览相机": VIEWS,
        "说明": "露天步道与连廊外观来自航拍和地面全景；部分弧廊尺寸及楼层连接待现场核实。",
    }
    (OUT/"楼间过道定位与来源.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"实拍贴图").mkdir(exist_ok=True)
    (OUT/"模型视角").mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene = bpy.context.scene
    original_objects = set(scene.objects)
    materials = photo_materials()
    colors = {
        "curb":(.38,.36,.32),"cement":(.27,.28,.28),"iron":(.062,.076,.078),
        "joint":(.13,.12,.11),"metal":(.18,.21,.23),"ochre":(.58,.30,.052),
        "glass":(.11,.21,.225),"white":(.66,.67,.57),"wood":(.20,.10,.049),
        "green":(.082,.172,.026),"soil":(.23,.175,.095),
        "cream":(.67,.58,.40),"blue":(.027,.10,.23),"red":(.63,.028,.022),
        "silver":(.49,.52,.51),
    }
    materials.update({key:material("楼间过道 "+key,color,.34 if key in ("glass","metal") else .83)
                      for key,color in colors.items()})
    paths = make_ground(scene,materials)
    planting_and_fixtures(scene,materials,paths)
    clean_generated_meshes(set(scene.objects)-original_objects)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=1.0
    scene.view_settings.exposure=.55
    cameras = {tag:camera(scene,f"{code} · {tag}",eye,target,aim,lens)
               for tag,code,_,_,eye,target,aim,lens in VIEWS}
    scene.camera = cameras["cherry"]
    scene.render.resolution_x = scene.render.resolution_y = 960
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_楼间过道细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_楼间过道细化.glb"),export_format="GLB",
                             export_cameras=False,export_lights=False)
    render_previews(scene,cameras)
    evidence()


if __name__ == "__main__":
    main()
