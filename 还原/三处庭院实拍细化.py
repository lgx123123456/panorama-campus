"""Continue the campus master with the three courtyards confirmed by the owner."""

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
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from 四栋教学楼实景细化 import reference
from 地面街道实景细化 import Ground
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 尚德广场实拍细化 import photo_material
from 楼间过道实拍细化 import camera, clean_generated_meshes, orient


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/楼间过道实拍细化/校园室外_楼间过道细化.blend"
OUT = ROOT / "成果/三处庭院实拍细化"
SCALE = CAL["metres_per_pixel"]
STEM = "校园室外_三处庭院细化"

# Coordinates follow the existing aerial reprojection. Hidden ground edges are estimates.
COURTS = {
    "C1": {
        "name": "樱花园 · 近门西翼与思远楼之间",
        "outline": [(607,354),(734,354),(753,363),(772,404),(608,405)],
        "beds": [
            [(610,355),(650,355),(666,362),(659,371),(632,369),(613,364)],
            [(669,356),(727,355),(738,362),(730,373),(712,376),(690,368)],
            [(611,393),(640,391),(660,394),(676,400),(676,405),(611,405)],
            [(681,395),(704,388),(728,385),(741,390),(747,403),(688,404)],
        ],
        "route": [(608,380),(632,381),(663,383),(691,382),(716,379),(748,381),(767,386)],
        "refs": "06/090、135、225、270；01/000；02天底",
        "trees": [(622,361),(640,363),(656,363),(684,363),(703,364),(722,363),
                  (621,399),(644,398),(665,401),(694,398),(715,394),(734,395)],
    },
    "C2": {
        "name": "思远楼与志远楼之间",
        "outline": [(548,263),(686,263),(699,276),(717,306),(734,319),(557,319),(544,294)],
        "beds": [
            [(550,265),(585,265),(605,270),(602,280),(578,284),(552,281)],
            [(610,265),(681,265),(692,275),(680,283),(651,280),(628,278)],
            [(557,297),(576,292),(601,293),(622,303),(621,316),(558,316)],
            [(633,299),(657,297),(683,291),(700,298),(711,314),(639,316)],
        ],
        "route": [(546,290),(574,288),(606,287),(630,289),(652,289),(678,287),(699,289),(721,307)],
        "refs": "15/000、045、315；21/000、090；01/000、045；02天底",
        "trees": [(559,272),(575,274),(593,272),(619,270),(642,272),(665,273),(679,273),
                  (565,307),(585,302),(605,307),(645,306),(662,303),(682,303),(700,308)],
    },
    "C3": {
        "name": "志远楼北侧至餐厅之间",
        "outline": [(504,183),(580,183),(623,179),(673,169),(705,177),(698,204),(685,227),(512,227)],
        "beds": [
            [(507,185),(538,185),(551,191),(542,201),(520,209),(510,206)],
            [(558,188),(581,186),(621,182),(660,175),(682,178),(686,191),(667,200),(639,201),(607,192),(580,194)],
            [(521,219),(544,211),(570,205),(594,204),(613,211),(625,226),(521,226)],
            [(633,214),(652,213),(678,211),(688,205),(682,226),(639,226)],
        ],
        "route": [(509,216),(536,207),(559,199),(580,199),(607,200),(633,207),(661,207),(684,204)],
        "refs": "22/135、180、225、270；15/135；01/045；02天底",
        "trees": [(517,193),(532,190),(565,190),(585,190),(605,187),(626,187),(646,183),
                  (666,183),(676,189),(530,222),(550,217),(570,212),(592,212),(609,219),
                  (643,221),(659,220),(678,220)],
    },
}

