"""Separate the existing classroom door triangles into hinged glTF nodes."""

import copy
import json
import math
import shutil
import struct
from pathlib import Path

import numpy as np

from prepare_campus import read_glb, triangle_count


ASSETS = Path(__file__).resolve().parents[2] / "assets/campus"
DTYPES = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def update_campus_manifest(document):
    path = ASSETS / "campus_full_manifest.json"
    data = json.loads(path.read_text("utf-8"))
    triangles, instances = triangle_count(document)
    assert triangles == data["master_triangles"]
    data["game_mesh_instances"] = instances
    data["game_triangles"] = triangles
    note = "Classroom door geometry is split into independent hinged meshes"
    if note not in data["changes"]:
        data["changes"].append(note)
    staged = path.with_suffix(".json.tmp")
    staged.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    staged.replace(path)


def read_array(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(DTYPES[accessor["componentType"]])
    width = WIDTHS[accessor["type"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    return np.ndarray((accessor["count"], width), dtype, binary, offset,
                      (stride, dtype.itemsize)).copy()


def append_array(document, binary, values, component, kind, target):
    values = np.asarray(values, dtype=DTYPES[component])
    binary.extend(b"\0" * (-len(binary) % 4))
    view = len(document["bufferViews"])
    document["bufferViews"].append({"buffer": 0, "byteOffset": len(binary),
                                  "byteLength": values.nbytes, "target": target})
    binary.extend(values.tobytes())
    accessor = {"bufferView": view, "componentType": component,
                "count": len(values), "type": kind}
    if kind == "VEC3":
        accessor["min"] = values.min(axis=0).tolist()
        accessor["max"] = values.max(axis=0).tolist()
    index = len(document["accessors"])
    document["accessors"].append(accessor)
    return index


def matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"]).reshape((4, 4), order="F")
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    result = np.eye(4)
    result[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                      [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                      [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    result[:3, :3] *= np.array(node.get("scale", [1, 1, 1]))
    result[:3, 3] = node.get("translation", [0, 0, 0])
    return result


def hinge_matrix(hinge, angle):
    result = np.eye(4)
    result[:3, :3] = [[math.cos(angle), 0, math.sin(angle)], [0, 1, 0],
                      [-math.sin(angle), 0, math.cos(angle)]]
    result[:3, 3] = hinge
    return result


def expected_doors(data):
    def point(value):
        return np.array([value[0], value[2], -value[1]])
    result = []
    for building in data["teaching_west_stairs"]["buildings"]:
        corner = point(building["corridor_path"][0])
        along = point(building["corridor_path"][1]) - corner
        along /= np.linalg.norm(along)
        across = np.array([-along[2], 0, along[0]])
        anchor = corner - along * 2.5 - across * 2.45
        for floor, height in enumerate(building["levels"]):
            for room in range(7):
                start = 3.5 if room == 0 else 14 + (room-1) * 64/6
                span = 10.5 if room == 0 else 64/6
                for side, offset in enumerate([0.83, 8.93]):
                    center = anchor + along * (start + offset * span/9.82)
                    center += across * (0.8 if room == 0 else 3.7)
                    center[1] = height
                    result.append({"id": f"{building['building']}_class_{floor}_{room}_{int(offset)}",
                                   "building": building["building"], "floor": floor,
                                   "room": room, "side": side, "expected": center})
    return result


def main():
    path = ASSETS / "campus_full.glb"
    document, binary = read_glb(path)
    manifest = ASSETS / "campus_classroom_doors.json"
    if document.get("extras", {}).get("native_classroom_doors"):
        records = document["extras"].get("native_classroom_door_records")
        if records is None:
            records = json.loads(manifest.read_text("utf-8"))
        assert len(records) == 140 and len({row["id"] for row in records}) == 140
        staged = manifest.with_suffix(".json.tmp")
        staged.write_text(json.dumps(records, ensure_ascii=False, indent=2), "utf-8")
        staged.replace(manifest)
        update_campus_manifest(document)
        print("Native classroom doors already prepared; manifest verified")
        return
    backup = Path("C:/CampusReconstructionRuntime/native-door-backup")
    backup.mkdir(parents=True, exist_ok=True)
    if not (backup / path.name).exists():
        shutil.copyfile(path, backup / path.name)
    candidates = expected_doors(json.loads((ASSETS / "campus_entrances.json").read_text("utf-8")))
    classroom_meshes = [index for index, mesh in enumerate(document["meshes"])
                        if any(document["materials"][p["material"]].get("name") == "front.001"
                               for p in mesh["primitives"])]
    assert len(classroom_meshes) == 1, classroom_meshes
    source_mesh = classroom_meshes[0]
    mesh = document["meshes"][source_mesh]
    original_nodes = list(enumerate(document["nodes"]))
    parents = {child: index for index, node in original_nodes for child in node.get("children", [])}

    def world(index):
        local = matrix(document["nodes"][index])
        return world(parents[index]) @ local if index in parents else local

    native = []
    leaves = []
    hinges = []
    for side, (door_y, degrees) in enumerate([(0.83, -169), (8.93, 11)]):
        hinge = np.array([-4.213, 0, -(door_y + 0.462)])
        opened = hinge_matrix(hinge, math.radians(degrees))
        inverse = np.linalg.inv(opened)
        leaf = {"name": f"OriginalClassroomDoor_{side}", "primitives": []}
        leaves.append(leaf)
        hinges.append((hinge, opened, inverse))

    kept = []
    for primitive in mesh["primitives"]:
        positions = read_array(document, binary, primitive["attributes"]["POSITION"])
        indices = read_array(document, binary, primitive["indices"]).reshape((-1, 3))
        remaining = np.ones(len(indices), dtype=bool)
        material = document["materials"][primitive["material"]].get("name", "")
        for side, (_, _, inverse) in enumerate(hinges):
            local = positions @ inverse[:3, :3].T + inverse[:3, 3]
            in_leaf = ((local[:, 0] > -0.002) & (local[:, 0] < 0.938)
                       & (local[:, 1] > 0.01) & (local[:, 1] < 2.163)
                       & (np.abs(local[:, 2]) < 0.135))
            selected = in_leaf[indices].all(axis=1) & remaining
            if material not in {"door", "door_edge", "frame", "silver", "透明平板玻璃"}:
                continue
            if not selected.any():
                continue
            used, remapped = np.unique(indices[selected].ravel(), return_inverse=True)
            attributes = {}
            for name, accessor_id in primitive["attributes"].items():
                accessor = document["accessors"][accessor_id]
                values = read_array(document, binary, accessor_id)[used]
                attributes[name] = append_array(document, binary, values, accessor["componentType"],
                                                accessor["type"], 34962)
            leaf_primitive = {"attributes": attributes, "material": primitive["material"],
                              "indices": append_array(document, binary, remapped.reshape((-1, 1)),
                                                      5125, "SCALAR", 34963)}
            leaves[side]["primitives"].append(leaf_primitive)
            remaining &= ~selected
        if remaining.any():
            part = copy.deepcopy(primitive)
            part["indices"] = append_array(document, binary, indices[remaining].reshape((-1, 1)),
                                            5125, "SCALAR", 34963)
            kept.append(part)
    mesh["primitives"] = kept
    for leaf in leaves:
        assert len(leaf["primitives"]) >= 5, leaf["name"]
    leaf_meshes = []
    for leaf in leaves:
        leaf_meshes.append(len(document["meshes"]))
        document["meshes"].append(leaf)

    for index, node in original_nodes:
        if node.get("mesh") != source_mesh:
            continue
        transform = world(index)
        for side, (hinge, opened, inverse) in enumerate(hinges):
            closed = hinge_matrix(hinge, -math.pi/2)
            center = (transform @ closed @ np.array([0.467, 0, 0, 1]))[:3]
            record = min((entry for entry in candidates if entry["side"] == side),
                         key=lambda entry: np.linalg.norm(entry["expected"] - center))
            distance = np.linalg.norm(record["expected"] - center)
            assert distance < 0.25, (node["name"], side, distance)
            direction = transform[:3, :3] @ np.array([-1, 0, 0])
            direction /= np.linalg.norm(direction)
            pivot_name = f"CampusClassroomPivot_{record['id']}"
            pivot_id = len(document["nodes"])
            document["nodes"].append({"name": pivot_name, "translation": hinge.tolist(),
                                      "rotation": [0, math.sin(-math.pi/4), 0, math.cos(-math.pi/4)],
                                      "children": [pivot_id+1]})
            document["nodes"].append({"name": f"CampusDoorLeaf_{record['id']}", "mesh": leaf_meshes[side],
                                      "matrix": inverse.flatten(order="F").tolist()})
            node.setdefault("children", []).append(pivot_id)
            width = np.linalg.norm(transform[:3, :3] @ np.array([0, 0, 0.933]))
            item = {key: record[key] for key in ["id", "building", "floor", "room"]}
            item.update({"point": center.tolist(), "outward": direction.tolist(), "width": float(width),
                         "pivot": pivot_name, "closed_angle": -math.pi/2,
                         "open_angle": math.radians(-169 if side == 0 else 11),
                         "swing_outward": side == 0, "height": 2.16})
            native.append(item)

    assert len(native) == 140 and len({record["id"] for record in native}) == 140
    for material in document["materials"]:
        if material.get("name") in {"front.001", "slide"}:
            color = [0.034, 0.106, 0.094, 1] if material["name"] == "front.001" else [0.715, 0.748, 0.727, 1]
            material["pbrMetallicRoughness"] = {"baseColorFactor": color, "metallicFactor": 0, "roughnessFactor": 0.88}
    native.sort(key=lambda row: (row["building"], row["floor"], row["room"], row["id"]))
    document.setdefault("extras", {})["native_classroom_doors"] = True
    document["extras"]["native_classroom_door_records"] = native
    document["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    output = struct.pack("<III", 0x46546C67, 2, 28+len(encoded)+len(binary))
    output += struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
    output += struct.pack("<II", len(binary), 0x004E4942) + binary
    staged_glb = path.with_suffix(".glb.tmp")
    staged_manifest = manifest.with_suffix(".json.tmp")
    staged_glb.write_bytes(output)
    staged_manifest.write_text(json.dumps(native, ensure_ascii=False, indent=2), "utf-8")
    verified, _ = read_glb(staged_glb)
    assert verified["extras"]["native_classroom_door_records"] == native
    staged_glb.replace(path)
    staged_manifest.replace(manifest)
    update_campus_manifest(document)
    print(f"Prepared {len(native)} native door pivots, preserving original glass, frames and handles")


if __name__ == "__main__":
    main()
