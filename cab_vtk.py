"""P2: VTK geometry builders for scSTREAM cab projects.

Part shading prefers Parasolid ``.x_t`` tessellation when Cradle
``pskernel.dll`` is available (smooth B-rep).  The tessellated mesh is
transformed into world coordinates with the part ``<transform>`` and gets
per-point normals so curved faces shade smoothly while sharp edges stay
crisp.  Otherwise — and always for Element division overlays — the
structured-mesh occupancy boxes from the ``element`` section are used
(stair-step solids).

Output is ``vtkPolyData`` ready for the GUI.
"""

from __future__ import annotations

import math
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
    those cells (kept for tests / domain checks).  When ``cad_polydata`` is
    set, Part shading uses the smooth CAD mesh; Element division still uses
    ``cells``.
    """

    name: str
    bounds: Bounds
    color: tuple[float, float, float]                        # 0..1 RGB
    opacity: float = 1.0
    cells: list[Bounds] = field(default_factory=list)
    cad_polydata: object = None  # optional vtkPolyData
    transform: Optional[str] = None  # XML <transform>, column-major 4x4


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
            # XML transform is column-major; row-vector convention needs @ m.
            corners = (hom @ m)[:, :3]
        return (float(corners[:, 0].min()), float(corners[:, 1].min()),
                float(corners[:, 2].min()), float(corners[:, 0].max()),
                float(corners[:, 1].max()), float(corners[:, 2].max()))
    except (ValueError, IndexError):
        return None


def _apply_transform(points: np.ndarray,
                     transform: Optional[str]) -> np.ndarray:
    """Apply the XML part transform (column-major 4x4) to points."""
    if not transform:
        return points
    try:
        m = np.array(
            [float(v) for v in transform.split(",")[:16]]
        ).reshape(4, 4)
    except (ValueError, IndexError):
        return points
    hom = np.hstack([points, np.ones((len(points), 1))])
    return (hom @ m)[:, :3]


def _tris_to_polydata(points: np.ndarray, triangles: np.ndarray):
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    if points.size == 0 or triangles.size == 0:
        return None
    pd = _polydata(np.asarray(points, dtype=np.float64),
                   np.asarray(triangles, dtype=np.int64), "tris")
    cleaned = vtk.vtkCleanPolyData()
    cleaned.SetInputData(pd)
    cleaned.Update()
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(cleaned.GetOutputPort())
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.SplittingOn()
    normals.SetFeatureAngle(45.0)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()
    return normals.GetOutput()


def attach_cad_meshes(
    boxes: list[PartBox],
    tess_parts: list,
) -> int:
    """Attach tessellated CAD meshes onto matching ``PartBox`` entries.

    Returns the number of parts that received CAD geometry.
    """
    by_name = {t.name: t for t in tess_parts}
    n = 0
    for box in boxes:
        tess = by_name.get(box.name)
        if tess is None:
            continue
        pts = _apply_transform(
            np.asarray(tess.points, dtype=np.float64), box.transform)
        pd = _tris_to_polydata(pts, tess.triangles)
        if pd is None:
            continue
        box.cad_polydata = pd
        # Prefer CAD AABB when mesh boxes are missing/odd
        if pts.size:
            box.bounds = (
                float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 2].min()), float(pts[:, 0].max()),
                float(pts[:, 1].max()), float(pts[:, 2].max()),
            )
        n += 1
    return n


def part_boxes(model: StpreModel,
               cad_meshes: Optional[list] = None) -> list[PartBox]:
    """Per-part geometry: mesh body cells, optionally with CAD shading mesh."""
    cad_names = {t.name for t in cad_meshes} if cad_meshes else set()
    out: list[PartBox] = []
    for p in model.parts():
        cells = _cells_from_element(model, p.name)
        bounds = _merge_bounds(cells)
        if bounds is None:
            cube = _box_bounds_from_cube(p)
            if cube is None:
                # Body geometry with no generated mesh yet: keep a placeholder
                # only when a matching Parasolid body can supply the surface.
                if p.name not in cad_names:
                    continue
                bounds = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            else:
                cells = [cube]
                bounds = cube
        color = _parse_color(p.color)
        opacity = 0.45 if p.attribute == "fluid" else 0.85
        out.append(PartBox(p.name, bounds, color, opacity, cells=cells,
                           transform=p.transform))
    if cad_meshes:
        attach_cad_meshes(out, cad_meshes)
        # Drop placeholder-only entries whose CAD body could not be attached.
        out = [b for b in out
               if b.cad_polydata is not None or b.cells]
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


_FACE_AXIS = {"Xmin": 0, "Xmax": 0, "Ymin": 1, "Ymax": 1,
              "Zmin": 2, "Zmax": 2}
_FACE_SIDE = {"Xmin": -1, "Xmax": 1, "Ymin": -1, "Ymax": 1,
              "Zmin": -1, "Zmax": 1}


def domain_face_edges(face_name: str, lo_m, hi_m):
    """Four line segments of one domain-boundary face (vtkPolyData)."""
    lo = np.asarray(lo_m, dtype=float)
    hi = np.asarray(hi_m, dtype=float)
    axis = _FACE_AXIS[face_name]
    c = lo[axis] if _FACE_SIDE[face_name] < 0 else hi[axis]
    others = [j for j in range(3) if j != axis]
    a, b = others
    pts = np.array([
        [c, lo[a], lo[b]],
        [c, hi[a], lo[b]],
        [c, hi[a], hi[b]],
        [c, lo[a], hi[b]],
    ], dtype=float)
    pts = pts[:, [0, 1, 2]]
    cells = np.array([[0, 1], [1, 2], [2, 3], [3, 0]], dtype=np.int64)
    return _polydata(pts, cells, "lines")


def root_block_frame(model: StpreModel) -> Optional[PartBox]:
    """STpre Layout→RootBlock AABB (mm→m) for the blue wireframe cuboid."""
    bb_mm = model.root_block_bounds()
    if bb_mm is None:
        return None
    xmin, ymin, zmin, xmax, ymax, zmax = bb_mm
    bb: Bounds = (xmin / 1000.0, ymin / 1000.0, zmin / 1000.0,
                  xmax / 1000.0, ymax / 1000.0, zmax / 1000.0)
    # Thin solid blue matching STpre RootBlock (screenshot wireframe)
    return PartBox("RootBlock", bb, (0.12, 0.35, 0.95), 1.0, cells=[bb])


def _wireframe_box_actor(bb_m: Bounds, color, line_width: float):
    """Shared thin wireframe cuboid actor (RootBlock / child blocks)."""
    pd = _bounds_polydata(bb_m, wireframe=True)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
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
    prop.SetOpacity(1.0)
    prop.SetRepresentationToWireframe()
    prop.SetLineWidth(line_width)
    prop.SetAmbient(1.0)
    prop.SetDiffuse(0.0)
    prop.LightingOff()
    try:
        prop.BackfaceCullingOff()
        prop.FrontfaceCullingOff()
    except Exception:
        pass
    return actor


def root_block_actor(model: StpreModel, line_width: float = 1.15):
    """Thin blue wireframe cuboid for Layout of Parts → RootBlock."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    frame = root_block_frame(model)
    if frame is None:
        return None
    return _wireframe_box_actor(frame.bounds, frame.color, line_width)


