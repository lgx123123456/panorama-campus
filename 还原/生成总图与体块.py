"""Generate the traced campus plan and the editable first-pass mesh."""

import csv
import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import constrained_delaunay_triangles
from shapely.affinity import scale
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
import trimesh


ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "数据"
OUTPUT = ROOT / "成果" / os.environ.get("CAMPUS_BUILD_FOLDER", "第1轮")
PLAN = json.loads((ROOT / "总图标注.json").read_text(encoding="utf-8"))
ORIGIN = np.asarray(PLAN["origin"])
SCALE_REF = PLAN["scale_reference"]
SCALE = SCALE_REF["assumed_m"] / math.dist(SCALE_REF["start"], SCALE_REF["end"])
WEST, EAST = PLAN["orientation_reference"]
ANGLE = math.atan2(EAST[1] - WEST[1], EAST[0] - WEST[0])
COS, SIN = math.cos(ANGLE), math.sin(ANGLE)

COLORS = {
    "ground": (102, 118, 79), "garden": (78, 105, 67), "stone": (173, 166, 149),
    "road": (91, 94, 97), "court": (41, 98, 143), "track": (174, 93, 82),
    "court_green": (93, 140, 79), "court_key": (183, 83, 53),
    "grass": (91, 130, 69), "grass_light": (107, 143, 78), "line": (230, 226, 203),
    "ochre": (192, 142, 60), "glass": (58, 85, 97), "roof": (101, 109, 111),
    "metal": (60, 68, 72),
    "gate": (140, 148, 150), "water": (45, 77, 93), "tree": (74, 105, 56),
    "wood": (108, 89, 68), "route": (242, 202, 106),
    "paving_joint": (109, 105, 98), "light_stone": (190, 181, 161),
    "paving_red": (154, 107, 92), "seat_red": (152, 54, 45),
    "seat_green": (62, 106, 66), "cherry": (182, 85, 124),
}


def world(pixel):
    x, y = np.asarray(pixel) - ORIGIN
    return (float((x * COS + y * SIN) * SCALE), float((x * SIN - y * COS) * SCALE))


def aerial():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    source = next(scene for scene in manifest["scenes"] if scene["index"] == 2)
    with Image.open(DATA / source["equirect"]) as image:
        panorama = np.asarray(image.convert("RGB"))
    axis = np.linspace(-1.52, 1.52, 1700, dtype=np.float32)
    x, y = np.meshgrid(axis, axis)
    lon = np.arctan2(x, -y)
    lat = np.arctan2(-1, np.hypot(x, y))
    pixels = cv2.remap(
        panorama, (lon / (2 * np.pi) + .5) * panorama.shape[1] - .5,
        (.5 - lat / np.pi) * panorama.shape[0] - .5,
        cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP,
    )
    return Image.fromarray(pixels).rotate(105, resample=Image.Resampling.BICUBIC).crop(
        (36, 520, 1348, 1180)
    )


