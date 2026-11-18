"""Trace exposed campus paving and export batched previews from the editable master."""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from shapely.geometry import LineString, Polygon
from shapely import union_all

import 地面街道实景细化 as paving
from 图书馆照片还原 import CAL, PLAN, world
from 校园透明玻璃 import GLASS_COLORS, OUT as GLASS_OUT, STEM as GLASS_NAME, prepare_web_glass

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "成果/地面补铺与预览优化"
STEM = "校园_地面细化"
SOURCE = GLASS_OUT / (GLASS_NAME+".blend")
SCALE = CAL["metres_per_pixel"]
# The pixel coordinates follow the traced 1312×660 aerial reprojection.
AREAS = (
    ("西翼教学楼南侧停车灰坪","parking","02航拍；03/270、05/225仅校核相邻地面材质",
     [(609,447),(760,449),(762,467),(776,473),(773,495),(608,493)],
     [[(619,468),(644,467),(651,484),(624,486)],[(704,473),(742,473),(745,486),(704,487)]]),
    ("东翼近主门侧石板前坪","stone","02航拍；03/045、05/135",
     [(867,442),(925,443),(908,467),(896,488),(872,501),(861,478)],[]),
    ("东翼东侧停车支路和回车坪","parking","02航拍；航拍所见车位和灰色地面",
     [(968,432),(1004,434),(1012,445),(1045,448),(1048,498),(1006,503),(973,493),
      (943,493),(931,483),(943,468),(955,452)], 
     [[(969,468),(979,464),(984,490),(968,490)],[(1004,455),(1024,456),(1028,472),(1008,473)]]),
    ("体育馆南侧入口和沿街停车灰坪","parking","02航拍；10/045、03/270校核材料",
     [(269,480),(371,477),(481,483),(576,485),(609,496),(594,520),(279,518)],
     [[(283,499),(294,495),(298,514),(283,515)],[(393,507),(405,507),(404,520),(392,520)]]),
    ("餐厅与篮球场间铺装边缘","concrete","02航拍；11/090、22/270",
     [(387,152),(422,155),(449,163),(471,159),(513,162),(564,163),(577,171),(570,200),
      (549,206),(504,202),(471,202),(454,196),(432,204),(404,200),(392,196)],
     [[(444,175),(463,175),(462,194),(447,193)],[(531,175),(551,176),(553,196),(530,196)]]),
    ("篮球场北口与看台后通路","concrete","02航拍；09/000、11/270",
     [(274,84),(314,89),(315,227),(304,240),(290,230),(293,176),(285,139),(274,117)],[]),
    ("北侧操场与公寓后勤路衔接","concrete","02航拍；14/270；树荫以下边缘估排",
     [(240,70),(280,69),(310,74),(347,77),(396,73),(494,72),(543,69),(578,66),(579,79),
      (549,81),(503,83),(396,84),(349,86),(310,85),(270,87),(254,97),(240,94)],[]),
    ("东教学区北侧庭院环步道","brick","02航拍；36/225、45/315校核入口；林下段估排",
     [(881,264),(946,261),(973,267),(982,285),(987,313),(979,325),(886,325),(876,302)],
     [[(899,278),(934,274),(958,275),(969,287),(975,312),(897,315)]]),
    ("东教学区南侧庭院环步道","brick","02航拍；40/315、45/270；林下段估排",
     [(877,355),(966,354),(990,359),(988,386),(969,405),(958,413),(887,412),(874,397)],
     [[(893,367),(950,365),(975,369),(968,390),(952,401),(897,400)]]),
    ("实验楼北侧接图书馆的前坪边缘","stone","02航拍；32/315、36/225",
     [(863,208),(917,207),(946,198),(969,209),(979,232),(970,237),(942,225),(909,223),
      (876,232),(865,241),(853,231)], [[(923,211),(943,206),(951,214),(934,218)]]),
    ("知远楼与识远楼侧门外灰坪","stone","02航拍；40/315、45/270",
     [(857,347),(878,349),(882,363),(891,373),(883,410),(866,416),(854,398),(855,371)],[]),
    ("主轴与西翼东端人行过渡","brick","02航拍；05/315、40/270",
     [(729,379),(754,369),(773,362),(787,377),(789,408),(778,447),(753,451),(746,429),
      (745,405)], [[(741,387),(756,380),(764,392),(755,405)]]),
)


