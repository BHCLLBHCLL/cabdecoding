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


def sketch_plane_grid(plane, points: bool = False):
    """Grid lines (or points) of a sketch plane in world metres."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    o = np.asarray(plane.origin, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    u0, u1 = plane.u_range
    v0, v1 = plane.v_range
    du = plane.delta[0] if plane.delta[0] > 0 else (u1 - u0)
    dv = plane.delta[1] if plane.delta[1] > 0 else (v1 - v0)
    us = np.arange(u0, u1 + du * 0.5, du)
    vs = np.arange(v0, v1 + dv * 0.5, dv)
    if len(us) < 2:
        us = np.array([u0, u1])
    if len(vs) < 2:
        vs = np.array([v0, v1])
    pts = []
    lines = []
    for uu in us:
        base = len(pts)
        pts.append(o + uu * u + v0 * v)
        pts.append(o + uu * u + v1 * v)
        lines.append([base, base + 1])
    for vv in vs:
        base = len(pts)
        pts.append(o + u0 * u + vv * v)
        pts.append(o + u1 * u + vv * v)
        lines.append([base, base + 1])
    vtk_pts = vtk.vtkPoints()
    for p in pts:
        vtk_pts.InsertNextPoint(*p)
    pd = vtk.vtkPolyData()
    pd.SetPoints(vtk_pts)
    cells = vtk.vtkCellArray()
    if points:
        for i in range(len(pts)):
            cells.InsertNextCell(1)
            cells.InsertCellPoint(i)
        pd.SetVerts(cells)
    else:
        for a, b in lines:
            cells.InsertNextCell(2)
            cells.InsertCellPoint(a)
            cells.InsertCellPoint(b)
        pd.SetLines(cells)
    return pd


def sketch_plane_actor(plane, opacity: float = 0.9):
    """Actor for the sketch-plane grid (colour from ``sketch_control``)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    pd = sketch_plane_grid(plane)
    color = tuple(c / 255.0 for c in plane.color[:3])
    return edges_actor(pd, color=color, opacity=opacity, line_width=1.0)


def sketch_axes_actors(plane, length: Optional[float] = None):
    """Three coloured U/V/W arrows + origin dot for the sketch plane."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    o = np.asarray(plane.origin, float) / 1000.0
    ur = plane.u_range
    vr = plane.v_range
    default_len = 0.1 * max(ur[1] - ur[0], vr[1] - vr[0], 0.01)
    ln = length or default_len
    actors = []
    for vec, col in ((np.asarray(plane.u), (0.85, 0.15, 0.15)),
                     (np.asarray(plane.v), (0.15, 0.75, 0.15)),
                     (np.asarray(plane.w), (0.15, 0.25, 0.9))):
        src = vtk.vtkLineSource()
        src.SetPoint1(*o)
        src.SetPoint2(*(o + vec * ln))
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(src.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*col)
        actor.GetProperty().SetLineWidth(2.2)
        actors.append(actor)
    sp = vtk.vtkSphereSource()
    sp.SetCenter(*o)
    sp.SetRadius(ln * 0.05)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sp.GetOutputPort())
    dot = vtk.vtkActor()
    dot.SetMapper(mapper)
    dot.GetProperty().SetColor(0.85, 0.1, 0.1)
    actors.append(dot)
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


def section_actor(pd, colors, mode: str = "show"):
    """Scalar-coloured actor for the cross-section slice.

    ``colors`` is the ``(name, rgb)`` list returned by
    :func:`element_section_data`; part_id 0 (fluid) is light grey.
    """
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    lut = vtk.vtkLookupTable()
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