def child_block_actors(model: StpreModel, line_width: float = 1.0,
                       color=(0.05, 0.65, 0.75)) -> list:
    """Thin cyan wireframes for every child block (multiblock structure).

    Visibility follows the Layout→RootBlock layer: the GUI appends these
    to the same layer actor list.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    blocks = model.mesh_blocks()
    if not blocks:
        return []
    actors: list = []

    def walk(blk: dict) -> None:
        lo, hi = blk.get("min"), blk.get("max")
        if lo is not None and hi is not None:
            import numpy as _np
            lo = _np.asarray(lo, dtype=float)
            hi = _np.asarray(hi, dtype=float)
            if _np.isfinite(lo).all() and _np.isfinite(hi).all():
                bb: Bounds = (lo[0] / 1000.0, lo[1] / 1000.0,
                              lo[2] / 1000.0, hi[0] / 1000.0,
                              hi[1] / 1000.0, hi[2] / 1000.0)
                actors.append(
                    _wireframe_box_actor(bb, color, line_width))
        for child in blk.get("children", []):
            walk(child)

    for blk in blocks:
        for child in blk.get("children", []):
            walk(child)
    return actors


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


def part_polydata(box: PartBox, *, for_part: bool = True,
                  wireframe: bool = False):
    """PolyData for Part shading (CAD if present) or Element boxes."""
    if for_part and box.cad_polydata is not None:
        return box.cad_polydata
    return _make_box_polydata(box, wireframe)


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


# STpre global / sketch triad colours (magenta X·U, green Y·V, blue Z·W)
_AXIS_COLOR_X = (0.90, 0.20, 0.55)
_AXIS_COLOR_Y = (0.15, 0.72, 0.22)
_AXIS_COLOR_Z = (0.18, 0.40, 0.95)


def axes_actor(length: float = 1.0):
    """STpre bottom-left **global XYZ** orientation triad.

    Proportions match the Draw Window corner gizmo: cylindrical shafts,
    conical tips ≈ 30% of arm length, magenta / green / blue, labels ``x y z``.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(length, length, length)
    axes.SetShaftTypeToCylinder()
    # Tip ≈ 1/3 of each arm (STpre screenshot proportions)
    try:
        axes.SetNormalizedShaftLength(0.70, 0.70, 0.70)
        axes.SetNormalizedTipLength(0.30, 0.30, 0.30)
    except Exception:
        pass
    axes.SetCylinderRadius(0.035)
    axes.SetConeRadius(0.12)
    axes.SetConeResolution(20)
    axes.SetCylinderResolution(16)
    axes.AxisLabelsOn()
    axes.SetXAxisLabelText("x")
    axes.SetYAxisLabelText("y")
    axes.SetZAxisLabelText("z")
    for getter, color in (
            (axes.GetXAxisShaftProperty, _AXIS_COLOR_X),
            (axes.GetXAxisTipProperty, _AXIS_COLOR_X),
            (axes.GetYAxisShaftProperty, _AXIS_COLOR_Y),
            (axes.GetYAxisTipProperty, _AXIS_COLOR_Y),
            (axes.GetZAxisShaftProperty, _AXIS_COLOR_Z),
            (axes.GetZAxisTipProperty, _AXIS_COLOR_Z)):
        try:
            prop = getter()
            prop.SetColor(*color)
            prop.SetAmbient(0.4)
            prop.SetDiffuse(0.7)
        except Exception:
            pass
    for cap, color in (
            (axes.GetXAxisCaptionActor2D(), _AXIS_COLOR_X),
            (axes.GetYAxisCaptionActor2D(), _AXIS_COLOR_Y),
            (axes.GetZAxisCaptionActor2D(), _AXIS_COLOR_Z)):
        try:
            tp = cap.GetCaptionTextProperty()
            tp.SetFontSize(16)
            tp.SetBold(1)
            tp.ShadowOff()
            tp.SetColor(*color)
            # Keep labels close to the tip
            cap.SetWidth(0.12)
            cap.SetHeight(0.08)
        except Exception:
            pass
    return axes


def orientation_marker_widget(interactor, size_frac: float = 0.17):
    """Bottom-left **global XYZ** marker (screen-space, STpre Axis Global)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    widget = vtk.vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes_actor())
    widget.SetInteractor(interactor)
    # Slightly larger than default so shaft/cone proportions read like STpre
    widget.SetViewport(0.0, 0.0, size_frac, size_frac)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


def edges_actor(pd, color: tuple[float, float, float] = (0.15, 0.15, 0.18),
                opacity: float = 1.0, line_width: float = 1.2):
    """Mesh-line overlay on a part polydata (from pph_vtk.edges_actor)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    # Already a line set (e.g. element_division_lines) — map directly.
    if pd is not None and pd.GetNumberOfLines() > 0 and pd.GetNumberOfPolys() == 0:
        edge_pd = pd
    else:
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
        # Pull lines in front of opaque CAD shading (STpre-like overlay).
        mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2, -8)
        mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -4)
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
    try:
        prop.SetRepresentationToWireframe()
    except Exception:
        pass
    return actor


