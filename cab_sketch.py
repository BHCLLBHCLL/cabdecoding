"""M8: STpre-like sketch plane and sketch part support.

Reference: Pre_eng manual
(Define_and_modify_the_sketch_plane / Control_Window_-_Sketch /
Edit_sketch_plane_dialog / Sketch_part / Part-Sketch_Part_Model_Type_is_*)
and the ``sketch_control`` XML member of official cab files:

.. code-block:: xml

   <sketch_control>
      <system unit="mm">
         <c> -100,-100,-100.1375493649 </c>   <!-- origin, mm -->
         <u> 1,0,0 </u><v> 0,1,0 </v><w> 0,0,1 </w>
      </system>
      <grid>
         <u_range> -0.0625,0.3125 </u_range>   <!-- metres -->
         <v_range> -0.0995388,0.497694 </v_range>
         <w_range> -0.103784,0.518922 </w_range>
         <delta> 0.0125,0.019907764064044,0.020756877468245 </delta>
         <snap> 0.0125,... </snap>
      </grid>
      <gridsnap> T </gridsnap><minus> F </minus>
      <color> 170,170,170,255 </color>
   </sketch_control>

Sketch parts (``<parts type="sketch">``) store a 2D profile on the sketch
plane (point sequence / rectangle / circle) and a model type (Panel /
Extrusion); the tessellation used for 3D and meshing is generated from the
profile + sketch plane, so no ``.x_t`` member is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from cabxml import StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
        QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
        QPushButton, QRadioButton, QSpinBox, QTabWidget, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
    try:
        from cab_widgets import CoordSpinBox
        QDoubleSpinBox = CoordSpinBox
    except Exception:
        pass
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless
    _HAS_GUI_DEPS = False
    QDialog = object  # type: ignore
    QDoubleSpinBox = object  # type: ignore
    QWidget = object  # type: ignore
    pyqtSignal = lambda *a, **k: None  # type: ignore


@dataclass
class SketchPlane:
    """Sketch coordinate system + grid (XML ``<sketch_control>``)."""

    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)   # mm
    u: tuple[float, float, float] = (1.0, 0.0, 0.0)
    v: tuple[float, float, float] = (0.0, 1.0, 0.0)
    w: tuple[float, float, float] = (0.0, 0.0, 1.0)
    # STpre new-project defaults (Control→Sketch / Grid, unit mm):
    #   interval=5, Minimum=-25, Maximum=125, Snap=5
    u_range: tuple[float, float] = (-0.025, 0.125)         # m
    v_range: tuple[float, float] = (-0.025, 0.125)
    w_range: tuple[float, float] = (-0.025, 0.125)
    delta: tuple[float, float, float] = (0.005, 0.005, 0.005)  # m
    snap: tuple[float, float, float] = (0.005, 0.005, 0.005)
    gridsnap: bool = True
    minus: bool = False
    color: tuple[int, int, int, int] = (160, 160, 160, 255)


def default_sketch_plane(model: Optional[StpreModel] = None) -> SketchPlane:
    """STpre startup Sketch Plane (origin on domain Zmin when available)."""
    p = SketchPlane()
    if model is not None:
        base = model.domain_base()
        if base is not None:
            p.origin = (0.0, 0.0, float(base[2]))
    return p


def _first(el, tag):
    from cabxml import _first as f
    return f(el, tag)


def _vec(el, tag, default) -> tuple:
    c = _first(el, tag)
    if c is None or not c.text:
        return tuple(float(v) for v in default)
    vals = [float(x.strip()) for x in c.text.split(",")]
    return tuple(vals)


def _set_vec(parent, tag, vals, unit=None) -> None:
    import xml.etree.ElementTree as ET
    from cabxml import set_text
    c = _first(parent, tag)
    if c is None:
        c = ET.SubElement(parent, tag)
        c.tail = "\n      "
    set_text(c, ",".join(f"{v:.17g}" for v in vals))
    if unit:
        c.attrib["unit"] = unit


def plane_from_xml(model: StpreModel) -> SketchPlane:
    """Read ``<sketch_control>``; returns defaults when missing."""
    sc = _first(model.root, "sketch_control")
    p = SketchPlane()
    if sc is None:
        return p
    sys_ = _first(sc, "system")
    if sys_ is not None:
        p.origin = _vec(sys_, "c", p.origin)
        p.u = _vec(sys_, "u", p.u)
        p.v = _vec(sys_, "v", p.v)
        p.w = _vec(sys_, "w", p.w)
    grid = _first(sc, "grid")
    if grid is not None:
        p.u_range = _vec(grid, "u_range", p.u_range)
        p.v_range = _vec(grid, "v_range", p.v_range)
        p.w_range = _vec(grid, "w_range", p.w_range)
        p.delta = _vec(grid, "delta", p.delta)
        p.snap = _vec(grid, "snap", p.snap)
    gs = _first(sc, "gridsnap")
    if gs is not None and gs.text:
        p.gridsnap = gs.text.strip().upper().startswith("T")
    mn = _first(sc, "minus")
    if mn is not None and mn.text:
        p.minus = mn.text.strip().upper().startswith("T")
    col = _first(sc, "color")
    if col is not None and col.text:
        vals = [int(x.strip()) for x in col.text.split(",")[:4]]
        if len(vals) == 4:
            p.color = tuple(vals)
    return p


def apply_plane(model: StpreModel, plane: SketchPlane) -> None:
    """Write ``<sketch_control>`` (creates it when missing)."""
    import xml.etree.ElementTree as ET
    from cabxml import set_text
    sc = _first(model.root, "sketch_control")
    if sc is None:
        sc = ET.Element("sketch_control")
        sc.tail = "\n   "
        model.root.append(sc)
        ET.SubElement(sc, "system")
        ET.SubElement(sc, "grid")
        ET.SubElement(sc, "gridsnap")
        ET.SubElement(sc, "minus")
        ET.SubElement(sc, "color")
    sys_ = _first(sc, "system")
    if sys_ is None:
        sys_ = ET.SubElement(sc, "system")
        sys_.tail = "\n   "
    sys_.attrib["unit"] = "mm"
    _set_vec(sys_, "c", plane.origin, "mm")
    _set_vec(sys_, "u", plane.u)
    _set_vec(sys_, "v", plane.v)
    _set_vec(sys_, "w", plane.w)
    grid = _first(sc, "grid")
    if grid is None:
        grid = ET.SubElement(sc, "grid")
        grid.tail = "\n   "
    _set_vec(grid, "u_range", plane.u_range)
    _set_vec(grid, "v_range", plane.v_range)
    _set_vec(grid, "w_range", plane.w_range)
    _set_vec(grid, "delta", plane.delta)
    _set_vec(grid, "snap", plane.snap)
    for tag, val in (("gridsnap", "T" if plane.gridsnap else "F"),
                     ("minus", "T" if plane.minus else "F")):
        e = _first(sc, tag)
        if e is None:
            e = ET.SubElement(sc, tag)
            e.tail = "\n   "
        set_text(e, val)
    col = _first(sc, "color")
    if col is None:
        col = ET.SubElement(sc, "color")
        col.tail = "\n   "
    set_text(col, ",".join(str(v) for v in plane.color))


def reset_plane_to_domain(model: StpreModel) -> SketchPlane:
    """STpre [Reset]: sketch plane on the Zmin boundary of the domain."""
    base = model.domain_base() or (0.0, 0.0, 0.0)
    size = model.domain_size() or (1.0, 1.0, 1.0)
    p = SketchPlane(origin=(0.0, 0.0, base[2]))
    dx, dy, dz = (s / 1000.0 for s in size)
    p.u_range = (0.0, dx)
    p.v_range = (0.0, dy)
    p.w_range = (0.0, 0.0)
    p.delta = (max(dx / 10.0, 1e-9), max(dy / 10.0, 1e-9), 0.0)
    p.snap = p.delta
    return p


def fit_plane_to_domain(model: StpreModel, plane: SketchPlane) -> SketchPlane:
    """STpre [Fit to computational domain]: grid range = domain extents."""
    base = model.domain_base() or (0.0, 0.0, 0.0)
    size = model.domain_size() or (1.0, 1.0, 1.0)
    b = np.asarray(base, float) / 1000.0
    s = np.asarray(size, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    w = np.asarray(plane.w, float)
    corners = np.array([
        b, b + [s[0], 0, 0], b + [0, s[1], 0], b + [0, 0, s[2]],
        b + [s[0], s[1], 0], b + [s[0], 0, s[2]], b + [0, s[1], s[2]],
        b + s])
    rel = corners - (np.asarray(plane.origin, float) / 1000.0)
    us = rel @ u
    vs = rel @ v
    ws = rel @ w
    plane.u_range = (float(us.min()), float(us.max()))
    plane.v_range = (float(vs.min()), float(vs.max()))
    plane.w_range = (float(ws.min()), float(ws.max()))
    du = max((plane.u_range[1] - plane.u_range[0]) / 10.0, 1e-9)
    dv = max((plane.v_range[1] - plane.v_range[0]) / 10.0, 1e-9)
    dw = max((plane.w_range[1] - plane.w_range[0]) / 10.0, 1e-9)
    plane.delta = (du, dv, dw)
    plane.snap = plane.delta
    return plane


# ------------------------------------------------------------- 2D profile


@dataclass
class SketchProfile:
    """2D sketch shape in sketch-plane U/V coordinates (mm)."""

    geometry_type: str = "rectangle"   # point_sequence | rectangle | circle
    points: list[tuple[float, float]] = field(default_factory=list)
    close: bool = True
    location: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (10.0, 10.0)
    center: tuple[float, float] = (0.0, 0.0)
    radius: float = 5.0
    divisions: int = 24               # circle -> regular polygon

    def polygon(self) -> list[tuple[float, float]]:
        """Outline vertices for tessellation (no duplicated closing point)."""
        if self.geometry_type == "rectangle":
            x0, y0 = self.location
            dx, dy = self.size
            return [(x0, y0), (x0 + dx, y0), (x0 + dx, y0 + dy),
                    (x0, y0 + dy)]
        if self.geometry_type == "circle":
            n = max(8, int(self.divisions))
            ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
            cx, cy = self.center
            return [(cx + self.radius * np.cos(a),
                     cy + self.radius * np.sin(a)) for a in ang]
        pts = list(self.points)
        # Drop accidental trailing duplicate of the first vertex
        while len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return pts


def _unit(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-12 else a


def _signed_area_uv(pts2: np.ndarray) -> float:
    n = len(pts2)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += float(pts2[i, 0] * pts2[j, 1] - pts2[j, 0] * pts2[i, 1])
    return 0.5 * area


def _poly2d_tris(n: int) -> np.ndarray:
    """Fan triangulation for a simple convex/near-convex n-gon (CCW)."""
    if n < 3:
        return np.zeros((0, 3), dtype=np.int64)
    return np.asarray([[0, i + 1, i + 2] for i in range(n - 2)],
                      dtype=np.int64)


def sketch_tess(plane: SketchPlane, profile: SketchProfile,
                model_type: str = "extrusion",
                thickness_mm: float = 10.0):
    """Tessellate a sketch part (Panel/Extrusion) on the sketch plane."""
    from cab_parts import PrimitivePart
    poly = profile.polygon()
    if len(poly) < 3:
        poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    pts2 = np.asarray(poly, float) / 1000.0
    if _signed_area_uv(pts2) < 0:
        pts2 = pts2[::-1].copy()
    o = np.asarray(plane.origin, float) / 1000.0
    u = _unit(plane.u)
    v = _unit(plane.v)
    w = _unit(plane.w)
    # Ensure right-handed frame (W ≈ U×V)
    if np.dot(np.cross(u, v), w) < 0:
        w = -w
    tris2 = _poly2d_tris(len(pts2))
    base3 = o + pts2[:, 0:1] * u + pts2[:, 1:2] * v
    if model_type == "panel":
        return PrimitivePart("", base3, tris2)
    # extrusion (solid): prism along W
    h = float(thickness_mm) / 1000.0
    if h <= 0:
        h = 0.005
    top3 = base3 + w * h
    pts = np.vstack([base3, top3])
    n = len(base3)
    tris = [list(t) for t in tris2]
    # Top face opposite winding
    tris += [[int(t[0]) + n, int(t[2]) + n, int(t[1]) + n] for t in tris2]
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + j])
        tris.append([i, n + j, n + i])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def _write_sketch_fields(el, *, plane: SketchPlane, profile: SketchProfile,
                         model_type: str, thickness_mm: float,
                         orientation: str = "W-Axis(Positive)",
                         scale_type: str = "Solid") -> None:
    import xml.etree.ElementTree as ET
    from cabxml import _first as f1

    def add(tag, value, unit=None):
        c = f1(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n         "
        c.text = f" {value} "
        if unit:
            c.attrib["unit"] = unit

    add("model_type", model_type)
    add("scale_type", scale_type)
    add("orientation", orientation)
    add("geometry_type", profile.geometry_type)
    add("close", "T" if profile.close else "F")
    add("thickness", f"{thickness_mm:.12g}", "mm")
    add("height", f"{thickness_mm:.12g}", "mm")
    if profile.geometry_type == "rectangle":
        add("location", f"{profile.location[0]:.12g},{profile.location[1]:.12g}",
            "mm")
        add("size", f"{profile.size[0]:.12g},{profile.size[1]:.12g}", "mm")
    elif profile.geometry_type == "circle":
        add("center", f"{profile.center[0]:.12g},{profile.center[1]:.12g}",
            "mm")
        add("radius", f"{profile.radius:.12g}", "mm")
        add("divisions", str(profile.divisions))
    else:
        pts = ",".join(f"{x:.12g},{y:.12g}" for x, y in profile.points)
        add("points", pts, "mm")
    add("plane_origin", f"{plane.origin[0]:.12g},{plane.origin[1]:.12g},"
                        f"{plane.origin[2]:.12g}", "mm")
    add("plane_u", ",".join(f"{x:.12g}" for x in plane.u))
    add("plane_v", ",".join(f"{x:.12g}" for x in plane.v))
    add("plane_w", ",".join(f"{x:.12g}" for x in plane.w))


def register_sketch_part(model: StpreModel, *, name: str, plane: SketchPlane,
                         profile: SketchProfile, model_type: str,
                         thickness_mm: float, material: str = "",
                         attribute: str = "Solid",
                         color: str = "25,117,255,255",
                         layer: str = "1",
                         orientation: str = "W-Axis(Positive)",
                         scale_type: str = "Solid") -> bool:
    """Add a ``<parts type="sketch">`` entry with profile parameters."""
    if model.find_part(name) is not None:
        return False
    el = model.add_part(name=name, kind="sketch", property_=material,
                        attribute=attribute, color=color, layer=str(layer))
    if el is None:
        return False
    _write_sketch_fields(
        el, plane=plane, profile=profile, model_type=model_type,
        thickness_mm=thickness_mm, orientation=orientation,
        scale_type=scale_type)
    return True


def update_sketch_part(model: StpreModel, *, name: str, plane: SketchPlane,
                       profile: SketchProfile, model_type: str,
                       thickness_mm: float, material: str = "",
                       attribute: str = "Solid",
                       color: str = "25,117,255,255",
                       layer: str = "1",
                       orientation: str = "W-Axis(Positive)",
                       scale_type: str = "Solid",
                       new_name: Optional[str] = None) -> bool:
    """Rewrite an existing sketch part's geometry / attributes."""
    from cabxml import set_text
    el = model.find_part(name)
    if el is None or el.attrib.get("type") != "sketch":
        return False
    dest = (new_name or name).strip() or name
    if dest != name and model.find_part(dest) is not None:
        return False
    if dest != name:
        model.rename_part(name, dest)
        el = model.find_part(dest)
        if el is None:
            return False
    import xml.etree.ElementTree as ET
    from cabxml import _first as f1
    for tag, val in (("property", material), ("attribute", attribute),
                     ("color", color), ("layer", str(layer))):
        c = f1(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n         "
        set_text(c, val)
    _write_sketch_fields(
        el, plane=plane, profile=profile, model_type=model_type,
        thickness_mm=thickness_mm, orientation=orientation,
        scale_type=scale_type)
    return True


def read_sketch_part(model: StpreModel, name: str
                     ) -> Optional[tuple[SketchProfile, dict]]:
    """Load profile + metadata for an existing sketch part."""
    from cabxml import _first as f1
    part = next((p for p in model.parts() if p.name == name), None)
    if part is None or part.kind != "sketch":
        return None
    el = part.elem

    def text(tag, default=""):
        c = f1(el, tag)
        return c.text.strip() if c is not None and c.text else default

    def vec2(tag, default=(0.0, 0.0)):
        t = text(tag)
        if not t:
            return tuple(float(v) for v in default)
        vals = [float(x) for x in t.split(",")[:2]]
        while len(vals) < 2:
            vals.append(0.0)
        return tuple(vals)

    geometry = text("geometry_type", "point_sequence")
    profile = SketchProfile(
        geometry_type=geometry,
        close=text("close", "T").upper().startswith("T"))
    if geometry == "rectangle":
        profile.location = vec2("location")
        profile.size = vec2("size", (10.0, 10.0))
    elif geometry == "circle":
        profile.center = vec2("center")
        profile.radius = float(text("radius", "5"))
        profile.divisions = int(float(text("divisions", "24")))
    else:
        t = text("points")
        vals = [float(x) for x in t.replace(";", ",").split(",") if x.strip()]
        profile.points = [(vals[i], vals[i + 1])
                          for i in range(0, len(vals) - 1, 2)]
    meta = {
        "name": name,
        "model_type": text("model_type", "extrusion"),
        "scale_type": text("scale_type", "Solid"),
        "orientation": text("orientation", "W-Axis(Positive)"),
        "thickness": float(text("thickness", text("height", "5"))),
        "attribute": part.attribute or "Obstacle",
        "material": part.property or "",
        "color": part.color or "120,160,220,255",
        "layer": text("layer", "1") or "1",
    }
    return profile, meta


def world_to_uv_mm(plane: SketchPlane, wx: float, wy: float, wz: float
                   ) -> tuple[float, float]:
    """Project a world point (metres) onto the sketch plane → (U,V) mm."""
    o = np.asarray(plane.origin, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    rel = np.asarray([wx, wy, wz], float) - o
    return float(np.dot(rel, u) * 1000.0), float(np.dot(rel, v) * 1000.0)


def snap_uv_mm(plane: SketchPlane, u_mm: float, v_mm: float
               ) -> tuple[float, float]:
    """Snap UV (mm) to sketch-plane snap interval when gridsnap is on."""
    if not plane.gridsnap:
        return u_mm, v_mm
    su = max(float(plane.snap[0]) * 1000.0, 1e-12)
    sv = max(float(plane.snap[1]) * 1000.0, 1e-12)
    return round(u_mm / su) * su, round(v_mm / sv) * sv


def pick_sketch_uv_mm(renderer, display_x: float, display_y: float,
                      plane: SketchPlane) -> Optional[tuple[float, float]]:
    """Ray ∩ sketch plane at display (x,y) → snapped (U,V) mm, or None."""
    if renderer is None:
        return None
    try:
        import vtk
    except Exception:
        return None
    # Near / far world points along the camera ray
    renderer.SetDisplayPoint(float(display_x), float(display_y), 0.0)
    renderer.DisplayToWorld()
    n = renderer.GetWorldPoint()
    renderer.SetDisplayPoint(float(display_x), float(display_y), 1.0)
    renderer.DisplayToWorld()
    f = renderer.GetWorldPoint()
    if abs(n[3]) < 1e-18 or abs(f[3]) < 1e-18:
        return None
    p0 = np.array([n[0] / n[3], n[1] / n[3], n[2] / n[3]], float)
    p1 = np.array([f[0] / f[3], f[1] / f[3], f[2] / f[3]], float)
    direction = p1 - p0
    o = np.asarray(plane.origin, float) / 1000.0
    w = np.asarray(plane.w, float)
    denom = float(np.dot(direction, w))
    if abs(denom) < 1e-14:
        # Parallel to plane — fall back to WorldPointPicker projection
        picker = vtk.vtkWorldPointPicker()
        picker.Pick(float(display_x), float(display_y), 0.0, renderer)
        wx, wy, wz = picker.GetPickPosition()
        u_mm, v_mm = world_to_uv_mm(plane, wx, wy, wz)
        return snap_uv_mm(plane, u_mm, v_mm)
    t = float(np.dot(o - p0, w) / denom)
    hit = p0 + t * direction
    u_mm, v_mm = world_to_uv_mm(plane, hit[0], hit[1], hit[2])
    return snap_uv_mm(plane, u_mm, v_mm)


def tess_for_sketch_part(model: StpreModel, part) -> Optional[object]:
    """Rebuild sketch-part geometry from XML (uses the stored plane)."""
    from cab_parts import PrimitivePart
    from cabxml import _first as f1
    el = part.elem
    if el.attrib.get("type") != "sketch":
        return None

    def text(tag, default=""):
        c = f1(el, tag)
        return c.text.strip() if c is not None and c.text else default

    def vec2(tag, default=(0.0, 0.0)):
        t = text(tag)
        if not t:
            return tuple(float(v) for v in default)
        vals = [float(x) for x in t.split(",")[:2]]
        while len(vals) < 2:
            vals.append(0.0)
        return tuple(vals)

    model_type = text("model_type", "extrusion")
    geometry = text("geometry_type", "rectangle")
    thickness = float(text("thickness", "10"))
    profile = SketchProfile(geometry_type=geometry,
                            close=text("close", "T").upper().startswith("T"))
    if geometry == "rectangle":
        profile.location = vec2("location")
        profile.size = vec2("size", (10.0, 10.0))
    elif geometry == "circle":
        profile.center = vec2("center")
        profile.radius = float(text("radius", "5"))
        profile.divisions = int(float(text("divisions", "24")))
    else:
        t = text("points")
        vals = [float(x) for x in t.replace(";", ",").split(",")]
        profile.points = [(vals[i], vals[i + 1])
                          for i in range(0, len(vals) - 1, 2)]
    plane = SketchPlane(
        origin=tuple(float(x) for x in
                     text("plane_origin", "0,0,0").split(",")[:3]),
        u=tuple(float(x) for x in text("plane_u", "1,0,0").split(",")[:3]),
        v=tuple(float(x) for x in text("plane_v", "0,1,0").split(",")[:3]),
        w=tuple(float(x) for x in text("plane_w", "0,0,1").split(",")[:3]),
    )
    p = sketch_tess(plane, profile, model_type, thickness)
    p.name = part.name
    return p


def sketch_parts_from_model(model: StpreModel) -> list[object]:
    return [p for p in (tess_for_sketch_part(model, pi)
                        for pi in model.parts()) if p is not None]


class SketchPartDialog(QDialog if _HAS_GUI_DEPS else object):
    """STpre [Part] - [Sketch Part] (Model Type/Vertex + Size/Attribute).

    Non-modal by default so the Draw Window can receive sketch-plane picks
    while the dialog is open (STpre behaviour).
    """

    preview_requested = pyqtSignal(object) if _HAS_GUI_DEPS else None  # type: ignore
    vertex_added = pyqtSignal(float, float) if _HAS_GUI_DEPS else None  # type: ignore

    def __init__(self, model: StpreModel, props, parent=None,
                 edit_name: Optional[str] = None):
        super().__init__(parent)
        from cab_dialogs import AttributePanel, ColorButton, CuboidSchematic

        self.setWindowTitle("Part (Sketch Part)")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.model = model
        self.props = props
        self.plane = plane_from_xml(model)
        self.edit_name = edit_name  # None = create; str = edit existing
        self._ColorButton = ColorButton
        self._MaterialListDialog = None
        try:
            from cab_dialogs import MaterialListDialog
            self._MaterialListDialog = MaterialListDialog
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._model_vertex_tab(), "Model Type/Vertex")
        self.tabs.addTab(
            self._size_attr_tab(AttributePanel, ColorButton, CuboidSchematic),
            "Size/Attribute")
        root.addWidget(self.tabs, 1)

        brow = QHBoxLayout()
        self.btn_preview = QPushButton("Preview", self)
        self.btn_preview.clicked.connect(self._preview)
        brow.addWidget(self.btn_preview)
        brow.addStretch(1)
        ok = QPushButton("OK", self)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        root.addLayout(brow)

        self.name_edit.setText("Extrusion1")
        self.resize(640, 560)
        self._sync_scale_enabled()
        self.model_type.currentIndexChanged.connect(self._on_model_type)
        self.rb_solid.toggled.connect(self._sync_scale_enabled)
        self.rb_panel.toggled.connect(self._sync_scale_enabled)
        self.rb_wall.toggled.connect(self._sync_scale_enabled)
        if edit_name:
            self.load_part(edit_name)

    # ------------------------------------------------------------------ tabs

    def _model_vertex_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setSpacing(6)

        f = QFormLayout()
        self.model_type = QComboBox(page)
        self.model_type.addItems([
            "Extrusion", "Panel", "Cutout", "Revolved Body",
            "Fan", "Axial flow fan"])
        f.addRow("(1) Model type", self.model_type)

        cut = QHBoxLayout()
        self.cutout_target = QLineEdit(page)
        self.cutout_target.setEnabled(False)
        btn_sel = QPushButton("Select", page)
        btn_sel.setEnabled(False)
        cut.addWidget(self.cutout_target, 1)
        cut.addWidget(btn_sel)
        f.addRow("(2) Target part for cutout", cut)

        grow = QHBoxLayout()
        self.geometry_type = QComboBox(page)
        self.geometry_type.addItems(
            ["Point sequence", "Rectangle", "Circle"])
        self.geometry_type.currentIndexChanged.connect(self._on_geometry)
        grow.addWidget(self.geometry_type, 1)
        self.btn_reset = QPushButton("Reset Vertex", page)
        self.btn_reset.clicked.connect(self._reset_vertices)
        grow.addWidget(self.btn_reset)
        f.addRow("(3) Geometry type of vertex", grow)
        lay.addLayout(f)

        lay.addWidget(QLabel("(4) Vertices information", page))
        self.points_table = QTableWidget(0, 4, page)
        self.points_table.setHorizontalHeaderLabels(
            ["#", "U", "V", "Angle"])
        self.points_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.points_table.verticalHeader().setVisible(False)
        lay.addWidget(self.points_table, 1)

        prow = QHBoxLayout()
        self.btn_add = QPushButton("Add vertex", page)
        self.btn_del = QPushButton("Delete selected line", page)
        self.btn_add.clicked.connect(self._add_empty_vertex)
        self.btn_del.clicked.connect(self._delete_selected_vertex)
        prow.addWidget(self.btn_add)
        prow.addWidget(self.btn_del)
        prow.addStretch(1)
        lay.addLayout(prow)

        # Rectangle / Circle editors (parented to page — never to dialog)
        self.rect_widget = QWidget(page)
        rf = QFormLayout(self.rect_widget)
        self.rect_loc = self._pair_spins(self.rect_widget)
        self.rect_size = self._pair_spins(self.rect_widget, (10.0, 10.0))
        rf.addRow("Location (U,V)", self.rect_loc["widget"])
        rf.addRow("Size (U,V)", self.rect_size["widget"])
        lay.addWidget(self.rect_widget)

        self.circle_widget = QWidget(page)
        cf = QFormLayout(self.circle_widget)
        self.circle_center = self._pair_spins(self.circle_widget)
        cf.addRow("Center (U,V)", self.circle_center["widget"])
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Radius", page))
        self.circle_radius = QDoubleSpinBox(self.circle_widget)
        self.circle_radius.setRange(1e-6, 1e7)
        self.circle_radius.setValue(5.0)
        crow.addWidget(self.circle_radius)
        crow.addWidget(QLabel("Regular polygon sides", page))
        self.circle_div = QSpinBox(self.circle_widget)
        self.circle_div.setRange(8, 360)
        self.circle_div.setValue(24)
        crow.addWidget(self.circle_div)
        cf.addRow(crow)
        lay.addWidget(self.circle_widget)

        self.close_chk = QCheckBox("Close start and end points", page)
        self.close_chk.setChecked(True)
        lay.addWidget(self.close_chk)

        # Sketch origin (display of plane origin — STpre chrome)
        org = QHBoxLayout()
        org.addWidget(QLabel("Sketch Origin", page))
        self.origin_spins = {}
        for i, ax in enumerate("XYZ"):
            org.addWidget(QLabel(ax, page))
            sb = QDoubleSpinBox(page)
            sb.setRange(-1e7, 1e7)
            sb.setDecimals(4)
            sb.setValue(float(self.plane.origin[i]))
            sb.setReadOnly(True)
            sb.setButtonSymbols(QDoubleSpinBox.NoButtons)
            self.origin_spins[ax] = sb
            org.addWidget(sb)
        org.addStretch(1)
        lay.addLayout(org)

        note = QLabel(
            "(5) Set size and attribute in the next page.\n"
            "Click the sketch plane in the Draw Window to add vertices "
            "(Point sequence).",
            page)
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay.addWidget(note)
        self._on_geometry()
        return page

    def _size_attr_tab(self, AttributePanel, ColorButton, CuboidSchematic
                       ) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Part Name", page))
        self.name_edit = QLineEdit(page)
        nrow.addWidget(self.name_edit, 1)
        self.color_btn = ColorButton((120, 160, 220, 255), page)
        nrow.addWidget(self.color_btn)
        nrow.addWidget(QLabel("Layer", page))
        self.layer_spin = QSpinBox(page)
        self.layer_spin.setRange(1, 999)
        self.layer_spin.setValue(1)
        nrow.addWidget(self.layer_spin)
        lay.addLayout(nrow)

        cols = QHBoxLayout()
        cols.setSpacing(8)

        scale = QGroupBox("Scale", page)
        sl = QVBoxLayout(scale)
        self.schematic = CuboidSchematic(scale, face="#cfe8a9")
        self.schematic.setMinimumHeight(120)
        sl.addWidget(self.schematic)

        tbox = QGroupBox("Type", scale)
        tl = QVBoxLayout(tbox)
        self.rb_solid = QRadioButton("Solid", tbox)
        self.rb_panel = QRadioButton("Panel", tbox)
        self.rb_wall = QRadioButton("Wall", tbox)
        self.rb_solid.setChecked(True)
        self._type_group = QButtonGroup(tbox)
        for rb in (self.rb_solid, self.rb_panel, self.rb_wall):
            self._type_group.addButton(rb)
            tl.addWidget(rb)
        sl.addWidget(tbox)

        sf = QFormLayout()
        self.orientation = QComboBox(scale)
        self.orientation.addItems([
            "W-Axis(Positive)", "W-Axis(Negative)",
            "U-Axis(Positive)", "U-Axis(Negative)",
            "V-Axis(Positive)", "V-Axis(Negative)"])
        sf.addRow("Orientation", self.orientation)
        self.height = QDoubleSpinBox(scale)
        self.height.setRange(1e-6, 1e7)
        self.height.setDecimals(4)
        self.height.setValue(5.0)
        sf.addRow("Height", self.height)
        self.wall_thickness = QDoubleSpinBox(scale)
        self.wall_thickness.setRange(1e-6, 1e7)
        self.wall_thickness.setDecimals(4)
        self.wall_thickness.setValue(1.0)
        sf.addRow("Thickness", self.wall_thickness)
        sl.addLayout(sf)
        unit = QLabel("Unit: mm", scale)
        unit.setAlignment(Qt.AlignRight)
        sl.addWidget(unit)
        cols.addWidget(scale, 3)

        self.attr_panel = AttributePanel(
            page,
            attributes=["Obstacle", "Solid", "Panel", "Condition region",
                        "Fluid"],
            attribute_enabled=True, heat_source=True, virtual_part=True,
            full_stpre=True)
        self.attr_panel.configure_requested.connect(self._configure_material)
        if self.props is not None and self.props.material_names():
            mats = self.props.material_names()
            obst = next((m for m in mats if "obstacle" in m.lower()
                         or m == "Obstacle"), mats[0])
            self.attr_panel.set_material(obst)
        else:
            self.attr_panel.set_material("Obstacle")
            idx = self.attr_panel.attribute.findText("Obstacle")
            if idx >= 0:
                self.attr_panel.attribute.setCurrentIndex(idx)
        cols.addWidget(self.attr_panel, 2)
        lay.addLayout(cols, 1)
        return page

    # -------------------------------------------------------------- helpers

    def _pair_spins(self, parent, defaults=(0.0, 0.0)):
        """UV spin pair — widgets parented to ``parent`` (avoids top-left leak)."""
        w = QWidget(parent)
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        spins = {}
        for key, val in (("u", defaults[0]), ("v", defaults[1])):
            sb = QDoubleSpinBox(w)
            sb.setRange(-1e7, 1e7)
            sb.setDecimals(4)
            sb.setValue(float(val))
            spins[key] = sb
            row.addWidget(sb)
        return {"widget": w, "u": spins["u"], "v": spins["v"]}

    def _on_geometry(self) -> None:
        g = self.geometry_type.currentText()
        is_pts = g == "Point sequence"
        self.points_table.setVisible(is_pts)
        self.btn_add.setVisible(is_pts)
        self.btn_del.setVisible(is_pts)
        self.close_chk.setVisible(is_pts)
        self.btn_reset.setVisible(True)
        self.rect_widget.setVisible(g == "Rectangle")
        self.circle_widget.setVisible(g == "Circle")

    def _on_model_type(self) -> None:
        is_cut = self.model_type.currentText() == "Cutout"
        self.cutout_target.setEnabled(is_cut)
        # Select button is sibling in the same row — find via parent layout
        for btn in self.findChildren(QPushButton):
            if btn.text() == "Select":
                btn.setEnabled(is_cut)
        defaults = {
            "Extrusion": "Extrusion1",
            "Panel": "Panel1",
            "Cutout": "Cutout1",
            "Revolved Body": "Revolved1",
            "Fan": "Fan1",
            "Axial flow fan": "AxialFan1",
        }
        cur = self.name_edit.text().strip()
        if cur in defaults.values() or not cur:
            self.name_edit.setText(
                defaults.get(self.model_type.currentText(), "SketchPart1"))
        self._sync_scale_enabled()

    def _sync_scale_enabled(self) -> None:
        mt = self.model_type.currentText()
        is_extrusion = mt == "Extrusion"
        is_panel_model = mt == "Panel"
        # Scale Type radios follow model type defaults
        if is_panel_model and not self.rb_panel.isChecked():
            self.rb_panel.blockSignals(True)
            self.rb_panel.setChecked(True)
            self.rb_panel.blockSignals(False)
        self.height.setEnabled(is_extrusion and self.rb_solid.isChecked())
        self.wall_thickness.setEnabled(
            self.rb_panel.isChecked() or self.rb_wall.isChecked())
        if is_panel_model:
            self.height.setEnabled(False)
            self.wall_thickness.setEnabled(True)

    def load_part(self, name: str) -> bool:
        """Populate the dialog from an existing ``type="sketch"`` part."""
        loaded = read_sketch_part(self.model, name)
        if loaded is None:
            return False
        profile, meta = loaded
        self.edit_name = name
        self.name_edit.setText(meta["name"])
        # Model type
        mt = meta["model_type"].capitalize()
        if meta["model_type"] == "extrusion":
            mt = "Extrusion"
        elif meta["model_type"] == "panel":
            mt = "Panel"
        idx = self.model_type.findText(mt)
        if idx >= 0:
            self.model_type.blockSignals(True)
            self.model_type.setCurrentIndex(idx)
            self.model_type.blockSignals(False)
        # Geometry + vertices
        gmap = {
            "point_sequence": "Point sequence",
            "rectangle": "Rectangle",
            "circle": "Circle",
        }
        gtxt = gmap.get(profile.geometry_type, "Point sequence")
        gi = self.geometry_type.findText(gtxt)
        if gi >= 0:
            self.geometry_type.setCurrentIndex(gi)
        self.points_table.blockSignals(True)
        self.points_table.setRowCount(0)
        self.points_table.blockSignals(False)
        if profile.geometry_type == "rectangle":
            self.rect_loc["u"].setValue(profile.location[0])
            self.rect_loc["v"].setValue(profile.location[1])
            self.rect_size["u"].setValue(profile.size[0])
            self.rect_size["v"].setValue(profile.size[1])
        elif profile.geometry_type == "circle":
            self.circle_center["u"].setValue(profile.center[0])
            self.circle_center["v"].setValue(profile.center[1])
            self.circle_radius.setValue(profile.radius)
            self.circle_div.setValue(profile.divisions)
        else:
            for u, v in profile.points:
                self.add_picked_vertex(u, v)
        self.close_chk.setChecked(profile.close)
        # Scale
        st = meta.get("scale_type", "Solid")
        {"Solid": self.rb_solid, "Panel": self.rb_panel,
         "Wall": self.rb_wall}.get(st, self.rb_solid).setChecked(True)
        oi = self.orientation.findText(meta.get("orientation", ""))
        if oi >= 0:
            self.orientation.setCurrentIndex(oi)
        self.height.setValue(float(meta["thickness"]))
        self.wall_thickness.setValue(float(meta["thickness"]))
        # Attribute
        ai = self.attr_panel.attribute.findText(meta["attribute"])
        if ai >= 0:
            self.attr_panel.attribute.setCurrentIndex(ai)
        if meta["material"]:
            self.attr_panel.set_material(meta["material"])
        try:
            rgba = tuple(int(float(x)) for x in meta["color"].split(",")[:4])
            if len(rgba) == 4:
                self.color_btn.set_rgba(rgba)
        except ValueError:
            pass
        try:
            self.layer_spin.setValue(int(float(meta["layer"])))
        except ValueError:
            pass
        self._sync_scale_enabled()
        return True

    def _configure_material(self) -> None:
        if self._MaterialListDialog is None:
            return
        dlg = self._MaterialListDialog(
            self.props, self,
            current=self.attr_panel.material_name(),
            part_name=self.name_edit.text().strip())
        if dlg.exec_() and dlg.selected_material():
            self.attr_panel.set_material(dlg.selected_material())

    def _reset_vertices(self) -> None:
        self.points_table.setRowCount(0)

    def _add_empty_vertex(self) -> None:
        self.add_picked_vertex(0.0, 0.0)

    def _delete_selected_vertex(self) -> None:
        rows = sorted({i.row() for i in self.points_table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.points_table.removeRow(r)
        self._renumber_vertices()

    def _renumber_vertices(self) -> None:
        for r in range(self.points_table.rowCount()):
            item = QTableWidgetItem(str(r + 1))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.points_table.setItem(r, 0, item)

    def add_picked_vertex(self, u_mm: float, v_mm: float) -> None:
        """Append a sketch-plane pick (mm) into the vertex table."""
        if self.geometry_type.currentText() != "Point sequence":
            self.geometry_type.setCurrentText("Point sequence")
        r = self.points_table.rowCount()
        self.points_table.insertRow(r)
        num = QTableWidgetItem(str(r + 1))
        num.setFlags(num.flags() & ~Qt.ItemIsEditable)
        self.points_table.setItem(r, 0, num)
        self.points_table.setItem(r, 1, QTableWidgetItem(f"{u_mm:g}"))
        self.points_table.setItem(r, 2, QTableWidgetItem(f"{v_mm:g}"))
        self.points_table.setItem(r, 3, QTableWidgetItem("0"))
        self.points_table.selectRow(r)
        if self.vertex_added is not None:
            self.vertex_added.emit(float(u_mm), float(v_mm))

    def _preview(self) -> None:
        if self.preview_requested is not None:
            self.preview_requested.emit(self.spec())

    def accepts_plane_picks(self) -> bool:
        return (self.isVisible()
                and self.geometry_type.currentText() == "Point sequence")

    def _profile(self) -> SketchProfile:
        g = self.geometry_type.currentText()
        if g == "Rectangle":
            return SketchProfile(
                geometry_type="rectangle",
                location=(self.rect_loc["u"].value(),
                          self.rect_loc["v"].value()),
                size=(self.rect_size["u"].value(),
                      self.rect_size["v"].value()))
        if g == "Circle":
            return SketchProfile(
                geometry_type="circle",
                center=(self.circle_center["u"].value(),
                        self.circle_center["v"].value()),
                radius=self.circle_radius.value(),
                divisions=self.circle_div.value())
        pts = []
        for r in range(self.points_table.rowCount()):
            u = self.points_table.item(r, 1)
            v = self.points_table.item(r, 2)
            if u is None or v is None:
                continue
            try:
                pts.append((float(u.text()), float(v.text())))
            except ValueError:
                continue
        return SketchProfile(geometry_type="point_sequence",
                             points=pts, close=self.close_chk.isChecked())

    def _resolved_model_type(self) -> str:
        mt = self.model_type.currentText()
        if mt == "Panel" or self.rb_panel.isChecked():
            return "panel"
        if mt == "Extrusion":
            return "extrusion"
        # Cutout / Fan / … fall back to extrusion geometry proxy
        return "extrusion"

    def _resolved_thickness(self) -> float:
        if self.rb_panel.isChecked() or self.rb_wall.isChecked() \
                or self.model_type.currentText() == "Panel":
            return float(self.wall_thickness.value())
        return float(self.height.value())

    def _scale_type(self) -> str:
        if self.rb_wall.isChecked():
            return "Wall"
        if self.rb_panel.isChecked():
            return "Panel"
        return "Solid"

    def spec(self) -> dict:
        rgba = self.color_btn.rgba()
        return {
            "name": self.name_edit.text().strip(),
            "model_type": self._resolved_model_type(),
            "scale_type": self._scale_type(),
            "orientation": self.orientation.currentText(),
            "profile": self._profile(),
            "thickness": self._resolved_thickness(),
            "attribute": self.attr_panel.attribute.currentText(),
            "material": self.attr_panel.material_name(),
            "color": ",".join(str(v) for v in rgba),
            "layer": str(self.layer_spin.value()),
            "monitor": self.attr_panel.monitor(),
            "virtual": bool(
                self.attr_panel.virtual_chk
                and self.attr_panel.virtual_chk.isChecked()),
        }
