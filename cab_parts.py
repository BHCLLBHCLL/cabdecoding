"""M7: Part menu primitive creation (Cuboid/Cylinder/Sphere/Panel).

Follows the Pre_eng part pages ([Part]-[Cuboid/Cylinder/Sphere/Panel]):

* Cuboid: Location (min) + Size
* Cylinder: Center (bottom) + Radius + Height + Orientation (+ divisions)
* Sphere: Center + Radius (oval optional) + divisions
* Panel: Location + Size + Direction (normal axis)

Each primitive is stored as ``<parts type="cube|cylinder|sphere|panel">``
with the geometry parameters in the XML, and a :class:`PrimitivePart`
(duck-typed TessPart: name/points/triangles) is generated for the 3D view
and for meshing.  On reload the geometry is rebuilt from the XML, so no
``.x_t`` member is required for primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from cabxml import StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
        QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget,
        QVBoxLayout,
    )
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless
    _HAS_GUI_DEPS = False
    QDialog = object  # type: ignore


PRIMITIVE_KINDS = ("cube", "cylinder", "sphere", "panel")


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


def cube_tess(base_mm, size_mm) -> PrimitivePart:
    b = np.asarray(base_mm, float) / 1000.0
    s = np.asarray(size_mm, float) / 1000.0
    pts = np.array([
        [b[0], b[1], b[2]], [b[0] + s[0], b[1], b[2]],
        [b[0] + s[0], b[1] + s[1], b[2]], [b[0], b[1] + s[1], b[2]],
        [b[0], b[1], b[2] + s[2]], [b[0] + s[0], b[1], b[2] + s[2]],
        [b[0] + s[0], b[1] + s[1], b[2] + s[2]], [b[0], b[1] + s[1], b[2] + s[2]],
    ])
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


def tess_for_part(part) -> Optional[PrimitivePart]:
    """Rebuild primitive geometry from a ``PartInfo``-like object."""
    kind = getattr(part, "kind", "body")
    if kind not in PRIMITIVE_KINDS:
        return None
    el = part.elem
    from cabxml import _first

    def vec(tag, default=(0.0, 0.0, 0.0)):
        c = _first(el, tag)
        if c is None or not c.text:
            return tuple(float(v) for v in default)
        vals = [float(x.strip()) for x in c.text.split(",")[:3]]
        while len(vals) < 3:
            vals.append(0.0)
        return tuple(vals)

    def scalar(tag, default):
        c = _first(el, tag)
        if c is None or not c.text:
            return float(default)
        return float(c.text.strip().split(",")[0])

    def text(tag, default):
        c = _first(el, tag)
        return c.text.strip() if c is not None and c.text else default

    name = getattr(part, "name", "")
    if kind == "cube":
        p = cube_tess(vec("base"), vec("size", (1.0, 1.0, 1.0)))
    elif kind == "cylinder":
        p = cylinder_tess(
            vec("center"), scalar("radius", 1.0), scalar("height", 1.0),
            text("direction", "+Z"), int(scalar("divisions", 24)))
    elif kind == "sphere":
        rv = vec("radius", (1.0, 1.0, 1.0))
        r = rv[0] if all(abs(x - rv[0]) < 1e-12 for x in rv) else rv
        p = sphere_tess(vec("center"), r, int(scalar("divisions", 12)))
    else:  # panel
        p = panel_tess(vec("base"), vec("size", (1.0, 1.0, 1.0)),
                       text("direction", "+Z"))
    p.name = name
    return p


def primitives_from_model(model: StpreModel) -> list[PrimitivePart]:
    return [p for p in (tess_for_part(pi) for pi in model.parts())
            if p is not None]


def tess_for_spec(kind: str, params: dict) -> PrimitivePart:
    if kind == "cube":
        return cube_tess(params["base"], params["size"])
    if kind == "cylinder":
        return cylinder_tess(
            params["center"], params["radius"], params["height"],
            params.get("direction", "+Z"), params.get("divisions", 24))
    if kind == "sphere":
        return sphere_tess(
            params["center"], params["radius"], params.get("divisions", 12))
    return panel_tess(params["base"], params["size"],
                      params.get("direction", "+Z"))


def register_primitive(model: StpreModel, *, name: str, kind: str,
                       params: dict, material: str = "",
                       attribute: str = "solid",
                       color: str = "25,117,255,255") -> bool:
    """Add a primitive ``<parts>`` entry with its geometry parameters."""
    if kind not in PRIMITIVE_KINDS or model.find_part(name) is not None:
        return False
    el = model.add_part(name=name, kind=kind, property_=material,
                        attribute=attribute, color=color)
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

    mm = lambda v: ",".join(f"{x:.12g}" for x in v)  # noqa: E731
    if kind in ("cube", "panel"):
        add("base", mm(params["base"]), "mm")
        add("size", mm(params["size"]), "mm")
    if kind == "cylinder":
        add("center", mm(params["center"]), "mm")
        add("radius", f"{params['radius']:.12g}")
        add("height", f"{params['height']:.12g}")
        add("direction", params.get("direction", "+Z"))
        add("divisions", str(params.get("divisions", 24)))
    if kind == "sphere":
        add("center", mm(params["center"]), "mm")
        r = params["radius"]
        add("radius", mm(r) if np.size(r) > 1 else f"{r:.12g}")
        add("divisions", str(params.get("divisions", 12)))
    return True


class CreatePartDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Part] - [Cuboid/Cylinder/Sphere/Panel] creation dialog."""

    _AXES = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
    _ATTRIBUTES = {
        "cube": ["Obstacle", "Solid", "Condition region", "Fluid"],
        "cylinder": ["Obstacle", "Solid", "Condition region", "Fluid"],
        "sphere": ["Obstacle", "Solid", "Panel", "Condition region",
                   "Condition region face"],
        "panel": ["Panel", "Condition region face",
                  "Particle generation region face"],
    }

    def __init__(self, model: StpreModel, props, initial_kind: str = "cube",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Part")
        self.model = model
        self.props = props
        lay = QVBoxLayout(self)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Part name", self))
        self.name_edit = QLineEdit(self)
        name_row.addWidget(self.name_edit, 1)
        lay.addLayout(name_row)

        self.tabs = QTabWidget(self)
        self._pages = {
            "cube": self._cube_page(),
            "cylinder": self._cylinder_page(),
            "sphere": self._sphere_page(),
            "panel": self._panel_page(),
        }
        self.tabs.addTab(self._pages["cube"], "Cuboid")
        self.tabs.addTab(self._pages["cylinder"], "Cylinder")
        self.tabs.addTab(self._pages["sphere"], "Sphere")
        self.tabs.addTab(self._pages["panel"], "Panel")
        keys = list(self._pages)
        self.tabs.setCurrentIndex(keys.index(initial_kind)
                                  if initial_kind in keys else 0)
        lay.addWidget(self.tabs)

        form = QFormLayout()
        self.attr = QComboBox(self)
        form.addRow("Attribute", self.attr)
        self.mat = QComboBox(self)
        if props is not None:
            self.mat.addItems(props.material_names())
        form.addRow("Material", self.mat)
        lay.addLayout(form)
        self._refresh_attributes()
        self.tabs.currentChanged.connect(lambda _i: self._refresh_attributes())

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
        self.resize(440, 420)

    # -- pages ------------------------------------------------------------

    def _spins(self, labels: list[tuple[str, float, float, float]]) -> dict:
        form = QFormLayout()
        out: dict[str, QDoubleSpinBox] = {}
        for key, lo, hi, val in labels:
            sb = QDoubleSpinBox(self)
            sb.setRange(lo, hi)
            sb.setDecimals(6)
            sb.setValue(val)
            out[key] = sb
            form.addRow(key, sb)
        w = QtWidgets.QWidget(self)
        w.setLayout(form)
        return out

    def _cube_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        self.cube_base = self._spins([
            ("base_x", -1e6, 1e6, 0.0), ("base_y", -1e6, 1e6, 0.0),
            ("base_z", -1e6, 1e6, 0.0)])
        lay.addWidget(self._spins_wrap(self.cube_base))
        self.cube_size = self._spins([
            ("size_x", 1e-6, 1e7, 10.0), ("size_y", 1e-6, 1e7, 10.0),
            ("size_z", 1e-6, 1e7, 10.0)])
        lay.addWidget(self._spins_wrap(self.cube_size))
        lay.addStretch(1)
        return page

    def _spins_wrap(self, spins: dict) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget(self)
        form = QFormLayout(w)
        for key, sb in spins.items():
            form.addRow(key, sb)
        return w

    def _cylinder_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        self.cyl_center = self._spins([
            ("center_x", -1e6, 1e6, 0.0), ("center_y", -1e6, 1e6, 0.0),
            ("center_z", -1e6, 1e6, 0.0)])
        lay.addWidget(self._spins_wrap(self.cyl_center))
        self.cyl_radius = QDoubleSpinBox(self)
        self.cyl_radius.setRange(1e-6, 1e6)
        self.cyl_radius.setValue(5.0)
        self.cyl_height = QDoubleSpinBox(self)
        self.cyl_height.setRange(1e-6, 1e7)
        self.cyl_height.setValue(10.0)
        self.cyl_axis = QComboBox(self)
        self.cyl_axis.addItems(self._AXES)
        self.cyl_axis.setCurrentText("+Z")
        self.cyl_div = QSpinBox(self)
        self.cyl_div.setRange(4, 360)
        self.cyl_div.setValue(24)
        f = QFormLayout()
        f.addRow("Radius", self.cyl_radius)
        f.addRow("Height", self.cyl_height)
        f.addRow("Orientation", self.cyl_axis)
        f.addRow("Number of divisions of circle", self.cyl_div)
        lay.addLayout(f)
        lay.addStretch(1)
        return page

    def _sphere_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        self.sph_center = self._spins([
            ("center_x", -1e6, 1e6, 0.0), ("center_y", -1e6, 1e6, 0.0),
            ("center_z", -1e6, 1e6, 0.0)])
        lay.addWidget(self._spins_wrap(self.sph_center))
        self.sph_radius = QDoubleSpinBox(self)
        self.sph_radius.setRange(1e-6, 1e6)
        self.sph_radius.setValue(5.0)
        self.sph_div = QSpinBox(self)
        self.sph_div.setRange(4, 180)
        self.sph_div.setValue(12)
        f = QFormLayout()
        f.addRow("Radius", self.sph_radius)
        f.addRow("Number of divisions", self.sph_div)
        lay.addLayout(f)
        lay.addStretch(1)
        return page

    def _panel_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        lay = QVBoxLayout(page)
        self.panel_base = self._spins([
            ("base_x", -1e6, 1e6, 0.0), ("base_y", -1e6, 1e6, 0.0),
            ("base_z", -1e6, 1e6, 0.0)])
        lay.addWidget(self._spins_wrap(self.panel_base))
        self.panel_size = self._spins([
            ("size_x", 1e-6, 1e7, 10.0), ("size_y", 1e-6, 1e7, 10.0),
            ("size_z", 1e-6, 1e7, 10.0)])
        lay.addWidget(self._spins_wrap(self.panel_size))
        self.panel_dir = QComboBox(self)
        self.panel_dir.addItems(self._AXES)
        self.panel_dir.setCurrentText("+Z")
        f = QFormLayout()
        f.addRow("Direction", self.panel_dir)
        lay.addLayout(f)
        lay.addStretch(1)
        return page

    # -- value helpers ----------------------------------------------------

    def _refresh_attributes(self) -> None:
        kind = self.current_kind()
        items = self._ATTRIBUTES.get(kind, ["Solid"])
        self.attr.clear()
        self.attr.addItems(items)
        self.attr.setCurrentText(
            "Panel" if kind == "panel" else "Solid")

    def current_kind(self) -> str:
        return list(self._pages)[self.tabs.currentIndex()]

    def spec(self) -> dict:
        kind = self.current_kind()
        params: dict = {}
        if kind == "cube":
            params["base"] = tuple(self.cube_base[k].value() for k in
                                   ("base_x", "base_y", "base_z"))
            params["size"] = tuple(self.cube_size[k].value() for k in
                                   ("size_x", "size_y", "size_z"))
        elif kind == "cylinder":
            params["center"] = tuple(self.cyl_center[k].value() for k in
                                     ("center_x", "center_y", "center_z"))
            params["radius"] = self.cyl_radius.value()
            params["height"] = self.cyl_height.value()
            params["direction"] = self.cyl_axis.currentText()
            params["divisions"] = self.cyl_div.value()
        elif kind == "sphere":
            params["center"] = tuple(self.sph_center[k].value() for k in
                                     ("center_x", "center_y", "center_z"))
            params["radius"] = self.sph_radius.value()
            params["divisions"] = self.sph_div.value()
        else:
            params["base"] = tuple(self.panel_base[k].value() for k in
                                   ("base_x", "base_y", "base_z"))
            params["size"] = tuple(self.panel_size[k].value() for k in
                                   ("size_x", "size_y", "size_z"))
            params["direction"] = self.panel_dir.currentText()
        return {
            "name": self.name_edit.text().strip(),
            "kind": kind,
            "params": params,
            "attribute": self.attr.currentText(),
            "material": self.mat.currentText(),
        }
