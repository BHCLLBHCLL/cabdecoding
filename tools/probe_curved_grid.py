# -*- coding: utf-8 -*-
"""F6/G3: threshold + axis_plane semantics on a curved part (live COM).

Creates a cylinder (curved surface) over COM, runs ExecuteGrid twice
(threshold=0 vs threshold=2.5), and reads back the mesh axes from the
saved cabs so the native cab_grid thresholds can be compared.

Usage: python tools/probe_curved_grid.py [--json data/grid_curved_probe.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _axes_from_cab(path: Path) -> dict:
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    xml = next(m.data for m in arch.members
               if m.name.endswith(".xml") and not m.name.startswith("_"))
    m = StpreModel(parse_stpre(xml))
    return {ax: [round(v, 6) for v in vals]
            for ax, vals in m.mesh_axes().items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/grid_curved_probe.json")
    args = ap.parse_args()

    import cab_stpre_api as api
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    from cab_parts import cube_tess  # noqa: F401 (import sanity)
    archive = CabArchive.parse(
        (Path(__file__).resolve().parents[1] / "tests" / "ex4_e.cab")
        .read_bytes())
    archive.fill_member_data()

    tmp = Path(tempfile.mkdtemp(prefix="grid_probe_"))
    from cab_grid import GridSpec
    out = {}
    for tag, threshold in (("thr_min", 1e-9), ("thr2_5", 2.5)):
        model = StpreModel(parse_stpre(
            next(m.data for m in archive.members
                 if m.name.endswith(".xml")
                 and not m.name.startswith("_"))))
        model.ensure_domain(base=(0.0, 0.0, 0.0), size=(50.0, 50.0, 50.0))
        src = tmp / f"in_{tag}.cab"
        dst = tmp / f"out_{tag}.cab"
        if not api.build_relay_cab(model, archive, src):
            out[tag] = {"error": "relay failed"}
            continue
        session = api.STpreSession()
        try:
            if not session.ensure_open(str(src)):
                out[tag] = {"error": "open failed"}
                continue
            doc = session.doc
            cyl = doc.call("CreateCylinderModel", "Cyl", 5.0, 5.0, 5.0,
                           3.0, 10.0, "z")
            if cyl is None:
                out[tag] = {"error": "CreateCylinderModel returned None"}
                continue
            spec = GridSpec(
                unit="mm", domain_min=(0.0, 0.0, 0.0),
                domain_max=(50.0, 50.0, 50.0),
                vertex_detection="minmax", method="rough_and_detail",
                standard_length=(2.5, 2.5, 2.5),
                threshold_length=(threshold,) * 3,
                geometric_ratio=(1.2, 1.2, 1.2),
                geometric_ratio_external=(1.2, 1.2, 1.2))
            params = api.build_grid_params(model)
            block_params = api.build_block_params_from_gridspec(spec)
            if not session.grid(params, "detail",
                                block_params=block_params):
                out[tag] = {"error": api.last_error}
                continue
            if not session.save(dst):
                out[tag] = {"error": "save failed"}
                continue
            out[tag] = {"axes": _axes_from_cab(dst)}
        finally:
            session.close()
    dest = Path(args.json)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    for tag, rec in out.items():
        if "axes" in rec:
            print(tag, "x-lines:", len(rec["axes"].get("x", [])))
        else:
            print(tag, "->", rec.get("error"))
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
