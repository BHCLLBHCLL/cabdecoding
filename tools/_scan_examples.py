# Inventory official ST example library against remaining cabdecoding gaps.
from __future__ import annotations

import collections
import io
import os
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre, _first

ROOT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example")


def inventory():
    print("=== top dirs ===")
    print([p.name for p in ROOT.iterdir() if p.is_dir()])
    ext = collections.Counter()
    for p in ROOT.rglob("*"):
        if p.is_file():
            ext[p.suffix.lower() or "(none)"] += 1
    print("=== extensions ===")
    for k, v in ext.most_common(30):
        print(f"  {k}: {v}")
    for k in (".cab", ".s", ".ccel", ".xfem", ".pst", ".nas", ".ifc",
              ".stl", ".x_t", ".ot", ".l", ".f"):
        print(f"  want {k}: {ext[k]}")


def parse_s_header(text: str):
    lines = text.splitlines()
    # after the '           1' marker used by our exporter
    hdr1 = hdr2 = None
    vfde = {}
    sections = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "1" and hdr1 is None and i + 2 < len(lines):
            def ints(line, w=12):
                out = []
                for j in range(0, len(line), w):
                    chunk = line[j:j + w].strip()
                    if chunk:
                        try:
                            out.append(int(float(chunk)))
                        except ValueError:
                            pass
                return out
            a = ints(lines[i + 1])
            b = ints(lines[i + 2])
            if len(a) >= 8 and len(b) >= 6:
                hdr1, hdr2 = a, b
        if s.isalpha() and s.isupper() and len(s) <= 12:
            sections.append(s)
        if s == "VFDE":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "/":
                row = lines[j].strip()
                m = re.match(r"([A-Z0-9]+)\s+(.*)", row)
                if m:
                    vfde[m.group(1)] = m.group(2).strip()
                j += 1
        i += 1
    return hdr1, hdr2, vfde, sections


