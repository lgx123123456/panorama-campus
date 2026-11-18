"""Rebuild the side gate and north campus drive from matched panorama stations."""

import json
import math
import random

import bpy
import bmesh
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from 三处庭院实拍细化 import foliage_cards, panel, unwrap_textured_boxes
from 公寓与运动区实拍细化 import front_panel, rod, segment
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 四栋教学楼实景细化 import reference
from 图书馆照片还原 import CAL, PLAN, material, open_campus, world
from 地面街道实景细化 import Ground
from 楼间过道实拍细化 import ROUND_CENTER, ROUND_RADIUS, camera, clean_generated_meshes
from 孔德广场与两侧花园 import OUT as PREVIOUS, STEM as PREVIOUS_STEM, raised, tree_shape
from 尚德广场实拍细化 import photo_material


OUT = PREVIOUS.parent / "西门至孔德广场沿线实拍细化"
SOURCE = PREVIOUS / (PREVIOUS_STEM+".blend")
STEM = "校园室外_西门至孔德广场"
SCALE = CAL["metres_per_pixel"]
GATE = (1044,166)
GATE_STATION = (1019.5,168.3)
HOMOGRAPHY = [
    [.4434771694,.2349917413,135.7998443],
    [-.0230985372,.5045694807,-730.9363320],
    [.0000005809566,.00026177135,.6199080],
]
ROAD = ((1060,166),(1044,166),(1028,166),(1019,165),(1006,160),(985,156),(949,155),
        (912,155),(882,151),(846,148),(810,148),(777,154),(743,156),(706,155),
        (671,157),(639,162),(603,165),(576,169),(545,175),(513,178),(476,177),
        (441,177),(412,179),(401,186),(399,194))
COUNTS = {
    646:("13/315",413),647:("28/045",69),648:("25/270",59),
    649:("02航拍",347),650:("28/090",382),651:("28/135",387),
    652:("28/045",346),653:("28/000",265),654:("28/315",278),
    655:("28/225",376),656:("25/045",342),657:("25/090",299),
    658:("25/180",307),659:("25/225",246),660:("25/000",88),
    661:("餐厅前直路及两侧树带，补充照片",None),662:("12/000",315),
    663:("02航拍，同组视角",None),664:("12/045",236),
    665:("12/090",254),666:("12/135",227),667:("12/180",318),
    668:("12/225",255),669:("12/315",270),670:("24/270",217),
    671:("24/180",231),672:("24/090",314),673:("24/000",182),
    674:("24/090",369),675:("22/045",299),676:("22/270",214),
    677:("15/135",340),678:("15/315",329),
}
VIEWS = (
    ("01_西门及宿舍端头","13","135",(1019,165),(1044,166),1.87,18,1.64),
    ("02_入西门沿蕙远楼","13","315",(1022,166),(952,155),1.85,19,1.64),
    ("03_圆弧玻璃楼旁回望西门","28","225",(891,168),(1019,164),1.75,18,1.64),
    ("04_女生公寓与柱廊通道","28","090",(888,153),(852,159),1.92,18,1.64),
    ("05_绅远楼对面架空通道","25","180",(676,151),(677,177),2.08,18,1.64),
    ("06_攀桂轩与宿舍端墙","12","090",(613,180),(578,148),2.20,18,1.64),
    ("07_餐厅出口与前场","24","000",(528,184),(532,155),2.64,19,1.64),
    ("08_沿餐厅前道路往孔德广场","24","090",(516,176),(401,188),2.10,19,1.64),
    ("09_西门至孔德广场全段","","",(776,421),(728,174),0,25,310),
)
# Perspective control points measured on the 780-pixel panorama proxies.
SAMPLES = {
    "细纹混凝土":("28","225",[(529,598),(682,597),(733,751),(551,751)],(600,500),3.5),
    "错缝红灰砖":("12","090",[(289,568),(381,562),(497,732),(208,749)],(512,480),3.0),
    "门卫房白墙":("13","135",[(543,357),(563,355),(563,392),(543,393)],(220,255),1.4),
    "勤奋题字":("13","000",[(357,408),(434,412),(438,452),(350,451)],(380,190),1),
    "餐厅勤俭节约":("22","000",[(138,289),(261,283),(260,319),(137,323)],(620,180),1),
    "餐厅中华美德":("24","000",[(510,221),(743,224),(743,273),(509,271)],(850,182),1),
    "餐厅入口字样":("24","000",[(342,260),(435,263),(435,294),(342,292)],(460,142),1),
    "食堂蓝色公告":("24","000",[(502,356),(564,357),(563,391),(501,391)],(360,201),1),
    "柱廊窗帘":("28","135",[(114,98),(184,137),(185,190),(113,150)],(380,300),1.2),
}


