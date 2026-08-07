"""STpre-style panes for cab_gui: Tree/List, Control, Message, PaneFrame."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QRadioButton,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QPlainTextEdit,
)

from cab_icons import AppIcons
from cabxml import PropertyModel, StpreModel, _children, _first


class PaneFrame(QFrame):
    """Title bar + content pane (from pph_gui)."""

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("PaneFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(24)
        bar.setAutoFillBackground(True)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 6, 0)
        self.title_label = QLabel(title, bar)
        self.title_label.setObjectName("PaneTitle")
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        lay.addWidget(bar)
        host = QFrame(self)
        host.setObjectName("PaneBody")
        host.setAutoFillBackground(True)
        host.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(content, 1)
        lay.addWidget(host, 1)
        self._content = content

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class MessageWindow(QWidget):
    """Message Window: operation log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(2, 2, 2, 2)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(2000)
        self.text.setPlaceholderText("Messages…")
        v.addWidget(self.text)

    def log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText(f"[{ts}] {level}: {msg}")
        self.text.verticalScrollBar().setValue(
            self.text.verticalScrollBar().maximum())

    def set_max_blocks(self, n: int) -> None:
        self.text.setMaximumBlockCount(max(100, int(n)))

    def clear(self) -> None:
        self.text.clear()


