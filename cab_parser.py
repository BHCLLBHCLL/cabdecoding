"""P0 CLI: summarize / extract / rebuild a Cradle scSTREAM `.cab` file."""

from __future__ import annotations

import argparse
import json
import os
import sys

from cab_container import CabArchive


def _print_summary(arch: CabArchive) -> None:
    print(f"archive: {arch._raw and len(arch._raw) or 0} B  "
          f"version {arch.version_minor}.{arch.version_major}  "
          f"set_id {arch.set_id}")
    for i, folder in enumerate(arch.folders):
        print(f"folder[{i}]: coff={folder.coff_cab_start} "
              f"blocks={folder.c_cfdata} type={folder.type_compress}")
    for m in arch.members:
        data = m.data or b""
        head = ""
        if data[:3] == b"\xef\xbb\xbf":
            head = "XML"
        elif data[:2] == b"**":
            head = "parasolid"
        print(f"  {m.name:<24} {m.cb_file:>8} B  off={m.uoff_folder_start:>8}"
              f"  {head}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cab", help="path to .cab project file")
    ap.add_argument("--json", action="store_true", help="print machine JSON")
    ap.add_argument("--extract", metavar="DIR", help="extract members into DIR")
    ap.add_argument("--rebuild", metavar="OUT",
                    help="write a byte-identical rebuild to OUT")
    args = ap.parse_args(argv)

    with open(args.cab, "rb") as fh:
        raw = fh.read()
    arch = CabArchive.parse(raw)
    arch.fill_member_data()

    if args.json:
        print(json.dumps({
            "file": args.cab,
            "size": len(raw),
            **arch.summary(),
        }, ensure_ascii=False, indent=1))
    else:
        _print_summary(arch)

    if args.extract:
        os.makedirs(args.extract, exist_ok=True)
        for m in arch.members:
            with open(os.path.join(args.extract, m.name), "wb") as fh:
                fh.write(m.data or b"")
            print(f"extracted {m.name} ({m.cb_file} B)")

    if args.rebuild:
        rebuilt = arch.to_bytes(preserve_source_blocks=True)
        with open(args.rebuild, "wb") as fh:
            fh.write(rebuilt)
        print(f"rebuilt {args.rebuild} ({len(rebuilt)} B, "
              f"{'byte-identical' if rebuilt == raw else 'DIFFERS'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
