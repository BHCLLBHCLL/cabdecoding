# -*- coding: utf-8 -*-
"""F6/R2 follow-up: scripted sandbox batch for destructive COM members.

Opens a *temp copy* of the relay cab per batch, invokes the destructive
members from the sandbox subset, records the outcome, and reclaims the
session.  The target list is extensible via --members.

Usage:
  python tools/probe_com_sandbox.py [--json data/com_sandbox.json]
      [--members Save,SaveAs,UpdateAll,ClearDocument,Quit]
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
    ap.add_argument("--json", default="data/com_sandbox.json")
    ap.add_argument("--members", default="Save,SaveAs,UpdateAll")
    args = ap.parse_args()
    members = [m.strip() for m in args.members.split(",") if m.strip()]

    import cab_stpre_api as api
    root = Path(__file__).resolve().parents[1]
    src = root / "tests" / "ex4_e.cab"
    sandbox = Path(tempfile.mkdtemp(prefix="com_sandbox_batch_"))
    results = []
    for member in members:
        work = sandbox / f"{member}.cab"
        shutil.copy2(str(src), str(work))
        session = api.STpreSession()
        rec = {"member": member, "status": "unknown"}
        try:
            if not session.ensure_open(str(work)):
                rec["status"] = "open-failed"
                continue
            app = session.application
            doc = session.doc
            if member == "Save":
                rec["status"] = "ok" if session.save(work) else "save-false"
            elif member == "SaveAs":
                dst = sandbox / f"{member}_out.cab"
                fn = getattr(app, "SaveAs", None) if app else None
                if fn is None:
                    fn = getattr(doc, "SaveAs", None)
                ok = fn(str(dst)) if fn else False
                rec["status"] = ("ok" if (ok or dst.exists())
                                 else "save-false")
            elif member == "UpdateAll":
                fn = getattr(app, "UpdateAll", None) if app else None
                if fn is None:
                    fn = getattr(doc, "UpdateAll", None)
                fn()
                rec["status"] = "ok"
            elif member == "ClearDocument":
                fn = getattr(app, "ClearDocument", None) if app else None
                if fn is None:
                    fn = getattr(doc, "ClearDocument", None)
                fn()
                rec["status"] = "ok"
            elif member == "Quit":
                rec["status"] = "skipped:terminates-session"
        except Exception as exc:
            rec["status"] = "error"
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        finally:
            session.close()
        results.append(rec)
        print(f"  {member:16s} {rec['status']}"
              + (f" ({rec.get('error', '')[:60]})"
                 if rec.get("error") else ""))
    dest = Path(args.json)
    dest.write_text(json.dumps({"results": results}, ensure_ascii=False,
                               indent=2), encoding="utf-8")
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
