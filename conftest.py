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
