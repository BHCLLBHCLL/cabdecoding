#!/usr/bin/env python3
"""Command-line tool for Cradle scSTREAM Pre .cab project files.

Usage:
    python cab_parser.py file.cab                 summary
    python cab_parser.py file.cab --extract DIR   extract members
    python cab_parser.py file.cab --rebuild OUT   rebuild archive + verify
    python cab_parser.py file.cab --json          machine readable summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import cab_container


def _fmt_size(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.2f} MiB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.2f} KiB"
    return f"{n} B"


def _xml_head(payload: bytes) -> list[str]:
    text = payload.decode("utf-8", "replace")
    lines = []
    for line in text.splitlines()[:8]:
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if stripped.startswith("<") and not stripped.startswith("<?"):
            break
    return lines


def _xt_head(payload: bytes) -> list[str]:
    lines = []
    for line in payload.decode("latin-1", "replace").splitlines()[:18]:
        lines.append(line.rstrip())
    return lines


def _content_summary(name: str, payload: bytes) -> dict:
    low = name.lower()
    if low.endswith(".xml"):
        return {"head": _xml_head(payload)}
    if low.endswith(".x_t"):
        return {"head": _xt_head(payload)}
    return {}


def summarize(arch: cab_container.CabArchive, out) -> None:
    members = arch.fill_member_data()
    print("== MSCF cabinet ==")
    print(
        f"signature=MSCF  version={arch.version_minor}.{arch.version_major}  "
        f"folders={len(arch.folders)}  files={len(arch.members)}  "
        f"setID={arch.set_id}  flags={arch.flags:#x}"
    )
    for i, folder in enumerate(arch.folders):
        print(
            f"folder[{i}] coffCabStart={folder.coff_cab_start}  "
            f"cCFData={folder.c_cfdata}  type={folder.type_compress} "
            f"(MSZIP)"
        )
    print()
    print("== members ==")
    for m, member in zip(members, arch.members):
        print(
            f"{member.name:<28} {_fmt_size(member.cb_file):>10}  "
            f"uoff={member.uoff_folder_start}  md5={hashlib.md5(m.data).hexdigest()}"
        )
    print()
    for m in members:
        print(f"-- {m.name} --")
        for line in _content_summary(m.name, m.data).get("head", []):
            print(f"   {line}")
        print()


def summarize_json(arch: cab_container.CabArchive) -> dict:
    members = arch.fill_member_data()
    return {
        "signature": "MSCF",
        "version": f"{arch.version_minor}.{arch.version_major}",
        "set_id": arch.set_id,
        "flags": arch.flags,
        "folders": [
            {
                "coff_cab_start": f.coff_cab_start,
                "c_cfdata": f.c_cfdata,
                "type_compress": f.type_compress,
            }
            for f in arch.folders
        ],
        "members": [
            {
                "name": m.name,
                "size": m.cb_file,
                "uoff_folder_start": m.uoff_folder_start,
                "md5": hashlib.md5(m.data).hexdigest(),
                "content": _content_summary(m.name, m.data),
            }
            for m in members
        ],
    }


def extract_members(arch: cab_container.CabArchive, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for m in arch.fill_member_data():
        path = os.path.join(out_dir, m.name)
        with open(path, "wb") as fh:
            fh.write(m.data)
        print(f"extracted {path} ({_fmt_size(m.cb_file)})")


def rebuild_and_verify(arch: cab_container.CabArchive, out_path: str) -> bool:
    arch.fill_member_data()
    original = arch.to_bytes(preserve_source_blocks=True)
    with open(out_path, "wb") as fh:
        fh.write(original)
    re_arch = cab_container.CabArchive.parse(original)
    ok = True
    for m, rm in zip(arch.members, re_arch.extract_members()):
        same = m.data == rm.data
        ok &= same
        print(
            f"{'OK ' if same else 'DIFF'} {m.name:<28} "
            f"{hashlib.md5(m.data).hexdigest()}"
        )
    print(f"archive byte-identical: {original == open(out_path, 'rb').read()}")
    print(f"round-trip members identical: {ok}")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cradle scSTREAM Pre .cab tool")
    ap.add_argument("cab", help="path to .cab project file")
    ap.add_argument("--extract", metavar="DIR", help="extract members into DIR")
    ap.add_argument("--rebuild", metavar="OUT", help="rebuild archive to OUT and verify")
    ap.add_argument("--json", action="store_true", help="machine readable summary")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.cab):
        print(f"error: no such file: {args.cab}", file=sys.stderr)
        return 2
    try:
        arch = cab_container.read_cab(args.cab)
    except cab_container.CabFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.extract:
        extract_members(arch, args.extract)
    if args.rebuild:
        ok = rebuild_and_verify(arch, args.rebuild)
        if not ok:
            return 1
    if args.json:
        print(json.dumps(summarize_json(arch), ensure_ascii=False, indent=2))
    if not (args.extract or args.rebuild or args.json):
        summarize(arch, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
