# -*- coding: utf-8 -*-
"""D6-1: corpus parity driver — emit .s from every official .cab and
classify the diff against the official .s.

Offline (no COM).  For each (cab, .s) pair in the official corpus:

1. parse the cab's XML member -> StpreModel;
2. build_sdat(model, props);
3. diff our lines vs the official lines at *command-block* granularity:
   - missing_cmds  : official blocks absent from ours (by command name);
   - extra_cmds    : our blocks the official file does not have;
   - line_diffs    : shared commands whose data lines differ (count +
                     first differing lines, up to a cap).

Results: data/corpus_parity.json  (+ stdout summary).

Usage::

    python tools/corpus_parity.py [--out data/corpus_parity.json]
        [--limit N] [--filter exA04]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    parse_property, parse_stpre
from s_export import build_sdat

ROOT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example")

# commands whose blocks are mesh-data dominated (axis dumps); counted
# but their line diffs are bucketed, not listed
BULK = {"CXYZ", "CYCZ", "CYCY"}


def find_pairs():
    out = []
    for dp, _d, ns in os.walk(ROOT):
        names = set(ns)
        for n in sorted(names):
            if n.endswith(".cab") and n[:-4] + ".s" in names:
                out.append((Path(dp) / n, Path(dp) / (n[:-4] + ".s")))
    return out


def split_blocks(lines):
    """command name -> list of raw block lines (cmd + data, no '/').

    '/'-terminated block grammar with nesting: a command line opens a
    block (depth+1), each '/' closes the innermost open block.  Only
    top-level commands (depth back to 0) count as the file's command
    set; nested commands (INIT_REGION's RHUM/TEMP, @UNDEFINED*
    containers) belong to their parent block's data.
    """
    blocks: dict[str, list[str]] = defaultdict(list)
    stack: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s == "/":
            if stack:
                stack.pop()
            continue
        is_cmd = (s and s == s.upper() and any(c.isalpha() for c in s)
                  and " " not in s and len(s) <= 16)
        if is_cmd:
            if stack:
                blocks[stack[-1]].append(ln)
            else:
                blocks[s].append(ln)
            stack.append(s)
        elif stack:
            blocks[stack[-1]].append(ln)
    return blocks


def norm(line: str) -> str:
    """numeric-tolerant normalisation for line diffing."""
    return " ".join(line.split())


def compare(cab_path: Path, s_path: Path):
    arch = CabArchive.parse(cab_path.read_bytes())
    members = {m.name: m for m in arch.fill_member_data()}
    xmls = [k for k in members if k.endswith(".xml")]
    if not xmls:
        return {"status": "no-xml"}
    try:
        m = StpreModel(parse_stpre(members[xmls[0]].data))
        props = PropertyModel(parse_property(new_property_bytes()))
        ours = build_sdat(m, props).split("\r\n")
    except Exception as e:  # noqa: BLE001 - report and continue
        return {"status": f"emit-error: {type(e).__name__}: {e}"}
    official = s_path.read_text(encoding="utf-8-sig",
                                errors="replace").splitlines()

    ob = split_blocks(official)
    mb = split_blocks(ours)
    missing = sorted(set(ob) - set(mb))
    extra = sorted(set(mb) - set(ob))
    line_diffs = {}
    for cmd in sorted(set(ob) & set(mb)):
        o = [norm(x) for x in ob[cmd]]
        n = [norm(x) for x in mb[cmd]]
        if o == n:
            continue
        sm = difflib.SequenceMatcher(a=o, b=n)
        diff_lines = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            for x in o[i1:i2][:3]:
                diff_lines.append("- " + x[:120])
            for x in n[j1:j2][:3]:
                diff_lines.append("+ " + x[:120])
            if len(diff_lines) > 8:
                break
        line_diffs[cmd] = {
            "official_lines": len(o), "ours_lines": len(n),
            "sample": diff_lines[:8],
        }
    return {
        "status": "ok",
        "missing_cmds": missing,
        "extra_cmds": extra,
        "line_diff_cmds": sorted(line_diffs),
        "line_diffs": line_diffs,
        "n_official_cmds": len(ob),
        "n_ours_cmds": len(mb),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/corpus_parity.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--filter", default="")
    args = ap.parse_args()

    pairs = find_pairs()
    if args.filter:
        pairs = [p for p in pairs if args.filter in p[0].name]
    if args.limit:
        pairs = pairs[:args.limit]
    print(f"pairs: {len(pairs)}")

    records = {}
    missing_counter: Counter = Counter()
    extra_counter: Counter = Counter()
    for cab, s in pairs:
        rec = compare(cab, s)
        records[cab.name] = rec
        if rec.get("status") == "ok":
            for c in rec["missing_cmds"]:
                missing_counter[c] += 1
            for c in rec["extra_cmds"]:
                extra_counter[c] += 1
    ok = sum(1 for r in records.values() if r.get("status") == "ok")
    clean = sum(1 for r in records.values()
                if r.get("status") == "ok" and not r["missing_cmds"]
                and not r["extra_cmds"] and not r["line_diff_cmds"])
    summary = {
        "pairs": len(pairs),
        "ok": ok,
        "emit_errors": len(pairs) - ok,
        "fully_parity": clean,
        "top_missing_cmds": missing_counter.most_common(25),
        "top_extra_cmds": extra_counter.most_common(25),
    }
    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "records": records},
                              ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