# All crop coordinates below use the original 1400-pixel direction images.
SAMPLES = {
    "brick": ("06","270",[(340,995),(800,995),(1100,1380),(120,1380)],2.8,(768,768)),
    "concrete": ("22","270",[(712,972),(1002,957),(1142,1330),(571,1351)],2.8,(512,512)),
    "wall": ("06","135",[(575,430),(658,433),(658,535),(575,535)],.9,(384,384)),
    "window": ("06","225",[(431,179),(496,166),(496,246),(431,263)],1.0,(256,320)),
    "hedgephoto": ("06","225",[(420,744),(590,744),(590,790),(420,790)],.75,(512,192)),
    "bridgeglass": ("06","135",[(719,451),(1107,469),(1107,535),(719,531)],1.0,(1280,288)),
    "board1": ("06","135",[(722,669),(815,670),(815,711),(722,710)],1.0,(640,288)),
    "board2": ("06","135",[(888,669),(973,671),(973,711),(888,711)],1.0,(640,288)),
    "board3": ("06","135",[(1003,671),(1074,673),(1074,711),(1003,711)],1.0,(640,288)),
}
VIEWS = [
    ("C1_东端桥头","C1","06","135",(697,384),(748,381),3.1,19,1.64),
    ("C1_沿庭院回望","C1","06","270",(727,382),(613,382),3.4,19,1.64),
    ("C2_思远志远庭院","C2","01","000",(573,287),(699,289),3.1,19,1.64),
    ("C2_庭院回望","C2","15","315",(687,286),(552,287),3.0,19,1.64),
    ("C3_志远北侧庭院","C3","22","180",(540,207),(675,208),3.0,19,1.64),
    ("C3_接餐厅道路","C3","22","270",(535,175),(634,171),2.9,19,1.64),
]


def prepare_materials():
    result = {}
    for key,(sid,angle,quad,period,size) in SAMPLES.items():
        source = np.asarray(Image.open(reference(sid,angle)).convert("RGB"))
        controls = np.float32(quad)*np.float32((source.shape[1]/1400,source.shape[0]/1400))
        w,h = size
        target = np.float32([(0,0),(w-1,0),(w-1,h-1),(0,h-1)])
        pixels = cv2.warpPerspective(source,cv2.getPerspectiveTransform(controls,target),size,
                                     flags=cv2.INTER_CUBIC)
        if key in {"brick","concrete","wall"}:
            low = cv2.GaussianBlur(pixels.astype(np.float32),(0,0),43)
            pixels = np.clip(pixels+.55*(np.median(low,axis=(0,1))-low),0,255).astype(np.uint8)
        if key=="hedgephoto":
            pixels = np.clip(255*(pixels/255)**.65,0,255).astype(np.uint8)
        path = OUT/"实拍贴图"/(key+".png")
        Image.fromarray(pixels).save(path)
        texture = bpy.data.images.load(str(path))
        texture.pack()
        result[key] = photo_material("三处庭院实拍 · "+key,texture,(.35,.35,.32),
                                     .36 if key=="window" else .87,period)
        result[key].name = "三处庭院实拍 · "+key
        result[key]["来源"] = f"{sid}/{angle}，原图四点 {quad}，基准1400像素"
    colors = {"curb":(.35,.34,.30),"soil":(.16,.12,.071),"joint":(.055,.065,.061),
              "iron":(.07,.082,.076),"ochre":(.70,.381,.045),"metal":(.11,.13,.13),
              "glass":(.12,.23,.25),"white":(.72,.72,.65),"wood":(.19,.09,.037),
              "green":(.064,.16,.024),"cream":(.66,.62,.51),"slate":(.16,.19,.20)}
    result.update({k:material("三处庭院 · "+k,rgb,.82) for k,rgb in colors.items()})
    # Pink pixels preserve the photographed petals. Blue sky and green leaves are keyed out.
    source = np.asarray(Image.open(reference("06","270")).convert("RGB"))[55:310,292:530]
    hsv = cv2.cvtColor(source,cv2.COLOR_RGB2HSV)
    mask = (((hsv[:,:,0]>144)|(hsv[:,:,0]<6))&(hsv[:,:,1]>32)&(hsv[:,:,2]>90)).astype(np.uint8)*255
    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    rgba = np.dstack((source,mask))
    path = OUT/"实拍贴图/樱花花簇透明.png"
    Image.fromarray(rgba).save(path)
    texture = bpy.data.images.load(str(path))
    texture.pack()
    flower = photo_material("实拍樱花花瓣镂空",texture,(.6,.3,.4),.86)
    flower.name = "实拍樱花花瓣镂空"
    shader = flower.node_tree.nodes.get("Principled BSDF")
    node = next(n for n in flower.node_tree.nodes if n.type=="TEX_IMAGE")
    flower.node_tree.links.new(node.outputs["Alpha"],shader.inputs["Alpha"])
    flower.surface_render_method = "DITHERED"
    flower.use_transparency_overlap = False
    flower["来源"] = "06/270，像素(292,55)-(530,310)，HSV粉花遮罩"
    result["flowers"] = flower
    source = np.asarray(Image.open(reference("06","225")).convert("RGB"))[10:160,610:790]
    red,green,blue = [source[:,:,i].astype(float) for i in range(3)]
    alpha = ((green-red>8)&(green-blue>3)).astype(np.uint8)*255
    yy,xx = np.mgrid[-1:1:complex(source.shape[0]),-1:1:complex(source.shape[1])]
    # Taper the card edge so a branch photograph does not form a visible rectangle.
    taper = np.clip((1-xx*xx-yy*yy)/.25,0,1)
    alpha = (alpha*taper).astype(np.uint8)
    source = np.clip(255*(source/255)**.78,0,255).astype(np.uint8)
    path = OUT/"实拍贴图/庭院树叶透明.png"
    Image.fromarray(np.dstack((source,alpha))).save(path)
    texture = bpy.data.images.load(str(path))
    texture.pack()
    leaf = photo_material("庭院实拍树叶镂空",texture,(.15,.3,.10),.90)
    leaf.name = "三处庭院实拍 · 树叶"
    shader = leaf.node_tree.nodes.get("Principled BSDF")
    node = next(n for n in leaf.node_tree.nodes if n.type=="TEX_IMAGE")
    leaf.node_tree.links.new(node.outputs["Alpha"],shader.inputs["Alpha"])
    leaf.surface_render_method = "DITHERED"
    leaf.use_transparency_overlap = False
    leaf["来源"] = "06/225，像素(610,10)-(790,160)，绿色叶片遮罩"
    result["leaves"] = leaf
    return result


