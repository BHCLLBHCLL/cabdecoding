"""M6: Initial Wizard and Condition Wizard (STpre [Wizard] menu).

Aligned with the Pre_eng manual pages and the STpre binary strings:

- STpreIwiz_Bx64.dll steps: Project / Solution / Import CAD Data /
  Computational Domain / Analysis Type / Initial Value/Gravity /
  Purpose of Analysis / Condition for Computational Domain Boundary /
  Confirm Settings; buttons ``Finish/Cancel/Next >>/<< Back`` and a
  step counter ``%s %s ( %d/%d ) step``;
- STpreCwiz_Bx64.dll pages: Analysis Types / Basic Settings / Fluid
  Region / Flow / Heat / Initial Condition / Boundary Condition
  (Flow, Wall, Thermal, Symmetrical) / Source Condition / Fixed
  Condition / Analysis Control (Steady-state, Solver Parameters,
  Stabilization, Option) / Output Condition / File Specification /
  Condition List / Setting Confirmation, with a left navigation tree
  where undefined steps show a grey ring icon and defined steps an
  orange check (STpre-style; no unused checkboxes).

Both wizards write back to the ``<analysis_set>`` / ``<project>`` /
``<condition>`` / ``<value>`` sections through ``cabxml.StpreModel`` so the
changes persist in the cab and reach the ``.s`` exporter.

Phase-1 approximations (documented in DEV_SUMMARY):
- wizard pages whose cab equivalent does not exist yet (building-affected
  winds, enclosure heat release detail) log a WARN and are not written;
- some Solver / Stabilization / Output sub-options are UI-faithful and
  only persist a subset of flags into ``analysis_set``.
"""

from __future__ import annotations

import os
from typing import Optional

import cab_domain
import cab_import
from cabxml import PropertyModel, StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
        QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
        QRadioButton, QSizePolicy, QSplitter, QStackedWidget, QTabWidget,
        QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore

from cab_dialogs import DialogHeader, MaterialListDialog
from cab_wizard_icons import action_column, icon_action_button, nav_status_icon

_UNIT_FACTOR = {"mm": 1.0, "m": 1000.0, "cm": 10.0}  # value -> mm
_GRAVITY_DIRS = [("X+", (1, 0, 0)), ("X-", (-1, 0, 0)),
                 ("Y+", (0, 1, 0)), ("Y-", (0, -1, 0)),
                 ("Z+", (0, 0, 1)), ("Z-", (0, 0, -1))]
# STpre Condition Wizard Basic Settings labels (same order / vectors)
_CW_GRAVITY_DIRS = [
    ("X-Axis(Positive)", (1.0, 0.0, 0.0)),
    ("X-Axis(Negative)", (-1.0, 0.0, 0.0)),
    ("Y-Axis(Positive)", (0.0, 1.0, 0.0)),
    ("Y-Axis(Negative)", (0.0, -1.0, 0.0)),
    ("Z-Axis(Positive)", (0.0, 0.0, 1.0)),
    ("Z-Axis(Negative)", (0.0, 0.0, -1.0)),
    ("User-defined", None),
]


def _row(layout, label, widget, stretch=1):
    """Label + widget row helper."""
    r = QHBoxLayout()
    r.addWidget(QLabel(label))
    r.addWidget(widget, stretch)
    layout.addLayout(r)


def _pair_row(layout, label, widget, unit=""):
    r = QHBoxLayout()
    r.addWidget(QLabel(label))
    r.addWidget(widget, 1)
    if unit:
        r.addWidget(QLabel(unit))
    r.addStretch(1)
    layout.addLayout(r)


def _vec16(loc_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
           scale: float = 1.0) -> str:
    """Column-major 4x4 with uniform scale + translation."""
    dx, dy, dz = loc_m
    return ",".join(f"{v:.17g}" for v in
                    (scale, 0, 0, 0,
                     0, scale, 0, 0,
                     0, 0, scale, 0,
                     dx, dy, dz, 1.0))


# ============================================================== framework


class WizardBase(QDialog if _HAS_GUI_DEPS else object):
    """Shared wizard chrome: step label, optional left nav tree, ordered
    page stack and ``<< Back`` / ``Next >>`` / ``Finish`` / ``Cancel``.

    ``chrome=\"stpre_cw\"`` matches the STpre Condition Wizard footer
    (Back/Next left, Finish right, no Cancel) and uses a splitter for
    the nav | content panes.
    """

    def __init__(self, title: str, *, parent=None, show_tree: bool = True,
                 chrome: str = "default"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._keys: list[str] = []
        self._index: dict[str, int] = {}
        self._titles: dict[str, str] = {}
        self._parents: dict[str, str] = {}
        self._items: dict[str, QTreeWidgetItem] = {}
        self._group_keys: set[str] = set()
        self._defined_keys: set[str] = set()
        self._hidden_keys: set[str] = set()
        self._current = 0
        self._chrome = chrome

        root = QVBoxLayout(self)
        # STpre Condition Wizard uses the window title + "N ( i/m ) step"
        # line only — skip the in-dialog DialogHeader caption (avoids
        # duplicating "Condition Wizard").
        self.header = DialogHeader(title, "wizard", self)
        root.addWidget(self.header)
        if chrome == "stpre_cw":
            self.header.hide()

        self.step_label = QLabel(self)
        self.step_label.setStyleSheet("color: #666;")
        root.addWidget(self.step_label)

        self.nav = None
        self.stack = QStackedWidget(self)
        if show_tree:
            self.nav = QTreeWidget(self)
            self.nav.setHeaderHidden(True)
            self.nav.setRootIsDecorated(True)
            self.nav.setUniformRowHeights(True)
            self.nav.setTextElideMode(Qt.ElideNone)
            self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.nav.setSizePolicy(QSizePolicy.Preferred,
                                  QSizePolicy.Expanding)
            # Default floor so Condition Wizard steps are readable before
            # _fit_nav_width() measures the longest label.
            self.nav.setMinimumWidth(240)
            self.nav.itemClicked.connect(self._on_nav)
            if chrome == "stpre_cw":
                split = QSplitter(Qt.Horizontal, self)
                split.addWidget(self.nav)
                split.addWidget(self.stack)
                split.setStretchFactor(0, 0)
                split.setStretchFactor(1, 1)
                split.setChildrenCollapsible(False)
                root.addWidget(split, 1)
                self._splitter = split
            else:
                mid = QHBoxLayout()
                mid.setSpacing(8)
                mid.addWidget(self.nav, 0)
                mid.addWidget(self.stack, 1)
                root.addLayout(mid, 1)
                self._splitter = None
        else:
            root.addWidget(self.stack, 1)
            self._splitter = None

        blay = QHBoxLayout()
        self.btn_back = QPushButton("<< Back", self)
        self.btn_next = QPushButton("Next >>", self)
        self.btn_finish = QPushButton("Finish", self)
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_finish.clicked.connect(self._finish)
        self.btn_cancel.clicked.connect(self._cancel)
        if chrome == "stpre_cw":
            blay.addWidget(self.btn_back)
            blay.addWidget(self.btn_next)
            blay.addStretch(1)
            blay.addWidget(self.btn_finish)
            self.btn_cancel.hide()
        else:
            blay.addStretch(1)
            for b in (self.btn_back, self.btn_next, self.btn_finish,
                      self.btn_cancel):
                blay.addWidget(b)
        root.addLayout(blay)
        self.resize(980 if show_tree else 760, 620)

    # -- page management --------------------------------------------------

    def _add_page(self, key: str, title: str, widget: Optional[QWidget],
                  parent_key: Optional[str] = None) -> None:
        """Register a page; ``widget=None`` creates a nav-group node only."""
        self._titles[key] = title
        if parent_key:
            self._parents[key] = parent_key
        is_group = widget is None
        if is_group:
            self._group_keys.add(key)
        if self.nav is not None:
            parent_item = self._items.get(parent_key) if parent_key \
                else None
            item = QTreeWidgetItem(
                parent_item or self.nav.invisibleRootItem(), [title])
            # No checkboxes — status shown via STpre-style icons.
            flags = item.flags()
            flags &= ~Qt.ItemIsUserCheckable
            item.setFlags(flags)
            item.setIcon(0, nav_status_icon(False, group=is_group))
            self._items[key] = item
            if parent_item is None:
                self.nav.addTopLevelItem(item)
            else:
                parent_item.setExpanded(True)
        if widget is not None:
            self._index[key] = len(self._keys)
            self._keys.append(key)
            self.stack.addWidget(widget)

    def _mark_defined(self, key: str, defined: bool) -> None:
        item = self._items.get(key)
        if defined:
            self._defined_keys.add(key)
        else:
            self._defined_keys.discard(key)
        if item is not None:
            item.setIcon(
                0, nav_status_icon(defined,
                                   group=key in self._group_keys))
        # Parent group turns defined when any child is defined.
        parent = self._parents.get(key)
        if parent and defined:
            self._mark_defined(parent, True)

    def _set_page_hidden(self, key: str, hidden: bool) -> None:
        """Hide/show a nav step (e.g. Analysis Control detail-only children)."""
        if hidden:
            self._hidden_keys.add(key)
        else:
            self._hidden_keys.discard(key)
        item = self._items.get(key)
        if item is not None:
            item.setHidden(hidden)

    def _next_visible_index(self, start: int, *,
                            forward: bool) -> Optional[int]:
        step = 1 if forward else -1
        i = start
        while 0 <= i < len(self._keys):
            if self._keys[i] not in self._hidden_keys:
                return i
            i += step
        return None

    def _fit_nav_width(self) -> None:
        """Widen the left step tree so titles like ``File Specification`` fit.

        Call after all ``_add_page`` registrations.  Without this the nav
        QTreeWidget collapses to a tiny sizeHint and truncates labels.
        """
        if self.nav is None:
            return
        self.nav.expandAll()
        self.nav.resizeColumnToContents(0)
        # column text + icon/branch chrome + padding
        need = int(self.nav.sizeHintForColumn(0)) + 48
        # Offscreen / before first layout, sizeHintForColumn can be 0 —
        # fall back to font metrics of the longest registered title.
        if self._titles:
            fm = self.nav.fontMetrics()
            longest = max(
                fm.horizontalAdvance(t) for t in self._titles.values())
            need = max(need, longest + 56)
        need = max(240, min(need, 400))
        self.nav.setMinimumWidth(need)
        if getattr(self, "_chrome", "") == "stpre_cw" and self._splitter:
            # Let the splitter own the width; seed a sensible start size.
            self.nav.resize(need, self.nav.height())
            self._splitter.setSizes([need, max(500, self.width() - need)])
        else:
            # Prefer a stable starting width; user can still grow the dialog.
            self.nav.setFixedWidth(need)

    def _show_page(self, idx: int) -> None:
        if not self._keys:
            return
        idx = max(0, min(idx, len(self._keys) - 1))
        if self._keys[idx] in self._hidden_keys:
            found = self._next_visible_index(idx, forward=True)
            if found is None:
                found = self._next_visible_index(idx, forward=False)
            if found is None:
                return
            idx = found
        self._current = idx
        key = self._keys[self._current]
        self.stack.setCurrentIndex(self._index[key])
        visible = [k for k in self._keys if k not in self._hidden_keys]
        try:
            pos = visible.index(key) + 1
        except ValueError:
            pos = self._current + 1
        total = max(1, len(visible))
        self.step_label.setText(
            f"{self._titles[key]}   ( {pos}/{total} ) step")
        prev_i = self._next_visible_index(self._current - 1, forward=False)
        next_i = self._next_visible_index(self._current + 1, forward=True)
        self.btn_back.setEnabled(prev_i is not None)
        self.btn_next.setEnabled(next_i is not None)
        if self.nav is not None:
            self.nav.setCurrentItem(self._items.get(key))

    def _on_nav(self, item, _col) -> None:
        for key, it in self._items.items():
            if it is item and key in self._index \
                    and key not in self._hidden_keys:
                if self._index[key] != self._current:
                    self._commit_current()
                self._show_page(self._index[key])
                # Clicking a step marks it defined (STpre nav check).
                self._mark_defined(key, True)
                return

    def _go_back(self) -> None:
        self._commit_current()
        i = self._next_visible_index(self._current - 1, forward=False)
        if i is not None:
            self._show_page(i)

    def _go_next(self) -> None:
        self._commit_current()
        i = self._next_visible_index(self._current + 1, forward=True)
        if i is not None:
            self._show_page(i)

    def _finish(self) -> None:
        self._commit_current()
        self._on_finish()
        self.accept()

    def _cancel(self) -> None:
        self.reject()

    def reject(self) -> None:
        """Window close / Cancel — restore pre-wizard model state."""
        self._on_cancel()
        super().reject()

    # subclass hooks --------------------------------------------------------

    def _commit_current(self) -> None:
        """Apply the current page and refresh its nav status (override)."""

    def _on_finish(self) -> None:
        """Write the wizard settings to the model (override)."""

    def _on_cancel(self) -> None:
        """Restore the pre-wizard state (override)."""

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)

    def _rebuild(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()


# ========================================================== Initial Wizard

from cab_iwizard_pages import (
    PURPOSE_BC,
    _IwAnalysisTypePage,
    _IwConfirmPage,
    _IwDomainPage,
    _IwInitialGravityPage,
    _IwProjectPage,
    _IwPurposePage,
)


class InitialWizard(WizardBase):
    """[Wizard] - [Initial Setting]: STpre Initial Wizard (6 steps).

    Pre_eng lists Import CAD Data as its own step; here it is embedded in
    the Project page (checkbox + table) so navigation stays 6 pages.
    """

    # Custom dialog result: user chose Open Existing Project (.cab).
    RESULT_OPEN_EXISTING = 2

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 cad_meshes, archive=None, parent=None):
        super().__init__("Initial Wizard", parent=parent, show_tree=False)
        self.header.hide()
        self.model = model
        self.props = props
        self.archive = archive
        self._snapshot = model.doc.serialize()
        # Always a mutable list so Import CAD can append tessellations
        # even when the host viewer still has ``_cad_meshes is None``.
        self._cad_meshes = list(cad_meshes) if cad_meshes else []
        self.opened_existing_path: Optional[str] = None

        self.p_project = _IwProjectPage(model, archive, self._cad_meshes)
        self.p_import = self.p_project
        self.p_domain = _IwDomainPage(model, props, self._cad_meshes)
        self.p_analysis = _IwAnalysisTypePage(model)
        self.p_initgrav = _IwInitialGravityPage(model)
        self.p_purpose = _IwPurposePage(model, log_fn=self._log)
        self.p_confirm = _IwConfirmPage()

        self._add_page("project", "Project", self.p_project)
        self._add_page("domain", "Computational Domain", self.p_domain)
        self._add_page("analysis", "Analysis Type", self.p_analysis)
        self._add_page("initgrav", "Initial Value/Gravity", self.p_initgrav)
        self._add_page("purpose", "Purpose of Analysis", self.p_purpose)
        self._add_page("confirm", "Confirm Settings", self.p_confirm)
        self._show_page(0)

    def open_existing_project(self, path: str) -> None:
        """Load path in the host viewer and close this wizard (no Finish)."""
        self.opened_existing_path = path
        # Bypass WizardBase.reject() snapshot restore — abandon wizard edits.
        QDialog.done(self, self.RESULT_OPEN_EXISTING)

    def _show_page(self, idx: int) -> None:
        if 0 <= idx < len(self._keys) and self._keys[idx] == "confirm":
            self.p_confirm.set_rows(self._summary_rows())
        super()._show_page(idx)

    def _go_next(self) -> None:
        if self._keys[self._current] == "purpose":
            self.p_purpose.refresh_boundary()
        super()._go_next()

    def _summary_rows(self) -> list[tuple[str, str]]:
        m = self.model
        spec = self.p_domain._current_spec()
        rows: list[tuple[str, str]] = []

        def sec(title: str) -> None:
            rows.append((f"* {title}", ""))

        def item(name: str, value: str) -> None:
            rows.append((f"    {name}", value))

        sec("Project")
        item("Project name", self.p_project.name.text())
        item("Comments", self.p_project.comment.text())
        if self.p_project.import_cad.isChecked():
            item("CAD data", f"{len(self.p_project._entries)} file(s) read")

        sec("Computational Domain")
        item("Coordinate system", self.p_domain.coordinate.currentText())
        item("Unit", spec.unit)
        item("Minimum", ", ".join(f"{v:g}" for v in spec.xyz_min))
        item("Maximum", ", ".join(f"{v:g}" for v in spec.xyz_max))
        item("Material", spec.material or "-")

        sec("Analysis Type")
        item("Heat", self.p_analysis.heat_solve.currentText())
        item("Flow type", self.p_analysis.flow_type.currentText())
        item("Turbulence model", self.p_analysis.turb_model.currentText())
        item("Radiation", self.p_analysis.radiation.currentText())
        item("Solar radiation", self.p_analysis.solar.currentText())

        sec("Initial Value/Gravity")
        ig = self.p_initgrav
        item("Ambient temperature", f"{ig.temp_default.value():g} "
             f"{ig.temp_unit.currentText()}")
        item("Gravity", f"{ig.gravity_acc.value():g} m/s2, "
             f"dir {ig.gravity_dir.currentText()}")

        sec("Purpose of Analysis")
        purpose = self.p_purpose.current()
        purpose_label = {
            "none": "No specification",
            "internal_enclosure": "Internal flow (enclosure heat release)",
            "external_natural": "External flow (natural convection)",
            "external_forced": "External flow (forced convection)",
            "external_buildings":
                "External flow (winds blowing through buildings)",
        }.get(purpose, purpose)
        item("Purpose", purpose_label)
        if purpose == "none":
            item("Boundary", "Set in Condition Wizard")
        else:
            bc = PURPOSE_BC.get(purpose, "")
            # One compact line — avoid multi-line rows that inflate height
            note = "; ".join(
                ln.strip() for ln in bc.splitlines() if ln.strip())
            if note:
                item("Boundary", note[:120] + ("…" if len(note) > 120 else ""))
        return rows

    def _on_finish(self) -> None:
        self.p_project.apply_project_fields()
        self.p_project.apply_to_model()
        # Keep wizard / domain page mesh lists in sync after Import CAD
        meshes = list(getattr(self.p_project, "cad_meshes", None)
                      or self._cad_meshes or [])
        self._cad_meshes = meshes
        self.p_domain.cad_meshes = meshes
        # STpre: after wizard CAD import, Domain follows geometry AABB
        if (self.p_project.import_cad.isChecked()
                and meshes
                and any(getattr(m, "points", None) is not None
                        for m in meshes)):
            try:
                self.p_domain._cad_size()
            except Exception:
                pass
        cab_domain.apply_domain(self.model, self.p_domain._current_spec())
        self.p_analysis.apply()
        self.p_initgrav.apply()
        self.model.set_analysis_set_value(
            "purpose", self.p_purpose.current())
        self.p_purpose.apply_boundary(self.model)
        self._rebuild()
        self._log("Initial Wizard finished; settings written to the "
                  "project (save the cab to persist).")

    def _on_cancel(self) -> None:
        import cabxml
        self.model.doc = cabxml.StpreDoc(self._snapshot)


