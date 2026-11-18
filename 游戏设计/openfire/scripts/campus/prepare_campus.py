"""Prepare the complete campus GLB, expanding GPU instances into glTF nodes."""

import hashlib
import json
import shutil
import struct
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT.parents[1] / "还原/成果/男女宿舍布局重排"
ASSETS = PROJECT / "assets/campus"
COMPONENTS = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    raw = path.read_bytes()
    json_size = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + json_size])
    binary_start = 20 + json_size + 8
    return document, bytearray(raw[binary_start:])


def accessor_values(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    layout = "<" + COMPONENTS[accessor["componentType"]] * WIDTHS[accessor["type"]]
    stride = view.get("byteStride", struct.calcsize(layout))
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [struct.unpack_from(layout, binary, offset + stride * i) for i in range(accessor["count"])]


def triangle_count(document):
    count = 0
    instances = 0
    for node in document["nodes"]:
        if "mesh" not in node:
            continue
        extension = node.get("extensions", {}).get("EXT_mesh_gpu_instancing")
        copies = document["accessors"][next(iter(extension["attributes"].values()))]["count"] if extension else 1
        instances += copies
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            indices = primitive.get("indices", primitive["attributes"]["POSITION"])
            count += document["accessors"][indices]["count"] // 3 * copies
    return count, instances


def open_gate(document, binary):
    # Reuse the already-open gate from the preceding playable version. These
    # meshes share the full preview's coordinates and vertex layout.
    previous, previous_binary = read_glb(ASSETS / "gate_plaza.glb")
    by_name = {node.get("name"): node for node in document["nodes"]}
    for node in previous["nodes"]:
        name = node.get("name", "")
        if name not in {"室外 构件 -1 -1 0", "室外 构件 0 -1 0"} and not name.startswith(("铁门双弧框", "铁门斜撑", "铁艺金色菱花")):
            continue
        target = by_name[name]
        source_primitives = previous["meshes"][node["mesh"]]["primitives"]
        target_primitives = document["meshes"][target["mesh"]]["primitives"]
        assert len(source_primitives) == len(target_primitives), name
        for source_primitive, target_primitive in zip(source_primitives, target_primitives):
            for semantic in ("POSITION", "NORMAL", "TANGENT"):
                if semantic not in source_primitive["attributes"]:
                    continue
                values = accessor_values(previous, previous_binary, source_primitive["attributes"][semantic])
                accessor = document["accessors"][target_primitive["attributes"][semantic]]
                assert len(values) == accessor["count"], (name, semantic)
                view = document["bufferViews"][accessor["bufferView"]]
                layout = "<" + COMPONENTS[accessor["componentType"]] * WIDTHS[accessor["type"]]
                stride = view.get("byteStride", struct.calcsize(layout))
                offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                for i, value in enumerate(values):
                    struct.pack_into(layout, binary, offset + stride * i, *value)
                if semantic == "POSITION":
                    accessor["min"] = [min(value[axis] for value in values) for axis in range(3)]
                    accessor["max"] = [max(value[axis] for value in values) for axis in range(3)]


def main():
    master, _ = read_glb(SOURCE / "校园_男女宿舍布局重排.glb")
    source_path = SOURCE / "预览_整校.glb"
    document, binary = read_glb(source_path)
    master_triangles, master_instances = triangle_count(master)
    assert triangle_count(document)[0] == master_triangles
    for node in list(document["nodes"]):
        extension = node.get("extensions", {}).pop("EXT_mesh_gpu_instancing", None)
        if extension is None:
            continue
        attributes = {semantic: accessor_values(document, binary, index) for semantic, index in extension["attributes"].items()}
        mesh = node.pop("mesh")
        children = node.setdefault("children", [])
        for instance in range(len(next(iter(attributes.values())))):
            child = {"name": "%s_instance_%03d" % (node["name"], instance), "mesh": mesh}
            for semantic, values in attributes.items():
                child[{"TRANSLATION": "translation", "ROTATION": "rotation", "SCALE": "scale"}[semantic]] = list(values[instance])
            children.append(len(document["nodes"]))
            document["nodes"].append(child)
        if not node["extensions"]:
            del node["extensions"]
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in document:
            document[key] = [extension for extension in document[key] if extension != "EXT_mesh_gpu_instancing"]
    open_gate(document, binary)
    output_triangles, output_instances = triangle_count(document)
    assert output_triangles == master_triangles
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    output = struct.pack("<III", 0x46546C67, 2, 28 + len(encoded) + len(binary))
    output += struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
    output += struct.pack("<II", len(binary), 0x004E4942) + binary
    (ASSETS / "campus_full.glb").write_bytes(output)
    shutil.copyfile(SOURCE / "楼门与公寓校正.json", ASSETS / "campus_entrances.json")
    manifest = {
        "source": str(source_path.relative_to(PROJECT.parents[1])),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "master_mesh_instances": master_instances,
        "master_triangles": master_triangles,
        "game_mesh_instances": output_instances,
        "game_triangles": output_triangles,
        "materials": len(document["materials"]),
        "images": len(document.get("images", [])),
        "changes": ["Static meshes use the complete batched preview", "All GPU room instances expanded to shared-mesh glTF nodes", "Main gate retains the preceding open-door pose"],
    }
    (ASSETS / "campus_full_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
