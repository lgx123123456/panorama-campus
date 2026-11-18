"""Update glazing in the current campus master and export matching game assets."""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy
from mathutils import Vector
from shapely import box as rectangle, constrained_delaunay_triangles, union_all
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "成果/教室与男女生公寓室内/校园_教室与男女生公寓室内.blend"
OUT = ROOT / "成果/校园透明玻璃"
STEM = "校园_室内外透明玻璃"
GLASS_COLORS = {
    "透明平板玻璃": ((.92,.97,.99), .055, .12),
    "浅灰蓝玻璃": ((.58,.73,.81), .075, .17),
    "透光玻璃砖": ((.78,.88,.92), .19, .26),
    "淡绿透光棚板": ((.43,.72,.50), .13, .23),
    "透明钢化玻璃": ((.89,.96,.99), .045, .13),
}
GLAZING = re.compile(
    r"(?:\bglass$|_glass$|玻璃$|玻璃亮面$|玻璃块$|玻璃塔楼$|"
    r"实拍 · (?:window|bridgeglass|桥窗|柱廊窗帘|公寓反光窗|公寓窗帘|圆弧[首二]层玻璃窗帘)$|"
    r"绿色透光棚板$|^宿舍窗外实拍(?:27|30)$)"
)
BACKINGS = re.compile(
    r"连续凹窗背衬|黄色首层裙墙|首层窗洞阴影|凹进窗玻璃背面|"
    r"实拍灰色墙板内衬|首层橙黄色实墙|底层窗洞暗框|凹窗边框及外窗台|"
    r"幕墙深色基层|退台阳台后墙|长边内衬|灰色底层|深灰立面内衬|首层裙墙底板|"
    r"入口玻璃门洞|侧后墙|窗带深灰内层|首层高深玻璃槽|餐厅玻璃门深色后面|"
    r"首层橙黄色板面|窗格深置衬框|塔楼通高暗灰内衬|窗洞暗色框衬|梯间背面窗暗衬|"
    r"机房暗部内衬|侧墙退深条窗|浅色长墙板|上部连续深灰分格衬墙|"
    r"蓝窗深色墙衬|看台背侧红墙|灰色长墙衬底|侧廊两侧黄色墙板|"
    r"门房内侧整面窗框|^深色窗框(?:\.\d+)?$|高端整面橙黄板墙|深灰窗洞侧框"
)
REMOVE_DEPTH_SHIMS = ("凹进窗玻璃背面","首层窗洞阴影","底层窗洞暗框","首层高深玻璃槽")
SHELLS = re.compile(
    r"^B(?:09A|09B|32)$|楼翼主体及侧廊凹口|门房灰石外墙|门卫房白色板墙"
)
LOCAL_ONLY = ("看台背侧红墙","高端整面橙黄板墙","门房内侧整面窗框","深色窗框")


def base_name(name):
    return re.sub(r"\.\d+$","",name)


def family(slot, object_name):
    name=base_name(slot)
    if object_name.endswith("消防箱浅色玻璃面"):
        return "透明平板玻璃"
    if object_name.endswith("条窗退后玻璃"):
        return "浅灰蓝玻璃"
    if not GLAZING.search(name):
        return None
    if "绿色透光棚板" in name:
        return "淡绿透光棚板"
    if "玻璃块" in name:
        return "透光玻璃砖"
    if "篮板" in name:
        return "透明钢化玻璃"
    if name in {"glass","校园室内 · glass","玻璃亮面"} or name.startswith("宿舍窗外实拍"):
        return "透明平板玻璃"
    return "浅灰蓝玻璃"


def material(name, props):
    rgb,rough,alpha=props
    mat=bpy.data.materials.new(name)
    mat.diffuse_color=(*rgb,1)
    mat.use_nodes=True
    shader=mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value=(*rgb,1)
    shader.inputs["Roughness"].default_value=rough
    shader.inputs["IOR"].default_value=1.46 if "棚板" not in name else 1.49
    shader.inputs["Transmission Weight"].default_value=1
    mat.surface_render_method="DITHERED"
    mat.use_raytrace_refraction=True
    mat["GLB 预览不透明度"]=alpha
    return mat


