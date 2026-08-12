"""STpre [Edit] menu dialogs (chrome aligned with Pre_eng + STpreTool strings).

Window titles and field labels match Cradle STpre English UI:
Group / Deletion of Parts / Convert Parts / Facet Accuracy / Face Extrusion /
Align Parts / Place Part / Copy: Mirror copy / Connected Region /
Boolean Operation / Change in geometry by Boolean operation / Cutting Plane /
Edit Solid / Part Simplification / Shape simplification / FEM Conversion /
Wrapping / Reset Computational Domain / Edit wiring of board / Place Image.
"""

from __future__ import annotations

from typing import Optional

import cab_edit_ops as ops
from cab_dialogs import DialogHeader
from cabxml import StpreModel, _first

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
        QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
        QPushButton, QRadioButton, QSpinBox, QTabWidget, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_GUI = True
except Exception:  # pragma: no cover
    _HAS_GUI = False
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore


def _part_names(model: StpreModel) -> list[str]:
    return [p.name for p in model.parts()]


def _fill_parts(lst: QListWidget, model: StpreModel,
                multi: bool = True) -> None:
    lst.clear()
    lst.setSelectionMode(
        QListWidget.MultiSelection if multi else QListWidget.SingleSelection)
    for name in _part_names(model):
        QListWidgetItem(name, lst)


def _selected(lst: QListWidget) -> list[str]:
    return [lst.item(i).text() for i in range(lst.count())
            if lst.item(i).isSelected()]


def _bottom_buttons(dlg, labels_slots) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch(1)
    for label, slot in labels_slots:
        btn = QPushButton(label, dlg)
        if label in ("OK", "Execute", "Execute deletion", "Reconstruct",
                     "B->A Execute", "Execute cutting", "Set", "Register"):
            btn.setDefault(True)
        btn.clicked.connect(slot)
        row.addWidget(btn)
    return row


def _capability_note(text: str, parent=None) -> QLabel:
    """Persistent honesty label for chrome / MVP Edit dialogs."""
    lab = QLabel(text, parent)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #555; font-size: 11px;")
    return lab


class _EditDlg(QDialog if _HAS_GUI else object):
    """Shared chrome: DialogHeader + body + status flag ``applied``."""

    def __init__(self, title: str, header: str, parent=None,
                 icon: str = "domain"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.applied = False
        self._root = QVBoxLayout(self)
        self._root.setSpacing(6)
        self._root.addWidget(DialogHeader(header, icon, self))
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self._root.addLayout(self.body, 1)


# ------------------------------------------------------------------ Group


class GroupDialog(_EditDlg):
    """[Edit] - [Group] — Operation / Create new / Add / Remove / Ungroup."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Group", "Group", parent, icon="group")
        self.model = model

        op = QGroupBox("Operation", self)
        ol = QVBoxLayout(op)
        self.bg = QButtonGroup(self)
        self.rb_name = QRadioButton("Group name", op)
        self.rb_add = QRadioButton("Add part", op)
        self.rb_rem = QRadioButton("Remove part", op)
        self.rb_ung = QRadioButton("Ungroup", op)
        self.rb_name.setChecked(True)
        for rb in (self.rb_name, self.rb_add, self.rb_rem, self.rb_ung):
            self.bg.addButton(rb)
            ol.addWidget(rb)
        nrow = QHBoxLayout()
        self.group_edit = QLineEdit(op)
        self.group_edit.setPlaceholderText("group name")
        nrow.addWidget(self.group_edit, 1)
        nrow.addWidget(QLabel("Parent Group", op))
        self.parent_combo = QComboBox(op)
        self.parent_combo.addItem("(root)")
        for g in ops.group_names(model):
            self.parent_combo.addItem(g)
        nrow.addWidget(self.parent_combo, 1)
        ol.addLayout(nrow)
        self.body.addWidget(op)

        cols = QHBoxLayout()
        gbox = QGroupBox("Groups", self)
        gl = QVBoxLayout(gbox)
        self.group_list = QListWidget(gbox)
        self._reload_groups()
        gl.addWidget(self.group_list)
        cols.addWidget(gbox, 1)

        pbox = QGroupBox("Parts", self)
        pl = QVBoxLayout(pbox)
        self.part_list = QListWidget(pbox)
        _fill_parts(self.part_list, model, multi=True)
        pl.addWidget(self.part_list)
        btn_clear = QPushButton("Clear List", pbox)
        btn_clear.clicked.connect(self.part_list.clearSelection)
        pl.addWidget(btn_clear)
        cols.addWidget(pbox, 2)
        self.body.addLayout(cols)

        self.bg.buttonClicked.connect(self._sync_action)
        self.group_list.itemSelectionChanged.connect(self._on_group_sel)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_action = QPushButton("Create new", self)
        self.btn_action.setDefault(True)
        self.btn_action.clicked.connect(self._on_action)
        btn_close = QPushButton("Close", self)
        btn_close.clicked.connect(self.accept)
        brow.addWidget(self.btn_action)
        brow.addWidget(btn_close)
        self._root.addLayout(brow)
        self._sync_action()

    def _reload_groups(self) -> None:
        self.group_list.clear()
        for g in ops.group_names(self.model):
            QListWidgetItem(g, self.group_list)

    def _on_group_sel(self) -> None:
        items = self.group_list.selectedItems()
        if items:
            self.group_edit.setText(items[0].text())

    def _sync_action(self, *_a) -> None:
        if self.rb_name.isChecked():
            label = "Create new"
        elif self.rb_add.isChecked():
            label = "Add part"
        elif self.rb_rem.isChecked():
            label = "Remove part"
        else:
            label = "Ungroup"
        self.btn_action.setText(label)

    def _warn(self, text: str) -> None:
        self.status = text
        QMessageBox.warning(self, "Group", text)

    def _on_action(self) -> None:
        gname = self.group_edit.text().strip()
        parts = _selected(self.part_list)
        self.status = ""
        if self.rb_name.isChecked():
            if not gname:
                self._warn("Enter a group name.")
                return
            if parts:
                self.model.move_parts_to_group(parts, gname)
            else:
                from xml.etree.ElementTree import Element, SubElement
                if gname in ops.group_names(self.model):
                    self.status = f"Group '{gname}' already exists."
                    return
                grp = Element("group")
                grp.tail = "\n   "
                n = SubElement(grp, "name")
                n.text = f" {gname} "
                n.tail = "\n   "
                self.model.root.append(grp)
            self.applied = True
            self._reload_groups()
            self.parent_combo.clear()
            self.parent_combo.addItem("(root)")
            for g in ops.group_names(self.model):
                self.parent_combo.addItem(g)
            self.status = f"Created group '{gname}'."
        elif self.rb_add.isChecked():
            if not gname or not parts:
                self._warn("Select a group and parts to add.")
                return
            moved = self.model.move_parts_to_group(parts, gname)
            self.applied = True
            self.status = f"Added {len(moved)} part(s) to '{gname}'."
        elif self.rb_rem.isChecked():
            if not parts:
                self._warn("Select parts to remove from group.")
                return
            moved = self.model.move_parts_to_group(parts, "")
            self.applied = True
            self.status = f"Removed {len(moved)} part(s) to root."
        else:
            if not gname:
                self._warn("Select a group to ungroup.")
                return
            moved = ops.ungroup(self.model, gname)
            self.applied = True
            self._reload_groups()
            self.status = f"Ungrouped '{gname}' ({len(moved)} part(s))."


# -------------------------------------------------------- Deletion of Parts


class DeletionOfPartsDialog(_EditDlg):
    """[Edit] - [Deletion of Parts] — criteria-based collective deletion."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Deletion of Parts", "Deletion of Parts",
                         parent, icon="group")
        self.model = model
        self.cad_meshes = cad_meshes
        self.deleted: list[str] = []

        rng = QGroupBox("Range of deletion", self)
        rl = QVBoxLayout(rng)
        self.rb_all = QRadioButton("All", rng)
        self.rb_grp = QRadioButton("Specified group", rng)
        self.rb_all.setChecked(True)
        rl.addWidget(self.rb_all)
        grow = QHBoxLayout()
        grow.addWidget(self.rb_grp)
        self.group_combo = QComboBox(rng)
        self.group_combo.addItem("")
        for g in ops.group_names(model):
            self.group_combo.addItem(g)
        grow.addWidget(self.group_combo, 1)
        rl.addLayout(grow)
        self.body.addWidget(rng)

        tgt = QGroupBox("Target", self)
        tl = QHBoxLayout(tgt)
        self.chk_solid = QCheckBox("Solid", tgt)
        self.chk_panel = QCheckBox("Panel", tgt)
        self.chk_solid.setChecked(True)
        self.chk_panel.setChecked(True)
        tl.addWidget(self.chk_solid)
        tl.addWidget(self.chk_panel)
        tl.addStretch(1)
        self.body.addWidget(tgt)

        meas = QGroupBox("Measure", self)
        ml = QVBoxLayout(meas)
        self.rb_vol = QRadioButton("Volume/Area", meas)
        self.rb_len = QRadioButton("Length", meas)
        self.rb_size = QRadioButton("Size", meas)
        self.rb_vol.setChecked(True)
        for rb in (self.rb_vol, self.rb_len, self.rb_size):
            ml.addWidget(rb)
        self.body.addWidget(meas)

        crow = QHBoxLayout()
        crow.addWidget(QLabel("Criteria", self))
        self.criteria = QDoubleSpinBox(self)
        self.criteria.setRange(0.0, 1e12)
        self.criteria.setDecimals(4)
        self.criteria.setValue(0.0)
        crow.addWidget(self.criteria, 1)
        self.body.addLayout(crow)

        self.chk_heat = QCheckBox(
            "Keep if heat source condition is set.", self)
        self.chk_heat.setChecked(True)
        self.body.addWidget(self.chk_heat)

        btn_sel = QPushButton(
            "Select parts to be deleted based on the criteria.", self)
        btn_sel.clicked.connect(self._select_by_criteria)
        self.body.addWidget(btn_sel)

        self.part_list = QListWidget(self)
        _fill_parts(self.part_list, model, multi=True)
        self.body.addWidget(self.part_list, 1)

        self._root.addLayout(_bottom_buttons(self, (
            ("Execute deletion", self._execute),
            ("Close", self.accept),
        )))

    def _measure_key(self) -> str:
        if self.rb_len.isChecked():
            return "length"
        if self.rb_size.isChecked():
            return "size"
        return "volume"

    def _select_by_criteria(self) -> None:
        group = self.group_combo.currentText() if self.rb_grp.isChecked() \
            else ""
        names = ops.parts_matching_deletion(
            self.model, self.cad_meshes,
            group=group,
            target_solid=self.chk_solid.isChecked(),
            target_panel=self.chk_panel.isChecked(),
            measure=self._measure_key(),
            criteria=self.criteria.value(),
            keep_heat=self.chk_heat.isChecked())
        self.part_list.clearSelection()
        for i in range(self.part_list.count()):
            if self.part_list.item(i).text() in names:
                self.part_list.item(i).setSelected(True)
        if not names:
            QMessageBox.information(
                self, "Deletion of Parts",
                "No parts match the criteria.")

    def _execute(self) -> None:
        names = _selected(self.part_list)
        if not names:
            QMessageBox.warning(
                self, "Deletion of Parts", "Select at least one part.")
            return
        if QMessageBox.question(
                self, "Deletion of Parts",
                f"Delete {len(names)} part(s)?") != QMessageBox.Yes:
            return
        for n in names:
            self.model.delete_part(n)
            self.deleted.append(n)
        self.applied = True
        _fill_parts(self.part_list, self.model, multi=True)
        QMessageBox.information(
            self, "Deletion of Parts",
            f"Deleted {len(names)} part(s).")


