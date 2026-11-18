"""Index source images without moving the original material."""

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
DATA = WORK / "数据"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXTRA = {
    "123312": "向知远楼看，主轴正向", "123334": "向知远楼看，较宽视场",
    "123340": "主轴与黄色侧门转角", "123348": "黄色侧门正视及棚梁投影",
    "123355": "仰视桥底和两侧梁列", "123405": "回望景石和校门",
    "123415": "另一侧门及桥底斜视", "123435": "侧门转回主轴与知远楼",
}


def main():
    with (ROOT/"场景细化清单.csv").open(encoding="utf-8-sig",newline="") as file:
        catalog = {row["场景"]: row for row in csv.DictReader(file)}
    manifest = json.loads((DATA/"manifest.json").read_text(encoding="utf-8"))
    names = {f'{s["index"]:02}': s["name"] for s in manifest["scenes"]}
    assert names.keys() == catalog.keys()
    with (ROOT/"45场景分类与细化顺序.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["顺序","场景","场景名称","类别","优先参照朝向","逐图细化事项","当前状态"])
        for sid,row in catalog.items():
            writer.writerow([row["顺序"],sid,names[sid],row["类别"],row["优先参照朝向"],
                             row["逐图细化事项"],row["当前状态"]])
    hotspots = {}
    with (DATA/"02_元数据"/"hotspots.csv").open(encoding="utf-8-sig",newline="") as file:
        for row in csv.DictReader(file):
            sid = f'{int(row["源序号"]):02}'
            target = f'{int(row["目标序号"]):02}'
            for name in {row["热点标题"], row["目标场景"]}:
                hotspots[(sid, name.replace("&", "_"))] = target
    rows = []
    for folder in (DATA, WORK/"地图素材", WORK/"校门还原小样"):
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            relative = path.relative_to(WORK)
            parent = relative.parts
            sid, target, detail = "", "", ""
            if parent[0] == "地图素材":
                sid, kind = "40", "补充截图"
                detail = EXTRA[path.stem[-6:]]
            elif parent[0] == "校门还原小样":
                sid = {"01":"02","02":"03","03":"03","04":"05","05":"05"}[path.name[:2]]
                kind, detail = "已有模型渲染", path.stem[3:]
            elif parent[1] == "01_全景原始":
                sid = parent[3][:2]
                kind = ("全景原图" if path.stem.startswith("equirect") else
                        "立方体面" if path.parent.name == "faces" else "全景预览条")
                detail = path.stem
            elif parent[1] == "03_附属资源":
                if parent[2] in ("previews","thumbs"):
                    sid, kind = path.name[:2], "导览预览" if parent[2]=="previews" else "导览缩略图"
                else:
                    kind = "导览界面素材"
            elif parent[1] == "04_建模参考" and "02_八方向" in parent:
                sid, kind, detail = path.parent.name[:2], "透视方向图", path.stem+"°"
            elif parent[1] == "04_建模参考" and "03_热点指向" in parent:
                sid, kind = path.name[:2], "热点方向图"
                match = re.search(r"__→(.+)__(ath.+)$",path.stem)
                if match:
                    target = hotspots.get((sid,match[1]),"")
                    detail = match[1] + " " + match[2]
            elif parent[1] == "04_建模参考" and path.name.startswith("01_"):
                sid, kind, detail = "02", "航拍俯视衍生图", path.stem
            else:
                kind, detail = "跨场景索引", path.stem
            rows.append([relative.as_posix(), sid, names.get(sid,""),
                         catalog[sid]["类别"] if sid else "通用素材", kind, target, detail])
    assert {row[1] for row in rows if row[1]} == names.keys()
    with (ROOT/"图片逐文件索引.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["文件","所属拍摄场景","场景名称","分类","图像类型","热点目标场景","朝向或内容"])
        writer.writerows(rows)
    print(f"{len(rows)} images, {len(names)} scenes")
    missing = [row[0] for row in rows if row[4]=="热点方向图" and not row[5]]
    if missing:
        print("Hotspot targets unresolved:",missing)


if __name__ == "__main__":
    main()
