# -*- coding: utf-8 -*-
"""F6/G6: D9 second campaign — no-object classes + sandbox destructive.

Acquisition paths for the four no-object classes:
  Sketch    <- doc.SetMode("sketch") + doc.GetSketcher()
  MeshBlock <- mesher.GetBlock("root")
  Property  <- doc.GetPropertyEntity / GetPropertyGroup
  Table     <- doc.GetTable

Destructive sandbox: Save/SaveAs/UpdateAll run against a *temp copy* of
the relay cab (never the source); results recorded separately.

Usage: python tools/probe_com_b2.py [--json data/com_b_probe2.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/com_b_probe2.json")
    args = ap.parse_args()

    import cab_stpre_api as api
    root = Path(__file__).resolve().parents[1]
    src = root / "tests" / "ex4_e.cab"
    session = api.STpreSession()
    out = {"classes": {}}
    if not session.ensure_open(str(src)):
        print("open failed:", getattr(api, "last_error", None))
        return 1

    def probe_class(vb, obj, members):
        rows = []
        for member in members:
            try:
                target = getattr(obj, member)
                value = target() if callable(target) else target
                rows.append({"member": member, "status": "ok",
                             "value": repr(value)[:100]})
            except Exception as exc:
                rows.append({"member": member, "status": "error",
                             "error": f"{type(exc).__name__}: "
                                      f"{str(exc)[:100]}"})
        out["classes"][vb] = rows

    try:
        doc = session.doc
        model = session.model("lower_cover_01")
        # acquisition
        acq = {}
        try:
            doc.call("SetMode", "sketch")
            acq["sketch_mode"] = True
        except Exception as exc:
            acq["sketch_mode"] = f"{type(exc).__name__}: {exc}"
        for name, getter in (("Sketch", "GetSketcher"),
                             ("Property", "GetPropertyEntity"),
                             ("Property", "GetPropertyGroup"),
                             ("Table", "GetTable")):
            try:
                fn = getattr(doc, getter, None)
                acq[f"{name}:{getter}"] = "ok" if fn() is not None else "None"
            except Exception as exc:
                acq[f"{name}:{getter}"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        try:
            mesher = session._mesher
            blk = api._invoke(mesher, "GetBlock", "root")
            acq["MeshBlock:GetBlock(root)"] = "ok" if blk else "None"
        except Exception as exc:
            acq["MeshBlock:GetBlock(root)"] = \
                f"{type(exc).__name__}: {str(exc)[:80]}"
        out["acquisition"] = acq

        # probe with live objects
        sketches = {}
        for name in ("Sketch", "MeshBlock", "Property", "Table"):
            obj = None
            try:
                if name == "Sketch":
                    obj = doc.call("GetSketcher")
                elif name == "MeshBlock":
                    obj = api._invoke(session._mesher, "GetBlock", "root")
                elif name == "Property":
                    obj = doc.call("GetPropertyEntity")
                elif name == "Table":
                    obj = doc.call("GetTable")
            except Exception:
                pass
            if obj is not None:
                sketches[name] = obj
        for vb, obj in sketches.items():
            members = sorted(set(api.API_CATALOG.get(vb, [])))
            probe_class(vb, obj, members)

        # destructive sandbox: Save on a temp copy
        sandbox = Path(tempfile.mkdtemp(prefix="com_sandbox_")) / "sb.cab"
        shutil.copy2(str(src), str(sandbox))
        if session.ensure_open(str(sandbox)):
            sandbox_rows = []
            for member, fn in (("Save", lambda: session.save(sandbox)),
                               ("UpdateAll",
                                lambda: doc.call("UpdateAll"))):
                try:
                    fn()
                    sandbox_rows.append({"member": member,
                                         "status": "ok"})
                except Exception as exc:
                    sandbox_rows.append({"member": member,
                                         "status": "error",
                                         "error": str(exc)[:100]})
            out["sandbox"] = sandbox_rows
    finally:
        session.close()

    dest = Path(args.json)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    for vb, rows in out.get("classes", {}).items():
        ok = sum(1 for r in rows if r.get("status") == "ok")
        err = sum(1 for r in rows if r.get("status") == "error")
        print(f"{vb:14s} ok={ok} err={err}")
    if "sandbox" in out:
        print("sandbox:", [(r["member"], r["status"])
                           for r in out["sandbox"]])
    print("acquisition:", out.get("acquisition"))
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
