"""Detail the remaining exterior blocks and reconstruct the campus landscape."""

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Point, Polygon, box

from 四栋教学楼实景细化 import Building, PALETTE, PLAN, reference
import 地面街道实景细化 as ground_tools
from 图书馆照片还原 import material, open_campus, world


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/"成果"/"地面街道实景细化"/"校园室外_地面街道细化.blend"
OUT = ROOT/"成果"/"剩余楼栋与景观细化"
BLOCKS = {
    "B22": ("22","餐厅",6,5, "dining"),
    "B25": ("25","绅远楼",5,4, "boys"),
    "B28": ("28","蕙远楼",5,4, "girls"),
    "B40W": ("40","艺远楼识远楼西翼",3,2, "wing"),
    "B40E": ("40","艺远楼识远楼东翼",3,2, "wing"),
    "B09A": ("09","体育区体块A",0,3, "sport"),
    "B09B": ("09","体育区体块B",1,0, "sport"),
}


def front(scene, key, record, materials):
    sid,name,i,j,kind=BLOCKS[key]
    a,b=map(world,(record["outline"][i],record["outline"][j]))
    front_edge={i,j}
    width=(a-b).length
    height=record["height"]
    # Only the front components are assigned using the ground panorama.
    obj = Building.__new__(Building)
    obj.anchor=(a+b)/2
    across=(b-a).normalized()
    depth=Vector((-across.y,across.x,0))
    middle=sum((world(p) for p in record["outline"]),Vector((0,0,0)))/len(record["outline"])
    if (middle-obj.anchor).dot(depth)<0:
        across,depth=-across,-depth
    obj.across,obj.depth=across,depth
    obj.width,obj.height,obj.sid,obj.name=width,height,sid,name
    obj.materials,obj.groups=materials,{}
    obj.collection=bpy.data.collections.new(key+" "+name+" · 外立面")
    scene.collection.children.link(obj.collection)
    b=obj.box
    base=3.8 if kind!="sport" else 3.15
    floors=record["floors"]-1 if kind!="sport" else 2
    level=(height-base-.75)/floors
    accent="ochre" if kind!="sport" else "sport_white"
    b("深灰立面内衬","slate",0,-.16,(height+base)/2,width,.36,height-base)
    b("首层裙墙底板",accent,0,-.26,base/2,width,.56,base)
    b("屋顶檐带",accent,0,-.43,height-.28,width+.14,.82,.55)
    half=width/2
    count=max(7,round(width/(2.65 if kind in {"boys","girls"} else 2.30)))
    pitch=width/count
    portals=([-width*.22,width*.22] if kind=="dining" else [0])
    if key=="B40W":
        portals=[width*.46]
    elif key=="B40E":
        portals=[-width*.44]
    entrance_width=6.6 if kind=="dining" else 4.3
    for f in range(floors):
        z=base+(f+.52)*level
        for i in range(count):
            x=-half+(i+.5)*pitch
            if kind in {"boys","girls"}:
                window_h=min(level*.55,1.56)
                window_w=pitch*.72
            else:
                window_h=level*.78
                window_w=pitch*.81
            glass="glass" if (i+2*f)%5 else "sideglass"
            b("分格玻璃",glass,x,-.39,z,window_w,.15,window_h)
            for m in (-1,0,1):
                b("窗竖梃","dark",x+m*window_w/2,-.488,z,.042,.065,window_h)
            b("窗横梃","dark",x,-.491,z+window_h*.16,window_w,.064,.068)
            if kind in {"boys","girls"} and (i+f)%3==0:
                ax=x+pitch*.34
                b("空调外机","white",ax,-.62,z-.48,.67,.38,.43)
                for j in range(4):
                    b("外机散热缝","slate",ax,-.817,z-.61+j*.083,.53,.015,.022)
        b("层间横梁","slate",0,-.50,base+(f+.96)*level,width,.45,.27)
    for i in range(count+1):
        x=-half+i*pitch
        stripe=accent if kind=="wing" and i%4==0 else "slate"
        b("窗间竖柱",stripe,x,-.49,(height+base)/2,.29 if stripe=="slate" else .72,.63,height-base)
        if i<count and all(abs(x+pitch*.5-center)>entrance_width*.67 for center in portals):
            b("下层窗带","glass",x+pitch/2,-.57,1.80,pitch*.74,.14,1.41)
            if kind in {"boys","girls"}:
                for j in range(6):
                    b("首层金属栏杆","silver",x+pitch/2+(j-2.5)*pitch*.112,-.68,1.80,.028,.046,1.42)
    for index,x in enumerate(portals):
        bottom=.46 if kind=="girls" else .30
        b("入口玻璃门洞","dark",x,-.63,1.82,entrance_width,.14,2.78)
        for j in range(5):
            leaf=x+(j-2)*entrance_width/5
            b("入口玻璃扇","glass",leaf,-.73,1.77,entrance_width/5-.085,.09,2.55)
            b("不锈钢门柱","silver",leaf-entrance_width/10,-.79,1.76,.065,.09,2.65)
        b("门上横梁","slate",x,-.76,3.18,entrance_width+.21,.23,.23)
        for j in range(3):
            step=bottom*(j+1)/3
            b("入口石阶","stone",x,-1.88+j*.31,step/2,entrance_width+.61,.35,step)
        b("入口平台","stone",x,-.99,bottom/2,entrance_width+.6,1.52,bottom)
        if kind in {"boys","girls"}:
            b("玻璃门廊顶","sideglass",x,-1.65,3.74,entrance_width+.99,2.48,.14)
            for j in range(6):
                b("门廊玻璃撑梁","silver",x+(j-2.5)*.80,-1.62,3.68,.074,2.42,.112)
            quad=((235,215),(461,215),(461,259),(235,259)) if kind=="boys" else (
                  (217,203),(468,203),(468,251),(217,251))
            obj.photo_panel("公寓实拍门头","000",quad,x,-.695,5.55,entrance_width-.33,.75)
        elif kind=="dining":
            if index==0:
                quad=((120,252),(230,244),(231,284),(120,293))
                heading="入口标语"
                image="000"
            else:
                quad=((475,202),(690,202),(690,256),(475,256))
                heading="出口标语"
                image="000"
                obj.sid="24"
            b("标语牌独立衬底","red",x,-.96,5.05,entrance_width+.08,.16,1.02)
            obj.photo_panel(heading,image,quad,x,-1.05,5.05,entrance_width,.95)
            obj.sid=sid
        elif kind=="wing":
            for z in (5.2,8.7,12.2,15.7):
                b("侧廊凹口","dark",x,-.80,z,entrance_width*.68,.16,2.42)
                obj.railing("侧廊栏杆",x-1.24,x+1.24,-.86,z-1.18,.72)
    if kind=="girls":
        # Alongside the central stair, the photo shows a separate sloping ramp.
        for i in range(16):
            yc=-6.9+i*.36
            z=.03+i*.028
            b("坡道铺板","stone",3.16,yc,z/2,1.32,.37,z)
            b("坡道栏杆立杆","silver",3.89,yc,z+.47,.031,.031,.94)
            b("坡道连续扶手","silver",3.89,yc,z+.94,.040,.382,.039)
        # Curved glazed pavilion visible when the camera turns to 180 degrees.
        for i in range(23):
            t=-math.pi/2+i*math.pi/22
            x=width*.33+3.38*math.cos(t)
            y=-4.85+3.38*math.sin(t)
            for z,material_key,h in ((1.66,"sideglass",2.85),(3.45,"ochre",.75),
                                     (5.06,"glass",2.44),(6.50,"slate",.64)):
                b("圆形裙房环形分格",material_key,x,y,z,.55,.55,h)
            b("裙房竖梃","silver",x,y,1.70,.082,.075,2.7)
    # Rear and end faces reuse ground-observed cladding colors. Their bay spacing
    # stays provisional where the feature is obscured in the available panorama.
    points=list(map(world,record["outline"]))
    for side_number,(start,end) in enumerate(zip(points,points[1:]+points[:1])):
        if {side_number,(side_number+1)%len(points)}==front_edge:
            continue
        outer=Building.__new__(Building)
        outer.anchor=(start+end)/2
        outer.across=(end-start).normalized()
        outer.depth=Vector((-outer.across.y,outer.across.x,0))
        if (middle-outer.anchor).dot(outer.depth)<0:
            outer.across,outer.depth=-outer.across,-outer.depth
        outer.sid=sid
        outer.groups,outer.collection,outer.materials={},obj.collection,materials
        length=(end-start).length
        rows=max(2,round(length/2.9))
        spacing=length/rows
        outer.box("侧后檐条",accent,0,-.43,height-.28,length,.82,.53)
        outer.box("侧后裙墙",accent,0,-.21,base/2,length,.48,base)
        if length<8 and kind in {"dining","wing"}:
            for level_z in (5.3,9.1,13.0):
                outer.box("短侧墙深色水平通风槽","dark",0,-.43,level_z,length*.55,.15,.34)
        else:
            for floor in range(floors):
                z=base+(floor+.52)*level
                for bay in range(rows):
                    x=-length/2+(bay+.5)*spacing
                    outer.box("侧后窗玻璃","glass",x,-.39,z,spacing*.74,.20,level*.53)
                    outer.box("侧后窗梃","slate",x,-.51,z,.064,.091,level*.53)
        outer.finish()
    obj.finish()
    return obj


