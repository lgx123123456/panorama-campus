"""Build editable reference-based interiors, one Blender scene per panorama."""

import csv
import math
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "成果" / "第2轮"
ROOMS = {
    16: (7, 14, 3.4, "hall"), 17: (8.4, 10, 3.5, "class"),
    18: (6.9, 10, 3.3, "office"), 19: (6.8, 10.7, 3.2, "meeting"),
    20: (6.4, 9, 3.2, "activity"), 23: (20, 24, 4.3, "dining"),
    26: (11, 12.5, 5.4, "lobby"), 27: (4, 6.2, 3.1, "dorm"),
    29: (11.3, 12.2, 5.4, "lobby"), 30: (4.1, 6, 3.1, "dorm"),
    31: (9, 13, 3.4, "laundry"), 33: (12, 15, 3.45, "reading"),
    34: (10, 12, 3.85, "forum"), 35: (13, 16, 3.85, "lecture"),
    37: (8.8, 10.9, 3.45, "lab"), 38: (8.8, 11.8, 3.45, "computer"),
    39: (8.2, 10.7, 3.35, "recording"), 41: (11, 13, 4, "dance"),
    42: (12, 15, 6.4, "aerobics"), 43: (10, 12, 3.45, "band"),
    44: (9.2, 12, 3.6, "art"),
}
COLORS = {
    "wall": (.74,.72,.63), "ceil": (.87,.86,.81), "tile": (.41,.45,.44),
    "jade": (.14,.40,.29), "wood": (.51,.27,.10), "dark_wood": (.29,.091,.049),
    "birch": (.71,.54,.32), "blue": (.12,.28,.43), "red": (.45,.065,.045),
    "metal": (.15,.17,.18), "steel": (.45,.47,.43), "white": (.83,.82,.76),
    "glass": (.59,.76,.84), "blackboard": (.036,.19,.13), "green": (.33,.45,.17),
    "orange": (.60,.22,.066), "mirror": (.53,.58,.63), "dark": (.07,.076,.083),
}
FACES = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))


