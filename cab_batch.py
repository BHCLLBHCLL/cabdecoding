# Batch execution orchestration (advanced tools, 2026-08-16).
#
# Sequential multi-project solver queue: each queued .cab is parsed into
# (StpreModel, PropertyModel), its S/XEMT files are exported into a per-case
# folder, and stsol runs case by case through the R6 SolverProcess monitor.
# Complements the Parametric Study case-matrix preview/CSV (parameter
# application per case is a documented future extension).
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
from cab_solver_proc import SolverProcess
from s_export import build_sdat
import xemt_export


def load_models(cab_path):
    # (model, props) from a project cab (mirrors the GUI member loading).
    archive = CabArchive.parse(Path(cab_path).read_bytes())
    archive.fill_member_data()
    xml_name = next((m.name for m in archive.members
                     if m.name.endswith('.xml')
                     and not m.name.startswith('_')), None)
    prop_name = next((m.name for m in archive.members
                      if m.name.endswith('_property.xml')), None)
    if xml_name is None:
        raise ValueError('no project xml member')
    xml_data = next(m.data for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_data))
    props = PropertyModel(parse_property(
        next(m.data for m in archive.members if m.name == prop_name)
    )) if prop_name else PropertyModel(None)
    return model, props


def prepare_case(cab_path, out_dir) -> str:
    # Export a project's .s/.xemt into out_dir; returns the .s path.
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model, props = load_models(cab_path)
    base = out_dir / (model.project_name or 'model')
    with open(base.with_suffix('.s'), 'w', encoding='utf-8-sig',
              newline='') as fh:
        fh.write(build_sdat(model, props))
    with open(base.with_suffix('.xemt'), 'w', encoding='utf-8-sig',
              newline='') as fh:
        fh.write(xemt_export.build_emt(model, props))
    return str(base.with_suffix('.s'))


class BatchRunner(QObject):
    # Sequential solver queue over project cabs (QObject signal loop).

    case_started = pyqtSignal(str, int, int)      # name, index, total
    case_finished = pyqtSignal(str, int, bool)    # name, exit_code, ok
    queue_done = pyqtSignal(int, int)             # ok_count, fail_count
    output_line = pyqtSignal(str)

    def __init__(self, exe: str, workdir: str, envfile: str = '',
                 restart: bool = False, stop_on_error: bool = True,
                 parent=None):
        super().__init__(parent)
        self._exe = exe
        self._workdir = workdir
        self._envfile = envfile
        self._restart = restart
        self._stop_on_error = stop_on_error
        self._cases: list = []
        self._idx = 0
        self._ok = 0
        self._fail = 0
        self._proc = None
        self._stopped = False

    def queue(self, cases) -> None:
        self._cases = list(cases)

    @property
    def is_running(self) -> bool:
        return (self._proc is not None and self._proc.is_running()) \
            or self._idx < len(self._cases)

    def start(self) -> bool:
        self._idx = 0
        self._ok = 0
        self._fail = 0
        self._stopped = False
        self._run_next()
        return True

    def stop(self) -> None:
        self._stopped = True
        if self._proc is not None and self._proc.is_running():
            self._proc.stop()

    def _run_next(self) -> None:
        while self._idx < len(self._cases) and not self._stopped:
            name, cab = self._cases[self._idx]
            try:
                case_dir = Path(self._workdir) / self._safe_name(name)
                sfile = prepare_case(cab, case_dir)
            except Exception as exc:
                self.output_line.emit(
                    f'[batch] {name}: prepare failed: {exc}')
                self._fail += 1
                self.case_finished.emit(name, -1, False)
                if self._stop_on_error:
                    self._stopped = True
                    break
                self._idx += 1
                continue
            args = [sfile]
            if self._envfile:
                args += ['-env', self._envfile]
            if self._restart:
                args += ['-restart']
            proc = SolverProcess(self)
            proc.output_line.connect(
                lambda line, n=name: self.output_line.emit(f'[{n}] {line}'))
            proc.success.connect(lambda n=name: self._on_success(n))
            proc.error.connect(lambda n=name: self._on_error(n))
            if proc.start(self._exe, args, str(case_dir)):
                self._proc = proc
                self.case_started.emit(name, self._idx + 1, len(self._cases))
                return
            self.output_line.emit(f'[batch] {name}: solver failed to start')
            self._fail += 1
            self.case_finished.emit(name, -1, False)
            if self._stop_on_error:
                self._stopped = True
                break
            self._idx += 1
        self._finish()

    def _on_success(self, name: str) -> None:
        self._ok += 1
        self.case_finished.emit(name, 0, True)
        self._next()

    def _on_error(self, name: str) -> None:
        self._fail += 1
        self.case_finished.emit(name, -1, False)
        self._next()

    def _next(self) -> None:
        self._proc = None
        self._idx += 1
        if self._stopped or (self._stop_on_error and self._fail):
            self._finish()
        else:
            self._run_next()

    def _finish(self) -> None:
        self._proc = None
        self.queue_done.emit(self._ok, self._fail)

    @staticmethod
    def _safe_name(name: str) -> str:
        keep = ''.join(c if (c.isalnum() or c in '-_.') else '_'
                       for c in name)
        return keep.strip('._') or 'case'

