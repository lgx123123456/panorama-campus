"""Refine the outdoor axis from the north edge of scene 05 to the library."""

import json
import math
from pathlib import Path

import bpy
import bmesh
import cv2
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import Polygon, box

from 地面街道实景细化 import Ground
from 图书馆照片还原 import material, open_campus, world
from 剩余楼栋与校园景观 import Planting, SiteDetails
from 四栋教学楼实景细化 import PALETTE, reference
from 尚德广场实拍细化 import photo_material


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/"成果"/"尚德广场实拍细化"/"校园室外_尚德广场实拍细化.blend"
OUT = ROOT/"成果"/"尚德至图书馆实拍细化"
SAMPLES = {
    "连廊灰石板": ("40","000",((236,532),(417,532),(480,697),(145,697)),2.38),
    "知远楼前石板": ("45","000",((249,527),(427,527),(484,696),(167,696)),2.38),
    "行远楼前石板": ("36","000",((229,551),(418,551),(455,695),(167,695)),2.40),
    "图书馆前石板": ("32","000",((257,536),(432,536),(493,698),(181,698)),2.40),
    "图书馆台阶石面": ("32","000",((273,361),(323,361),(322,366),(272,366)),.70),
    "图书馆前分类站实拍": ("32","315",((528,369),(660,372),(661,408),(528,402)),1.0),
}
VIEWS = (
    ("40","000","穿过连廊看主轴",(825,413),(813,214),1.62),
    ("45","000","知远楼前看图书馆",(827,339),(814,214),1.62),
    ("36","000","行远楼前与图书馆广场",(819,289),(819,213),1.62),
    ("32","000","图书馆正门台阶与前场",(811,260),(809,208),2.0),
    ("32","045","图书馆入口左侧与树阵",(811,260),(774,220),1.62),
    ("32","315","图书馆入口右侧与分类站",(811,260),(859,228),1.62),
)


def photo(label,spec):
    sid,yaw,quad,repeat=spec
    with Image.open(reference(sid,yaw)) as image:
        rgb=np.asarray(image.convert("RGB"))
    points=np.array(quad,np.float32)*np.float32([rgb.shape[1]/700,rgb.shape[0]/700])
    size=(720,240) if "分类站" in label else (768,768) if "石板" in label else (420,120)
    w,h=size
    target=np.array(((0,0),(w-1,0),(w-1,h-1),(0,h-1)),np.float32)
    crop=cv2.warpPerspective(rgb,cv2.getPerspectiveTransform(points,target),size,flags=cv2.INTER_CUBIC)
    if "石板" in label:
        # Reduce large baked shadows while preserving the original joints and grain.
        low=cv2.GaussianBlur(crop.astype(np.float32),(0,0),67)
        cropshift=np.median(low,axis=(0,1),keepdims=True)
        crop=np.clip(crop.astype(np.float32)+.49*(cropshift-low),0,255).astype(np.uint8)
    path=OUT/"实拍材质"/(label+".png")
    Image.fromarray(crop).save(path)
    tex=bpy.data.images.load(str(path),check_existing=True)
    tex.pack()
    mat=photo_material(label,tex,(.31,.30,.28),.87,repeat)
    mat.name="沿线实拍 · "+label
    return mat