# -------------------------------------------------------- Parts Conversion


class PartsConversionDialog(_EditDlg):
    """[Convert Parts] — conversion type tree + part list."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Convert Parts", "Convert Parts", parent)
        self.model = model
        self.cad_meshes = cad_meshes

        cols = QHBoxLayout()
        left = QGroupBox("Conversion", self)
        ll = QVBoxLayout(left)
        self.tree = QTreeWidget(left)
        self.tree.setHeaderHidden(True)
        root = QTreeWidgetItem(self.tree, ["Conversion"])
        for label in ("Cuboid", "Hexahedron", "Cylinder", "Sphere", "Panel"):
            QTreeWidgetItem(root, [label])
        self.tree.expandAll()
        self.tree.setCurrentItem(root.child(0))
        ll.addWidget(self.tree)
        opt = QGroupBox("Conversion option", left)
        ol = QVBoxLayout(opt)
        self.rb_minmax = QRadioButton("Keep minimum and maximum", opt)
        self.rb_vol = QRadioButton("Keep volume", opt)
        self.rb_minmax.setChecked(True)
        ol.addWidget(self.rb_minmax)
        ol.addWidget(self.rb_vol)
        ll.addWidget(opt)
        cols.addWidget(left, 1)

        right = QGroupBox("Conversion Parts List", self)
        rl = QVBoxLayout(right)
        self.part_list = QListWidget(right)
        _fill_parts(self.part_list, model, multi=True)
        rl.addWidget(self.part_list)
        cols.addWidget(right, 1)
        self.body.addLayout(cols)

        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _ok(self) -> None:
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            QMessageBox.warning(self, "Convert Parts",
                                "Select a conversion type.")
            return
        kind_map = {
            "Cuboid": "cuboid", "Hexahedron": "hexahedron",
            "Cylinder": "cylinder", "Sphere": "sphere", "Panel": "panel",
        }
        kind = kind_map.get(item.text(0), "cuboid")
        names = _selected(self.part_list)
        if not names:
            QMessageBox.warning(self, "Convert Parts",
                                "Select parts to convert.")
            return
        keep = "volume" if self.rb_vol.isChecked() else "minmax"
        n_ok = 0
        for name in names:
            if ops.convert_part_to_type(
                    self.model, name, kind, self.cad_meshes, keep=keep):
                n_ok += 1
        if not n_ok:
            QMessageBox.warning(
                self, "Convert Parts",
                "Conversion failed (no geometry bounds).")
            return
        self.applied = True
        self.accept()


# -------------------------------------------------------- Facet Accuracy


class FacetAccuracyDialog(_EditDlg):
    """[Facet Accuracy] — Reconstruct of Part Facet (M24: PK_TOPOL_facet_2)."""

    def __init__(self, model: StpreModel, parent=None, archive=None,
                 cad_meshes=None):
        super().__init__("Facet Accuracy", "Facet Accuracy", parent)
        self.model = model
        self.archive = archive
        self.cad_meshes = cad_meshes
        self.reconstructed = 0
        form = QFormLayout()
        self.facet_len = QDoubleSpinBox(self)
        self.facet_len.setRange(0.0, 1e6)
        self.facet_len.setDecimals(4)
        self.facet_len.setValue(0.0)
        form.addRow("Facet length*", self.facet_len)
        self.tolerance = QDoubleSpinBox(self)
        self.tolerance.setRange(0.0, 1.0)
        self.tolerance.setDecimals(6)
        self.tolerance.setValue(0.01)
        form.addRow("Tolerance", self.tolerance)
        self.body.addLayout(form)
        self.part_list = QListWidget(self)
        _fill_parts(self.part_list, model, multi=True)
        self.body.addWidget(QLabel("Parts", self))
        self.body.addWidget(self.part_list, 1)
        note = QLabel(
            "Reconstruct recalculates facet division used for drawing "
            "and element division (imported free surfaces).", self)
        note.setWordWrap(True)
        self.body.addWidget(note)
        self._root.addLayout(_bottom_buttons(self, (
            ("Reconstruct", self._recon),
            ("Close", self.accept),
        )))

    def _recon(self) -> None:
        names = _selected(self.part_list)
        if not names:
            QMessageBox.warning(self, "Facet Accuracy",
                                "Select parts to reconstruct.")
            return
        from cabxml import set_text
        from xml.etree.ElementTree import SubElement
        for name in names:
            el = self.model.find_part(name)
            if el is None:
                continue
            for tag, val in (("facet_length", f"{self.facet_len.value():g}"),
                             ("facet_tolerance",
                              f"{self.tolerance.value():g}")):
                c = _first(el, tag)
                if c is None:
                    c = SubElement(el, tag)
                    c.tail = "\n         "
                set_text(c, val)
        tol = self.tolerance.value() or 1e-4
        if self.archive is not None and self.cad_meshes is not None:
            import cab_edit_ops as eops
            updated = eops.reconstruct_part_facets(
                self.model, self.archive, self.cad_meshes, names,
                facet_tol=tol, facet_angle=12.0)
            self.reconstructed = len(updated)
        self.applied = True
        msg = f"Facet parameters stored for {len(names)} part(s)."
        if self.reconstructed:
            msg += f"\nRebuilt {self.reconstructed} tessellation(s) via PK_TOPOL_facet_2."
        else:
            msg += "\n(No XT tessellation rebuilt — store only / pskernel missing.)"
        QMessageBox.information(self, "Facet Accuracy", msg)


# -------------------------------------------------------- Face Extrusion


class FaceExtrusionDialog(_EditDlg):
    """[Face Extrusion] — Sweep Part Face."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Face Extrusion", "Face Extrusion", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.created_name: Optional[str] = None

        self.picked_cell: Optional[int] = None
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Selected face / part", self))
        self.part_combo = QComboBox(self)
        self.part_combo.addItems(_part_names(model))
        sel.addWidget(self.part_combo, 1)
        btn = QPushButton("Select", self)
        btn.clicked.connect(self._use_picked_face)
        sel.addWidget(btn)
        self.body.addLayout(sel)
        self.pick_hint = QLabel(
            "Select uses the current Draw Window face pick when available.",
            self)
        self.pick_hint.setWordWrap(True)
        self.body.addWidget(self.pick_hint)

        form = QFormLayout()
        self.height = QDoubleSpinBox(self)
        self.height.setRange(0.0, 1e6)
        self.height.setDecimals(3)
        self.height.setValue(10.0)
        form.addRow("Height", self.height)
        self.orient = QComboBox(self)
        self.orient.addItems(["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
        self.orient.setCurrentText("+Z")
        form.addRow("Orientation", self.orient)
        self.disp = QCheckBox("Displacement", self)
        form.addRow(self.disp)
        self.name_edit = QLineEdit(self)
        self.name_edit.setText("extrusion_1")
        form.addRow("Part Name", self.name_edit)
        self.body.addLayout(form)

        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))
        self._use_picked_face(silent=True)

    def _use_picked_face(self, silent: bool = False) -> None:
        parent = self.parent()
        picked = getattr(parent, "_picked_face", None) if parent else None
        if not picked:
            if not silent:
                QMessageBox.information(
                    self, "Face Extrusion",
                    "Pick a Face in the Draw Window first "
                    "(Target of selection = Faces).")
            return
        pname, cell = picked
        idx = self.part_combo.findText(str(pname))
        if idx >= 0:
            self.part_combo.setCurrentIndex(idx)
        self.picked_cell = None if cell is None else int(cell)
        plane = ops.face_plane_from_cell(
            next((t for t in (self.cad_meshes or [])
                  if getattr(t, "name", None) == pname), None),
            self.picked_cell if self.picked_cell is not None else -1,
            "")
        if plane is not None:
            self.orient.setCurrentText(plane["direction"])
            self.pick_hint.setText(
                f"Using face pick on '{pname}' "
                f"(cell {self.picked_cell}, {plane['direction']}).")
        else:
            self.pick_hint.setText(f"Using part '{pname}' (AABB fallback).")

    def _ok(self) -> None:
        src = self.part_combo.currentText()
        if not src:
            QMessageBox.warning(self, "Face Extrusion", "Select a part.")
            return
        name = ops.extrude_part_face(
            self.model, self.cad_meshes, src, self.height.value(),
            cell_id=self.picked_cell,
            orientation=self.orient.currentText(),
            displacement=self.disp.isChecked(),
            result_name=self.name_edit.text().strip() or "extrusion_1")
        if not name:
            QMessageBox.warning(
                self, "Face Extrusion",
                "No geometry for selected part.")
            return
        self.created_name = name
        self.applied = True
        self.accept()