class TreeListView(QWidget):
    """Tree/List View Window: Layout of Parts / Conditions / Archive."""

    visibility_changed = pyqtSignal(str, str, bool)  # kind, name, visible
    item_selected = pyqtSignal(str, object)          # kind, name
    item_activated = pyqtSignal(str, object)         # kind, name (double-click)
    status_requested = pyqtSignal(str)               # message
    context_action = pyqtSignal(str, str, object)    # action, kind, name

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.layout_tree = QTreeWidget(self)
        self.layout_tree.setHeaderLabels(["Layout of Parts"])
        self.layout_tree.setIconSize(QSize(16, 16))
        self.layout_tree.itemChanged.connect(self._on_item_changed)
        self.layout_tree.itemSelectionChanged.connect(self._on_selection)
        self.layout_tree.itemDoubleClicked.connect(self._on_double_click)
        self.layout_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layout_tree.customContextMenuRequested.connect(
            self._layout_context)
        self.cond_tree = QTreeWidget(self)
        self.cond_tree.setHeaderLabels(["Conditions"])
        self.cond_tree.setIconSize(QSize(16, 16))
        self.cond_tree.itemSelectionChanged.connect(self._on_cond_selection)
        self.archive_tree = QTreeWidget(self)
        self.archive_tree.setHeaderLabels(["Member", "Size"])
        self.archive_tree.setIconSize(QSize(16, 16))
        self.archive_tree.itemSelectionChanged.connect(
            self._on_archive_selection)
        self.tabs.addTab(self.layout_tree, "Layout of Parts")
        self.tabs.addTab(self.cond_tree, "Conditions")
        self.tabs.addTab(self.archive_tree, "Archive")
        v.addWidget(self.tabs)
        self._block = False

    # -- populate ----------------------------------------------------------

    def clear(self) -> None:
        self.layout_tree.clear()
        self.cond_tree.clear()
        self.archive_tree.clear()

    def populate(self, model: StpreModel, archive_members: list) -> None:
        self._populate_layout(model)
        self._populate_conditions(model)
        self._populate_archive(archive_members)

    def _add(self, parent, label, data, icon=None, checkable=False,
             checked=True):
        item = QTreeWidgetItem([label] if parent.columnCount() == 1
                               else [label, ""])
        item.setData(0, Qt.UserRole, data)
        if icon:
            item.setIcon(0, AppIcons.get(icon, 16))
        if checkable:
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable
                          | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _populate_layout(self, model: StpreModel) -> None:
        tree = self.layout_tree
        self._block = True
        tree.clear()
        parts_root = self._add(tree, "Parts", ("parts_root", None),
                               "folder", checkable=True)
        # Computational_Domain
        domain = self._add(parts_root, "Computational_Domain",
                           ("domain_folder", None), "domain")
        ar = model.analysis_region()
        dname = "Domain(cuboid)"
        if ar is not None:
            n = _first(ar, "name")
            if n is not None and n.text:
                dname = n.text.strip()
        self._add(domain, dname, ("domain", dname), "domain",
                  checkable=True, checked=True)
        mb = model.mesh_block()
        bname = "RootBlock"
        if mb is not None:
            n = _first(mb, "name")
            if n is not None and n.text:
                bname = n.text.strip()
        axes = model.mesh_axes()
        axis_info = ""
        if axes:
            axis_info = (f"  [{len(axes.get('x', []))}×"
                         f"{len(axes.get('y', []))}×"
                         f"{len(axes.get('z', []))}]")
        self._add(domain, bname + axis_info, ("mesh_block", bname), "mesh")

        # groups / parts
        root_parts = [p for p in model.parts() if not p.group]
        if root_parts:
            gnode = self._add(parts_root, "(ungrouped)", ("group", ""),
                              "group", checkable=True)
            for p in root_parts:
                self._add(gnode, f"{p.name}  [{p.property}]",
                          ("part", p.name), "part", checkable=True)
        for grp in model.groups():
            gname = ""
            n = _first(grp, "name")
            if n is not None and n.text:
                gname = n.text.strip()
            gnode = self._add(parts_root, gname or "(ungrouped)",
                              ("group", gname), "group", checkable=True)
            for p in model.parts():
                if p.group != gname:
                    continue
                self._add(gnode, f"{p.name}  [{p.property}]",
                          ("part", p.name), "part", checkable=True)

        # Region: domain faces + registered regions
        reg_root = self._add(parts_root, "Region", ("region_folder", None),
                             "folder")
        if ar is not None:
            for reg in _children(ar, "region"):
                n = _first(reg, "name")
                if n is None or not n.text:
                    continue
                rname = n.text.strip()
                self._add(reg_root, rname, ("domain_face", rname), "region")
        for r in model.regions():
            n = _first(r, "name")
            if n is None or not n.text:
                continue
            rname = n.text.strip()
            self._add(reg_root, rname, ("region", rname), "region")

        others = self._add(parts_root, "Others", ("others", None), "folder")
        self._add(others, "(empty)", ("others_empty", None), "generic")

        parts_root.setExpanded(True)
        domain.setExpanded(True)
        for i in range(parts_root.childCount()):
            parts_root.child(i).setExpanded(True)
        self._block = False

    def _populate_conditions(self, model: StpreModel) -> None:
        tree = self.cond_tree
        tree.clear()
        vals = self._add(tree, f"Values ({len(model.values())})",
                         ("values_root", None), "condition")
        for v in model.values():
            n = _first(v, "name")
            name = n.text.strip() if n is not None and n.text else "?"
            self._add(vals, name, ("value", name), "condition")
        conds = self._add(tree, f"Conditions ({len(model.conditions())})",
                          ("conditions_root", None), "condition")
        for c in model.conditions():
            n = _first(c, "name")
            name = n.text.strip() if n is not None and n.text else "?"
            self._add(conds, name, ("condition", name), "condition")
        vals.setExpanded(True)
        conds.setExpanded(True)

    def _populate_archive(self, members: list) -> None:
        tree = self.archive_tree
        tree.clear()
        for m in members:
            name = getattr(m, "name", str(m))
            size = getattr(m, "data", None)
            nbytes = len(size) if size is not None else getattr(m, "cbFile", 0)
            item = QTreeWidgetItem([name, f"{nbytes:,} B"])
            item.setData(0, Qt.UserRole, ("archive", name))
            ext = os.path.splitext(name)[1].lower()
            if ext == ".xml":
                icon = "xml"
            elif ext in (".x_t", ".xt"):
                icon = "part"
            else:
                icon = "generic"
            item.setIcon(0, AppIcons.get(icon, 16))
            tree.addTopLevelItem(item)

    # -- lookup ------------------------------------------------------------

    def find_part_item(self, name: str) -> Optional[QTreeWidgetItem]:
        def walk(item):
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "part" and data[1] == name:
                return item
            for i in range(item.childCount()):
                hit = walk(item.child(i))
                if hit is not None:
                    return hit
            return None

        for i in range(self.layout_tree.topLevelItemCount()):
            hit = walk(self.layout_tree.topLevelItem(i))
            if hit is not None:
                return hit
        return None

    # -- events ------------------------------------------------------------

    def _on_item_changed(self, item, _col) -> None:
        if self._block:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, name = data
        checked = item.checkState(0) == Qt.Checked
        if kind == "part" and name:
            self.visibility_changed.emit("part", name, checked)
        elif kind == "domain" and name:
            # Checked = opaque face mode; unchecked = volume wireframe
            self.visibility_changed.emit("domain", name, checked)
        elif kind == "group":
            self._block = True
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                cdata = child.data(0, Qt.UserRole)
                if cdata and cdata[0] == "part":
                    self.visibility_changed.emit("part", cdata[1], checked)
            self._block = False
        elif kind == "parts_root":
            self._block = True
            for i in range(item.childCount()):
                child = item.child(i)
                if child.flags() & Qt.ItemIsUserCheckable:
                    child.setCheckState(
                        0, Qt.Checked if checked else Qt.Unchecked)
            self._block = False

    def _emit_selection(self, item) -> None:
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if data:
            self.item_selected.emit(data[0], data[1])

    def _on_selection(self) -> None:
        items = self.layout_tree.selectedItems()
        self._emit_selection(items[0] if items else None)

    def _on_cond_selection(self) -> None:
        items = self.cond_tree.selectedItems()
        self._emit_selection(items[0] if items else None)

    def _on_archive_selection(self) -> None:
        items = self.archive_tree.selectedItems()
        self._emit_selection(items[0] if items else None)

    def _layout_context(self, pos) -> None:
        item = self.layout_tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, name = data
        menu = QMenu(self)
        if kind == "part":
            menu.addAction("Reference (Edit Part)",
                           lambda: self.context_action.emit(
                               "refer", kind, name))
            menu.addAction("Display Part",
                           lambda: self._set_checked(item, True))
            menu.addAction("Hide Part",
                           lambda: self._set_checked(item, False))
        elif kind == "domain":
            menu.addAction("Reference (Edit Computational Domain)",
                           lambda: self.context_action.emit(
                               "refer", kind, name))
        elif kind == "mesh_block":
            menu.addAction("Gridding…",
                           lambda: self.context_action.emit(
                               "refer", kind, name))
        if not menu.isEmpty():
            menu.exec_(self.layout_tree.viewport().mapToGlobal(pos))

    def _on_double_click(self, item, _col) -> None:
        data = item.data(0, Qt.UserRole)
        if data and data[0] in ("domain", "mesh_block", "part"):
            self.item_activated.emit(data[0], data[1])

    def _set_checked(self, item, on: bool) -> None:
        item.setCheckState(0, Qt.Checked if on else Qt.Unchecked)