def ground(scene):
    texture_dir=OUT/"贴图"
    texture_dir.mkdir(parents=True,exist_ok=True)
    paving.OUT=texture_dir
    mats={
        "parking":paving.surfaced("场地补铺 · 细粒暖灰停车地坪",(142,139,129),.91,"停车地坪",4.5),
        "concrete":paving.surfaced("场地补铺 · 灰米混凝土",(166,162,151),.94,"校内混凝土",5.0),
        "stone":paving.surfaced("场地补铺 · 灰石板",(153,154,148),.88,"灰石板",2.4,(4,4,0)),
        "brick":paving.surfaced("场地补铺 · 暖灰砖",(153,137,127),.89,"暖灰砖",1.2,(4,8,.5)),
        "line":bpy.data.materials["磨损白色标线"],
        "joint":bpy.data.materials["混凝土缩缝"],
    }
    layer=paving.Ground(scene,materials=mats)
    layer.region("补铺 · 航拍确认的地面空缺")
    campus=Polygon(PLAN["boundary"])
    blocks=union_all([Polygon(b["outline"]).buffer(.75) for b in PLAN["buildings"]])
    existing=union_all([])
    records=[]
    covered={}
    for label,key,ref,shell,holes in AREAS:
        island=union_all([Polygon(hole) for hole in holes])
        region=Polygon(shell).difference(island).intersection(campus).difference(blocks).difference(existing)
        existing=existing.union(region)
        covered[label]=region
        layer.surface(label,key,region,.026)
        records.append({"地面":label,"航拍像素轮廓":shell,"保留种植区":holes,
                        "面积估算平方米":round(region.area*SCALE*SCALE,1),"依据":ref})

    # Parked cars in the aerial identify the parking edges, with obstructions left clear.
    for name,regions in (
        ("西翼教学楼南侧停车灰坪",((617,687,457,465),(677,751,484,491))),
        ("东翼东侧停车支路和回车坪",((989,1037,483,492),)),
        ("体育馆南侧入口和沿街停车灰坪",((304,391,487,497),(417,545,490,501))),
    ):
        outline=covered[name]
        for x0,x1,y0,y1 in regions:
            for x in range(x0,x1,6):
                strip=LineString(((x,y0),(x,y1))).buffer(.092/(2*SCALE),cap_style="flat")
                layer.surface(name+" · 停车位线","line",strip.intersection(outline),.029)

    for label in ("北侧操场与公寓后勤路衔接","篮球场北口与看台后通路","餐厅与篮球场间铺装边缘"):
        outline=covered[label]
        x0,y0,x1,y1=outline.bounds
        vertical=x1-x0>y1-y0
        if vertical:
            lines=[((x,y0),(x+.6,y1)) for x in range(math.ceil(x0+5),math.floor(x1-4),11)]
        else:
            lines=[((x0,y),(x1,y+.6)) for y in range(math.ceil(y0+5),math.floor(y1-4),11)]
        for a,b in lines:
            seam=LineString((a,b)).buffer(.011,cap_style="flat").intersection(outline)
            layer.surface(label+" · 混凝土接缝","joint",seam,.028)
    layer.build()
    return records


def active_glass():
    return {name:bpy.data.materials[name] for name in GLASS_COLORS}


def export_asset(path, selection=False, instances=False):
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=selection,
                              export_gpu_instances=instances,export_lights=False,export_cameras=False)


