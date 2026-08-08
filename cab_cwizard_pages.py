"""STpre Condition Wizard pages (layout aligned with Pre_eng + STpreCwiz UI).

Extra steps beyond the original Basic-Exercise subset: Source / Fixed /
Analysis Control children / Output Condition.  Values are written through
``StpreModel`` ``analysis_set`` / ``value`` where fields exist; richer
solver options are retained in the UI for fidelity and logged on apply.
"""

from __future__ import annotations

from typing import Optional

from cabxml import StpreModel

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
        QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
        QRadioButton, QTabWidget, QTableWidget, QTableWidgetItem,
        QTextEdit, QVBoxLayout, QWidget,
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


class _CwSourcePage(QWidget if _HAS_GUI else object):
    """Source Condition — volumetric force / pressure loss (subset)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Source conditions such as volumetric force and pressure loss, "
            "perforated plate condition.", self))
        tabs = QTabWidget(self)
        # Volumetric force
        vf = QWidget()
        vl = QVBoxLayout(vf)
        self.vf_on = QCheckBox("Consider volumetric force", vf)
        vl.addWidget(self.vf_on)
        g = QGroupBox("Force components", vf)
        gl = QFormLayout(g)
        self.vf_x = QDoubleSpinBox(g); self.vf_x.setRange(-1e9, 1e9)
        self.vf_y = QDoubleSpinBox(g); self.vf_y.setRange(-1e9, 1e9)
        self.vf_z = QDoubleSpinBox(g); self.vf_z.setRange(-1e9, 1e9)
        gl.addRow("X [N/m3]", self.vf_x)
        gl.addRow("Y [N/m3]", self.vf_y)
        gl.addRow("Z [N/m3]", self.vf_z)
        vl.addWidget(g)
        vl.addStretch(1)
        tabs.addTab(vf, "Volumetric Force")
        # Pressure loss
        pl = QWidget()
        pll = QVBoxLayout(pl)
        self.pl_on = QCheckBox("Consider pressure loss", pl)
        pll.addWidget(self.pl_on)
        self.pl_coeff = QDoubleSpinBox(pl)
        self.pl_coeff.setDecimals(4)
        self.pl_coeff.setRange(0, 1e6)
        _pair(pll, "Loss coefficient", self.pl_coeff)
        pll.addStretch(1)
        tabs.addTab(pl, "Pressure Loss")
        lay.addWidget(tabs, 1)

    def apply(self) -> None:
        # Persist a lightweight flag in analysis_set for round-trip awareness
        self.model.set_analysis_set_value(
            "source_volumetric",
            "T" if self.vf_on.isChecked() else "F")
        self.model.set_analysis_set_value(
            "source_pressure_loss",
            "T" if self.pl_on.isChecked() else "F")


class _CwFixedPage(QWidget if _HAS_GUI else object):
    """Fixed Condition — temperature / velocity / cancel options."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)

        tpage = QWidget()
        tl = QVBoxLayout(tpage)
        self.fix_temp = QCheckBox("Set fixed temperature", tpage)
        tl.addWidget(self.fix_temp)
        self.fix_temp_val = QDoubleSpinBox(tpage)
        self.fix_temp_val.setRange(-273.15, 1e6)
        self.fix_temp_val.setValue(20.0)
        _pair(tl, "Temperature", self.fix_temp_val, "C")
        tl.addStretch(1)
        tabs.addTab(tpage, "Fixed Temperature Condition")

        vpage = QWidget()
        vl = QVBoxLayout(vpage)
        self.fix_vel = QCheckBox("Set fixed velocity", vpage)
        vl.addWidget(self.fix_vel)
        self.fix_u = QDoubleSpinBox(vpage); self.fix_u.setRange(-1e6, 1e6)
        self.fix_v = QDoubleSpinBox(vpage); self.fix_v.setRange(-1e6, 1e6)
        self.fix_w = QDoubleSpinBox(vpage); self.fix_w.setRange(-1e6, 1e6)
        _pair(vl, "U", self.fix_u, "m/s")
        _pair(vl, "V", self.fix_v, "m/s")
        _pair(vl, "W", self.fix_w, "m/s")
        vl.addStretch(1)
        tabs.addTab(vpage, "Fixed Velocity Condition")

        opage = QWidget()
        ol = QVBoxLayout(opage)
        ol.addWidget(_note("Cancels fixed condition in a specified range.",
                           opage))
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
        self.cancel_v_thr = QDoubleSpinBox(g2)
        _pair(g2l, "Type", self.cancel_v_type)
        _pair(g2l, "Threshold", self.cancel_v_thr, "m/s")
        ol.addWidget(g2)
        ol.addStretch(1)
        tabs.addTab(opage, "Option")

        lay.addWidget(tabs, 1)
        self.cancel_t.toggled.connect(self._sync)
        self.cancel_v.toggled.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        on_t = self.cancel_t.isChecked()
        self.cancel_t_type.setEnabled(on_t)
        self.cancel_t_thr.setEnabled(on_t)
        on_v = self.cancel_v.isChecked()
        self.cancel_v_type.setEnabled(on_v)
        self.cancel_v_thr.setEnabled(on_v)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "fixed_temperature",
            "T" if self.fix_temp.isChecked() else "F")
        if self.fix_temp.isChecked():
            self.model.set_analysis_set_value(
                "fixed_temperature_value",
                f"{self.fix_temp_val.value():g}")