def draw_plan(reference, track, pitch):
    def font(size):
        return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)

    overlay = Image.new("RGBA", reference.size)
    draw = ImageDraw.Draw(overlay)
    draw.line([tuple(point) for point in PLAN["boundary"] + PLAN["boundary"][:1]],
              fill=(243, 233, 204, 235), width=2)
    for area in PLAN["areas"]:
        draw.polygon([tuple(point) for point in area["outline"]],
                     fill=(*COLORS[area["material"]], 72), outline=(240, 230, 202, 132))
    for geometry, color in ((track, "track"), (pitch, "grass")):
        draw.line(list(geometry.exterior.coords), fill=(*COLORS[color], 245), width=3)
    for building in PLAN["buildings"]:
        outline = [tuple(point) for point in building["outline"]]
        draw.polygon(outline, fill=(222, 159, 65, 80), outline=(247, 206, 117, 245), width=2)
        center = Polygon(outline).centroid
        draw.text((center.x, center.y), building["id"], anchor="mm", font=font(14),
                  fill="white", stroke_width=2, stroke_fill="#262921")
    draw.line([tuple(point) for point in PLAN["route"]], fill="#ffe08b", width=4)
    for camera in PLAN["cameras"]:
        x, y = camera["eye"]
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#fff4cf", outline="#35362f", width=2)
        draw.text((x + 10, y), camera["id"], anchor="lm", font=font(14), fill="white",
                  stroke_width=2, stroke_fill="#303028")

    width, height = reference.size
    canvas = Image.new("RGB", (width + 275, height + 98), "#f4f0e5")
    canvas.paste(Image.alpha_composite(reference.convert("RGBA"), overlay).convert("RGB"), (0, 71))
    legend = ImageDraw.Draw(canvas)
    legend.text((22, 17), "石家庄一中东校区 · 航拍描图", font=font(28), fill="#202923")
    legend.text((23, 53), "场景02全景重投影  /  比例与北向为初估  /  黄色线为首段漫游路线",
                font=font(13), fill="#4e594e")
    x = width + 22
    legend.text((x, 92), "建筑索引", font=font(21), fill="#202923")
    for i, building in enumerate(PLAN["buildings"]):
        suffix = " *" if building.get("estimated_id") else ""
        legend.text((x, 133 + i * 26), f'{building["id"]}   {building["name"]}{suffix}',
                    font=font(14), fill="#303831")
    legend.text((x, 461), "* 楼名位置待复核", font=font(13), fill="#5f665b")
    legend.text((x, 500), "首段路线", font=font(20), fill="#202923")
    legend.text((x, 538), "校门 → 尚德广场 → 知远楼", font=font(15), fill="#303831")
    legend.line((x + 14, 650, x + 14, 602), fill="#303831", width=2)
    legend.polygon(((x + 14, 589), (x + 8, 605), (x + 20, 605)), fill="#303831")
    legend.text((x + 30, 599), "北（初估）", font=font(14), fill="#303831")
    length = round(50 / SCALE)
    legend.line((x, 677, x + length, 677), fill="#303831", width=3)
    for edge in (x, x + length):
        legend.line((edge, 672, edge, 682), fill="#303831", width=2)
    legend.text((x, 692), "0", font=font(12), fill="#303831")
    legend.text((x + length, 692), "50 m", font=font(12), anchor="ra", fill="#303831")
    canvas.save(OUTPUT / "校园总平面.png")


def add(scene, name, mesh, material):
    color = COLORS[material]
    mesh.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
        name=material, baseColorFactor=(*color, 255), roughnessFactor=.82, metallicFactor=0
    ))
    scene.add_geometry(mesh, node_name=name, geom_name=name)


def prism(geometry, bottom, top):
    contour = orient(Polygon([world(point) for point in geometry.exterior.coords]))
    if not contour.is_valid or contour.area <= 0:
        raise ValueError("Invalid footprint")
    points = list(contour.exterior.coords)[:-1]
    point_index = {point: index for index, point in enumerate(points)}
    faces = [
        [point_index[point] for point in list(orient(triangle).exterior.coords)[:3]]
        for triangle in constrained_delaunay_triangles(contour).geoms
    ]
    mesh = trimesh.creation.extrude_triangulation(
        np.asarray(points), np.asarray(faces), top - bottom
    )
    mesh.apply_translation((0, 0, bottom))
    return mesh


def box(center, size, z, angle=0):
    matrix = trimesh.transformations.rotation_matrix(angle, (0, 0, 1))
    matrix[:3, 3] = (*center, z + size[2] / 2)
    return trimesh.creation.box(extents=size, transform=matrix)


def beam(start, end, width, z, height):
    a, b = np.asarray(world(start)), np.asarray(world(end))
    return world_beam(a, b, width, z, height)


def world_beam(a, b, width, z, height):
    dx, dy = b - a
    return box((a + b) / 2, (math.hypot(dx, dy), width, height), z, math.atan2(dy, dx))


