"""Tests for the reverse-engineered PK_TOPOL_facet_2 node path."""
from __future__ import annotations

from pathlib import Path

import pytest

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"
TR03 = ROOT / "tests" / "tr03.cab"

ps_facet2 = pytest.importorskip("ps_facet2_nodes")


def _xt(path: Path) -> bytes:
    archive = CabArchive.parse(path.read_bytes())
    archive.fill_member_data()
    return next(m.data for m in archive.members if m.name.endswith(".x_t"))


@pytest.mark.skipif(not ps_facet2.available(),
                    reason="Cradle pskernel.dll not installed")
def test_facet2_box_surface():
    """box.cab must yield the real 8-vertex/12-triangle cube surface."""
    parts = ps_facet2.tessellate_xt(_xt(BOX))
    assert len(parts) == 1
    box = parts[0]
    assert box.name == "box"
    assert len(box.points) == 8
    assert len(box.triangles) == 12
    # Coordinates agree with the GO path (0..0.01 cube), not the old
    # mis-decoded "6 unit axis vectors".
    mn, mx = box.points.min(0), box.points.max(0)
    assert abs(mn.min() - 0.0) < 1e-12
    assert abs(mx.max() - 0.01) < 1e-12


@pytest.mark.skipif(not ps_facet2.available(),
                    reason="Cradle pskernel.dll not installed")
def test_facet2_tr03_matches_go_counts():
    """tr03 (x_t only, no element mesh) must produce visible surfaces and
    agree with the render_facet GO path triangle-for-triangle."""
    xt = _xt(TR03)
    # One kernel session per process: drive both paths from the same
    # ps_facet2 session (ps_tessellate would try to start a second one).
    sess = ps_facet2._get_session()
    tags = sess.receive_xt(xt)
    assert len(tags) == 3
    t2 = {sess.body_name(t): sess.facet2(t) for t in tags}
    go = {sess.body_name(t): sess.facet_go(t) for t in tags}
    assert set(t2) == set(go) == {"Case", "Impeller", "Rotate"}
    for name, part in t2.items():
        assert part is not None and go[name] is not None
        assert len(part.triangles) == len(go[name].triangles)
        assert len(part.triangles) > 0
        # facet_2 deduplicates shared vertices, so it never has *more*
        # nodes than the GO strip path.
        assert len(part.points) <= len(go[name].points)


@pytest.mark.skipif(not ps_facet2.available(),
                    reason="Cradle pskernel.dll not installed")
def test_facet2_attach_to_cab_vtk():
    """GUI wiring: facet2 TessParts attach as smooth CAD polydata even for
    tr03, which has no element occupancy boxes."""
    import cab_vtk

    archive = CabArchive.parse(TR03.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    model = StpreModel(parse_stpre(members["tr03.xml"]))
    tess = ps_facet2.tessellate_xt(members["_tr03_all.x_t"])
    boxes = cab_vtk.part_boxes(model, tess)
    assert {b.name for b in boxes} == {"Case", "Impeller", "Rotate"}
    for box in boxes:
        assert not box.cells                # no element section in tr03
        assert box.cad_polydata is not None
        assert box.cad_polydata.GetNumberOfPolys() > 0
        assert box.cad_polydata.GetPointData().GetNormals() is not None


@pytest.mark.skipif(not ps_facet2.available(),
                    reason="Cradle pskernel.dll not installed")
def test_facet2_adaptive_refines_large_curved_faces():
    """Adaptive mode must keep every body and refine large curved faces
    (per-face local tolerances), never coarsen a body."""
    sess = ps_facet2._get_session()
    tags = sess.receive_xt(_xt(TR03))
    base = {sess.body_name(t): sess.facet2(t) for t in tags}
    adp = {sess.body_name(t): sess.facet_body_adaptive(t) for t in tags}
    assert set(base) == set(adp) == {"Case", "Impeller", "Rotate"}
    for name, part in base.items():
        assert part is not None and adp[name] is not None
        assert len(adp[name].triangles) >= len(part.triangles)
    # Case is the complex body: it must actually be refined.
    assert len(adp["Case"].triangles) > len(base["Case"].triangles)
    # Per-face probe metrics must be well-formed on every face.
    tag = next(t for t in tags if sess.body_name(t) == "Case")
    faces = sess.body_faces(tag)
    assert faces
    for ft in faces[:3]:
        nf, area, max_ang, _pts = sess._face_metrics(
            ft, facet_tol=ps_facet2.DEFAULT_FACET_TOL,
            facet_angle_deg=ps_facet2.DEFAULT_FACET_ANGLE_DEG)
        assert nf > 0 and area > 0.0 and 0.0 <= max_ang <= 180.0


@pytest.mark.skipif(not ps_facet2.available(),
                    reason="Cradle pskernel.dll not installed")
def test_facet2_adaptive_flat_box_unchanged():
    """A flat box has no angularly-coarse faces, so adaptive must be a no-op."""
    sess = ps_facet2._get_session()
    tag = sess.receive_xt(_xt(BOX))[0]
    base = sess.facet2(tag)
    adp = sess.facet_body_adaptive(tag)
    assert base is not None and adp is not None
    assert len(base.triangles) == len(adp.triangles) == 12
    assert len(base.points) == len(adp.points) == 8