def wing_ends(scene,materials):
    for key,side in (("B40W",-1),("B40E",1)):
        data=next(item for item in PLAN["buildings"] if item["id"]==key)
        ia,ib=(2,1) if side==-1 else (0,3)
        a,b=map(world,(data["outline"][ia],data["outline"][ib]))
        item=Building.__new__(Building)
        item.anchor=(a+b)/2
        item.across=(b-a).normalized()
        item.depth=Vector((-item.across.y,item.across.x,0))
        item.sid="40"
        item.groups,item.materials={},materials
        item.collection=bpy.data.collections.new(key+" 面向连廊的黄色端面")
        scene.collection.children.link(item.collection)
        w=(a-b).length
        core=bpy.data.objects.get(key)
        if core is not None:
            bpy.data.objects.remove(core,do_unlink=True)
        opening_width=w*.39
        notch_world=[item.point(x,y,0) for x,y in (
            (-opening_width/2,-1),(opening_width/2,-1),(opening_width/2,2.5),(-opening_width/2,2.5))]
        # Cut the lobby recess in world coordinates before recreating the solid wall shell.
        footprint=Polygon([(world(p).x,world(p).y) for p in data["outline"]])
        footprint=footprint.difference(Polygon([(p.x,p.y) for p in notch_world]))
        verts,faces=[],[]
        for tri in constrained_delaunay_triangles(footprint).geoms:
            ring=list(tri.exterior.coords)[:3]
            if not tri.exterior.is_ccw:
                ring.reverse()
            k=len(verts)
            verts.extend((x,y,data["height"]) for x,y in ring)
            faces.append((k,k+1,k+2))
        for a,b in zip(list(footprint.exterior.coords),list(footprint.exterior.coords)[1:]):
            k=len(verts)
            verts.extend((p[0],p[1],z) for p,z in ((a,0),(b,0),(b,data["height"]),(a,data["height"])))
            faces.append((k,k+1,k+2,k+3))
        item.link("楼翼主体及侧廊凹口",verts,faces,materials["ochre"])
        item.box("侧廊深色进深","dark",0,2.44,8.7,w*.38,.20,17.4)
        for sign in (-1,1):
            x=sign*w*.36
            item.box("侧廊两侧黄色墙板","ochre",x,-.80,9.8,w*.279,.87,19.6)
            for j in range(1,14):
                item.box("端面横向分缝","joint",x,-1.242,j*1.40,w*.278,.014,.018)
            for j in range(5):
                item.box("端面墙板方形孔","dark",x*1.16,-1.245,2.19+j*3.20,.18,.019,.23)
        for z in (3.4,6.92,10.46,14.0,17.50):
            item.box("侧廊退后台板","slate",0,-.95,z,w*.45,.72,.38)
            item.box("侧廊黄色跨梁","ochre",0,-.47,z+.31,w*.44,.28,.19)
            item.railing("侧廊浅灰扶栏",-w*.17,w*.17,-1.29,z+.19,.83)
        item.finish()