def building_mesh(scene, record):
    asset_id = record["id"]
    footprint = Polygon(record["outline"])
    height = record["height"]
    add(scene, asset_id, prism(footprint, 0, height), "ochre")
    add(scene, asset_id + "_roof", prism(footprint, height, height + .34), "roof")
    wall = [world(point) for point in record["outline"]]
    windows, frames, bands = [], [], []
    detailed = asset_id in {"B40W", "B40E", "B45", "B36", "B32", "B21", "B15"}
    for index, (a, b) in enumerate(zip(wall, wall[1:] + wall[:1])):
        a, b = np.asarray(a), np.asarray(b)
        vector = b - a
        distance = np.linalg.norm(vector)
        bays = int(distance / (2.85 if detailed else 3.25))
        if bays == 0:
            continue
        angle = math.atan2(vector[1], vector[0])
        spacing = distance / bays
        is_end = detailed and len(wall) == 4 and distance < 24
        for bay in range(bays):
            position = a + vector * ((bay + .5) / bays)
            for floor in range(record["floors"]):
                z = height / record["floors"] * floor + 1.13
                if is_end:
                    if bay == bays // 2:
                        windows.append(box(position, (spacing * 1.85, .24, .76), z + .7, angle))
                    continue
                width = spacing * (.88 if detailed else .70)
                height_window = 2.65 if detailed else 2.0
                windows.append(box(position, (width, .22, height_window), z, angle))
                if detailed:
                    frames.append(box(position, (.10, .32, height_window), z, angle))
                    frames.append(box(position, (width, .31, .10), z + 1.35, angle))
            if detailed and not is_end and bay % 4 == 0:
                frames.append(box(position - vector / bays * .47, (.26, .40, height - .4), .15, angle))
        if detailed:
            bands.append(world_beam(a, b, .46, height - .52, .46))
            bands.append(world_beam(a, b, .48, 3.72, .35))
            if is_end and index in (1, 3) and asset_id != "B32":
                bands.append(box((a + b) / 2, (distance * .58, 2.5, 2.4), height, angle))
    if windows:
        add(scene, asset_id + "_windows", trimesh.util.concatenate(windows), "glass")
    if frames:
        add(scene, asset_id + "_mullions", trimesh.util.concatenate(frames), "metal")
    if bands:
        add(scene, asset_id + "_fascia", trimesh.util.concatenate(bands), "ochre")