class _CwAnalysisControlHubPage(QWidget if _HAS_GUI else object):
    """Analysis Control root — Simple / Detailed setting (STpre hub)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.addWidget(_note("Selects type of setting for analysis control.",
                           page))
        self.simple = QRadioButton("Simple setting", page)
        self.detailed = QRadioButton("Detailed setting", page)
        self.simple.setChecked(True)
        pl.addWidget(self.simple)
        pl.addWidget(QLabel(
            "  • Steady-state analysis (Start/End cycle, "
            "Steady-state convergence criteria)\n"
            "  • Solver parameters (heat balance)", page))
        pl.addWidget(self.detailed)
        pl.addWidget(QLabel(
            "  • Steady-state\n"
            "  • Solver parameters\n"
            "  • Stabilization\n"
            "  • Option (process interruption, unsupported analysis "
            "conditions, list of scripts)", page))
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
        self.param_mode.addItems(["Default (solver-defined)", "User"])
        self.param_mode.setEnabled(False)
        self.param_set.toggled.connect(self.param_mode.setEnabled)
        al.addWidget(self.param_set)
        al.addWidget(self.param_mode, 1)
        ol.addWidget(apar)
        pl.addWidget(opt)
        pl.addStretch(1)
        tabs.addTab(page, "Analysis Control")
        lay.addWidget(tabs, 1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "control_detail",
            "detailed" if self.detailed.isChecked() else "simple")


class _CwSteadyPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Steady-state Analysis (Cycle / Criteria / Stop)."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)

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
        ts = QGroupBox("Time step", cyc)
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

        # --- Stop divergence ---
        stop = QWidget()
        sl = QVBoxLayout(stop)
        sl.addWidget(_note(
            "Sets the conditions to stop the calculation for the "
            "prevention of solution divergence.", stop))
        self.stop_table = QTableWidget(7, 2, stop)
        self.stop_table.setHorizontalHeaderLabels(["Target", "Stop value"])
        self.stop_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        for i, name in enumerate((
                "X-component of velocity", "Y-component of velocity",
                "Z-component of velocity", "Pressure", "Temperature",
                "Turbulent kinetic energy", "Turbulent dissipation rate")):
            self.stop_table.setItem(i, 0, QTableWidgetItem(name))
            self.stop_table.setItem(i, 1, QTableWidgetItem("0"))
        sl.addWidget(self.stop_table, 1)
        sl.addWidget(_note(
            "Note) If the absolute value of a variable exceeds its "
            "specified stop value, the calculation is stopped.", stop))
        tabs.addTab(stop, "Stop (Prevention of Divergence)")

        # --- Stop specified point ---
        sp = QWidget()
        spl = QVBoxLayout(sp)
        spl.addWidget(_note(
            "Sets upper and lower limits for variables at specified "
            "points.", sp))
        self.limit_table = QTableWidget(0, 4, sp)
        self.limit_table.setHorizontalHeaderLabels(
            ["Region name", "*", "Location", "Variable"])
        self.limit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        spl.addWidget(self.limit_table, 1)
        lim = QGroupBox("Upper and Lower limits for variables", sp)
        ll = QFormLayout(lim)
        self.lim_var = QComboBox(lim)
        self.lim_var.addItems([
            "Temperature", "Pressure", "X-velocity", "Y-velocity",
            "Z-velocity"])
        self.lim_lo_on = QCheckBox("Lower limit", lim)
        self.lim_lo = QDoubleSpinBox(lim)
        self.lim_hi_on = QCheckBox("Upper limit", lim)
        self.lim_hi = QDoubleSpinBox(lim)
        ll.addRow("Variable name", self.lim_var)
        row_lo = QHBoxLayout()
        row_lo.addWidget(self.lim_lo_on)
        row_lo.addWidget(self.lim_lo)
        row_lo.addWidget(QLabel("C"))
        ll.addRow(row_lo)
        row_hi = QHBoxLayout()
        row_hi.addWidget(self.lim_hi_on)
        row_hi.addWidget(self.lim_hi)
        row_hi.addWidget(QLabel("C"))
        ll.addRow(row_hi)
        spl.addWidget(lim)
        tabs.addTab(sp, "Stop (Specified Point)")

        lay.addWidget(tabs, 1)
        self._load()

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

    def apply(self) -> None:
        self.model.set_cycles(
            int(self.start_cycle.value()), int(self.last_cycle.value()),
            transient=self.model.analysis_set_value("calculation")
            == "transient")
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


class _CwSolverPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Solver Parameters."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)

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

        # Matrix / advection
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
        for i, name in enumerate((
                "X-component of velocity", "Y-component of velocity",
                "Z-component of velocity", "Pressure", "Temperature",
                "Turbulent kinetic energy", "Turbulent dissipation rate")):
            self.solver_table.setItem(i, 0, QTableWidgetItem(name))
            self.solver_table.setItem(i, 1, QTableWidgetItem("Default"))
            self.solver_table.setItem(i, 2, QTableWidgetItem(""))
            self.solver_table.setItem(
                i, 3, QTableWidgetItem("1st order upwind"))
        ml.addWidget(self.solver_table, 1)
        msg = QGroupBox("Matrix solver", mx)
        mgl = QFormLayout(msg)
        self.solver_type = QComboBox(msg)
        self.solver_type.addItems(["Default", "ICCG", "BiCGSTAB"])
        mgl.addRow("Solver type", self.solver_type)
        ml.addWidget(msg)
        adv = QGroupBox("Advection term", mx)
        al = QVBoxLayout(adv)
        self.adv1 = QRadioButton("1st order upwind", adv)
        self.adv2 = QRadioButton("QUICK (Incompressible)", adv)
        self.adv3 = QRadioButton("WENO", adv)
        self.adv1.setChecked(True)
        for r in (self.adv1, self.adv2, self.adv3):
            al.addWidget(r)
        ml.addWidget(adv)
        tabs.addTab(mx, "Matrix Solver/Advection Term")

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

        lay.addWidget(tabs, 1)

    def apply(self) -> None:
        # heat_balance in analysis_set is typically "F,F"
        flag = "T" if self.hbal_on.isChecked() else "F"
        self.model.set_analysis_set_value("heat_balance", f"{flag},{flag}")


class _CwStabilizationPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Stabilization."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)

        fp = QWidget()
        fl = QVBoxLayout(fp)
        fl.addWidget(_note(
            "Stabilizes the flow field computation by fixing the "
            "pressure at specified location(s).", fp))
        g = QGroupBox("Specific region", fp)
        gl = QVBoxLayout(g)
        self.p_table = QTableWidget(0, 4, g)
        self.p_table.setHorizontalHeaderLabels(
            ["Point name", "*", "Location", "Pressure"])
        self.p_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        gl.addWidget(self.p_table, 1)
        self.auto_p = QCheckBox(
            "Automatically fix pressure in a pressure indefinite region",
            fp)
        self.auto_p.setChecked(True)
        fl.addWidget(g)
        fl.addWidget(self.auto_p)
        self.p_mode1 = QRadioButton(
            "Solve a pressure correction equation in which fixed "
            "pressure is incorporated", fp)
        self.p_mode2 = QRadioButton(
            "Compute fixed pressure after a pressure correction "
            "equation is solved", fp)
        self.p_mode1.setChecked(True)
        fl.addWidget(self.p_mode1)
        fl.addWidget(self.p_mode2)
        fl.addStretch(1)
        tabs.addTab(fp, "Fixed Pressure")

        ur = QWidget()
        ul = QVBoxLayout(ur)
        ul.addWidget(_note(
            "Under-relaxation / Pseudo time step relaxation factors.", ur))
        self.ur_flow = QDoubleSpinBox(ur)
        self.ur_flow.setRange(0.01, 1.0)
        self.ur_flow.setSingleStep(0.05)
        self.ur_flow.setValue(0.7)
        self.ur_temp = QDoubleSpinBox(ur)
        self.ur_temp.setRange(0.01, 1.0)
        self.ur_temp.setValue(0.7)
        _pair(ul, "Flow under-relaxation", self.ur_flow)
        _pair(ul, "Temperature under-relaxation", self.ur_temp)
        ul.addStretch(1)
        tabs.addTab(ur, "Under-relaxation/Pseudo Time Step Relaxation")

        lay.addWidget(tabs, 1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "auto_fix_pressure",
            "T" if self.auto_p.isChecked() else "F")


class _CwControlOptionPage(QWidget if _HAS_GUI else object):
    """Analysis Control → Option."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)

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

        for title in ("Unsupported STpre Analysis Conditions",
                      "Script List", "Parallel Computing"):
            pg = QWidget()
            pgl = QVBoxLayout(pg)
            pgl.addWidget(_note(
                f"{title} (STpre Condition Wizard page — informational "
                "in cabdecoding).", pg))
            pgl.addStretch(1)
            tabs.addTab(pg, title)

        lay.addWidget(tabs, 1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "process_interrupt",
            "T" if self.proc.isChecked() else "F")


