"""Model the teaching-axis portal and its open overhead structure."""

import math
from pathlib import Path

import bpy
from mathutils import Vector

from 图书馆照片还原 import material, open_campus, world


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/"成果"/"图书馆实景样板"/"校园室外_图书馆实景细化.blend"
OUT = ROOT/"成果"/"主轴连廊实景样板"


def main():
    OUT.mkdir(exist_ok=True)
    open_campus(SOURCE)
    scene = bpy.context.scene
    old = ("B40_portal_", "B40_bridge_", "B40_canopy_")
    for obj in list(scene.objects):
        if obj.name.startswith(old):
            bpy.data.objects.remove(obj, do_unlink=True)
    collection = bpy.data.collections.new("40 艺远楼与识远楼 · 连廊实景细化")
    scene.collection.children.link(collection)
    center = world((832,429))
    palette = {
        key: material("40 "+name, rgb, roughness)
        for key, name, rgb, roughness in (
            ("gold","橙黄色板面",(.64,.32,.047),.74),
            ("joint","板缝",(.32,.15,.023),.84),
            ("steel","蓝灰钢结构",(.087,.105,.124),.60),
            ("brace","斜撑",(.37,.22,.078),.60),
            ("slab","灰色桥底",(.24,.245,.241),.80),
            ("glass","灰蓝色玻璃",(.075,.14,.18),.31),
            ("light","石台及排行",(.37,.36,.34),.79),
        )
    }
    meshes = {}

    def cuboid(label, color, at, size, angle=0):
        vertices, faces = meshes.setdefault((label,color),([],[]))
        x,y,z = at
        w,d,h = (v/2 for v in size)
        cosine,sine = math.cos(angle),math.sin(angle)
        start=len(vertices)
        vertices.extend(center+Vector((x+a*w*cosine+c*h*sine,y+b*d,z-a*w*sine+c*h*cosine))
                        for a,b,c in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                      (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)))
        faces.extend(tuple(start+i for i in face) for face in (
            (0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)))

    for side in (-1,1):
        for x in (side*19.15,side*21.75):
            cuboid("侧门框黄柱","gold",(x,0,8.7),(1.24,10.8,17.25))
            for y in (-5.41,5.41):
                for n in range(1,14):
                    cuboid("黄色板材横分缝","joint",(x,y,n*1.24),(1.25,.024,.022))
        for y in (-5.09,5.09):
            cuboid("外侧深灰立柱","steel",(side*23.3,y,8.4),(.68,.76,16.7))
        for level in (3.45,6.75,10.05,13.35):
            cuboid("侧门内退楼层","slab",(side*20.5,0,level),(1.85,9.8,.32))
            for y in (-4.1,4.1):
                cuboid("侧门内退玻璃","glass",(side*20.5,y,level+1.18),(1.68,.14,1.8))
                cuboid("侧门内退横梃","steel",(side*20.5,y,level+1.26),(1.71,.20,.10))
        cuboid("侧门石槛","light",(side*20.5,0,.12),(4.18,11.3,.24))
    for y in (-5.17,5.17):
        cuboid("前后黄色通高框梁","gold",(0,y,17.29),(43.6,.87,1.12))
    for i in range(13):
        x=(i-6)*3.01
        cuboid("棚顶细梁纵列","steel",(x,0,16.62),(.24,10.05,.43))
    for y in (-3.75,-2.25,2.25,3.75):
        cuboid("棚顶横向钢梁","steel",(0,y,16.43),(38.4,.29,.35))
    cuboid("空中桥楼板","slab",(0,0,10.19),(39.2,3.62,.52))
    cuboid("空中桥底分块","steel",(0,0,9.91),(39.2,3.35,.095))
    for y in (-1.81,1.81):
        for i in range(12):
            x=(i-5.5)*3.24
            cuboid("桥侧玻璃分格","glass",(x,y,11.61),(3.11,.092,2.19))
            cuboid("桥侧钢立框","steel",(x-1.58,y,11.61),(.12,.23,2.30))
            cuboid("桥侧金色斜撑","brace",(x,y*1.055,11.60),
                   (math.hypot(2.96,1.88),.113,.12),(-1)**i*math.atan2(1.88,2.96))
        for z in (10.52,12.79):
            cuboid("桥侧钢横框","steel",(0,y,z),(39.2,.20,.18))
    cuboid("空中桥屋面","slab",(0,0,12.92),(39.22,3.73,.25))
    for (label,color),(vertices,faces) in meshes.items():
        mesh=bpy.data.meshes.new(label)
        mesh.from_pydata(vertices,[],faces)
        mesh.update()
        mesh.materials.append(palette[color])
        obj=bpy.data.objects.new(label,mesh)
        collection.objects.link(obj)
        obj["参考场景"]="05/000，40/090、270、天顶，45/180"

    def camera(label, at, target, lens):
        data=bpy.data.cameras.new(label)
        data.lens=lens
        camera=bpy.data.objects.new(label,data)
        collection.objects.link(camera)
        camera.location=at
        camera.rotation_euler=(target-at).to_track_quat("-Z","Y").to_euler()
        return camera

    views = (
        (camera("05 尚德广场看连廊",world((822,505))+Vector((0,0,1.62)),
                center+Vector((0,0,3.4)),19),"连廊南面"),
        (camera("45 主轴回看连廊",world((828,350))+Vector((0,0,1.62)),
                center+Vector((0,0,4)),21),"连廊北面"),
        (camera("40 连廊仰视",center+Vector((0,-2.8,1.6)),
                center+Vector((4,0,12.7)),18),"连廊仰视"),
    )
    scene.camera=views[0][0]
    scene.render.resolution_x=scene.render.resolution_y=940
    scene.cycles.samples=18
    scene.render.filepath=str(OUT/"连廊南面.png")
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_主轴实景细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_主轴实景细化.glb"),export_format="GLB",
                             export_cameras=False,export_lights=False)
    for view,name in views:
        scene.camera=view
        scene.render.filepath=str(OUT/(name+".png"))
        bpy.ops.render.render(write_still=True)


if __name__=="__main__":
    main()