def split_geometry(mesh, material_indices):
    polygons=[p for p in mesh.polygons if p.material_index in material_indices]
    by_vertex=defaultdict(list)
    for face in polygons:
        for vi in face.vertices:
            by_vertex[vi].append(face.index)
    remaining={face.index for face in polygons}
    while remaining:
        stack=[remaining.pop()]
        vertices=set()
        normal=mesh.polygons[stack[0]].normal.copy()
        while stack:
            for vi in mesh.polygons[stack.pop()].vertices:
                if vi in vertices:
                    continue
                vertices.add(vi)
                for neighbor in by_vertex[vi]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
        if len(vertices) in (4,8):
            yield [mesh.vertices[vi].co.copy() for vi in sorted(vertices)],normal


def oriented_glass(points, guess_normal):
    zmin,zmax=min(p.z for p in points),max(p.z for p in points)
    if zmax-zmin<.22:
        return None
    if len(points)==8:
        edges=[p-points[0] for p in points[1:]
               if abs(p.z-points[0].z)<.03 and (p-points[0]).length>.005]
        if len(edges)<2:
            return None
        thickness=min(edges,key=lambda p:p.length)
        normal=Vector((thickness.x,thickness.y,0)).normalized()
        if thickness.length>.40:
            return None
    else:
        if abs(guess_normal.z)>.20:
            return None
        normal=Vector((guess_normal.x,guess_normal.y,0)).normalized()
    across=Vector((-normal.y,normal.x,0))
    xs=[p.dot(across) for p in points]
    if max(xs)-min(xs)<.12:
        return None
    n=[p.dot(normal) for p in points]
    center=normal*((min(n)+max(n))/2)+across*((min(xs)+max(xs))/2)
    center.z=(zmin+zmax)/2
    return center,normal,points


class PaneIndex:
    def __init__(self, cell=4.0):
        self.cells=defaultdict(list)
        self.items=[]
        self.cell=cell

    def keys(self, vertices, margin=0):
        area=[(min(p[i] for p in vertices)-margin,max(p[i] for p in vertices)+margin) for i in range(2)]
        for a in range(math.floor(area[0][0]/self.cell),math.floor(area[0][1]/self.cell)+1):
            for b in range(math.floor(area[1][0]/self.cell),math.floor(area[1][1]/self.cell)+1):
                yield a,b

    def add(self, obj, pane):
        key=len(self.items)
        self.items.append((obj,*pane))
        for cell in self.keys(pane[2]):
            self.cells[cell].append(key)

    def near(self, vertices, margin):
        indices={i for key in self.keys(vertices,margin) for i in self.cells.get(key,())}
        return (self.items[i] for i in sorted(indices))


def convert_glazing(scene, mats):
    panes=PaneIndex()
    slots_by_source={}
    applied=Counter()
    objects=0
    for obj in scene.objects:
        if obj.type!="MESH" or not obj.data.materials:
            continue
        mesh=obj.data
        if mesh not in slots_by_source:
            kinds={i: family(m.name,base_name(obj.name)) for i,m in enumerate(mesh.materials) if m}
            targets={i:kind for i,kind in kinds.items() if kind}
            parts=list(split_geometry(mesh,targets)) if targets else []
            for i,kind in targets.items():
                applied[(mesh.materials[i].name,kind)]+=1
                mesh.materials[i]=mats[kind]
            slots_by_source[mesh]=(targets,parts)
        targets,parts=slots_by_source[mesh]
        if not targets:
            continue
        objects+=1
        mat=obj.matrix_world
        normal_matrix=mat.to_3x3().inverted_safe().transposed()
        for vertices,normal in parts:
            pane=oriented_glass([mat@p for p in vertices],normal_matrix@normal)
            if pane:
                panes.add(obj,pane)
    return panes,applied,objects


def bounds(values):
    v=list(values)
    return min(v),max(v)