def axis_ground(scene,materials):
    obj=scene.objects.get("教学主轴大块灰色石板")
    if obj:
        bpy.data.objects.remove(obj,do_unlink=True)
    helper=Ground.__new__(Ground)
    helper.scene=scene
    helper.batches={}
    helper.materials=materials
    helper.region("尚德至图书馆 · 连续铺装")
    layout=Polygon(((780,448),(868,447),(863,326),(872,286),(870,238),(883,222),
                    (753,215),(725,231),(707,244),(753,299),(771,332)))
    sectors=(
        ("连廊灰石板",(700,381,891,448)),
        ("知远楼前石板",(700,307,891,381)),
        ("行远楼前石板",(700,253,891,307)),
        ("图书馆前石板",(700,204,891,253)),
    )
    existing_pits=((788,405),(857,414),(793,380),(847,359),(783,344),(838,318),(783,285))
    new_pits=((792,313),(788,299),(786,273),(793,249),(784,233),(775,225),(769,253))
    for label,region in sectors:
        area=layout.intersection(box(*region))
        for x,y in existing_pits+new_pits:
            area=area.difference(box(x-1.22,y-1.22,x+1.22,y+1.22))
        helper.surface("沿线实拍 · "+label,label,area,.058)
    for x,y in new_pits:
        outer=box(x-1.23,y-1.23,x+1.23,y+1.23)
        inner=box(x-1.10,y-1.10,x+1.10,y+1.10)
        helper.surface("图书馆树池石边","stone",outer.difference(inner),.070)
        helper.surface("图书馆树池土底","soil",inner,.049)
        for delta in (-.77,-.42,0,.42,.77):
            helper.line("图书馆暗绿树阵格栅","green",(x-1,y+delta),(x+1,y+delta),.024,.069)
            helper.line("图书馆暗绿树阵格栅","green",(x+delta,y-1),(x+delta,y+1),.024,.069)
    for a,b in (((775,437),(782,383)),((864,436),(857,382)),
                ((781,371),(785,328)),((851,374),(845,328))):
        helper.line("临楼深灰条带","stone",a,b,.20,.063)
    for location in ((817,414),(839,365),(809,315),(856,268),(824,243)):
        helper.cover("沿线铸铁井盖",location,.063,.29,"iron")
    helper.build()
    return new_pits


def library_steps(scene,stone):
    # Reuse the already fitted stair envelope and all the existing steel railings.
    from 图书馆照片还原 import PLAN
    outline=next(row["outline"] for row in PLAN["buildings"] if row["id"]=="B32")
    left,right=world(outline[8]),world(outline[7])
    center=(left+right)/2
    east=(right-left).normalized()
    south=Vector((east.y,-east.x,0))
    item=SiteDetails(scene,{"stone":stone,
        "gold":material("B32 中央台阶黄褐立面",(.38,.20,.06),.82),
        "silver":material("B32 入口栏杆银灰",(.40,.44,.45),.35),
    }).zone("32 图书馆 · 台阶铺面与中央梯道",(0,0))
    item.anchor=center
    item.across,item.depth=east,-south
    for key in ("花岗岩台阶","入口平台"):
        obj=scene.objects.get(key)
        if not obj:
            continue
        obj.data.materials[0]=stone
        uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
        for face in obj.data.polygons:
            for i in face.loop_indices:
                p=obj.matrix_world@obj.data.vertices[obj.data.loops[i].vertex_index].co-center
                u=p.dot(east)/.72
                v=p.dot(south)/.37 if abs(face.normal.z)>.5 else p.z/.17
                uv.data[i].uv=(u,v)
    for i in range(6):
        tread=3.40-i*.17
        height=.23+i*.046
        y=-1.08-i*.33
        item.box("入口中部黄褐踏步","gold",0,y,tread+height/2,.96,.332,height)
        for x in (-.55,.55):
            item.box("中央踏步两侧石边","stone",x,y,tread+height/2+.04,.15,.332,height+.08)
    item.finish()


def vase(collection,center,scale,mat):
    profile=((0,.22),(.07,.22),(.11,.17),(.24,.11),(.31,.16),(.33,.26),
             (.43,.36),(.49,.39),(.54,.39),(.54,.327),(.48,.316),(.39,.15))
    count=32
    verts=[center+Vector((math.cos(i*math.tau/count)*r*scale,math.sin(i*math.tau/count)*r*scale,z*scale))
           for z,r in profile for i in range(count)]
    faces=[]
    for band in range(len(profile)-1):
        for i in range(count):
            k=(i+1)%count
            a=band*count
            faces.append((a+i,a+k,a+count+k,a+count+i))
    mesh=bpy.data.meshes.new("旋制花钵")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    mesh.materials.append(mat)
    for face in mesh.polygons:
        face.use_smooth=True
    obj=bpy.data.objects.new("图书馆阶前浅灰石花钵",mesh)
    collection.objects.link(obj)