def materials():
    palette={
        "stone":(.48,.46,.41),"pale":(.71,.707,.64),"charcoal":(.095,.109,.116),
        "dark":(.046,.057,.061),"ochre":(.72,.38,.068),"ochre_dark":(.56,.263,.041),
        "green":(.052,.153,.093),"shed":(.039,.218,.153),"metal":(.12,.15,.163),
        "silver":(.52,.55,.56),"brown":(.267,.144,.068),"roof":(.143,.110,.083),
        "glass":(.105,.263,.366),"yellow":(.80,.492,.073),"black":(.036,.046,.049),
        "red":(.65,.06,.035),"blue":(.051,.154,.349),"white":(.78,.762,.704),
    }
    mats={k:material("西门沿线 · "+k,rgb,.71) for k,rgb in palette.items()}
    for key,(sid,angle,controls,size,period) in SAMPLES.items():
        with Image.open(reference(sid,angle)) as image:
            photo=np.asarray(image.convert("RGB"))
        src=np.float32(controls)*np.float32((photo.shape[1]/780,photo.shape[0]/780))
        w,h=size
        dst=np.float32(((0,0),(w-1,0),(w-1,h-1),(0,h-1)))
        pixels=cv2.warpPerspective(photo,cv2.getPerspectiveTransform(src,dst),size)
        if period>1:
            raw=pixels.astype(np.float32)
            low=cv2.GaussianBlur(raw,(0,0),max(10,min(size)/11))
            pixels=np.clip(raw+.80*(np.median(low,axis=(0,1))-low),0,255).astype(np.uint8)
        if key=="细纹混凝土":
            yy,xx=np.mgrid[:h,:w]
            edge=np.minimum.reduce((yy,xx,h-1-yy,w-1-xx))
            blend=np.clip(edge/52,0,1)[:,:,None]
            pixels=(pixels*blend+np.median(pixels,axis=(0,1))*(1-blend)).astype(np.uint8)
        path=OUT/"实拍贴图"/(key+".png")
        Image.fromarray(pixels).save(path)
        tex=bpy.data.images.load(str(path))
        tex.pack()
        mats[key]=photo_material(key,tex,(.38,.40,.39),.88,period)
        mats[key].name="西门沿线实拍 · "+key
    mats["绿棚半透顶"]=material("西门沿线 · 绿色透光棚板",(.07,.41,.252),.31)
    bsdf=mats["绿棚半透顶"].node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value=.59
    mats["绿棚半透顶"].surface_render_method="DITHERED"
    mats["旗面红"]=bpy.data.materials["孔德广场实拍 · 旗帜红"]
    mats["旗面黄"]=bpy.data.materials["孔德广场实拍 · 旗帜黄"]
    return mats


def remove_placeholders(scene):
    removed=set()
    names={"公寓南侧连续步道","公寓道路连续道牙"}
    for collection in list(scene.collection.children):
        if collection.name.startswith(("西门道路旁 · 绿色棚架","A09 篮球场—餐厅—绅远楼 · 地坪",
                                       "A10 绅远楼—蕙远楼—图书馆背面 · 地坪")):
            removed.update(collection.objects.keys())
            for obj in list(collection.objects):
                bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.collections.remove(collection)
    for obj in list(scene.objects):
        if obj.name.startswith(("P13_offsite_gate_","P13_planters_","P13_walk_connection","西门支路减速垄")) or obj.name in names:
            removed.add(obj.name)
            bpy.data.objects.remove(obj,do_unlink=True)
    # These sign planes belonged to the generic dining model with the doors in reverse order.
    dining=scene.collection.children.get("B22 餐厅 · 外立面")
    if dining:
        names=("B22 入口标语","B24 出口标语","B22 标语牌独立衬底")
        for obj in list(dining.objects):
            if obj.name.startswith(names):
                removed.add(obj.name)
                bpy.data.objects.remove(obj,do_unlink=True)
    return sorted(removed)