class Room:
    def __init__(self, scene, w, d, h):
        self.scene = scene
        self.w, self.d, self.h = w, d, h
        self.groups = {}

    def box(self, label, color, x, y, z, w, d, h, angle=0):
        vertices, faces, mats = self.groups.setdefault(label, ([], [], []))
        start = len(vertices)
        co, si = math.cos(angle), math.sin(angle)
        for dx, dy, dz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                           (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)):
            a, b = dx*w/2, dy*d/2
            vertices.append((x+a*co-b*si,y+a*si+b*co,z+dz*h/2))
        faces.extend(tuple(start+i for i in face) for face in FACES)
        mats.extend([color]*6)

    def desk(self, x, y, w=1.1, d=.50, color="wood", z=.76):
        self.box("桌面",color,x,y,z,w,d,.07)
        for a in (-1,1):
            for b in (-1,1):
                self.box("桌腿","metal",x+a*(w/2-.08),y+b*(d/2-.07),z/2,.044,.044,z)

    def chair(self, x, y, color="blue"):
        self.box("座面",color,x,y,.44,.40,.41,.065)
        self.box("椅背",color,x,y-.19,.66,.40,.055,.39)
        for a in (-1,1):
            for b in (-1,1):
                self.box("椅脚","metal",x+a*.15,y+b*.15,.21,.038,.038,.42)

    def shelf(self, x, y, width=1.5, books=False):
        for a in (-1,1):
            self.box("柜体","birch",x+a*width/2,y,1,width*.035,.35,2)
        for level in range(5):
            z=.13+level*.43
            self.box("层板","birch",x,y,z,width,.36,.055)
            if books:
                for i in range(8):
                    palette = ("blue","red","white","green","orange")
                    height=.21+.035*((i+level)%4)
                    self.box("书册",palette[(i+level)%5],x+(i-3.5)*width/9,y,z+height/2+.03,
                             width*.090,.22,height)

    def board(self, color="blackboard", width=4.8):
        self.box("讲台板框","steel",0,self.d/2-.13,1.68,width+.13,.13,1.35)
        self.box("讲台板面",color,0,self.d/2-.215,1.68,width,.07,1.22)

    def shell(self, floor, wainscot, window_count):
        w,d,h=self.w,self.d,self.h
        self.box("地坪",floor,0,0,-.07,w+.20,d+.20,.14)
        self.box("天花","ceil",0,0,h+.052,w+.2,d+.2,.10)
        self.box("前墙","wall",0,d/2,h/2,w+.20,.16,h)
        # The rear door aperture is modeled as an opening.
        door_x = -w*.28
        for left,right in ((-w/2,door_x-.53),(door_x+.53,w/2)):
            self.box("后墙","wall",(left+right)/2,-d/2,h/2,right-left,.16,h)
        self.box("门楣","wall",door_x,-d/2,(h+2.16)/2,1.06,.16,h-2.16)
        for x in (door_x-.53,door_x+.53):
            self.box("门框","dark_wood",x,-d/2,1.08,.085,.25,2.16)
        self.box("开启门扇","dark_wood",door_x-.50,-d/2+.46,1.04,.063,.92,2.08)
        self.box("左墙","wall",-w/2,0,h/2,.16,d,h)
        self.box("窗下墙",wainscot,w/2,0,.48,.16,d,.96)
        self.box("窗上墙","wall",w/2,0,(h+2.52)/2,.16,d,h-2.52)
        for i in range(window_count):
            length=d/window_count
            y=-d/2+(i+.5)*length
            self.box("侧窗玻璃","glass",w/2,y,1.74,.08,length-.26,1.53)
            self.box("窗间墙","wall",w/2,y-length/2,1.74,.18,.26,1.57)
            self.box("窗框","steel",w/2-.06,y,1.68,.10,length-.24,.065)
            self.box("窗框","steel",w/2-.06,y,1.74,.10,.067,1.54)
        self.box("窗间墙","wall",w/2,d/2,1.74,.18,.26,1.57)
        for x,y,ww,dd in ((0,d/2-.09,w,.042),(-w/2+.09,0,.042,d)):
            self.box("墙裙",wainscot,x,y,.52,ww,dd,1.04)
        for x in (-w*.24,w*.24):
            for y in (-d*.29,0,d*.29):
                self.box("灯盘","white",x,y,h-.10,.30,1.40,.075)

    def furniture(self, kind):
        w,d,h=self.w,self.d,self.h
        if kind in {"class","lab","computer","recording","reading","office","dining","art"}:
            rows, cols, wd, dp, color = {
                "class":(5,3,1.42,.50,"wood"), "lab":(4,3,1.62,.70,"jade"),
                "computer":(5,3,1.75,.64,"white"), "recording":(4,3,1.46,.52,"wood"),
                "reading":(4,3,2.0,.94,"white"), "office":(3,2,1.83,.76,"white"),
                "dining":(6,5,2.2,.74,"white"), "art":(3,2,1.30,.59,"green"),
            }[kind]
            for r in range(rows):
                y=-d*.31+(r+.5)*d*.63/rows
                for c in range(cols):
                    x=(c-(cols-1)/2)*w*.77/cols
                    self.desk(x,y,wd,dp,color)
                    if kind=="dining":
                        for side in (-1,1):
                            self.box("固定餐凳","blue",x,y+side*.66,.44,wd,.24,.09)
                            self.box("餐凳支架","metal",x,y+side*.66,.22,1.18,.10,.42)
                    elif kind!="art":
                        for dx in (-wd*.23,wd*.23):
                            self.chair(x+dx,y-dp/2-.26,"dark" if kind=="office" else "blue")
                    if kind in {"computer","office"}:
                        for dx in (-wd*.25,wd*.25):
                            self.box("显示器","dark",x+dx,y,.99,.42,.087,.29)
                            self.box("屏幕","glass",x+dx,y-.049,1,.37,.013,.225)
                            self.box("键盘","dark",x+dx,y-.21,.809,.30,.108,.018)
                    if kind=="lab":
                        self.box("显微镜底座","white",x+.37,y,.835,.20,.24,.065)
                        self.box("显微镜架","metal",x+.38,y,.99,.065,.08,.32)
                        self.box("显微镜镜筒","white",x+.38,y-.04,1.13,.092,.15,.075)
                    if kind=="office":
                        self.box("绿色工位隔板","green",x,y+.33,1,wd,.085,.48)
                    if kind=="art":
                        self.box("画架","birch",x,y-.32,1.02,.09,.1,1.96)
                        self.box("画板","white",x,y-.31,1.25,.60,.065,.73)
            if kind=="reading":
                for x in (-w*.29,0,w*.29):
                    self.shelf(x,d/2-.35,width=2.18,books=True)
            elif kind=="dining":
                for i in range(6):
                    x=(i-2.5)*w*.145
                    self.box("餐饮档口","steel",x,d/2-.65,.57,2.1,.90,1.14)
                    self.box("档口色带","red",x,d/2-.18,2.55,2.12,.12,.40)
            elif kind in {"class","lab","computer","recording","art"}:
                self.board("white" if kind=="recording" else "blackboard")
                self.desk(0,d*.36,1.52,.60,"steel")
        elif kind in {"meeting","activity"}:
            self.desk(0,.25,w*.40,d*.57,"dark_wood")
            for side in (-1,1):
                for i in range(5):
                    self.chair(side*w*.26,(i-2)*d*.105,"dark")
            self.board("white",w*.53)
            self.box("窗帘","blue" if kind=="activity" else "red",0,d/2-.31,2.20,w*.85,.12,1.42)
        elif kind in {"dorm","lobby","hall","laundry"}:
            self.utility(kind)
        else:
            self.performance(kind)

    def utility(self, kind):
        w,d,h=self.w,self.d,self.h
        if kind=="dorm":
            for x in (-w*.32,w*.32):
                for y in (-d*.22,d*.19):
                    for z in (.53,1.73):
                        self.box("上下铺钢架","steel",x,y,z,.96,1.89,.12)
                        self.box("床垫","blue",x,y,z+.095,.88,1.80,.12)
                        self.box("枕头","white",x,y+.66,z+.185,.72,.29,.10)
                    for dx in (-.47,.47):
                        for dy in (-.90,.90):
                            self.box("床架立柱","steel",x+dx,y+dy,1.035,.045,.045,2.07)
                    for z in (.35,.66,.97,1.28,1.59):
                        self.box("床梯","steel",x-math.copysign(.53,x),y-.66,z,.21,.043,.043)
            self.box("储物柜","steel",w*.2,-d*.42,1,.96,.50,2)
        elif kind=="laundry":
            for i in range(5):
                x=(i-2)*w*.16
                self.box("洗衣机机身","white",x,d*.32,.60,.78,.79,1.2)
                self.box("机门","dark",x,d*.32-.405,.74,.50,.042,.52)
            self.desk(0,.35,2.8,.88,"white")
            self.shelf(-w*.37,d*.14,1.22)
            self.shelf(w*.32,d*.14,1.22)
        else:
            counter = "饮水台" if kind=="hall" else "服务台"
            self.box(counter,"steel",-w*.245,d*.24,.55,2.7,.65,1.1)
            for i in range(4):
                x=(i-1.5)*w*.15
                self.box("墙面展示板","blue",x,d/2-.11,1.62,.61,.055,.53)
            for i in (-1,1):
                self.box("大厅柱","wall",i*w*.28,d*.18,h/2,.51,.51,h)
            if kind=="lobby":
                self.box("大厅电子屏","red",0,d/2-.14,3.7,w*.57,.08,.53)
            else:
                self.box("饮水机","blue",-w*.245,d*.24,1.26,1.08,.5,.30)

    def performance(self, kind):
        w,d,h=self.w,self.d,self.h
        if kind in {"dance","aerobics"}:
            for i in range(8):
                x=(i-3.5)*w*.103
                self.box("镜墙","mirror",x,d/2-.14,1.65,w*.100,.07,2.15)
            self.box("把杆","birch",0,d/2-.51,1.04,w*.85,.055,.055)
            for x in (-w*.33,0,w*.33):
                self.box("把杆支撑","steel",x,d/2-.51,.53,.05,.05,1.06)
            if kind=="aerobics":
                self.box("训练垫","blue",0,d*.12,.21,2.5,1.55,.42)
                self.box("高窗","glass",0,d/2-.11,h*.71,w*.74,.065,1.5)
        elif kind=="forum":
            for i in range(5):
                self.box("阶梯平台","blue",0,d*.12+i*.77,.13*(i+1),w*.90,1.0,.26*(i+1))
            self.box("投影幕","white",0,-d/2+.13,2.45,w*.44,.08,1.1)
            self.desk(w*.32,-d*.23,.72,.58,"dark_wood",1.03)
        else:
            self.box("舞台","wood",0,d*.30,.15,w*.91,d*.24,.30)
            self.board("white" if kind=="lecture" else "blackboard")
            for i in range(6):
                for j in range(9):
                    x=(j-4)*w*.093+(math.copysign(.35,j-4) if j!=4 else 0)
                    y=-d*.33+i*d*.085
                    self.chair(x,y,"orange" if kind=="lecture" else "dark")
                    if kind=="band":
                        self.box("谱架杆","metal",x,y+.31,.49,.041,.041,.98)
                        self.box("谱架面","metal",x,y+.31,1.0,.43,.07,.26)

    def finish(self, materials):
        for name,(verts,faces,slots) in self.groups.items():
            mesh=bpy.data.meshes.new(name)
            mesh.from_pydata(verts,[],faces)
            obj=bpy.data.objects.new(name,mesh)
            self.scene.collection.objects.link(obj)
            keys=list(dict.fromkeys(slots))
            for key in keys:
                mesh.materials.append(materials[key])
            mesh.polygons.foreach_set("material_index",[keys.index(key) for key in slots])


