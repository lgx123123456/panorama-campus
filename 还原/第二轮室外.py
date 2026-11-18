"""Round-two exterior details drawn from the panorama set."""

import math

import numpy as np
from shapely.geometry import Polygon
import trimesh


def enhance(scene, plan, add, box, beam, world_beam, world, colors):
    colors.update({
        "gold_wall": (203, 147, 53), "glazing_dark": (42, 59, 71),
        "glazing_blue": (65, 103, 121), "sign_red": (155, 47, 40),
        "park_green": (60, 91, 50), "court_blue": (42, 95, 139),
    })
    batches = {}

    def collect(name, color, mesh):
        batches.setdefault((name, color), []).append(mesh)

    def volume(name, color, pixel, dimensions, z=0):
        collect(name, color, box(world(pixel), dimensions, z))

    def strip(name, color, a, b, width, z, height):
        collect(name, color, beam(a, b, width, z, height))

    # The chosen long sides are the photographed entrance-facing walls.
    fronts = {
        "B15": (3, 2), "B21": (3, 2), "B22": (6, 5),
        "B25": (5, 4), "B28": (5, 4), "B32": (6, 7),
        "B36": (0, 3), "B45": (0, 3), "B40W": (1, 2), "B40E": (0, 3),
    }
    for record in plan["buildings"]:
        asset = record["id"]
        if asset not in fronts:
            continue
        side_a, side_b = fronts[asset]
        points = [np.asarray(world(point)) for point in record["outline"]]
        center = np.mean(points, axis=0)
        start, end = points[side_a], points[side_b]
        vector = end - start
        distance = float(np.linalg.norm(vector))
        direction = vector / distance
        angle = math.atan2(direction[1], direction[0])
        normal = np.asarray((-direction[1], direction[0]))
        if np.dot((start + end) / 2 - center, normal) < 0:
            normal *= -1
        height = record["height"]
        total_bays = max(4, round(distance / 2.45))
        step = distance / total_bays

        # Offset the new curtain wall past the previous simple window geometry.
        # Opaque cladding remains behind the glazing in this exterior model.
        face = start + normal * .33
        collect(asset + "_facade", "glazing_dark",
                world_beam(face, face + vector, .24, 3.35, height - 4.25))
        for floor in range(1, record["floors"]):
            level = 3.55 + (floor - 1) * (height - 4.25) / (record["floors"] - 1)
            for i in range(total_bays):
                position = face + direction * ((i + .5) * step) + normal * .15
                floor_h = (height - 4.25) / (record["floors"] - 1)
                collect(asset + "_panels", "glazing_blue",
                        box(position, (step * .85, .075, floor_h * .68), level, angle))
            collect(asset + "_spandrel", "gold_wall",
                    world_beam(face + normal * .20, face + vector + normal * .20,
                               .16, level - .20, .26))
        for i in range(total_bays + 1):
            position = face + direction * (i * step) + normal * .21
            collect(asset + "_facade_frames", "metal",
                    box(position, (.073, .12, height - 4.15), 3.37, angle))
        middle = face + vector * (.52 if asset != "B22" else .40)
        is_library = asset == "B32"
        is_dorm = asset in {"B25", "B28"}
        entry_width = min(7.4 if is_library else 5.4, distance * .55)
        for factor in (-.5, .5):
            collect(asset + "_portico", "gold_wall",
                    box(middle + direction * entry_width * factor + normal * 1.4,
                        (.45, .62, 3.30), .06, angle))
        collect(asset + "_canopy", "gold_wall",
                box(middle + normal * 1.18, (entry_width + .66, 3.05, .36), 3.28, angle))
        collect(asset + "_entrance_glass", "glazing_blue",
                box(middle + normal * .31, (entry_width - .48, .11, 2.70), .23, angle))
        for i in range(1, 6):
            collect(asset + "_door_frames", "metal",
                    box(middle + normal * .39 + direction * ((i-3) * entry_width / 6),
                        (.061, .075, 2.64), .25, angle))
        if is_library or is_dorm:
            for tier in range(4 if is_library else 3):
                collect(asset + "_entry_steps", "light_stone",
                        box(middle + normal * (1.78 - tier * .31),
                            (entry_width, 1.22, .16 * (tier+1)), .02, angle))
        if is_library or asset == "B22":
            collect(asset + "_entrance_panel", "sign_red",
                    box(middle + normal * .43, (entry_width * .75, .11, .83), 4.40, angle))
        if asset == "B22":
            exit_center = face + vector * .78
            collect(asset + "_exit_glass", "glazing_blue",
                    box(exit_center + normal * .31, (4.1, .12, 2.65), .22, angle))
            collect(asset + "_exit_canopy", "gold_wall",
                    box(exit_center + normal * .92, (4.8, 2.05, .33), 3.19, angle))
            for offset in (-1.3, 0, 1.3):
                collect(asset + "_exit_frames", "metal",
                        box(exit_center + direction * offset + normal * .41,
                            (.07, .09, 2.60), .23, angle))

    # 西门名称来自场景13。局部位置先按场景12–14关系和航拍北侧通道估放。
    for x in (915, 931):
        volume("P13_offsite_gate_piers", "light_stone", (x, 153), (.70, .82, 2.7))
    strip("P13_offsite_gate_transom", "gold_wall", (915,153),(931,153),.52,2.70,.32)
    for x in (903, 941):
        volume("P13_planters", "light_stone", (x,159), (3.0,1.9,.42))
        volume("P13_planters_greenery", "park_green", (x,159), (2.8,1.7,.48), .39)
    for y in (137, 144):
        strip("P13_walk_connection", "stone", (903,y),(945,y),3.4,.012,.018)
    for x in range(824, 928, 10):
        volume("P14_growing_beds", "wood", (x,160), (3.25,1.02,.24),.028)
        volume("P14_crop_rows", "park_green", (x,160), (2.96,.82,.29),.23)
    for x in range(609, 714, 10):
        volume("P12_pergola_posts","wood",(x,174),(.20,.20,2.4))
        volume("P12_pergola_posts","wood",(x,184),(.20,.20,2.4))
        strip("P12_roof_rafters","gold_wall",(x,172),(x,186),.16,2.4,.16)
    for y in (174,184):
        strip("P12_pergola_beams","wood",(605,y),(715,y),.22,2.29,.25)
    pingpong = ((252,438),(252,449),(252,460))
    strip("P10_pingpong_paving","stone",(251,432),(251,469),5.5,.050,.055)
    for i, point in enumerate(pingpong):
        volume("P10_tabletops","court_blue",point,(1.53,2.74,.08),.74)
        volume("P10_nets","metal",point,(1.55,.035,.15),.81)
        for side in (-1,1):
            volume("P10_table_legs","sign_red",(point[0],point[1]+side*1.5),(.09,.09,.75),.06)
    for line in (
        ((395,187),(807,185)), ((956,169),(1023,171)), ((890,487),(1018,482)),
        ((350,491),(600,493)), ((544,275),(696,275)), ((585,366),(722,365)),
    ):
        a,b=map(np.asarray,line)
        count=int(np.linalg.norm(b-a)/13)
        for i in range(count+1):
            point=a+(b-a)*i/count
            loc=world(point)
            crown=trimesh.creation.icosphere(subdivisions=2,radius=1)
            radius=1.35+(.24*(i%3))
            crown.apply_scale((radius,radius,1.45*radius))
            crown.apply_translation((*loc,3.0+.12*(i%4)))
            collect("R06_walk_trees","park_green",crown)
            volume("R06_walk_tree_trunks","wood",point,(.21,.21,2.95))
            if i%4==0:
                volume("R06_walk_lamps","metal",point+(0,3),(.15,.15,3.75))
                volume("R06_walk_lamp_heads","line",point+(0,3),(.47,.27,.16),3.68)
    for (name,color),meshes in batches.items():
        add(scene, name+"_"+color, trimesh.util.concatenate(meshes),color)