def library_tree(plant,pixel,height):
    ground=world(pixel)+Vector((0,0,.063))
    fork=ground+Vector((0,0,height*.47))
    plant.limb("树干与分枝","lightbark",ground,fork,.115,.061)
    rng=plant.rng
    for index in range(11):
        angle=index*2.39996
        direction=Vector((math.cos(angle),math.sin(angle),0))
        root=ground.lerp(fork,.83+index*.014)
        branch=root+direction*rng.uniform(.50,.96)+Vector((0,0,rng.uniform(1.0,2.0)))
        plant.limb("树干与分枝","lightbark",root,branch,.033,.011)
        for _ in range(8):
            tip=branch+Vector((rng.uniform(-.63,.63),rng.uniform(-.63,.63),rng.uniform(.13,1.42)))
            plant.limb("细枝","lightbark",branch,tip,.010,.003)
            for _ in range(4):
                leaf=tip+Vector(tuple(rng.uniform(-.34,.34) for _ in range(3)))
                radius=rng.uniform(.14,.30)
                plant.crown("多簇叶冠或樱花",rng.choice(("olive","leaf","leaf","deep")),
                            leaf,radius,radius*.8,radius*1.21)


def remove_library_placeholders(scene):
    plants=scene.collection.children.get("校园绿化 · 树、花池、草地")
    if plants is None:
        return
    centers=[world((826,251)).xy,world((850,248)).xy]
    labels=("树干与分枝","细枝","多簇叶冠或樱花")
    for obj in plants.objects:
        if not obj.name.startswith(labels):
            continue
        mesh=bmesh.new()
        mesh.from_mesh(obj.data)
        obsolete=[v for v in mesh.verts
                  if any((v.co.xy-center).length<3.2 for center in centers)]
        bmesh.ops.delete(mesh,geom=obsolete,context="VERTS")
        mesh.to_mesh(obj.data)
        mesh.free()


def details(scene,materials,pits):
    remove_library_placeholders(scene)
    plant=Planting(scene)
    plant.group.name="32 图书馆前·树阵与主轴绿篱补植"
    for i,p in enumerate(pits):
        library_tree(plant,p,6.2+(i%3)*.34)
    for points in (((767,219),(786,220)),((836,220),(853,222),(869,222)),
                   ((864,302),(872,297),(879,293)),((774,376),(769,383),(772,389)),
                   ((854,368),(862,371),(867,378))):
        plant.hedge(points,.48)
    plant.finish()
    pots=bpy.data.collections.new("32 图书馆 · 石花钵")
    scene.collection.children.link(pots)
    for x,y,scale in ((792,229,1.33),(840,227,1.02),(846,225,.86),(782,225,.57)):
        vase(pots,world((x,y))+Vector((0,0,.058)),scale,materials["white"])
    site=SiteDetails(scene,materials)
    for o,n in enumerate(((783,220),(846,240),(790,275),(853,300),(786,368),(859,391))):
        item=site.zone("主轴灯柱 · "+str(o+1),n)
        item.box("深灰柱脚","slate",0,0,.19,.17,.17,.38)
        item.box("灯杆","dark",0,0,1.70,.076,.076,3.37)
        item.box("浅色椭圆灯罩","white",0,0,3.38,.23,.15,.18)
        item.box("黑色灯帽","slate",0,0,3.51,.26,.19,.065)
        item.finish()
    item=site.zone("32 图书馆右侧 · 分类回收设施",(866,246))
    item.across=Vector((0,-1,0))
    item.depth=Vector((1,0,0))
    item.box("分类站深灰后板","slate",0,.26,.92,3.5,.16,1.84)
    item.box("绿色防雨檐","green",0,0,1.96,3.70,.96,.12)
    for x in (-1.69,1.69):
        item.box("分类站立柱","slate",x,0,1.00,.071,.09,2.0)
    for x,key in zip((-1.24,-.41,.41,1.24),("blue","red","dark","green")):
        item.box("四色回收桶",key,x,-.12,.56,.72,.56,.96)
        item.box("投料盖",key,x,-.12,1.06,.74,.57,.075)
    label="图书馆前分类站实拍"
    coords=[item.point(x,-.412,z) for x,z in ((-1.60,.975),(1.60,.975),(1.60,.20),(-1.60,.20))]
    obj=item.link("分类桶实拍标识",coords,[(3,2,1,0)],materials[label])
    uv=obj.data.uv_layers.new()
    for loop in obj.data.loops:
        uv.data[loop.index].uv=((0,1),(1,1),(1,0),(0,0))[loop.vertex_index]
    item.finish()
    item=site.zone("32 图书馆入口左侧 · 空调外机",(792,220))
    for x,z in ((-.44,.44),(.44,.44),(-.44,1.06)):
        item.box("外机米灰外壳","white",x,0,z,.74,.31,.53)
        for i in range(6):
            item.box("散热片","slate",x,-.165,z-.20+.079*i,.56,.025,.018)
    item.finish()