def road_surfaces(scene,mats):
    g=Ground(scene)
    g.materials.update(mats)
    g.region("西门至孔德广场连续车道、沿路道牙和铺装")
    axis=LineString(ROAD)
    build=unary_union([Polygon(b["outline"]) for b in PLAN["buildings"]])
    round_house=Point(ROUND_CENTER).buffer(ROUND_RADIUS/SCALE+.8)
    obstacles=build.union(round_house)
    route=axis.buffer(6.55,cap_style="flat",join_style="round").difference(obstacles)
    dining=Polygon(((394,163),(454,168),(514,166),(563,169),(572,188),(527,195),(421,186),(393,182)))
    aprons=unary_union((
        dining,Polygon(((864,155),(893,155),(915,157),(924,175),(908,181),(887,173),(869,169))),
        Polygon(((651,145),(687,145),(689,167),(650,170))),
        Polygon(((1029,155),(1043,151),(1063,155),(1063,178),(1040,181),(1025,178))),
    )).difference(obstacles)
    # Leave the concrete forecourts and the asphalt-free campus drive continuous at intersections.
    g.surface("校园车行道浅灰混凝土","细纹混凝土",route,.126)
    g.surface("西门、公寓和餐厅入口连续前坪","细纹混凝土",aprons.difference(route),.125)
    for side in (-1,1):
        outer=axis.offset_curve(side*7.05)
        curb=outer.buffer(.22,cap_style="flat").difference(obstacles.union(aprons))
        raised(g,"路侧石道牙","stone",curb,.116,.173)
    brick=axis.buffer(11.9,cap_style="flat").difference(axis.buffer(7.08,cap_style="flat"))
    g.surface("红灰砖慢行步道","错缝红灰砖",brick.difference(obstacles.union(aprons)),.151)
    for dist in np.arange(9,axis.length-2,14):
        pt=axis.interpolate(dist)
        q=axis.interpolate(dist+.04)
        dx,dy=q.x-pt.x,q.y-pt.y
        span=math.hypot(dx,dy)
        a,b=(pt.x-dy/span*6.35,pt.y+dx/span*6.35),(pt.x+dy/span*6.35,pt.y-dx/span*6.35)
        line=LineString((a,b)).buffer(.024).intersection(route)
        g.surface("浅横向切缝","joint",line,.129)
    for a,b in zip(ROAD[-8:-1],ROAD[-7:]):
        g.dash("餐厅外白色短虚线","white",a,b,.075,4.8,6.55,.130)
    for center,end in ((425,191),(532,191),(673,168)):
        for y in range(end-24,end,4):
            for side in (-1,1):
                x=center+side*4.4
                bar=box(x-2.36,y-.13,x+2.36,y+.13).intersection(route.union(aprons))
                g.surface("门前两列黄色短标线","yellow",bar,.132)
    for x,y in ((1030,164),(1005,158),(906,156),(820,148),(745,156),(674,157),(540,176),(428,175)):
        g.cover("金属检修井盖",(x,y),.133,.37)
    for i in range(17):
        y=158.5+i*.75
        raised(g,"西门黑黄减速胶带", "yellow" if i%2 else "black",
               box(1016.82,y,1017.74,y+.744),.127,.193)
    for x,y in ((1038,174),(1026,157),(899,173),(877,155),(598,174),(419,184),(522,162)):
        item=SiteDetails(scene,mats).zone("路边横向雨水箅",(x,y))
        item.box("排水槽铸铁框","dark",0,0,.136,.72,.33,.022)
        for j in range(10):
            item.box("格栅分条","metal",(j-4.5)*.063,0,.151,.028,.29,.012)
        item.finish()
    g.build()