# ======================================================== Condition Wizard

_CW_PAGES = [
    ("analysis", "Analysis Types", None),
    ("basic", "Basic Settings", None),
    ("fluid", "Fluid Region", None),
    ("flow", "Flow", None),
    ("heat", "Heat", None),
    ("humidity", "Humidity", None),
    ("solar", "Solar Radiation", None),
    ("porous", "Porous Media", None),
    ("diffusion", "Diffusion", None),
    ("particle", "Particle", None),
    ("jos_model", "Thermoregulation Model", None),
    ("current", "Electric Current", None),
    ("electrostatic", "Electrostatic Field", None),
    ("ventilation", "Ventilation Efficiency", None),
    ("reaction", "Reaction", None),
    ("fusion", "Solidification/Melting", None),
    ("artificial_light", "Lamp", None),
    ("pcm", "Phase Change Material", None),
    ("plant_canopy", "Plant Canopy", None),
    ("moving_body", "Moving Object", None),
    ("marangoni", "Marangoni Convection", None),
    ("topology_opti", "Topology Optimization", None),
    ("aircon_model", "Air Conditioner Unit", None),
    ("evaporation", "Evaporation (Free Surface)", None),
    ("boil", "Boil/Condensation", None),
    ("initial", "Initial Condition", None),
    ("bc", "Boundary Condition", None),
    ("bc_flow", "Flow Boundary", "bc"),
    ("bc_wall", "Wall Boundary", "bc"),
    ("bc_thermal", "Thermal Boundary", "bc"),
    ("bc_symm", "Symmetrical Boundary", "bc"),
    ("bc_radiation", "Radiation Grouping", "bc"),
    ("bc_diffusion", "Diffusion Boundary", "bc"),
    ("source", "Source Condition", None),
    ("fixed", "Fixed Condition", None),
    ("control", "Analysis Control", None),
    ("ctrl_steady", "Steady-state Analysis", "control"),
    ("ctrl_solver", "Solver Parameters", "control"),
    ("ctrl_stab", "Stabilization", "control"),
    ("ctrl_option", "Option", "control"),
    ("output", "Output Condition", None),
    ("out_field", "Field File", "output"),
    ("out_heatpath", "Heat Path", "output"),
    ("out_series", "Time Series", "output"),
    ("out_lfile", "L File", "output"),
    ("file", "File Specification", None),
    ("condlist", "Condition List", None),
    ("confirm", "Setting Confirmation", None),
]