# -------------------------------------------------------- Align Parts


class AlignPartsDialog(_EditDlg):
    """[Align Parts] — Part A / Part B / axis / location / B->A Execute."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Align Parts", "Align Parts", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        form = QFormLayout()
        names = _part_names(model)
        self.part_a = QComboBox(self)
        self.part_a.addItems(names)
        self.part_b = QComboBox(self)
        self.part_b.addItems(names)
        if len(names) > 1:
            self.part_b.setCurrentIndex(1)
        form.addRow("Part A", self.part_a)
        form.addRow("Part B", self.part_b)
        self.axis = QComboBox(self)
        self.axis.addItems(["X", "Y", "Z"])
        form.addRow("Coordinate axis", self.axis)
        self.loc = QComboBox(self)
        self.loc.addItems(["Minimum", "Center", "Maximum"])
        form.addRow("Location after movement", self.loc)
        self.body.addLayout(form)
        self._root.addLayout(_bottom_buttons(self, (
            ("B->A Execute", self._exec),
            ("Close", self.accept),
        )))

    def _exec(self) -> None:
        a, b = self.part_a.currentText(), self.part_b.currentText()
        if not a or not b or a == b:
            QMessageBox.warning(self, "Align Parts",
                                "Select two different parts.")
            return
        ok = ops.align_parts(
            self.model, a, b, self.axis.currentText(),
            self.loc.currentText(), self.cad_meshes)
        if not ok:
            QMessageBox.warning(
                self, "Align Parts",
                "Alignment failed (missing geometry bounds).")
            return
        self.applied = True
        QMessageBox.information(self, "Align Parts",
                                f"Aligned '{b}' to '{a}'.")


# -------------------------------------------------------- Place Part


class PlacePartDialog(_EditDlg):
    """[Place Part] — fit by centers (vertices/faces approximated)."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Place Part", "Place Part", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        method = QGroupBox("Method", self)
        ml = QVBoxLayout(method)
        self.rb_vert = QRadioButton("Select vertices", method)
        self.rb_plane = QRadioButton("Select plane surfaces", method)
        self.rb_cyl = QRadioButton("Select cylindrical surfaces", method)
        self.rb_vert.setChecked(True)
        for rb in (self.rb_vert, self.rb_plane, self.rb_cyl):
            ml.addWidget(rb)
        self.body.addWidget(method)
        form = QFormLayout()
        names = _part_names(model)
        self.move_part = QComboBox(self)
        self.move_part.addItems(names)
        self.ref_part = QComboBox(self)
        self.ref_part.addItems(names)
        if len(names) > 1:
            self.ref_part.setCurrentIndex(1)
        form.addRow("Part to move", self.move_part)
        form.addRow("Reference part", self.ref_part)
        self.ox = QDoubleSpinBox(self)
        self.oy = QDoubleSpinBox(self)
        self.oz = QDoubleSpinBox(self)
        for w in (self.ox, self.oy, self.oz):
            w.setRange(-1e6, 1e6)
            w.setDecimals(3)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Offset", self))
        orow.addWidget(self.ox)
        orow.addWidget(self.oy)
        orow.addWidget(self.oz)
        self.body.addLayout(form)
        self.body.addLayout(orow)
        note = QLabel(
            "Vertex/face picking uses part centers when interactive "
            "pick is unavailable.", self)
        note.setWordWrap(True)
        self.body.addWidget(note)
        self._root.addLayout(_bottom_buttons(self, (
            ("Set", self._set),
            ("Close", self.accept),
        )))

    def _set(self) -> None:
        ok = ops.place_part_by_centers(
            self.model, self.move_part.currentText(),
            self.ref_part.currentText(), self.cad_meshes,
            offset=(self.ox.value(), self.oy.value(), self.oz.value()))
        if not ok:
            QMessageBox.warning(self, "Place Part",
                                "Place failed (missing geometry).")
            return
        self.applied = True
        QMessageBox.information(self, "Place Part", "Part placed.")


# -------------------------------------------------------- Mirror Copy


