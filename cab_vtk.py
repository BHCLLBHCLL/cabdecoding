"""P2: VTK geometry builders for scSTREAM cab projects.

scSTREAM Pre shades **Parasolid** (``.x_t``) B-rep — that needs a commercial
kernel and is out of scope.  What *is* fully present in the cab XML is the
structured-mesh occupancy of every part: the ``element`` section stores many
``i1,i2,j1,j2,k1,k2`` index boxes per part (cut-cell / body lists).

Earlier builds merged those boxes into a single AABB, which made every part
look like a long rectangular brick and erased chamfer / fillet transitions.

This module renders the **union of index boxes** (stair-step solid) so the
Draw Window follows the same mesh occupancy STpre uses for Element division,
including stepped approximations of rounded corners.

Output is ``vtkPolyData`` ready for the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


Bounds = tuple[float, float, float, float, float, float]


@dataclass
class PartBox:
    """One part's display geometry.

    ``cells`` holds every mesh body box (meters).  ``bounds`` is the AABB of
    those cells (kept for tests / domain checks).
    """

    name: str
    bounds: Bounds
    color: tuple[float, float, float]                        # 0..1 RGB
    opacity: float = 1.0
    cells: list[Bounds] = field(default_factory=list)


def _parse_color(text: str) -> tuple[float, float, float]:
    try:
        parts = [float(x) for x in text.split(",")]
    except ValueError:
        return (0.7, 0.7, 0.7)
    if len(parts) >= 3:
        return tuple(max(0.0, min(1.0, v / 255.0)) for v in parts[:3])
    return (0.7, 0.7, 0.7)


def _ijk_box_to_bounds(axes: dict[str, list[float]],
                       box: list[int]) -> Optional[Bounds]:
    """Map one ``i1,i2,j1,j2,k1,k2,...`` list entry → world AABB (meters)."""
    if len(box) < 6:
        return None
    mins: list[float] = []
    maxs: list[float] = []
    for a, axis in enumerate(("x", "y", "z")):
        i1, i2 = box[2 * a], box[2 * a + 1]
        coords = axes[axis]
        if not (1 <= i1 <= len(coords) and 0 <= i2 < len(coords)):
            return None
        # Same convention as the historical AABB merger: lo at (i1-1), hi at i2.
        lo = coords[i1 - 1] / 1000.0
        hi = coords[i2] / 1000.0
        if hi < lo:
            lo, hi = hi, lo
        if abs(hi - lo) < 1e-15:
            # degenerate slab — nudge by a tiny epsilon of local spacing
            span = max(abs(coords[-1] - coords[0]) / max(len(coords), 1),
                       1e-6) / 1000.0
            hi = lo + span * 0.01
        mins.append(lo)
        maxs.append(hi)
    return (mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2])


def _merge_bounds(cells: list[Bounds]) -> Optional[Bounds]:
    if not cells:
        return None
    mins = [min(c[i] for c in cells) for i in range(3)]
    maxs = [max(c[i + 3] for c in cells) for i in range(3)]
    return (mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2])


def _cells_from_element(model: StpreModel, part_name: str) -> list[Bounds]:
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return []
    out: list[Bounds] = []
    for box in model.part_boxes(part_name):
        b = _ijk_box_to_bounds(axes, box)
        if b is not None:
            out.append(b)
    return out


def _box_bounds_from_cube(part) -> Optional[Bounds]:
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
    """Per-part geometry: one ``PartBox`` with all mesh body cells."""
    out: list[PartBox] = []
    for p in model.parts():
        cells = _cells_from_element(model, p.name)
        bounds = _merge_bounds(cells)
        if bounds is None:
            cube = _box_bounds_from_cube(p)
            if cube is None:
                continue
            cells = [cube]
            bounds = cube
        color = _parse_color(p.color)
        opacity = 0.45 if p.attribute == "fluid" else 0.85
        out.append(PartBox(p.name, bounds, color, opacity, cells=cells))
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
    bb: Bounds = (b[0], b[1], b[2], b[0] + s[0], b[1] + s[1], b[2] + s[2])
    return PartBox("Domain", bb, (0.4, 0.7, 1.0), 1.0, cells=[bb])


def _bounds_polydata(bounds: Bounds, wireframe: bool):
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
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


def _make_box_polydata(box: PartBox, wireframe: bool):
    """PolyData for a part: union of all mesh body cells (not just AABB)."""
    cells = box.cells or [box.bounds]
    if len(cells) == 1:
        return _bounds_polydata(cells[0], wireframe)
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    append = vtk.vtkAppendPolyData()
    for cell in cells:
        append.AddInputData(_bounds_polydata(cell, wireframe))
    append.Update()
    cleaned = vtk.vtkCleanPolyData()
    cleaned.SetInputConnection(append.GetOutputPort())
    cleaned.Update()
    return cleaned.GetOutput()


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


def axes_actor(length: float = 1.0):
    """Compact XYZ triad for the corner orientation marker (from pph_vtk)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(length, length, length)
    axes.SetShaftTypeToCylinder()
    axes.SetCylinderRadius(0.02)
    axes.SetConeRadius(0.08)
    axes.SetConeResolution(12)
    axes.SetCylinderResolution(12)
    axes.AxisLabelsOn()
    for cap in (axes.GetXAxisCaptionActor2D(),
                axes.GetYAxisCaptionActor2D(),
                axes.GetZAxisCaptionActor2D()):
        prop = cap.GetCaptionTextProperty()
        prop.SetFontSize(12)
        prop.SetBold(1)
        prop.ShadowOff()
    return axes


