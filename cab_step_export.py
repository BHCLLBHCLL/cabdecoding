"""STEP export through three descending branches (P3-3).

scSTREAM Pre exports geometry through Cradle's *licensed* CAD conversion
chain (CADthru / STEPAssistant), whose executables are GUI apps that must
not be invoked headlessly (they hang, see ``cab_occ``).  pskernel has no
``PK_BODY_EXPORT`` (docs/pskernel_exports.txt).  STEP export therefore
falls back through three branches::

    (a) Parasolid ``.x_t`` transmit + a local *headless* CAD CLI
        (FreeCAD ``FreeCADCmd`` etc., configured via ``STPRE_STEP_CLI``);
    (b) pythonocc-core / OCP ``STEPControl_Writer`` (if installed);
    (c) **B-level declaration** — STEP/SAT import is already supported and
        STpre's own STEP export relies on the same licensed chain, so when
        neither (a) nor (b) is available we declare STEP export B-level and
        raise an actionable error instead of writing a broken file.

The exported solid set mirrors the IFC export: every part becomes a
box / cylinder / polygon-prim whose placement matrix (mm) is written into
STEP world coordinates (metres).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

import cab_ifc
import cab_occ

_B_LEVEL_MARK = "B-level"  # stable marker asserted by tests / docs


class StepExportUnavailable(RuntimeError):
    """No STEP-export backend (CAD CLI or OCC) is available."""


class SatExportUnavailable(RuntimeError):
    """No SAT-export backend is available (FMT-4 B-level declaration).

    ACIS SAT has no open-source writer: pythonocc/OCC cannot write SAT at
    all (read-only via STEPControl-style readers), and FreeCAD exposes no
    ACIS export either.  The only branch is a user-supplied headless CLI
    (``STPRE_SAT_CLI``) that converts ``.x_t`` -> ``.sat``; STpre's own SAT
    export goes through the same licensed CADthru chain.
    """


def _candidate_clis() -> list[str]:
    """Candidate headless CAD CLI executables (env override first)."""
    env = os.environ.get("STPRE_STEP_CLI")
    out = [env] if env else []
    out += ["freecadcmd.exe", "freecadcmd", "FreeCADCmd.exe",
            "FreeCADCmd"]
    return [c for c in out if c]


def find_cad_cli() -> str | None:
    """Locate a headless CAD CLI able to convert ``.x_t`` -> STEP."""
    for name in _candidate_clis():
        if os.sep in name and os.path.isfile(name):
            return name
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def step_export_strategy() -> str:
    """Return the best available branch: ``'cli'`` | ``'occ'`` | ``'none'``."""
    if find_cad_cli():
        return "cli"
    if cab_occ.occ_available():
        return "occ"
    return "none"


def _write_xt(archive, tags: list, path) -> None:
    """Write the model's Parasolid ``.x_t`` text to ``path`` (branch a)."""
    if archive is not None:
        for m in archive.members:
            if m.name.endswith(".x_t") and m.data:
                Path(path).write_bytes(m.data)
                return
    if tags:
        import cab_ps_ops
        if cab_ps_ops.available():
            Path(path).write_bytes(cab_ps_ops.transmit_parts(list(tags)))
            return
    raise StepExportUnavailable(
        "STEP export branch (a) needs a .x_t archive member or pskernel "
        "body tags to feed the CAD CLI")


