"""Rebuild four teaching block fronts from their ground panoramas."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps

from 图书馆照片还原 import material, open_campus, world


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果" / "主轴连廊实景样板" / "校园室外_主轴实景细化.blend"
OUT = ROOT / "成果" / "教学楼实景细化"
REFS = ROOT.parent / "数据" / "04_建模参考" / "02_八方向"
PLAN = json.loads((ROOT / "总图标注.json").read_text(encoding="utf-8"))
PALETTE = {
    "ochre": ("暖黄色墙板", (.68, .355, .043), .76),
    "ochre_dark": ("檐底黄色", (.47, .218, .030), .77),
    "joint": ("墙板接缝", (.29, .15, .032), .84),
    "slate": ("深灰结构", (.093, .108, .117), .83),
    "dark": ("窗槽与进深阴影", (.028, .032, .032), .83),
    "glass": ("蓝灰玻璃", (.069, .149, .194), .22),
    "sideglass": ("玻璃块", (.105, .233, .293), .32),
    "silver": ("栏杆", (.39, .42, .44), .29),
    "stone": ("灰色入口台阶", (.215, .229, .233), .82),
    "greybrick": ("灰砖", (.235, .238, .217), .93),
    "redbrick": ("红砖", (.26, .141, .111), .92),
    "red": ("红色公告栏立柱", (.47, .035, .024), .68),
    "blue": ("蓝色公告栏与垃圾桶", (.020, .13, .39), .57),
    "white": ("浅色公告栏边框", (.63, .67, .65), .68),
    "green": ("分类桶绿色", (.055, .30, .13), .59),
    "lettering": ("浅金楼名", (.64, .48, .22), .47),
}
CASES = {
    "15": ("志远楼", "000", "045", "志远楼近景：双开门、上层栏杆和实拍公告栏"),
    "21": ("思远楼", "000", "045", "思远楼近景：单入口、玻璃门楣和木廊架"),
    "36": ("行远楼", "315", "270", "行远楼：端墙条窗、凸出阳台和南侧接桥"),
    "45": ("知远楼", "315", "090", "知远楼：黄色端墙、蓝灰转角和北侧接桥"),
}
FACES = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))


def reference(sid, angle):
    return next(REFS.glob(sid + "_*")) / (angle + ".jpg")


class Building:
    def __init__(self, scene, sid, label, points, height, materials):
        a,b,c,d = map(world, points)
        self.anchor = (a+d)/2
        self.across = (d-a).normalized()
        self.depth = Vector((-self.across.y, self.across.x, 0))
        self.width = (d-a).length
        self.length = ((b+c)/2-self.anchor).dot(self.depth)
        self.height, self.sid, self.name = height, sid, label
        self.collection = bpy.data.collections.new(f"B{sid} {label} · 逐图细化")
        scene.collection.children.link(self.collection)
        self.materials, self.groups = materials, {}
        if self.length <= 0:
            raise ValueError(f"Invalid building orientation {sid}")

    def point(self, x, y, z):
        point = self.anchor + self.across*x + self.depth*y
        point.z = z
        return point

    def box(self, group, key, x, y, z, width, depth, height):
        verts, faces = self.groups.setdefault((group,key), ([],[]))
        start = len(verts)
        verts.extend(self.point(x+a*width/2,y+b*depth/2,z+c*height/2)
                     for a,b,c in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                   (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)))
        faces.extend(tuple(start+i for i in face) for face in FACES)

    def link(self, label, verts, faces, mat):
        name = f"B{self.sid} {label}"
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts,[],faces)
        mesh.update()
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(name,mesh)
        self.collection.objects.link(obj)
        return obj

    def photo_panel(self, label, angle, coords, x, y, z, width, height):
        mat = material(f"B{self.sid} {label}",(.42,.42,.42),.75)
        shader = mat.node_tree.nodes.get("Principled BSDF")
        texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(str(reference(self.sid,angle)),check_existing=True)
        if not texture.image.packed_file:
            texture.image.pack()
        for socket in ("Base Color","Emission Color"):
            mat.node_tree.links.new(texture.outputs["Color"],shader.inputs[socket])
        shader.inputs["Emission Strength"].default_value=.29
        verts = [self.point(xx,y,zz) for xx,zz in (
            (x-width/2,z+height/2),(x+width/2,z+height/2),
            (x+width/2,z-height/2),(x-width/2,z-height/2))]
        obj = self.link(label,verts,[(3,2,1,0)],mat)
        uv = obj.data.uv_layers.new().data
        for loop in obj.data.loops:
            u,v = coords[loop.vertex_index]
            uv[loop.index].uv = (u/700,1-v/700)
        obj["实拍来源"] = f"{self.sid}/{angle}.jpg"

    def railing(self, label, x1, x2, depth, base, height=.88):
        for i in range(3):
            self.box(label,"silver",(x1+x2)/2,depth,base+.10+i*(height-.10)/2,x2-x1,.034,.036)
        count = max(2,math.ceil((x2-x1)/.15))
        for i in range(count+1):
            self.box(label,"silver",x1+i*(x2-x1)/count,depth,base+height/2,.023,.023,height)

    def wall_with_slots(self, label, x1, x2, z1, z2, slots):
        """Leave an actual aperture in each photographed horizontal slot."""
        current = z1
        for low,high,left,right in slots:
            if low > current:
                self.box(label,"ochre",(x1+x2)/2,.06,(current+low)/2,x2-x1,.30,low-current)
            for a,b in ((x1,left),(right,x2)):
                if b > a:
                    self.box(label,"ochre",(a+b)/2,.06,(low+high)/2,b-a,.30,high-low)
            self.box("条窗退后玻璃","dark",(left+right)/2,.49,(low+high)/2,
                     right-left,.08,high-low)
            current = high
        if current < z2:
            self.box(label,"ochre",(x1+x2)/2,.06,(current+z2)/2,x2-x1,.30,z2-current)

    def sides(self):
        length,width,height=self.length,self.width,self.height
        # Orthogonal roof and side layout are estimated from the aerial footprint.
        self.box("屋顶","slate",0,length/2,height-.19,width,length,.38)
        self.box("底板","stone",0,length/2,.05,width,length,.10)
        self.box("后墙占位","slate",0,length-.15,height/2,width,.30,height)
        for side in (-1,1):
            x=side*(width/2-.12)
            self.box("长边内衬","slate",x,length/2,height/2,.23,length,height)
            zone = length*(.31 if self.sid in ("36","45") else .19)
            self.box("长边玻璃转角","glass",x+side*.20,zone/2+1.05,height/2,
                     .21,zone-.65,height-1.27)
            for y in (2.2,4.1,6.0,7.9,9.8):
                if y < zone:
                    self.box("转角纵梃","slate",x+side*.32,y,height/2,.16,.083,height-1.25)
            for z in (1.7,3.3,5,6.65,8.3,9.95,11.6,13.25,14.9,16.55,18.2):
                self.box("转角玻璃横梃","slate",x+side*.33,zone/2+1.05,z,.17,zone-.58,.081)
            for z in (3.4,height-.55):
                self.box("侧墙连续黄色檐带","ochre",x+side*.25,length/2,z,.72,length,.75)
            for y in (1.04,zone+1.05,length-.8):
                self.box("侧墙通高黄柱","ochre",x+side*.23,y,height/2,.62,.86,height)
            # Preserve a background wall beyond the detailed corner.
            span=length-zone-2
            steps=max(2,round(span/2.45))
            for i in range(steps):
                yy=zone+1.42+(i+.5)*span/steps
                for z in (1.25,5.25,8.75,12.25,15.75):
                    self.box("长边可见窗组","glass",x+side*.15,yy,z,.20,span/steps-.36,2.43)

    def storefront(self, double=False, steps=3):
        w=self.width
        bottom=.16*steps
        self.box("首层退后墙","slate",0,1.30,1.87,w,.25,3.74)
        self.box("首层上梁","slate",0,.80,3.49,w,1.65,.51)
        count=2 if double else 1
        door_centers=(-1.84,1.84) if double else (.72,)
        for i,x in enumerate(door_centers):
            span=2.64 if double else 3.18
            self.box("门洞进深","dark",x,1.12,bottom+1.22,span,.10,2.44)
            for side in (-1,1):
                self.box("门洞两侧门框","silver",x+side*span/2,-.17,bottom+1.33,.10,.22,2.68)
                self.box("门侧玻璃固定扇","glass",x+side*(span/2-.24),-.11,
                         bottom+1.16,.42,.085,2.26)
                self.box("玻璃门蓝贴条","blue",x+side*(span/2-.24),-.161,bottom+1.05,.42,.025,.072)
            self.box("门头上窗","glass",x,-.06,bottom+2.79,span,.095,.44)
            self.box("门框上横梃","silver",x,-.17,bottom+2.54,span,.18,.084)
        entry_width=8.9 if double else 5.1
        for i in range(steps):
            height=(i+1)*.16
            self.box("石阶踏步","stone",0,-1.73+i*.34,height/2,entry_width,.37,height)
            self.box("踏步前缘","silver",0,-1.89+i*.34,height-.026,entry_width,.042,.045)
        self.box("门前平台","stone",0,-.47,bottom/2,entry_width,1.12,bottom)
        if count==2:
            for x in (-4.25,4.25):
                self.railing("入口平台护栏",x-.87,x+.87,-.88,bottom,.79)

    def small_entrance(self):
        self.storefront(double=self.sid=="15",steps=3 if self.sid=="15" else 4)
        w=self.width
        self.box("入口黄色挑檐","ochre",0,-.61,3.93,w,1.34,.68)
        self.box("灰色檐底","slate",0,-.73,3.58,w-.36,1.08,.115)
        for level in (4.32,8.04,11.76,15.48):
            self.box("退台阳台后墙","slate",0,.80,level+1.32,w,.18,2.64)
            for phase in (-1,1):
                center=phase*w*.218
                self.box("退台阳台玻璃","glass",center,.69,level+1.30,w*.246,.12,2.12)
                self.railing("阳台实杆",center-w*.11,center+w*.11,-.42,level,.87)
            self.box("阳台楼板和黄腰带","ochre",0,.065,level-.15,w,1.02,.36)
        for x,ratio in ((0,.22),(-w*.45,.10),(w*.448,.103)):
            self.box("端面黄色竖板","ochre",x,-.08,11.50,w*ratio,.45,15.02)
        if self.sid=="15":
            self.box("玻璃砖竖槽","sideglass",w*.319,.12,11.62,.95,.23,13.80)
            for i in range(28):
                self.box("玻璃砖横缝","slate",w*.319,-.017,4.77+.48*i,.94,.026,.025)
        self.notice_and_paving()

    def notice_and_paving(self):
        is_zhiyuan=self.sid=="15"
        shift=-4.1 if is_zhiyuan else -3.95
        panels=(
            ((204,285),(434,285),(434,421),(204,421)),
            ((468,285),(575,287),(575,413),(468,413)),
        ) if is_zhiyuan else (
            ((50,282),(243,303),(243,400),(50,416)),
            ((270,306),(340,309),(339,389),(270,394)),
            ((359,313),(450,316),(450,383),(359,389)),
        )
        for i,coords in enumerate(panels):
            x=shift+(i-1)*1.36
            self.box("公告栏红色立柱","red",x-.69,-2.23,.93,.10,.11,1.86)
            self.box("公告栏浅边","white",x,-2.27,1.21,1.36,.14,.81)
            self.box("公告栏雨帽","blue" if i==1 else "white",x,-2.24,1.84,1.48,.43,.073)
            self.photo_panel(f"实拍公告栏{i+1}","090" if is_zhiyuan else "045",coords,
                             x,-2.348,1.21,1.28,.72)
        if not is_zhiyuan:
            self.photo_panel("思远楼门楣实拍","000",((286,253),(413,248),(411,281),(286,285)),
                             .72,-.19,3.36,2.90,.32)
        self.bins((4.0,4.53,5.06,5.59) if not is_zhiyuan else (-4.78,),-1.75)
        for j in range(13):
            for i in range(30):
                key="redbrick" if (i+3*j)%7 in (0,1) else "greybrick"
                x=(i-14.5)*.34+((j%2)*.17)
                self.box("入口红灰错缝砖铺",key,x,-2.50-.177*j,.060,.327,.165,.018)

    def bins(self, locations, y):
        keys=("blue","blue","dark","dark") if self.sid in ("15","21") else ("blue","red","dark","green")
        for i,x in enumerate(locations):
            key=keys[i%len(keys)]
            self.box("分类桶桶身",key,x,y,.44,.44,.43,.78)
            self.box("分类桶盖",key,x,y,.855,.50,.48,.071)
            self.box("分类桶浅色标示","white",x,y-.221,.54,.16,.018,.14)

    def tower(self):
        w,h=self.width,self.height
        is_xing=self.sid=="36"
        self.box("灰色底层","slate",0,.52,1.59,w,1.38,3.18)
        for i in range(8):
            x=(i-3.5)*w/9
            self.box("转角底层连续玻璃","glass",x,-.22,1.58,w/9-.13,.14,2.52)
        self.box("底层黄色带","ochre",0,-.31,3.30,w,.65,.62)
        x1,x2=-w*.48,w*.31
        slots=[(4.02,6.59,-w*.28,w*.10)]
        for level in (8.0,11.56,15.12):
            slots.extend((level+j*.79,level+j*.79+.34,-w*.255,w*.070) for j in (0,1))
        self.wall_with_slots("主轴端面有洞口的黄墙",x1,x2,3.6,h-.10,slots)
        self.railing("端面低层大开口栏杆",-w*.27,w*.095,-.115,4.09,.90)
        self.box("阳台灰色竖井","dark",w*.402,.31,(h+3.6)/2,w*.178,.26,h-3.6)
        for level in (6.55,10.06,13.54,17.04):
            self.box("悬挑阳台灰板","slate",w*.412,-.33,level,w*.167,1.28,.35)
            self.box("阳台遮板","stone",w*.412,-.69,level+.41,w*.155,.21,.62)
            self.railing("阳台护栏",w*.337,w*.484,-.72,level+.23,.75)
        for z in (7.56,11.04,14.57,18.07):
            self.box("端面板材分缝","joint",-.075*w,-.102,z,w*.78,.014,.017)
        roof_x=-w*.07
        if is_xing:
            for x in (roof_x-2.0,roof_x+2.0):
                self.box("屋顶设备框立墙","ochre",x,1.87,h+1.42,.44,4.0,2.9)
            self.box("屋顶设备框顶梁","ochre",roof_x,.58,h+2.73,4.49,.44,.44)
            self.box("屋顶设备框底梁","ochre",roof_x,.58,h+.14,4.49,.44,.34)
        else:
            self.box("屋顶设备间后墙","ochre_dark",roof_x,3.55,h+1.44,4.25,.34,2.94)
            for i in range(6):
                x=roof_x+(i-2.5)*.67
                self.box("顶部孔板竖肋","ochre",x,.86,h+1.49,.48,.44,2.96)
            for j in range(5):
                self.box("顶部孔板横肋","ochre",roof_x,.86,h+.12+j*.66,4.13,.44,.43)
        self.bins((-.94,-.44,.06,.56),-.62)

    def nameplate(self, font):
        sign="行远楼" if self.sid=="36" else "知远楼"
        for i,char in enumerate(sign):
            name=f"B{self.sid} 楼名 {char}"
            text=bpy.data.curves.new(name,"FONT")
            text.body=char
            text.font=font
            text.size=.60
            text.extrude=.012
            text.align_x="CENTER"
            text.materials.append(self.materials["lettering"])
            obj=bpy.data.objects.new(name,text)
            self.collection.objects.link(obj)
            obj.location=self.point(-self.width*.397,-.107,12.7-i*.78)
            obj.rotation_euler=(-self.depth).to_track_quat("Z","Y").to_euler()
            obj["来源"]="本地场景名称，按照片位置重制文字"

    def finish(self):
        for (label,color),(verts,faces) in self.groups.items():
            self.link(label,verts,faces,self.materials[color])

    def camera(self, angle, position, target, focal):
        label=f"{self.sid} 参考 {angle}"
        camera=bpy.data.cameras.new(label)
        camera.lens=focal
        obj=bpy.data.objects.new(label,camera)
        self.collection.objects.link(obj)
        obj.location=self.point(*position)
        obj.rotation_euler=(self.point(*target)-obj.location).to_track_quat("-Z","Y").to_euler()
        return obj


def teaching_bridge(scene, materials):
    # Scene 36/270 faces the bridge between the photographed teaching wings.
    # The facing edges here come from the provisional aerial footprint.
    outline = [(875,266),(883,265),(883,327),(875,326)]
    bridge = Building(scene,"36","行远楼与知远楼低层连廊",outline,8.6,materials)
    w = bridge.width
    bridge.box("连廊黄色底带","ochre",0,.57,4.00,w+.28,3.7,.64)
    bridge.box("连廊楼板","slate",0,.55,4.42,w,3.48,.26)
    bridge.box("连廊顶板","slate",0,.55,8.18,w,3.48,.31)
    for y in (-1.02,2.18):
        bridge.box("连廊连续窗","glass",0,y,6.05,w,.135,3.00)
        for i in range(25):
            x = (i-12)*w/24
            bridge.box("连廊窗格竖梃","slate",x,y,6.08,.065,.20,2.99)
        for z in (4.56,5.26,5.96,6.66,7.36):
            bridge.box("连廊窗格横梃","silver",0,y,z,w,.20,.058)
    for i in range(7):
        x = (i-3)*w/6.6
        bridge.box("连廊灰柱","stone",x,-.65,2.00,.34,.39,4.00)
        bridge.box("连廊窗间柱","stone",x,-1.10,6.00,.32,.34,3.03)
    for i in range(36):
        x=(i-17.5)*w/36
        bridge.box("连廊前树篱","green",x,-3.45,.30,w/36+.05,1.03,.60)
    bridge.box("连廊标语衬板","white",0,-1.11,7.82,w,.15,1.06)
    bridge.photo_panel("连廊实拍标语","270",
                       ((117,233),(576,229),(575,261),(116,263)),
                       0,-1.192,7.82,w-.05,1.01)
    bridge.finish()
    return bridge.camera("270",(0,-22,1.64),(0,0,4.15),19)


def compare():
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    for sid,(_,first,second,caption) in CASES.items():
        image=Image.new("RGB",(1220,690),"#eeebe3")
        draw=ImageDraw.Draw(image)
        draw.text((12,12),caption,font=font,fill="#202923")
        for i,angle in enumerate((first,second)):
            for j,path in enumerate((reference(sid,angle),OUT/f"{sid}_{angle}.png")):
                x=10+(i*2+j)*302
                draw.text((x,43),f"{angle}° {'实景' if j==0 else '模型'}",font=font,fill="#202923")
                with Image.open(path) as pic:
                    image.paste(ImageOps.fit(pic.convert("RGB"),(292,292)),(x,73))
        image.crop((0,0,1220,376)).save(OUT/f"{sid}_实景对照.png")


VIEWS = {
    "15": (((1.0,-6.2,1.60),(0,0,1.8),20),((-4.8,-5.5,1.6),(-.4,-.6,2),18)),
    "21": (((1.28,-5.8,1.61),(.4,0,1.60),20),((-4.6,-6.0,1.6),(-1.0,-1.0,1.65),18)),
    "36": (((7.0,-17.0,1.65),(0,.6,6.8),20),),
    "45": (((-8.9,-17.6,1.65),(0,1.2,6.9),19),((.10,-22.5,1.65),(0,0,6.0),21)),
}


def main():
    OUT.mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    materials={key:material(name,rgb,roughness) for key,(name,rgb,roughness) in PALETTE.items()}
    font=bpy.data.fonts.load("C:/Windows/Fonts/simhei.ttf",check_existing=True)
    views=[]
    for sid,(label,first,second,_) in CASES.items():
        prefix="B"+sid
        for obj in list(scene.objects):
            if obj.name==prefix or obj.name.startswith(prefix+"_"):
                bpy.data.objects.remove(obj,do_unlink=True)
        data=next(s for s in PLAN["buildings"] if s["id"]==prefix)
        building=Building(scene,sid,label,data["outline"],data["height"],materials)
        building.sides()
        if sid in ("15","21"):
            building.small_entrance()
        else:
            building.tower()
            building.nameplate(font)
        building.finish()
        for angle,params in zip((first,second),VIEWS[sid]):
            views.append((building.camera(angle,*params),sid,angle))
    views.append((teaching_bridge(scene,materials),"36","270"))
    scene.camera=next(cam for cam,sid,angle in views if (sid,angle)==("45","315"))
    scene.render.resolution_x=scene.render.resolution_y=760
    scene.cycles.samples=20
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.51
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_四栋教学楼细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_四栋教学楼细化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for camera,sid,angle in views:
        scene.camera=camera
        scene.render.filepath=str(OUT/f"{sid}_{angle}.png")
        bpy.ops.render.render(write_still=True)
    compare()


if __name__=="__main__":
    main()
