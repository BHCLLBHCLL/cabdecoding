# Follow-up: hdr exceptions, CBODY, VB COM surface, leftover kinds.
from __future__ import annotations

import collections
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre, _first

ROOT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example")


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


def parse_s_header(text: str):
    lines = text.splitlines()
    hdr1 = hdr2 = None
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "1" and hdr1 is None and i + 2 < len(lines):
            a = ints(lines[i + 1])
            b = ints(lines[i + 2])
            if len(a) >= 8 and len(b) >= 6:
                hdr1, hdr2 = a, b
                break
        i += 1
    return hdr1, hdr2, lines


def xml_hints(cab_path: Path):
    hints = {}
    try:
        arch = CabArchive.parse(cab_path.read_bytes())
        members = {m.name: m.data for m in arch.fill_member_data()}
        xml_name = next(n for n in members
                        if n.endswith(".xml") and not n.startswith("_"))
        model = StpreModel(parse_stpre(members[xml_name]))
    except Exception as exc:
        return {"err": str(exc)}
    aset = model.root.find("analysis_set")
    rad = aset.find("radiation") if aset is not None else None
    if rad is not None:
        hints["rad_type"] = rad.attrib.get("type", "")
        for tag in ("max_particle", "max_group_num", "parts_group_num",
                    "calc_cycle", "space_cycle", "output_cycle",
                    "max_reflection", "smrt_rays"):
            el = rad.find(tag)
            if el is not None and (el.text or "").strip():
                hints[tag] = el.text.strip()
    if aset is not None:
        for tag in ("turbulence_model", "restart", "multi_block",
                    "block_num", "transient", "cycle"):
            el = aset.find(tag)
            if el is not None and (el.text or "").strip():
                hints[tag] = el.text.strip()
    aet = _first(model.root, "analysis_etc")
    if aet is not None:
        hints["etc"] = ",".join(c.tag for c in list(aet))
    hints["n_parts"] = len(list(model.parts()))
    hints["kinds"] = sorted({p.kind for p in model.parts()})
    hints["cut"] = sum(1 for p in model.parts() if "cut" in (p.attribute or "").lower()
                       or (getattr(p, "cutcell", None)))
    # dump a few unique analysis_set children
    if aset is not None:
        hints["aset_kids"] = ",".join(sorted({c.tag for c in list(aset)}))
    return hints


def find_cab_for_s(s_path: Path):
    cands = list(s_path.parent.glob(s_path.stem + ".cab"))
    if cands:
        return cands[0]
    # sometimes _e suffix
    alt = s_path.parent / (s_path.stem.replace("_e", "") + ".cab")
    if alt.exists():
        return alt
    return None


def scan_hdr_exceptions():
    print("=== hdr exceptions ===")
    n_parse_fail = 0
    for p in sorted(ROOT.rglob("*.s")):
        text = p.read_text(encoding="utf-8", errors="replace")
        hdr1, hdr2, _ = parse_s_header(text)
        if hdr1 is None:
            n_parse_fail += 1
            # show first 40 non-empty lines for a few
            if n_parse_fail <= 3:
                print("  PARSE FAIL", p.relative_to(ROOT))
                nonempty = [ln for ln in text.splitlines() if ln.strip()][:25]
                for ln in nonempty:
                    print("   |", ln[:80])
            continue
        t1 = tuple(hdr1[-5:])
        t2 = tuple(hdr2[-6:]) if hdr2 and len(hdr2) >= 6 else None
        if t1 != (1, 1, 0, 0, 0) or t2 != (0, 0, 0, 0, 0, 0):
            cab = find_cab_for_s(p)
            hints = xml_hints(cab) if cab else {"no_cab": True}
            rel = str(p.relative_to(ROOT))
            print(f"\n  {rel}")
            print(f"    hdr1={hdr1} tail={t1}")
            print(f"    hdr2={hdr2} tail={t2}")
            print(f"    xml={hints}")
    print(f"\n  parse_fail={n_parse_fail}")


def scan_cbody():
    print("\n=== CBODY ccel ===")
    import ccel
    for p in ROOT.rglob("*.ccel"):
        parts, _a, _f = ccel.read_ccel_doc(p.read_bytes())
        for part in parts:
            if part.attr == "CBODY":
                print(" ", p.relative_to(ROOT), part.name, part.type_str, part.attr)


def scan_kinds():
    print("\n=== uncommon kinds / attributes ===")
    kinds = collections.Counter()
    attrs = collections.Counter()
    files_by_kind = collections.defaultdict(set)
    for p in ROOT.rglob("*.cab"):
        arch = CabArchive.parse(p.read_bytes())
        members = {m.name: m.data for m in arch.fill_member_data()}
        xml_name = next(n for n in members
                        if n.endswith(".xml") and not n.startswith("_"))
        model = StpreModel(parse_stpre(members[xml_name]))
        for part in model.parts():
            kinds[part.kind] += 1
            attrs[part.attribute] += 1
            if part.kind not in ("cube", "body", "panel", "point", "hexa"):
                files_by_kind[part.kind].add(str(p.relative_to(ROOT)))
    print("  all kinds", kinds)
    print("  all attrs", attrs)
    for k, files in sorted(files_by_kind.items()):
        print(f"  {k}: {sorted(files)[:8]}")


def scan_vb_stpre():
    print("\n=== VB STpre method calls ===")
    vb_root = ROOT / "VB_Samples" / "STpre"
    methods = collections.Counter()
    for p in vb_root.rglob("*"):
        if p.suffix.lower() not in (".vb", ".vbs"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\.(Get\w+|Set\w+|Create\w+|Add\w+|Open\w+|Save\w+|Import\w+|Export\w+|Delete\w+|Copy\w+|Move\w+|Make\w+|Run\w+|Calc\w+|Mesh\w+|Grid\w+)\b", text):
            methods[m.group(1)] += 1
    print("  top methods:")
    for k, v in methods.most_common(60):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    scan_hdr_exceptions()
    scan_cbody()
    scan_kinds()
    scan_vb_stpre()
