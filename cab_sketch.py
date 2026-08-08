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
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
        QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget,
        QTableWidget, QTableWidgetItem, QVBoxLayout,
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


@dataclass
class SketchPlane:
    """Sketch coordinate system + grid (XML ``<sketch_control>``)."""

    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)   # mm
    u: tuple[float, float, float] = (1.0, 0.0, 0.0)
    v: tuple[float, float, float] = (0.0, 1.0, 0.0)
    w: tuple[float, float, float] = (0.0, 0.0, 1.0)
    u_range: tuple[float, float] = (0.0, 1.0)              # m
    v_range: tuple[float, float] = (0.0, 1.0)
    w_range: tuple[float, float] = (0.0, 0.0)
    delta: tuple[float, float, float] = (0.1, 0.1, 0.1)    # m
    snap: tuple[float, float, float] = (0.1, 0.1, 0.1)
    gridsnap: bool = True
    minus: bool = False
    color: tuple[int, int, int, int] = (170, 170, 170, 255)


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
        if self.close and len(pts) > 2 and pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts


def _poly2d_tris(n: int) -> np.ndarray:
    return np.array([[0, i + 1, i + 2] for i in range(n - 2)],
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
    o = np.asarray(plane.origin, float) / 1000.0
    u = np.asarray(plane.u, float)
    v = np.asarray(plane.v, float)
    w = np.asarray(plane.w, float)
    base3 = o + pts2[:, 0:1] * u + pts2[:, 1:2] * v
    if model_type == "panel":
        tris = _poly2d_tris(len(base3))
        return PrimitivePart("", base3, tris)
    # extrusion (solid): prism along W
    h = float(thickness_mm) / 1000.0
    top3 = base3 + w * h
    pts = np.vstack([base3, top3])
    n = len(base3)
    tris = list(_poly2d_tris(n))
    tris += [list(t + n) for t in _poly2d_tris(n)[:, ::-1]]
    for i in range(n):
        j = (i + 1) % n
        tris.append([i, j, n + j])
        tris.append([i, n + j, n + i])
    return PrimitivePart("", pts, np.asarray(tris, dtype=np.int64))


def register_sketch_part(model: StpreModel, *, name: str, plane: SketchPlane,
                         profile: SketchProfile, model_type: str,
                         thickness_mm: float, material: str = "",
                         attribute: str = "Solid",
                         color: str = "25,117,255,255") -> bool:
    """Add a ``<parts type="sketch">`` entry with profile parameters."""
    import xml.etree.ElementTree as ET
    from cabxml import _first as f1
    if model.find_part(name) is not None:
        return False
    el = model.add_part(name=name, kind="sketch", property_=material,
                        attribute=attribute, color=color)
    if el is None:
        return False

    def add(tag, value, unit=None):
        c = f1(el, tag)
        if c is None:
            c = ET.SubElement(el, tag)
            c.tail = "\n         "
        c.text = f" {value} "
        if unit:
            c.attrib["unit"] = unit

    add("model_type", model_type)
    add("geometry_type", profile.geometry_type)
    add("close", "T" if profile.close else "F")
    add("thickness", f"{thickness_mm:.12g}", "mm")
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
    # snapshot of the plane used at creation (origin mm, grid m)
    add("plane_origin", f"{plane.origin[0]:.12g},{plane.origin[1]:.12g},"
                        f"{plane.origin[2]:.12g}", "mm")
    add("plane_u", ",".join(f"{x:.12g}" for x in plane.u))
    add("plane_v", ",".join(f"{x:.12g}" for x in plane.v))
    add("plane_w", ",".join(f"{x:.12g}" for x in plane.w))
    return True


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
    """[Part] - [Sketch Part] creation dialog (Panel / Extrusion)."""

    def __init__(self, model: StpreModel, props, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sketch Part")
        self.model = model
        self.props = props
        self.plane = plane_from_xml(model)
        lay = QVBoxLayout(self)
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Part name", self))
        self.name_edit = QLineEdit(self)
        nrow.addWidget(self.name_edit, 1)
        lay.addLayout(nrow)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._model_vertex_tab(), "Model Type/Vertex")
        self.tabs.addTab(self._size_attr_tab(), "Size/Attribute")
        lay.addWidget(self.tabs)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", self)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        lay.addLayout(brow)
        self.resize(520, 460)

    def _model_vertex_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        f = QFormLayout()
        self.model_type = QComboBox(self)
        self.model_type.addItems(["Extrusion", "Panel"])
        f.addRow("Model type", self.model_type)
        self.geometry_type = QComboBox(self)
        self.geometry_type.addItems(
            ["Point sequence", "Rectangle", "Circle"])
        self.geometry_type.currentIndexChanged.connect(
            self._on_geometry)
        f.addRow("Geometry type of vertex", self.geometry_type)
        lay.addLayout(f)

        self.points_table = QTableWidget(self)
        self.points_table.setColumnCount(2)
        self.points_table.setHorizontalHeaderLabels(["U (mm)", "V (mm)"])
        self.points_table.setRowCount(4)
        lay.addWidget(self.points_table, 1)
        prow = QHBoxLayout()
        self.btn_add = QPushButton("Add vertex", self)
        self.btn_del = QPushButton("Delete selected line", self)
        prow.addWidget(self.btn_add)
        prow.addWidget(self.btn_del)
        prow.addStretch(1)
        lay.addLayout(prow)

        rf = QFormLayout()
        self.rect_loc = self._pair_spins("Location")
        self.rect_size = self._pair_spins("Size")
        rf.addRow("Location (U,V)", self.rect_loc["row"])
        rf.addRow("Size (U,V)", self.rect_size["row"])
        self.rect_widget = QtWidgets.QWidget(self)
        self.rect_widget.setLayout(rf)
        lay.addWidget(self.rect_widget)

        cf = QFormLayout()
        self.circle_center = self._pair_spins("Center")
        cf.addRow("Center (U,V)", self.circle_center["row"])
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Radius", self))
        self.circle_radius = QDoubleSpinBox(self)
        self.circle_radius.setRange(1e-6, 1e7)
        self.circle_radius.setValue(5.0)
        crow.addWidget(self.circle_radius)
        crow.addWidget(QLabel("Regular polygon sides", self))
        self.circle_div = QSpinBox(self)
        self.circle_div.setRange(8, 360)
        self.circle_div.setValue(24)
        crow.addWidget(self.circle_div)
        cf.addRow(crow)
        self.circle_widget = QtWidgets.QWidget(self)
        self.circle_widget.setLayout(cf)
        lay.addWidget(self.circle_widget)

        self.close_chk = QCheckBox("Close start and end points", self)
        self.close_chk.setChecked(True)
        lay.addWidget(self.close_chk)
        self._on_geometry()
        return page

    def _pair_spins(self, _label):
        w = QtWidgets.QWidget(self)
        row = QHBoxLayout(w)
        out: dict[str, QDoubleSpinBox] = {}
        for key in ("u", "v"):
            sb = QDoubleSpinBox(self)
            sb.setRange(-1e7, 1e7)
            sb.setValue(0.0 if key == "u" else 0.0)
            out[key] = sb
            row.addWidget(sb)
        return {"row": row, "u": out["u"], "v": out["v"]}

    def _size_attr_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        f = QFormLayout()
        self.thickness = QDoubleSpinBox(self)
        self.thickness.setRange(1e-6, 1e7)
        self.thickness.setValue(10.0)
        self.thickness.setSuffix(" mm")
        f.addRow("Thickness (W direction)", self.thickness)
        self.attribute = QComboBox(self)
        self.attribute.addItems(
            ["Solid", "Obstacle", "Condition region", "Panel"])
        f.addRow("Attribute", self.attribute)
        self.material = QComboBox(self)
        self.material.setEditable(True)
        if self.props is not None:
            self.material.addItems(self.props.material_names())
        f.addRow("Material", self.material)
        lay.addLayout(f)
        hint = QLabel(
            "Sketch plane: origin=%.4g mm, U=%s, V=%s, W=%s"
            % (self.plane.origin[0], self.plane.u, self.plane.v,
               self.plane.w), self)
        hint.setStyleSheet("color: #555;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return page

    def _on_geometry(self) -> None:
        g = self.geometry_type.currentText()
        self.points_table.setVisible(g == "Point sequence")
        self.btn_add.setVisible(g == "Point sequence")
        self.btn_del.setVisible(g == "Point sequence")
        self.close_chk.setVisible(g == "Point sequence")
        self.rect_widget.setVisible(g == "Rectangle")
        self.circle_widget.setVisible(g == "Circle")

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
            u = self.points_table.item(r, 0)
            v = self.points_table.item(r, 1)
            if u is None or v is None:
                continue
            try:
                pts.append((float(u.text()), float(v.text())))
            except ValueError:
                continue
        return SketchProfile(geometry_type="point_sequence",
                             points=pts, close=self.close_chk.isChecked())

    def spec(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "model_type": self.model_type.currentText().lower(),
            "profile": self._profile(),
            "thickness": self.thickness.value(),
            "attribute": self.attribute.currentText(),
            "material": self.material.currentText(),
        }
