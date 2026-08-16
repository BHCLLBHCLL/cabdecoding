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

