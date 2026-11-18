"""Rebuild the library front using scene 32 and retain the existing campus layout."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
ROUND = ROOT / "成果" / "第2轮"
OUT = ROOT / "成果" / "图书馆实景样板"
REF = ROOT.parent / "数据" / "04_建模参考" / "02_八方向" / "32_图书馆" / "000.jpg"
PLAN = json.loads((ROOT / "总图标注.json").read_text(encoding="utf-8"))
CAL = json.loads((ROUND / "底图校准记录.json").read_text(encoding="utf-8"))


def world(point):
    dx, dy = Vector(point) - Vector(PLAN["origin"])
    angle = math.radians(CAL["rotation_degrees"])
    scale = CAL["metres_per_pixel"]
    return Vector((scale*(dx*math.cos(angle)+dy*math.sin(angle)),
                   scale*(dx*math.sin(angle)-dy*math.cos(angle)), 0))


def material(name, rgb, roughness):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*rgb, 1)
    shader.inputs["Roughness"].default_value = roughness
    return mat


def open_campus(source=None):
    bpy.ops.wm.open_mainfile(filepath=str(source or ROUND / "校园室外还原.blend"), load_ui=False)


def main():
    OUT.mkdir(exist_ok=True)
    open_campus()
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.name.startswith("B32_") and obj.name != "B32_roof":
            bpy.data.objects.remove(obj, do_unlink=True)
    outline = next(row["outline"] for row in PLAN["buildings"] if row["id"] == "B32")
    left, right = world(outline[8]), world(outline[7])
    center = (left + right) / 2
    east = (right - left).normalized()
    south = Vector((east.y, -east.x, 0))
    up = Vector((0, 0, 1))
    width = (right - left).length
    library = bpy.data.collections.new("B32 图书馆 · 场景32实景还原")
    scene.collection.children.link(library)
    palette = {
        "gold": material("B32 橙黄饰带", (.53,.25,.040), .74),
        "grey": material("B32 深灰横带", (.095,.090,.079), .78),
        "light": material("B32 浅灰柱面", (.49,.51,.52), .67),
        "stone": material("B32 台阶花岗岩", (.22,.205,.18), .85),
        "sill": material("B32 踏步边", (.33,.32,.30), .75),
        "metal": material("B32 银灰栏杆", (.44,.48,.49), .29),
        "frame": material("B32 深色窗框", (.035,.042,.047), .57),
        "glass": material("B32 蓝灰玻璃", (.059,.126,.178), .24),
        "door": material("B32 入口玻璃", (.039,.062,.072), .28),
    }
    stair = palette["stone"].node_tree
    shader = stair.nodes.get("Principled BSDF")
    noise = stair.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 85
    ramp = stair.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (.11,.10,.088,1)
    ramp.color_ramp.elements[1].color = (.34,.32,.29,1)
    stair.links.new(noise.outputs["Fac"],ramp.inputs[0])
    stair.links.new(ramp.outputs["Color"],shader.inputs["Base Color"])

    def point(x, y, z):
        return center + east*x + south*y + up*z

    def link(name, verts, faces, mat):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        library.objects.link(obj)
        mesh.materials.append(mat)
        return obj

    batches = {}

    def box(group, color, x, y, z, w, d, h):
        verts, faces = batches.setdefault((group, color), ([], []))
        i = len(verts)
        for a,b,c in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                      (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)):
            verts.append(point(x+a*w/2,y-b*d/2,z+c*h/2))
        for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            faces.append(tuple(i+j for j in face))

    def rod(group, a, b, radius):
        start, end = point(*a), point(*b)
        axis = end - start
        side = axis.normalized().cross(up)
        if side.length < .01:
            side = east.copy()
        side.normalize()
        other = axis.normalized().cross(side)
        verts, faces = batches.setdefault((group, "metal"), ([], []))
        count = 8
        j = len(verts)
        verts.extend(base + radius*(side*math.cos(i*math.tau/count) +
                     other*math.sin(i*math.tau/count)) for base in (start,end) for i in range(count))
        for i in range(count):
            k = (i+1)%count
            faces.append((j+i,j+k,j+k+count,j+i+count))
        faces.extend((tuple(j+i for i in reversed(range(count))),
                      tuple(j+count+i for i in range(count))))

    box("幕墙深色基层", "grey", 0,.22,9.65,width,.48,19.30)
    for z,h in ((19.34,1.27),(3.08,.83)):
        box("橙黄檐口与底层腰线","gold",0,.66,z,width+.12,.82,h)
    portal = 7.9
    for x in (-portal/2-.39,portal/2+.39):
        box("入口通高浅灰立柱","light",x,.73,10.40,.78,.86,16.90)
        for i in range(1,17):
            box("浅灰柱分缝","grey",x,1.17,1.95+i*.99,.79,.022,.016)
    wing = (width-portal-1.56)/2
    for side in (-1,1):
        xmid = side*(portal/2+.78+wing/2)
        for z in (5.88,9.38,12.88,16.38):
            box("灰色楼层横梁","grey",xmid,.75,z-1.12,wing,.64,.91)
            for i in range(12):
                x = xmid + (i-5.5)*wing/12
                box("蓝灰幕墙分格","glass",x,.53,z+.10,wing/12-.12,.15,2.28)
                box("窗横梃","frame",x,.64,z+.04,wing/12-.036,.09,.068)
                box("竖向灰白遮阳肋","light",x-wing/24,.78,z+.06,.105,.47,2.50)
        for i in range(12):
            x = xmid+(i-5.5)*wing/12
            box("底层玻璃","door",x,.55,1.24,wing/12-.16,.16,1.68)
            box("底层窗柱","grey",x-wing/24,.68,1.26,.17,.32,2.51)
    for z in (12.87,15.36,17.35):
        box("入口上方深色横梁","grey",0,.65,z,portal,.52,.66)
        for i in range(9):
            x = (i-4)*portal/9
            box("入口上方玻璃","glass",x,.50,z-.84,portal/9-.07,.16,1.35)
    box("入口深色门带","door",0,.68,4.91,portal,.18,2.65)
    for x in (-3.65,-2.54,-1.46,0,1.46,2.54,3.65):
        box("入口门竖框","frame",x,.82,4.92,.09,.16,2.64)
    box("入口门横框","frame",0,.82,5.95,portal,.16,.11)

    # Two landing runs with 20 risers and a distinct center rail/plinth.
    for i in range(20):
        z=.17*(i+1)
        y=1.08+(19-i)*.33
        w = 11.60 - .16*i
        box("花岗岩台阶","stone",0,y,z/2,w,.37,z)
        box("台阶踏步收边","sill",0,y+.16,z-.021,w,.065,.042)
    box("入口平台","stone",0,.68,1.70,8.65,1.50,3.40)
    for side in (-1,1):
        for i in range(6):
            y=7.49-i*1.24
            x=side*(5.80-i*.31)
            low=.22+i*.64
            rod("外侧栏杆立杆",(x,y,low),(x,y,low+.92),.035)
            if i<5:
                for h in (.31,.61,.92):
                    rod("外侧坡道栏杆",(x,y,low+h),
                        (side*(5.80-(i+1)*.31),y-1.24,low+.64+h),.026)
    for side in (-1,1):
        for i in range(4):
            x=side*.78
            y=1.00+i*.48
            low=3.38-i*.22
            rod("入口中央栏杆",(x,y,low),(x,y,low+.86),.031)
            if i<3:
                rod("入口中央栏杆",(x,y,low+.86),(x,y+.48,low+.64),.024)
    for (label,color),(verts,faces) in batches.items():
        link(label, verts, faces, palette[color])

    # Project only the observed sign and LED panel, using original frame coordinates.
    # Their textures retain the source image; windows, stairs and railings are meshes.
    image = bpy.data.images.load(str(REF), check_existing=True)
    image.pack()
    for label, coords, z, height in (
        ("图书馆实拍牌匾", ((346,198),(510,198),(510,237),(346,237)), 11.20, 1.75),
        ("图书馆实拍电子屏", ((348,238),(505,240),(504,309),(348,312)), 8.62, 3.27),
    ):
        corners = [point(x, .90, zz) for x,zz in (
            (-portal/2,z+height/2),(portal/2,z+height/2),
            (portal/2,z-height/2),(-portal/2,z-height/2))]
        mat = material(label,(.5,.5,.5),.79)
        shader=mat.node_tree.nodes.get("Principled BSDF")
        tex=mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image=image
        mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Base Color"])
        mat.node_tree.links.new(tex.outputs["Color"],shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value=.38
        obj=link(label,corners,[(3,2,1,0)],mat)
        layer=obj.data.uv_layers.new()
        for loop in obj.data.loops:
            u,v=coords[loop.vertex_index]
            layer.data[loop.index].uv=(u/850,1-v/850)

    def camera(name, eye, target, lens):
        data=bpy.data.cameras.new(name)
        data.lens=lens
        obj=bpy.data.objects.new(name,data)
        library.objects.link(obj)
        obj.location=point(*eye)
        obj.rotation_euler=(point(*target)-obj.location).to_track_quat("-Z","Y").to_euler()
        return obj

    front=camera("图书馆正面 · 32_000", (0,21.8,1.62),(0,0,1.62),18)
    side=camera("图书馆侧视 · 参考32_045",(-14.8,19.4,1.65),(-4.7,0,3.0),18)
    scene.camera=front
    scene.render.resolution_x=scene.render.resolution_y=1000
    scene.cycles.samples=24
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.47
    bpy.context.preferences.filepaths.save_version=0
    scene.render.filepath=str(OUT/"图书馆正面.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"校园室外_图书馆实景细化.blend"))
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园室外_图书馆实景细化.glb"),
                             export_format="GLB",export_cameras=False,export_lights=False)
    bpy.ops.render.render(write_still=True)
    scene.camera=side
    scene.render.filepath=str(OUT/"图书馆侧视.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
