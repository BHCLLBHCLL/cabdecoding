"""Pytest root conftest: sandbox-safe temp directories.

The DSH workspace sandbox denies file writes inside directories created by
tempfile.mkdtemp (its security descriptor differs from a plain os.makedirs
directory).  Patch mkdtemp to build the same unique path with os.makedirs so
pytest's tmp_path fixture and the code under test can both write temp files
in this environment.  Harmless elsewhere.
"""
import os
import tempfile
import uuid

_ORIGINAL_MKDTEMP = tempfile.mkdtemp


def _mkdtemp_safe(suffix=None, prefix=None, dir=None):
    base = dir if dir is not None else tempfile.gettempdir()
    name = (prefix or "tmp") + uuid.uuid4().hex + (suffix or "")
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=False)
    return path


tempfile.mkdtemp = _mkdtemp_safe


# ---------------------------------------------------------------------------
# I4: COM-process leak guard.
#
# COM automation tests (STpre gridding, FEM probes, typelib sweeps) launch
# external preprocessor processes.  A crashed test can leak the process —
# a leaked scFLOWpre once grew to 48 GB and starved the whole suite.  The
# guard records the preprocessor processes alive at session start and
# reaps every *new* one at session end: anything still running after the
# last test was launched by the suite itself (the session-ownership guard
# in cab_stpre_api refuses to attach to user instances, so pre-existing
# processes are never reaped).
import atexit

_LEAK_TARGETS = ("stpre", "scflow", "scpost", "heatpre")


def _preprocessor_pids() -> dict:
    """{pid: name} of Cradle preprocessor processes currently running."""
    try:
        import psutil
    except ImportError:
        return {}
    out = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info["name"] or "").lower()
        except Exception:
            continue
        if any(t in name for t in _LEAK_TARGETS):
            out[proc.info["pid"]] = proc.info["name"]
    return out


def _reap_leaked_com_processes(baseline: dict) -> list:
    reaped = []
    for pid, name in _preprocessor_pids().items():
        if pid in baseline:
            continue
        try:
            import psutil
            psutil.Process(pid).kill()
            reaped.append((pid, name))
        except Exception:
            pass
    return reaped


def _pytest_session_start_guard():
    baseline = _preprocessor_pids()

    def _finish():
        reaped = _reap_leaked_com_processes(baseline)
        for pid, name in reaped:
            print(f"\n[com-leak-guard] reaped leaked {name} (pid {pid})")

    atexit.register(_finish)


_pytest_session_start_guard()


import pytest  # noqa: E402  (conftest-local fixture support)


@pytest.fixture(scope="module")
def com_guard():
    """Per-module COM leak reap.

    COM test modules request this fixture; after the module's last test,
    any preprocessor process that appeared during the module (baseline
    taken at module setup) is killed.  User-opened instances are excluded
    by the same baseline, and cab_stpre_api's ownership guard already
    refuses to attach to running instances.
    """
    baseline = _preprocessor_pids()
    yield
    reaped = _reap_leaked_com_processes(baseline)
    for pid, name in reaped:
        print(f"\n[com-leak-guard] reaped leaked {name} (pid {pid})")