class MirrorCopyDialog(_EditDlg):
    """[Copy: Mirror copy] — mirror plane + OK."""

    def __init__(self, model: StpreModel, names: list[str], parent=None):
        super().__init__("Copy: Mirror copy", "Mirror Copy", parent)
        self.model = model
        self.names = names or _part_names(model)
        self.created: list[str] = []

        self.body.addWidget(QLabel(
            f"Parts: {', '.join(self.names) or '(none)'}", self))
        form = QFormLayout()
        self.axis = QComboBox(self)
        self.axis.addItems(["X", "Y", "Z"])
        form.addRow("Mirror plane axis", self.axis)
        self.plane = QDoubleSpinBox(self)
        self.plane.setRange(-1e6, 1e6)
        self.plane.setDecimals(3)
        self.plane.setValue(0.0)
        form.addRow("Plane position", self.plane)
        self.body.addLayout(form)
        if not names:
            self.part_list = QListWidget(self)
            _fill_parts(self.part_list, model, multi=True)
            self.body.addWidget(self.part_list, 1)
        else:
            self.part_list = None
        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _ok(self) -> None:
        names = self.names
        if self.part_list is not None:
            names = _selected(self.part_list)
        if not names:
            QMessageBox.warning(self, "Mirror Copy",
                                "Select parts to mirror copy.")
            return
        self.created = ops.mirror_copy_parts(
            self.model, names, self.axis.currentText(),
            self.plane.value())
        if not self.created:
            QMessageBox.warning(self, "Mirror Copy",
                                "No parts were copied.")
            return
        self.applied = True
        self.accept()


# -------------------------------------------------------- Connected Region


class ConnectedRegionDialog(_EditDlg):
    """[Connected Region] — seed point + search range."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Connected Region", "Connected Region", parent)
        self.model = model
        self.body.addWidget(QLabel(
            "Searches for connected region containing specified coordinate.",
            self))
        form = QFormLayout()
        self.x = QDoubleSpinBox(self)
        self.y = QDoubleSpinBox(self)
        self.z = QDoubleSpinBox(self)
        for w, v in ((self.x, 0.0), (self.y, 0.0), (self.z, 0.0)):
            w.setRange(-1e6, 1e6)
            w.setDecimals(3)
            w.setValue(v)
        form.addRow("X", self.x)
        form.addRow("Y", self.y)
        form.addRow("Z", self.z)
        self.attr = QComboBox(self)
        self.attr.addItems(["Condition region", "Obstacle"])
        form.addRow("Attribute", self.attr)
        self.body.addLayout(form)

        rng = QGroupBox("Range of search", self)
        rl = QGridLayout(rng)
        self.limit = QCheckBox("Limit search range", rng)
        rl.addWidget(self.limit, 0, 0, 1, 4)
        for i, lab in enumerate(("x1", "y1", "z1", "x2", "y2", "z2")):
            sp = QDoubleSpinBox(rng)
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(3)
            setattr(self, f"r_{lab}", sp)
            rl.addWidget(QLabel(lab, rng), 1 + i // 3, (i % 3) * 2)
            rl.addWidget(sp, 1 + i // 3, (i % 3) * 2 + 1)
        self.body.addWidget(rng)
        self.chk_panel = QCheckBox("Consider a panel as well", self)
        self.chk_blocks = QCheckBox("Search all blocks", self)
        self.chk_blocks.setChecked(True)
        self.body.addWidget(self.chk_panel)
        self.body.addWidget(self.chk_blocks)

        tabs = QTabWidget(self)
        heat = QWidget(tabs)
        hl = QVBoxLayout(heat)
        self.chk_heat = QCheckBox(
            "Set as the internal region of enclosure in the heat path", heat)
        hl.addWidget(self.chk_heat)
        hl.addStretch(1)
        tabs.addTab(QWidget(self), "Region")
        tabs.addTab(heat, "Heat Path")
        self.body.addWidget(tabs)

        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _ok(self) -> None:
        # Register a named region marker (full flood-fill needs meshing).
        name = ops.unique_part_name(self.model, "connected_region")
        from xml.etree.ElementTree import Element, SubElement
        from cabxml import set_text
        reg = Element("region")
        reg.attrib["type"] = "point"
        reg.tail = "\n   "
        n = SubElement(reg, "name")
        set_text(n, name)
        n.tail = "\n      "
        p = SubElement(reg, "point")
        set_text(p, f"{self.x.value():g},{self.y.value():g},{self.z.value():g}")
        p.tail = "\n      "
        a = SubElement(reg, "attribute")
        set_text(a, "condition" if "Condition" in self.attr.currentText()
                 else "obstacle")
        a.tail = "\n      "
        self.model.root.append(reg)
        self.applied = True
        self.accept()


# -------------------------------------------------------- Boolean


class BooleanOperationDialog(_EditDlg):
    """[Boolean Operation] — Part A/B + Unite/Subtract/Intersect/Divide."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Boolean Operation", "Boolean Operation", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.result_name: Optional[str] = None
        self.body.addWidget(_capability_note(
            "M33+: PK_BODY_boolean_2 on real x_t bodies when available; "
            "tessellation CSG fallback when pskernel is unavailable. "
            "Seamless stays reserved.", self))

        form = QFormLayout()
        names = _part_names(model)
        self.part_a = QComboBox(self)
        self.part_a.addItems(names)
        self.part_b = QComboBox(self)
        self.part_b.addItems(names)
        if len(names) > 1:
            self.part_b.setCurrentIndex(1)
        form.addRow("Part A", self.part_a)
        form.addRow("Part B", self.part_b)
        swap = QPushButton("Swap", self)
        swap.clicked.connect(self._swap)
        form.addRow(swap)
        self.body.addLayout(form)

        op = QGroupBox("Operation", self)
        ol = QVBoxLayout(op)
        self.rb_unite = QRadioButton("Unite(A+B)", op)
        self.rb_sub = QRadioButton("Subtract(A-B)", op)
        self.rb_int = QRadioButton("Intersect(A*B)", op)
        self.rb_div = QRadioButton("Divide(Subtract+Intersect)", op)
        self.rb_unite.setChecked(True)
        for rb in (self.rb_unite, self.rb_sub, self.rb_int, self.rb_div):
            ol.addWidget(rb)
        self.chk_keep_a = QCheckBox("Keep A", op)
        self.chk_keep_b = QCheckBox("Keep B", op)
        self.chk_seamless = QCheckBox("Seamless", op)
        self.chk_seamless.setEnabled(False)
        self.chk_seamless.setToolTip(
            "Seamless merge option reserved; M33 uses PK_BODY_boolean_2 "
            "with CSG fallback.")
        ol.addWidget(self.chk_keep_a)
        ol.addWidget(self.chk_keep_b)
        ol.addWidget(self.chk_seamless)
        self.body.addWidget(op)
        self.body.addWidget(_capability_note(
            "M33: prefers PK_BODY_boolean_2 (solid blocks from world AABB); "
            "falls back to tessellation CSG when pskernel is unavailable.",
            self))

        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Part name after operation", self))
        self.name_edit = QLineEdit(self)
        self.name_edit.setText("boolean_1")
        nrow.addWidget(self.name_edit, 1)
        self.body.addLayout(nrow)

        self._root.addLayout(_bottom_buttons(self, (
            ("Execute", self._exec),
            ("Close", self.accept),
        )))
        self.backend = ""

    def _swap(self) -> None:
        ia, ib = self.part_a.currentIndex(), self.part_b.currentIndex()
        self.part_a.setCurrentIndex(ib)
        self.part_b.setCurrentIndex(ia)

    def _exec(self) -> None:
        a, b = self.part_a.currentText(), self.part_b.currentText()
        if not a or not b or a == b:
            QMessageBox.warning(self, "Boolean Operation",
                                "Select two different parts.")
            return
        if self.rb_unite.isChecked():
            op = "unite"
        elif self.rb_sub.isChecked():
            op = "subtract"
        else:
            op = "intersect"
        archive = getattr(self.parent(), "archive", None)
        out = ops.boolean_mesh_parts(
            self.model, self.cad_meshes, a, b, op,
            self.name_edit.text().strip() or "boolean_1",
            keep_a=self.chk_keep_a.isChecked(),
            keep_b=self.chk_keep_b.isChecked(),
            archive=archive)
        if not out:
            QMessageBox.warning(
                self, "Boolean Operation",
                "Boolean failed (need tessellation for both parts).")
            return
        name, backend = out
        self.result_name = name
        self.backend = backend
        self.applied = True
        eng = ("PK_BODY_boolean_2" if backend == "pk"
               else "tessellation CSG fallback")
        QMessageBox.information(
            self, "Boolean Operation",
            f"Created '{name}' via {eng}.")