def sports(scene, track, pitch):
    add(scene, "P09_track", prism(track, .005, .06), "track")
    add(scene, "P09_pitch", prism(pitch, .06, .09), "grass")
    for i in range(0, 10, 2):
        top = 184 + 226 * i / 10
        stripe = Polygon([(96, top), (243, top), (243, top + 22.6), (96, top + 22.6)])
        add(scene, f"P09_turf_{i}", prism(stripe, .09, .098), "grass_light")
    for i, (start, end) in enumerate([
        ((97, 185), (242, 185)), ((242, 185), (242, 409)),
        ((242, 409), (97, 409)), ((97, 409), (97, 185)),
        ((97, 297), (242, 297)),
    ]):
        add(scene, f"P09_line_{i}", beam(start, end, .12, .102, .008), "line")
    marks = []
    for inset in range(0, 8):
        path = track.buffer(-2.6 * inset - 2, join_style="round").exterior
        for start, end in zip(list(path.coords), list(path.coords)[1:]):
            marks.append(beam(start, end, .075, .064, .008))
    points = [(169 + 19.7 * math.cos(i * math.tau / 48),
               297 + 19.7 * math.sin(i * math.tau / 48)) for i in range(48)]
    for a, b in zip(points, points[1:] + points[:1]):
        marks.append(beam(a, b, .12, .102, .008))
    add(scene, "P09_markings", trimesh.util.concatenate(marks), "line")
    features = {"gate": [], "seat_red": [], "seat_green": [], "light_stone": [], "metal": []}
    for tier in range(10):
        x = 246 + tier * 2
        for start, end in ((139, 198), (206, 272), (325, 397), (405, 450)):
            features["gate"].append(beam((x, start), (x, end), .95, .07, .34 * (tier + 1)))
            color = "seat_green" if tier < 3 else "seat_red"
            features[color].append(beam((x - .69, start), (x - .69, end), .32,
                                        .34 * tier + .10, .28))
        for start, end in ((198, 206), (397, 405)):
            features["light_stone"].append(beam((x, start), (x, end), .94, .07, .34 * (tier + 1)))
    features["light_stone"].append(beam((263, 273), (263, 324), 7, .08, 4.2))
    features["seat_red"].append(beam((259, 273), (259, 324), 2.1, .08, 1.65))
    features["metal"].append(beam((260, 270), (260, 327), 8, 6.5, .38))
    for y in (275, 322):
        features["metal"].append(box(world((266, y)), (.34, .34, 6.5), .08))
    for color, meshes in features.items():
        add(scene, "P09_grandstand_" + color, trimesh.util.concatenate(meshes), color)

    court_lines = []
    for y0, y1 in ((93, 158), (165, 230)):
        x0, x1 = 321, 382
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        surface = Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
        add(scene, f"P11_court_surface_{y0}", prism(surface, .033, .045), "court_green")
        for a, b in [
            ((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)),
            ((mid_x, y0), (mid_x, y1)),
        ]:
            court_lines.append(beam(a, b, .09, .049, .008))
        ring = [(mid_x + 4.1 * math.cos(t * math.tau / 24),
                 mid_y + 4.1 * math.sin(t * math.tau / 24)) for t in range(24)]
        for a, b in zip(ring, ring[1:] + ring[:1]):
            court_lines.append(beam(a, b, .09, .049, .008))
        for x, facing in ((x0 + 1, 1), (x1 - 1, -1)):
            inner_x = x + facing * 12
            key = Polygon(((x, mid_y - 5), (inner_x, mid_y - 5),
                           (inner_x, mid_y + 5), (x, mid_y + 5)))
            add(scene, f"P11_key_{x}_{y0}", prism(key, .045, .048), "court_key")
            for a, b in zip(list(key.exterior.coords), list(key.exterior.coords)[1:]):
                court_lines.append(beam(a, b, .09, .050, .008))
            add(scene, f"P11_pole_{x}_{y0}", box(world((x, mid_y)), (.12, .12, 3.3), .05), "metal")
            add(scene, f"P11_board_{x}_{y0}",
                box(world((x + facing * 1.7, mid_y)), (.09, 1.65, .9), 2.7), "line")
    add(scene, "P11_court_lines", trimesh.util.concatenate(court_lines), "line")


def paving(scene):
    for index, area in enumerate(PLAN["areas"]):
        if area["id"] not in {"P03", "P05", "P40", "P07"}:
            continue
        shape = Polygon([world(point) for point in area["outline"]])
        x0, y0, x1, y1 = shape.bounds
        intervals = [
            LineString(((x, y0), (x, y1))) for x in np.arange(math.ceil(x0), x1, 1.2)
        ] + [
            LineString(((x0, y), (x1, y))) for y in np.arange(math.ceil(y0), y1, 1.2)
        ]
        joints = []
        for interval in intervals:
            cut = shape.intersection(interval)
            segments = list(cut.geoms) if hasattr(cut, "geoms") else [cut]
            for segment in segments:
                if segment.geom_type == "LineString" and segment.length > .10:
                    a, b = np.asarray(segment.coords)
                    joints.append(world_beam(a, b, .022, .0205 + index * .002, .0015))
        add(scene, area["id"] + "_paving_joints", trimesh.util.concatenate(joints), "paving_joint")