def clean_previous(scene):
    masks = unary_union([Polygon(c["outline"]) for c in COURTS.values()])
    polygons = list(masks.geoms) if hasattr(masks,"geoms") else [masks]
    world_masks = [Polygon([world(p).xy for p in part.exterior.coords]) for part in polygons]
    removed = []
    side_names = {"长边内衬","长边玻璃转角","转角纵梃","转角玻璃横梃", "侧墙连续黄色檐带",
                  "侧墙通高黄柱","长边可见窗组"}
    for obj in list(scene.objects):
        if obj.name[:3] in {"B15","B21"} and obj.name[4:] in side_names:
            removed.append(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    for collection_name in ("A02 樱花园砖铺庭院与平地绿篱","A03 思远楼—志远楼 · 地坪"):
        group = bpy.data.collections.get(collection_name)
        if group:
            for obj in list(group.objects):
                removed.append(obj.name)
                bpy.data.objects.remove(obj,do_unlink=True)
    for name in ("樱花园花篱内表土","樱花园矮绿篱顶面"):
        obj = scene.objects.get(name)
        if obj:
            removed.append(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    # These four original objects belong to the north long side of the near-gate west wing.
    wing = bpy.data.collections["B40W 艺远楼识远楼西翼 · 外立面"]
    for name in ("B40 侧后檐条","B40 侧后裙墙","B40 侧后窗玻璃","B40 侧后窗梃"):
        obj = wing.objects.get(name)
        if obj:
            removed.append(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    # Old vegetation is merged by material. Remove whole connected branches or crowns by centroid.
    for obj in list(scene.objects):
        if obj.type!="MESH":
            continue
        vegetation = obj.name.startswith(("草叶","树干与分枝","细枝","多簇叶冠或樱花","修剪绿篱",
                                           "樱花花簇","樱花树干","樱花细枝"))
        if not vegetation:
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        unseen = set(mesh.verts)
        deleted = []
        while unseen:
            seed = unseen.pop()
            component,stack = [seed],[seed]
            while stack:
                vertex = stack.pop()
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    if other in unseen:
                        unseen.remove(other)
                        stack.append(other)
                        component.append(other)
            center = obj.matrix_world @ (sum((v.co for v in component),Vector())/len(component))
            if any(contains_xy(mask,center.x,center.y) for mask in world_masks):
                deleted.extend(component)
        if deleted:
            bmesh.ops.delete(mesh,geom=deleted,context="VERTS")
            mesh.to_mesh(obj.data)
        mesh.free()
    return removed


def ground_and_beds(scene,materials):
    ground = Ground.__new__(Ground)
    ground.scene,ground.batches,ground.materials = scene,{},materials
    solids = unary_union([Polygon(b["outline"]) for b in PLAN["buildings"]])
    bed_map = {}
    for code,court in COURTS.items():
        ground.region(code+" "+court["name"]+" · 完整地坪")
        border = Polygon(court["outline"]).difference(solids.buffer(.15))
        beds = [Polygon(p).buffer(.60,join_style="round").intersection(border) for p in court["beds"]]
        bed_map[code] = beds
        union = unary_union(beds)
        ground.surface("实拍红绿砖庭院 "+code,"brick",border.difference(union),.145)
        for bed in beds:
            ground.surface("林下表土 "+code,"soil",bed,.151)
            edge = bed.boundary.buffer(.075/SCALE)
            ground.surface("种植边缘暗缝 "+code,"joint",edge,.154)
            hedge = bed.boundary.buffer(.27/SCALE,join_style="round")
            ground.raised("实拍叶片连续低绿篱 "+code,"hedgephoto",hedge,.16,.69)
        for xy in {"C1":[(648,383),(728,379),(757,392)],"C2":[(587,288),(683,286)],
                   "C3":[(536,208),(667,206)]}[code]:
            if border.difference(union).contains(Point(xy)):
                ground.cover("圆井盖 "+code,xy,.153,.29)
        court["estimated_paved_area_m2"] = round(border.difference(union).area*SCALE*SCALE,2)
        court["estimated_bed_area_m2"] = round(union.area*SCALE*SCALE,2)
    # The third court meets the light concrete road in front of the dining hall.
    ground.region("C3 餐厅道路转角与砖铺衔接")
    apron = Polygon([(485,166),(576,164),(609,165),(608,184),(575,188),(536,185),(491,183)])
    ground.surface("餐厅前浅色混凝土接通","concrete",apron.difference(solids),.134)
    for x in range(494,607,17):
        ground.line("混凝土缩缝","joint",(x,166),(x,182),.017,.137)
    ground.build()
    return bed_map


def panel(item,label,key,x,y,z,width,height):
    vertices = [item.point(px,y,pz) for px,pz in ((x-width/2,z-height/2),(x+width/2,z-height/2),
                                                (x+width/2,z+height/2),(x-width/2,z+height/2))]
    obj = item.link(label,vertices,[(0,1,2,3)],item.materials[key])
    uv = obj.data.uv_layers.new()
    for loop in obj.data.loops:
        uv.data[loop.index].uv = ((0,0),(1,0),(1,1),(0,1))[loop.vertex_index]
    return obj


def detailed_facade(site,sid,a,b,height,estimated):
    center = tuple((x+y)/2 for x,y in zip(a,b))
    item = site.zone(f"C 楼侧长立面 B{sid} {a}—{b}",center)
    item.sid = sid
    orient(item,a,b)
    span = (world(b)-world(a)).length
    # Each edge is ordered clockwise in image space, so positive depth points outwards.
    count = round(span/3.15)
    pitch = span/count
    base = 3.65
    upper = (height-base-.70)/4
    item.box("连续凹窗背衬","slate",0,-.20,height/2,span,.18,height)
    item.box("黄色首层裙墙","ochre",0,-.02,base/2,span,.32,base)
    item.box("黄色屋顶框带","ochre",0,.08,height-.30,span+.15,.52,.60)
    item.box("墙脚灰石勒脚","curb",0,.15,.20,span,.12,.36)
    # Photo window inserts sit behind modeled reveals and metal frames.
    for i in range(count):
        x = -span/2+(i+.5)*pitch
        window_w = pitch*.63
        item.box("首层窗洞阴影","joint",x,.165,1.90,window_w+.13,.045,1.85)
        panel(item,"首层实拍窗玻璃","window",x,.19,1.91,window_w,1.73)
        for z in (1.05,2.77):
            item.box("首层窗框","metal",x,.225,z,window_w+.10,.065,.058)
        for dx in (-window_w/2,0,window_w/2):
            item.box("首层窗竖框","metal",x+dx,.23,1.91,.045,.065,1.73)
        for floor in range(4):
            low = base+floor*upper
            win_h = upper*.58
            z = low+upper*.57
            item.box("窗下灰色实体裙板","wall",x,.01,low+upper*.145,pitch-.16,.30,upper*.29)
            item.box("灰色窗顶过梁","wall",x,.01,low+upper*.95,pitch-.16,.30,upper*.10)
            item.box("凹进窗玻璃背面","joint",x,.07,z,window_w+.13,.075,win_h+.13)
            panel(item,"实拍窗格反射","window",x,.115,z,window_w,win_h)
            # Recess depth remains visible from both directions along the court.
            for dx in (-window_w/2-.065,window_w/2+.065):
                item.box("窗洞两侧进深","wall",x+dx,.19,z,.13,.32,win_h+.12)
            for zz in (z-win_h/2,z+win_h/2):
                item.box("窗框横梃","metal",x,.185,zz,window_w+.06,.075,.055)
            for dx in (-window_w/2,0,window_w/2):
                item.box("窗框竖梃","metal",x+dx,.183,z,.046,.070,win_h)
            item.box("上亮窗横梃","metal",x,.19,z+win_h*.23,window_w,.075,.045)
            # Narrow vertical lights and a square vent repeat between the broad classroom windows.
            xx = x+pitch*.397
            item.box("窄竖窗玻璃","glass",xx,.04,z,.16,.07,win_h)
            item.box("窗间灰板","wall",x+pitch*.265,.13,low+upper/2,.24,.40,upper-.025)
        if i%2==0:
            item.box("墙面竖向拼缝","joint",x-pitch/2,.225,height/2,.013,.018,height-1.0)
    for i in range(count+1):
        x = -span/2+i*pitch
        item.box("通高灰色立柱","wall",x,.12,(base+height-.63)/2,.20,.48,height-base-.63)
        for level in range(4):
            item.box("灰板水平分缝","joint",x,.368,base+(level+1)*upper-.018,.20,.015,.019)
    for x in (-span/2+.36,span/2-.36):
        item.box("端头通高黄框","ochre",x,.12,height/2,.68,.57,height)
    item.finish()
    for obj in item.collection.objects:
        obj["依据"] = "06/225、270实拍灰墙黄腰带及窗洞；01/000航拍校楼层"
        obj["尺寸状态"] = estimated


def facades(scene,materials):
    site = SiteDetails(scene,materials)
    for sid in ("15","21"):
        record = next(b for b in PLAN["buildings"] if b["id"]=="B"+sid)
        p = record["outline"]
        for a,b in ((p[0],p[1]),(p[2],p[3])):
            detailed_facade(site,sid,a,b,record["height"],"总高20m沿用估算；遮挡开间按同楼规律续建")
    record = next(b for b in PLAN["buildings"] if b["id"]=="B40W")
    detailed_facade(site,"40W",record["outline"][0],record["outline"][1],record["height"],
                    "靠樱花园北立面；被树挡住的窗列依航拍估算")


def tree(plant,pixel,height,kind,cards,leaf_cards):
    rng = plant.rng
    ground = world(pixel)+Vector((0,0,.17))
    fork = ground+Vector((rng.uniform(-.12,.12),rng.uniform(-.12,.12),height*.40))
    plant.limb("庭院分枝树干","bark",ground,fork,.105 if kind=="cherry" else .14,.052)
    plant.limb("树干刷白段","white",ground,ground+Vector((0,0,.72)),.108 if kind=="cherry" else .143,.12)
    for i in range(7):
        angle = i*2.39996+rng.uniform(-.25,.25)
        reach = height*(.25 if kind=="cherry" else .26)
        arm = fork+Vector((math.cos(angle)*reach,math.sin(angle)*reach,height*rng.uniform(.12,.40)))
        plant.limb("庭院二级枝","bark",fork,arm,.043,.016)
        for j in range(4):
            tip = arm+Vector((rng.uniform(-.70,.70),rng.uniform(-.70,.70),rng.uniform(.15,1.10)))
            plant.limb("庭院三级细枝","bark",arm,tip,.016,.0035)
            if kind=="cherry":
                for _ in range(4):
                    center = tip+Vector((rng.uniform(-.30,.30),rng.uniform(-.30,.30),rng.uniform(-.13,.22)))
                    cards.append((center,rng.uniform(.30,.46),rng.uniform(0,math.tau)))
            else:
                for _ in range(10):
                    center = tip+Vector((rng.uniform(-.38,.38),rng.uniform(-.38,.38),rng.uniform(-.22,.27)))
                    leaf_cards.append((center,rng.uniform(.17,.29),rng.uniform(0,math.tau)))


def foliage_cards(group,material_value,cards,label):
    vertices,faces,coords = [],[],[]
    for center,radius,angle in cards:
        for turn in (0,math.pi/2):
            direction = Vector((math.cos(angle+turn),math.sin(angle+turn),0))*radius
            up = Vector((0,0,radius))
            start = len(vertices)
            vertices.extend((center-direction-up,center+direction-up,center+direction+up,center-direction+up))
            faces.append((start,start+1,start+2,start+3))
            coords.extend(((0,0),(1,0),(1,1),(0,1)))
        # An oblique card also keeps the canopy legible from an aerial inspection.
        start = len(vertices)
        across = Vector((math.cos(angle),math.sin(angle),0))*radius
        along = Vector((-math.sin(angle),math.cos(angle),.28))*radius
        vertices.extend((center-across-along,center+across-along,center+across+along,center-across+along))
        faces.append((start,start+1,start+2,start+3))
        coords.extend(((0,0),(1,0),(1,1),(0,1)))
    mesh = bpy.data.meshes.new(label)
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    mesh.materials.append(material_value)
    uv = mesh.uv_layers.new()
    for loop in mesh.loops:
        uv.data[loop.index].uv = coords[loop.vertex_index]
    obj = bpy.data.objects.new(label,mesh)
    group.objects.link(obj)


def planting(scene,materials,bed_map):
    for code,court in COURTS.items():
        cards,leaf_cards = [],[]
        plant = Planting(scene)
        plant.group.name = "C1 樱花园 · 分枝与实拍花簇" if code=="C1" else code+" 庭院分层乔灌木"
        plant.palette["white"] = materials["white"]
        # Dense low foliage follows the traced island outline, leaving the paved middle open.
        for bed in bed_map[code]:
            ring = LineString(bed.exterior.coords)
            for along in np.arange(0,ring.length,.34/SCALE):
                center = world(ring.interpolate(along).coords[0])+Vector((0,0,.67))
                leaf_cards.append((center,plant.rng.uniform(.12,.18),plant.rng.uniform(0,math.tau)))
            # Small ground cover patches retain visible earth around the trunks.
            x0,y0,x1,y1 = bed.bounds
            for _ in range(round(bed.area*.07)):
                p = Point(plant.rng.uniform(x0,x1),plant.rng.uniform(y0,y1))
                if bed.contains(p):
                    plant.crown("林下地被","deep",world(p.coords[0])+Vector((0,0,.20)),.24,.21,.10)
        for i,xy in enumerate(court["trees"]):
            if not any(bed.buffer(1).contains(Point(xy)) for bed in bed_map[code]):
                raise ValueError(f"Tree outside planting island: {code} {xy}")
            kind = "cherry" if code=="C1" and i%3!=1 else "leaf"
            height = (3.8+(i%3)*.36) if kind=="cherry" else (5.5+(i%4)*.55)
            tree(plant,xy,height,kind,cards,leaf_cards)
        plant.finish()
        for obj in plant.group.objects:
            for face in obj.data.polygons:
                face.use_smooth = True
        if cards:
            foliage_cards(plant.group,materials["flowers"],cards,code+" 实拍透明樱花花簇")
        foliage_cards(plant.group,materials["leaves"],leaf_cards,code+" 实拍树叶分枝簇")


def fixtures(scene,materials):
    site = SiteDetails(scene,materials)
    bridge = site.zone("C1 深灰桥头实拍展板与落水管",(749.5,380))
    orient(bridge,(737,352),(762,408))
    span = (world((762,408))-world((737,352))).length
    glass_w = (span-2.50)/2
    for side in (-1,1):
        for sign in (-1,1):
            x = sign*(1.25+glass_w/2)
            panel(bridge,"桥侧实拍反射玻璃","bridgeglass",x,side*1.72,5.48,glass_w,2.41)
            for z in (4.28,4.90,5.53,6.18,6.70):
                bridge.box("实拍玻璃外横梃","metal",x,side*1.75,z,glass_w,.055,.048)
            for xx in np.arange(x-glass_w/2,x+glass_w/2,.95):
                bridge.box("实拍玻璃外竖梃","metal",xx,side*1.75,5.48,.045,.055,2.41)
    for i,x in enumerate((4.0,7.4,10.7)):
        bridge.box("展板银框","cream",x,-1.93,1.18,2.77,.10,1.20)
        panel(bridge,"桥下实拍展板"+str(i+1),"board"+str(i+1),x,-1.99,1.18,2.63,1.06)
        for dx in (-1.15,1.15):
            bridge.box("展板落地支腿","metal",x+dx,-1.94,.43,.045,.075,.60)
    bridge.box("桥头白色雨水立管","white",-.93,-1.92,3.75,.072,.085,7.12)
    bridge.box("落水管顶弯接头","white",-.93,-1.88,7.27,.125,.17,.12)
    for z in (.5,2.2,4.0,5.8):
        bridge.box("落水管抱箍","metal",-.93,-1.92,z,.105,.11,.038)
    bridge.finish()
    # Grates are located at the ends and low points visible in the paving photographs.
    for code,xy in (("C1",(750,386)),("C2",(550,291)),("C3",(516,214))):
        item = site.zone(code+" 小型排水格栅",xy)
        item.box("格栅边框","iron",0,0,.161,.85,.31,.032)
        for x in np.linspace(-.36,.36,12):
            item.box("格栅条","curb",x,0,.181,.026,.26,.021)
        item.finish()
    # Dining-hall frontage has rectangular concrete planters, kept clear of the road.
    for xy in ((528,166),(545,167),(562,168)):
        item = site.zone("C3 餐厅侧矩形矮花池",xy)
        item.box("花池混凝土脚","curb",0,0,.29,2.42,.94,.38)
        item.box("花池植土","soil",0,0,.49,2.27,.79,.06)
        for x in np.linspace(-.95,.95,7):
            item.box("整形方绿篱","green",x,0,.67,.37,.81,.40)
        item.finish()


def preview_and_evidence(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = 850
    cameras = {}
    for tag,code,sid,angle,eye,target,aim,lens,height in VIEWS:
        view = camera(scene,tag,eye,target,aim,lens,height)
        cameras[tag] = view
        scene.camera = view
        scene.render.filepath = str(OUT/"模型视角"/(tag+".png"))
        bpy.ops.render.render(write_still=True)
    overview = camera(scene,"三处庭院总览",(879,545),(637,292),0,39,161)
    scene.camera = overview
    scene.render.resolution_x,scene.render.resolution_y = 1450,1050
    scene.render.filepath = str(OUT/"三处庭院总览.png")
    bpy.ops.render.render(write_still=True)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",20)
    for code,court in COURTS.items():
        pairs = [v for v in VIEWS if v[1]==code]
        canvas = Image.new("RGB",(1440,1510),"#e8e6de")
        draw = ImageDraw.Draw(canvas)
        draw.text((18,14),court["name"],fill="#24322a",font=font)
        draw.text((18,46),"上行为素材参照，下行为模型视角；相机位置与遮挡仍需逐站校准",fill="#24322a",font=font)
        for i,(tag,_,sid,angle,*_) in enumerate(pairs):
            x = 12+i*714
            draw.text((x,78),f"{sid}/{angle} · {tag}",fill="#24322a",font=font)
            for row,path in enumerate((reference(sid,angle),OUT/"模型视角"/(tag+".png"))):
                im = Image.open(path).convert("RGB")
                canvas.paste(ImageOps.fit(im,(700,680)),(x,112+row*695))
        canvas.save(OUT/(code+"_实景与模型对照.png"))
    aerial = Image.open(ROOT/"成果/第2轮/航拍重投影.png").convert("RGB")
    draw = ImageDraw.Draw(aerial)
    for (code,court),color in zip(COURTS.items(),("#ff90cf","#31ffee","#ffdc45")):
        ring = [tuple(p) for p in court["outline"]]
        draw.line(ring+[ring[0]],fill=color,width=3)
        for bed in court["beds"]:
            draw.line([tuple(p) for p in bed]+[tuple(bed[0])],fill=color,width=1)
        draw.text(ring[0],code,fill=color,font=font,stroke_width=2,stroke_fill="#15221b")
    aerial.crop((385,142,805,460)).resize((1680,1272)).save(OUT/"三处庭院航拍描边.png")
    return cameras


def unwrap_textured_boxes(objects):
    for obj in objects:
        if obj.type!="MESH" or obj.data.uv_layers or not obj.data.materials:
            continue
        mat = obj.data.materials[0]
        if not mat.use_nodes or not any(n.type=="TEX_IMAGE" for n in mat.node_tree.nodes):
            continue
        period = mat.get("UV周期米",1.0)
        uv = obj.data.uv_layers.new()
        for face in obj.data.polygons:
            axis = max(range(3),key=lambda index:abs(face.normal[index]))
            axes = ((1,2),(0,2),(0,1))[axis]
            for loop_index in face.loop_indices:
                point = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                uv.data[loop_index].uv = (point[axes[0]]/period,point[axes[1]]/period)


def validate(scene,original_names,removed):
    new = [o for o in scene.objects if o.name not in original_names and o.type=="MESH"]
    bad = [o.name for o in new if any(not math.isfinite(v) for p in o.data.vertices for v in p.co)]
    degenerate = {o.name:sum(p.area<1e-9 for p in o.data.polygons) for o in new}
    degenerate = {k:v for k,v in degenerate.items() if v}
    images = [n.image for m in bpy.data.materials if m.name.startswith(("三处庭院实拍","实拍樱花"))
              and m.use_nodes for n in m.node_tree.nodes if n.type=="TEX_IMAGE" and n.image]
    missing = [im.name for im in images if not im.packed_file]
    missing_uv = [o.name for o in new if not o.data.uv_layers and any(
        m and m.use_nodes and any(n.type=="TEX_IMAGE" for n in m.node_tree.nodes) for m in o.data.materials)]
    record = {"新增网格":len(new),"新增顶点":sum(len(o.data.vertices) for o in new),
              "新增实拍图像":len(images),"未打包图像":missing,"实拍材质缺UV网格":missing_uv,
              "非有限顶点":bad,"新增退化面":degenerate,
              "删除旧粗长立面及庭院面":removed,
              "场景总顶点":sum(len(o.data.vertices) for o in scene.objects if o.type=="MESH"),
              "说明":"庭院面积、树位、遮挡立面开间与楼高依据航拍及可见构件估算，等待实测修订"}
    if missing or missing_uv or bad or degenerate:
        raise ValueError(record)
    (OUT/"模型验收记录.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ("实拍贴图","模型视角"):
        (OUT/name).mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene = bpy.context.scene
    original_names = {o.name for o in scene.objects}
    removed = clean_previous(scene)
    materials = prepare_materials()
    bed_map = ground_and_beds(scene,materials)
    facades(scene,materials)
    planting(scene,materials,bed_map)
    fixtures(scene,materials)
    unwrap_textured_boxes([o for o in scene.objects if o.name not in original_names])
    clean_generated_meshes([o for o in scene.objects if o.name not in original_names])
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.15
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.42,.60,.78,1)
    scene.view_settings.exposure = .65
    validate(scene,original_names,removed)
    record = {"用户确认":"樱花园、思远与志远之间、志远北侧至餐厅之间，2026-11-15",
              "母版":str(SOURCE),"网站入口":"https://www.720yun.com/t/84vkb78yz8w?scene_id=94229759",
              "网站入口场景":"14 学生劳动课程基地，沿公寓北围墙，已与三处庭院分开定位",
              "三处庭院":COURTS,"贴图四点与周期":SAMPLES,"相机":VIEWS,
              "精度状态":"道路与花坛按航拍描边；照片清楚处细化实物，遮挡树位及开间沿同楼规律估算"}
    (OUT/"三处庭院定位与来源.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB",export_cameras=False,export_lights=False)
    cameras = preview_and_evidence(scene)
    scene.camera = cameras["C1_东端桥头"]
    scene.render.resolution_x = scene.render.resolution_y = 850
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    print("COURTYARDS_COMPLETE",str(OUT))


if __name__=="__main__":
    main()