class ShapeChangeBooleanDialog(_EditDlg):
    """[Change in geometry by Boolean operation]."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(
            "Change in geometry by Boolean operation",
            "Change in geometry by Boolean operation", parent)
        self.model = model
        self.body.addWidget(_capability_note(
            "Registers the Boolean shape-change intent on the project "
            "(geometry kernel application pending).", self))
        form = QFormLayout()
        names = ["Domain(cuboid)"] + _part_names(model)
        self.part_a = QComboBox(self)
        self.part_a.addItems(names)
        self.part_b = QComboBox(self)
        self.part_b.addItems(_part_names(model))
        form.addRow("Part A", self.part_a)
        form.addRow("Part B (List)", self.part_b)
        self.body.addLayout(form)
        typ = QGroupBox("Type", self)
        tl = QVBoxLayout(typ)
        self.rb_sub = QRadioButton("Subtraction", typ)
        self.rb_face = QRadioButton("Face division", typ)
        self.rb_sub.setChecked(True)
        tl.addWidget(self.rb_sub)
        tl.addWidget(self.rb_face)
        self.body.addWidget(typ)
        self._root.addLayout(_bottom_buttons(self, (
            ("Set", self._set),
            ("Cancel", self.reject),
        )))

    def _set(self) -> None:
        # Record intent as a condition-like annotation on Part A.
        a, b = self.part_a.currentText(), self.part_b.currentText()
        if not b:
            QMessageBox.warning(self, "Boolean", "Select Part B.")
            return
        kind = "subtraction" if self.rb_sub.isChecked() else "face_division"
        self.model.set_project_value(
            "boolean_shape_change", f"{kind}:{a}:{b}")
        self.applied = True
        self.accept()


# -------------------------------------------------------- Cutting Plane


class CuttingPlaneDialog(_EditDlg):
    """[Cutting Plane] — plane definition + Execute cutting."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Cutting Plane", "Cutting Plane", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.created: list[str] = []

        sel = QHBoxLayout()
        sel.addWidget(QLabel("Part to be cut", self))
        self.part = QComboBox(self)
        self.part.addItems(_part_names(model))
        sel.addWidget(self.part, 1)
        sel.addWidget(QPushButton("Select", self))
        self.body.addLayout(sel)

        plane = QGroupBox("Cutting plane", self)
        pl = QVBoxLayout(plane)
        self.rb_direct = QRadioButton("Direct input", plane)
        self.rb_3pt = QRadioButton("Plane (Specify 3 points)", plane)
        self.rb_cyl = QRadioButton("Cylindrical surface", plane)
        self.rb_direct.setChecked(True)
        for rb in (self.rb_direct, self.rb_3pt, self.rb_cyl):
            pl.addWidget(rb)
        form = QFormLayout()
        self.nx = QDoubleSpinBox(self)
        self.ny = QDoubleSpinBox(self)
        self.nz = QDoubleSpinBox(self)
        self.px = QDoubleSpinBox(self)
        self.py = QDoubleSpinBox(self)
        self.pz = QDoubleSpinBox(self)
        for w, v in ((self.nx, 0), (self.ny, 0), (self.nz, 1),
                     (self.px, 0), (self.py, 0), (self.pz, 0)):
            w.setRange(-1e6, 1e6)
            w.setDecimals(4)
            w.setValue(float(v))
        form.addRow("Normal vector X/Y/Z", self._xyz_row(
            self.nx, self.ny, self.nz))
        form.addRow("Point on surface X/Y/Z", self._xyz_row(
            self.px, self.py, self.pz))
        pl.addLayout(form)
        self.chk_show = QCheckBox("Show", plane)
        self.chk_show.setChecked(True)
        pl.addWidget(self.chk_show)
        self.body.addWidget(plane)

        keep = QGroupBox("Portion to be maintained", self)
        kl = QVBoxLayout(keep)
        self.chk_front = QCheckBox("Keep front side ( light blue )", keep)
        self.chk_back = QCheckBox("Keep back side ( gray )", keep)
        self.chk_front.setChecked(True)
        kl.addWidget(self.chk_front)
        kl.addWidget(self.chk_back)
        self.body.addWidget(keep)

        self._root.addLayout(_bottom_buttons(self, (
            ("Execute cutting", self._exec),
            ("Close", self.accept),
        )))

    @staticmethod
    def _xyz_row(x, y, z) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(x)
        lay.addWidget(y)
        lay.addWidget(z)
        return w

    def _exec(self) -> None:
        name = self.part.currentText()
        if not name:
            return
        bounds = ops.part_world_bounds(self.model, name, self.cad_meshes)
        if bounds is None:
            QMessageBox.warning(self, "Cutting Plane",
                                "No geometry for selected part.")
            return
        lo, hi = bounds
        # Split AABB by plane point along dominant normal axis.
        n = abs(self.nx.value()), abs(self.ny.value()), abs(self.nz.value())
        idx = int(max(range(3), key=lambda i: n[i]))
        split = (self.px.value(), self.py.value(), self.pz.value())[idx]
        created = []
        if self.chk_front.isChecked():
            flo, fhi = lo.copy(), hi.copy()
            flo[idx] = max(flo[idx], split)
            if (fhi > flo).all():
                created.append(self._make_half(name, "_front", flo, fhi))
        if self.chk_back.isChecked():
            blo, bhi = lo.copy(), hi.copy()
            bhi[idx] = min(bhi[idx], split)
            if (bhi > blo).all():
                created.append(self._make_half(name, "_back", blo, bhi))
        if not created:
            QMessageBox.warning(self, "Cutting Plane",
                                "Nothing to keep on the selected side(s).")
            return
        self.model.delete_part(name)
        self.created = [c for c in created if c]
        self.applied = True
        QMessageBox.information(
            self, "Cutting Plane",
            f"Created {len(self.created)} part(s) (AABB cut).")

    def _make_half(self, src, suffix, lo, hi) -> Optional[str]:
        new = ops.unique_part_name(self.model, f"{src}{suffix}")
        el = self.model.add_part(name=new, kind="cube", attribute="solid")
        if el is None:
            return None
        from cabxml import set_text
        from xml.etree.ElementTree import SubElement
        size = hi - lo
        for tag, val in (
                ("base", ",".join(f"{v:.17g}" for v in lo)),
                ("size", ",".join(f"{v:.17g}" for v in size)),
        ):
            c = _first(el, tag)
            if c is None:
                c = SubElement(el, tag)
                c.tail = "\n         "
            set_text(c, val)
        return new


# -------------------------------------------------------- Edit Solid