class ControlWindow(QWidget):
    """Control Window: Show/Select + Property + Library."""

    drawing_mode_changed = pyqtSignal(str)           # Line/Shading/Translucent
    layer_toggled = pyqtSignal(str, bool)            # layer key, on
    selection_target_changed = pyqtSignal(str)       # Part/Face/...
    apply_requested = pyqtSignal()

    LAYER_KEYS = [
        # Aligned with STpre Show/Select — Part + Element division can both be ON
        ("Part", "part", True),
        ("Mesh Block", "mesh_block", True),     # magenta coarse grid (STpre)
        ("Element division", "element", True),  # mesh lines on part + domain
        ("Face division", "face", False),
        ("Condition", "condition", False),
        ("Sketch plane", "sketch_plane", False),
        ("Domain frame", "domain_frame", True),
        ("Mesh", "mesh", True),                 # with Element: domain wireframe
        ("Axis (Global)", "axis_global", True),
        ("Axis (Sketch)", "axis_sketch", False),
        ("Origin", "origin", False),
        ("Aspect ratio", "aspect_ratio", False),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_show_select(), "Show/Select")
        self.prop_page = QWidget(self)
        self.prop_layout = QFormLayout(self.prop_page)
        self.prop_title = QLabel("选择树节点查看属性")
        self.prop_layout.addRow(self.prop_title)
        self.prop_fields: dict[str, QWidget] = {}
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        self.tabs.addTab(self.prop_page, "Property")
        self.lib_tree = QTreeWidget(self)
        self.lib_tree.setHeaderLabels(["Material", ""])
        self.tabs.addTab(self.lib_tree, "Library")
        v.addWidget(self.tabs)
        self._prop_target = ("", None)
        self._drawing_mode = "Shading"

    def _build_show_select(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        draw_box = QGroupBox("Drawing ON/OFF", page)
        gl = QVBoxLayout(draw_box)
        self.layer_checks: dict[str, QCheckBox] = {}
        for label, key, default in self.LAYER_KEYS:
            cb = QCheckBox(label, draw_box)
            cb.setChecked(default)
            cb.toggled.connect(
                lambda on, k=key: self.layer_toggled.emit(k, on))
            self.layer_checks[key] = cb
            gl.addWidget(cb)
        lay.addWidget(draw_box)

        mode_box = QGroupBox("Drawing mode", page)
        ml = QHBoxLayout(mode_box)
        self.mode_group = QButtonGroup(mode_box)
        for text in ("Line", "Shading", "Translucent"):
            rb = QRadioButton(text, mode_box)
            self.mode_group.addButton(rb)
            ml.addWidget(rb)
            if text == "Shading":
                rb.setChecked(True)
            rb.toggled.connect(self._on_mode)
        lay.addWidget(mode_box)
        tip = QLabel(
            "Line + Element = 结构化面网格线；"
            "勾选 Domain(cuboid)=面模式；取消=体网格线框（同 STpre Layout）",
            page)
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #555; font-size: 11px;")
        lay.addWidget(tip)

        sel_box = QGroupBox("Target of selection", page)
        sl = QVBoxLayout(sel_box)
        self.sel_group = QButtonGroup(sel_box)
        for text in ("Part", "Face", "Vertice", "Domain boundary"):
            rb = QRadioButton(text, sel_box)
            self.sel_group.addButton(rb)
            sl.addWidget(rb)
            if text == "Part":
                rb.setChecked(True)
            rb.toggled.connect(self._on_sel_target)
        lay.addWidget(sel_box)
        lay.addStretch(1)
        return page

    def _on_mode(self, checked: bool) -> None:
        if not checked:
            return
        btn = self.mode_group.checkedButton()
        if btn:
            self._drawing_mode = btn.text()
            self.drawing_mode_changed.emit(self._drawing_mode)

    def _on_sel_target(self, checked: bool) -> None:
        if not checked:
            return
        btn = self.sel_group.checkedButton()
        if btn:
            self.selection_target_changed.emit(btn.text())

    def set_drawing_mode(self, mode: str) -> None:
        for btn in self.mode_group.buttons():
            if btn.text() == mode:
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
                self._drawing_mode = mode
                break

    def drawing_mode(self) -> str:
        return self._drawing_mode

    def layer_on(self, key: str) -> bool:
        cb = self.layer_checks.get(key)
        return cb.isChecked() if cb else False

    def populate_library(self, props: Optional[PropertyModel]) -> None:
        self.lib_tree.clear()
        if props is None:
            return
        for name in props.material_names():
            item = QTreeWidgetItem([name, ""])
            item.setIcon(0, AppIcons.get("library", 16))
            item.setData(0, Qt.UserRole, ("material", name))
            self.lib_tree.addTopLevelItem(item)

    # -- property form -----------------------------------------------------

    def clear_property(self) -> None:
        # Detach Apply before removeRow (which deletes child widgets).
        if self.apply_btn.parent() is not None:
            self.prop_layout.removeWidget(self.apply_btn)
            self.apply_btn.setParent(self)
        while self.prop_layout.rowCount():
            self.prop_layout.removeRow(0)
        self.prop_fields.clear()
        self.prop_title = QLabel("选择树节点查看属性")
        self.prop_layout.addRow(self.prop_title)
        if self.apply_btn is None or not hasattr(self.apply_btn, "setEnabled"):
            self.apply_btn = QPushButton("Apply")
            self.apply_btn.clicked.connect(self.apply_requested.emit)
        self.apply_btn.setEnabled(False)
        self._prop_target = ("", None)

    def show_property(self, kind: str, name, model: Optional[StpreModel],
                      props: Optional[PropertyModel]) -> None:
        self.clear_property()
        self._prop_target = (kind, name)
        self.tabs.setCurrentWidget(self.prop_page)

        def field(label, value, ro=False, combo=None):
            if combo is not None:
                w = QComboBox()
                w.addItems(combo)
                idx = w.findText(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                else:
                    w.setEditText(value) if w.isEditable() else None
                    w.addItem(value)
                    w.setCurrentText(value)
                w.setEnabled(not ro)
            else:
                w = QLineEdit("" if value is None else str(value))
                w.setReadOnly(ro)
            self.prop_layout.addRow(label, w)
            self.prop_fields[label] = w
            return w

        if kind == "part" and name and model is not None:
            part = next((p for p in model.parts() if p.name == name), None)
            if part is None:
                return
            self.prop_title.setText(f"Part: {name}")
            mats = props.material_names() if props else []
            field("名称", part.name)
            field("材料", part.property, combo=mats or None)
            field("类型", part.kind, ro=True)
            field("属性", part.attribute, ro=True)
            field("颜色 RGBA", part.color)
            field("体积", part.volume, ro=True)
            field("组", part.group, ro=True)
            self.apply_btn.setEnabled(True)
            self.prop_layout.addRow(self.apply_btn)
        elif kind == "domain" and model is not None:
            ar = model.analysis_region()
            self.prop_title.setText("Computational Domain")
            if ar is not None:
                for tag in ("name", "base", "size", "color", "property"):
                    el = _first(ar, tag)
                    field(tag, el.text.strip() if el is not None and el.text
                          else "", ro=True)
        elif kind == "mesh_block" and model is not None:
            axes = model.mesh_axes()
            self.prop_title.setText("Mesh Block")
            for ax, vals in axes.items():
                field(f"{ax} points", str(len(vals)), ro=True)
                if vals:
                    field(f"{ax} range (mm)",
                          f"{vals[0]:g} … {vals[-1]:g}", ro=True)
        elif kind == "value" and name and model is not None:
            el = model.find_value(name)
            self.prop_title.setText(f"Value: {name}")
            if el is not None:
                for ch in el:
                    if ch.tag == "name":
                        continue
                    field(ch.tag, (ch.text or "").strip())
                self.apply_btn.setEnabled(True)
                self.prop_layout.addRow(self.apply_btn)
        elif kind == "condition" and name:
            self.prop_title.setText(f"Condition: {name}")
            field("名称", name, ro=True)
        elif kind == "material" and name and props is not None:
            self.prop_title.setText(f"Material: {name}")
            entry = props.find_entry(name)
            if entry is not None:
                for ch in entry:
                    field(ch.tag, (ch.text or "").strip(), ro=True)
        elif kind == "archive" and name:
            self.prop_title.setText(f"Archive: {name}")
            field("成员", name, ro=True)
        elif kind in ("region", "domain_face") and name:
            self.prop_title.setText(f"Region: {name}")
            field("名称", name, ro=True)
        else:
            self.prop_title.setText(kind or "Property")

    def prop_target(self):
        return self._prop_target

    def field_text(self, label: str) -> str:
        w = self.prop_fields.get(label)
        if w is None:
            return ""
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""