def gate_and_canopy(scene,site,mats):
    gate,width=segment(site,"西门 · 绿色拱形栏门与浅石柱",(1044,158.7),(1044,173.3))
    for x in (-width/2,width/2):
        gate.box("浅石方门柱","stone",x,0,1.49,.54,.58,2.72)
        gate.box("门柱平石帽","pale",x,0,2.885,.64,.67,.115)
        gate.box("门柱腰部深绿色分格","green",x,-.30,1.59,.52,.032,.13)
    for sign in (-1,1):
        a=(0 if sign>0 else -width/2+.20)
        b=(width/2-.20 if sign>0 else 0)
        for z in (.33,.75,1.62):
            rod(gate,"门扇横框","green",(a,0,z),(b,0,z),.040)
        positions=np.linspace(a,b,17)
        top=lambda x: 2.68+.29*(1-(2*x/width)**2)
        for x in positions:
            rod(gate,"深绿色竖条栏门","green",(x,0,.35),(x,0,top(x)),.024)
        for l,r in zip(positions,positions[1:]):
            rod(gate,"拱形门扇上缘","green",(l,0,top(l)),(r,0,top(r)),.037)
    gate.finish()
    booth=site.zone("西门 · 红檐白色门卫房",(1038,176.5))
    b=booth.box
    b("门卫房白色板墙","门卫房白墙",0,0,1.42,3.78,2.82,2.51)
    b("门卫房灰底","stone",0,0,.21,3.86,2.90,.17)
    for x in (-1.84,1.84):
        for y in (-1.40,1.40):
            b("红色收边角铁","red",x,y,1.43,.095,.10,2.61)
    for sign in (-1,1):
        a=booth.point(-2.07,0,3.07); c=booth.point(2.07,0,3.07)
        d=booth.point(2.07,sign*1.63,2.74); e=booth.point(-2.07,sign*1.63,2.74)
        booth.link("红边浅色坡屋顶",[a,c,d,e],[(0,1,2,3)],mats["roof"])
        rod(booth,"红色坡檐","red",(-2.13,sign*1.63,2.73),(2.13,sign*1.63,2.73),.061)
        for x in (-2.08,2.08):
            rod(booth,"红色山面压边","red",(x,0,3.09),(x,sign*1.65,2.73),.057)
    for y in (-1.429,1.429):
        b("小窗玻璃","glass",-.17,y,1.66,1.09,.072,.80)
        for x in (-.73,-.17,.38):
            b("门卫房小窗细框","pale",x,y*1.013,1.66,.040,.071,.84)
        for z in (1.24,1.67,2.08):
            b("门卫房小窗横饰条","pale",-.17,y*1.016,z,1.14,.049,.038)
    b("房门玻璃","glass",-1.90,.2,1.31,.08,.90,2.14)
    booth.finish()
    canopy,length=segment(site,"西门内绿色车棚",(1023,99),(1029,153))
    radius=2.87
    for x in np.arange(-length/2,length/2+.20,2.2):
        for y in (-radius,radius):
            rod(canopy,"青绿色钢柱","shed",(x,y,.14),(x,y,2.1),.058)
        band=[(x,y,2.10+.72*(1-(y/radius)**2)) for y in np.linspace(-radius,radius,19)]
        for a,b in zip(band,band[1:]):
            rod(canopy,"拱形车棚肋","shed",a,b,.044)
    for y in np.linspace(-radius,radius,9):
        z=2.10+.72*(1-(y/radius)**2)
        rod(canopy,"车棚连续檩条","shed",(-length/2,y,z),(length/2,y,z),.032)
    roof=[canopy.point(x,y,2.13+.72*(1-(y/radius)**2)) for y in np.linspace(-radius,radius,25)
          for x in (-length/2-.18,length/2+.18)]
    canopy.link("弯弧绿色半透明棚面",roof,[(j,j+1,j+3,j+2) for j in range(0,48,2)],mats["绿棚半透顶"])
    for x in np.arange(-length/2+.30,length/2,.54):
        rod(canopy,"车棚停车分隔弯架","silver",(x,-2.43,.16),(x,-1.90,.54),.020)
        rod(canopy,"车棚停车分隔弯架","silver",(x,-1.90,.54),(x,-1.49,.16),.020)
    canopy.finish()
    g=Ground(scene)
    g.materials.update(mats)
    g.region("西门入口小园、车棚地坪和砖径")
    g.surface("车棚浅混凝土底面","细纹混凝土",LineString(((1023,98),(1029,154))).buffer(7.2),.105)
    garden=Polygon(((1008,175),(1025,173),(1034,177),(1046,181),(1044,204),
                    (1032,218),(1009,212),(996,196)))
    walk=LineString(((1002,173),(1009,183),(1018,188),(1032,193),(1046,198))).buffer(1.9)
    g.surface("西门入口小园地被","soil",garden.difference(walk),.145)
    g.surface("西门小园弯砖径","错缝红灰砖",walk,.153)
    g.build()
    rock=site.zone("西门花园勤奋题石",(1015,177))
    bm=bmesh.new()
    bmesh.ops.create_icosphere(bm,subdivisions=3,radius=1)
    for v in bm.verts:
        x,y,z=v.co
        v.co=rock.point(.95*x+.08*z,.47*y,min(1.4,max(.15,.74+.65*z+.054*math.cos(8*x+3*y))))
    data=bpy.data.meshes.new("西门勤奋天然石")
    bm.to_mesh(data)
    bm.free()
    obj=bpy.data.objects.new("西门勤奋天然石",data)
    rock.collection.objects.link(obj)
    data.materials.append(mats["stone"])
    panel(rock,"勤奋红字实拍刻面","勤奋题字",0,-.477,.793,1.06,.56)
    rock.finish()
    shelter=site.zone("西门小园 · 木构休息亭",(1032,196))
    for x in (-1.36,1.36):
        for y in (-1.30,1.30):
            shelter.box("小园木亭立柱","brown",x,y,1.44,.15,.17,2.53)
        shelter.box("小园木亭横梁","brown",x,0,2.65,.19,2.85,.18)
    for y in (-1.30,1.30):
        shelter.box("小园木亭纵梁","brown",0,y,2.65,2.97,.19,.18)
        shelter.box("侧边靠栏木坐板","brown",0,y,.62,2.32,.35,.10)
    eaves=[shelter.point(x,y,2.75) for x,y in ((-1.67,-1.63),(1.67,-1.63),(1.67,1.63),(-1.67,1.63))]
    crown=shelter.point(0,0,3.78)
    shelter.link("四坡深色木亭瓦顶",eaves+[crown],[(i,(i+1)%4,4) for i in range(4)],mats["roof"])
    shelter.box("小园木亭石基","stone",0,0,.216,3.25,3.17,.16)
    shelter.finish()


