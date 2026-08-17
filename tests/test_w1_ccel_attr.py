"""W1: ccel ATTR follows part attribute (PANEL / BODY / FLUID)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EX4_CAB = ROOT / "tests" / "ex4_e.cab"


@pytest.fixture()
def ex4_model():
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    arch = CabArchive.parse(EX4_CAB.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return StpreModel(parse_stpre(members["ex4_e.xml"]))


def test_ccel_attr_mapping_unit():
    import s_export

    class P:
        def __init__(self, attribute="", kind=""):
            self.attribute = attribute
            self.kind = kind

    assert s_export._ccel_attr(P("panel")) == "PANEL"
    assert s_export._ccel_attr(P("Sheet")) == "PANEL"
    assert s_export._ccel_attr(P(kind="quad_panel")) == "PANEL"
    assert s_export._ccel_attr(P("fluid")) == "FLUID"
    assert s_export._ccel_attr(P("Fluid region")) == "FLUID"
    assert s_export._ccel_attr(P("solid")) == "BODY"
    assert s_export._ccel_attr(P("obstacle")) == "BODY"
    assert s_export._ccel_attr(P("Fan", kind="fan")) == "BODY"


def test_build_ccel_attr_fluid_and_panel(ex4_model):
    import cab_mesh
    import ccel
    import s_export
    model = ex4_model
    p = model.parts()[0]
    assert cab_mesh.set_part_cutcell(model, p.name, True)

    class _Tess:
        pass

    tess = _Tess()
    tess.name = p.name
    tess.points = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0],
                            [0.0, 0.1, 0.0]])
    tess.triangles = np.array([[0, 1, 2]])

    p.elem.find("attribute").text = " fluid "
    parts, _a, _f = ccel.read_ccel_doc(s_export.build_ccel(model, [tess]))
    assert parts[0].attr == "FLUID"

    p.elem.find("attribute").text = " panel "
    parts, _a, _f = ccel.read_ccel_doc(s_export.build_ccel(model, [tess]))
    assert parts[0].attr == "PANEL"

    p.elem.find("attribute").text = " solid "
    parts, _a, _f = ccel.read_ccel_doc(s_export.build_ccel(model, [tess]))
    assert parts[0].attr == "BODY"