def _sketch_axis_samples(lo: float, hi: float, delta: float) -> np.ndarray:
    """Inclusive samples from ``lo`` to ``hi`` at ``delta`` (metres).

    Keeps every full interval step **and** the endpoint (STpre).  Important
    when ``(hi-lo)/delta`` is not an integer — e.g. 0…25 mm with Δ=10 mm
    must yield ``0, 10, 20, 25`` (not ``0, 10, 25`` which drops the 20 mm
    secondary line via ``round(2.5)→2``).
    """
    if hi < lo:
        lo, hi = hi, lo
    span = hi - lo
    if span < 1e-15:
        return np.array([lo, hi], dtype=np.float64)
    d = delta if delta > 1e-15 else max(span / 10.0, 1e-9)
    tol = 1e-9 * max(1.0, abs(hi), abs(lo))
    n_fit = int(np.floor(span / d + 1e-12))
    vals = [lo]
    for i in range(1, n_fit + 1):
        v = lo + i * d
        if v < hi - tol:
            vals.append(v)
        else:
            # landed on (or past) the end
            break
    if abs(vals[-1] - hi) > tol:
        vals.append(hi)
    else:
        vals[-1] = hi
    return np.asarray(vals, dtype=np.float64)


def _lines_polydata(segments: list[tuple[np.ndarray, np.ndarray]]):
    """Build vtkPolyData lines from ``(p0, p1)`` segments (metres)."""
    vtk_pts = vtk.vtkPoints()
    cells = vtk.vtkCellArray()
    for a, b in segments:
        i0 = vtk_pts.InsertNextPoint(float(a[0]), float(a[1]), float(a[2]))
        i1 = vtk_pts.InsertNextPoint(float(b[0]), float(b[1]), float(b[2]))
        cells.InsertNextCell(2)
        cells.InsertCellPoint(i0)
        cells.InsertCellPoint(i1)
    pd = vtk.vtkPolyData()
    pd.SetPoints(vtk_pts)
    pd.SetLines(cells)
    return pd


def sketch_plane_major_stride(plane, target_majors: int = 5) -> int:
    """How many minor intervals per major line (STpre-style 5 → labels 0,25,…).

    When the span has fewer than 5 intervals (e.g. Max=25, Δ=5 → 5 intervals,
    or Max=25, Δ=10 → 3 steps), keep **all interior lines as 副网格** and put
    主网格 only on the ends (stride = n_intervals).
    """
    du = plane.delta[0] if plane.delta[0] > 0 else 0.005
    span = abs(plane.u_range[1] - plane.u_range[0])
    n_int = max(int(np.floor(span / du + 1e-12)), 1)
    # endpoint-only remainder still counts as an extra segment for display
    samples = _sketch_axis_samples(
        float(plane.u_range[0]), float(plane.u_range[1]), du)
    n_seg = max(len(samples) - 1, 1)
    if n_seg < target_majors:
        return n_seg
    if n_int >= target_majors and n_int % target_majors == 0:
        return target_majors
    for cand in (5, 4, 2, 10):
        if n_seg >= cand:
            return cand
    return 1


def sketch_plane_grid(plane, points: bool = False):
    """All grid lines of a sketch plane (compat; prefer major/minor helpers)."""
    minor, major, _labels = sketch_plane_grid_layers(plane)
    if points:
        return major
    # Merge for callers that expect a single polydata
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    append = vtk.vtkAppendPolyData()
    append.AddInputData(minor)
    append.AddInputData(major)
    append.Update()
    return append.GetOutput()


def sketch_plane_grid_layers(plane):
    """Return ``(minor_pd, major_pd, edge_labels)``.

    ``edge_labels`` is a list of ``(world_xyz_m, text)`` for major ticks
    along the +U and +V borders (mm integers, STpre style).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    o = np.asarray(plane.origin, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    nu = np.linalg.norm(u)
    nv = np.linalg.norm(v)
    if nu > 1e-12:
        u = u / nu
    if nv > 1e-12:
        v = v / nv
    u0, u1 = float(plane.u_range[0]), float(plane.u_range[1])
    v0, v1 = float(plane.v_range[0]), float(plane.v_range[1])
    du = plane.delta[0] if plane.delta[0] > 0 else max(abs(u1 - u0) / 10, 1e-9)
    dv = plane.delta[1] if plane.delta[1] > 0 else max(abs(v1 - v0) / 10, 1e-9)
    us = _sketch_axis_samples(u0, u1, du)
    vs = _sketch_axis_samples(v0, v1, dv)
    stride = sketch_plane_major_stride(plane)
    minor_seg: list[tuple[np.ndarray, np.ndarray]] = []
    major_seg: list[tuple[np.ndarray, np.ndarray]] = []
    labels: list[tuple[tuple[float, float, float], str]] = []

    def _put(uu, vv0, vv1, major: bool):
        p0 = o + uu * u + vv0 * v
        p1 = o + uu * u + vv1 * v
        (major_seg if major else minor_seg).append((p0, p1))

    def _put_h(vv, uu0, uu1, major: bool):
        p0 = o + uu0 * u + vv * v
        p1 = o + uu1 * u + vv * v
        (major_seg if major else minor_seg).append((p0, p1))

    for i, uu in enumerate(us):
        is_maj = (i % stride == 0) or i == 0 or i == len(us) - 1
        _put(uu, v0, v1, is_maj)
        if is_maj:
            # label along the far (+V) edge
            pos = o + uu * u + v1 * v
            labels.append(((float(pos[0]), float(pos[1]), float(pos[2])),
                           f"{uu * 1000:g}"))
    for j, vv in enumerate(vs):
        is_maj = (j % stride == 0) or j == 0 or j == len(vs) - 1
        _put_h(vv, u0, u1, is_maj)
        if is_maj:
            pos = o + u0 * u + vv * v
            labels.append(((float(pos[0]), float(pos[1]), float(pos[2])),
                           f"{vv * 1000:g}"))

    return (_lines_polydata(minor_seg), _lines_polydata(major_seg), labels)


def _line_actor(pd, color, line_width: float, opacity: float = 1.0):
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetLineWidth(line_width)
    prop.SetAmbient(1.0)
    prop.SetDiffuse(0.0)
    prop.LightingOff()
    try:
        prop.SetRepresentationToWireframe()
    except Exception:
        pass
    return actor


def sketch_plane_actors(plane, opacity: float = 1.0) -> list:
    """STpre sketch grid: thin minor + thick major lines (+ mm tick labels)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    minor_pd, major_pd, labels = sketch_plane_grid_layers(plane)
    base = tuple(c / 255.0 for c in plane.color[:3])
    # Minor: light grey; major: darker (STpre thick/thin combo)
    minor_col = tuple(min(1.0, c + 0.12) for c in base)
    major_col = tuple(max(0.0, c - 0.25) for c in base)
    if sum(major_col) / 3 > 0.65:
        minor_col = (0.72, 0.74, 0.78)
        major_col = (0.38, 0.40, 0.46)
    actors = []
    # Skip empty polydata (no secondary lines) so VTK does not drop the grid
    if minor_pd.GetNumberOfLines() > 0:
        actors.append(
            _line_actor(minor_pd, minor_col, 1.0, opacity * 0.9))
    if major_pd.GetNumberOfLines() > 0:
        actors.append(
            _line_actor(major_pd, major_col, 2.0, opacity))
    # Tick labels (skip duplicates at corners by text)
    seen: set[str] = set()
    for (x, y, z), text in labels:
        key = f"{text}@{x:.6g},{y:.6g},{z:.6g}"
        if key in seen:
            continue
        seen.add(key)
        try:
            cap = vtk.vtkBillboardTextActor3D()
            cap.SetInput(text)
            cap.SetPosition(x, y, z)
            tp = cap.GetTextProperty()
            tp.SetFontSize(14)
            tp.SetColor(0.25, 0.25, 0.28)
            tp.SetBold(0)
            tp.ShadowOff()
            actors.append(cap)
        except Exception:
            pass
    return actors


