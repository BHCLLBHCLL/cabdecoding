# -*- coding: utf-8 -*-
"""F6/G6/R2: D9 third campaign — parameterised member calls.

The first campaign's 45 errors are mostly missing-argument TypeErrors.
This probe retries the parameterised members with sensible names drawn
from the live project (parts, materials, expressions) and records the
outcomes.  Also runs the destructive sandbox batch (SaveAs/UpdateAll/
ClearDocument on a temp copy).

Usage: python tools/probe_com_b3.py [--json data/com_b_probe3.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# member -> candidate arguments (first argument name from the VB manual)
ARG_CANDIDATES = {
    "GetAnalysisType": ["flow"],
    "GetExpression": ["expr1"],
    "GetModel": ["lower_cover_01"],
    "GetMoveBodyOption": ["lower_cover_01"],
    "GetPhaseParam": ["water"],
    "GetPropertyEntity": ["air(incompressible/20C)"],
    "GetScript": ["script1"],
    "GetSolidMeltParam": ["water"],
    "GetSolverParam": ["flow"],
    "GetTable": ["air(incompressible/20C)"],
    "GetUnit": ["length"],
    "GetEvaporationParam": ["water"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/com_b_probe3.json")
    opts = ap.parse_args()

    import cab_stpre_api as api
    root = Path(__file__).resolve().parents[1]
    src = root / "tests" / "ex4_e.cab"
    session = api.STpreSession()
    out = {"param_calls": [], "sandbox": []}
    if not session.ensure_open(str(src)):
        print("open failed:", getattr(api, "last_error", None))
        return 1
    try:
        doc = session.doc
        for member, args_list in ARG_CANDIDATES.items():
            fn = getattr(doc, member, None)
            if fn is None:
                continue
            for args in args_list:
                try:
                    r = fn(args)
                    out["param_calls"].append(
                        {"member": member, "args": args, "status": "ok",
                         "value": repr(r)[:90]})
                    break
                except Exception as exc:
                    last = {"member": member, "args": args,
                            "status": "error",
                            "error": f"{type(exc).__name__}: "
                                     f"{str(exc)[:90]}"}
            else:
                out["param_calls"].append(last)

        # destructive sandbox batch on temp copies
        sandbox = Path(tempfile.mkdtemp(prefix="com_sb3_"))
        for name in ("SaveAs", "ClearDocument"):
            sb = sandbox / f"{name}.cab"
            shutil.copy2(str(src), str(sb))
            if not session.ensure_open(str(sb)):
                out["sandbox"].append({"member": name,
                                       "status": "open-failed"})
                continue
            try:
                if name == "SaveAs":
                    dst = sandbox / f"{name}_out.cab"
                    session.save(dst)
                    out["sandbox"].append({"member": name,
                                           "status": "ok",
                                           "exists": dst.exists()})
                else:  # ClearDocument on the sandbox copy
                    try:
                        doc.call("ClearDocument")
                        out["sandbox"].append({"member": name,
                                               "status": "ok"})
                    except Exception as exc:
                        out["sandbox"].append(
                            {"member": name, "status": "error",
                             "error": str(exc)[:90]})
            except Exception as exc:
                out["sandbox"].append({"member": name, "status": "error",
                                       "error": str(exc)[:90]})
    finally:
        session.close()

    dest = Path(opts.json) if hasattr(args, 'json') else Path('data/com_b_probe3.json')
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    ok = sum(1 for r in out["param_calls"] if r["status"] == "ok")
    err = sum(1 for r in out["param_calls"] if r["status"] == "error")
    print(f"param calls: ok={ok} err={err} / {len(out['param_calls'])}")
    print("sandbox:", [(r["member"], r["status"]) for r in out["sandbox"]])
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
