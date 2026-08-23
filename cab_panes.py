"""STpre-style panes for cab_gui: Tree/List, Control, Message, PaneFrame."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import time

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QRadioButton, QStyle, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QPlainTextEdit,
)

from cab_icons import AppIcons
from cabxml import (
    DOMAIN_FACE_NAMES, PropertyModel, StpreModel, _children, _first,
)

try:  # strip insignificant trailing zeros on coordinate spin boxes
    from cab_widgets import CoordSpinBox as QDoubleSpinBox
except Exception:  # pragma: no cover
    from PyQt5.QtWidgets import QDoubleSpinBox


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


class ConvergenceWindow(QWidget):
    """P1-1 Convergence Window: solver residual curve.

    QPainter 自绘 (仓库惯例, 不引 matplotlib/pyqtgraph):
      - Y 轴 log10 刻度 (残差跨数量级);
      - X 轴为点序号, 两端标注 cycle 号 (标签缺失时按序绘);
      - 少于 2 点时显示占位提示。
    """

    _MARGIN_L, _MARGIN_R, _MARGIN_T, _MARGIN_B = 46, 14, 10, 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []  # [(cycle, residual), ...]
        self.setMinimumHeight(110)

    # ------------------------------------------------------------- data API

    def set_points(self, points) -> None:
        self._points = [(int(c), float(v)) for c, v in points]
        self.update()

    def add_point(self, cycle: int, value: float) -> None:
        self._points.append((int(cycle), float(value)))
        self.update()

    def clear(self) -> None:
        self._points = []
        self.update()

    def points(self) -> list:
        return list(self._points)

    # ------------------------------------------------------------- painting

    def paintEvent(self, event) -> None:
        from PyQt5.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        left = self._MARGIN_L
        top = self._MARGIN_T
        plot_w = max(10, self.width() - left - self._MARGIN_R)
        plot_h = max(10, self.height() - top - self._MARGIN_B)
        pts = self._points
        if len(pts) < 2:
            p.setPen(QColor(130, 130, 130))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Convergence graph — no residual data yet")
            return
        import math
        # log10 映射; 非正值钳到极小, 保证跨零/负残差不崩
        logs = [math.log10(v) if v > 0 else -300.0 for _, v in pts]
        lo, hi = min(logs), max(logs)
        if hi - lo < 1e-9:            # 全等值: 留出上下边距
            hi = lo + 1.0
        span = hi - lo

        def _x(i: float) -> float:
            return left + plot_w * (i / (len(pts) - 1))

        def _y(lv: float) -> float:
            return top + plot_h * (1.0 - (lv - lo) / span)

        # 框架: 边框 + 中值横网格线
        p.setPen(QPen(QColor(190, 190, 190), 1))
        p.drawRect(int(left), int(top), int(plot_w), int(plot_h))
        mid = _y((lo + hi) / 2.0)
        p.drawLine(int(left), int(mid), int(left + plot_w), int(mid))
        # 曲线
        p.setPen(QPen(QColor(31, 78, 148), 2))
        poly = []
        for i, lv in enumerate(logs):
            poly.append((_x(i), _y(lv)))
        for k in range(len(poly) - 1):
            p.drawLine(*[int(round(v)) for v in poly[k]],
                       *[int(round(v)) for v in poly[k + 1]])
        # 末点标记
        p.setBrush(QColor(31, 78, 148))
        p.drawEllipse(int(poly[-1][0]) - 3, int(poly[-1][1]) - 3, 6, 6)
        # 轴标注: Y 首末数量级, X 首末 cycle 号
        p.setPen(QColor(90, 90, 90))
        p.drawText(4, int(top + 10), f"1e{lo:.0f}")
        p.drawText(4, int(top + plot_h), f"1e{hi:.0f}")
        first_c = pts[0][0] if pts[0][0] >= 0 else 1
        last_c = pts[-1][0] if pts[-1][0] >= 0 else len(pts)
        p.drawText(int(left), self.height() - 4, str(first_c))
        label = str(last_c)
        p.drawText(int(left + plot_w - 8 * len(label)),
                   self.height() - 4, label)
        p.drawText(4, int(top + plot_h / 2) + 4, "res")


class TreeListView(QWidget):
    """Tree/List View Window: Layout of Parts / Conditions / Archive.

    Layout / Conditions tabs mirror STpre Tree/List View (DomainBoundary
    faces Xmin…Zmax under Region; Conditions as a 4-column table).
    """

    visibility_changed = pyqtSignal(str, str, bool)  # kind, name, visible
    item_selected = pyqtSignal(str, object)          # kind, name (current)
    items_selected = pyqtSignal(list)                # [(kind, name), ...]
    item_activated = pyqtSignal(str, object)         # kind, name (double-click)
    status_requested = pyqtSignal(str)               # message
    context_action = pyqtSignal(str, str, object)    # action, kind, name

    # Condition-type labels shown in the Conditions table (value kind/type)
    _VALUE_TYPE_LABELS = {
        "TEMP": "Initial T",
        "no_slip": "Noslip(smooth)",
        "adiabatic": "Adiabatic",
        "log_law": "Heat transfer",
        "conductive": "Conduction",
        "normal": "Radiation",
        "total_pres": "Total pressure",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setIconSize(QSize(16, 16))

        self.layout_tree = QTreeWidget(self)
        self.layout_tree.setHeaderLabels(["Layout of Parts"])
        self.layout_tree.setIconSize(QSize(16, 16))
        # Ctrl / Shift multi-select (STpre Layout of Parts behaviour)
        self.layout_tree.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        self.layout_tree.itemChanged.connect(self._on_item_changed)
        self.layout_tree.itemSelectionChanged.connect(self._on_selection)
        self.layout_tree.itemDoubleClicked.connect(self._on_double_click)
        self.layout_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layout_tree.customContextMenuRequested.connect(
            self._layout_context)
        # Track click position so checkbox double-clicks do not open
        # Edit Computational Domain / Mesh:block / Part dialogs.
        self._tree_click_pos = None
        self._last_check_change = None  # (item, monotonic_time)
        self.layout_tree.viewport().installEventFilter(self)

        self.cond_page = QWidget(self)
        cond_lay = QVBoxLayout(self.cond_page)
        cond_lay.setContentsMargins(2, 2, 2, 2)
        cond_lay.setSpacing(2)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(2, 2, 2, 2)
        self.cond_filter = QComboBox(self.cond_page)
        self.cond_filter.addItems([
            "All", "Domain", "DomainBoundary", "Obstacle", "Region",
        ])
        self.cond_filter.currentTextChanged.connect(self._apply_cond_filter)
        self.cond_only_property = QCheckBox("Only Property", self.cond_page)
        self.cond_only_condition = QCheckBox("Only Condition", self.cond_page)
        self.cond_only_property.toggled.connect(self._apply_cond_filter)
        self.cond_only_condition.toggled.connect(self._apply_cond_filter)
        filter_row.addWidget(self.cond_filter)
        filter_row.addWidget(self.cond_only_property)
        filter_row.addWidget(self.cond_only_condition)
        filter_row.addStretch(1)
        cond_lay.addLayout(filter_row)
        self.cond_tree = QTreeWidget(self.cond_page)
        self.cond_tree.setHeaderLabels([
            "Part/Region name", "Region type",
            "Condition name", "Condition type",
        ])
        self.cond_tree.setIconSize(QSize(16, 16))
        self.cond_tree.setRootIsDecorated(False)
        self.cond_tree.setUniformRowHeights(True)
        hdr = self.cond_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.cond_tree.itemSelectionChanged.connect(self._on_cond_selection)
        cond_lay.addWidget(self.cond_tree, 1)

        self.archive_tree = QTreeWidget(self)
        self.archive_tree.setHeaderLabels(["Member", "Size"])
        self.archive_tree.setIconSize(QSize(16, 16))
        self.archive_tree.itemSelectionChanged.connect(
            self._on_archive_selection)

        self.tabs.addTab(self.layout_tree, AppIcons.get("cube", 16),
                         "Layout of Parts")
        self.tabs.addTab(self.cond_page, AppIcons.get("surface", 16),
                         "Conditions")
        self.tabs.addTab(self.archive_tree, "Archive")
        v.addWidget(self.tabs)
        self._block = False
        self._cond_rows: list[tuple] = []  # (item, region_type, has_cond)
        self._order_clipboard: list[str] = []  # Change order: Copy

    # -- populate ----------------------------------------------------------

    def clear(self) -> None:
        self.layout_tree.clear()
        self.cond_tree.clear()
        self.archive_tree.clear()
        self._cond_rows = []

    def populate(self, model: StpreModel, archive_members: list) -> None:
        self._populate_layout(model)
        self._populate_conditions(model)
        self._populate_archive(archive_members)

    def _add(self, parent, label, data, icon=None, checkable=False,
             checked=True):
        item = QTreeWidgetItem([label])
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
        """STpre Layout of Parts: Parts / Computational_Domain / Region / Others."""
        tree = self.layout_tree
        self._block = True
        tree.clear()

        # --- Parts (only geometry parts / groups) ---
        parts_root = self._add(tree, "Parts", ("parts_root", None),
                               "folder", checkable=True)
        root_parts = [p for p in model.parts() if not p.group]
        for p in root_parts:
            self._add(parts_root, p.name, ("part", p.name), "cube",
                      checkable=True)
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
                self._add(gnode, p.name, ("part", p.name), "cube",
                          checkable=True)

        # --- Computational_Domain ---
        domain = self._add(tree, "Computational_Domain",
                           ("domain_folder", None), "domain")
        dname = model.domain_name() or "Domain(cuboid)"
        # Checked = opaque Domain faces (matches _domain_face_mode on load)
        self._add(domain, dname, ("domain", dname), "domain",
                  checkable=True, checked=True)
        mb = model.mesh_block()
        bname = "RootBlock"
        if mb is not None:
            n = _first(mb, "name")
            if n is not None and n.text:
                bname = n.text.strip()
        # Always list RootBlock (falls back to domain AABB when no mesh yet)
        rb_on = model.root_block_visible() if mb is not None else True
        self._add(domain, bname, ("mesh_block", bname), "mesh",
                  checkable=True, checked=rb_on)

        # --- Region: always Xmin…Zmax (DomainBoundary) then other regions ---
        reg_root = self._add(tree, "Region", ("region_folder", None),
                             "region")
        for fname, _el in model.domain_faces():
            self._add(reg_root, fname, ("domain_face", fname), "surface",
                      checkable=True, checked=True)
        for r in model.regions():
            if r.attrib.get("type") == "undefine":
                continue  # undefined defaults live in Conditions, not Layout
            n = _first(r, "name")
            if n is None or not n.text:
                continue
            rname = n.text.strip()
            if rname in DOMAIN_FACE_NAMES:
                continue
            self._add(reg_root, rname, ("region", rname), "surface",
                      checkable=True, checked=True)

        others = self._add(tree, "Others", ("others", None), "folder",
                           checkable=True, checked=True)

        parts_root.setExpanded(True)
        domain.setExpanded(True)
        reg_root.setExpanded(True)
        others.setExpanded(True)
        self._block = False

    def _value_label(self, el) -> str:
        if el is None:
            return ""
        typ = _first(el, "type")
        typ_s = (typ.text or "").strip() if typ is not None and typ.text else ""
        if typ_s in self._VALUE_TYPE_LABELS:
            return self._VALUE_TYPE_LABELS[typ_s]
        kind = _first(el, "kind")
        kind_s = (kind.text or "").strip() if kind is not None and kind.text else ""
        if kind_s in self._VALUE_TYPE_LABELS:
            return self._VALUE_TYPE_LABELS[kind_s]
        if el.attrib.get("type") == "initial" or typ_s == "TEMP":
            return "Initial T"
        return kind_s or typ_s or el.attrib.get("type", "")

    def _condition_bindings(self, model: StpreModel) -> dict[str, tuple[str, object]]:
        """Map target key → (value_name, value_element).

        Keys: ``analysis:<name>``, ``region:<name>``, ``face:<name>``,
        ``undefineN``.
        """
        values = {}
        for v in model.values():
            n = _first(v, "name")
            if n is not None and n.text:
                values[n.text.strip()] = v
        # undefine seq → display name
        undef_names: dict[str, str] = {}
        for r in model.regions():
            if r.attrib.get("type") != "undefine":
                continue
            seq = _first(r, "seq_no")
            nm = _first(r, "name")
            if seq is None or nm is None or not nm.text:
                continue
            undef_names[f"undefine{(seq.text or '').strip()}"] = nm.text.strip()

        out: dict[str, tuple[str, object]] = {}
        for c in model.conditions():
            v_el = _first(c, "value")
            vname = (v_el.text or "").strip() if v_el is not None and v_el.text else ""
            vel = values.get(vname)
            a = _first(c, "analysis")
            if a is not None and a.text:
                out[f"analysis:{(a.text or '').strip()}"] = (vname, vel)
            r = _first(c, "region")
            if r is not None and r.text:
                key = (r.text or "").strip()
                if key.startswith("undefine"):
                    out[key] = (vname, vel)
                    disp = undef_names.get(key)
                    if disp:
                        out[f"region:{disp}"] = (vname, vel)
                elif key in DOMAIN_FACE_NAMES:
                    out[f"face:{key}"] = (vname, vel)
                else:
                    out[f"region:{key}"] = (vname, vel)
        return out

    def _populate_conditions(self, model: StpreModel) -> None:
        """STpre Conditions table: name / region type / condition / type."""
        tree = self.cond_tree
        tree.clear()
        self._cond_rows = []
        binds = self._condition_bindings(model)

        def add_row(name: str, rtype: str, kind: str, icon: str,
                    bind_keys: list[str]):
            vname, vel = "", None
            for k in bind_keys:
                if k in binds:
                    vname, vel = binds[k]
                    break
            ctype = self._value_label(vel) if vel is not None else ""
            item = QTreeWidgetItem([name, rtype, vname, ctype])
            item.setData(0, Qt.UserRole, (kind, name))
            item.setIcon(0, AppIcons.get(icon, 16))
            tree.addTopLevelItem(item)
            self._cond_rows.append((item, rtype, bool(vname)))

        dname = model.domain_name() or "Domain(cuboid)"
        if model.analysis_region() is not None or dname:
            add_row(dname, "Domain", "domain", "domain",
                    [f"analysis:{dname}"])

        for fname, _el in model.domain_faces():
            add_row(fname, "DomainBoundary", "domain_face", "surface",
                    [f"face:{fname}", f"region:{fname}"])

        for p in model.parts():
            attr = (p.attribute or "").strip()
            rtype = attr[:1].upper() + attr[1:] if attr else "Obstacle"
            add_row(p.name, rtype, "part", "cube",
                    [f"part:{p.name}", f"region:{p.name}"])

        for r in model.regions():
            n = _first(r, "name")
            if n is None or not n.text:
                continue
            rname = n.text.strip()
            rtype_attr = r.attrib.get("type", "region")
            display_type = "Region"
            keys = [f"region:{rname}"]
            if rtype_attr == "undefine":
                seq = _first(r, "seq_no")
                if seq is not None and seq.text:
                    keys.insert(0, f"undefine{(seq.text or '').strip()}")
            add_row(rname, display_type, "region", "surface", keys)

        self._apply_cond_filter()

    def _apply_cond_filter(self, *_args) -> None:
        filt = self.cond_filter.currentText() if hasattr(self, "cond_filter") else "All"
        only_prop = (hasattr(self, "cond_only_property")
                     and self.cond_only_property.isChecked())
        only_cond = (hasattr(self, "cond_only_condition")
                     and self.cond_only_condition.isChecked())
        for item, rtype, has_cond in self._cond_rows:
            show = True
            if filt != "All" and rtype != filt:
                # Obstacle filter matches any non-Domain/Region/DomainBoundary
                if filt == "Obstacle":
                    show = rtype not in ("Domain", "DomainBoundary", "Region")
                else:
                    show = False
            if only_cond and not has_cond:
                show = False
            if only_prop and rtype in ("DomainBoundary", "Region") and not has_cond:
                # Property-oriented rows: Domain + parts (materials)
                show = False
            if only_prop and rtype == "DomainBoundary":
                show = False
            if only_prop and rtype == "Region":
                show = False
            item.setHidden(not show)

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

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.layout_tree.viewport() and event.type() in (
                QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            self._tree_click_pos = event.pos()
        return super().eventFilter(obj, event)

    def _check_indicator_rect(self, item):
        """Viewport rect of the item's checkbox, or None if not checkable."""
        if item is None or not (item.flags() & Qt.ItemIsUserCheckable):
            return None
        tree = self.layout_tree
        opt = QStyleOptionViewItem()
        opt.initFrom(tree)
        opt.rect = tree.visualItemRect(item)
        opt.features = QStyleOptionViewItem.HasCheckIndicator
        opt.checkState = item.checkState(0)
        opt.decorationSize = tree.iconSize()
        if not item.icon(0).isNull():
            opt.features |= QStyleOptionViewItem.HasDecoration
        opt.widget = tree
        rect = tree.style().subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator, opt, tree)
        if rect.isValid() and rect.width() > 0:
            return rect
        # Fallback: left strip of the item row (branch/check area)
        vr = tree.visualItemRect(item)
        return vr.adjusted(0, 0, -(max(0, vr.width() - 22)), 0)

    def _click_on_check_indicator(self, item) -> bool:
        pos = self._tree_click_pos
        if item is None or pos is None:
            return False
        rect = self._check_indicator_rect(item)
        return bool(rect is not None and rect.contains(pos))

    def _on_item_changed(self, item, _col) -> None:
        if self._block:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        # Remember check toggles so a double-click on the checkbox (which
        # also flips checkState) does not open the edit dialog.
        if item.flags() & Qt.ItemIsUserCheckable:
            self._last_check_change = (item, time.monotonic())
        kind, name = data
        checked = item.checkState(0) == Qt.Checked
        if kind == "part" and name:
            self.visibility_changed.emit("part", name, checked)
        elif kind == "domain" and name:
            # Checked = opaque face mode; unchecked = volume wireframe
            self.visibility_changed.emit("domain", name, checked)
        elif kind == "domain_face" and name:
            self.visibility_changed.emit("domain_face", name, checked)
        elif kind == "mesh_block" and name:
            self.visibility_changed.emit("mesh_block", name, checked)
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
                    cdata = child.data(0, Qt.UserRole)
                    if cdata and cdata[0] == "part":
                        self.visibility_changed.emit(
                            "part", cdata[1], checked)
                    elif cdata and cdata[0] == "group":
                        for j in range(child.childCount()):
                            gc = child.child(j)
                            gc.setCheckState(
                                0, Qt.Checked if checked else Qt.Unchecked)
                            gd = gc.data(0, Qt.UserRole)
                            if gd and gd[0] == "part":
                                self.visibility_changed.emit(
                                    "part", gd[1], checked)
            self._block = False

    def _emit_selection(self, item) -> None:
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if data:
            self.item_selected.emit(data[0], data[1])

    @staticmethod
    def _selection_pairs(items) -> list:
        pairs = []
        for it in items:
            data = it.data(0, Qt.UserRole)
            if data:
                pairs.append((data[0], data[1]))
        return pairs

    def _on_selection(self) -> None:
        items = self.layout_tree.selectedItems()
        pairs = self._selection_pairs(items)
        cur = self.layout_tree.currentItem()
        if cur is None or cur not in items:
            cur = items[0] if items else None
        self._emit_selection(cur)
        self.items_selected.emit(pairs)

    def _on_cond_selection(self) -> None:
        items = self.cond_tree.selectedItems()
        self.items_selected.emit(self._selection_pairs(items))
        self._emit_selection(items[0] if items else None)

    def _on_archive_selection(self) -> None:
        items = self.archive_tree.selectedItems()
        self.items_selected.emit(self._selection_pairs(items))
        self._emit_selection(items[0] if items else None)

    def _layout_context(self, pos) -> None:
        item = self.layout_tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        # Keep multi-selection when right-clicking an already-selected row
        # (STpre Layout of Parts). Otherwise select the clicked item alone.
        if not item.isSelected():
            self.layout_tree.clearSelection()
            item.setSelected(True)
            self.layout_tree.setCurrentItem(item)

        kind, name = data
        selected = self._selection_pairs(self.layout_tree.selectedItems())
        part_names = [n for k, n in selected if k == "part" and n]
        menu = QMenu(self)

        if kind == "part" or (kind == "group" and part_names):
            # Prefer part menu when parts are selected (multi-select case)
            self._fill_part_context_menu(menu, part_names or [name], name)
        elif kind == "group":
            act = menu.addAction("Rearrange Group Name")
            act.triggered.connect(
                lambda: self.context_action.emit("rearrange_group", kind, name))
            menu.addAction("Create Group",
                           lambda: self.context_action.emit(
                               "create_group", "part", part_names))
            menu.addAction("Cancel Group",
                           lambda: self.context_action.emit(
                               "cancel_group", kind, name))
            clip = getattr(self, "_order_clipboard", None) or []
            a_app = menu.addAction(
                "Change order; Append to group",
                lambda: self.context_action.emit(
                    "order_append_group", kind, name))
            a_app.setEnabled(bool(clip))
        elif kind == "domain":
            menu.addAction("Reference (Edit Computational Domain)",
                           lambda: self.context_action.emit(
                               "refer", kind, name))
        elif kind == "mesh_block":
            menu.addAction("Reference (Edit Mesh Block)",
                           lambda: self.context_action.emit(
                               "refer", kind, name))
            menu.addAction("Display RootBlock",
                           lambda: self._set_checked(item, True))
            menu.addAction("Hide RootBlock",
                           lambda: self._set_checked(item, False))
        if not menu.isEmpty():
            menu.exec_(self.layout_tree.viewport().mapToGlobal(pos))

    def _fill_part_context_menu(self, menu: QMenu, part_names: list,
                                anchor_name) -> None:
        """STpre Layout of Parts part popup (single / multi selection)."""
        names = list(part_names)
        primary = anchor_name if anchor_name in names else (
            names[0] if names else None)
        clip = list(getattr(self, "_order_clipboard", []) or [])

        def emit(action: str, payload=None):
            self.context_action.emit(
                action, "part", payload if payload is not None else names)

        menu.addAction("Refer to Part",
                       lambda: emit("refer", primary))
        menu.addAction("Translation/Copy Part",
                       lambda: emit("translate_copy"))
        menu.addAction("Delete Part",
                       lambda: emit("delete"))
        menu.addAction("Change part setting together",
                       lambda: emit("change_settings"))
        menu.addAction("Show Parts List Dialog",
                       lambda: emit("parts_list"))
        menu.addSeparator()
        menu.addAction("Display Part",
                       lambda: self._set_checked_parts(names, True))
        menu.addAction("Hide Part",
                       lambda: self._set_checked_parts(names, False))
        menu.addSeparator()
        menu.addAction("Create Group",
                       lambda: emit("create_group"))
        menu.addAction("Cancel Group",
                       lambda: emit("cancel_group"))
        menu.addSeparator()
        menu.addAction("Change order: Copy",
                       lambda: emit("order_copy"))
        act_re = menu.addAction("Rearrange Group Name")
        act_re.setEnabled(False)
        act_prev = menu.addAction(
            "Change order: Append(previous)",
            lambda: emit("order_append_prev", primary))
        act_prev.setEnabled(bool(clip) and primary is not None)
        act_next = menu.addAction(
            "Change order: Append(next)",
            lambda: emit("order_append_next", primary))
        act_next.setEnabled(bool(clip) and primary is not None)
        act_grp = menu.addAction(
            "Change order; Append to group",
            lambda: emit("order_append_group", primary))
        act_grp.setEnabled(bool(clip))
        act_lib = menu.addAction(
            "Register to library",
            lambda: emit("register_library"))
        act_lib.setEnabled(bool(names))

    def _set_checked_parts(self, names: list, on: bool) -> None:
        want = set(names or [])
        state = Qt.Checked if on else Qt.Unchecked

        def walk(item):
            data = item.data(0, Qt.UserRole)
            if (data and data[0] == "part" and data[1] in want
                    and (item.flags() & Qt.ItemIsUserCheckable)):
                item.setCheckState(0, state)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.layout_tree.topLevelItemCount()):
            walk(self.layout_tree.topLevelItem(i))

    def _on_double_click(self, item, _col) -> None:
        """Open edit dialogs only for double-clicks on the label/text.

        Clicks / double-clicks on the checkbox must only toggle visibility
        (Domain face mode, RootBlock, Part hide) — never pop Edit Domain.
        """
        data = item.data(0, Qt.UserRole) if item is not None else None
        if not data or data[0] not in ("domain", "mesh_block", "part"):
            return
        if self._click_on_check_indicator(item):
            return
        last = self._last_check_change
        if (last is not None and last[0] is item
                and (time.monotonic() - last[1]) < 0.4):
            return
        self.item_activated.emit(data[0], data[1])

    def _set_checked(self, item, on: bool) -> None:
        item.setCheckState(0, Qt.Checked if on else Qt.Unchecked)