def gardens(scene):
    # 场景07/08的日晷花池与石文化墙，场景06的樱花和矮绿篱。
    for i, point in enumerate(((429, 310), (511, 290), (677, 383), (705, 382))):
        center = world(point)
        curb = trimesh.creation.cylinder(radius=2.8, height=.55, sections=36)
        curb.apply_translation((*center, .275))
        add(scene, f"Garden_curb_{i}", curb, "light_stone")
        hedge = trimesh.creation.cylinder(radius=2.58, height=.48, sections=36)
        hedge.apply_translation((*center, .68))
        add(scene, f"Garden_hedge_{i}", hedge, "tree")
    base = world((429, 310))
    disk = trimesh.creation.cylinder(radius=.94, height=.19, sections=48)
    disk.apply_transform(trimesh.transformations.rotation_matrix(math.radians(51), (1, 0, 0)))
    disk.apply_translation((*base, 1.68))
    add(scene, "P07_sundial_disk", disk, "light_stone")
    add(scene, "P07_sundial_plinth", box(base, (1.45, 1.2, 1.11), .30), "gate")
    for i, x in enumerate((452, 462, 472, 482)):
        add(scene, f"P07_culture_pier_{i}", box(world((x, 301)), (.82, .76, 2.1), 0), "light_stone")
        if i < 3:
            add(scene, f"P07_culture_panel_{i}", beam((x, 301), (x + 10, 301), .48, .42, 1.18),
                "gate")
    blossoms, trunks = [], []
    for x, y in ((677, 383), (705, 382), (657, 381), (722, 385), (692, 376)):
        a, b = world((x, y))
        trunks.append(box((a, b), (.25, .25, 3.6), .35))
        for angle in np.linspace(0, math.tau, 6, endpoint=False):
            crown = trimesh.creation.icosphere(subdivisions=2, radius=1)
            crown.apply_scale((1.55, 1.25, .95))
            crown.apply_translation((a + 1.14 * math.cos(angle), b + 1.14 * math.sin(angle), 3.8))
            blossoms.append(crown)
    add(scene, "P06_cherry_trunks", trimesh.util.concatenate(trunks), "wood")
    add(scene, "P06_cherry_canopies", trimesh.util.concatenate(blossoms), "cherry")


def entrance(scene):
    for name, outline in (
        ("Gate_west", [(790, 514), (804, 514), (804, 525), (790, 525)]),
        ("Gate_east", [(838, 514), (852, 514), (852, 525), (838, 525)]),
    ):
        add(scene, name, prism(Polygon(outline), 0, 3.1), "gate")
    for i, point in enumerate([(803, 519), (839, 519)]):
        add(scene, f"Gate_column_{i}", box(world(point), (1.5, 1.7, 5.5), 0), "gate")
    add(scene, "Gate_canopy", beam((791, 520), (851, 520), 4.6, 5.35, 1), "gate")
    add(scene, "Honor_wall", beam((779, 511), (763, 513), .35, 0, 2.1), "gate")
    pool = Polygon([(815, 456), (829, 456), (829, 486), (815, 486)])
    add(scene, "P05_pool_rim", prism(pool, .01, .28), "gate")
    add(scene, "P05_water", prism(pool.buffer(-1), .278, .29), "water")
    for i, point in enumerate([(786, 429), (877, 429)]):
        add(scene, f"B40_portal_column_{i}", box(world(point), (2.2, 4.8, 18), 0), "ochre")
    add(scene, "B40_bridge_deck", beam((788, 429), (875, 429), 5.3, 10.5, .66), "ochre")
    add(scene, "B40_bridge_glazing", beam((788, 429), (875, 429), 4.7, 11.16, 2.3), "glass")
    members = []
    for x in range(792, 873, 4):
        for y in (424, 434):
            members.append(box(world((x, y)), (.14, .14, 2.35), 11.15))
    add(scene, "B40_bridge_mullions", trimesh.util.concatenate(members), "metal")
    add(scene, "B40_portal_roof", beam((787, 429), (877, 429), 7, 17.8, 1.6), "ochre")
    slats = [beam((789, y), (875, y), .36, 17.35, .50) for y in range(418, 444, 3)]
    add(scene, "B40_canopy_slats", trimesh.util.concatenate(slats), "metal")
    arc = [(670, 448), (684, 469), (711, 489), (748, 506), (788, 514), (833, 517),
           (875, 509), (913, 491), (946, 464), (972, 431), (990, 392), (999, 352),
           (995, 308), (984, 263), (960, 221), (927, 186), (891, 164)]
    for i, (a, b) in enumerate(zip(arc, arc[1:])):
        add(scene, f"R05_arc_{i:02}", beam(a, b, 3.1, 4.1, .65), "gate")
        add(scene, f"R05_post_{i:02}", box(world(a), (.53, .53, 4.1), 0), "gate")
    trees = [(798, 467), (848, 474), (787, 447), (855, 450), (790, 395), (853, 409),
             (773, 368), (798, 363), (851, 371), (879, 384), (749, 244), (750, 264),
             (754, 281), (751, 299), (726, 279), (649, 374), (672, 378), (691, 383),
             (711, 372), (430, 312), (450, 322), (483, 310), (531, 300)]
    trunks, crowns = [], []
    for i, point in enumerate(trees):
        x, y = world(point)
        height = 3 + (i % 4) * .27
        trunks.append(box((x, y), (.24, .24, height), 0))
        crown = trimesh.creation.icosphere(subdivisions=1, radius=1)
        crown.apply_scale((1.5 + (i % 3) * .22, 1.56, 1.6))
        crown.apply_translation((x, y, height + .45))
        crowns.append(crown)
    add(scene, "Trees_trunks", trimesh.util.concatenate(trunks), "wood")
    add(scene, "Trees_crowns", trimesh.util.concatenate(crowns), "tree")