def sketch_plane_actor(plane, opacity: float = 0.95):
    """Single combined actor (compat). Prefer :func:`sketch_plane_actors`."""
    actors = sketch_plane_actors(plane, opacity=opacity)
    return actors[1] if len(actors) > 1 else actors[0]


def sketch_profile_actors(plane, uv_points_mm, *, close: bool = True,
                          color=(0.62, 0.18, 0.78),
                          line_width: float = 2.5,
                          point_radius_mm: float = 1.2,
                          lift_mm: float = 0.15) -> list:
    """Draw an in-progress sketch profile (polyline + dots + # labels).

    ``uv_points_mm`` is a sequence of ``(U, V)`` in millimetres on ``plane``.
    Geometry is lifted slightly along ``W`` to avoid z-fighting the grid.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    pts_uv = list(uv_points_mm or [])
    if not pts_uv:
        return []
    o = np.asarray(plane.origin, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    w = np.asarray(plane.w, float)
    for vec in (u, v, w):
        n = np.linalg.norm(vec)
        if n > 1e-12:
            vec /= n
    lift = float(lift_mm) / 1000.0
    world = []
    for uu, vv in pts_uv:
        p = o + (float(uu) / 1000.0) * u + (float(vv) / 1000.0) * v + lift * w
        world.append(p)

    actors: list = []
    # Polyline (+ optional close segment)
    if len(world) >= 2:
        segs = [(world[i], world[i + 1]) for i in range(len(world) - 1)]
        if close and len(world) >= 3:
            segs.append((world[-1], world[0]))
        actors.append(_line_actor(
            _lines_polydata(segs), color, line_width, 1.0))

    # Vertex spheres
    r = max(float(point_radius_mm) / 1000.0, 1e-5)
    for p in world:
        sph = vtk.vtkSphereSource()
        sph.SetCenter(float(p[0]), float(p[1]), float(p[2]))
        sph.SetRadius(r)
        sph.SetThetaResolution(12)
        sph.SetPhiResolution(12)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(sph.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*color)
        prop.SetOpacity(1.0)
        prop.LightingOff()
        actors.append(actor)

    # Number labels (1-based), STpre style
    for i, p in enumerate(world):
        try:
            cap = vtk.vtkBillboardTextActor3D()
            cap.SetInput(str(i + 1))
            # offset slightly in U+V so text is not buried in the sphere
            off = p + (1.8 * r) * (u + v)
            cap.SetPosition(float(off[0]), float(off[1]), float(off[2]))
            tp = cap.GetTextProperty()
            tp.SetFontSize(16)
            tp.SetColor(*color)
            tp.SetBold(1)
            tp.ShadowOff()
            actors.append(cap)
        except Exception:
            pass
    return actors


def _arrow_actor(origin, direction, length: float, color,
                 tip_length: float = 0.22, tip_radius: float = 0.06,
                 shaft_radius: float = 0.02):
    """Unit-X arrow transformed to ``origin → origin+dir*length``."""
    d = np.asarray(direction, float)
    n = np.linalg.norm(d)
    if n < 1e-12 or length <= 0:
        return None
    d = d / n
    arrow = vtk.vtkArrowSource()
    arrow.SetTipResolution(20)
    arrow.SetShaftResolution(16)
    arrow.SetTipLength(tip_length)
    arrow.SetTipRadius(tip_radius)
    arrow.SetShaftRadius(shaft_radius)
    # map unit-X arrow → direction, then scale/translate
    x = np.array([1.0, 0.0, 0.0])
    cross = np.cross(x, d)
    dot = float(np.dot(x, d))
    tform = vtk.vtkTransform()
    tform.Identity()
    tform.Translate(float(origin[0]), float(origin[1]), float(origin[2]))
    if np.linalg.norm(cross) < 1e-8:
        if dot < 0:
            tform.RotateWXYZ(180.0, 0.0, 1.0, 0.0)
    else:
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        tform.RotateWXYZ(ang, float(cross[0]), float(cross[1]), float(cross[2]))
    tform.Scale(length, length, length)
    tf_filter = vtk.vtkTransformPolyDataFilter()
    tf_filter.SetTransform(tform)
    tf_filter.SetInputConnection(arrow.GetOutputPort())
    tf_filter.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(tf_filter.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetAmbient(0.35)
    prop.SetDiffuse(0.75)
    prop.SetSpecular(0.15)
    return actor


def sketch_axes_actors(plane, length: Optional[float] = None):
    """STpre **local UVW** triad on the sketch plane (Draw Window centre).

    Same arrow proportions as the corner global XYZ gizmo; placed at the
    sketch-plane origin (UV plane = sketch plane in global coordinates).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    o = np.asarray(plane.origin, float) / 1000.0
    ur = plane.u_range
    vr = plane.v_range
    span = max(abs(ur[1] - ur[0]), abs(vr[1] - vr[0]), 0.01)
    ln = length if length is not None else 0.22 * span
    ln = float(min(max(ln, 0.015), 0.06))
    actors = []
    specs = (
        (np.asarray(plane.u, float), _AXIS_COLOR_X, "U"),
        (np.asarray(plane.v, float), _AXIS_COLOR_Y, "V"),
        (np.asarray(plane.w, float), _AXIS_COLOR_Z, "W"),
    )
    for vec, col, label in specs:
        n = np.linalg.norm(vec)
        if n < 1e-12:
            continue
        vec = vec / n
        # tip_length≈0.30 matches corner vtkAxesActor normalized tip
        arr = _arrow_actor(o, vec, ln, col,
                           tip_length=0.30, tip_radius=0.08,
                           shaft_radius=0.028)
        if arr is not None:
            try:
                arr.SetUseBounds(False)
            except Exception:
                pass
            actors.append(arr)
        tip = o + vec * (ln * 1.10)
        try:
            cap = vtk.vtkBillboardTextActor3D()
            cap.SetInput(label)
            cap.SetPosition(float(tip[0]), float(tip[1]), float(tip[2]))
            tp = cap.GetTextProperty()
            tp.SetFontSize(16)
            tp.SetBold(1)
            tp.SetColor(*col)
            tp.ShadowOff()
            actors.append(cap)
        except Exception:
            pass
    # Grey origin ball + faint blue ring (STpre sketch-axis hub)
    r_ball = ln * 0.07
    sp = vtk.vtkSphereSource()
    sp.SetCenter(float(o[0]), float(o[1]), float(o[2]))
    sp.SetRadius(r_ball)
    sp.SetThetaResolution(24)
    sp.SetPhiResolution(24)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sp.GetOutputPort())
    dot = vtk.vtkActor()
    dot.SetMapper(mapper)
    dot.GetProperty().SetColor(0.40, 0.40, 0.43)
    try:
        dot.SetUseBounds(False)
    except Exception:
        pass
    actors.append(dot)
    try:
        ring = vtk.vtkRegularPolygonSource()
        ring.SetCenter(float(o[0]), float(o[1]), float(o[2]))
        ring.SetNormal(
            float(plane.w[0]), float(plane.w[1]), float(plane.w[2]))
        ring.SetRadius(r_ball * 1.55)
        ring.SetNumberOfSides(48)
        ring.GeneratePolygonOff()
        ring.GeneratePolylineOn()
        rm = vtk.vtkPolyDataMapper()
        rm.SetInputConnection(ring.GetOutputPort())
        ra = vtk.vtkActor()
        ra.SetMapper(rm)
        ra.GetProperty().SetColor(0.35, 0.55, 0.95)
        ra.GetProperty().SetLineWidth(1.5)
        ra.GetProperty().SetOpacity(0.65)
        ra.SetUseBounds(False)
        actors.append(ra)
    except Exception:
        pass
    return actors


