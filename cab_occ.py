"""STEP / SAT geometry import through OpenCascade (pythonocc-core / OCP).

The Cradle CADthru/STEPAssistant executables are GUI applications and must
not be used for headless conversion (they hang).  Parasolid's pskernel only
reads its native ``.x_t``, so STEP/ACIS import is delegated to OCC when
available::

    pip install OCP        # pythonocc-core

The imported shape is tessellated with ``BRepMesh_IncrementalMesh`` and
returned as ``(points, triangles)``; the caller persists it as an STL
member, so OCC is only required at import time.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.TopoDS import TopoDS_Face
    _OCC = True
    try:
        from OCC.Core.SATControl import SATControl_Reader  # noqa: F401
        _SAT = True
    except Exception:
        _SAT = False
except Exception:  # pragma: no cover - OCC not installed
    _OCC = False
    _SAT = False


def occ_available() -> bool:
    return _OCC


def sat_available() -> bool:
    return _OCC and _SAT


def _tessellate(shape) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate an OCC TopoDS_Shape into ``(points, triangles)``."""
    mesh = BRepMesh_IncrementalMesh(shape, 0.001)
    mesh.Perform()
    pts: list[tuple[float, float, float]] = []
    index: dict[tuple, int] = {}
    tris: list[list[int]] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS_Face(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation(face, loc)
        if tri is not None:
            n_nodes = tri.NbNodes()
            for i in range(1, n_nodes + 1):
                p = tri.Node(i)
                xyz = (p.X(), p.Y(), p.Z())
                key = (round(xyz[0], 9), round(xyz[1], 9),
                       round(xyz[2], 9))
                if key not in index:
                    index[key] = len(pts)
                    pts.append(xyz)
            for i in range(1, tri.NbTriangles() + 1):
                t = tri.Triangle(i)
                tris.append([index[(round(tri.Node(t.Value(1)).X(), 9),
                                    round(tri.Node(t.Value(1)).Y(), 9),
                                    round(tri.Node(t.Value(1)).Z(), 9))],
                             index[(round(tri.Node(t.Value(2)).X(), 9),
                                    round(tri.Node(t.Value(2)).Y(), 9),
                                    round(tri.Node(t.Value(2)).Z(), 9))],
                             index[(round(tri.Node(t.Value(3)).X(), 9),
                                    round(tri.Node(t.Value(3)).Y(), 9),
                                    round(tri.Node(t.Value(3)).Z(), 9))]])
        exp.Next()
    if not tris:
        raise ValueError("OCC tessellation produced no triangles")
    return (np.asarray(pts, dtype=np.float64),
            np.asarray(tris, dtype=np.int64))


def step_to_triangles(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    if not _OCC:
        raise RuntimeError(
            "OpenCascade (pythonocc-core / OCP) is not installed. "
            "Install it with `pip install OCP` to import STEP/SAT, "
            "or convert the file to .x_t with your own tool first.")
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != 1:
        raise RuntimeError(f"STEP read failed (status={status}): {path}")
    reader.TransferRoots()
    return _tessellate(reader.OneShape())


def sat_to_triangles(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    if not _OCC:
        raise RuntimeError(
            "OpenCascade (pythonocc-core / OCP) is not installed. "
            "Install it with `pip install OCP` to import STEP/SAT, "
            "or convert the file to .x_t with your own tool first.")
    if not _SAT:
        raise RuntimeError(
            "this OCP build has no SATControl reader; convert the .sat "
            "file to .x_t with your own tool first.")
    reader = SATControl_Reader()
    status = reader.ReadFile(str(path))
    if status != 1:
        raise RuntimeError(f"SAT read failed (status={status}): {path}")
    reader.TransferRoots()
    return _tessellate(reader.OneShape())


def triangles_to_stl(points: np.ndarray, triangles: np.ndarray,
                     name: str = "occ_part") -> bytes:
    """Write an ASCII STL stream for cab persistence."""
    out = [f"solid {name}"]
    for t in triangles:
        a, b, c = (points[int(i)] for i in t)
        out.append("  facet normal 0 0 0")
        out.append("    outer loop")
        for p in (a, b, c):
            out.append(f"      vertex {p[0]:.9g} {p[1]:.9g} {p[2]:.9g}")
        out.append("    endloop")
        out.append("  endfacet")
    out.append(f"endsolid {name}")
    return ("\n".join(out) + "\n").encode("ascii")