def scan_s_files():
    print("\n=== .s hdr / VFDE / rare sections ===")
    hdr1_tails = collections.Counter()
    hdr2_tails = collections.Counter()
    leap = collections.Counter()
    em1 = collections.Counter()
    mref = collections.Counter()
    mrcl = collections.Counter()
    rare = collections.Counter()
    n = 0
    n_vfde = 0
    for p in ROOT.rglob("*.s"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        n += 1
        hdr1, hdr2, vfde, secs = parse_s_header(text)
        if hdr1 and len(hdr1) >= 5:
            hdr1_tails[tuple(hdr1[-5:])] += 1
        if hdr2 and len(hdr2) >= 6:
            hdr2_tails[tuple(hdr2[-6:])] += 1
        if vfde:
            n_vfde += 1
            leap[vfde.get("LEAP", "-")] += 1
            em1[vfde.get("EM1", "-")] += 1
            mref[vfde.get("MREF", "-")] += 1
            mrcl[vfde.get("MRCL", "-")] += 1
        for s in secs:
            if s in ("PELTIER_SET", "PELTIER_OUT", "MOVB", "CUTCELL",
                     "HEATPATH", "VFEX", "VFDE", "AIRCON", "TCMDL",
                     "HTRC", "FEM", "XFEM"):
                rare[s] += 1
    print(f"  .s files {n}, with VFDE {n_vfde}")
    print("  hdr1 tails", hdr1_tails.most_common(8))
    print("  hdr2 tails", hdr2_tails.most_common(8))
    print("  LEAP", leap.most_common())
    print("  EM1", em1.most_common())
    print("  MREF", mref.most_common())
    print("  MRCL", mrcl.most_common())
    print("  rare sections", dict(rare))


SPECIAL_KINDS = (
    "peltier", "card_guide", "heat_pipe", "delphi", "multi_resistor",
    "two_resistor", "ac_unit", "air_outlet", "diffuser", "fan",
    "axial_fan", "blower_fan", "pin_fin", "slit_punching", "anemostat",
    "mesh_body",
)
ETC_TAGS = (
    "evaporation", "free_surf", "fusion", "artificial_light", "pcm",
    "phase_change_material", "jos_model", "current", "particle",
    "plant_resistance", "marangoni", "boil_condensation",
)
PART_TAGS_INTEREST = (
    "mesh_fine_divide", "divide", "cutcell", "thermal_node",
    "cooling_part", "heat_release_part", "rjc", "rjb",
)


def scan_cabs():
    print("\n=== .cab XML inventory ===")
    kinds = collections.Counter()
    special_hits = collections.defaultdict(list)
    extra_children = collections.defaultdict(collections.Counter)
    etc = collections.Counter()
    rad_types = collections.Counter()
    rad_kids = collections.Counter()
    fine = []
    attr_vals = collections.Counter()
    has_cs = 0
    fem_kinds = collections.Counter()
    n_ok = n_fail = 0
    for p in ROOT.rglob("*.cab"):
        try:
            arch = CabArchive.parse(p.read_bytes())
            members = {m.name: m.data for m in arch.fill_member_data()}
            xml_name = next(n for n in members
                            if n.endswith(".xml") and not n.startswith("_"))
            model = StpreModel(parse_stpre(members[xml_name]))
        except Exception as exc:
            n_fail += 1
            continue
        n_ok += 1
        if _first(model.root, "coordinate_systems") is not None:
            has_cs += 1
        aset = model.root.find("analysis_set")
        rad = aset.find("radiation") if aset is not None else None
        if rad is not None:
            rad_types[rad.attrib.get("type", "")] += 1
            for c in list(rad):
                rad_kids[c.tag] += 1
        aet = _first(model.root, "analysis_etc")
        if aet is not None:
            for c in list(aet):
                etc[c.tag] += 1
        for part in model.parts():
            kinds[part.kind] += 1
            attr_vals[(part.attribute or "").strip().lower()] += 1
            if part.mesh_fine_divide:
                fine.append((str(p.relative_to(ROOT)), part.name,
                             part.kind, part.mesh_fine_divide))
            if part.kind in SPECIAL_KINDS:
                special_hits[part.kind].append(str(p.relative_to(ROOT)))
                kids = {c.tag for c in list(part.elem)}
                for t in kids:
                    extra_children[part.kind][t] += 1
        for mname, data in members.items():
            if mname.endswith(".xfem") or b"<femodel" in data[:200]:
                try:
                    txt = data.decode("utf-8-sig", errors="replace")
                except Exception:
                    continue
                for k in re.findall(r'kind="(\d+)"', txt):
                    fem_kinds[k] += 1
    print(f"  cabs parsed {n_ok}, fail {n_fail}")
    print("  kinds", kinds.most_common(25))
    print("  attributes", attr_vals.most_common(15))
    print("  radiation types", dict(rad_types))
    print("  radiation children", rad_kids.most_common())
    print("  analysis_etc", etc.most_common())
    print("  named CS count", has_cs)
    print("  FEM element kinds", dict(fem_kinds))
    print("  mesh_fine_divide samples", len(fine))
    for row in fine[:20]:
        print("   ", row)
    print("  specialty part files:")
    for k, files in special_hits.items():
        uniq = sorted(set(files))
        print(f"    {k}: {len(uniq)} cabs, children {extra_children[k].most_common(18)}")
        for f in uniq[:6]:
            print(f"      {f}")


def scan_ccel_attr():
    print("\n=== .ccel ATTR values ===")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import ccel
    attrs = collections.Counter()
    types = collections.Counter()
    n = 0
    for p in ROOT.rglob("*.ccel"):
        try:
            parts, _a, _f = ccel.read_ccel_doc(p.read_bytes())
        except Exception as exc:
            print("  fail", p.name, exc)
            continue
        n += 1
        for part in parts:
            attrs[part.attr] += 1
            types[part.type_str] += 1
    print(f"  ccel files {n}")
    print("  ATTR", dict(attrs))
    print("  TYPE", dict(types))


if __name__ == "__main__":
    inventory()
    scan_s_files()
    scan_cabs()
    scan_ccel_attr()