def world_origin_marker_actors(scale: float):
    """Drawing→Origin: small grey hub at world (0,0,0) — not a full XYZ triad.

    Global XYZ lives in the corner orientation marker; local UVW is the
    sketch-plane triad. Origin only marks the world origin point.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    r = min(max(scale * 0.012, 4e-5), 0.0012)
    actors = []
    sp = vtk.vtkSphereSource()
    sp.SetCenter(0.0, 0.0, 0.0)
    sp.SetRadius(r)
    sp.SetThetaResolution(20)
    sp.SetPhiResolution(20)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sp.GetOutputPort())
    ball = vtk.vtkActor()
    ball.SetMapper(mapper)
    ball.GetProperty().SetColor(0.40, 0.40, 0.43)
    try:
        ball.SetUseBounds(False)
    except Exception:
        pass
    actors.append(ball)
    try:
        ring = vtk.vtkRegularPolygonSource()
        ring.SetCenter(0.0, 0.0, 0.0)
        ring.SetNormal(0.0, 0.0, 1.0)
        ring.SetRadius(r * 1.6)
        ring.SetNumberOfSides(40)
        ring.GeneratePolygonOff()
        ring.GeneratePolylineOn()
        rm = vtk.vtkPolyDataMapper()
        rm.SetInputConnection(ring.GetOutputPort())
        ra = vtk.vtkActor()
        ra.SetMapper(rm)
        ra.GetProperty().SetColor(0.35, 0.55, 0.95)
        ra.GetProperty().SetLineWidth(1.2)
        ra.GetProperty().SetOpacity(0.55)
        ra.SetUseBounds(False)
        actors.append(ra)
    except Exception:
        pass
    return actors


def _axis_slice_m(axes: dict[str, list[float]], axis: str,
                  i1: int, i2: int) -> Optional[list[float]]:
    """Node coordinates (m) covering element index range ``i1..i2`` (1-based)."""
    coords = axes.get(axis) or []
    if not (1 <= i1 <= len(coords) and 0 <= i2 < len(coords)):
        return None
    lo = min(i1 - 1, i2)
    hi = max(i1 - 1, i2)
    # include both ends of the occupied cell span (same as _ijk_box_to_bounds)
    return [coords[k] / 1000.0 for k in range(lo, hi + 1)]


def element_division_lines(model: StpreModel, part_name: str | None = None,
                           max_lines: int = 250_000,
                           surface_eps: float = 1e-5,
                           boxes: list | None = None,
                           interior_stride: int = 0):
    """Structured-mesh lines for STpre **Element division**.

    Unlike occupancy-box FeatureEdges (coarse stair outlines), this draws the
    ``mesh_block`` grid on every face of each ``element`` index box — the dense
    body mesh lines STpre shows when Element division is on.

    Pass ``part_name`` for ``element/parts``, or ``boxes`` for a pre-fetched
    index list (e.g. Domain from ``element/analysis``).

    ``surface_eps`` (meters) nudges each face grid slightly outward so lines
    remain visible over opaque CAD shading.

    ``interior_stride`` > 0 also draws sparse internal grid planes (volume
    mesh) every N node lines — used for Domain(cuboid) body.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    if boxes is None:
        if not part_name:
            return None
        boxes = model.part_boxes(part_name)
    if not boxes:
        return None

    pts: list[list[float]] = []
    lines: list[list[int]] = []
    eps = max(0.0, float(surface_eps))
    stride_i = max(0, int(interior_stride))

    def add_line(a, b):
        i = len(pts)
        pts.append(a)
        pts.append(b)
        lines.append([i, i + 1])

    for box in boxes:
        if len(box) < 6:
            continue
        xs = _axis_slice_m(axes, "x", box[0], box[1])
        ys = _axis_slice_m(axes, "y", box[2], box[3])
        zs = _axis_slice_m(axes, "z", box[4], box[5])
        if not xs or not ys or not zs:
            continue
        if len(xs) < 2 or len(ys) < 2 or len(zs) < 2:
            continue
        x0, x1 = xs[0], xs[-1]
        y0, y1 = ys[0], ys[-1]
        z0, z1 = zs[0], zs[-1]
        # outward nudge so overlay clears shaded CAD
        xl, xh = x0 - eps, x1 + eps
        yl, yh = y0 - eps, y1 + eps
        zl, zh = z0 - eps, z1 + eps

        # 6 faces of this occupancy brick — full structured grid on each face
        for y in ys:
            add_line([xl, y, zl], [xh, y, zl])
            add_line([xl, y, zh], [xh, y, zh])
            add_line([xl, y, zl], [xl, y, zh])
            add_line([xh, y, zl], [xh, y, zh])
        for x in xs:
            add_line([x, yl, zl], [x, yh, zl])
            add_line([x, yl, zh], [x, yh, zh])
            add_line([x, yl, zl], [x, yl, zh])
            add_line([x, yh, zl], [x, yh, zh])
        for z in zs:
            add_line([xl, yl, z], [xh, yl, z])
            add_line([xl, yh, z], [xh, yh, z])
            add_line([xl, yl, z], [xl, yh, z])
            add_line([xh, yl, z], [xh, yh, z])

        # sparse interior planes for volume domain mesh
        if stride_i > 0:
            for x in xs[stride_i:-stride_i:stride_i]:
                for y in ys:
                    add_line([x, y, zl], [x, y, zh])
                for z in zs:
                    add_line([x, yl, z], [x, yh, z])
            for y in ys[stride_i:-stride_i:stride_i]:
                for x in xs:
                    add_line([x, y, zl], [x, y, zh])
                for z in zs:
                    add_line([xl, y, z], [xh, y, z])
            for z in zs[stride_i:-stride_i:stride_i]:
                for x in xs:
                    add_line([x, yl, z], [x, yh, z])
                for y in ys:
                    add_line([xl, y, z], [xh, y, z])

        if len(lines) > max_lines:
            break

    if not lines:
        return None
    return _polydata(np.asarray(pts, dtype=np.float64),
                     np.asarray(lines, dtype=np.int64), "lines")


