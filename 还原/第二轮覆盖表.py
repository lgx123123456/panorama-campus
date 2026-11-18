"""Trace the 45 source viewpoints to delivered Blender or GLB assets."""

import csv
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "成果" / "第2轮"
EXTERIOR = {
    1: ("Campus_ground", "航拍底图与全校室外模型"),
    2: ("Campus_ground", "总平面描图与全校室外模型"),
    3: ("校名实拍贴面", "门楼及门房"),
    4: ("Honor_wall", "荣誉墙体块，图文待补"),
    5: ("P05", "尚德广场铺装和喷泉"),
    6: ("P06", "樱花园与花池"),
    7: ("P07_sundial_disk", "日晷与围合花池"),
    8: ("P07_culture_panel", "文化墙和石柱，文字待补"),
    9: ("P09_track", "操场、跑道和看台"),
    10: ("P10_tabletops", "乒乓球台及场地，位置估算"),
    11: ("P11_court_lines", "篮球场、标线及球架"),
    12: ("P12_pergola", "攀桂轩廊架，位置估算"),
    13: ("P13_offsite_gate", "西门景观试摆，入口位置和外形待复核"),
    14: ("P14_growing_beds", "劳动基地种植畦，位置估算"),
    15: ("B15_facade", "志远楼入口与立面"),
    21: ("B21_facade", "思远楼入口与立面"),
    22: ("B22_facade", "餐厅立面，入口位置估算"),
    24: ("B22_exit_glass", "餐厅出口几何，门位待复核"),
    25: ("B25_facade", "绅远楼立面与入口，楼名对应待复核"),
    28: ("B28_facade", "蕙远楼立面与入口，楼名对应待复核"),
    32: ("B32_facade", "图书馆幕墙与入口台阶"),
    36: ("B36_facade", "行远楼立面和入口"),
    40: ("B40_bridge_deck", "艺远楼与识远楼之间的连廊"),
    45: ("B45_facade", "知远楼立面和入口"),
}
INTERIOR_PARENT = {
    16: "B15", 17: "B15", 18: "B15", 19: "B40W/B40E", 20: "B40W/B40E",
    23: "B22", 26: "B25", 27: "B25", 29: "B28", 30: "B28", 31: "楼栋待核实",
    33: "B32", 34: "B32", 35: "B32", 37: "B36", 38: "B36", 39: "B36",
    41: "B40W/B40E", 42: "B40W/B40E", 43: "B40W/B40E", 44: "B40W/B40E",
}


def read_glb(path):
    data = path.read_bytes()
    magic, version, total, size, chunk_type = struct.unpack_from("<4sIIII", data)
    if (magic, version, total, chunk_type) != (b"glTF", 2, len(data), 0x4E4F534A):
        raise ValueError(f"Invalid GLB header: {path}")
    return json.loads(data[20:20+size])


def main():
    outdoor = OUT / "校园室外还原.glb"
    nodes = {node["name"] for node in read_glb(outdoor)["nodes"]}
    with (ROOT.parent/"数据"/"02_元数据"/"scenes.csv").open(encoding="utf-8-sig") as file:
        sources = list(csv.DictReader(file))
    if set(EXTERIOR) & set(INTERIOR_PARENT) or len(sources) != len(EXTERIOR) + len(INTERIOR_PARENT):
        raise ValueError("The coverage must include each source viewpoint once")
    with (OUT/"45场景覆盖表.csv").open("w",newline="",encoding="utf-8-sig") as file:
        writer=csv.writer(file)
        writer.writerow(["场景编号","原始场景","参考分组","当前几何","模型内定位","模型文件","复核项"])
        for source in sources:
            number=int(source["序号"])
            sid=f"{number:02}"
            name=source["名称"]
            if number in EXTERIOR:
                prefix,detail=EXTERIOR[number]
                if not any(node.startswith(prefix) for node in nodes):
                    raise ValueError(f"No exported geometry for {sid} {prefix}")
                fields=["室外",prefix,outdoor.name,detail]
            else:
                indoor=OUT/"室内"/f"{sid}_{name}.glb"
                if not read_glb(indoor).get("meshes"):
                    raise ValueError(f"No room geometry for {sid}")
                fields=["独立室内",f"参考归属 {INTERIOR_PARENT[number]}",
                        indoor.relative_to(OUT).as_posix(),"尺寸估算，实际楼层、门位与连通关系待复核"]
            writer.writerow([sid,name,source["分组"],*fields])


if __name__=="__main__":
    main()
