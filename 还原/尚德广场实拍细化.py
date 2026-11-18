"""Rebuild only scene 05 from the aerial footprint and its panorama photographs."""

import json
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import Polygon, box

from 地面街道实景细化 import Ground
from 图书馆照片还原 import material, open_campus, world
from 四栋教学楼实景细化 import Building, reference


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/"成果"/"大门逐图校准"/"校园室外_大门逐图校准.blend"
OUT = ROOT/"成果"/"尚德广场实拍细化"
SAMPLES = {
    "广场石板": ("270", ((275,474),(483,474),(625,666),(124,666)), (900,900)),
    "池边深色石材": ("000", ((45,461),(206,461),(206,464),(44,464)), (420,32)),
    "水面波纹": ("000", ((170,414),(229,414),(238,451),(191,451)), (480,480)),
    "景石石纹": ("000", ((287,344),(316,341),(316,348),(287,350)), (260,92)),
    "西侧六格宣传栏": ("090", ((362,331),(634,332),(634,367),(361,369)), (1200,155)),
    "东侧六格宣传栏": ("270", ((61,332),(336,332),(336,370),(61,370)), (1200,170)),
}
VIEWS = (
    ("000","门内向北看喷泉与景石",(821.5,488),(821.5,453),1.62),
    ("090","向西看铺地与宣传栏",(821.5,488),(777,487),1.62),
    ("180","向南回望大门及地面交界",(821.5,488),(821.5,520),1.62),
    ("270","向东看铺地与宣传栏",(821.5,488),(873,487),1.62),
)


def rectify(name, spec):
    angle,quad,(width,height)=spec
    with Image.open(reference("05",angle)) as original:
        src=np.asarray(original.convert("RGB"))
    points=np.asarray(quad,np.float32)*np.float32([src.shape[1]/700,src.shape[0]/700])
    corners=np.asarray(((0,0),(width-1,0),(width-1,height-1),(0,height-1)),np.float32)
    result=cv2.warpPerspective(src,cv2.getPerspectiveTransform(points,corners),(width,height),
                               flags=cv2.INTER_CUBIC)
    if name=="水面波纹":
        # Retain the captured ripples while reducing the baked sky/column color.
        grey=cv2.cvtColor(result,cv2.COLOR_RGB2GRAY).astype(np.float32)
        grey=np.clip(49+(grey-cv2.GaussianBlur(grey,(0,0),17))*.87,18,105)
        result=np.stack((grey*.68,grey*.83,grey*.98),axis=-1).astype(np.uint8)
        for axis in (0,1):
            arr=result if axis==0 else result.transpose(1,0,2)
            for row in range(35):
                factor=.5*(1-row/35)**2
                a,b=arr[row].astype(float),arr[-row-1].astype(float)
                arr[row]=(a*(1-factor)+b*factor).astype(np.uint8)
                arr[-row-1]=(b*(1-factor)+a*factor).astype(np.uint8)
    path=OUT/"实拍材质"/(name+".png")
    Image.fromarray(result).save(path)
    image=bpy.data.images.load(str(path),check_existing=True)
    image.pack()
    return image


def photo_material(label,image,rgb,roughness,period=1,reflect=False):
    mat=material("05 实拍 · "+label,rgb,roughness)
    mat["UV周期米"]=period
    nodes=mat.node_tree.nodes
    shader=next(node for node in nodes if node.type=="BSDF_PRINCIPLED")
    texture=nodes.new("ShaderNodeTexImage")
    texture.image=image
    mat.node_tree.links.new(texture.outputs["Color"],shader.inputs["Base Color"])
    if reflect:
        shader.inputs["Coat Weight"].default_value=.31
        shader.inputs["Coat Roughness"].default_value=.19
        noise=nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value=24
        bump=nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value=.23
        bump.inputs["Distance"].default_value=.021
        mat.node_tree.links.new(noise.outputs["Fac"],bump.inputs["Height"])
        mat.node_tree.links.new(bump.outputs["Normal"],shader.inputs["Normal"])
    return mat


