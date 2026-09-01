# -*- coding: utf-8 -*-
"""F6/D10: live COM probe for FEM element kinds (shell / hex / tet).

The .xfem writer only knew kind=4 (4-node tetra from solid bodies); the
shell and hex kind values had no evidence.  This probe drives STpre over
COM, converts different source geometries (solid cuboid, panel/sheet) to
FEM and records the ``<e ... kind="?">`` values written into .xfem.

Usage:  python tools/probe_fem_kinds.py [--json data/fem_kind_probe.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _read_xfem(cab_path: Path):
    """Return {model_name: [kinds...]} from the cab's .xfem member."""
    from cab_container import CabArchive
    arch = CabArchive.parse(cab_path.read_bytes())
    arch.fill_member_data()
    data = next((m.data for m in arch.members if m.name.endswith(".xfem")),
                None)
    if data is None:
        return None
    import re
    text = data.decode("utf-8-sig", "replace")
    out = {}
    for mdl in re.finditer(r'<model name="([^"]+)"[^>]*>(.*?)</model>',
                           text, re.S):
        name, body = mdl.group(1), mdl.group(2)
        kinds = [int(k) for k in re.findall(r'<e [^>]*kind="(\d+)"', body)]
        nodes = re.findall(r'<e [^>]*kind="\d+"[^>]*>([^<]*)</e>', body)
        sizes = {len(n.strip().split(",")) for n in nodes if n.strip()}
        out[name] = {"kinds": sorted(set(kinds)),
                     "n_elements": len(kinds),
                     "nodes_per_element": sorted(sizes)}
    return out


def _build_case(name: str, creator, args, *, length=2.0, scale="F",
                edge="T") -> dict:
    """Run one conversion case; returns a record (never raises)."""
    rec = {"case": name, "creator": creator, "args": list(args)}
    try:
        import cab_stpre_api
        from cab_container import CabArchive
        from cabxml import StpreModel, new_stpre_bytes, parse_stpre
        tmp = Path(tempfile.mkdtemp(prefix="fem_probe_"))
        model = StpreModel(parse_stpre(new_stpre_bytes("T")))
        model.ensure_domain(base=(0.0, 0.0, 0.0),
                            size=(50.0, 50.0, 50.0))
        src = tmp / "in.cab"
        # build_relay_cab needs an archive for the property member
        archive = CabArchive.parse(
            (Path(__file__).resolve().parents[1] / "tests" / "ex4_e.cab")
            .read_bytes())
        archive.fill_member_data()
        if not cab_stpre_api.build_relay_cab(model, archive, src):
            rec["error"] = "relay build failed"
            return rec
        session = cab_stpre_api.STpreSession()
        out = tmp / "out.cab"
        try:
            if not session.ensure_open(src):
                rec["error"] = "open failed"
                return rec
            doc_wrap = session.doc
            obj = doc_wrap.call(creator, *args)
            if obj is None:
                rec["error"] = f"{creator} returned None"
                return rec
            part = session.model(args[0])
            if part is None or part.raw is None:
                rec["error"] = "model lookup failed"
                return rec
            fem = part.CreateFEM(length, scale, edge)
            rec["fem_returned"] = None if fem is None else str(fem)
            if not session.save(out):
                rec["error"] = "save failed"
                return rec
        finally:
            session.close()
        rec["xfem"] = _read_xfem(out)
        try:
            from cabxml import StpreModel, parse_stpre
            oarch = CabArchive.parse(out.read_bytes())
            oarch.fill_member_data()
            oxml = next(m.data for m in oarch.members
                        if m.name.endswith(".xml")
                        and not m.name.startswith("_"))
            rec["fem_parts"] = StpreModel(
                parse_stpre(oxml)).fem_parts()
        except Exception as exc:
            rec["fem_parts_error"] = f"{type(exc).__name__}: {exc}" 
    except Exception as exc:  # probe: record and continue
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/fem_kind_probe.json")
    args = ap.parse_args()

    cases = [
        _build_case("solid_cuboid", "CreateCubeModel",
                    ("FemBox", 0.0, 0.0, 0.0, 10.0, 10.0, 10.0)),
        # VB manual sample: CreatePanelModel(name, bx,by,bz, sx,sy,sz, mode)
        _build_case("panel", "CreatePanelModel",
                    ("FemPanel", 5.0, 5.0, 5.0, 10.0, 10.0, 0.0, "a")),
        _build_case("quad_panel", "CreateQuadPanelModel",
                    ("FemQuad", 5.0, 5.0, 5.0, 10.0, 10.0, 0.0, "a")),
        _build_case("cylinder", "CreateCylinderModel",
                    ("FemCyl", 5.0, 5.0, 5.0, 3.0, 10.0, "z")),
        _build_case("hexahedron", "CreateHexahedronModel",
                    ("FemHex", 0.0, 0.0, 0.0, 10.0, 10.0, 10.0)),
        _build_case("solid_fine", "CreateCubeModel",
                    ("FemBoxFine", 0.0, 0.0, 0.0, 10.0, 10.0, 10.0),
                    length=1.0),
    ]
    out = {"cases": cases}
    dest = Path(args.json)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    for c in cases:
        print(c["case"], "->", c.get("xfem") or c.get("error"))
    print("written:", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
