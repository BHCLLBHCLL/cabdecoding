# -*- coding: utf-8 -*-
"""D2-1: snapshot representative official <parts> elements per kind.

Walks the official corpus, picks the first cab part for every kind in
``_SPECIAL_PARAM_FIELDS`` (plus a second sample where the schema varies)
and writes each as a standalone XML file under
``tests/fixtures/official_parts/<kind>__<partname>.xml`` so the
fidelity matrix tests stay self-contained (no corpus dependency).

Regenerable: rerunning overwrites the fixtures in place.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre, canonical_part_kind

ROOT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example")
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" \
    / "official_parts"

KINDS = ("peltier", "card_guide", "ac_unit", "diffuser", "heat_pipe",
         "fan", "axial_fan", "blower_fan", "pin_fin", "slit_punching",
         "anemostat", "two_resistor", "delphi", "plate_fin", "panel",
         "sphere", "enclosure")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    written = 0
    for dp, _d, ns in sorted(os.walk(str(ROOT))):
        for n in sorted(ns):
            if not n.endswith(".cab"):
                continue
            p = Path(dp) / n
            try:
                arch = CabArchive.parse(p.read_bytes())
                members = {m.name: m for m in arch.fill_member_data()}
                xmls = [k for k in members if k.endswith(".xml")]
                if not xmls:
                    continue
                model = StpreModel(parse_stpre(members[xmls[0]].data))
            except Exception:
                continue
            for part in model.parts():
                kind = canonical_part_kind(
                    part.elem.attrib.get("type", ""), part.elem)
                if kind not in KINDS:
                    continue
                seen[kind] = seen.get(kind, 0) + 1
                if seen[kind] > 2:      # up to 2 samples per kind
                    continue
                tag = "b" if seen[kind] == 2 else ""
                name = (part.name or kind).strip().replace(" ", "_")
                out = OUT / f"{kind}__{tag}{name}.xml"
                ET.ElementTree(part.elem).write(out, encoding="utf-8",
                                                xml_declaration=False)
                written += 1
    print("written:", written)
    for k in KINDS:
        n = len(list(OUT.glob(f"{k}__*.xml")))
        print(f"  {k}: {n}")


import os  # noqa: E402

if __name__ == "__main__":
    main()