def rebase_pool(scene,mats):
    collection=bpy.data.collections["04 尚德广场与喷泉"]
    # Match the outer painted roof-plan corners visible in the aerial reprojection.
    a,b,c,d=map(world,((811,477),(832,477),(811,450),(832,450)))
    center=(a+b+c+d)/4
    width=(b-a).length
    depth=(c-a).length
    rim=scene.objects["水池黑石边沿"]
    bounds=[rim.matrix_world@Vector(v) for v in rim.bound_box]
    xmin,xmax=min(v.x for v in bounds),max(v.x for v in bounds)
    ymin,ymax=min(v.y for v in bounds),max(v.y for v in bounds)
    base=Vector(((xmin+xmax)/2,(ymin+ymax)/2,0))
    fit=Matrix.Diagonal((width/(xmax-xmin),depth/(ymax-ymin),1,1))
    transform=Matrix.Translation(center-fit.to_3x3()@base)@fit
    existing={o:o.matrix_world.copy() for o in collection.all_objects}
    for obj,matrix in existing.items():
        obj.parent=None
        obj.matrix_world=transform@matrix
    water=scene.objects["水面"]
    stone=scene.objects["题字景观石"]
    for obj,key,period in ((water,"水面波纹",2.55),(rim,"池边深色石材",.77),
                           (stone,"景石石纹",.77)):
        obj.data.materials[0]=mats[key]
        uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
        for face in obj.data.polygons:
            for i in face.loop_indices:
                vertex=obj.matrix_world@obj.data.vertices[obj.data.loops[i].vertex_index].co
                uv.data[i].uv=(vertex.x/period,(vertex.z if key=="景石石纹" else vertex.y)/period)
    return center


def ground(scene,mats):
    for name in ("尚德广场暖灰石板","尚德广场至主轴连续铺底"):
        if (obj:=scene.objects.get(name)) is not None:
            bpy.data.objects.remove(obj,do_unlink=True)
    helper=Ground.__new__(Ground)
    helper.scene,helper.batches=scene,{}
    helper.materials={"slab":mats["广场石板"],"edge":material("05 灰色排边石",(.24,.26,.26),.87),
                      "soil":material("05 树池表土",(.112,.088,.056),.95),
                      "grate":material("05 树池格栅",(.071,.115,.068),.89)}
    helper.region("05 尚德广场 · 实拍石板和树池")
    apron=Polygon(((772,493),(777,472),(786,447),(863,445),(875,466),(883,491),(866,500),(789,499)))
    pool=box(811,450,832,477)
    tree_centers=((805,468),(805,455),(839,468),(839,454))
    rings=[box(x-1.05,y-1.05,x+1.05,y+1.05) for x,y in tree_centers]
    stone=apron.difference(pool)
    for ring in rings:
        stone=stone.difference(ring)
    helper.surface("05 尚德广场实拍石板总面","slab",stone,.056)
    for x,y in tree_centers:
        outer=box(x-1.15,y-1.15,x+1.15,y+1.15)
        inner=box(x-.88,y-.88,x+.88,y+.88)
        helper.surface("05 方树池窄边","edge",outer.difference(inner),.066)
        helper.surface("05 方树池土底","soil",inner,.048)
        for d in (-.63,-.32,0,.32,.63):
            helper.line("05 树池暗绿格栅","grate",(x-.84,y+d),(x+.84,y+d),.019,.061)
            helper.line("05 树池暗绿格栅","grate",(x+d,y-.84),(x+d,y+.84),.019,.061)
    helper.polyline("05 门内石板与混凝土灰色收边","edge",
                    ((777,493),(789,499),(866,500),(883,491)),.26,.069)
    helper.build()
    return tree_centers


