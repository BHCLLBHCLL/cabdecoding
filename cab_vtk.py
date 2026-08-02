"""P2: VTK geometry builders for scSTREAM cab projects.

Full facet geometry would require a Parasolid kernel (out of scope), so the
3D view is assembled from data that is fully present in the cab XML:

- every part's meshed i/j/k box ranges (``element`` section) mapped through
  the ``mesh_block`` axis coordinates -> world-space part bounds;
- the analysis domain frame;
- cube parts additionally carry an analytic ``base``/``size`` (mm) plus a
  ``transform`` matrix, used as a fallback when the mesh tables are missing.

Output is ``vtkPolyData`` ready for the GUI (solid boxes + wireframes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from cabxml import StpreModel

try:
    import vtk
    from vtk.util import numpy_support
    _HAS_VTK = True
except Exception:  # pragma: no cover - environment without vtk
    vtk = None
    numpy_support = None
    _HAS_VTK = False


@dataclass
class PartBox:
    name: str
    bounds: tuple[float, float, float, float, float, float]  # xmin..zmax (m)
    color: tuple[float, float, float]                        # 0..1 RGB
    opacity: float = 1.0


def _parse_color(text: str) -> tuple[float, float, float]:
    try:
        parts = [float(x) for x in text.split(",")]
    except ValueError:
        return (0.7, 0.7, 0.7)
    if len(parts) >= 3:
        return tuple(max(0.0, min(1.0, v / 255.0)) for v in parts[:3])
    return (0.7, 0.7, 0.7)


def _box_bounds_from_element(model: StpreModel, part_name: str
                             ) -> Optional[tuple[float, float, float,
                                                 float, float, float]]:
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    boxes = model.part_boxes(part_name)
    if not boxes:
        return None
    mins = [float("inf")] * 3
    maxs = [-float("inf")] * 3
    axis_names = ("x", "y", "z")
    for box in boxes:
        if len(box) < 6:
            continue
        for a in range(3):
            i1, i2 = box[2 * a], box[2 * a + 1]
            coords = axes[axis_names[a]]
            if not (1 <= i1 <= len(coords) and 1 <= i2 <= len(coords)):
                return None
            lo = coords[i1 - 1] / 1000.0          # XML stores mm
            hi = coords[i2] / 1000.0
            mins[a] = min(mins[a], lo)
            maxs[a] = max(maxs[a], hi)
    if not all(np.isfinite(m) for m in mins + maxs):
        return None
    return (mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2])


def _box_bounds_from_cube(part) -> Optional[tuple[float, float, float,
                                                  float, float, float]]:
    if not part.base or not part.size:
        return None
    try:
        base = [float(v) / 1000.0 for v in part.base.split(",")[:3]]
        size = [float(v) / 1000.0 for v in part.size.split(",")[:3]]
        corners = np.array([
            [base[0], base[1], base[2]],
            [base[0] + size[0], base[1], base[2]],
            [base[0], base[1] + size[1], base[2]],
            [base[0] + size[0], base[1] + size[1], base[2]],
            [base[0], base[1], base[2] + size[2]],
            [base[0] + size[0], base[1], base[2] + size[2]],
            [base[0], base[1] + size[1], base[2] + size[2]],
            [base[0] + size[0], base[1] + size[1], base[2] + size[2]],
        ])
        if part.transform:
            m = np.array(
                [float(v) for v in part.transform.split(",")[:16]]
            ).reshape(4, 4)
            hom = np.hstack([corners, np.ones((8, 1))])
            corners = (hom @ m.T)[:, :3]
        return (float(corners[:, 0].min()), float(corners[:, 1].min()),
                float(corners[:, 2].min()), float(corners[:, 0].max()),
                float(corners[:, 1].max()), float(corners[:, 2].max()))
    except (ValueError, IndexError):
        return None


def part_boxes(model: StpreModel) -> list[PartBox]:
    """World-space bounds for every part (meters, mesh-derived first)."""
    out: list[PartBox] = []
    for p in model.parts():
        bounds = _box_bounds_from_element(model, p.name)
        if bounds is None:
            bounds = _box_bounds_from_cube(p)
        if bounds is None:
            continue
        color = _parse_color(p.color)
        opacity = 0.45 if p.attribute == "fluid" else 0.85
        out.append(PartBox(p.name, bounds, color, opacity))
    return out


def domain_frame(model: StpreModel) -> Optional[PartBox]:
    ar = model.analysis_region()
    if ar is None:
        return None
    from cabxml import _first
    base = _first(ar, "base")
    size = _first(ar, "size")
    if base is None or size is None:
        return None
    try:
        b = [float(v) / 1000.0 for v in base.text.split(",")[:3]]
        s = [float(v) / 1000.0 for v in size.text.split(",")[:3]]
    except ValueError:
        return None
    return PartBox("Domain", (b[0], b[1], b[2],
                              b[0] + s[0], b[1] + s[1], b[2] + s[2]),
                   (0.4, 0.7, 1.0), 1.0)


def _make_box_polydata(box: PartBox, wireframe: bool):
    xmin, ymin, zmin, xmax, ymax, zmax = box.bounds
    pts = np.array([
        [xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin],
        [xmin, ymax, zmin], [xmin, ymin, zmax], [xmax, ymin, zmax],
        [xmax, ymax, zmax], [xmin, ymax, zmax],
    ], dtype=np.float64)
    if wireframe:
        lines = np.array([
            [0, 1], [1, 2], [2, 3], [3, 0],
            [4, 5], [5, 6], [6, 7], [7, 4],
            [0, 4], [1, 5], [2, 6], [3, 7],
        ], dtype=np.int64)
        return _polydata(pts, lines, "lines")
    quads = np.array([
        [0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1],
        [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0],
    ], dtype=np.int64)
    return _polydata(pts, quads, "quads")


def _polydata(points: np.ndarray, cells: np.ndarray, kind: str):
    pd = vtk.vtkPolyData()
    vpts = vtk.vtkPoints()
    vpts.SetData(numpy_support.numpy_to_vtk(points, deep=True))
    pd.SetPoints(vpts)
    n = cells.shape[1]
    conn = np.column_stack([np.full(len(cells), n, dtype=np.int64),
                            cells]).reshape(-1)
    if kind == "lines":
        arr = vtk.vtkCellArray()
        arr.SetCells(len(cells),
                     numpy_support.numpy_to_vtkIdTypeArray(conn, deep=True))
        pd.SetLines(arr)
    else:
        arr = vtk.vtkCellArray()
        arr.SetCells(len(cells),
                     numpy_support.numpy_to_vtkIdTypeArray(conn, deep=True))
        pd.SetPolys(arr)
    return pd


def build_scene(boxes: list[PartBox],
                wireframe: bool = False) -> list[tuple[vtk.vtkPolyData,
                                                       tuple[float, float, float],
                                                       float]]:
    """One vtkPolyData + color + opacity per part."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    out = []
    for box in boxes:
        pd = _make_box_polydata(box, wireframe)
        out.append((pd, box.color, box.opacity))
    return out
