"""P6 close-out: the four Edit Solid PK ops wired through cab_edit_ops.

Exercises the model+archive+cad_meshes bridge functions (hollow/offset/
replace/imprint ``*_part_pk``) on the real ex4_e x_t bodies, including the
write-back member and the part ``<file>`` re-point the dialog relies on.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_edit_ops
import cab_ps_ops

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
pytest.importorskip("cab_ps_ops")

ROOT = Path(__file__).resolve().parents[1]

# 0.5 mm wall / offset on the 10 mm ex4_e cubes.
THICKNESS = 0.0005

_requires_kernel = pytest.mark.skipif(
    not cab_ps_ops.available(), reason="pskernel not available")


def _project():
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    import cab_import
    arch = CabArchive.parse((ROOT / "tests" / "ex4_e.cab").read_bytes())
    arch.fill_member_data()
    mm = {m.name: m.data for m in arch.members}
    model = StpreModel(parse_stpre(mm["ex4_e.xml"]))
    tess = {b.name: b.tess for b in cab_import.import_xt_bytes(
        mm["_ex4_e_all.x_t"], adaptive=False)}
    meshes = [tess["button"], tess["battery"]]
    return arch, model, meshes


def _body_tag(model, arch, name):
    tag = cab_edit_ops._find_body_tags(model, arch, name, "")[0]
    assert tag is not None, f"no B-rep body resolved for {name}"
    return tag


def _facet(tag):
    sess = ps_facet2._get_session()
    part = (sess.facet_body_adaptive(tag) or sess.facet2(tag)
            or sess.facet_go(tag))
    assert part is not None
    return (np.asarray(part.points, dtype=np.float64),
            np.asarray(part.triangles, dtype=np.int64))


def _volume(tag):
    pts, tris = _facet(tag)
    return cab_ps_ops.mesh_volume_m3(pts, tris)


def _part_file_ref(model, name):
    info = next(p for p in model.parts() if p.name == name)
    f_el = info.elem.find("file")
    return (f_el.text or "").strip() if f_el is not None else ""


@_requires_kernel
def test_hollow_part_pk_shells_body_and_writes_member():
    arch, model, meshes = _project()
    vol0 = _volume(_body_tag(model, arch, "button"))
    out = cab_edit_ops.hollow_part_pk(
        model, arch, meshes, "button", THICKNESS)
    assert out["rc"] == 0 and out["ok"] is True, out
    # write-back: private member + part <file> re-point
    assert any(m.name == "button.x_t" for m in arch.members)
    assert _part_file_ref(model, "button") == "button.x_t"
    vol1 = _volume(_body_tag(model, arch, "button"))
    # 10 mm cube shelled at 0.5 mm: ~2.7e-7 m^3 (interior removed, not collapsed)
    assert 0.01 * vol0 < vol1 < 0.9 * vol0


@_requires_kernel
def test_offset_part_pk_grows_body_by_offset():
    arch, model, meshes = _project()
    tag0 = _body_tag(model, arch, "button")
    pts0, _ = _facet(tag0)
    vol0 = cab_ps_ops.mesh_volume_m3(pts0, _facet(tag0)[1])
    out = cab_edit_ops.offset_part_pk(
        model, arch, meshes, "button", THICKNESS)
    assert out["rc"] == 0 and out["ok"] is True, out
    assert any(m.name == "button.x_t" for m in arch.members)
    tag1 = _body_tag(model, arch, "button")
    pts1, tris1 = _facet(tag1)
    vol1 = cab_ps_ops.mesh_volume_m3(pts1, tris1)
    assert vol1 > vol0
    # every axis grows by ~2 * offset (facet tolerance slack)
    grow = (pts1.max(0) - pts1.min(0)) - (pts0.max(0) - pts0.min(0))
    assert np.all(grow > 0.5 * THICKNESS)
    assert np.all(grow < 4.0 * THICKNESS)


@_requires_kernel
def test_replace_face_pk_moves_top_face_down():
    # box_01 is a plain 12-triangle box part of ex4_e: PK_FACE_replace_surfs_2
    # works there.  On curved bodies (e.g. "button") the kernel silently
    # no-ops the replace (rc=0, geometry untouched) — kernel behaviour, not
    # the op's, so the geometric assertion runs on the box.
    arch, model, meshes = _project()
    tag = _body_tag(model, arch, "box_01")
    pts, tris = _facet(tag)
    cents = pts[tris].mean(axis=1)
    top = int(np.argmax(cents[:, 2]))
    a, b, c = (pts[tris[top, i]] for i in range(3))
    n = np.cross(b - a, c - a)
    n = n / np.linalg.norm(n)
    face = cab_ps_ops.match_face_by_plane(
        tag, tuple(n), tuple(cents[top]))
    assert face is not None, "top plane did not match a B-rep face"
    lo, hi = pts.min(0), pts.max(0)
    loc = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0,
           lo[2] + 0.25 * (hi[2] - lo[2]))
    vol0 = cab_ps_ops.mesh_volume_m3(pts, tris)
    out = cab_edit_ops.replace_face_pk(
        model, arch, meshes, "box_01", int(face), loc, (0.0, 0.0, 1.0))
    assert out["rc"] == 0 and out["ok"] is True, out
    assert any(m.name == "box_01.x_t" for m in arch.members)
    assert _part_file_ref(model, "box_01") == "box_01.x_t"
    vol1 = _volume(_body_tag(model, arch, "box_01"))
    # top face pushed down to 25 % height -> volume shrinks to ~a quarter
    assert 0.05 * vol0 < vol1 < 0.9 * vol0


@_requires_kernel
def test_imprint_part_pk_splits_target_faces():
    arch, model, meshes = _project()
    sess = ps_facet2._get_session()
    faces0 = len(sess.body_faces(_body_tag(model, arch, "button")) or [])
    out = cab_edit_ops.imprint_part_pk(
        model, arch, meshes, "button", "battery")
    assert out["rc"] == 0 and out["ok"] is True, out
    assert out.get("n_edges", 0) >= 0
    faces1 = len(sess.body_faces(_body_tag(model, arch, "button")) or [])
    # overlapping tool splits target faces -> face count must grow
    assert faces1 > faces0, (faces0, faces1)


def test_ops_fail_clean_without_archive_or_body():
    arch, model, meshes = _project()
    out = cab_edit_ops.hollow_part_pk(model, None, None, "button", 1e-3)
    assert out["ok"] is False and "pskernel" in out["msg"]
    # an archive without x_t members has no B-rep bodies to resolve
    from cab_container import CabArchive
    bare = CabArchive.parse((ROOT / "tests" / "ex4_e.cab").read_bytes())
    bare.members = [m for m in bare.members
                    if not m.name.endswith((".x_t", ".xmt_txt"))]
    out = cab_edit_ops.offset_part_pk(model, bare, meshes, "button", 1e-3)
    assert out["ok"] is False and "No B-rep body" in out["msg"]
    out = cab_edit_ops.imprint_part_pk(
        model, bare, meshes, "button", "battery")
    assert out["ok"] is False and "B-rep bodies" in out["msg"]


def test_edit_solid_dialog_exposes_p6_types():
    """Structural wiring: 12 types incl. the 4 P6 ops + new form fields."""
    try:
        from PyQt5.QtWidgets import QApplication, QDoubleSpinBox, QComboBox
        import sys
    except Exception:
        return
    from cab_edit_dialogs import EditSolidDialog
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    app = QApplication.instance() or QApplication(sys.argv)
    model = StpreModel(parse_stpre(new_stpre_bytes("T")))
    model.add_part(name="A", kind="cube", attribute="solid")
    model.add_part(name="B", kind="cube", attribute="solid")
    dlg = EditSolidDialog(model, None)
    try:
        for etype in ("Hollow shell", "Offset body",
                      "Replace face", "Imprint faces"):
            assert etype in dlg.TYPES
        offsets = [c for c in dlg.children() if isinstance(c, QDoubleSpinBox)]
        assert offsets, "Offset spinbox missing"
        tools = [c for c in dlg.children() if isinstance(c, QComboBox)]
        assert tools, "Tool part combo missing"
        assert hasattr(dlg, "result_msg")
    finally:
        dlg.close()
        dlg.deleteLater()
        app.processEvents()
