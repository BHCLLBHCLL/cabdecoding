"""M32: menu dialog alignment helpers (panelize / options pages)."""

from __future__ import annotations

import numpy as np

from cab_edit_ops import (
    panel_direction_from_normal,
    panel_params_from_aabb,
    panelize_part_face,
)
from cab_parts import PrimitivePart, register_primitive
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _empty_model() -> StpreModel:
    return StpreModel(parse_stpre(new_stpre_bytes()))


def test_panel_direction_from_normal():
    assert panel_direction_from_normal([0, 0, 1]) == "+Z"
    assert panel_direction_from_normal([0, 0, -2]) == "-Z"
    assert panel_direction_from_normal([1, 0.1, 0]) == "+X"


def test_panel_params_from_aabb():
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([10.0, 20.0, 30.0])
    base, size = panel_params_from_aabb(lo, hi, "+Z")
    assert abs(base[2] - 30.0) < 1e-9
    assert size[0] == 10.0 and size[1] == 20.0
    assert size[2] > 0.0


def test_panelize_part_face_creates_panel():
    model = _empty_model()
    assert register_primitive(
        model, name="Box1", kind="cube",
        params={"base": (0, 0, 0), "size": (10, 10, 10)},
        attribute="Solid")
    from cab_parts import tess_for_spec
    tess = tess_for_spec("cube", {"base": (0, 0, 0), "size": (10, 10, 10)})
    tess.name = "Box1"
    meshes = [tess]
    pname = panelize_part_face(model, meshes, "Box1", cell_id=None)
    assert pname is not None
    info = next(p for p in model.parts() if p.name == pname)
    assert info.kind == "panel"
    assert "panel" in (info.attribute or "").lower()
    assert any(getattr(m, "name", None) == pname for m in meshes)


def test_panelize_skips_sketch():
    model = _empty_model()
    el = model.add_part(name="Sketch1", kind="sketch", attribute="solid")
    assert el is not None
    meshes = [PrimitivePart(
        "Sketch1",
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float) / 1000.0,
        np.array([[0, 1, 2]], dtype=np.int64))]
    assert panelize_part_face(model, meshes, "Sketch1") is None


def test_options_environment_page_count():
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    from cab_options import OptionsDialog
    dlg = OptionsDialog(detailed=False)
    # Pre_eng ≈13 Environment pages + Mouse/Tree/Shortcut extras
    assert dlg.tabs.count() >= 13
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "Mesh" in titles
    assert "User Interface" in titles
    assert "Mouse" in titles
    vals = dlg.values()
    assert "use_stpre_api" in vals
    assert isinstance(vals["use_stpre_api"], bool)