def set_comparison_light(scene):
    sun=scene.objects.get("日光")
    sun.rotation_euler=Vector((.72,.74,-.69)).to_track_quat("-Z","Y").to_euler()
    sun.data.energy=3.1
    sun.data.angle=math.radians(4)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.72
    scene.view_settings.look="AgX - Medium High Contrast"
    scene.view_settings.exposure=.24


def compare():
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    for page,views in enumerate((VIEWS[:3],VIEWS[3:]),start=1):
        canvas=Image.new("RGB",(1110,1164),"#f0ece3")
        draw=ImageDraw.Draw(canvas)
        draw.text((12,10),"尚德广场至图书馆 · 左为原始实景，右为模型估算视角",
                  font=font,fill="#273128")
        for i,(sid,angle,label,*_) in enumerate(views):
            y=42+i*371
            draw.text((12,y),f"{sid}/{angle}  {label}",font=font,fill="#273128")
            for j,path in enumerate((reference(sid,angle),OUT/"模型视角"/f"{sid}_{angle}.png")):
                with Image.open(path) as pic:
                    canvas.paste(ImageOps.fit(pic.convert("RGB"),(540,337)),(11+549*j,y+24))
        canvas.save(OUT/f"沿线实景对照_{page}.png")


def main():
    (OUT/"实拍材质").mkdir(parents=True,exist_ok=True)
    (OUT/"模型视角").mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    mats={name:photo(name,spec) for name,spec in SAMPLES.items()}
    mats.update({key:material("沿线 "+name,rgb,rough) for key,(name,rgb,rough) in PALETTE.items()
                 if key in ("stone","white","green","blue","red","slate","dark")})
    mats.update({"soil":material("沿线 树池灰褐表土",(.17,.13,.076),.95),
                 "iron":material("沿线 铸铁井盖",(.077,.079,.077),.89),
                 "joint":material("沿线 井盖压纹",(.146,.14,.12),.89)})
    pits=axis_ground(scene,mats)
    library_steps(scene,mats["图书馆台阶石面"])
    details(scene,mats,pits)
    set_comparison_light(scene)
    cameras=[]
    for sid,angle,name,eye,target,aim in VIEWS:
        lens=bpy.data.cameras.new(sid+"/"+angle+" "+name)
        lens.lens=16.5
        camera=bpy.data.objects.new(lens.name,lens)
        scene.collection.objects.link(camera)
        camera.location=world(eye)+Vector((0,0,1.63))
        camera.rotation_euler=(world(target)+Vector((0,0,aim))-camera.location).to_track_quat("-Z","Y").to_euler()
        cameras.append((camera,sid,angle))
    scene.camera=cameras[3][0]
    scene.render.resolution_x=scene.render.resolution_y=840
    scene.cycles.samples=16
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_尚德至图书馆细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_尚德至图书馆细化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for camera,sid,angle in cameras:
        scene.camera=camera
        scene.render.filepath=str(OUT/"模型视角"/f"{sid}_{angle}.png")
        bpy.ops.render.render(write_still=True)
    compare()
    (OUT/"实拍来源与路线.json").write_text(json.dumps({
        "路线":["05 尚德广场北缘","40 艺远楼与识远楼桥下","45 知远楼前","36 行远楼前","32 图书馆台阶前"],
        "贴图坐标":"700×700参考图坐标，运行时映射至全分辨率方向图",
        "样本":SAMPLES,"尺度":"地物、石板模数及相机位按航拍和地面照估算",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
