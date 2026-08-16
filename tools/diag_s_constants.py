# -*- coding: utf-8 -*-
"""R8-B: .s 导出 opaque 常量多样本交叉诊断工具。

对比 CradleCFD_2023.2_ST_Example 中每个 (项目 .cab, 官方 .s) 样本对：
  * XML 侧：analysis_set 开关（heat / turbulence / turbulence_model /
    calculation / cycle / thermal_solver / radiation.* / heat_path）、
    steady_param/under_relax、根级 <diffusion> 元素个数（物种数）、
    <analysis_etc><free_surf>（自由面开关）。
  * .s 侧：SDAT 头两行计数（各 9 列）、EQUA 掩码、HSOL 两行、
    CYCS/CYCT、UNDR、VFEM 行、HEATPATH/VFEX/VFDE 段存在性。

输出 JSON 对照表 + 控制台摘要，并按 R8-B 实现的派生规则逐样本
回验（derived vs actual），不一致的行标 MISMATCH。

用法:
    python tools/diag_s_constants.py [示例库根目录] [--json out.json]
"""

from __future__ import annotations

import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cab_container import CabArchive  # noqa: E402

DEFAULT_ROOT = r"D:\training\cradle\CradleCFD_2023.2_ST_Example"


def _text(el, tag):
    if el is None:
        return ""
    c = el.find(tag)
    return (c.text or "").strip() if c is not None and c.text else ""


