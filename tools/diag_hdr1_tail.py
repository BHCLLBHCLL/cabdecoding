# -*- coding: utf-8 -*-
"""P5-1: hdr1 尾列黑盒差异实验（双分支定档证据工具）。

扫描本机全部 Cradle 示例库（不止 R8-B 的 295 对 ST 样本，还包括
scFLOW 2023.2 / scFLOW 2025.2 / tr03 / box 等本地工程产物）中每个
.s 文件的 SDAT hdr1 行尾 5 列与 hdr2 行尾 6 列。

**P5-1 实验结论（2026-08-24，分支 a：派生公式 A 级）**

全库 299 个 .s（295 对可配 XML）中仅 exB12/exB12_e 偏离默认
(1,1,0,0,0)，其 hdr1 尾列为 (1,1,10000,1,1)。交叉表排除
type/turbulence/diffusion/calculation/heat/moving_body/mesh_kind
后锁定唯一驱动特征：<analysis_etc><particle><kind>。按
``col4 = col5 = 1 iff kind=="reaction"`` 回验 295 对零失配
（marker 6 / mass 6 / reaction 2 / 无粒子 281）。公式已实现于
s_export.hdr1_tail；本工具留作定档证据与未来库扩充复检。

用法:
    python tools/diag_hdr1_tail.py [根目录 ...] [--json out.json]
根目录缺省为 D:\\training\\cradle 下全部子目录 + tests/box。
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CRADLE = r"D:\training\cradle"


def s_header(path):
    """SDAT 头两行计数行 -> (hdr1 尾 5 元组, hdr2 尾 6 元组)；失败 None。"""
    try:
        lines = open(path, encoding="utf-8-sig", errors="replace"
                     ).read().splitlines()
    except OSError:
        return None
    stripped = [l.strip() for l in lines]
    if "SDAT" not in stripped:
        return None
    i = stripped.index("SDAT")
    rows = []
    for l in lines[i + 1:i + 30]:
        f = [l[k:k + 12].strip() for k in range(0, len(l), 12)]
        f = [x for x in f if x != ""]
        if len(f) >= 8 and all(x.lstrip("-").isdigit() for x in f):
            rows.append([int(x) for x in f])
        elif rows:
            break
        if len(rows) == 2:
            break
    if not rows:
        return None
    h1 = tuple(rows[0][3:8]) if len(rows[0]) >= 8 else None
    h2 = (tuple(rows[1][3:9]) if len(rows) > 1 and len(rows[1]) >= 9
          else None)
    return h1, h2


def xml_features(cab_path):
    """候选驱动特征（仅对偏离样本调用）。"""
    from cab_container import CabArchive
    arch = CabArchive.parse(open(cab_path, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    name = next(k for k in members
                if k.endswith(".xml") and not k.startswith("_"))
    import xml.etree.ElementTree as ET
    root = ET.fromstring(members[name])

    def t(el, tag):
        if el is None:
            return ""
        c = el.find(tag)
        return (c.text or "").strip() if c is not None and c.text else ""

    aset = root.find("analysis_set")
    mb = root.find("mesh_block")
    return {
        "type": t(aset, "type"),
        "heat": t(aset, "heat"),
        "turbulence": t(aset, "turbulence"),
        "calculation": t(aset, "calculation"),
        "moving_body": t(aset, "moving_body"),
        "mesh_kind": mb.attrib.get("kind", "") if mb is not None else "",
        "particle": root.find("analysis_etc/particle") is not None,
        "free_surf": root.find("analysis_etc/free_surf") is not None,
        "fusion": root.find("analysis_etc/fusion") is not None,
        "diffusion": len(root.findall("diffusion")),
    }


def main():
    args = sys.argv[1:]
    out_json = None
    if "--json" in args:
        i = args.index("--json")
        if i + 1 < len(args):
            out_json = args[i + 1]
            del args[i:i + 2]
    roots = args or [os.path.join(CRADLE, d) for d in os.listdir(CRADLE)]
    roots.append(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tests", "box"))

    dist1 = Counter()
    dist2 = Counter()
    by_lib1 = {}
    deviations = []
    n_total = n_parsed = 0
    for root in roots:
        lib = os.path.basename(root.rstrip("\\/")) or root
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if not f.endswith(".s"):
                    continue
                n_total += 1
                got = s_header(os.path.join(dirpath, f))
                if got is None:
                    continue
                h1, h2 = got
                n_parsed += 1
                dist1[h1] += 1
                dist2[h2 or ("-",)] += 1
                by_lib1.setdefault(lib, Counter())[h1] += 1
                if h1[:2] != (1, 1) or h1[3:] != (0, 0):
                    rel = os.path.relpath(os.path.join(dirpath, f), root)
                    row = {"sample": f"{lib}/{rel}", "hdr1_tail": h1}
                    cab = os.path.join(dirpath, f[:-2] + ".cab")
                    if os.path.exists(cab):
                        try:
                            row["xml"] = xml_features(cab)
                        except Exception as e:  # noqa: BLE001
                            row["xml_error"] = str(e)
                    deviations.append(row)

    print(f"scanned .s files: {n_total}, parsed header: {n_parsed}")
    print("\n== hdr1 tail-5 distribution ==")
    for val, n in dist1.most_common():
        print(f"  {val}: {n}")
    print("\n== hdr2 tail-6 distribution ==")
    for val, n in dist2.most_common():
        print(f"  {val}: {n}")
    print("\n== per-library hdr1 tail ==")
    for lib, c in sorted(by_lib1.items()):
        tops = ", ".join(f"{k}:{v}" for k, v in c.most_common(4))
        print(f"  {lib}: {tops}")

    print(f"\n== deviations from (1,1,*,0,0): {len(deviations)} ==")
    for row in deviations:
        print(f"  {row['sample']}: hdr1_tail={row['hdr1_tail']}"
              + (f" xml={row['xml']}" if "xml" in row else ""))

    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump({"dist_hdr1": {str(k): v for k, v in dist1.items()},
                       "dist_hdr2": {str(k): v for k, v in dist2.items()},
                       "deviations": deviations}, fh, ensure_ascii=False,
                      indent=1, default=str)
        print(f"\nJSON 已写入 {out_json}")


if __name__ == "__main__":
    main()