class ControlWindow(QWidget):
    """STpre Control Window tabs.

    Show/Select · Sketch · Layer · Library · ActivePart · Property
    (aligned with Pre_eng *Control Window* pages and UI screenshots).
    """

    drawing_mode_changed = pyqtSignal(str)
    layer_toggled = pyqtSignal(str, bool)
    selection_target_changed = pyqtSignal(str)
    apply_requested = pyqtSignal()
    sketch_action = pyqtSignal(str)              # update | reset | fit
    layer_apply_requested = pyqtSignal()         # Display/Operating layer Apply
    active_part_apply = pyqtSignal(str)          # ActivePart Apply

    # Show/Select Drawing On/Off — (label, key, default) in STpre column order
    LAYER_KEYS = [
        ("Part", "part", True),
        ("Mesh block", "mesh_block", True),
        ("Element division", "element", True),
        ("Condition (flow, etc)", "condition", False),
        ("Sketch plane", "sketch_plane", True),
        ("Domain frame", "domain_frame", True),
        ("Mesh", "mesh", False),
        ("Face division", "face", False),
        ("Axis (Global)", "axis_global", True),
        ("Axis (Sketch)", "axis_sketch", True),
        ("Origin", "origin", True),
        ("Point", "point", False),
        ("Aspect ratio", "aspect_ratio", False),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(16, 16))

        self.tabs.addTab(self._build_show_select(),
                         AppIcons.get("select", 16), "Show/Select")
        self.sketch_page = self._build_sketch()
        self.tabs.addTab(self.sketch_page,
                         AppIcons.get("panel", 16), "Sketch")
        self.layer_page = self._build_layer()
        self.tabs.addTab(self.layer_page,
                         AppIcons.get("folder", 16), "Layer")
        self.lib_page = self._build_library()
        self.tabs.addTab(self.lib_page,
                         AppIcons.get("library", 16), "Library")
        self.active_page = self._build_active_part()
        self.tabs.addTab(self.active_page,
                         AppIcons.get("cube", 16), "ActivePart")

        # Property (cabdecoding extension — kept for part/domain inspect)
        self.prop_page = QWidget(self)
        self.prop_layout = QFormLayout(self.prop_page)
        self.prop_title = QLabel("选择树节点查看属性")
        self.prop_layout.addRow(self.prop_title)
        self.prop_fields: dict[str, QWidget] = {}
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        self.tabs.addTab(self.prop_page, AppIcons.get("xml", 16), "Property")

        v.addWidget(self.tabs)
        self._prop_target = ("", None)
        self._drawing_mode = "Shading"
        self._active_part = ""

    # ------------------------------------------------------------------ Show/Select

    def _build_show_select(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        draw_box = QGroupBox("Drawing On/Off", page)
        grid = QGridLayout(draw_box)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self.layer_checks: dict[str, QCheckBox] = {}
        # 3 columns matching STpre screenshot
        col_keys = [
            ["part", "mesh_block", "element", "condition", "sketch_plane"],
            ["domain_frame", "mesh", "face", "axis_global", "axis_sketch"],
            ["origin", "point", "aspect_ratio"],
        ]
        by_key = {k: (lab, k, d) for lab, k, d in self.LAYER_KEYS}
        for c, keys in enumerate(col_keys):
            for r, key in enumerate(keys):
                lab, key, default = by_key[key]
                cb = QCheckBox(lab, draw_box)
                cb.setChecked(default)
                cb.toggled.connect(
                    lambda on, k=key: self.layer_toggled.emit(k, on))
                if key == "condition":
                    cb.setToolTip("Domain-boundary wireframe overlay (MVP).")
                elif key == "aspect_ratio":
                    cb.setToolTip("Element occupancy wireframe (MVP).")
                self.layer_checks[key] = cb
                grid.addWidget(cb, r, c)
        detail = QPushButton("Detail...", draw_box)
        detail.setFixedWidth(72)
        detail.setToolTip(
            "Open the per-layer detail sheet (state / actor counts).")
        detail.clicked.connect(
            lambda: self.selection_target_changed.emit("Detail"))
        grid.addWidget(detail, 3, 2, Qt.AlignLeft)
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
        ml.addStretch(1)
        lay.addWidget(mode_box)

        sel_box = QGroupBox("Target of selection", page)
        sl = QHBoxLayout(sel_box)
        self.sel_group = QButtonGroup(sel_box)
        for text in ("Parts", "Faces"):
            rb = QRadioButton(text, sel_box)
            self.sel_group.addButton(rb)
            sl.addWidget(rb)
            if text == "Parts":
                rb.setChecked(True)
            rb.toggled.connect(self._on_sel_target)
        self.sel_vertices = QCheckBox("Vertices", sel_box)
        self.sel_domain_bnd = QCheckBox("Domain boundary", sel_box)
        self.sel_vertices.toggled.connect(self._on_sel_extra)
        self.sel_domain_bnd.toggled.connect(self._on_sel_extra)
        sl.addWidget(self.sel_vertices)
        sl.addWidget(self.sel_domain_bnd)
        sl.addStretch(1)
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
            # normalize to singular used elsewhere
            text = "Part" if btn.text() == "Parts" else "Face"
            self.selection_target_changed.emit(text)

    def _on_sel_extra(self, checked: bool) -> None:
        """M35: Vertices / Domain boundary modifiers for pick target."""
        if self.sel_domain_bnd.isChecked():
            self.selection_target_changed.emit("DomainBoundary")
            return
        if self.sel_vertices.isChecked():
            # Face+Vertices when Faces radio on; else Vertices alone
            btn = self.sel_group.checkedButton()
            if btn and btn.text() == "Faces":
                self.selection_target_changed.emit("Faces + Vertices")
            else:
                self.selection_target_changed.emit("Vertices")
            return
        if checked:
            return
        # unchecked → restore radio target
        self._on_sel_target(True)

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

    # ------------------------------------------------------------------ Sketch

    def _build_sketch(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # Coordinate system — Origin / (U) / (W) × X Y Z
        cs = QGroupBox("Coordinate system", page)
        cg = QGridLayout(cs)
        cg.setHorizontalSpacing(4)
        for i, ax in enumerate("XYZ"):
            lab = QLabel(ax, cs)
            lab.setAlignment(Qt.AlignCenter)
            cg.addWidget(lab, 0, i + 1)
        self.sk_cs: dict[str, dict[str, QDoubleSpinBox]] = {}
        defaults = {
            "Origin": (0.0, 0.0, 0.0),
            "(U)": (1.0, 0.0, 0.0),
            "(W)": (0.0, 0.0, 1.0),
        }
        for r, row in enumerate(("Origin", "(U)", "(W)"), start=1):
            cg.addWidget(QLabel(row, cs), r, 0)
            self.sk_cs[row] = {}
            for i, ax in enumerate("xyz"):
                sb = QDoubleSpinBox(cs)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(defaults[row][i])
                sb.setMinimumWidth(64)
                cg.addWidget(sb, r, i + 1)
                self.sk_cs[row][ax] = sb
        # compat aliases used by older sketch_plane code paths
        self.sk_origin = self.sk_cs["Origin"]
        right = QVBoxLayout()
        btn_reset = QPushButton("Reset", cs)
        btn_reset.clicked.connect(
            lambda: self.sketch_action.emit("reset"))
        right.addWidget(btn_reset)
        self.sk_fix = QCheckBox("Fix", cs)
        right.addWidget(self.sk_fix)
        right.addWidget(QLabel("mm", cs))
        right.addStretch(1)
        cg.addLayout(right, 1, 4, 3, 1)
        brow = QHBoxLayout()
        btn_edit = QPushButton("Edit system...", cs)
        btn_edit.clicked.connect(
            lambda: self.sketch_action.emit("update"))
        btn_fit = QPushButton("Fit to computational domain", cs)
        btn_fit.clicked.connect(
            lambda: self.sketch_action.emit("fit"))
        brow.addWidget(btn_edit)
        brow.addWidget(btn_fit)
        brow.addStretch(1)
        cg.addLayout(brow, 4, 0, 1, 5)
        lay.addWidget(cs)

        # Grid — (U)/(V)/(W) × interval / Minimum / Maximum / Snap  (mm)
        grd = QGroupBox("Grid", page)
        gg = QGridLayout(grd)
        for i, h in enumerate(("interval", "Minimum", "Maximum", "Snap")):
            lab = QLabel(h, grd)
            lab.setAlignment(Qt.AlignCenter)
            gg.addWidget(lab, 0, i + 1)
        self.sk_grid: dict[str, dict[str, QDoubleSpinBox]] = {}
        # STpre Control→Sketch defaults (mm): Δ=5, Min=-25, Max=125, Snap=5
        gdefs = {
            "(U)": (5.0, -25.0, 125.0, 5.0),
            "(V)": (5.0, -25.0, 125.0, 5.0),
            "(W)": (5.0, -25.0, 125.0, 5.0),
        }
        for r, row in enumerate(("(U)", "(V)", "(W)"), start=1):
            gg.addWidget(QLabel(row, grd), r, 0)
            self.sk_grid[row] = {}
            for i, col in enumerate(("interval", "Minimum", "Maximum", "Snap")):
                sb = QDoubleSpinBox(grd)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(gdefs[row][i])
                sb.setMinimumWidth(56)
                gg.addWidget(sb, r, i + 1)
                self.sk_grid[row][col] = sb
        grow = QVBoxLayout()
        grow.addWidget(QLabel("mm", grd))
        self.sk_grid_on = QCheckBox("Grid", grd)
        grow.addWidget(self.sk_grid_on)
        btn_gedit = QPushButton("Edit", grd)
        btn_gedit.clicked.connect(
            lambda: self.sketch_action.emit("update"))
        grow.addWidget(btn_gedit)
        grow.addStretch(1)
        gg.addLayout(grow, 1, 5, 3, 1)
        # compat
        self.sk_delta = {a: self.sk_grid[f"({a.upper()})"]["interval"]
                         for a in "uvw"}
        self.sk_snap = {a: self.sk_grid[f"({a.upper()})"]["Snap"]
                        for a in "uvw"}
        self.sk_urange = {
            "min": self.sk_grid["(U)"]["Minimum"],
            "max": self.sk_grid["(U)"]["Maximum"],
        }
        self.sk_vrange = {
            "min": self.sk_grid["(V)"]["Minimum"],
            "max": self.sk_grid["(V)"]["Maximum"],
        }
        self.sk_gridsnap = self.sk_grid_on
        self.sk_minus = QCheckBox("Minus", grd)
        self.sk_minus.setVisible(False)
        self.sk_u_label = QLabel("(1, 0, 0)")
        self.sk_w_label = QLabel("(0, 0, 1)")
        lay.addWidget(grd)

        sel = QGroupBox("Selection", page)
        sl = QHBoxLayout(sel)
        self.sk_sel_group = QButtonGroup(sel)
        for text in ("Snap", "Vertex", "None"):
            rb = QRadioButton(text, sel)
            self.sk_sel_group.addButton(rb)
            sl.addWidget(rb)
            if text == "Snap":
                rb.setChecked(True)
        sl.addStretch(1)
        btn_apply = QPushButton("Apply", sel)
        btn_apply.clicked.connect(
            lambda: self.sketch_action.emit("update"))
        sl.addWidget(btn_apply)
        lay.addWidget(sel)
        lay.addStretch(1)
        return page

    def load_sketch(self, model) -> None:
        import cab_sketch
        plane = cab_sketch.plane_from_xml(model)
        for i, ax in enumerate("xyz"):
            self.sk_cs["Origin"][ax].setValue(plane.origin[i])
            self.sk_cs["(U)"][ax].setValue(plane.u[i])
            self.sk_cs["(W)"][ax].setValue(plane.w[i])
        self.sk_u_label.setText(
            "(" + ", ".join(f"{x:.4g}" for x in plane.u) + ")")
        self.sk_w_label.setText(
            "(" + ", ".join(f"{x:.4g}" for x in plane.w) + ")")
        # XML stores metres → UI mm
        for axis, rng, d, s in (
                ("(U)", plane.u_range, plane.delta[0], plane.snap[0]),
                ("(V)", plane.v_range, plane.delta[1], plane.snap[1]),
                ("(W)", plane.w_range, plane.delta[2], plane.snap[2])):
            self.sk_grid[axis]["interval"].setValue(d * 1000.0)
            self.sk_grid[axis]["Minimum"].setValue(rng[0] * 1000.0)
            self.sk_grid[axis]["Maximum"].setValue(rng[1] * 1000.0)
            self.sk_grid[axis]["Snap"].setValue(s * 1000.0)
        self.sk_grid_on.setChecked(plane.gridsnap)
        self.sk_minus.setChecked(plane.minus)

    def sketch_plane(self):
        import cab_sketch
        import numpy as np
        u = tuple(self.sk_cs["(U)"][a].value() for a in "xyz")
        w = tuple(self.sk_cs["(W)"][a].value() for a in "xyz")
        # normalize
        u_a = np.asarray(u, float)
        w_a = np.asarray(w, float)
        if np.linalg.norm(u_a) > 1e-12:
            u_a = u_a / np.linalg.norm(u_a)
        if np.linalg.norm(w_a) > 1e-12:
            w_a = w_a / np.linalg.norm(w_a)
        v_a = np.cross(w_a, u_a)
        if np.linalg.norm(v_a) > 1e-12:
            v_a = v_a / np.linalg.norm(v_a)
        # UI mm → metres for ranges / delta / snap
        def mm(axis, col):
            return self.sk_grid[axis][col].value() / 1000.0

        return cab_sketch.SketchPlane(
            origin=tuple(self.sk_cs["Origin"][a].value() for a in "xyz"),
            u=tuple(float(x) for x in u_a),
            v=tuple(float(x) for x in v_a),
            w=tuple(float(x) for x in w_a),
            u_range=(mm("(U)", "Minimum"), mm("(U)", "Maximum")),
            v_range=(mm("(V)", "Minimum"), mm("(V)", "Maximum")),
            w_range=(mm("(W)", "Minimum"), mm("(W)", "Maximum")),
            delta=(mm("(U)", "interval"), mm("(V)", "interval"),
                   mm("(W)", "interval")),
            snap=(mm("(U)", "Snap"), mm("(V)", "Snap"), mm("(W)", "Snap")),
            gridsnap=self.sk_grid_on.isChecked(),
            minus=self.sk_minus.isChecked(),
        )

    # ------------------------------------------------------------------ Layer

    def _build_layer(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)

        all_box = QGroupBox("All layer display", page)
        al = QHBoxLayout(all_box)
        self.layer_all_group = QButtonGroup(all_box)
        self.layer_all_on = QRadioButton("ON", all_box)
        self.layer_all_off = QRadioButton("OFF", all_box)
        self.layer_all_on.setChecked(True)
        self.layer_all_group.addButton(self.layer_all_on)
        self.layer_all_group.addButton(self.layer_all_off)
        al.addWidget(self.layer_all_on)
        al.addWidget(self.layer_all_off)
        al.addStretch(1)
        self.layer_all_on.toggled.connect(self._on_all_layer)
        lay.addWidget(all_box)

        disp = QGroupBox("Display Layer", page)
        dg = QGridLayout(disp)
        self.display_layers: list[QCheckBox] = []
        for i in range(16):
            cb = QCheckBox(str(i + 1), disp)
            cb.setChecked(True)
            self.display_layers.append(cb)
            dg.addWidget(cb, i // 8, i % 8)
        lay.addWidget(disp)

        op = QGroupBox("Operating layer", page)
        og = QGridLayout(op)
        self.operating_group = QButtonGroup(op)
        self.operating_layers: list[QRadioButton] = []
        for i in range(16):
            rb = QRadioButton(str(i + 1), op)
            self.operating_group.addButton(rb, i + 1)
            self.operating_layers.append(rb)
            og.addWidget(rb, i // 8, i % 8)
            if i == 0:
                rb.setChecked(True)
        lay.addWidget(op)

        brow = QHBoxLayout()
        btn = QPushButton("Apply", page)
        btn.clicked.connect(self.layer_apply_requested.emit)
        brow.addWidget(btn)
        brow.addStretch(1)
        lay.addLayout(brow)
        lay.addStretch(1)
        return page

    def _on_all_layer(self, on: bool) -> None:
        for cb in self.display_layers:
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)

    def display_layer_set(self) -> set[int]:
        return {i + 1 for i, cb in enumerate(self.display_layers)
                if cb.isChecked()}

    def operating_layer(self) -> int:
        bid = self.operating_group.checkedId()
        return bid if bid > 0 else 1

    # ------------------------------------------------------------------ Library

    def _build_library(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        self.lib_tree = QTreeWidget(page)
        self.lib_tree.setHeaderHidden(True)
        self.lib_tree.setIconSize(QSize(16, 16))
        lay.addWidget(self.lib_tree, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Select File", page))
        self.lib_file = QLineEdit(page)
        row.addWidget(self.lib_file, 1)
        lay.addLayout(row)
        frow = QHBoxLayout()
        frow.addWidget(QLabel("(filter)", page))
        self.lib_filter = QLineEdit(page)
        self.lib_filter.textChanged.connect(self._filter_library)
        frow.addWidget(self.lib_filter, 1)
        lay.addLayout(frow)
        self.lib_tree.itemSelectionChanged.connect(self._on_lib_sel)
        self._lib_root = self._default_library_root()
        return page

    @staticmethod
    def _default_library_root() -> str:
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Documents", "Cradle", "Stwin2025", "Library"),
            os.path.join(home, "Documents", "Cradle", "Stwin", "Library"),
            r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64",
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
        return candidates[0]

    def populate_library(self, props: Optional[PropertyModel] = None) -> None:
        """Populate Library tab: file tree + optional material groups."""
        self.lib_tree.clear()
        folder_icon = AppIcons.get("folder", 16)
        root_path = self._lib_root
        root_item = QTreeWidgetItem([root_path + ("" if root_path.endswith(
            ("\\", "/")) else "\\")])
        root_item.setIcon(0, folder_icon)
        root_item.setData(0, Qt.UserRole, ("folder", root_path))
        self.lib_tree.addTopLevelItem(root_item)
        if os.path.isdir(root_path):
            try:
                names = sorted(os.listdir(root_path), key=str.lower)
            except OSError:
                names = []
            for name in names:
                full = os.path.join(root_path, name)
                child = QTreeWidgetItem([name])
                if os.path.isdir(full):
                    child.setIcon(0, folder_icon)
                    child.setData(0, Qt.UserRole, ("folder", full))
                    # one level of children
                    try:
                        for sub in sorted(os.listdir(full), key=str.lower)[:50]:
                            sc = QTreeWidgetItem([sub])
                            sp = os.path.join(full, sub)
                            sc.setIcon(0, folder_icon if os.path.isdir(sp)
                                       else AppIcons.get("xml", 16))
                            sc.setData(0, Qt.UserRole, (
                                "folder" if os.path.isdir(sp) else "file", sp))
                            child.addChild(sc)
                    except OSError:
                        pass
                else:
                    child.setIcon(0, AppIcons.get("xml", 16))
                    child.setData(0, Qt.UserRole, ("file", full))
                root_item.addChild(child)
        root_item.setExpanded(True)

        # Project part library stub (Register to library)
        proj = QTreeWidgetItem(["[Project Parts]"])
        proj.setIcon(0, AppIcons.get("library", 16))
        proj.setData(0, Qt.UserRole, ("part_lib_group", "[Project Parts]"))
        for entry in getattr(self, "_project_part_library", []) or []:
            label = entry.get("name") or "(unnamed)"
            kind = entry.get("kind") or "body"
            c = QTreeWidgetItem([f"{label} ({kind})"])
            c.setIcon(0, AppIcons.get("cube", 16))
            c.setData(0, Qt.UserRole, ("part_lib", entry.get("name"), entry))
            c.setToolTip(0, entry.get("summary") or label)
            proj.addChild(c)
        self.lib_tree.addTopLevelItem(proj)
        proj.setExpanded(True)

        # Materials group (from project / standard library)
        if props is not None:
            mats = QTreeWidgetItem(["[Materials]"])
            mats.setIcon(0, AppIcons.get("library", 16))
            mats.setData(0, Qt.UserRole, ("material_group", "[Materials]"))
            for gtype, gname, names in props.group_catalog():
                if not gname:
                    continue
                gitem = QTreeWidgetItem([gname])
                gitem.setIcon(0, folder_icon)
                gitem.setData(0, Qt.UserRole, ("material_group", gname))
                for mat in names:
                    c = QTreeWidgetItem([mat])
                    c.setIcon(0, AppIcons.get("library", 16))
                    c.setData(0, Qt.UserRole, ("material", mat))
                    gitem.addChild(c)
                mats.addChild(gitem)
            self.lib_tree.addTopLevelItem(mats)

    def _on_lib_sel(self) -> None:
        items = self.lib_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if data and data[0] in ("file", "folder"):
            self.lib_file.setText(data[1])
        elif data and data[0] == "material":
            self.lib_file.setText(data[1])
        elif data and data[0] == "part_lib":
            self.lib_file.setText(str(data[1] or ""))

    def register_parts_to_library(self, entries: list) -> int:
        """Append part property stubs into the project Library tree."""
        lib = list(getattr(self, "_project_part_library", []) or [])
        by_name = {e.get("name"): i for i, e in enumerate(lib)}
        n = 0
        for entry in entries or []:
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            if name in by_name:
                lib[by_name[name]] = entry
            else:
                by_name[name] = len(lib)
                lib.append(entry)
            n += 1
        self._project_part_library = lib
        return n

    def show_library_part(self, name: str, entry: dict) -> None:
        """Property pane for a [Project Parts] library stub (read-only)."""
        self.clear_property()
        self._prop_target = ("part_lib", name)
        self.tabs.setCurrentWidget(self.prop_page)
        self.prop_title.setText(f"Library Part: {name}")
        for label, value in (
            ("名称", name),
            ("类型", (entry or {}).get("kind") or ""),
            ("属性", (entry or {}).get("attribute") or ""),
            ("材料", (entry or {}).get("material") or ""),
            ("摘要", (entry or {}).get("summary") or ""),
            ("Place", "Double-click Library entry to place"),
        ):
            w = QLineEdit("" if value is None else str(value))
            w.setReadOnly(True)
            self.prop_layout.addRow(label, w)
            self.prop_fields[label] = w
        self.apply_btn.setEnabled(False)

    def _filter_library(self, text: str) -> None:
        needle = text.strip().lower()

        def walk(item: QTreeWidgetItem) -> bool:
            data = item.data(0, Qt.UserRole) or ("",)
            label = item.text(0).lower()
            child_vis = False
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    child_vis = True
            match = (not needle) or needle in label or child_vis
            if data[0] == "folder" and child_vis:
                match = True
            item.setHidden(not match)
            return match

        for i in range(self.lib_tree.topLevelItemCount()):
            walk(self.lib_tree.topLevelItem(i))

    # ------------------------------------------------------------------ ActivePart

    def _build_active_part(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        self.active_table = QTableWidget(1, 2, page)
        self.active_table.setHorizontalHeaderLabels(["Parts", ""])
        self.active_table.verticalHeader().setVisible(False)
        self.active_table.horizontalHeader().setStretchLastSection(True)
        self.active_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.active_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.active_table.setItem(0, 0, QTableWidgetItem(""))
        self.active_table.setItem(0, 1, QTableWidgetItem("Not selected !"))
        lay.addWidget(self.active_table, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.active_apply = QPushButton("Apply", page)
        self.active_apply.setEnabled(False)
        self.active_apply.clicked.connect(self._on_active_apply)
        brow.addWidget(self.active_apply)
        lay.addLayout(brow)
        return page

    def set_active_part(self, name: Optional[str]) -> None:
        self._active_part = name or ""
        if self.active_table.rowCount() < 1:
            self.active_table.setRowCount(1)
        if name:
            self.active_table.setItem(0, 0, QTableWidgetItem(name))
            self.active_table.setItem(0, 1, QTableWidgetItem("Selected"))
            self.active_apply.setEnabled(True)
        else:
            self.active_table.setItem(0, 0, QTableWidgetItem(""))
            self.active_table.setItem(
                0, 1, QTableWidgetItem("Not selected !"))
            self.active_apply.setEnabled(False)

    def _on_active_apply(self) -> None:
        if self._active_part:
            self.active_part_apply.emit(self._active_part)

    # ------------------------------------------------------------------ Property

    def clear_property(self) -> None:
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
        if kind == "part" and name:
            self.set_active_part(name)

        def field(label, value, ro=False, combo=None):
            if combo is not None:
                w = QComboBox()
                w.addItems(combo)
                idx = w.findText(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                else:
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
        elif kind in ("file", "folder") and name:
            self.prop_title.setText(f"Library: {os.path.basename(name)}")
            field("路径", name, ro=True)
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