def directions(points):
    u=(points[1]-points[0]).normalized()
    v=(points[3]-points[0]).normalized()
    if abs(u.z)>.04 or abs(v.z)>.04 or abs(u.dot(v))>.08:
        return ()
    axes=[Vector((axis.x,axis.y,0)).normalized() for axis in (u,v)]
    return sorted(axes,key=lambda axis:abs((points[1]-points[0]).dot(axis))+abs((points[3]-points[0]).dot(axis)),
                  reverse=True)


def nearby_openings(obj, points, pane_index, axis, normal, distance, u0,u1,n0,n1,z0,z1):
    local=set(obj.users_collection) if any(name in obj.name for name in LOCAL_ONLY) else set()
    holes=[]
    for owner,center,direction,vertices in pane_index.near(points,distance):
        if owner==obj or abs(direction.dot(normal))<.975 or not n0-distance<=center.dot(normal)<=n1+distance:
            continue
        if local and not local.intersection(owner.users_collection):
            continue
        p0,p1=bounds(p.dot(axis) for p in vertices)
        q0,q1=bounds(p.z for p in vertices)
        low,high=max(u0,p0+.002),min(u1,p1-.002)
        sill,head=max(z0,q0+.002),min(z1,q1-.002)
        if high-low<.07 or head-sill<.10:
            continue
        holes.append(rectangle(low,sill,high,head))
    return holes


def openings_for(obj, points, pane_index, axis, distance):
    normal=Vector((axis.y,-axis.x,0))
    u0,u1=bounds(p.dot(axis) for p in points)
    n0,n1=bounds(p.dot(normal) for p in points)
    z0,z1=bounds(p.z for p in points)
    space=rectangle(u0,z0,u1,z1)
    holes=nearby_openings(obj,points,pane_index,axis,normal,distance,u0,u1,n0,n1,z0,z1)
    if not holes:
        return None
    cut=space.difference(union_all(holes))
    if space.area-cut.area<.012:
        return None
    return axis,normal,n0,n1,cut,len(holes)


def block_uv(mesh, polygon, inverse):
    if not mesh.uv_layers or len(polygon.loop_indices)<3:
        return None
    coords=mesh.uv_layers.active.data
    loops=polygon.loop_indices
    origin=mesh.vertices[mesh.loops[loops[0]].vertex_index].co
    along=mesh.vertices[mesh.loops[loops[1]].vertex_index].co-origin
    up=mesh.vertices[mesh.loops[loops[-1]].vertex_index].co-origin
    base=coords[loops[0]].uv.copy()
    du=coords[loops[1]].uv-base
    dv=coords[loops[-1]].uv-base
    aa,ab,bb=along.length_squared,along.dot(up),up.length_squared
    determinant=aa*bb-ab*ab
    if determinant<1e-12:
        return None

    def project(points):
        result=[]
        for point in points:
            local=inverse@point-origin
            a,b=local.dot(along),local.dot(up)
            result.append(base+du*((bb*a-ab*b)/determinant)+dv*((aa*b-ab*a)/determinant))
        return result
    return project