class Planting:
    def __init__(self, scene):
        self.scene=scene
        self.group=bpy.data.collections.new("校园绿化 · 树、花池、草地")
        scene.collection.children.link(self.group)
        self.rng=random.Random(256)
        self.meshes={}
        self.palette={
            "bark":material("自然灰褐树皮",(.18,.126,.067),.94),
            "lightbark":material("灰白主轴树皮",(.27,.22,.151),.91),
            "grass1":material("草地黄绿斑块",(.127,.185,.055),.95),
            "grass2":material("草地中绿斑块",(.077,.135,.031),.96),
            "grass3":material("草地背阴斑块",(.101,.149,.041),.97),
            "olive":material("初春乔木暖叶",(.171,.273,.052),.88),
            "leaf":material("行道树绿色叶冠",(.085,.202,.031),.91),
            "deep":material("绿篱深色叶片",(.046,.109,.018),.94),
            "pink":material("樱花中间色",(.58,.22,.26),.79),
            "pink_light":material("樱花亮瓣",(.75,.42,.39),.76),
            "pink_shade":material("樱花暗瓣",(.39,.105,.17),.84),
        }

    def buffer(self,label,color):
        return self.meshes.setdefault((label,color),([],[]))

    def limb(self,label,color,a,b,start_r,end_r):
        verts,faces=self.buffer(label,color)
        direction=(b-a).normalized()
        side=direction.cross(Vector((0,0,1)))
        if side.length<.04:
            side=Vector((1,0,0))
        side.normalize()
        other=direction.cross(side)
        start=len(verts)
        for center,r in ((a,start_r),(b,end_r)):
            verts.extend(center+r*(side*math.cos(i*math.tau/7)+other*math.sin(i*math.tau/7))
                         for i in range(7))
        faces.extend((start+i,start+(i+1)%7,start+7+(i+1)%7,start+7+i) for i in range(7))
        faces.extend((tuple(start+i for i in reversed(range(7))),tuple(start+7+i for i in range(7))))

    def crown(self,label,color,center,rx,ry,rz):
        verts,faces=self.buffer(label,color)
        offset=len(verts)
        for j,z in enumerate((-.91,-.54,0,.63,.93)):
            radial=(.38,.82,1,.77,.29)[j]
            for i in range(8):
                angle=(i+j*.38)*math.tau/8
                rough=self.rng.uniform(.76,1.24)
                verts.append(center+Vector((math.cos(angle)*rx*radial*rough,
                                            math.sin(angle)*ry*radial*rough,rz*z)))
        faces.append(tuple(offset+i for i in reversed(range(8))))
        for j in range(4):
            for i in range(8):
                a,k=offset+j*8,(i+1)%8
                faces.append((a+i,a+k,a+k+8,a+i+8))
        faces.append(tuple(offset+32+i for i in range(8)))

    def tree(self,pixel,height,kind):
        rng=self.rng
        ground=world(pixel)
        ground.z=.077
        trunk="lightbark" if kind=="pollard" else "bark"
        fork=ground+Vector((rng.uniform(-.25,.25),rng.uniform(-.16,.16),height*.47))
        self.limb("树干与分枝",trunk,ground,fork,height*.029,height*.014)
        reach=height*(.38 if kind=="cherry" else .285)
        for i in range(6 if kind!="cherry" else 9):
            angle=(i*.94+rng.uniform(-.32,.32))
            arm=fork+Vector((math.cos(angle)*reach*rng.uniform(.55,1.04),
                             math.sin(angle)*reach*rng.uniform(.61,1.10),height*rng.uniform(.19,.41)))
            self.limb("树干与分枝",trunk,fork,arm,height*.014,height*.004)
            for j in range(3):
                tip=arm+Vector((rng.uniform(-.62,.62),rng.uniform(-.62,.62),height*rng.uniform(.08,.23)))
                self.limb("细枝",trunk,arm,tip,height*.005,height*.0015)
                if kind!="pollard":
                    r=rng.uniform(.56,1.00)*(height/4)**.57
                    choices=("pink","pink_light","pink_shade") if kind=="cherry" else ("olive","leaf","leaf","deep")
                    self.crown("多簇叶冠或樱花",rng.choice(choices),tip,1.12*r,r,.74*r)

    def hedge(self,points,width=.53):
        for a,b in zip(points,points[1:]):
            start,end=world(a),world(b)
            distance=(end-start).length
            for i in range(max(1,math.ceil(distance/.48))):
                factor=min((i+.5)*.48/distance,1)
                pos=start.lerp(end,factor)+Vector((0,0,.35))
                self.crown("修剪绿篱",self.rng.choice(("deep","leaf","deep")),
                           pos,width,.65*width,.40)
                self.crown("修剪绿篱","leaf",pos+Vector((.05,-.04,.20)),width*.72,width*.55,.24)

    def grass(self,areas):
        for polygon in areas:
            x0,y0,x1,y1=polygon.bounds
            for _ in range(round(polygon.area*.28)):
                p=Point(self.rng.uniform(x0,x1),self.rng.uniform(y0,y1))
                if not polygon.contains(p):
                    continue
                center=world((p.x,p.y))
                center.z=.025
                for j in range(3):
                    color=self.rng.choice(("grass1","grass2","grass3"))
                    verts,faces=self.buffer("草叶丛",color)
                    index=len(verts)
                    angle=self.rng.random()*math.tau
                    u=Vector((math.cos(angle),math.sin(angle),0))
                    verts.extend((center-u*.028,center+u*.028,
                                  center+u*.08+Vector((0,0,self.rng.uniform(.06,.16)))))
                    faces.append((index,index+1,index+2))

    def finish(self):
        for (label,color),(verts,faces) in self.meshes.items():
            mesh=bpy.data.meshes.new(label)
            mesh.from_pydata(verts,[],faces)
            mesh.update()
            if label in {"多簇叶冠或樱花","修剪绿篱","地被灌木","树干与分枝"}:
                for face in mesh.polygons:
                    face.use_smooth=True
            mesh.materials.append(self.palette[color])
            obj=bpy.data.objects.new(label,mesh)
            self.group.objects.link(obj)


