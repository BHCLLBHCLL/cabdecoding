"""STpre Condition Wizard pages (layout aligned with Pre_eng + STpreCwiz UI).

Extra steps beyond the original Basic-Exercise subset: Source / Fixed /
Analysis Control children / Output Condition / File Specification /
Condition List / Setting Confirmation.  Values are written through
``StpreModel`` ``analysis_set`` / ``file`` / ``output`` / ``value``
where fields exist; richer options are retained in the UI for fidelity.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from cabxml import StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
        QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QMenu, QMessageBox, QPushButton, QRadioButton, QSpinBox,
        QSplitter, QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
        QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_GUI = True
except Exception:  # pragma: no cover
    _HAS_GUI = False
    QWidget = object  # type: ignore


def _note(text: str, parent=None) -> QLabel:
    lab = QLabel(text, parent)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #555;")
    return lab


def _pair(lay, label: str, widget, unit: str = "") -> None:
    row = QHBoxLayout()
    row.addWidget(QLabel(label))
    row.addWidget(widget, 1)
    if unit:
        row.addWidget(QLabel(unit))
    row.addStretch(1)
    lay.addLayout(row)


# Value types written for Source Condition (STpre-aligned; C2 extends the
# volumetric set with humidity/diffusion sources).
_SRC_VOL_TYPES = frozenset({
    "volumetric_force", "volumetric_pressure_loss", "heat_source",
    "source_term", "moisture_source", "smoke_source", "humidification",
    "plant_canopy", "driver", "time_series", "diffusion",
})
_SRC_AREA_TYPES = frozenset({
    "area_pressure_loss", "area_heat_source",
})


class _CwSourcePage(QWidget if _HAS_GUI else object):
    """STpre Condition Wizard → Source Condition
    (Volumetric / Area / Perforated Plate tabs)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self.model.ensure_domain_faces()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)

        # --- Volumetric Source Condition ---
        self.vol_page, self.vol_table, self.vol_display = self._make_list_tab(
            "Sets the volumetric source conditions.",
            star=False,
            new_actions=(
                ("Volumetric force", self._new_vol_force),
                ("Volumetric pressure loss", self._new_vol_ploss),
                ("Volumetric heat source", self._new_vol_heat),
                ("Moisture source", self._new_vol_moisture),
                ("Humidification", self._new_vol_humidification),
                ("Smoke source", self._new_vol_smoke),
                ("Plant canopy", self._new_vol_canopy),
                ("Driver", self._new_vol_driver),
                ("Time series", self._new_vol_time_series),
                ("Expression", self._new_vol_expression),
                ("Manage expressions", self._manage_expressions),
                ("Diffusion source", self._new_vol_diffusion),
                ("Generalized source term", self._new_vol_term),
            ),
            face_buttons=False,
            existing=True,
        )
        self.tabs.addTab(self.vol_page, "Volumetric Source Condition")

        # --- Area Source Condition ---
        self.area_page, self.area_table, self.area_display = \
            self._make_list_tab(
                "Sets the area source conditions.",
                star=True,
                new_actions=(
                    ("Area pressure loss", self._new_area_ploss),
                    ("Area heat source", self._new_area_heat),
                ),
                face_buttons=True,
                existing=True,
            )
        self.tabs.addTab(self.area_page, "Area Source Condition")

        # --- Perforated Plate (shown when panels may exist) ---
        self.perf_page, self.perf_table, self.perf_display = \
            self._make_list_tab(
                "Sets pressure loss and thermal conditions of a "
                "perforated plate.",
                star=False,
                new_actions=(
                    ("Perforated plate", self._new_perforated),
                ),
                face_buttons=True,
                existing=True,
            )
        self.tabs.addTab(self.perf_page, "Perforated Plate Condition")

        # --- Option (Heat Source) ---
        opt = QWidget()
        ol = QVBoxLayout(opt)
        ol.addWidget(QLabel("Sets options for heat source conditions.", opt))
        sep = QFrame(opt)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        ol.addWidget(sep)
        self.hs_auto = QCheckBox(
            "Heat generation per volume is automatically calculated "
            "from the total amount of heat generation", opt)
        hs_flag = (model.analysis_set_value("heat_source_auto", "F")
                   or "F").strip().upper()
        self.hs_auto.setChecked(hs_flag in ("T", "1"))
        ol.addWidget(self.hs_auto)
        ol.addStretch(1)
        self.tabs.addTab(opt, "Option (Heat Source)")

        root.addWidget(self.tabs, 1)
        # legacy flags kept so apply() still writes analysis_set markers
        self.vf_on = QCheckBox(self)
        self.vf_on.hide()
        self.pl_on = QCheckBox(self)
        self.pl_on.hide()
        vf = (model.analysis_set_value("source_volumetric", "F")
              or "F").strip().upper()
        pl = (model.analysis_set_value("source_pressure_loss", "F")
              or "F").strip().upper()
        self.vf_on.setChecked(vf in ("T", "1"))
        self.pl_on.setChecked(pl in ("T", "1"))
        self.vol_display.currentIndexChanged.connect(self.refresh)
        self.area_display.currentIndexChanged.connect(self.refresh)
        self.perf_display.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _make_list_tab(self, blurb: str, *, star: bool, new_actions,
                       face_buttons: bool, existing: bool):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(blurb, page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", page))
        display = QComboBox(page)
        display.addItems(["All regions", "Domain", "DomainBoundary", "Parts"])
        drow.addWidget(display, 1)
        drow.addStretch(1)
        lay.addLayout(drow)

        body = QHBoxLayout()
        headers = (["Region name", "*", "Region type", "Condition name"]
                   if star else
                   ["Region name", "Region type", "Condition name"])
        table = QTableWidget(0, len(headers), page)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(table, 1)

        right = QVBoxLayout()
        new_box = QGroupBox("New", page)
        nl = QVBoxLayout(new_box)
        for label, slot in new_actions:
            b = QPushButton(label, new_box)
            b.clicked.connect(slot)
            nl.addWidget(b)
        right.addWidget(new_box)
        if existing:
            ex = QGroupBox("Existing conditions", page)
            el = QVBoxLayout(ex)
            btn_ex = QPushButton("Existing conditions", ex)
            btn_ex.clicked.connect(
                lambda: self._assign_existing(table, star))
            el.addWidget(btn_ex)
            right.addWidget(ex)
        right.addStretch(1)
        body.addLayout(right)
        lay.addLayout(body, 1)

        brow = QHBoxLayout()
        if face_buttons:
            b_create = QPushButton("Create Face...", page)
            b_create.clicked.connect(lambda: self._create_face(table))
            brow.addWidget(b_create)
            b_edit = QPushButton("Edit Face...", page)
            b_edit.clicked.connect(lambda: self._edit_face(table))
            brow.addWidget(b_edit)
        btn_edit = QPushButton("Edit...", page)
        btn_cancel = QPushButton("Cancel", page)
        btn_select = QPushButton("Select", page)
        btn_select.setToolTip(
            "Select all visible region rows; Ctrl+click adds individual rows.")
        btn_select.clicked.connect(lambda: self._select_all(table))
        btn_edit.clicked.connect(
            lambda: self._edit_selected(table, star))
        btn_cancel.clicked.connect(
            lambda: self._cancel_selected(table, star))
        brow.addWidget(btn_edit)
        brow.addWidget(btn_cancel)
        brow.addStretch(1)
        brow.addWidget(btn_select)
        lay.addLayout(brow)
        tip = QLabel("Select from list > New", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)
        # stash star flag on table
        table.setProperty("star_col", star)
        return page, table, display

    # -- refresh ----------------------------------------------------------

    def _domain_name(self) -> str:
        return self.model.domain_name() or "Domain"

    def _bindings(self, types: frozenset) -> list[tuple[str, str, str]]:
        from cabxml import _first
        names = set()
        for v in self.model.values():
            if v.attrib.get("type") in types:
                for ch in v:
                    if ch.tag == "name" and ch.text:
                        names.add(ch.text.strip())
        rows = []
        for c in self.model.conditions():
            v = _first(c, "value")
            vname = (v.text or "").strip() if v is not None else ""
            if vname not in names:
                continue
            region, rtype = "", ""
            for kind, label in (("analysis", "Domain"),
                                ("parts", "Parts"),
                                ("region", "DomainBoundary")):
                t = _first(c, kind)
                if t is not None and (t.text or "").strip():
                    region = (t.text or "").strip()
                    rtype = label
                    break
            if region:
                rows.append((region, rtype, vname))
        return rows

    def _fill_table(self, table: QTableWidget, display: QComboBox,
                    types: frozenset, *,
                    seed_domain: bool, seed_faces: bool) -> None:
        star = bool(table.property("star_col"))
        filt = display.currentText()
        rows = self._bindings(types)
        if filt == "Domain":
            rows = [r for r in rows if r[1] == "Domain"]
        elif filt == "DomainBoundary":
            rows = [r for r in rows if r[1] == "DomainBoundary"]
        elif filt == "Parts":
            rows = [r for r in rows if r[1] == "Parts"]
        shown = {(r[0], r[1]) for r in rows}
        table.setRowCount(0)

        def add(region, rtype, cname=""):
            i = table.rowCount()
            table.insertRow(i)
            vals = ([region, "", rtype, cname] if star
                    else [region, rtype, cname])
            for c, text in enumerate(vals):
                table.setItem(i, c, QTableWidgetItem(text))

        for region, rtype, cname in rows:
            add(region, rtype, cname)
        if seed_domain and filt in ("All regions", "Domain"):
            dname = self._domain_name()
            if (dname, "Domain") not in shown:
                add(dname, "Domain", "")
        if seed_faces and filt in ("All regions", "DomainBoundary"):
            for face, _el in self.model.domain_faces():
                if (face, "DomainBoundary") not in shown:
                    add(face, "DomainBoundary", "")
            # custom sub-faces created by Create Face... also appear
            from cabxml import _first as _f
            ar = self.model.analysis_region()
            for r in (list(ar) if ar is not None else []):
                if r.attrib.get("type") != "face_list":
                    continue
                n = _f(r, "name")
                if n is None or not (n.text or "").strip():
                    continue
                nm = n.text.strip()
                if nm not in {f for f, _e in self.model.domain_faces()} \
                        and (nm, "DomainBoundary") not in shown:
                    add(nm, "DomainBoundary", "")

    def refresh(self) -> None:
        self._fill_table(
            self.vol_table, self.vol_display, _SRC_VOL_TYPES,
            seed_domain=True, seed_faces=False)
        self._fill_table(
            self.area_table, self.area_display, _SRC_AREA_TYPES,
            seed_domain=False, seed_faces=True)
        self._fill_table(
            self.perf_table, self.perf_display, frozenset({"perforated_plate"}),
            seed_domain=False, seed_faces=True)
        # sync legacy checkboxes from presence of conditions
        self.vf_on.setChecked(any(
            v.attrib.get("type") == "volumetric_force"
            for v in self.model.values()))
        self.pl_on.setChecked(any(
            v.attrib.get("type") in (
                "volumetric_pressure_loss", "area_pressure_loss")
            for v in self.model.values()))

    def _selected(self, table: QTableWidget, star: bool):
        sel = table.selectionModel().selectedRows()
        if not sel:
            return "", "", ""
        row = sel[0].row()
        c0 = 0
        c_type = 2 if star else 1
        c_name = 3 if star else 2
        region = table.item(row, c0).text() if table.item(row, c0) else ""
        rtype = (table.item(row, c_type).text()
                 if table.item(row, c_type) else "")
        cname = (table.item(row, c_name).text()
                 if table.item(row, c_name) else "")
        return region, rtype, cname

    def _bind_target(self, region: str, rtype: str, cname: str) -> None:
        kind = ("analysis" if rtype == "Domain"
                else "parts" if rtype == "Parts" else "region")
        if not region:
            region = self._domain_name()
            kind = "analysis"
        self.model.bind_condition(kind, region, cname)

    def _selected_regions(self, table: QTableWidget, star: bool
                          ) -> list[tuple[str, str]]:
        """All selected region rows (Ctrl/Shift multi-select)."""
        out: list[tuple[str, str]] = []
        for idx in table.selectionModel().selectedRows():
            row = idx.row()
            c0 = 0
            c_type = 2 if star else 1
            region = table.item(row, c0).text() if table.item(row, c0) else ""
            rtype = (table.item(row, c_type).text()
                     if table.item(row, c_type) else "")
            if region:
                out.append((region, rtype))
        return out

    def _select_all(self, table: QTableWidget) -> None:
        table.selectAll()
        self._log(f"Select: {table.selectionModel().selectedRows().__len__()}"
                  " region row(s) selected.")

    @staticmethod
    def _write_face_region(model: StpreModel, region_name: str, face: str,
                           u0: float, u1: float,
                           v0: float, v1: float) -> bool:
        """Create/update an axis-aligned sub-face region on a boundary face.

        Persisted as ``<analysis_region><region type="face_list">`` with
        ``name`` / ``parent`` (Xmin…Zmax) / ``u0,u1,v0,v1`` (normalised
        0..1 along the face's local U/V axes).  S-file export mapping for
        partial faces is still a documented limitation (L5).
        """
        import xml.etree.ElementTree as ET
        from cabxml import _first
        ar = model.analysis_region()
        if ar is None:
            model.ensure_domain()
            ar = model.analysis_region()
        if ar is None:
            return False
        reg = None
        for r in list(ar):
            n = _first(r, "name")
            if (r.attrib.get("type") == "face_list"
                    and n is not None
                    and (n.text or "").strip() == region_name):
                reg = r
                break
        if reg is None:
            reg = ET.SubElement(ar, "region")
            reg.attrib["type"] = "face_list"
            reg.tail = "\n   "

        def _set(tag: str, text: str) -> None:
            el = _first(reg, tag)
            if el is None:
                el = ET.SubElement(reg, tag)
                el.tail = "\n      "
            el.text = f" {text} "

        _set("name", region_name)
        _set("parent", face)
        _set("u0", f"{u0:g}")
        _set("u1", f"{u1:g}")
        _set("v0", f"{v0:g}")
        _set("v1", f"{v1:g}")
        return True

    def _face_dialog(self, *, region_name: str = "", face: str = "Xmin",
                     u0: float = 0.0, u1: float = 1.0,
                     v0: float = 0.0, v1: float = 1.0) -> Optional[dict]:
        from PyQt5.QtWidgets import (
            QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLineEdit,
            QPushButton, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Face (Create/Edit)")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit(region_name or "Face1", dlg)
        _pair(lay, "Face name", name_ed)
        face_cb = QComboBox(dlg)
        face_cb.addItems(["Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"])
        if face in [face_cb.itemText(i) for i in range(face_cb.count())]:
            face_cb.setCurrentText(face)
        _pair(lay, "Boundary face", face_cb)
        spins: dict[str, QDoubleSpinBox] = {}
        for key, label, default in (
                ("u0", "U from", u0), ("u1", "U to", u1),
                ("v0", "V from", v0), ("v1", "V to", v1)):
            sp = QDoubleSpinBox(dlg)
            sp.setRange(0.0, 1.0)
            sp.setDecimals(4)
            sp.setValue(default)
            _pair(lay, label, sp)
            spins[key] = sp
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return None
        return {
            "name": name_ed.text().strip() or "Face1",
            "face": face_cb.currentText(),
            "u0": spins["u0"].value(), "u1": spins["u1"].value(),
            "v0": spins["v0"].value(), "v1": spins["v1"].value(),
        }

    def _create_face(self, table: QTableWidget) -> None:
        res = self._face_dialog()
        if res is None:
            return
        if self._write_face_region(
                self.model, res["name"], res["face"],
                res["u0"], res["u1"], res["v0"], res["v1"]):
            self.refresh()
            self._log(
                f"Created face '{res['name']}' on {res['face']} "
                f"U[{res['u0']:g},{res['u1']:g}] "
                f"V[{res['v0']:g},{res['v1']:g}]")

    def _edit_face(self, table: QTableWidget) -> None:
        star = bool(table.property("star_col"))
        region, _rtype, _cname = self._selected(table, star)
        if not region:
            self._log("Edit Face: select a face region row first.", "WARN")
            return
        from cabxml import _first
        face, u0, u1, v0, v1 = "Xmin", 0.0, 1.0, 0.0, 1.0
        ar = self.model.analysis_region()
        for r in (list(ar) if ar is not None else []):
            n = _first(r, "name")
            if (r.attrib.get("type") != "face_list" or n is None
                    or (n.text or "").strip() != region):
                continue
            p = _first(r, "parent")
            if p is not None and (p.text or "").strip():
                face = p.text.strip()
            for tag in ("u0", "u1", "v0", "v1"):
                el = _first(r, tag)
                if el is not None and el.text:
                    try:
                        val = float(el.text.strip())
                    except ValueError:
                        continue
                    if tag == "u0":
                        u0 = val
                    elif tag == "u1":
                        u1 = val
                    elif tag == "v0":
                        v0 = val
                    else:
                        v1 = val
            break
        res = self._face_dialog(
            region_name=region, face=face, u0=u0, u1=u1, v0=v0, v1=v1)
        if res is None:
            return
        if self._write_face_region(
                self.model, res["name"], res["face"],
                res["u0"], res["u1"], res["v0"], res["v1"]):
            self.refresh()
            self._log(f"Edited face '{res['name']}' on {res['face']}")

    # -- New dialogs ------------------------------------------------------

    def _dlg_name_value(self, title: str, default_name: str,
                        fields: list[tuple[str, str, float, str]],
                        *, unit_choices: Optional[list[str]] = None):
        """Simple name + numeric fields dialog.

        ``fields`` = list of (label, unit, default, attr_key unused).
        Returns (name, [values], unit_or_None) or None.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit(default_name, dlg)
        _pair(lay, "Condition name", name_ed)
        spins = []
        for label, unit, default, _k in fields:
            sp = QDoubleSpinBox(dlg)
            sp.setDecimals(6)
            sp.setRange(-1.0e12, 1.0e12)
            sp.setValue(default)
            _pair(lay, label, sp, unit)
            spins.append(sp)
        unit_combo = None
        if unit_choices:
            unit_combo = QComboBox(dlg)
            unit_combo.addItems(list(unit_choices))
            _pair(lay, "Unit", unit_combo)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return None
        cname = name_ed.text().strip() or default_name
        unit = unit_combo.currentText() if unit_combo is not None else None
        return cname, [sp.value() for sp in spins], unit

    def _new_vol_force(self) -> None:
        res = self._dlg_name_value(
            "Condition (Volumetric Force)", "VolForce1",
            [("X-component", "N/m3", 0.0, "x"),
             ("Y-component", "N/m3", 0.0, "y"),
             ("Z-component", "N/m3", -1.0, "z")])
        if res is None:
            return
        name, vals, _unit = res
        self.model.upsert_value("volumetric_force", name, [
            ("force", ",".join(f"{v:g}" for v in vals), "N/m3"),
            ("fx", f"{vals[0]:g}", "N/m3"),
            ("fy", f"{vals[1]:g}", "N/m3"),
            ("fz", f"{vals[2]:g}", "N/m3"),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self.vf_on.setChecked(True)
        self._log(f"Source: volumetric force '{name}'")
        self.refresh()

    def _new_vol_ploss(self) -> None:
        res = self._dlg_name_value(
            "Condition (Volumetric Pressure Loss)", "VolPLoss1",
            [("Loss coefficient", "", 0.0, "c")])
        if res is None:
            return
        name, vals, _unit = res
        self.model.upsert_value("volumetric_pressure_loss", name, [
            ("coeff", f"{vals[0]:g}", None),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self.pl_on.setChecked(True)
        self._log(f"Source: volumetric pressure loss '{name}'")
        self.refresh()

    def _new_vol_heat(self) -> None:
        # STpre SetHeatSource unit set (Doc class manual): W, W/m3,
        # Kcal/h, Kcal/h/m3, W/m2.
        res = self._dlg_name_value(
            "Condition (Volumetric Heat Source)", "HeatSource1",
            [("Heat source", "W", 0.0, "q")],
            unit_choices=["W", "W/m3", "Kcal/h", "Kcal/h/m3", "W/m2"])
        if res is None:
            return
        name, vals, unit = res
        unit = unit or "W"
        self.model.upsert_value("heat_source", name, [
            ("source", f"{vals[0]:g}", unit),
            ("heat", f"{vals[0]:g}", unit),
            ("kind", "volumetric", None),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: volumetric heat source '{name}' "
                  f"({vals[0]:g} {unit})")
        self.refresh()

    def _new_vol_term(self) -> None:
        res = self._dlg_name_value(
            "Condition (Source Term)", "SourceTerm1",
            [("Source term", "", 0.0, "s")])
        if res is None:
            return
        name, vals, _unit = res
        self.model.upsert_value("source_term", name, [
            ("param", f"{vals[0]:g}", None),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: generalized source term '{name}'")
        self.refresh()

    def _new_vol_moisture(self) -> None:
        """C2: humidity source (STpre [Moisture source], humidity analysis)."""
        res = self._dlg_name_value(
            "Condition (Humidification)", "MoistSource1",
            [("Moisture source", "kg/s", 0.0, "q")])
        if res is None:
            return
        name, vals, unit = res
        self.model.upsert_value("moisture_source", name, [
            ("source", f"{vals[0]:g}", unit or "kg/s"),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: moisture source '{name}' "
                  f"({vals[0]:g} {unit or 'kg/s'})")
        self.refresh()

    def _new_vol_smoke(self) -> None:
        """C2: smoke source (STpre [Smoke source], diffusion/reaction)."""
        res = self._dlg_name_value(
            "Condition (Smoke)", "SmokeSource1",
            [("Smoke source", "kg/s", 0.0, "q")])
        if res is None:
            return
        name, vals, unit = res
        self.model.upsert_value("smoke_source", name, [
            ("source", f"{vals[0]:g}", unit or "kg/s"),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: smoke source '{name}' "
                  f"({vals[0]:g} {unit or 'kg/s'})")
        self.refresh()

    def _new_vol_humidification(self) -> None:
        """P2: humidification source (STpre [Humidification], humidity)."""
        res = self._dlg_name_value(
            "Condition (Humidification)", "Humidify1",
            [("Humidification", "kg/s", 0.0, "q")])
        if res is None:
            return
        name, vals, unit = res
        self.model.upsert_value("humidification", name, [
            ("source", f"{vals[0]:g}", unit or "kg/s"),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: humidification '{name}' "
                  f"({vals[0]:g} {unit or 'kg/s'})")
        self.refresh()

    def _new_vol_canopy(self) -> None:
        """P2: plant canopy source (STpre [Plant Canopy], drag/transpiration)."""
        res = self._dlg_name_value(
            "Condition (Plant Canopy)", "Canopy1",
            [("Leaf area density", "1/m", 0.0, "a"),
             ("Drag coefficient", "", 0.2, "c")])
        if res is None:
            return
        name, vals, unit = res
        self.model.upsert_value("plant_canopy", name, [
            ("leaf_area_density", f"{vals[0]:g}", unit or "1/m"),
            ("drag_coefficient", f"{vals[1]:g}", ""),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: plant canopy '{name}' "
                  f"(LAD {vals[0]:g} 1/m)")
        self.refresh()

    def _new_vol_driver(self) -> None:
        """P2: LES driver source (STpre [Driver], velocity fluctuation)."""
        res = self._dlg_name_value(
            "Condition (Driver)", "Driver1",
            [("Velocity amplitude", "m/s", 0.0, "v"),
             ("Frequency", "Hz", 1.0, "f")])
        if res is None:
            return
        name, vals, unit = res
        self.model.upsert_value("driver", name, [
            ("velocity", f"{vals[0]:g}", unit or "m/s"),
            ("frequency", f"{vals[1]:g}", "Hz"),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: LES driver '{name}' "
                  f"(amplitude {vals[0]:g} m/s)")
        self.refresh()

    def _new_vol_time_series(self) -> None:
        """P2: time-series volumetric source (table of time/value pairs)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Time Series)")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit("TimeSeries1", dlg)
        _pair(lay, "Condition name", name_ed)
        table = QTableWidget(0, 2, dlg)
        table.setHorizontalHeaderLabels(["Time (s)", "Value"])
        table.horizontalHeader().setStretchLastSection(True)
        for t, v in ((0.0, 0.0), (1.0, 1.0)):
            table.insertRow(table.rowCount())
            table.setItem(table.rowCount() - 1, 0, QTableWidgetItem(f"{t:g}"))
            table.setItem(table.rowCount() - 1, 1, QTableWidgetItem(f"{v:g}"))
        lay.addWidget(table)
        row = QHBoxLayout()
        add_btn = QPushButton("Add row", dlg)
        del_btn = QPushButton("Remove row", dlg)
        add_btn.clicked.connect(lambda: (
            table.insertRow(table.rowCount()),
            table.setItem(table.rowCount() - 1, 0,
                          QTableWidgetItem("0")),
            table.setItem(table.rowCount() - 1, 1,
                          QTableWidgetItem("0"))))
        del_btn.clicked.connect(
            lambda: table.removeRow(table.currentRow())
            if table.currentRow() >= 0 else None)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        lay.addLayout(row)
        btns = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        if not dlg.exec_():
            return
        name = name_ed.text().strip() or "TimeSeries1"
        pairs = []
        for r in range(table.rowCount()):
            it_t = table.item(r, 0)
            it_v = table.item(r, 1)
            if it_t is None or it_v is None:
                continue
            try:
                t = float(it_t.text().strip())
                v = float(it_v.text().strip())
            except ValueError:
                continue
            pairs.append(f"{t:g}:{v:g}")
        if not pairs:
            return
        self.model.upsert_value("time_series", name, [
            ("data", ";".join(pairs), None),
        ])
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: time series '{name}' ({len(pairs)} pairs)")
        self.refresh()

    def _write_expression_source(self, name: str, expr_name: str,
                                 formula: str, unit: str) -> None:
        """P2: expression (computing-function) heat source.

        STpre COM-probed shape (2026-08-15): <express> computing function
        + <value type="heat_source"><source type="express" unit>
        expr_name </source></value>.
        """
        self.model.upsert_express(expr_name, "VENT_source", formula)
        self.model.upsert_value("heat_source", name, [
            ("source", expr_name, unit),
            ("kind", "volumetric", None),
        ])
        from cabxml import _first
        v = self.model.find_value(name)
        src_el = _first(v, "source") if v is not None else None
        if src_el is not None:
            src_el.attrib["type"] = "express"

    def _new_vol_expression(self) -> None:
        """P2: expression source (STpre computing-function heat source)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Expression)")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit("ExprSource1", dlg)
        _pair(lay, "Condition name", name_ed)
        expr_ed = QLineEdit("ExprSource1_f", dlg)
        _pair(lay, "Function name", expr_ed)
        formula_ed = QLineEdit("1000*sin(2*pi*t)", dlg)
        _pair(lay, "Formula (t = time)", formula_ed)
        unit_cb = QComboBox(dlg)
        unit_cb.addItems(["W/m3", "W", "W/m2", "Kcal/h", "Kcal/h/m3"])
        _pair(lay, "Unit", unit_cb)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return
        name = name_ed.text().strip() or "ExprSource1"
        expr_name = expr_ed.text().strip() or f"{name}_f"
        formula = formula_ed.text().strip() or "0"
        unit = unit_cb.currentText()
        self._write_expression_source(name, expr_name, formula, unit)
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: expression '{name}' -> {expr_name}")
        self.refresh()

    def _manage_expressions(self) -> None:
        """R2: expression manager — list / edit / delete <express> functions."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Expressions")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Computing functions used by expression conditions.", dlg))
        table = QTableWidget(0, 3, dlg)
        table.setHorizontalHeaderLabels(["Name", "Kind", "Formula"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        rows = self.model.express_list()
        table.setRowCount(len(rows))
        for r, (name, kind, formula) in enumerate(rows):
            for c, txt in enumerate((name, kind, formula)):
                table.setItem(r, c, QTableWidgetItem(txt))
        table.setCurrentCell(0, 0)
        lay.addWidget(table, 1)

        def _selected() -> Optional[tuple[str, str, str]]:
            r = table.currentRow()
            if 0 <= r < len(rows):
                return rows[r]
            return None

        def _edit() -> None:
            sel = _selected()
            if sel is None:
                return
            name, kind, formula = sel
            ed = QDialog(dlg)
            ed.setWindowTitle(f"Edit expression '{name}'")
            elay = QVBoxLayout(ed)
            formula_ed = QLineEdit(formula, ed)
            _pair(elay, "Formula (t = time)", formula_ed)
            brow = QHBoxLayout()
            ok = QPushButton("OK", ed)
            cancel = QPushButton("Cancel", ed)
            ok.clicked.connect(ed.accept)
            cancel.clicked.connect(ed.reject)
            brow.addStretch(1)
            brow.addWidget(ok)
            brow.addWidget(cancel)
            elay.addLayout(brow)
            if ed.exec_() and formula_ed.text().strip():
                self.model.upsert_express(name, kind,
                                          formula_ed.text().strip())
                self._log(f"Source: expression '{name}' updated")
                dlg.accept()

        def _delete() -> None:
            sel = _selected()
            if sel is None:
                return
            name = sel[0]
            refs = self.model.express_referenced_by(name)
            if refs:
                ret = QMessageBox.question(
                    dlg, "Delete expression",
                    f"'{name}' is referenced by: {', '.join(refs)}.\n"
                    "Delete the expression and those conditions too?")
                if ret != QMessageBox.Yes:
                    return
                self.model.delete_express(name, cascade=True)
                self._log(f"Source: expression '{name}' deleted "
                          f"(with {len(refs)} condition(s))")
            else:
                self.model.delete_express(name)
                self._log(f"Source: expression '{name}' deleted")
            dlg.accept()

        row = QHBoxLayout()
        edit_btn = QPushButton("Edit", dlg)
        del_btn = QPushButton("Delete", dlg)
        close = QPushButton("Close", dlg)
        edit_btn.clicked.connect(_edit)
        del_btn.clicked.connect(_delete)
        close.clicked.connect(dlg.accept)
        row.addWidget(edit_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec_()
        self.refresh()

    def _write_diffusion_source(self, name: str, no: int, amount: float,
                                unit: str) -> None:
        """P2: diffusion (mass diffusion) source condition.

        STpre COM-probed shape (2026-08-15, SetDiffusionCondition(name, no,
        'source', amount, 0)): <value type="diffusion"><kind> source
        </kind><no> N </no><diff_source unit> amount </diff_source></value>.
        """
        self.model.upsert_value("diffusion", name, [
            ("kind", "source", None),
            ("no", str(int(no)), None),
            ("diff_source", f"{amount:g}", unit),
        ])

    def _new_vol_diffusion(self) -> None:
        """P2: diffusion source (STpre SetDiffusionCondition 'source')."""
        res = self._dlg_name_value(
            "Condition (Diffusion Source)", "DiffSource1",
            [("Species number", "", 1.0, "n"),
             ("Amount", "mol/s", 0.0, "a")],
            unit_choices=["mol/s", "kg/s", "1/s"])
        if res is None:
            return
        name, vals, unit = res
        self._write_diffusion_source(
            name, int(vals[0]), vals[1], unit or "mol/s")
        regions = self._selected_regions(self.vol_table, False)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "Domain", name)
        self._log(f"Source: diffusion source '{name}' "
                  f"(species {int(vals[0])}, {vals[1]:g} {unit or 'mol/s'})")
        self.refresh()

    def _new_area_ploss(self) -> None:
        res = self._dlg_name_value(
            "Condition (Area Pressure Loss)", "AreaPLoss1",
            [("Loss coefficient", "", 0.0, "c")])
        if res is None:
            return
        name, vals, _unit = res
        self.model.upsert_value("area_pressure_loss", name, [
            ("coeff", f"{vals[0]:g}", None),
        ])
        regions = self._selected_regions(self.area_table, True)
        if not regions:
            regions = [("Xmin", "DomainBoundary")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "DomainBoundary", name)
        self.pl_on.setChecked(True)
        self._log(f"Source: area pressure loss '{name}' on {region}")
        self.refresh()

    def _new_area_heat(self) -> None:
        res = self._dlg_name_value(
            "Condition (Area Heat Source)", "AreaHeat1",
            [("Heat source", "W", 0.0, "q")],
            unit_choices=["W", "W/m2"])
        if res is None:
            return
        name, vals, unit = res
        unit = unit or "W"
        self.model.upsert_value("area_heat_source", name, [
            ("source", f"{vals[0]:g}", unit),
            ("heat", f"{vals[0]:g}", unit),
            ("kind", "area", None),
        ])
        regions = self._selected_regions(self.area_table, True)
        if not regions:
            regions = [("Xmin", "DomainBoundary")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "DomainBoundary", name)
        self._log(f"Source: area heat source '{name}' on {region} "
                  f"({vals[0]:g} {unit})")
        self.refresh()

    def _new_perforated(self) -> None:
        res = self._dlg_name_value(
            "Condition (Perforated Plate)", "PerfPlate1",
            [("Pressure loss coefficient", "", 0.0, "c")])
        if res is None:
            return
        name, vals, _unit = res
        self.model.upsert_value("perforated_plate", name, [
            ("coeff", f"{vals[0]:g}", None),
        ])
        regions = self._selected_regions(self.perf_table, False)
        if not regions:
            regions = [("Xmin", "DomainBoundary")]
        for region, rtype in regions:
            self._bind_target(region, rtype or "DomainBoundary", name)
        self._log(f"Source: perforated plate '{name}' on {region}")
        self.refresh()

    def _assign_existing(self, table: QTableWidget, star: bool) -> None:
        types = (_SRC_VOL_TYPES if table is self.vol_table
                 else _SRC_AREA_TYPES if table is self.area_table
                 else frozenset({"perforated_plate"}))
        names = []
        for v in self.model.values():
            if v.attrib.get("type") in types:
                for ch in v:
                    if ch.tag == "name" and ch.text:
                        names.append(ch.text.strip())
        if not names:
            QMessageBox.information(
                self, "Existing conditions",
                "No source conditions of this type exist yet.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "List of Existing Conditions",
            "Condition name:", names, 0, False)
        if not ok or not name:
            return
        regions = self._selected_regions(table, star)
        if not regions:
            regions = [(self._domain_name(), "Domain")]
        for region, rtype in regions:
            self._bind_target(region, rtype, name)
        self.refresh()

    def _edit_selected(self, table: QTableWidget, star: bool) -> None:
        region, _rtype, cname = self._selected(table, star)
        if not cname:
            QMessageBox.information(
                self, "Edit", "Select a region that already has a condition, "
                "or use New.")
            return
        val = self.model.find_value(cname)
        if val is None:
            return
        from cabxml import _first
        # edit first numeric-ish child
        for tag in ("source", "force", "coeff", "param"):
            el = _first(val, tag)
            if el is None or not el.text:
                continue
            try:
                cur = float(el.text.strip().split(",")[0])
            except ValueError:
                cur = 0.0
            unit = el.attrib.get("unit", "")
            new_v, ok = QtWidgets.QInputDialog.getDouble(
                self, f"Edit {cname}",
                f"{tag} [{unit}]:" if unit else f"{tag}:",
                cur, -1.0e12, 1.0e12, 6)
            if ok:
                text = el.text.strip()
                if "," in text:
                    parts = text.split(",")
                    parts[0] = f"{new_v:g}"
                    self.model.upsert_value(
                        val.attrib.get("type", "heat_source"), cname,
                        [(tag, ",".join(parts), unit or None)])
                else:
                    self.model.upsert_value(
                        val.attrib.get("type", "heat_source"), cname,
                        [(tag, f"{new_v:g}", unit or None)])
                self.refresh()
            return
        self._log(f"Source: nothing editable on '{cname}' ({region})")

    def _cancel_selected(self, table: QTableWidget, star: bool) -> None:
        region, rtype, cname = self._selected(table, star)
        if not cname or not region:
            return
        from cabxml import _first
        kind = ("analysis" if rtype == "Domain"
                else "parts" if rtype == "Parts" else "region")
        for c in list(self.model.conditions()):
            t = _first(c, kind)
            v = _first(c, "value")
            if t is None or v is None:
                continue
            if (t.text or "").strip() == region and \
                    (v.text or "").strip() == cname:
                self.model.root.remove(c)
                break
        self._log(f"Source: cancelled '{cname}' on {region}")
        self.refresh()

    def apply(self) -> None:
        # M36: Option flags + auto-mark volumetric/pressure when values exist
        types_present = {
            (v.attrib.get("type") or "").strip()
            for v in self.model.values()}
        has_vf = ("volumetric_force" in types_present
                  or self.vf_on.isChecked())
        has_pl = bool(types_present & {
            "volumetric_pressure_loss", "area_pressure_loss",
            "perforated_plate"}) or self.pl_on.isChecked()
        has_heat = bool(types_present & {
            "heat_source", "area_heat_source"})
        has_term = "source_term" in types_present
        self.vf_on.setChecked(has_vf)
        self.pl_on.setChecked(has_pl)
        self.model.set_analysis_set_value(
            "source_volumetric", "T" if has_vf else "F")
        self.model.set_analysis_set_value(
            "source_pressure_loss", "T" if has_pl else "F")
        self.model.set_analysis_set_value(
            "source_heat", "T" if has_heat else "F")
        self.model.set_analysis_set_value(
            "source_term", "T" if has_term else "F")
        self.model.set_analysis_set_value(
            "heat_source_auto",
            "T" if self.hs_auto.isChecked() else "F")
        # Heat analysis must be on when heat sources exist.
        if has_heat:
            self.model.set_analysis_set_value("heat", "1")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_log"):
                parent._log(msg)
                return
            if hasattr(parent, "log"):
                parent.log(msg)
                return
            parent = parent.parent()


class _CwFixedPage(QWidget if _HAS_GUI else object):
    """STpre Condition Wizard → Fixed Condition
    (Temperature / Velocity / Option)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self.model.ensure_domain_faces()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)

        # --- Fixed Temperature ---
        self.temp_page, self.temp_table, self.temp_display = \
            self._make_list_tab(
                "Sets the fixed temperature conditions.",
                star=True,
                new_label="Fixed temperature",
                new_slot=self._new_fixed_temp,
                face_buttons=False,
            )
        tabs.addTab(self.temp_page, "Fixed Temperature Condition")

        # --- Fixed Velocity ---
        self.vel_page, self.vel_table, self.vel_display = \
            self._make_list_tab(
                "Sets the fixed velocity conditions.",
                star=True,
                new_label="Fixed velocity",
                new_slot=self._new_fixed_vel,
                face_buttons=True,
            )
        tabs.addTab(self.vel_page, "Fixed Velocity Condition")

        # --- Option (cancel range) — matches STpre Option tab ---
        opage = QWidget()
        ol = QVBoxLayout(opage)
        ol.addWidget(QLabel(
            "Cancels fixed condition in a specified range.", opage))
        sep = QFrame(opage)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        ol.addWidget(sep)
        g1 = QGroupBox("Fixed temperature condition", opage)
        g1l = QVBoxLayout(g1)
        self.cancel_t = QCheckBox(
            "Set the temperature range to cancel fixed condition", g1)
        g1l.addWidget(self.cancel_t)
        self.cancel_t_type = QComboBox(g1)
        self.cancel_t_type.addItems([
            "Cancel if greater than threshold",
            "Cancel if less than threshold",
        ])
        self.cancel_t_thr = QDoubleSpinBox(g1)
        self.cancel_t_thr.setRange(-1e6, 1e6)
        _pair(g1l, "Type", self.cancel_t_type)
        _pair(g1l, "Threshold", self.cancel_t_thr, "C")
        ol.addWidget(g1)
        g2 = QGroupBox("Fixed flow velocity condition", opage)
        g2l = QVBoxLayout(g2)
        self.cancel_v = QCheckBox(
            "Set the velocity component range to cancel fixed condition", g2)
        g2l.addWidget(self.cancel_v)
        self.cancel_v_type = QComboBox(g2)
        self.cancel_v_type.addItems([
            "Cancel if greater than threshold",
            "Cancel if less than threshold",
        ])
        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Threshold"))
        self.cancel_v_thr = QDoubleSpinBox(g2)
        self.cancel_v_thr.setRange(0.0, 1e6)
        thr_row.addWidget(self.cancel_v_thr, 1)
        self.cancel_v_unit = QComboBox(g2)
        self.cancel_v_unit.addItems(["m/s", "cm/s", "mm/s"])
        thr_row.addWidget(self.cancel_v_unit)
        thr_row.addStretch(1)
        _pair(g2l, "Type", self.cancel_v_type)
        g2l.addLayout(thr_row)
        ol.addWidget(g2)
        ol.addStretch(1)
        tabs.addTab(opage, "Option")

        root.addWidget(tabs, 1)
        # legacy attrs for apply / callers
        self.fix_temp = QCheckBox(self); self.fix_temp.hide()
        self.fix_temp_val = QDoubleSpinBox(self); self.fix_temp_val.hide()
        self.fix_temp_val.setRange(-273.15, 1e6)
        self.fix_temp_val.setValue(20.0)
        self.fix_vel = QCheckBox(self); self.fix_vel.hide()
        self.fix_u = QDoubleSpinBox(self); self.fix_u.hide()
        self.fix_v = QDoubleSpinBox(self); self.fix_v.hide()
        self.fix_w = QDoubleSpinBox(self); self.fix_w.hide()
        for sp in (self.fix_u, self.fix_v, self.fix_w):
            sp.setRange(-1e6, 1e6)

        self.cancel_t.toggled.connect(self._sync_opt)
        self.cancel_v.toggled.connect(self._sync_opt)
        self.temp_display.currentIndexChanged.connect(self.refresh)
        self.vel_display.currentIndexChanged.connect(self.refresh)
        self._load_opt()
        self._sync_opt()
        self.refresh()

    def _make_list_tab(self, blurb: str, *, star: bool, new_label: str,
                       new_slot, face_buttons: bool):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(blurb, page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", page))
        display = QComboBox(page)
        display.addItems(["All regions", "Domain", "DomainBoundary", "Parts"])
        drow.addWidget(display, 1)
        drow.addStretch(1)
        lay.addLayout(drow)

        body = QHBoxLayout()
        headers = (["Region name", "*", "Region type", "Condition name"]
                   if star else
                   ["Region name", "Region type", "Condition name"])
        table = QTableWidget(0, len(headers), page)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(table, 1)

        right = QVBoxLayout()
        new_box = QGroupBox("New", page)
        nl = QVBoxLayout(new_box)
        btn = QPushButton(new_label, new_box)
        btn.clicked.connect(new_slot)
        nl.addWidget(btn)
        right.addWidget(new_box)
        ex = QGroupBox("Existing conditions", page)
        el = QVBoxLayout(ex)
        btn_ex = QPushButton("Existing conditions", ex)
        btn_ex.clicked.connect(
            lambda: self._assign_existing(table, new_label))
        el.addWidget(btn_ex)
        right.addWidget(ex)
        right.addStretch(1)
        body.addLayout(right)
        lay.addLayout(body, 1)

        brow = QHBoxLayout()
        if face_buttons:
            for text in ("Create Face...", "Edit Face..."):
                b = QPushButton(text, page)
                b.setEnabled(False)
                b.setToolTip(
                    "Face create/edit is not implemented in cabdecoding "
                    "(use DomainBoundary faces from Layout / Domain).")
                brow.addWidget(b)
        btn_edit = QPushButton("Edit...", page)
        btn_cancel = QPushButton("Cancel", page)
        btn_select = QPushButton("Select", page)
        btn_select.setEnabled(False)
        btn_select.setToolTip("Region multi-select not wired in cabdecoding.")
        btn_edit.clicked.connect(
            lambda: self._edit_selected(table, new_label))
        btn_cancel.clicked.connect(
            lambda: self._cancel_selected(table))
        brow.addWidget(btn_edit)
        brow.addWidget(btn_cancel)
        brow.addStretch(1)
        brow.addWidget(btn_select)
        lay.addLayout(brow)
        tip = QLabel("Select from list > New", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)
        table.setProperty("star_col", star)
        table.setProperty("kind", new_label)
        return page, table, display

    def _domain_name(self) -> str:
        return self.model.domain_name() or "Domain"

    def _bindings(self, vtype: str) -> list[tuple[str, str, str]]:
        from cabxml import _first
        names = set()
        for v in self.model.values():
            if v.attrib.get("type") != vtype:
                continue
            for ch in v:
                if ch.tag == "name" and ch.text:
                    names.add(ch.text.strip())
        rows = []
        for c in self.model.conditions():
            v = _first(c, "value")
            vname = (v.text or "").strip() if v is not None else ""
            if vname not in names:
                continue
            region, rtype = "", ""
            for kind, label in (("analysis", "Domain"),
                                ("parts", "Parts"),
                                ("region", "DomainBoundary")):
                t = _first(c, kind)
                if t is not None and (t.text or "").strip():
                    region = (t.text or "").strip()
                    rtype = label
                    break
            if region:
                rows.append((region, rtype, vname))
        return rows

    def _fill(self, table: QTableWidget, display: QComboBox, vtype: str,
              *, seed_domain: bool, seed_faces: bool) -> None:
        star = bool(table.property("star_col"))
        filt = display.currentText()
        rows = self._bindings(vtype)
        if filt == "Domain":
            rows = [r for r in rows if r[1] == "Domain"]
        elif filt == "DomainBoundary":
            rows = [r for r in rows if r[1] == "DomainBoundary"]
        elif filt == "Parts":
            rows = [r for r in rows if r[1] == "Parts"]
        shown = {(r[0], r[1]) for r in rows}
        table.setRowCount(0)

        def add(region, rtype, cname=""):
            i = table.rowCount()
            table.insertRow(i)
            vals = ([region, "", rtype, cname] if star
                    else [region, rtype, cname])
            for c, text in enumerate(vals):
                table.setItem(i, c, QTableWidgetItem(text))

        for region, rtype, cname in rows:
            add(region, rtype, cname)
        if seed_domain and filt in ("All regions", "Domain"):
            dname = self._domain_name()
            if (dname, "Domain") not in shown:
                add(dname, "Domain", "")
        if seed_faces and filt in ("All regions", "DomainBoundary"):
            for face, _el in self.model.domain_faces():
                if (face, "DomainBoundary") not in shown:
                    add(face, "DomainBoundary", "")

    def refresh(self) -> None:
        self._fill(self.temp_table, self.temp_display, "fixed_temperature",
                   seed_domain=True, seed_faces=False)
        self._fill(self.vel_table, self.vel_display, "fixed_velocity",
                   seed_domain=False, seed_faces=True)
        self.fix_temp.setChecked(any(
            v.attrib.get("type") == "fixed_temperature"
            for v in self.model.values()))
        self.fix_vel.setChecked(any(
            v.attrib.get("type") == "fixed_velocity"
            for v in self.model.values()))

    def _selected(self, table: QTableWidget):
        star = bool(table.property("star_col"))
        sel = table.selectionModel().selectedRows()
        if not sel:
            return "", "", ""
        row = sel[0].row()
        c_type = 2 if star else 1
        c_name = 3 if star else 2
        region = table.item(row, 0).text() if table.item(row, 0) else ""
        rtype = (table.item(row, c_type).text()
                 if table.item(row, c_type) else "")
        cname = (table.item(row, c_name).text()
                 if table.item(row, c_name) else "")
        return region, rtype, cname

    def _bind(self, region: str, rtype: str, cname: str) -> None:
        kind = ("analysis" if rtype == "Domain"
                else "parts" if rtype == "Parts" else "region")
        if not region:
            region = self._domain_name()
            kind = "analysis"
        self.model.bind_condition(kind, region, cname)

    def _new_fixed_temp(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Fixed Temperature)")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit("FixedTemp1", dlg)
        _pair(lay, "Condition name", name_ed)
        temp = QDoubleSpinBox(dlg)
        temp.setDecimals(2)
        temp.setRange(-273.15, 1e6)
        temp.setValue(self.fix_temp_val.value())
        unit = self.model.units.get("temperature", "C") or "C"
        _pair(lay, "Temperature", temp, unit)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg); cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        row.addStretch(1); row.addWidget(ok); row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return
        cname = name_ed.text().strip() or "FixedTemp1"
        self.model.upsert_value("fixed_temperature", cname, [
            ("temperature", f"{temp.value():g}", unit),
        ])
        region, rtype, _ = self._selected(self.temp_table)
        self._bind(region or self._domain_name(), rtype or "Domain", cname)
        self.fix_temp.setChecked(True)
        self.fix_temp_val.setValue(temp.value())
        self._log(f"Fixed Condition: temperature '{cname}' = {temp.value():g}")
        self.refresh()

    def _new_fixed_vel(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Fixed Velocity)")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit("FixedVel1", dlg)
        _pair(lay, "Condition name", name_ed)
        u = QDoubleSpinBox(dlg); v = QDoubleSpinBox(dlg); w = QDoubleSpinBox(dlg)
        for sp, ax, cur in ((u, "X", self.fix_u), (v, "Y", self.fix_v),
                            (w, "Z", self.fix_w)):
            sp.setDecimals(6); sp.setRange(-1e6, 1e6); sp.setValue(cur.value())
            _pair(lay, f"{ax}-component of velocity", sp, "m/s")
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg); cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        row.addStretch(1); row.addWidget(ok); row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return
        cname = name_ed.text().strip() or "FixedVel1"
        self.model.upsert_value("fixed_velocity", cname, [
            ("velocity", f"{u.value():g},{v.value():g},{w.value():g}", None),
        ])
        region, rtype, _ = self._selected(self.vel_table)
        if not region:
            region, rtype = "Xmin", "DomainBoundary"
        self._bind(region, rtype or "DomainBoundary", cname)
        self.fix_vel.setChecked(True)
        self.fix_u.setValue(u.value())
        self.fix_v.setValue(v.value())
        self.fix_w.setValue(w.value())
        self._log(f"Fixed Condition: velocity '{cname}' on {region}")
        self.refresh()

    def _assign_existing(self, table: QTableWidget, kind: str) -> None:
        vtype = ("fixed_temperature" if "temperature" in kind.lower()
                 else "fixed_velocity")
        names = []
        for v in self.model.values():
            if v.attrib.get("type") != vtype:
                continue
            for ch in v:
                if ch.tag == "name" and ch.text:
                    names.append(ch.text.strip())
        if not names:
            QMessageBox.information(
                self, "Existing conditions",
                f"No {vtype.replace('_', ' ')} conditions exist yet.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "List of Existing Conditions",
            "Condition name:", names, 0, False)
        if not ok or not name:
            return
        region, rtype, _ = self._selected(table)
        self._bind(region, rtype, name)
        self.refresh()

    def _edit_selected(self, table: QTableWidget, kind: str) -> None:
        region, _rtype, cname = self._selected(table)
        if not cname:
            QMessageBox.information(
                self, "Edit",
                "Select a region that already has a condition, or use New.")
            return
        if "temperature" in kind.lower():
            self._edit_temp(cname)
        else:
            self._edit_vel(cname)

    def _edit_temp(self, cname: str) -> None:
        from cabxml import _first
        val = self.model.find_value(cname)
        cur = self.fix_temp_val.value()
        unit = self.model.units.get("temperature", "C") or "C"
        if val is not None:
            el = _first(val, "temperature")
            if el is not None and el.text:
                try:
                    cur = float(el.text.strip())
                except ValueError:
                    pass
                unit = el.attrib.get("unit", unit)
        new_v, ok = QtWidgets.QInputDialog.getDouble(
            self, f"Edit {cname}", f"Temperature [{unit}]:",
            cur, -273.15, 1e6, 2)
        if not ok:
            return
        self.model.upsert_value("fixed_temperature", cname, [
            ("temperature", f"{new_v:g}", unit),
        ])
        self.fix_temp_val.setValue(new_v)
        self.refresh()

    def _edit_vel(self, cname: str) -> None:
        from cabxml import _first
        val = self.model.find_value(cname)
        ux, uy, uz = (self.fix_u.value(), self.fix_v.value(),
                      self.fix_w.value())
        if val is not None:
            el = _first(val, "velocity")
            if el is not None and el.text:
                parts = el.text.strip().split(",")
                try:
                    ux = float(parts[0]); uy = float(parts[1])
                    uz = float(parts[2])
                except (ValueError, IndexError):
                    pass
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {cname}")
        lay = QVBoxLayout(dlg)
        su = QDoubleSpinBox(dlg); sv = QDoubleSpinBox(dlg); sw = QDoubleSpinBox(dlg)
        for sp, ax, cur in ((su, "X", ux), (sv, "Y", uy), (sw, "Z", uz)):
            sp.setDecimals(6); sp.setRange(-1e6, 1e6); sp.setValue(cur)
            _pair(lay, f"{ax}-component", sp, "m/s")
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg); cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        row.addStretch(1); row.addWidget(ok); row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return
        self.model.upsert_value("fixed_velocity", cname, [
            ("velocity",
             f"{su.value():g},{sv.value():g},{sw.value():g}", None),
        ])
        self.fix_u.setValue(su.value())
        self.fix_v.setValue(sv.value())
        self.fix_w.setValue(sw.value())
        self.refresh()

    def _cancel_selected(self, table: QTableWidget) -> None:
        region, rtype, cname = self._selected(table)
        if not cname or not region:
            return
        from cabxml import _first
        kind = ("analysis" if rtype == "Domain"
                else "parts" if rtype == "Parts" else "region")
        for c in list(self.model.conditions()):
            t = _first(c, kind)
            v = _first(c, "value")
            if t is None or v is None:
                continue
            if (t.text or "").strip() == region and \
                    (v.text or "").strip() == cname:
                self.model.root.remove(c)
                break
        self._log(f"Fixed Condition: cancelled '{cname}' on {region}")
        self.refresh()

    def _load_opt(self) -> None:
        ct = self.model.analysis_set_value("fixt_cancel_temp", "0")
        self.cancel_t.setChecked(ct.strip().lower() in ("1", "t", "true"))
        try:
            self.cancel_t_thr.setValue(float(
                self.model.analysis_set_value("fixt_cancel_temp_thr", "0")))
        except ValueError:
            pass
        ttype = self.model.analysis_set_value(
            "fixt_cancel_temp_type", "greater")
        self.cancel_t_type.setCurrentIndex(
            0 if "less" not in ttype.lower() else 1)
        cv = self.model.analysis_set_value("fixt_cancel_vel", "0")
        self.cancel_v.setChecked(cv.strip().lower() in ("1", "t", "true"))
        try:
            self.cancel_v_thr.setValue(float(
                self.model.analysis_set_value("fixt_cancel_vel_thr", "0")))
        except ValueError:
            pass
        vtype = self.model.analysis_set_value(
            "fixt_cancel_vel_type", "greater")
        self.cancel_v_type.setCurrentIndex(
            0 if "less" not in vtype.lower() else 1)

    def _sync_opt(self) -> None:
        on_t = self.cancel_t.isChecked()
        self.cancel_t_type.setEnabled(on_t)
        self.cancel_t_thr.setEnabled(on_t)
        on_v = self.cancel_v.isChecked()
        self.cancel_v_type.setEnabled(on_v)
        self.cancel_v_thr.setEnabled(on_v)
        self.cancel_v_unit.setEnabled(on_v)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "fixed_temperature",
            "T" if self.fix_temp.isChecked() else "F")
        if self.fix_temp.isChecked():
            self.model.set_analysis_set_value(
                "fixed_temperature_value",
                f"{self.fix_temp_val.value():g}")
        self.model.set_analysis_set_value(
            "fixed_velocity",
            "T" if self.fix_vel.isChecked() else "F")
        self.model.set_analysis_set_value(
            "fixt_cancel_temp",
            "1" if self.cancel_t.isChecked() else "0")
        self.model.set_analysis_set_value(
            "fixt_cancel_temp_type",
            "less" if self.cancel_t_type.currentIndex() == 1 else "greater")
        self.model.set_analysis_set_value(
            "fixt_cancel_temp_thr", f"{self.cancel_t_thr.value():g}")
        self.model.set_analysis_set_value(
            "fixt_cancel_vel",
            "1" if self.cancel_v.isChecked() else "0")
        self.model.set_analysis_set_value(
            "fixt_cancel_vel_type",
            "less" if self.cancel_v_type.currentIndex() == 1 else "greater")
        self.model.set_analysis_set_value(
            "fixt_cancel_vel_thr", f"{self.cancel_v_thr.value():g}")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_log"):
                parent._log(msg)
                return
            if hasattr(parent, "log"):
                parent.log(msg)
                return
            parent = parent.parent()


class _CwAnalysisControlHubPage(QWidget if _HAS_GUI else object):
    """Analysis Control root — Simple / Detailed setting (STpre hub)."""

    def __init__(self, model: StpreModel, on_mode_changed=None):
        super().__init__()
        self.model = model
        self._on_mode_changed = on_mode_changed
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.addWidget(_note("Selects type of setting for analysis control.",
                           page))
        self.simple = QRadioButton("Simple setting", page)
        self.detailed = QRadioButton("Detailed setting", page)
        self.simple_bullets = QLabel(page)
        self.detailed_bullets = QLabel(page)
        for lab in (self.simple_bullets, self.detailed_bullets):
            lab.setStyleSheet("color: #333; margin-left: 18px;")
            lab.setWordWrap(True)
        pl.addWidget(self.simple)
        pl.addWidget(self.simple_bullets)
        pl.addWidget(self.detailed)
        pl.addWidget(self.detailed_bullets)
        detail = self.model.analysis_set_value("control_detail", "simple")
        if detail.strip().lower() in ("detailed", "1", "detail"):
            self.detailed.setChecked(True)
        else:
            self.simple.setChecked(True)
        self.simple.toggled.connect(self._mode_toggled)
        self.detailed.toggled.connect(self._mode_toggled)
        opt = QGroupBox("Options", page)
        ol = QVBoxLayout(opt)
        jfnk = QGroupBox("JFNK method", opt)
        jl = QHBoxLayout(jfnk)
        self.jfnk = QCheckBox("Consider JFNK method", jfnk)
        self.jfnk_mode = QComboBox(jfnk)
        self.jfnk_mode.addItems(["Forced convection", "Natural convection"])
        self.jfnk_mode.setEnabled(False)
        self.jfnk.toggled.connect(self.jfnk_mode.setEnabled)
        jl.addWidget(self.jfnk)
        jl.addWidget(self.jfnk_mode, 1)
        ol.addWidget(jfnk)
        apar = QGroupBox("Analysis parameters", opt)
        al = QHBoxLayout(apar)
        self.param_set = QCheckBox("Parameter set", apar)
        self.param_mode = QComboBox(apar)
        self.param_mode.addItems([
            "Default(solver-defined)",
            "High-Speed (Forced convection)",
            "High-Speed (Natural convection)",
            "JFNK (Forced convection)",
            "JFNK (Natural convection)",
            "Low-Mach-number approximation",
        ])
        self.param_mode.setEnabled(False)
        self.param_set.toggled.connect(self.param_mode.setEnabled)
        al.addWidget(self.param_set)
        al.addWidget(self.param_mode, 1)
        ol.addWidget(apar)
        pl.addWidget(opt)
        pl.addStretch(1)
        tabs.addTab(page, "Analysis Control")
        lay.addWidget(tabs, 1)
        self.refresh_bullets()

    def is_detailed(self) -> bool:
        return self.detailed.isChecked()

    def refresh_bullets(self) -> None:
        """Update Simple/Detailed bullet lists for steady vs transient."""
        transient = (self.model.analysis_set_value("calculation", "steady")
                     == "transient")
        if transient:
            simple = (
                "* Transient analysis(start/end cycle, Time step, "
                "Stop(Time))\n"
                "* Solver parameters(heat balance)")
            detailed = (
                "* Transient analysis\n"
                "* View factor\n"
                "* Solver parameters\n"
                "* Stabilization\n"
                "* Option(process interruption, unsupported analysis "
                "conditions, list of scripts)")
        else:
            simple = (
                "* Steady-state analysis(Start/End cycle, "
                "Steady-state convergence criteria)\n"
                "* Solver parameters(heat balance)")
            detailed = (
                "* Steady-state\n"
                "* View factor\n"
                "* Solver parameters\n"
                "* Stabilization\n"
                "* Option(process interruption, unsupported analysis "
                "conditions, list of scripts)")
        self.simple_bullets.setText(simple)
        self.detailed_bullets.setText(detailed)

    def _mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        if callable(self._on_mode_changed):
            self._on_mode_changed(self.is_detailed())

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "control_detail",
            "detailed" if self.detailed.isChecked() else "simple")


def _set_tab_visible(tabs: "QTabWidget", index: int, visible: bool) -> None:
    if index < 0 or index >= tabs.count():
        return
    if hasattr(tabs, "setTabVisible"):
        tabs.setTabVisible(index, visible)
    else:  # pragma: no cover - older Qt
        tabs.setTabEnabled(index, visible)


class _CwSteadyPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Steady-state Analysis (Cycle / Criteria / Stop)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        self.tabs = tabs

        # --- Cycle ---
        cyc = QWidget()
        cl = QVBoxLayout(cyc)
        cl.addWidget(_note("Specifies the number of cycles.", cyc))
        g = QGroupBox("Cycle", cyc)
        gl = QVBoxLayout(g)
        self.start_cycle = QDoubleSpinBox(g)
        self.start_cycle.setDecimals(0)
        self.start_cycle.setRange(1, 1e9)
        self.last_cycle = QDoubleSpinBox(g)
        self.last_cycle.setDecimals(0)
        self.last_cycle.setRange(1, 1e9)
        _pair(gl, "Start cycle no.", self.start_cycle)
        _pair(gl, "Last cycle no.", self.last_cycle)
        gl.addWidget(_note(
            "Note) Enter 1 in the start cycle no. for an initial "
            "calculation. Enter 2 or a larger number for a restart "
            "calculation.", g))
        cl.addWidget(g)
        # Time step is Transient-Analysis only (STpre Cycle for steady
        # has Start/Last cycle only).
        ts = QGroupBox("Time step", cyc)
        self.ts_box = ts
        tsl = QVBoxLayout(ts)
        self.ts_fixed = QRadioButton("Fixed time step", ts)
        self.ts_var = QRadioButton(
            "Variable time step (automatically calculated)", ts)
        self.ts_var.setChecked(True)
        tsl.addWidget(self.ts_fixed)
        tsl.addWidget(self.ts_var)
        self.init_dt = QDoubleSpinBox(ts)
        self.init_dt.setDecimals(6)
        self.init_dt.setRange(1.0e-9, 1.0e9)
        self.init_dt.setValue(0.01)
        _pair(tsl, "Initial time step", self.init_dt, "s")
        self.courant = QDoubleSpinBox(ts)
        self.courant.setDecimals(2)
        self.courant.setRange(0.01, 100.0)
        self.courant.setValue(0.9)
        _pair(tsl, "Courant number", self.courant)
        cl.addWidget(ts)
        cl.addStretch(1)
        tabs.addTab(cyc, "Cycle")

        # --- Convergence ---
        conv = QWidget()
        cvl = QVBoxLayout(conv)
        cvl.addWidget(_note(
            "Specifies the steady-state convergence criteria.", conv))
        g1 = QGroupBox(
            "Steady-state convergence criterion for each variable", conv)
        g1l = QVBoxLayout(g1)
        self.crit_table = QTableWidget(4, 4, g1)
        self.crit_table.setHorizontalHeaderLabels(
            ["Target", "Type", "Cycle interval", "Criterion"])
        self.crit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        for i, name in enumerate((
                "Flow", "Temperature",
                "Turbulent kinetic energy",
                "Turbulent dissipation rate")):
            self.crit_table.setItem(i, 0, QTableWidgetItem(name))
            self.crit_table.setItem(i, 1, QTableWidgetItem("Default"))
            self.crit_table.setItem(i, 2, QTableWidgetItem("1"))
            self.crit_table.setItem(i, 3, QTableWidgetItem("0.0001"))
        g1l.addWidget(self.crit_table)
        self.crit_type = QComboBox(g1)
        self.crit_type.addItems(["Default", "Absolute", "Relative"])
        _pair(g1l, "Criterion type", self.crit_type)
        g1l.addWidget(_note(
            "Note) When diffusive species is changed, this setting must "
            "be redone.", g1))
        cvl.addWidget(g1)
        g2 = QGroupBox(
            "Steady-state convergence criteria based on heat balance", conv)
        g2l = QVBoxLayout(g2)
        self.hbal = QCheckBox(
            "Specify the steady-state convergence criteria based on "
            "the heat balance", g2)
        g2l.addWidget(self.hbal)
        self.hbal_eps = QDoubleSpinBox(g2)
        self.hbal_eps.setDecimals(6)
        self.hbal_eps.setEnabled(False)
        self.hbal.toggled.connect(self.hbal_eps.setEnabled)
        _pair(g2l, "Criterion", self.hbal_eps)
        cvl.addWidget(g2)
        g3 = QGroupBox("Option for steady-state judgment", conv)
        g3l = QVBoxLayout(g3)
        self.steady_start = QDoubleSpinBox(g3)
        self.steady_start.setDecimals(0)
        self.steady_start.setRange(1, 1e9)
        self.steady_start.setValue(50)
        _pair(g3l, "Start cycle", self.steady_start)
        self.continue_ss = QCheckBox(
            "Continue calculation after it reaches the steady state", g3)
        g3l.addWidget(self.continue_ss)
        self.ss_hold = QDoubleSpinBox(g3)
        self.ss_hold.setDecimals(0)
        self.ss_hold.setRange(1, 1e6)
        self.ss_hold.setValue(1)
        _pair(g3l, "No. of cycles which steady state continues",
              self.ss_hold)
        g3l.addWidget(_note(
            "Note) Calculation will end when steady-state criteria are "
            "satisfied for the specified no. of cycles.", g3))
        cvl.addWidget(g3)
        cvl.addStretch(1)
        tabs.addTab(conv, "Steady-state Convergence Criteria")

        # --- Stop (Prevention of Divergence) — STpre list + Apply ---
        self._STOP_TARGETS = (
            "X-component of velocity", "Y-component of velocity",
            "Z-component of velocity", "Pressure", "Temperature",
            "Turbulent kinetic energy", "Turbulent dissipation rate",
        )
        stop = QWidget()
        sl = QVBoxLayout(stop)
        sl.addWidget(_note(
            "Sets the conditions to stop the calculation for the "
            "prevention of solution divergence.", stop))
        sep_s = QFrame(stop)
        sep_s.setFrameShape(QFrame.HLine)
        sep_s.setFrameShadow(QFrame.Sunken)
        sl.addWidget(sep_s)
        sbody = QHBoxLayout()
        self.stop_table = QTableWidget(0, 2, stop)
        self.stop_table.setHorizontalHeaderLabels(["Target", "Stop value"])
        self.stop_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.stop_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.stop_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stop_table.setSelectionMode(QTableWidget.SingleSelection)
        self.stop_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stop_table.itemSelectionChanged.connect(self._stop_on_sel)
        sbody.addWidget(self.stop_table, 1)
        sright = QVBoxLayout()
        svg = QGroupBox("Stop value", stop)
        svl = QVBoxLayout(svg)
        self.stop_value = QDoubleSpinBox(svg)
        self.stop_value.setDecimals(6)
        self.stop_value.setRange(0.0, 1.0e30)
        self.stop_value.setValue(0.0)
        _pair(svl, "Stop value", self.stop_value)
        self.stop_btn_apply = QPushButton("Apply", svg)
        self.stop_btn_apply.clicked.connect(self._stop_apply_value)
        svl.addWidget(self.stop_btn_apply)
        sright.addWidget(svg)
        sright.addWidget(_note(
            "Note) If the absolute value of a variable exceeds its "
            "specified stop value, the calculation is stopped.", stop))
        sright.addStretch(1)
        sbody.addLayout(sright)
        sl.addLayout(sbody, 1)
        sbrow = QHBoxLayout()
        tip_s = QLabel("Select from list > Set the stop", stop)
        tip_s.setStyleSheet("color: #555;")
        sbrow.addWidget(tip_s)
        sbrow.addStretch(1)
        self.stop_btn_cancel = QPushButton("Cancel", stop)
        self.stop_btn_cancel.clicked.connect(self._stop_cancel_value)
        sbrow.addWidget(self.stop_btn_cancel)
        sl.addLayout(sbrow)
        tabs.addTab(stop, "Stop (Prevention of Divergence)")

        # --- Stop (Specified Point) — point list + limits ---
        self._POINT_VARS = (
            "Temperature", "Pressure",
            "X-component of velocity", "Y-component of velocity",
            "Z-component of velocity",
        )
        sp = QWidget()
        spl = QVBoxLayout(sp)
        spl.addWidget(_note(
            "Sets the conditions to stop the calculation at a "
            "specified point.", sp))
        sep_p = QFrame(sp)
        sep_p.setFrameShape(QFrame.HLine)
        sep_p.setFrameShadow(QFrame.Sunken)
        spl.addWidget(sep_p)
        pbody = QHBoxLayout()
        self.limit_table = QTableWidget(0, 4, sp)
        self.limit_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Location", "Variable"])
        self.limit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.limit_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.limit_table.setSelectionMode(QTableWidget.SingleSelection)
        self.limit_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.limit_table.itemSelectionChanged.connect(self._point_on_sel)
        pbody.addWidget(self.limit_table, 1)
        lim = QGroupBox("Upper and Lower limits", sp)
        ll = QVBoxLayout(lim)
        ll.addWidget(QLabel("for variables", lim))
        self.lim_var = QComboBox(lim)
        self.lim_var.addItems(self._POINT_VARS)
        self.lim_var.currentIndexChanged.connect(self._point_sync_units)
        _pair(ll, "Variable name", self.lim_var)
        row_lo = QHBoxLayout()
        self.lim_lo_on = QCheckBox("Lower limit", lim)
        self.lim_lo = QDoubleSpinBox(lim)
        self.lim_lo.setDecimals(4)
        self.lim_lo.setRange(-1.0e30, 1.0e30)
        self.lim_lo_unit = QLabel("C", lim)
        row_lo.addWidget(self.lim_lo_on)
        row_lo.addWidget(self.lim_lo, 1)
        row_lo.addWidget(self.lim_lo_unit)
        ll.addLayout(row_lo)
        row_hi = QHBoxLayout()
        self.lim_hi_on = QCheckBox("Upper limit", lim)
        self.lim_hi = QDoubleSpinBox(lim)
        self.lim_hi.setDecimals(4)
        self.lim_hi.setRange(-1.0e30, 1.0e30)
        self.lim_hi_unit = QLabel("C", lim)
        row_hi.addWidget(self.lim_hi_on)
        row_hi.addWidget(self.lim_hi, 1)
        row_hi.addWidget(self.lim_hi_unit)
        ll.addLayout(row_hi)
        brow = QHBoxLayout()
        self.point_btn_apply = QPushButton("Apply", lim)
        self.point_btn_modify = QPushButton("Modify", lim)
        self.point_btn_apply.clicked.connect(self._point_apply)
        self.point_btn_modify.clicked.connect(self._point_modify)
        brow.addWidget(self.point_btn_apply)
        brow.addWidget(self.point_btn_modify)
        brow.addStretch(1)
        ll.addLayout(brow)
        ll.addStretch(1)
        pbody.addWidget(lim)
        spl.addLayout(pbody, 1)
        pbrow = QHBoxLayout()
        tip_p = QLabel(
            "Select from list > Sets Upper and Lower limits for variables",
            sp)
        tip_p.setStyleSheet("color: #555;")
        pbrow.addWidget(tip_p)
        pbrow.addStretch(1)
        self.point_btn_cancel = QPushButton("Cancel", sp)
        self.point_btn_select = QPushButton("Select", sp)
        self.point_btn_cancel.clicked.connect(self._point_cancel)
        self.point_btn_select.clicked.connect(self._point_select_hint)
        pbrow.addWidget(self.point_btn_cancel)
        pbrow.addWidget(self.point_btn_select)
        spl.addLayout(pbrow)
        # name -> {var, lo, lo_on, hi, hi_on}
        self._point_limits: dict[str, dict] = {}
        tabs.addTab(sp, "Stop (Specified Point)")

        lay.addWidget(tabs, 1)
        self._load()
        # Default projects are steady — hide Time step until transient.
        self.ts_box.setVisible(self._is_transient())
        self._stop_fill_table()
        self._point_fill_table()

    def _is_transient(self) -> bool:
        return (self.model.analysis_set_value("calculation", "steady")
                == "transient")

    def set_detail_mode(self, detailed: bool) -> None:
        """Simple: Cycle (+ Criteria for steady). Detailed: all Stop tabs."""
        transient = self._is_transient()
        if hasattr(self, "ts_box"):
            self.ts_box.setVisible(transient)
        # 0 Cycle — always
        _set_tab_visible(self.tabs, 1, detailed or not transient)
        _set_tab_visible(self.tabs, 2, detailed)
        _set_tab_visible(self.tabs, 3, detailed)
        if detailed:
            self._stop_fill_table()
            self._point_fill_table()
        if self.tabs.currentIndex() >= 0 and not self.tabs.isTabEnabled(
                self.tabs.currentIndex()):
            self.tabs.setCurrentIndex(0)
        if hasattr(self.tabs, "isTabVisible"):
            if not self.tabs.isTabVisible(self.tabs.currentIndex()):
                self.tabs.setCurrentIndex(0)

    # -- Stop (Prevention of Divergence) ---------------------------------

    def _stop_values(self) -> list[str]:
        """Per-target stop values; empty string = unset (blank in table)."""
        raw = self.model.analysis_set_value("snan", "")
        parts = [p.strip() for p in raw.split(",")] if raw else []
        n = len(self._STOP_TARGETS)
        while len(parts) < n:
            parts.append("")
        return parts[:n]

    def _stop_fill_table(self) -> None:
        if not hasattr(self, "stop_table"):
            return
        vals = self._stop_values()
        self.stop_table.blockSignals(True)
        self.stop_table.setRowCount(0)
        for i, name in enumerate(self._STOP_TARGETS):
            self.stop_table.insertRow(i)
            self.stop_table.setItem(i, 0, QTableWidgetItem(name))
            text = vals[i]
            # Treat bare 0 as unset to match STpre's initially blank column.
            if text in ("", "0", "0.0"):
                text = ""
            self.stop_table.setItem(i, 1, QTableWidgetItem(text))
        self.stop_table.blockSignals(False)
        if self.stop_table.rowCount():
            self.stop_table.selectRow(0)

    def _stop_selected_row(self) -> int:
        rows = self.stop_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _stop_on_sel(self) -> None:
        r = self._stop_selected_row()
        if r < 0:
            return
        it = self.stop_table.item(r, 1)
        text = it.text().strip() if it else ""
        try:
            self.stop_value.setValue(float(text) if text else 0.0)
        except ValueError:
            self.stop_value.setValue(0.0)

    def _stop_apply_value(self) -> None:
        r = self._stop_selected_row()
        if r < 0:
            QMessageBox.information(
                self, "Stop value", "Select a target from the list.")
            return
        vals = self._stop_values()
        vals[r] = f"{self.stop_value.value():g}"
        self.model.set_analysis_set_value("snan", ",".join(vals))
        self.stop_table.setItem(r, 1, QTableWidgetItem(vals[r]))

    def _stop_cancel_value(self) -> None:
        r = self._stop_selected_row()
        if r < 0:
            return
        vals = self._stop_values()
        vals[r] = ""
        self.model.set_analysis_set_value("snan", ",".join(vals))
        self.stop_table.setItem(r, 1, QTableWidgetItem(""))
        self.stop_value.setValue(0.0)

    # -- Stop (Specified Point) ------------------------------------------

    def _point_parts(self) -> list[tuple[str, str]]:
        """``(name, location)`` for point parts (STpre: create points first)."""
        out: list[tuple[str, str]] = []
        for p in self.model.parts():
            kind = (p.kind or "").lower()
            attr = (p.attribute or "").lower()
            name = p.name or ""
            if not (kind == "point" or "point" in attr
                    or name.lower().startswith("point")):
                continue
            loc = p.base.strip() if p.base else ""
            if loc and not loc.startswith("("):
                loc = f"({loc})"
            out.append((name, loc))
        return out

    def _point_load_limits(self) -> None:
        self._point_limits = {}
        raw = self.model.analysis_set_value("stop_var", "")
        if not raw:
            return
        for rec in raw.split(";"):
            rec = rec.strip()
            if not rec:
                continue
            bits = rec.split("|")
            if len(bits) < 6:
                continue
            name, var, lo, lo_on, hi, hi_on = bits[:6]
            self._point_limits[name] = {
                "var": var,
                "lo": lo,
                "lo_on": lo_on in ("1", "T", "true", "True"),
                "hi": hi,
                "hi_on": hi_on in ("1", "T", "true", "True"),
            }

    def _point_save_limits(self) -> None:
        parts = []
        for name, d in self._point_limits.items():
            parts.append("|".join((
                name, d.get("var", "Temperature"),
                str(d.get("lo", "0")),
                "1" if d.get("lo_on") else "0",
                str(d.get("hi", "0")),
                "1" if d.get("hi_on") else "0",
            )))
        self.model.set_analysis_set_value("stop_var", ";".join(parts))

    def _point_fill_table(self) -> None:
        if not hasattr(self, "limit_table"):
            return
        self._point_load_limits()
        sel = self._point_selected_name()
        self.limit_table.blockSignals(True)
        self.limit_table.setRowCount(0)
        keep = -1
        for i, (name, loc) in enumerate(self._point_parts()):
            d = self._point_limits.get(name, {})
            self.limit_table.insertRow(i)
            self.limit_table.setItem(i, 0, QTableWidgetItem(name))
            self.limit_table.setItem(i, 1, QTableWidgetItem(""))
            self.limit_table.setItem(i, 2, QTableWidgetItem(loc))
            self.limit_table.setItem(
                i, 3, QTableWidgetItem(d.get("var", "")))
            if name == sel:
                keep = i
        self.limit_table.blockSignals(False)
        if self.limit_table.rowCount():
            self.limit_table.selectRow(keep if keep >= 0 else 0)
            self._point_on_sel()

    def _point_selected_name(self) -> str:
        rows = self.limit_table.selectionModel().selectedRows() \
            if hasattr(self, "limit_table") and self.limit_table.selectionModel() \
            else []
        if not rows:
            return ""
        it = self.limit_table.item(rows[0].row(), 0)
        return it.text().strip() if it else ""

    def _point_unit_for(self, var: str) -> str:
        if var == "Temperature":
            return "C"
        if var == "Pressure":
            return "Pa"
        return "m/s"

    def _point_sync_units(self) -> None:
        u = self._point_unit_for(self.lim_var.currentText())
        self.lim_lo_unit.setText(u)
        self.lim_hi_unit.setText(u)

    def _point_on_sel(self) -> None:
        name = self._point_selected_name()
        d = self._point_limits.get(name, {})
        var = d.get("var", "Temperature")
        idx = self.lim_var.findText(var)
        self.lim_var.blockSignals(True)
        self.lim_var.setCurrentIndex(idx if idx >= 0 else 0)
        self.lim_var.blockSignals(False)
        self._point_sync_units()
        try:
            self.lim_lo.setValue(float(d.get("lo", "0") or 0))
        except ValueError:
            self.lim_lo.setValue(0.0)
        try:
            self.lim_hi.setValue(float(d.get("hi", "0") or 0))
        except ValueError:
            self.lim_hi.setValue(0.0)
        self.lim_lo_on.setChecked(bool(d.get("lo_on", False)))
        self.lim_hi_on.setChecked(bool(d.get("hi_on", False)))

    def _point_capture(self) -> Optional[dict]:
        name = self._point_selected_name()
        if not name:
            QMessageBox.information(
                self, "Stop (Specified Point)",
                "Select a point region from the list.\n"
                "(Note) Create a point part in advance.")
            return None
        if not self.lim_lo_on.isChecked() and not self.lim_hi_on.isChecked():
            QMessageBox.warning(
                self, "Stop (Specified Point)",
                "Turn on Lower limit and/or Upper limit.")
            return None
        return {
            "var": self.lim_var.currentText(),
            "lo": f"{self.lim_lo.value():g}",
            "lo_on": self.lim_lo_on.isChecked(),
            "hi": f"{self.lim_hi.value():g}",
            "hi_on": self.lim_hi_on.isChecked(),
        }

    def _point_apply(self) -> None:
        name = self._point_selected_name()
        data = self._point_capture()
        if data is None:
            return
        if name in self._point_limits:
            QMessageBox.information(
                self, "Apply",
                "Limits already set for this point. Use Modify to change.")
            return
        self._point_limits[name] = data
        self._point_save_limits()
        self._point_fill_table()

    def _point_modify(self) -> None:
        name = self._point_selected_name()
        data = self._point_capture()
        if data is None:
            return
        self._point_limits[name] = data
        self._point_save_limits()
        self._point_fill_table()

    def _point_cancel(self) -> None:
        name = self._point_selected_name()
        if not name or name not in self._point_limits:
            return
        del self._point_limits[name]
        self._point_save_limits()
        self._point_fill_table()

    def _point_select_hint(self) -> None:
        QMessageBox.information(
            self, "Select",
            "Select a point part in the Draw window "
            "(phase-1: use the list).")

    def _load(self) -> None:
        cycle = self.model.analysis_set_value("cycle", "1,100").split(",")
        try:
            self.start_cycle.setValue(float(cycle[0]))
            self.last_cycle.setValue(float(cycle[1]))
        except (ValueError, IndexError):
            pass
        try:
            self.steady_start.setValue(float(
                self.model.analysis_set_value("steady_check_cycle", "50")))
            self.hbal_eps.setValue(float(
                self.model.analysis_set_value("steady_hbal_eps", "0")))
            self.init_dt.setValue(float(
                self.model.analysis_set_value("init_time_step", "0.01")))
            self.courant.setValue(float(
                self.model.analysis_set_value("courant", "0.9")))
        except ValueError:
            pass
        self._point_load_limits()

    def apply(self) -> None:
        transient = self._is_transient()
        self.model.set_cycles(
            int(self.start_cycle.value()), int(self.last_cycle.value()),
            transient=transient)
        if transient:
            self.model.set_analysis_set_value(
                "init_time_step", f"{self.init_dt.value():g}")
            self.model.set_analysis_set_value(
                "courant", f"{self.courant.value():g}")
        self.model.set_analysis_set_value(
            "steady_check_cycle", f"{int(self.steady_start.value())}")
        self.model.set_analysis_set_value(
            "steady_hbal_eps", f"{self.hbal_eps.value():g}")
        self.model.set_analysis_set_value(
            "steady_hbal_cycle",
            "1" if self.hbal.isChecked() else "0")
        # Stop tabs write through Apply already; flush current tables.
        vals = []
        for r in range(self.stop_table.rowCount()):
            it = self.stop_table.item(r, 1)
            vals.append(it.text().strip() if it else "")
        self.model.set_analysis_set_value("snan", ",".join(vals))
        self._point_save_limits()


class _CwSolverPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Solver Parameters."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        self.tabs = tabs

        # Heat balance
        hb = QWidget()
        hl = QVBoxLayout(hb)
        hl.addWidget(_note(
            "Corrects temperature for accuracy and stabilization by "
            "solving heat balance equation.", hb))
        g = QGroupBox("Heat balance", hb)
        gl = QVBoxLayout(g)
        self.hbal_on = QCheckBox("Consider heat balance", g)
        self.hbal_on.setChecked(True)
        gl.addWidget(self.hbal_on)
        self.hbal_interval = QDoubleSpinBox(g)
        self.hbal_interval.setDecimals(0)
        self.hbal_interval.setRange(1, 1e6)
        self.hbal_interval.setValue(1)
        _pair(gl, "Interval of calculation", self.hbal_interval, "cycle")
        ex = QGroupBox("Execution type", g)
        el = QVBoxLayout(ex)
        self.exec1 = QRadioButton(
            "Assume uniform thermal conductivity "
            "(entire computational domain as target)", ex)
        self.exec2 = QRadioButton(
            "Assume uniform thermal conductivity "
            "(each fluid region as target)", ex)
        self.exec3 = QRadioButton(
            "Assume difference in thermal conductivity for different "
            "parts (entire computational domain as target)", ex)
        self.exec4 = QRadioButton(
            "Assume difference in thermal conductivity for different "
            "parts (each fluid region as target)", ex)
        self.exec3.setChecked(True)
        for r in (self.exec1, self.exec2, self.exec3, self.exec4):
            el.addWidget(r)
        self.scale_k = QDoubleSpinBox(ex)
        self.scale_k.setRange(0.01, 1e6)
        self.scale_k.setValue(2)
        self.scale_k.setEnabled(False)
        _pair(el, "Scaling factor of thermal conductivity",
              self.scale_k, "times")
        gl.addWidget(ex)
        st = QGroupBox("Stabilization", g)
        sl = QVBoxLayout(st)
        self.pseudo = QCheckBox(
            "Consider the Pseudo time step relaxation for the heat "
            "balance equation", st)
        self.pseudo.setChecked(True)
        self.under = QCheckBox(
            "Consider the under-relaxation for the advection and "
            "diffusion term of the heat balance equation", st)
        self.under.setChecked(True)
        sl.addWidget(self.pseudo)
        sl.addWidget(self.under)
        gl.addWidget(st)
        self.out_matrix = QCheckBox(
            "Output matrix information of the heat balance equation "
            "to the L file", g)
        gl.addWidget(self.out_matrix)
        hl.addWidget(g)
        hl.addStretch(1)
        tabs.addTab(hb, "Heat Balance Correction")

        # Matrix / advection (STpre: list + Matrix solver + Advection term)
        mx = QWidget()
        ml = QVBoxLayout(mx)
        ml.addWidget(_note(
            "Specifies the matrix solver and the differencing scheme "
            "for the advection term.", mx))
        self.solver_table = QTableWidget(7, 4, mx)
        self.solver_table.setHorizontalHeaderLabels(
            ["Target", "Solver type", "Parameter", "Advection term"])
        self.solver_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.solver_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.solver_table.setSelectionMode(QTableWidget.SingleSelection)
        self.solver_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._SOLVER_DEFAULT_PARAM = (
            "(Maximum number of iterations for each cycle= 100 "
            "Relative error= 1e-06)")
        for i, name in enumerate((
                "X-component of velocity", "Y-component of velocity",
                "Z-component of velocity", "Pressure", "Temperature",
                "Turbulent kinetic energy", "Turbulent dissipation rate")):
            self.solver_table.setItem(i, 0, QTableWidgetItem(name))
            self.solver_table.setItem(
                i, 1, QTableWidgetItem("Default"))
            self.solver_table.setItem(
                i, 2, QTableWidgetItem(self._SOLVER_DEFAULT_PARAM))
            adv0 = "---" if name == "Pressure" else "1st order upwind"
            self.solver_table.setItem(i, 3, QTableWidgetItem(adv0))
        self.solver_table.itemSelectionChanged.connect(
            self._solver_on_sel)
        ml.addWidget(self.solver_table, 1)
        tip_mx = QLabel(
            "Select a variable > Specify the matrix solver type and "
            "the differencing scheme for the advection term.", mx)
        tip_mx.setStyleSheet("color: #555;")
        tip_mx.setWordWrap(True)
        ml.addWidget(tip_mx)

        edit_row = QHBoxLayout()
        msg = QGroupBox("Matrix solver", mx)
        mgl = QVBoxLayout(msg)
        self.solver_type = QComboBox(msg)
        self.solver_type.addItems([
            "Default", "Default solver type",
            "JACOBI", "MICCG", "ILUCR", "ILUCGS", "FMGCG", "FMGCGS",
            "ICCG", "BiCGSTAB",
        ])
        _pair(mgl, "Solver type", self.solver_type)
        self.solver_max_iter = QDoubleSpinBox(msg)
        self.solver_max_iter.setDecimals(0)
        self.solver_max_iter.setRange(1, 1.0e9)
        self.solver_max_iter.setValue(100)
        _pair(mgl, "Maximum number of iterations for each cycle",
              self.solver_max_iter)
        self.solver_rel_err = QDoubleSpinBox(msg)
        self.solver_rel_err.setDecimals(10)
        self.solver_rel_err.setRange(1.0e-30, 1.0)
        self.solver_rel_err.setValue(1.0e-6)
        _pair(mgl, "Relative error", self.solver_rel_err)
        edit_row.addWidget(msg, 1)

        adv = QGroupBox("Advection term", mx)
        al = QVBoxLayout(adv)
        self.adv1 = QRadioButton("1st order upwind", adv)
        self.adv2 = QRadioButton("QUICK (Incompressible)", adv)
        self.adv3 = QRadioButton("WENO", adv)
        self.adv1.setChecked(True)
        for r in (self.adv1, self.adv2, self.adv3):
            al.addWidget(r)
        al.addStretch(1)
        edit_row.addWidget(adv, 1)
        ml.addLayout(edit_row)

        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        self.solver_btn_apply = QPushButton("Apply", mx)
        self.solver_btn_apply.clicked.connect(self._solver_apply)
        apply_row.addWidget(self.solver_btn_apply)
        ml.addLayout(apply_row)
        tabs.addTab(mx, "Matrix Solver/Advection Term")
        if self.solver_table.rowCount():
            self.solver_table.selectRow(0)

        # Characteristic / Equation loops (compact)
        for title, key in (
                ("Characteristic Loop", "char"),
                ("Equation Loop", "eqn")):
            pg = QWidget()
            pl = QVBoxLayout(pg)
            pl.addWidget(_note(
                "Controls convergence criterion of characteristic loop "
                "for each function." if key == "char"
                else "Sets a loop for each equation.", pg))
            tbl = QTableWidget(1, 2, pg)
            tbl.setHorizontalHeaderLabels(["Target", "Parameter"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tbl.setItem(0, 0, QTableWidgetItem(
                "Temperature dependence of specific heat"
                if key == "char" else "Temperature"))
            tbl.setItem(0, 1, QTableWidgetItem("Default"))
            pl.addWidget(tbl)
            box = QGroupBox("Characteristic loop", pg)
            bl = QVBoxLayout(box)
            chk = QCheckBox("Set convergence tolerance", box)
            bl.addWidget(chk)
            it = QDoubleSpinBox(box); it.setDecimals(0)
            ref = QDoubleSpinBox(box)
            _pair(bl, "The maximum number of iterations", it)
            _pair(bl, "Reference value of convergence tolerance", ref)
            it.setEnabled(False); ref.setEnabled(False)
            chk.toggled.connect(it.setEnabled)
            chk.toggled.connect(ref.setEnabled)
            pl.addWidget(box)
            pl.addStretch(1)
            tabs.addTab(pg, title)
            if key == "char":
                self.char_tol = chk
            else:
                self.eqn_tol = chk

        # I1a: Solver Control — header flags (PCTY/TBEC/JFNK/WALL_MODEL/
        # CYLD/LESM/UPWD) + STMC/PBAS_MATERIAL row tables.  Storage tags
        # match the H1b/H1h emitters byte-verified against the corpus.
        sc = QWidget()
        sl2 = QVBoxLayout(sc)
        flags = QGroupBox("Solver control flags", sc)
        ff = QFormLayout(flags)
        self.pcty = QSpinBox(flags)
        self.pcty.setRange(0, 9)
        self.tbec = QSpinBox(flags)
        self.tbec.setRange(0, 1)
        self.jfnk_flag = QSpinBox(flags)
        self.jfnk_flag.setRange(0, 99)
        self.wall_model = QSpinBox(flags)
        self.wall_model.setRange(0, 15)
        ff.addRow("PCTY (pressure type)", self.pcty)
        ff.addRow("TBEC", self.tbec)
        ff.addRow("JFNK (int flag)", self.jfnk_flag)
        ff.addRow("Wall model", self.wall_model)
        cyl = QHBoxLayout()
        self.cyl_a = QSpinBox(flags)
        self.cyl_a.setRange(0, 1)
        self.cyl_b = QSpinBox(flags)
        self.cyl_b.setRange(0, 1)
        cyl.addWidget(QLabel("flag", flags))
        cyl.addWidget(self.cyl_a)
        cyl.addWidget(QLabel("coord", flags))
        cyl.addWidget(self.cyl_b)
        cyl.addStretch(1)
        ff.addRow("CYLD (cylindrical)", cyl)
        lesm = QHBoxLayout()
        self.lesm_m = QSpinBox(flags)
        self.lesm_m.setRange(0, 9)
        self.lesm_s1 = QSpinBox(flags)
        self.lesm_s1.setRange(0, 99)
        self.lesm_s2 = QSpinBox(flags)
        self.lesm_s2.setRange(0, 99)
        for lab, w in (("model", self.lesm_m), ("sub1", self.lesm_s1),
                       ("sub2", self.lesm_s2)):
            lesm.addWidget(QLabel(lab, flags))
            lesm.addWidget(w)
        lesm.addStretch(1)
        ff.addRow("LESM (LES model)", lesm)
        self.upwd_mask = QLineEdit(flags)
        self.upwd_mask.setMaxLength(8)
        self.upwd_mask.setPlaceholderText("11000000")
        ff.addRow("UPWD mask (8 digits)", self.upwd_mask)
        sl2.addWidget(flags)

        stmc = QGroupBox("STMC (steady multi-control)", sc)
        stl = QVBoxLayout(stmc)
        strow = QHBoxLayout()
        strow.addWidget(QLabel("Flag", stmc))
        self.stmc_flag = QSpinBox(stmc)
        self.stmc_flag.setRange(0, 9)
        strow.addWidget(self.stmc_flag)
        strow.addStretch(1)
        self.stmc_add = QPushButton("Add", stmc)
        self.stmc_del = QPushButton("Delete", stmc)
        self.stmc_add.clicked.connect(self._stmc_add_row)
        self.stmc_del.clicked.connect(self._stmc_del_row)
        strow.addWidget(self.stmc_add)
        strow.addWidget(self.stmc_del)
        stl.addLayout(strow)
        self.stmc_table = QTableWidget(0, 2, stmc)
        self.stmc_table.setHorizontalHeaderLabels(["No", "Values (csv)"])
        self.stmc_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        stl.addWidget(self.stmc_table)
        sl2.addWidget(stmc)

        pbas = QGroupBox("PBAS_MATERIAL (compressible base pressure)",
                         sc)
        pbl = QVBoxLayout(pbas)
        prow = QHBoxLayout()
        prow.addStretch(1)
        self.pbas_add = QPushButton("Add", pbas)
        self.pbas_del = QPushButton("Delete", pbas)
        self.pbas_add.clicked.connect(self._pbas_add_row)
        self.pbas_del.clicked.connect(self._pbas_del_row)
        prow.addWidget(self.pbas_add)
        prow.addWidget(self.pbas_del)
        pbl.addLayout(prow)
        self.pbas_table = QTableWidget(0, 3, pbas)
        self.pbas_table.setHorizontalHeaderLabels(
            ["Material no", "Pressure (Pa)", "Temperature (C)"])
        self.pbas_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        pbl.addWidget(self.pbas_table)
        sl2.addWidget(pbas)
        sl2.addStretch(1)
        tabs.addTab(sc, "Solver Control")
        self._solver_control_load()

        lay.addWidget(tabs, 1)

    def _solver_param_text(self) -> str:
        return (
            f"(Maximum number of iterations for each cycle= "
            f"{int(self.solver_max_iter.value())} "
            f"Relative error= {self.solver_rel_err.value():g})")

    def _solver_selected_row(self) -> int:
        rows = self.solver_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _solver_on_sel(self) -> None:
        r = self._solver_selected_row()
        if r < 0:
            return
        st = self.solver_table.item(r, 1)
        if st is not None:
            idx = self.solver_type.findText(st.text().split("(")[0].strip())
            if idx < 0:
                idx = self.solver_type.findText(st.text())
            if idx >= 0:
                self.solver_type.setCurrentIndex(idx)
        param = self.solver_table.item(r, 2)
        text = param.text() if param else ""
        # Parse "…cycle= N Relative error= E"
        m_it = re.search(r"cycle=\s*([0-9.eE+-]+)", text)
        m_er = re.search(r"Relative error=\s*([0-9.eE+-]+)", text)
        if m_it:
            try:
                self.solver_max_iter.setValue(float(m_it.group(1)))
            except ValueError:
                pass
        if m_er:
            try:
                self.solver_rel_err.setValue(float(m_er.group(1)))
            except ValueError:
                pass
        adv = self.solver_table.item(r, 3)
        adv_t = adv.text() if adv else ""
        target = self.solver_table.item(r, 0)
        is_pressure = target is not None and target.text() == "Pressure"
        for w in (self.adv1, self.adv2, self.adv3):
            w.setEnabled(not is_pressure)
        if "QUICK" in adv_t:
            self.adv2.setChecked(True)
        elif "WENO" in adv_t:
            self.adv3.setChecked(True)
        else:
            self.adv1.setChecked(True)

    def _solver_apply(self) -> None:
        r = self._solver_selected_row()
        if r < 0:
            QMessageBox.information(
                self, "Matrix solver", "Select a target from the list.")
            return
        stype = self.solver_type.currentText()
        self.solver_table.setItem(r, 1, QTableWidgetItem(stype))
        self.solver_table.setItem(
            r, 2, QTableWidgetItem(self._solver_param_text()))
        target = self.solver_table.item(r, 0)
        if target is not None and target.text() == "Pressure":
            adv = "---"
        elif self.adv2.isChecked():
            adv = "QUICK (Incompressible)"
        elif self.adv3.isChecked():
            adv = "WENO"
        else:
            adv = "1st order upwind"
        self.solver_table.setItem(r, 3, QTableWidgetItem(adv))

    def set_detail_mode(self, detailed: bool) -> None:
        """Simple setting exposes only Heat Balance Correction."""
        for i in range(1, self.tabs.count()):
            _set_tab_visible(self.tabs, i, detailed)
        if self.tabs.currentIndex() != 0 and not detailed:
            self.tabs.setCurrentIndex(0)

    # -- I1a: Solver Control tab ------------------------------------------

    def _stmc_add_row(self) -> None:
        r = self.stmc_table.rowCount()
        self.stmc_table.insertRow(r)
        self.stmc_table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
        self.stmc_table.setItem(r, 1, QTableWidgetItem("0.99,0.5,0.0001"))

    def _stmc_del_row(self) -> None:
        rows = self.stmc_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.stmc_table.removeRow(idx)

    def _pbas_add_row(self) -> None:
        r = self.pbas_table.rowCount()
        self.pbas_table.insertRow(r)
        self.pbas_table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
        self.pbas_table.setItem(r, 1, QTableWidgetItem("101325"))
        self.pbas_table.setItem(r, 2, QTableWidgetItem("0"))

    def _pbas_del_row(self) -> None:
        rows = self.pbas_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.pbas_table.removeRow(idx)

    @staticmethod
    def _spin_val(sb, default: str = "") -> str:
        text = default
        try:
            text = f"{int(sb.value()):d}"
        except (TypeError, ValueError, AttributeError):
            pass
        return text

    def _solver_control_load(self) -> None:
        aset = self.model
        self.pcty.setValue(int(float(
            aset.analysis_set_value("pcty", "0") or 0)))
        self.tbec.setValue(int(float(
            aset.analysis_set_value("tbec", "0") or 0)))
        self.jfnk_flag.setValue(int(float(
            aset.analysis_set_value("jfnk", "0") or 0)))
        self.wall_model.setValue(int(float(
            aset.analysis_set_value("wall_model", "0") or 0)))
        cyl = aset.analysis_set_value("cyl_coord", "0,0").split(",")
        try:
            self.cyl_a.setValue(int(float(cyl[0])))
            self.cyl_b.setValue(int(float(cyl[1]) if len(cyl) > 1 else 0))
        except (ValueError, IndexError):
            pass
        lesm = aset.analysis_set_value("lesm", "0,0,0").split(",")
        try:
            self.lesm_m.setValue(int(float(lesm[0])))
            for sb, i in ((self.lesm_s1, 1), (self.lesm_s2, 2)):
                sb.setValue(int(float(lesm[i])) if len(lesm) > i else 0)
        except (ValueError, IndexError):
            pass
        self.upwd_mask.setText(
            aset.analysis_set_value("upwd_mask", ""))
        # STMC rows
        import xml.etree.ElementTree as ET
        st = self.model.root.find("analysis_etc/stmc")
        self.stmc_table.setRowCount(0)
        if st is not None:
            try:
                self.stmc_flag.setValue(int(float(st.attrib.get("flag",
                                                                "1"))))
            except ValueError:
                pass
            for r in st.findall("row"):
                row = self.stmc_table.rowCount()
                self.stmc_table.insertRow(row)
                self.stmc_table.setItem(
                    row, 0, QTableWidgetItem(r.attrib.get("no", "1")))
                self.stmc_table.setItem(
                    row, 1, QTableWidgetItem(r.attrib.get("vals", "")))
        # PBAS rows
        pb = self.model.root.find("analysis_etc/pbas_material")
        self.pbas_table.setRowCount(0)
        if pb is not None:
            for r in pb.findall("row"):
                row = self.pbas_table.rowCount()
                self.pbas_table.insertRow(row)
                self.pbas_table.setItem(
                    row, 0, QTableWidgetItem(r.attrib.get("no", "1")))
                self.pbas_table.setItem(
                    row, 1, QTableWidgetItem(r.attrib.get("p", "101325")))
                self.pbas_table.setItem(
                    row, 2, QTableWidgetItem(r.attrib.get("t", "0")))

    def _solver_control_apply(self) -> None:
        aset = self.model
        aset.set_analysis_set_value("pcty", self._spin_val(self.pcty, "0"))
        aset.set_analysis_set_value("tbec", self._spin_val(self.tbec, "0"))
        aset.set_analysis_set_value("jfnk",
                                    self._spin_val(self.jfnk_flag, "0"))
        aset.set_analysis_set_value("wall_model",
                                    self._spin_val(self.wall_model, "0"))
        aset.set_analysis_set_value(
            "cyl_coord",
            f"{self.cyl_a.value()},{self.cyl_b.value()}")
        aset.set_analysis_set_value(
            "lesm",
            f"{self.lesm_m.value()},{self.lesm_s1.value()},"
            f"{self.lesm_s2.value()}")
        mask = self.upwd_mask.text().strip()
        if mask:
            aset.set_analysis_set_value("upwd_mask", mask)
        else:
            # clear by writing an empty value is lossy — drop the tag
            el = aset.root.find("analysis_set")
            if el is not None:
                from cabxml import _first
                c = _first(el, "upwd_mask")
                if c is not None:
                    el.remove(c)
        # STMC
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("stmc")
        if old is not None:
            aet.remove(old)
        if self.stmc_table.rowCount():
            st = ET.SubElement(aet, "stmc")
            st.attrib["flag"] = str(self.stmc_flag.value())
            for r in range(self.stmc_table.rowCount()):
                no_it = self.stmc_table.item(r, 0)
                vals_it = self.stmc_table.item(r, 1)
                row = ET.SubElement(st, "row")
                row.attrib["no"] = (no_it.text() if no_it else str(r + 1))
                row.attrib["vals"] = (vals_it.text() if vals_it else "")
        # PBAS
        old = aet.find("pbas_material")
        if old is not None:
            aet.remove(old)
        if self.pbas_table.rowCount():
            pb = ET.SubElement(aet, "pbas_material")
            for r in range(self.pbas_table.rowCount()):
                it = [self.pbas_table.item(r, c) for c in range(3)]
                row = ET.SubElement(pb, "row")
                row.attrib["no"] = it[0].text() if it[0] else str(r + 1)
                row.attrib["p"] = it[1].text() if it[1] else "101325"
                row.attrib["t"] = it[2].text() if it[2] else "0"

    def apply(self) -> None:
        # heat_balance in analysis_set is typically "F,F"
        flag = "T" if self.hbal_on.isChecked() else "F"
        self.model.set_analysis_set_value("heat_balance", f"{flag},{flag}")
        # I1a: Solver Control flags + STMC/PBAS row tables
        self._solver_control_apply()
        # Persist matrix-solver rows (type|iters|relerr|adv per target).
        rows = []
        for r in range(self.solver_table.rowCount()):
            cells = []
            for c in range(4):
                it = self.solver_table.item(r, c)
                cells.append(it.text() if it else "")
            rows.append("|".join(cells))
        self.model.set_analysis_set_value("solv", ";".join(rows))


class _CwStabilizationPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Stabilization (Fixed Pressure / UNDR·DTSR)."""

    _UR_TARGETS = (
        "Flow", "Pressure", "Temperature", "Temperature (Solid)",
        "Turbulence", "Humidity",
    )
    _UR_TYPES = (
        "Default(solver-defined)",
        "High-Speed(Forced convection)",
        "High-Speed(Natural convection)",
        "JFNK(Forced convection)",
        "JFNK(Natural convection)",
        "Low-Mach-number approximation",
        "Constant",
        "Constant (controlled)",
        "Use the following equation",
    )
    _DTS_TYPES = _UR_TYPES + ("Same as temperature",)

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        self._fixp: dict[str, str] = {}  # point name -> pressure text
        self._ur_rows: dict[str, dict] = {}

        # ---------- Fixed Pressure ----------
        fp = QWidget()
        fl = QVBoxLayout(fp)
        fl.addWidget(_note(
            "Stabilizes the flow field computation by fixing the "
            "pressure at specified location(s).", fp))
        sep = QFrame(fp)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        fl.addWidget(sep)

        spec = QGroupBox("Specific region", fp)
        sgl = QVBoxLayout(spec)
        sbody = QHBoxLayout()
        self.p_table = QTableWidget(0, 4, spec)
        self.p_table.setHorizontalHeaderLabels(
            ["Point name", "*", "Location", "Pressure"])
        self.p_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.p_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.p_table.setSelectionMode(QTableWidget.SingleSelection)
        self.p_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.p_table.itemSelectionChanged.connect(self._fixp_on_sel)
        sbody.addWidget(self.p_table, 1)
        pright = QVBoxLayout()
        pbox = QGroupBox("Pressure", spec)
        pbl = QVBoxLayout(pbox)
        self.fixp_value = QDoubleSpinBox(pbox)
        self.fixp_value.setDecimals(4)
        self.fixp_value.setRange(-1.0e30, 1.0e30)
        self.fixp_unit = QComboBox(pbox)
        self.fixp_unit.addItems(["Pa", "atm", "mmHg"])
        prow = QHBoxLayout()
        prow.addWidget(self.fixp_value, 1)
        prow.addWidget(self.fixp_unit)
        pbl.addLayout(prow)
        self.fixp_btn_apply = QPushButton("Apply", pbox)
        self.fixp_btn_apply.clicked.connect(self._fixp_apply)
        pbl.addWidget(self.fixp_btn_apply)
        pright.addWidget(pbox)
        pright.addWidget(_note(
            "Note) Only one pressure-fixed point is applied per fluid "
            "region. If more than one pressure-fixed points are "
            "specified within one fluid region, only the last point "
            "is applied.", spec))
        pright.addStretch(1)
        sbody.addLayout(pright)
        sgl.addLayout(sbody, 1)
        tip_row = QHBoxLayout()
        tip = QLabel("Select from list > Specify the pressure value", spec)
        tip.setStyleSheet("color: #555;")
        tip_row.addWidget(tip)
        tip_row.addStretch(1)
        self.fixp_btn_cancel = QPushButton("Cancel", spec)
        self.fixp_btn_select = QPushButton("Select", spec)
        self.fixp_btn_cancel.clicked.connect(self._fixp_cancel)
        self.fixp_btn_select.clicked.connect(self._fixp_select_hint)
        tip_row.addWidget(self.fixp_btn_cancel)
        tip_row.addWidget(self.fixp_btn_select)
        sgl.addLayout(tip_row)
        fl.addWidget(spec, 1)

        auto = QGroupBox("Automatic fixation of pressure", fp)
        al = QVBoxLayout(auto)
        self.auto_p = QCheckBox(
            "Automatically fix pressure in a pressure indefinite region",
            auto)
        self.auto_p.setChecked(True)
        al.addWidget(self.auto_p)
        self.p_mode1 = QRadioButton(
            "Solve a pressure correction equation in which fixed "
            "pressure is incorporated", auto)
        self.p_mode2 = QRadioButton(
            "Compute fixed pressure after a pressure correction "
            "equation is solved", auto)
        self.p_mode1.setChecked(True)
        al.addWidget(self.p_mode1)
        al.addWidget(self.p_mode2)
        self.auto_p.toggled.connect(self.p_mode1.setEnabled)
        self.auto_p.toggled.connect(self.p_mode2.setEnabled)
        fl.addWidget(auto)
        tabs.addTab(fp, "Fixed Pressure")

        # ---------- Under-relaxation / Pseudo time step ----------
        ur = QWidget()
        ul = QVBoxLayout(ur)
        ul.addWidget(_note(
            "Controls stabilization of computation by setting "
            "coefficients of under-relaxation and/or pseudo time "
            "step relaxation.", ur))
        drow = QHBoxLayout()
        drow.addStretch(1)
        self.ur_details = QCheckBox("Details", ur)
        self.ur_details.setChecked(True)
        drow.addWidget(self.ur_details)
        ul.addLayout(drow)

        self.ur_table = QTableWidget(0, 3, ur)
        self.ur_table.setHorizontalHeaderLabels([
            "Target", "Under-relaxation coefficient",
            "Pseudo time step relaxation coefficient"])
        self.ur_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ur_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ur_table.setSelectionMode(QTableWidget.SingleSelection)
        self.ur_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ur_table.itemSelectionChanged.connect(self._ur_on_sel)
        ul.addWidget(self.ur_table, 1)

        edit = QHBoxLayout()
        # Under-relaxation
        ug = QGroupBox("Stabilization (Under-relaxation)", ur)
        ugl = QVBoxLayout(ug)
        self.ur_type = QComboBox(ug)
        self.ur_type.addItems(self._UR_TYPES)
        _pair(ugl, "Type", self.ur_type)
        self.ur_const = QDoubleSpinBox(ug)
        self.ur_init = QDoubleSpinBox(ug)
        self.ur_final = QDoubleSpinBox(ug)
        self.ur_ref = QDoubleSpinBox(ug)
        for sp in (self.ur_const, self.ur_init, self.ur_final, self.ur_ref):
            sp.setDecimals(6)
            sp.setRange(0.0, 1.0e6)
        _pair(ugl, "Constant (UND)", self.ur_const)
        _pair(ugl, "Initial value (UNDS)", self.ur_init)
        _pair(ugl, "Final value (UNDE)", self.ur_final)
        _pair(ugl, "Reference value (UDFC)", self.ur_ref)
        ugl.addWidget(_note(
            "UND = UNDS - {max(1 - ε/UDFC, 0)}^2 × (UNDS - UNDE)\n"
            "ε : Standardized variation\n"
            "Note) When non-linear loop is used, only the initial "
            "value is valid.", ug))
        self.ur_type.currentIndexChanged.connect(self._ur_sync_fields)
        edit.addWidget(ug, 1)

        # Pseudo time step
        dg = QGroupBox(
            "Stabilization (Pseudo time step relaxation)", ur)
        dgl = QVBoxLayout(dg)
        self.dts_type = QComboBox(dg)
        self.dts_type.addItems(self._DTS_TYPES)
        _pair(dgl, "Type", self.dts_type)
        self.dts_const = QDoubleSpinBox(dg)
        self.dts_init = QDoubleSpinBox(dg)
        self.dts_final = QDoubleSpinBox(dg)
        self.dts_rate = QDoubleSpinBox(dg)
        for sp in (self.dts_const, self.dts_init, self.dts_final,
                   self.dts_rate):
            sp.setDecimals(6)
            sp.setRange(0.0, 1.0e6)
        _pair(dgl, "Constant (DTS)", self.dts_const)
        _pair(dgl, "Initial value (DTSS)", self.dts_init)
        _pair(dgl, "Final value (DTSE)", self.dts_final)
        _pair(dgl, "Rate of increase (DTSC)", self.dts_rate)
        dgl.addWidget(_note(
            "DTS = min(DTSE, DTSS × DTSC^NCYC)\n"
            "(NCYC : Cycle)", dg))
        self.dts_type.currentIndexChanged.connect(self._ur_sync_fields)
        edit.addWidget(dg, 1)
        ul.addLayout(edit)

        foot = QHBoxLayout()
        self.ur_out_l = QCheckBox(
            "Output under-relaxation coefficient to L file", ur)
        foot.addWidget(self.ur_out_l)
        foot.addStretch(1)
        self.ur_btn_apply = QPushButton("Apply", ur)
        self.ur_btn_apply.clicked.connect(self._ur_apply)
        foot.addWidget(self.ur_btn_apply)
        ul.addLayout(foot)
        tabs.addTab(ur, "Under-relaxation/Pseudo Time Step Relaxation")

        lay.addWidget(tabs, 1)
        self._load()
        self._fixp_fill()
        self._ur_fill()
        self._ur_sync_fields()

    # -- Fixed Pressure ---------------------------------------------------

    def _point_parts(self) -> list[tuple[str, str]]:
        out = []
        for p in self.model.parts():
            kind = (p.kind or "").lower()
            attr = (p.attribute or "").lower()
            name = p.name or ""
            if not (kind == "point" or "point" in attr
                    or name.lower().startswith("point")):
                continue
            loc = p.base.strip() if p.base else ""
            if loc and not loc.startswith("("):
                loc = f"({loc})"
            out.append((name, loc))
        return out

    def _fixp_fill(self) -> None:
        raw = self.model.analysis_set_value("fixp", "")
        self._fixp = {}
        if raw:
            for rec in raw.split(";"):
                if "|" in rec:
                    n, v = rec.split("|", 1)
                    self._fixp[n.strip()] = v.strip()
        sel = self._fixp_selected_name()
        self.p_table.blockSignals(True)
        self.p_table.setRowCount(0)
        keep = -1
        for i, (name, loc) in enumerate(self._point_parts()):
            self.p_table.insertRow(i)
            self.p_table.setItem(i, 0, QTableWidgetItem(name))
            self.p_table.setItem(i, 1, QTableWidgetItem(""))
            self.p_table.setItem(i, 2, QTableWidgetItem(loc))
            self.p_table.setItem(
                i, 3, QTableWidgetItem(self._fixp.get(name, "")))
            if name == sel:
                keep = i
        self.p_table.blockSignals(False)
        if self.p_table.rowCount():
            self.p_table.selectRow(keep if keep >= 0 else 0)

    def _fixp_selected_name(self) -> str:
        if not hasattr(self, "p_table") or self.p_table.selectionModel() is None:
            return ""
        rows = self.p_table.selectionModel().selectedRows()
        if not rows:
            return ""
        it = self.p_table.item(rows[0].row(), 0)
        return it.text().strip() if it else ""

    def _fixp_on_sel(self) -> None:
        name = self._fixp_selected_name()
        text = self._fixp.get(name, "0")
        try:
            self.fixp_value.setValue(float(text) if text else 0.0)
        except ValueError:
            self.fixp_value.setValue(0.0)

    def _fixp_apply(self) -> None:
        name = self._fixp_selected_name()
        if not name:
            QMessageBox.information(
                self, "Fixed Pressure",
                "Select a point from the list.\n"
                "(Note) Create a point part in advance.")
            return
        val = f"{self.fixp_value.value():g}"
        self._fixp[name] = val
        self._fixp_save()
        self._fixp_fill()

    def _fixp_cancel(self) -> None:
        name = self._fixp_selected_name()
        if not name or name not in self._fixp:
            return
        del self._fixp[name]
        self._fixp_save()
        self._fixp_fill()

    def _fixp_select_hint(self) -> None:
        QMessageBox.information(
            self, "Select",
            "Select a point part in the Draw window "
            "(phase-1: use the list).")

    def _fixp_save(self) -> None:
        parts = [f"{n}|{v}" for n, v in self._fixp.items()]
        self.model.set_analysis_set_value("fixp", ";".join(parts))

    # -- Under-relaxation / DTSR -----------------------------------------

    def _ur_summary(self, kind: str, d: dict) -> str:
        t = d.get(f"{kind}_type", "Default(solver-defined)")
        if t.startswith("Default"):
            return "Default(solver-defined)"
        if t == "Same as temperature" or t == "Same as above":
            return t
        if t == "Constant":
            key = "ur_const" if kind == "ur" else "dts_const"
            return f"Constant= {d.get(key, '0')}"
        if t == "Use the following equation":
            if kind == "ur":
                return (f"Initial value= {d.get('ur_init', '0')} "
                        f"Final value= {d.get('ur_final', '0')} "
                        f"Reference value= {d.get('ur_ref', '0')}")
            return (f"Initial value= {d.get('dts_init', '0')} "
                    f"Final value= {d.get('dts_final', '0')} "
                    f"Rate of increase= {d.get('dts_rate', '0')}")
        return t

    def _ur_default_row(self, target: str) -> dict:
        d = {
            "ur_type": "Default(solver-defined)",
            "dts_type": "Default(solver-defined)",
            "ur_const": "0", "ur_init": "0", "ur_final": "0", "ur_ref": "0",
            "dts_const": "0", "dts_init": "0", "dts_final": "0",
            "dts_rate": "0",
        }
        if target == "Temperature (Solid)":
            d["ur_type"] = "Same as above"
            d["dts_type"] = "Same as above"
        return d

    def _ur_fill(self) -> None:
        if not self._ur_rows:
            for t in self._UR_TARGETS:
                self._ur_rows[t] = self._ur_default_row(t)
        self.ur_table.blockSignals(True)
        self.ur_table.setRowCount(0)
        for i, t in enumerate(self._UR_TARGETS):
            d = self._ur_rows.setdefault(t, self._ur_default_row(t))
            self.ur_table.insertRow(i)
            self.ur_table.setItem(i, 0, QTableWidgetItem(t))
            self.ur_table.setItem(
                i, 1, QTableWidgetItem(self._ur_summary("ur", d)))
            self.ur_table.setItem(
                i, 2, QTableWidgetItem(self._ur_summary("dts", d)))
        self.ur_table.blockSignals(False)
        if self.ur_table.rowCount():
            self.ur_table.selectRow(0)
            self._ur_on_sel()

    def _ur_selected_target(self) -> str:
        rows = self.ur_table.selectionModel().selectedRows() \
            if self.ur_table.selectionModel() else []
        if not rows:
            return ""
        it = self.ur_table.item(rows[0].row(), 0)
        return it.text() if it else ""

    def _ur_on_sel(self) -> None:
        t = self._ur_selected_target()
        if not t:
            return
        d = self._ur_rows.setdefault(t, self._ur_default_row(t))
        for combo, key, items in (
                (self.ur_type, "ur_type", self._UR_TYPES),
                (self.dts_type, "dts_type", self._DTS_TYPES)):
            val = d.get(key, items[0])
            idx = combo.findText(val)
            combo.blockSignals(True)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
        for sp, key in (
                (self.ur_const, "ur_const"), (self.ur_init, "ur_init"),
                (self.ur_final, "ur_final"), (self.ur_ref, "ur_ref"),
                (self.dts_const, "dts_const"), (self.dts_init, "dts_init"),
                (self.dts_final, "dts_final"), (self.dts_rate, "dts_rate")):
            try:
                sp.setValue(float(d.get(key, "0") or 0))
            except ValueError:
                sp.setValue(0.0)
        # Solid temperature: under-relaxation cannot be set (STpre note).
        solid = t == "Temperature (Solid)"
        self.ur_type.setEnabled(not solid and self.ur_details.isChecked())
        self._ur_sync_fields()

    def _ur_sync_fields(self) -> None:
        details = self.ur_details.isChecked()
        t = self._ur_selected_target()
        solid = t == "Temperature (Solid)"
        ur_t = self.ur_type.currentText()
        dts_t = self.dts_type.currentText()
        ur_edit = details and not solid and ur_t in (
            "Constant", "Constant (controlled)",
            "Use the following equation")
        dts_edit = details and dts_t in (
            "Constant", "Constant (controlled)",
            "Use the following equation")
        self.ur_const.setEnabled(ur_edit and ur_t.startswith("Constant"))
        for sp in (self.ur_init, self.ur_final, self.ur_ref):
            sp.setEnabled(ur_edit and ur_t.startswith("Use the following"))
        self.dts_const.setEnabled(dts_edit and dts_t.startswith("Constant"))
        for sp in (self.dts_init, self.dts_final, self.dts_rate):
            sp.setEnabled(dts_edit and dts_t.startswith("Use the following"))
        self.ur_type.setEnabled(details and not solid)
        self.dts_type.setEnabled(details)
        self.ur_btn_apply.setEnabled(details)

    def _ur_apply(self) -> None:
        t = self._ur_selected_target()
        if not t:
            QMessageBox.information(
                self, "Stabilization", "Select a target from the list.")
            return
        d = self._ur_rows.setdefault(t, self._ur_default_row(t))
        if t != "Temperature (Solid)":
            d["ur_type"] = self.ur_type.currentText()
            d["ur_const"] = f"{self.ur_const.value():g}"
            d["ur_init"] = f"{self.ur_init.value():g}"
            d["ur_final"] = f"{self.ur_final.value():g}"
            d["ur_ref"] = f"{self.ur_ref.value():g}"
        d["dts_type"] = self.dts_type.currentText()
        d["dts_const"] = f"{self.dts_const.value():g}"
        d["dts_init"] = f"{self.dts_init.value():g}"
        d["dts_final"] = f"{self.dts_final.value():g}"
        d["dts_rate"] = f"{self.dts_rate.value():g}"
        self._ur_rows[t] = d
        self._ur_fill()
        # reselect same target
        for r in range(self.ur_table.rowCount()):
            it = self.ur_table.item(r, 0)
            if it and it.text() == t:
                self.ur_table.selectRow(r)
                break

    def _load(self) -> None:
        auto = self.model.analysis_set_value("auto_fix_pressure", "T")
        self.auto_p.setChecked(auto.upper() not in ("F", "0", "FALSE"))
        mode = self.model.analysis_set_value("autofixp_mode", "0")
        if mode.strip() == "1":
            self.p_mode2.setChecked(True)
        else:
            self.p_mode1.setChecked(True)
        out = self.model.analysis_set_value("undr_lfile", "F")
        self.ur_out_l.setChecked(out.upper() in ("T", "1", "TRUE"))
        raw = self.model.analysis_set_value("undr", "")
        self._ur_rows = {}
        if raw:
            for rec in raw.split(";;"):
                bits = rec.split("|")
                if len(bits) >= 9:
                    name = bits[0]
                    self._ur_rows[name] = {
                        "ur_type": bits[1], "dts_type": bits[2],
                        "ur_const": bits[3], "ur_init": bits[4],
                        "ur_final": bits[5], "ur_ref": bits[6],
                        "dts_const": bits[7], "dts_init": bits[8],
                        "dts_final": bits[9] if len(bits) > 9 else "0",
                        "dts_rate": bits[10] if len(bits) > 10 else "0",
                    }
        self.ur_details.toggled.connect(self._ur_sync_fields)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "auto_fix_pressure",
            "T" if self.auto_p.isChecked() else "F")
        self.model.set_analysis_set_value(
            "autofixp_mode", "1" if self.p_mode2.isChecked() else "0")
        self._fixp_save()
        self.model.set_analysis_set_value(
            "undr_lfile", "T" if self.ur_out_l.isChecked() else "F")
        parts = []
        for t in self._UR_TARGETS:
            d = self._ur_rows.get(t, self._ur_default_row(t))
            parts.append("|".join((
                t, d.get("ur_type", ""), d.get("dts_type", ""),
                d.get("ur_const", "0"), d.get("ur_init", "0"),
                d.get("ur_final", "0"), d.get("ur_ref", "0"),
                d.get("dts_const", "0"), d.get("dts_init", "0"),
                d.get("dts_final", "0"), d.get("dts_rate", "0"),
            )))
        self.model.set_analysis_set_value("undr", ";;".join(parts))


class _CwControlOptionPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Option (Process / Unsupported / Script / Parallel)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._scripts: list[dict] = []  # {name, type, body}
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        self.tabs = tabs

        # ----- Process Interruption -----
        pi = QWidget()
        pl = QVBoxLayout(pi)
        pl.addWidget(_note("Sets process interruption routine.", pi))
        g1 = QGroupBox("Process interruption", pi)
        g1l = QVBoxLayout(g1)
        self.proc = QCheckBox("Process interruption", g1)
        g1l.addWidget(self.proc)
        self.proc_udf = QRadioButton("User-defined Function", g1)
        self.proc_script = QRadioButton("Formatted script", g1)
        self.proc_udf.setEnabled(False)
        self.proc_script.setEnabled(False)
        self.proc.toggled.connect(self.proc_udf.setEnabled)
        self.proc.toggled.connect(self.proc_script.setEnabled)
        g1l.addWidget(self.proc_udf)
        g1l.addWidget(self.proc_script)
        pl.addWidget(g1)
        g2 = QGroupBox("Modification of final cycle", pi)
        g2l = QHBoxLayout(g2)
        self.final_cycle = QCheckBox("Final cycle", g2)
        g2l.addWidget(self.final_cycle)
        g2l.addStretch(1)
        pl.addWidget(g2)
        g3 = QGroupBox("Creation of user-defined variables", pi)
        g3l = QHBoxLayout(g3)
        self.udv = QCheckBox("User-defined variables", g3)
        g3l.addWidget(self.udv)
        g3l.addStretch(1)
        pl.addWidget(g3)
        pl.addStretch(1)
        tabs.addTab(pi, "Process Interruption")

        # ----- Unsupported STpre Analysis Conditions -----
        uns = QWidget()
        ul = QVBoxLayout(uns)
        ul.addWidget(_note(
            "The following text is added to the end of S file and output.",
            uns))
        urow = QHBoxLayout()
        self.uns_out = QCheckBox("Output", uns)
        self.uns_lines = QLabel("Number of input lines: 0", uns)
        urow.addWidget(self.uns_out)
        urow.addStretch(1)
        urow.addWidget(self.uns_lines)
        ul.addLayout(urow)
        self.uns_text = QTextEdit(uns)
        self.uns_text.setAcceptRichText(False)
        self.uns_text.setPlaceholderText(
            "Enter unsupported analysis conditions (appended before "
            "the last command of the S file when Output is checked).")
        self.uns_text.textChanged.connect(self._uns_update_lines)
        self.uns_out.toggled.connect(self.uns_text.setEnabled)
        ul.addWidget(self.uns_text, 1)
        tabs.addTab(uns, "Unsupported STpre Analysis Conditions")

        # ----- Script List -----
        sc = QWidget()
        scl = QVBoxLayout(sc)
        scl.addWidget(_note("List of scripts are shown below.", sc))
        split = QSplitter(Qt.Horizontal, sc)
        left = QWidget(split)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.script_table = QTableWidget(0, 3, left)
        self.script_table.setHorizontalHeaderLabels(["Name", "*", "Type"])
        self.script_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.script_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.script_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        self.script_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.script_table.setSelectionMode(QTableWidget.SingleSelection)
        self.script_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.script_table.itemSelectionChanged.connect(self._script_on_sel)
        ll.addWidget(self.script_table, 1)
        split.addWidget(left)
        right = QWidget(split)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Contents (Display only)", right))
        self.script_view = QTextEdit(right)
        self.script_view.setReadOnly(True)
        self.script_view.setAcceptRichText(False)
        rl.addWidget(self.script_view, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        scl.addWidget(split, 1)
        brow = QHBoxLayout()
        self.script_btn_edit = QPushButton("Edit", sc)
        self.script_btn_del = QPushButton("Delete", sc)
        self.script_btn_gvar = QPushButton("Global Variable", sc)
        self.script_btn_new = QPushButton("Script", sc)
        self.script_btn_check = QPushButton("Check", sc)
        self.script_btn_edit.clicked.connect(self._script_edit)
        self.script_btn_del.clicked.connect(self._script_delete)
        self.script_btn_gvar.clicked.connect(self._script_global_var)
        self.script_btn_new.clicked.connect(self._script_new)
        self.script_btn_check.clicked.connect(self._script_check)
        for b in (self.script_btn_edit, self.script_btn_del,
                  self.script_btn_gvar, self.script_btn_new):
            brow.addWidget(b)
        brow.addStretch(1)
        brow.addWidget(self.script_btn_check)
        scl.addLayout(brow)
        note = QLabel(
            "(Note) Scripts set to material properties and DEM Particle "
            "Characteristics will not be listed.", sc)
        note.setStyleSheet("color: #555;")
        note.setWordWrap(True)
        scl.addWidget(note)
        tabs.addTab(sc, "Script List")

        # ----- Parallel Computing -----
        par = QWidget()
        pal = QVBoxLayout(par)
        pal.addWidget(_note(
            "Controls the domain partitioning in parallel computing.", par))
        sep = QFrame(par)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        pal.addWidget(sep)
        node = QGroupBox("Cluster node", par)
        nl = QVBoxLayout(node)
        self.par_uniform = QCheckBox(
            "Assign domain so that the number of elements allocated "
            "to each node will be uniform", node)
        nl.addWidget(self.par_uniform)
        pal.addWidget(node)
        pal.addStretch(1)
        tabs.addTab(par, "Parallel Computing")

        lay.addWidget(tabs, 1)
        self._load()

    def _uns_update_lines(self) -> None:
        text = self.uns_text.toPlainText()
        if not text:
            n = 0
        elif text.endswith("\n"):
            n = text.count("\n")
        else:
            n = text.count("\n") + 1
        self.uns_lines.setText(f"Number of input lines: {n}")

    def _script_fill(self) -> None:
        self.script_table.blockSignals(True)
        self.script_table.setRowCount(0)
        for i, sc in enumerate(self._scripts):
            self.script_table.insertRow(i)
            self.script_table.setItem(i, 0, QTableWidgetItem(sc["name"]))
            self.script_table.setItem(i, 1, QTableWidgetItem(""))
            self.script_table.setItem(i, 2, QTableWidgetItem(sc["type"]))
        self.script_table.blockSignals(False)
        if self._scripts:
            self.script_table.selectRow(0)
        else:
            self.script_view.clear()

    def _script_selected_index(self) -> int:
        rows = self.script_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _script_on_sel(self) -> None:
        i = self._script_selected_index()
        if 0 <= i < len(self._scripts):
            self.script_view.setPlainText(self._scripts[i].get("body", ""))
        else:
            self.script_view.clear()

    def _script_dialog(self, *, name: str = "", stype: str = "Unformatted",
                       body: str = "") -> Optional[dict]:
        dlg = QDialog(self)
        dlg.setWindowTitle("Script")
        dlg.resize(480, 360)
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit(name or self._script_unique_name(), dlg)
        _pair(lay, "Name", name_ed)
        type_cb = QComboBox(dlg)
        type_cb.addItems(["Unformatted", "Formatted"])
        idx = type_cb.findText(stype)
        type_cb.setCurrentIndex(idx if idx >= 0 else 0)
        _pair(lay, "Type", type_cb)
        lay.addWidget(QLabel("Contents", dlg))
        body_ed = QTextEdit(dlg)
        body_ed.setAcceptRichText(False)
        if not body and not name:
            n = name_ed.text().strip() or "sc1"
            body = f"function {n}()\n{{\n    return 0.0;\n}}\n"
        body_ed.setPlainText(body)
        lay.addWidget(body_ed, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        lay.addLayout(brow)
        if not dlg.exec_():
            return None
        n = name_ed.text().strip()
        if not n:
            QMessageBox.warning(self, "Script", "Enter a script name.")
            return None
        return {
            "name": n,
            "type": type_cb.currentText(),
            "body": body_ed.toPlainText(),
        }

    def _script_unique_name(self) -> str:
        existing = {s["name"] for s in self._scripts}
        i = 1
        while f"sc{i}" in existing:
            i += 1
        return f"sc{i}"

    def _script_new(self) -> None:
        result = self._script_dialog()
        if result is None:
            return
        if any(s["name"] == result["name"] for s in self._scripts):
            QMessageBox.warning(
                self, "Script",
                f"Script '{result['name']}' already exists.")
            return
        self._scripts.append(result)
        self._script_fill()
        self.script_table.selectRow(len(self._scripts) - 1)

    def _script_edit(self) -> None:
        i = self._script_selected_index()
        if i < 0:
            QMessageBox.information(
                self, "Edit", "Select a script from the list.")
            return
        cur = self._scripts[i]
        result = self._script_dialog(
            name=cur["name"], stype=cur["type"], body=cur.get("body", ""))
        if result is None:
            return
        for j, s in enumerate(self._scripts):
            if j != i and s["name"] == result["name"]:
                QMessageBox.warning(
                    self, "Script",
                    f"Script '{result['name']}' already exists.")
                return
        self._scripts[i] = result
        self._script_fill()
        self.script_table.selectRow(i)

    def _script_delete(self) -> None:
        i = self._script_selected_index()
        if i < 0:
            return
        name = self._scripts[i]["name"]
        if QMessageBox.question(
                self, "Delete",
                f"Delete script '{name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        del self._scripts[i]
        self._script_fill()

    def _script_global_var(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Global Variable")
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note(
            "Register a global variable used from scripts "
            "(phase-1: stored with Script List).", dlg))
        name_ed = QLineEdit(dlg)
        _pair(lay, "Variable name", name_ed)
        val_ed = QLineEdit("0", dlg)
        _pair(lay, "Initial value", val_ed)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        lay.addLayout(brow)
        if not dlg.exec_():
            return
        n = name_ed.text().strip()
        if not n:
            return
        # Represent as a small helper script entry for visibility.
        body = f"// global {n} = {val_ed.text().strip() or '0'}\n"
        self._scripts.append({
            "name": n, "type": "Global variable", "body": body})
        self._script_fill()

    def _script_check(self) -> None:
        i = self._script_selected_index()
        if i < 0:
            QMessageBox.information(
                self, "Check", "Select a script from the list.")
            return
        sc = self._scripts[i]
        body = sc.get("body", "")
        problems = []
        if not body.strip():
            problems.append("Script body is empty.")
        if sc["type"] == "Unformatted" and "function" not in body \
                and "return" not in body:
            problems.append(
                "Unformatted script typically defines a function "
                "with a return value.")
        if problems:
            QMessageBox.warning(
                self, "Check",
                f"Script '{sc['name']}':\n- " + "\n- ".join(problems))
        else:
            QMessageBox.information(
                self, "Check",
                f"Script '{sc['name']}' looks OK.")

    def _load(self) -> None:
        out = self.model.analysis_set_value("unsupported_output", "F")
        self.uns_out.setChecked(out.upper() in ("T", "1", "TRUE"))
        text = self.model.analysis_set_value("unsupported_sfile", "")
        # Newlines were stored as &#10; or literal \n — accept both.
        text = text.replace("&#10;", "\n").replace("\\n", "\n")
        self.uns_text.setPlainText(text)
        self.uns_text.setEnabled(self.uns_out.isChecked())
        self._uns_update_lines()

        self._scripts = []
        raw = self.model.analysis_set_value("script_list", "")
        if raw:
            for rec in raw.split("\x1e"):  # record separator
                bits = rec.split("\x1f", 2)
                if len(bits) >= 3:
                    self._scripts.append({
                        "name": bits[0],
                        "type": bits[1],
                        "body": bits[2].replace("&#10;", "\n"),
                    })
        self._script_fill()

        uni = self.model.analysis_set_value("partition_uniform", "F")
        self.par_uniform.setChecked(uni.upper() in ("T", "1", "TRUE"))

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "process_interrupt",
            "T" if self.proc.isChecked() else "F")
        self.model.set_analysis_set_value(
            "final_cycle_mod",
            "T" if self.final_cycle.isChecked() else "F")
        self.model.set_analysis_set_value(
            "user_defined_vars",
            "T" if self.udv.isChecked() else "F")
        self.model.set_analysis_set_value(
            "unsupported_output",
            "T" if self.uns_out.isChecked() else "F")
        # Store newlines escaped so analysis_set text stays single-line-ish.
        body = self.uns_text.toPlainText().replace("\n", "&#10;")
        self.model.set_analysis_set_value("unsupported_sfile", body)
        parts = []
        for sc in self._scripts:
            parts.append("\x1f".join((
                sc["name"], sc["type"],
                sc.get("body", "").replace("\n", "&#10;"))))
        self.model.set_analysis_set_value("script_list", "\x1e".join(parts))
        self.model.set_analysis_set_value(
            "partition_uniform",
            "T" if self.par_uniform.isChecked() else "F")


def _fill_var_table(table: "QTableWidget", names: list[str],
                    selected: set[str]) -> None:
    table.setRowCount(0)
    for i, name in enumerate(names):
        table.insertRow(i)
        table.setItem(i, 0, QTableWidgetItem(name))
        table.setItem(
            i, 1, QTableWidgetItem("Selected" if name in selected else ""))


def _var_table_page(parent, blurb: str, names: list[str], selected: set[str],
                    *, extra_top=None):
    """Shared Variable/Output list with Output / Cancel (STpre pattern)."""
    page = QWidget(parent)
    lay = QVBoxLayout(page)
    lay.addWidget(_note(blurb, page))
    if extra_top is not None:
        lay.addLayout(extra_top)
    body = QHBoxLayout()
    table = QTableWidget(0, 2, page)
    table.setHorizontalHeaderLabels(["Variable", "Output"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    _fill_var_table(table, names, selected)
    body.addWidget(table, 1)
    side = QVBoxLayout()
    btn_out = QPushButton("Output", page)
    btn_cancel = QPushButton("Cancel", page)

    def _out():
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        selected.add(name)
        _fill_var_table(table, names, selected)

    def _cancel():
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        selected.discard(name)
        _fill_var_table(table, names, selected)

    btn_out.clicked.connect(_out)
    btn_cancel.clicked.connect(_cancel)
    side.addWidget(btn_out)
    side.addWidget(btn_cancel)
    side.addStretch(1)
    body.addLayout(side)
    lay.addLayout(body, 1)
    return page, table


class _CwOutputFieldPage(QWidget if _HAS_GUI else object):
    """Output Condition → Field File (STpre tab order)."""

    _TAB_ORDER = (
        "Surface Data",
        "Analysis Variables",
        "WBGT",
        "Heat Transfer Coefficient (Mapping)",
    )

    _ANALYSIS_VARS = (
        "X-component of velocity", "Y-component of velocity",
        "Z-component of velocity", "Pressure", "Temperature",
        "Turbulent kinetic energy", "Turbulent dissipation rate",
        "Coefficient of eddy viscosity", "Density",
        "Absolute humidity", "Relative humidity",
        "X-component of heat flux", "Y-component of heat flux",
        "Z-component of heat flux",
        "Specific heat at constant pressure", "Viscosity",
        "Thermal conductivity",
    )
    _SURFACE_VARS = (
        "Wall friction velocity", "Wall shear stress",
        "Dimensionless wall distance", "Coefficient of heat transfer",
        "Surface temperature", "Heat flux",
        "Mean radiant temperature", "Radiation surface irradiation",
        "Sunshine heat flux", "Pressure",
    )

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._fld_sel: set[str] = set()
        self._surf_sel: set[str] = {
            "Coefficient of heat transfer", "Surface temperature", "Heat flux"}
        self._htc_sel: set[str] = set()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        self.tabs = tabs
        builders = {
            "Surface Data": self._build_surface,
            "Analysis Variables": self._build_analysis,
            "WBGT": self._build_wbgt,
            "Heat Transfer Coefficient (Mapping)": self._build_htc_map,
        }
        for title in self._TAB_ORDER:
            tabs.addTab(builders[title](), title)
        root.addWidget(tabs, 1)
        self._load()
        _fill_var_table(self.fld_table, list(self._ANALYSIS_VARS),
                        self._fld_sel)
        self._fld_sync_enabled()
        self._wbgt_sync_enabled()

    def _build_surface(self) -> QWidget:
        surf, self.surf_table = _var_table_page(
            self,
            "Sets the surface data to be output to Field file.",
            list(self._SURFACE_VARS), self._surf_sel)
        return surf

    def _build_analysis(self) -> QWidget:
        av = QWidget()
        al = QVBoxLayout(av)
        al.addWidget(_note("Sets variables to be output to Field file.", av))
        self.fld_change = QCheckBox("Change output variables", av)
        self.fld_change.setChecked(True)
        al.addWidget(self.fld_change)
        tip = QLabel(
            "(It is recommended that all the computed variables are "
            "output.)", av)
        tip.setStyleSheet("color: #555;")
        tip.setWordWrap(True)
        al.addWidget(tip)
        self.fld_mod = QComboBox(av)
        self.fld_mod.addItems([
            "Add to default variables", "Only specified variables"])
        _pair(al, "Modification type", self.fld_mod)
        body = QHBoxLayout()
        self.fld_table = QTableWidget(0, 2, av)
        self.fld_table.setHorizontalHeaderLabels(["Variable", "Output"])
        self.fld_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.fld_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fld_table.setSelectionMode(QTableWidget.SingleSelection)
        self.fld_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.fld_table, 1)
        side = QVBoxLayout()
        self.fld_btn_out = QPushButton("Output", av)
        self.fld_btn_cancel = QPushButton("Cancel", av)
        self.fld_btn_out.clicked.connect(
            lambda: self._toggle_sel(self.fld_table, self._fld_sel,
                                     self._ANALYSIS_VARS, True))
        self.fld_btn_cancel.clicked.connect(
            lambda: self._toggle_sel(self.fld_table, self._fld_sel,
                                     self._ANALYSIS_VARS, False))
        side.addWidget(self.fld_btn_out)
        side.addWidget(self.fld_btn_cancel)
        side.addStretch(1)
        body.addLayout(side)
        al.addLayout(body, 1)
        les = QGroupBox("Averaging of data (LES model)", av)
        ll = QVBoxLayout(les)
        self.fld_avg = QCheckBox("Execute time-averaged data", les)
        ll.addWidget(self.fld_avg)
        spat = QGroupBox("Type of spatial average", les)
        sl = QVBoxLayout(spat)
        self.fld_avg_none = QRadioButton("None", spat)
        self.fld_avg_x = QRadioButton("X direction", spat)
        self.fld_avg_y = QRadioButton("Y direction", spat)
        self.fld_avg_z = QRadioButton("Z direction", spat)
        self.fld_avg_none.setChecked(True)
        for r in (self.fld_avg_none, self.fld_avg_x, self.fld_avg_y,
                  self.fld_avg_z):
            sl.addWidget(r)
            r.setEnabled(False)
        self.fld_avg.toggled.connect(
            lambda on: [w.setEnabled(on) for w in (
                self.fld_avg_none, self.fld_avg_x, self.fld_avg_y,
                self.fld_avg_z)])
        ll.addWidget(spat)
        ll.addWidget(_note(
            "Note) If [None] is selected, only time average is executed.\n"
            "Note) Every time a field file is output, averaging "
            "operation is reset.", les))
        al.addWidget(les)
        self.fld_change.toggled.connect(self._fld_sync_enabled)
        return av

    def _build_wbgt(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets parameters to output WBGT to Field file.", page))
        self.wbgt_on = QCheckBox("Output WBGT", page)
        lay.addWidget(self.wbgt_on)
        self.wbgt_type = QComboBox(page)
        self.wbgt_type.addItems([
            "Indoor / Outdoor (auto)", "Indoor", "Outdoor"])
        _pair(lay, "Calculation type", self.wbgt_type)
        lay.addWidget(_note(
            "Note) Space distribution of global solar radiation in a "
            "solar radiation analysis must be output.", page))
        self.wbgt_vel = QDoubleSpinBox(page)
        self.wbgt_vel.setDecimals(4)
        self.wbgt_vel.setRange(0, 1e6)
        self.wbgt_vel.setValue(0.1)
        _pair(lay, "Velocity", self.wbgt_vel, "m/s")
        self.wbgt_insol = QDoubleSpinBox(page)
        self.wbgt_insol.setDecimals(4)
        self.wbgt_insol.setRange(0, 1e6)
        self.wbgt_insol.setValue(0)
        _pair(lay, "Insolation", self.wbgt_insol, "W/m2")
        lay.addWidget(_note(
            "Note) WBGT is calculated for indoor when the values is "
            "below the threshold, and for outdoor when the value is "
            "over the threshold.", page))
        self.wbgt_rh = QDoubleSpinBox(page)
        self.wbgt_rh.setDecimals(2)
        self.wbgt_rh.setRange(0, 100)
        self.wbgt_rh.setValue(50)
        _pair(lay, "Relative humidity", self.wbgt_rh, "%")
        lay.addWidget(_note(
            "Note) Set the parameter when humidity is not analyzed.", page))
        thr = QGroupBox("Threshold", page)
        tl = QVBoxLayout(thr)
        self.wbgt_thr = QDoubleSpinBox(thr)
        self.wbgt_thr.setDecimals(4)
        self.wbgt_thr.setRange(0, 1e6)
        self.wbgt_thr.setValue(0)
        _pair(tl, "Threshold", self.wbgt_thr)
        lay.addWidget(thr)
        lay.addStretch(1)
        self.wbgt_on.toggled.connect(self._wbgt_sync_enabled)
        return page

    def _build_htc_map(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets parts whose heat transfer coefficient and corresponding "
            "temperature are used in the mapping destination.", page))
        body = QHBoxLayout()
        self.htc_table = QTableWidget(0, 3, page)
        self.htc_table.setHorizontalHeaderLabels(
            ["Part name", "*", "Output"])
        self.htc_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.htc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.htc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.htc_table, 1)
        side = QVBoxLayout()
        btn_s = QPushButton("Set", page)
        btn_c = QPushButton("Cancel", page)
        btn_s.clicked.connect(lambda: self._htc_toggle(True))
        btn_c.clicked.connect(lambda: self._htc_toggle(False))
        side.addWidget(btn_s)
        side.addWidget(btn_c)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 1)
        tip = QLabel("Select from list > Set", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)
        return page

    def _htc_fill(self) -> None:
        names = [p.name for p in self.model.parts() if p.name]
        self.htc_table.setRowCount(0)
        for i, name in enumerate(names):
            self.htc_table.insertRow(i)
            self.htc_table.setItem(i, 0, QTableWidgetItem(name))
            self.htc_table.setItem(i, 1, QTableWidgetItem(""))
            mark = "Selected" if name in self._htc_sel else ""
            self.htc_table.setItem(i, 2, QTableWidgetItem(mark))

    def _htc_toggle(self, on: bool) -> None:
        rows = self.htc_table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.htc_table.item(rows[0].row(), 0).text()
        if on:
            self._htc_sel.add(name)
        else:
            self._htc_sel.discard(name)
        self.htc_table.item(rows[0].row(), 2).setText(
            "Selected" if on else "")

    @staticmethod
    def _toggle_sel(table, selected: set, names, add: bool) -> None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        if add:
            selected.add(name)
        else:
            selected.discard(name)
        _fill_var_table(table, list(names), selected)

    def _fld_sync_enabled(self) -> None:
        on = self.fld_change.isChecked()
        self.fld_mod.setEnabled(on)
        self.fld_table.setEnabled(on)
        self.fld_btn_out.setEnabled(on)
        self.fld_btn_cancel.setEnabled(on)

    def _wbgt_sync_enabled(self) -> None:
        on = self.wbgt_on.isChecked()
        for w in (self.wbgt_type, self.wbgt_vel, self.wbgt_insol,
                  self.wbgt_rh, self.wbgt_thr):
            w.setEnabled(on)

    def _load(self) -> None:
        ch = self.model.analysis_set_value("fld_change_vars", "T")
        self.fld_change.setChecked(ch.upper() not in ("F", "0", "FALSE"))
        mod = self.model.analysis_set_value("fld_mod_type", "add")
        self.fld_mod.setCurrentIndex(
            1 if mod.strip().lower() in ("only", "specified") else 0)
        raw = self.model.analysis_set_value("fld_vars", "")
        if raw:
            self._fld_sel = {x for x in raw.split("|") if x}
        raw_s = self.model.analysis_set_value("fld_surf_vars", "")
        if raw_s:
            self._surf_sel = {x for x in raw_s.split("|") if x}
        _fill_var_table(self.surf_table, list(self._SURFACE_VARS),
                        self._surf_sel)
        avg = self.model.analysis_set_value("fld_time_avg", "F")
        self.fld_avg.setChecked(avg.upper() in ("T", "1", "TRUE"))
        spat = self.model.analysis_set_value("fld_spatial_avg", "none")
        {"x": self.fld_avg_x, "y": self.fld_avg_y, "z": self.fld_avg_z
         }.get(spat.strip().lower(), self.fld_avg_none).setChecked(True)

        wbgt = self.model.analysis_set_value("fld_wbgt", "F")
        self.wbgt_on.setChecked(wbgt.upper() in ("T", "1", "TRUE"))
        wtype = self.model.analysis_set_value("fld_wbgt_type", "auto")
        idx = {"auto": 0, "indoor": 1, "outdoor": 2}.get(
            wtype.strip().lower(), 0)
        self.wbgt_type.setCurrentIndex(idx)
        try:
            self.wbgt_vel.setValue(float(
                self.model.analysis_set_value("fld_wbgt_vel", "0.1") or 0.1))
            self.wbgt_insol.setValue(float(
                self.model.analysis_set_value("fld_wbgt_insol", "0") or 0))
            self.wbgt_rh.setValue(float(
                self.model.analysis_set_value("fld_wbgt_rh", "50") or 50))
            self.wbgt_thr.setValue(float(
                self.model.analysis_set_value("fld_wbgt_thr", "0") or 0))
        except ValueError:
            pass
        self._htc_sel = {
            x for x in self.model.analysis_set_value(
                "fld_htc_map_parts", "").split("|") if x}
        self._htc_fill()

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "fld_change_vars",
            "T" if self.fld_change.isChecked() else "F")
        self.model.set_analysis_set_value(
            "fld_mod_type",
            "only" if self.fld_mod.currentIndex() == 1 else "add")
        self.model.set_analysis_set_value(
            "fld_vars", "|".join(sorted(self._fld_sel)))
        self.model.set_analysis_set_value(
            "fld_surf_vars", "|".join(sorted(self._surf_sel)))
        self.model.set_analysis_set_value(
            "fld_time_avg",
            "T" if self.fld_avg.isChecked() else "F")
        spat = "none"
        if self.fld_avg_x.isChecked():
            spat = "x"
        elif self.fld_avg_y.isChecked():
            spat = "y"
        elif self.fld_avg_z.isChecked():
            spat = "z"
        self.model.set_analysis_set_value("fld_spatial_avg", spat)
        self.model.set_analysis_set_value(
            "fld_wbgt", "T" if self.wbgt_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "fld_wbgt_type",
            ("auto", "indoor", "outdoor")[self.wbgt_type.currentIndex()])
        self.model.set_analysis_set_value(
            "fld_wbgt_vel", f"{self.wbgt_vel.value():g}")
        self.model.set_analysis_set_value(
            "fld_wbgt_insol", f"{self.wbgt_insol.value():g}")
        self.model.set_analysis_set_value(
            "fld_wbgt_rh", f"{self.wbgt_rh.value():g}")
        self.model.set_analysis_set_value(
            "fld_wbgt_thr", f"{self.wbgt_thr.value():g}")
        self.model.set_analysis_set_value(
            "fld_htc_map_parts", "|".join(sorted(self._htc_sel)))


class _CwOutputHeatPathPage(QWidget if _HAS_GUI else object):
    """Output Condition → Heat Path."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._encl_parts: list[str] = ["*"]
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs the information required for investigating the "
            "heat path.", page))
        self.hp_on = QCheckBox("Output heat path file", page)
        lay.addWidget(self.hp_on)

        amb = QGroupBox("Ambient temperature", page)
        al = QVBoxLayout(amb)
        self.hp_amb = QDoubleSpinBox(amb)
        self.hp_amb.setDecimals(4)
        self.hp_amb.setRange(-273, 1e6)
        self.hp_amb.setValue(20)
        _pair(al, "Ambient temperature", self.hp_amb, "C")
        al.addWidget(_note(
            "Note) Set the reference temperature for buoyancy force and "
            "the default value of temperature.", amb))
        lay.addWidget(amb)

        iv = QGroupBox("Output interval", page)
        il = QVBoxLayout(iv)
        row = QHBoxLayout()
        self.hp_interval = QPushButton("Output Interval...", iv)
        self.hp_interval_lbl = QLabel("Last cycle only", iv)
        self.hp_interval.clicked.connect(self._edit_interval)
        row.addWidget(self.hp_interval)
        row.addWidget(self.hp_interval_lbl)
        row.addStretch(1)
        il.addLayout(row)
        self.hp_prop = QCheckBox("Output material properties", iv)
        self.hp_face = QCheckBox(
            "Output center of contact surfaces between parts", iv)
        il.addWidget(self.hp_prop)
        il.addWidget(self.hp_face)
        lay.addWidget(iv)

        enc = QGroupBox("Internal region of enclosure", page)
        el = QVBoxLayout(enc)
        self.hp_encl = QTableWidget(0, 1, enc)
        self.hp_encl.setHorizontalHeaderLabels(["Part name"])
        self.hp_encl.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.hp_encl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hp_encl.setSelectionBehavior(QTableWidget.SelectRows)
        el.addWidget(self.hp_encl, 1)
        brow = QHBoxLayout()
        b_add = QPushButton("Add", enc)
        b_del = QPushButton("Delete", enc)
        b_add.clicked.connect(self._encl_add)
        b_del.clicked.connect(self._encl_del)
        brow.addWidget(b_add)
        brow.addWidget(b_del)
        brow.addStretch(1)
        el.addLayout(brow)
        lay.addWidget(enc, 1)
        lay.addWidget(_note(
            "Note) Heat balance information targeted for all parts are "
            "always output.", page))

        self._hp_widgets = [
            amb, iv, self.hp_amb, self.hp_interval, self.hp_interval_lbl,
            self.hp_prop, self.hp_face,
        ]
        self.hp_on.toggled.connect(self._sync_enabled)
        tabs.addTab(page, "Heat Path")
        root.addWidget(tabs, 1)
        self._load()
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        on = self.hp_on.isChecked()
        for w in self._hp_widgets:
            w.setEnabled(on)

    def _encl_fill(self) -> None:
        self.hp_encl.setRowCount(0)
        for i, name in enumerate(self._encl_parts):
            self.hp_encl.insertRow(i)
            self.hp_encl.setItem(i, 0, QTableWidgetItem(name))

    def _encl_add(self) -> None:
        names = ["*"] + [p.name for p in self.model.parts() if p.name]
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "Internal region of enclosure", "Part name:",
            names, 0, False)
        if not ok or not name or name in self._encl_parts:
            return
        self._encl_parts.append(name)
        self._encl_fill()

    def _encl_del(self) -> None:
        rows = self.hp_encl.selectionModel().selectedRows()
        if not rows:
            return
        name = self.hp_encl.item(rows[0].row(), 0).text()
        if name == "*" and len(self._encl_parts) == 1:
            return
        self._encl_parts.pop(rows[0].row())
        if not self._encl_parts:
            self._encl_parts = ["*"]
        self._encl_fill()

    def _edit_interval(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Details (Output Interval)")
        dlg.resize(360, 160)
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note(
            "Sets the output interval of the heat path information.", dlg))
        only = QCheckBox("Last cycle only", dlg)
        only.setChecked(self.hp_interval_lbl.text() == "Last cycle only")
        lay.addWidget(only)
        cycle = QDoubleSpinBox(dlg)
        cycle.setDecimals(0)
        cycle.setRange(1, 1e9)
        try:
            cycle.setValue(float(
                self.model.analysis_set_value("heat_path_cycle", "0")
                or 0) or 1)
        except ValueError:
            cycle.setValue(1)
        _pair(lay, "Every N cycles", cycle)
        cycle.setEnabled(not only.isChecked())
        only.toggled.connect(lambda on: cycle.setEnabled(not on))
        bb = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        bb.addStretch(1)
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        if dlg.exec_() != QDialog.Accepted:
            return
        if only.isChecked():
            self.model.set_analysis_set_value("heat_path_cycle", "0")
            # keep type ":L" via attribute if element exists
            aset = self.model.ensure_analysis_set()
            el = None
            for c in aset:
                if c.tag == "heat_path_cycle":
                    el = c
                    break
            if el is not None:
                el.attrib["type"] = ":L"
            self.hp_interval_lbl.setText("Last cycle only")
        else:
            n = int(cycle.value())
            self.model.set_analysis_set_value("heat_path_cycle", f"{n}")
            self.hp_interval_lbl.setText(f"Every {n} cycle + Last cycle")

    def _load(self) -> None:
        hp = self.model.analysis_set_value("heat_path", "0")
        self.hp_on.setChecked(hp.strip() not in ("0", "F", "FALSE", ""))
        try:
            amb = float(self.model.project_value(
                "ambient_temperature", "20") or 20)
            self.hp_amb.setValue(amb)
        except ValueError:
            self.hp_amb.setValue(20)
        cyc = self.model.analysis_set_value("heat_path_cycle", "0")
        try:
            n = int(float(cyc or 0))
        except ValueError:
            n = 0
        if n <= 0:
            self.hp_interval_lbl.setText("Last cycle only")
        else:
            self.hp_interval_lbl.setText(f"Every {n} cycle + Last cycle")
        self.hp_prop.setChecked(
            self.model.analysis_set_value("heat_path_property", "0")
            .strip() in ("1", "T", "TRUE"))
        self.hp_face.setChecked(
            self.model.analysis_set_value("heat_path_face_center", "0")
            .strip() in ("1", "T", "TRUE"))
        raw = self.model.analysis_set_value("heat_path_enclosure", "*")
        self._encl_parts = [x for x in raw.split("|") if x] or ["*"]
        self._encl_fill()

    def apply(self) -> None:
        on = self.hp_on.isChecked()
        self.model.set_analysis_set_value("heat_path", "1" if on else "0")
        # Ambient is shared with Basic/Initial; only write when this page
        # can edit it (Output heat path file checked).
        if on:
            self.model.set_project_value(
                "ambient_temperature", f"{self.hp_amb.value():g}")
        self.model.set_analysis_set_value(
            "heat_path_property",
            "1" if self.hp_prop.isChecked() else "0")
        self.model.set_analysis_set_value(
            "heat_path_face_center",
            "1" if self.hp_face.isChecked() else "0")
        self.model.set_analysis_set_value(
            "heat_path_enclosure", "|".join(self._encl_parts))


class _CwOutputSeriesPage(QWidget if _HAS_GUI else object):
    """Output Condition → Time Series (point monitors)."""

    _TS_VARS = (
        "Temperature", "Pressure",
        "X-component of velocity", "Y-component of velocity",
        "Z-component of velocity",
        "Turbulent kinetic energy", "Turbulent dissipation rate",
        "Absolute humidity", "Relative humidity",
        "Surface temperature",
    )

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._ts: dict[str, str] = {}  # point -> variable
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.addWidget(_note("Set the time series data.", page))
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", page))
        self.ts_display = QComboBox(page)
        self.ts_display.addItems(["All regions", "Parts"])
        drow.addWidget(self.ts_display, 1)
        drow.addStretch(1)
        pl.addLayout(drow)

        body = QHBoxLayout()
        self.ts_table = QTableWidget(0, 4, page)
        self.ts_table.setHorizontalHeaderLabels(
            ["Point name", "*", "Coordinates", "Variable"])
        self.ts_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ts_table.setSelectionMode(QTableWidget.SingleSelection)
        self.ts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.ts_table, 1)
        newb = QGroupBox("New", page)
        nl = QVBoxLayout(newb)
        self.ts_var = QComboBox(newb)
        self.ts_var.addItems(self._TS_VARS)
        _pair(nl, "Variable name", self.ts_var)
        self.ts_btn_add = QPushButton("Add", newb)
        self.ts_btn_add.clicked.connect(self._ts_add)
        nl.addWidget(self.ts_btn_add)
        nl.addStretch(1)
        body.addWidget(newb)
        pl.addLayout(body, 1)

        # ---- R8-A 深字段：时间序列输出间隔 + 字段选择表 ----
        # .s 实证 TMSR 段（exB01 等）：每监测点行尾 R1/R2/R3... 为输出
        # 字段编号；XML 侧无 COM 保存实证，间隔存 analysis_set
        # timeseries_interval，字段选择存 timeseries_fields（分号分隔，
        # 未实证，按 TMSR 条目定义）。
        irow = QHBoxLayout()
        irow.addWidget(QLabel("Output interval (cycles)", page))
        self.ts_interval = QSpinBox(page)
        self.ts_interval.setRange(1, 10000000)
        try:
            self.ts_interval.setValue(int(float(
                model.analysis_set_value("timeseries_interval", "1"))))
        except (TypeError, ValueError):
            self.ts_interval.setValue(1)
        irow.addWidget(self.ts_interval)
        irow.addStretch(1)
        pl.addLayout(irow)

        fgrp = QGroupBox("Output fields", page)
        fgl = QVBoxLayout(fgrp)
        self.ts_fields = QTableWidget(0, 2, fgrp)
        self.ts_fields.setHorizontalHeaderLabels(["Field", "Output"])
        self.ts_fields.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        sel = set(filter(None, (s.strip() for s in
                                model.analysis_set_value(
                                    "timeseries_fields", "").split(";"))))
        for i, var in enumerate(self._TS_VARS):
            self.ts_fields.insertRow(i)
            self.ts_fields.setItem(i, 0, QTableWidgetItem(var))
            self.ts_fields.setItem(
                i, 1, QTableWidgetItem(
                    "Yes" if (not sel or var in sel) else "No"))
        fgl.addWidget(self.ts_fields)
        pl.addWidget(fgrp)

        brow = QHBoxLayout()
        tip = QLabel("Select from list > New", page)
        tip.setStyleSheet("color: #555;")
        brow.addWidget(tip)
        brow.addStretch(1)
        self.ts_btn_cancel = QPushButton("Cancel", page)
        self.ts_btn_select = QPushButton("Select", page)
        self.ts_btn_cancel.clicked.connect(self._ts_cancel)
        self.ts_btn_select.clicked.connect(self._ts_select_hint)
        brow.addWidget(self.ts_btn_cancel)
        brow.addWidget(self.ts_btn_select)
        pl.addLayout(brow)
        tabs.addTab(page, "Time Series")
        lay.addWidget(tabs, 1)
        self._load()
        self._ts_fill()

    def _point_parts(self) -> list[tuple[str, str]]:
        out = []
        for p in self.model.parts():
            kind = (p.kind or "").lower()
            attr = (p.attribute or "").lower()
            name = p.name or ""
            if not (kind == "point" or "point" in attr
                    or name.lower().startswith("point")):
                continue
            loc = p.base.strip() if p.base else ""
            if loc and not loc.startswith("("):
                loc = f"({loc})"
            out.append((name, loc))
        return out

    def _ts_fill(self) -> None:
        self.ts_table.setRowCount(0)
        for i, (name, loc) in enumerate(self._point_parts()):
            self.ts_table.insertRow(i)
            self.ts_table.setItem(i, 0, QTableWidgetItem(name))
            self.ts_table.setItem(i, 1, QTableWidgetItem(""))
            self.ts_table.setItem(i, 2, QTableWidgetItem(loc))
            self.ts_table.setItem(
                i, 3, QTableWidgetItem(self._ts.get(name, "")))

    def _ts_selected_name(self) -> str:
        rows = self.ts_table.selectionModel().selectedRows()
        if not rows:
            return ""
        it = self.ts_table.item(rows[0].row(), 0)
        return it.text().strip() if it else ""

    def _ts_add(self) -> None:
        name = self._ts_selected_name()
        if not name:
            QMessageBox.information(
                self, "Time Series",
                "Select a point from the list.\n"
                "(Note) Create a point part in advance.")
            return
        self._ts[name] = self.ts_var.currentText()
        self._ts_fill()

    def _ts_cancel(self) -> None:
        name = self._ts_selected_name()
        if not name or name not in self._ts:
            return
        del self._ts[name]
        self._ts_fill()

    def _ts_select_hint(self) -> None:
        QMessageBox.information(
            self, "Select",
            "Select a point part in the Draw window "
            "(phase-1: use the list).")

    def _load(self) -> None:
        raw = self.model.analysis_set_value("timeseries_points", "")
        self._ts = {}
        if raw:
            for rec in raw.split(";"):
                if "|" in rec:
                    n, v = rec.split("|", 1)
                    self._ts[n.strip()] = v.strip()

    def apply(self) -> None:
        parts = [f"{n}|{v}" for n, v in self._ts.items()]
        self.model.set_analysis_set_value(
            "timeseries_points", ";".join(parts))
        self.model.set_analysis_set_value(
            "timeseries_output",
            "T" if self._ts else "F")
        # R8-A 深字段：输出间隔与字段选择表写回
        self.model.set_analysis_set_value(
            "timeseries_interval", str(self.ts_interval.value()))
        chosen = []
        for i in range(self.ts_fields.rowCount()):
            it = self.ts_fields.item(i, 1)
            if it is not None and it.text().strip().lower() == "yes":
                name = self.ts_fields.item(i, 0)
                if name is not None:
                    chosen.append(name.text().strip())
        self.model.set_analysis_set_value(
            "timeseries_fields", ";".join(chosen))


class _CwOutputLFilePage(QWidget if _HAS_GUI else object):
    """Output Condition → L File (STpre tab order / layouts)."""

    # Order matches STpre Condition Wizard → L File.
    _TAB_ORDER = (
        "Entire Domain",
        "Specified Region",
        "Flux Balance",
        "Specified Region (Passage)",
        "Specified Region (Pressure)",
        "Standardized Concentration in Living Space",
        "Heat Balance (Per Part Unit)",
        "Heat Balance (Between Parts)",
        "Amount of Heat Transfer (Region)",
        "Cycle Information/Warning/Error",
    )

    _DOMAIN_VARS = (
        "X-component of velocity", "Y-component of velocity",
        "Z-component of velocity", "Pressure", "Temperature",
        "Turbulent kinetic energy", "Turbulent dissipation rate",
        "Coefficient of eddy viscosity", "Density",
        "Dynamic pressure", "Thermal energy density",
    )
    _REGION_VARS = (
        "Temperature", "Pressure",
        "X-component of velocity", "Y-component of velocity",
        "Z-component of velocity",
        "Turbulent kinetic energy", "Turbulent dissipation rate",
    )
    _PASSAGE_VARS = ("Flow rate", "Heat flux", "Temperature")
    _PRESSURE_VARS = ("Pressure", "Dynamic pressure", "Total pressure")

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._dom_sel: set[str] = {
            "X-component of velocity", "Y-component of velocity",
            "Z-component of velocity", "Pressure", "Temperature",
            "Turbulent kinetic energy", "Turbulent dissipation rate",
        }
        self._rgn_vol: dict[str, str] = {}
        self._rgn_face: dict[str, str] = {}
        self._passage: dict[str, str] = {}
        self._pressure: dict[str, str] = {}
        self._aent_sel: set[str] = set()
        self._hbal_part_sel: set[str] = set()
        self._hbal_pair_sel: set[str] = set()
        self._flux_sel: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        self.tabs = tabs

        builders = {
            "Entire Domain": self._build_entire_domain,
            "Specified Region": self._build_specified_region,
            "Flux Balance": self._build_flux_balance,
            "Specified Region (Passage)": self._build_passage,
            "Specified Region (Pressure)": self._build_pressure_region,
            "Standardized Concentration in Living Space":
                self._build_ncoz,
            "Heat Balance (Per Part Unit)": self._build_hbal_part,
            "Heat Balance (Between Parts)": self._build_hbal_pair,
            "Amount of Heat Transfer (Region)": self._build_aent_region,
            "Cycle Information/Warning/Error": self._build_cycle_warn,
        }
        for title in self._TAB_ORDER:
            tabs.addTab(builders[title](), title)

        root.addWidget(tabs, 1)
        self._load()
        _fill_var_table(self.l_dom_table, list(self._DOMAIN_VARS),
                        self._dom_sel)

    # -- tab builders -----------------------------------------------------

    def _build_entire_domain(self) -> QWidget:
        dom = QWidget()
        dl = QVBoxLayout(dom)
        dl.addWidget(_note(
            "Outputs average/minimum/maximum value of variables in the "
            "entire computational domain to L file.", dom))
        top = QHBoxLayout()
        col = QVBoxLayout()
        self.l_avg = QCheckBox("Output average value of variables", dom)
        self.l_avg.setChecked(True)
        self.l_minmax = QCheckBox(
            "Output minimum/maximum value of variables", dom)
        self.l_minmax.setChecked(True)
        col.addWidget(self.l_avg)
        col.addWidget(self.l_minmax)
        top.addLayout(col, 1)
        self.l_dom_cycle = QDoubleSpinBox(dom)
        self.l_dom_cycle.setDecimals(0)
        self.l_dom_cycle.setRange(1, 1e9)
        self.l_dom_cycle.setValue(1)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Output cycle"))
        crow.addWidget(self.l_dom_cycle)
        top.addLayout(crow)
        dl.addLayout(top)
        self.l_dom_type = QComboBox(dom)
        self.l_dom_type.addItems(["By parts", "Entire domain"])
        _pair(dl, "Output type", self.l_dom_type)
        ov = QGroupBox("Output variables", dom)
        ovl = QHBoxLayout(ov)
        self.l_dom_table = QTableWidget(0, 2, ov)
        self.l_dom_table.setHorizontalHeaderLabels(["Variable", "Output"])
        self.l_dom_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.l_dom_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.l_dom_table.setSelectionMode(QTableWidget.SingleSelection)
        self.l_dom_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ovl.addWidget(self.l_dom_table, 1)
        side = QVBoxLayout()
        btn_o = QPushButton("Output", ov)
        btn_c = QPushButton("Cancel", ov)
        btn_o.clicked.connect(
            lambda: self._toggle_sel(self.l_dom_table, self._dom_sel,
                                     self._DOMAIN_VARS, True))
        btn_c.clicked.connect(
            lambda: self._toggle_sel(self.l_dom_table, self._dom_sel,
                                     self._DOMAIN_VARS, False))
        side.addWidget(btn_o)
        side.addWidget(btn_c)
        side.addStretch(1)
        ovl.addLayout(side)
        dl.addWidget(ov, 1)
        return dom

    def _build_specified_region(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs average/minimum/maximum value of variables in the "
            "specified region to L file.", page))
        typ = QGroupBox("Output type of each variable", page)
        tl = QVBoxLayout(typ)
        row = QHBoxLayout()
        col = QVBoxLayout()
        self.rgn_avg = QCheckBox("Average", typ)
        self.rgn_avg.setChecked(True)
        self.rgn_minmax = QCheckBox("Minimum/maximum", typ)
        self.rgn_minmax.setChecked(True)
        col.addWidget(self.rgn_avg)
        col.addWidget(self.rgn_minmax)
        row.addLayout(col)
        stats = QGroupBox("Statistics", typ)
        sl = QVBoxLayout(stats)
        self.rgn_std = QCheckBox("Standard deviation", stats)
        self.rgn_var = QCheckBox("Variance", stats)
        self.rgn_ui = QCheckBox("Uniformity index", stats)
        for c in (self.rgn_std, self.rgn_var, self.rgn_ui):
            sl.addWidget(c)
        row.addWidget(stats)
        row.addStretch(1)
        self.rgn_cycle = QDoubleSpinBox(typ)
        self.rgn_cycle.setDecimals(0)
        self.rgn_cycle.setRange(1, 1e9)
        self.rgn_cycle.setValue(1)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Output cycle"))
        crow.addWidget(self.rgn_cycle)
        row.addLayout(crow)
        tl.addLayout(row)
        lay.addWidget(typ)

        self.rgn_vol_table, self.rgn_vol_var = self._region_var_block(
            lay, page, "Specified region (volume)", self._rgn_vol,
            self._REGION_VARS, self._vol_region_names)
        self.rgn_face_table, self.rgn_face_var = self._region_var_block(
            lay, page, "Specified region (face)", self._rgn_face,
            self._REGION_VARS, self._face_region_names)
        return page

    def _region_var_block(self, parent_lay, page, title, store, variables,
                          names_fn):
        box = QGroupBox(title, page)
        bl = QVBoxLayout(box)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", box))
        disp = QComboBox(box)
        disp.addItems(["All regions", "Parts"])
        drow.addWidget(disp, 1)
        drow.addStretch(1)
        bl.addLayout(drow)
        body = QHBoxLayout()
        table = QTableWidget(0, 3, box)
        table.setHorizontalHeaderLabels(["Region name", "*", "Variable"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(table, 1)
        right = QVBoxLayout()
        btn_sel = QPushButton("Select", box)
        var = QComboBox(box)
        var.addItems(variables)
        _pair(right, "Variable name", var)
        btn_add = QPushButton("Add", box)
        btn_cancel = QPushButton("Cancel", box)

        def _fill():
            table.setRowCount(0)
            for i, name in enumerate(names_fn()):
                table.insertRow(i)
                table.setItem(i, 0, QTableWidgetItem(name))
                table.setItem(i, 1, QTableWidgetItem(""))
                table.setItem(i, 2, QTableWidgetItem(store.get(name, "")))

        def _sel_name():
            rows = table.selectionModel().selectedRows()
            if not rows:
                return ""
            it = table.item(rows[0].row(), 0)
            return it.text() if it else ""

        def _add():
            n = _sel_name()
            if not n:
                QMessageBox.information(
                    self, title, "Select a region from the list.")
                return
            store[n] = var.currentText()
            _fill()

        def _cancel():
            n = _sel_name()
            if n in store:
                del store[n]
                _fill()

        btn_add.clicked.connect(_add)
        btn_cancel.clicked.connect(_cancel)
        btn_sel.clicked.connect(
            lambda: QMessageBox.information(
                self, "Select",
                "Select a region in the Draw window (phase-1: use list)."))
        right.addWidget(btn_sel)
        right.addWidget(btn_add)
        right.addWidget(btn_cancel)
        right.addStretch(1)
        body.addLayout(right)
        bl.addLayout(body, 1)
        tip = QLabel("Select from list > Add/Cancel", box)
        tip.setStyleSheet("color: #555;")
        bl.addWidget(tip)
        parent_lay.addWidget(box, 1)
        table._fill = _fill  # type: ignore[attr-defined]
        _fill()
        return table, var

    def _vol_region_names(self) -> list[str]:
        return [p.name for p in self.model.parts() if p.name]

    def _face_region_names(self) -> list[str]:
        names = [n for n, _ in self.model.domain_faces()]
        for p in self.model.parts():
            if p.name and (p.kind or "").lower() in (
                    "panel", "partface", "face"):
                names.append(p.name)
            elif p.name and "face" in (p.attribute or "").lower():
                names.append(p.name)
        return names

    def _build_flux_balance(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs flux balance information to an L file.", page))
        self.flux_on = QCheckBox("Output flux balance", page)
        lay.addWidget(self.flux_on)
        crow = QHBoxLayout()
        crow.addStretch(1)
        self.flux_cycle = QDoubleSpinBox(page)
        self.flux_cycle.setDecimals(0)
        self.flux_cycle.setRange(1, 1e9)
        self.flux_cycle.setValue(1)
        crow.addWidget(QLabel("Output cycle"))
        crow.addWidget(self.flux_cycle)
        lay.addLayout(crow)
        box = QGroupBox("Target", page)
        bl = QVBoxLayout(box)
        self.flux_open = QCheckBox("Openings / domain boundary faces", box)
        self.flux_parts = QCheckBox("Parts", box)
        bl.addWidget(self.flux_open)
        bl.addWidget(self.flux_parts)
        lay.addWidget(box)
        lay.addStretch(1)
        return page

    def _build_passage(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs the flow rate and heat flux passing through the "
            "specified region, to an L file.", page))
        top = QHBoxLayout()
        self.pass_on = QCheckBox(
            "Output the amount of the specified variable", page)
        self.pass_on.setChecked(True)
        top.addWidget(self.pass_on)
        top.addStretch(1)
        self.pass_cycle = QDoubleSpinBox(page)
        self.pass_cycle.setDecimals(0)
        self.pass_cycle.setRange(1, 1e9)
        self.pass_cycle.setValue(1)
        top.addWidget(QLabel("Output cycle"))
        top.addWidget(self.pass_cycle)
        lay.addLayout(top)

        mars = QGroupBox("Output Passage/MARS Method (SURFLIST)", page)
        mfl = QFormLayout(mars)
        self.mars_cycle = QSpinBox(mars)
        self.mars_cycle.setRange(0, 1000000000)
        self.mars_cycle.setValue(1)
        mfl.addRow("Output cycle (0=off)", self.mars_cycle)
        self.mars_mvof = QComboBox(mars)
        self.mars_mvof.addItems(["VOF1", "VOF2"])
        self.mars_mvof.setCurrentIndex(1)
        mfl.addRow("Fluid", self.mars_mvof)
        self.mars_region = QLineEdit(mars)
        mfl.addRow("Region name", self.mars_region)
        btn_mars = QPushButton("Add MARS passage", mars)
        btn_mars.clicked.connect(self._mars_add)
        mfl.addRow(btn_mars)
        self.mars_table = QTableWidget(0, 2, mars)
        self.mars_table.setHorizontalHeaderLabels(["Region", "MVOF"])
        self.mars_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.mars_table.setEditTriggers(QTableWidget.NoEditTriggers)
        mfl.addRow(self.mars_table)
        lay.addWidget(mars)

        box = QGroupBox("Specified region", page)
        bl = QVBoxLayout(box)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", box))
        disp = QComboBox(box)
        disp.addItems(["All regions", "Parts"])
        drow.addWidget(disp, 1)
        bl.addLayout(drow)
        body = QHBoxLayout()
        self.pass_table = QTableWidget(0, 4, box)
        self.pass_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Variable", "Target"])
        self.pass_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.pass_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pass_table.setSelectionMode(QTableWidget.SingleSelection)
        self.pass_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.pass_table, 1)
        right = QVBoxLayout()
        self.pass_var = QComboBox(box)
        self.pass_var.addItems(self._PASSAGE_VARS)
        _pair(right, "Variable name", self.pass_var)
        tgt = QGroupBox("Target (Flow direction)", box)
        tgl = QVBoxLayout(tgt)
        self.pass_total = QCheckBox("Total", tgt)
        self.pass_fwd = QCheckBox("Forward", tgt)
        self.pass_bwd = QCheckBox("Backward", tgt)
        self.pass_total.setChecked(True)
        for c in (self.pass_total, self.pass_fwd, self.pass_bwd):
            tgl.addWidget(c)
        right.addWidget(tgt)
        btn_add = QPushButton("Add", box)
        btn_mod = QPushButton("Modify", box)
        btn_cancel = QPushButton("Cancel", box)
        btn_add.clicked.connect(lambda: self._passage_set(False))
        btn_mod.clicked.connect(lambda: self._passage_set(True))
        btn_cancel.clicked.connect(self._passage_cancel)
        for b in (btn_add, btn_mod, btn_cancel):
            right.addWidget(b)
        right.addStretch(1)
        body.addLayout(right)
        bl.addLayout(body, 1)
        tip = QLabel("Select from list > Add/Modify/Cancel", box)
        tip.setStyleSheet("color: #555;")
        bl.addWidget(tip)
        bl.addWidget(_note(
            "Note) As for computational domain face and face regions, "
            "it is valid only for faces with inflow and outflow "
            "conditions.", box))
        lay.addWidget(box, 1)
        area = QGroupBox("Output area", page)
        al = QVBoxLayout(area)
        self.pass_area = QCheckBox(
            "Area is counted except a face whose velocity is zero", area)
        al.addWidget(self.pass_area)
        lay.addWidget(area)
        self._passage_fill()
        return page

    def _passage_fill(self) -> None:
        self.pass_table.setRowCount(0)
        names = self._face_region_names()
        for i, name in enumerate(names):
            self.pass_table.insertRow(i)
            self.pass_table.setItem(i, 0, QTableWidgetItem(name))
            self.pass_table.setItem(i, 1, QTableWidgetItem(""))
            val = self._passage.get(name, "")
            var, tgt = (val.split("|", 1) + [""])[:2] if val else ("", "")
            self.pass_table.setItem(i, 2, QTableWidgetItem(var))
            self.pass_table.setItem(i, 3, QTableWidgetItem(tgt))

    def _passage_selected(self) -> str:
        rows = self.pass_table.selectionModel().selectedRows()
        if not rows:
            return ""
        it = self.pass_table.item(rows[0].row(), 0)
        return it.text() if it else ""

    def _passage_set(self, modify: bool) -> None:
        name = self._passage_selected()
        if not name:
            QMessageBox.information(
                self, "Specified Region (Passage)",
                "Select a region from the list.")
            return
        if modify and name not in self._passage:
            QMessageBox.information(
                self, "Modify", "No setting exists. Use Add.")
            return
        if not modify and name in self._passage:
            QMessageBox.information(
                self, "Add", "Already set. Use Modify.")
            return
        dirs = []
        if self.pass_total.isChecked():
            dirs.append("Total")
        if self.pass_fwd.isChecked():
            dirs.append("Forward")
        if self.pass_bwd.isChecked():
            dirs.append("Backward")
        self._passage[name] = (
            f"{self.pass_var.currentText()}|{'+'.join(dirs) or 'Total'}")
        self._passage_fill()

    def _passage_cancel(self) -> None:
        name = self._passage_selected()
        if name in self._passage:
            del self._passage[name]
            self._passage_fill()

    def _build_pressure_region(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs pressure information of the specified region "
            "to an L file.", page))
        top = QHBoxLayout()
        self.pres_on = QCheckBox("Output pressure of specified region", page)
        self.pres_on.setChecked(True)
        top.addWidget(self.pres_on)
        top.addStretch(1)
        self.pres_cycle = QDoubleSpinBox(page)
        self.pres_cycle.setDecimals(0)
        self.pres_cycle.setRange(1, 1e9)
        self.pres_cycle.setValue(1)
        top.addWidget(QLabel("Output cycle"))
        top.addWidget(self.pres_cycle)
        lay.addLayout(top)
        self.pres_table, self.pres_var = self._region_var_block(
            lay, page, "Specified region", self._pressure,
            self._PRESSURE_VARS, self._face_region_names)
        return page

    def _build_ncoz(self) -> QWidget:
        """Standardized Concentration in Living Space (C4, NCOZ_OUTPUT).

        The L-file card layout has no corpus evidence yet — the enable/
        cycle persist to analysis_set; emission is probe-deferred.
        """
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Refers a standardized concentration in living space "
            "environment (L file).", page))
        top = QHBoxLayout()
        self.ncoz_on = QCheckBox(
            "Output the standardized concentration", page)
        self.ncoz_on.setChecked(True)
        top.addWidget(self.ncoz_on)
        top.addStretch(1)
        self.ncoz_cycle = QDoubleSpinBox(page)
        self.ncoz_cycle.setDecimals(0)
        self.ncoz_cycle.setRange(1, 1e9)
        self.ncoz_cycle.setValue(1)
        top.addWidget(QLabel("Output cycle"))
        top.addWidget(self.ncoz_cycle)
        lay.addLayout(top)
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Occupied zone region", page))
        self.ncoz_rgn = QLineEdit(page)
        rrow.addWidget(self.ncoz_rgn, 1)
        lay.addLayout(rrow)
        lay.addStretch(1)
        return page

    def _build_hbal_part(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Output the heat balance information per part unit to "
            "an L file.", page))
        row = QHBoxLayout()
        self.hbal_part_on = QCheckBox(
            "Output heat balance per part unit", page)
        row.addWidget(self.hbal_part_on)
        self.hbal_part_interval = QPushButton("Output Interval...", page)
        row.addWidget(self.hbal_part_interval)
        row.addWidget(QLabel("Last cycle only"))
        row.addStretch(1)
        lay.addLayout(row)
        self.hbal_line_tag = QCheckBox("Line tag output", page)
        self.hbal_zero = QCheckBox("Output even if zero value", page)
        lay.addWidget(self.hbal_line_tag)
        lay.addWidget(self.hbal_zero)
        box = QGroupBox("Output parts", page)
        bl = QHBoxLayout(box)
        self.hbal_part_table = QTableWidget(0, 3, box)
        self.hbal_part_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Output"])
        self.hbal_part_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.hbal_part_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hbal_part_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bl.addWidget(self.hbal_part_table, 1)
        side = QVBoxLayout()
        btn_o = QPushButton("Output", box)
        btn_c = QPushButton("Cancel", box)
        btn_o.clicked.connect(
            lambda: self._toggle_name_sel(
                self.hbal_part_table, self._hbal_part_sel, True))
        btn_c.clicked.connect(
            lambda: self._toggle_name_sel(
                self.hbal_part_table, self._hbal_part_sel, False))
        side.addWidget(btn_o)
        side.addWidget(btn_c)
        side.addStretch(1)
        bl.addLayout(side)
        lay.addWidget(box, 1)
        self._fill_name_table(self.hbal_part_table, self._vol_region_names(),
                              self._hbal_part_sel)
        return page

    def _build_hbal_pair(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Output the heat balance information between parts to "
            "the L file.", page))
        self.hbal_pair_on = QCheckBox(
            "Output heat balance between parts", page)
        lay.addWidget(self.hbal_pair_on)
        box = QGroupBox("List of region pairs", page)
        bl = QHBoxLayout(box)
        self.hbal_pair_table = QTableWidget(0, 4, box)
        self.hbal_pair_table.setHorizontalHeaderLabels(
            ["Region pair", "Part1", "Part2", "Output"])
        self.hbal_pair_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.hbal_pair_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hbal_pair_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bl.addWidget(self.hbal_pair_table, 1)
        side = QVBoxLayout()
        btn_o = QPushButton("Output", box)
        btn_c = QPushButton("Cancel", box)
        btn_new = QPushButton("New...", box)
        btn_o.clicked.connect(self._hbal_pair_output)
        btn_c.clicked.connect(self._hbal_pair_cancel)
        btn_new.clicked.connect(
            lambda: QMessageBox.information(
                self, "New",
                "Register a region pair in Thermal Boundary "
                "(Between Parts), then select it here."))
        for b in (btn_o, btn_c, btn_new):
            side.addWidget(b)
        side.addStretch(1)
        bl.addLayout(side)
        lay.addWidget(box, 1)
        self._hbal_pair_fill()
        return page

    def _hbal_pair_fill(self) -> None:
        self.hbal_pair_table.setRowCount(0)
        for i, (name, p1, p2) in enumerate(self.model.region_pairs()):
            self.hbal_pair_table.insertRow(i)
            self.hbal_pair_table.setItem(i, 0, QTableWidgetItem(name))
            self.hbal_pair_table.setItem(i, 1, QTableWidgetItem(p1))
            self.hbal_pair_table.setItem(i, 2, QTableWidgetItem(p2))
            self.hbal_pair_table.setItem(
                i, 3, QTableWidgetItem(
                    "Selected" if name in self._hbal_pair_sel else ""))

    def _hbal_pair_output(self) -> None:
        rows = self.hbal_pair_table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.hbal_pair_table.item(rows[0].row(), 0).text()
        self._hbal_pair_sel.add(name)
        self._hbal_pair_fill()

    def _hbal_pair_cancel(self) -> None:
        rows = self.hbal_pair_table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.hbal_pair_table.item(rows[0].row(), 0).text()
        self._hbal_pair_sel.discard(name)
        self._hbal_pair_fill()

    def _build_aent_region(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Outputs the amount of heat transfer through a specified "
            "region to L file.", page))
        row = QHBoxLayout()
        self.aent_on = QCheckBox("Output the amount of heat transfer", page)
        self.aent_on.setChecked(True)
        row.addWidget(self.aent_on)
        self.aent_interval = QPushButton("Output Interval...", page)
        row.addWidget(self.aent_interval)
        row.addWidget(QLabel("Last cycle only"))
        row.addStretch(1)
        lay.addLayout(row)
        box = QGroupBox("Output parts", page)
        bl = QVBoxLayout(box)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", box))
        disp = QComboBox(box)
        disp.addItems(["All regions", "Parts"])
        drow.addWidget(disp, 1)
        bl.addLayout(drow)
        body = QHBoxLayout()
        self.aent_table = QTableWidget(0, 4, box)
        self.aent_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Region type", "Output"])
        self.aent_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.aent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.aent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.aent_table, 1)
        side = QVBoxLayout()
        btn_o = QPushButton("Output", box)
        btn_c = QPushButton("Cancel", box)
        btn_o.clicked.connect(
            lambda: self._toggle_name_sel(
                self.aent_table, self._aent_sel, True, col=3))
        btn_c.clicked.connect(
            lambda: self._toggle_name_sel(
                self.aent_table, self._aent_sel, False, col=3))
        side.addWidget(btn_o)
        side.addWidget(btn_c)
        side.addStretch(1)
        body.addLayout(side)
        bl.addLayout(body, 1)
        tip = QLabel("Select from list > Output/Cancel", box)
        tip.setStyleSheet("color: #555;")
        bl.addWidget(tip)
        bl.addWidget(_note(
            "Note) Only regions with heat transfer conditions are listed.",
            box))
        lay.addWidget(box, 1)
        self._aent_fill()
        return page

    def _aent_fill(self) -> None:
        self.aent_table.setRowCount(0)
        for i, name in enumerate(self._face_region_names()):
            self.aent_table.insertRow(i)
            self.aent_table.setItem(i, 0, QTableWidgetItem(name))
            self.aent_table.setItem(i, 1, QTableWidgetItem(""))
            self.aent_table.setItem(i, 2, QTableWidgetItem("PartFace"))
            self.aent_table.setItem(
                i, 3, QTableWidgetItem(
                    "Selected" if name in self._aent_sel else ""))

    def _build_cycle_warn(self) -> QWidget:
        warn = QWidget()
        wl = QVBoxLayout(warn)
        wl.addWidget(_note("Controls information output to L file.", warn))
        g1 = QGroupBox("Output information", warn)
        g1l = QVBoxLayout(g1)
        self.l_warn = QCheckBox("Output warning/error message", g1)
        self.l_warn.setChecked(True)
        self.l_cmd = QCheckBox("Output input command", g1)
        g1l.addWidget(self.l_warn)
        g1l.addWidget(self.l_cmd)
        wl.addWidget(g1)
        g2 = QGroupBox("Cycle/Matrix calculation information", warn)
        g2l = QVBoxLayout(g2)
        self.l_mode1 = QRadioButton(
            "Output cycle information every cycle. Do not output "
            "matrix calculation information.", g2)
        self.l_mode2 = QRadioButton(
            "Output cycle information every cycle and information of "
            "matrix solver every specified cycle.", g2)
        self.l_mode3 = QRadioButton(
            "Output cycle information and information of matrix "
            "solver every specified cycle.", g2)
        self.l_mode2.setChecked(True)
        self.l_cycle2 = QDoubleSpinBox(g2)
        self.l_cycle2.setDecimals(0)
        self.l_cycle2.setRange(1, 1e9)
        self.l_cycle2.setValue(1)
        self.l_cycle3 = QDoubleSpinBox(g2)
        self.l_cycle3.setDecimals(0)
        self.l_cycle3.setRange(1, 1e9)
        self.l_cycle3.setValue(1)
        for r in (self.l_mode1, self.l_mode2, self.l_mode3):
            g2l.addWidget(r)
        row2 = QHBoxLayout()
        row2.addSpacing(24)
        row2.addWidget(QLabel("Output cycle"))
        row2.addWidget(self.l_cycle2)
        row2.addStretch(1)
        g2l.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addSpacing(24)
        row3.addWidget(QLabel("Output cycle"))
        row3.addWidget(self.l_cycle3)
        row3.addStretch(1)
        g2l.addLayout(row3)
        wl.addWidget(g2)
        wl.addStretch(1)
        return warn

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _toggle_sel(table, selected: set, names, add: bool) -> None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        if add:
            selected.add(name)
        else:
            selected.discard(name)
        _fill_var_table(table, list(names), selected)

    @staticmethod
    def _fill_name_table(table, names: list[str], selected: set,
                         *, col: int = 2) -> None:
        table.setRowCount(0)
        for i, name in enumerate(names):
            table.insertRow(i)
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem(""))
            for c in range(2, table.columnCount()):
                text = ("Selected" if name in selected and c == col else "")
                table.setItem(i, c, QTableWidgetItem(text))

    def _toggle_name_sel(self, table, selected: set, add: bool,
                         col: int = 2) -> None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        if add:
            selected.add(name)
        else:
            selected.discard(name)
        # refresh Output column only
        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if it is None:
                continue
            table.setItem(
                r, col, QTableWidgetItem(
                    "Selected" if it.text() in selected else ""))

    @staticmethod
    def _dump_map(store: dict) -> str:
        return ";".join(f"{k}|{v}" for k, v in store.items())

    @staticmethod
    def _load_map(raw: str) -> dict:
        out = {}
        if not raw:
            return out
        for rec in raw.split(";"):
            if "|" in rec:
                k, v = rec.split("|", 1)
                out[k.strip()] = v.strip()
        return out

    def _mars_add(self) -> None:
        region = self.mars_region.text().strip()
        if not region:
            return
        mvof = self.mars_mvof.currentIndex() + 1
        row = self.mars_table.rowCount()
        self.mars_table.insertRow(row)
        self.mars_table.setItem(row, 0, QTableWidgetItem(region))
        self.mars_table.setItem(row, 1, QTableWidgetItem(str(mvof)))
        self.mars_region.clear()

    def _mars_records(self) -> str:
        out = []
        for r in range(self.mars_table.rowCount()):
            it0 = self.mars_table.item(r, 0)
            it1 = self.mars_table.item(r, 1)
            if it0 and it1 and it0.text():
                out.append(f"{it0.text()}|{it1.text()}")
        return ";".join(out)

    def _load(self) -> None:
        self.mars_cycle.setValue(int(float(
            self.model.analysis_set_value("lfile_surflist_cycle", "1")
            or 1)))
        for rec in self.model.analysis_set_value(
                "lfile_surflist", "").split(";"):
            bits = rec.split("|")
            if len(bits) == 2 and bits[0]:
                r = self.mars_table.rowCount()
                self.mars_table.insertRow(r)
                self.mars_table.setItem(r, 0, QTableWidgetItem(bits[0]))
                self.mars_table.setItem(r, 1, QTableWidgetItem(bits[1]))
        self.l_warn.setChecked(
            self.model.analysis_set_value("lfile_warn", "T").upper()
            not in ("F", "0", "FALSE"))
        self.l_cmd.setChecked(
            self.model.analysis_set_value("lfile_cmd", "F").upper()
            in ("T", "1", "TRUE"))
        mode = self.model.analysis_set_value("lfile_cycle_mode", "2")
        {"1": self.l_mode1, "2": self.l_mode2, "3": self.l_mode3
         }.get(mode.strip(), self.l_mode2).setChecked(True)
        try:
            self.l_cycle2.setValue(float(
                self.model.analysis_set_value("lfile_matrix_cycle", "1")))
            self.l_cycle3.setValue(float(
                self.model.analysis_set_value("lfile_both_cycle", "1")))
            self.l_dom_cycle.setValue(float(
                self.model.analysis_set_value("lfile_domain_cycle", "1")))
            self.rgn_cycle.setValue(float(
                self.model.analysis_set_value("lfile_rgn_cycle", "1")))
            self.pass_cycle.setValue(float(
                self.model.analysis_set_value("lfile_passage_cycle", "1")))
            self.pres_cycle.setValue(float(
                self.model.analysis_set_value("lfile_pressure_cycle", "1")))
            self.flux_cycle.setValue(float(
                self.model.analysis_set_value("lfile_flux_cycle", "1")))
            self.ncoz_cycle.setValue(float(
                self.model.analysis_set_value("lfile_ncoz_cycle", "1")))
        except ValueError:
            pass
        self.ncoz_rgn.setText(
            self.model.analysis_set_value("lfile_ncoz_rgn", ""))
        self.ncoz_on.setChecked(
            self.model.analysis_set_value("lfile_ncoz", "T").upper()
            not in ("F", "0", "FALSE"))
        raw = self.model.analysis_set_value("lfile_domain_vars", "")
        if raw:
            self._dom_sel = {x for x in raw.split("|") if x}
        self._rgn_vol = self._load_map(
            self.model.analysis_set_value("lfile_rgn_vol", ""))
        self._rgn_face = self._load_map(
            self.model.analysis_set_value("lfile_rgn_face", ""))
        self._passage = self._load_map(
            self.model.analysis_set_value("lfile_passage", ""))
        self._pressure = self._load_map(
            self.model.analysis_set_value("lfile_pressure_rgn", ""))
        self._aent_sel = {
            x for x in self.model.analysis_set_value(
                "lfile_aent_rgn", "").split("|") if x}
        self._hbal_part_sel = {
            x for x in self.model.analysis_set_value(
                "lfile_hbal_part_sel", "").split("|") if x}
        self._hbal_pair_sel = {
            x for x in self.model.analysis_set_value(
                "lfile_hbal_pair_sel", "").split("|") if x}
        # refresh dynamic tables
        if hasattr(self.rgn_vol_table, "_fill"):
            self.rgn_vol_table._fill()
        if hasattr(self.rgn_face_table, "_fill"):
            self.rgn_face_table._fill()
        self._passage_fill()
        if hasattr(self.pres_table, "_fill"):
            self.pres_table._fill()
        self._aent_fill()
        self._fill_name_table(
            self.hbal_part_table, self._vol_region_names(),
            self._hbal_part_sel)
        self._hbal_pair_fill()

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "lfile_warn", "T" if self.l_warn.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_cmd", "T" if self.l_cmd.isChecked() else "F")
        mode = "2"
        if self.l_mode1.isChecked():
            mode = "1"
        elif self.l_mode3.isChecked():
            mode = "3"
        self.model.set_analysis_set_value("lfile_cycle_mode", mode)
        self.model.set_analysis_set_value(
            "lfile_matrix_cycle", f"{int(self.l_cycle2.value())}")
        self.model.set_analysis_set_value(
            "lfile_both_cycle", f"{int(self.l_cycle3.value())}")
        self.model.set_analysis_set_value(
            "lfile_domain_cycle", f"{int(self.l_dom_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_domain_avg",
            "T" if self.l_avg.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_domain_minmax",
            "T" if self.l_minmax.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_domain_type",
            "parts" if self.l_dom_type.currentIndex() == 0 else "entire")
        self.model.set_analysis_set_value(
            "lfile_domain_vars", "|".join(sorted(self._dom_sel)))
        self.model.set_analysis_set_value(
            "lfile_rgn_cycle", f"{int(self.rgn_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_rgn_vol", self._dump_map(self._rgn_vol))
        self.model.set_analysis_set_value(
            "lfile_rgn_face", self._dump_map(self._rgn_face))
        self.model.set_analysis_set_value(
            "lfile_flux_on", "T" if self.flux_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_flux_cycle", f"{int(self.flux_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_passage", self._dump_map(self._passage))
        self.model.set_analysis_set_value(
            "lfile_passage_cycle", f"{int(self.pass_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_pressure_rgn", self._dump_map(self._pressure))
        self.model.set_analysis_set_value(
            "lfile_pressure_cycle", f"{int(self.pres_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_ncoz", "T" if self.ncoz_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_ncoz_cycle", f"{int(self.ncoz_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_surflist_cycle", f"{int(self.mars_cycle.value())}")
        self.model.set_analysis_set_value(
            "lfile_surflist", self._mars_records())
        self.model.set_analysis_set_value(
            "lfile_ncoz_rgn", self.ncoz_rgn.text().strip())
        self.model.set_analysis_set_value(
            "lfile_hbal_part_on",
            "T" if self.hbal_part_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_hbal_part_sel", "|".join(sorted(self._hbal_part_sel)))
        self.model.set_analysis_set_value(
            "lfile_hbal_pair_on",
            "T" if self.hbal_pair_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_hbal_pair_sel", "|".join(sorted(self._hbal_pair_sel)))
        self.model.set_analysis_set_value(
            "lfile_aent_on", "T" if self.aent_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "lfile_aent_rgn", "|".join(sorted(self._aent_sel)))
        self.model.set_analysis_set_value(
            "lfile_residual",
            "T" if self.l_warn.isChecked() else "F")


class _CwFilePage(QWidget if _HAS_GUI else object):
    """File Specification — STpre Condition Wizard tabs (File Name … Mapping)."""

    _TAB_ORDER = (
        "File Name",
        "Option (Field File)",
        "Option (Time Series)",
        "Option (Restart)",
        "Maximum/Minimum Temperature",
        "Partial FLD",
        "Parts' Internal Variables",
        "CSV Mapping",
        "Mapping (Coordinate)",
        "Mapping (Individual Correction)",
        "Mapping (Variable)",
    )

    _MAP_VARS = (
        ("Temperature", "TEMP", "SURT / MRT / SMRT"),
        ("External temperature", "SURT", "TEMP / MRT / SMRT / ZSFT"),
        ("Mean radiation temperature", "MRT", "TEMP / SURT / SMRT"),
        ("Heat transfer coefficient", "HTRC", "ZHTR"),
        ("Heat generation", "HEAT", "—"),
    )

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._ot_sel: set[str] = set()
        self._ocsv_sel: set[str] = set()
        self._partial: list[dict] = []
        self._csv_maps: list[dict] = []
        self._map_corr: list[dict] = []
        self._map_var_sel: set[str] = set()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        builders = {
            "File Name": self._build_file_name,
            "Option (Field File)": self._build_opt_field,
            "Option (Time Series)": self._build_opt_series,
            "Option (Restart)": self._build_opt_restart,
            "Maximum/Minimum Temperature": self._build_ot,
            "Partial FLD": self._build_partial,
            "Parts' Internal Variables": self._build_ocsv,
            "CSV Mapping": self._build_csv,
            "Mapping (Coordinate)": self._build_map_coord,
            "Mapping (Individual Correction)": self._build_map_indiv,
            "Mapping (Variable)": self._build_map_var,
        }
        for title in self._TAB_ORDER:
            self.tabs.addTab(builders[title](), title)
        lay.addWidget(self.tabs, 1)
        self._load()

    def _browse(self, edit: QLineEdit, *, title: str, filt: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title, edit.text(), filt)
        if path:
            edit.setText(path)

    def _browse_save(self, edit: QLineEdit, *, title: str, filt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, title, edit.text(), filt)
        if path:
            edit.setText(path)

    def _file_row(self, lay, label: str, edit: QLineEdit,
                  browse=None) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit, 1)
        if browse is not None:
            btn = QPushButton("...")
            btn.setFixedWidth(32)
            btn.clicked.connect(browse)
            row.addWidget(btn)
        lay.addLayout(row)

    def _part_names(self) -> list[str]:
        return [p.name for p in self.model.parts() if p.name]

    def _fill_sel_table(self, table: QTableWidget, names: list[str],
                        selected: set[str], col_out: int = 2) -> None:
        table.blockSignals(True)
        table.setRowCount(0)
        for i, name in enumerate(names):
            table.insertRow(i)
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem(""))
            mark = "Selected" if name in selected else ""
            table.setItem(i, col_out, QTableWidgetItem(mark))
        table.blockSignals(False)

    def _toggle_sel(self, table: QTableWidget, selected: set[str],
                    on: bool, col: int = 2) -> None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        if on:
            selected.add(name)
        else:
            selected.discard(name)
        item = table.item(rows[0].row(), col)
        if item is not None:
            item.setText("Selected" if on else "")

    def _build_file_name(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets output file name and comments for this solution.", page))

        g1 = QGroupBox("Generic name for all output file", page)
        g1l = QVBoxLayout(g1)
        self.sol_name = QLineEdit(g1)
        row = QHBoxLayout()
        row.addWidget(QLabel("(Solution name)"))
        row.addWidget(self.sol_name, 1)
        auto = QPushButton("Auto-Configured", g1)
        auto.clicked.connect(self._auto_configure)
        row.addWidget(auto)
        g1l.addLayout(row)
        lay.addWidget(g1)

        g2 = QGroupBox("File name", page)
        g2l = QVBoxLayout(g2)
        self.f_fld = QLineEdit(g2)
        self.f_tm = QLineEdit(g2)
        self.f_ri = QLineEdit(g2)
        self.f_ro = QLineEdit(g2)
        self.f_ot = QLineEdit(g2)
        self.f_hpt = QLineEdit(g2)
        self.f_vf = QLineEdit(g2)
        self.f_sufl = QLineEdit(g2)
        self.f_map = QLineEdit(g2)
        self.f_ocsv = QLineEdit(g2)
        self.f_pcl = QLineEdit(g2)
        self._file_row(g2l, "Generic name of Field file (Output)", self.f_fld)
        self._file_row(g2l, "Time-series file (Output)", self.f_tm)
        self._file_row(
            g2l, "Restart (R) file (Input)", self.f_ri,
            browse=lambda: self._browse(
                self.f_ri, title="Restart (R) file (Input)",
                filt="Restart (*.r *.R);;All (*.*)"))
        self._file_row(g2l, "Restart (R) file (Output)", self.f_ro)
        self._file_row(
            g2l, "Maximum/Minimum temperature (OT) file (Output)", self.f_ot,
            browse=lambda: self._browse_save(
                self.f_ot, title="OT file", filt="OT (*.ot);;All (*.*)"))
        self._file_row(
            g2l, "Heat path (HPT) file (Output)", self.f_hpt,
            browse=lambda: self._browse_save(
                self.f_hpt, title="HPT file", filt="HPT (*.hpt);;All (*.*)"))
        vf_row = QHBoxLayout()
        self.vf_on = QCheckBox(
            "Radiation view factor (VF) file (Output/Input)", g2)
        self.vf_on.setChecked(True)
        vf_row.addWidget(self.vf_on)
        vf_row.addWidget(self.f_vf, 1)
        vf_btn = QPushButton("...", g2)
        vf_btn.setFixedWidth(32)
        vf_btn.clicked.connect(lambda: self._browse_save(
            self.f_vf, title="VF file", filt="VF (*.vf);;All (*.*)"))
        vf_row.addWidget(vf_btn)
        g2l.addLayout(vf_row)
        self.vf_on.toggled.connect(self.f_vf.setEnabled)
        self.vf_on.toggled.connect(vf_btn.setEnabled)
        self._file_row(
            g2l, "Free surface location file (Output)", self.f_sufl,
            browse=lambda: self._browse_save(
                self.f_sufl, title="Free surface file",
                filt="CSV (*.csv);;All (*.*)"))
        self._file_row(
            g2l, "Field file for mapping (Input)", self.f_map,
            browse=lambda: self._browse(
                self.f_map, title="FLD file for mapping",
                filt="FLD (*.fld *.FLD);;All (*.*)"))
        self._file_row(
            g2l,
            "Generic name of Parts' internal variable (OCSV) file (Output)",
            self.f_ocsv)
        self._file_row(g2l, "Pathline (PCL) file", self.f_pcl)
        lay.addWidget(g2)

        g3 = QGroupBox("Comments", page)
        g3l = QVBoxLayout(g3)
        self.f_comment = QLineEdit(g3)
        g3l.addWidget(self.f_comment)
        lay.addWidget(g3)
        lay.addStretch(1)
        return page

    def _auto_configure(self) -> None:
        base = self.sol_name.text().strip() or "project"
        self.f_fld.setText(base)
        self.f_tm.setText(f"{base}_tm.csv")
        self.f_ro.setText(f"{base}.r")
        self.f_ot.setText(f"{base}.ot")
        self.f_hpt.setText(f"{base}.hpt")
        if self.vf_on.isChecked():
            self.f_vf.setText(f"{base}.vf")
        self.f_sufl.setText(f"{base}_sufl_tm.csv")
        self.f_ocsv.setText(base)
        self.f_pcl.setText(f"{base}.pcl")
        self.model.set_file_value("s", f"{base}.s")

    def _build_opt_field(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Set the cycle/time interval at which a field file is output.",
            page))
        fmt = QGroupBox("Output file format", page)
        fl = QVBoxLayout(fmt)
        self.out_fld = QCheckBox("Default (FLD file)", fmt)
        self.out_fld.setChecked(True)
        self.out_p = QCheckBox("P file", fmt)
        self.out_ifld = QCheckBox("iFLD file", fmt)
        self.out_s_in_fld = QCheckBox(
            "Output the S file contents to FLD file", fmt)
        self.out_s_in_fld.setChecked(True)
        self.out_single = QCheckBox("Single precision FLD file", fmt)
        for w in (self.out_fld, self.out_p, self.out_ifld,
                  self.out_s_in_fld, self.out_single):
            fl.addWidget(w)
        note = QLabel(
            "(Note) iFLD and coarse-grained FLD cannot be output "
            "simultaneously.", fmt)
        note.setStyleSheet("color: #555;")
        note.setWordWrap(True)
        fl.addWidget(note)
        lay.addWidget(fmt)

        red = QGroupBox("Processing for large-scale analysis", page)
        rl = QHBoxLayout(red)
        self.out_reduce = QCheckBox(
            "Output reduction (coarse-grained) FLD file", red)
        self.out_reduce_detail = QPushButton("Detail...", red)
        self.out_reduce_detail.clicked.connect(self._fld_reduce_detail)
        rl.addWidget(self.out_reduce)
        rl.addWidget(self.out_reduce_detail)
        rl.addStretch(1)
        lay.addWidget(red)

        iv = QGroupBox("Output interval", page)
        il = QVBoxLayout(iv)
        self.fld_only_last = QCheckBox("Only last cycle", iv)
        il.addWidget(self.fld_only_last)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Constant interval"))
        self.fld_cycle = QDoubleSpinBox(iv)
        self.fld_cycle.setDecimals(0)
        self.fld_cycle.setRange(1, 1e9)
        self.fld_cycle.setValue(1)
        crow.addWidget(self.fld_cycle)
        crow.addWidget(QLabel("cycle + last cycle"))
        crow.addStretch(1)
        il.addLayout(crow)
        self.fld_init = QCheckBox("Output the initial values", iv)
        il.addWidget(self.fld_init)
        tip = QLabel(
            "(Note) There is a field output file at the last calculation "
            "cycle.", iv)
        tip.setStyleSheet("color: #555;")
        tip.setWordWrap(True)
        il.addWidget(tip)
        lay.addWidget(iv)
        lay.addStretch(1)
        return page

    def _fld_reduce_detail(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Details (Coarse-grained FLD Output)")
        dlg.resize(360, 200)
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note(
            "Sets the output of reduction FLD file.", dlg))
        cycle = QDoubleSpinBox(dlg)
        cycle.setDecimals(0)
        cycle.setRange(1, 1e9)
        try:
            cycle.setValue(float(
                self.model.analysis_set_value("fld_reduce_cycle", "1") or 1))
        except ValueError:
            cycle.setValue(1)
        _pair(lay, "Output cycle", cycle)
        bb = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        bb.addStretch(1)
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        if dlg.exec_() == QDialog.Accepted:
            self.model.set_analysis_set_value(
                "fld_reduce_cycle", f"{int(cycle.value())}")
            self.out_reduce.setChecked(True)

    def _build_opt_series(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Set the cycle interval at which the time series data are "
            "output.", page))
        g = QGroupBox("Output Interval", page)
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel("Time series file output cycle"))
        self.ts_cycle = QDoubleSpinBox(g)
        self.ts_cycle.setDecimals(0)
        self.ts_cycle.setRange(1, 1e9)
        self.ts_cycle.setValue(1)
        row.addWidget(self.ts_cycle)
        row.addWidget(QLabel("cycles"))
        detail = QPushButton("Details...", g)
        detail.clicked.connect(self._ts_interval_detail)
        row.addWidget(detail)
        row.addStretch(1)
        gl.addLayout(row)
        lay.addWidget(g)
        g2 = QGroupBox("Time series file", page)
        g2l = QVBoxLayout(g2)
        self.ts_append = QCheckBox("Append time series file", g2)
        g2l.addWidget(self.ts_append)
        tip = QLabel(
            "If checked, the time series data is appended if there already "
            "exists a time series data file of the same name.", g2)
        tip.setStyleSheet("color: #555;")
        tip.setWordWrap(True)
        g2l.addWidget(tip)
        lay.addWidget(g2)
        g3 = QGroupBox("Initial values", page)
        g3l = QVBoxLayout(g3)
        self.ts_init = QCheckBox("Output the initial values", g3)
        g3l.addWidget(self.ts_init)
        tip2 = QLabel(
            "(Note) Inapplicable for restart calculations.", g3)
        tip2.setStyleSheet("color: #555;")
        g3l.addWidget(tip2)
        lay.addWidget(g3)
        lay.addStretch(1)
        return page

    def _ts_interval_detail(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Details (Output Interval)")
        dlg.resize(360, 160)
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note(
            "Set the output interval to output the information to the "
            "time series and L files.", dlg))
        cycle = QDoubleSpinBox(dlg)
        cycle.setDecimals(0)
        cycle.setRange(1, 1e9)
        cycle.setValue(self.ts_cycle.value())
        _pair(lay, "Output cycle", cycle)
        bb = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        bb.addStretch(1)
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        if dlg.exec_() == QDialog.Accepted:
            self.ts_cycle.setValue(cycle.value())

    def _build_opt_restart(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Set the parameters for restart calculation and the output "
            "interval of saving/overwriting the restart file.", page))
        g1 = QGroupBox("Initialize at restart", page)
        g1l = QVBoxLayout(g1)
        self.rst_init = QCheckBox("Initialize at restart", g1)
        g1l.addWidget(self.rst_init)
        self.rst_solid = QCheckBox("Initial temperature of solid", g1)
        self.rst_solid.setChecked(True)
        g1l.addWidget(self.rst_solid)
        lay.addWidget(g1)
        g2 = QGroupBox("Rate of saving the restart file", page)
        g2l = QVBoxLayout(g2)
        self.rst_none = QRadioButton("Do not output", g2)
        self.rst_const = QRadioButton("Constant interval", g2)
        self.rst_const.setChecked(True)
        g2l.addWidget(self.rst_none)
        row = QHBoxLayout()
        row.addWidget(self.rst_const)
        self.rst_cycle = QDoubleSpinBox(g2)
        self.rst_cycle.setDecimals(0)
        self.rst_cycle.setRange(1, 1e9)
        self.rst_cycle.setValue(100)
        row.addWidget(self.rst_cycle)
        row.addWidget(QLabel("cycle"))
        row.addStretch(1)
        g2l.addLayout(row)
        tip = QLabel(
            "(Note) The type of file name of a restart file specified in "
            "[File Name] tab determines file saving mode. When the file "
            "name is generic name, multiple files are saved. When the "
            "file name has an extension, a file is overwritten and saved.",
            g2)
        tip.setStyleSheet("color: #555;")
        tip.setWordWrap(True)
        g2l.addWidget(tip)
        lay.addWidget(g2)
        lay.addStretch(1)
        return page

    def _build_ot(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Select a part for which the max/min temperatures are to be "
            "monitored.", page))
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Output cycle"))
        self.ot_cycle = QDoubleSpinBox(page)
        self.ot_cycle.setDecimals(0)
        self.ot_cycle.setRange(1, 1e9)
        self.ot_cycle.setValue(1)
        crow.addWidget(self.ot_cycle)
        crow.addStretch(1)
        lay.addLayout(crow)
        body = QHBoxLayout()
        self.ot_table = QTableWidget(0, 3, page)
        self.ot_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Output"])
        self.ot_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ot_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ot_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.ot_table, 1)
        side = QVBoxLayout()
        btn_s = QPushButton("Set", page)
        btn_c = QPushButton("Cancel", page)
        btn_s.clicked.connect(
            lambda: self._toggle_sel(self.ot_table, self._ot_sel, True))
        btn_c.clicked.connect(
            lambda: self._toggle_sel(self.ot_table, self._ot_sel, False))
        side.addWidget(btn_s)
        side.addWidget(btn_c)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 1)
        tip = QLabel("Select from list > Set", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)
        lay.addWidget(_note(
            "(Note) Valid when heat is analyzed. Applied to solid parts, "
            "heat conduction panels, or fluid regions.", page))
        return page

    def _build_partial(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets a region to be output to a partial FLD file.", page))
        g = QGroupBox("Cuboid region/Plane", page)
        gl = QHBoxLayout(g)
        b_cube = QPushButton("Cuboid Region...", g)
        b_plane = QPushButton("Plane...", g)
        b_cube.clicked.connect(lambda: self._partial_add("Cuboid Region"))
        b_plane.clicked.connect(lambda: self._partial_add("Plane"))
        gl.addWidget(b_cube)
        gl.addWidget(b_plane)
        gl.addStretch(1)
        lay.addWidget(g)
        g2 = QGroupBox("Region", page)
        g2l = QVBoxLayout(g2)
        body = QHBoxLayout()
        self.partial_table = QTableWidget(0, 3, page)
        self.partial_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Parameter"])
        self.partial_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.partial_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.partial_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.partial_table, 1)
        side = QVBoxLayout()
        b_add = QPushButton("Add", page)
        b_del = QPushButton("Delete", page)
        b_add.clicked.connect(lambda: self._partial_add("Region"))
        b_del.clicked.connect(self._partial_del)
        side.addWidget(b_add)
        side.addWidget(b_del)
        side.addStretch(1)
        body.addLayout(side)
        g2l.addLayout(body, 1)
        lay.addWidget(g2, 1)
        lay.addWidget(_note(
            "(Note) Cut-cell parts cannot be specified.", page))
        return page

    def _partial_fill(self) -> None:
        self.partial_table.setRowCount(0)
        for i, item in enumerate(self._partial):
            self.partial_table.insertRow(i)
            self.partial_table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.partial_table.setItem(i, 1, QTableWidgetItem(item["type"]))
            self.partial_table.setItem(
                i, 2, QTableWidgetItem(item.get("param", "")))

    def _partial_add(self, kind: str) -> None:
        n = len(self._partial) + 1
        if kind == "Cuboid Region":
            name = f"Cuboid{n}"
            param = "0,0,0 / 1,1,1"
        elif kind == "Plane":
            name = f"Plane{n}"
            param = "Z=0"
        else:
            names = self._part_names()
            if not names:
                QMessageBox.information(
                    self, "Partial FLD", "No region is available.")
                return
            name, ok = QtWidgets.QInputDialog.getItem(
                self, "Partial FLD", "Region:", names, 0, False)
            if not ok:
                return
            param = name
            name = f"Region:{name}"
        self._partial.append({"name": name, "type": kind, "param": param})
        self._partial_fill()

    def _partial_del(self) -> None:
        rows = self.partial_table.selectionModel().selectedRows()
        if not rows:
            return
        del self._partial[rows[0].row()]
        self._partial_fill()

    def _build_ocsv(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets parts whose internal variables are output.", page))
        body = QHBoxLayout()
        self.ocsv_table = QTableWidget(0, 3, page)
        self.ocsv_table.setHorizontalHeaderLabels(
            ["Part name", "*", "Output"])
        self.ocsv_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ocsv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ocsv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.ocsv_table, 1)
        side = QVBoxLayout()
        btn_s = QPushButton("Set", page)
        btn_c = QPushButton("Cancel", page)
        btn_s.clicked.connect(
            lambda: self._toggle_sel(self.ocsv_table, self._ocsv_sel, True))
        btn_c.clicked.connect(
            lambda: self._toggle_sel(self.ocsv_table, self._ocsv_sel, False))
        side.addWidget(btn_s)
        side.addWidget(btn_c)
        side.addStretch(1)
        body.addLayout(side)
        ofl = QFormLayout()
        self.ocsv_itype = QComboBox(page)
        self.ocsv_itype.addItems([
            "Center of each element inside the part",
            "Center of each element face (outer side)",
            "Center of each element face (inner side)"])
        ofl.addRow("Output location", self.ocsv_itype)
        self.ocsv_lvar = QLineEdit(page)
        self.ocsv_lvar.setText("TEMP")
        ofl.addRow("Output variables (LVAR)", self.ocsv_lvar)
        lay.addLayout(ofl)
        lay.addLayout(body, 1)
        lay.addWidget(_note(
            "(Note) Displayed when an OCSV file is enabled in Detailed "
            "Program Settings. Valid when temperature is analyzed and a "
            "solid part or heat conduction panel exists.", page))
        return page

    def _build_csv(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets CSV file information for CSV mapping.", page))
        body = QHBoxLayout()
        self.csv_table = QTableWidget(0, 3, page)
        self.csv_table.setHorizontalHeaderLabels(
            ["Name", "File", "Variable"])
        self.csv_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.csv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.csv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.csv_table, 1)
        side = QVBoxLayout()
        b_add = QPushButton("Add", page)
        b_del = QPushButton("Delete", page)
        b_add.clicked.connect(self._csv_add)
        b_del.clicked.connect(self._csv_del)
        side.addWidget(b_add)
        side.addWidget(b_del)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 1)
        return page

    def _csv_fill(self) -> None:
        self.csv_table.setRowCount(0)
        for i, item in enumerate(self._csv_maps):
            self.csv_table.insertRow(i)
            self.csv_table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.csv_table.setItem(i, 1, QTableWidgetItem(item["file"]))
            self.csv_table.setItem(i, 2, QTableWidgetItem(item["var"]))

    def _csv_add(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("CSV Mapping Data")
        dlg.resize(420, 200)
        lay = QVBoxLayout(dlg)
        name = QLineEdit(f"csv{len(self._csv_maps) + 1}", dlg)
        path_ed = QLineEdit(dlg)
        var = QComboBox(dlg)
        var.addItems(["Temperature", "Velocity", "Pressure", "Custom"])
        _pair(lay, "Name", name)
        row = QHBoxLayout()
        row.addWidget(QLabel("CSV file"))
        row.addWidget(path_ed, 1)
        b = QPushButton("...", dlg)
        b.setFixedWidth(32)
        b.clicked.connect(lambda: self._browse(
            path_ed, title="CSV file", filt="CSV (*.csv);;All (*.*)"))
        row.addWidget(b)
        lay.addLayout(row)
        _pair(lay, "Variable", var)
        bb = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        bb.addStretch(1)
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._csv_maps.append({
            "name": name.text().strip() or f"csv{len(self._csv_maps) + 1}",
            "file": path_ed.text().strip(),
            "var": var.currentText(),
        })
        self._csv_fill()

    def _csv_del(self) -> None:
        rows = self.csv_table.selectionModel().selectedRows()
        if not rows:
            return
        del self._csv_maps[rows[0].row()]
        self._csv_fill()

    def _build_map_coord(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Correct coordinates of input FLD file for mapping so that "
            "they correspond to current coordinates.", page))
        self.map_coord_on = QCheckBox(
            "Correct coordinates of the whole", page)
        lay.addWidget(self.map_coord_on)
        g = QGroupBox("Translation", page)
        gl = QFormLayout(g)
        self.map_tx = QDoubleSpinBox(g)
        self.map_ty = QDoubleSpinBox(g)
        self.map_tz = QDoubleSpinBox(g)
        for sp in (self.map_tx, self.map_ty, self.map_tz):
            sp.setDecimals(6)
            sp.setRange(-1e9, 1e9)
        gl.addRow("X", self.map_tx)
        gl.addRow("Y", self.map_ty)
        gl.addRow("Z", self.map_tz)
        lay.addWidget(g)
        g2 = QGroupBox("Rotation (deg)", page)
        g2l = QFormLayout(g2)
        self.map_rx = QDoubleSpinBox(g2)
        self.map_ry = QDoubleSpinBox(g2)
        self.map_rz = QDoubleSpinBox(g2)
        for sp in (self.map_rx, self.map_ry, self.map_rz):
            sp.setDecimals(6)
            sp.setRange(-3600, 3600)
        g2l.addRow("X", self.map_rx)
        g2l.addRow("Y", self.map_ry)
        g2l.addRow("Z", self.map_rz)
        lay.addWidget(g2)
        lay.addWidget(_note(
            "(Note) When both rotation and translation are considered, "
            "rotate first, then translate.", page))
        lay.addStretch(1)
        for w in (self.map_tx, self.map_ty, self.map_tz,
                  self.map_rx, self.map_ry, self.map_rz):
            self.map_coord_on.toggled.connect(w.setEnabled)
            w.setEnabled(False)
        return page

    def _build_map_indiv(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note(
            "Sets correction information to be specified for each mapping.",
            page))
        body = QHBoxLayout()
        self.map_corr_table = QTableWidget(0, 3, page)
        self.map_corr_table.setHorizontalHeaderLabels(
            ["Name", "Translation", "Rotation"])
        self.map_corr_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.map_corr_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.map_corr_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.map_corr_table, 1)
        side = QVBoxLayout()
        b_add = QPushButton("Add", page)
        b_del = QPushButton("Delete", page)
        b_add.clicked.connect(self._map_corr_add)
        b_del.clicked.connect(self._map_corr_del)
        side.addWidget(b_add)
        side.addWidget(b_del)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 1)
        return page

    def _map_corr_fill(self) -> None:
        self.map_corr_table.setRowCount(0)
        for i, item in enumerate(self._map_corr):
            self.map_corr_table.insertRow(i)
            self.map_corr_table.setItem(
                i, 0, QTableWidgetItem(item["name"]))
            self.map_corr_table.setItem(
                i, 1, QTableWidgetItem(item["trans"]))
            self.map_corr_table.setItem(
                i, 2, QTableWidgetItem(item["rot"]))

    def _map_corr_add(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Individual Correction of Mapping")
        dlg.resize(360, 220)
        lay = QVBoxLayout(dlg)
        name = QLineEdit(f"corr{len(self._map_corr) + 1}", dlg)
        _pair(lay, "Name", name)
        tx = QDoubleSpinBox(dlg)
        ty = QDoubleSpinBox(dlg)
        tz = QDoubleSpinBox(dlg)
        rx = QDoubleSpinBox(dlg)
        ry = QDoubleSpinBox(dlg)
        rz = QDoubleSpinBox(dlg)
        for sp in (tx, ty, tz, rx, ry, rz):
            sp.setDecimals(6)
            sp.setRange(-1e9, 1e9)
        lay.addWidget(QLabel("Translation", dlg))
        rowt = QHBoxLayout()
        for sp, lab in ((tx, "X"), (ty, "Y"), (tz, "Z")):
            rowt.addWidget(QLabel(lab))
            rowt.addWidget(sp)
        lay.addLayout(rowt)
        lay.addWidget(QLabel("Rotation (deg)", dlg))
        rowr = QHBoxLayout()
        for sp, lab in ((rx, "X"), (ry, "Y"), (rz, "Z")):
            rowr.addWidget(QLabel(lab))
            rowr.addWidget(sp)
        lay.addLayout(rowr)
        bb = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        bb.addStretch(1)
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._map_corr.append({
            "name": name.text().strip() or f"corr{len(self._map_corr) + 1}",
            "trans": f"{tx.value():g},{ty.value():g},{tz.value():g}",
            "rot": f"{rx.value():g},{ry.value():g},{rz.value():g}",
        })
        self._map_corr_fill()

    def _map_corr_del(self) -> None:
        rows = self.map_corr_table.selectionModel().selectedRows()
        if not rows:
            return
        del self._map_corr[rows[0].row()]
        self._map_corr_fill()

    def _build_map_var(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(_note("Change the variable for mapping.", page))
        self.map_var_on = QCheckBox("Change the variable", page)
        lay.addWidget(self.map_var_on)
        g = QGroupBox("Variable to be used", page)
        gl = QVBoxLayout(g)
        body = QHBoxLayout()
        self.map_var_table = QTableWidget(0, 4, page)
        self.map_var_table.setHorizontalHeaderLabels(
            ["Parameter", "Variable before change", "Alterable variable",
             "Change"])
        self.map_var_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.map_var_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.map_var_table.setEditTriggers(QTableWidget.NoEditTriggers)
        body.addWidget(self.map_var_table, 1)
        side = QVBoxLayout()
        btn_s = QPushButton("Set", page)
        btn_c = QPushButton("Cancel", page)
        btn_s.clicked.connect(self._map_var_set)
        btn_c.clicked.connect(self._map_var_cancel)
        side.addWidget(btn_s)
        side.addWidget(btn_c)
        side.addStretch(1)
        body.addLayout(side)
        gl.addLayout(body, 1)
        lay.addWidget(g, 1)
        self.map_var_on.toggled.connect(self.map_var_table.setEnabled)
        self.map_var_on.toggled.connect(btn_s.setEnabled)
        self.map_var_on.toggled.connect(btn_c.setEnabled)
        self.map_var_table.setEnabled(False)
        btn_s.setEnabled(False)
        btn_c.setEnabled(False)
        return page

    def _map_var_fill(self) -> None:
        self.map_var_table.setRowCount(0)
        for i, (param, before, alter) in enumerate(self._MAP_VARS):
            self.map_var_table.insertRow(i)
            self.map_var_table.setItem(i, 0, QTableWidgetItem(param))
            self.map_var_table.setItem(i, 1, QTableWidgetItem(before))
            self.map_var_table.setItem(i, 2, QTableWidgetItem(alter))
            mark = "Selected" if param in self._map_var_sel else ""
            self.map_var_table.setItem(i, 3, QTableWidgetItem(mark))

    def _map_var_set(self) -> None:
        rows = self.map_var_table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.map_var_table.item(rows[0].row(), 0).text()
        self._map_var_sel.add(name)
        self.map_var_table.item(rows[0].row(), 3).setText("Selected")

    def _map_var_cancel(self) -> None:
        rows = self.map_var_table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.map_var_table.item(rows[0].row(), 0).text()
        self._map_var_sel.discard(name)
        self.map_var_table.item(rows[0].row(), 3).setText("")

    @staticmethod
    def _dump_list(items: list[dict], keys: tuple[str, ...]) -> str:
        parts = []
        for it in items:
            parts.append(";".join(it.get(k, "") for k in keys))
        return "|".join(parts)

    @staticmethod
    def _load_list(text: str, keys: tuple[str, ...]) -> list[dict]:
        out: list[dict] = []
        for chunk in (text or "").split("|"):
            if not chunk.strip():
                continue
            vals = chunk.split(";")
            d = {k: (vals[i] if i < len(vals) else "")
                 for i, k in enumerate(keys)}
            out.append(d)
        return out

    def _load(self) -> None:
        m = self.model
        self.sol_name.setText(m.project_name)
        self.f_comment.setText(m.project_value("comment", ""))
        self.f_fld.setText(m.file_value("fld", m.project_name or ""))
        self.f_tm.setText(m.file_value("tm", ""))
        self.f_ri.setText(m.file_value("ri", ""))
        self.f_ro.setText(m.file_value("ro", ""))
        self.f_ot.setText(m.file_value("ot", ""))
        self.f_hpt.setText(m.file_value("hpt", ""))
        self.f_vf.setText(m.file_value("vf", ""))
        self.f_sufl.setText(m.file_value("sufl", ""))
        self.f_map.setText(m.file_value("map", ""))
        self.f_ocsv.setText(m.file_value("ocsv", ""))
        self.f_pcl.setText(m.file_value("pcl", ""))
        vf_io = m.analysis_set_value("vf_file_io", "T")
        self.vf_on.setChecked(vf_io.upper() not in ("F", "0", "FALSE"))

        self.out_fld.setChecked(
            m.output_value("fld_file", "1") not in ("0", "F", "FALSE"))
        self.out_p.setChecked(
            m.output_value("p_file", "0") in ("1", "T", "TRUE"))
        self.out_ifld.setChecked(
            m.output_value("ifld_file", "0") in ("1", "T", "TRUE"))
        self.out_s_in_fld.setChecked(
            m.output_value("s_in_fld", "1") not in ("0", "F", "FALSE"))
        self.out_single.setChecked(
            m.output_value("single_precision_fld", "0")
            in ("1", "T", "TRUE"))
        self.out_reduce.setChecked(
            m.analysis_set_value("fld_reduce", "F").upper()
            in ("T", "1", "TRUE"))
        try:
            self.fld_cycle.setValue(float(
                m.analysis_set_value("fld_out_cycle", "1") or 1))
        except ValueError:
            self.fld_cycle.setValue(1)
        self.fld_only_last.setChecked(
            m.analysis_set_value("fld_only_last", "F").upper()
            in ("T", "1", "TRUE"))
        self.fld_init.setChecked(
            m.output_value("post", "F", type_="initial").upper()
            in ("T", "1", "TRUE"))

        try:
            self.ts_cycle.setValue(float(
                m.output_value("time_series_cycle", "1") or 1))
        except ValueError:
            self.ts_cycle.setValue(1)
        self.ts_append.setChecked(
            m.analysis_set_value("tmsr_append", "F").upper()
            in ("T", "1", "TRUE"))
        self.ts_init.setChecked(
            m.analysis_set_value("tmsr_initial", "F").upper()
            in ("T", "1", "TRUE"))

        self.rst_init.setChecked(
            m.analysis_set_value("restart_init", "F").upper()
            in ("T", "1", "TRUE"))
        self.rst_solid.setChecked(
            m.analysis_set_value("restart_solid_temp", "T").upper()
            not in ("F", "0", "FALSE"))
        try:
            self.rst_cycle.setValue(float(
                m.output_value("restart", "100", type_="const_cycle")
                or 100))
        except ValueError:
            self.rst_cycle.setValue(100)
        if m.analysis_set_value("restart_no_output", "F").upper() in (
                "T", "1", "TRUE"):
            self.rst_none.setChecked(True)
        else:
            self.rst_const.setChecked(True)

        try:
            self.ot_cycle.setValue(float(
                m.output_value("minmax_cycle", "1") or 1))
        except ValueError:
            self.ot_cycle.setValue(1)
        self._ot_sel = {
            x for x in m.analysis_set_value("tprt_parts", "").split("|") if x}
        self._fill_sel_table(self.ot_table, self._part_names(), self._ot_sel)

        self._partial = self._load_list(
            m.analysis_set_value("partial_fld", ""),
            ("name", "type", "param"))
        self._partial_fill()

        self._ocsv_sel = {
            x for x in m.analysis_set_value("ocsv_parts", "").split("|") if x}
        self._fill_sel_table(
            self.ocsv_table, self._part_names(), self._ocsv_sel)
        try:
            self.ocsv_itype.setCurrentIndex(int(float(
                m.analysis_set_value("lfile_ocsv_itype", "1"))) - 1)
        except ValueError:
            pass
        self.ocsv_lvar.setText(
            m.analysis_set_value("lfile_ocsv_lvar", "TEMP"))

        self._csv_maps = self._load_list(
            m.analysis_set_value("csv_mapping", ""),
            ("name", "file", "var"))
        self._csv_fill()

        self.map_coord_on.setChecked(
            m.analysis_set_value("map_coord_on", "F").upper()
            in ("T", "1", "TRUE"))
        try:
            tx, ty, tz = (m.analysis_set_value(
                "map_trans", "0,0,0") or "0,0,0").split(",")[:3]
            self.map_tx.setValue(float(tx))
            self.map_ty.setValue(float(ty))
            self.map_tz.setValue(float(tz))
        except ValueError:
            pass
        try:
            rx, ry, rz = (m.analysis_set_value(
                "map_rot", "0,0,0") or "0,0,0").split(",")[:3]
            self.map_rx.setValue(float(rx))
            self.map_ry.setValue(float(ry))
            self.map_rz.setValue(float(rz))
        except ValueError:
            pass

        self._map_corr = self._load_list(
            m.analysis_set_value("map_indiv", ""),
            ("name", "trans", "rot"))
        self._map_corr_fill()

        self.map_var_on.setChecked(
            m.analysis_set_value("map_var_on", "F").upper()
            in ("T", "1", "TRUE"))
        self._map_var_sel = {
            x for x in m.analysis_set_value("map_vars", "").split("|") if x}
        self._map_var_fill()

    def apply(self) -> None:
        m = self.model
        name = self.sol_name.text().strip()
        if name:
            m.set_project_name(name)
        m.set_project_value("comment", self.f_comment.text().strip())
        m.set_file_value("fld", self.f_fld.text().strip())
        m.set_file_value("tm", self.f_tm.text().strip())
        m.set_file_value("ri", self.f_ri.text().strip())
        m.set_file_value("ro", self.f_ro.text().strip())
        m.set_file_value("ot", self.f_ot.text().strip())
        m.set_file_value("hpt", self.f_hpt.text().strip())
        m.set_file_value(
            "vf",
            self.f_vf.text().strip() if self.vf_on.isChecked() else "")
        m.set_file_value("sufl", self.f_sufl.text().strip())
        m.set_file_value("map", self.f_map.text().strip())
        m.set_file_value("ocsv", self.f_ocsv.text().strip())
        m.set_file_value("pcl", self.f_pcl.text().strip())
        if name and not m.file_value("s"):
            m.set_file_value("s", f"{name}.s")
        m.set_analysis_set_value(
            "vf_file_io", "T" if self.vf_on.isChecked() else "F")

        m.set_output_value(
            "fld_file", "1" if self.out_fld.isChecked() else "0")
        m.set_output_value(
            "p_file", "1" if self.out_p.isChecked() else "0")
        m.set_output_value(
            "ifld_file", "1" if self.out_ifld.isChecked() else "0")
        m.set_output_value(
            "s_in_fld", "1" if self.out_s_in_fld.isChecked() else "0")
        m.set_output_value(
            "single_precision_fld",
            "1" if self.out_single.isChecked() else "0")
        m.set_analysis_set_value(
            "fld_reduce", "T" if self.out_reduce.isChecked() else "F")
        m.set_analysis_set_value(
            "fld_out_cycle", f"{int(self.fld_cycle.value())}")
        m.set_analysis_set_value(
            "fld_only_last", "T" if self.fld_only_last.isChecked() else "F")
        m.set_output_value(
            "post", "T" if self.fld_init.isChecked() else "F",
            type_="initial")

        m.set_output_value(
            "time_series_cycle", f"{int(self.ts_cycle.value())}",
            type_extra="cycle:L")
        m.set_analysis_set_value(
            "tmsr_append", "T" if self.ts_append.isChecked() else "F")
        m.set_analysis_set_value(
            "tmsr_initial", "T" if self.ts_init.isChecked() else "F")

        m.set_analysis_set_value(
            "restart_init", "T" if self.rst_init.isChecked() else "F")
        m.set_analysis_set_value(
            "restart_solid_temp",
            "T" if self.rst_solid.isChecked() else "F")
        m.set_analysis_set_value(
            "restart_no_output",
            "T" if self.rst_none.isChecked() else "F")
        m.set_output_value(
            "restart", f"{int(self.rst_cycle.value())}",
            type_="const_cycle")
        m.set_output_value(
            "restart", "F" if self.rst_none.isChecked() else "T",
            type_="rest_file")

        m.set_output_value(
            "minmax_cycle", f"{int(self.ot_cycle.value())}")
        m.set_analysis_set_value(
            "tprt_parts", "|".join(sorted(self._ot_sel)))
        m.set_analysis_set_value(
            "partial_fld",
            self._dump_list(self._partial, ("name", "type", "param")))
        m.set_analysis_set_value(
            "ocsv_parts", "|".join(sorted(self._ocsv_sel)))
        m.set_analysis_set_value(
            "lfile_ocsv_itype", str(self.ocsv_itype.currentIndex() + 1))
        m.set_analysis_set_value(
            "lfile_ocsv_lvar", self.ocsv_lvar.text().strip() or "TEMP")
        m.set_analysis_set_value(
            "lfile_ocsv_label",
            os.path.splitext(self.f_ocsv.text().strip())[0] or "ocsv")
        m.set_analysis_set_value(
            "csv_mapping",
            self._dump_list(self._csv_maps, ("name", "file", "var")))
        m.set_analysis_set_value(
            "map_coord_on", "T" if self.map_coord_on.isChecked() else "F")
        m.set_analysis_set_value(
            "map_trans",
            f"{self.map_tx.value():g},{self.map_ty.value():g},"
            f"{self.map_tz.value():g}")
        m.set_analysis_set_value(
            "map_rot",
            f"{self.map_rx.value():g},{self.map_ry.value():g},"
            f"{self.map_rz.value():g}")
        m.set_analysis_set_value(
            "map_indiv",
            self._dump_list(self._map_corr, ("name", "trans", "rot")))
        m.set_analysis_set_value(
            "map_var_on", "T" if self.map_var_on.isChecked() else "F")
        m.set_analysis_set_value(
            "map_vars", "|".join(sorted(self._map_var_sel)))


class _CwConditionListPage(QWidget if _HAS_GUI else object):
    """Condition List — STpre tree grouped by condition type."""

    _GROUP_ORDER = (
        "initial", "flux", "wall", "heat_transfer", "radiation_boundary",
        "fixed_temperature", "fixed_velocity",
        "volumetric_force", "volumetric_pressure_loss", "heat_source",
        "moisture_source", "smoke_source", "source_term",
        "humidification", "plant_canopy", "driver", "time_series",
        "area_pressure_loss", "area_heat_source",
        "perforated_plate", "marangoni", "diffusion",
    )

    _GROUP_LABELS = {
        "initial": "Initial condition",
        "flux": "Flow boundary condition",
        "wall": "Wall Boundary Condition",
        "heat_transfer": "Heat transfer condition",
        "radiation_boundary": "Radiation boundary",
        "fixed_temperature": "Fixed temperature condition",
        "fixed_velocity": "Fixed flow velocity condition",
        "volumetric_force": "Volumetric force",
        "volumetric_pressure_loss": "Volumetric pressure loss",
        "heat_source": "Volumetric heat source",
        "moisture_source": "Moisture source",
        "smoke_source": "Smoke source",
        "source_term": "Generalized source term",
        "humidification": "Humidification",
        "plant_canopy": "Plant canopy",
        "driver": "Driver (LES)",
        "time_series": "Time series",
        "area_pressure_loss": "Area pressure loss",
        "area_heat_source": "Area heat source",
        "perforated_plate": "Perforated plate",
        "marangoni": "Marangoni convection",
        "diffusion": "Diffusion",
    }

    _KIND_LABELS = {
        "TEMP": "Initial T",
        "PRES": "Initial P",
        "UNOR": "Initial U",
        "VNOR": "Initial V",
        "WNOR": "Initial W",
        "total_pres": "Total pressure",
        "static_pres": "Static pressure",
        "fixed_vel": "Fixed velocity",
        "no_slip": "Noslip(smooth)",
        "free_slip": "Free slip",
        "log_law": "Heat transfer",
        "adiabatic": "Adiabatic",
        "conductive": "Conduction",
        "normal": "Radiation",
        "fixed": "Fixed temperature",
    }

    _ROLE_KIND = int(Qt.UserRole) + 1
    _ROLE_NAME = int(Qt.UserRole) + 2
    _ROLE_VTYPE = int(Qt.UserRole) + 3

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Already defined conditions are shown below.", self))
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Condition name", "Type"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self.tree, 1)
        tip = QLabel(
            "Note) The conditions may be modified (copied, removed etc) "
            "by right-clicking the name. Also, the checked conditions "
            "may be saved as an XML file.", self)
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)
        self._folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self._value_icon = self._make_value_icon()
        self._block_check = False
        self.refresh()

    @staticmethod
    def _make_value_icon() -> QIcon:
        pm = QPixmap(16, 16)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor(0, 200, 0))
        p.setPen(QColor(0, 140, 0))
        p.drawEllipse(2, 2, 12, 12)
        p.end()
        return QIcon(pm)

    @classmethod
    def _group_label(cls, vtype: str) -> str:
        return cls._GROUP_LABELS.get(vtype, vtype.replace("_", " ").title())

    @classmethod
    def _is_default_name(cls, name: str) -> bool:
        n = (name or "").strip()
        return (n.startswith("_")
                or "(default)" in n
                or "(undefined" in n)

    def _value_name(self, val) -> str:
        for ch in val:
            if ch.tag == "name":
                return (ch.text or "").strip()
        return ""

    def _value_kind_label(self, val) -> str:
        kind = ""
        typ = ""
        for ch in val:
            if ch.tag == "kind" and (ch.text or "").strip():
                kind = (ch.text or "").strip()
            elif ch.tag == "type" and (ch.text or "").strip():
                typ = (ch.text or "").strip()
        key = kind or typ
        if key in self._KIND_LABELS:
            return self._KIND_LABELS[key]
        return key

    def _targets_of(self, name: str) -> list[str]:
        targets: list[str] = []
        for c in self.model.conditions():
            tname = None
            val = None
            for ch in c:
                if ch.tag in ("region", "parts", "analysis"):
                    tname = (ch.text or "").strip()
                elif ch.tag == "value":
                    val = (ch.text or "").strip()
            if val == name and tname:
                targets.append(tname)
        return targets

    def _in_use(self, name: str) -> bool:
        return bool(self._targets_of(name))

    def refresh(self) -> None:
        self._block_check = True
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, ["Condition", ""])
        root.setFlags(root.flags() | Qt.ItemIsUserCheckable
                      | Qt.ItemIsTristate)
        root.setCheckState(0, Qt.Checked)
        root.setIcon(0, self._folder_icon)
        root.setData(0, self._ROLE_KIND, "root")

        groups: dict[str, list] = {}
        for val in self.model.values():
            vtype = val.attrib.get("type") or ""
            if not vtype:
                continue
            name = self._value_name(val)
            if not name:
                continue
            groups.setdefault(vtype, []).append(val)

        ordered = [t for t in self._GROUP_ORDER if t in groups]
        ordered += sorted(t for t in groups if t not in self._GROUP_ORDER)

        for vtype in ordered:
            gitem = QTreeWidgetItem(root, [self._group_label(vtype), ""])
            gitem.setFlags(gitem.flags() | Qt.ItemIsUserCheckable
                           | Qt.ItemIsTristate)
            gitem.setCheckState(0, Qt.Checked)
            gitem.setIcon(0, self._folder_icon)
            gitem.setData(0, self._ROLE_KIND, "group")
            gitem.setData(0, self._ROLE_VTYPE, vtype)
            for val in sorted(groups[vtype], key=self._value_name):
                name = self._value_name(val)
                leaf = QTreeWidgetItem(
                    gitem, [name, self._value_kind_label(val)])
                leaf.setFlags((leaf.flags() | Qt.ItemIsUserCheckable)
                              & ~Qt.ItemIsTristate)
                leaf.setCheckState(0, Qt.Checked)
                leaf.setIcon(0, self._value_icon)
                leaf.setData(0, self._ROLE_KIND, "value")
                leaf.setData(0, self._ROLE_NAME, name)
                leaf.setData(0, self._ROLE_VTYPE, vtype)
                tip = ", ".join(self._targets_of(name))
                if tip:
                    leaf.setToolTip(0, f"Target: {tip}")
        self.tree.expandAll()
        self.tree.resizeColumnToContents(1)
        self._block_check = False

    def _on_item_changed(self, item, column) -> None:
        if self._block_check or column != 0:
            return
        # Keep parent/child checkboxes consistent for groups.
        kind = item.data(0, self._ROLE_KIND)
        if kind in ("root", "group"):
            state = item.checkState(0)
            self._block_check = True
            for i in range(item.childCount()):
                ch = item.child(i)
                ch.setCheckState(0, state)
                if ch.data(0, self._ROLE_KIND) == "group":
                    for j in range(ch.childCount()):
                        ch.child(j).setCheckState(0, state)
            self._block_check = False

    def _on_double_click(self, item, _column) -> None:
        if item.data(0, self._ROLE_KIND) == "value":
            self._details(item.data(0, self._ROLE_NAME))

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        kind = item.data(0, self._ROLE_KIND) if item is not None else None
        name = item.data(0, self._ROLE_NAME) if item is not None else None
        if kind == "value" and name:
            menu.addAction(
                "(Condition) Details...", lambda: self._details(name))
            menu.addAction("Rename...", lambda: self._rename(name))
            menu.addAction("Copy + add", lambda: self._copy(name))
            menu.addAction("Remove", lambda: self._remove(name))
            menu.addSeparator()
        menu.addAction(
            "Delete Unnecessary Conditions", self._delete_unnecessary)
        menu.addAction("(File) Save...", self._file_save)
        menu.addAction("(All Conditions) Remove", self._remove_all)
        if kind == "value" and name:
            menu.addAction(
                "(Condition) Output", lambda: self._condition_output(name))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _details(self, name: str) -> None:
        val = self.model.find_value(name)
        if val is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition Details")
        dlg.resize(420, 320)
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note(f"Condition: {name}", dlg))
        text = QTextEdit(dlg)
        text.setReadOnly(True)
        lines = [f"type = {val.attrib.get('type', '')}"]
        for ch in val:
            if ch.tag == "name":
                continue
            unit = ch.attrib.get("unit", "")
            body = (ch.text or "").strip()
            if unit:
                lines.append(f"{ch.tag} = {body} [{unit}]")
            else:
                lines.append(f"{ch.tag} = {body}")
        targets = self._targets_of(name)
        if targets:
            lines.append("")
            lines.append("Target: " + ", ".join(targets))
        text.setPlainText("\n".join(lines))
        lay.addWidget(text, 1)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)
        dlg.exec_()

    def _rename(self, old: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Rename")
        dlg.resize(360, 120)
        lay = QVBoxLayout(dlg)
        lay.addWidget(_note("Renames condition names.", dlg))
        ed = QLineEdit(old, dlg)
        _pair(lay, "Condition name", ed)
        row = QHBoxLayout()
        btn_r = QPushButton("Rename", dlg)
        btn_c = QPushButton("Cancel", dlg)
        btn_r.clicked.connect(dlg.accept)
        btn_c.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(btn_r)
        row.addWidget(btn_c)
        lay.addLayout(row)
        if dlg.exec_() != QDialog.Accepted:
            return
        new = ed.text().strip()
        if not new or new == old:
            return
        if self.model.find_value(new) is not None:
            QMessageBox.warning(
                self, "Rename",
                f"Condition name ({new}) already exists.")
            return
        from cabxml import set_text
        val = self.model.find_value(old)
        if val is not None:
            for ch in val:
                if ch.tag == "name":
                    set_text(ch, new)
        for c in self.model.conditions():
            for ch in c:
                if ch.tag == "value" and (ch.text or "").strip() == old:
                    set_text(ch, new)
        self.refresh()

    def _unique_copy_name(self, old: str) -> str:
        base = f"{old}_copy"
        if self.model.find_value(base) is None:
            return base
        n = 2
        while self.model.find_value(f"{base}{n}") is not None:
            n += 1
        return f"{base}{n}"

    def _copy(self, old: str) -> None:
        import xml.etree.ElementTree as ET
        val = self.model.find_value(old)
        if val is None:
            return
        new_name = self._unique_copy_name(old)
        copy = ET.fromstring(ET.tostring(val))
        for ch in copy:
            if ch.tag == "name":
                ch.text = f" {new_name} "
        self.model.root.append(copy)
        self.refresh()

    def _remove(self, name: str) -> None:
        if self._in_use(name):
            QMessageBox.warning(
                self, "Remove",
                f"{name} was in use and could not be deleted.")
            return
        if self._is_default_name(name):
            QMessageBox.information(
                self, "Remove",
                "Default conditions are not deleted.")
            return
        val = self.model.find_value(name)
        if val is not None:
            self.model.root.remove(val)
        self.refresh()

    def _delete_unnecessary(self) -> None:
        removed = 0
        for val in list(self.model.values()):
            vtype = val.attrib.get("type")
            if not vtype:
                continue
            name = self._value_name(val)
            if not name or self._is_default_name(name):
                continue
            if self._in_use(name):
                continue
            self.model.root.remove(val)
            removed += 1
        self.refresh()
        QMessageBox.information(
            self, "Delete Unnecessary Conditions",
            f"{removed} unused condition(s) deleted.")

    def _checked_value_names(self) -> list[str]:
        names: list[str] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.data(0, self._ROLE_KIND) == "value":
                if item.checkState(0) == Qt.Checked:
                    names.append(item.data(0, self._ROLE_NAME))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return names

class _CwSolarPage(QWidget if _HAS_GUI else object):
    """Condition Wizard — Solar Radiation (Location / Date-Time / Absorptance).

    Enables the Analysis Types "Solar radiation" flag and stores the
    location (latitude/longitude/timezone), date-time and the default
    absorptance (emissivity) as analysis_set values so they persist in
    the cab and round-trip.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Solar radiation analysis options. Enable syncs the Analysis "
            "Types flag; the location, date/time and absorptance are "
            "stored as analysis settings.", self))
        g = QGroupBox("Solar radiation", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider solar radiation", g)
        aset = (model.analysis_set_value("solar", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(False)
        f.addRow(self.enable)
        loc = QGroupBox("Location", g)
        locl = QFormLayout(loc)
        self.lat = QDoubleSpinBox(loc)
        self.lat.setRange(-90.0, 90.0)
        self.lat.setDecimals(4)
        self.lon = QDoubleSpinBox(loc)
        self.lon.setRange(-180.0, 180.0)
        self.lon.setDecimals(4)
        self.tz = QSpinBox(loc)
        self.tz.setRange(-12, 14)
        for name, w, default in (
                ("solar_latitude", self.lat, 35.0),
                ("solar_longitude", self.lon, 135.0),
                ("solar_timezone", self.tz, 9)):
            try:
                w.setValue(float(model.analysis_set_value(
                    name, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        locl.addRow("Latitude (deg)", self.lat)
        locl.addRow("Longitude (deg)", self.lon)
        locl.addRow("Time zone (UTC offset)", self.tz)
        f.addRow(loc)
        dt = QGroupBox("Date and time", g)
        dtl = QHBoxLayout(dt)
        self.month = QSpinBox(dt)
        self.month.setRange(1, 12)
        self.day = QSpinBox(dt)
        self.day.setRange(1, 31)
        self.hour = QSpinBox(dt)
        self.hour.setRange(0, 23)
        for name, w, default in (
                ("solar_month", self.month, 8),
                ("solar_day", self.day, 1),
                ("solar_hour", self.hour, 12)):
            try:
                w.setValue(int(float(model.analysis_set_value(
                    name, str(default)))))
            except (TypeError, ValueError):
                w.setValue(default)
        dtl.addWidget(QLabel("Month", dt))
        dtl.addWidget(self.month)
        dtl.addWidget(QLabel("Day", dt))
        dtl.addWidget(self.day)
        dtl.addWidget(QLabel("Hour", dt))
        dtl.addWidget(self.hour)
        dtl.addStretch(1)
        f.addRow(dt)
        self.absorptance = QDoubleSpinBox(g)
        self.absorptance.setRange(0.0, 1.0)
        self.absorptance.setDecimals(3)
        try:
            self.absorptance.setValue(float(model.analysis_set_value(
                "solar_absorptance", "0.8")))
        except (TypeError, ValueError):
            self.absorptance.setValue(0.8)
        f.addRow("Default absorptance", self.absorptance)
        lay.addWidget(g)

        # I1c: SOLAR .s cards (exA08-1 / exA07-5) — head, default table,
        # absorber regions.  lat/lon/timezone widgets above feed the
        # SOLAR head row (meridian = timezone x 15).
        sc = QGroupBox("SOLAR .s cards (exA08-1)", self)
        scl = QVBoxLayout(sc)
        self.solar_emit = QCheckBox("Emit SOLAR/SOLA_DEFAULT cards", sc)
        self.solar_emit.setChecked(
            self.model.root.find("analysis_etc/solar") is not None)
        scl.addWidget(self.solar_emit)
        sform = QFormLayout()
        self.solar_a1 = QDoubleSpinBox(sc)
        self.solar_a2 = QDoubleSpinBox(sc)
        self.solar_a3 = QDoubleSpinBox(sc)
        self.solar_a4 = QDoubleSpinBox(sc)
        self.solar_a5 = QDoubleSpinBox(sc)
        for w in (self.solar_a1, self.solar_a2, self.solar_a3,
                  self.solar_a4, self.solar_a5):
            w.setRange(-1e6, 1e6)
            w.setDecimals(3)
        self.solar_a4.setValue(14.0)
        srow1 = QHBoxLayout()
        for lab, w in (("a1", self.solar_a1), ("a2", self.solar_a2),
                       ("a3", self.solar_a3), ("a4", self.solar_a4),
                       ("a5", self.solar_a5)):
            srow1.addWidget(QLabel(lab, sc))
            srow1.addWidget(w)
        srow1.addStretch(1)
        sform.addRow("Auxiliary fixed values", srow1)
        self.solar_ashrae = QDoubleSpinBox(sc)
        self.solar_ashrae.setRange(0.0, 1e6)
        self.solar_ashrae.setDecimals(3)
        self.solar_ashrae.setValue(0.1)
        sform.addRow("ASHRAE value", self.solar_ashrae)
        self.solar_n1 = QSpinBox(sc)
        self.solar_n1.setRange(0, 99)
        self.solar_n1.setValue(9)
        self.solar_n2 = QSpinBox(sc)
        self.solar_n2.setRange(0, 99)
        self.solar_n2.setValue(1)
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("n1", sc))
        nrow.addWidget(self.solar_n1)
        nrow.addWidget(QLabel("n2", sc))
        nrow.addWidget(self.solar_n2)
        nrow.addStretch(1)
        sform.addRow("Header ints", nrow)
        self.solar_monthly1 = QLineEdit(sc)
        self.solar_monthly2 = QLineEdit(sc)
        self.solar_monthly1.setPlaceholderText("12 comma values")
        self.solar_monthly2.setPlaceholderText("12 comma values")
        sform.addRow("Monthly table 1", self.solar_monthly1)
        sform.addRow("Monthly table 2", self.solar_monthly2)
        scl.addLayout(sform)
        dform = QFormLayout()
        self.sola_idrf = QSpinBox(sc)
        self.sola_idrf.setRange(0, 99)
        self.sola_idrf.setValue(1)
        self.sola_sky = QDoubleSpinBox(sc)
        self.sola_sky.setDecimals(5)
        self.sola_sky.setValue(1.0)
        self.sola_gnd = QDoubleSpinBox(sc)
        self.sola_gnd.setDecimals(5)
        self.sola_gnd.setValue(0.2)
        self.sola_info = QSpinBox(sc)
        self.sola_info.setRange(0, 99)
        self.sola_info.setValue(1)
        self.sola_mpcl = QSpinBox(sc)
        self.sola_mpcl.setRange(0, 999999)
        self.sola_mpcl.setValue(20000)
        self.sola_maxm = QSpinBox(sc)
        self.sola_maxm.setRange(0, 999999)
        self.sola_maxm.setValue(4000)
        self.sola_ashrae = QSpinBox(sc)
        self.sola_ashrae.setRange(0, 9999)
        self.sola_ashrae.setValue(2013)
        dform.addRow("SOLA_DEFAULT IDRF", self.sola_idrf)
        dform.addRow("SOLA_DEFAULT SKY", self.sola_sky)
        dform.addRow("SOLA_DEFAULT GND", self.sola_gnd)
        dform.addRow("SOLA_DEFAULT INFO", self.sola_info)
        dform.addRow("SOLA_DEFAULT MPCL", self.sola_mpcl)
        dform.addRow("SOLA_DEFAULT MAXM", self.sola_maxm)
        dform.addRow("SOLA_DEFAULT ASHRAE (year)", self.sola_ashrae)
        scl.addLayout(dform)
        self.sola_table = QTableWidget(0, 8, sc)
        self.sola_table.setHorizontalHeaderLabels(
            ["Kind", "Name", "v1", "v2", "v3", "v4", "Flag", "Region"])
        self.sola_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        scl.addWidget(self.sola_table)
        srrow = QHBoxLayout()
        self.sola_add = QPushButton("Add absorber region", sc)
        self.sola_del = QPushButton("Delete", sc)
        self.sola_add.clicked.connect(self._sola_add)
        self.sola_del.clicked.connect(self._sola_del)
        srrow.addWidget(self.sola_add)
        srrow.addStretch(1)
        srrow.addWidget(self.sola_del)
        scl.addLayout(srrow)
        _sol = self.model.root.find("analysis_etc/solar")
        if _sol is not None:
            try:
                self.solar_ashrae.setValue(float(
                    _sol.attrib.get("ashrae_val", "0.1")))
                self.solar_n1.setValue(int(float(
                    _sol.attrib.get("n1", "9"))))
                self.solar_n2.setValue(int(float(
                    _sol.attrib.get("n2", "1"))))
                for w, k in ((self.solar_a1, "a1"), (self.solar_a2, "a2"),
                             (self.solar_a3, "a3"), (self.solar_a4, "a4"),
                             (self.solar_a5, "a5")):
                    w.setValue(float(_sol.attrib.get(k, "0") or 0))
            except ValueError:
                pass
            self.solar_monthly1.setText(_sol.attrib.get("monthly1", ""))
            self.solar_monthly2.setText(_sol.attrib.get("monthly2", ""))
            d = _sol.find("default")
            if d is not None:
                try:
                    self.sola_idrf.setValue(int(float(
                        d.attrib.get("IDRF", "1"))))
                    self.sola_sky.setValue(float(d.attrib.get("SKY",
                                                              "1.0")))
                    self.sola_gnd.setValue(float(d.attrib.get("GND",
                                                              "0.2")))
                    self.sola_info.setValue(int(float(
                        d.attrib.get("INFO", "1"))))
                    self.sola_mpcl.setValue(int(float(
                        d.attrib.get("MPCL", "20000"))))
                    self.sola_maxm.setValue(int(float(
                        d.attrib.get("MAXM", "4000"))))
                    self.sola_ashrae.setValue(int(float(
                        d.attrib.get("ASHRAE", "2013"))))
                except ValueError:
                    pass
            for rec in _sol.findall("region"):
                self._sola_add(
                    rec.attrib.get("kind", "body_d"),
                    rec.attrib.get("name", ""),
                    rec.attrib.get("v1", "0"), rec.attrib.get("v2", "0"),
                    rec.attrib.get("v3", "0"), rec.attrib.get("v4", "0"),
                    rec.attrib.get("flag", "0"),
                    rec.attrib.get("region", ""))
        lay.addWidget(sc)
        lay.addStretch(1)

    # -- I1c: SOLAR .s cards ----------------------------------------------

    @staticmethod
    def _table_text(table, row: int, col: int, default: str = "") -> str:
        it = table.item(row, col)
        return it.text().strip() if it is not None and it.text()             else default

    def _sola_add(self, kind: str = "body_d", name: str = "吸収体",
                  v1: str = "0", v2: str = "0", v3: str = "0",
                  v4: str = "0", flag: str = "0", region: str = "") -> None:
        r = self.sola_table.rowCount()
        self.sola_table.insertRow(r)
        for col, text in enumerate((kind, name, v1, v2, v3, v4, flag,
                                    region)):
            self.sola_table.setItem(r, col, QTableWidgetItem(str(text)))

    def _sola_del(self) -> None:
        rows = self.sola_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.sola_table.removeRow(idx)

    def _solar_apply(self) -> None:
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("solar")
        if old is not None:
            aet.remove(old)
        if not self.solar_emit.isChecked():
            return
        sol = ET.SubElement(aet, "solar")
        sol.attrib.update(mode="latitude_dec",
                          lat=f"{self.lat.value():g}",
                          lon=f"{self.lon.value():g}",
                          meridian=f"{self.tz.value() * 15}",
                          a1=f"{self.solar_a1.value():g}",
                          a2=f"{self.solar_a2.value():g}",
                          a3=f"{self.solar_a3.value():g}",
                          a4=f"{self.solar_a4.value():g}",
                          a5=f"{self.solar_a5.value():g}",
                          ashrae_kind="ASHRAE",
                          ashrae_val=f"{self.solar_ashrae.value():g}",
                          n1=str(self.solar_n1.value()),
                          n2=str(self.solar_n2.value()),
                          monthly1=self.solar_monthly1.text().strip(),
                          monthly2=self.solar_monthly2.text().strip())
        d = ET.SubElement(sol, "default")
        d.attrib.update(IDRF=str(self.sola_idrf.value()),
                        SKY=f"{self.sola_sky.value():g}",
                        GND=f"{self.sola_gnd.value():g}",
                        INFO=str(self.sola_info.value()),
                        MPCL=str(self.sola_mpcl.value()),
                        MAXM=str(self.sola_maxm.value()),
                        ASHRAE=str(self.sola_ashrae.value()))
        for r in range(self.sola_table.rowCount()):
            rec = ET.SubElement(sol, "region")
            rec.attrib.update(
                kind=self._table_text(self.sola_table, r, 0, "body_d"),
                name=self._table_text(self.sola_table, r, 1),
                v1=self._table_text(self.sola_table, r, 2, "0"),
                v2=self._table_text(self.sola_table, r, 3, "0"),
                v3=self._table_text(self.sola_table, r, 4, "0"),
                v4=self._table_text(self.sola_table, r, 5, "0"),
                flag=self._table_text(self.sola_table, r, 6, "0"),
                region=self._table_text(self.sola_table, r, 7))

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_analysis_set_value("solar", "1" if on else "0")
        self._solar_apply()
        if on:
            self.model.set_analysis_set_value(
                "solar_latitude", f"{self.lat.value():g}")
            self.model.set_analysis_set_value(
                "solar_longitude", f"{self.lon.value():g}")
            self.model.set_analysis_set_value(
                "solar_timezone", str(self.tz.value()))
            self.model.set_analysis_set_value(
                "solar_month", str(self.month.value()))
            self.model.set_analysis_set_value(
                "solar_day", str(self.day.value()))
            self.model.set_analysis_set_value(
                "solar_hour", str(self.hour.value()))
            self.model.set_analysis_set_value(
                "solar_absorptance", f"{self.absorptance.value():g}")

    def _file_save(self) -> None:
        import xml.etree.ElementTree as ET
        names = self._checked_value_names()
        if not names:
            QMessageBox.information(
                self, "(File) Save",
                "Check one or more conditions to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "(File) Save", "conditions.xml",
            "XML (*.xml);;All (*.*)")
        if not path:
            return
        root = ET.Element("conditions")
        for name in names:
            val = self.model.find_value(name)
            if val is None:
                continue
            root.append(ET.fromstring(ET.tostring(val)))
        ET.ElementTree(root).write(
            path, encoding="utf-8", xml_declaration=True)

    def _remove_all(self) -> None:
        ans = QMessageBox.question(
            self, "(All Conditions) Remove",
            "All conditions will be canceled and deleted from all regions.\n"
            "Once the conditions are deleted, they cannot be restored "
            "with Undo.\n"
            "The conditions will also be deleted from the parts "
            "(such as fan parts).\n\n"
            "Delete anyway?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        for c in list(self.model.conditions()):
            self.model.root.remove(c)
        for val in list(self.model.values()):
            if not val.attrib.get("type"):
                continue
            name = self._value_name(val)
            if self._is_default_name(name):
                continue
            self.model.root.remove(val)
        self.refresh()

    def _condition_output(self, name: str) -> None:
        import xml.etree.ElementTree as ET
        val = self.model.find_value(name)
        if val is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "(Condition) Output", f"{name}.xml",
            "XML (*.xml);;All (*.*)")
        if not path:
            return
        ET.ElementTree(ET.fromstring(ET.tostring(val))).write(
            path, encoding="utf-8", xml_declaration=True)


class _CwConfirmPage(QWidget if _HAS_GUI else object):
    """Setting Confirmation — STpre Items/Conditions table."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "The following settings have been made.", self))
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Items", "Conditions"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        clip = QPushButton("Clipboard", self)
        fout = QPushButton("File Output...", self)
        clip.clicked.connect(self._clipboard)
        fout.clicked.connect(self._file_output)
        brow.addWidget(clip)
        brow.addWidget(fout)
        lay.addLayout(brow)
        self._rows: list[tuple[str, str]] = []

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        self._rows = list(rows)
        self.table.setRowCount(0)
        for i, (item, cond) in enumerate(rows):
            self.table.insertRow(i)
            it = QTableWidgetItem(item)
            cd = QTableWidgetItem(cond)
            if item.startswith("* "):
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, cd)
        self.table.resizeRowsToContents()

    def set_summary(self, text: str) -> None:
        """Backward-compatible: plain text -> rows."""
        rows = []
        for line in (text or "").splitlines():
            if "\t" in line:
                a, b = line.split("\t", 1)
                rows.append((a, b))
            else:
                rows.append((line, ""))
        self.set_rows(rows)

    def _as_text(self) -> str:
        lines = ["Items\tConditions"]
        for item, cond in self._rows:
            lines.append(f"{item}\t{cond}")
        return "\n".join(lines)

    def _clipboard(self) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(self._as_text())
        except Exception:
            pass

    def _file_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "File Output", "condition_settings.txt",
            "Text (*.txt);;All (*.*)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._as_text())


# ---------------------------------------------------------------------------
# M28: Humidity / Porous / Radiation grouping (chrome + project writeback)
# ---------------------------------------------------------------------------


class _CwHumidityPage(QWidget if _HAS_GUI else object):
    """Condition Wizard — Humidity (analysis_set + initial RH value)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Humidity analysis options. Enable syncs Analysis Types; "
            "default RH is written as an initial humidity value.", self))
        g = QGroupBox("Humidity", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider humidity", g)
        # Prefer analysis_set flag when present
        aset_on = (model.analysis_set_value("humidity", "") or "").strip()
        if aset_on in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("humidity_enable", "F") == "T")
        self.rh = QDoubleSpinBox(g)
        self.rh.setRange(0.0, 100.0)
        self.rh.setDecimals(1)
        try:
            self.rh.setValue(float(model.project_value("humidity_rh", "50")))
        except ValueError:
            self.rh.setValue(50.0)
        self.bind_domain = QCheckBox(
            "Bind default RH to computational domain", g)
        self.bind_domain.setChecked(
            model.project_value("humidity_bind_domain", "T") == "T")
        f.addRow(self.enable)
        f.addRow("Default relative humidity (%)", self.rh)
        f.addRow(self.bind_domain)
        lay.addWidget(g)

        # C2: humidity boundary conditions — official ``<value
        # type="humidity">`` storage (exA05-2 evidence); type=2 emits
        # HUMW_REGION transfer/wallhumidity cards, type=1 (region-pair
        # family) is stored but its .s emission is probe-deferred.
        bc = QGroupBox("Humidity boundary conditions", self)
        bl = QVBoxLayout(bc)
        self.hum_table = QTableWidget(0, 5, bc)
        self.hum_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Param1", "Param2", "Regions"])
        self.hum_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.hum_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bl.addWidget(self.hum_table, 1)
        hrow = QHBoxLayout()
        btn_flux = QPushButton("Constant moisture flux…", bc)
        btn_flux.clicked.connect(self._new_humidity_flux)
        btn_wall = QPushButton("Humidity transfer (wall)…", bc)
        btn_wall.clicked.connect(self._new_humidity_wall)
        btn_src = QPushButton("Moisture source flux (fluxhumid)…", bc)
        btn_src.clicked.connect(self._new_humidity_source)
        btn_del = QPushButton("Delete", bc)
        btn_del.clicked.connect(self._hum_delete)
        hrow.addWidget(btn_flux)
        hrow.addWidget(btn_wall)
        hrow.addWidget(btn_src)
        hrow.addStretch(1)
        hrow.addWidget(btn_del)
        bl.addLayout(hrow)
        lay.addWidget(bc)

        # I1b: humidity evaporation control — HUMD_CONTROL keyword pairs +
        # HUMC initial absolute-humidity concentration (exA05-1)
        ev = QGroupBox("Evaporation control (exA05-1)", self)
        evl = QFormLayout(ev)
        self.humd_evaporation = QCheckBox("Consider evaporation", ev)
        self.humd_upper = QCheckBox("Apply upper limit", ev)
        evl.addRow(self.humd_evaporation)
        evl.addRow(self.humd_upper)
        self.humc_value = QDoubleSpinBox(ev)
        self.humc_value.setRange(0.0, 1.0)
        self.humc_value.setDecimals(9)
        self.humc_value.setSingleStep(1e-5)
        evl.addRow("Initial humidity concentration (kg/kg)", self.humc_value)
        _humc = model.analysis_etc_section("humc")
        try:
            self.humc_value.setValue(float(
                (_humc.text or "0").strip() or 0) if _humc is not None
                else 0.0)
        except ValueError:
            self.humc_value.setValue(0.0)
        _ctrl = model.root.find("analysis_etc/humd_control")
        if _ctrl is not None:
            _ev = _ctrl.find("evaporation")
            _ul = _ctrl.find("upper_limit")
            self.humd_evaporation.setChecked(
                _ev is not None and (_ev.text or "0").strip() == "1")
            self.humd_upper.setChecked(
                _ul is not None and (_ul.text or "0").strip() == "1")
        lay.addWidget(ev)
        self._hum_reload()
        lay.addStretch(1)

    # -- C2 humidity boundary conditions ---------------------------------

    _HUM_FACES = ("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax")

    def _hum_regions(self) -> list[str]:
        names = [f"{f}面" for f in self._HUM_FACES]
        dom = self.model.domain_name()
        try:
            from cab_domain import domain_faces
            faces = domain_faces(self.model)
            if faces:
                names = [str(f) for f in faces]
        except Exception:
            pass
        if dom:
            names.append(dom)
        return names

    def _commit_humidity(self, name: str, type_code: int, param1: float,
                         param2: Optional[float], region: str,
                         hum_ltype: str = "") -> bool:
        """Create/update one ``<value type="humidity">`` condition.

        ``hum_ltype`` (F2) selects the HUMW_REGION LTYPE for type=1
        values (lewislaw / diffusion / transfer / insulation — the
        official sample cannot be mapped without it)."""
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        children = [("kind", "boundary", None),
                    ("type", str(int(type_code)), None),
                    ("param1", f"{float(param1):g}", "m/s")]
        if hum_ltype:
            children.append(("hum_ltype", hum_ltype, None))
        if param2 is not None:
            children.append(("param2", f"{float(param2):g}", None))
        if not self.model.upsert_value("humidity", name, children):
            return False
        self.model.bind_condition("region", region, name)
        self._hum_reload()
        return True

    def _hum_pick(self, title: str, param2: bool):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, title, "Condition name:")
        if not ok or not str(name).strip():
            return None
        p1, ok1 = QInputDialog.getDouble(
            self, title, "Param1 (m/s)", 0.0, -1e9, 1e9, 6)
        if not ok1:
            return None
        p2 = 0.0
        if param2:
            p2, ok2 = QInputDialog.getDouble(
                self, title, "Param2", 0.0, -1e9, 1e9, 6)
            if not ok2:
                return None
        region, okr = QInputDialog.getItem(
            self, title, "Region:", self._hum_regions(), 0, False)
        if not okr:
            return None
        return str(name).strip(), float(p1), (float(p2) if param2 else None), \
            str(region)

    def _new_humidity_flux(self) -> None:
        """Constant moisture flux (type=1; sign sets the direction)."""
        picked = self._hum_pick("Constant Moisture Flux", param2=False)
        if picked is None:
            return
        name, p1, _p2, region = picked
        self._commit_humidity(name, 1, p1, None, region)

    def _new_humidity_wall(self) -> None:
        """Humidity transfer wall (type=2 -> HUMW_REGION card)."""
        picked = self._hum_pick("Humidity Transfer (wall)", param2=True)
        if picked is None:
            return
        name, p1, p2, region = picked
        self._commit_humidity(name, 2, p1, p2, region)

    def _new_humidity_source(self) -> None:
        """I1b: Moisture source flux (type=4 -> HUMF_REGION fluxhumid
        card, exA05-1: param1 = flux, param2 = secondary value)."""
        picked = self._hum_pick("Moisture Source Flux (fluxhumid)",
                                param2=True)
        if picked is None:
            return
        name, p1, p2, region = picked
        self._commit_humidity(name, 4, p1, p2, region)

    def _new_initial_moisture(self) -> None:
        """C2/F2: [Condition (Initial Moisture)] — HUMH_REGION wallwater
        condition (humidity type=3)."""
        picked = self._hum_pick("Initial Moisture", param2=False)
        if picked is None:
            return
        name, p1, _p2, region = picked
        self._commit_humidity(name, 3, p1, None, region)

    def _hum_delete(self) -> None:
        row = self.hum_table.currentRow()
        if row < 0:
            return
        name = self.hum_table.item(row, 0).text()
        from cabxml import _first
        # drop the value element + every condition binding to it
        for val in self.model.values_of_type("humidity"):
            n = _first(val, "name")
            if n is not None and n.text and n.text.strip() == name:
                self.model.root.remove(val)
                break
        for c in list(self.model.conditions()):
            v = _first(c, "value")
            if v is not None and v.text and v.text.strip() == name:
                self.model.root.remove(c)
        self._hum_reload()

    def _hum_reload(self) -> None:
        rows: dict[str, dict] = {}
        for val in self.model.values_of_type("humidity"):
            name = ""
            from cabxml import _first
            n = _first(val, "name")
            if n is not None and n.text:
                name = n.text.strip()
            if not name:
                continue
            row = rows.setdefault(name, {"type": "", "p1": "", "p2": "",
                                         "regions": []})
            for c in val:
                if c.tag == "type":
                    row["type"] = (c.text or "").strip()
                elif c.tag == "param1":
                    row["p1"] = (c.text or "").strip()
                elif c.tag == "param2":
                    row["p2"] = (c.text or "").strip()
        for c in self.model.conditions():
            vname = ""
            region = ""
            for ch in c:
                if ch.tag == "region":
                    region = (ch.text or "").strip()
            from cabxml import _first
            v = _first(c, "value")
            if v is not None and v.text:
                vname = v.text.strip()
            if vname in rows and region:
                rows[vname]["regions"].append(region)
        self.hum_table.setRowCount(0)
        for name, row in rows.items():
            r = self.hum_table.rowCount()
            self.hum_table.insertRow(r)
            regions = ", ".join(row["regions"])
            for col, text in enumerate(
                    (name, row["type"], row["p1"], row["p2"], regions)):
                self.hum_table.setItem(r, col, QTableWidgetItem(text))

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "humidity_enable", "T" if on else "F")
        self.model.set_project_value("humidity_rh", f"{self.rh.value():g}")
        self.model.set_project_value(
            "humidity_bind_domain",
            "T" if self.bind_domain.isChecked() else "F")
        self.model.set_analysis_set_value("humidity", "1" if on else "0")
        # Deeper write-back: initial humidity value + optional domain bind
        vname = "Humidity_RH_default"
        self.model.upsert_value(
            "humidity", vname,
            [("relative_humidity", f"{self.rh.value():g}", "%"),
             ("humidity_enable", "1" if on else "0", None)])
        if on and self.bind_domain.isChecked():
            domain = self.model.domain_name() or "Domain"
            self.model.bind_condition("analysis", domain, vname)
        # I1b: HUMD_CONTROL + HUMC (exA05-1 evaporation family)
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("humd_control")
        if old is not None:
            aet.remove(old)
        if self.humd_evaporation.isChecked() or self.humd_upper.isChecked():
            ctrl = ET.SubElement(aet, "humd_control")
            ET.SubElement(ctrl, "evaporation").text = (
                "1" if self.humd_evaporation.isChecked() else "0")
            ET.SubElement(ctrl, "upper_limit").text = (
                "1" if self.humd_upper.isChecked() else "0")
        old = aet.find("humc")
        if old is not None:
            aet.remove(old)
        if self.humc_value.value() > 0:
            ET.SubElement(aet, "humc").text = (
                f" {self.humc_value.value():g} ")


class _CwPorousPage(QWidget if _HAS_GUI else object):
    """Condition Wizard — Porous Media (analysis_set + coeff value)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Porous media pressure-loss / heat models. Enable syncs "
            "analysis_set; coefficients are stored as a porous value.",
            self))
        g = QGroupBox("Porous Media", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Enable porous media", g)
        aset = (model.analysis_set_value("porous_media", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("porous_enable", "F") == "T")
        self.model_type = QComboBox(g)
        self.model_type.addItems([
            "Isotropic", "Anisotropic", "Pressure Loss Heat (Fluid-Solid)"])
        cur = model.project_value("porous_model", "Isotropic")
        i = self.model_type.findText(cur)
        if i >= 0:
            self.model_type.setCurrentIndex(i)
        self.alpha = QDoubleSpinBox(g)
        self.alpha.setRange(0.0, 1e12)
        self.alpha.setDecimals(6)
        try:
            self.alpha.setValue(float(
                model.project_value("porous_alpha", "0")))
        except ValueError:
            self.alpha.setValue(0.0)
        self.beta = QDoubleSpinBox(g)
        self.beta.setRange(0.0, 1e12)
        self.beta.setDecimals(6)
        try:
            self.beta.setValue(float(
                model.project_value("porous_beta", "0")))
        except ValueError:
            self.beta.setValue(0.0)
        self.target_part = QComboBox(g)
        self.target_part.addItem("(none)")
        for p in model.parts():
            self.target_part.addItem(p.name)
        f.addRow(self.enable)
        f.addRow("Model", self.model_type)
        f.addRow("Viscous resistance α (1/m2)", self.alpha)
        f.addRow("Inertial resistance β (1/m)", self.beta)
        f.addRow("Bind to part", self.target_part)
        lay.addWidget(g)
        self._porous_subtype_ui()
        lay.addStretch(1)

    # R4-3/4/5: porous subtype deep fields (moisture source / plate-fin /
    # solid-solid / particle release) — stored as porous children.
    def _commit_porous_subtype(self, subtype: str, **kwargs: float
                               ) -> bool:
        name = f"Porous_{subtype}"
        children = [("subtype", subtype, None)]
        for k, v in kwargs.items():
            children.append((k, f"{float(v):.12g}", None))
        if not self.model.upsert_value("porous", name, children):
            return False
        return True

    def _porous_subtype_value(self, subtype: str) -> dict:
        for val in self.model.values_of_type("porous"):
            from cabxml import _first
            el = _first(val, "subtype")
            if el is not None and (el.text or "").strip() == subtype:
                n = _first(val, "name")
                return {c.tag: (c.text or "").strip() for c in val} if                     (n is not None and n.text) else {}
        return {}

    def _lay_add(self, widget) -> None:
        lay = self.layout()
        if lay is not None:
            lay.addWidget(widget)

    # A2: subtype UI (moisture / plate_fin / solid_solid / particle)
    def _porous_subtype_ui(self) -> None:
        from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QPushButton
        g = QGroupBox("Porous subtype parameters", self)
        f = QFormLayout(g)
        self.ps_subtype = QComboBox(g)
        self.ps_subtype.addItems(["moisture", "plate_fin", "solid_solid",
                                  "particle"])
        f.addRow("Subtype", self.ps_subtype)
        self.ps_k1 = QDoubleSpinBox(g)
        self.ps_k1.setRange(-1e9, 1e9)
        self.ps_k1.setDecimals(6)
        f.addRow("Param1", self.ps_k1)
        self.ps_k2 = QDoubleSpinBox(g)
        self.ps_k2.setRange(-1e9, 1e9)
        self.ps_k2.setDecimals(6)
        f.addRow("Param2", self.ps_k2)
        btn = QPushButton("Apply subtype", g)
        btn.clicked.connect(self._ps_apply)
        f.addRow(btn)
        self._lay_add(g)

    def _ps_apply(self) -> None:
        sub = self.ps_subtype.currentText()
        fields = {}
        if self.ps_k1.value() != 0.0:
            fields["k1"] = self.ps_k1.value()
        if self.ps_k2.value() != 0.0:
            fields["k2"] = self.ps_k2.value()
        if not fields:
            fields["k1"] = 0.0
        self._commit_porous_subtype(sub, **fields)
        self.ps_subtype.setEnabled(False)

    def apply(self) -> None:
        on = self.enable.isChecked()
        mtype = self.model_type.currentText()
        self.model.set_project_value(
            "porous_enable", "T" if on else "F")
        self.model.set_project_value("porous_model", mtype)
        self.model.set_project_value(
            "porous_alpha", f"{self.alpha.value():g}")
        self.model.set_project_value(
            "porous_beta", f"{self.beta.value():g}")
        self.model.set_analysis_set_value(
            "porous_media", "1" if on else "0")
        vname = "Porous_default"
        self.model.upsert_value(
            "porous_media", vname,
            [("model", mtype, None),
             ("alpha", f"{self.alpha.value():g}", "1/m2"),
             ("beta", f"{self.beta.value():g}", "1/m"),
             ("enable", "1" if on else "0", None)])
        part = self.target_part.currentText()
        if on and part and part != "(none)":
            self.model.bind_condition("parts", part, vname)


class _CwRadiationGroupingPage(QWidget if _HAS_GUI else object):
    """Condition Wizard — Radiation Grouping (part rad_group_num)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Radiation grouping of parts. Assigns rad_group_num on selected "
            "solid/obstacle parts when enabled.", self))
        g = QGroupBox("Radiation Grouping", self)
        gl = QVBoxLayout(g)
        self.enable = QCheckBox("Enable radiation grouping", g)
        self.enable.setChecked(
            model.project_value("rad_group_enable", "F") == "T")
        self.group_name = QLineEdit(
            model.project_value("rad_group_name", "RadGroup1"), g)
        self.group_num = QSpinBox(g)
        self.group_num.setRange(1, 999)
        try:
            self.group_num.setValue(int(float(
                model.project_value("rad_group_num", "1"))))
        except ValueError:
            self.group_num.setValue(1)
        self.apply_all = QCheckBox(
            "Assign group number to all Solid/Obstacle parts", g)
        self.apply_all.setChecked(True)
        row = QHBoxLayout()
        row.addWidget(QLabel("Group name", g))
        row.addWidget(self.group_name, 1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Group number", g))
        row2.addWidget(self.group_num)
        row2.addStretch(1)
        gl.addWidget(self.enable)
        gl.addLayout(row)
        gl.addLayout(row2)
        gl.addWidget(self.apply_all)
        # ---- R8-A 深字段：辐射求解器（Monte Carlo / VF） ----
        # 子元素名 method/calc_cycle/solver_eps/space_cycle/max_particle/
        # max_group_num 实证于 STpre 2025.2 COM 保存样本（probe_work/
        # cwtypes2_*.cab 的 <analysis_set><radiation type='vf'>）；取值域按
        # Solver 手册 VFDE 命令（MPCL=20000 光线数、MAXM=4000 分组面上限、
        # METH 0=Monte Carlo/1=Radiosity 隐式/2=Radiosity 显式）。
        # 反射次数（VFDE MREF=100）与 SMRT 光线数（VFDE MRCL）的 XML 子元素
        # 名未实证，按 VFDE 条目命名（max_reflection / smrt_rays）。
        rg = QGroupBox("Radiation Solver (Monte Carlo / VF)", self)
        rf = QFormLayout(rg)
        self.rad_type = QComboBox(rg)
        self.rad_type.addItem("VF method", "vf")
        self.rad_type.addItem("Flux method", "flux")
        self.rad_type.addItem("Monte Carlo method", "mc")
        cur_t = model.radiation_type() or "vf"
        i = self.rad_type.findData(cur_t)
        self.rad_type.setCurrentIndex(i if i >= 0 else 0)
        self.rad_method = QComboBox(rg)
        for label, val in (
                ("Monte Carlo method", "0"),
                ("Radiosity method (implicit)", "1"),
                ("Radiosity method (explicit)", "2")):
            self.rad_method.addItem(label, val)
        cur_m = model.radiation_param("method", "1")
        i = self.rad_method.findData(cur_m)
        self.rad_method.setCurrentIndex(i if i >= 0 else 1)
        # MC 光线数：VFDE MPCL（默认 20000；XML 子元素 max_particle 实证）
        self.mc_rays = QSpinBox(rg)
        self.mc_rays.setRange(1, 100000000)
        self.mc_rays.setValue(int(float(
            model.radiation_param("max_particle", "20000"))))
        # 单根光线最大反射次数：VFDE MREF（默认 100；XML 子元素未实证）
        self.mc_reflect = QSpinBox(rg)
        self.mc_reflect.setRange(1, 100000)
        self.mc_reflect.setValue(int(float(
            model.radiation_param("max_reflection", "100"))))
        # SMRT 用光线数：VFDE MRCL（默认=MPCL；XML 子元素未实证）
        self.smrt_rays = QSpinBox(rg)
        self.smrt_rays.setRange(1, 100000000)
        self.smrt_rays.setValue(int(float(
            model.radiation_param("smrt_rays", "20000"))))
        # 分组面上限：VFDE MAXM（默认 4000；XML 子元素 max_group_num 实证）
        self.group_max = QSpinBox(rg)
        self.group_max.setRange(1, 1000000)
        self.group_max.setValue(int(float(
            model.radiation_param("max_group_num", "4000"))))
        # 辐射计算周期：XML 子元素 calc_cycle 实证（COM 默认 -1）
        self.calc_cycle = QSpinBox(rg)
        self.calc_cycle.setRange(-1, 10000000)
        try:
            self.calc_cycle.setValue(int(float(
                model.radiation_param("calc_cycle", "-1"))))
        except ValueError:
            self.calc_cycle.setValue(-1)
        # 求解收敛判据：XML 子元素 solver_eps 实证（COM 默认 -1）
        self.solver_eps = QDoubleSpinBox(rg)
        self.solver_eps.setRange(-1.0, 1.0)
        self.solver_eps.setDecimals(6)
        try:
            self.solver_eps.setValue(float(
                model.radiation_param("solver_eps", "-1")))
        except ValueError:
            self.solver_eps.setValue(-1.0)
        # SMRT 空间平均再计算周期：XML 子元素 space_cycle 实证（默认 0）
        self.space_cycle = QSpinBox(rg)
        self.space_cycle.setRange(0, 10000000)
        self.space_cycle.setValue(int(float(
            model.radiation_param("space_cycle", "0"))))
        rf.addRow("Radiation method (analysis type)", self.rad_type)
        rf.addRow("View-factor calculation method", self.rad_method)
        rf.addRow("Monte Carlo rays per group face", self.mc_rays)
        rf.addRow("Max. reflections per ray", self.mc_reflect)
        rf.addRow("Rays for spatial mean radiant temp.", self.smrt_rays)
        rf.addRow("Upper limit of group faces", self.group_max)
        rf.addRow("Radiation calculation cycle", self.calc_cycle)
        rf.addRow("Solver convergence criterion", self.solver_eps)
        rf.addRow("SMRT recalculation cycle", self.space_cycle)
        lay.addWidget(rg)
        lay.addStretch(1)

    def apply(self) -> None:
        from cabxml import _first, set_text
        import xml.etree.ElementTree as ET
        on = self.enable.isChecked()
        gname = self.group_name.text().strip() or "RadGroup1"
        gnum = self.group_num.value()
        self.model.set_project_value(
            "rad_group_enable", "T" if on else "F")
        self.model.set_project_value("rad_group_name", gname)
        self.model.set_project_value("rad_group_num", str(gnum))
        self.model.set_analysis_set_value(
            "radiation_grouping", "1" if on else "0")
        self.model.upsert_value(
            "radiation_group", gname,
            [("group_num", str(gnum), None),
             ("enable", "1" if on else "0", None)])
        # R8-A 深字段：辐射求解器参数写回 <analysis_set>/<radiation>
        self.model.set_radiation_type(self.rad_type.currentData())
        self.model.set_radiation_param(
            "method", str(self.rad_method.currentData()))
        self.model.set_radiation_param(
            "max_particle", str(self.mc_rays.value()))
        self.model.set_radiation_param(
            "max_reflection", str(self.mc_reflect.value()))
        self.model.set_radiation_param(
            "smrt_rays", str(self.smrt_rays.value()))
        self.model.set_radiation_param(
            "max_group_num", str(self.group_max.value()))
        self.model.set_radiation_param(
            "calc_cycle", str(self.calc_cycle.value()))
        self.model.set_radiation_param(
            "solver_eps", f"{self.solver_eps.value():g}")
        self.model.set_radiation_param(
            "space_cycle", str(self.space_cycle.value()))
        if on and self.apply_all.isChecked():
            for p in self.model.parts():
                attr = (p.attribute or "").lower()
                if attr not in ("solid", "obstacle", ""):
                    continue
                el = self.model.find_part(p.name)
                if el is None:
                    continue
                c = _first(el, "rad_group_num")
                if c is None:
                    c = ET.SubElement(el, "rad_group_num")
                    c.tail = "\n         "
                set_text(c, str(gnum))


class _CwDiffusionPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Diffusion (species transport)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Diffusion analysis options (species concentration transport). "
            "Enable syncs the Analysis Types flag; the molecular diffusion "
            "coefficient and turbulent Schmidt number are stored as "
            "analysis settings.", self))
        g = QGroupBox("Diffusion", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider diffusion", g)
        aset = (model.analysis_set_value("diffusion", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("diffusion_enable", "F") == "T")
        self.n_species = QSpinBox(g)
        self.n_species.setRange(1, 10)
        self.coeff = QDoubleSpinBox(g)
        self.coeff.setRange(1e-12, 1.0)
        self.coeff.setDecimals(9)
        self.schmidt = QDoubleSpinBox(g)
        self.schmidt.setRange(0.01, 100.0)
        self.schmidt.setDecimals(3)
        for name, w, default in (
                ("diffusion_n_species", self.n_species, 1),
                ("diffusion_coefficient", self.coeff, 1.6e-5),
                ("diffusion_schmidt", self.schmidt, 0.9)):
            try:
                w.setValue(float(model.project_value(name, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        f.addRow(self.enable)
        f.addRow("Number of species", self.n_species)
        f.addRow("Molecular diffusion coefficient (m2/s)", self.coeff)
        f.addRow("Turbulent Schmidt number", self.schmidt)
        lay.addWidget(g)

        # I2: CNRM_MATERIAL rows (exA14-2/exB12) — species-material
        # mapping for the chemical species family
        cn = QGroupBox("CNRM_MATERIAL — species material map (exA14-2)",
                       self)
        cnl = QVBoxLayout(cn)
        self.cnrm_table = QTableWidget(0, 2, cn)
        self.cnrm_table.setHorizontalHeaderLabels(
            ["Material no", "Species no"])
        self.cnrm_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        cnl.addWidget(self.cnrm_table)
        crow2 = QHBoxLayout()
        self.cnrm_add = QPushButton("Add", cn)
        self.cnrm_del = QPushButton("Delete", cn)
        self.cnrm_add.clicked.connect(self._cnrm_add)
        self.cnrm_del.clicked.connect(self._cnrm_del)
        crow2.addWidget(self.cnrm_add)
        crow2.addStretch(1)
        crow2.addWidget(self.cnrm_del)
        cnl.addLayout(crow2)
        _cn = self.model.root.find("analysis_etc/cnrm")
        if _cn is not None:
            for r in _cn.findall("row"):
                self._cnrm_add(r.attrib.get("no", "1"),
                               r.attrib.get("val", "1"))
        lay.addWidget(cn)
        lay.addStretch(1)

    # -- I2: CNRM rows ----------------------------------------------------

    def _cnrm_add(self, no: str = "1", val: str = "1") -> None:
        r = self.cnrm_table.rowCount()
        self.cnrm_table.insertRow(r)
        self.cnrm_table.setItem(r, 0, QTableWidgetItem(str(no)))
        self.cnrm_table.setItem(r, 1, QTableWidgetItem(str(val)))

    def _cnrm_del(self) -> None:
        rows = self.cnrm_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.cnrm_table.removeRow(idx)

    def _cnrm_apply(self) -> None:
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("cnrm")
        if old is not None:
            aet.remove(old)
        if not self.cnrm_table.rowCount():
            return
        cn = ET.SubElement(aet, "cnrm")
        for r in range(self.cnrm_table.rowCount()):
            it = [self.cnrm_table.item(r, c) for c in range(2)]
            row = ET.SubElement(cn, "row")
            row.attrib["no"] = it[0].text() if it[0] else str(r + 1)
            row.attrib["val"] = it[1].text() if it[1] else "1"

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "diffusion_enable", "T" if on else "F")
        self._cnrm_apply()
        self.model.set_project_value(
            "diffusion_n_species", str(self.n_species.value()))
        self.model.set_project_value(
            "diffusion_coefficient", f"{self.coeff.value():g}")
        self.model.set_project_value(
            "diffusion_schmidt", f"{self.schmidt.value():g}")
        self.model.set_analysis_set_value("diffusion", "1" if on else "0")
        self.model.upsert_value(
            "diffusion", "Diffusion_default",
            [("diffusion_coefficient", f"{self.coeff.value():g}", "m2/s"),
             ("diffusion_schmidt", f"{self.schmidt.value():g}", None),
             ("n_species", str(self.n_species.value()), None)])


class _CwParticlePage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Particle (discrete phase tracking)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Particle tracking analysis. Enable syncs the Analysis Types "
            "flag; the interaction mode, diameter and density are stored "
            "as analysis settings.", self))
        g = QGroupBox("Particle", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider particle", g)
        aset = (model.analysis_set_value("particle", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("particle_enable", "F") == "T")
        self.mode = QComboBox(g)
        self.mode.addItems([
            "W/o inter-particle interaction",
            "With inter-particle interaction"])
        cur = model.project_value("particle_mode",
                                  "W/o inter-particle interaction")
        i = self.mode.findText(cur)
        if i >= 0:
            self.mode.setCurrentIndex(i)
        self.diameter = QDoubleSpinBox(g)
        self.diameter.setRange(1e-9, 1.0)
        self.diameter.setDecimals(9)
        self.density = QDoubleSpinBox(g)
        self.density.setRange(1.0, 1e6)
        self.density.setDecimals(3)
        for name, w, default in (
                ("particle_diameter", self.diameter, 1e-5),
                ("particle_density", self.density, 1000.0)):
            try:
                w.setValue(float(model.project_value(name, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        f.addRow(self.enable)
        f.addRow("Interaction model", self.mode)
        f.addRow("Particle diameter (m)", self.diameter)
        f.addRow("Particle density (kg/m3)", self.density)
        lay.addWidget(g)

        # ---- R8-A 深字段：粒子完整模型 ----
        # .s 实证 PCLE_CREATE 段（exA07-1 等）：粒径分布/个数率/初速等
        # 按序给出；XML 侧无 COM 保存实证，统一存 <value type='particle'>
        # Particle_default 的子元素 kv（字段名按 Solver 手册 PCLE_CREATE
        # 条目命名，标注「未实证，按手册定义」）。
        pf = model.value_fields("particle", "Particle_default")

        def _num(key: str, default: float, w) -> None:
            try:
                w.setValue(float(pf.get(key, default)))
            except (TypeError, ValueError):
                w.setValue(default)

        dg = QGroupBox("Particle Model (size distribution / drag / wall)", self)
        dfl = QFormLayout(dg)
        # 粒径分布类型（PCLE_CREATE 分布种类：0=均一/1=対数正規/2=Rosin-
        # Rammler；未实证，按手册定义）
        self.dia_dist = QComboBox(dg)
        for label, val in (("Uniform", "0"), ("Log-normal", "1"),
                           ("Rosin-Rammler", "2")):
            self.dia_dist.addItem(label, val)
        i = self.dia_dist.findData(pf.get("particle_distribution", "0"))
        self.dia_dist.setCurrentIndex(i if i >= 0 else 0)
        # 最小/最大/平均粒径（PCLE_CREATE 粒径三值；单位 m）
        self.dia_min = QDoubleSpinBox(dg)
        self.dia_min.setRange(1e-12, 1.0)
        self.dia_min.setDecimals(9)
        _num("particle_dia_min", 1e-5, self.dia_min)
        self.dia_max = QDoubleSpinBox(dg)
        self.dia_max.setRange(1e-12, 1.0)
        self.dia_max.setDecimals(9)
        _num("particle_dia_max", 1e-4, self.dia_max)
        self.dia_mean = QDoubleSpinBox(dg)
        self.dia_mean.setRange(1e-12, 1.0)
        self.dia_mean.setDecimals(9)
        _num("particle_dia_mean", 5e-5, self.dia_mean)
        # 对数正态标准差 / Rosin-Rammler 分布指数（未实证，按手册定义）
        self.dia_sigma = QDoubleSpinBox(dg)
        self.dia_sigma.setRange(0.01, 10.0)
        self.dia_sigma.setDecimals(3)
        _num("particle_sigma", 0.5, self.dia_sigma)
        # 电力模型（PCLE_CREATE IDRG：0=Stokes/1=Stokes+Cunningham/
        # 2=Newton/3=Schiller-Naumann；未实证，按手册定义）
        self.drag = QComboBox(dg)
        for label, val in (
                ("Stokes drag", "0"),
                ("Stokes with Cunningham correction", "1"),
                ("Newton drag", "2"),
                ("Schiller-Naumann drag", "3")):
            self.drag.addItem(label, val)
        i = self.drag.findData(pf.get("drag_model", "3"))
        self.drag.setCurrentIndex(i if i >= 0 else 3)
        # 壁面反弹系数：法向/切向（PCLE_CREATE 反弹率 EN/ET，0~1）
        self.restitution_n = QDoubleSpinBox(dg)
        self.restitution_n.setRange(0.0, 1.0)
        self.restitution_n.setDecimals(3)
        _num("wall_restitution_normal", 0.9, self.restitution_n)
        self.restitution_t = QDoubleSpinBox(dg)
        self.restitution_t.setRange(0.0, 1.0)
        self.restitution_t.setDecimals(3)
        _num("wall_restitution_tangent", 0.9, self.restitution_t)
        # 湍流扩散（随机轨道模型：0=off/1=on；未实证，按手册定义）
        self.turb_diff = QComboBox(dg)
        self.turb_diff.addItem("Off (deterministic)", "0")
        self.turb_diff.addItem("On (random walk)", "1")
        i = self.turb_diff.findData(pf.get("turbulent_diffusion", "1"))
        self.turb_diff.setCurrentIndex(i if i >= 0 else 1)
        # 随机轨道尝试数（未实证，按手册定义，默认 1）
        self.turb_tries = QSpinBox(dg)
        self.turb_tries.setRange(1, 10000)
        try:
            self.turb_tries.setValue(int(float(
                pf.get("turbulent_tries", "1"))))
        except (TypeError, ValueError):
            self.turb_tries.setValue(1)
        dfl.addRow("Diameter distribution", self.dia_dist)
        dfl.addRow("Min. diameter (m)", self.dia_min)
        dfl.addRow("Max. diameter (m)", self.dia_max)
        dfl.addRow("Mean diameter (m)", self.dia_mean)
        dfl.addRow("[Log-normal] sigma / [R-R] spread", self.dia_sigma)
        dfl.addRow("Drag model", self.drag)
        dfl.addRow("Wall restitution (normal)", self.restitution_n)
        dfl.addRow("Wall restitution (tangent)", self.restitution_t)
        dfl.addRow("Turbulent diffusion", self.turb_diff)
        dfl.addRow("Random-walk tries", self.turb_tries)
        lay.addWidget(dg)
        lay.addStretch(1)
        self._hook_family_ui()

    # -- C1: DEM interaction / particle condition storage -----------------

    _DEM_CONTACT = {1: "linear_spring_dashpot"}
    _DEM_ROLLING = {1: "simplified_linear"}

    def _commit_dem(self, *, contact_model: int = 1,
                    rolling_model: int = 1, it_scheme: int = 2,
                    detect_algorithm: int = 3, detect_cycle: int = 1,
                    n_factor: float = 1.2, min_reynolds: float = 1e-10,
                    stab_scale: float = 0.0, time_divide: int = 5,
                    max_loop: int = 100, recovery_scale: float = 0.1,
                    recovery_max: int = 100) -> None:
        """Write the DEM interaction block (Force between Particles
        family) into ``<analysis_etc><dem>`` — the official storage the
        LSOL_* .s sections are derived from (exA07-4 evidence)."""
        s = self.model.set_analysis_etc_child
        s("dem", "dem_motion", "1")
        s("dem", "dem_contact_model", str(int(contact_model)))
        s("dem", "dem_rolling_resistance_model", str(int(rolling_model)))
        s("dem", "dem_adhesion", "0")
        s("dem", "dem_it_scheme", str(int(it_scheme)))
        s("dem", "dem_detect_algorithm", str(int(detect_algorithm)))
        s("dem", "dem_detect_cycle", str(int(detect_cycle)))
        s("dem", "dem_detect_n_factor", f"{float(n_factor):g}")
        s("dem", "dem_min_reynolds", f"{float(min_reynolds):g}")
        s("dem", "dem_stab_scale", f"{float(stab_scale):g}")
        s("dem", "dem_time_divide", str(int(time_divide)))
        s("dem", "dem_max_loop", str(int(max_loop)))
        s("dem", "dem_recoverty_step_scale", f"{float(recovery_scale):g}")
        s("dem", "dem_recoverty_max", str(int(recovery_max)))

    def _commit_particle_condition(self, name: str, kind: str,
                                   region: str, applied_face: int = 0
                                   ) -> bool:
        """Create one ``<value type="particle_condition">`` — kind
        destruction (Particle Vanishment) and sedimentation
        (Particle Sedimentation) emit PCLE_HANDLING cards; other kinds
        are stored without emission (no card evidence)."""
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        if not self.model.upsert_value("particle_condition", name, [
                ("kind", kind, None),
                ("applied_face", str(int(applied_face)), None)]):
            return False
        self.model.bind_condition("region", region, name)
        return True

    # R4: particle family groups — storage-first records.
    _R4 = {"dem_gen": "dem_gen", "dem_restitution": "dem_restitution",
           "heat_source": "particle_heat_source",
           "fixed_velocity": "particle_velocity",
           "motion_udf": "particle_motion_udf",
           "statistics": "particle_statistics"}

    def _r4_set(self, key: str, field: str, value) -> None:
        self.model.set_analysis_set_value(
            f"{key}_{field}", str(value))

    def _r4_get(self, key: str, field: str, default: str = "") -> str:
        return self.model.analysis_set_value(f"{key}_{field}", default)

    def commit_particle_family(self, key: str, fields: dict) -> str:
        """Write a particle-family record; returns 'ok:key' for tests."""
        if key not in self._R4:
            raise ValueError(key)
        for f, v in fields.items():
            self._r4_set(self._R4[key], f, v)
        self._r4_set(self._R4[key], "_record",
                     ";".join(f"{f}={v}" for f, v in fields.items()))
        if hasattr(self, "pf_table"):
            self._pf_reload()
        return f"ok:{key}"

    def read_particle_family(self, key: str, fields: tuple) -> dict:
        return {f: self._r4_get(self._R4[key], f) for f in fields}

    # -- R4: S-level UI controls for the six particle families ------------

    _FAMILY_LABELS = {
        "heat_source": ("Particle heat source",
                        ("region", "power", "unit")),
        "fixed_velocity": ("Particle fixed velocity",
                           ("vx", "vy", "vz")),
        "motion_udf": ("Particle motion (user-defined)",
                       ("name",)),
        "statistics": ("Particle statistics", ("cycle",)),
        "dem_gen": ("DEM particle generation",
                    ("count", "radius")),
        "dem_restitution": ("DEM restitution",
                            ("normal", "tangential")),
    }

    def _particle_family_ui(self, lay) -> None:
        """Add a family-record editor table (name -> key/value pairs)."""
        self.pf_table = QTableWidget(0, 2, self)
        self.pf_table.setHorizontalHeaderLabels(["Family", "Record"])
        self.pf_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.pf_table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.pf_table, 1)
        self._pf_reload()

    def _pf_reload(self) -> None:
        self.pf_table.setRowCount(0)
        for key in self._R4:
            raw = self._r4_get(self._R4[key], "_record")
            if raw:
                r = self.pf_table.rowCount()
                self.pf_table.insertRow(r)
                self.pf_table.setItem(r, 0, QTableWidgetItem(key))
                self.pf_table.setItem(r, 1, QTableWidgetItem(raw))

    def _hook_family_ui(self):
        """Attach the family table into the page layout (A2)."""
        lay = self.layout()
        if lay is None:
            return
        self._particle_family_ui(lay)

    def apply(self) -> None:
        on = self.enable.isChecked()
        mode = self.mode.currentText()
        self.model.set_project_value(
            "particle_enable", "T" if on else "F")
        self.model.set_project_value("particle_mode", mode)
        self.model.set_project_value(
            "particle_diameter", f"{self.diameter.value():g}")
        self.model.set_project_value(
            "particle_density", f"{self.density.value():g}")
        self.model.set_analysis_set_value("particle", "1" if on else "0")
        # R8-A 深字段：粒子完整模型写回 Particle_default 的 kv 扩展
        self.model.upsert_value(
            "particle", "Particle_default",
            [("particle_mode", mode, None),
             ("particle_diameter", f"{self.diameter.value():g}", "m"),
             ("particle_density", f"{self.density.value():g}", "kg/m3"),
             ("particle_distribution",
              self.dia_dist.currentData(), None),
             ("particle_dia_min", f"{self.dia_min.value():g}", "m"),
             ("particle_dia_max", f"{self.dia_max.value():g}", "m"),
             ("particle_dia_mean", f"{self.dia_mean.value():g}", "m"),
             ("particle_sigma", f"{self.dia_sigma.value():g}", None),
             ("drag_model", self.drag.currentData(), None),
             ("wall_restitution_normal",
              f"{self.restitution_n.value():g}", None),
             ("wall_restitution_tangent",
              f"{self.restitution_t.value():g}", None),
             ("turbulent_diffusion",
              self.turb_diff.currentData(), None),
             ("turbulent_tries",
              str(self.turb_tries.value()), None)])


class _CwThermoregulationPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Thermoregulation model (JOS-2 comfort)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Thermoregulation model (human comfort, JOS-2 style). Enable "
            "syncs the Analysis Types flag; metabolic rate and clothing "
            "insulation are stored as analysis settings.", self))
        g = QGroupBox("Thermoregulation model", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider thermoregulation model", g)
        aset = (model.analysis_set_value("jos_model", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("jos_enable", "F") == "T")
        self.metabolic = QDoubleSpinBox(g)
        self.metabolic.setRange(0.0, 20.0)
        self.metabolic.setDecimals(1)
        self.clothing = QDoubleSpinBox(g)
        self.clothing.setRange(0.0, 5.0)
        self.clothing.setDecimals(2)
        for name, w, default in (
                ("jos_metabolic_rate", self.metabolic, 1.1),
                ("jos_clothing", self.clothing, 0.7)):
            try:
                w.setValue(float(model.project_value(name, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        f.addRow(self.enable)
        f.addRow("Metabolic rate (met)", self.metabolic)
        f.addRow("Clothing insulation (clo)", self.clothing)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "jos_enable", "T" if on else "F")
        self.model.set_project_value(
            "jos_metabolic_rate", f"{self.metabolic.value():g}")
        self.model.set_project_value(
            "jos_clothing", f"{self.clothing.value():g}")
        self.model.set_analysis_set_value("jos_model", "1" if on else "0")
        self.model.upsert_value(
            "jos_model", "JOS_default",
            [("metabolic_rate", f"{self.metabolic.value():g}", "met"),
             ("clothing", f"{self.clothing.value():g}", "clo")])


class _CwFreeSurfacePage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Free Surface conditions (MARS): Wave Generation,
    Wave Energy Attenuation Zone, Permeable Object, Foaming Resin (C6)."""

    _WAVE_KINDS = ("stokes3", "stokes5", "irregular", "solitary")

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Free surface (MARS) conditions. Wave Generation and the "
            "energy-attenuation zones emit SURF_WAVEGENE / SURF_POROUS "
            "cards from the official storage shapes.", self))
        self.tabs = tabs = QTabWidget(self)

        # ---- Wave Generation ----
        wg = QWidget()
        wl = QVBoxLayout(wg)
        self.wave_table = QTableWidget(0, 7, wg)
        self.wave_table.setHorizontalHeaderLabels(
            ["Name", "Kind", "Bias (m)", "Depth (m)", "Height (m)",
             "Period", "Parts"])
        self.wave_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.wave_table.setEditTriggers(QTableWidget.NoEditTriggers)
        wl.addWidget(self.wave_table, 1)
        wrow = QHBoxLayout()
        btn_wave = QPushButton("Wave Generation…", wg)
        btn_wave.clicked.connect(self._new_wave)
        wdel = QPushButton("Delete", wg)
        wdel.clicked.connect(self._wave_delete)
        wrow.addWidget(btn_wave)
        wrow.addStretch(1)
        wrow.addWidget(wdel)
        wl.addLayout(wrow)
        tabs.addTab(wg, "Wave Generation")

        # ---- Attenuation / Permeable / Foaming ----
        az = QWidget()
        al = QVBoxLayout(az)
        self.az_table = QTableWidget(0, 5, az)
        self.az_table.setHorizontalHeaderLabels(
            ["Name", "Kind", "Direction", "Fluid no", "Parts"])
        self.az_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.az_table.setEditTriggers(QTableWidget.NoEditTriggers)
        al.addWidget(self.az_table, 1)
        arow = QHBoxLayout()
        btn_att = QPushButton("Wave energy attenuation zone…", az)
        btn_att.clicked.connect(self._new_attenuation)
        btn_perm = QPushButton("Permeable object…", az)
        btn_perm.clicked.connect(self._new_permeable)
        adel = QPushButton("Delete", az)
        adel.clicked.connect(self._az_delete)
        arow.addWidget(btn_att)
        arow.addWidget(btn_perm)
        arow.addStretch(1)
        arow.addWidget(adel)
        al.addLayout(arow)
        al.addWidget(_note(
            "Permeable-object cards share the SURF_POROUS section with a "
            "different kind; the card layout has no corpus sample, so "
            "they are stored without emission.", az))
        tabs.addTab(az, "Permeable Object/Attenuation Zone")

        fm = QWidget()
        fl = QVBoxLayout(fm)
        fl.addWidget(_note(
            "Sets flow conditions of foaming resin (single-phase MARS). "
            "Valid when solidification/melting is not analyzed.", fm))
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Foaming rate", fm))
        self.foam_rate = QDoubleSpinBox(fm)
        self.foam_rate.setRange(-1e6, 1e6)
        self.foam_rate.setDecimals(6)
        self.foam_rate.setValue(1.0)
        frow.addWidget(self.foam_rate)
        btn_foam = QPushButton("Apply foaming resin", fm)
        btn_foam.clicked.connect(self._apply_foaming)
        frow.addWidget(btn_foam)
        frow.addStretch(1)
        fl.addLayout(frow)
        fl.addStretch(1)
        tabs.addTab(fm, "Foaming Resin")

        lay.addWidget(tabs, 1)
        self._reload()

    # -- commits (testable) -----------------------------------------------

    def _commit_wave(self, name: str, kind: str, bias: float,
                     depth: float, height: float, period: float,
                     parts: str) -> bool:
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("wave_gen", name, [
                ("kind", kind, None),
                ("angle", "0", None),
                ("bias", f"{float(bias):g}", "m"),
                ("depth", f"{float(depth):g}", "m"),
                ("height", f"{float(height):g}", "m"),
                ("period", f"{float(period):g}", None),
                ("num", "0", None)]):
            return False
        self.model.bind_condition("parts", parts, name)
        self._reload()
        return True

    def _commit_attenuation(self, name: str, direction: str,
                            fluid_no: int, decay: str, depth: float,
                            parts: str) -> bool:
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("surface_porous", name, [
                ("kind", "energy_decay", None),
                ("direction", direction, None),
                ("fluid_no", str(int(fluid_no)), None),
                ("decay", decay, None),
                ("depth", f"{float(depth):g}", "m")]):
            return False
        self.model.bind_condition("parts", parts, name)
        self._reload()
        return True

    def _commit_permeable(self, name: str, parts: str) -> bool:
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("surface_porous", name, [
                ("kind", "permeable", None)]):
            return False
        self.model.bind_condition("parts", parts, name)
        self._reload()
        return True

    def _apply_foaming(self) -> None:
        self.model.upsert_value("foaming", "FoamingResin1", [
            ("rate", f"{self.foam_rate.value():g}", None)])

    # -- dialog wrappers ---------------------------------------------------

    def _form_row(self, lay, label, widget):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(widget, 1)
        lay.addLayout(row)

    def _wave_dialog(self):
        from PyQt5.QtWidgets import (
            QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
            QLineEdit)
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Wave Generation)")
        lay = QVBoxLayout(dlg)
        self._wg_name = QLineEdit(dlg)
        self._form_row(lay, "Condition name", self._wg_name)
        self._wg_kind = QComboBox(dlg)
        self._wg_kind.addItems(list(self._WAVE_KINDS))
        self._form_row(lay, "Wave type", self._wg_kind)
        self._wg_bias = QDoubleSpinBox(dlg)
        self._wg_bias.setRange(-1e6, 1e6)
        self._wg_bias.setValue(7.0)
        self._form_row(lay, "Bias (m)", self._wg_bias)
        self._wg_depth = QDoubleSpinBox(dlg)
        self._wg_depth.setRange(0.0, 1e6)
        self._wg_depth.setValue(7.0)
        self._form_row(lay, "Depth (m)", self._wg_depth)
        self._wg_height = QDoubleSpinBox(dlg)
        self._wg_height.setRange(0.0, 1e6)
        self._wg_height.setValue(2.0)
        self._form_row(lay, "Height (m)", self._wg_height)
        self._wg_period = QDoubleSpinBox(dlg)
        self._wg_period.setRange(0.0, 1e6)
        self._wg_period.setValue(5.0)
        self._form_row(lay, "Period (s)", self._wg_period)
        self._wg_parts = QLineEdit(dlg)
        self._form_row(lay, "Source region (parts name)", self._wg_parts)
        dlg.addButton(QDialogButtonBox.Ok)
        return dlg

    def _new_wave(self) -> None:
        dlg = self._wave_dialog()
        if not dlg.exec_():
            return
        self._commit_wave(
            self._wg_name.text(), self._wg_kind.currentText(),
            self._wg_bias.value(), self._wg_depth.value(),
            self._wg_height.value(), self._wg_period.value(),
            self._wg_parts.text())

    def _new_attenuation(self) -> None:
        from PyQt5.QtWidgets import QInputDialog
        title = "Wave Energy Attenuation Zone"
        name, ok = QInputDialog.getText(self, title, "Condition name:")
        if not ok or not str(name).strip():
            return
        direction, okd = QInputDialog.getItem(
            self, title, "Direction:", ("-X", "+X"), 0, False)
        if not okd:
            return
        fluid_no, okn = QInputDialog.getInt(
            self, title, "Fluid no:", 2, 1, 9)
        if not okn:
            return
        decay, okc = QInputDialog.getText(
            self, title, "Decay coefficients (a,b,c,d):", "2,0,0,3")
        if not okc:
            return
        depth, okdp = QInputDialog.getDouble(
            self, title, "Depth (m)", 7.0, 0.0, 1e6, 6)
        if not okdp:
            return
        parts, okp = QInputDialog.getText(self, title, "Parts name:")
        if not okp:
            return
        self._commit_attenuation(str(name).strip(), str(direction),
                                 int(fluid_no), str(decay),
                                 float(depth), str(parts))

    def _new_permeable(self) -> None:
        from PyQt5.QtWidgets import QInputDialog
        title = "Permeable Object"
        name, ok = QInputDialog.getText(self, title, "Condition name:")
        if not ok or not str(name).strip():
            return
        parts, okp = QInputDialog.getText(self, title, "Parts name:")
        if not okp:
            return
        self._commit_permeable(str(name).strip(), str(parts))

    def _delete_value(self, vtype: str, name: str) -> None:
        from cabxml import _first
        for val in self.model.values_of_type(vtype):
            n = _first(val, "name")
            if n is not None and n.text and n.text.strip() == name:
                self.model.root.remove(val)
                break
        for c in list(self.model.conditions()):
            v = _first(c, "value")
            if v is not None and v.text and v.text.strip() == name:
                self.model.root.remove(c)

    def _wave_delete(self) -> None:
        row = self.wave_table.currentRow()
        if row >= 0:
            self._delete_value("wave_gen",
                               self.wave_table.item(row, 0).text())
        self._reload()

    def _az_delete(self) -> None:
        row = self.az_table.currentRow()
        if row >= 0:
            self._delete_value("surface_porous",
                               self.az_table.item(row, 0).text())
        self._reload()

    # -- table reload ------------------------------------------------------

    def _reload(self) -> None:
        from cabxml import _first

        def _row_map(vtype):
            rows: dict = {}
            for val in self.model.values_of_type(vtype):
                n = _first(val, "name")
                name = n.text.strip() if n is not None and n.text else ""
                if not name:
                    continue
                rows[name] = {c.tag: (c.text or "").strip() for c in val}
            for c in self.model.conditions():
                v = _first(c, "value")
                vname = v.text.strip() if v is not None and v.text else ""
                if vname not in rows:
                    continue
                for ch in c:
                    if ch.tag == "parts" and (ch.text or "").strip():
                        rows[vname].setdefault("_parts", []).append(
                            (ch.text or "").strip())
            return rows

        self.wave_table.setRowCount(0)
        for name, row in _row_map("wave_gen").items():
            r = self.wave_table.rowCount()
            self.wave_table.insertRow(r)
            for col, key in enumerate(("name", "kind", "bias", "depth",
                                       "height", "period")):
                self.wave_table.setItem(
                    r, col, QTableWidgetItem(row.get(key, "")))
            self.wave_table.setItem(
                r, 6, QTableWidgetItem(", ".join(row.get("_parts", []))))
        self.az_table.setRowCount(0)
        for name, row in _row_map("surface_porous").items():
            r = self.az_table.rowCount()
            self.az_table.insertRow(r)
            for col, key in enumerate(("name", "kind", "direction",
                                       "fluid_no")):
                self.az_table.setItem(
                    r, col, QTableWidgetItem(row.get(key, "")))
            self.az_table.setItem(
                r, 4, QTableWidgetItem(", ".join(row.get("_parts", []))))

    def apply(self) -> None:
        pass


class _CwCurrentPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Electric current (Joule heating)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Electric current analysis (Joule heating). Enable syncs the "
            "Analysis Types flag; the electrical conductivity is stored "
            "as an analysis setting.", self))
        g = QGroupBox("Electric current", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider electric current", g)
        aset = (model.analysis_set_value("current", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("current_enable", "F") == "T")
        self.conductivity = QDoubleSpinBox(g)
        self.conductivity.setRange(1e-12, 1e9)
        self.conductivity.setDecimals(6)
        try:
            self.conductivity.setValue(float(
                model.project_value("current_conductivity", "5.8e7")))
        except (TypeError, ValueError):
            self.conductivity.setValue(5.8e7)
        f.addRow(self.enable)
        f.addRow("Electrical conductivity (S/m)", self.conductivity)
        lay.addWidget(g)

        # C3: electrical contact resistance (5 modes per the manual); the
        # solver card has no corpus evidence — storage-only for now.
        ecr = QGroupBox("Electrical contact resistance", self)
        el = QVBoxLayout(ecr)
        self.ecr_table = QTableWidget(0, 4, ecr)
        self.ecr_table.setHorizontalHeaderLabels(
            ["Name", "Mode", "Param", "Regions"])
        self.ecr_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ecr_table.setEditTriggers(QTableWidget.NoEditTriggers)
        el.addWidget(self.ecr_table, 1)
        crow = QHBoxLayout()
        btn_ecr = QPushButton("Electrical contact resistance…", ecr)
        btn_ecr.clicked.connect(self._new_econtact)
        btn_del = QPushButton("Delete", ecr)
        btn_del.clicked.connect(self._ecr_delete)
        crow.addWidget(btn_ecr)
        crow.addStretch(1)
        crow.addWidget(btn_del)
        el.addLayout(crow)
        lay.addWidget(ecr)
        self._ecr_reload()

        # I1c: ECUR subsystem (exA12-1) — head flags, magnetic field,
        # per-material conductivity rows
        ec = QGroupBox("ECUR — electric current .s cards (exA12-1)", self)
        efl = QFormLayout(ec)
        self.ecur_i1 = QSpinBox(ec)
        self.ecur_i1.setRange(0, 9)
        self.ecur_i2 = QSpinBox(ec)
        self.ecur_i2.setRange(0, 9)
        self.ecur_i3 = QSpinBox(ec)
        self.ecur_i3.setRange(0, 9)
        irow = QHBoxLayout()
        for lab, w in (("i1", self.ecur_i1), ("i2", self.ecur_i2),
                       ("i3", self.ecur_i3)):
            irow.addWidget(QLabel(lab, ec))
            irow.addWidget(w)
        irow.addStretch(1)
        efl.addRow("Head flags", irow)
        self.ecur_mag_kind = QComboBox(ec)
        self.ecur_mag_kind.addItem("(off)", "")
        self.ecur_mag_kind.addItem("uniform", "uniform")
        self.ecur_mag_no = QSpinBox(ec)
        self.ecur_mag_no.setRange(0, 99)
        self.ecur_mag_region = QLineEdit(ec)
        self.ecur_mag_region.setPlaceholderText("@S:rbmx")
        self.ecur_mag_v1 = QDoubleSpinBox(ec)
        self.ecur_mag_v1.setRange(-1e9, 1e9)
        self.ecur_mag_v1.setDecimals(6)
        self.ecur_mag_v2 = QDoubleSpinBox(ec)
        self.ecur_mag_v2.setRange(-1e9, 1e9)
        self.ecur_mag_v2.setDecimals(6)
        efl.addRow("Magnetic field kind", self.ecur_mag_kind)
        efl.addRow("Magnetic field no", self.ecur_mag_no)
        efl.addRow("Magnetic field region", self.ecur_mag_region)
        mvrow = QHBoxLayout()
        mvrow.addWidget(self.ecur_mag_v1)
        mvrow.addWidget(self.ecur_mag_v2)
        mvrow.addStretch(1)
        efl.addRow("Magnetic field values", mvrow)
        self.ecur_table = QTableWidget(0, 2, ec)
        self.ecur_table.setHorizontalHeaderLabels(
            ["Material no", "Conductivity"])
        self.ecur_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        efl.addRow(self.ecur_table)
        eprow = QHBoxLayout()
        self.ecur_add = QPushButton("Add material", ec)
        self.ecur_del = QPushButton("Delete", ec)
        self.ecur_add.clicked.connect(self._ecur_add)
        self.ecur_del.clicked.connect(self._ecur_del)
        eprow.addWidget(self.ecur_add)
        eprow.addStretch(1)
        eprow.addWidget(self.ecur_del)
        efl.addRow(eprow)
        _ecur = self.model.root.find("analysis_etc/ecur")
        if _ecur is not None:
            try:
                self.ecur_i1.setValue(int(float(
                    _ecur.attrib.get("i1", "1"))))
                self.ecur_i2.setValue(int(float(
                    _ecur.attrib.get("i2", "0"))))
                self.ecur_i3.setValue(int(float(
                    _ecur.attrib.get("i3", "0"))))
            except ValueError:
                pass
            _mk = _ecur.attrib.get("mag_kind", "")
            _mi = self.ecur_mag_kind.findData(_mk)
            self.ecur_mag_kind.setCurrentIndex(_mi if _mi >= 0 else 0)
            self.ecur_mag_region.setText(_ecur.attrib.get("mag_region",
                                                          ""))
            try:
                self.ecur_mag_no.setValue(int(float(
                    _ecur.attrib.get("mag_no", "0"))))
                self.ecur_mag_v1.setValue(float(
                    _ecur.attrib.get("mag_v1", "0")))
                self.ecur_mag_v2.setValue(float(
                    _ecur.attrib.get("mag_v2", "0")))
            except ValueError:
                pass
            for p in _ecur.findall("prop"):
                self._ecur_add(p.attrib.get("no", "1"),
                               p.attrib.get("v", "0"))
        lay.addWidget(ec)
        lay.addStretch(1)

    _ECR_MODES = (
        ("insulation", "Insulation"),
        ("total_resistance", "Electrical contact resistance"),
        ("inverse_conductance", "Inverse of conductance (per unit area)"),
        ("conductivity_thickness", "Electrical conductivity and thickness"),
        ("no_resistance_current", "Electric current without resistance"),
    )

    # -- I1c: ECUR subsystem ----------------------------------------------

    @staticmethod
    def _table_text(table, row: int, col: int, default: str = "") -> str:
        it = table.item(row, col)
        return it.text().strip() if it is not None and it.text()             else default

    def _ecur_add(self, no: str = "1", v: str = "1e6") -> None:
        r = self.ecur_table.rowCount()
        self.ecur_table.insertRow(r)
        self.ecur_table.setItem(r, 0, QTableWidgetItem(str(no)))
        self.ecur_table.setItem(r, 1, QTableWidgetItem(str(v)))

    def _ecur_del(self) -> None:
        rows = self.ecur_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.ecur_table.removeRow(idx)

    def _ecur_apply(self) -> None:
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("ecur")
        if old is not None:
            aet.remove(old)
        props = [tuple(self._table_text(self.ecur_table, r, c)
                       for c in range(2))
                 for r in range(self.ecur_table.rowCount())]
        mag = self.ecur_mag_kind.currentData()
        if not props and not mag and not self.ecur_mag_region.text().strip():
            # all defaults -> nothing stored
            if (self.ecur_i1.value(), self.ecur_i2.value(),
                    self.ecur_i3.value()) == (1, 0, 0):
                return
        ec = ET.SubElement(aet, "ecur")
        ec.attrib.update(i1=str(self.ecur_i1.value()),
                         i2=str(self.ecur_i2.value()),
                         i3=str(self.ecur_i3.value()))
        if mag:
            ec.attrib.update(mag_kind=mag,
                             mag_no=str(self.ecur_mag_no.value()),
                             mag_region=self.ecur_mag_region.text().strip(),
                             mag_v1=f"{self.ecur_mag_v1.value():g}",
                             mag_v2=f"{self.ecur_mag_v2.value():g}")
        for no, v in props:
            p = ET.SubElement(ec, "prop")
            p.attrib.update(no=no or "1", v=v or "0")

    def _commit_econtact(self, name: str, mode: str, param: float,
                         region: str) -> bool:
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        if not self.model.upsert_value("econtact", name, [
                ("mode", mode, None),
                ("param", f"{float(param):g}", None)]):
            return False
        self.model.bind_condition("region", region, name)
        self._ecr_reload()
        return True

    def _new_econtact(self) -> None:
        from PyQt5.QtWidgets import QInputDialog
        title = "Electrical Contact Resistance"
        name, ok = QInputDialog.getText(self, title, "Condition name:")
        if not ok or not str(name).strip():
            return
        modes = [label for _k, label in self._ECR_MODES]
        mode_label, okm = QInputDialog.getItem(
            self, title, "Mode:", modes, 0, False)
        if not okm:
            return
        mode = next(k for k, label in self._ECR_MODES
                    if label == mode_label)
        param, okp = QInputDialog.getDouble(
            self, title, "Value", 0.0, -1e30, 1e30, 8)
        if not okp:
            return
        region, okr = QInputDialog.getItem(
            self, title, "Region:", self._ES_FACES, 0, False)
        if not okr:
            return
        self._commit_econtact(str(name).strip(), mode, float(param),
                              str(region))

    def _ecr_delete(self) -> None:
        row = self.ecr_table.currentRow()
        if row < 0:
            return
        name = self.ecr_table.item(row, 0).text()
        from cabxml import _first
        for val in self.model.values_of_type("econtact"):
            n = _first(val, "name")
            if n is not None and n.text and n.text.strip() == name:
                self.model.root.remove(val)
                break
        for c in list(self.model.conditions()):
            v = _first(c, "value")
            if v is not None and v.text and v.text.strip() == name:
                self.model.root.remove(c)
        self._ecr_reload()

    def _ecr_reload(self) -> None:
        from cabxml import _first
        labels = dict(self._ECR_MODES)
        rows: dict[str, dict] = {}
        for val in self.model.values_of_type("econtact"):
            n = _first(val, "name")
            name = n.text.strip() if n is not None and n.text else ""
            if not name:
                continue
            mode = _first(val, "mode")
            param = _first(val, "param")
            rows[name] = {
                "mode": labels.get((mode.text or "").strip()
                                   if mode is not None else "",
                                   (mode.text or "").strip()
                                   if mode is not None else ""),
                "param": (param.text or "").strip()
                if param is not None else "",
                "regions": [],
            }
        for c in self.model.conditions():
            v = _first(c, "value")
            vname = v.text.strip() if v is not None and v.text else ""
            if vname not in rows:
                continue
            for ch in c:
                if ch.tag == "region" and (ch.text or "").strip():
                    rows[vname]["regions"].append((ch.text or "").strip())
        self.ecr_table.setRowCount(0)
        for name, row in rows.items():
            r = self.ecr_table.rowCount()
            self.ecr_table.insertRow(r)
            for col, text in enumerate(
                    (name, row["mode"], row["param"],
                     ", ".join(row["regions"]))):
                self.ecr_table.setItem(r, col, QTableWidgetItem(text))

    def apply(self) -> None:
        self._ecur_apply()
        on = self.enable.isChecked()
        self.model.set_project_value(
            "current_enable", "T" if on else "F")
        self.model.set_project_value(
            "current_conductivity", f"{self.conductivity.value():g}")
        self.model.set_analysis_set_value("current", "1" if on else "0")
        self.model.upsert_value(
            "current", "Current_default",
            [("conductivity", f"{self.conductivity.value():g}", "S/m")])


class _CwElectrostaticPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Electrostatic field."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Electrostatic field analysis. Enable syncs the Analysis "
            "Types flag; the relative permittivity is stored as an "
            "analysis setting.", self))
        g = QGroupBox("Electrostatic field", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider electrostatic field", g)
        # STpre canonical storage: <analysis_etc><partcile_echarge> 1|2
        # (1 = es_field, each cycle; 2 = es_field_initial, start only);
        # the legacy flat analysis_set/electrostatic tag is kept in sync.
        ec = (model.analysis_etc_value("partcile_echarge", "")
              or "").strip()
        if ec in ("1", "2"):
            self.enable.setChecked(True)
        else:
            aset = (model.analysis_set_value("electrostatic", "")
                    or "").strip()
            if aset in ("1", "T", "t"):
                self.enable.setChecked(True)
            else:
                self.enable.setChecked(
                    model.project_value("electrostatic_enable", "F") == "T")
        self.timing = QComboBox(g)
        self.timing.addItems(
            ["Each cycle", "Only at calculation start"])
        self.timing.setCurrentIndex(0 if ec != "2" else 1)
        self.permittivity = QDoubleSpinBox(g)
        self.permittivity.setRange(1.0, 1e6)
        self.permittivity.setDecimals(3)
        try:
            self.permittivity.setValue(float(
                model.project_value("electrostatic_permittivity", "1.0")))
        except (TypeError, ValueError):
            self.permittivity.setValue(1.0)
        f.addRow(self.enable)
        f.addRow("Calculation timing", self.timing)
        f.addRow("Relative permittivity", self.permittivity)
        lay.addWidget(g)

        # C3: electric-potential boundary conditions — official <value
        # type="e_field"> storage (exA07-3); type emits ES_FIELD_BC cards.
        bc = QGroupBox("Electrostatic boundary conditions", self)
        bl = QVBoxLayout(bc)
        self.es_table = QTableWidget(0, 3, bc)
        self.es_table.setHorizontalHeaderLabels(
            ["Name", "Potential (V)", "Regions"])
        self.es_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.es_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bl.addWidget(self.es_table, 1)
        erow = QHBoxLayout()
        btn_pot = QPushButton("Electric potential…", bc)
        btn_pot.clicked.connect(self._new_e_potential)
        btn_movb = QPushButton("Fixed potential (moving object)…", bc)
        btn_movb.clicked.connect(self._new_e_movb)
        btn_del = QPushButton("Delete", bc)
        btn_del.clicked.connect(self._es_delete)
        erow.addWidget(btn_pot)
        erow.addWidget(btn_movb)
        erow.addStretch(1)
        erow.addWidget(btn_del)
        bl.addLayout(erow)
        lay.addWidget(bc)
        self._es_reload()
        lay.addStretch(1)

    _ES_FACES = ("Xmin面", "Xmax面", "Ymin面", "Ymax面", "Zmin面", "Zmax面")

    def _commit_e_potential(self, name: str, potential: float,
                            region: str, movb: bool = False) -> bool:
        """Create/update one ``<value type="e_field">`` condition."""
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        children = [("e_potential", f"{float(potential):g}", "V")]
        if movb:
            # MOVB_ESF_SORC (moving-object dielectric fixed potential):
            # storage marker only, card emission has no corpus evidence.
            children.append(("movb_fixed", "T", None))
        if not self.model.upsert_value("e_field", name, children):
            return False
        self.model.bind_condition("region", region, name)
        self._es_reload()
        return True

    def _es_pick(self, title: str):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, title, "Condition name:")
        if not ok or not str(name).strip():
            return None
        pot, okp = QInputDialog.getDouble(
            self, title, "Electric potential (V)", 0.0, -1e9, 1e9, 6)
        if not okp:
            return None
        region, okr = QInputDialog.getItem(
            self, title, "Region:", list(self._ES_FACES), 0, False)
        if not okr:
            return None
        return str(name).strip(), float(pot), str(region)

    def _new_e_potential(self) -> None:
        picked = self._es_pick("Electric Potential")
        if picked is None:
            return
        self._commit_e_potential(*picked)

    def _new_e_movb(self) -> None:
        picked = self._es_pick(
            "Electrostatic Field - Fixed Electric Potential")
        if picked is None:
            return
        self._commit_e_potential(picked[0], picked[1], picked[2],
                                 movb=True)

    def _es_delete(self) -> None:
        row = self.es_table.currentRow()
        if row < 0:
            return
        name = self.es_table.item(row, 0).text()
        from cabxml import _first
        for val in self.model.values_of_type("e_field"):
            n = _first(val, "name")
            if n is not None and n.text and n.text.strip() == name:
                self.model.root.remove(val)
                break
        for c in list(self.model.conditions()):
            v = _first(c, "value")
            if v is not None and v.text and v.text.strip() == name:
                self.model.root.remove(c)
        self._es_reload()

    def _es_reload(self) -> None:
        from cabxml import _first
        rows: dict[str, dict] = {}
        for val in self.model.values_of_type("e_field"):
            n = _first(val, "name")
            name = n.text.strip() if n is not None and n.text else ""
            if not name:
                continue
            pot = _first(val, "e_potential")
            rows[name] = {
                "pot": (pot.text or "").strip() if pot is not None else "",
                "movb": any(c.tag == "movb_fixed" for c in val),
                "regions": [],
            }
        for c in self.model.conditions():
            v = _first(c, "value")
            vname = v.text.strip() if v is not None and v.text else ""
            if vname not in rows:
                continue
            for ch in c:
                if ch.tag == "region" and (ch.text or "").strip():
                    rows[vname]["regions"].append((ch.text or "").strip())
        self.es_table.setRowCount(0)
        for name, row in rows.items():
            r = self.es_table.rowCount()
            self.es_table.insertRow(r)
            label = name + ("  [moving object]" if row["movb"] else "")
            for col, text in enumerate(
                    (label, row["pot"], ", ".join(row["regions"]))):
                self.es_table.setItem(r, col, QTableWidgetItem(text))

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "electrostatic_enable", "T" if on else "F")
        self.model.set_project_value(
            "electrostatic_permittivity", f"{self.permittivity.value():g}")
        self.model.set_analysis_etc_value(
            "partcile_echarge",
            "2" if on and self.timing.currentIndex() == 1 else
            "1" if on else "0")
        self.model.set_analysis_set_value(
            "electrostatic", "1" if on else "0")
        self.model.upsert_value(
            "electrostatic", "Electrostatic_default",
            [("permittivity", f"{self.permittivity.value():g}", None)])


class _CwVentilationPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Ventilation efficiency."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Ventilation efficiency analysis. Enable syncs the Analysis "
            "Types flag; the evaluation method is stored as an analysis "
            "setting.", self))
        g = QGroupBox("Ventilation efficiency", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider ventilation efficiency", g)
        aset = (model.analysis_set_value("ventilation", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("ventilation_enable", "F") == "T")
        self.method = QComboBox(g)
        self.method.addItems([
            "Age of air", "Local air exchange efficiency",
            "Contaminant removal efficiency"])
        cur = model.project_value("ventilation_method", "Age of air")
        i = self.method.findText(cur)
        if i >= 0:
            self.method.setCurrentIndex(i)
        f.addRow(self.enable)
        f.addRow("Evaluation method", self.method)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        method = self.method.currentText()
        self.model.set_project_value(
            "ventilation_enable", "T" if on else "F")
        self.model.set_project_value("ventilation_method", method)
        self.model.set_analysis_set_value(
            "ventilation", "1" if on else "0")
        self.model.upsert_value(
            "ventilation", "Ventilation_default",
            [("method", method, None)])


class _CwReactionPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Reaction (chemical species reaction)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Reaction analysis. Enable syncs the Analysis Types flag; "
            "the reaction mode and rate are stored as analysis settings.",
            self))
        g = QGroupBox("Reaction", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider reaction", g)
        aset = (model.analysis_set_value("reaction", "") or "").strip()
        if aset in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("reaction_enable", "F") == "T")
        self.mode = QComboBox(g)
        self.mode.addItems(["Single-step reaction", "Multi-step reaction"])
        cur = model.project_value("reaction_mode", "Single-step reaction")
        i = self.mode.findText(cur)
        if i >= 0:
            self.mode.setCurrentIndex(i)
        self.rate = QDoubleSpinBox(g)
        self.rate.setRange(0.0, 1e12)
        self.rate.setDecimals(6)
        try:
            self.rate.setValue(float(model.project_value("reaction_rate", "0")))
        except (TypeError, ValueError):
            self.rate.setValue(0.0)
        f.addRow(self.enable)
        f.addRow("Reaction mode", self.mode)
        f.addRow("Reaction rate (1/s)", self.rate)
        lay.addWidget(g)

        # ---- R8-A 深字段：多步反应速率表 ----
        # .s 实证 REAC_REGION 段（exA04-1 等）：速率行为
        # 'A, n, E, T_ref, order...'（Arrhenius 三参数 + 级数）；XML 侧
        # 无 COM 保存实证，每步存一个 <value type='reaction'>
        # Reaction_step{N} 子元素 kv（未实证，按手册定义）。
        rg = QGroupBox("Multi-step Rate Constants (Arrhenius)", self)
        rgl = QVBoxLayout(rg)
        self.step_table = QTableWidget(0, 5, rg)
        self.step_table.setHorizontalHeaderLabels([
            "Rate constant A (1/s)", "Temp. exponent n",
            "Activation energy E (J/mol)", "Reference temp. (K)",
            "Reaction order (-)"])
        self.step_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        rgl.addWidget(self.step_table, 1)
        btns = QHBoxLayout()
        self.step_add = QPushButton("Add step", rg)
        self.step_add.clicked.connect(
            lambda: self._step_insert(
                self.step_table.rowCount(),
                1.0, 0.0, 1.0e4, 0.0, 1.0))
        self.step_del = QPushButton("Remove last", rg)
        self.step_del.clicked.connect(self._step_remove_last)
        btns.addWidget(self.step_add)
        btns.addWidget(self.step_del)
        btns.addStretch(1)
        rgl.addLayout(btns)
        lay.addWidget(rg)
        self._steps_load()

        # I1c: chemical species subsystem — SNAM registers / CDIF
        # diffusivity / REAC_REGION reactions / VDFU_REGION sources
        # (emitters byte-verified against exA04-1 / exA03-1)
        chem = QGroupBox("Chemical species (.s: SNAM/CDIF/REAC/VDFU)",
                         self)
        cl = QVBoxLayout(chem)
        sn = QFormLayout()
        self.snam_r1 = QLineEdit(chem)
        self.snam_r2 = QLineEdit(chem)
        self.snam_p1 = QLineEdit(chem)
        self.snam_p2 = QLineEdit(chem)
        snrow = QHBoxLayout()
        for lab, w in (("R1", self.snam_r1), ("R2", self.snam_r2),
                       ("P1", self.snam_p1), ("P2", self.snam_p2)):
            snrow.addWidget(QLabel(lab, chem))
            snrow.addWidget(w)
        sn.addRow("Species register names (blank = off)", snrow)
        cl.addLayout(sn)
        self.dif_table = QTableWidget(0, 2, chem)
        self.dif_table.setHorizontalHeaderLabels(
            ["Species", "Diffusivity"])
        self.dif_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        cl.addWidget(self.dif_table)
        drow = QHBoxLayout()
        self.dif_add = QPushButton("Add diffusivity", chem)
        self.dif_del = QPushButton("Delete", chem)
        self.dif_add.clicked.connect(self._dif_add)
        self.dif_del.clicked.connect(self._dif_del)
        drow.addWidget(self.dif_add)
        drow.addStretch(1)
        drow.addWidget(self.dif_del)
        cl.addLayout(drow)
        self.reac_table = QTableWidget(0, 5, chem)
        self.reac_table.setHorizontalHeaderLabels(
            ["No", "Formula", "Params (a,b,c,e,x1,x2,x3)",
             "Tail", "Region"])
        self.reac_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        cl.addWidget(self.reac_table)
        rrow = QHBoxLayout()
        self.reac_add = QPushButton("Add reaction", chem)
        self.reac_del2 = QPushButton("Delete", chem)
        self.reac_add.clicked.connect(self._reac_add)
        self.reac_del2.clicked.connect(self._reac_del)
        rrow.addWidget(self.reac_add)
        rrow.addStretch(1)
        rrow.addWidget(self.reac_del2)
        cl.addLayout(rrow)
        self.vdfu_table = QTableWidget(0, 4, chem)
        self.vdfu_table.setHorizontalHeaderLabels(
            ["Species", "Name", "Value", "Region"])
        self.vdfu_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        cl.addWidget(self.vdfu_table)
        vrow = QHBoxLayout()
        self.vdfu_add = QPushButton("Add source", chem)
        self.vdfu_del = QPushButton("Delete", chem)
        self.vdfu_add.clicked.connect(self._vdfu_add)
        self.vdfu_del.clicked.connect(self._vdfu_del)
        vrow.addWidget(self.vdfu_add)
        vrow.addStretch(1)
        vrow.addWidget(self.vdfu_del)
        cl.addLayout(vrow)
        self._chem_load()
        lay.addWidget(chem)
        lay.addStretch(1)

    # -- I1c: chemical species subsystem ----------------------------------

    def _chem_load(self) -> None:
        chem = self.model.root.find("analysis_etc/chem")
        if chem is None:
            return
        snam = chem.find("snam")
        if snam is not None:
            self.snam_r1.setText(snam.attrib.get("r1", ""))
            self.snam_r2.setText(snam.attrib.get("r2", ""))
            self.snam_p1.setText(snam.attrib.get("p1", ""))
            self.snam_p2.setText(snam.attrib.get("p2", ""))
        for d in chem.findall("dif"):
            self._dif_add(d.attrib.get("species", ""),
                          d.attrib.get("value", "0"))
        for r in chem.findall("reac"):
            self._reac_add(
                r.attrib.get("no", "1"), r.attrib.get("formula", ""),
                r.attrib.get("a", "0"), r.attrib.get("b", "0"),
                r.attrib.get("c", "0"), r.attrib.get("e", "0"),
                r.attrib.get("x1", "0"), r.attrib.get("x2", "0"),
                r.attrib.get("x3", "0"), r.attrib.get("tail", "0"),
                r.attrib.get("region", ""))
        for v in chem.findall("vdfu"):
            self._vdfu_add(v.attrib.get("species", ""),
                           v.attrib.get("name", ""),
                           v.attrib.get("value", "0"),
                           v.attrib.get("region", ""))

    @staticmethod
    def _table_text(table, row: int, col: int, default: str = "") -> str:
        it = table.item(row, col)
        return it.text().strip() if it is not None and it.text() \
            else default

    def _dif_add(self, species: str = "", value: str = "0") -> None:
        r = self.dif_table.rowCount()
        self.dif_table.insertRow(r)
        self.dif_table.setItem(r, 0, QTableWidgetItem(str(species)))
        self.dif_table.setItem(r, 1, QTableWidgetItem(str(value)))

    def _dif_del(self) -> None:
        rows = self.dif_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.dif_table.removeRow(idx)

    def _reac_add(self, no: str = "1", formula: str = "", a: str = "0",
                  b: str = "0", c: str = "0", e: str = "0", x1: str = "0",
                  x2: str = "0", x3: str = "0", tail: str = "0",
                  region: str = "") -> None:
        r = self.reac_table.rowCount()
        self.reac_table.insertRow(r)
        params = ",".join((a, b, c, e, x1, x2, x3))
        for col, text in enumerate((no, formula, params, tail, region)):
            self.reac_table.setItem(r, col, QTableWidgetItem(text))

    def _reac_del(self) -> None:
        rows = self.reac_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.reac_table.removeRow(idx)

    def _vdfu_add(self, species: str = "", name: str = "",
                  value: str = "0", region: str = "") -> None:
        r = self.vdfu_table.rowCount()
        self.vdfu_table.insertRow(r)
        for col, text in enumerate((species, name, value, region)):
            self.vdfu_table.setItem(r, col, QTableWidgetItem(text))

    def _vdfu_del(self) -> None:
        rows = self.vdfu_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.vdfu_table.removeRow(idx)

    def _chem_apply(self) -> None:
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("chem")
        if old is not None:
            aet.remove(old)
        names = [self.snam_r1.text().strip(),
                 self.snam_r2.text().strip(),
                 self.snam_p1.text().strip(),
                 self.snam_p2.text().strip()]
        difs = [(self._table_text(self.dif_table, r, 0),
                 self._table_text(self.dif_table, r, 1))
                for r in range(self.dif_table.rowCount())]
        reacs = [tuple(self._table_text(self.reac_table, r, c)
                       for c in range(5))
                 for r in range(self.reac_table.rowCount())]
        vdfus = [tuple(self._table_text(self.vdfu_table, r, c)
                       for c in range(4))
                 for r in range(self.vdfu_table.rowCount())]
        if not any(names) and not difs and not reacs and not vdfus:
            return
        chem = ET.SubElement(aet, "chem")
        if any(names):
            sn = ET.SubElement(chem, "snam")
            sn.attrib.update(r1=names[0], r2=names[1],
                             p1=names[2], p2=names[3])
        for species, value in difs:
            d = ET.SubElement(chem, "dif")
            d.attrib.update(species=species, value=value)
        for no, formula, params, tail, region in reacs:
            p = [x.strip() for x in params.split(",")] + ["0"] * 7
            r = ET.SubElement(chem, "reac")
            r.attrib.update(no=no or "1", formula=formula,
                            a=p[0], b=p[1], c=p[2], e=p[3],
                            x1=p[4], x2=p[5], x3=p[6], tail=tail or "0",
                            region=region)
        for species, name, value, region in vdfus:
            v = ET.SubElement(chem, "vdfu")
            v.attrib.update(species=species, name=name, value=value,
                            region=region)

    def _steps_load(self) -> None:
        """从 Reaction_step{N} value 重建多步速率表。"""

        def _f(fields: dict, key: str, default: float) -> float:
            try:
                return float(fields.get(key, default))
            except (TypeError, ValueError):
                return default

        self.step_table.setRowCount(0)
        steps = []
        for v in self.model.values_of_type("reaction"):
            n = next((c for c in v if c.tag == "name"), None)
            name = (n.text or "").strip() if n is not None else ""
            if not name.startswith("Reaction_step"):
                continue
            try:
                idx = int(name[len("Reaction_step"):])
            except ValueError:
                continue
            fields = {c.tag: (c.text or "").strip()
                      for c in v if c.tag != "name"}
            steps.append((idx, fields))
        for _idx, f in sorted(steps):
            self._step_insert(
                self.step_table.rowCount(),
                _f(f, "rate_constant", 1.0),
                _f(f, "temp_exponent", 0.0),
                _f(f, "activation_energy", 1.0e4),
                _f(f, "ref_temp", 0.0),
                _f(f, "reaction_order", 1.0))

    def _step_insert(self, row: int, a: float, n: float, e: float,
                     tref: float, order: float) -> None:
        self.step_table.insertRow(row)
        for col, val in enumerate((a, n, e, tref, order)):
            self.step_table.setItem(
                row, col, QTableWidgetItem(f"{val:g}"))

    def _step_remove_last(self) -> None:
        row = self.step_table.rowCount()
        if row > 0:
            self.step_table.removeRow(row - 1)

    def _commit_reaction_pdf(self, name: str, region: str) -> bool:
        """C6: [Condition (Reaction - PDF)] — PDF-method reaction region.

        Storage-only (no corpus evidence for the card)."""
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        if not self.model.upsert_value("reaction_pdf", name, [
                ("method", "pdf", None)]):
            return False
        self.model.bind_condition("region", region, name)
        return True

    def apply(self) -> None:
        on = self.enable.isChecked()
        mode = self.mode.currentText()
        self.model.set_project_value(
            "reaction_enable", "T" if on else "F")
        self.model.set_project_value("reaction_mode", mode)
        self.model.set_project_value(
            "reaction_rate", f"{self.rate.value():g}")
        self.model.set_analysis_set_value("reaction", "1" if on else "0")
        self.model.upsert_value(
            "reaction", "Reaction_default",
            [("reaction_mode", mode, None),
             ("reaction_rate", f"{self.rate.value():g}", "1/s")])
        self._chem_apply()
        # R8-A 深字段：多步速率表写回 Reaction_step{N}（步数减少时删多余）
        rows = self.step_table.rowCount()
        for i in range(rows):
            def _cell(r: int, c: int, default: str = "0") -> str:
                it = self.step_table.item(r, c)
                return it.text().strip() if it and it.text().strip() \
                    else default
            self.model.upsert_value(
                "reaction", f"Reaction_step{i + 1}",
                [("rate_constant", _cell(i, 0, "1"), "1/s"),
                 ("temp_exponent", _cell(i, 1, "0"), None),
                 ("activation_energy", _cell(i, 2, "0"), "J/mol"),
                 ("ref_temp", _cell(i, 3, "0"), "K"),
                 ("reaction_order", _cell(i, 4, "1"), None)])
        i = rows + 1
        while self.model.delete_value(f"Reaction_step{i}"):
            i += 1


class _CwFusionPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Solidification/melting."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Solidification/melting analysis. Enable syncs the Analysis "
            "Types flag; solidus/liquidus temperature and latent heat are "
            "stored as analysis settings.", self))
        g = QGroupBox("Solidification/melting", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider solidification/melting", g)
        if model.analysis_etc_section("fusion") is not None:
            self.enable.setChecked(True)
        else:
            aset = (model.analysis_set_value("fusion", "") or "").strip()
            if aset in ("1", "T", "t"):
                self.enable.setChecked(True)
            else:
                self.enable.setChecked(
                    model.project_value("fusion_enable", "F") == "T")
        self.solidus = QDoubleSpinBox(g)
        self.solidus.setRange(-273.15, 10000.0)
        self.solidus.setDecimals(2)
        self.liquidus = QDoubleSpinBox(g)
        self.liquidus.setRange(-273.15, 10000.0)
        self.liquidus.setDecimals(2)
        self.latent = QDoubleSpinBox(g)
        self.latent.setRange(0.0, 1e9)
        self.latent.setDecimals(2)
        for name, w, default in (
                ("fusion_solidus", self.solidus, 0.0),
                ("fusion_liquidus", self.liquidus, 0.0),
                ("fusion_latent_heat", self.latent, 334000.0)):
            etc = model.analysis_etc_child("fusion", name.replace("fusion_", ""), "")
            raw = etc or model.project_value(name, str(default))
            try:
                w.setValue(float(raw))
            except (TypeError, ValueError):
                w.setValue(default)
        f.addRow(self.enable)
        f.addRow("Solidus temperature (C)", self.solidus)
        f.addRow("Liquidus temperature (C)", self.liquidus)
        f.addRow("Latent heat (J/kg)", self.latent)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "fusion_enable", "T" if on else "F")
        self.model.set_project_value(
            "fusion_solidus", f"{self.solidus.value():g}")
        self.model.set_project_value(
            "fusion_liquidus", f"{self.liquidus.value():g}")
        self.model.set_project_value(
            "fusion_latent_heat", f"{self.latent.value():g}")
        if on:
            self.model.ensure_analysis_etc_section("fusion")
            self.model.set_analysis_etc_child(
                "fusion", "solidus", f"{self.solidus.value():g}", unit="C")
            self.model.set_analysis_etc_child(
                "fusion", "liquidus", f"{self.liquidus.value():g}", unit="C")
            self.model.set_analysis_etc_child(
                "fusion", "latent_heat", f"{self.latent.value():g}",
                unit="J/kg")
        else:
            self.model.remove_analysis_etc_section("fusion")
        self.model.set_analysis_set_value("fusion", "1" if on else "0")
        self.model.upsert_value(
            "fusion", "Fusion_default",
            [("solidus", f"{self.solidus.value():g}", "C"),
             ("liquidus", f"{self.liquidus.value():g}", "C"),
             ("latent_heat", f"{self.latent.value():g}", "J/kg")])


class _CwLampPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Lamp (artificial light heat source)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Lamp (artificial light) analysis. Enable syncs the Analysis "
            "Types flag; the lamp model and luminous flux are stored as "
            "analysis settings.", self))
        g = QGroupBox("Lamp", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider lamp", g)
        if model.analysis_etc_section("artificial_light") is not None:
            self.enable.setChecked(True)
        else:
            aset = (model.analysis_set_value("artificial_light", "")
                    or "").strip()
            if aset in ("1", "T", "t"):
                self.enable.setChecked(True)
            else:
                self.enable.setChecked(
                    model.project_value("lamp_enable", "F") == "T")
        self.model_type = QComboBox(g)
        self.model_type.addItems([
            "Point source", "Line source", "Area source"])
        cur = (model.analysis_etc_child(
            "artificial_light", "lamp_model", "")
            or model.project_value("lamp_model", "Point source"))
        i = self.model_type.findText(cur)
        if i >= 0:
            self.model_type.setCurrentIndex(i)
        self.flux = QDoubleSpinBox(g)
        self.flux.setRange(0.0, 1e9)
        self.flux.setDecimals(2)
        try:
            flux_raw = (model.analysis_etc_child(
                "artificial_light", "lamp_flux", "")
                or model.project_value("lamp_flux", "0"))
            self.flux.setValue(float(flux_raw))
        except (TypeError, ValueError):
            self.flux.setValue(0.0)
        f.addRow(self.enable)
        f.addRow("Lamp model", self.model_type)
        f.addRow("Luminous flux (lm)", self.flux)
        lay.addWidget(g)
        lay.addStretch(1)

    def _commit_laser(self, name: str, total_luminosity: float,
                      flux_density: float, region: str) -> bool:
        """C6: [Condition (Laser)] — lighting source + heat release.

        Storage-only: the laser solver card has no corpus sample
        (DEV_PLAN §23 C6)."""
        name = (name or "").strip()
        region = (region or "").strip()
        if not name or not region:
            return False
        if not self.model.upsert_value("laser", name, [
                ("total_luminosity", f"{float(total_luminosity):g}", "W"),
                ("flux_density", f"{float(flux_density):g}", "W/m2")]):
            return False
        self.model.bind_condition("region", region, name)
        return True

    def apply(self) -> None:
        on = self.enable.isChecked()
        mtype = self.model_type.currentText()
        self.model.set_project_value(
            "lamp_enable", "T" if on else "F")
        self.model.set_project_value("lamp_model", mtype)
        self.model.set_project_value("lamp_flux", f"{self.flux.value():g}")
        if on:
            self.model.ensure_analysis_etc_section("artificial_light")
            self.model.set_analysis_etc_child(
                "artificial_light", "lamp_model", mtype)
            self.model.set_analysis_etc_child(
                "artificial_light", "lamp_flux", f"{self.flux.value():g}",
                unit="lm")
        else:
            self.model.remove_analysis_etc_section("artificial_light")
        self.model.set_analysis_set_value(
            "artificial_light", "1" if on else "0")
        self.model.upsert_value(
            "artificial_light", "Lamp_default",
            [("lamp_model", mtype, None),
             ("lamp_flux", f"{self.flux.value():g}", "lm")])


class _CwPcmPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Phase change material."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Phase change material analysis. Enable syncs the Analysis "
            "Types flag; the melting temperature and latent heat are "
            "stored as analysis settings.", self))
        g = QGroupBox("Phase change material", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider phase change material", g)
        # STpre canonical storage: <analysis_etc><phase_change_material/>
        # (SetAnalysisType "pcm", COM probe 2026-08-15); the legacy flat
        # analysis_set/pcm tag is kept in sync for older readers.
        if model.analysis_etc_section("phase_change_material") is not None:
            self.enable.setChecked(True)
        else:
            aset = (model.analysis_set_value("pcm", "") or "").strip()
            if aset in ("1", "T", "t"):
                self.enable.setChecked(True)
            else:
                self.enable.setChecked(
                    model.project_value("pcm_enable", "F") == "T")
        self.melting = QDoubleSpinBox(g)
        self.melting.setRange(-273.15, 10000.0)
        self.melting.setDecimals(2)
        self.latent = QDoubleSpinBox(g)
        self.latent.setRange(0.0, 1e9)
        self.latent.setDecimals(2)
        for name, w, default in (
                ("pcm_melting_temp", self.melting, 28.0),
                ("pcm_latent_heat", self.latent, 200000.0)):
            try:
                w.setValue(float(model.project_value(name, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        f.addRow(self.enable)
        f.addRow("Melting temperature (C)", self.melting)
        f.addRow("Latent heat (J/kg)", self.latent)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "pcm_enable", "T" if on else "F")
        self.model.set_project_value(
            "pcm_melting_temp", f"{self.melting.value():g}")
        self.model.set_project_value(
            "pcm_latent_heat", f"{self.latent.value():g}")
        if on:
            self.model.ensure_analysis_etc_section("phase_change_material")
        else:
            self.model.remove_analysis_etc_section("phase_change_material")
        self.model.set_analysis_set_value("pcm", "1" if on else "0")
        self.model.upsert_value(
            "pcm", "PCM_default",
            [("melting_temp", f"{self.melting.value():g}", "C"),
             ("latent_heat", f"{self.latent.value():g}", "J/kg")])

# ---------------------------------------------------------------------------
# P1-3: analysis types with STpre <analysis_etc> storage (2025.2 COM probe)
# ---------------------------------------------------------------------------
class _CwPlantCanopyPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Plant canopy (vegetation resistance).

    STpre keeps the flag in <analysis_etc><plant_resistance>
    (SetAnalysisType "plant_resistance"); the canopy conditions
    (leaf area density / drag coefficient) are plant_canopy source
    conditions bound to regions from the Source Condition page.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Plant canopy analysis models the flow resistance and "
            "transpiration of vegetation. Enable writes STpre's "
            "plant_resistance analysis flag; the canopy conditions (leaf "
            "area density, drag coefficient) are created in the Source "
            "Condition page and bound to regions.", self))
        g = QGroupBox("Plant canopy", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider plant canopy", g)
        on = (model.analysis_etc_value("plant_resistance", "0")
              or "0").strip()
        if on in ("1", "T", "t"):
            self.enable.setChecked(True)
        else:
            self.enable.setChecked(
                model.project_value("plant_canopy_enable", "F") == "T")
        f.addRow(self.enable)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "plant_canopy_enable", "T" if on else "F")
        self.model.set_analysis_etc_value(
            "plant_resistance", "1" if on else "0")


# ---------------------------------------------------------------------------
# I1b: LES turbulence page — LES_INIT + LES_OPTION
# (emitters byte-verified against exB18; LESM lives in the Solver Control
#  tab of _CwSolverPage, same analysis_set tag)
# ---------------------------------------------------------------------------
class _CwLesPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - LES (large-eddy simulation) initialisation and
    options."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "LES analysis. LESM (model selector) is on the Solver "
            "Parameters → Solver Control tab; this page carries the "
            "initialisation field and the option table.", self))

        init = QGroupBox("LES_INIT — initial turbulence field (exB18)",
                         self)
        il = QFormLayout(init)
        self.init_enable = QCheckBox("Consider LES initialisation", init)
        li = model.root.find("analysis_etc/les_init")
        self.init_enable.setChecked(li is not None)
        self.init_method = QComboBox(init)
        self.init_method.addItem("random", "random")
        self.init_region = QLineEdit(init)
        self.init_name = QLineEdit(init)
        self.init_r1 = QDoubleSpinBox(init)
        self.init_r2 = QDoubleSpinBox(init)
        self.init_r3 = QDoubleSpinBox(init)
        for w in (self.init_r1, self.init_r2, self.init_r3):
            w.setRange(-1e9, 1e9)
            w.setDecimals(6)
        self.init_r1.setValue(1.0)
        self.init_r2.setValue(3.0)
        self.init_r3.setValue(3.0)
        if li is not None:
            def _t(tag, default=""):
                c = li.find(tag)
                return (c.text or "").strip() if c is not None else default
            _mi = self.init_method.findData(_t("method", "random"))
            self.init_method.setCurrentIndex(_mi if _mi >= 0 else 0)
            self.init_region.setText(_t("region"))
            self.init_name.setText(_t("name"))
            try:
                self.init_r1.setValue(float(_t("r1", "1.0")))
                self.init_r2.setValue(float(_t("r2", "3.0")))
                self.init_r3.setValue(float(_t("r3", "3.0")))
            except ValueError:
                pass
        il.addRow(self.init_enable)
        il.addRow("Method", self.init_method)
        il.addRow("Name (comment)", self.init_name)
        il.addRow("Scale 1 (turb. energy)", self.init_r1)
        il.addRow("Scale 2", self.init_r2)
        il.addRow("Scale 3", self.init_r3)
        il.addRow("Driver region", self.init_region)
        lay.addWidget(init)

        drv = QGroupBox("DRIVER_REGION — LES inflow driver (exB18/exB20a)",
                        self)
        dl = QFormLayout(drv)
        self.drv_stage = QComboBox(drv)
        self.drv_stage.addItem("fully-developed", "fully-developed")
        self.drv_stage.addItem("developing", "developing")
        self.drv_dir = QComboBox(drv)
        self.drv_dir.addItem("positive_x", "positive_x")
        self.drv_dir.addItem("negative_x", "negative_x")
        self.drv_dir.addItem("positive_y", "positive_y")
        self.drv_dir.addItem("negative_y", "negative_y")
        self.drv_dir.addItem("positive_z", "positive_z")
        self.drv_dir.addItem("negative_z", "negative_z")
        self.drv_kind = QComboBox(drv)
        self.drv_kind.addItem("velocity", "velocity")
        self.drv_kind.addItem("script", "script")
        self.drv_name = QLineEdit(drv)
        self.drv_value = QDoubleSpinBox(drv)
        self.drv_value.setRange(-1e9, 1e9)
        self.drv_value.setDecimals(6)
        self.drv_direction_line = QLineEdit(drv)
        self.drv_direction_line.setPlaceholderText("z-direction")
        self.drv_params = QLineEdit(drv)
        self.drv_params.setPlaceholderText("1,0")
        self.drv_region = QLineEdit(drv)
        dl.addRow("Stage", self.drv_stage)
        dl.addRow("Direction", self.drv_dir)
        dl.addRow("Kind", self.drv_kind)
        dl.addRow("Name (comment)", self.drv_name)
        dl.addRow("Inflow velocity", self.drv_value)
        dl.addRow("[script] Direction line", self.drv_direction_line)
        dl.addRow("[script] Params", self.drv_params)
        dl.addRow("Driver region(s, csv)", self.drv_region)
        _ld = model.root.find("analysis_etc/les_driver")
        if _ld is not None:
            _si = self.drv_stage.findData(_ld.attrib.get("stage",
                                                         "fully-developed"))
            self.drv_stage.setCurrentIndex(_si if _si >= 0 else 0)
            _di = self.drv_dir.findData(_ld.attrib.get("direction",
                                                       "positive_x"))
            self.drv_dir.setCurrentIndex(_di if _di >= 0 else 0)
            _ki = self.drv_kind.findData(_ld.attrib.get("kind",
                                                        "velocity"))
            self.drv_kind.setCurrentIndex(_ki if _ki >= 0 else 0)
            self.drv_name.setText(_ld.attrib.get("name", ""))
            try:
                self.drv_value.setValue(float(
                    _ld.attrib.get("value", "0") or 0))
            except ValueError:
                pass
            self.drv_direction_line.setText(
                _ld.attrib.get("direction_line", "z-direction"))
            self.drv_params.setText(_ld.attrib.get("params", "1,0"))
            self.drv_region.setText(_ld.attrib.get("region", ""))
        lay.addWidget(drv)

        opt = QGroupBox("LES_OPTION — option table (exB18)", self)
        ol = QVBoxLayout(opt)
        self.opt_table = QTableWidget(0, 2, opt)
        self.opt_table.setHorizontalHeaderLabels(["Option", "Value"])
        self.opt_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        ol.addWidget(self.opt_table, 1)
        orow = QHBoxLayout()
        btn_add = QPushButton("Add", opt)
        btn_add.clicked.connect(self._opt_add)
        btn_del = QPushButton("Delete", opt)
        btn_del.clicked.connect(self._opt_del)
        orow.addWidget(btn_add)
        orow.addStretch(1)
        orow.addWidget(btn_del)
        ol.addLayout(orow)
        lo = model.root.find("analysis_etc/les_option")
        if lo is not None:
            for c in lo:
                if c.text and c.text.strip():
                    self._opt_add(c.tag, c.text.strip())
        lay.addWidget(opt)
        lay.addStretch(1)

    def _opt_add(self, keyword: str = "", value: str = "1") -> None:
        r = self.opt_table.rowCount()
        self.opt_table.insertRow(r)
        self.opt_table.setItem(r, 0, QTableWidgetItem(keyword or ""))
        self.opt_table.setItem(r, 1, QTableWidgetItem(str(value)))

    def _opt_del(self) -> None:
        rows = self.opt_table.selectionModel().selectedRows()
        for idx in sorted((i.row() for i in rows), reverse=True):
            self.opt_table.removeRow(idx)

    def apply(self) -> None:
        import xml.etree.ElementTree as ET
        aet = self.model.ensure_analysis_etc()
        old = aet.find("les_init")
        if old is not None:
            aet.remove(old)
        if self.init_enable.isChecked():
            li = ET.SubElement(aet, "les_init")
            ET.SubElement(li, "method").text = \
                self.init_method.currentData()
            ET.SubElement(li, "name").text = self.init_name.text().strip()
            ET.SubElement(li, "r1").text = f"{self.init_r1.value():g}"
            ET.SubElement(li, "r2").text = f"{self.init_r2.value():g}"
            ET.SubElement(li, "r3").text = f"{self.init_r3.value():g}"
            ET.SubElement(li, "region").text = \
                self.init_region.text().strip()
        old = aet.find("les_option")
        if old is not None:
            aet.remove(old)
        rows = {}
        for r in range(self.opt_table.rowCount()):
            k_it = self.opt_table.item(r, 0)
            v_it = self.opt_table.item(r, 1)
            k = k_it.text().strip() if k_it else ""
            v = v_it.text().strip() if v_it else ""
            if k and v:
                rows[k] = v
        if rows:
            lo = ET.SubElement(aet, "les_option")
            for k, v in rows.items():
                ET.SubElement(lo, k).text = v
        old = aet.find("les_driver")
        if old is not None:
            aet.remove(old)
        region = self.drv_region.text().strip()
        if region:
            ld = ET.SubElement(aet, "les_driver")
            ld.attrib.update(
                stage=self.drv_stage.currentData(),
                direction=self.drv_dir.currentData(),
                kind=self.drv_kind.currentData(),
                name=self.drv_name.text().strip(),
                region=region)
            if self.drv_kind.currentData() == "script":
                ld.attrib.update(
                    direction_line=self.drv_direction_line.text().strip(),
                    params=self.drv_params.text().strip() or "1,0")
            else:
                ld.attrib["value"] = f"{self.drv_value.value():g}"


class _CwMovingBodyPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Moving object (STpre move_body analysis).

    analysis_set tags verified against STpre 2025.2 COM:
      moving_body = 1 (move_body) | 2 (move_body_t, with heat transfer)
      moving_body_file = 0 (S file) | 1 (external file)
      moving_body_option (SetMoveBodyOption serialization; kept "")
      list_position  (>0: cycle interval of position list output, 0: off)
      gap_filling    (1: consider gaps between objects)
    Motion definitions (rotation/translation tables) are part-level
    attributes edited in the model tree (Edit Solid) - documented.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Moving object analysis moves solid parts through the fluid "
            "domain. Enable writes STpre's moving_body flag; per-part "
            "motion definitions (rotation axis, velocity tables) are part "
            "attributes set from the model tree.", self))
        g = QGroupBox("Moving object", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider moving object", g)
        mv = (model.analysis_set_value("moving_body", "0") or "0").strip()
        self.enable.setChecked(mv in ("1", "2"))
        self.with_heat = QCheckBox("With heat transfer (move_body_t)", g)
        self.with_heat.setChecked(mv == "2")
        self.enable.toggled.connect(self.with_heat.setEnabled)
        self.with_heat.setEnabled(self.enable.isChecked())
        self.list_pos = QSpinBox(g)
        self.list_pos.setRange(0, 1000000)
        try:
            self.list_pos.setValue(int(float(
                model.analysis_set_value("list_position", "0") or "0")))
        except (TypeError, ValueError):
            self.list_pos.setValue(0)
        self.gap_fill = QCheckBox("Consider gaps between objects", g)
        self.gap_fill.setChecked(
            (model.analysis_set_value("gap_filling", "0")
             or "0").strip() in ("1", "T"))
        f.addRow(self.enable)
        f.addRow("", self.with_heat)
        f.addRow("Position list output cycle (0: off)", self.list_pos)
        f.addRow("", self.gap_fill)
        lay.addWidget(g)
        lay.addStretch(1)
        self._mo_humidity_heat_ui()

    # -- C7: moving-object conditions (exA09-4 storage shapes) -----------

    def _commit_6dof(self, name: str, label: str, parts: str,
                     move_kind: str = "free", rotate_kind: str = "free",
                     forces=(0.0, 0.0, 0.0)) -> bool:
        """6DOF rigid-body motion — ``<value type="body_move_6dof">``
        bound via ``<parts>`` (exA09-4); emits the MOVB_CONTROL dynamical
        entry + DYNA_MOTION block."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        f = [float(v) for v in forces[:3]]
        while len(f) < 3:
            f.append(0.0)
        if not self.model.upsert_value("body_move_6dof", name, [
                ("label", (label or name).strip(), None),
                ("move_kind", move_kind, None),
                ("initial_v_x", "0", "m/s"), ("force_x", f"{f[0]:g}", "N"),
                ("initial_v_y", "0", "m/s"), ("force_y", f"{f[1]:g}", "N"),
                ("initial_v_z", "0", "m/s"), ("force_z", f"{f[2]:g}", "N"),
                ("rotate_kind", rotate_kind, None)]):
            return False
        return self.model.bind_condition("parts", parts, name)

    def _commit_repulsion(self, name: str, parts: str,
                          coefficient: float = 1.0) -> bool:
        """Moving-object repulsion (C7) — storage-only, no card sample."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("body_repulsion", name, [
                ("coefficient", f"{float(coefficient):g}", None)]):
            return False
        return self.model.bind_condition("parts", parts, name)

    def _commit_mo_mass_transfer(self, name: str, parts: str,
                                 transfer: float) -> bool:
        """Moving-object mass transfer (C7) — storage-only, no card
        sample."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("mo_mass_transfer", name, [
                ("transfer", f"{float(transfer):g}", "m/s")]):
            return False
        return self.model.bind_condition("parts", parts, name)

    # R4 leftover: MO humidity + contact-face heat transfer
    def _commit_mo_humidity(self, name: str, parts: str,
                            humidity: float) -> bool:
        """Moving-object humidity boundary (storage-only; no card
        evidence)."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("mo_humidity", name, [
                ("humidity", f"{float(humidity):.12g}", "%")]):
            return False
        return self.model.bind_condition("parts", parts, name)

    def _commit_mo_contact_heat(self, name: str, parts: str,
                                coefficient: float) -> bool:
        """Moving-object contact-face heat transfer (storage-only)."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("mo_contact_heat", name, [
                ("coefficient", f"{float(coefficient):.12g}",
                 "W/(m2.K)")]):
            return False
        return self.model.bind_condition("parts", parts, name)

    # A2: MO humidity / contact-face heat UI group
    def _mo_humidity_heat_ui(self) -> None:
        from PyQt5.QtWidgets import QLineEdit, QDoubleSpinBox, QPushButton
        g = QGroupBox("Moving-object humidity / contact heat", self)
        f = QFormLayout(g)
        self.mo_hum_name = QLineEdit(g)
        f.addRow("Condition name", self.mo_hum_name)
        self.mo_hum_value = QDoubleSpinBox(g)
        self.mo_hum_value.setRange(0.0, 100.0)
        self.mo_hum_value.setDecimals(2)
        f.addRow("Humidity (%)", self.mo_hum_value)
        btn1 = QPushButton("Apply humidity", g)
        btn1.clicked.connect(self._mo_hum_apply)
        f.addRow(btn1)
        self.mo_ct_name = QLineEdit(g)
        f.addRow("Condition name", self.mo_ct_name)
        self.mo_ct_value = QDoubleSpinBox(g)
        self.mo_ct_value.setRange(0.0, 1e9)
        self.mo_ct_value.setDecimals(4)
        f.addRow("Heat transfer coefficient (W/(m2.K))", self.mo_ct_value)
        btn2 = QPushButton("Apply contact heat", g)
        btn2.clicked.connect(self._mo_ct_apply)
        f.addRow(btn2)
        lay = self.layout()
        if lay is not None:
            lay.addWidget(g)
            lay.addStretch(1)

    def _mo_hum_apply(self) -> None:
        self._commit_mo_humidity(
            self.mo_hum_name.text().strip() or "MOHum1", "MovingObject",
            self.mo_hum_value.value())

    def _mo_ct_apply(self) -> None:
        self._commit_mo_contact_heat(
            self.mo_ct_name.text().strip() or "MOCont1", "MovingObject",
            self.mo_ct_value.value())

    def apply(self) -> None:
        on = self.enable.isChecked()
        mv = ("2" if on and self.with_heat.isChecked() else
              "1" if on else "0")
        self.model.set_analysis_set_value("moving_body", mv)
        self.model.set_analysis_set_value("moving_body_file", "0")
        if not (self.model.analysis_set_value(
                "moving_body_option", "")):
            self.model.set_analysis_set_value("moving_body_option", "")
        self.model.set_analysis_set_value(
            "list_position", str(int(self.list_pos.value())))
        self.model.set_analysis_set_value(
            "gap_filling", "1" if self.gap_fill.isChecked() else "0")


class _CwMarangoniPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Marangoni convection.

    STpre 2025.2 stores the analysis in
    <analysis_etc><marangoni><temp_coeff> (SetAnalysisType
    "marangoni" writes temp_coeff 0).  The MARANGONI condition value
    carries the temperature coefficient multiplied by -1.0 (N/(m.K)).
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Marangoni convection analysis adds surface-tension driven "
            "flow at fluid surfaces. Enable creates STpre's marangoni "
            "analysis section; the temperature coefficient of surface "
            "tension (N/(m.K)) is stored as temp_coeff and exported as a "
            "marangoni condition.", self))
        g = QGroupBox("Marangoni convection", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider Marangoni convection", g)
        sec = model.analysis_etc_section("marangoni")
        self.enable.setChecked(sec is not None)
        self.coeff = QDoubleSpinBox(g)
        self.coeff.setRange(-1.0, 1.0)
        self.coeff.setDecimals(6)
        self.coeff.setSingleStep(0.0001)
        try:
            self.coeff.setValue(float(model.analysis_etc_child(
                "marangoni", "temp_coeff", "0") or "0"))
        except (TypeError, ValueError):
            self.coeff.setValue(0.0)
        f.addRow(self.enable)
        f.addRow("Temperature coefficient (N/(m.K))", self.coeff)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "marangoni_enable", "T" if on else "F")
        self.model.set_project_value(
            "marangoni_temp_coeff", f"{self.coeff.value():g}")
        if on:
            self.model.set_analysis_etc_child(
                "marangoni", "temp_coeff", f"{self.coeff.value():g}")
            self.model.upsert_value(
                "marangoni", "Marangoni_default",
                [("temp_coeff", f"{self.coeff.value():g}", "N/(m.K)")])
        else:
            self.model.remove_analysis_etc_section("marangoni")


# STpre default block written by SetAnalysisType("topopt", "T")
_TOPOPT_DEFAULTS = (
    ("penalty_type", "1", None),
    ("penalty_lamda", "0", None),
    ("solver_type", "1", None),
    ("scale_factor", "100,100,100", None),
    ("thermal_conductivity_type", "2", None),
    ("thermal_conductivity_ratio", "0", None),
    ("topo_opti_projection_flag", "F", None),
    ("topo_opti_projection_type", "1", None),
    ("topo_opti_proj_sharp", "0", None),
    ("topo_opti_proj_sharp_updatetype", "0", None),
    ("topo_opti_proj_sharp_increment", "0", None),
    ("topo_opti_proj_sharp_interval", "0", None),
    ("topo_opti_proj_sharp_final", "0", None),
    ("topo_opti_proj_center", "0.5", None),
    ("topo_opti_filter_flag", "F", None),
    ("topo_opti_filter_type", "2", None),
    ("topo_opti_filter_helm_rad_x", "0", "m"),
    ("topo_opti_filter_helm_rad_y", "0", "m"),
    ("topo_opti_filter_helm_rad_z", "0", "m"),
    ("topo_opti_filter_convol_rad", "0", "m"),
    ("topo_opti_filter_max_cycle", "0", None),
    ("topo_opti_filter_error", "0", None),
    ("topo_opti_material_interp_flag", "F", None),
    ("topo_opti_material_interp_curv", "0", None),
    ("topo_opti_material_interp_curv_updatetype", "0", None),
    ("topo_opti_material_interp_curv_increment", "0", None),
    ("topo_opti_material_interp_curv_interval", "0", None),
    ("topo_opti_material_interp_curv_final", "0", None),
    ("topo_opti_energy_interp_flag", "F", None),
    ("topo_opti_energy_interp_type", "1", None),
    ("topo_opti_energy_interp_convex", "3", None),
    ("topo_opti_energy_interp_convex_updatetype", "1", None),
    ("topo_opti_energy_interp_convex_increment", "1", None),
    ("topo_opti_energy_interp_convex_interval", "100", None),
    ("topo_opti_energy_interp_convex_final", "5", None),
    ("topo_opti_harmonic_mean_cond_flag", "F", None),
    ("topo_opti_harmonic_mean_cond_type", "0", None),
    ("topo_opti_exclude_solid_conv_flag", "F", None),
    ("topo_opti_exclude_solid_conv_type", "0", None),
    ("topo_opti_krylov_flag", "F", None),
    ("topo_opti_krylov_max_projection", "960", None),
    ("topo_opti_krylov_max_restart", "10", None),
    ("topo_opti_krylov_newton_error", "0.1", None),
    ("topo_opti_krylov_newton_error_max", "0.999", None),
    ("topo_opti_krylov_nonlinear_error", "0.0001", None),
    ("topo_opti_krylov_nonlinear_max_iter", "10", None),
)


class _CwTopologyOptiPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Topology optimization (STpre topopt).

    Enable writes the complete STpre default topology_optimize block
    under <analysis_etc>; key settings (penalty, solver, thermal
    conductivity, filter, Krylov) are exposed, the rest keep STpre
    defaults (verified against a SetAnalysisType("topopt","T") save).
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Topology optimization (adjoint-based) removes low-relevance "
            "solid cells to minimize an objective. Enable writes STpre's "
            "topology_optimize analysis block with its defaults; the "
            "optimization target and design region are set on the target "
            "condition of the analysis.", self))
        g = QGroupBox("Topology optimization", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider topology optimization", g)
        sec = model.analysis_etc_section("topology_optimize")
        self.enable.setChecked(sec is not None)

        def child(tag, default=""):
            return (model.analysis_etc_child(
                "topology_optimize", tag, default) or default).strip()

        self.penalty = QSpinBox(g)
        self.penalty.setRange(1, 2)
        self.solver = QSpinBox(g)
        self.solver.setRange(1, 2)
        self.tc_type = QSpinBox(g)
        self.tc_type.setRange(1, 2)
        self.tc_ratio = QDoubleSpinBox(g)
        self.tc_ratio.setRange(0.0, 1e6)
        self.tc_ratio.setDecimals(4)
        self.filter_on = QCheckBox("Helmholtz density filter", g)
        self.filter_type = QSpinBox(g)
        self.filter_type.setRange(1, 2)
        self.helm_rx = QDoubleSpinBox(g)
        self.helm_rx.setRange(0.0, 1e3)
        self.helm_rx.setDecimals(6)
        self.helm_rx.setSuffix(" m")
        self.helm_ry = QDoubleSpinBox(g)
        self.helm_ry.setRange(0.0, 1e3)
        self.helm_ry.setDecimals(6)
        self.helm_ry.setSuffix(" m")
        self.helm_rz = QDoubleSpinBox(g)
        self.helm_rz.setRange(0.0, 1e3)
        self.helm_rz.setDecimals(6)
        self.helm_rz.setSuffix(" m")
        self.krylov_on = QCheckBox("Krylov subspace solver", g)
        defaults = {t: v for t, v, _u in _TOPOPT_DEFAULTS}
        for w, tag, cast in (
                (self.penalty, "penalty_type", int),
                (self.solver, "solver_type", int),
                (self.tc_type, "thermal_conductivity_type", int),
                (self.tc_ratio, "thermal_conductivity_ratio", float),
                (self.filter_type, "topo_opti_filter_type", int),
                (self.helm_rx, "topo_opti_filter_helm_rad_x", float),
                (self.helm_ry, "topo_opti_filter_helm_rad_y", float),
                (self.helm_rz, "topo_opti_filter_helm_rad_z", float)):
            try:
                w.setValue(cast(child(tag, defaults.get(tag, "0"))))
            except (TypeError, ValueError):
                pass
        self.filter_on.setChecked(child("topo_opti_filter_flag", "F")
                                  in ("T", "1"))
        self.krylov_on.setChecked(child("topo_opti_krylov_flag", "F")
                                  in ("T", "1"))
        f.addRow(self.enable)
        f.addRow("Penalty type", self.penalty)
        f.addRow("Solver type", self.solver)
        f.addRow("Thermal conductivity model", self.tc_type)
        f.addRow("Thermal conductivity ratio", self.tc_ratio)
        f.addRow(self.filter_on)
        f.addRow("Filter type", self.filter_type)
        f.addRow("Filter radius X", self.helm_rx)
        f.addRow("Filter radius Y", self.helm_ry)
        f.addRow("Filter radius Z", self.helm_rz)
        f.addRow(self.krylov_on)
        lay.addWidget(g)
        lay.addStretch(1)

    # -- C8: design space (exA28-1_step2 storage shape) -------------------

    def _commit_design_space(self, name: str, parts: str,
                             vol_constraint_type: str = "upper",
                             vol_constraint: float = 0.12) -> bool:
        """[Condition (Design Space)] — volume-constrained design space
        for topology optimization (``<value type="topo_design_space">``);
        emits the TOPOPT_REGION card via the objective-function linkage."""
        name = (name or "").strip()
        parts = (parts or "").strip()
        if not name or not parts:
            return False
        if not self.model.upsert_value("topo_design_space", name, [
                ("vol_constraint_type", vol_constraint_type, None),
                ("vol_constraint", f"{float(vol_constraint):g}", None)]):
            return False
        return self.model.bind_condition("parts", parts, name)

    def _commit_area_objective(self, name: str, value: float,
                               weight: float) -> bool:
        """R4-18: Area Objective Function — ICNS=2 weighted objective
        record (TOPOPT_REGION branch b)."""
        name = (name or "").strip()
        if not name:
            return False
        return self.model.upsert_value("topo_area_obj", name, [
            ("obj_constraint", f"{float(value):.12g}", None),
            ("weight", f"{float(weight):.12g}", None)])

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "topology_opti_enable", "T" if on else "F")
        if not on:
            self.model.remove_analysis_etc_section("topology_optimize")
            return
        for tag, text, unit in _TOPOPT_DEFAULTS:
            if self.model.analysis_etc_child(
                    "topology_optimize", tag, "!") == "!":
                self.model.set_analysis_etc_child(
                    "topology_optimize", tag, text, unit=unit)
        overrides = (
            ("penalty_type", str(self.penalty.value())),
            ("solver_type", str(self.solver.value())),
            ("thermal_conductivity_type", str(self.tc_type.value())),
            ("thermal_conductivity_ratio", f"{self.tc_ratio.value():g}"),
            ("topo_opti_filter_flag",
             "T" if self.filter_on.isChecked() else "F"),
            ("topo_opti_filter_type", str(self.filter_type.value())),
            ("topo_opti_filter_helm_rad_x", f"{self.helm_rx.value():g}"),
            ("topo_opti_filter_helm_rad_y", f"{self.helm_ry.value():g}"),
            ("topo_opti_filter_helm_rad_z", f"{self.helm_rz.value():g}"),
            ("topo_opti_krylov_flag",
             "T" if self.krylov_on.isChecked() else "F"),
        )
        for tag, text in overrides:
            self.model.set_analysis_etc_child(
                "topology_optimize", tag, text,
                unit="m" if "helm_rad" in tag else None)


class _CwAirconPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Air conditioner unit (STpre aircon analysis).

    The analysis flag lives in analysis_set/aircon_model (T/F, as in the
    official template).  Air conditioner unit models themselves are parts
    (CreateAirconModel equivalent); capacity / air flow / COP are
    parameters of those parts.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Air conditioner unit analysis couples the AC unit models "
            "(parts) with the room airflow. Enable writes the aircon_model "
            "analysis flag; the AC unit capacity and air flow are set on "
            "the air conditioner parts in the model tree.", self))
        g = QGroupBox("Air conditioner unit", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider air conditioner unit", g)
        v = (model.analysis_set_value("aircon_model", "F") or "F").strip()
        self.enable.setChecked(v in ("1", "T", "t"))
        f.addRow(self.enable)
        lay.addWidget(g)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_analysis_set_value(
            "aircon_model", "T" if on else "F")
        self.model.set_project_value(
            "aircon_model_enable", "T" if on else "F")

# ---------------------------------------------------------------------------
# P1-3: Evaporation (free surface) - analysis_etc/evaporation storage
# (COM-probed 2026-08-15: SetAnalysisType('evap','T') writes
#  <analysis_etc><evaporation><liquid_temp/><gas_temp/><latent_heat/>)
# ---------------------------------------------------------------------------
class _CwEvaporationPage(QWidget if _HAS_GUI else object):
    """Condition Wizard - Evaporation (free surf.)."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Evaporation analysis (requires the Free surface analysis). "
            "Enable writes STpre's evaporation section (bubble point / dew "
            "point / latent heat); the recoil pressure model and atomic "
            "mass are stored alongside.", self))
        g = QGroupBox("Evaporation (free surf.)", self)
        f = QFormLayout(g)
        self.enable = QCheckBox("Consider evaporation", g)
        sec = model.analysis_etc_section("evaporation")
        self.enable.setChecked(sec is not None)

        def child(tag, default=""):
            return (model.analysis_etc_child(
                "evaporation", tag, default) or default).strip()

        self.liquid_temp = QDoubleSpinBox(g)
        self.liquid_temp.setRange(-273.15, 10000.0)
        self.liquid_temp.setDecimals(2)
        self.gas_temp = QDoubleSpinBox(g)
        self.gas_temp.setRange(-273.15, 10000.0)
        self.gas_temp.setDecimals(2)
        self.latent = QDoubleSpinBox(g)
        self.latent.setRange(0.0, 1e9)
        self.latent.setDecimals(2)
        self.latent_unit = QComboBox(g)
        self.latent_unit.addItems(["J/kg", "kJ/kg"])
        self.recoil = QComboBox(g)
        self.recoil.addItems([
            "Not considered (0)", "Molecular dynamics (1)",
            "Clausius-Clapeyron (2)"])
        self.atomic = QDoubleSpinBox(g)
        self.atomic.setRange(0.0, 1e6)
        self.atomic.setDecimals(6)
        for w, tag, cast, default in (
                (self.liquid_temp, "liquid_temp", float, 100.0),
                (self.gas_temp, "gas_temp", float, 100.0),
                (self.latent, "latent_heat", float, 2256000.0),
                (self.atomic, "atomic_mass", float, 0.018015)):
            try:
                w.setValue(cast(child(tag, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        r = child("recoil_model", "0")
        self.recoil.setCurrentIndex(int(r) if r.isdigit()
                                    and 0 <= int(r) <= 2 else 0)
        f.addRow(self.enable)
        f.addRow("Bubble point (C)", self.liquid_temp)
        f.addRow("Dew point (C)", self.gas_temp)
        f.addRow("Latent heat", self.latent)
        f.addRow("Latent heat unit", self.latent_unit)
        f.addRow("Recoil pressure model", self.recoil)
        f.addRow("Atomic mass of liquid (kg/mol)", self.atomic)

        # ---- R8-A 深字段：自由面 MARS / VOF 求解参数 ----
        # 存储实证于 STpre 2025.2 COM 保存样本（probe_work/cwtypes2_mars.cab
        # 与 cwtypes2_vof.cab 的 <analysis_etc><free_surf type='mars'|'vof'>
        # 属性集）。属性名与默认值对齐样本；取值域按 Solver 手册
        # SURF_CONTROL 命令（NFS=5 分步数、EPSVF=1e-4 VOF 阈值、IFILL/FILL
        # 填充率检查 0/2/12 与 95%）。filling_check / fill_rate 两个属性名
        # 未实证（样本缺省未写出），按 SURF_CONTROL 条目命名。
        fg = QGroupBox("Free Surface (MARS / VOF)", self)
        ff = QFormLayout(fg)
        self.fs_enable = QCheckBox("Consider free surface analysis", fg)
        self.fs_enable.setChecked(
            model.analysis_etc_section("free_surf") is not None)
        self.fs_method = QComboBox(fg)
        self.fs_method.addItem("MARS method", "mars")
        self.fs_method.addItem("VOF method", "vof")
        cur_fs = model.free_surf_type() or "mars"
        i = self.fs_method.findData(cur_fs)
        self.fs_method.setCurrentIndex(i if i >= 0 else 0)
        # 接触角（SUFS_REGION contactangle；XML 属性 contact 实证，默认 90）
        self.fs_contact = QSpinBox(fg)
        self.fs_contact.setRange(0, 180)
        self.fs_contact.setValue(int(float(
            model.free_surf_attr("contact", "90"))))
        # VOF 阈值（SURF_CONTROL EPSVF，默认 1e-4）：样本 cutoff 为
        # 'EPSVF,0.5,eps_save' 三元组，仅暴露并回写第 1 值，其余原样保留
        self.fs_cutoff = QDoubleSpinBox(fg)
        self.fs_cutoff.setRange(1e-9, 1.0)
        self.fs_cutoff.setDecimals(6)
        try:
            self.fs_cutoff.setValue(float(
                (model.free_surf_attr("cutoff", "0.0001,0.5,1e-06")
                 .split(",") + ["0.0001"])[0]))
        except ValueError:
            self.fs_cutoff.setValue(1e-4)
        # VOF 值检查周期（SURF_CONTROL NCKVF；XML 属性 vof_list_cycle 实证）
        self.fs_check_cycle = QSpinBox(fg)
        self.fs_check_cycle.setRange(0, 10000000)
        self.fs_check_cycle.setValue(int(float(
            model.free_surf_attr("vof_list_cycle", "0"))))
        # 填充率检查（SURF_CONTROL IFILL 0/2/12；XML 属性名未实证）
        self.fs_fill_check = QComboBox(fg)
        for label, val in (
                ("Off", "0"), ("Finish when filled", "2"),
                ("Close inflow/outflow when filled", "12")):
            self.fs_fill_check.addItem(label, val)
        cur_fill = model.free_surf_attr("filling_check", "0")
        i = self.fs_fill_check.findData(cur_fill)
        self.fs_fill_check.setCurrentIndex(i if i >= 0 else 0)
        # 填充率阈值 %（SURF_CONTROL FILL，默认 95.0）
        self.fs_fill_rate = QDoubleSpinBox(fg)
        self.fs_fill_rate.setRange(1.0, 100.0)
        self.fs_fill_rate.setDecimals(2)
        try:
            self.fs_fill_rate.setValue(float(
                model.free_surf_attr("fill_rate", "95")))
        except ValueError:
            self.fs_fill_rate.setValue(95.0)
        # MARS：分步数（SURF_CONTROL NFS，默认 5；XML 属性实证）
        self.fs_frac_step = QSpinBox(fg)
        self.fs_frac_step.setRange(0, 100)
        self.fs_frac_step.setValue(int(float(
            model.free_surf_attr("fractional_step", "5"))))
        # MARS：粘度平均（IVSCC 0=算术/1=调和；XML 属性实证）
        self.fs_visc_avg = QComboBox(fg)
        self.fs_visc_avg.addItem("Arithmetic mean", "0")
        self.fs_visc_avg.addItem("Harmonic mean", "1")
        i = self.fs_visc_avg.findData(
            model.free_surf_attr("viscosity_average", "0"))
        self.fs_visc_avg.setCurrentIndex(i if i >= 0 else 0)
        # MARS：守恒修正项（IMADV 0/1；XML 属性实证，默认 1）
        self.fs_conservation = QComboBox(fg)
        self.fs_conservation.addItem("Disabled", "0")
        self.fs_conservation.addItem("Enabled", "1")
        i = self.fs_conservation.findData(
            model.free_surf_attr("conservation_term", "1"))
        self.fs_conservation.setCurrentIndex(i if i >= 0 else 1)
        # MARS：单相流模型种类（XML 属性 one_fluid_model 实证，样本默认 2）
        self.fs_one_fluid = QSpinBox(fg)
        self.fs_one_fluid.setRange(0, 2)
        self.fs_one_fluid.setValue(int(float(
            model.free_surf_attr("one_fluid_model", "2"))))
        # VOF：自由面形状（IPRPL 1=VOF 分布/2=曲率最小；XML 属性实证）
        self.fs_surface_set = QComboBox(fg)
        self.fs_surface_set.addItem("VOF value distribution", "1")
        self.fs_surface_set.addItem("Minimum curvature", "2")
        i = self.fs_surface_set.findData(
            model.free_surf_attr("surface_set", "1"))
        self.fs_surface_set.setCurrentIndex(i if i >= 0 else 0)
        # VOF：流量检查输出周期（NVCH；XML 属性 flow_list 实证）
        self.fs_flow_list = QSpinBox(fg)
        self.fs_flow_list.setRange(0, 10000000)
        self.fs_flow_list.setValue(int(float(
            model.free_surf_attr("flow_list", "1"))))
        # VOF：静压初始分布（ISFDR 0/1；XML 属性 hydro_pres 实证）
        self.fs_hydro = QComboBox(fg)
        self.fs_hydro.addItem("No hydrostatic pressure", "0")
        self.fs_hydro.addItem("Hydrostatic pressure", "1")
        i = self.fs_hydro.findData(
            model.free_surf_attr("hydro_pres", "0"))
        self.fs_hydro.setCurrentIndex(i if i >= 0 else 0)
        ff.addRow(self.fs_enable)
        ff.addRow("Free surface method", self.fs_method)
        ff.addRow("Contact angle (deg)", self.fs_contact)
        ff.addRow("VOF cutoff threshold", self.fs_cutoff)
        ff.addRow("VOF check cycle", self.fs_check_cycle)
        ff.addRow("Filling rate check", self.fs_fill_check)
        ff.addRow("Filling rate (%)", self.fs_fill_rate)
        ff.addRow("[MARS] Fractional step divisions", self.fs_frac_step)
        ff.addRow("[MARS] Viscosity average", self.fs_visc_avg)
        ff.addRow("[MARS] Conservation term", self.fs_conservation)
        ff.addRow("[MARS] One-fluid model kind", self.fs_one_fluid)
        ff.addRow("[VOF] Free-surface shape", self.fs_surface_set)
        ff.addRow("[VOF] Flow rate check cycle", self.fs_flow_list)
        ff.addRow("[VOF] Initial hydrostatic pressure", self.fs_hydro)

        # I1b: VOF2 second phase / SURF_1MARS / SURF_AENT / VFRT_SPC
        # (emitters byte-verified against exA09-4 / exA15-3 / exA15-1 /
        # exA02-2a)
        self.fs_p2_name = QLineEdit(fg)
        self.fs_p2_density = QDoubleSpinBox(fg)
        self.fs_p2_density.setRange(1e-6, 1e6)
        self.fs_p2_density.setDecimals(6)
        self.fs_p2_density.setValue(1.0)
        ff.addRow("VOF2 phase-2 name (blank = off)", self.fs_p2_name)
        ff.addRow("VOF2 phase-2 density", self.fs_p2_density)
        self.fs_1mars_m1 = QSpinBox(fg)
        self.fs_1mars_m1.setRange(0, 9)
        self.fs_1mars_m1.setValue(0)
        self.fs_1mars_m2 = QSpinBox(fg)
        self.fs_1mars_m2.setRange(0, 99)
        ff.addRow("[1MARS] mode (0 = off)", self.fs_1mars_m1)
        ff.addRow("[1MARS] sub-mode", self.fs_1mars_m2)
        self.fs_aent_kind = QComboBox(fg)
        self.fs_aent_kind.addItem("(off)", "")
        self.fs_aent_kind.addItem("adiabatic", "adiabatic")
        self.fs_aent_kind.addItem("conduction", "conduction")
        self.fs_aent_value = QDoubleSpinBox(fg)
        self.fs_aent_value.setRange(-1e9, 1e9)
        self.fs_aent_value.setDecimals(6)
        ff.addRow("[SURF_AENT] exchange kind", self.fs_aent_kind)
        ff.addRow("[SURF_AENT] value", self.fs_aent_value)
        self.fs_vfrt_region = QLineEdit(fg)
        ff.addRow("VFRT_SPC reference region", self.fs_vfrt_region)
        cur = model.free_surf_attr
        self.fs_p2_name.setText(cur("phase2_name", ""))
        try:
            self.fs_p2_density.setValue(float(
                cur("phase2_density", "1.0") or 1.0))
        except ValueError:
            pass
        try:
            _m = (cur("surf_1mars", "").split(",") + ["0", "0"])[:2]
            self.fs_1mars_m1.setValue(int(float(_m[0] or 0)))
            self.fs_1mars_m2.setValue(int(float(_m[1] or 0)))
        except ValueError:
            pass
        _ak = cur("surf_aent_kind", "")
        _ai = self.fs_aent_kind.findData(_ak)
        self.fs_aent_kind.setCurrentIndex(_ai if _ai >= 0 else 0)
        try:
            self.fs_aent_value.setValue(float(
                cur("surf_aent_value", "0") or 0))
        except ValueError:
            pass
        self.fs_vfrt_region.setText(cur("vfrt_spc_region", ""))
        lay.addWidget(g)
        lay.addWidget(fg)
        lay.addStretch(1)

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            "evaporation_enable", "T" if on else "F")
        if not on:
            self.model.remove_analysis_etc_section("evaporation")
        else:
            self.model.set_analysis_etc_child(
                "evaporation", "liquid_temp",
                f"{self.liquid_temp.value():g}")
            self.model.set_analysis_etc_child(
                "evaporation", "gas_temp", f"{self.gas_temp.value():g}")
            self.model.set_analysis_etc_child(
                "evaporation", "latent_heat", f"{self.latent.value():g}",
                unit=self.latent_unit.currentText())
            self.model.set_analysis_etc_child(
                "evaporation", "recoil_model",
                str(self.recoil.currentIndex()))
            self.model.set_analysis_etc_child(
                "evaporation", "atomic_mass", f"{self.atomic.value():g}")
        # R8-A 深字段：自由面 MARS/VOF 参数写回 <analysis_etc>/<free_surf>
        if self.fs_enable.isChecked():
            m = self.model
            m.set_free_surf_attr("type", self.fs_method.currentData())
            m.set_free_surf_attr("contact", str(self.fs_contact.value()))
            # cutoff 为 'EPSVF,0.5,eps_save' 三元组（样本实证）：仅替换
            # 第 1 值，后两值原样保留（缺省补样本默认 0.5 / 1e-06）
            parts = (m.free_surf_attr("cutoff", "0.0001,0.5,1e-06")
                     .split(",") + ["0.5", "1e-06"])[:3]
            parts[0] = f"{self.fs_cutoff.value():g}"
            m.set_free_surf_attr("cutoff", ",".join(parts))
            m.set_free_surf_attr(
                "vof_list_cycle", str(self.fs_check_cycle.value()))
            m.set_free_surf_attr(
                "filling_check", self.fs_fill_check.currentData())
            m.set_free_surf_attr(
                "fill_rate", f"{self.fs_fill_rate.value():g}")
            m.set_free_surf_attr(
                "fractional_step", str(self.fs_frac_step.value()))
            m.set_free_surf_attr(
                "viscosity_average", self.fs_visc_avg.currentData())
            m.set_free_surf_attr(
                "conservation_term", self.fs_conservation.currentData())
            m.set_free_surf_attr(
                "one_fluid_model", str(self.fs_one_fluid.value()))
            m.set_free_surf_attr(
                "surface_set", self.fs_surface_set.currentData())
            m.set_free_surf_attr(
                "flow_list", str(self.fs_flow_list.value()))
            m.set_free_surf_attr(
                "hydro_pres", self.fs_hydro.currentData())
            # I1b: VOF2 second phase / SURF_1MARS / SURF_AENT / VFRT_SPC
            m.set_free_surf_attr(
                "phase2_name", self.fs_p2_name.text().strip())
            m.set_free_surf_attr(
                "phase2_density", f"{self.fs_p2_density.value():g}")
            m.set_free_surf_attr(
                "surf_1mars",
                f"{self.fs_1mars_m1.value()},{self.fs_1mars_m2.value()}"
                if self.fs_1mars_m1.value() else "")
            m.set_free_surf_attr(
                "surf_aent_kind", self.fs_aent_kind.currentData())
            m.set_free_surf_attr(
                "surf_aent_value", f"{self.fs_aent_value.value():g}")
            m.set_free_surf_attr(
                "vfrt_spc_region", self.fs_vfrt_region.text().strip())
        else:
            # 取消勾选时移除整个自由面节（与 CW Analysis Types 行为一致）
            self.model.remove_analysis_etc_section("free_surf")

# P1-3: Boil/condensation - kinds boil_condensation (Phase change) and
# boil_lee (Bubbles) COM-validated 2026-08-16 (SetAnalysisType rc=1);
# param keys phase_boil / phase_boil_latent_heat / phase_gas_temp /
# phase_satulate_temp / phase_solid_temp / phase_gas_density recovered
# from STpreBase strings.  Stored as analysis_etc/boil_condensation
# (sibling of the evaporation section; sub-type kept as a child tag).
# ---------------------------------------------------------------------------
class _CwBoilPage(QWidget if _HAS_GUI else object):
    # Condition Wizard - Boil/condensation (Phase change / Bubbles).

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            'Boiling analysis (requires the Free surface analysis). The '
            'STpre kinds boil_condensation (Phase change) and boil_lee '
            '(Bubbles) are COM-validated; parameters follow the STpreBase '
            'phase_* keys inside analysis_etc/boil_condensation.', self))
        g = QGroupBox('Boil/condensation', self)
        f = QFormLayout(g)
        self.enable = QCheckBox('Consider boil/condensation', g)
        sec = model.analysis_etc_section('boil_condensation')
        self.enable.setChecked(sec is not None)

        def child(tag, default=''):
            return (model.analysis_etc_child(
                'boil_condensation', tag, default) or default).strip()

        self.kind = QComboBox(g)
        self.kind.addItems([
            'Phase change (boil_condensation)',
            'Bubbles (boil_lee)'])
        self.sat_temp = QDoubleSpinBox(g)
        self.sat_temp.setRange(-273.15, 10000.0)
        self.sat_temp.setDecimals(2)
        self.latent = QDoubleSpinBox(g)
        self.latent.setRange(0.0, 1e9)
        self.latent.setDecimals(2)
        self.gas_temp = QDoubleSpinBox(g)
        self.gas_temp.setRange(-273.15, 10000.0)
        self.gas_temp.setDecimals(2)
        self.solid_temp = QDoubleSpinBox(g)
        self.solid_temp.setRange(-273.15, 10000.0)
        self.solid_temp.setDecimals(2)
        self.gas_density = QDoubleSpinBox(g)
        self.gas_density.setRange(0.0, 1e6)
        self.gas_density.setDecimals(6)
        for w, tag, cast, default in (
                (self.sat_temp, 'phase_satulate_temp', float, 100.0),
                (self.latent, 'phase_boil_latent_heat', float, 2256000.0),
                (self.gas_temp, 'phase_gas_temp', float, 100.0),
                (self.solid_temp, 'phase_solid_temp', float, 0.0),
                (self.gas_density, 'phase_gas_density', float, 0.6)):
            try:
                w.setValue(cast(child(tag, str(default))))
            except (TypeError, ValueError):
                w.setValue(default)
        k = child('type', 'phase_change')
        self.kind.setCurrentIndex(1 if k == 'lee' else 0)
        f.addRow(self.enable)
        f.addRow('Model', self.kind)
        f.addRow('Saturation temperature (C)', self.sat_temp)
        f.addRow('Latent heat (J/kg)', self.latent)
        f.addRow('Gas temperature (C)', self.gas_temp)
        f.addRow('Solid temperature (C)', self.solid_temp)
        f.addRow('Gas density (kg/m3)', self.gas_density)
        lay.addWidget(g)
        lay.addStretch(1)

    def _commit_bubble_nucleus(self, name: str, nucleation_site: float,
                               q0: float) -> bool:
        """R4-19: Bubble Nucleus Generation — storage-only record
        (module: boil/condensation)."""
        name = (name or "").strip()
        if not name:
            return False
        return self.model.upsert_value("bubble_nucleus", name, [
            ("nucleation_site", f"{float(nucleation_site):.12g}", "1/m2"),
            ("q0", f"{float(q0):.12g}", "W/m2")])

    def apply(self) -> None:
        on = self.enable.isChecked()
        self.model.set_project_value(
            'boil_enable', 'T' if on else 'F')
        if not on:
            self.model.remove_analysis_etc_section('boil_condensation')
            return
        sub = 'lee' if self.kind.currentIndex() == 1 else 'phase_change'
        self.model.set_analysis_etc_child(
            'boil_condensation', 'type', sub)
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_boil', 'T')
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_satulate_temp',
            f'{self.sat_temp.value():g}')
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_boil_latent_heat',
            f'{self.latent.value():g}')
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_gas_temp',
            f'{self.gas_temp.value():g}')
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_solid_temp',
            f'{self.solid_temp.value():g}')
        self.model.set_analysis_etc_child(
            'boil_condensation', 'phase_gas_density',
            f'{self.gas_density.value():g}')