class MeshWriter:
    def __init__(self):
        self.vertices=[]
        self.faces=[]
        self.uv=[]
        self.indices=[]
        self.keys={}

    def face(self, vertices, slot, uv=None):
        face=[]
        for point in vertices:
            key=tuple(round(x,6) for x in point)
            if key not in self.keys:
                self.keys[key]=len(self.vertices)
                self.vertices.append(point)
            face.append(self.keys[key])
        if len(set(face))==len(face):
            self.faces.append(tuple(face))
            self.indices.append(slot)
            self.uv.append(uv)

    def split_extrude(self, solution, slot, inverse, uv):
        axis,normal,n0,n1,shape,_=solution

        def surface(xy,n):
            return Vector((axis.x*xy[0]+normal.x*n,axis.y*xy[0]+normal.y*n,xy[1]))

        def face(points):
            self.face([inverse@p for p in points],slot,uv(points) if uv else None)

        parts=[shape] if shape.geom_type=="Polygon" else shape.geoms
        for part in parts:
            if part.geom_type!="Polygon" or part.area<1e-6:
                continue
            part=orient(part,sign=1.0)
            for triangle in constrained_delaunay_triangles(part).geoms:
                xy=list(orient(triangle,sign=1.0).exterior.coords)[:3]
                face([surface(p,n1) for p in xy])
                face([surface(p,n0) for p in reversed(xy)])
            for ring in (part.exterior,*part.interiors):
                for a,b in zip(ring.coords, list(ring.coords)[1:]):
                    if a!=b:
                        face([surface(a,n0),surface(b,n0),surface(b,n1),surface(a,n1)])

    def plane(self, shape, axis, normal, depth, slot, inverse, uv):
        parts=[shape] if shape.geom_type=="Polygon" else shape.geoms
        for part in parts:
            if part.geom_type!="Polygon" or part.area<1e-6:
                continue
            for triangle in constrained_delaunay_triangles(part).geoms:
                ring=list(orient(triangle,sign=1.0).exterior.coords)[:3]
                points=[Vector((axis.x*x+normal.x*depth,axis.y*x+normal.y*depth,z)) for x,z in ring]
                self.face([inverse@p for p in points],slot,uv(points) if uv else None)

    def install(self, obj):
        original=obj.data
        mesh=bpy.data.meshes.new(original.name+" · 窗洞")
        mesh.from_pydata(self.vertices,[],self.faces)
        for m in original.materials:
            mesh.materials.append(m)
        uv=mesh.uv_layers.new(name=original.uv_layers.active.name) if original.uv_layers else None
        for face,slot,coords in zip(mesh.polygons,self.indices,self.uv):
            face.material_index=slot
            if uv and coords:
                for i,p in zip(face.loop_indices,coords):
                    uv.data[i].uv=p
        mesh.update()
        obj.data=mesh