def raised_gallery(site,label,a,b,levels,open_width):
    wing,length=segment(site,label,a,b)
    bld=wing.box
    depth=3.25
    for z,key in ((3.24,"ochre"),(6.89,"ochre_dark"),(9.91,"ochre"))[:levels]:
        height=.94 if z==3.24 else .64
        bld("深进深平台和橙黄檐带",key,0,0,z,length+.08,depth,height)
    bld("沿线深灰檐底","dark",0,.02,2.738,length,depth,.07)
    parts=max(3,round(length/3.5))
    pitch=length/parts
    for i in range(parts+1):
        x=i*pitch-length/2
        if abs(x)>open_width/2:
            for y in (-1.20,1.17):
                rod(wing,"柱廊圆形清水混凝土柱","charcoal",(x,y,.15),(x,y,2.93),.178,14)
        for z in (5.0,8.27)[:levels-1]:
            bld("楼层灰色竖柱","charcoal",x,1.11,z,.26,.37,2.83)
        if i<parts:
            front_panel(wing,"实拍窗帘可见玻璃带","柱廊窗帘",x+pitch/2,1.249,5.02,pitch-.22,2.61)
            for k in (.0,.32,.67):
                bld("实拍窗带细竖梃","metal",x+k*pitch,1.285,5.02,.057,.09,2.64)
    for z in (3.77,6.56):
        bld("窗带银灰横梃","metal",0,1.3,z,length,.085,.066)
    for z in (7.39,7.70,7.97):
        if levels>2:
            rod(wing,"上层敞开廊栏杆","silver",(-length/2,1.36,z),(length/2,1.36,z),.027)
    for side in (-1,1):
        outer=(side*length/2,side*open_width/2)
        for z in (.45,.76,1.05):
            rod(wing,"首层银色通透栏杆","silver",(outer[0],1.20,z),(outer[1],1.20,z),.023)
        for x in np.linspace(*outer,max(2,round((length-open_width)/2)+1)):
            rod(wing,"首层通透栏杆立柱","silver",(x,1.20,.15),(x,1.20,1.05),.024)
    wing.finish()


