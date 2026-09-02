# -*- coding: utf-8 -*-
"""G7: byte-level section verification against official samples.

For each official cab whose .s contains one of the F6/G1 sections, run
build_sdat and extract the matching block from our output and the
official file, then compare byte-for-byte.  This is the strongest
evidence that the emitted sections are correct.

Usage: python tools/verify_sections_official.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CORPUS = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example\Exercise\Function")

# (sample dir, section name)
CASES = [
    ("exA05-2", "HUMW_REGION"),
    ("exA07-3", "PCLE_CREATE"),
    ("exA07-3", "ES_FIELD_BC"),
    ("exA07-3", "ES_FIELD"),
    ("exA07-3", "PCLE_HANDLING"),
    ("exA07-4", "LSOL_FORCE_MODEL"),
    ("exA07-4", "LSOL_OPTION"),
    ("exA07-4", "LSOL_TIME_STEP"),
    ("exA07-4", "LSOL_FORCE_IP"),
    ("exA15-6", "SURF_POROUS"),
    ("exA18-2", "FLUX_SUM"),
    ("exA28-1", "TOPOPT_REGION"),
    ("exA09-4", "SUFS_REGION"),
    ("exA09-4", "MOVB_CONTROL"),
    ("exA09-4", "DYNA_MOTION"),
]


def extract_block(lines, cmd):
    """Extract a section block starting at cmd, ending at the matching /."""
    start = None
    for i, l in enumerate(lines):
        if l.rstrip() == cmd:
            start = i
            break
    if start is None:
        return None
    depth = 0
    for j in range(start, len(lines)):
        stripped = lines[j].rstrip()
        if stripped == "/":
            if depth == 0:
                return lines[start:j + 1]
            depth -= 1
        elif stripped.endswith(" /") or stripped == cmd:
            depth += 1
    return lines[start:]


def main() -> int:
    from cab_container import CabArchive
    from s_export import build_sdat
    from cabxml import PropertyModel, StpreModel, parse_property, \
        parse_stpre
    results = []
    for sample_dir, cmd in CASES:
        d = CORPUS / sample_dir
        cab_path = next(iter(sorted(d.glob("*step2*.cab")) or d.glob("*.cab")), None)
        s_path = next(iter(d.glob("*.s")), None)
        if cab_path is None or s_path is None:
            results.append({"section": cmd, "sample": sample_dir,
                            "status": "file-not-found"})
            continue
        try:
            arch = CabArchive.parse(cab_path.read_bytes())
            arch.fill_member_data()
            xml_data = next(m.data for m in arch.members
                            if m.name.endswith(".xml")
                            and not m.name.startswith("_"))
            prop_data = next((m.data for m in arch.members
                              if "_property" in m.name), None)
            model = StpreModel(parse_stpre(xml_data))
            props = PropertyModel(parse_property(prop_data)) \
                if prop_data else PropertyModel(parse_property(
                    new_property_bytes()))
            our_s = build_sdat(model, props)
            official_s = s_path.read_text(encoding="utf-8",
                                          errors="replace")
            our_block = extract_block(our_s.split("\r\n"), cmd)
            off_block = extract_block(official_s.splitlines(), cmd)
            if our_block is None and off_block is None:
                results.append({"section": cmd, "sample": sample_dir,
                                "status": "both-absent"})
            elif our_block is None or off_block is None:
                results.append({"section": cmd, "sample": sample_dir,
                                "status": "one-absent",
                                "ours": our_block is not None,
                                "official": off_block is not None})
            elif our_block == off_block:
                results.append({"section": cmd, "sample": sample_dir,
                                "status": "match", "lines": len(our_block)})
            else:
                diff_lines = [(a, b) for a, b in zip(our_block, off_block)
                              if a != b]
                results.append({"section": cmd, "sample": sample_dir,
                                "status": "diff",
                                "our_lines": len(our_block),
                                "official_lines": len(off_block),
                                "first_diffs": [
                                    {"ours": a, "official": b}
                                    for a, b in diff_lines[:4]]})
        except Exception as exc:
            results.append({"section": cmd, "sample": sample_dir,
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}"})
    for r in results:
        s = r["status"]
        extra = ""
        if s == "match":
            extra = f" ({r['lines']} lines)"
        elif s == "diff":
            extra = f" (ours={r['our_lines']} official={r['official_lines']})"
        elif s == "error":
            extra = f" {r.get('error', '')[:70]}"
        print(f"  {r['section']:22s} {r['sample']:30s} {s}{extra}")
    out = Path(__file__).parent / ".." / "data" / "g7_section_verify.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("written:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
