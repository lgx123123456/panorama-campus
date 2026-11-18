"""Integrate the missing gate assembly and rectify selected photograph patches."""

import json
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps

from 图书馆照片还原 import open_campus, world
from 四栋教学楼实景细化 import reference


ROOT = Path(__file__).resolve().parent
OUT = ROOT/"成果"/"大门逐图校准"
SHOTS = OUT/"网页实景截图"
SOURCE = ROOT/"成果"/"剩余楼栋与景观细化"/"校园室外_楼栋道路与绿化.blend"
STUDY = ROOT.parent/"校门还原小样"/"校门与尚德广场.blend"
MATERIALS = {
    "门前混凝土": ("03","000",[(369,531),(430,532),(465,681),(370,681)],2.20),
    "湘江道旧混凝土": ("03","180",[(220,529),(340,528),(350,682),(192,683)],2.55),
    "尚德广场石板": ("05","000",[(168,498),(252,497),(226,528),(129,528)],.61),
    "教学区石板": ("40","000",[(308,529),(427,529),(438,586),(312,586)],.60),
    "运动场深绿草皮": ("09","000",[(126,565),(278,566),(287,689),(81,689)],1.53),
    "运动场浅绿草皮": ("09","000",[(439,571),(577,571),(652,690),(452,690)],1.53),
    "门房花岗岩": ("03","315",[(275,287),(320,294),(320,314),(275,309)],.52),
}
VIEWS = (
    ("门外正面","03_门外正面",(0,-11.6,1.6),(0,0,1.6),18.0),
    ("门外左门房","03_门外左门房",(0,-11.6,1.6),(-10.5,-.2,1.6),18.5),
    ("门外右门房","03_门外右门房",(0,-11.6,1.6),(10.5,-.2,1.6),18.5),
    ("门内回望","05_门内回望",(0,11.05,1.6),(0,0,1.6),18.0),
    ("门前铺地","03_门前铺地",(0,-11.6,1.6),(0,-.4,-2.58),18.0),
)


def rectify(label, spec):
    sid,direction,quad,period=spec
    source=reference(sid,direction)
    with Image.open(source) as img:
        arr=np.asarray(img.convert("RGB"))
    size=512
    corners=np.asarray(quad,np.float32)*np.float32([arr.shape[1]/700,arr.shape[0]/700])
    to=np.asarray(((0,0),(size-1,0),(size-1,size-1),(0,size-1)),np.float32)
    result=cv2.warpPerspective(arr,cv2.getPerspectiveTransform(corners,to),(size,size),
                               flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)
    # Taper the cyclic border from the two sides to avoid repeat seams.
    work=result.astype(np.float32)
    for dimension in (0,1):
        view=work if dimension==0 else work.transpose(1,0,2)
        for i in range(39):
            amount=(1-i/39)**2*.5
            low=view[i].copy()
            high=view[-i-1].copy()
            view[i]=low*(1-amount)+high*amount
            view[-i-1]=high*(1-amount)+low*amount
    texture=OUT/"实拍材质"/(label+".jpg")
    Image.fromarray(np.clip(work,0,255).astype(np.uint8)).save(texture,quality=96)
    return texture,period


def bind_photo(obj,texture,period,label,vertical=False):
    old=obj.data.materials[0]
    mat=old.copy()
    mat.name="实拍纹理 · "+label
    image=bpy.data.images.load(str(texture),check_existing=True)
    if not image.packed_file:
        image.pack()
    tree=mat.node_tree
    shader=next(n for n in tree.nodes if n.type=="BSDF_PRINCIPLED")
    for link in list(shader.inputs["Base Color"].links):
        tree.links.remove(link)
    tex=tree.nodes.new("ShaderNodeTexImage")
    tex.image=image
    tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
    obj.data.materials[0]=mat
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
    for polygon in obj.data.polygons:
        normal=obj.matrix_world.to_3x3()@polygon.normal
        for i in polygon.loop_indices:
            vertex=obj.data.loops[i].vertex_index
            pos=obj.matrix_world@obj.data.vertices[vertex].co
            if vertical and abs(normal.z)<max(abs(normal.x),abs(normal.y)):
                u=pos.y if abs(normal.x)>abs(normal.y) else pos.x
                uv.data[i].uv=(u/period,pos.z/period)
            else:
                uv.data[i].uv=(pos.x/period,pos.y/period)
    obj["照片来源"]=label