def _run_cli_convert(cli: str, xt: Path, step: Path) -> None:
    """Run a FreeCAD-style headless CAD CLI to convert ``xt`` -> ``step``."""
    script = (
        "import Part, sys\n"
        f"shape = Part.Shape()\n"
        f"shape.read(r'{xt.as_posix()}')\n"
        f"shape.exportStep(r'{step.as_posix()}')\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        script_path = fh.name
    try:
        subprocess.run([cli, script_path], check=True, timeout=600,
                       capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise StepExportUnavailable(
            f"STEP export branch (a): CAD CLI {cli!r} failed: {exc}") \
            from exc
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
    if not Path(step).is_file():
        raise StepExportUnavailable(
            f"STEP export branch (a): CAD CLI {cli!r} produced no output")


def _cli_export_step(cli: str, archive, tags: list, step: Path) -> None:
    """Branch (a): ``.x_t`` intermediate + local headless CAD CLI."""
    with tempfile.TemporaryDirectory(prefix="cabstep_") as td:
        xt = Path(td) / "model.x_t"
        _write_xt(archive, tags, xt)
        _run_cli_convert(cli, xt, step)


def _metre_matrix(base_mm, m) -> np.ndarray:
    """Effective 4x4 placement in metres: translation(base) @ rotation(m)."""
    T = np.eye(4)
    T[:3, :3] = np.asarray(m, dtype=np.float64)[:3, :3]
    b = np.asarray(base_mm, dtype=np.float64)[:3] / 1000.0
    T[:3, 3] = b
    return T


def _occ_part_shape(p):
    """OCC TopoDS_Shape for one part in mm-local coordinates (metres)."""
    from OCC.Core.BRepPrimAPI import (
        BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakePrism)
    from OCC.Core.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace)
    from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec

    if p.kind == "cylinder":
        try:
            radius = float(cab_ifc._part_child_text(p, "radius"))
            height = float(cab_ifc._part_child_text(p, "height"))
        except (TypeError, ValueError):
            return None
        if radius <= 0 or height <= 0:
            return None
        return BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            radius / 1000.0, height / 1000.0).Shape()
    if p.kind == "polygon":
        fp = []
        for tok in cab_ifc._part_child_text(p, "points").split():
            try:
                x, y = tok.split(",")
                fp.append((float(x) / 1000.0, float(y) / 1000.0))
            except ValueError:
                continue
        if len(fp) < 3:
            return None
        size = cab_ifc._parse_triple(cab_ifc._part_child_text(p, "size"),
                                     (0.0, 0.0, 0.0))
        depth = size[2] / 1000.0
        if depth <= 0:
            return None
        wire = BRepBuilderAPI_MakeWire(
            BRepBuilderAPI_MakeEdge(
                gp_Pnt(fp[0][0], fp[0][1], 0.0),
                gp_Pnt(fp[1][0], fp[1][1], 0.0)).Edge())
        for i in range(1, len(fp)):
            a, b = fp[i], fp[(i + 1) % len(fp)]
            e = BRepBuilderAPI_MakeEdge(
                gp_Pnt(a[0], a[1], 0.0), gp_Pnt(b[0], b[1], 0.0)).Edge()
            wire.Add(e)
        wire = wire.Wire()
        face = BRepBuilderAPI_MakeFace(wire).Face()
        return BRepPrimAPI_MakePrism(
            face, gp_Vec(0.0, 0.0, depth)).Shape()
    box = cab_ifc._part_box(p)
    if box is None:
        return None
    base, size, _m = box
    sx, sy, sz = (float(s) / 1000.0 for s in size)
    if sx <= 0 or sy <= 0 or sz <= 0:
        return None
    return BRepPrimAPI_MakeBox(gp_Pnt(0.0, 0.0, 0.0),
                               gp_Pnt(sx, sy, sz)).Shape()


def _occ_export_step(model, step: Path) -> None:
    """Branch (b): pythonocc-core / OCP ``STEPControl_Writer``."""
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCC.Core.TopoDS import TopoDS_Compound
    from OCC.Core.gp import gp_Trsf

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for p in model.parts():
        shape = _occ_part_shape(p)
        if shape is None:
            continue
        m = cab_ifc._part_matrix(p)
        base = cab_ifc._parse_triple(
            p.base if (p.base or '').strip() else '0,0,0',
            (0.0, 0.0, 0.0))
        t4 = _metre_matrix(base, m)
        trsf = gp_Trsf()
        trsf.SetValues(
            float(t4[0, 0]), float(t4[0, 1]), float(t4[0, 2]),
            float(t4[0, 3]),
            float(t4[1, 0]), float(t4[1, 1]), float(t4[1, 2]),
            float(t4[1, 3]),
            float(t4[2, 0]), float(t4[2, 1]), float(t4[2, 2]),
            float(t4[2, 3]))
        moved = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        builder.Add(compound, moved)
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    if writer.Write(str(step)) != 1:
        raise StepExportUnavailable(
            f"STEP export branch (b): STEPControl_Writer failed for "
            f"{step}")