def load_xml(cab_path):
    arch = CabArchive.parse(open(cab_path, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    name = next(k for k in members
                if k.endswith(".xml") and not k.startswith("_"))
    import xml.etree.ElementTree as ET
    return ET.fromstring(members[name])


def xml_state(root):
    aset = root.find("analysis_set")
    rad = aset.find("radiation") if aset is not None else None
    sp = root.find("steady_param")
    return {
        "type": _text(aset, "type"),
        "heat": _text(aset, "heat"),
        "turbulence": _text(aset, "turbulence"),
        "turbulence_model": _text(aset, "turbulence_model"),
        "calculation": _text(aset, "calculation"),
        "cycle": _text(aset, "cycle"),
        "thermal_solver": _text(aset, "thermal_solver"),
        "heat_path": _text(aset, "heat_path"),
        "time_step": _text(aset, "time_step"),
        "init_time_step": _text(aset, "init_time_step"),
        "courant": _text(aset, "courant"),
        "radiation": "1" if rad is not None else "",
        "rad_type": rad.attrib.get("type", "") if rad is not None else "",
        "rad_method": _text(rad, "method"),
        "rad_calc_cycle": _text(rad, "calc_cycle"),
        "under_relax": _text(root.find("steady_param"), "under_relax"),
        "undr_list": [((e.attrib.get("type", "T"),
                        (e.text or "0").split(",")[0].strip())
                       if e is not None else ("", ""))
                      for e in (sp.findall("under_relax")
                                if sp is not None else [])],
        "sted_list": [((e.attrib.get("type", "T"),
                        (e.text or "0,0").split(","))
                       if e is not None else ("", ""))
                      for e in (sp.findall("conv_check")
                                if sp is not None else [])],
        # 各轴向网格区间数（mesh_block 轴 num 属性 - 1；圆柱块 r/t/z）
        "axes": _axes_intervals(root),
        # 根级 <diffusion> 元素每个代表一个扩散物种（多样本证据）
        "diffusion_species": len(root.findall("diffusion")),
        # 自由面：analysis_etc/free_surf 存在即开启（exA15-8/9 实证）；
        # mars_fluid_energy=1 时 EQUA 位5=2（两流体能量方程）
        "free_surface": "1" if root.find("analysis_etc/free_surf")
                        is not None else "",
        "mars_fluid_energy": _text(
            root.find("analysis_etc/free_surf"), "mars_fluid_energy"),
        # 运动件：存在 body_move 类型的 value 定义（条件绑定见 cabxml）
        "moving_parts": "1" if any(
            v.attrib.get("type") == "body_move"
            for v in root.iter("value")) else "",
    }


def _axes_intervals(root):
    """mesh_block 各轴区间数 (x,y,z)；圆柱块 r/t/z 映射回 x/y/z。"""
    mb = root.find("mesh_block")
    out = [1, 1, 1]
    if mb is None:
        return tuple(out)
    for base, tags in enumerate((("x", "r"), ("y", "t"), ("z", "z"))):
        el = None
        for tag in tags:
            el = mb.find(tag)
            if el is not None:
                break
        if el is None:
            continue
        if el.attrib.get("num", "").strip().isdigit():
            out[base] = max(int(el.attrib["num"]) - 1, 0)
        else:
            out[base] = max(len(el.findall("g")) - 1, 0)
    return tuple(out)


def s_state(path):
    lines = open(path, encoding="utf-8-sig", errors="replace"
                 ).read().splitlines()
    out = {"sections": []}
    stripped = [l.strip() for l in lines]
    # SDAT 头两行 12 宽整数计数行
    hdr = []
    for i, l in enumerate(stripped):
        if l == "SDAT":
            for j in range(i + 1, min(i + 40, len(lines))):
                f = [lines[j][k:k + 12].strip()
                     for k in range(0, len(lines[j]), 12)]
                f = [x for x in f if x != ""]
                if len(f) >= 8 and all(x.lstrip("-").isdigit()
                                       for x in f[:8]):
                    hdr.append(f[:9])
            break
    out["hdr"] = hdr
    for i, l in enumerate(stripped):
        if l == "EQUA":
            out["equa"] = lines[i + 1].strip()
        elif l == "HSOL":
            out["hsol"] = [lines[i + 1].strip(), lines[i + 2].strip()]
        elif l in ("CYCS", "CYCT"):
            out["cyc"] = l + " " + " ".join(lines[i + 1].split())
        elif l == "UNDR":
            out.setdefault("undrs", []).append(lines[i + 1].strip())
        elif l == "STED":
            out.setdefault("steds", []).append(lines[i + 1].strip())
        elif l == "VFEM":
            out["vfem"] = lines[i + 1].strip()
    for sec in ("HEATPATH", "VFEX", "VFDE", "VFEM"):
        if sec in stripped:
            out["sections"].append(sec)
    return out


# ---- R8-B 派生规则（与 s_export.py 实现一致，用于回验） -----------------

def derive_equa(x):
    """EQUA 8 位掩码：位1-3 各轴向区间数>1（2D/1D 关对应动量方程）；
    位4 恒 1（连续性）；位5=heat(0/1，自由面=2)；位6-7 湍流 k/eps；
    位8 扩散物种>0。"""
    heat = x["heat"] == "1"
    mars = x["free_surface"] == "1" and x["mars_fluid_energy"] == "1"
    turb = x["turbulence"] not in ("", "0")
    diff = x["diffusion_species"] > 0
    bits = "".join("1" if n > 1 else "0" for n in x["axes"][:3])
    bits += "1"
    if not heat:
        bits += "0"
    elif mars:
        bits += "2"
    else:
        bits += "1"
    bits += ("1" if turb else "0") * 2
    bits += "1" if diff else "0"
    return bits


def derive_hdr2(x):
    """SDAT 第二行 9 列：col1=扩散物种数；col2=辐射面组数
    (无辐射 0 / type=flux 2 / 其余 4)；col3=湍流模型号；其余 0。"""
    col2 = "2" if x["rad_type"] == "flux" else (
        "4" if x["radiation"] else "0")
    col3 = x["turbulence_model"] or "0"
    return [str(x["diffusion_species"]), col2, col3,
            "0", "0", "0", "0", "0", "0"]


def derive_hsol(x):
    """HSOL 仅热分析 + type!=compressive + 无自由面 + 无运动件发射；
    值取 thermal_solver 的 [0] / [1],[3],[4]。"""
    if not (x["heat"] == "1"
            and x["type"] != "compressive"
            and x["free_surface"] != "1"
            and x["moving_parts"] != "1"):
        return None
    ts = (x["thermal_solver"] or "1,3,2,1,1,0").split(",")
    return [ts[0], [ts[1], ts[3], ts[4]]]


def derive_cyc(x):
    """CYCS(稳态) / CYCT(瞬态, 第三值: 固定 time_step=-1, courant=1)。"""
    cyc = (x["cycle"] or "1,100").split(",")
    c0 = cyc[0] if cyc and cyc[0] else "1"
    c1 = cyc[1] if len(cyc) > 1 and cyc[1] else "100"
    if x["calculation"] == "transient":
        third = "-1" if x["time_step"] else "1"
        return "CYCT %s %s %s" % (c0, c1, third)
    return "CYCS %s %s" % (c0, c1)


_TYPE_IDX = {"U": 1, "V": 2, "W": 3, "P": 4, "T": 5, "K": 6, "E": 7}


def _parse_undr(text):
    """'5 9.9e-01' -> (5, 0.99)，供派生/实际两侧统一数值比较。"""
    p = text.split()
    return (int(p[0]), float(p[1]) if len(p) > 1 else 0.0)


def derive_undrs(x):
    """UNDR 行：类型索引 U1 V2 W3 P4 T5 K6 E7 + under_relax 首值。"""
    out = []
    for typ, val in x["undr_list"]:
        out.append("%d %s" % (_TYPE_IDX.get(typ, 5), float(val or 0)))
    return out


def derive_steds(x):
    """STED 行：类型索引 + conv_check[0] 步数 + conv_check[1] eps。"""
    out = []
    for typ, parts in x["sted_list"]:
        if not parts or parts[0] in ("", "0"):
            continue
        eps = parts[1] if len(parts) > 1 and parts[1] else "0"
        out.append("%d %s %s" % (_TYPE_IDX.get(typ, 5),
                                 int(parts[0]), float(eps)))
    return out


def derive_sections(x):
    """VFEX 仅角系数法辐射；HEATPATH 仅 heat_path=1。"""
    return {
        "vfex": bool(x["radiation"]) and x["rad_type"] != "flux",
        "heatpath": x["heat_path"] == "1",
    }


def main():
    # 位置参数为示例库根目录；--json <file> 指定 JSON 输出
    args = sys.argv[1:]
    pos = []
    out_json = None
    i = 0
    while i < len(args):
        if args[i] == "--json" and i + 1 < len(args):
            out_json = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            i += 1
        else:
            pos.append(args[i])
            i += 1
    root = pos[0] if pos else DEFAULT_ROOT

    pairs = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".s"):
                stem = f[:-2]
                cab = os.path.join(dirpath, stem + ".cab")
                if os.path.exists(cab):
                    pairs.append((cab, os.path.join(dirpath, f)))

    table = []
    for cab, sfile in sorted(pairs):
        try:
            x = xml_state(load_xml(cab))
            s = s_state(sfile)
        except Exception as e:  # noqa: BLE001
            table.append({"sample": os.path.basename(sfile), "error": str(e)})
            continue
        row = {"sample": os.path.basename(sfile), "xml": x, "s": s}
        # 派生规则回验（与 s_export.py 实现一致）
        secs = derive_sections(x)
        row["check"] = {
            "equa": {"derived": derive_equa(x),
                     "actual": s.get("equa", ""),
                     "ok": derive_equa(x) == s.get("equa", "")},
            "hdr2": {"derived": derive_hdr2(x),
                     "actual": s["hdr"][1] if len(s["hdr"]) > 1 else [],
                     "ok": (len(s["hdr"]) > 1
                            and derive_hdr2(x) == s["hdr"][1])},
            "cyc": {"derived": derive_cyc(x),
                    "actual": s.get("cyc", ""),
                    "ok": derive_cyc(x) == s.get("cyc", "")},
            "undrs": {"derived": derive_undrs(x),
                      "actual": s.get("undrs", []),
                      "ok": [_parse_undr(l) for l in derive_undrs(x)]
                      == [_parse_undr(l) for l in s.get("undrs", [])]},
            "vfex": {"derived": secs["vfex"],
                     "actual": "VFEX" in s["sections"],
                     "ok": secs["vfex"] == ("VFEX" in s["sections"])},
            "heatpath": {"derived": secs["heatpath"],
                         "actual": "HEATPATH" in s["sections"],
                         "ok": secs["heatpath"]
                         == ("HEATPATH" in s["sections"])},
            "hsol": {"derived": derive_hsol(x),
                     "actual": s.get("hsol"),
                     "ok": True},
        }
        # HSOL 存在性 + 数值回验
        hs = derive_hsol(x)
        if hs is None:
            row["check"]["hsol"]["ok"] = "hsol" not in s
        else:
            want = [f"{int(hs[0]):d}",
                    " ".join(f"{int(v):12d}" for v in hs[1])]
            got = s.get("hsol")
            row["check"]["hsol"]["ok"] = (
                got is not None
                and got[0].split() == want[0].split()
                and got[1].split() == want[1].split())
        table.append(row)

    # 摘要
    keys = list(table[0]["check"]) if table else []
    n_ok = dict.fromkeys(keys, 0)
    n_all = dict.fromkeys(keys, 0)
    print(f"{'sample':<22}{'heat':>4}{'turb':>5}{'tm':>3}{'fs':>3}"
          f"{'diff':>5}{'rad':>4} {'EQUA(d/a)':<19}"
          f"{'CYC(d/a)':<24}{'HSOL':>6}{'VFEX':>6}{'HPT':>5}")
    for row in table:
        if "error" in row:
            print(f"{row['sample']:<22} ERROR {row['error']}")
            continue
        x, s, c = row["xml"], row["s"], row["check"]
        for k in keys:
            if c[k]["ok"]:
                n_ok[k] += 1
            n_all[k] += 1
        h2a = " ".join(s["hdr"][1]) if len(s["hdr"]) > 1 else "?"
        h2d = " ".join(c["hdr2"]["derived"])
        print(f"{row['sample']:<22}{x['heat']:>4}{x['turbulence']:>5}"
              f"{x['turbulence_model'][:2]:>3}"
              f"{x['free_surface'] or '-':>3}{x['diffusion_species']:>5}"
              f"{x['radiation'] or '-':>4} "
              f"{c['equa']['derived']+'/'+c['equa']['actual']:<19}"
              f"{c['cyc']['derived']+'/'+c['cyc']['actual']:<24}"
              f"{str(c['hsol']['ok']):>6}{str(c['vfex']['ok']):>6}"
              f"{str(c['heatpath']['ok']):>5}")
    print("\n== 派生规则命中率 ==")
    for k in keys:
        print(f"  {k}: {n_ok[k]}/{n_all[k]}")

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=1)
        print(f"\nJSON 对照表已写入 {out_json}")


if __name__ == "__main__":
    main()