def frontage(site):
    # These raised structures occupy the open side of the drive as seen from 25 and 28.
    raised_gallery(site,"蕙远楼对面 · 圆弧楼相接架空柱廊",(873,162),(904,177),3,4.5)
    for a,b in (((824,153.2),(842,151.9)),((842,151.9),(872,155.5)),((872,155.5),(890,165.1))):
        north,length=segment(site,"图书馆北侧 · 公寓路外立面与檐柱",a,b)
        north.box("灰色长墙衬底","charcoal",0,-.21,12.78,length,.60,13.84)
        north.box("宿舍路架空沿线黄腰带","ochre",0,.35,3.30,length+.12,1.10,.89)
        north.box("深灰檐底","dark",0,.29,2.82,length,1.03,.072)
        north.box("连续暖黄顶檐","ochre",0,.04,19.72,length+.08,.57,.49)
        pitch=length/max(2,round(length/1.67))
        for x in np.arange(-length/2+pitch*.5,length/2,pitch):
            for z in (6.25,9.52,12.79,16.08,18.20):
                north.box("窄竖窗玻璃","glass",x,.124,z,.62,.085,1.58)
                north.box("窄窗立框","metal",x-.32,.180,z,.048,.064,1.68)
            if round((x+length/2)/pitch)%3==0:
                rod(north,"圆柱支承黄檐","charcoal",(x,.62,.14),(x,.62,2.86),.142,12)
        north.finish()
    raised_gallery(site,"绅远楼对面 · 黄梁玻璃连廊",(643,181),(701,176),3,4.9)
    end,length=segment(site,"绅远楼靠餐厅端面 · 橙黄色楼梯台",(592,141),(579,122))
    end.box("高端整面橙黄板墙","ochre",0,.27,11.94,length,.59,23.54)
    for z in np.arange(1.65,23.1,1.49):
        end.box("橙黄面板水平分缝","ochre_dark",0,.573,z,length,.015,.016)
    for z in (4.93,8.59,12.26,15.93,19.59):
        end.box("楼梯层深窗","glass",length*.24,.573,z,2.15,.12,1.76)
        end.box("灰色挑出台阶平台","charcoal",length*.24,.90,z-.64,2.24,.89,.28)
        for k in range(8):
            x=length*.24+(k-3.5)*.25
            rod(end,"楼梯平台细栏杆","silver",(x,1.29,z-.52),(x,1.29,z+.33),.019)
        rod(end,"楼梯台栏杆扶手","silver",(length*.24-.91,1.29,z+.33),(length*.24+.91,1.29,z+.33),.033)
    end.finish()
    side,length=segment(site,"攀桂轩路口 · 黄色侧墙和屋顶格架",(569,109),(571,161))
    side.box("食堂侧向橙色墙面","ochre",0,.12,3.25,length,.56,6.45)
    for x in np.linspace(-length/2+.68,length/2-.68,13):
        side.box("橙墙小方方窗","dark",x,.408,5.32,.44,.049,.43)
        side.box("橙墙竖向拼接缝","ochre_dark",x+.63,.405,3.2,.016,.012,6.3)
    for z in (1.32,2.52,3.74,4.95):
        side.box("橙墙横向拼接缝","ochre_dark",0,.407,z,length,.011,.018)
    for x in np.linspace(-length/2+.63,length/2-.63,11):
        side.box("上部露天架灰横梁","charcoal",x,-1.49,14.81,.17,3.49,.22)
    for y in (-3.19,.21):
        side.box("上部灰色长骨架","charcoal",0,y,14.87,length,.22,.28)
    side.finish()