class _CwOutputFieldPage(QWidget if _HAS_GUI else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Specifies Field file (.f) output timing and variables.", self))
        self.cycle = QDoubleSpinBox(self)
        self.cycle.setDecimals(0)
        self.cycle.setRange(1, 1e9)
        self.cycle.setValue(10)
        _pair(lay, "Output cycle interval", self.cycle)
        self.vel = QCheckBox("Velocity", self); self.vel.setChecked(True)
        self.pres = QCheckBox("Pressure", self); self.pres.setChecked(True)
        self.temp = QCheckBox("Temperature", self); self.temp.setChecked(True)
        for c in (self.vel, self.pres, self.temp):
            lay.addWidget(c)
        lay.addStretch(1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "field_output_cycle", f"{int(self.cycle.value())}")


class _CwOutputSeriesPage(QWidget if _HAS_GUI else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "Time-series (monitor) output at specified points.", self))
        self.on = QCheckBox("Enable time-series output", self)
        lay.addWidget(self.on)
        self.interval = QDoubleSpinBox(self)
        self.interval.setDecimals(0)
        self.interval.setRange(1, 1e9)
        self.interval.setValue(1)
        _pair(lay, "Sampling interval [cycle]", self.interval)
        lay.addStretch(1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "timeseries_output",
            "T" if self.on.isChecked() else "F")


class _CwOutputLFilePage(QWidget if _HAS_GUI else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        lay.addWidget(_note(
            "L-file log output options.", self))
        self.residual = QCheckBox("Output residuals", self)
        self.residual.setChecked(True)
        self.hbal = QCheckBox("Output heat balance", self)
        lay.addWidget(self.residual)
        lay.addWidget(self.hbal)
        lay.addStretch(1)

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "lfile_residual",
            "T" if self.residual.isChecked() else "F")
