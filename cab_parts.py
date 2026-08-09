"""Part menu primitive creation (aligned with STpre [Part] menu).

Supports Cuboid / Hexahedron / Cylinder / Conical Base / Sphere / Panel /
Quadrilateral Panel / Revolved Rectangle / Point / Fan / Axial-Flow Fan /
Blower Fan / Sketch Part (extrusion) / Pipe Part.

Each primitive is stored as ``<parts type="…">`` with geometry parameters in
XML. A :class:`PrimitivePart` (duck-typed TessPart) is generated for the 3D
view. On reload the geometry is rebuilt from XML (no ``.x_t`` required).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from cabxml import StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QRadioButton, QSpinBox, QTabWidget, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless
    _HAS_GUI_DEPS = False
    QDialog = object  # type: ignore
    pyqtSignal = lambda *a, **k: None  # type: ignore

try:
    from cab_widgets import CoordSpinBox
    QDoubleSpinBox = CoordSpinBox
except Exception:
    pass


# STpre Part(P) menu order — None = separator
PART_MENU_ITEMS: list[tuple[str, str] | None] = [
    ("Cuboid…", "cube"),
    ("Hexahedron…", "hexahedron"),
    ("Cylinder…", "cylinder"),
    ("Conical Base…", "conical"),
    ("Sphere…", "sphere"),
    ("Panel…", "panel"),
    ("Quadrilateral Panel…", "quad_panel"),
    ("Revolved Rectangle…", "revolved"),
    ("Point…", "point"),
    None,
    ("Enclosure…", "enclosure"),
    ("Plate Fin…", "plate_fin"),
    ("Pin Fin…", "pin_fin"),
    ("Peltier Device Model…", "peltier"),
    ("Thermal Circuit Model (Two-Resistor)…", "two_resistor"),
    None,
    ("Fan…", "fan"),
    ("Axial-Flow Fan…", "axial_fan"),
    ("Blower Fan…", "blower_fan"),
    None,
    ("Sketch Part…", "sketch"),
    ("Pipe Part…", "pipe"),
]

PRIMITIVE_KINDS = (
    "cube", "hexahedron", "cylinder", "conical", "sphere", "panel",
    "quad_panel", "revolved", "point", "fan", "axial_fan", "blower_fan",
    "sketch", "pipe",
    "enclosure", "plate_fin", "pin_fin", "peltier", "two_resistor",
)

KIND_TITLES = {
    "cube": "Cuboid",
    "hexahedron": "Hexahedron",
    "cylinder": "Cylinder",
    "conical": "Conical Base",
    "sphere": "Sphere",
    "panel": "Panel",
    "quad_panel": "Quadrilateral Panel",
    "revolved": "Revolved Rectangle",
    "point": "Point",
    "fan": "Fan",
    "axial_fan": "Axial-Flow Fan",
    "blower_fan": "Blower Fan",
    "sketch": "Sketch Part",
    "pipe": "Pipe Part",
    "enclosure": "Enclosure",
    "plate_fin": "Plate Fin",
    "pin_fin": "Pin Fin",
    "peltier": "Peltier Device Model",
    "two_resistor": "Thermal Circuit Model (Two-Resistor)",
}


@dataclass
class PrimitivePart:
    """Duck-typed TessPart for generated primitive geometry."""

    name: str
    points: np.ndarray
    triangles: np.ndarray


def _axis_vector(axis: str) -> np.ndarray:
    return {
        "+X": np.array([1.0, 0.0, 0.0]),
        "-X": np.array([-1.0, 0.0, 0.0]),
        "+Y": np.array([0.0, 1.0, 0.0]),
        "-Y": np.array([0.0, -1.0, 0.0]),
        "+Z": np.array([0.0, 0.0, 1.0]),
        "-Z": np.array([0.0, 0.0, -1.0]),
    }.get(axis, np.array([0.0, 0.0, 1.0]))


def _rotation_to(axis: str) -> np.ndarray:
    """3x3 rotation mapping +Z onto ``axis`` (Rodrigues)."""
    target = _axis_vector(axis)
    z = np.array([0.0, 0.0, 1.0])
    if np.allclose(target, z):
        return np.eye(3)
    if np.allclose(target, -z):
        return np.diag([1.0, -1.0, -1.0])
    v = np.cross(z, target)
    s = np.linalg.norm(v)
    c = float(np.dot(z, target))
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def _rotation_align(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """3x3 rotation mapping unit vector ``src`` onto ``dst``."""
    a = src / (np.linalg.norm(src) + 1e-30)
    b = dst / (np.linalg.norm(dst) + 1e-30)
    if np.allclose(a, b):
        return np.eye(3)
    if np.allclose(a, -b):
        # 180° about any perpendicular
        if abs(a[0]) < 0.9:
            axis = np.cross(a, np.array([1.0, 0.0, 0.0]))
        else:
            axis = np.cross(a, np.array([0.0, 1.0, 0.0]))
        axis /= np.linalg.norm(axis)
        vx = np.array([[0, -axis[2], axis[1]],
                       [axis[2], 0, -axis[0]],
                       [-axis[1], axis[0], 0]])
        return np.eye(3) + 2 * vx @ vx
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = float(np.dot(a, b))
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


# ---------------------------------------------------------------------------
# Tessellation
# ---------------------------------------------------------------------------

def cube_tess(base_mm, size_mm) -> PrimitivePart:
    b = np.asarray(base_mm, float) / 1000.0
    s = np.asarray(size_mm, float) / 1000.0
    pts = np.array([
        [b[0], b[1], b[2]], [b[0] + s[0], b[1], b[2]],
        [b[0] + s[0], b[1] + s[1], b[2]], [b[0], b[1] + s[1], b[2]],
        [b[0], b[1], b[2] + s[2]], [b[0] + s[0], b[1], b[2] + s[2]],
        [b[0] + s[0], b[1] + s[1], b[2] + s[2]],
        [b[0], b[1] + s[1], b[2] + s[2]],
    ])
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return PrimitivePart("", pts, tris)


def hexahedron_tess(points_mm) -> PrimitivePart:
    """8 corner points in STpre order (bottom 1-4, top 5-8)."""
    pts = np.asarray(points_mm, float).reshape(8, 3) / 1000.0
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return PrimitivePart("", pts, tris)


def cylinder_tess(center_mm, radius: float, height: float,
                  axis: str = "+Z", divisions: int = 24) -> PrimitivePart:
    c = np.asarray(center_mm, float) / 1000.0
    r = float(radius) / 1000.0
    h = float(height) / 1000.0
    n = max(4, int(divisions))
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    ring = np.stack([r * np.cos(ang), r * np.sin(ang), np.zeros(n)], axis=1)
    local = np.vstack([ring, ring + np.array([0.0, 0.0, h])])
    pts = local @ _rotation_to(axis).T + c
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + j])
        tris.append([i, n + j, n + i])
    for i in range(1, n - 1):
        tris.append([0, i + 1, i])
    for i in range(1, n - 1):
        tris.append([n, n + i, n + i + 1])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def conical_tess(center1_mm, center2_mm, radius1: float, radius2: float,
                 divisions: int = 24) -> PrimitivePart:
    """Frustum (conical base) between two circular faces."""
    c1 = np.asarray(center1_mm, float) / 1000.0
    c2 = np.asarray(center2_mm, float) / 1000.0
    r1 = float(radius1) / 1000.0
    r2 = float(radius2) / 1000.0
    n = max(4, int(divisions))
    axis = c2 - c1
    length = float(np.linalg.norm(axis))
    if length < 1e-12:
        axis = np.array([0.0, 0.0, 1.0])
        length = 1e-6
    rot = _rotation_align(np.array([0.0, 0.0, 1.0]), axis)
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    ring1 = np.stack([r1 * np.cos(ang), r1 * np.sin(ang), np.zeros(n)], 1)
    ring2 = np.stack([r2 * np.cos(ang), r2 * np.sin(ang),
                      np.full(n, length)], 1)
    local = np.vstack([ring1, ring2])
    pts = local @ rot.T + c1
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + j])
        tris.append([i, n + j, n + i])
    if r1 > 1e-12:
        for i in range(1, n - 1):
            tris.append([0, i + 1, i])
    if r2 > 1e-12:
        for i in range(1, n - 1):
            tris.append([n, n + i, n + i + 1])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def sphere_tess(center_mm, radius, divisions: int = 12) -> PrimitivePart:
    c = np.asarray(center_mm, float) / 1000.0
    r = np.atleast_1d(np.asarray(radius, float) / 1000.0)
    if r.size == 1:
        r = np.array([r[0], r[0], r[0]])
    nlat = max(4, divisions // 2)
    nlon = max(4, divisions)
    pts = []
    pts.append(c + np.array([0.0, 0.0, r[2]]))
    for i in range(1, nlat):
        phi = np.pi * i / nlat
        for j in range(nlon):
            theta = 2.0 * np.pi * j / nlon
            pts.append(c + np.array([
                r[0] * np.sin(phi) * np.cos(theta),
                r[1] * np.sin(phi) * np.sin(theta),
                r[2] * np.cos(phi)]))
    pts.append(c - np.array([0.0, 0.0, r[2]]))
    tris = []
    for j in range(nlon):
        j2 = (j + 1) % nlon
        tris.append([0, 1 + j2, 1 + j])
    for i in range(nlat - 2):
        base = 1 + i * nlon
        for j in range(nlon):
            j2 = (j + 1) % nlon
            a = base + j
            b = base + j2
            c2 = a + nlon
            d = b + nlon
            tris.append([a, b, d])
            tris.append([a, d, c2])
    last = 1 + (nlat - 1) * nlon
    for j in range(nlon):
        j2 = (j + 1) % nlon
        tris.append([last + j, last + j2, last + nlon])
    return PrimitivePart("", np.asarray(pts), np.asarray(tris, dtype=np.int64))


def panel_tess(base_mm, size_mm, direction: str = "+Z") -> PrimitivePart:
    b = np.asarray(base_mm, float) / 1000.0
    s = np.asarray(size_mm, float) / 1000.0
    axis = _axis_vector(direction)
    i = int(np.argmax(np.abs(axis)))
    other = [k for k in range(3) if k != i]
    pts = np.zeros((4, 3))
    for k, idx in enumerate(other):
        pts[1 if k == 0 else 2, idx] = s[idx]
    pts[3] = pts[1] + pts[2]
    pts += b
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return PrimitivePart("", pts, tris)


def quad_panel_tess(points_mm) -> PrimitivePart:
    pts = np.asarray(points_mm, float).reshape(4, 3) / 1000.0
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return PrimitivePart("", pts, tris)


def revolved_tess(radius1: float, radius2: float, angle1_deg: float,
                  angle2_deg: float, z1: float, z2: float,
                  divisions: int = 24) -> PrimitivePart:
    """Annular sector revolved about +Z (STpre Revolved Rectangle)."""
    r_lo = min(float(radius1), float(radius2)) / 1000.0
    r_hi = max(float(radius1), float(radius2)) / 1000.0
    z_lo = min(float(z1), float(z2)) / 1000.0
    z_hi = max(float(z1), float(z2)) / 1000.0
    a0 = np.deg2rad(float(angle1_deg))
    a1 = np.deg2rad(float(angle2_deg))
    if abs(a1 - a0) < 1e-9:
        a1 = a0 + 2.0 * np.pi
    n = max(4, int(divisions))
    ang = np.linspace(a0, a1, n + 1)
    # rings: inner/outer at z_lo and z_hi
    def ring(r, z):
        return np.stack([r * np.cos(ang), r * np.sin(ang),
                         np.full(ang.shape, z)], 1)

    ri0, ro0 = ring(r_lo, z_lo), ring(r_hi, z_lo)
    ri1, ro1 = ring(r_lo, z_hi), ring(r_hi, z_hi)
    pts = np.vstack([ri0, ro0, ri1, ro1])
    # index helpers: 0..n inner-lo, n+1..2n+1 outer-lo, …
    def idx(base, i):
        return base + i

    tris = []
    n1 = n + 1
    for i in range(n):
        # bottom annulus
        tris.append([idx(0, i), idx(n1, i), idx(n1, i + 1)])
        tris.append([idx(0, i), idx(n1, i + 1), idx(0, i + 1)])
        # top annulus
        tris.append([idx(2 * n1, i), idx(2 * n1, i + 1), idx(3 * n1, i + 1)])
        tris.append([idx(2 * n1, i), idx(3 * n1, i + 1), idx(3 * n1, i)])
        # inner wall
        if r_lo > 1e-12:
            tris.append([idx(0, i), idx(0, i + 1), idx(2 * n1, i + 1)])
            tris.append([idx(0, i), idx(2 * n1, i + 1), idx(2 * n1, i)])
        # outer wall
        tris.append([idx(n1, i), idx(3 * n1, i), idx(3 * n1, i + 1)])
        tris.append([idx(n1, i), idx(3 * n1, i + 1), idx(n1, i + 1)])
    # end caps if not full 360
    if abs((a1 - a0) - 2 * np.pi) > 1e-6:
        for i0, i1 in ((0, 2 * n1), (n, 2 * n1 + n)):
            # at angle start (i=0) and end (i=n): quad outer-inner lo-hi
            pass
        # start face (i=0): ri0, ro0, ro1, ri1
        tris.append([0, n1, 3 * n1])
        tris.append([0, 3 * n1, 2 * n1])
        # end face (i=n)
        tris.append([n, 2 * n1 + n, 3 * n1 + n])
        tris.append([n, 3 * n1 + n, n1 + n])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def point_tess(center_mm, marker_mm: float = 1.0) -> PrimitivePart:
    """Small octahedron marker for a Point part."""
    c = np.asarray(center_mm, float) / 1000.0
    s = float(marker_mm) / 1000.0
    pts = np.array([
        c + [s, 0, 0], c + [-s, 0, 0], c + [0, s, 0],
        c + [0, -s, 0], c + [0, 0, s], c + [0, 0, -s],
    ])
    tris = np.array([
        [4, 0, 2], [4, 2, 1], [4, 1, 3], [4, 3, 0],
        [5, 2, 0], [5, 1, 2], [5, 3, 1], [5, 0, 3],
    ], dtype=np.int64)
    return PrimitivePart("", pts, tris)


def annulus_disk_tess(center_mm, outer_r: float, inner_r: float,
                      thickness: float, axis: str = "+Z",
                      divisions: int = 24) -> PrimitivePart:
    """Thick annular disk (Fan / Axial-Flow Fan).

    STpre places the mid-plane of the thickness at ``center`` (flow is
    applied on that mid face).  Local +Z is mapped to the flow axis.
    """
    c = np.asarray(center_mm, float) / 1000.0
    ro = max(float(outer_r), float(inner_r), 1e-9) / 1000.0
    ri = max(min(float(outer_r), float(inner_r)), 0.0) / 1000.0
    if ri >= ro:
        ri = 0.0
    h = max(float(thickness), 1e-3) / 1000.0
    n = max(8, int(divisions))
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    rings = []
    # Mid-plane centred: z ∈ [-h/2, +h/2]
    for z in (-0.5 * h, 0.5 * h):
        for r in (ri if ri > 1e-12 else 0.0, ro):
            rings.append(np.stack(
                [r * np.cos(ang), r * np.sin(ang), np.full(n, z)], 1))
    # order: z0-inner, z0-outer, z1-inner, z1-outer
    local = np.vstack(rings)
    pts = local @ _rotation_to(axis).T + c
    tris = []
    for i in range(n):
        j = (i + 1) % n
        # bottom (-h/2)
        tris += [[i, n + j, n + i], [i, j, n + j]]
        # top (+h/2)
        tris += [[2 * n + i, 3 * n + i, 3 * n + j],
                 [2 * n + i, 3 * n + j, 2 * n + j]]
        # outer wall
        tris += [[n + i, n + j, 3 * n + j], [n + i, 3 * n + j, 3 * n + i]]
        if ri > 1e-12:
            tris += [[i, 2 * n + i, 2 * n + j], [i, 2 * n + j, j]]
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def fan_tess(center_mm, outer_r: float, inner_r: float, thickness: float,
             axis: str = "+Z", divisions: int = 24) -> PrimitivePart:
    """STpre Part(Fan) geometry helper."""
    return annulus_disk_tess(
        center_mm, outer_r, inner_r, thickness, axis, divisions)


def pipe_tess(start_mm, end_mm, radius: float,
              divisions: int = 16) -> PrimitivePart:
    s = np.asarray(start_mm, float)
    e = np.asarray(end_mm, float)
    axis = e - s
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        length = 1.0
        axis = np.array([0.0, 0.0, 1.0])
    # cylinder_tess expects center at bottom + axis direction label; build
    # directly along arbitrary axis.
    c = s / 1000.0
    r = float(radius) / 1000.0
    h = length / 1000.0
    n = max(4, int(divisions))
    rot = _rotation_align(np.array([0.0, 0.0, 1.0]), axis)
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    ring = np.stack([r * np.cos(ang), r * np.sin(ang), np.zeros(n)], 1)
    local = np.vstack([ring, ring + np.array([0.0, 0.0, h])])
    pts = local @ rot.T + c
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + j])
        tris.append([i, n + j, n + i])
    for i in range(1, n - 1):
        tris.append([0, i + 1, i])
        tris.append([n, n + i, n + i + 1])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


# ---------------------------------------------------------------------------
# XML ↔ tess
# ---------------------------------------------------------------------------

def _el_vec(el, tag, default=(0.0, 0.0, 0.0)):
    from cabxml import _first
    c = _first(el, tag)
    if c is None or not c.text:
        return tuple(float(v) for v in default)
    vals = [float(x.strip()) for x in c.text.split(",")[:3]]
    while len(vals) < 3:
        vals.append(0.0)
    return tuple(vals)


def _el_scalar(el, tag, default):
    from cabxml import _first
    c = _first(el, tag)
    if c is None or not c.text:
        return float(default)
    return float(c.text.strip().split(",")[0])


def _el_text(el, tag, default):
    from cabxml import _first
    c = _first(el, tag)
    return c.text.strip() if c is not None and c.text else default


def _el_points(el, tag, n, default_fn):
    from cabxml import _first
    c = _first(el, tag)
    if c is None or not c.text:
        return default_fn()
    vals = [float(x.strip()) for x in c.text.replace(";", ",").split(",")
            if x.strip()]
    if len(vals) < n * 3:
        return default_fn()
    return np.asarray(vals[:n * 3], float).reshape(n, 3)


def tess_for_part(part) -> Optional[PrimitivePart]:
    """Rebuild primitive geometry from a ``PartInfo``-like object."""
    kind = getattr(part, "kind", "body")
    if kind not in PRIMITIVE_KINDS:
        return None
    el = part.elem
    name = getattr(part, "name", "")
    p: Optional[PrimitivePart] = None

    if kind == "sketch":
        # Parametric UV profile — tessellated by cab_sketch.tess_for_sketch_part
        return None
    if kind in ("cube", "blower_fan", "enclosure", "peltier",
                "two_resistor"):
        p = cube_tess(_el_vec(el, "base"),
                      _el_vec(el, "size", (10.0, 10.0, 10.0)))
    elif kind == "plate_fin":
        p = _plate_fin_tess({
            "base": _el_vec(el, "base"),
            "size": _el_vec(el, "size", (10.0, 10.0, 10.0)),
            "fin_count": int(_el_scalar(el, "fin_count", 5)),
            "fin_thickness": _el_scalar(el, "fin_thickness", 0.5),
        })
    elif kind == "pin_fin":
        p = _pin_fin_tess({
            "base": _el_vec(el, "base"),
            "size": _el_vec(el, "size", (10.0, 10.0, 10.0)),
            "pin_nx": int(_el_scalar(el, "pin_nx", 4)),
            "pin_ny": int(_el_scalar(el, "pin_ny", 4)),
            "pin_radius": _el_scalar(el, "pin_radius", 1.0),
        })
    elif kind == "hexahedron":
        pts = _el_points(
            el, "points", 8,
            lambda: _hexa_from_base_size(
                _el_vec(el, "base"), _el_vec(el, "size", (10, 10, 10))))
        p = hexahedron_tess(pts)
    elif kind == "cylinder":
        p = cylinder_tess(
            _el_vec(el, "center"), _el_scalar(el, "radius", 5.0),
            _el_scalar(el, "height", 10.0), _el_text(el, "direction", "+Z"),
            int(_el_scalar(el, "divisions", 24)))
    elif kind == "conical":
        p = conical_tess(
            _el_vec(el, "center1"), _el_vec(el, "center2", (0, 0, 10)),
            _el_scalar(el, "radius1", 5.0), _el_scalar(el, "radius2", 2.0),
            int(_el_scalar(el, "divisions", 24)))
    elif kind == "sphere":
        rv = _el_vec(el, "radius", (5.0, 5.0, 5.0))
        # radius may be scalar stored as single value
        from cabxml import _first
        rc = _first(el, "radius")
        if rc is not None and rc.text and "," not in rc.text:
            r = float(rc.text.strip())
        else:
            r = rv[0] if all(abs(x - rv[0]) < 1e-12 for x in rv) else rv
        p = sphere_tess(_el_vec(el, "center"), r,
                        int(_el_scalar(el, "divisions", 12)))
    elif kind == "panel":
        p = panel_tess(_el_vec(el, "base"),
                       _el_vec(el, "size", (10, 10, 0)),
                       _el_text(el, "direction", "+Z"))
    elif kind == "quad_panel":
        pts = _el_points(
            el, "points", 4,
            lambda: _quad_from_base_size(
                _el_vec(el, "base"), _el_vec(el, "size", (10, 10, 0)),
                _el_text(el, "direction", "+Z")))
        p = quad_panel_tess(pts)
    elif kind == "revolved":
        p = revolved_tess(
            _el_scalar(el, "radius1", 5.0), _el_scalar(el, "radius2", 10.0),
            _el_scalar(el, "angle1", 0.0), _el_scalar(el, "angle2", 360.0),
            _el_scalar(el, "z1", 0.0), _el_scalar(el, "z2", 10.0),
            int(_el_scalar(el, "divisions", 24)))
    elif kind == "point":
        p = point_tess(_el_vec(el, "center"),
                       _el_scalar(el, "marker", 1.0))
    elif kind == "fan":
        from cabxml import _first
        axis = _el_text(el, "direction", "+Z")
        # Prefer explicit STpre fields; fall back to base/size AABB
        if _first(el, "center") is not None:
            center = _el_vec(el, "center")
        else:
            base = _el_vec(el, "base")
            size = _el_vec(el, "size", (10, 10, 2))
            center = (base[0] + size[0] * 0.5, base[1] + size[1] * 0.5,
                      base[2] + size[2] * 0.5)
        outer = _el_scalar(el, "outer_radius", 0.0)
        if outer <= 1e-12:
            size = _el_vec(el, "size", (10, 10, 2))
            ai = int(np.argmax(np.abs(_axis_vector(axis))))
            outer = 0.5 * max(size[(ai + 1) % 3], size[(ai + 2) % 3], 1e-6)
        thick = _el_scalar(el, "thickness", 2.0)
        if thick <= 1e-12:
            size = _el_vec(el, "size", (10, 10, 2))
            ai = int(np.argmax(np.abs(_axis_vector(axis))))
            thick = size[ai] if size[ai] > 1e-12 else 2.0
        p = fan_tess(
            center, outer, _el_scalar(el, "inner_radius", 0.0), thick, axis,
            int(_el_scalar(el, "divisions", 24)))
    elif kind == "axial_fan":
        p = annulus_disk_tess(
            _el_vec(el, "center"),
            _el_scalar(el, "outer_radius", 10.0),
            _el_scalar(el, "inner_radius", 3.0),
            _el_scalar(el, "thickness", 5.0),
            _el_text(el, "direction", "+Z"),
            int(_el_scalar(el, "divisions", 24)))
    elif kind == "pipe":
        p = pipe_tess(
            _el_vec(el, "start"), _el_vec(el, "end", (0, 0, 20)),
            _el_scalar(el, "radius", 2.0),
            int(_el_scalar(el, "divisions", 16)))
    if p is not None:
        p.name = name
    return p


def _hexa_from_base_size(base, size):
    b = np.asarray(base, float)
    s = np.asarray(size, float)
    return np.array([
        [b[0], b[1], b[2]], [b[0] + s[0], b[1], b[2]],
        [b[0] + s[0], b[1] + s[1], b[2]], [b[0], b[1] + s[1], b[2]],
        [b[0], b[1], b[2] + s[2]], [b[0] + s[0], b[1], b[2] + s[2]],
        [b[0] + s[0], b[1] + s[1], b[2] + s[2]],
        [b[0], b[1] + s[1], b[2] + s[2]],
    ])


def _plate_fin_tess(params: dict) -> PrimitivePart:
    """M30: plate-fin proxy = base plate + N thin vertical plates."""
    base = np.asarray(params["base"], float)
    size = np.asarray(params["size"], float)
    n = max(1, int(params.get("fin_count", 5)))
    thick = float(params.get("fin_thickness", max(size[0] / (2 * n), 0.5)))
    parts = [cube_tess(base, size)]
    span = size[0]
    for i in range(n):
        x = base[0] + (i + 0.5) * span / n - thick * 0.5
        parts.append(cube_tess(
            (x, base[1], base[2]),
            (thick, size[1], size[2] * 1.2)))
    return _merge_primitive_parts("plate_fin", parts)


def _pin_fin_tess(params: dict) -> PrimitivePart:
    """M30: pin-fin proxy = base + nx*ny short cylinders as cubes."""
    base = np.asarray(params["base"], float)
    size = np.asarray(params["size"], float)
    nx = max(1, int(params.get("pin_nx", 4)))
    ny = max(1, int(params.get("pin_ny", 4)))
    r = float(params.get("pin_radius", 1.0))
    parts = [cube_tess(base, (size[0], size[1], size[2] * 0.2))]
    for i in range(nx):
        for j in range(ny):
            cx = base[0] + (i + 0.5) * size[0] / nx - r
            cy = base[1] + (j + 0.5) * size[1] / ny - r
            parts.append(cube_tess(
                (cx, cy, base[2] + size[2] * 0.2),
                (2 * r, 2 * r, size[2] * 0.8)))
    return _merge_primitive_parts("pin_fin", parts)


def _merge_primitive_parts(name: str, parts: list) -> PrimitivePart:
    pts = []
    tris = []
    for p in parts:
        off = len(pts)
        pts.extend(np.asarray(p.points).tolist())
        for t in np.asarray(p.triangles):
            tris.append([int(t[0]) + off, int(t[1]) + off, int(t[2]) + off])
    return PrimitivePart(
        name, np.asarray(pts, dtype=np.float64),
        np.asarray(tris, dtype=np.int64))


def _quad_from_base_size(base, size, direction="+Z"):
    pan = panel_tess(base, size, direction)
    return pan.points * 1000.0  # back to mm for reshape path


def primitives_from_model(model: StpreModel) -> list[PrimitivePart]:
    return [p for p in (tess_for_part(pi) for pi in model.parts())
            if p is not None]


def tess_for_spec(kind: str, params: dict) -> PrimitivePart:
    # M30 specialty thermal parts → cuboid / fin array proxies
    if kind in ("cube", "blower_fan", "enclosure", "peltier",
                "two_resistor"):
        return cube_tess(params["base"], params["size"])
    if kind == "sketch":
        # Creation path uses cab_sketch.sketch_tess; keep a cuboid proxy here
        return cube_tess(params["base"], params["size"])
    if kind == "plate_fin":
        return _plate_fin_tess(params)
    if kind == "pin_fin":
        return _pin_fin_tess(params)
    if kind == "hexahedron":
        if "points" in params:
            return hexahedron_tess(params["points"])
        return hexahedron_tess(_hexa_from_base_size(
            params["base"], params["size"]))
    if kind == "cylinder":
        return cylinder_tess(
            params["center"], params["radius"], params["height"],
            params.get("direction", "+Z"), params.get("divisions", 24))
    if kind == "conical":
        return conical_tess(
            params["center1"], params["center2"],
            params["radius1"], params["radius2"],
            params.get("divisions", 24))
    if kind == "sphere":
        return sphere_tess(
            params["center"], params["radius"], params.get("divisions", 12))
    if kind == "panel":
        return panel_tess(params["base"], params["size"],
                          params.get("direction", "+Z"))
    if kind == "quad_panel":
        if "points" in params:
            return quad_panel_tess(params["points"])
        return panel_tess(params["base"], params["size"],
                          params.get("direction", "+Z"))
    if kind == "revolved":
        return revolved_tess(
            params["radius1"], params["radius2"],
            params["angle1"], params["angle2"],
            params["z1"], params["z2"], params.get("divisions", 24))
    if kind == "point":
        return point_tess(params["center"], params.get("marker", 1.0))
    if kind == "fan":
        axis = params.get("direction", "+Z")
        center = params.get("center")
        if center is None:
            base = params["base"]
            size = params["size"]
            center = [base[i] + size[i] * 0.5 for i in range(3)]
        outer = float(params.get("outer_radius", 0.0) or 0.0)
        if outer <= 1e-12:
            size = params.get("size", (10, 10, 2))
            ai = int(np.argmax(np.abs(_axis_vector(axis))))
            outer = 0.5 * max(size[(ai + 1) % 3], size[(ai + 2) % 3], 1e-6)
        thick = float(params.get("thickness", 0.0) or 0.0)
        if thick <= 1e-12:
            size = params.get("size", (10, 10, 2))
            ai = int(np.argmax(np.abs(_axis_vector(axis))))
            thick = size[ai] if size[ai] > 1e-12 else 2.0
        return fan_tess(
            center, outer, params.get("inner_radius", 0.0), thick, axis,
            params.get("divisions", 24))
    if kind == "axial_fan":
        return annulus_disk_tess(
            params["center"], params["outer_radius"],
            params.get("inner_radius", 0.0), params.get("thickness", 5.0),
            params.get("direction", "+Z"), params.get("divisions", 24))
    if kind == "pipe":
        return pipe_tess(params["start"], params["end"], params["radius"],
                         params.get("divisions", 16))
    return cube_tess((0, 0, 0), (10, 10, 10))


def register_primitive(model: StpreModel, *, name: str, kind: str,
                       params: dict, material: str = "",
                       attribute: str = "solid",
                       color: str = "25,117,255,255",
                       layer: str = "1") -> bool:
    """Add a primitive ``<parts>`` entry with its geometry parameters."""
    if kind not in PRIMITIVE_KINDS or model.find_part(name) is not None:
        return False
    el = model.add_part(name=name, kind=kind, property_=material,
                        attribute=attribute, color=color, layer=str(layer))
    if el is None:
        return False
    from cabxml import _first
    import xml.etree.ElementTree as ET

    def add(tag, value, unit=None):
        c = _first(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n         "
        c.text = f" {value} "
        if unit:
            c.attrib["unit"] = unit

    mm = lambda v: ",".join(f"{x:.12g}" for x in np.ravel(v))  # noqa: E731

    if kind in ("cube", "panel", "sketch", "blower_fan",
                "enclosure", "plate_fin", "pin_fin", "peltier",
                "two_resistor"):
        add("base", mm(params["base"]), "mm")
        add("size", mm(params["size"]), "mm")
    if kind == "plate_fin":
        add("fin_count", str(params.get("fin_count", 5)))
        add("fin_thickness", f"{params.get('fin_thickness', 1.0):.12g}")
    if kind == "pin_fin":
        add("pin_nx", str(params.get("pin_nx", 4)))
        add("pin_ny", str(params.get("pin_ny", 4)))
        add("pin_radius", f"{params.get('pin_radius', 1.0):.12g}")
    if kind == "panel":
        add("direction", params.get("direction", "+Z"))
    if kind == "fan":
        # STpre Fan: Center / Size / Outer·Inner radius / Thickness / Condition
        add("center", mm(params.get("center", (0, 0, 0))), "mm")
        add("base", mm(params.get("base", (0, 0, 0))), "mm")
        add("size", mm(params.get("size", (10, 10, 0))), "mm")
        add("direction", params.get("direction", "+Z"))
        add("flow_ui", params.get("flow_ui", "W-Axis(Positive)"))
        add("ref_coord", params.get("ref_coord", "Sketch coordinate system"))
        add("location_mode", params.get("location_mode", "center"))
        add("outer_radius",
            f"{params.get('outer_radius', 5.0):.12g}", "mm")
        add("inner_radius",
            f"{params.get('inner_radius', 0):.12g}", "mm")
        add("thickness",
            f"{params.get('thickness', 2.0):.12g}", "mm")
        add("flow_mode", params.get("flow_mode", "flow_rate"))
        if "flow_rate" in params:
            add("flow_rate", f"{params['flow_rate']:.12g}")
        add("flow_rate_unit", params.get("flow_rate_unit", "m3/s"))
        if "velocity" in params:
            add("velocity", f"{params['velocity']:.12g}")
        add("setting_location", params.get("setting_location", "internal"))
        if "sketch_origin" in params:
            add("sketch_origin", mm(params["sketch_origin"]), "mm")
        add("divisions", str(int(params.get("divisions", 32))))
    if kind == "hexahedron":
        if "points" in params:
            add("points", mm(params["points"]), "mm")
        else:
            add("base", mm(params["base"]), "mm")
            add("size", mm(params["size"]), "mm")
    if kind == "cylinder":
        add("center", mm(params["center"]), "mm")
        add("radius", f"{params['radius']:.12g}")
        add("height", f"{params['height']:.12g}")
        add("direction", params.get("direction", "+Z"))
        add("divisions", str(params.get("divisions", 24)))
    if kind == "conical":
        add("center1", mm(params["center1"]), "mm")
        add("center2", mm(params["center2"]), "mm")
        add("radius1", f"{params['radius1']:.12g}")
        add("radius2", f"{params['radius2']:.12g}")
        add("divisions", str(params.get("divisions", 24)))
    if kind == "sphere":
        add("center", mm(params["center"]), "mm")
        r = params["radius"]
        add("radius", mm(r) if np.size(r) > 1 else f"{float(r):.12g}")
        add("divisions", str(params.get("divisions", 12)))
    if kind == "quad_panel":
        if "points" in params:
            add("points", mm(params["points"]), "mm")
        else:
            add("base", mm(params["base"]), "mm")
            add("size", mm(params["size"]), "mm")
            add("direction", params.get("direction", "+Z"))
    if kind == "revolved":
        for key in ("radius1", "radius2", "angle1", "angle2", "z1", "z2"):
            add(key, f"{params[key]:.12g}")
        add("divisions", str(params.get("divisions", 24)))
    if kind == "point":
        add("center", mm(params["center"]), "mm")
        add("marker", f"{params.get('marker', 1.0):.12g}")
    if kind == "axial_fan":
        add("center", mm(params["center"]), "mm")
        add("outer_radius", f"{params['outer_radius']:.12g}")
        add("inner_radius", f"{params.get('inner_radius', 0):.12g}")
        add("thickness", f"{params.get('thickness', 5):.12g}")
        add("direction", params.get("direction", "+Z"))
        add("divisions", str(params.get("divisions", 24)))
    if kind == "pipe":
        add("start", mm(params["start"]), "mm")
        add("end", mm(params["end"]), "mm")
        add("radius", f"{params['radius']:.12g}")
        add("divisions", str(params.get("divisions", 16)))
    if kind == "sketch":
        add("model_type", params.get("model_type", "extrusion"))
    if kind == "blower_fan":
        add("rotation_axis", params.get("rotation_axis", "+Z"))
    return True


# ---------------------------------------------------------------------------
# Dialog (STpre Part(P) chrome — screenshots + STpreParts_Bx64.dll labels)
# ---------------------------------------------------------------------------

_ORIENT_UI = ["X-direction", "Y-direction", "Z-direction",
              "-X-direction", "-Y-direction", "-Z-direction"]
_ORIENT_TO_AXIS = {
    "X-direction": "+X", "Y-direction": "+Y", "Z-direction": "+Z",
    "-X-direction": "-X", "-Y-direction": "-Y", "-Z-direction": "-Z",
}
_AXIS_TO_ORIENT = {v: k for k, v in _ORIENT_TO_AXIS.items()}
_FLOW_UI = [
    "X-Axis(Positive)", "X-Axis(Negative)",
    "Y-Axis(Positive)", "Y-Axis(Negative)",
    "Z-Axis(Positive)", "Z-Axis(Negative)",
]
_FLOW_UVW_UI = [
    "U-Axis(Positive)", "U-Axis(Negative)",
    "V-Axis(Positive)", "V-Axis(Negative)",
    "W-Axis(Positive)", "W-Axis(Negative)",
]
_FLOW_TO_AXIS = {
    "X-Axis(Positive)": "+X", "X-Axis(Negative)": "-X",
    "Y-Axis(Positive)": "+Y", "Y-Axis(Negative)": "-Y",
    "Z-Axis(Positive)": "+Z", "Z-Axis(Negative)": "-Z",
    "U-Axis(Positive)": "+U", "U-Axis(Negative)": "-U",
    "V-Axis(Positive)": "+V", "V-Axis(Negative)": "-V",
    "W-Axis(Positive)": "+W", "W-Axis(Negative)": "-W",
}

_DEFAULT_NAME = {
    "cube": "Cuboid1", "hexahedron": "Hexahedron1", "cylinder": "Cylinder1",
    "conical": "Cone1", "sphere": "Sphere1", "panel": "Panel1",
    "quad_panel": "QuadPanel1", "revolved": "RevolvedRect1", "point": "Point1",
    "fan": "Fan1", "axial_fan": "FanModel1", "blower_fan": "BlowerFan1",
    "sketch": "SketchPart1", "pipe": "Pipe1",
    "enclosure": "Enclosure1", "plate_fin": "PlateFin1", "pin_fin": "PinFin1",
    "peltier": "Peltier1", "two_resistor": "TwoResistor1",
}
_DEFAULT_COLOR = {
    "cube": (180, 180, 180, 255), "hexahedron": (180, 200, 160, 255),
    "cylinder": (200, 200, 200, 255), "conical": (190, 190, 190, 255),
    "sphere": (190, 190, 190, 255), "panel": (80, 180, 80, 255),
    "quad_panel": (80, 180, 80, 255), "revolved": (180, 180, 180, 255),
    "point": (255, 0, 200, 255), "fan": (255, 140, 0, 255),
    "axial_fan": (255, 160, 40, 255), "blower_fan": (140, 220, 40, 255),
    "sketch": (120, 160, 220, 255), "pipe": (100, 160, 200, 255),
    "enclosure": (160, 160, 200, 255), "plate_fin": (200, 160, 120, 255),
    "pin_fin": (200, 180, 100, 255), "peltier": (120, 200, 160, 255),
    "two_resistor": (180, 140, 200, 255),
}
_ATTRIBUTES = {
    "cube": ["Obstacle", "Solid", "Condition region", "Fluid"],
    "hexahedron": ["Obstacle", "Solid", "Panel", "Condition region",
                   "Condition region face"],
    "cylinder": ["Obstacle", "Solid", "Condition region", "Fluid"],
    "conical": ["Obstacle", "Solid", "Panel", "Condition region",
                "Condition region face"],
    "sphere": ["Obstacle", "Solid", "Panel", "Condition region",
               "Condition region face"],
    "panel": ["Panel", "Condition region face",
              "Particle generation region face"],
    "quad_panel": ["Panel", "Condition region face"],
    "revolved": ["Obstacle", "Solid", "Panel", "Condition region"],
    "point": ["Condition region", "Particle generation region"],
    "fan": ["Fan"],
    "axial_fan": ["Axial flow fan"],
    "blower_fan": ["Blower fan"],
    "sketch": ["Obstacle", "Solid", "Panel", "Condition region"],
    "pipe": ["Obstacle", "Solid", "Panel"],
    "enclosure": ["Obstacle", "Solid", "Condition region"],
    "plate_fin": ["Solid", "Obstacle"],
    "pin_fin": ["Solid", "Obstacle"],
    "peltier": ["Solid"],
    "two_resistor": ["Solid"],
}
_EXTRA_TABS = {
    "cube": ["Particle Generation"],
    "hexahedron": ["Panel Face", "Finite Element Model Division"],
    "conical": ["Finite Element Model Division"],
    "panel": ["Particle Generation"],
    "revolved": ["Panel Face", "Particle Generation"],
    "point": ["Time Series", "Fixed Pressure"],
    "fan": ["Deformer"],
    "blower_fan": ["Face Information"],
    "sketch": ["Size/Attribute"],
    "pipe": ["Size/Attribute"],
}


class CreatePartDialog(QDialog if _HAS_GUI_DEPS else object):
    """STpre ``Part (Cuboid/…)`` creation dialog.

    Layout matches Pre screenshots / ``STpreParts_Bx64.dll`` labels:

    * Tab bar (geometry + optional secondary tabs)
    * Part Name · Color… · Layer
    * Left ``Scale`` · Right ``Attribute/Condition``
    * ``[Preview] [Apply] [OK] [Cancel]``
    """

    preview_requested = pyqtSignal(object) if _HAS_GUI_DEPS else None  # type: ignore

    def __init__(self, model: StpreModel, props, initial_kind: str = "cube",
                 parent=None, single_kind: bool = True):
        super().__init__(parent)
        from cab_dialogs import (
            AttributePanel, ColorButton, CuboidSchematic, FanConditionPanel,
            FanSchematic, MaterialListDialog,
        )
        self.model = model
        self.props = props
        self._kind = initial_kind if initial_kind in PRIMITIVE_KINDS else "cube"
        self._MaterialListDialog = MaterialListDialog
        self._FanSchematic = FanSchematic
        title = KIND_TITLES.get(self._kind, "Part")
        self.setWindowTitle(f"Part ({title})")
        self.resize(820 if self._kind == "fan" else 780,
                    560 if self._kind == "fan" else 520)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self.tabs = QTabWidget(self)
        main = QWidget(self)
        mlay = QVBoxLayout(main)
        mlay.setContentsMargins(6, 6, 6, 6)

        # Part Name / Color / Layer
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Part Name", main))
        self.name_edit = QLineEdit(main)
        self.name_edit.setText(_DEFAULT_NAME.get(self._kind, f"{title}1"))
        nrow.addWidget(self.name_edit, 1)
        self.color_btn = ColorButton(
            _DEFAULT_COLOR.get(self._kind, (25, 117, 255, 255)), main)
        nrow.addWidget(self.color_btn)
        nrow.addWidget(QLabel("Layer", main))
        self.layer_spin = QSpinBox(main)
        self.layer_spin.setRange(1, 999)
        self.layer_spin.setValue(1)
        nrow.addWidget(self.layer_spin)
        mlay.addLayout(nrow)

        cols = QHBoxLayout()
        cols.setSpacing(8)
        self.scale_box = QGroupBox("Scale", main)
        self.scale_lay = QVBoxLayout(self.scale_box)
        self.scale_lay.setSpacing(4)
        cols.addWidget(self.scale_box, 3)

        # STpre Fan uses a dedicated [Condition] panel (not Attribute/Condition)
        self.fan_condition = None
        if self._kind == "fan":
            self.fan_condition = FanConditionPanel(main)
            self.attr_panel = None
            cols.addWidget(self.fan_condition, 2)
        else:
            attrs = _ATTRIBUTES.get(self._kind, ["Obstacle", "Solid"])
            self.attr_panel = AttributePanel(
                main, attributes=attrs, attribute_enabled=True,
                heat_source=True, virtual_part=True, full_stpre=True)
            self.attr_panel.configure_requested.connect(
                self._configure_material)
            if self.props is not None and self.props.material_names():
                mats = self.props.material_names()
                if self._kind in ("axial_fan", "blower_fan"):
                    mat = next(
                        (m for m in mats
                         if "air" in m.lower() and "incompress" in m.lower()),
                        next((m for m in mats if m.lower().startswith("air")),
                             mats[0]))
                else:
                    mat = next((m for m in mats if "obstacle" in m.lower()
                                or m == "Obstacle"), mats[0])
                self.attr_panel.set_material(mat)
            else:
                self.attr_panel.set_material(
                    "air(incompressible/20C)"
                    if self._kind in ("axial_fan", "blower_fan")
                    else "Obstacle")
            cols.addWidget(self.attr_panel, 2)
        mlay.addLayout(cols, 1)

        self.tabs.addTab(main, title)
        for extra in _EXTRA_TABS.get(self._kind, []):
            stub = QLabel(
                f"[{extra}]\n\n"
                f"Secondary tab — settings follow STpre "
                f"[Part] - [{title}] ({extra}).\n"
                f"Geometry is defined on the primary tab.",
                self)
            stub.setAlignment(Qt.AlignCenter)
            stub.setWordWrap(True)
            stub.setStyleSheet("color:#555; padding:16px;")
            self.tabs.addTab(stub, extra)
        # Sketch / Pipe: first tab is workflow page, second is size
        if self._kind == "sketch":
            self.tabs.setTabText(0, "Model Type/Vertex")
        elif self._kind == "pipe":
            self.tabs.setTabText(0, "Center Line of Pipe")
        root.addWidget(self.tabs, 1)

        if self._kind == "fan":
            self._build_fan_scale(self.scale_lay)
        else:
            self._build_scale(self.scale_lay, CuboidSchematic)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_preview = QPushButton("Preview", self)
        self.btn_apply = QPushButton("Apply", self)
        self.btn_ok = QPushButton("OK", self)
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_ok.setDefault(True)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        for b in (self.btn_preview, self.btn_apply, self.btn_ok,
                  self.btn_cancel):
            brow.addWidget(b)
        root.addLayout(brow)

        # Compatibility aliases used by older tests
        self._wire_compat_aliases()

    # -- scale builders ----------------------------------------------------

    def _ref_coord_row(self, lay) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Reference coordinate system", self))
        self.ref_coord = QComboBox(self)
        self.ref_coord.addItem("Global coordinate system")
        self.ref_coord.addItem("Sketch coordinate system")
        try:
            self.ref_coord.model().item(1).setEnabled(False)
        except Exception:
            pass
        row.addWidget(self.ref_coord, 1)
        lay.addLayout(row)

    def _unit_note(self, lay, extra: str = "") -> None:
        lab = QLabel("Unit: mm" + (f"   Notes){extra}" if extra else ""), self)
        lab.setStyleSheet("color:#444; font-size:11px;")
        lay.addWidget(lab)

    def _fan_sync_size_from_outer(self, value: float) -> None:
        """STpre: Size U/V = 2×Outer; Size W = 0 (flow along W)."""
        if not hasattr(self, "_spins"):
            return
        diam = float(value) * 2.0
        for ax, val in (("u", diam), ("v", diam), ("w", 0.0)):
            key = f"Size_{ax}"
            if key not in self._spins:
                # legacy XYZ keys
                key = f"Size_{'xyz'['uvw'.index(ax)]}"
            if key not in self._spins:
                continue
            sb = self._spins[key]
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

    def _build_fan_scale(self, lay) -> None:
        """STpre Part(Fan) Scale: Sketch UVW + Location Center/End point."""
        lay.addWidget(self._FanSchematic(self), 0, Qt.AlignHCenter)

        # Reference coordinate system (Sketch — matches STpre Fan dialog)
        row = QHBoxLayout()
        row.addWidget(QLabel("Reference coordinate system", self))
        self.ref_coord = QComboBox(self)
        self.ref_coord.addItems([
            "Sketch coordinate system", "Global coordinate system"])
        row.addWidget(self.ref_coord, 1)
        lay.addLayout(row)

        form = QFormLayout()
        self.fan_dir = QComboBox(self)
        self.fan_dir.addItems(_FLOW_UVW_UI + _FLOW_UI)
        self.fan_dir.setCurrentText("W-Axis(Positive)")
        form.addRow("Flow direction", self.fan_dir)
        lay.addLayout(form)

        # Location: Center / End point
        loc_box = QGroupBox("Location", self)
        loc_lay = QVBoxLayout(loc_box)
        lrow = QHBoxLayout()
        self.rb_fan_center = QRadioButton("Center", loc_box)
        self.rb_fan_end = QRadioButton("End point", loc_box)
        self.rb_fan_center.setChecked(True)
        self._fan_loc_group = QtWidgets.QButtonGroup(loc_box)
        self._fan_loc_group.addButton(self.rb_fan_center)
        self._fan_loc_group.addButton(self.rb_fan_end)
        lrow.addWidget(self.rb_fan_center)
        lrow.addWidget(self.rb_fan_end)
        lrow.addStretch(1)
        loc_lay.addLayout(lrow)

        grid, self._spins = self._uvw_grid([
            ("Center", (0, 0, 0)), ("Size", (10, 10, 0))])
        loc_lay.addLayout(grid)

        form2 = QFormLayout()
        self.fan_inner = QDoubleSpinBox(self)
        self.fan_inner.setRange(0, 1e6)
        self.fan_inner.setDecimals(4)
        self.fan_inner.setValue(2.5)
        self.fan_outer = QDoubleSpinBox(self)
        self.fan_outer.setRange(1e-6, 1e6)
        self.fan_outer.setDecimals(4)
        self.fan_outer.setValue(5.0)
        self.fan_thick = QDoubleSpinBox(self)
        self.fan_thick.setRange(1e-6, 1e6)
        self.fan_thick.setDecimals(4)
        self.fan_thick.setValue(2.0)
        form2.addRow("Inner radius", self.fan_inner)
        form2.addRow("Outer radius", self.fan_outer)
        form2.addRow("Thickness", self.fan_thick)
        loc_lay.addLayout(form2)
        unit = QLabel("Unit: mm", loc_box)
        unit.setStyleSheet("color:#444; font-size:11px;")
        loc_lay.addWidget(unit)
        lay.addWidget(loc_box)

        # Sketch origin (world XYZ of sketch plane origin)
        org = QHBoxLayout()
        org.addWidget(QLabel("Sketch origin", self))
        self.fan_origin = {}
        try:
            import cab_sketch
            plane = cab_sketch.plane_from_xml(self.model)
            origin = plane.origin
        except Exception:
            origin = (0.0, 0.0, 0.0)
        for i, ax in enumerate("XYZ"):
            org.addWidget(QLabel(ax, self))
            sb = QDoubleSpinBox(self)
            sb.setRange(-1e7, 1e7)
            sb.setDecimals(4)
            sb.setValue(float(origin[i]))
            self.fan_origin[ax.lower()] = sb
            org.addWidget(sb)
        org.addStretch(1)
        lay.addLayout(org)

        self.fan_outer.valueChanged.connect(self._fan_sync_size_from_outer)
        self.ref_coord.currentIndexChanged.connect(self._fan_on_ref_changed)

    def _uvw_grid(self, labels_rows) -> tuple:
        """U/V/W coordinate grid (STpre Sketch Fan)."""
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for i, ax in enumerate("UVW"):
            lab = QLabel(ax, self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, i + 1)
        spins: dict = {}
        for r, (name, defaults) in enumerate(labels_rows, start=1):
            grid.addWidget(QLabel(name, self), r, 0)
            for i, ax in enumerate("uvw"):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(float(defaults[i]))
                sb.setMinimumWidth(70)
                grid.addWidget(sb, r, i + 1)
                spins[f"{name}_{ax}"] = sb
        return grid, spins

    def _fan_on_ref_changed(self) -> None:
        """Toggle Flow direction labels for Sketch vs Global."""
        sketch = "Sketch" in self.ref_coord.currentText()
        cur = self.fan_dir.currentText()
        self.fan_dir.blockSignals(True)
        self.fan_dir.clear()
        self.fan_dir.addItems(_FLOW_UVW_UI if sketch else _FLOW_UI)
        # map W↔Z, U↔X, V↔Y when switching
        swap = {
            "W-Axis(Positive)": "Z-Axis(Positive)",
            "W-Axis(Negative)": "Z-Axis(Negative)",
            "U-Axis(Positive)": "X-Axis(Positive)",
            "U-Axis(Negative)": "X-Axis(Negative)",
            "V-Axis(Positive)": "Y-Axis(Positive)",
            "V-Axis(Negative)": "Y-Axis(Negative)",
        }
        inv = {v: k for k, v in swap.items()}
        target = (cur if (sketch and cur in _FLOW_UVW_UI)
                  or (not sketch and cur in _FLOW_UI)
                  else (inv.get(cur) if sketch else swap.get(cur)))
        if target:
            i = self.fan_dir.findText(target)
            if i >= 0:
                self.fan_dir.setCurrentIndex(i)
        elif sketch:
            self.fan_dir.setCurrentText("W-Axis(Positive)")
        else:
            self.fan_dir.setCurrentText("Z-Axis(Positive)")
        self.fan_dir.blockSignals(False)

    def _xyz_grid(self, labels_rows) -> tuple[QGridLayout, dict]:
        """Build X/Y/Z grid. ``labels_rows`` = list of (row_label, defaults)."""
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for i, ax in enumerate("XYZ"):
            lab = QLabel(ax, self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, i + 1)
        spins: dict[str, QDoubleSpinBox] = {}
        for r, (name, defaults) in enumerate(labels_rows, start=1):
            grid.addWidget(QLabel(name, self), r, 0)
            for i, ax in enumerate("xyz"):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(float(defaults[i]))
                sb.setMinimumWidth(70)
                grid.addWidget(sb, r, i + 1)
                spins[f"{name}_{ax}"] = sb
        return grid, spins

    def _build_scale(self, lay, CuboidSchematic) -> None:
        kind = self._kind
        if kind in ("cube", "hexahedron", "blower_fan", "sketch",
                    "enclosure", "plate_fin", "pin_fin", "peltier",
                    "two_resistor"):
            lay.addWidget(CuboidSchematic(self, face="#cfe8a9"), 0,
                          Qt.AlignHCenter)
        elif kind in ("panel", "quad_panel"):
            lay.addWidget(CuboidSchematic(self, face="#90d090"), 0,
                          Qt.AlignHCenter)
        else:
            lay.addWidget(CuboidSchematic(self, face="#c8d8e8"), 0,
                          Qt.AlignHCenter)

        if kind == "hexahedron":
            asst = QHBoxLayout()
            asst.addWidget(QLabel("Input assistance", self))
            self.input_assist = QComboBox(self)
            self.input_assist.addItems(
                ["8-point input", "2-point input", "Location/size input"])
            asst.addWidget(self.input_assist, 1)
            lay.addLayout(asst)
        elif kind == "quad_panel":
            asst = QHBoxLayout()
            asst.addWidget(QLabel("Input assistance", self))
            self.input_assist = QComboBox(self)
            self.input_assist.addItems(
                ["4-point input", "2-point input", "Location/size input"])
            asst.addWidget(self.input_assist, 1)
            lay.addLayout(asst)

        self._ref_coord_row(lay)

        if kind in ("cube", "enclosure", "plate_fin", "pin_fin", "peltier",
                    "two_resistor"):
            grid, self._spins = self._xyz_grid([
                ("Location", (0, 0, 0)), ("Size", (10, 10, 10))])
            lay.addLayout(grid)
            self._unit_note(lay)
            # compat
            self.cube_base = {f"base_{a}": self._spins[f"Location_{a}"]
                              for a in "xyz"}
            self.cube_size = {f"size_{a}": self._spins[f"Size_{a}"]
                              for a in "xyz"}
            if kind == "plate_fin":
                self.fin_count = QSpinBox(self)
                self.fin_count.setRange(1, 200)
                self.fin_count.setValue(5)
                fr = QHBoxLayout()
                fr.addWidget(QLabel("Fin count", self))
                fr.addWidget(self.fin_count)
                lay.addLayout(fr)
            if kind == "pin_fin":
                self.pin_nx = QSpinBox(self)
                self.pin_ny = QSpinBox(self)
                for w in (self.pin_nx, self.pin_ny):
                    w.setRange(1, 50)
                    w.setValue(4)
                pr = QHBoxLayout()
                pr.addWidget(QLabel("Pin nx/ny", self))
                pr.addWidget(self.pin_nx)
                pr.addWidget(self.pin_ny)
                lay.addLayout(pr)

        elif kind == "hexahedron":
            self.hexa_table = QTableWidget(8, 3, self)
            self.hexa_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
            self.hexa_table.setVerticalHeaderLabels(
                [f"Point{i}" for i in range(1, 9)])
            defaults = [
                (0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
                (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10),
            ]
            for r, pt in enumerate(defaults):
                for c, v in enumerate(pt):
                    self.hexa_table.setItem(
                        r, c, QTableWidgetItem(f"{v:g}"))
            self.hexa_table.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(self.hexa_table, 1)
            self._unit_note(lay)
            # location/size compat hidden defaults
            self.hexa_base = {f"base_{a}": _FakeSpin(0) for a in "xyz"}
            self.hexa_size = {f"size_{a}": _FakeSpin(10) for a in "xyz"}

        elif kind == "cylinder":
            grid, self._spins = self._xyz_grid([("Center", (0, 0, 0))])
            lay.addLayout(grid)
            form = QFormLayout()
            self.cyl_radius = QDoubleSpinBox(self)
            self.cyl_radius.setRange(1e-6, 1e6)
            self.cyl_radius.setValue(5.0)
            self.cyl_height = QDoubleSpinBox(self)
            self.cyl_height.setRange(1e-6, 1e7)
            self.cyl_height.setValue(10.0)
            self.cyl_axis = QComboBox(self)
            self.cyl_axis.addItems(_ORIENT_UI)
            self.cyl_axis.setCurrentText("Z-direction")
            self.cyl_div = QSpinBox(self)
            self.cyl_div.setRange(4, 360)
            self.cyl_div.setValue(48)
            form.addRow("Radius", self.cyl_radius)
            form.addRow("Height", self.cyl_height)
            form.addRow("Orientation", self.cyl_axis)
            form.addRow("The number of divisions of circle", self.cyl_div)
            lay.addLayout(form)
            self._unit_note(lay)
            self.cyl_center = {f"center_{a}": self._spins[f"Center_{a}"]
                               for a in "xyz"}

        elif kind == "conical":
            grid, self._spins = self._xyz_grid([
                ("Center1", (0, 0, 0)), ("Center2", (0, 0, 10)),
                ("Start direction", (1, 0, 0))])
            lay.addLayout(grid)
            form = QFormLayout()
            self.cone_r1 = QDoubleSpinBox(self)
            self.cone_r1.setRange(0, 1e6)
            self.cone_r1.setValue(10.0)
            self.cone_r2 = QDoubleSpinBox(self)
            self.cone_r2.setRange(0, 1e6)
            self.cone_r2.setValue(5.0)
            self.cone_a1 = QDoubleSpinBox(self)
            self.cone_a1.setRange(-3600, 3600)
            self.cone_a1.setValue(0)
            self.cone_a2 = QDoubleSpinBox(self)
            self.cone_a2.setRange(-3600, 3600)
            self.cone_a2.setValue(360)
            self.cone_div = QSpinBox(self)
            self.cone_div.setRange(4, 360)
            self.cone_div.setValue(48)
            form.addRow("Radius1", self.cone_r1)
            form.addRow("Radius2", self.cone_r2)
            form.addRow("Start angle", self.cone_a1)
            form.addRow("End angle", self.cone_a2)
            form.addRow("The number of divisions of circle", self.cone_div)
            lay.addLayout(form)
            self._unit_note(lay, "Angle:degrees")
            self.cone_c1 = {f"c1_{a}": self._spins[f"Center1_{a}"]
                            for a in "xyz"}
            self.cone_c2 = {f"c2_{a}": self._spins[f"Center2_{a}"]
                            for a in "xyz"}

        elif kind == "sphere":
            grid, self._spins = self._xyz_grid([
                ("Center", (0, 0, 0)), ("Radius", (10, 10, 10))])
            lay.addLayout(grid)
            self.sph_oval = QCheckBox("Oval sphere", self)
            lay.addWidget(self.sph_oval)
            form = QFormLayout()
            self.sph_axis = QComboBox(self)
            self.sph_axis.addItems(_ORIENT_UI)
            self.sph_axis.setCurrentText("Z-direction")
            self.sph_a1 = QDoubleSpinBox(self)
            self.sph_a1.setRange(-3600, 3600)
            self.sph_a1.setValue(0)
            self.sph_a2 = QDoubleSpinBox(self)
            self.sph_a2.setRange(-3600, 3600)
            self.sph_a2.setValue(360)
            self.sph_div = QSpinBox(self)
            self.sph_div.setRange(4, 180)
            self.sph_div.setValue(48)
            self.sph_radius = self._spins["Radius_x"]  # compat scalar
            form.addRow("Axis of rotation", self.sph_axis)
            form.addRow("Start angle", self.sph_a1)
            form.addRow("End angle", self.sph_a2)
            form.addRow("The number of divisions of circle", self.sph_div)
            lay.addLayout(form)
            self._unit_note(lay, "Angle:degrees")
            self.sph_center = {f"center_{a}": self._spins[f"Center_{a}"]
                               for a in "xyz"}

        elif kind == "panel":
            grid, self._spins = self._xyz_grid([
                ("Location", (0, 0, 0)), ("Size", (10, 10, 10))])
            lay.addLayout(grid)
            self.panel_dir = QComboBox(self)
            self.panel_dir.addItems(_ORIENT_UI)
            self.panel_dir.setCurrentText("Z-direction")
            form = QFormLayout()
            form.addRow("Direction", self.panel_dir)
            lay.addLayout(form)
            self._unit_note(lay)
            self.panel_base = {f"base_{a}": self._spins[f"Location_{a}"]
                               for a in "xyz"}
            self.panel_size = {f"size_{a}": self._spins[f"Size_{a}"]
                               for a in "xyz"}

        elif kind == "quad_panel":
            self.quad_table = QTableWidget(4, 3, self)
            self.quad_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
            self.quad_table.setVerticalHeaderLabels(
                [f"Point {i}" for i in range(1, 5)])
            defaults = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
            for r, pt in enumerate(defaults):
                for c, v in enumerate(pt):
                    self.quad_table.setItem(
                        r, c, QTableWidgetItem(f"{v:g}"))
            lay.addWidget(self.quad_table, 1)
            self._unit_note(lay)

        elif kind == "revolved":
            form = QFormLayout()
            self.rev_r1 = QDoubleSpinBox(self)
            self.rev_r1.setRange(0, 1e6)
            self.rev_r1.setValue(15)
            self.rev_r2 = QDoubleSpinBox(self)
            self.rev_r2.setRange(0, 1e6)
            self.rev_r2.setValue(25)
            self.rev_a1 = QDoubleSpinBox(self)
            self.rev_a1.setRange(-3600, 3600)
            self.rev_a1.setValue(0)
            self.rev_a2 = QDoubleSpinBox(self)
            self.rev_a2.setRange(-3600, 3600)
            self.rev_a2.setValue(90)
            self.rev_z1 = QDoubleSpinBox(self)
            self.rev_z1.setRange(-1e6, 1e6)
            self.rev_z1.setValue(0)
            self.rev_z2 = QDoubleSpinBox(self)
            self.rev_z2.setRange(-1e6, 1e6)
            self.rev_z2.setValue(10)
            self.rev_div = QSpinBox(self)
            self.rev_div.setRange(4, 360)
            self.rev_div.setValue(32)
            form.addRow("Radius1", self.rev_r1)
            form.addRow("Radius2", self.rev_r2)
            form.addRow("Start angle", self.rev_a1)
            form.addRow("End angle", self.rev_a2)
            form.addRow("Z1", self.rev_z1)
            form.addRow("Z2", self.rev_z2)
            form.addRow("The number of divisions of circle", self.rev_div)
            lay.addLayout(form)
            self._unit_note(lay, "Angle:degrees")

        elif kind == "point":
            form = QFormLayout()
            self.pt_input = QComboBox(self)
            self.pt_input.addItems(["X-Y-Z input", "R-Theta-Z input"])
            form.addRow("Input type", self.pt_input)
            lay.addLayout(form)
            grid, self._spins = self._xyz_grid([("Location", (0, 0, 0))])
            lay.addLayout(grid)
            self.pt_marker = QDoubleSpinBox(self)
            self.pt_marker.setRange(1e-3, 1e4)
            self.pt_marker.setValue(1.0)
            self.pt_center = {f"center_{a}": self._spins[f"Location_{a}"]
                              for a in "xyz"}
            self._unit_note(lay)

        elif kind == "fan":
            # Built by _build_fan_scale (Sketch UVW layout)
            pass

        elif kind == "axial_fan":
            form = QFormLayout()
            self.af_shape = QComboBox(self)
            self.af_shape.addItems(
                ["Open rectangle", "Square", "Round"])
            self.af_dir = QComboBox(self)
            self.af_dir.addItems(_FLOW_UI)
            self.af_dir.setCurrentText("Z-Axis(Positive)")
            form.addRow("Shape", self.af_shape)
            form.addRow("Flow direction", self.af_dir)
            lay.addLayout(form)
            grid, self._spins = self._xyz_grid([("Center", (0, 0, 0))])
            lay.addLayout(grid)
            form2 = QFormLayout()
            self.af_sx = QDoubleSpinBox(self)
            self.af_sx.setRange(1e-6, 1e6)
            self.af_sx.setValue(10)
            self.af_sy = QDoubleSpinBox(self)
            self.af_sy.setRange(1e-6, 1e6)
            self.af_sy.setValue(10)
            self.af_thick = QDoubleSpinBox(self)
            self.af_thick.setRange(1e-6, 1e6)
            self.af_thick.setValue(10)
            self.af_outer = QDoubleSpinBox(self)
            self.af_outer.setRange(1e-6, 1e6)
            self.af_outer.setValue(5)
            self.af_inner = QDoubleSpinBox(self)
            self.af_inner.setRange(0, 1e6)
            self.af_inner.setValue(0)
            form2.addRow("Size X", self.af_sx)
            form2.addRow("Size Y", self.af_sy)
            form2.addRow("Thickness", self.af_thick)
            form2.addRow("Outer radius", self.af_outer)
            form2.addRow("Inner radius", self.af_inner)
            lay.addLayout(form2)
            self.af_frame = QCheckBox("Outer frame", self)
            lay.addWidget(self.af_frame)
            self._unit_note(lay)
            self.af_center = {f"center_{a}": self._spins[f"Center_{a}"]
                              for a in "xyz"}

        elif kind == "blower_fan":
            form = QFormLayout()
            self.bl_axis = QComboBox(self)
            self.bl_axis.addItems(_ORIENT_UI)
            self.bl_axis.setCurrentText("Z-direction")
            form.addRow("Axis of rotation", self.bl_axis)
            lay.addLayout(form)
            grid, self._spins = self._xyz_grid([
                ("Location", (0, 0, 0)), ("Size", (10, 10, 10))])
            lay.addLayout(grid)
            self._unit_note(lay)
            self.bl_base = {f"base_{a}": self._spins[f"Location_{a}"]
                            for a in "xyz"}
            self.bl_size = {f"size_{a}": self._spins[f"Size_{a}"]
                            for a in "xyz"}

        elif kind == "sketch":
            form = QFormLayout()
            self.sk_type = QComboBox(self)
            self.sk_type.addItems([
                "Extrusion", "Panel", "Cutout", "Revolved Body", "Fan",
                "Axial flow fan"])
            form.addRow("(1) Model type", self.sk_type)
            self.sk_geom = QComboBox(self)
            self.sk_geom.addItems(["Point sequence", "Regular polygon"])
            form.addRow("(3) Geometry type of vertex", self.sk_geom)
            lay.addLayout(form)
            tip = QLabel(
                "(4) Vertices — enter a rectangular UV profile below "
                "(simplified; full sketch plane editing is STpre-only).",
                self)
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#555;")
            lay.addWidget(tip)
            grid, self._spins = self._xyz_grid([
                ("Location", (0, 0, 0)), ("Size", (10, 10, 10))])
            lay.addLayout(grid)
            self._unit_note(lay, "Angle:degrees")
            self.sk_base = {f"base_{a}": self._spins[f"Location_{a}"]
                            for a in "xyz"}
            self.sk_size = {f"size_{a}": self._spins[f"Size_{a}"]
                            for a in "xyz"}

        elif kind == "pipe":
            tip = QLabel(
                "Points on center line — enter start/end (multi-point "
                "polyline editing follows STpre [Part]-[Pipe Part]).",
                self)
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#555;")
            lay.addWidget(tip)
            grid, self._spins = self._xyz_grid([
                ("Start", (0, 0, 0)), ("End", (0, 0, 20))])
            lay.addLayout(grid)
            form = QFormLayout()
            self.pipe_r = QDoubleSpinBox(self)
            self.pipe_r.setRange(1e-6, 1e6)
            self.pipe_r.setValue(2.0)
            self.pipe_div = QSpinBox(self)
            self.pipe_div.setRange(4, 360)
            self.pipe_div.setValue(16)
            form.addRow("Radius", self.pipe_r)
            form.addRow("The number of divisions of circle", self.pipe_div)
            lay.addLayout(form)
            self._unit_note(lay, "Angle:degrees")
            self.pipe_start = {f"start_{a}": self._spins[f"Start_{a}"]
                               for a in "xyz"}
            self.pipe_end = {f"end_{a}": self._spins[f"End_{a}"]
                             for a in "xyz"}

        lay.addStretch(1)

    def _wire_compat_aliases(self) -> None:
        """Keep attribute names expected by existing unit tests."""
        pass

    def _configure_material(self) -> None:
        if self.attr_panel is None:
            return
        dlg = self._MaterialListDialog(
            self.props, self,
            current=self.attr_panel.material_name(),
            part_name=self.name_edit.text().strip())
        if dlg.exec_() and dlg.selected_material():
            self.attr_panel.set_material(dlg.selected_material())

    def _fan_world_center_and_axis(self) -> tuple[tuple, str]:
        """Map Fan UVW (or XYZ) Center + flow direction → world center / axis."""
        sketch = ("Sketch" in self.ref_coord.currentText()
                  if hasattr(self, "ref_coord") else True)
        if sketch and "Center_u" in self._spins:
            cu = self._spins["Center_u"].value()
            cv = self._spins["Center_v"].value()
            cw = self._spins["Center_w"].value()
            try:
                import cab_sketch
                plane = cab_sketch.plane_from_xml(self.model)
                # Prefer dialog Sketch origin if edited
                o = np.array([
                    self.fan_origin["x"].value(),
                    self.fan_origin["y"].value(),
                    self.fan_origin["z"].value()], float)
                u = np.asarray(plane.u, float)
                v = np.asarray(plane.v, float)
                w = np.asarray(plane.w, float)
                for vec in (u, v, w):
                    n = np.linalg.norm(vec)
                    if n > 1e-12:
                        vec /= n
                center = tuple(o + cu * u + cv * v + cw * w)
            except Exception:
                center = (cu, cv, cw)
            flow = self.fan_dir.currentText()
            # UVW flow → world axis from sketch plane
            try:
                import cab_sketch
                plane = cab_sketch.plane_from_xml(self.model)
                mapping = {
                    "+U": plane.u, "-U": tuple(-x for x in plane.u),
                    "+V": plane.v, "-V": tuple(-x for x in plane.v),
                    "+W": plane.w, "-W": tuple(-x for x in plane.w),
                }
                key = _FLOW_TO_AXIS.get(flow, "+W")
                direction = mapping.get(key, plane.w)
                # pick nearest global axis label for storage / tess
                d = np.asarray(direction, float)
                d = d / (np.linalg.norm(d) or 1.0)
                absd = np.abs(d)
                ai = int(np.argmax(absd))
                sign = "+" if d[ai] >= 0 else "-"
                axis = f"{sign}{'XYZ'[ai]}"
            except Exception:
                axis = "+Z"
            # End point: shift by half thickness along flow
            if getattr(self, "rb_fan_end", None) and self.rb_fan_end.isChecked():
                thick = self.fan_thick.value()
                try:
                    key = _FLOW_TO_AXIS.get(flow, "+W")
                    import cab_sketch
                    plane = cab_sketch.plane_from_xml(self.model)
                    vecs = {"+U": plane.u, "-U": tuple(-x for x in plane.u),
                            "+V": plane.v, "-V": tuple(-x for x in plane.v),
                            "+W": plane.w, "-W": tuple(-x for x in plane.w)}
                    fw = np.asarray(vecs.get(key, plane.w), float)
                    fw = fw / (np.linalg.norm(fw) or 1.0)
                    center = tuple(np.asarray(center) + fw * (thick * 0.5))
                except Exception:
                    pass
            return center, axis
        # Global XYZ path
        c = (self._spins["Center_x"].value(),
             self._spins["Center_y"].value(),
             self._spins["Center_z"].value())
        axis = _FLOW_TO_AXIS.get(self.fan_dir.currentText(), "+Z")
        if axis.startswith(("+", "-")) and axis[1] in "UVW":
            axis = "+Z"
        return c, axis

    def _table_points(self, table: "QTableWidget") -> list:
        pts = []
        for r in range(table.rowCount()):
            row = []
            for c in range(3):
                item = table.item(r, c)
                row.append(float(item.text()) if item and item.text() else 0.0)
            pts.append(row)
        return pts

    def _on_preview(self) -> None:
        if self.preview_requested is not None:
            try:
                self.preview_requested.emit(self.spec())
            except Exception:
                pass

    def _on_apply(self) -> None:
        self._on_preview()

    def current_kind(self) -> str:
        return self._kind

    def spec(self) -> dict:
        kind = self._kind
        params: dict = {}

        def xyz(spins, prefix):
            return tuple(spins[f"{prefix}_{a}"].value() for a in "xyz")

        if kind in ("cube", "enclosure", "plate_fin", "pin_fin", "peltier",
                    "two_resistor"):
            params["base"] = xyz(self.cube_base, "base")
            params["size"] = xyz(self.cube_size, "size")
            if kind == "plate_fin" and hasattr(self, "fin_count"):
                params["fin_count"] = self.fin_count.value()
            if kind == "pin_fin":
                if hasattr(self, "pin_nx"):
                    params["pin_nx"] = self.pin_nx.value()
                    params["pin_ny"] = self.pin_ny.value()
        elif kind == "hexahedron":
            params["points"] = self._table_points(self.hexa_table)
        elif kind == "cylinder":
            params["center"] = xyz(self.cyl_center, "center")
            params["radius"] = self.cyl_radius.value()
            params["height"] = self.cyl_height.value()
            params["direction"] = _ORIENT_TO_AXIS.get(
                self.cyl_axis.currentText(), "+Z")
            params["divisions"] = self.cyl_div.value()
        elif kind == "conical":
            params["center1"] = xyz(self.cone_c1, "c1")
            params["center2"] = xyz(self.cone_c2, "c2")
            params["radius1"] = self.cone_r1.value()
            params["radius2"] = self.cone_r2.value()
            params["angle1"] = self.cone_a1.value()
            params["angle2"] = self.cone_a2.value()
            params["divisions"] = self.cone_div.value()
        elif kind == "sphere":
            params["center"] = xyz(self.sph_center, "center")
            if self.sph_oval.isChecked():
                params["radius"] = (
                    self._spins["Radius_x"].value(),
                    self._spins["Radius_y"].value(),
                    self._spins["Radius_z"].value())
            else:
                params["radius"] = self._spins["Radius_x"].value()
            params["divisions"] = self.sph_div.value()
        elif kind == "panel":
            params["base"] = xyz(self.panel_base, "base")
            params["size"] = xyz(self.panel_size, "size")
            params["direction"] = _ORIENT_TO_AXIS.get(
                self.panel_dir.currentText(), "+Z")
        elif kind == "quad_panel":
            params["points"] = self._table_points(self.quad_table)
        elif kind == "revolved":
            params.update({
                "radius1": self.rev_r1.value(),
                "radius2": self.rev_r2.value(),
                "angle1": self.rev_a1.value(),
                "angle2": self.rev_a2.value(),
                "z1": self.rev_z1.value(),
                "z2": self.rev_z2.value(),
                "divisions": self.rev_div.value(),
            })
        elif kind == "point":
            params["center"] = xyz(self.pt_center, "center")
            params["marker"] = self.pt_marker.value()
        elif kind == "fan":
            # STpre Sketch Fan: UVW Center/Size → world center + flow axis
            c, axis = self._fan_world_center_and_axis()
            if "Size_u" in self._spins:
                s = (self._spins["Size_u"].value(),
                     self._spins["Size_v"].value(),
                     self._spins["Size_w"].value())
            else:
                s = xyz(self._spins, "Size")
            outer = float(self.fan_outer.value())
            inner = min(float(self.fan_inner.value()), outer)
            thick = float(self.fan_thick.value())
            ai = {"+X": 0, "-X": 0, "+Y": 1, "-Y": 1, "+Z": 2, "-Z": 2}[axis]
            bbox = [outer * 2, outer * 2, outer * 2]
            if "Size_u" in self._spins:
                bbox[0] = s[0] if s[0] > 1e-12 else outer * 2
                bbox[1] = s[1] if s[1] > 1e-12 else outer * 2
            bbox[ai] = thick
            base = [c[i] - bbox[i] * 0.5 for i in range(3)]
            params["center"] = tuple(float(x) for x in c)
            params["base"] = tuple(base)
            params["size"] = tuple(s)
            params["bbox_size"] = tuple(bbox)
            params["direction"] = axis
            params["flow_ui"] = self.fan_dir.currentText()
            params["ref_coord"] = self.ref_coord.currentText()
            params["location_mode"] = (
                "end" if self.rb_fan_end.isChecked() else "center")
            params["outer_radius"] = outer
            params["inner_radius"] = inner
            params["thickness"] = thick
            params["divisions"] = 32
            if self.fan_condition is not None:
                params.update(self.fan_condition.values())
            else:
                params["flow_rate"] = 1.0
                params["flow_rate_unit"] = "m3/s"
            if hasattr(self, "fan_origin"):
                params["sketch_origin"] = (
                    self.fan_origin["x"].value(),
                    self.fan_origin["y"].value(),
                    self.fan_origin["z"].value())
        elif kind == "axial_fan":
            params["center"] = xyz(self.af_center, "center")
            params["outer_radius"] = self.af_outer.value()
            params["inner_radius"] = self.af_inner.value()
            params["thickness"] = self.af_thick.value()
            params["direction"] = _FLOW_TO_AXIS.get(
                self.af_dir.currentText(), "+Z")
            params["size_x"] = self.af_sx.value()
            params["size_y"] = self.af_sy.value()
        elif kind == "blower_fan":
            params["base"] = xyz(self.bl_base, "base")
            params["size"] = xyz(self.bl_size, "size")
            params["rotation_axis"] = _ORIENT_TO_AXIS.get(
                self.bl_axis.currentText(), "+Z")
        elif kind == "sketch":
            params["base"] = xyz(self.sk_base, "base")
            params["size"] = xyz(self.sk_size, "size")
            params["model_type"] = self.sk_type.currentText().lower().replace(
                " ", "_")
        elif kind == "pipe":
            params["start"] = xyz(self.pipe_start, "start")
            params["end"] = xyz(self.pipe_end, "end")
            params["radius"] = self.pipe_r.value()
            params["divisions"] = self.pipe_div.value()

        rgba = self.color_btn.rgba()
        if kind == "fan" and self.fan_condition is not None:
            cond = self.fan_condition.values()
            attribute = "Fan"
            material = "air(incompressible/20C)"
            if self.props is not None and self.props.material_names():
                mats = self.props.material_names()
                material = next(
                    (m for m in mats
                     if "air" in m.lower() and "incompress" in m.lower()),
                    next((m for m in mats if m.lower().startswith("air")),
                         mats[0]))
            monitor = False
            virtual = bool(cond.get("virtual"))
        else:
            attribute = self.attr_panel.attribute.currentText()
            material = self.attr_panel.material_name()
            monitor = self.attr_panel.monitor()
            virtual = bool(
                self.attr_panel.virtual_chk
                and self.attr_panel.virtual_chk.isChecked())
        return {
            "name": self.name_edit.text().strip(),
            "kind": kind,
            "params": params,
            "attribute": attribute,
            "material": material,
            "color": ",".join(str(v) for v in rgba),
            "layer": str(self.layer_spin.value()),
            "monitor": monitor,
            "virtual": virtual,
        }


class _FakeSpin:
    """Tiny stand-in so unused compat dicts still expose ``.value()``."""

    def __init__(self, v: float):
        self._v = float(v)

    def value(self) -> float:
        return self._v

    def setValue(self, v: float) -> None:
        self._v = float(v)
