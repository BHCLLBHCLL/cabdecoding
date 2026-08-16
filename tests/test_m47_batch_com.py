# M47/M48: COM bridge extended surface + batch execution orchestration.
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / 'tests' / 'box.cab'


def test_stpredoc_extended_surface_wrapped():
    # 2026-08-16 signature sweep (data/com_sig_probe.json) wrapped surface.
    import cab_stpre_api
    for name in (
            'SetSolverParam', 'GetSolverParam', 'SetEvaporationParam',
            'GetEvaporationParam', 'SetSolidMeltParam', 'GetSolidMeltParam',
            'SetPhaseParam', 'GetPhaseParam', 'SetPorousHeatTransfer',
            'SetCycle', 'GetCycle', 'SetUserEntity', 'GetUserEntity',
            'GetScript', 'GetExpression', 'GetReferencedExpression',
            'SetUserFunction', 'GetUserFunction', 'SetUserData',
            'GetUserData'):
        assert hasattr(cab_stpre_api.STpreDoc, name), name


def test_com_sig_probe_evidence_committed():
    import json
    d = json.loads((ROOT / 'data' / 'com_sig_probe.json').read_text(
                   encoding='utf-8'))
    wins = {k: v.get('win_shape') for k, v in d.items()}
    assert wins.get('SetSolverParam') == ['steady_convergence', '1e-4']
    assert wins.get('SetPorousHeatTransfer') == ['Xmin', 'conduction', '10']
    assert wins.get('SetCycle') == ['transient', '100']
    assert wins.get('GetCycle') == []
    assert wins.get('SetUserEntity') == ['key1', '42']


def test_batch_load_models_box():
    import cab_batch
    model, props = cab_batch.load_models(BOX)
    assert model.project_name == 'box'


def test_batch_prepare_case_writes_s_and_xemt():
    import shutil
    import cab_batch
    tmp_path = ROOT / 'tests' / '_batch_tmp'
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir()
    try:
        sfile = cab_batch.prepare_case(BOX, tmp_path)
        p = Path(sfile)
        assert p.exists() and p.suffix == '.s'
        assert p.with_suffix('.xemt').exists()
        head = p.read_text(encoding='utf-8-sig')[:200]
        assert 'SDAT' in head.upper() or 'SCSTREAM' in head.upper()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_param_overrides_resolution():
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre, _first
    import cab_batch
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name="P", kind="cube", attribute="solid")
    n = cab_batch.apply_param_overrides(model, {
        "ambient_temperature": "25",
        "project.comment": "case-x",
        "etc.cutcell_enable": "T",
        "P.heat_source": "7.5",
    })
    assert n == 4
    assert model.analysis_set_value("ambient_temperature", "") == "25"
    assert model.project_value("comment") == "case-x"
    assert model.analysis_etc_value("cutcell_enable", "") == "T"
    el = model.find_part("P")
    assert (_first(el, "heat_source").text or "").strip() == "7.5"


def test_prepare_case_with_overrides():
    import shutil
    import cab_batch
    out = ROOT / "tests" / "_batch_tmp2"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    try:
        sfile = cab_batch.prepare_case(BOX, out, {"ambient_temperature": "99"})
        head = Path(sfile).read_text(encoding="utf-8-sig")
        assert "99" in head
    finally:
        shutil.rmtree(out, ignore_errors=True)

def test_scan_solver_results():
    import shutil
    import cab_gui
    out = ROOT / "tests" / "_res_tmp"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    try:
        (out / "model.s").write_text("s")
        (out / "model.pst").write_text("pst")
        (out / "model.out").write_text("out\ncycle 100 converged")
        (out / "other.txt").write_text("x")
        files = cab_gui.CabViewer._scan_solver_results(
            None, str(out), str(out / "model.s"))
        names = [f.name for f in files]
        assert "model.pst" in names
        assert "model.out" in names
        assert "other.txt" not in names
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_read_back_solver_results():
    import shutil
    import cab_gui
    out = ROOT / "tests" / "_res_tmp2"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    try:
        (out / "model.s").write_text("s")
        (out / "model.pst").write_text("pst")
        (out / "model.out").write_text("log\ncycle 100 converged")
        class _SB:
            def showMessage(self, *a, **k):
                pass
        class _Stub:
            pass
        stub = _Stub()
        stub._solver_run = (str(out), str(out / "model.s"))
        stub._scan_solver_results =             lambda cwd, sfile: cab_gui.CabViewer._scan_solver_results(
                None, cwd, sfile)
        stub._last_result_pst = None
        stub.logs = []
        sb = _SB()
        stub.statusBar = lambda: sb
        def _log(msg, level="INFO"):
            stub.logs.append((msg, level))
        stub.log = _log
        cab_gui.CabViewer._read_back_solver_results(stub)
        assert stub._last_result_pst == str(out / "model.pst")
        assert any("Post file ready" in m for m, _ in stub.logs)
        assert any("Convergence tail" in m for m, _ in stub.logs)
    finally:
        shutil.rmtree(out, ignore_errors=True)

def test_batch_runner_prepare_failure_paths():
    # Exercises the queue loop's prepare-failure handling without spawning
    # a solver process (sandbox-safe).
    import cab_batch
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    done = []
    finished = []
    r = cab_batch.BatchRunner('noop.exe', str(ROOT), stop_on_error=True)
    r.queue([('bad1', str(ROOT / 'missing1.cab')),
             ('bad2', str(ROOT / 'missing2.cab'))])
    r.queue_done.connect(lambda ok, fail: done.append((ok, fail)))
    r.case_finished.connect(lambda n, c, ok: finished.append(n))
    r.start()
    app.processEvents()
    assert done == [(0, 1)]           # stop_on_error stops after first
    assert finished == ['bad1']

    r2 = cab_batch.BatchRunner('noop.exe', str(ROOT), stop_on_error=False)
    done2 = []
    r2.queue([('bad1', str(ROOT / 'missing1.cab')),
              ('bad2', str(ROOT / 'missing2.cab'))])
    r2.queue_done.connect(lambda ok, fail: done2.append((ok, fail)))
    r2.start()
    app.processEvents()
    assert done2 == [(0, 2)]          # continues past failures