def element_division_shell(model: StpreModel, part_name: str | None = None,
                           boxes: list | None = None,
                           max_quads: int = 500_000,
                           surface_eps: float = 0.0):
    """Opaque structured quads on occupancy-box faces (STpre Element shading).

    Builds the closed outer shell of each index brick as mesh_block face
    quads so Domain/Part element division can be drawn opaque (not wireframe).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    if boxes is None:
        if not part_name:
            return None
        boxes = model.part_boxes(part_name)
    if not boxes:
        return None

    pts: list[list[float]] = []
    quads: list[list[int]] = []
    eps = max(0.0, float(surface_eps))

    def add_quad(a, b, c, d):
        i = len(pts)
        pts.extend((a, b, c, d))
        quads.append([i, i + 1, i + 2, i + 3])

    for box in boxes:
        if len(box) < 6:
            continue
        xs = _axis_slice_m(axes, "x", box[0], box[1])
        ys = _axis_slice_m(axes, "y", box[2], box[3])
        zs = _axis_slice_m(axes, "z", box[4], box[5])
        if not xs or not ys or not zs:
            continue
        if len(xs) < 2 or len(ys) < 2 or len(zs) < 2:
            continue
        x0, x1 = xs[0] - eps, xs[-1] + eps
        y0, y1 = ys[0] - eps, ys[-1] + eps
        z0, z1 = zs[0] - eps, zs[-1] + eps
        # Keep face grids on the nudged planes but use original node spacing
        # in-plane (map xs/ys/zs onto [x0,x1] only at ends).
        xs_f = list(xs)
        ys_f = list(ys)
        zs_f = list(zs)
        xs_f[0], xs_f[-1] = x0, x1
        ys_f[0], ys_f[-1] = y0, y1
        zs_f[0], zs_f[-1] = z0, z1

        # z = const faces
        for z in (zs_f[0], zs_f[-1]):
            for i in range(len(xs_f) - 1):
                for j in range(len(ys_f) - 1):
                    add_quad(
                        [xs_f[i], ys_f[j], z],
                        [xs_f[i + 1], ys_f[j], z],
                        [xs_f[i + 1], ys_f[j + 1], z],
                        [xs_f[i], ys_f[j + 1], z],
                    )
        # y = const faces
        for y in (ys_f[0], ys_f[-1]):
            for i in range(len(xs_f) - 1):
                for k in range(len(zs_f) - 1):
                    add_quad(
                        [xs_f[i], y, zs_f[k]],
                        [xs_f[i + 1], y, zs_f[k]],
                        [xs_f[i + 1], y, zs_f[k + 1]],
                        [xs_f[i], y, zs_f[k + 1]],
                    )
        # x = const faces
        for x in (xs_f[0], xs_f[-1]):
            for j in range(len(ys_f) - 1):
                for k in range(len(zs_f) - 1):
                    add_quad(
                        [x, ys_f[j], zs_f[k]],
                        [x, ys_f[j + 1], zs_f[k]],
                        [x, ys_f[j + 1], zs_f[k + 1]],
                        [x, ys_f[j], zs_f[k + 1]],
                    )

        if len(quads) > max_quads:
            break

    if not quads:
        return None
    return _polydata(np.asarray(pts, dtype=np.float64),
                     np.asarray(quads, dtype=np.int64), "quads")


def shaded_poly_actor(pd, color: tuple[float, float, float],
                      opacity: float = 1.0):
    """Opaque (or translucent) surface actor for element/domain shells."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetInterpolationToFlat()
    prop.SetAmbient(0.45)
    prop.SetDiffuse(0.55)
    prop.SetSpecular(0.05)
    prop.EdgeVisibilityOff()
    return actor