def cut_backing(obj, pane_index):
    old=obj.data
    if len(old.vertices)%8 or len(old.polygons)!=len(old.vertices)//8*6:
        return 0,0
    authority=obj.matrix_world
    inv=authority.inverted_safe()
    writer=MeshWriter()
    opened=groups=0
    distance=1.33 if "灰色底层" in obj.name else .87
    for i in range(0,len(old.vertices),8):
        local=[v.co.copy() for v in old.vertices[i:i+8]]
        points=[authority@p for p in local]
        faces=old.polygons[i//8*6:i//8*6+6]
        axes=directions(points)
        solution=openings_for(obj,points,pane_index,axes[0],distance) if axes else None
        if solution:
            match=max(faces,key=lambda face:abs((authority.to_3x3()@face.normal).normalized().dot(solution[1])))
            uv=block_uv(old,match,inv)
            writer.split_extrude(solution,match.material_index,inv,uv)
            opened+=solution[-1]
            groups+=1
        else:
            for face in faces:
                coords=[old.uv_layers.active.data[j].uv.copy() for j in face.loop_indices] if old.uv_layers else None
                writer.face([old.vertices[k].co.copy() for k in face.vertices],face.material_index,coords)
    if groups:
        writer.install(obj)
    return groups,opened


def cut_shell_surfaces(obj, pane_index):
    """Cut the relevant faces of solid placeholder volumes, keeping their roofs and footprint."""
    old=obj.data
    transform=obj.matrix_world
    inverse=transform.inverted_safe()
    normals=inverse.to_3x3().transposed()
    writer=MeshWriter()
    changed=window_count=0
    for face in old.polygons:
        coords=[old.vertices[i].co.copy() for i in face.vertices]
        points=[transform@p for p in coords]
        normal=(normals@face.normal).normalized()
        z0,z1=bounds(p.z for p in points)
        if abs(normal.z)<.06 and z1-z0>.28:
            normal.z=0
            normal.normalize()
            across=Vector((-normal.y,normal.x,0))
            depth=sum(p.dot(normal) for p in points)/len(points)
            planar=[(p.dot(across),p.z) for p in points]
            u0,u1=bounds(p[0] for p in planar)
            original=Polygon(planar)
            if original.is_valid and original.area>.01:
                holes=nearby_openings(obj,points,pane_index,across,normal,.74,
                                      u0,u1,depth,depth,z0,z1)
                if holes:
                    modified=original.difference(union_all(holes))
                    if original.area-modified.area>.01:
                        writer.plane(modified,across,normal,depth,face.material_index,
                                     inverse,block_uv(old,face,inverse))
                        changed+=1
                        window_count+=len(holes)
                        continue
        uv=[old.uv_layers.active.data[i].uv.copy() for i in face.loop_indices] if old.uv_layers else None
        writer.face(coords,face.material_index,uv)
    if changed:
        writer.install(obj)
    return changed,window_count


def restore_round_window_stripe():
    obj=next(o for o in bpy.context.scene.objects if o.name.startswith("B32R 首层实拍玻璃及绿色腰线"))
    original=obj.data
    center=(original.vertices[0].co+original.vertices[-2].co)/2
    vertices=[]
    for item in original.vertices:
        point=item.co.copy()
        offset=point-center
        offset.z=0
        point+=offset.normalized()*.013
        point.z=1.48+(.07 if item.index%2 else -.07)
        vertices.append(point)
    data=bpy.data.meshes.new("圆弧玻璃 · 绿色腰线")
    data.from_pydata(vertices,[],[tuple(f.vertices) for f in original.polygons])
    mat=bpy.data.materials.new("圆弧窗 · 绿色腰线")
    mat.diffuse_color=(.05,.33,.09,1)
    mat.use_nodes=True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=mat.diffuse_color
    data.materials.append(mat)
    stripe=bpy.data.objects.new(data.name,data)
    obj.users_collection[0].objects.link(stripe)
    stripe.matrix_world=obj.matrix_world.copy()


def clear_visual_backings(scene, pane_index):
    results={}
    for obj in list(scene.objects):
        if obj.type!="MESH":
            continue
        if SHELLS.search(obj.name):
            groups,openings=cut_shell_surfaces(obj,pane_index)
            if groups:
                results[obj.name]=[groups,openings]
        elif not BACKINGS.search(obj.name):
            continue
        elif any(key in obj.name for key in REMOVE_DEPTH_SHIMS):
            name=obj.name
            bpy.data.objects.remove(obj,do_unlink=True)
            results[name]="移除旧窗洞阴影片"
        else:
            groups, openings=cut_backing(obj,pane_index)
            if groups:
                results[obj.name]=[groups,openings]
    return results


def prepare_web_glass(mats):
    for name,mat in mats.items():
        _,rough,alpha=GLASS_COLORS[name]
        shader=mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Transmission Weight"].default_value=0
        shader.inputs["Alpha"].default_value=alpha
        shader.inputs["Roughness"].default_value=rough
        mat.surface_render_method="BLENDED"


def exports(scene):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=str(OUT/(STEM+".glb")),export_format="GLB")
    for obj in bpy.data.collections["楼内还原"].all_objects:
        if obj.type=="MESH":
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUT/"校园_室内透明玻璃.glb"),export_format="GLB",use_selection=True)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE),load_ui=False)
    scene=bpy.context.scene
    scene.eevee.use_raytracing=True
    scene.cycles.transmission_bounces=max(8,scene.cycles.transmission_bounces)
    mats={name:material(name,props) for name,props in GLASS_COLORS.items()}
    panes,applied,object_count=convert_glazing(scene,mats)
    backings=clear_visual_backings(scene,panes)
    restore_round_window_stripe()
    bpy.context.view_layer.update()
    report={
        "源母版":str(SOURCE.relative_to(ROOT.parent)),
        "玻璃对象数":object_count,
        "可检测立面玻璃片数":len(panes.items),
        "原玻璃材质":[[old,new,count] for (old,new),count in sorted(applied.items())],
        "遮挡处理":backings,
        "导出":"Blender采用透射着色。GLB采用半透明PBR便于实时查看。窗框与实体构件保留。",
    }
    (OUT/"玻璃材质与窗洞记录.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
    if "--draft" not in sys.argv:
        prepare_web_glass(mats)
        exports(scene)


if __name__=="__main__":
    main()
