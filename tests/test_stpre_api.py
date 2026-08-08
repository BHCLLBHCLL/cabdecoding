"""STpre VB/COM API bridge tests (cab_stpre_api + GUI switch)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(autouse=True)
def _reset_stpre_switch():
    import cab_options
    cab_options.set_setting("use_stpre_api", "False")
    yield
    cab_options.set_setting("use_stpre_api", "False")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _model():
    import cab_stpre_api
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    return StpreModel(parse_stpre(members[xml_name])), archive


def _viewer(qapp):
    import cab_gui
    from cab_container import CabArchive
    from cabxml import PropertyModel, parse_property
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    prop_name = next(n for n in members if n.endswith("_property.xml"))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.archive = archive
    from cabxml import StpreModel, parse_stpre
    viewer.model = StpreModel(parse_stpre(members[xml_name]))
    viewer.props = PropertyModel(parse_property(members[prop_name]))
    return viewer


def test_api_available_registry():
    import cab_stpre_api
    assert isinstance(cab_stpre_api.api_available(), bool)


def test_build_grid_params_mapping():
    import cab_stpre_api
    model, _ = _model()
    params = cab_stpre_api.build_grid_params(model)
    d = dict((p[0], p) for p in params)
    assert d["division_method"][1] == "detail"
    sv = int(model.mesh_control_value("select_vertex") or 3)
    expected = {0: "all", 1: "main", 2: "plane", 3: "minmax",
                4: "none", 5: "uniform"}[sv]
    assert d["division_type"][1] == expected
    assert len(d["outer_ratio"]) == 4
    # auto1 with target elements
    p2 = cab_stpre_api.build_grid_params(
        model, method="auto1", target_elements=1000)
    d2 = dict((p[0], p) for p in p2)
    assert d2["division_num"][1] == 1000
    assert d2["division_num"][3] == 0


def test_build_relay_cab_keeps_rootblock_and_domain():
    import cab_stpre_api
    from cab_container import CabArchive
    model, archive = _model()
    model.ensure_domain(base=(-25, -25, -25), size=(50, 50, 50))
    import os
    src = os.path.join(os.environ.get("TEMP", "."), "relay_test.cab")
    assert cab_stpre_api.build_relay_cab(model, archive, src) is True
    arch = CabArchive.parse(open(src, "rb").read())
    arch.fill_member_data()
    members = {m.name: m.data for m in arch.members}
    from cabxml import StpreModel, parse_stpre
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    m2 = StpreModel(parse_stpre(members[xml_name]))
    assert m2.doc.root.find("mesh_control") is not None
    assert m2.domain_base() == (-25.0, -25.0, -25.0)
    # coordinate tables are cleared so STpre regenerates them from the
    # RootBlock range (otherwise it keeps the template's old range)
    mb = m2.doc.root.find("mesh_block")
    assert mb is not None and mb.find("x") is None
    assert m2.doc.root.find("element") is None


def test_merge_mesh_result():
    import cab_stpre_api
    from cabxml import StpreModel, parse_stpre
    model, _ = _model()
    # build an "output" model whose mesh_block has an extra x line
    out_raw = model.doc.serialize()
    out_model = StpreModel(parse_stpre(out_raw))
    out_model.set_mesh(
        {"x": [0.0, 1.0, 2.0, 3.0], "y": [0.0, 1.0], "z": [0.0, 1.0]},
        domain_min=(0, 0, 0), domain_max=(3, 1, 1))
    merged = cab_stpre_api.merge_mesh_result(model, out_model)
    assert "mesh_control" in merged
    assert "mesh_block" in merged
    assert len(model.mesh_axes()["x"]) == 4


def test_option_toggle(qapp):
    import cab_options
    cab_options.set_setting("use_stpre_api", "True")
    assert str(cab_options.get_setting("use_stpre_api", "False")).lower() \
        == "true"
    cab_options.set_setting("use_stpre_api", "False")
    viewer = _viewer(qapp)
    viewer._toggle_stpre_api(True)
    assert viewer._stpre_api_enabled() is True
    viewer._toggle_stpre_api(False)
    assert viewer._stpre_api_enabled() is False


def test_build_params_from_gridspec(qapp):
    import cab_grid
    import cab_stpre_api
    spec = cab_grid.GridSpec(
        vertex_detection="minmax", method="rough_and_detail",
        geometric_ratio_external=(1.2, 1.3, 1.4))
    params = cab_stpre_api.build_params_from_gridspec(spec, edge_contact=1)
    d = dict((p[0], p) for p in params)
    assert d["division_method"][1] == "detail"
    assert d["division_type"][1] == "minmax"
    assert d["outer_ratio"][1:4] == (1.2, 1.3, 1.4)
    assert d["edge_contact"][1] == 1
    spec2 = cab_grid.GridSpec(
        method="num_elements", target_per_axis=(10, 20, 30))
    d2 = dict((p[0], p) for p in
              cab_stpre_api.build_params_from_gridspec(spec2))
    assert d2["division_method"][1] == "auto3"
    assert d2["division_num"][1:4] == (10, 20, 30)


def test_gridding_dialog_callback_short_circuit(qapp):
    import cab_dialogs
    viewer = _viewer(qapp)
    calls = []
    dlg = cab_dialogs.GriddingDialog(
        viewer.model, [], parent=viewer)
    dlg.stpre_callback = lambda spec, ec: calls.append((spec, ec)) or True
    before = viewer.model.mesh_axes()
    dlg._gridding()
    assert len(calls) == 1 and calls[0][1] is False
    assert viewer.model.mesh_axes() == before


def test_gridding_dialog_opens_even_with_stpre_on(qapp, monkeypatch):
    import cab_dialogs
    import cab_options
    viewer = _viewer(qapp)
    cab_options.set_setting("use_stpre_api", "True")
    opened = []
    monkeypatch.setattr(
        cab_dialogs.GriddingDialog, "exec_",
        lambda self: opened.append(1) or self.reject())
    viewer._gridding_dialog()
    assert opened == [1]  # Mesh:Set Division window still opens
    cab_options.set_setting("use_stpre_api", "False")


def test_stpre_grid_from_dialog_uses_dialog_params(qapp, monkeypatch):
    import cab_grid
    import cab_options
    viewer = _viewer(qapp)
    cab_options.set_setting("use_stpre_api", "True")
    captured = {}
    monkeypatch.setattr(
        viewer, "_run_stpre_api",
        lambda action, params=None, method="detail": captured.update(
            action=action, params=params, method=method) or "stpre")
    spec = cab_grid.GridSpec(
        vertex_detection="representative", method="rough_and_detail",
        geometric_ratio_external=(1.2, 1.2, 1.2))
    assert viewer._stpre_grid_from_dialog(spec, False) is True
    assert captured["action"] == "grid"
    assert captured["method"] == "detail"
    d = dict((p[0], p) for p in captured["params"])
    assert d["division_type"][1] == "main"
    cab_options.set_setting("use_stpre_api", "False")


class _FakeSession:
    """STpreSession stand-in that records calls and echoes the relay."""

    def __init__(self, fail_grid=False, fail_open=False):
        self.fail_grid = fail_grid
        self.fail_open = fail_open
        self.opened = []
        self.grid_calls = []
        self.element_calls = 0
        self.save_calls = []
        self.close_calls = 0

    def ensure_open(self, src):
        if self.fail_open:
            return False
        self.opened.append(str(src))
        return True

    def grid(self, params, method):
        self.grid_calls.append((params, method))
        return not self.fail_grid

    def element(self):
        self.element_calls += 1
        return True

    def save(self, dst):
        import shutil
        self.save_calls.append(str(dst))
        shutil.copyfile(self.opened[-1], str(dst))
        return True

    def close(self):
        self.close_calls += 1


def test_gui_dispatch_fallback_closes_session(qapp, monkeypatch):
    import cab_options
    import cab_stpre_api
    viewer = _viewer(qapp)
    cab_options.set_setting("use_stpre_api", "True")
    monkeypatch.setattr(cab_stpre_api, "api_available", lambda: True)
    fake = _FakeSession(fail_grid=True)
    monkeypatch.setattr(cab_stpre_api, "STpreSession", lambda: fake)
    monkeypatch.setattr(
        cab_stpre_api, "build_relay_cab",
        lambda *a, **k: True)
    assert viewer._run_stpre_api("grid") == "native"
    assert fake.close_calls == 1
    assert viewer._stpre_session is None
    cab_options.set_setting("use_stpre_api", "False")


def test_stpre_session_reused_grid_then_mesh(qapp, monkeypatch):
    """[Gridding] then [Meshing] share one STpre process; Meshing only
    runs ExecuteElement (no second ExecuteGrid / COM cold start)."""
    import cab_options
    import cab_stpre_api
    viewer = _viewer(qapp)
    cab_options.set_setting("use_stpre_api", "True")
    monkeypatch.setattr(cab_stpre_api, "api_available", lambda: True)
    fake = _FakeSession()
    monkeypatch.setattr(cab_stpre_api, "STpreSession", lambda: fake)
    real_build = cab_stpre_api.build_relay_cab
    keeps = []

    def fake_build(model, archive, src, *, keep_mesh=False):
        keeps.append(keep_mesh)
        return real_build(model, archive, src, keep_mesh=keep_mesh)

    monkeypatch.setattr(cab_stpre_api, "build_relay_cab", fake_build)

    assert viewer._run_stpre_api("grid") == "stpre"
    assert viewer._stpre_session is fake
    assert len(fake.grid_calls) == 1
    assert fake.element_calls == 0
    assert keeps == [False]

    # Gridding merged a mesh_block into the in-memory model; Meshing now
    # carries it into a fresh relay and only executes element division.
    viewer.model.set_mesh(
        {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0],
         "z": [0.0, 1.0, 2.0]},
        domain_min=(0, 0, 0), domain_max=(2, 2, 2))
    assert viewer._run_stpre_api("mesh") == "stpre"
    assert viewer._stpre_session is fake
    assert len(fake.grid_calls) == 1     # no second ExecuteGrid
    assert fake.element_calls == 1
    assert len(fake.opened) == 2         # second relay reopened in session
    assert len(fake.save_calls) == 2
    assert keeps == [False, True]
    assert fake.close_calls == 0         # session stays alive for reuse
    cab_options.set_setting("use_stpre_api", "False")


def test_stpre_session_reopen_logic(qapp, monkeypatch):
    """ensure_open re-opens a new relay file without restarting COM."""
    import cab_stpre_api
    pytest.importorskip("win32com.client")
    calls = {"open": [], "quit": 0}

    class _Flag:
        def _FlagAsMethod(self, name):
            return self

    class FakeMesher(_Flag):
        pass

    class FakeDoc(_Flag):
        def __init__(self):
            self.mesher = FakeMesher()

        def OpenCabFile(self, path):
            calls["open"].append(str(path))
            return 1

        def GetMesher(self):
            return self.mesher

        def SaveCabFile(self, path):
            return 1

    class FakeApp(_Flag):
        Visible = True

        def __init__(self):
            self.doc = FakeDoc()

        def GetDocument(self):
            return self.doc

        def Quit(self):
            calls["quit"] += 1

    monkeypatch.setattr("win32com.client.Dispatch",
                        lambda progid: FakeApp())
    session = cab_stpre_api.STpreSession()
    assert session.ensure_open("a.cab") is True
    assert calls["open"] == ["a.cab"]
    # same file: no second OpenCabFile
    assert session.ensure_open("a.cab") is True
    assert calls["open"] == ["a.cab"]
    # new relay: re-opened in the same process (no Quit)
    assert session.ensure_open("b.cab") is True
    assert calls["open"] == ["a.cab", "b.cab"]
    assert calls["quit"] == 0
    session.close()
    assert calls["quit"] == 1