def canteen(site):
    # Keep the roof and back wall. Fine south-side bays sit in front of the earlier placeholder face.
    item,length=segment(site,"餐厅入口及出口实拍外立面",(567,159.6),(392,154.6))
    # Orientation is reversed along the frontage so positive depth faces the campus drive.
    b=item.box
    if item.depth.y>0:
        item.across=-item.across
        item.depth=-item.depth
    doors=((-length*.31,"餐厅中华美德"),(length*.32,"餐厅勤俭节约"))
    b("上部连续深灰分格衬墙","charcoal",0,-.11,10.91,length,.30,11.16)
    b("暖黄屋面檐边","ochre",0,.11,16.55,length+.18,.31,.58)
    for i in range(24):
        x=(i-11.5)*length/24
        for z in (8.22,13.47):
            b("深灰窗洞侧框","metal",x,.014,z,2.71,.22,3.24)
            for j in (-1,0,1):
                b("高窗各扇玻璃","glass",x+j*.78,.156,z, .74,.078,2.97)
            for z1 in (z+.44,z-.52):
                b("玻璃分格横框","charcoal",x,.195,z1,2.42,.082,.071)
        b("通高外墙灰竖肋","charcoal",x-length/48,.21,10.93,.26,.36,11.03)
        if all(abs(x-door)>4.25 for door,_ in doors):
            b("食堂首层橙黄色板面","ochre",x,-.01,2.77,length/24-.026,.49,5.36)
            b("首层高深玻璃槽","dark",x,.253,2.14,.93,.028,2.86)
            b("槽窗深色玻璃","glass",x,.276,2.13,.77,.075,2.56)
            b("槽窗上口方亮窗","glass",x,.282,4.26,.67,.065,.55)
    for center,sign in doors:
        b("餐厅玻璃门深色后面","dark",center,-.20,2.12,5.54,.26,3.83)
        for i in range(6):
            x=center+(i-2.5)*.82
            b("餐厅门窗玻璃扇","glass",x,.23,1.91,.76,.09,3.24)
            b("槽口不锈钢门窗框","metal",x-.407,.286,1.91,.043,.071,3.39)
            b("玻璃门水平扶手","silver",x,.32,1.39,.68,.042,.039)
        for i in range(3):
            z=.14*(i+1)
            b("餐厅门前三步灰石阶","stone",center,1.42-i*.35,z/2+.125,5.84,.37,z)
        b("橙黄餐厅门楣","ochre",center,.18,4.44,6.10,.43,.83)
        front_panel(item,"实拍餐厅金色门名","餐厅入口字样",center,.406,4.45,2.32,.77)
        offset=-4.35 if sign=="餐厅中华美德" else 4.35
        b("红底标语独立薄板","red",center+offset,.28,5.58,5.18,.24,1.24)
        front_panel(item,"实拍红底标语",sign,center+offset,.412,5.58,5.15,1.20)
        front_panel(item,"门侧实拍蓝公告","食堂蓝色公告",center+offset,.294,2.26,1.16,.63)
    item.finish()


def landscaping(scene,site,mats):
    plant=Planting(scene)
    plant.group.name="西门沿线 · 行道树冠、绿篱和宿舍花树"
    plant.palette["white"]=mats["white"]
    rng=random.Random(4478)
    cards={"green":[],"light":[],"purple":[]}
    for i,x in enumerate(range(886,1017,9)):
        y=143+(x-886)*.067
        tree_shape(plant,(x,y),7.1+.42*(i%4),1.7,"green",cards,rng)
    for i,x in enumerate(range(594,777,14)):
        y=151+(620-x)*.022
        if abs(x-673)>8:
            tree_shape(plant,(x,y),6.5+.46*(i%3),1.7,"green",cards,rng)
    for i,p in enumerate(((1019,177),(1031,182),(1038,185),(1027,198),(1016,194),(1008,188),
                          (1011,183),(602,175),(616,176),(629,177),(651,178),(694,169),
                          (914,171),(929,169),(945,171),(974,168),(989,172),(1002,172),
                          (449,168),(471,169),(505,168),(542,167))):
        tree_shape(plant,p,3.8+.68*(i%5),1.4,"purple" if i%4==1 else "light",cards,rng)
    for points in (
        ((1030,173),(1041,177),(1047,180)),((1017,153),(1025,153),(1032,156)),
        ((916,165),(933,166),(949,165),(968,164),(990,165),(1002,169)),
        ((861,158),(875,163),(889,168)),((649,174),(662,174)),
        ((691,172),(703,171)),((612,177),(628,177),(637,175)),
    ):
        plant.hedge(points,.82)
    mats_by_type={
        "green":bpy.data.materials["孔德广场实拍 · 绿叶簇"],
        "light":bpy.data.materials["孔德广场实拍 · 浅绿叶簇"],
        "purple":bpy.data.materials["孔德广场实拍 · 紫叶簇"],
    }
    for key,positions in cards.items():
        foliage_cards(plant.group,mats_by_type[key],positions,"西门行道树 · "+key)
    for n,pt in enumerate(((1029,157),(1008,172),(979,151),(950,163),(916,146),(876,157),
                            (833,143),(793,146),(741,149),(700,162),(648,153),(603,171),
                            (564,179),(499,170),(453,170),(418,186))):
        item=site.zone("西门沿线太阳能灯与红黄旗",(pt))
        rod(item,"蓝色灯杆漆脚","blue",(0,0,.14),(0,0,.93),.061)
        rod(item,"白色太阳能灯杆","pale",(0,0,.89),(0,0,5.37),.050)
        rod(item,"灯头挑臂","metal",(0,0,4.74),(-.72,0,5.15),.032)
        item.box("纤长深蓝灯罩","blue",-.83,0,5.18,.32,.15,.076)
        if n<3:
            item.box("黑灰太阳能板背壳","charcoal",.22,0,5.44,.71,.49,.074)
        for x,key in ((-.32,"旗面红"),(.32,"旗面黄")):
            item.box("薄旗底衬","ochre_dark",x,0,3.27,.54,.029,1.15)
            panel(item,"双面实拍旗面",key,x,-.019,3.27,.53,1.13)
            front_panel(item,"双面实拍旗面",key,x,.019,3.27,.53,1.13)
        item.finish()
    plant.finish()


