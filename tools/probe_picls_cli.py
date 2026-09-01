# -*- coding: utf-8 -*-
"""F6/D11: probe whether PICLS accepts a project-file argument.

PICLS has no documented CLI (Tools_eng only covers the Kicker launcher),
so this probe launches the EXE with a project path under a hard timeout,
observes whether it stays resident (GUI app, like scPOST) or exits, and
always reclaims the process.

Usage: python tools/probe_picls_cli.py [--json data/picls_cli_probe.json]
       [--wait 20]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def find_exe():
    import cab_tools
    for key in ("picls", "PICLS"):
        try:
            hit = cab_tools.find_cradle_tool(key)
            if hit:
                return hit
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/picls_cli_probe.json")
    ap.add_argument("--wait", type=float, default=20.0)
    ap.add_argument("--project", default="tests/ex4_e.cab")
    args = ap.parse_args()

    exe = find_exe()
    rec = {"exe": str(exe) if exe else None,
           "project": args.project,
           "wait_s": args.wait}
    if not exe or not os.path.isfile(exe):
        rec["status"] = "exe-not-found"
        Path(args.json).write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(rec, ensure_ascii=False))
        return 1
    proj = Path(args.project)
    proc = None
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [exe, str(proj)], cwd=str(proj.parent),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rec["pid"] = proc.pid
        try:
            rc = proc.wait(timeout=args.wait)
            rec["status"] = "exited"
            rec["returncode"] = rc
        except subprocess.TimeoutExpired:
            rec["status"] = "still-running"
            rec["elapsed_s"] = round(time.time() - t0, 2)
    except Exception as exc:
        rec["status"] = "launch-error"
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            rec["killed"] = True
    dest = Path(args.json)
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(json.dumps(rec, ensure_ascii=False))
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