def orientation_marker_widget(interactor, size_frac: float = 0.14):
    """Corner orientation marker — does not pollute the scene bounds."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    widget = vtk.vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes_actor())
    widget.SetInteractor(interactor)
    # bottom-left, matching STpre triad placement
    widget.SetViewport(0.0, 0.0, size_frac, size_frac)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


def edges_actor(pd, color: tuple[float, float, float] = (0.15, 0.15, 0.18),
                opacity: float = 1.0, line_width: float = 1.2):
    """Mesh-line overlay on a part polydata (from pph_vtk.edges_actor)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    try:
        ext = vtk.vtkFeatureEdges()
        ext.SetInputData(pd)
        ext.BoundaryEdgesOn()
        ext.ManifoldEdgesOn()
        ext.NonManifoldEdgesOff()
        ext.FeatureEdgesOff()
        ext.ColoringOff()
        ext.Update()
        edge_pd = ext.GetOutput()
        if edge_pd is None or edge_pd.GetNumberOfCells() == 0:
            raise RuntimeError("empty feature edges")
    except Exception:
        ext2 = vtk.vtkExtractEdges()
        ext2.SetInputData(pd)
        ext2.Update()
        edge_pd = ext2.GetOutput()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(edge_pd)
    mapper.ScalarVisibilityOff()
    try:
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-1, -4)
    except Exception:
        pass
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetLineWidth(line_width)
    prop.SetAmbient(1.0)
    prop.SetDiffuse(0.0)
    prop.LightingOff()
    return actor


def mesh_block_grid(model: StpreModel, stride: int = 1):
    """Structured-mesh grid lines from ``mesh_block`` axes (meters).

    ``stride`` > 1 thins lines for large grids (e.g. 99×243×63).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    xs = [v / 1000.0 for v in axes["x"][::max(1, stride)]]
    ys = [v / 1000.0 for v in axes["y"][::max(1, stride)]]
    zs = [v / 1000.0 for v in axes["z"][::max(1, stride)]]
    if len(xs) < 2 or len(ys) < 2 or len(zs) < 2:
        return None
    x0, x1 = xs[0], xs[-1]
    y0, y1 = ys[0], ys[-1]
    z0, z1 = zs[0], zs[-1]
    pts: list[list[float]] = []
    lines: list[list[int]] = []

    def add_line(a, b):
        i = len(pts)
        pts.append(a)
        pts.append(b)
        lines.append([i, i + 1])

    # faces of the domain AABB — full grid on each face (readable, not 3-D dense)
    for y in ys:
        for z in (z0, z1):
            add_line([x0, y, z], [x1, y, z])
        for x in (x0, x1):
            add_line([x, y, z0], [x, y, z1])
    for x in xs:
        for z in (z0, z1):
            add_line([x, y0, z], [x, y1, z])
        for y in (y0, y1):
            add_line([x, y, z0], [x, y, z1])
    for z in zs:
        for y in (y0, y1):
            add_line([x0, y, z], [x1, y, z])
        for x in (x0, x1):
            add_line([x, y0, z], [x, y1, z])

    arr_pts = np.asarray(pts, dtype=np.float64)
    arr_lines = np.asarray(lines, dtype=np.int64)
    return _polydata(arr_pts, arr_lines, "lines")