def build(track, pitch):
    scene = trimesh.Scene()
    add(scene, "Campus_ground", prism(Polygon(PLAN["boundary"]), -.45, 0), "ground")
    for index, area in enumerate(PLAN["areas"]):
        add(scene, area["id"], prism(Polygon(area["outline"]), -.01, .02 + index * .002),
            area["material"])
    sports(scene, track, pitch)
    paving(scene)
    gardens(scene)
    for record in PLAN["buildings"]:
        building_mesh(scene, record)
    entrance(scene)
    if OUTPUT.name == "第2轮":
        from 第二轮室外 import enhance
        enhance(scene, PLAN, add, box, beam, world_beam, world, COLORS)
    return scene


def export(scene):
    # glTF has Y-up. Blender and the working coordinates have Z-up.
    scene.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, (1, 0, 0)))
    (OUTPUT / "校园室外体块.glb").write_bytes(scene.export(file_type="glb"))
    rows = PLAN["buildings"] + PLAN["areas"]
    with (OUTPUT / "资产与证据.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["编号", "名称", "参考场景", "估测高度(m)", "状态"])
        for item in rows:
            status = "轮廓、高度和楼名对应待复核" if item.get("estimated_id") else "航拍初描，尺寸待复核"
            writer.writerow([item["id"], item["name"], item.get("scene", "02"),
                             item.get("height", ""), status])
    span = PLAN["check_references"][0]
    width_m = math.dist(span["start"], span["end"]) * SCALE
    road = PLAN["check_references"][1]
    a, b = map(world, (road["start"], road["end"]))
    road_angle = math.degrees(math.atan2(abs(a[1] - b[1]), abs(a[0] - b[0])))
    calibration = {
        "source": PLAN["reference"], "status": "估算，待测量或地图控制点",
        "origin_pixel": PLAN["origin"], "metres_per_pixel": SCALE,
        "rotation_degrees": math.degrees(ANGLE),
        "scale_reference": SCALE_REF, "orientation_reference": PLAN["orientation_reference"],
        "check_references": PLAN["check_references"],
        "pitch_width_m": round(width_m, 2),
        "pitch_width_delta_from_assumption_m": round(width_m - span["assumed_m"], 2),
        "road_angle_degrees": round(road_angle, 2),
        "camera_local_xyz": {camera["id"]: [*world(camera["eye"]), 1.6] for camera in PLAN["cameras"]},
    }
    (OUTPUT / "底图校准记录.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reference = aerial()
    reference.save(OUTPUT / "航拍重投影.png")
    track = LineString([(166, 209), (164, 389)]).buffer(105, quad_segs=20)
    # Use the visible straights and semicircles. The along-track scale is visual only.
    track = scale(track, xfact=1.02, yfact=.97)
    pitch = Polygon([(96, 184), (243, 184), (243, 410), (96, 410)])
    draw_plan(reference, track, pitch)
    export(build(track, pitch))


if __name__ == "__main__":
    main()