def _axis_cell_planes_m(model: StpreModel):
    """Element cell planes per axis (metres): mid-planes i=0..len-2.

    Returns ``{axis: ndarray of len(axis_coords)-1 planes}`` for the
    cross-section display.
    """
    axes = model.mesh_axes()
    out: dict[str, np.ndarray] = {}
    for ax in "xyz":
        coords = [v / 1000.0 for v in axes.get(ax, [])]
        if len(coords) < 2:
            out[ax] = np.zeros(0)
        else:
            out[ax] = np.asarray(coords, dtype=np.float64)
    return out


def _cell_mask_from_boxes(ni: int, nj: int, nk: int,
                          boxes: list[list[int]]) -> np.ndarray:
    """0-based occupancy mask from 1-based inclusive i/j/k boxes (local copy
    to avoid a cab_mesh <-> cab_vtk import cycle)."""
    mask = np.zeros((ni, nj, nk), dtype=bool)
    for b in boxes:
        if len(b) < 6:
            continue
        i0, i1, j0, j1, k0, k1 = [int(v) for v in b[:6]]
        i0 = max(0, i0 - 1); i1 = min(ni - 1, i1 - 1)
        j0 = max(0, j0 - 1); j1 = min(nj - 1, j1 - 1)
        k0 = max(0, k0 - 1); k1 = min(nk - 1, k1 - 1)
        if i0 <= i1 and j0 <= j1 and k0 <= k1:
            mask[i0:i1 + 1, j0:j1 + 1, k0:k1 + 1] = True
    return mask


def element_section_data(model: StpreModel, axis: str, index: int,
                         mode: str = "show"):
    """Cells of the cross-section plane at element ``index`` (1-based).

    ``axis`` is x/y/z; ``index`` selects one element layer along it.
    ``mode`` matches STpre [Show Element Cross-Section]:
      show        -> all cells (fluid + parts)
      hide        -> part cells only
      fluid_only  -> fluid cells only

    Returns ``(cells, colors)`` where ``cells`` is a list of
    ``(quad_pts[4x3] in metres, part_id)`` (0 = fluid, n = 1-based part
    number in ``colors``) and ``colors`` is the ``[(part_name, rgb)]`` list
    aligned so ``part_id`` maps to ``colors[part_id - 1]``.
    """
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return [], []
    ncells = {a: len(axes[a]) - 1 for a in "xyz"}
    if axis not in ncells or not (1 <= index <= ncells[axis]):
        return [], []
    el = model.elements()
    order = [p.attrib.get("name", "") for p in el.findall("parts")
             ] if el is not None else []
    order = [n for n in order if n and model.part_boxes(n)]
    colors = [(n, _parse_color(
        next((p.color for p in model.parts() if p.name == n),
             "180,180,180"))) for n in order]
    masks: dict[str, np.ndarray] = {}
    ni, nj, nk = ncells["x"], ncells["y"], ncells["z"]
    for name in order:
        masks[name] = _cell_mask_from_boxes(ni, nj, nk,
                                            model.part_boxes(name))
    union = np.zeros((ni, nj, nk), dtype=bool)
    for m in masks.values():
        union |= m

    planes = _axis_cell_planes_m(model)
    # in-plane axes ordered (va, wa) so the slice is a 2D grid
    axes2 = [a for a in "xyz" if a != axis]
    va, wa = axes2
    v = planes[va]
    w = planes[wa]
    cells: list[tuple[list[list[float]], int]] = []
    n0 = 0.5 * (planes[axis][index - 1] + planes[axis][index])

    def point(i: int, j: int) -> list[float]:
        if axis == "x":
            return [n0, v[i], w[j]]
        if axis == "y":
            return [v[i], n0, w[j]]
        return [v[i], w[j], n0]

    for iv in range(len(v) - 1):
        for iw in range(len(w) - 1):
            if axis == "x":
                i, j, k = index, iv + 1, iw + 1
            elif axis == "y":
                i, j, k = iv + 1, index, iw + 1
            else:
                i, j, k = iv + 1, iw + 1, index
            part_id = 0
            for n, name in enumerate(order, start=1):
                if masks[name][i - 1, j - 1, k - 1]:
                    part_id = n
                    break
            if mode == "fluid_only" and part_id != 0:
                continue
            if mode == "hide" and part_id == 0:
                continue
            quad = [point(iv, iw), point(iv + 1, iw),
                    point(iv + 1, iw + 1), point(iv, iw + 1)]
            cells.append((quad, part_id))
    return cells, colors


