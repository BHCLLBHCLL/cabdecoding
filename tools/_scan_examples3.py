from __future__ import annotations
import io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre, _first
from xml.etree import ElementTree as ET

ROOT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example")

def dump(rel, what):
    p = ROOT / rel
    arch = CabArchive.parse(p.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    xml_name = next(n for n in members if n.endswith(".xml") and not n.startswith("_"))
    root = StpreModel(parse_stpre(members[xml_name])).root
    print("\n====", rel, what)
    if what == "particle":
        el = root.find("analysis_etc/particle")
        if el is None:
            print("  missing")
            return
        print(ET.tostring(el, encoding="unicode")[:2500])
    elif what == "network":
        for part in root.findall(".//parts"):
            if part.attrib.get("type") == "network":
                print(ET.tostring(part, encoding="unicode")[:2000])
    elif what == "fan":
        for part in root.findall(".//parts"):
            if "fan" in part.attrib.get("type", ""):
                print(ET.tostring(part, encoding="unicode")[:1800])
    elif what == "cbody":
        for part in root.findall(".//parts"):
            name = (part.findtext("name") or "").strip()
            if "押し" in name or "extrud" in name.lower() or "push" in name.lower():
                print("NAME", name)
                print(" type", part.attrib.get("type"), "attr", (part.findtext("attribute") or "").strip())
                kids = [(c.tag, (c.text or "").strip()[:80]) for c in list(part)]
                print(" kids", kids)
    elif what == "movb":
        aset = root.find("analysis_set")
        for tag in ("moving_body", "moving_body_file", "moving_body_option"):
            el = aset.find(tag) if aset is not None else None
            print(tag, None if el is None else (el.text or "").strip(), el.attrib if el is not None else "")
        # also count moving parts
        n = 0
        for part in root.findall(".//parts"):
            mb = part.find("moving") or part.find("motion") or part.find("moving_body")
            if mb is not None:
                n += 1
                print(" part", part.findtext("name"), mb.tag, ET.tostring(mb, encoding="unicode")[:400])
        print("moving parts", n)
    elif what == "fusion":
        el = root.find("analysis_etc/fusion")
        print(ET.tostring(el, encoding="unicode")[:1500] if el is not None else "missing")
    elif what == "loop":
        aset = root.find("analysis_set")
        for tag in ("loop_option", "initial_restart", "calculation"):
            el = aset.find(tag) if aset is not None else None
            print(tag, None if el is None else (el.text or "").strip())

dump(r"Exercise_e\Function\exA07-1\exA07-1_e.cab", "particle")
dump(r"Exercise_e\Function\exA07-6\exA07-6_e.cab", "particle")
dump(r"Exercise_e\Function\exA22-1\exA22-1_e.cab", "network")
dump(r"Exercise_e\Function\exA13-2\exA13-2_e.cab", "fan")
dump(r"Exercise\Function\exA23-1\exA23-1a.cab", "cbody")
dump(r"Exercise_e\Function\exA09-1\exA09-1_e.cab", "movb")
dump(r"Exercise_e\Function\exA09-2\exA09-2_e.cab", "movb")
dump(r"Exercise_e\Function\exA11-1\exA11-1_e.cab", "fusion")
dump(r"Exercise_e\Function\exA05-2\exA05-2a_e.cab", "loop")

def dump_kind(rel, k):
    p = ROOT / rel
    arch = CabArchive.parse(p.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    xml_name = next(n for n in members if n.endswith(".xml") and not n.startswith("_"))
    root = StpreModel(parse_stpre(members[xml_name])).root
    print("\n====", rel, k)
    for part in root.findall(".//parts"):
        if part.attrib.get("type") == k:
            print(ET.tostring(part, encoding="unicode")[:1800])
            break

dump_kind(r"Exercise_e\Function\exA10-1\exA10-1_e.cab", "spin_rectangle")
dump_kind(r"Exercise_e\Function\exA07-5\exA07-5_e.cab", "case_cube")
dump_kind(r"Exercise_e\Function\exA09-1\exA09-1_e.cab", "hexa")