def render(scene,views):
    scene.render.engine="CYCLES"
    scene.cycles.samples=12
    scene.cycles.use_denoising=True
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
    for tag,sid,angle,*_ in VIEWS:
        scene.camera=views[tag]
        scene.render.resolution_x,scene.render.resolution_y=(1440,930) if not sid else (760,760)
        out=OUT/"模型视角"/(tag+".png")
        scene.render.filepath=str(out)
        bpy.ops.render.render(write_still=True)
        if sid:
            canvas=Image.new("RGB",(1540,825),"#ebeae2")
            draw=ImageDraw.Draw(canvas)
            draw.text((10,9),tag[3:],fill="#222d26",font=font)
            draw.text((10,37),f"实景全景 {sid}/{angle}°",fill="#222d26",font=font)
            draw.text((779,37),"Blender视角（站位估算）",fill="#222d26",font=font)
            for x,path in ((8,reference(sid,angle)),(774,out)):
                with Image.open(path) as image:
                    canvas.paste(ImageOps.fit(image.convert("RGB"),(760,760)),(x,61))
            canvas.save(OUT/"实景对照"/(tag+".jpg"),quality=94)


def main():
    for folder in ("实拍贴图","模型视角","实景对照"):
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    before=set(scene.objects.keys())
    removed=remove_placeholders(scene)
    mats=materials()
    site=SiteDetails(scene,mats)
    road_surfaces(scene,mats)
    gate_and_canopy(scene,site,mats)
    frontage(site)
    canteen(site)
    landscaping(scene,site,mats)
    new=[o for o in scene.objects if o.type=="MESH" and o.name not in before.difference(removed)]
    unwrap_textured_boxes(new)
    clean_generated_meshes(new)
    for obj in new:
        assert all(math.isfinite(v) for point in obj.data.vertices for v in point.co),obj.name
        assert all(face.area>=1e-9 for face in obj.data.polygons),obj.name
    cameras={tag:camera(scene,tag,eye,target,aim,lens,z) for tag,_,_,eye,target,aim,lens,z in VIEWS}
    scene.camera=cameras["09_西门至孔德广场全段"]
    scene.render.resolution_x,scene.render.resolution_y=1440,930
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")), export_format="GLB",export_cameras=False,export_lights=False)
    data={"续作母版":str(SOURCE),"学校文件夹照片对应":COUNTS,"航拍单应变换":HOMOGRAPHY,
          "西门站点":GATE_STATION,"西门栏门估计中心":GATE,"道路中心线":ROAD,
          "道路估计长度米":round(LineString(ROAD).length*SCALE,1),"相机":VIEWS,"贴图四点":SAMPLES,
          "替换旧对象":removed,"新增网格":len(new),
          "待测":"实际门线、栏门宽度、车棚长度、路宽、架空廊进深、车道接头及树木精确位置。"}
    (OUT/"定位与验收.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    render(scene,cameras)


if __name__=="__main__":
    main()
