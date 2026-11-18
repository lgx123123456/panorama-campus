"""Trace road edges from the aerial frame and rebuild the photographed ground surfaces."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from 图书馆照片还原 import material, open_campus, world


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果" / "教学楼实景细化" / "校园室外_四栋教学楼细化.blend"
OUT = ROOT / "成果" / "地面街道实景细化"
REFS = ROOT.parent / "数据" / "04_建模参考" / "02_八方向"
SCALE = 105 / 226
VIEWS = (
    ("03", "000", "校门混凝土地坪与黄白标线", (820,551), (821,523), 20, 3.4),
    ("03", "180", "校门外湘江道", (821,553), (821,577), 20, 1.3),
    ("40", "000", "教学主轴花岗岩石板", (828,414), (825,260), 18, 2.5),
    ("07", "000", "孔德广场环形小砖", (423,340), (433,306), 19, 2.2),
    ("22", "270", "餐厅与公寓之间的校内道路", (482,173), (651,170), 23, 1.9),
)


def surface_texture(key, rgb, pattern=None):
    """Create a seamless PBR base-color map from the observed surface pattern."""
    size = 512
    rng = np.random.default_rng(sum(map(ord,key)))
    coarse = np.asarray(Image.fromarray(rng.integers(0,255,(32,32),dtype=np.uint8))
                        .resize((size,size),Image.Resampling.BICUBIC),dtype=float)/255
    medium = rng.normal(0,2.2,(size,size))
    grain = rng.normal(0,2.9 if key == "asphalt" else 1.55,(size,size))
    values = (coarse-.48)*10+medium+grain
    if pattern:
        nx,ny,stagger = pattern
        y,x = np.indices((size,size))
        row = np.floor(y * ny / size).astype(int)
        yy = y * ny / size % 1
        xx = (x * nx / size + stagger * (row % 2)) % 1
        col = np.floor(x * nx / size + stagger * (row % 2)).astype(int) % nx
        tile = rng.normal(0,3.5,(ny,nx))
        values += tile[row,col]
        seam = np.minimum(np.minimum(xx,1-xx),np.minimum(yy,1-yy))
        values -= 30*np.exp(-seam*115)
        values += 5*np.exp(-((seam-.014)*180)**2)
    array=np.clip(np.array(rgb)[None,None,:]+values[:,:,None],0,255).astype(np.uint8)
    path=OUT/(key+".png")
    Image.fromarray(array).save(path)
    image=bpy.data.images.load(str(path))
    image.pack()
    return image


def surfaced(name, base_rgb, roughness, key, period, pattern=None):
    mat=material(name, tuple((c/255)**2.2 for c in base_rgb),roughness)
    mat["UV周期米"]=period
    tree=mat.node_tree
    image=tree.nodes.new("ShaderNodeTexImage")
    image.image=surface_texture(key,base_rgb,pattern)
    tree.links.new(image.outputs["Color"],tree.nodes.get("Principled BSDF").inputs["Base Color"])
    return mat


class Ground:
    def __init__(self, scene, materials=None):
        self.scene=scene
        self.zone=None
        self.materials=materials if materials is not None else {
            "road":surfaced("湘江道 · 灰色沥青",(115,112,105),.94,"asphalt",5),
            "cement":surfaced("校内车道 · 浅灰混凝土",(173,167,153),.95,"concrete",6),
            "apron":surfaced("校门前 · 粗细混凝土",(178,171,156),.94,"apron",5),
            "grey":surfaced("教学主轴 · 灰色花岗岩板",(143,144,140),.86,"granite",2.4,(4,4,0)),
            "sand":surfaced("尚德与孔德广场 · 浅暖石板",(173,166,151),.87,"sandstone",2.4,(4,4,0)),
            "brick":surfaced("人行步道 · 红灰错缝砖",(147,123,111),.87,"brick",1.2,(5,10,.5)),
            "redbrick":surfaced("孔德广场 · 环形暖砖",(159,124,103),.89,"circlebrick",.96,(4,8,.5)),
            "curb":material("混凝土立缘石",(.27,.26,.235),.90),
            "yellow":material("磨损黄色标线",(.64,.38,.048),.83),
            "white":material("磨损白色标线",(.61,.60,.54),.88),
            "joint":material("混凝土缩缝",(.14,.133,.117),.95),
            "iron":material("深灰铸铁井盖",(.071,.076,.073),.8),
            "rust":material("锈红井盖",(.23,.085,.042),.88),
            "green":material("低矮绿篱",(.095,.155,.047),.94),
            "soil":material("树池表土",(.15,.112,.068),.99),
            "rail":material("道路护栏 · 深绿色",(.041,.080,.045),.78),
            "tree_bark":material("行道树树皮",(.15,.118,.074),.93),
            "tree_leaves":material("行道树叶",(.069,.154,.043),.97),
            "black":material("减速带黑胶",(.054,.063,.061),.91),
        }
        self.batches={}

    def region(self, name):
        self.zone=bpy.data.collections.new(name)
        self.scene.collection.children.link(self.zone)

    def mesh(self, label,key):
        return self.batches.setdefault((self.zone,label,key),([],[],[]))

    def surface(self,label,key,geometry,z):
        if geometry.is_empty:
            return
        if geometry.geom_type != "Polygon":
            for polygon in geometry.geoms:
                if polygon.geom_type in {"Polygon","MultiPolygon"}:
                    self.surface(label,key,polygon,z)
            return
        verts,faces,uv=self.mesh(label,key)
        period=self.materials[key].get("UV周期米",1)
        for tri in constrained_delaunay_triangles(geometry).geoms:
            coords=list(tri.exterior.coords)[:3]
            if tri.exterior.is_ccw:
                coords.reverse()  # image y points south; Blender y points north
            index=len(verts)
            for xy in coords:
                location=world(xy)
                location.z=z
                verts.append(location)
                uv.append((location.x/period,location.y/period))
            faces.append((index,index+1,index+2))

    def line(self,label,key,start,end,width,z):
        self.surface(label,key,LineString((start,end)).buffer(width/(2*SCALE),cap_style="flat"),z)

    def polyline(self,label,key,points,width,z):
        self.surface(label,key,LineString(points).buffer(width/(2*SCALE),cap_style="flat",join_style="round"),z)

    def raised(self,label,key,geometry,bottom,top):
        self.surface(label,key,geometry,top)
        if geometry.is_empty:
            return
        verts,faces,uv=self.mesh(label,key)
        for ring in (geometry.exterior,*geometry.interiors):
            points=list(ring.coords)
            for a,b in zip(points,points[1:]):
                i=len(verts)
                for p,z in ((a,bottom),(b,bottom),(b,top),(a,top)):
                    location=world(p)
                    location.z=z
                    verts.append(location)
                    uv.append((location.x+location.y,z))
                faces.append((i,i+1,i+2,i+3))

    def dash(self,label,key,a,b,width,length,gap,z):
        path=LineString((a,b))
        for t in np.arange(0,path.length,length+gap):
            start=path.interpolate(t).coords[0]
            end=path.interpolate(min(t+length,path.length)).coords[0]
            self.line(label,key,start,end,width,z)

    def cover(self,label,point,z,radius=.38,key="iron"):
        circle=Point(point).buffer(radius/SCALE,quad_segs=16)
        self.surface(label,key,circle,z)
        for scale in (.63,.83):
            outer=Point(point).buffer(radius*scale/SCALE,quad_segs=16)
            inner=Point(point).buffer((radius*scale-.018)/SCALE,quad_segs=16)
            self.surface(label+"压纹","joint",outer.difference(inner),z+.001)

    def tree(self, xy, shift):
        self.raised("行道树树干","tree_bark",Point(xy).buffer(.27,quad_segs=3),.10,3.75)
        rng=np.random.default_rng(shift)
        verts,faces,uv=self.mesh("行道树冠","tree_leaves")
        base=world(xy)
        rings=(.58,1.25,1.27,.72)
        start=len(verts)
        for level,radius in enumerate(rings):
            for i in range(10):
                angle=(i+level*.3)*math.tau/10
                r=radius*rng.uniform(.81,1.23)
                verts.append(base+Vector((r*math.cos(angle),r*math.sin(angle),
                             2.65+level*1.05+rng.uniform(-.26,.26))))
                uv.append((0,0))
        faces.append(tuple(start+i for i in reversed(range(10))))
        for level in range(3):
            for i in range(10):
                k=(i+1)%10
                a=start+level*10
                faces.append((a+i,a+k,a+10+k,a+10+i))
        faces.append(tuple(start+30+i for i in range(10)))

    def build(self):
        for (zone,label,key),(verts,faces,coords) in self.batches.items():
            if not faces:
                continue
            mesh=bpy.data.meshes.new(label)
            mesh.from_pydata(verts,[],faces)
            mesh.update()
            uv=mesh.uv_layers.new()
            for loop in mesh.loops:
                uv.data[loop.index].uv=coords[loop.vertex_index]
            mesh.materials.append(self.materials[key])
            obj=bpy.data.objects.new(label,mesh)
            zone.objects.link(obj)


def streets(g):
    g.region("路面01 · 湘江道与东侧路口（场景01、02、03）")
    south=Polygon(((46,550),(944,552),(1028,550),(1168,550),
                   (1168,582),(1026,585),(929,581),(46,577)))
    east=Polygon(((1081,22),(1114,22),(1108,488),(1118,532),(1122,607),
                  (1050,607),(1053,537),(1074,486)))
    asphalt=south.union(east)
    g.surface("两条车行道与交叉口","road",asphalt,.029)
    for limits in (
        ((48,551.8),(773,553)),((870,554),(1027,552)),
        ((48,575.4),(936,579)),((945,579),(1027,583)),
        ((1083,25),(1077,478)),((1112,23),(1106,481)),
    ):
        a,b=limits
        g.polyline("车道边缘线","white",(a,b),.14,.036)
    for start,end in (((48,561),(1026,566)),((48,568),(1026,574)),
                      ((1089,25),(1082,486)),((1103,25),(1096,486))):
        g.dash("白色车道虚线","white",start,end,.145,7,10,.036)
    for start,end in (((48,565),(1020,570)),((1095,25),(1089,485))):
        g.dash("黄色分向线","yellow",start,end,.135,10,9,.036)
    for x in (170,345,555,786,958):
        g.line("路面修补接缝","joint",(x,553),(x+7,577),.025,.036)

    for y in (544,590):
        for x in range(1057,1118,3):
            g.surface("交叉口斑马线","white",box(x,y-3,x+1.30,y+3),.040)
    for x in (1036,1129):
        for y in range(553,582,3):
            g.surface("交叉口斑马线","white",box(x-4,y,x+4,y+1.25),.040)
    for a,b in (((1025,552),(1025,566)),((1140,568),(1140,582)),
                ((1057,532),(1080,532)),((1099,599),(1119,599))):
        g.line("停车线","white",a,b,.32,.039)
    # Sidewalks and low curbs stop at the school driveway and at the intersection.
    segments=(
        ((55,543),(780,546)),((868,549),(1017,547)),((55,582),(1026,589)),
        ((1065,29),(1060,471)),((1124,28),(1119,476)),
    )
    for a,b in segments:
        edge=LineString((a,b))
        sidewalk=edge.buffer(2.9,cap_style="flat").difference(asphalt)
        g.surface("街道人行砖铺","brick",sidewalk,.123)
        curb=edge.buffer(.40,cap_style="flat")
        g.raised("街道混凝土路缘","curb",curb,.024,.128)
    opposite = LineString(((48,595),(940,598),(1021,602)))
    g.surface("湘江道对侧绿化基底","green",opposite.buffer(7,cap_style="flat"),.098)
    barrier = LineString(((52,590),(940,593),(1018,597)))
    for height in (.19,.63,.99):
        g.raised("对街绿色护栏横杆","rail",barrier.buffer(.045,cap_style="flat"),
                 height,height+.045)
    for distance in np.arange(0,barrier.length,3.2):
        p=barrier.interpolate(distance)
        g.raised("对街绿色护栏立杆","rail",p.buffer(.11,quad_segs=2),.13,1.06)
    g.surface("校门两侧林带地面","soil",
              box(650,521,777,542).union(box(873,521,978,543)),.037)
    for i,x in enumerate(range(544,1020,17)):
        g.tree((x,596+(x-544)*.014),46+i)
    for i,x in enumerate((*range(652,776,16),*range(877,998,17))):
        g.tree((x,535+(i%3-1)*2),210+i)
    g.region("路面02 · 校门混凝土地坪（场景03、05）")
    apron=Polygon(((785,497),(861,498),(875,555),(777,555)))
    g.surface("校门浅灰混凝土地坪","apron",apron,.050)
    for x in (804,812.5,821,829.5,838):
        g.line("入口纵向黄色短线","yellow",(x,545.6),(x-.06,555),.087,.054)
    for y in (534,540,544):
        for x in (795,814,833,851):
            g.line("门前横向黄色短线","yellow",(x,y),(x+5.2,y+.03),.113,.054)
    for a,b in (((807,525),(802,551)),((835,525),(840,551))):
        g.line("门房两侧白线","white",a,b,.13,.054)
    for x in (797,821,848):
        g.line("门前混凝土缩缝","joint",(x,527),(x+.17,555),.019,.053)
    for y in (505,524,551):
        g.line("门前横向缩缝","joint",(787,y),(861,y+.13),.026,.054)
    for x,y in ((805,507),(843,532),(839,538)):
        g.surface("门前方形排水盖","iron",box(x-.67,y-.54,x+.67,y+.54),.056)
        for i in range(6):
            g.line("排水盖平行缝","curb",(x-.55+.22*i,y-.45),
                   (x-.55+.22*i,y+.45),.015,.059)


def campus_surfaces(g,plan):
    g.region("路面03 · 尚德广场与教学主轴（场景05、40、45、32）")
    lookup={area["id"]:Polygon(area["outline"]) for area in plan["areas"]}
    apron=Polygon(((785,497),(861,498),(875,555),(777,555)))
    connector=Polygon(((785,449),(863,449),(885,482),(875,500),(780,500),(758,487)))
    g.surface("尚德广场至主轴连续铺底","sand",connector.difference(
        unary_union([apron,lookup["P03"],lookup["P05"],lookup["P40"]])),.044)
    claimed=apron
    for key,label,mat in (
        ("P03","校门内侧与门厅衔接处","apron"),("P05","尚德广场暖灰石板","sand"),
        ("P40","教学主轴大块灰色石板","grey"),("P07","孔德广场浅色石板","sand"),
    ):
        polygon=lookup[key].difference(claimed)
        g.surface(label,mat,polygon,.043)
        claimed=claimed.union(lookup[key])
    for index,(x,y) in enumerate(((788,405),(857,414),(793,380),(847,359),
                                  (783,344),(838,318),(783,285),(832,252))):
        g.raised("方形树池立缘","curb",box(x-2.45,y-2.45,x+2.45,y+2.45),.041,.16)
        g.surface("方形树池绿格","green" if index%2==0 else "soil",
                  box(x-2.29,y-2.29,x+2.29,y+2.29),.166)
        for d in (-1.4,0,1.4):
            g.line("树池方格","iron",(x-2.2,y+d),(x+2.2,y+d),.027,.172)
            g.line("树池方格","iron",(x+d,y-2.2),(x+d,y+2.2),.027,.172)
    for point in ((840,399),(815,322),(809,466),(709,381),(453,329)):
        g.cover("广场圆形井盖",point,.049)
    g.region("路面04 · 孔德广场与樱花园（场景06、07、08）")
    center=Point((429,310))
    band=center.buffer(14,quad_segs=42).difference(center.buffer(6.0,quad_segs=42))
    band=band.intersection(lookup["P07"])
    g.surface("日晷环形红褐砖带","redbrick",band,.050)
    for i in range(23):
        angles=np.linspace(0,math.tau,86)
        radius=6.3+i*.33
        ring=LineString([(429+radius*math.cos(a),310+radius*math.sin(a)) for a in angles])
        g.surface("弧形砖缝","joint",ring.buffer(.017).intersection(band),.052)
    for a,b in (((443,322),(499,338)),((442,324),(498,340))):
        g.line("文化墙前红色条带","redbrick",a,b,.29,.050)
    garden_path=LineString(((614,392),(652,394),(686,391),(733,383)))
    g.surface("樱花园砖砌小路","brick",garden_path.buffer(3.0,join_style="round"),.051)
    g.region("路面05 · 校园支路（场景13、14、15、21、22、24、28）")
    for key,label in (("R03","北侧餐厅和公寓混凝土路"),("R04","南侧校园支路")):
        g.surface(label,"cement",lookup[key],.047)
    for a,b in (
        ((397,164),(573,164)),((573,164),(810,158)),((810,158),(993,154)),
        ((396,182),(573,185)),((573,185),(812,181)),((812,181),(981,180)),
        ((301,488),(608,497)),((301,512),(606,519)),
        ((737,222),(759,250)),((751,271),(784,309)),
    ):
        path=LineString((a,b))
        g.raised("校内低路缘","curb",path.buffer(.31,cap_style="flat"),.034,.125)
    for a,b in (
        ((427,179),(818,173)),((824,173),(967,168)),
        ((508,287),(754,284)),((574,367),(774,366)),((892,488),(1012,481)),
    ):
        if a[1]>220:
            footprint=LineString((a,b)).buffer(5.0,cap_style="round")
            g.surface("教学区混凝土支路","cement",footprint,.038)
        else:
            g.dash("餐厅侧黄色短线","yellow",a,b,.094,8,10,.053)
    for x in range(403,973,22):
        y=174-(x-403)*.021
        g.line("北侧混凝土伸缩缝","joint",(x,y-4.7),(x+.4,y+4.8),.019,.052)
    for a,b in (
        ((446,186),(736,182)),((744,184),(1008,180)),
        ((507,275),(681,273)),((562,359),(722,361)),
    ):
        g.polyline("校内错缝人行道","brick",(a,b),1.26,.075)
    for x,y in ((930,171),(698,178),(534,179),(640,288),(576,365)):
        g.cover("支路井盖",(x,y),.056,.34,"rust")
    for i in range(10):
        x=910+i*1.34
        g.raised("西门支路减速垄","yellow" if i%2 else "black",
                 box(x,166.8,x+1.32,168.1),.049,.111)


def make_comparison():
    font="C:/Windows/Fonts/msyh.ttc"
    title=ImageFont.truetype(font,26)
    label=ImageFont.truetype(font,17)
    tile=385
    canvas=Image.new("RGB",(2*tile+26,68+len(VIEWS)*(tile+35)),"#f0ede4")
    d=ImageDraw.Draw(canvas)
    d.text((12,10),"地面与街道 · 实景对照",font=title,fill="#1e2822")
    d.text((12,46),"左：现场照片     右：模型估算视角",font=label,fill="#38443b")
    for i,(sid,angle,name,*_) in enumerate(VIEWS):
        y=71+i*(tile+35)
        d.text((12,y),f"{sid}/{angle}  {name}",font=label,fill="#1e2822")
        paths=(next(REFS.glob(sid+"_*"))/(angle+".jpg"),OUT/(sid+"_"+angle+".png"))
        for j,path in enumerate(paths):
            with Image.open(path) as pic:
                canvas.paste(ImageOps.fit(pic.convert("RGB"),(tile,tile)),(11+j*(tile+6),y+25))
    canvas.save(OUT/"地面与街道实景对照.png")


def main():
    OUT.mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    plan=json.loads((ROOT/"总图标注.json").read_text(encoding="utf-8"))
    original={"R01","R02","R03","R04","P03","P05","P40","P07",
              "P03_paving_joints","P05_paving_joints","P40_paving_joints","P07_paving_joints"}
    for obj in list(scene.objects):
        if obj.name in original:
            bpy.data.objects.remove(obj,do_unlink=True)
    ground=Ground(scene)
    streets(ground)
    campus_surfaces(ground,plan)
    ground.build()
    cameras=[]
    for sid,angle,name,eye,target,lens,aim in VIEWS:
        data=bpy.data.cameras.new(name)
        data.lens=lens
        obj=bpy.data.objects.new(name,data)
        scene.collection.objects.link(obj)
        obj.location=world(eye)+Vector((0,0,1.65))
        obj.rotation_euler=(world(target)+Vector((0,0,aim))-obj.location).to_track_quat("-Z","Y").to_euler()
        cameras.append((obj,sid+"_"+angle))
    scene.camera=cameras[0][0]
    scene.render.resolution_x=scene.render.resolution_y=850
    scene.cycles.samples=18
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_地面街道细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_地面街道细化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for camera,file in cameras:
        scene.camera=camera
        scene.render.filepath=str(OUT/(file+".png"))
        bpy.ops.render.render(write_still=True)
    data=bpy.data.cameras.new("校门与东侧道路俯瞰")
    data.type="ORTHO"
    data.ortho_scale=232
    overview=bpy.data.objects.new(data.name,data)
    scene.collection.objects.link(overview)
    target=world((966,509))
    overview.location=target+Vector((12,-66,122))
    overview.rotation_euler=(target-overview.location).to_track_quat("-Z","Y").to_euler()
    scene.camera=overview
    scene.render.resolution_x,scene.render.resolution_y=1210,790
    scene.render.filepath=str(OUT/"湘江道与路口俯瞰.png")
    bpy.ops.render.render(write_still=True)
    make_comparison()


if __name__=="__main__":
    main()