def export_step_file(model, path, *, archive=None, tags=None) -> Path:
    """Export the model to a STEP file via the three descending branches.

    Returns the written ``Path``.  Raises :class:`StepExportUnavailable`
    (a B-level declaration) when no backend is available.
    """
    step = Path(path)
    strategy = step_export_strategy()
    if strategy == "cli":
        _cli_export_step(find_cad_cli(), archive, tags or [], step)
    elif strategy == "occ":
        if not cab_occ.occ_available():
            raise StepExportUnavailable("STEP export branch (b): OCC import "
                                        "unavailable")
        _occ_export_step(model, step)
    else:
        raise StepExportUnavailable(
            "STEP export is B-level-declared: no CAD CLI (set "
            "STPRE_STEP_CLI / install FreeCAD) and no pythonocc-core "
            "(`pip install OCP`) is available.  STEP/SAT *import* works "
            "already and STpre's own STEP export relies on the same "
            "licensed chain, so a runtime STEP writer is not bundled. "
            f"[{_B_LEVEL_MARK}]")
    return step


# --------------------------------------------------------------------------
# FMT-4: ACIS SAT export (CLI branch + B-level declaration; no OCC writer)

def find_sat_cli() -> str | None:
    """Locate a user-supplied headless CLI able to convert ``.x_t``->SAT.

    No default candidates exist: neither pythonocc/OCC nor FreeCAD can
    *write* ACIS SAT, so only the ``STPRE_SAT_CLI`` environment variable
    (a command invoked as ``<cli> <in.x_t> <out.sat>``) enables branch (a).
    """
    env = os.environ.get("STPRE_SAT_CLI")
    if not env:
        return None
    if os.sep in env and os.path.isfile(env):
        return env
    return shutil.which(env)


def sat_export_strategy() -> str:
    """Return the available SAT branch: ``'cli'`` | ``'none'``."""
    return "cli" if find_sat_cli() else "none"


def export_sat_file(model, path, *, archive=None, tags=None) -> Path:
    """Export the model to an ACIS ``.sat`` file (FMT-4).

    Branch (a): ``.x_t`` intermediate + ``STPRE_SAT_CLI``.  Otherwise the
    B-level declaration raises :class:`SatExportUnavailable` — SAT *import*
    works already (``cab_occ.sat_to_triangles``) and STpre's own SAT export
    relies on the same licensed CADthru chain.
    """
    sat = Path(path)
    cli = find_sat_cli()
    if cli is None:
        raise SatExportUnavailable(
            "SAT export is B-level-declared: ACIS has no open-source "
            "writer (OCC/FreeCAD cannot write SAT) and no converter CLI "
            "is configured.  Set STPRE_SAT_CLI to a command invoked as "
            "'<cli> <in.x_t> <out.sat>', or use STEP/Parasolid XT export. "
            f"[{_B_LEVEL_MARK}]")
    with tempfile.TemporaryDirectory(prefix="cabsat_") as td:
        xt = Path(td) / "model.x_t"
        _write_xt(archive, tags or [], xt)
        subprocess.run([cli, str(xt), str(sat)], check=True, timeout=600,
                       capture_output=True, text=True)
    if not sat.is_file():
        raise SatExportUnavailable(
            f"SAT export branch (a): CLI {cli!r} produced no output")
    return sat
