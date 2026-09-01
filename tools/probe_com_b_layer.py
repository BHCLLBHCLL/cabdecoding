# -*- coding: utf-8 -*-
"""F6/D9: live COM B-layer probe — read-only semantic verification.

For every member of the VB manual catalog (data/com_typelib_members.json
via cab_stpre_api.API_CATALOG) the probe obtains a live wrapped object of
the owning class and attempts a NON-DESTRUCTIVE access:

  * ``Get*/Is*/Has*/Count*`` -> invoked with no arguments;
  * plain attributes (ErrorCode / ErrorString / Visible / UserControl) ->
    read as properties;
  * everything else (Set*, Delete*, Create*, Open/Save/Close/Quit ...) ->
    skipped as destructive or argument-dependent (§22: destructive
    members need an isolated sandbox copy per call).

Usage: python tools/probe_com_b_layer.py [--json data/com_b_probe.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SKIP_PREFIX = ("Set", "Delete", "Create", "Open", "Save", "Close", "Quit",
               "Update", "Write", "Import", "Export", "Execute", "Append",
               "Clear", "Begin", "End", "Init", "Reset", "Apply", "Add",
               "Remove", "Register", "Convert", "Read", "Load")
CALL_PREFIX = ("Get", "Is", "Has", "Find", "Search", "Count", "Check")
ATTRS = ("ErrorCode", "ErrorString", "Visible", "UserControl", "Name",
         "Type", "Count", "Value", "Kind", "Length", "Number")


def classify(member: str) -> str:
    if member in ATTRS:
        return "attr"
    if any(member.startswith(p) for p in SKIP_PREFIX):
        return "skip"
    if any(member.startswith(p) for p in CALL_PREFIX):
        return "call"
    return "skip"


def live_objects(session, model_name):
    """Best-effort live wrapped object per VB class name."""
    objs = {}
    try:
        objs["Application"] = session.application
    except Exception:
        pass
    try:
        objs["Doc"] = session.doc
    except Exception:
        pass
    model = None
    try:
        model = session.model(model_name)
    except Exception:
        pass
    if model is not None:
        objs["Model"] = model
    doc = objs.get("Doc")
    for vb in ("Value", "Property", "Sketch", "Table", "Mesher",
               "AirconModel", "GerberModel", "Femodel"):
        for owner in (doc, model):
            if owner is None:
                continue
            for getter in (f"Get{vb}", vb):
                fn = getattr(owner, getter, None)
                if fn is None:
                    continue
                try:
                    objs[vb] = fn()
                    break
                except Exception:
                    continue
            if vb in objs:
                break
    return objs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/com_b_probe.json")
    ap.add_argument("--classes", default="")
    ap.add_argument("--part", default="lower_cover_01")
    args = ap.parse_args()

    import cab_stpre_api as api
    src = (Path(__file__).resolve().parents[1] / "tests" / "ex4_e.cab")
    session = api.STpreSession()
    if not session.ensure_open(str(src)):
        print("open failed:", getattr(api, "last_error", None))
        return 1
    results = {"part": args.part, "classes": {}}
    t0 = time.time()
    try:
        objs = live_objects(session, args.part)
        targets = list(api._TYPED_BY_VB)
        if args.classes:
            want = set(args.classes.split(","))
            targets = [c for c in targets if c in want and c in objs]
        for vb in targets:
            obj = objs.get(vb)
            rows = []
            for member in sorted(set(api.API_CATALOG.get(vb, []))):
                kind = classify(member)
                if kind == "skip":
                    rows.append({"member": member, "kind": "skip"})
                    continue
                if obj is None:
                    rows.append({"member": member, "kind": kind,
                                 "status": "no-object"})
                    continue
                try:
                    target = getattr(obj, member)
                    value = target() if kind == "call" else target
                    rows.append({"member": member, "kind": kind,
                                 "status": "ok",
                                 "value": repr(value)[:120]})
                except Exception as exc:
                    rows.append({"member": member, "kind": kind,
                                 "status": "error",
                                 "error": f"{type(exc).__name__}: "
                                          f"{str(exc)[:110]}"})
            results["classes"][vb] = rows
    finally:
        session.close()
    results["elapsed_s"] = round(time.time() - t0, 2)
    dest = Path(args.json)
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    tot = {"ok": 0, "error": 0, "skip": 0, "no-object": 0}
    for vb, rows in results["classes"].items():
        summary = {}
        for r in rows:
            key = r.get("status", r["kind"])
            summary[key] = summary.get(key, 0) + 1
            tot[key] = tot.get(key, 0) + 1
        print(f"{vb:14s} {summary}")
    print("TOTAL", {k: v for k, v in tot.items() if v})
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