class BatchExecutionDialog(QDialog):
    # File -> Batch Execution... : queue project cabs and solve them in
    # sequence with the R6 SolverProcess monitor.

    def __init__(self, parent=None, find_exe=None, default_workdir=''):
        super().__init__(parent)
        self.setWindowTitle('Batch Execution')
        self.setMinimumWidth(520)
        self._find_exe = find_exe
        self._runner = None
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            'Queue project .cab files; each is exported (.s/.xemt) into a '
            'per-case folder under the working directory and solved by '
            'stsol in sequence.', self))
        self.listw = QListWidget(self)
        root.addWidget(self.listw, 1)
        row = QHBoxLayout()
        for label, slot in (('Add...', self._add), ('Remove', self._remove),
                             ('Clear', self._clear)):
            b = QPushButton(label, self)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)
        form = QFormLayout()
        self.workdir = QLineEdit(default_workdir, self)
        brow = QHBoxLayout()
        brow.addWidget(self.workdir, 1)
        bwd = QPushButton('...', self)
        bwd.clicked.connect(self._pick_dir)
        brow.addWidget(bwd)
        form.addRow('Working directory', brow)
        self.envfile = QLineEdit('', self)
        form.addRow('Environment file', self.envfile)
        self.restart = QCheckBox('Restart from previous result', self)
        form.addRow(self.restart)
        self.stop_err = QCheckBox('Stop on first error', self)
        self.stop_err.setChecked(True)
        form.addRow(self.stop_err)
        root.addLayout(form)
        self.logview = QPlainTextEdit(self)
        self.logview.setReadOnly(True)
        self.logview.setMaximumBlockCount(2000)
        root.addWidget(self.logview, 1)
        brow2 = QHBoxLayout()
        self.run_btn = QPushButton('Run queue', self)
        self.run_btn.clicked.connect(self._run)
        cancel = QPushButton('Close', self)
        cancel.clicked.connect(self.reject)
        brow2.addStretch(1)
        brow2.addWidget(self.run_btn)
        brow2.addWidget(cancel)
        root.addLayout(brow2)

    def _add(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Add project cabs', '', 'Cradle cab (*.cab);;All (*.*)')
        for f in files:
            if not any(self.listw.item(i).data(Qt.UserRole) == f
                       for i in range(self.listw.count())):
                it = QListWidgetItem(str(Path(f).name), self.listw)
                it.setData(Qt.UserRole, f)
                it.setToolTip(f)

    def _remove(self) -> None:
        for it in self.listw.selectedItems():
            self.listw.takeItem(self.listw.row(it))

    def _clear(self) -> None:
        self.listw.clear()

    def _pick_dir(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(
            self, 'Working directory', self.workdir.text())
        if d:
            self.workdir.setText(d)

    def _run(self) -> None:
        cases = [(self.listw.item(i).text(),
                  self.listw.item(i).data(Qt.UserRole))
                 for i in range(self.listw.count())]
        if not cases:
            QMessageBox.warning(self, 'Batch Execution',
                                'Add at least one project cab.')
            return
        exe = (self._find_exe(['stsol_Dx64net.exe', 'stsol_Sx64net.exe',
                               'stsol.exe'])
               if self._find_exe else None)
        if exe is None:
            QMessageBox.warning(self, 'Batch Execution',
                                'stsol not found (Cradle CFD install).')
            return
        self._runner = BatchRunner(
            exe, self.workdir.text().strip() or '.',
            envfile=self.envfile.text().strip(),
            restart=self.restart.isChecked(),
            stop_on_error=self.stop_err.isChecked(), parent=self)
        self._runner.queue(cases)
        self._runner.case_started.connect(self._on_started)
        self._runner.case_finished.connect(self._on_finished)
        self._runner.queue_done.connect(self._on_done)
        self._runner.output_line.connect(
            lambda line: self.logview.appendPlainText(line))
        self.run_btn.setEnabled(False)
        self._runner.start()

    def _on_started(self, name: str, idx: int, total: int) -> None:
        self.logview.appendPlainText(f'--- [{idx}/{total}] {name} ---')

    def _on_finished(self, name: str, exit_code: int, ok: bool) -> None:
        self.logview.appendPlainText(
            f'--- {name}: exit={exit_code} '
            f'{"ok" if ok else "FAILED"} ---')

    def _on_done(self, ok: int, fail: int) -> None:
        self.logview.appendPlainText(
            f'=== queue done: {ok} ok, {fail} failed ===')
        self.run_btn.setEnabled(True)