class EditSolidDialog(_EditDlg):
    """[Edit Solid] — 8 edit types (STpre)."""

    TYPES = (
        "Unify surfaces",
        "Fill sheet",
        "Sew sheets",
        "Create cover",
        "Extract empty region",
        "Create sheet from edges",
        "Delete faces",
        "Remove redundant edges",
    )

    def __init__(self, model: StpreModel, cad_meshes=None, parent=None):
        super().__init__("Edit Solid", "Edit Solid", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.body.addWidget(_capability_note(
            "M33: Delete faces removes the coplanar triangle cluster from "
            "the current Draw face pick (tessellation). Other edit types "
            "remain project intent until full B-rep heal paths land.", self))
        form = QFormLayout()
        self.edit_type = QComboBox(self)
        self.edit_type.addItems(self.TYPES)
        form.addRow("Edit type", self.edit_type)
        self.target = QComboBox(self)
        self.target.addItems(_part_names(model))
        form.addRow("Target part", self.target)
        self.tolerance = QDoubleSpinBox(self)
        self.tolerance.setRange(0.0, 1e3)
        self.tolerance.setDecimals(6)
        self.tolerance.setValue(0.0)
        form.addRow("Tolerance", self.tolerance)
        self.out_name = QLineEdit(self)
        form.addRow("Part name", self.out_name)
        self.thickness = QDoubleSpinBox(self)
        self.thickness.setRange(0.0, 1e6)
        self.thickness.setDecimals(3)
        self.thickness.setValue(1.0)
        form.addRow("Thickness", self.thickness)
        self.body.addLayout(form)
        self._root.addLayout(_bottom_buttons(self, (
            ("Preview", lambda: None),
            ("Execute", self._exec),
            ("Close", self.accept),
        )))
        self.deleted = 0

    def _exec(self) -> None:
        etype = self.edit_type.currentText()
        target = self.target.currentText()
        self.model.set_project_value(
            "edit_solid_last",
            f"{etype}|{target}|{self.tolerance.value():g}")
        if etype == "Delete faces":
            parent = self.parent()
            picked = getattr(parent, "_picked_face", None) if parent else None
            cell = None
            if picked and picked[0] == target:
                cell = picked[1]
            self.deleted = ops.delete_selected_faces_tess(
                self.cad_meshes, target, cell)
            if self.deleted <= 0:
                QMessageBox.warning(
                    self, "Edit Solid",
                    "Delete faces needs a Face pick on the target part.")
                return
            self.applied = True
            QMessageBox.information(
                self, "Edit Solid",
                f"Deleted {self.deleted} triangle(s) on '{target}'.")
            return
        self.applied = True
        QMessageBox.information(
            self, "Edit Solid",
            f"'{etype}' queued for '{target}'.\n"
            "This edit type is still project-intent only.")


# -------------------------------------------------------- Simplification


class PartSimplificationDialog(_EditDlg):
    """[Part Simplification]."""

    def __init__(self, model: StpreModel, cad_meshes=None, parent=None):
        super().__init__("Part Simplification", "Part Simplification",
                         parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.deleted = 0
        self.body.addWidget(_capability_note(
            "M33: Delete selected face removes the coplanar triangle cluster "
            "from the current Draw face pick.", self))
        row = QHBoxLayout()
        row.addWidget(QLabel("Target", self))
        self.part = QComboBox(self)
        self.part.addItems(_part_names(model))
        row.addWidget(self.part, 1)
        btn = QPushButton("Select", self)
        btn.clicked.connect(self._use_pick)
        row.addWidget(btn)
        self.body.addLayout(row)
        method = QGroupBox("Method", self)
        ml = QVBoxLayout(method)
        for lab in (
                "Auto selection by internal loop",
                "Hole and projection face in thin geometry",
                "External loop face in 2.5 dimensional geometry",
        ):
            rb = QRadioButton(lab, method)
            if "internal" in lab:
                rb.setChecked(True)
            ml.addWidget(rb)
        self.body.addWidget(method)
        self.body.addWidget(QLabel(
            "Additional selection and cancel of selected face", self))
        self._root.addLayout(_bottom_buttons(self, (
            ("Preview", lambda: None),
            ("Cancel all selections (Initialization)", lambda: None),
            ("Delete selected face", self._exec),
            ("Close", self.accept),
        )))

    def _use_pick(self) -> None:
        parent = self.parent()
        picked = getattr(parent, "_picked_face", None) if parent else None
        if picked:
            idx = self.part.findText(str(picked[0]))
            if idx >= 0:
                self.part.setCurrentIndex(idx)

    def _exec(self) -> None:
        target = self.part.currentText()
        parent = self.parent()
        picked = getattr(parent, "_picked_face", None) if parent else None
        cell = picked[1] if picked and picked[0] == target else None
        self.deleted = ops.delete_selected_faces_tess(
            self.cad_meshes, target, cell)
        if self.deleted <= 0:
            QMessageBox.warning(
                self, "Part Simplification",
                "Pick a Face on the target part in the Draw Window.")
            return
        self.applied = True
        QMessageBox.information(
            self, "Part Simplification",
            f"Deleted {self.deleted} triangle(s) on '{target}'.")


class ShapeSimplificationDialog(_EditDlg):
    """[Shape simplification] — screw-hole name based."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Shape simplification", "Shape simplification",
                         parent)
        self.model = model
        form = QFormLayout()
        self.screw = QLineEdit(self)
        form.addRow("Identification name (screw)", self.screw)
        self.mag = QDoubleSpinBox(self)
        self.mag.setRange(0.1, 100.0)
        self.mag.setValue(1.0)
        self.mag.setDecimals(3)
        form.addRow("Magnification rate", self.mag)
        self.body.addLayout(form)
        self._root.addLayout(_bottom_buttons(self, (
            ("Selection", lambda: QMessageBox.information(
                self, "Shape simplification",
                "Select faces by identification name.")),
            ("Delete selected faces", self._exec),
            ("Close", self.accept),
        )))

    def _exec(self) -> None:
        if not self.screw.text().strip():
            QMessageBox.warning(self, "Shape simplification",
                                "Enter an identification name.")
            return
        self.applied = True
        self.model.set_project_value(
            "shape_simplify",
            f"{self.screw.text().strip()}|{self.mag.value():g}")
        QMessageBox.information(
            self, "Shape simplification",
            "Delete selected faces requested (Parasolid).")


# -------------------------------------------------------- FEM / Wrapping


class FEMConversionDialog(_EditDlg):
    """[FEM Conversion]."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("FEM Conversion", "FEM Conversion", parent)
        self.model = model
        form = QFormLayout()
        self.target = QComboBox(self)
        self.target.addItems(_part_names(model))
        form.addRow("Target", self.target)
        self.elem_size = QDoubleSpinBox(self)
        self.elem_size.setRange(1e-6, 1e6)
        self.elem_size.setDecimals(4)
        self.elem_size.setValue(5.0)
        form.addRow("Element size of FEM", self.elem_size)
        self.leave = QCheckBox("Leave edges", self)
        form.addRow(self.leave)
        self.body.addLayout(form)
        contact = QGroupBox("Create edges where Target contacts another part",
                            self)
        cl = QHBoxLayout(contact)
        self.contact = QComboBox(contact)
        self.contact.addItems(_part_names(model))
        cl.addWidget(QLabel("Contacting Part", contact))
        cl.addWidget(self.contact, 1)
        cl.addWidget(QPushButton("Execute", contact))
        self.body.addWidget(contact)
        self._root.addLayout(_bottom_buttons(self, (
            ("Execute", self._exec),
            ("Close", self.accept),
        )))

    def _exec(self) -> None:
        el = self.model.find_part(self.target.currentText())
        if el is None:
            return
        el.attrib["type"] = "fem"
        from cabxml import set_text
        from xml.etree.ElementTree import SubElement
        c = _first(el, "fem_element_size")
        if c is None:
            c = SubElement(el, "fem_element_size")
            c.tail = "\n         "
        set_text(c, f"{self.elem_size.value():g}")
        self.applied = True
        QMessageBox.information(self, "FEM Conversion",
                                "FEM conversion finished.")


class WrappingDialog(_EditDlg):
    """[Wrapping] — Convex hull / Specify wrapping accuracy."""

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__("Wrapping", "Wrapping", parent)
        self.model = model
        self.cad_meshes = cad_meshes
        self.created_name: Optional[str] = None
        self.body.addWidget(_capability_note(
            "MVP: Convex hull from tessellation AABB / point cloud. "
            "Specify wrapping accuracy uses hull with inflated margin.",
            self))
        form = QFormLayout()
        self.target = QComboBox(self)
        self.target.addItems(_part_names(model))
        form.addRow("Target", self.target)
        self.body.addLayout(form)
        typ = QGroupBox("Type", self)
        tl = QVBoxLayout(typ)
        self.rb_hull = QRadioButton("Convex hull", typ)
        self.rb_acc = QRadioButton("Specify wrapping accuracy", typ)
        self.rb_hull.setChecked(True)
        tl.addWidget(self.rb_hull)
        tl.addWidget(self.rb_acc)
        self.accuracy = QDoubleSpinBox(typ)
        self.accuracy.setRange(0.0, 1.0)
        self.accuracy.setDecimals(4)
        self.accuracy.setValue(0.5)
        tl.addWidget(self.accuracy)
        self.leave = QCheckBox("Leave edges", typ)
        tl.addWidget(self.leave)
        self.body.addWidget(typ)
        self._root.addLayout(_bottom_buttons(self, (
            ("Execute", self._exec),
            ("Close", self.accept),
        )))

    def _exec(self) -> None:
        name = self.target.currentText()
        bounds = ops.part_world_bounds(self.model, name, self.cad_meshes)
        if bounds is None:
            QMessageBox.warning(self, "Wrapping",
                                "No geometry for target.")
            return
        lo, hi = bounds
        new = ops.unique_part_name(self.model, f"{name}_wrap")
        el = self.model.add_part(name=new, kind="cube", attribute="solid")
        if el is None:
            return
        from cabxml import set_text
        from xml.etree.ElementTree import SubElement
        size = hi - lo
        for tag, val in (
                ("base", ",".join(f"{v:.17g}" for v in lo)),
                ("size", ",".join(f"{v:.17g}" for v in size)),
        ):
            c = _first(el, tag)
            if c is None:
                c = SubElement(el, tag)
                c.tail = "\n         "
            set_text(c, val)
        self.created_name = new
        self.applied = True
        QMessageBox.information(
            self, "Wrapping",
            f"Wrapped as '{new}' (AABB / convex-hull proxy).")


# ------------------------------------------- Reset Computational Domain


class ResetComputationalDomainDialog(_EditDlg):
    """[Reset Computational Domain] — distinct from Edit Computational Domain."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Reset Computational Domain",
                         "Reset Computational Domain", parent)
        self.model = model

        dom = QGroupBox("Computational domain setting", self)
        dl = QVBoxLayout(dom)
        self.chk_update = QCheckBox("Update computational domain", dom)
        self.chk_update.setChecked(True)
        dl.addWidget(self.chk_update)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Coordinate System", dom))
        self.coord = QComboBox(dom)
        self.coord.addItems([
            "Cartesian System", "Cylindrical System", "Axis Symmetry"])
        crow.addWidget(self.coord, 1)
        dl.addLayout(crow)
        self.chk_periodic = QCheckBox(
            "Periodic boundary in Y direction", dom)
        dl.addWidget(self.chk_periodic)
        self.body.addWidget(dom)

        grav = QGroupBox("Gravity and Default Values", self)
        gl = QVBoxLayout(grav)
        grow = QHBoxLayout()
        self.chk_grav = QCheckBox("Acceleration of gravity", grav)
        self.chk_grav.setChecked(True)
        grow.addWidget(self.chk_grav)
        self.grav_acc = QDoubleSpinBox(grav)
        self.grav_acc.setRange(0.0, 1000.0)
        self.grav_acc.setDecimals(4)
        self.grav_acc.setValue(9.8)
        grow.addWidget(self.grav_acc)
        self.grav_unit = QComboBox(grav)
        self.grav_unit.addItems(["m/s2", "cm/s2", "ft/s2"])
        grow.addWidget(self.grav_unit)
        gl.addLayout(grow)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Direction", grav))
        self.grav_dir = QComboBox(grav)
        self.grav_dir.addItems([
            "-Z", "+Z", "-Y", "+Y", "-X", "+X"])
        drow.addWidget(self.grav_dir, 1)
        gl.addLayout(drow)

        trow = QHBoxLayout()
        self.chk_temp = QCheckBox("Default Temperature", grav)
        self.chk_temp.setChecked(True)
        trow.addWidget(self.chk_temp)
        self.temp = QDoubleSpinBox(grav)
        self.temp.setRange(-273.0, 1e6)
        self.temp.setDecimals(2)
        try:
            self.temp.setValue(float(
                model.project_value("ambient_temperature", "20") or 20))
        except ValueError:
            self.temp.setValue(20.0)
        trow.addWidget(self.temp)
        gl.addLayout(trow)
        self.chk_all_temp = QCheckBox(
            "Update part and boundary temperature all together", grav)
        gl.addWidget(self.chk_all_temp)

        erow = QHBoxLayout()
        self.chk_emis = QCheckBox("Default emissivity", grav)
        self.chk_emis.setChecked(True)
        erow.addWidget(self.chk_emis)
        self.emis = QDoubleSpinBox(grav)
        self.emis.setRange(0.0, 1.0)
        self.emis.setDecimals(3)
        try:
            self.emis.setValue(float(
                model.project_value("default_emissivity", "0.9") or 0.9))
        except ValueError:
            self.emis.setValue(0.9)
        erow.addWidget(self.emis)
        gl.addLayout(erow)
        self.body.addWidget(grav)

        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _ok(self) -> None:
        vec_map = {
            "-Z": (0.0, 0.0, -1.0), "+Z": (0.0, 0.0, 1.0),
            "-Y": (0.0, -1.0, 0.0), "+Y": (0.0, 1.0, 0.0),
            "-X": (-1.0, 0.0, 0.0), "+X": (1.0, 0.0, 0.0),
        }
        acc = self.grav_acc.value()
        unit = self.grav_unit.currentText()
        if unit == "cm/s2":
            acc /= 100.0
        elif unit == "ft/s2":
            acc *= 0.3048
        ops.apply_reset_domain(
            self.model,
            update_domain=self.chk_update.isChecked(),
            coordinate=self.coord.currentText(),
            periodic_y=self.chk_periodic.isChecked(),
            update_gravity=self.chk_grav.isChecked(),
            gravity_acc=acc,
            gravity_vec=vec_map[self.grav_dir.currentText()],
            update_temp=self.chk_temp.isChecked(),
            default_temp=self.temp.value(),
            update_all_temps=self.chk_all_temp.isChecked(),
            update_emissivity=self.chk_emis.isChecked(),
            default_emissivity=self.emis.value(),
        )
        self.applied = True
        self.accept()


# -------------------------------------------------------- Wiring / Image


class EditWiringOnBoardDialog(_EditDlg):
    """[Edit wiring of board] — Basic setting / Gerber / Thermal Via tabs."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Edit wiring of board", "Edit wiring of board",
                         parent)
        self.model = model
        tabs = QTabWidget(self)
        basic = QWidget(tabs)
        bl = QFormLayout(basic)
        self.board = QComboBox(basic)
        self.board.addItems(_part_names(model))
        bl.addRow("Board part", self.board)
        self.coord = QComboBox(basic)
        self.coord.addItems(["XY", "YZ", "ZX"])
        bl.addRow("Coordinate system of board", self.coord)
        tabs.addTab(basic, "Basic setting")

        gerber = QWidget(tabs)
        gl = QVBoxLayout(gerber)
        grow = QHBoxLayout()
        self.gerber_path = QLineEdit(gerber)
        btn = QPushButton("...", gerber)
        btn.clicked.connect(self._browse_gerber)
        grow.addWidget(QLabel("Gerber file", gerber))
        grow.addWidget(self.gerber_path, 1)
        grow.addWidget(btn)
        gl.addLayout(grow)
        gl.addStretch(1)
        tabs.addTab(gerber, "Wiring (Gerber)")

        via = QWidget(tabs)
        vl = QFormLayout(via)
        self.via_dia = QDoubleSpinBox(via)
        self.via_dia.setRange(0.0, 1e3)
        self.via_dia.setDecimals(3)
        self.via_dia.setValue(0.3)
        vl.addRow("Thermal via diameter", self.via_dia)
        tabs.addTab(via, "Thermal Via")
        self.body.addWidget(tabs)

        self._root.addLayout(_bottom_buttons(self, (
            ("Register", self._reg),
            ("Close", self.accept),
        )))

    def _browse_gerber(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Gerber file", "",
            "Gerber (*.gbr *.ger *.pho);;All (*.*)")
        if path:
            self.gerber_path.setText(path)

    def _reg(self) -> None:
        meta = "-|-"
        path = self.gerber_path.text().strip()
        if path:
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                meta = f"{len(raw)}|{raw.count(b'\n') + 1}"
            except OSError:
                meta = "err|-"
        self.model.set_project_value(
            "board_wiring",
            f"{self.board.currentText()}|{self.coord.currentText()}|"
            f"{self.gerber_path.text()}|{self.via_dia.value():g}|{meta}")
        self.applied = True
        QMessageBox.information(
            self, "Edit wiring of board",
            "Wiring information registered.")


class PlaceImageDialog(_EditDlg):
    """[Place Image] — length correction + origin."""

    def __init__(self, model: StpreModel, parent=None):
        super().__init__("Place Image", "Place Image", parent)
        self.model = model
        path_row = QHBoxLayout()
        self.path = QLineEdit(self)
        btn = QPushButton("...", self)
        btn.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Image (24-bit BMP)", self))
        path_row.addWidget(self.path, 1)
        path_row.addWidget(btn)
        self.body.addLayout(path_row)

        g1 = QGroupBox(
            "(1) Correction of length by selecting two points on the image.",
            self)
        l1 = QFormLayout(g1)
        self.distance = QDoubleSpinBox(g1)
        self.distance.setRange(0.0, 1e6)
        self.distance.setDecimals(3)
        self.distance.setValue(100.0)
        l1.addRow("Distance between the two points", self.distance)
        self.body.addWidget(g1)

        g2 = QGroupBox("(2) Setting of coordinate origin", self)
        l2 = QFormLayout(g2)
        self.ox = QDoubleSpinBox(g2)
        self.oy = QDoubleSpinBox(g2)
        self.oz = QDoubleSpinBox(g2)
        for w in (self.ox, self.oy, self.oz):
            w.setRange(-1e6, 1e6)
            w.setDecimals(3)
        l2.addRow("Origin X", self.ox)
        l2.addRow("Origin Y", self.oy)
        l2.addRow("Z coordinate", self.oz)
        self.body.addWidget(g2)

        self._root.addLayout(_bottom_buttons(self, (
            ("Undo settings", self._undo_settings),
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Place Image", "",
            "Bitmap (*.bmp);;All (*.*)")
        if path:
            self.path.setText(path)

    def _undo_settings(self) -> None:
        self.distance.setValue(100.0)
        self.ox.setValue(0.0)
        self.oy.setValue(0.0)
        self.oz.setValue(0.0)

    def _ok(self) -> None:
        if not self.path.text().strip():
            QMessageBox.warning(self, "Place Image",
                                "Select a 24-bit BMP image.")
            return
        self.model.set_project_value(
            "placed_image",
            f"{self.path.text()}|{self.distance.value():g}|"
            f"{self.ox.value():g},{self.oy.value():g},{self.oz.value():g}")
        self.applied = True
        self.accept()


# ------------------------------------------- Layout tree context dialogs


class TranslationCopyPartDialog(_EditDlg):
    """Tree context: Translation/Copy Part (distance + optional copies)."""

    def __init__(self, model: StpreModel, names: list[str], parent=None):
        super().__init__("Translation/Copy Part", "Translation/Copy Part",
                         parent)
        self.model = model
        self.names = list(names)
        self.created: list[str] = []
        self.created_pairs: list[tuple[str, str]] = []
        self.body.addWidget(QLabel(
            f"Parts: {', '.join(self.names) or '(none)'}", self))
        form = QFormLayout()
        self.dx = QDoubleSpinBox(self)
        self.dy = QDoubleSpinBox(self)
        self.dz = QDoubleSpinBox(self)
        for w in (self.dx, self.dy, self.dz):
            w.setRange(-1e7, 1e7)
            w.setDecimals(3)
            w.setValue(0.0)
        drow = QHBoxLayout()
        drow.addWidget(self.dx)
        drow.addWidget(self.dy)
        drow.addWidget(self.dz)
        form.addRow("Distance (mm)", drow)
        self.trans_only = QCheckBox("Translation only", self)
        self.trans_only.setChecked(True)
        form.addRow(self.trans_only)
        self.n_copies = QSpinBox(self)
        self.n_copies.setRange(1, 999)
        self.n_copies.setValue(1)
        self.n_copies.setEnabled(False)
        form.addRow("The number of copies", self.n_copies)
        self.trans_only.toggled.connect(
            lambda on: self.n_copies.setEnabled(not on))
        self.body.addLayout(form)
        self._root.addLayout(_bottom_buttons(self, (
            ("OK", self._ok),
            ("Cancel", self.reject),
        )))

    def _ok(self) -> None:
        if not self.names:
            QMessageBox.warning(self, "Translation/Copy Part",
                                "No parts selected.")
            return
        delta = (self.dx.value(), self.dy.value(), self.dz.value())
        n = 0 if self.trans_only.isChecked() else int(self.n_copies.value())
        self.created_pairs = ops.translate_copy_parts(
            self.model, self.names, delta, n)
        self.created = [dst for _src, dst in self.created_pairs]
        self.applied = True
        self.accept()


class ChangePartSettingTogetherDialog(_EditDlg):
    """Tree context: Change part setting together (batch attribute edits)."""

    def __init__(self, model: StpreModel, names: list[str],
                 props: Optional[object] = None, parent=None):
        super().__init__("Change Settings", "Change part setting together",
                         parent)
        self.model = model
        self.names = list(names)
        self.props = props
        self.body.addWidget(QLabel(
            f"Selected parts ({len(self.names)}): "
            f"{', '.join(self.names[:8])}"
            + ("…" if len(self.names) > 8 else ""), self))

        form = QFormLayout()
        self.apply_mat = QCheckBox("Apply", self)
        self.material = QLineEdit(self)
        mrow = QHBoxLayout()
        mrow.addWidget(self.material, 1)
        mrow.addWidget(self.apply_mat)
        pick = QPushButton("Material…", self)
        pick.clicked.connect(self._pick_material)
        mrow.addWidget(pick)
        form.addRow("Material", mrow)

        self.apply_attr = QCheckBox("Apply", self)
        self.attribute = QComboBox(self)
        self.attribute.addItems(
            ["solid", "fluid", "panel", "Solid", "Fluid", "Panel"])
        arow = QHBoxLayout()
        arow.addWidget(self.attribute, 1)
        arow.addWidget(self.apply_attr)
        form.addRow("Attribute", arow)

        self.apply_color = QCheckBox("Apply", self)
        self.color = QLineEdit(self)
        self.color.setText("25,117,255,255")
        crow = QHBoxLayout()
        crow.addWidget(self.color, 1)
        crow.addWidget(self.apply_color)
        form.addRow("Color RGBA", crow)

        self.apply_virt = QCheckBox("Apply", self)
        self.virtual = QCheckBox("Virtual part", self)
        vrow = QHBoxLayout()
        vrow.addWidget(self.virtual, 1)
        vrow.addWidget(self.apply_virt)
        form.addRow("Other settings", vrow)

        self.apply_mon = QCheckBox("Apply", self)
        self.monitor = QCheckBox("Output to Monitor", self)
        orow = QHBoxLayout()
        orow.addWidget(self.monitor, 1)
        orow.addWidget(self.apply_mon)
        form.addRow("", orow)
        self.body.addLayout(form)
        self._root.addLayout(_bottom_buttons(self, (
            ("Set", self._ok),
            ("Close", self.reject),
        )))

    def _pick_material(self) -> None:
        try:
            from cab_dialogs import MaterialListDialog
        except Exception:
            return
        dlg = MaterialListDialog(self.props, parent=self,
                                 current=self.material.text().strip())
        if dlg.exec_() and dlg.selected_material():
            self.material.setText(dlg.selected_material())
            self.apply_mat.setChecked(True)

    def _ok(self) -> None:
        if not self.names:
            QMessageBox.warning(self, "Change Settings",
                                "No parts selected.")
            return
        if not any((self.apply_mat.isChecked(), self.apply_attr.isChecked(),
                    self.apply_color.isChecked(), self.apply_virt.isChecked(),
                    self.apply_mon.isChecked())):
            QMessageBox.warning(
                self, "Change Settings",
                "Check Apply on at least one setting.")
            return
        for name in self.names:
            if self.apply_mat.isChecked():
                mat = self.material.text().strip()
                if mat:
                    self.model.set_part_property(name, mat)
            if self.apply_attr.isChecked():
                self.model.set_part_attribute(
                    name, self.attribute.currentText())
            if self.apply_color.isChecked():
                parts = self.color.text().split(",")[:4]
                if len(parts) == 4 and all(
                        x.strip().lstrip("-").isdigit() for x in parts):
                    self.model.set_part_color(
                        name, tuple(int(x) for x in parts))
            if self.apply_virt.isChecked():
                self.model.set_part_virtual(name, self.virtual.isChecked())
            if self.apply_mon.isChecked():
                self.model.set_part_monitor(name, self.monitor.isChecked())
        self.applied = True
        self.accept()