def gate_assembly(scene,center):
    name="03 铁艺门及门岗"
    with bpy.data.libraries.load(str(STUDY),link=False) as (available,loaded):
        assert name in available.collections
        loaded.collections=[name]
    group=loaded.collections[0]
    scene.collection.children.link(group)
    bpy.context.view_layer.update()
    scale=scene["校门小样缩放"]
    transform=Matrix.Translation(Vector((center.x,center.y,.046)))@Matrix.Scale(scale,4)
    matrices={obj: obj.matrix_world.copy() for obj in group.all_objects}
    for obj,matrix in matrices.items():
        obj.parent=None
        obj.matrix_world=transform@matrix
        obj["照片对照"]="720云大门外场景03和门内场景05"
    return group


def comparison():
    size=(675,430)
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
    canvas=Image.new("RGB",(1380,49+len(VIEWS)*469),"#efebe1")
    draw=ImageDraw.Draw(canvas)
    draw.text((13,14),"大门逐图校准 · 左为720云真实网页，右为对应模型估算视角",font=font,fill="#222b23")
    for i,(name,shot,*_) in enumerate(VIEWS):
        y=50+i*469
        draw.text((13,y),name,font=font,fill="#222b23")
        for j,path in enumerate((SHOTS/(shot+".png"),OUT/"模型视角"/(name+".png"))):
            with Image.open(path) as im:
                canvas.paste(ImageOps.fit(im.convert("RGB"),size),(12+j*685,y+28))
    canvas.save(OUT/"大门实景与模型对照.png")


def main():
    (OUT/"实拍材质").mkdir(parents=True,exist_ok=True)
    (OUT/"模型视角").mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    center=world((821,521))
    group=gate_assembly(scene,center)
    objects={
        "门前混凝土":("校门浅灰混凝土地坪","校门内侧与门厅衔接处"),
        "湘江道旧混凝土":("两条车行道与交叉口",),
        "尚德广场石板":("尚德广场暖灰石板","尚德广场至主轴连续铺底"),
        "教学区石板":("教学主轴大块灰色石板",),
        "运动场深绿草皮":("P09_pitch",),
        "运动场浅绿草皮":tuple(o.name for o in scene.objects if o.name.startswith("P09_turf_")),
        "门房花岗岩":tuple(o.name for o in scene.objects if o.name.startswith(
            ("门房灰石外墙","门房檐线","花岗岩主柱"))),
    }
    for label,spec in MATERIALS.items():
        tex,period=rectify(label,spec)
        for name in objects[label]:
            item=scene.objects.get(name)
            if item:
                bind_photo(item,tex,period,f"{spec[0]}/{spec[1]} {label}",label=="门房花岗岩")
    cameras=[]
    for name,_,eye,target,lens in VIEWS:
        data=bpy.data.cameras.new(name)
        data.lens=lens
        camera=bpy.data.objects.new(name,data)
        scene.collection.objects.link(camera)
        camera.location=center+Vector(eye)
        camera.rotation_euler=(center+Vector(target)-camera.location).to_track_quat("-Z","Y").to_euler()
        cameras.append(camera)
    scene.camera=cameras[0]
    scene.render.resolution_x,scene.render.resolution_y=1080,690
    scene.render.resolution_percentage=100
    scene.cycles.samples=20
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_大门逐图校准.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_大门逐图校准.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for camera in cameras:
        scene.camera=camera
        scene.render.filepath=str(OUT/"模型视角"/(camera.name+".png"))
        bpy.ops.render.render(write_still=True)
    comparison()
    (OUT/"贴图与构件来源.json").write_text(json.dumps({
        "网页截图":"720云大门03与尚德广场05，1440×920原页面截图保留界面",
        "贴图控制点":"坐标以700×700预览为基准，取原图进行透视拉正",
        "照片贴图":MATERIALS,
        "铁艺门及门岗":"对照网页截图，接回校门小样中缺失的193个门扇、道闸和两侧门岗构件",
        "尺度":"沿用航拍估算米制，门楼绝对尺寸和场景相机站位仍待实测",
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("Gate parts",len(group.all_objects),"photo materials",len(MATERIALS))


if __name__=="__main__":
    main()