def element_section_polydata(model: StpreModel, axis: str, index: int,
                             mode: str = "show"):
    """vtkPolyData of the cross-section slice with a ``part_id`` cell scalar."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    cells, colors = element_section_data(model, axis, index, mode)
    if not cells:
        return None, colors
    pts: list[list[float]] = []
    quads: list[list[int]] = []
    ids: list[int] = []
    for quad, part_id in cells:
        base = len(pts)
        for p in quad:
            pts.append(list(p))
        quads.append([base, base + 1, base + 2, base + 3])
        ids.append(part_id)
    pd = _polydata(np.asarray(pts, dtype=np.float64),
                   np.asarray(quads, dtype=np.int64), "quads")
    arr = numpy_support.numpy_to_vtk(
        np.asarray(ids, dtype=np.uint8), deep=True)
    arr.SetName("part_id")
    pd.GetCellData().AddArray(arr)
    return pd, colors


def element_quality_section_polydata(model: StpreModel, axis: str,
                                    index: int, mode: str = 'show'):
    # vtkPolyData of the cross-section slice coloured by element aspect
    # ratio. Each slice cell carries an 'aspect' cell scalar = longest /
    # shortest edge of the local cell box (1.0 = perfect cube). Used by
    # [Mesh] - [Showing Element Cross-Section] display type 'Quality'.
    if not _HAS_VTK:
        raise RuntimeError('vtk is not installed')
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    cells, _colors = element_section_data(model, axis, index, mode)
    if not cells:
        return None
    widths = {a: np.asarray([
        axes[a][i + 1] - axes[a][i] for i in range(len(axes[a]) - 1)])
        for a in 'xyz'}
    w_axis = widths[axis][index - 1]
    pts = []
    quads = []
    aspects = []
    for quad, part_id in cells:
        base = len(pts)
        for p in quad:
            pts.append(list(p))
        quads.append([base, base + 1, base + 2, base + 3])
        p0 = np.asarray(quad[0])
        e1 = float(np.linalg.norm(np.asarray(quad[1]) - p0))
        e2 = float(np.linalg.norm(np.asarray(quad[3]) - p0))
        longest = max(e1, e2, w_axis)
        shortest = min(x for x in (e1, e2, w_axis) if x > 0) or 1e-30
        aspects.append(longest / shortest)
    pd = _polydata(np.asarray(pts, dtype=np.float64),
                   np.asarray(quads, dtype=np.int64), 'quads')
    arr = numpy_support.numpy_to_vtk(
        np.asarray(aspects, dtype=np.float64), deep=True)
    arr.SetName('aspect')
    pd.GetCellData().AddArray(arr)
    return pd


def section_actor(pd, colors, mode: str = "show"):
    """Scalar-coloured actor for the cross-section slice.

    ``colors`` is the ``(name, rgb)`` list returned by
    :func:`element_section_data`; part_id 0 (fluid) is light grey.  When
    ``colors`` is None the slice carries an ``aspect`` cell scalar and is
    coloured by element quality (blue = cube-like, red = high aspect).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    lut = vtk.vtkLookupTable()
    if colors is None:
        lut.SetNumberOfTableValues(64)
        lut.SetHueRange(0.667, 0.0)   # blue -> red
        lut.SetSaturationRange(1.0, 1.0)
        lut.SetValueRange(1.0, 0.7)
        arr = pd.GetCellData().GetArray("aspect")
        rng = arr.GetRange() if arr is not None else (1.0, 1.0)
        lut.SetRange(rng[0], rng[1])
        lut.Build()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        mapper.SetLookupTable(lut)
        mapper.SetScalarRange(rng[0], rng[1])
        mapper.SetScalarModeToUseCellData()
        mapper.SelectColorArray("aspect")
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        return actor
    lut.SetNumberOfTableValues(len(colors) + 1)
    lut.SetTableValue(0, 0.82, 0.84, 0.86, 1.0)   # fluid
    for i, (_name, rgb) in enumerate(colors, start=1):
        lut.SetTableValue(i, rgb[0], rgb[1], rgb[2], 1.0)
    lut.SetRange(0, len(colors))
    lut.Build()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.SetLookupTable(lut)
    mapper.SetScalarRange(0, len(colors))
    mapper.SetScalarModeToUseCellData()
    mapper.SelectColorArray("part_id")
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def mesh_block_extents_m(model: StpreModel
                         ) -> Optional[tuple[float, float, float,
                                             float, float, float]]:
    """RootBlock / mesh_block AABB in metres from axis end-points."""
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    return (
        axes["x"][0] / 1000.0, axes["y"][0] / 1000.0, axes["z"][0] / 1000.0,
        axes["x"][-1] / 1000.0, axes["y"][-1] / 1000.0, axes["z"][-1] / 1000.0,
    )


def mesh_block_shell_polydata(model: StpreModel):
    """Closed AABB shell (6 quads) for depth occlusion of Mesh face grids.

    STpre Drawing→Mesh shows face grids with back-face occlusion; a light
    shell writes the Z-buffer so rear grid lines are hidden while parts
    inside remain visible through a translucent fill.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    ext = mesh_block_extents_m(model)
    if ext is None:
        return None
    x0, y0, z0, x1, y1, z1 = ext
    # Slightly inset so RootBlock blue edges stay visible outside the shell
    eps = max(1e-6, 0.0005 * max(x1 - x0, y1 - y0, z1 - z0, 1e-3))
    x0 += eps; y0 += eps; z0 += eps
    x1 -= eps; y1 -= eps; z1 -= eps
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        return None
    pts = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=np.float64)
    quads = np.array([
        [0, 1, 2, 3],  # z0
        [4, 5, 6, 7],  # z1
        [0, 1, 5, 4],  # y0
        [3, 2, 6, 7],  # y1
        [0, 3, 7, 4],  # x0
        [1, 2, 6, 5],  # x1
    ], dtype=np.int64)
    return _polydata(pts, quads, "polys")


def mesh_block_grid(model: StpreModel, stride: int = 1):
    """Structured-mesh grid lines on the six RootBlock faces (meters).

    ``stride`` > 1 thins lines for large grids (e.g. 99×243×63).
    Face-only (not a full 3-D lattice) — matches STpre Drawing→Mesh.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return None
    step = max(1, int(stride))

    def _sample(vals: list[float]) -> list[float]:
        out = [v / 1000.0 for v in vals[::step]]
        last = vals[-1] / 1000.0
        if not out or abs(out[-1] - last) > 1e-12:
            out.append(last)
        return out

    xs, ys, zs = _sample(axes["x"]), _sample(axes["y"]), _sample(axes["z"])
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

    # Six faces of the domain AABB — full structured grid on each face
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


def mesh_block_display_actors(
        model: StpreModel, *,
        stride: int = 1,
        line_color: tuple[float, float, float] = (0.35, 0.48, 0.62),
        shell_color: tuple[float, float, float] = (0.78, 0.86, 0.92),
        shell_opacity: float = 0.55,
        line_width: float = 1.05) -> list:
    """STpre Drawing→Mesh: face grids + translucent shell (depth occlusion).

    Returns ``[shell_actor, line_actor]`` (either may be omitted if empty).
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    actors: list = []
    shell_pd = mesh_block_shell_polydata(model)
    if shell_pd is not None and shell_pd.GetNumberOfCells() > 0:
        shell = shaded_poly_actor(
            shell_pd, color=shell_color, opacity=shell_opacity)
        # Write depth so rear grid lines / far faces are occluded
        prop = shell.GetProperty()
        prop.SetAmbient(0.55)
        prop.SetDiffuse(0.45)
        prop.BackfaceCullingOff()
        actors.append(shell)
    grid = mesh_block_grid(model, stride=stride)
    if grid is not None and grid.GetNumberOfCells() > 0:
        lines = edges_actor(
            grid, color=line_color, line_width=line_width, opacity=1.0)
        # Depth-test against the shell / parts (do not force always-on-top)
        try:
            mapper = lines.GetMapper()
            mapper.SetResolveCoincidentTopologyToPolygonOffset()
            mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-1, -2)
        except Exception:
            pass
        actors.append(lines)
    return actors