def lighting_and_camera(scene,w,d,h,kind):
    data=bpy.data.cameras.new("室内对照")
    data.lens=19 if kind!="dorm" else 16
    cam=bpy.data.objects.new("室内对照",data)
    scene.collection.objects.link(cam)
    cam.location=(-w*.12,-d*.38,1.57)
    cam.rotation_euler=(Vector((w*.12,d*.30,1.45))-cam.location).to_track_quat("-Z","Y").to_euler()
    scene.camera=cam
    for i in (-1,0,1):
        light=bpy.data.lights.new("室内面光","AREA")
        light.energy=25*w*d/10
        light.shape="RECTANGLE"
        light.size=w*.47
        light.size_y=d*.23
        lamp=bpy.data.objects.new("室内面光",light)
        scene.collection.objects.link(lamp)
        lamp.location=(0,d*.28*i,h-.26)
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.cycles.use_denoising=True
    scene.render.resolution_x,scene.render.resolution_y=600,450
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"


def compare(rows, previews, out):
    refs=ROOT.parent/"数据"/"04_建模参考"/"02_八方向"
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    for page,start in enumerate(range(0,len(rows),7),1):
        batch=rows[start:start+7]
        canvas=Image.new("RGB",(1052,48+len(batch)*236),"#f2eee4")
        draw=ImageDraw.Draw(canvas)
        draw.text((15,12),"室内还原 · 左侧原始全景参考，右侧模型视角 · 尺寸估算",font=font,fill="#203125")
        for i,(number,name) in enumerate(batch):
            sid=f"{number:02}"
            y=48+i*236
            draw.text((15,y),f"{sid}  {name}",font=font,fill="#203125")
            source=next(refs.glob(sid+"_*"))/"000.jpg"
            for j,path in enumerate((source,previews/f"{sid}.png")):
                with Image.open(path) as picture:
                    img=picture.convert("RGB")
                    img.thumbnail((495,199))
                    canvas.paste(img,(15+j*518,y+26))
        canvas.save(out/f"室内实景对照_{page}.png")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    initial=bpy.context.scene
    out=OUT/"室内"
    out.mkdir(parents=True,exist_ok=True)
    previews=out/"渲染"
    previews.mkdir(exist_ok=True)
    with (ROOT.parent/"数据"/"02_元数据"/"scenes.csv").open(encoding="utf-8-sig") as source:
        names={int(row["序号"]):row["名称"] for row in csv.DictReader(source)}
    mats={}
    for color,rgb in COLORS.items():
        mat=bpy.data.materials.new(color)
        mat.use_nodes=True
        shader=mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value=(*rgb,1)
        shader.inputs["Roughness"].default_value=.16 if color=="mirror" else .7
        shader.inputs["Metallic"].default_value=.88 if color=="mirror" else 0
        if color=="glass":
            shader.inputs["Emission Color"].default_value=(*rgb,1)
            shader.inputs["Emission Strength"].default_value=.6
        mat.diffuse_color=(*rgb,1)
        mats[color]=mat
    rows=[]
    scenes=[]
    for number,(w,d,h,kind) in ROOMS.items():
        sid=f"{number:02}"
        scene=bpy.data.scenes.new(f"{sid} {names[number]}")
        scenes.append(scene)
        scene.unit_settings.system="METRIC"
        scene["参考场景"]=sid
        scene["尺寸状态"]="按全景估算，实际楼层与门位待核实"
        room=Room(scene,w,d,h)
        floor="wood" if kind in {"meeting","activity","dance","aerobics"} else "tile"
        lower=("jade" if kind in {"class","lab","computer","art"} else
               "dark_wood" if kind in {"dance","aerobics"} else "birch")
        room.shell(floor,lower,max(2,round(d/2.25)))
        room.furniture(kind)
        room.finish(mats)
        lighting_and_camera(scene,w,d,h,kind)
        rows.append((number,names[number]))
    bpy.context.window.scene=scenes[1]
    bpy.data.scenes.remove(initial)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"校园室内样板.blend"))
    for scene,(number,name) in zip(scenes,rows):
        bpy.context.window.scene=scene
        sid=f"{number:02}"
        bpy.ops.export_scene.gltf(filepath=str(out/f"{sid}_{name}.glb"),export_format="GLB",
                                 use_active_scene=True,export_cameras=False,export_lights=False)
        scene.render.filepath=str(previews/f"{sid}.png")
        bpy.ops.render.render(write_still=True)
    compare(rows,previews,out)
    print("Interior scenes completed:",len(rows),flush=True)


if __name__=="__main__":
    main()