def surroundings(scene,mats,tree_centers):
    from 剩余楼栋与校园景观 import Planting

    # Replace the previous placeholder poles and noticeboards inside this plaza.
    for name in ("道路设施 · 灯杆 1","道路设施 · 灯杆 2","道路设施 · 灯杆 6",
                 "道路设施 · 宣传栏与分类桶 1"):
        if (group:=bpy.data.collections.get(name)) is not None:
            for obj in list(group.objects):
                bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.collections.remove(group)

    plants=Planting(scene)
    plants.group.name="05 尚德广场 · 池侧行道树与矮篱"
    for i,point in enumerate(tree_centers):
        plants.tree(point,4.9+.42*(i%2),"green")
    for points in (((768,479),(768,488),(769,492)),((876,478),(877,487),(878,492))):
        plants.hedge(points,.45)
    plants.finish()
    colors={
        "grey":material("05 灯杆深灰下段",(.16,.19,.20),.84),
        "white":material("05 灯杆乳白发光段",(.72,.72,.64),.49),
        "gold":material("05 灯杆黄帽",(.58,.31,.035),.68),
        "red":material("05 宣传栏红柱",(.50,.046,.025),.64),
        "blue":material("05 宣传栏蓝框",(.011,.105,.35),.62),
        **mats,
    }
    group=bpy.data.collections.new("05 尚德广场 · 两侧宣传栏和柱灯")
    scene.collection.children.link(group)

    def parts(at,axis,inside):
        obj=Building.__new__(Building)
        obj.anchor=world(at)
        obj.across,obj.depth=Vector(axis),Vector(inside)
        obj.sid="05"
        obj.collection,obj.groups,obj.materials=group,{},colors
        return obj

    for at in ((799,482),(844,482),(802,452),(843,451)):
        obj=parts(at,(1,0,0),(0,1,0))
        obj.box("两段式柱灯深灰底","grey",0,0,.85,.118,.118,1.70)
        obj.box("两段式柱灯乳白段","white",0,0,2.36,.107,.107,1.32)
        obj.box("黄色灯帽","gold",0,0,3.044,.123,.123,.050)
        obj.finish()
    for key,at,axis,depth in (
        ("西侧六格宣传栏",(777,482),(0,-1,0),(-1,0,0)),
        ("东侧六格宣传栏",(874,482),(0,1,0),(1,0,0)),
    ):
        obj=parts(at,axis,depth)
        width=12.3
        for i in range(7):
            obj.box("宣传栏立柱","red" if i not in (0,6) else "blue",
                    (i-3)*width/6,0,.84,.105,.14,1.68)
        obj.box("宣传栏长横梁","blue",0,0,1.66,width+.12,.17,.09)
        coords=[obj.point(x,-.094,z) for x,z in (
            (-width/2,1.67),(width/2,1.67),(width/2,.29),(-width/2,.29))]
        panel=obj.link(key,coords,[(3,2,1,0)],mats[key])
        layer=panel.data.uv_layers.new()
        uv=((0,1),(1,1),(1,0),(0,0))
        for loop in panel.data.loops:
            layer.data[loop.index].uv=uv[loop.vertex_index]
        obj.finish()


def comparison():
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    canvas=Image.new("RGB",(1212,728),"#eeebe4")
    draw=ImageDraw.Draw(canvas)
    draw.text((12,12),"05 尚德广场 · 每组左为实景，右为模型估算视角",font=font,fill="#202923")
    for i,(angle,title,*_) in enumerate(VIEWS):
        x=10+(i%2)*602
        y=46+(i//2)*334
        draw.text((x,y),angle+"°  "+title,font=font,fill="#202923")
        for j,path in enumerate((reference("05",angle),OUT/"模型视角"/(angle+".png"))):
            with Image.open(path) as image:
                canvas.paste(ImageOps.fit(image.convert("RGB"),(291,291)),(x+j*296,y+28))
    canvas.save(OUT/"尚德广场四向实景对照.png")


def main():
    (OUT/"实拍材质").mkdir(parents=True,exist_ok=True)
    (OUT/"模型视角").mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene=bpy.context.scene
    mats={}
    for name,spec in SAMPLES.items():
        glossy=name=="水面波纹"
        mats[name]=photo_material(name,rectify(name,spec),(.26,.26,.25),
                                  .28 if glossy else .82,
                                  period=2.39 if name=="广场石板" else 1,reflect=glossy)
    rebase_pool(scene,mats)
    surroundings(scene,mats,ground(scene,mats))
    shots=[]
    for angle,title,eye,target,height in VIEWS:
        data=bpy.data.cameras.new("05 "+angle+" "+title)
        data.lens=18
        obj=bpy.data.objects.new(data.name,data)
        scene.collection.objects.link(obj)
        obj.location=world(eye)+Vector((0,0,1.62))
        obj.rotation_euler=(world(target)+Vector((0,0,height))-obj.location).to_track_quat("-Z","Y").to_euler()
        shots.append((obj,angle))
    scene.camera=shots[0][0]
    scene.render.resolution_x=scene.render.resolution_y=850
    scene.cycles.samples=16
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_尚德广场实拍细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_尚德广场实拍细化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    for camera,angle in shots:
        scene.camera=camera
        scene.render.filepath=str(OUT/"模型视角"/(angle+".png"))
        bpy.ops.render.render(write_still=True)
    comparison()
    (OUT/"照片位置与贴图控制点.json").write_text(json.dumps({
        "场景":"05 尚德广场", "控制点坐标基准":"700×700方向图等比换算至原图",
        "照片贴图":SAMPLES, "水池边界像素":[[811,450],[832,450],[832,477],[811,477]],
        "地面依据":"场景05四向照片及航拍重投影",
        "尺寸状态":"池宽、池深及站位按航拍和照片估算，待实测",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