def select_meshes(scene, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        if obj.type in {"MESH","CURVE","SURFACE","FONT","EMPTY"}:
            obj.select_set(True)


def tile_for(obj):
    a,b=(obj.matrix_world @ Vector(obj.bound_box[i]) for i in (0,6))
    center=(a+b)/2
    return math.floor(center.x/28),math.floor(center.y/28),math.floor(center.z/5)


def merge_meshes(items, name, parent):
    vertices,faces,indices,smooth,uv_data=[],[],[],[],[]
    material_ids={}
    for obj in items:
        mesh=obj.data
        offset=len(vertices)
        positions=np.empty(len(mesh.vertices)*3,dtype=np.float32)
        mesh.vertices.foreach_get("co",positions)
        matrix=np.asarray(obj.matrix_world)
        vertices.extend((positions.reshape((-1,3))@matrix[:3,:3].T+matrix[:3,3]).tolist())
        slots=[material_ids.setdefault(m,len(material_ids)) for m in mesh.materials]
        mirror=np.linalg.det(matrix[:3,:3])<0
        uv=mesh.uv_layers.active
        if uv:
            coords=np.empty(len(mesh.loops)*2,dtype=np.float32)
            uv.uv.foreach_get("vector",coords)
            coords=coords.reshape((-1,2))
        for poly in mesh.polygons:
            vertices_order=list(poly.vertices)
            loops=list(poly.loop_indices)
            if mirror:
                vertices_order.reverse()
                loops.reverse()
            faces.append(tuple(offset+i for i in vertices_order))
            indices.append(slots[poly.material_index])
            smooth.append(poly.use_smooth)
            if uv:
                uv_data.extend(coords[loops])
    merged=bpy.data.meshes.new(name)
    merged.from_pydata(vertices,[],faces)
    for mat in material_ids:
        merged.materials.append(mat)
    merged.polygons.foreach_set("material_index",np.asarray(indices,dtype=np.int32))
    merged.polygons.foreach_set("use_smooth",np.asarray(smooth,dtype=np.bool_))
    if uv_data:
        layer=merged.uv_layers.new(name="UVMap")
        layer.uv.foreach_set("vector",np.asarray(uv_data,dtype=np.float32).ravel())
    merged.update()
    combined=bpy.data.objects.new(name,merged)
    parent.objects.link(combined)


def batch_preview(scene):
    """Batch static geometry in spatial groups and retain shared mesh objects for instancing."""
    interior=set(bpy.data.collections["楼内还原"].all_objects)
    batches=defaultdict(list)
    repeat=defaultdict(list)
    material_families=set(GLASS_COLORS)
    for obj in list(scene.objects):
        if obj.type!="MESH" or obj.hide_render:
            continue
        zone="室内" if obj in interior else "室外"
        if obj.data.users>1:
            if zone=="室内":
                repeat[zone,obj.data.name,*tile_for(obj)].append(obj)
            continue
        if len(obj.data.uv_layers)>1 or len(obj.data.vertices)<3 or obj.data.color_attributes:
            continue
        materials={m.name for m in obj.data.materials if m}
        if not materials or any(m is None for m in obj.data.materials):
            continue
        glass=bool(material_families.intersection(materials))
        key=(zone,*tile_for(obj),glass,bool(obj.data.uv_layers))
        batches[key].append(obj)
    select_meshes(scene,[])
    merged=0
    remove=[]
    for key,items in batches.items():
        if len(items)<3:
            continue
        name=f"{key[0]} {'玻璃' if key[4] else '构件'} {key[1]} {key[2]} {key[3]}"
        merge_meshes(items,name,items[0].users_collection[0])
        remove.extend(items)
        merged+=1
    bpy.data.batch_remove(ids=remove)
    for key,items in repeat.items():
        if len(items)<2:
            continue
        group=bpy.data.objects.new("共享房间批次",None)
        items[0].users_collection[0].objects.link(group)
        for obj in items:
            transform=obj.matrix_world.copy()
            obj.parent=group
            obj.matrix_world=transform
    bpy.context.view_layer.update()
    return {"合批网格对象":merged,"合入原网格":len(remove),"共享房间分组数":len(repeat)}


def publish_preview(scene):
    stats=batch_preview(scene)
    prepare_web_glass(active_glass())
    export_asset(OUT/"预览_整校.glb",instances=True)
    interiors=set(bpy.data.collections["楼内还原"].all_objects)
    select_meshes(scene,interiors)
    export_asset(OUT/"预览_室内.glb",selection=True,instances=True)
    select_meshes(scene,(o for o in scene.objects if o not in interiors))
    export_asset(OUT/"预览_室外.glb",selection=True,instances=True)
    return stats


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rebuilding_preview="--preview-only" in sys.argv
    bpy.ops.wm.open_mainfile(filepath=str(OUT/(STEM+".blend") if rebuilding_preview else SOURCE),load_ui=False)
    scene=bpy.context.scene
    report_path=OUT/"地面与预览记录.json"
    if rebuilding_preview:
        report=json.loads(report_path.read_text(encoding="utf8"))
    else:
        details=ground(scene)
        report={"来源":str(SOURCE.relative_to(ROOT.parent)),"地面依据":details,
                "说明":"补铺层低于既有细节铺装，树池与主要花园按航拍轮廓保留。车位线和遮挡处按图估排。"}
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        bpy.context.preferences.filepaths.save_version=0
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(STEM+".blend")))
        if "--draft" in sys.argv:
            return
        prepare_web_glass(active_glass())
        export_asset(OUT/(STEM+".glb"))
    report["预览合批"]=publish_preview(scene)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
