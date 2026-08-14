"""D1: specialized part kinds (Delphi/HeatPipe/Multi-Resistor/CardGuide/Slit/Anemostat)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import cab_parts
from cabxml import StpreModel, new_stpre_bytes, parse_stpre

NEW_KINDS = [
    "delphi", "multi_resistor", "heat_pipe",
    "card_guide", "slit_punching", "anemostat",
]


def test_new_kinds_are_registered():
    for k in NEW_KINDS:
        assert k in cab_parts.PRIMITIVE_KINDS, k
        assert k in cab_parts.KIND_TITLES, k


@pytest.mark.parametrize("kind", NEW_KINDS)
def test_register_and_tessellate(kind):
    model = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    ok = cab_parts.register_primitive(
        model, name=f"{kind}_1", kind=kind,
        params={"base": (0.0, 0.0, 0.0), "size": (10.0, 10.0, 10.0)},
        attribute="solid")
    assert ok, f"register {kind} failed"
    info = next((p for p in model.parts() if p.name == f"{kind}_1"), None)
    assert info is not None and info.kind == kind
    tess = cab_parts.tess_for_part(info)
    assert tess is not None and len(tess.points) >= 8, f"tess {kind} empty"
    # round-trip: serialize + reparse keeps the part kind
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    assert reparsed.find_part(f"{kind}_1") is not None