class _CwAnalysisTypesPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Analysis Types (tabbed page layout)."""

    # (label, analysis_set tag, optional combo items or None)
    # Three columns match STpreCwiz Analysis Types group.
    _TYPE_COLS = (
        (
            ("Heat", "heat", None),
            ("Humidity", "humidity", None),
            ("Diffusion", "diffusion", None),
            ("Porous media", "porous_media", None),
            ("Plant canopy", "plant_canopy", None),
            ("Moving object", "moving_body", None),
            ("Thermoregulation model", "jos_model", None),
            ("Evaporation (free surf.)", "evaporation", None),
        ),
        (
            ("Solar radiation", "sun_light", None),
            ("Lamp", "artificial_light", None),
            ("Reaction", "reaction", None),
            ("Ventilation efficiency", "ventilation", None),
            ("Solidification/melting", "fusion", None),
            ("Boil/condensation", "boil", None),
            ("Marangoni convection", "marangoni", None),
            ("Topology optimization", "topology_opti", None),
        ),
        (
            ("Radiation", "radiation_analysis", (
                "VF method", "Flux method", "Monte Carlo method")),
            ("Particle", "particle", (
                "W/o inter-particle interaction",
                "With inter-particle interaction")),
            ("Air conditioner unit", "aircon_model", None),
            ("Free surface", "free_surface", (
                "MARS method", "VOF method")),
            ("Electric current", "current", None),
            ("Electrostatic field", "electrostatic", None),
            ("Phase change material", "pcm", None),
            ("MSC CoSim", "msc_cosim", None),
            ("BCI-ROM", "bci_rom", None),
        ),
    )
    # Grayed in typical incompressible sessions until a parent option exists.
    _DISABLED_UNTIL_FS = frozenset({"evaporation", "boil"})
    # scFLOW-only coupling analyses: scSTREAM .cab cannot carry their
    # configuration (MSC CoSim / BCI-ROM are configured in scFLOW's
    # project settings, not in the scSTREAM condition set).  Kept grey
    # rather than writing unverified tags.
    _ALWAYS_DISABLED = frozenset({"msc_cosim", "bci_rom"})
    _DISABLED_TIP = (
        "scFLOW-only analysis (configured in scFLOW project settings); "
        "not applicable to scSTREAM .cab projects."
    )
    # Analysis types whose checkbox state lives outside the flat
    # <analysis_set> tags (verified against STpre 2025.2 COM saves):
    #   ("plant_canopy", "etc", "plant_resistance")  -> <analysis_etc>
    #   ("marangoni",    "etc-section", "marangoni") -> <analysis_etc>
    #   ("topology_opti","etc-section", "topology_optimize")
    #   ("moving_body",  "aset", "moving_body")      -> flat, value 1|2
    #   ("aircon_model", "aset", "aircon_model")     -> flat, value T|F
    _SPECIAL_TAGS = {
        "plant_canopy": ("etc", "plant_resistance"),
        "moving_body": ("aset", "moving_body"),
        "marangoni": ("etc_sec", "marangoni"),
        "topology_opti": ("etc_sec", "topology_optimize"),
        "aircon_model": ("aset", "aircon_model"),
        "pcm": ("etc_sec", "phase_change_material"),
        "electrostatic": ("etc", "partcile_echarge"),
        "evaporation": ("etc_sec", "evaporation"),
        "boil": ("etc_sec", "boil_condensation"),
    }

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self.types: dict[str, QCheckBox] = {}
        self.type_combos: dict[str, QComboBox] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Selects analysis options.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        # --- Incompressible / Compressible ---
        ic = QGroupBox("Incompressible/Compressible flow", page)
        icl = QHBoxLayout(ic)
        self.incomp = QRadioButton("Incompressible", ic)
        self.comp = QRadioButton("Compressible", ic)
        self.incomp.setChecked(True)
        icl.addWidget(self.incomp)
        icl.addWidget(self.comp)
        icl.addStretch(1)
        lay.addWidget(ic)

        # --- Flow field ---
        flow = QGroupBox("Flow field", page)
        fl = QVBoxLayout(flow)
        self.flow_chk = QCheckBox("Flow", flow)
        self.flow_chk.setChecked(True)
        fl.addWidget(self.flow_chk)
        trow = QHBoxLayout()
        trow.addSpacing(18)
        self.laminar = QRadioButton("Laminar flow", flow)
        self.turbulent = QRadioButton("Turbulent flow", flow)
        self.turb_model = QComboBox(flow)
        self.turb_model.addItems([
            "Standard k-eps model", "RNG k-eps model", "MP k-eps model",
            "Linear low-Re model", "Non-linear low-Re model",
            "Improved LK k-eps model", "LES"])
        trow.addWidget(self.laminar)
        trow.addWidget(self.turbulent)
        trow.addWidget(self.turb_model, 1)
        fl.addLayout(trow)
        lay.addWidget(flow)
        self.flow_chk.toggled.connect(self._sync_flow)

        # --- Analysis types (3 columns) ---
        tg = QGroupBox("Analysis types", page)
        grid = QGridLayout(tg)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        for col, items in enumerate(self._TYPE_COLS):
            for row, (label, key, combo_items) in enumerate(items):
                cell = QHBoxLayout()
                cb = QCheckBox(label, tg)
                self.types[key] = cb
                cell.addWidget(cb)
                if combo_items:
                    cmb = QComboBox(tg)
                    cmb.addItems(list(combo_items))
                    cmb.setEnabled(False)
                    self.type_combos[key] = cmb
                    cell.addWidget(cmb, 1)
                    cb.toggled.connect(cmb.setEnabled)
                else:
                    cell.addStretch(1)
                grid.addLayout(cell, row, col)
        lay.addWidget(tg)
        # Free-surface dependents + always-disabled rows
        if "free_surface" in self.types:
            self.types["free_surface"].toggled.connect(self._sync_fs_deps)
        for key in self._ALWAYS_DISABLED:
            if key in self.types:
                self.types[key].setEnabled(False)
                self.types[key].setChecked(False)
                self.types[key].setToolTip(self._DISABLED_TIP)

        # --- Steady / Transient ---
        stg = QGroupBox("Steady-state analysis/Transient analysis", page)
        stl = QHBoxLayout(stg)
        self.steady = QRadioButton("Steady-state analysis", stg)
        self.transient = QRadioButton("Transient analysis", stg)
        self.steady.setChecked(True)
        stl.addWidget(self.steady)
        stl.addWidget(self.transient)
        stl.addStretch(1)
        lay.addWidget(stg)

        # --- For scripts ---
        scr = QGroupBox("For scripts", page)
        scl = QVBoxLayout(scr)
        self.var_reg = QCheckBox("Variable Registration", scr)
        scl.addWidget(self.var_reg)
        lay.addWidget(scr)

        lay.addStretch(1)
        tabs.addTab(page, "Analysis Types")
        root.addWidget(tabs, 1)
        self._load()
        self._sync_flow(self.flow_chk.isChecked())
        self._sync_fs_deps(
            self.types["free_surface"].isChecked()
            if "free_surface" in self.types else False)

    def _sync_flow(self, on: bool) -> None:
        for w in (self.laminar, self.turbulent, self.turb_model):
            w.setEnabled(on)

    def _sync_fs_deps(self, on: bool) -> None:
        for key in self._DISABLED_UNTIL_FS:
            cb = self.types.get(key)
            if cb is None:
                continue
            cb.setEnabled(on)
            if not on:
                cb.setChecked(False)
        fs_cmb = self.type_combos.get("free_surface")
        if fs_cmb is not None:
            fs_cmb.setEnabled(
                on and self.types["free_surface"].isChecked())

    def _flag(self, tag: str, default: str = "0") -> bool:
        v = self.model.analysis_set_value(tag, default).strip().lower()
        return v in ("1", "t", "true", "on")

    def _special_flag(self, key: str) -> bool:
        """Checkbox state of the STpre <analysis_etc>/special-stored types."""
        kind, tag = self._SPECIAL_TAGS[key]
        if kind == "etc":
            return self.model.analysis_etc_value(tag, "0").strip() \
                in ("1", "2", "T", "t")
        if kind == "etc_sec":
            return self.model.analysis_etc_section(tag) is not None
        v = self.model.analysis_set_value(tag, "0").strip().lower()
        if key == "moving_body":
            return v in ("1", "2")
        return v in ("1", "t", "true", "on")

    def _apply_special(self, key: str, on: bool) -> None:
        """Write the STpre-canonical storage for the special analysis keys."""
        kind, tag = self._SPECIAL_TAGS[key]
        if kind == "etc":
            if on:
                # partcile_echarge 2 (initial-only) must survive a flag
                # re-apply: only stamp "1" over an off value.
                cur = self.model.analysis_etc_value(tag, "0").strip()
                if cur not in ("1", "2"):
                    self.model.set_analysis_etc_value(tag, "1")
            else:
                self.model.set_analysis_etc_value(tag, "0")
            return
        if kind == "etc_sec":
            if on:
                # create the section when missing; never overwrite deeper
                # parameters already written by the product page
                self.model.ensure_analysis_etc_section(tag)
            else:
                self.model.remove_analysis_etc_section(tag)
            return
        if key == "moving_body":
            self.model.set_analysis_set_value(tag, "1" if on else "0")
            if on:
                self.model.set_analysis_set_value("moving_body_file", "0")
            return
        self.model.set_analysis_set_value(tag, "T" if on else "F")

    def _load(self) -> None:
        typ = self.model.analysis_set_value("type", "incompressive").lower()
        self.comp.setChecked(typ.startswith("comp"))
        self.incomp.setChecked(not self.comp.isChecked())
        turb = self.model.analysis_set_value("turbulence", "0")
        self.flow_chk.setChecked(True)
        self.turbulent.setChecked(turb not in ("0", "", "none"))
        self.laminar.setChecked(not self.turbulent.isChecked())
        try:
            mi = int(float(
                self.model.analysis_set_value("turbulence_model", "0")))
            if 0 <= mi < self.turb_model.count():
                self.turb_model.setCurrentIndex(mi)
        except ValueError:
            pass
        # heat uses 1/0; other flags may be 1/0 or T/F.
        # The five advanced types live in <analysis_etc> / special
        # analysis_set tags (STpre COM round-trip verified).
        for key, cb in self.types.items():
            if key == "heat":
                cb.setChecked(
                    self.model.analysis_set_value("heat", "0") == "1")
            elif key in self._SPECIAL_TAGS:
                cb.setChecked(self._special_flag(key))
            else:
                cb.setChecked(self._flag(key))
        # Radiation element type → combo
        rad = self.type_combos.get("radiation_analysis")
        if rad is not None:
            from cabxml import _first
            aset = _first(self.model.root, "analysis_set")
            rel = _first(aset, "radiation") if aset is not None else None
            if rel is not None and rel.attrib.get("type", "").lower() == "vf":
                rad.setCurrentIndex(0)
            # treat existing nested <radiation> as analysis-on
            if rel is not None and not self.types["radiation_analysis"].isChecked():
                # only auto-check when an explicit flag says so
                pass
        calc = self.model.analysis_set_value("calculation", "steady")
        self.transient.setChecked(calc == "transient")
        self.steady.setChecked(calc != "transient")
        self.var_reg.setChecked(self._flag("operation_var"))

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "type",
            "compressive" if self.comp.isChecked() else "incompressive")
        heat = "1" if self.types["heat"].isChecked() else "0"
        self.model.set_analysis_set_value("heat", heat)
        if self.flow_chk.isChecked():
            turb = "1" if self.turbulent.isChecked() else "0"
            self.model.set_analysis_set_value("turbulence", turb)
            self.model.set_analysis_set_value(
                "turbulence_model", str(self.turb_model.currentIndex()))
        else:
            self.model.set_analysis_set_value("turbulence", "0")
        for key, cb in self.types.items():
            if key == "heat":
                continue
            if key in self._SPECIAL_TAGS:
                self._apply_special(key, cb.isChecked())
                continue
            self.model.set_analysis_set_value(
                key, "1" if cb.isChecked() else "0")
        # Keep / refresh radiation@type when Radiation is on (do not
        # overwrite the nested <radiation> element via set_analysis_set_value).
        if self.types["radiation_analysis"].isChecked():
            from cabxml import _first
            import xml.etree.ElementTree as ET
            aset = self.model.ensure_analysis_set()
            rel = _first(aset, "radiation")
            if rel is None:
                rel = ET.SubElement(aset, "radiation")
                rel.tail = "\n   "
            cmb = self.type_combos.get("radiation_analysis")
            mode = (cmb.currentText() if cmb is not None else "VF method")
            rel.attrib["type"] = (
                "vf" if mode.startswith("VF") else
                "flux" if "Flux" in mode else "mc")
        self.model.set_analysis_set_value(
            "operation_var",
            "1" if self.var_reg.isChecked() else "0")
        cycle = self.model.analysis_set_value("cycle", "1,100").split(",")
        try:
            start = int(float(cycle[0]))
            end = int(float(cycle[1]))
        except (ValueError, IndexError):
            start, end = 1, 100
        self.model.set_cycles(
            start, end, transient=self.transient.isChecked())


class _CwBasicSettingsPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Basic Settings (Coordinate System/Gravity)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        self._syncing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Sets coordinate system and gravity.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        # --- Coordinate system ---
        cg = QGroupBox("Coordinate system", page)
        cgl = QVBoxLayout(cg)
        cgl.addWidget(QLabel("Sets Cartesian coordinate.", cg))
        note_c = QLabel(
            "Note) Modify coordinate system in [Edit]-[Reset Computational "
            "Domain] menu.", cg)
        note_c.setWordWrap(True)
        note_c.setStyleSheet("color: #555;")
        cgl.addWidget(note_c)
        lay.addWidget(cg)

        # --- Gravity ---
        gg = QGroupBox("Gravity", page)
        ggl = QVBoxLayout(gg)
        self.gravity_chk = QCheckBox("Consider gravity", gg)
        ggl.addWidget(self.gravity_chk)

        drow = QHBoxLayout()
        drow.addWidget(QLabel("Direction of gravity", gg))
        self.gravity_dir = QComboBox(gg)
        for label, _v in _CW_GRAVITY_DIRS:
            self.gravity_dir.addItem(label)
        drow.addWidget(self.gravity_dir, 1)
        ggl.addLayout(drow)

        crow = QHBoxLayout()
        crow.addWidget(QLabel("Direction component", gg))
        self.grav_comp: dict[str, QDoubleSpinBox] = {}
        for ax in "xyz":
            crow.addWidget(QLabel(ax.upper(), gg))
            sp = QDoubleSpinBox(gg)
            sp.setDecimals(6)
            sp.setRange(-1.0e6, 1.0e6)
            sp.setSingleStep(0.1)
            sp.setMaximumWidth(72)
            self.grav_comp[ax] = sp
            crow.addWidget(sp)
        self.btn_check = QPushButton("Check Direction", gg)
        self.btn_check.clicked.connect(self._check_direction)
        crow.addWidget(self.btn_check)
        crow.addStretch(1)
        ggl.addLayout(crow)

        arow = QHBoxLayout()
        arow.addWidget(QLabel("Acceleration due to gravity", gg))
        self.gravity_acc = QDoubleSpinBox(gg)
        self.gravity_acc.setRange(0.0, 1000.0)
        self.gravity_acc.setDecimals(4)
        self.gravity_acc.setValue(9.8)
        arow.addWidget(self.gravity_acc)
        self.gravity_unit = QComboBox(gg)
        self.gravity_unit.addItems(["m/s2", "cm/s2", "ft/s2"])
        arow.addWidget(self.gravity_unit)
        arow.addStretch(1)
        ggl.addLayout(arow)

        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Reference density", gg))
        self.ref_density = QDoubleSpinBox(gg)
        self.ref_density.setDecimals(6)
        self.ref_density.setRange(0.0, 1.0e9)
        self.ref_density.setEnabled(False)
        rrow.addWidget(self.ref_density)
        rrow.addWidget(QLabel("kg/m3", gg))
        rrow.addStretch(1)
        ggl.addLayout(rrow)
        lay.addWidget(gg)

        # --- Ambient temperature ---
        ag = QGroupBox("Ambient temperature", page)
        agl = QVBoxLayout(ag)
        self.ambient = QDoubleSpinBox(ag)
        self.ambient.setRange(-273.15, 1.0e6)
        self.ambient.setDecimals(2)
        _pair_row(agl, "Ambient temperature", self.ambient, "C")
        note_a = QLabel(
            "Note) Set the reference temperature for buoyancy force and "
            "the default value of temperature.", ag)
        note_a.setWordWrap(True)
        note_a.setStyleSheet("color: #555;")
        agl.addWidget(note_a)
        lay.addWidget(ag)

        # --- Periodic boundary ---
        pg = QGroupBox("Periodic boundary", page)
        pgl = QVBoxLayout(pg)
        self.periodic = QCheckBox("Consider periodic boundary", pg)
        pgl.addWidget(self.periodic)
        lay.addWidget(pg)

        lay.addStretch(1)
        tabs.addTab(page, "Coordinate System/Gravity")
        root.addWidget(tabs, 1)

        self.gravity_chk.toggled.connect(self._sync_gravity_enabled)
        self.gravity_dir.currentIndexChanged.connect(self._on_dir_combo)
        for sp in self.grav_comp.values():
            sp.valueChanged.connect(self._on_comp_edited)
        self._load()
        self._sync_gravity_enabled(self.gravity_chk.isChecked())

    def _vec(self) -> tuple[float, float, float]:
        return (self.grav_comp["x"].value(),
                self.grav_comp["y"].value(),
                self.grav_comp["z"].value())

    def _set_comp(self, vec: tuple[float, float, float]) -> None:
        self._syncing = True
        try:
            self.grav_comp["x"].setValue(vec[0])
            self.grav_comp["y"].setValue(vec[1])
            self.grav_comp["z"].setValue(vec[2])
        finally:
            self._syncing = False

    def _on_dir_combo(self, idx: int) -> None:
        if self._syncing:
            return
        _label, vec = _CW_GRAVITY_DIRS[idx]
        if vec is not None:
            self._set_comp(vec)

    def _on_comp_edited(self, *_args) -> None:
        if self._syncing:
            return
        vec = self._vec()
        self._syncing = True
        try:
            matched = False
            for i, (_label, v) in enumerate(_CW_GRAVITY_DIRS):
                if v is not None and all(
                        abs(a - b) < 1e-9 for a, b in zip(vec, v)):
                    self.gravity_dir.setCurrentIndex(i)
                    matched = True
                    break
            if not matched:
                # last entry = User-defined
                self.gravity_dir.setCurrentIndex(len(_CW_GRAVITY_DIRS) - 1)
        finally:
            self._syncing = False

    def _sync_gravity_enabled(self, on: bool) -> None:
        for w in (self.gravity_dir, self.btn_check, self.gravity_acc,
                  self.gravity_unit, *self.grav_comp.values()):
            w.setEnabled(on)

    def _check_direction(self) -> None:
        vx, vy, vz = self._vec()
        self._log(
            f"Gravity direction ({vx:g}, {vy:g}, {vz:g}) — "
            "shown at the domain centre in STpre; "
            "written to analysis_set grav_vec on Finish.")

    def _load(self) -> None:
        try:
            self.ambient.setValue(float(self.model.project_value(
                "ambient_temperature", "20")))
        except ValueError:
            pass
        grav = self.model.analysis_set_value("grav_vec", "0,0,-1").split(",")
        try:
            vec = (float(grav[0]), float(grav[1]), float(grav[2]))
        except (ValueError, IndexError):
            vec = (0.0, 0.0, -1.0)
        self.gravity_chk.setChecked(any(abs(v) > 1e-15 for v in vec))
        self._set_comp(vec)
        self._on_comp_edited()
        try:
            self.gravity_acc.setValue(float(
                self.model.analysis_set_value("grav_abs", "9.8")))
        except ValueError:
            pass
        try:
            self.ref_density.setValue(float(
                self.model.analysis_set_value("ref_density", "0")))
        except ValueError:
            pass
        per = self.model.analysis_set_value("periodic_boundary", "0").strip()
        self.periodic.setChecked(per.lower() in ("1", "t", "true"))

    def apply(self) -> None:
        self.model.set_project_value(
            "ambient_temperature", f"{self.ambient.value():g}")
        if self.gravity_chk.isChecked():
            self.model.set_gravity(self.gravity_acc.value(), self._vec())
            unit = self.gravity_unit.currentText()
            # keep unit on grav_abs (STpre stores unit="m/s2")
            from cabxml import _first
            aset = self.model.ensure_analysis_set()
            el = _first(aset, "grav_abs")
            if el is not None:
                el.attrib["unit"] = unit
        else:
            self.model.set_gravity(0.0, (0.0, 0.0, 0.0))
        self.model.set_analysis_set_value(
            "ref_density", f"{self.ref_density.value():g}")
        self.model.set_analysis_set_value(
            "periodic_boundary",
            "1" if self.periodic.isChecked() else "0")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg)
        # ConditionWizard may sit a level above page widgets
        gp = parent.parent() if parent is not None else None
        if gp is not None and hasattr(gp, "_log"):
            gp._log(msg)


class _CwFluidRegionPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Fluid Region."""

    def __init__(self, model: StpreModel, props):
        super().__init__()
        self.model = model
        self.props = props
        # rows: dict(no, region, material, type, flow)  flow=Laminar|Turbulent
        self._rows: list[dict] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        typ = model.analysis_set_value("type", "incompressive").lower()
        tip = ("Sets region for compressible fluid."
               if typ.startswith("comp")
               else "Sets region for incompressible fluid.")
        lay.addWidget(QLabel(tip, page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        g = QGroupBox("Fluid region", page)
        gl = QVBoxLayout(g)
        head = QHBoxLayout()
        head.addStretch(1)
        self.num_lab = QLabel("No. of fluid type:1", g)
        head.addWidget(self.num_lab)
        gl.addLayout(head)

        body = QHBoxLayout()
        self.table = QTableWidget(0, 5, g)
        self.table.setHorizontalHeaderLabels([
            "Fluid No.", "Region name", "Material", "Type", "Flow field"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_dbl)
        body.addWidget(self.table, 1)

        arrows = QVBoxLayout()
        self.btn_up = QPushButton("▲", g)
        self.btn_down = QPushButton("▼", g)
        self.btn_up.setFixedWidth(28)
        self.btn_down.setFixedWidth(28)
        self.btn_up.clicked.connect(lambda: self._move_row(-1))
        self.btn_down.clicked.connect(lambda: self._move_row(1))
        arrows.addWidget(self.btn_up)
        arrows.addWidget(self.btn_down)
        arrows.addStretch(1)
        body.addLayout(arrows)
        gl.addLayout(body)

        bot = QHBoxLayout()
        left_btns = QVBoxLayout()
        self.btn_set = QPushButton("Set Fluid Material...", g)
        self.btn_cancel_mat = QPushButton("Cancel Fluid Material", g)
        self.btn_set.clicked.connect(self._set_material)
        self.btn_cancel_mat.clicked.connect(self._cancel_material)
        left_btns.addWidget(self.btn_set)
        left_btns.addWidget(self.btn_cancel_mat)
        left_btns.addStretch(1)
        bot.addLayout(left_btns)

        ff = QGroupBox("Flow field", g)
        ffl = QVBoxLayout(ff)
        rrow = QHBoxLayout()
        self.flow_lam = QRadioButton("Laminar", ff)
        self.flow_turb = QRadioButton("Turbulent", ff)
        self.flow_turb.setChecked(True)
        self.btn_flow_set = QPushButton("Set", ff)
        self.btn_flow_set.clicked.connect(self._set_flow)
        rrow.addWidget(self.flow_lam)
        rrow.addWidget(self.flow_turb)
        rrow.addWidget(self.btn_flow_set)
        rrow.addStretch(1)
        ffl.addLayout(rrow)
        self.btn_reset_turb = QPushButton("Reset all to turbulent", ff)
        self.btn_reset_turb.clicked.connect(self._reset_all_turbulent)
        ffl.addWidget(self.btn_reset_turb)
        bot.addWidget(ff, 1)
        gl.addLayout(bot)

        note = QLabel(
            "Note)\n"
            "* Able to set computational domain and first-tier of group "
            "hierarchy as fluid region.\n"
            "* Sets Fluid 1 double-clicking region name.\n"
            "* Considered diffusion and reaction for only fluid number 1.",
            g)
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        gl.addWidget(note)
        lay.addWidget(g)

        self.low_mach = QCheckBox("Low-Mach-number approximation", page)
        lay.addWidget(self.low_mach)
        note_lm = QLabel(
            "Note) Set reference density and reference temperature in "
            "[Incompressible Fluid].", page)
        note_lm.setWordWrap(True)
        note_lm.setStyleSheet("color: #555;")
        lay.addWidget(note_lm)
        self.pcorr_each = QCheckBox(
            "Calculate pressure correction equation for each fluid material",
            page)
        self.pcorr_each.setEnabled(False)
        lay.addWidget(self.pcorr_each)
        lay.addStretch(1)

        tabs.addTab(page, "Fluid Region")
        root.addWidget(tabs, 1)
        # keep a combo for older call sites / tests that look it up
        self.fluid_combo = QComboBox(self)
        self.fluid_combo.hide()
        if props:
            self.fluid_combo.addItems(props.material_names())
        self._load()

    def _material_type(self, material: str) -> str:
        m = (material or "").lower()
        if "compressible" in m and "incompressible" not in m:
            return "compressible"
        if self.model.analysis_set_value("type", "").lower().startswith(
                "comp"):
            return "compressible"
        return "incompressible"

    def _default_flow(self) -> str:
        turb = self.model.analysis_set_value("turbulence", "0")
        return "Turbulent" if turb not in ("0", "", "none") else "Laminar"

    def _parse_region_text(self, text: str) -> tuple[str, str, str]:
        parts = [p.strip() for p in (text or "").split(",")]
        region = parts[0] if parts else self.model.domain_name() or "Domain"
        material = parts[1] if len(parts) > 1 else (
            self.model.domain_material() or "")
        flow = self._default_flow()
        if len(parts) > 2:
            fl = parts[2].lower()
            if fl.startswith("lam"):
                flow = "Laminar"
            elif fl.startswith("turb"):
                flow = "Turbulent"
        return region, material, flow

    def _load(self) -> None:
        from cabxml import _first, _children
        self._rows = []
        aset = _first(self.model.root, "analysis_set")
        fr = _first(aset, "fluid_region") if aset is not None else None
        if fr is not None:
            for reg in _children(fr, "region"):
                no = reg.attrib.get("no", str(len(self._rows) + 1))
                region, material, flow = self._parse_region_text(
                    (reg.text or "").strip())
                self._rows.append({
                    "no": no, "region": region, "material": material,
                    "type": self._material_type(material), "flow": flow,
                })
        if not self._rows:
            mat = self.model.domain_material() or ""
            self._rows.append({
                "no": "1",
                "region": self.model.domain_name() or "Domain",
                "material": mat,
                "type": self._material_type(mat),
                "flow": self._default_flow(),
            })
        self._refresh_table()
        if self._rows:
            flow0 = self._rows[0]["flow"]
            self.flow_turb.setChecked(flow0 == "Turbulent")
            self.flow_lam.setChecked(flow0 != "Turbulent")
            idx = self.fluid_combo.findText(self._rows[0]["material"])
            if idx >= 0:
                self.fluid_combo.setCurrentIndex(idx)
        lm = self.model.analysis_set_value("low_mach", "0").strip().lower()
        self.low_mach.setChecked(lm in ("1", "t", "true"))
        self.table.selectRow(0)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            vals = [row["no"], row["region"], row["material"],
                    row["type"], row["flow"]]
            for c, text in enumerate(vals):
                self.table.setItem(i, c, QTableWidgetItem(text))
        self.num_lab.setText(f"No. of fluid type:{len(self._rows)}")

    def _selected_row(self) -> int:
        sel = self.table.selectionModel().selectedRows()
        return sel[0].row() if sel else -1

    def _set_material(self) -> None:
        i = self._selected_row()
        if i < 0:
            i = 0
            self.table.selectRow(0)
        if not self._rows:
            return
        cur = self._rows[i]["material"]
        dlg = MaterialListDialog(
            self.props, self, current=cur,
            part_name=self._rows[i]["region"])
        if dlg.exec_() and dlg.selected_material():
            mat = dlg.selected_material()
            self._rows[i]["material"] = mat
            self._rows[i]["type"] = self._material_type(mat)
            self._refresh_table()
            self.table.selectRow(i)
            idx = self.fluid_combo.findText(mat)
            if idx >= 0:
                self.fluid_combo.setCurrentIndex(idx)
            self._log(f"Fluid Region: material[{i + 1}] = {mat}")

    def _cancel_material(self) -> None:
        i = self._selected_row()
        if i < 0 or not self._rows:
            return
        self._rows[i]["material"] = ""
        self._rows[i]["type"] = self._material_type("")
        self._refresh_table()
        self.table.selectRow(i)

    def _set_flow(self) -> None:
        i = self._selected_row()
        if i < 0 or not self._rows:
            return
        flow = "Turbulent" if self.flow_turb.isChecked() else "Laminar"
        self._rows[i]["flow"] = flow
        self._refresh_table()
        self.table.selectRow(i)

    def _reset_all_turbulent(self) -> None:
        for row in self._rows:
            row["flow"] = "Turbulent"
        self.flow_turb.setChecked(True)
        self._refresh_table()

    def _move_row(self, delta: int) -> None:
        i = self._selected_row()
        j = i + delta
        if i < 0 or j < 0 or j >= len(self._rows):
            return
        self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
        for k, row in enumerate(self._rows):
            row["no"] = str(k + 1)
        self._refresh_table()
        self.table.selectRow(j)

    def _on_dbl(self, item) -> None:
        if item is None:
            return
        # STpre: double-click region name sets Fluid 1 material
        if item.column() == 1:
            self.table.selectRow(item.row())
            self._set_material()

    def apply(self) -> None:
        import xml.etree.ElementTree as ET
        from cabxml import _first, _children, set_text
        if self._rows:
            mat = self._rows[0]["material"]
            if mat:
                self.model.set_domain_material(mat)
            # fluid 1 flow → turbulence flag (Analysis Types may overwrite)
            flow = self._rows[0]["flow"]
            if flow == "Turbulent":
                turb = self.model.analysis_set_value("turbulence", "0")
                if turb in ("0", "", "none"):
                    self.model.set_analysis_set_value("turbulence", "1")
            else:
                self.model.set_analysis_set_value("turbulence", "0")
        aset = self.model.ensure_analysis_set()
        fr = _first(aset, "fluid_region")
        if fr is None:
            fr = ET.SubElement(aset, "fluid_region")
            fr.tail = "\n   "
        for ch in list(_children(fr, "region")):
            fr.remove(ch)
        fr.attrib["num"] = str(len(self._rows))
        for row in self._rows:
            el = ET.SubElement(fr, "region")
            el.attrib["no"] = str(row["no"])
            flow_tag = ("turbulent" if row["flow"] == "Turbulent"
                        else "laminar")
            text = f"{row['region']},{row['material']},{flow_tag}"
            set_text(el, text)
            el.tail = "\n         "
        self.model.set_analysis_set_value(
            "low_mach", "1" if self.low_mach.isChecked() else "0")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "log"):
                parent.log(msg)
                return
            if hasattr(parent, "_log"):
                parent._log(msg)
                return
            parent = parent.parent()


class _CwFlowPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Flow (Flow / Turbulent Flow Option)."""

    _ADAPTIVE = (
        "Do not use adaptive wall function",
        "Use adaptive wall function (without the advection effect)",
        "Use adaptive wall function (with the advection effect)",
    )

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)

        # ---------- Flow tab ----------
        flow = QWidget()
        fl = QVBoxLayout(flow)
        fl.addWidget(QLabel("Selects velocity components of flow.", flow))
        sep = QFrame(flow)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        fl.addWidget(sep)

        g = QGroupBox("Components of velocity", flow)
        gl = QVBoxLayout(g)
        gl.addWidget(QLabel("Solve the following velocity component.", g))
        crow = QHBoxLayout()
        self.vel: dict[str, QCheckBox] = {}
        for ax, label in (("x", "X-direction"), ("y", "Y-direction"),
                          ("z", "Z-direction")):
            cb = QCheckBox(label, g)
            crow.addWidget(cb)
            self.vel[ax] = cb
        crow.addStretch(1)
        gl.addLayout(crow)
        note_ax = QLabel(
            "Note) When axial symmetry is considered, the velocity "
            "component in Y direction is invalid.", g)
        note_ax.setWordWrap(True)
        note_ax.setStyleSheet("color: #555;")
        gl.addWidget(note_ax)
        fl.addWidget(g)

        wc = QGroupBox("Wall correction model", flow)
        wcl = QVBoxLayout(wc)
        self.wall_corr = QCheckBox("Use wall correction model", wc)
        wcl.addWidget(self.wall_corr)
        note_wc = QLabel(
            "Note) It is valid when a cut-cell part exists.", wc)
        note_wc.setWordWrap(True)
        note_wc.setStyleSheet("color: #555;")
        wcl.addWidget(note_wc)
        fl.addWidget(wc)

        aw = QGroupBox("Adaptive wall function", flow)
        awl = QVBoxLayout(aw)
        self.adaptive: list[QRadioButton] = []
        for text in self._ADAPTIVE:
            rb = QRadioButton(text, aw)
            awl.addWidget(rb)
            self.adaptive.append(rb)
        self.adaptive[0].setChecked(True)
        note_aw = QLabel(
            "Note) Valid when incompressible fluid and a low-Reynolds-"
            "number turbulence model are used. With free surface, "
            "\"with the advection effect\" cannot be used.", aw)
        note_aw.setWordWrap(True)
        note_aw.setStyleSheet("color: #555;")
        awl.addWidget(note_aw)
        fl.addWidget(aw)
        fl.addStretch(1)
        tabs.addTab(flow, "Flow")

        # ---------- Turbulent Flow Option ----------
        turb = QWidget()
        tl = QVBoxLayout(turb)
        tl.addWidget(QLabel("Sets the options for turbulent flows.", turb))
        sep2 = QFrame(turb)
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        tl.addWidget(sep2)

        ev = QGroupBox("Eddy-viscosity limiter (incompressible)", turb)
        evl = QVBoxLayout(ev)
        erow = QHBoxLayout()
        self.eddy_lim = QCheckBox("Use the eddy-viscosity limiter", ev)
        erow.addWidget(self.eddy_lim)
        erow.addSpacing(12)
        erow.addWidget(QLabel("Over-limiting coefficient", ev))
        self.eddy_coeff = QDoubleSpinBox(ev)
        self.eddy_coeff.setDecimals(4)
        self.eddy_coeff.setRange(0.0, 1.0)
        self.eddy_coeff.setSingleStep(0.1)
        self.eddy_coeff.setEnabled(False)
        self.eddy_lim.toggled.connect(self.eddy_coeff.setEnabled)
        erow.addWidget(self.eddy_coeff)
        erow.addStretch(1)
        evl.addLayout(erow)
        note_ev = QLabel(
            "Note) Valid for incompressible Standard / RNG k-eps or "
            "Linear low-Re models.", ev)
        note_ev.setWordWrap(True)
        note_ev.setStyleSheet("color: #555;")
        evl.addWidget(note_ev)
        tl.addWidget(ev)

        ds = QGroupBox("Density stratification (Incompressible)", turb)
        dsl = QVBoxLayout(ds)
        self.dens_strat = QCheckBox("Consider density stratification", ds)
        dsl.addWidget(self.dens_strat)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Method", ds))
        self.dens_method = QComboBox(ds)
        self.dens_method.addItems([
            "Ushijima formula", "User-defined function"])
        mrow.addWidget(self.dens_method, 1)
        dsl.addLayout(mrow)
        lim = QGroupBox(
            "Limiting values when the local Richardson number "
            "is calculated", ds)
        liml = QHBoxLayout(lim)
        self.dens_rn = QDoubleSpinBox(lim)
        self.dens_rn.setDecimals(4)
        self.dens_rn.setRange(0.0, 1.0e6)
        self.dens_rd = QDoubleSpinBox(lim)
        self.dens_rd.setDecimals(4)
        self.dens_rd.setRange(0.0, 1.0e6)
        liml.addWidget(QLabel("Rn", lim))
        liml.addWidget(self.dens_rn)
        liml.addWidget(QLabel("Rd", lim))
        liml.addWidget(self.dens_rd)
        liml.addStretch(1)
        dsl.addWidget(lim)
        urow = QHBoxLayout()
        urow.addWidget(QLabel("User-defined function", ds))
        self.dens_udf = QPushButton("Details...", ds)
        self.dens_udf.setEnabled(False)
        self.dens_udf.clicked.connect(lambda: self._log(
            "Density stratification UDF Details (informational)."))
        urow.addWidget(self.dens_udf)
        urow.addStretch(1)
        dsl.addLayout(urow)
        note_ds = QLabel(
            "Note) It is valid when the gravity direction is negative "
            "Z-axis direction.", ds)
        note_ds.setWordWrap(True)
        note_ds.setStyleSheet("color: #555;")
        dsl.addWidget(note_ds)
        tl.addWidget(ds)
        tl.addStretch(1)
        tabs.addTab(turb, "Turbulent Flow Option")

        self.dens_strat.toggled.connect(self._sync_dens)
        self.dens_method.currentIndexChanged.connect(self._sync_dens)

        root.addWidget(tabs, 1)
        self._load()
        self._sync_dens()

    def _sync_dens(self, *_args) -> None:
        on = self.dens_strat.isChecked()
        for w in (self.dens_method, self.dens_rn, self.dens_rd):
            w.setEnabled(on)
        self.dens_udf.setEnabled(
            on and self.dens_method.currentIndex() == 1)

    def _load(self) -> None:
        comps = self.model.analysis_set_value("velocity_components", "xyz")
        for ax in "xyz":
            self.vel[ax].setChecked(ax in comps.lower())
        wc = self.model.analysis_set_value("wall_correction", "0").strip()
        self.wall_corr.setChecked(wc.lower() in ("1", "t", "true"))
        try:
            ai = int(float(self.model.analysis_set_value(
                "adaptive_wall", "0")))
        except ValueError:
            ai = 0
        ai = max(0, min(ai, len(self.adaptive) - 1))
        self.adaptive[ai].setChecked(True)
        el = self.model.analysis_set_value("eddy_visc_limiter", "0").strip()
        self.eddy_lim.setChecked(el.lower() in ("1", "t", "true"))
        try:
            self.eddy_coeff.setValue(float(
                self.model.analysis_set_value("eddy_over_limit", "0")))
        except ValueError:
            pass
        ds = self.model.analysis_set_value(
            "density_stratification", "0").strip()
        self.dens_strat.setChecked(ds.lower() in ("1", "t", "true"))
        method = self.model.analysis_set_value(
            "dens_strat_method", "Ushijima formula")
        mi = self.dens_method.findText(method)
        if mi >= 0:
            self.dens_method.setCurrentIndex(mi)
        try:
            self.dens_rn.setValue(float(
                self.model.analysis_set_value("dens_strat_rn", "0")))
            self.dens_rd.setValue(float(
                self.model.analysis_set_value("dens_strat_rd", "0")))
        except ValueError:
            pass

    def apply(self) -> None:
        comps = "".join(a for a in "xyz" if self.vel[a].isChecked()) or "x"
        self.model.set_analysis_set_value("velocity_components", comps)
        self.model.set_analysis_set_value(
            "wall_correction",
            "1" if self.wall_corr.isChecked() else "0")
        ai = next((i for i, r in enumerate(self.adaptive) if r.isChecked()),
                  0)
        self.model.set_analysis_set_value("adaptive_wall", str(ai))
        # keep legacy wall_type in sync (STpre uses related WLTY/WALL_MODEL)
        if self.wall_corr.isChecked():
            self.model.set_analysis_set_value("wall_type", "1")
        self.model.set_analysis_set_value(
            "eddy_visc_limiter",
            "1" if self.eddy_lim.isChecked() else "0")
        self.model.set_analysis_set_value(
            "eddy_over_limit", f"{self.eddy_coeff.value():g}")
        self.model.set_analysis_set_value(
            "density_stratification",
            "1" if self.dens_strat.isChecked() else "0")
        self.model.set_analysis_set_value(
            "dens_strat_method", self.dens_method.currentText())
        self.model.set_analysis_set_value(
            "dens_strat_rn", f"{self.dens_rn.value():g}")
        self.model.set_analysis_set_value(
            "dens_strat_rd", f"{self.dens_rd.value():g}")

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


class _CwHeatPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Heat."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Sets parameters for heat.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        ug = QGroupBox("Unit", page)
        ugl = QVBoxLayout(ug)
        self.temp_unit = QComboBox(ug)
        self.temp_unit.addItems(["C", "K", "F", "R"])
        _pair_row(ugl, "Unit of temperature", self.temp_unit)
        note_u = QLabel(
            "Note) The unit selected here is used for temperature input "
            "in STpre. Changing the unit does not convert existing "
            "temperature values.", ug)
        note_u.setWordWrap(True)
        note_u.setStyleSheet("color: #555;")
        ugl.addWidget(note_u)
        lay.addWidget(ug)

        sg = QGroupBox("Shear dissipation", page)
        sgl = QVBoxLayout(sg)
        self.shear = QCheckBox("Shear dissipation", sg)
        sgl.addWidget(self.shear)
        lay.addWidget(sg)
        lay.addStretch(1)

        tabs.addTab(page, "Heat")
        root.addWidget(tabs, 1)
        self._load()

    def _load(self) -> None:
        unit = self.model.units.get("temperature", "C")
        idx = self.temp_unit.findText(unit)
        self.temp_unit.setCurrentIndex(idx if idx >= 0 else 0)
        sh = self.model.analysis_set_value(
            "shear_dissipation", "0").strip().lower()
        self.shear.setChecked(sh in ("1", "t", "true"))

    def apply(self) -> None:
        import xml.etree.ElementTree as ET
        from cabxml import _first, set_text
        u = _first(self.model.root, "unit")
        if u is None:
            u = ET.SubElement(self.model.root, "unit")
            u.tail = "\n   "
        el = _first(u, "temperature")
        if el is None:
            el = ET.SubElement(u, "temperature")
            el.tail = "\n      "
        set_text(el, self.temp_unit.currentText())
        self.model.set_analysis_set_value(
            "shear_dissipation",
            "1" if self.shear.isChecked() else "0")


class _CwInitialPage(QWidget if _HAS_GUI_DEPS else object):
    """STpre Condition Wizard → Initial Condition."""

    _SOLID_ROW = "__solid_undefined__"

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        # Kept for apply() / tests; edited via dialogs and solid-row UI.
        self.fluid_temp = QDoubleSpinBox(self)
        self.fluid_temp.setRange(-273.15, 1.0e6)
        self.fluid_temp.setDecimals(2)
        self.fluid_temp.hide()
        self.solid_temp = QDoubleSpinBox(self)
        self.solid_temp.setRange(-273.15, 1.0e6)
        self.solid_temp.setDecimals(2)
        self.solid_temp.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Sets the initial conditions.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", page))
        self.display = QComboBox(page)
        self.display.addItems([
            "All regions", "Domain", "Parts", "Condition regions"])
        drow.addWidget(self.display, 1)
        drow.addStretch(1)
        lay.addLayout(drow)

        body = QHBoxLayout()
        self.table = QTableWidget(0, 4, page)
        self.table.setHorizontalHeaderLabels(
            ["Region name", "*", "Region type", "Condition name"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_dbl)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        body.addWidget(self.table, 1)

        # STpre: New group (Initial value / LES field) + Existing below.
        col = action_column(page)
        right = QVBoxLayout(col)
        right.setContentsMargins(0, 0, 0, 0)
        new_box = QGroupBox("New", col)
        new_lay = QVBoxLayout(new_box)
        new_lay.setSpacing(3)
        new_lay.setContentsMargins(6, 8, 6, 6)
        self.btn_init_val = icon_action_button(
            col, "Initial value", "initial_value", self._new_initial_value)
        self.btn_turb_field = icon_action_button(
            col, "Initial turbulence field", "turb_field",
            self._new_turb_field)
        new_lay.addWidget(self.btn_init_val)
        new_lay.addWidget(self.btn_turb_field)
        right.addWidget(new_box)
        self.btn_existing = icon_action_button(
            col, "Existing conditions", "existing", self._assign_existing)
        right.addWidget(self.btn_existing)
        right.addStretch(1)
        body.addWidget(col, 0)
        lay.addLayout(body, 1)

        brow = QHBoxLayout()
        self.btn_edit = QPushButton("Edit...", page)
        self.btn_cancel_cond = QPushButton("Cancel", page)
        self.btn_select = QPushButton("Select", page)
        self.btn_select.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_cancel_cond.clicked.connect(self._cancel_selected)
        brow.addWidget(self.btn_edit)
        brow.addWidget(self.btn_cancel_cond)
        brow.addStretch(1)
        brow.addWidget(self.btn_select)
        lay.addLayout(brow)
        tip = QLabel("Select from list > New", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)

        tabs.addTab(page, "Initial Condition")
        root.addWidget(tabs, 1)
        self.display.currentIndexChanged.connect(self.refresh)
        self._load_defaults()
        self.refresh()

    def _load_defaults(self) -> None:
        try:
            self.fluid_temp.setValue(float(self.model.project_value(
                "ambient_temperature", "20")))
        except ValueError:
            self.fluid_temp.setValue(20.0)
        try:
            self.solid_temp.setValue(float(self.model.project_value(
                "solid_init_temperature", "20")))
        except ValueError:
            self.solid_temp.setValue(20.0)

    def _unit_c(self) -> str:
        return self.model.units.get("temperature", "C") or "C"

    def _initial_bindings(self) -> list[tuple[str, str, str]]:
        """Return (region, region_type, condition_name) for initial values."""
        from cabxml import _first
        name_to_type: dict[str, str] = {}
        for v in self.model.values():
            if v.attrib.get("type") != "initial":
                continue
            nm = ""
            for ch in v:
                if ch.tag == "name":
                    nm = (ch.text or "").strip()
            if nm:
                name_to_type[nm] = "initial"
        rows: list[tuple[str, str, str]] = []
        for c in self.model.conditions():
            val = _first(c, "value")
            vname = (val.text or "").strip() if val is not None else ""
            if vname not in name_to_type:
                continue
            region = ""
            rtype = ""
            # STpre labels: Domain / Solid / Condition region
            for kind, label in (("analysis", "Domain"),
                                ("parts", "Solid"),
                                ("region", "Condition region")):
                t = _first(c, kind)
                if t is not None and (t.text or "").strip():
                    region = (t.text or "").strip()
                    rtype = label
                    break
            if region:
                rows.append((region, rtype, vname))
        return rows

    def refresh(self) -> None:
        filt = self.display.currentText()
        rows = self._initial_bindings()
        if filt == "Domain":
            rows = [r for r in rows if r[1] == "Domain"]
        elif filt == "Parts":
            rows = [r for r in rows if r[1] == "Solid"]
        elif filt == "Condition regions":
            rows = [r for r in rows if r[1] == "Condition region"]
        # Always append the undefined-solid placeholder (STpre list row)
        unit = self._unit_c()
        solid_disp = f"{self.solid_temp.value():g} {unit}"
        self.table.setRowCount(0)
        for region, rtype, cname in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(region))
            self.table.setItem(i, 1, QTableWidgetItem(""))
            self.table.setItem(i, 2, QTableWidgetItem(rtype))
            self.table.setItem(i, 3, QTableWidgetItem(cname))
        i = self.table.rowCount()
        self.table.insertRow(i)
        self.table.setItem(
            i, 0, QTableWidgetItem(
                "Undefined:Initial temperature of solid parts"))
        self.table.setItem(i, 1, QTableWidgetItem(""))
        self.table.setItem(i, 2, QTableWidgetItem(""))
        self.table.setItem(i, 3, QTableWidgetItem(solid_disp))
        it = self.table.item(i, 0)
        if it is not None:
            it.setData(Qt.UserRole, self._SOLID_ROW)
        # LES-only control
        turb_model = self.model.analysis_set_value("turbulence_model", "0")
        try:
            is_les = int(float(turb_model)) >= 6  # LES is last in Analysis Types
        except ValueError:
            is_les = "les" in turb_model.lower()
        self.btn_turb_field.setEnabled(is_les)
        self._sync_buttons()

    def _selected_row(self) -> int:
        sel = self.table.selectionModel().selectedRows()
        return sel[0].row() if sel else -1

    def _is_solid_row(self, row: int) -> bool:
        if row < 0:
            return False
        it = self.table.item(row, 0)
        return it is not None and it.data(Qt.UserRole) == self._SOLID_ROW

    def _sync_buttons(self) -> None:
        row = self._selected_row()
        ok = row >= 0
        self.btn_edit.setEnabled(ok)
        # Cancel removes a binding; solid default row is edited, not cancelled
        self.btn_cancel_cond.setEnabled(ok and not self._is_solid_row(row))

    def _domain_name(self) -> str:
        return self.model.domain_name() or "Domain"

    def _new_initial_value(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition (Initial Value)")
        form = QVBoxLayout(dlg)
        name_ed = QLineEdit("FluidTemp1", dlg)
        _pair_row(form, "Condition name", name_ed)
        var = QComboBox(dlg)
        var.addItems([
            "TEMP", "VELX", "VELY", "VELZ", "PRES", "K", "EPS"])
        _pair_row(form, "Variable name", var)
        val = QDoubleSpinBox(dlg)
        val.setDecimals(6)
        val.setRange(-1.0e10, 1.0e10)
        val.setValue(self.fluid_temp.value())
        unit = self._unit_c()
        _pair_row(form, "Initial value", val, unit if var.currentText() == "TEMP"
                  else "")
        tgt = QComboBox(dlg)
        tgt.addItem(self._domain_name())
        _pair_row(form, "Target region", tgt)
        buttons = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        form.addLayout(buttons)
        if not dlg.exec_():
            return
        cname = name_ed.text().strip()
        if not cname:
            return
        vtype = var.currentText()
        unit_attr = unit if vtype == "TEMP" else None
        self.model.upsert_value("initial", cname, [
            ("type", vtype, None),
            ("param", f"{val.value():g}", unit_attr),
        ])
        self.model.bind_condition("analysis", tgt.currentText(), cname)
        if vtype == "TEMP":
            self.fluid_temp.setValue(val.value())
        self._log(f"Initial Condition: created '{cname}'.")
        self.refresh()

    def _assign_existing(self) -> None:
        names = []
        for v in self.model.values():
            if v.attrib.get("type") != "initial":
                continue
            for ch in v:
                if ch.tag == "name" and ch.text:
                    names.append(ch.text.strip())
        if not names:
            QMessageBox.information(
                self, "Existing conditions",
                "No initial-value conditions exist yet.\n"
                "Create one with [Initial value].")
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "List of Existing Conditions",
            "Condition name:", names, 0, False)
        if not ok or not name:
            return
        self.model.bind_condition("analysis", self._domain_name(), name)
        self._log(f"Initial Condition: assigned existing '{name}'.")
        self.refresh()

    def _new_turb_field(self) -> None:
        amp, ok = QtWidgets.QInputDialog.getDouble(
            self, "Condition (Initial Turbulence Field)",
            "Amplitude of velocity fluctuations:", 0.0, 0.0, 1.0e6, 4)
        if not ok:
            return
        name = "LesInit1"
        self.model.upsert_value("initial", name, [
            ("type", "LES_INIT", None),
            ("param", f"{amp:g}", None),
        ])
        self.model.bind_condition("analysis", self._domain_name(), name)
        self._log(f"Initial Condition: LES field '{name}' amplitude={amp:g}.")
        self.refresh()

    def _edit_solid(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Details (Initial Temperature of Solid)")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Sets the default initial temperature to a solid part "
            "which is undefined.", dlg))
        sp = QDoubleSpinBox(dlg)
        sp.setDecimals(2)
        sp.setRange(-273.15, 1.0e6)
        sp.setValue(self.solid_temp.value())
        _pair_row(lay, "Initial temperature", sp, self._unit_c())
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if dlg.exec_():
            self.solid_temp.setValue(sp.value())
            self.refresh()

    def _edit_selected(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        if self._is_solid_row(row):
            self._edit_solid()
            return
        cname = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
        if not cname:
            return
        val = self.model.find_value(cname)
        cur = self.fluid_temp.value()
        unit = self._unit_c()
        if val is not None:
            from cabxml import _first
            p = _first(val, "param")
            if p is not None and p.text:
                try:
                    cur = float(p.text.strip())
                except ValueError:
                    pass
                unit = p.attrib.get("unit", unit)
        new_val, ok = QtWidgets.QInputDialog.getDouble(
            self, "Edit Initial Value",
            f"{cname} [{unit}]:", cur, -1.0e10, 1.0e10, 6)
        if not ok:
            return
        self.model.upsert_value("initial", cname, [
            ("param", f"{new_val:g}", unit),
        ])
        # keep fluid_temp in sync for TEMP conditions
        from cabxml import _first
        v = self.model.find_value(cname)
        typ = _first(v, "type") if v is not None else None
        if typ is not None and (typ.text or "").strip() == "TEMP":
            self.fluid_temp.setValue(new_val)
        self.refresh()

    def _cancel_selected(self) -> None:
        row = self._selected_row()
        if row < 0 or self._is_solid_row(row):
            return
        region = self.table.item(row, 0).text()
        cname = self.table.item(row, 3).text()
        from cabxml import _first
        for c in list(self.model.conditions()):
            v = _first(c, "value")
            if v is None or (v.text or "").strip() != cname:
                continue
            for kind in ("analysis", "parts", "region"):
                t = _first(c, kind)
                if t is not None and (t.text or "").strip() == region:
                    self.model.root.remove(c)
                    break
        self._log(f"Initial Condition: cancelled '{cname}' on {region}.")
        self.refresh()

    def _on_dbl(self, item) -> None:
        if item is None:
            return
        self.table.selectRow(item.row())
        self._edit_selected()

    def apply(self) -> None:
        self.model.set_project_value(
            "ambient_temperature", f"{self.fluid_temp.value():g}")
        self.model.set_project_value(
            "solid_init_temperature", f"{self.solid_temp.value():g}")

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


class _BoundaryPageBase(QWidget if _HAS_GUI_DEPS else object):
    """STpre Boundary Condition page chrome: table + New actions.

    Subclasses set ``page_title`` / ``blurb`` / New buttons.  A hidden
    ``QListWidget`` named ``region`` is kept for older tests that drive
    face selection through the list API.
    """

    page_title = "Boundary Condition"
    blurb = "Sets boundary conditions."
    value_type = ""  # flux | wall | heat_transfer
    show_star_col = False

    def __init__(self, model: StpreModel, value_type: str = ""):
        super().__init__()
        self.model = model
        if value_type:
            self.value_type = value_type
        self.model.ensure_domain_faces()
        self._faces = [n for n, _el in self.model.domain_faces()] or [
            "Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"]

        # Compatibility face list (hidden) — tests use .region / ._faces
        self.region = QListWidget(self)
        self.region.addItems(self._faces)
        self.region.hide()
        self.region.currentRowChanged.connect(lambda *_: self._sync_buttons())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.main_page = QWidget()
        lay = QVBoxLayout(self.main_page)
        lay.addWidget(QLabel(self.blurb, self.main_page))
        sep = QFrame(self.main_page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", self.main_page))
        self.display = QComboBox(self.main_page)
        self.display.addItems(["All regions", "DomainBoundary", "Parts"])
        drow.addWidget(self.display, 1)
        drow.addStretch(1)
        lay.addLayout(drow)

        body = QHBoxLayout()
        cols = (["Region name", "*", "Region type", "Condition name"]
                if self.show_star_col
                else ["Region name", "Region type", "Condition name"])
        self.table = QTableWidget(0, len(cols), self.main_page)
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_table_sel)
        self.table.itemDoubleClicked.connect(self._on_dbl)
        body.addWidget(self.table, 1)

        col = action_column(self.main_page)
        right = QVBoxLayout(col)
        right.setContentsMargins(0, 0, 0, 0)
        self.new_box = QGroupBox("New", col)
        self.new_lay = QVBoxLayout(self.new_box)
        self.new_lay.setSpacing(3)
        self.new_lay.setContentsMargins(6, 8, 6, 6)
        self._populate_new_actions(self.new_lay)
        right.addWidget(self.new_box)
        # Existing conditions uses the same icon-button style as STpre.
        self.btn_existing = icon_action_button(
            col, "Existing conditions", "existing",
            self._assign_existing)
        right.addWidget(self.btn_existing)
        right.addStretch(1)
        body.addWidget(col, 0)
        lay.addLayout(body, 1)

        brow = QHBoxLayout()
        self.btn_create_face = QPushButton("Create Face...", self.main_page)
        self.btn_edit_face = QPushButton("Edit Face...", self.main_page)
        self.btn_edit = QPushButton("Edit...", self.main_page)
        self.btn_cancel_cond = QPushButton("Cancel", self.main_page)
        self.btn_select = QPushButton("Select", self.main_page)
        self.btn_create_face.clicked.connect(self._create_face)
        self.btn_edit_face.clicked.connect(self._edit_face)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_cancel_cond.clicked.connect(self._cancel_selected)
        for b in (self.btn_create_face, self.btn_edit_face, self.btn_edit,
                  self.btn_cancel_cond):
            brow.addWidget(b)
        brow.addStretch(1)
        brow.addWidget(self.btn_select)
        lay.addLayout(brow)

        self._extra_options(lay)
        tip = QLabel("Select from list > New", self.main_page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)

        self.tabs.addTab(self.main_page, self.page_title)
        self._add_extra_tabs(self.tabs)
        root.addWidget(self.tabs, 1)

        self.display.currentIndexChanged.connect(self.refresh)
        self.refresh()
        self._sync_buttons()

    # -- subclass hooks ---------------------------------------------------

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        raise NotImplementedError

    def _extra_options(self, lay: QVBoxLayout) -> None:
        pass

    def _add_extra_tabs(self, tabs: QTabWidget) -> None:
        pass

    def _new(self) -> None:
        """Legacy entry used by Symmetrical tests."""
        raise NotImplementedError

    # -- table / selection ------------------------------------------------

    def _condition_for_face(self, face: str) -> str:
        from cabxml import _first
        for c in self.model.conditions():
            t = _first(c, "region")
            if t is None or (t.text or "").strip() != face:
                continue
            v = _first(c, "value")
            if v is None:
                continue
            vname = (v.text or "").strip()
            val = self.model.find_value(vname)
            if val is None:
                continue
            vtype = val.attrib.get("type", "")
            if self.value_type and vtype != self.value_type:
                continue
            return vname
        return ""

    def _extra_rows(self) -> list[tuple[str, str, str]]:
        """Optional (region, type, condition) rows below DomainBoundary."""
        return []

    def refresh(self) -> None:
        filt = self.display.currentText()
        self.table.setRowCount(0)
        for face in self._faces:
            if filt not in ("All regions", "DomainBoundary"):
                continue
            cname = self._condition_for_face(face)
            self._add_row(face, "DomainBoundary", cname)
        if filt in ("All regions", "Parts"):
            for region, rtype, cname in self._extra_rows():
                self._add_row(region, rtype, cname)
        # keep hidden list in sync
        self.region.blockSignals(True)
        self.region.clear()
        self.region.addItems(self._faces)
        self.region.blockSignals(False)
        if self._faces:
            self.region.setCurrentRow(0)
            self.table.selectRow(0)

    def _add_row(self, region: str, rtype: str, cname: str) -> None:
        i = self.table.rowCount()
        self.table.insertRow(i)
        if self.show_star_col:
            vals = [region, "", rtype, cname]
        else:
            vals = [region, rtype, cname]
        for c, text in enumerate(vals):
            self.table.setItem(i, c, QTableWidgetItem(text))

    def _on_table_sel(self) -> None:
        face = self._current_face()
        if face in self._faces:
            self.region.setCurrentRow(self._faces.index(face))
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        row = self._selected_row()
        ok = row >= 0
        face = self._current_face()
        is_domain = face in self._faces
        has_cond = bool(self._condition_for_face(face)) if is_domain else False
        self.btn_edit.setEnabled(ok and (has_cond or not is_domain))
        self.btn_cancel_cond.setEnabled(ok and has_cond)
        self.btn_edit_face.setEnabled(ok and is_domain)
        self.btn_select.setEnabled(False)

    def _selected_row(self) -> int:
        sel = self.table.selectionModel().selectedRows()
        return sel[0].row() if sel else -1

    def _current_face(self) -> str:
        row = self._selected_row()
        if row >= 0:
            col = 0
            it = self.table.item(row, col)
            if it is not None and it.text():
                return it.text()
        r = self.region.currentRow()
        return self._faces[r] if 0 <= r < len(self._faces) else "Xmin"

    def _show_current(self) -> None:
        """Compatibility hook — refresh table after a commit."""
        self.refresh()

    def _on_dbl(self, item) -> None:
        if item is None:
            return
        self.table.selectRow(item.row())
        face = self._current_face()
        if face in self._faces and self._condition_for_face(face):
            self._edit_selected()
        else:
            self._new()

    def _create_face(self) -> None:
        self._log("Create Face… (use Layout of Parts / region tools).")

    def _edit_face(self) -> None:
        self._log(f"Edit Face… {self._current_face()} "
                  "(informational — face geometry is in analysis_region).")

    def _edit_selected(self) -> None:
        self._new()

    def _cancel_selected(self) -> None:
        face = self._current_face()
        cname = self._condition_for_face(face)
        if not cname:
            return
        from cabxml import _first
        for c in list(self.model.conditions()):
            t = _first(c, "region")
            v = _first(c, "value")
            if t is None or v is None:
                continue
            if (t.text or "").strip() == face and \
                    (v.text or "").strip() == cname:
                self.model.root.remove(c)
                break
        self._log(f"{self.page_title}: cancelled '{cname}' on {face}.")
        self.refresh()

    def _assign_existing(self) -> None:
        names = []
        for v in self.model.values():
            if v.attrib.get("type") != self.value_type:
                continue
            for ch in v:
                if ch.tag == "name" and ch.text:
                    names.append(ch.text.strip())
        if not names:
            QMessageBox.information(
                self, "Existing conditions",
                f"No {self.value_type or 'boundary'} conditions exist yet.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "List of Existing Conditions",
            "Condition name:", names, 0, False)
        if not ok or not name:
            return
        self.model.bind_condition("region", self._current_face(), name)
        self.refresh()

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

    def apply(self) -> None:
        pass


class _CwFlowBoundaryPage(_BoundaryPageBase):
    page_title = "Flow Boundary Condition"
    blurb = "Sets the flow boundary conditions."
    value_type = "flux"

    def __init__(self, model: StpreModel):
        super().__init__(model, "flux")

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        for label, kind, slot in (
                ("Opening", "opening", self._new_opening),
                ("Total temperature, total pressure", "total_pres",
                 self._new_total_pres),
                ("Pressure loss", "pressure_loss", self._new_pressure_loss),
                ("Fan", "fan", self._new_fan),
                ("Power law", "power_law", self._new_power_law)):
            lay.addWidget(icon_action_button(
                self.new_box, label, kind, slot))

    def _extra_options(self, lay: QVBoxLayout) -> None:
        self.show_wall = QCheckBox("Show wall conditions", self.main_page)
        lay.addWidget(self.show_wall)

    def _new(self) -> None:
        self._new_opening()

    def _build_opening_widgets(self) -> QDialog:
        """Build the [Condition (Opening)] dialog widgets (test-friendly:
        no exec_)."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition (Opening) on {self._current_face()}")
        lay = QVBoxLayout(dlg)
        self._cname = QLineEdit(dlg)
        _row(lay, "Condition name", self._cname)
        self._ctype = QComboBox(dlg)
        self._ctype.addItems(["Fixed velocity", "Fixed static pressure",
                              "Natural outflow"])
        _row(lay, "Condition type", self._ctype)
        self._vel = {a: QDoubleSpinBox() for a in "xyz"}
        for a in "xyz":
            self._vel[a].setRange(-1.0e6, 1.0e6)
            self._vel[a].setDecimals(3)
            _row(lay, f"Velocity component {a.upper()} (m/s)", self._vel[a])
        self._temp = QDoubleSpinBox()
        self._temp.setRange(-273.15, 1.0e6)
        self._temp.setDecimals(2)
        _row(lay, "Inflow temperature (C)", self._temp)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        return dlg

    def _new_opening(self) -> None:
        dlg = self._build_opening_widgets()
        if dlg.exec_():
            self._commit(self._current_face())

    def _commit(self, face: str) -> None:
        name = self._cname.text().strip() or f"Opening_{face}"
        ctype = self._ctype.currentIndex()
        kind = ("fixed_vel" if ctype == 0
                else "total_pres" if ctype == 1 else "out")
        children = [("kind", kind, None)]
        if kind == "fixed_vel":
            children.append((
                "velocity", ",".join(f"{self._vel[a].value():g}"
                                     for a in "xyz"), None))
            children.append(("temperature",
                             f"{self._temp.value():g}", "C"))
        elif kind == "total_pres":
            children.append(("pressure", "0", "Pa"))
            children.append(("temperature",
                             f"{self._temp.value():g}", "C"))
        children += [("turbulence_type", "none", None),
                     ("panel_option", "none", None)]
        self.model.upsert_value("flux", name, children)
        self.model.bind_condition("region", face, name)
        self._show_current()
        self._log(f"Flow Boundary: {face} <- '{name}' ({kind})")

    def _new_total_pres(self) -> None:
        face = self._current_face()
        name = f"TotalPT_{face}"
        self.model.upsert_value("flux", name, [
            ("kind", "total_pres", None),
            ("pressure", "0", "Pa"),
            ("temperature", "20", "C"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Flow Boundary: {face} <- '{name}' (total_pres)")
        self.refresh()

    def _new_pressure_loss(self) -> None:
        face = self._current_face()
        name = f"PLoss_{face}"
        self.model.upsert_value("flux", name, [
            ("kind", "pressure_loss", None),
            ("pressure", "0", "Pa"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Flow Boundary: {face} <- '{name}' (pressure_loss)")
        self.refresh()

    def _new_fan(self) -> None:
        face = self._current_face()
        name = f"Fan_{face}"
        self.model.upsert_value("flux", name, [
            ("kind", "fan", None),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Flow Boundary: {face} <- '{name}' (fan)")
        self.refresh()

    def _new_power_law(self) -> None:
        face = self._current_face()
        name = f"PowerLaw_{face}"
        self.model.upsert_value("flux", name, [
            ("kind", "power_law", None),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Flow Boundary: {face} <- '{name}' (power_law)")
        self.refresh()


class _CwWallBoundaryPage(_BoundaryPageBase):
    page_title = "Wall Boundary Condition"
    blurb = "Sets the wall boundary conditions."
    value_type = "wall"

    def __init__(self, model: StpreModel):
        super().__init__(model, "wall")

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        for label, kind, icon in (
                ("Freeslip", "free_slip", "freeslip"),
                ("Noslip", "no_slip", "noslip"),
                ("Rough", "rough", "rough"),
                ("Power-law", "power_law", "power_law_wall")):
            lay.addWidget(icon_action_button(
                self.new_box, label, icon,
                lambda _=False, k=kind, lab=label: self._new_wall(k, lab)))

    def _extra_rows(self) -> list[tuple[str, str, str]]:
        return [("Undefined(Stress:...)", "Undefined region", "")]

    def _new(self) -> None:
        self._new_wall("free_slip", "Freeslip")

    def _new_wall(self, kind: str, label: str) -> None:
        face = self._current_face()
        if face not in self._faces:
            face = self._faces[0] if self._faces else "Xmin"
        name = f"Wall_{face}"
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition ({label}) on {face}")
        lay = QVBoxLayout(dlg)
        name_ed = QLineEdit(name, dlg)
        _row(lay, "Condition name", name_ed)
        b = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addStretch(1)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if not dlg.exec_():
            return
        cname = name_ed.text().strip() or name
        self.model.upsert_value("wall", cname, [
            ("kind", kind, None), ("option", "1", None)])
        self.model.bind_condition("region", face, cname)
        self._log(f"Wall Boundary: {face} <- '{cname}' ({kind})")
        self.refresh()


class _CwDiffusionBoundaryPage(_BoundaryPageBase):
    """Diffusion Boundary Condition (STpre SetDiffusionCondition shapes)."""
    page_title = 'Diffusion Boundary Condition'
    blurb = ('Sets the diffusion boundary conditions (mass transfer by '
             'diffusion / diffusion transfer coefficient).')
    value_type = 'diffusion'

    def __init__(self, model: StpreModel):
        super().__init__(model, 'diffusion')

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        for label, kind, slot in (
                ('Diffusion (concentration)', 'diffusion',
                 self._new_diffusion),
                ('Transfer coefficient', 'transfer',
                 self._new_transfer)):
            lay.addWidget(icon_action_button(
                self.new_box, label, kind, slot))

    def _new(self) -> None:
        self._new_diffusion()

    def _build_dialog(self, with_coeff: bool) -> QDialog:
        dlg = QDialog(self)
        title = ('Transfer' if with_coeff else 'Diffusion')
        dlg.setWindowTitle(f'Condition ({title}) on {self._current_face()}')
        lay = QVBoxLayout(dlg)
        self._cname = QLineEdit(dlg)
        _row(lay, 'Condition name', self._cname)
        self._no = QSpinBox(dlg)
        self._no.setRange(1, 100)
        _row(lay, 'Species number', self._no)
        self._conc = QDoubleSpinBox(dlg)
        self._conc.setRange(-1.0e12, 1.0e12)
        self._conc.setDecimals(6)
        _row(lay, 'Boundary concentration', self._conc)
        self._coeff = None
        if with_coeff:
            self._coeff = QDoubleSpinBox(dlg)
            self._coeff.setRange(0.0, 1.0e9)
            self._coeff.setDecimals(6)
            _row(lay, 'Diffusion transfer coefficient', self._coeff)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton('OK', dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton('Cancel', dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        return dlg

    def _new_diffusion(self) -> None:
        dlg = self._build_dialog(with_coeff=False)
        if not dlg.exec_():
            return
        face = self._current_face()
        name = self._cname.text().strip() or f'DiffBound_{face}'
        # probed: diffusion type -> kind boundary, diff_param1=-1,
        # diff_param2 = boundary concentration
        self.model.upsert_value('diffusion', name, [
            ('kind', 'boundary', None),
            ('no', str(self._no.value()), None),
            ('diff_param1', '-1', None),
            ('diff_param2', f'{self._conc.value():g}', None),
        ])
        self.model.bind_condition('region', face, name)
        self._log(f'Diffusion Boundary: {face} <- {name!r} '
                  f'(concentration {self._conc.value():g})')
        self.refresh()

    def _new_transfer(self) -> None:
        dlg = self._build_dialog(with_coeff=True)
        if not dlg.exec_():
            return
        face = self._current_face()
        name = self._cname.text().strip() or f'DiffTrans_{face}'
        # probed: transfer type -> kind boundary, diff_param1 = transfer
        # coefficient, diff_param2 = boundary concentration
        self.model.upsert_value('diffusion', name, [
            ('kind', 'boundary', None),
            ('no', str(self._no.value()), None),
            ('diff_param1', f'{self._coeff.value():g}', None),
            ('diff_param2', f'{self._conc.value():g}', None),
        ])
        self.model.bind_condition('region', face, name)
        self._log(f'Diffusion Boundary: {face} <- {name!r} '
                  f'(transfer {self._coeff.value():g})')
        self.refresh()


class _CwThermalBoundaryPage(_BoundaryPageBase):
    page_title = "Thermal Boundary Condition"
    blurb = "Sets the thermal boundary conditions."
    value_type = "heat_transfer"
    show_star_col = True

    def __init__(self, model: StpreModel):
        super().__init__(model, "heat_transfer")

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        self.btn_heat = icon_action_button(
            self.new_box, "Heat transfer", "heat_transfer",
            self._new_heat_transfer)
        self.btn_encl = icon_action_button(
            self.new_box, "Enclosure", "enclosure",
            self._new_enclosure)
        self.btn_rad = icon_action_button(
            self.new_box, "Radiation", "radiation",
            self._new_radiation)
        self.btn_solar = icon_action_button(
            self.new_box, "Solar radiation/Lamp", "solar_lamp",
            self._new_solar_lamp)
        for b in (self.btn_heat, self.btn_encl, self.btn_rad, self.btn_solar):
            lay.addWidget(b)

    def _extra_options(self, lay: QVBoxLayout) -> None:
        self.show_flux_wall = QCheckBox(
            "Show flux and wall boundaries", self.main_page)
        lay.addWidget(self.show_flux_wall)

    def _add_extra_tabs(self, tabs: QTabWidget) -> None:
        tabs.addTab(self._build_between_parts_page(),
                    "Thermal Boundary Condition (Between Parts)")
        tabs.addTab(self._build_thermal_option_page(),
                    "Option (Thermal Boundary)")

    def _build_between_parts_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(
            "Set the heat transfer conditions between parts.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        top = QHBoxLayout()
        # Part 1
        p1_box = QVBoxLayout()
        p1_box.addWidget(QLabel("List of part 1", page))
        self.bp_part1 = QTableWidget(0, 2, page)
        self.bp_part1.setHorizontalHeaderLabels(["Part name", "*"])
        self.bp_part1.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.bp_part1.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.bp_part1.setSelectionBehavior(QTableWidget.SelectRows)
        self.bp_part1.setSelectionMode(QTableWidget.SingleSelection)
        self.bp_part1.setEditTriggers(QTableWidget.NoEditTriggers)
        p1_box.addWidget(self.bp_part1, 1)
        btn_p1 = QPushButton("Select", page)
        btn_p1.clicked.connect(lambda: self._bp_select_hint("part 1"))
        p1_box.addWidget(btn_p1)
        top.addLayout(p1_box, 1)

        # Part 2
        p2_box = QVBoxLayout()
        p2_hdr = QHBoxLayout()
        p2_hdr.addWidget(QLabel("List of part 2", page))
        p2_hdr.addWidget(QLabel("(multiple selection)", page))
        p2_hdr.addStretch(1)
        p2_box.addLayout(p2_hdr)
        self.bp_part2 = QTableWidget(0, 2, page)
        self.bp_part2.setHorizontalHeaderLabels(["Part name", "*"])
        self.bp_part2.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.bp_part2.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.bp_part2.setSelectionBehavior(QTableWidget.SelectRows)
        self.bp_part2.setSelectionMode(QTableWidget.MultiSelection)
        self.bp_part2.setEditTriggers(QTableWidget.NoEditTriggers)
        p2_box.addWidget(self.bp_part2, 1)
        p2_row = QHBoxLayout()
        self.bp_show_obst = QCheckBox("Show obstacles", page)
        self.bp_show_obst.toggled.connect(self._bp_fill_part2)
        p2_row.addWidget(self.bp_show_obst)
        p2_row.addStretch(1)
        btn_p2 = QPushButton("Select", page)
        btn_p2.clicked.connect(lambda: self._bp_select_hint("part 2"))
        p2_row.addWidget(btn_p2)
        p2_box.addLayout(p2_row)
        top.addLayout(p2_box, 1)

        # New / Existing
        right = QVBoxLayout()
        new_box = QGroupBox("New", page)
        nl = QVBoxLayout(new_box)
        self.bp_btn_total = QPushButton("Total heat transfer", new_box)
        self.bp_btn_contact = QPushButton("Contact thermal resistance", new_box)
        self.bp_btn_total.clicked.connect(
            lambda: self._bp_new("total_heat_transfer"))
        self.bp_btn_contact.clicked.connect(
            lambda: self._bp_new("contact_thermal_resist"))
        nl.addWidget(self.bp_btn_total)
        nl.addWidget(self.bp_btn_contact)
        right.addWidget(new_box)
        self.bp_btn_existing = QPushButton("Existing conditions", page)
        self.bp_btn_existing.clicked.connect(self._bp_assign_existing)
        right.addWidget(self.bp_btn_existing)
        right.addStretch(1)
        top.addLayout(right)
        lay.addLayout(top, 2)

        # Region pairs
        lay.addWidget(QLabel("List of region pairs", page))
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Display type", page))
        self.bp_display = QComboBox(page)
        self.bp_display.addItems(["All regions", "Parts"])
        self.bp_display.currentIndexChanged.connect(self._bp_refresh_pairs)
        drow.addWidget(self.bp_display, 1)
        drow.addStretch(1)
        lay.addLayout(drow)

        body = QHBoxLayout()
        self.bp_pairs = QTableWidget(0, 5, page)
        self.bp_pairs.setHorizontalHeaderLabels(
            ["Region pair", "*", "Part1", "Part2", "Condition name"])
        self.bp_pairs.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.bp_pairs.setSelectionBehavior(QTableWidget.SelectRows)
        self.bp_pairs.setSelectionMode(QTableWidget.SingleSelection)
        self.bp_pairs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.bp_pairs.itemDoubleClicked.connect(
            lambda *_: self._bp_edit_selected())
        body.addWidget(self.bp_pairs, 1)
        side = QVBoxLayout()
        self.bp_btn_edit = QPushButton("Edit...", page)
        self.bp_btn_cancel = QPushButton("Cancel", page)
        self.bp_btn_edit.clicked.connect(self._bp_edit_selected)
        self.bp_btn_cancel.clicked.connect(self._bp_cancel_selected)
        side.addWidget(self.bp_btn_edit)
        side.addWidget(self.bp_btn_cancel)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 2)

        tip = QLabel("Select from list > New", page)
        tip.setStyleSheet("color: #555;")
        lay.addWidget(tip)

        self.bp_part1.itemSelectionChanged.connect(self._bp_on_part1_changed)
        self._bp_fill_parts()
        self._bp_refresh_pairs()
        return page

    def _build_thermal_option_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(
            "Sets the options for the thermal boundary.", page))
        sep = QFrame(page)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        panel = QGroupBox("Between fluids blocked by a panel", page)
        pl = QVBoxLayout(panel)
        self.opt_panel_ht = QRadioButton("Heat transfer", panel)
        self.opt_panel_ad = QRadioButton("Adiabatic", panel)
        aent = self.model.analysis_set_value("aent_panel_option", "0")
        if aent.strip() in ("1", "adiabatic"):
            self.opt_panel_ad.setChecked(True)
        else:
            self.opt_panel_ht.setChecked(True)
        pl.addWidget(self.opt_panel_ht)
        pl.addWidget(self.opt_panel_ad)
        note = QLabel(
            "Note) Heat conduction panel, condition region face, and "
            "particle generation region face are excluded.", panel)
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        pl.addWidget(note)
        lay.addWidget(panel)

        area = QGroupBox("Part faces with area heat source", page)
        al = QVBoxLayout(area)
        self.opt_ahso_not = QRadioButton(
            "Not register to undefined region", area)
        self.opt_ahso_yes = QRadioButton(
            "Register to undefined region", area)
        ahso = self.model.analysis_set_value("ahso_area_option", "0,1")
        # Default template "0,1" = not register; leading 1 = register.
        if ahso.strip().startswith("1"):
            self.opt_ahso_yes.setChecked(True)
        else:
            self.opt_ahso_not.setChecked(True)
        al.addWidget(self.opt_ahso_not)
        al.addWidget(self.opt_ahso_yes)
        lay.addWidget(area)
        lay.addStretch(1)
        return page

    def _bp_select_hint(self, which: str) -> None:
        QMessageBox.information(
            self, "Select",
            f"Select {which} in the Draw window (phase-1: use the list).")

    def _bp_part_names(self, *, include_domain: bool,
                       include_obstacles: bool) -> list[str]:
        names: list[str] = []
        if include_domain:
            d = self.model.domain_name() or "Domain(cuboid)"
            names.append(d)
        for p in self.model.parts():
            if not p.name:
                continue
            attr = (p.attribute or "").lower()
            if (not include_obstacles) and "obstacle" in attr:
                continue
            names.append(p.name)
        return names

    def _bp_on_part1_changed(self) -> None:
        self._bp_fill_part2()

    def _bp_fill_table(self, table: QTableWidget, names: list[str],
                       keep: list[str]) -> None:
        table.blockSignals(True)
        table.setRowCount(0)
        keep_set = set(keep)
        for name in names:
            i = table.rowCount()
            table.insertRow(i)
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem(""))
            if name in keep_set:
                table.selectRow(i)
        if table.rowCount() and not table.selectionModel().hasSelection():
            table.selectRow(0)
        table.blockSignals(False)

    def _bp_fill_part2(self) -> None:
        if not hasattr(self, "bp_part2"):
            return
        p2_sel = self._bp_selected_names(self.bp_part2)
        show_obst = self.bp_show_obst.isChecked()
        p1 = self._bp_selected_names(self.bp_part1)
        p1_name = p1[0] if p1 else ""
        p2_names = [n for n in self._bp_part_names(
            include_domain=False, include_obstacles=show_obst)
            if n != p1_name]
        self._bp_fill_table(self.bp_part2, p2_names, p2_sel)

    def _bp_fill_parts(self, *_args) -> None:
        if not hasattr(self, "bp_part1"):
            return
        p1_sel = self._bp_selected_names(self.bp_part1)
        self._bp_fill_table(
            self.bp_part1,
            self._bp_part_names(include_domain=True, include_obstacles=True),
            p1_sel)
        self._bp_fill_part2()

    def _bp_selected_names(self, table: QTableWidget) -> list[str]:
        rows = sorted({idx.row() for idx in table.selectedIndexes()})
        out = []
        for r in rows:
            it = table.item(r, 0)
            if it is not None and it.text().strip():
                out.append(it.text().strip())
        return out

    def _bp_unique_name(self, prefix: str) -> str:
        existing = set()
        for v in self.model.values():
            from cabxml import _first
            n = _first(v, "name")
            if n is not None and n.text:
                existing.add(n.text.strip())
        for name, _a, _b in self.model.region_pairs():
            existing.add(name)
        i = 1
        while f"{prefix}{i}" in existing:
            i += 1
        return f"{prefix}{i}"

    def _bp_current_selection(self) -> Optional[tuple[str, list[str]]]:
        p1 = self._bp_selected_names(self.bp_part1)
        p2 = self._bp_selected_names(self.bp_part2)
        if not p1:
            QMessageBox.warning(
                self, "Between Parts", "Select a part from List of part 1.")
            return None
        if not p2:
            QMessageBox.warning(
                self, "Between Parts",
                "Select one or more parts from List of part 2.")
            return None
        return p1[0], p2

    def _bp_new(self, kind: str) -> None:
        sel = self._bp_current_selection()
        if sel is None:
            return
        part1, part2s = sel
        if kind == "total_heat_transfer":
            result = self._bp_dialog_total_heat()
        else:
            result = self._bp_dialog_contact()
        if result is None:
            return
        cname, children, vtype = result
        self.model.upsert_value(vtype, cname, children)
        for part2 in part2s:
            pair = self._bp_unique_name("PartPair")
            self.model.upsert_region_pair(pair, part1, part2)
            self.model.bind_condition("region", pair, cname)
            self._log(
                f"Thermal Between Parts: {pair} ({part1}/{part2}) "
                f"<- '{cname}' ({vtype})")
        self._bp_refresh_pairs()

    def _bp_dialog_total_heat(self, *, name: str = "",
                              kind: str = "transfer",
                              transfer: float = 0.0,
                              temperature: float = 0.0
                              ) -> Optional[tuple[str, list, str]]:
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition ( Total Heat Transfer Condition )")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Sets the total heat transfer conditions.", dlg))
        name_ed = QLineEdit(name or self._bp_unique_name("HeatTransfer"), dlg)
        _row(lay, "Condition name", name_ed)

        mode_ad = QRadioButton("Adiabatic", dlg)
        mode_ht = QRadioButton("Heat transfer", dlg)
        sub_cond = QRadioButton("Conduction", dlg)
        sub_log = QRadioButton(
            "Log-law heat transfer (conduction for laminar flow)", dlg)
        sub_spec = QRadioButton("Specify heat transfer coefficient", dlg)
        if kind == "adiabatic":
            mode_ad.setChecked(True)
        else:
            mode_ht.setChecked(True)
            if kind == "conductive":
                sub_cond.setChecked(True)
            elif kind == "log_law":
                sub_log.setChecked(True)
            else:
                sub_spec.setChecked(True)
        lay.addWidget(mode_ad)
        lay.addWidget(mode_ht)
        sub = QVBoxLayout()
        sub.setContentsMargins(24, 0, 0, 0)
        for w in (sub_cond, sub_log, sub_spec):
            sub.addWidget(w)
        lay.addLayout(sub)

        htc = QDoubleSpinBox(dlg)
        htc.setRange(0.0, 1.0e9)
        htc.setDecimals(4)
        htc.setValue(transfer)
        _row(lay, "Heat transfer coefficient (W/(m2.K))", htc)
        temp = QDoubleSpinBox(dlg)
        temp.setRange(-273.15, 1.0e6)
        temp.setDecimals(2)
        temp.setValue(temperature)
        _row(lay, "External temperature (C)", temp)

        def _sync():
            on = mode_ht.isChecked()
            for w in (sub_cond, sub_log, sub_spec, htc, temp):
                w.setEnabled(on)
            htc.setEnabled(on and sub_spec.isChecked())

        mode_ad.toggled.connect(lambda *_: _sync())
        mode_ht.toggled.connect(lambda *_: _sync())
        sub_spec.toggled.connect(lambda *_: _sync())
        _sync()

        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if not dlg.exec_():
            return None
        cname = name_ed.text().strip() or name_ed.placeholderText() or \
            "HeatTransfer1"
        if mode_ad.isChecked():
            children = [
                ("kind", "adiabatic", None),
                ("temperature", f"{temp.value():g}", "C"),
                ("use", "2", None),
            ]
        elif sub_cond.isChecked():
            children = [
                ("kind", "conductive", None),
                ("temperature", f"{temp.value():g}", "C"),
                ("use", "2", None),
            ]
        elif sub_log.isChecked():
            children = [
                ("kind", "log_law", None),
                ("temperature", f"{temp.value():g}", "C"),
                ("use", "2", None),
            ]
        else:
            children = [
                ("kind", "transfer", None),
                ("transfer", f"{htc.value():g}", None),
                ("temperature", f"{temp.value():g}", "C"),
                ("use", "2", None),
            ]
        return cname, children, "heat_transfer"

    def _bp_dialog_contact(self, *, name: str = "",
                           mode: str = "conductivity_distance",
                           htc: float = 0.0, resist: float = 0.0,
                           total_resist: float = 0.0,
                           conductivity: float = 0.66,
                           distance: float = 1.0
                           ) -> Optional[tuple[str, list, str]]:
        dlg = QDialog(self)
        dlg.setWindowTitle("Condition ( Contact Thermal Resistance )")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Sets contact thermal resistance conditions.", dlg))
        name_ed = QLineEdit(name or self._bp_unique_name("HeatTransfer"), dlg)
        _row(lay, "Condition name", name_ed)

        r_htc = QRadioButton("Contact heat transfer coefficient", dlg)
        r_res = QRadioButton(
            "Contact thermal resistance "
            "(Total contact thermal resistance * contact area)", dlg)
        r_tot = QRadioButton(
            "Total contact thermal resistance (only between parts)", dlg)
        r_cd = QRadioButton("Thermal conductivity and distance", dlg)
        {"htc": r_htc, "resist": r_res, "total_resist": r_tot,
         "conductivity_distance": r_cd}.get(mode, r_cd).setChecked(True)
        for w in (r_htc, r_res, r_tot, r_cd):
            lay.addWidget(w)

        sp_htc = QDoubleSpinBox(dlg)
        sp_htc.setRange(0.0, 1.0e9)
        sp_htc.setDecimals(4)
        sp_htc.setValue(htc)
        _row(lay, "Contact heat transfer coefficient (W/(m2.K))", sp_htc)
        sp_res = QDoubleSpinBox(dlg)
        sp_res.setRange(0.0, 1.0e9)
        sp_res.setDecimals(6)
        sp_res.setValue(resist)
        _row(lay, "Contact thermal resistance (m2.K/W)", sp_res)
        sp_tot = QDoubleSpinBox(dlg)
        sp_tot.setRange(0.0, 1.0e9)
        sp_tot.setDecimals(6)
        sp_tot.setValue(total_resist)
        _row(lay, "Total contact thermal resistance (K/W)", sp_tot)
        sp_k = QDoubleSpinBox(dlg)
        sp_k.setRange(0.0, 1.0e9)
        sp_k.setDecimals(4)
        sp_k.setValue(conductivity)
        _row(lay, "Thermal conductivity (W/(m.K))", sp_k)
        sp_d = QDoubleSpinBox(dlg)
        sp_d.setRange(0.0, 1.0e9)
        sp_d.setDecimals(4)
        sp_d.setValue(distance)
        _row(lay, "Distance (mm)", sp_d)

        def _sync():
            sp_htc.setEnabled(r_htc.isChecked())
            sp_res.setEnabled(r_res.isChecked())
            sp_tot.setEnabled(r_tot.isChecked())
            sp_k.setEnabled(r_cd.isChecked())
            sp_d.setEnabled(r_cd.isChecked())

        for w in (r_htc, r_res, r_tot, r_cd):
            w.toggled.connect(lambda *_: _sync())
        _sync()

        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if not dlg.exec_():
            return None
        cname = name_ed.text().strip() or "HeatTransfer1"
        if r_htc.isChecked():
            children = [
                ("kind", "htc", None),
                ("transfer", f"{sp_htc.value():g}", None),
            ]
        elif r_res.isChecked():
            children = [
                ("kind", "resist", None),
                ("resistance", f"{sp_res.value():g}", None),
            ]
        elif r_tot.isChecked():
            children = [
                ("kind", "total_resist", None),
                ("total_resistance", f"{sp_tot.value():g}", None),
            ]
        else:
            children = [
                ("kind", "conductivity_distance", None),
                ("conductivity", f"{sp_k.value():g}", None),
                ("distance", f"{sp_d.value():g}", "mm"),
            ]
        return cname, children, "contact_thermal_resist"

    def _bp_pair_condition(self, pair: str) -> str:
        from cabxml import _first
        for c in self.model.conditions():
            t = _first(c, "region")
            if t is None or (t.text or "").strip() != pair:
                continue
            v = _first(c, "value")
            if v is None:
                continue
            vname = (v.text or "").strip()
            val = self.model.find_value(vname)
            if val is None:
                continue
            vtype = val.attrib.get("type", "")
            if vtype in ("heat_transfer", "contact_thermal_resist"):
                return vname
        return ""

    def _bp_refresh_pairs(self) -> None:
        if not hasattr(self, "bp_pairs"):
            return
        filt = self.bp_display.currentText()
        self.bp_pairs.setRowCount(0)
        for name, p1, p2 in self.model.region_pairs():
            if filt == "Parts" and not (p1 or p2):
                continue
            cname = self._bp_pair_condition(name)
            i = self.bp_pairs.rowCount()
            self.bp_pairs.insertRow(i)
            for col, text in enumerate((name, "", p1, p2, cname)):
                self.bp_pairs.setItem(i, col, QTableWidgetItem(text))

    def _bp_selected_pair_row(self) -> Optional[tuple[str, str]]:
        rows = self.bp_pairs.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        pair_it = self.bp_pairs.item(r, 0)
        cond_it = self.bp_pairs.item(r, 4)
        if pair_it is None:
            return None
        return (pair_it.text().strip(),
                cond_it.text().strip() if cond_it else "")

    def _bp_edit_selected(self) -> None:
        from cabxml import _first
        sel = self._bp_selected_pair_row()
        if sel is None:
            QMessageBox.information(
                self, "Edit", "Select a region pair first.")
            return
        _pair, cname = sel
        if not cname:
            QMessageBox.information(
                self, "Edit", "No condition is set on this region pair.")
            return
        val = self.model.find_value(cname)
        if val is None:
            return
        vtype = val.attrib.get("type", "")

        def _t(tag: str, default: str = "") -> str:
            c = _first(val, tag)
            return (c.text or "").strip() if c is not None and c.text \
                else default

        if vtype == "contact_thermal_resist":
            result = self._bp_dialog_contact(
                name=cname, mode=_t("kind", "conductivity_distance"),
                htc=float(_t("transfer", "0") or 0),
                resist=float(_t("resistance", "0") or 0),
                total_resist=float(_t("total_resistance", "0") or 0),
                conductivity=float(_t("conductivity", "0.66") or 0.66),
                distance=float(_t("distance", "1") or 1),
            )
        else:
            result = self._bp_dialog_total_heat(
                name=cname, kind=_t("kind", "transfer"),
                transfer=float(_t("transfer", "0") or 0),
                temperature=float(_t("temperature", "0") or 0),
            )
        if result is None:
            return
        new_name, children, new_type = result
        self.model.upsert_value(new_type, new_name, children)
        if new_name != cname:
            self.model.bind_condition("region", _pair, new_name)
        self._log(f"Thermal Between Parts: edited '{new_name}' on {_pair}")
        self._bp_refresh_pairs()

    def _bp_cancel_selected(self) -> None:
        sel = self._bp_selected_pair_row()
        if sel is None:
            return
        pair, cname = sel
        if not cname:
            self.model.remove_region_pair(pair)
            self._bp_refresh_pairs()
            return
        self.model.remove_condition("region", pair)
        self.model.remove_region_pair(pair)
        self._log(f"Thermal Between Parts: cancelled '{cname}' on {pair}")
        self._bp_refresh_pairs()

    def _bp_assign_existing(self) -> None:
        from cabxml import _first
        sel = self._bp_current_selection()
        if sel is None:
            return
        part1, part2s = sel
        names = []
        for v in self.model.values():
            vtype = v.attrib.get("type", "")
            if vtype not in ("heat_transfer", "contact_thermal_resist"):
                continue
            n = _first(v, "name")
            if n is not None and n.text:
                names.append(n.text.strip())
        if not names:
            QMessageBox.information(
                self, "Existing conditions", "No thermal conditions exist.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "List of Existing Conditions",
            "Condition name:", names, 0, False)
        if not ok or not name:
            return
        for part2 in part2s:
            pair = self._bp_unique_name("PartPair")
            self.model.upsert_region_pair(pair, part1, part2)
            self.model.bind_condition("region", pair, name)
            self._log(
                f"Thermal Between Parts: {pair} ({part1}/{part2}) "
                f"<- existing '{name}'")
        self._bp_refresh_pairs()

    def _extra_rows(self) -> list[tuple[str, str, str]]:
        return [
            ("Undefined(Heat: Outer)", "Undefined region", "_heat_condition"),
            ("Undefined(Heat: Solid)", "Undefined region", "_heat_condition"),
            ("Undefined(Heat: Fluid)", "Undefined region", "_heat_condition"),
        ]

    def _new(self) -> None:
        self._new_heat_transfer()

    def _new_heat_transfer(self) -> None:
        face = self._current_face()
        if face not in self._faces:
            face = self._faces[0] if self._faces else "Xmin"
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition (Heat transfer) on {face}")
        lay = QVBoxLayout(dlg)
        name = QLineEdit(f"Heat_{face}", dlg)
        _row(lay, "Condition name", name)
        kind = QComboBox(dlg)
        kind.addItems(["Adiabatic", "Fixed temperature",
                       "Heat transfer coefficient"])
        _row(lay, "Thermal boundary", kind)
        temp = QDoubleSpinBox()
        temp.setRange(-273.15, 1.0e6)
        temp.setDecimals(2)
        _row(lay, "External temperature (C)", temp)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if not dlg.exec_():
            return
        k = ("adiabatic" if kind.currentIndex() == 0
             else "fixed" if kind.currentIndex() == 1 else "transfer")
        children = [("kind", k, None),
                    ("temperature", f"{temp.value():g}", "C")]
        if k == "transfer":
            children.append(("transfer", "10", None))
        children.append(("use", "2", None))
        cname = name.text().strip()
        self.model.upsert_value("heat_transfer", cname, children)
        self.model.bind_condition("region", face, cname)
        self._log(f"Thermal Boundary: {face} <- '{cname}' ({k})")
        self.refresh()

    def _new_enclosure(self) -> None:
        face = self._current_face()
        if face not in self._faces:
            face = self._faces[0] if self._faces else "Xmin"
        name = f"Enclosure_{face}"
        self.model.upsert_value("heat_transfer", name, [
            ("kind", "enclosure", None),
            ("temperature", "20", "C"),
            ("transfer", "1.3", None),
            ("use", "2", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Thermal Boundary: {face} <- '{name}' (enclosure)")
        self.refresh()

    def _new_radiation(self) -> None:
        face = self._current_face()
        if face not in self._faces:
            face = self._faces[0] if self._faces else "Xmin"
        name = f"Radiation_{face}"
        self.model.upsert_value("radiation_boundary", name, [
            ("kind", "normal", None),
            ("emissivity", "0.9", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Thermal Boundary: {face} <- '{name}' (radiation)")
        self.refresh()

    def _new_solar_lamp(self) -> None:
        face = self._current_face()
        if face not in self._faces:
            face = self._faces[0] if self._faces else "Xmin"
        name = f"Solar_{face}"
        self.model.upsert_value("heat_transfer", name, [
            ("kind", "solar", None),
            ("temperature", "20", "C"),
            ("use", "2", None),
        ])
        self.model.bind_condition("region", face, name)
        self._log(f"Thermal Boundary: {face} <- '{name}' (solar/lamp)")
        self.refresh()

    def apply(self) -> None:
        if hasattr(self, "opt_panel_ad"):
            self.model.set_analysis_set_value(
                "aent_panel_option",
                "1" if self.opt_panel_ad.isChecked() else "0")
        if hasattr(self, "opt_ahso_yes"):
            self.model.set_analysis_set_value(
                "ahso_area_option",
                "1,1" if self.opt_ahso_yes.isChecked() else "0,1")


class _CwSymmetricalPage(_BoundaryPageBase):
    page_title = "Symmetrical Boundary Condition"
    blurb = "Sets the symmetrical boundary conditions."
    value_type = "wall"

    def __init__(self, model: StpreModel):
        super().__init__(model, "wall")

    def _populate_new_actions(self, lay: QVBoxLayout) -> None:
        lay.addWidget(icon_action_button(
            self.new_box, "Symmetrical boundary", "symmetry", self._new))

    def _extra_options(self, lay: QVBoxLayout) -> None:
        self.show_flux_wall = QCheckBox(
            "Show flux and wall boundaries", self.main_page)
        lay.addWidget(self.show_flux_wall)

    def _new(self) -> None:
        # Prefer the compatibility region list (tests drive selection there).
        row = self.region.currentRow()
        if 0 <= row < self.region.count() and self.region.item(row):
            face = self.region.item(row).text()
        else:
            face = self._current_face()
        name = f"Symmetry_{face}"
        # symmetrical = free-slip wall + adiabatic + emissivity 0
        self.model.upsert_value("wall", name, [
            ("kind", "free_slip", None), ("option", "1", None)])
        self.model.bind_condition("region", face, name)
        heat = f"SymmetryHeat_{face}"
        self.model.upsert_value("heat_transfer", heat, [
            ("kind", "adiabatic", None),
            ("temperature", "20", "C"), ("use", "2", None)])
        self.model.bind_condition("region", face, heat)
        self._show_current()
        self._log(f"Symmetrical Boundary: {face} <- '{name}' + '{heat}' "
                  f"(free-slip + adiabatic, emissivity 0.0)")


class ConditionWizard(WizardBase):
    """[Wizard] - [Condition Setting]: STpre Condition Wizard.

    Navigation tree mirrors STpreCwiz; undefined steps stay grey
    (unchecked), defined steps turn checked as you Finish.  Extra pages
    (Source / Fixed / Analysis Control children / Output) live in
    ``cab_cwizard_pages``.
    """

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 parent=None):
        super().__init__("Condition Wizard", parent=parent, show_tree=True,
                         chrome="stpre_cw")
        self.model = model
        self.props = props
        self._snapshot = model.doc.serialize()

        from cab_cwizard_pages import (
            _CwAirconPage, _CwAnalysisControlHubPage,
            _CwBoilPage,
            _CwConditionListPage, _CwConfirmPage, _CwControlOptionPage,
            _CwCurrentPage, _CwDiffusionPage, _CwElectrostaticPage,
            _CwEvaporationPage,
            _CwFilePage, _CwFixedPage, _CwFusionPage,
            _CwHumidityPage, _CwLampPage, _CwMarangoniPage,
            _CwMovingBodyPage, _CwOutputFieldPage, _CwOutputHeatPathPage,
            _CwOutputLFilePage, _CwOutputSeriesPage, _CwParticlePage,
            _CwPcmPage, _CwPlantCanopyPage, _CwPorousPage,
            _CwReactionPage, _CwRadiationGroupingPage, _CwSolarPage,
            _CwSolverPage, _CwSourcePage, _CwStabilizationPage,
            _CwSteadyPage, _CwThermoregulationPage,
            _CwTopologyOptiPage, _CwVentilationPage,
        )

        self.p_analysis = _CwAnalysisTypesPage(model)
        self.p_basic = _CwBasicSettingsPage(model)
        self.p_fluid = _CwFluidRegionPage(model, props)
        self.p_flow = _CwFlowPage(model)
        self.p_heat = _CwHeatPage(model)
        self.p_humidity = _CwHumidityPage(model)
        self.p_solar = _CwSolarPage(model)
        self.p_porous = _CwPorousPage(model)
        self.p_diffusion = _CwDiffusionPage(model)
        self.p_particle = _CwParticlePage(model)
        self.p_jos = _CwThermoregulationPage(model)
        self.p_current = _CwCurrentPage(model)
        self.p_electrostatic = _CwElectrostaticPage(model)
        self.p_ventilation = _CwVentilationPage(model)
        self.p_reaction = _CwReactionPage(model)
        self.p_fusion = _CwFusionPage(model)
        self.p_lamp = _CwLampPage(model)
        self.p_pcm = _CwPcmPage(model)
        self.p_evaporation = _CwEvaporationPage(model)
        self.p_boil = _CwBoilPage(model)
        self.p_plant = _CwPlantCanopyPage(model)
        self.p_movebody = _CwMovingBodyPage(model)
        self.p_marangoni = _CwMarangoniPage(model)
        self.p_topopt = _CwTopologyOptiPage(model)
        self.p_aircon = _CwAirconPage(model)
        self.p_initial = _CwInitialPage(model)
        self.p_bc_flow = _CwFlowBoundaryPage(model)
        self.p_bc_wall = _CwWallBoundaryPage(model)
        self.p_bc_thermal = _CwThermalBoundaryPage(model)
        self.p_bc_symm = _CwSymmetricalPage(model)
        self.p_bc_radiation = _CwRadiationGroupingPage(model)
        self.p_bc_diffusion = _CwDiffusionBoundaryPage(model)
        self.p_source = _CwSourcePage(model)
        self.p_fixed = _CwFixedPage(model)
        self.p_control = _CwAnalysisControlHubPage(
            model, on_mode_changed=self._on_control_mode_changed)
        self.p_ctrl_steady = _CwSteadyPage(model)
        self.p_ctrl_solver = _CwSolverPage(model)
        self.p_ctrl_stab = _CwStabilizationPage(model)
        self.p_ctrl_option = _CwControlOptionPage(model)
        self.p_out_field = _CwOutputFieldPage(model)
        self.p_out_heatpath = _CwOutputHeatPathPage(model)
        self.p_out_series = _CwOutputSeriesPage(model)
        self.p_out_lfile = _CwOutputLFilePage(model)
        self.p_file = _CwFilePage(model)
        self.p_list = _CwConditionListPage(model)
        self.p_confirm = _CwConfirmPage()

        page_map = {
            "analysis": self.p_analysis, "basic": self.p_basic,
            "fluid": self.p_fluid, "flow": self.p_flow,
            "heat": self.p_heat,
            "humidity": self.p_humidity, "solar": self.p_solar,
            "porous": self.p_porous,
            "diffusion": self.p_diffusion, "particle": self.p_particle,
            "jos_model": self.p_jos, "current": self.p_current,
            "electrostatic": self.p_electrostatic,
            "ventilation": self.p_ventilation,
            "reaction": self.p_reaction, "fusion": self.p_fusion,
            "artificial_light": self.p_lamp, "pcm": self.p_pcm,
            "plant_canopy": self.p_plant,
            "moving_body": self.p_movebody,
            "marangoni": self.p_marangoni,
            "topology_opti": self.p_topopt,
            "aircon_model": self.p_aircon,
            "evaporation": self.p_evaporation,
            "boil": self.p_boil,
            "initial": self.p_initial,
            "bc": None,
            "bc_flow": self.p_bc_flow, "bc_wall": self.p_bc_wall,
            "bc_thermal": self.p_bc_thermal, "bc_symm": self.p_bc_symm,
            "bc_radiation": self.p_bc_radiation,
            "bc_diffusion": self.p_bc_diffusion,
            "source": self.p_source, "fixed": self.p_fixed,
            "control": self.p_control,
            "ctrl_steady": self.p_ctrl_steady,
            "ctrl_solver": self.p_ctrl_solver,
            "ctrl_stab": self.p_ctrl_stab,
            "ctrl_option": self.p_ctrl_option,
            "output": None,
            "out_field": self.p_out_field,
            "out_heatpath": self.p_out_heatpath,
            "out_series": self.p_out_series,
            "out_lfile": self.p_out_lfile,
            "file": self.p_file,
            "condlist": self.p_list, "confirm": self.p_confirm,
        }
        for key, title, parent_key in _CW_PAGES:
            self._add_page(key, title, page_map[key], parent_key)
        self._fit_nav_width()
        self._page_by_key = {k: w for k, w in page_map.items()
                             if w is not None}
        self._refresh_nav_status()
        self._sync_control_children(self.p_control.is_detailed())
        self._show_page(0)

    def _commit_current(self) -> None:
        """Leaving a step: write it and show the STpre orange check."""
        if not self._keys:
            return
        key = self._keys[self._current]
        page = self._page_by_key.get(key)
        if page is not None and hasattr(page, "apply"):
            page.apply()
        self._mark_defined(key, True)

    def _refresh_nav_status(self) -> None:
        """Check only steps that already have real condition values.

        Defaults (Analysis Types, ambient, file names, …) do **not** count —
        those get the orange check only after the user visits / clicks them.
        """
        def has_types(*types: str) -> bool:
            want = set(types)
            for v in self.model.values():
                if v.attrib.get("type") in want:
                    return True
            return False

        if has_types("flux"):
            self._mark_defined("bc_flow", True)
        if has_types("wall"):
            self._mark_defined("bc_wall", True)
        if has_types("heat_transfer", "radiation_boundary", "enclosure",
                     "solar_lamp"):
            self._mark_defined("bc_thermal", True)
        if has_types(
                "volumetric_force", "volumetric_pressure_loss", "heat_source",
                "source_term", "area_pressure_loss", "area_heat_source",
                "perforated_plate"):
            self._mark_defined("source", True)
        if has_types("fixed_temperature", "fixed_velocity", "fixed_pressure"):
            self._mark_defined("fixed", True)
        if has_types("initial"):
            self._mark_defined("initial", True)

    def _on_control_mode_changed(self, detailed: bool) -> None:
        self._sync_control_children(detailed)

    def _sync_control_children(self, detailed: bool) -> None:
        """Show Stabilization / Option only for Detailed setting (STpre)."""
        for key in ("ctrl_stab", "ctrl_option"):
            self._set_page_hidden(key, not detailed)
        if hasattr(self.p_ctrl_steady, "set_detail_mode"):
            self.p_ctrl_steady.set_detail_mode(detailed)
        if hasattr(self.p_ctrl_solver, "set_detail_mode"):
            self.p_ctrl_solver.set_detail_mode(detailed)
        # If the current step was just hidden, jump to Analysis Control.
        if self._keys and self._keys[self._current] in self._hidden_keys:
            self._show_page(self._index["control"])
        else:
            # Refresh Back/Next / step counter for the new visible set.
            self._show_page(self._current)

    def _show_page(self, idx: int) -> None:
        key = self._keys[idx] if 0 <= idx < len(self._keys) else ""
        if key == "control":
            self.p_control.refresh_bullets()
            # Analysis Types may have flipped steady/transient — retarget tabs.
            detailed = self.p_control.is_detailed()
            if hasattr(self.p_ctrl_steady, "set_detail_mode"):
                self.p_ctrl_steady.set_detail_mode(detailed)
        elif key == "ctrl_steady":
            if hasattr(self.p_ctrl_steady, "set_detail_mode"):
                self.p_ctrl_steady.set_detail_mode(
                    self.p_control.is_detailed())
        elif key == "condlist":
            self.p_list.refresh()
        elif key == "confirm":
            self.p_confirm.set_rows(self._summary_rows())
        elif key == "source":
            self.p_source.refresh()
        elif key == "fixed":
            self.p_fixed.refresh()
        elif key == "out_heatpath":
            # Refresh ambient from Basic/Initial before editing Heat Path.
            try:
                amb = float(self.model.project_value(
                    "ambient_temperature", "20") or 20)
                self.p_out_heatpath.hp_amb.setValue(amb)
            except ValueError:
                pass
        elif key.startswith("bc_") and hasattr(
                getattr(self, f"p_{key}", None), "refresh"):
            getattr(self, f"p_{key}").refresh()
        super()._show_page(idx)

    @staticmethod
    def _consider(on: bool) -> str:
        return "Consider" if on else "Do not consider"

    def _summary_rows(self) -> list[tuple[str, str]]:
        """Build STpre Setting Confirmation Items/Conditions rows."""
        rows: list[tuple[str, str]] = []
        a = self.p_analysis
        b = self.p_basic
        f = self.p_fluid
        flow = self.p_flow
        heat = self.p_heat
        init = self.p_initial

        def sec(title: str) -> None:
            rows.append((f"* {title}", ""))

        def item(name: str, value: str) -> None:
            rows.append((f"    {name}", value))

        # --- Analysis Types ---
        sec("Analysis Types")
        item("Incompressible/Compressible flow",
             "Compressible" if a.comp.isChecked() else "Incompressible")
        if a.flow_chk.isChecked():
            item("Flow field",
                 "Turbulent flow" if a.turbulent.isChecked()
                 else "Laminar flow")
            if a.turbulent.isChecked():
                item("Turbulence model", a.turb_model.currentText())
        item("Flow", self._consider(a.flow_chk.isChecked()))
        for label, key, _combo in (
                row for col in a._TYPE_COLS for row in col):
            cb = a.types.get(key)
            if cb is None:
                continue
            if key in a.type_combos and cb.isChecked():
                item(label, a.type_combos[key].currentText())
            else:
                item(label, self._consider(cb.isChecked()))
        item("Steady Analysis/Transient Analysis",
             "Transient analysis" if a.transient.isChecked()
             else "Steady-state analysis")
        item("Variable registration",
             "Possible" if a.var_reg.isChecked() else "Impossible")

        # --- Basic Settings ---
        sec("Basic Settings")
        item("Gravity", self._consider(b.gravity_chk.isChecked()))
        if b.gravity_chk.isChecked():
            vx, vy, vz = b._vec()
            unit = b.gravity_unit.currentText()
            item("Acceleration due to gravity",
                 f"( {vx:g}, {vy:g}, {vz:g} ) {b.gravity_acc.value():g} "
                 f"[{unit}]")
        item("Ambient temperature",
             f"{b.ambient.value():g} [C]")

        # --- Fluid Region ---
        sec("Fluid Region")
        for row in getattr(f, "_rows", []) or []:
            mat = row.get("material") or "-"
            region = row.get("region") or "-"
            item(f"Fluid number {row.get('no', '?')}",
                 f"{region} : {mat}")

        # --- Flow ---
        sec("Flow")
        comps = []
        for ax, lab in (("x", "X"), ("y", "Y"), ("z", "Z")):
            if flow.vel.get(ax) is not None and flow.vel[ax].isChecked():
                comps.append(f"{lab}-direction")
        item("Components of velocity",
             ", ".join(comps) if comps else "None")

        # --- Heat ---
        sec("Heat")
        item("Unit of temperature", heat.temp_unit.currentText())

        # --- Initial Condition ---
        sec("Initial Condition")
        item("Fluid temperature",
             f"{init.fluid_temp.value():g} [C]")

        # --- Boundary / Source / Fixed (from model values) ---
        by_type: dict[str, list[str]] = {}
        for v in self.model.values():
            vtype = v.attrib.get("type") or ""
            if not vtype:
                continue
            name = ""
            for ch in v:
                if ch.tag == "name":
                    name = (ch.text or "").strip()
                    break
            if name:
                by_type.setdefault(vtype, []).append(name)

        group_labels = {
            "flux": "Flow Boundary Condition",
            "wall": "Wall Boundary Condition",
            "heat_transfer": "Thermal Boundary Condition",
            "radiation_boundary": "Radiation Boundary Condition",
            "initial": "Initial Condition (values)",
            "volumetric_force": "Source Condition",
            "volumetric_pressure_loss": "Source Condition",
            "heat_source": "Source Condition",
            "source_term": "Source Condition",
            "area_pressure_loss": "Source Condition",
            "area_heat_source": "Source Condition",
            "perforated_plate": "Source Condition",
            "fixed_temperature": "Fixed Condition",
            "fixed_velocity": "Fixed Condition",
        }
        shown_groups: set[str] = set()
        for vtype, names in by_type.items():
            gname = group_labels.get(
                vtype, vtype.replace("_", " ").title())
            if gname not in shown_groups:
                sec(gname)
                shown_groups.add(gname)
            for name in names:
                item(name, vtype)

        # --- Analysis Control ---
        sec("Analysis Control")
        cyc = self.model.analysis_set_value("cycle", "")
        item("Cycles", cyc or "-")
        item("Calculation",
             self.model.analysis_set_value("calculation", "-") or "-")
        item("Heat balance",
             self.model.analysis_set_value("heat_balance", "-") or "-")

        # --- Output / File ---
        sec("Output Condition")
        item("Field file",
             "Output" if self.model.output_value("fld_file", "1")
             not in ("0", "F") else "Do not output")
        item("Heat path",
             "Output" if self.model.analysis_set_value("heat_path", "0")
             not in ("0", "F", "") else "Do not output")

        sec("File Specification")
        item("Project / solution name",
             self.model.project_name or "-")
        item("Field file (generic name)",
             self.model.file_value("fld", "-") or "-")
        item("Time-series file",
             self.model.file_value("tm", "-") or "-")

        return rows

    def _on_finish(self) -> None:
        # Analysis Types first (mode), then Steady-state last among
        # control pages so cycle numbers win over the Analysis Types
        # default of 1..100.
        apply_order = [
            ("analysis", self.p_analysis),
            ("basic", self.p_basic),
            ("fluid", self.p_fluid),
            ("flow", self.p_flow),
            ("heat", self.p_heat),
            ("initial", self.p_initial),
            ("bc_flow", self.p_bc_flow),
            ("bc_wall", self.p_bc_wall),
            ("bc_thermal", self.p_bc_thermal),
            ("bc_symm", self.p_bc_symm),
            ("source", self.p_source),
            ("fixed", self.p_fixed),
            ("control", self.p_control),
            ("ctrl_solver", self.p_ctrl_solver),
            ("ctrl_stab", self.p_ctrl_stab),
            ("ctrl_option", self.p_ctrl_option),
            ("ctrl_steady", self.p_ctrl_steady),
            ("out_field", self.p_out_field),
            ("out_heatpath", self.p_out_heatpath),
            ("out_series", self.p_out_series),
            ("out_lfile", self.p_out_lfile),
            ("file", self.p_file),
        ]
        for key, page in apply_order:
            if hasattr(page, "apply"):
                page.apply()
            self._mark_defined(key, True)
        for group in ("bc", "control", "output"):
            self._mark_defined(group, True)
        self.p_list.refresh()
        self._rebuild()
        self._log("Condition Wizard finished; conditions written to the "
                  "project (save the cab to persist).")

    def _on_cancel(self) -> None:
        import cabxml
        self.model.doc = cabxml.StpreDoc(self._snapshot)


def initial_wizard_dialog(model: StpreModel, props, cad_meshes, parent=None
                          ) -> InitialWizard:
    return InitialWizard(model, props, cad_meshes, parent)


def condition_wizard_dialog(model: StpreModel, props, parent=None
                            ) -> ConditionWizard:
    return ConditionWizard(model, props, parent)
