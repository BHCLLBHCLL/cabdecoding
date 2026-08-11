"""Assembly XT import (cellular_phone) — expand before faceting."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT / "tests" / "cellular_phone.x_t"
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"

cab_import = pytest.importorskip("cab_import")
ps = pytest.importorskip("ps_facet2_nodes")


@pytest.mark.skipif(not cab_import.available(),
                    reason="Cradle pskernel.dll not installed")
@pytest.mark.skipif(not PHONE.is_file(), reason="cellular_phone.x_t missing")
def test_expand_cellular_phone_assembly():
    sess = ps._get_session()
    tags = sess.receive_xt(PHONE.read_bytes())
    assert len(tags) == 1
    assert sess.entity_class(tags[0]) == ps.PK_CLASS_assembly
    bodies = sess.expand_to_bodies(tags)
    assert len(bodies) >= 100
    assert all(sess.entity_class(t) == ps.PK_CLASS_body for t in bodies[:5])


@pytest.mark.skipif(not cab_import.available(),
                    reason="Cradle pskernel.dll not installed")
@pytest.mark.skipif(not PHONE.is_file(), reason="cellular_phone.x_t missing")
def test_import_cellular_phone_no_crash():
    """Import must expand the assembly and return drawable bodies."""
    bodies = cab_import.import_xt_file(PHONE, adaptive=False)
    assert len(bodies) >= 50
    assert all(b.tess is not None and b.tess.triangles.size > 0
               for b in bodies[:10])


@pytest.mark.skipif(not cab_import.available(),
                    reason="Cradle pskernel.dll not installed")
def test_import_box_still_works():
    bodies = cab_import.import_xt_file(BOX_XT, adaptive=False)
    assert len(bodies) == 1
    assert bodies[0].name == "box"


@pytest.mark.skipif(not cab_import.available(),
                    reason="Cradle pskernel.dll not installed")
@pytest.mark.skipif(not PHONE.is_file(), reason="cellular_phone.x_t missing")
def test_register_assembly_assigns_distinct_colors():
    """Assembly import colors cycle like ex4_e.cab."""
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    bodies = cab_import.import_xt_file(PHONE, adaptive=False)
    assert len(bodies) > 1
    model = StpreModel(parse_stpre(new_stpre_bytes("phone")))
    added = cab_import.register_parts(model, bodies)
    assert len(added) == len(bodies)
    colors = [p.color.strip() for p in model.parts() if p.name in added]
    assert len(set(colors)) > 1
    assert colors[0] == cab_import.STPRE_PART_COLORS[0]
    assert colors[1] == cab_import.STPRE_PART_COLORS[1]
    n = len(cab_import.STPRE_PART_COLORS)
    if len(colors) > n:
        assert colors[n] == cab_import.STPRE_PART_COLORS[0]


def test_part_color_for_index_cycles():
    assert cab_import.part_color_for_index(0) == "25,25,255,255"
    assert cab_import.part_color_for_index(11) == cab_import.part_color_for_index(0)