def campus_planting(scene):
    plants=Planting(scene)
    for i,p in enumerate(((787,403),(858,412),(786,373),(849,380),(787,346),(852,343),
                          (782,320),(838,317),(783,284),(826,251),(850,248))):
        plants.tree(p,4.0+i%3*.48,"pollard" if i<8 else "green")
    for p in ((677,383),(706,382),(657,380),(722,383),(693,375)):
        plants.tree(p,3.2,"cherry")
    for a,b,amount in (((391,187),(789,181),25),((912,182),(1029,175),8),
                       ((885,482),(1021,473),9),((506,273),(703,274),10),
                       ((560,360),(726,361),9),((383,281),(498,291),7),
                       ((709,510),(758,502),4),((1008,309),(1019,420),8)):
        for i in range(amount):
            t=(i+.4)/amount
            p=(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
            plants.tree(p,4.0+(i%4)*.62,"green")
    for line in (
        ((769,410),(779,410),(779,420),(769,420),(769,410)),
        ((859,396),(872,396),(873,407),(861,407),(859,396)),
        ((846,354),(849,344),(857,343)),((773,367),(783,365)),
        ((664,379),(663,388),(678,390),(679,380),(664,379)),
        ((691,377),(694,387),(709,386),(710,377)),
        ((908,161),(918,160),(928,162),(935,165)),((944,181),(972,176)),
        ((659,183),(686,184)),((552,182),(574,182)),((427,304),(436,311),(432,318)),
    ):
        plants.hedge(line)
    areas=[
        Polygon(((614,372),(743,366),(752,376),(703,389),(618,388))),
        box(403,190,735,195),box(921,179,1017,188),
        Polygon(((692,489),(756,487),(776,506),(762,517),(698,518))),
        Polygon(((883,476),(1034,461),(1039,487),(914,492))),
        Polygon(((552,365),(700,362),(703,374),(552,374))),
        Polygon(((504,273),(696,270),(706,280),(507,284))),
    ]
    for i,polygon in enumerate(areas):
        for x,y in list(polygon.exterior.coords)[::2]:
            if i in (3,4):
                plants.crown("地被灌木","deep",world((x,y))+Vector((0,0,.29)),.75,.62,.51)
    plants.grass(areas)
    plants.finish()
    return areas


class SiteDetails:
    def __init__(self, scene, materials):
        self.scene=scene
        self.materials=materials

    def zone(self,name,pixel):
        item=Building.__new__(Building)
        item.anchor=world(pixel)
        item.across=Vector((1,0,0))
        item.depth=Vector((0,1,0))
        item.sid="场地"
        item.groups={}
        item.materials=self.materials
        item.collection=bpy.data.collections.new(name)
        self.scene.collection.children.link(item.collection)
        return item

    @staticmethod
    def lamp(item,x,y,with_flag):
        b=item.box
        b("蓝灰立杆","slate",x,y,2.15,.12,.12,4.3)
        b("浅色杆身","silver",x,y,2.91,.105,.105,2.76)
        b("支臂","silver",x+.27,y,4.29,.66,.062,.057)
        b("路灯光源","white",x+.58,y,4.26,.38,.15,.095)
        if with_flag:
            b("黄红底旗","red",x+.23,y,2.89,.40,.04,.60)
            b("旗帜浅金边","ochre",x+.39,y-.03,2.89,.059,.026,.60)

    @staticmethod
    def notice(item,x,y,key):
        for i in range(3):
            dx=(i-1)*1.55
            item.box("红立柱展板","red",x+dx-.76,y,1.10,.09,.106,2.2)
            item.box("蓝色展面","blue",x+dx,y,1.33,1.55,.11,.87)
            item.box("浅色挑盖","white",x+dx,y,1.91,1.67,.39,.065)
            item.photo_panel(f"实拍展板 {key}-{i}","090",((206,286),(434,286),(434,419),(206,419)),
                             x+dx,y-.061,1.33,1.45,.78)

    def make(self):
        for j,pixel in enumerate(((772,435),(868,433),(773,372),(863,370),
                                  (789,247),(824,491),(424,301),(525,269),
                                  (661,171),(752,169),(918,170),(991,164))):
            item=self.zone("道路设施 · 灯杆 "+str(j+1),pixel)
            self.lamp(item,0,0,j in (6,7,8,9,10,11))
            item.finish()
        for j,pixel in enumerate(((861,488),(527,250),(582,343),(683,163),(912,158))):
            item=self.zone("道路设施 · 宣传栏与分类桶 "+str(j+1),pixel)
            item.sid="15"
            self.notice(item,0,0,j)
            item.bins((-1.0,-.49,.02,.53),1.10)
            item.finish()
        for j,pixel in enumerate(((763,403),(863,392),(773,373),(853,355),
                                  (403,319),(468,303),(923,166))):
            item=self.zone("低石花池与坐凳 "+str(j+1),pixel)
            item.box("花池灰石台面","stone",0,0,.175,3.15,1.12,.28)
            item.box("花池内土","soil",0,0,.296,2.94,.91,.12)
            if j%2==0:
                item.box("条形坐凳座面","stone",0,1.0,.42,1.89,.38,.10)
                for x in (-.65,.65):
                    item.box("条形坐凳脚","stone",x,1,.22,.25,.34,.42)
            item.finish()
        for j,pixel in enumerate(((970,155),(990,153),(1010,151))):
            item=self.zone("劳动基地 · 种植畦与支架 "+str(j+1),pixel)
            item.box("矩形种植畦","soil",0,0,.14,5.9,1.37,.21)
            for i in range(14):
                x=(i-6.5)*.41
                for y in (-.37,.37):
                    item.box("细竹竿","twig",x,y,.76,.025,.025,1.41)
                    item.box("菜株","green",x,y,.25,.20,.22,.23)
                item.box("竹支架横档","twig",x,0,1.20,.022,.85,.027)
            item.finish()
        item=self.zone("孔德广场 · 文化墙实景饰面",(467,300))
        item.sid="08"
        for i,x in enumerate((-3.9,-1.3,1.3,3.9)):
            item.box("文化墙石柱","stone",x,0,.92,.68,.49,1.83)
            for z in (.17,.36,.59,.81,1.03,1.28,1.51,1.69):
                item.box("石柱横缝","slate",x,-.256,z,.68,.021,.017)
            if i<3:
                item.box("石墙展板衬底","white",x+1.30,0,.80,2.23,.37,1.14)
        item.photo_panel("实拍文化墙板","000",((490,297),(576,295),(575,361),(488,357)),
                         -2.60,-.19,.81,2.20,1.09)
        item.finish()
        item=self.zone("北侧攀桂轩 · 砖径木廊架",(654,183))
        for i in range(16):
            x=(i-7.5)*1.75
            for y in (-.91,.91):
                item.box("廊架木柱","twig",x,y,1.33,.115,.115,2.66)
                item.box("廊柱石础","stone",x,y,.11,.25,.25,.23)
            for k in range(4):
                item.box("廊顶短椽","twig",x+(k-1.5)*.44,0,2.68,.075,2.36,.095)
        for y in (-.85,.85):
            item.box("廊架纵梁","twig",0,y,2.57,27.3,.115,.17)
        item.finish()
        item=self.zone("西门道路旁 · 绿色棚架与路缘",(949,163))
        for i in range(7):
            for y in (-1.31,1.31):
                item.box("棚架深绿立杆","green",(i-3)*1.67,y,1.18,.068,.068,2.36)
            item.box("棚架支梁","green",(i-3)*1.67,0,2.36,.07,2.92,.11)
        item.box("棚顶绿片","green",0,0,2.47,10.85,2.91,.09)
        item.finish()
        item=self.zone("荣誉墙 · 场景04实拍牌面",(760,510))
        item.sid="04"
        item.box("荣誉墙主体","stone",0,0,1.33,5.9,.37,2.66)
        item.box("黑石墙脚","slate",0,-.07,.21,6.0,.5,.42)
        item.box("顶部压条","stone",0,-.02,2.68,6.02,.54,.16)
        item.photo_panel("荣誉墙整幅牌面","000",((88,216),(610,218),(610,453),(91,448)),
                         0,-.19,1.42,5.68,2.09)
        item.finish()


def finish_ground(scene,areas):
    # Add landscaped strips and connections over the existing ground without replacing the prior road mesh.
    ground_tools.OUT=OUT
    g=ground_tools.Ground.__new__(ground_tools.Ground)
    g.scene=scene
    g.batches={}
    g.materials = {key:bpy.data.materials[name] for key,name in (
        ("brick","人行步道 · 红灰错缝砖"),("grey","教学主轴 · 灰色花岗岩板"),
        ("cement","校内车道 · 浅灰混凝土"),("curb","混凝土立缘石"),
        ("joint","混凝土缩缝"),("iron","深灰铸铁井盖"),
    )}
    g.materials["grass"]=ground_tools.surfaced("草地 · 绿黄斑驳",(112,130,70),.96,"campusgrass",3.6)
    g.region("细化地面 · 草地与实景步行支路")
    for polygon in areas:
        g.surface("校园草地斑驳地表","grass",polygon,.021)
    for route,width,key,z in (
        (((601,390),(637,392),(658,393),(688,391),(719,385),(748,382)),1.86,"brick",.057),
        (((757,404),(751,422),(750,444),(741,472),(711,491)),1.63,"brick",.050),
        (((890,495),(922,485),(961,481),(1018,473)),1.75,"brick",.056),
        (((421,331),(444,340),(488,351),(527,354),(549,349)),2.05,"brick",.055),
        (((911,170),(940,176),(981,175),(1020,165)),1.69,"brick",.067),
        (((504,284),(546,293),(607,295),(690,291),(744,286)),2.37,"cement",.061),
        (((564,369),(604,369),(667,372),(727,373),(768,366)),2.49,"cement",.061),
    ):
        g.polyline("校内连接铺装",key,route,width,z)
        if key=="brick":
            for index,p in enumerate(route):
                if index%2==0:
                    g.cover("支路井盖与横缝",p,z+.004,.23)
    g.build()


def compose(views):
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    width=1390
    for page,start in enumerate(range(0,len(views),4),1):
        batch=views[start:start+4]
        canvas=Image.new("RGB",(width,54+math.ceil(len(batch)/2)*349),"#ede9dd")
        draw=ImageDraw.Draw(canvas)
        draw.text((14,14),"校园楼栋与道路设施 · 每组左为实景，右为模型估算视角",font=font,fill="#283221")
        for i,(tag,sid,angle,name) in enumerate(batch):
            x=(i%2)*694+8
            y=(i//2)*349+51
            draw.text((x,y),name,font=font,fill="#283221")
            for j,path in enumerate((reference(sid,angle),OUT/(tag+".png"))):
                with Image.open(path) as image:
                    canvas.paste(ImageOps.fit(image.convert("RGB"),(336,310)),(x+j*340,y+25))
        canvas.save(OUT/f"楼栋与道路对照_{page}.png")


def camera(scene,name,eye,target,lens=20):
    data=bpy.data.cameras.new(name)
    data.lens=lens
    obj=bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location=eye
    obj.rotation_euler=(target-eye).to_track_quat("-Z","Y").to_euler()
    return obj


def main():
    OUT.mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    materials={k:material(name,rgb,roughness) for k,(name,rgb,roughness) in PALETTE.items()}
    materials.update({
        "sport_white":material("体育建筑浅灰立面",(.51,.514,.49),.83),
        "twig":material("种植架原竹色",(.41,.262,.105),.91),
        "soil":material("种植花池表土",(.113,.077,.040),.97),
    })
    obsolete=("R06_walk_trees","R06_walk_tree_trunks","Trees_crowns","Trees_trunks",
              "P06_cherry_","Honor_wall","P07_culture_pier","P07_culture_panel",
              "P12_pergola_","P12_roof_","P14_growing_beds","P14_crop_rows")
    for obj in list(scene.objects):
        facade=any(obj.name.startswith(key+"_") and not obj.name.startswith(("B40_portal","B40_bridge","B40_canopy"))
                   for key in BLOCKS)
        if facade or obj.name.startswith(obsolete):
            bpy.data.objects.remove(obj,do_unlink=True)
    buildings={}
    for key in BLOCKS:
        rec=next(a for a in PLAN["buildings"] if a["id"]==key)
        buildings[key]=front(scene,key,rec,materials)
    wing_ends(scene,materials)
    areas=campus_planting(scene)
    finish_ground(scene,areas)
    SiteDetails(scene,materials).make()
    shots=[]
    for key,sid,angle,label in (
        ("B22","22","000","餐厅 · 深灰窗列及两处门厅"),
        ("B25","25","000","绅远楼 · 灰色单元窗和门廊"),
        ("B28","28","180","蕙远楼 · 玻璃裙房与入口"),
        ("B40W","40","270","教学西翼 · 黄柱和侧廊"),
        ("B40E","40","090","教学东翼 · 黄柱和侧廊"),
        ("B09A","09","045","体育区 · 场边建筑及看台周边"),
        ("B09B","07","270","体育区 · 孔德广场对侧建筑"),
    ):
        block=buildings[key]
        if key=="B22":
            eye,target=block.point(-block.width*.22+3,-13,1.68),block.point(-block.width*.22,0,4.1)
        elif key=="B25":
            eye,target=block.point(6.5,-8.5,1.68),block.point(0,0,3.4)
        elif key=="B28":
            eye,target=block.point(block.width*.33+2,-15,1.68),block.point(block.width*.33,-4.5,3.5)
        elif key in ("B40W","B40E"):
            at=(810,430) if key=="B40W" else (853,429)
            look=(788,429) if key=="B40W" else (875,429)
            eye,target=world(at)+Vector((0,0,1.64)),world(look)+Vector((0,0,6.15))
        else:
            offset=block.width*.39 if key.startswith("B40") else 0
            if key=="B40E":
                offset=-offset
            eye,target=block.point(offset-2,-17,1.66),block.point(offset,0,5.4)
        shots.append((camera(scene,label,eye,target,21),key,sid,angle,label))
    for index,(sid,angle,label,eye,target) in enumerate((
        ("40","000","主轴 · 修枝树、树池和绿篱",(827,416),(820,263)),
        ("06","000","樱花园 · 砖径、分枝花冠和树篱",(654,401),(682,384)),
        ("07","000","孔德广场 · 小径、文化墙与花池",(421,340),(443,305)),
        ("14","000","劳动基地 · 混凝土路和种植畦",(989,171),(990,154)),
        ("04","000","校门旁荣誉墙 · 实拍牌面",(761,523),(760,510)),
    )):
        at=world(eye)+Vector((0,0,2.2 if sid=="14" else 1.65))
        look=world(target)+Vector((0,0,.6 if sid=="14" else 1.58))
        shots.append((camera(scene,label,at,look,21 if sid=="14" else 20),
                      f"site{index}",sid,angle,label))
    scene.camera=shots[7][0]
    scene.render.resolution_x=scene.render.resolution_y=810
    scene.cycles.samples=16
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_楼栋道路与绿化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_楼栋道路与绿化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for cam,tag,*_ in shots:
        scene.camera=cam
        scene.render.filepath=str(OUT/(tag+".png"))
        bpy.ops.render.render(write_still=True)
    compose([shot[1:] for shot in shots])


if __name__=="__main__":
    main()
