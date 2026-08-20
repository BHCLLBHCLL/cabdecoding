"""W5: typelib authoritative enumeration + per-class coverage metric.

Layered COM closure (function_gap_analysis.md §四.6):

1. typelib_member_table — HKCR ProgID -> CLSID -> TypeLib ->
   pythoncom.LoadRegTypeLib, enumerate every type info's funcs+vars.
   Live test skipped when STpre is not registered (RuntimeError path);
2. coverage_report — exact-name intersection (typed wrappers expose VB
   member names verbatim) against the typelib table, manual
   API_MEMBER_COUNTS baseline when no table is available;
3. cache round-trip — save/load JSON so the metric works offline.
"""

from __future__ import annotations

import json

import pytest

import cab_stpre_api as api


def test_typelib_member_table_live_or_skip():
    try:
        table = api.typelib_member_table()
    except RuntimeError as exc:
        pytest.skip(f"STpre typelib not enumerable: {exc}")
    assert isinstance(table, dict) and table
    total = sum(len(v) for v in table.values())
    assert total >= 500  # manual baseline says ~1.4k members
    # at least one typelib type name must match a typed wrapper class
    overlap = set(table) & set(api._TYPED_BY_VB)
    assert overlap, f"no overlap between typelib types {list(table)[:5]} and wrappers"


def test_coverage_report_synthetic_table():
    table = {
        "Doc": ["OpenCabFile", "SaveCabFile", "ZZZNotWrapped"],
        "Application": ["Visible", "Quit"],
    }
    rows = api.coverage_report(table)
    doc = rows["Doc"]
    assert doc["typelib"] == 3
    assert "OpenCabFile" in doc["missing_head"] or doc["typed"] >= 2
    assert doc["typed"] == 2  # OpenCabFile + SaveCabFile wrapped verbatim
    assert doc["pct"] == pytest.approx(66.7)
    assert doc["missing_head"] == ["ZZZNotWrapped"]
    app = rows["Application"]
    assert app["typelib"] == 2 and app["pct"] == pytest.approx(100.0)
    total = rows["TOTAL"]
    assert total["typelib"] == 5 and total["typed"] == 4
    assert total["pct"] == pytest.approx(80.0)


def test_coverage_report_manual_baseline_without_table():
    rows = api.coverage_report({})
    assert set(rows) == set(api._TYPED_BY_VB) | {"TOTAL"}
    for vb in api._TYPED_BY_VB:
        assert rows[vb]["typelib"] == 0
        assert rows[vb]["pct"] is None
        assert rows[vb]["manual"] == api.API_MEMBER_COUNTS[vb]
    # documented manual denominator: 12+459+458+272+69+88+12+22+12
    # + AirconModel 7 + Femodel 11 + GerberModel 25 (W5 snapshot classes)
    assert rows["TOTAL"]["manual"] == sum(api.API_MEMBER_COUNTS.values())
    assert rows["TOTAL"]["pct"] is None


def test_manual_member_table_live_or_skip():
    try:
        table = api.manual_member_table()
    except RuntimeError as exc:
        pytest.skip(f"VB manual not installed: {exc}")
    # anchor counts verified by hand 2026-08-18 (heading ids == TOC level-2)
    assert len(table.get("Doc", [])) >= 380
    assert len(table.get("Model", [])) >= 150
    assert len(table.get("Mesher", [])) == 19
    assert len(table.get("Application", [])) == 17  # "Appliation" typo page
    # extra STpre classes beyond the nine typed wrappers
    assert {"AirconModel", "Femodel", "GerberModel"} <= set(table)
    # members carry VB names verbatim
    assert "CreateCubeModel" in table["Doc"]
    assert "ExecuteGrid" in table["Mesher"]


def test_save_cache_records_provenance(tmp_path):
    # typelib is unregistered on this machine -> chain must fall through to
    # the manual and stamp the source; a machine WITH a typelib may return
    # either stamp.
    cache = tmp_path / "prov.json"
    try:
        api.save_typelib_cache(cache)
    except RuntimeError as exc:
        pytest.skip(f"no member source: {exc}")
    table = api.load_typelib_cache(cache)
    assert table.get("_source") in {"typelib", "manual"}
    members = {k: v for k, v in table.items() if not k.startswith("_")}
    assert members
    # TOTAL covers only the nine typed-wrapper classes; the extra manual
    # classes (AirconModel/Femodel/GerberModel) stay out of the metric
    core = sum(len(v) for k, v in members.items() if k in api._TYPED_BY_VB)
    assert api.coverage_report(members)["TOTAL"]["typelib"] == core


def test_typelib_cache_roundtrip(tmp_path):
    table = {"Doc": ["OpenCabFile", "SaveSFile"], "Model": ["GetName"]}
    cache = tmp_path / "tl.json"
    cache.write_text(json.dumps(table), encoding="utf-8")
    assert api.load_typelib_cache(cache) == table
    # absent / corrupt cache degrades to {} (never raises)
    assert api.load_typelib_cache(tmp_path / "none.json") == {}
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert api.load_typelib_cache(tmp_path / "bad.json") == {}
    # default cache path is a committed data/ sibling
    assert api._TYPELIB_CACHE.name == "com_typelib_members.json"


# ── W5 layer-A closure: 100% wrapper coverage over the full catalog ────────


def test_layer_a_catalog_fully_wrapped():
    # every API_CATALOG member is reachable as a class attribute (explicit
    # typed wrapper or generically attached at import)
    for vb, cls in api._TYPED_BY_VB.items():
        wrapped = {n for n in dir(cls) if not n.startswith("_")}
        missing = [m for m in api.API_CATALOG.get(vb, []) if m not in wrapped]
        assert not missing, f"{vb}: {missing[:5]}"


def test_coverage_report_full_catalog_table_100():
    rows = api.coverage_report(api.API_CATALOG)
    for vb in api._TYPED_BY_VB:
        assert rows[vb]["pct"] == pytest.approx(100.0), (vb, rows[vb])
    total = rows["TOTAL"]
    assert total["typelib"] == sum(len(v) for v in api.API_CATALOG.values())
    assert total["pct"] == pytest.approx(100.0)


def test_coverage_report_cache_layer_a_100():
    table = api.load_typelib_cache()
    if not table:
        pytest.skip("no committed member cache")
    # committed cache + MeshBlock catalog fallback -> full 100% report
    rows = api.coverage_report()
    for vb, row in rows.items():
        if vb != "TOTAL":
            assert row["pct"] == pytest.approx(100.0), (vb, row)
    assert rows["TOTAL"]["typed"] == rows["TOTAL"]["typelib"]
    assert rows["MeshBlock"]["typelib"] == len(api.API_CATALOG["MeshBlock"])


def test_attached_method_forwards_to_call():
    calls = []

    class FakeDispatch:
        def _FlagAsMethod(self, name):
            calls.append(("flag", name))

        def __getattr__(self, name):
            def invoke(*args):
                calls.append(("call", name, args))
                return 42
            return invoke

    doc = api.STpreDoc(FakeDispatch())
    # generically attached member (was missing before the W5 closure)
    assert doc.SetWall("region", "T") == 42
    assert ("flag", "SetWall") in calls
    assert ("call", "SetWall", ("region", "T")) in calls


def test_attached_property_is_property():
    class FakeDispatch:
        def _FlagAsMethod(self, name):
            raise AssertionError("property read must not flag a method")

        def __getattr__(self, name):
            assert name == "Visible"
            return 99

    # Sketch.Visible: manual member wrapped as a real property, not a method
    assert isinstance(getattr(api.STpreSketch, "Visible"), property)
    assert api.STpreSketch(FakeDispatch()).Visible == 99


def test_meshblock_generic_members_attached():
    # MeshBlock members beyond the typed wrappers come from API_CATALOG
    for name in ("GetDependentBlockArray", "GetNumBlockArray"):
        assert hasattr(api.STpreMeshBlock, name)


def test_new_class_typed_getter_routes():
    class FakeDispatch:
        def __init__(self, ret):
            self._ret = ret

        def _FlagAsMethod(self, name):
            pass

        def __getattr__(self, name):
            def invoke(*args):
                return self._ret
            return invoke

    sentinel = object()
    doc = api.STpreDoc(FakeDispatch(sentinel))
    assert isinstance(doc.GetAirconModel(), api.STpreAirconModel)
    assert doc.GetAirconModel().raw is sentinel
    model = api.STpreModel(FakeDispatch(sentinel))
    assert isinstance(model.GetAirconModel(), api.STpreAirconModel)
    assert isinstance(model.GetGerberModel(), api.STpreGerberModel)
    fem = api.STpreFemodel(FakeDispatch(sentinel))
    assert isinstance(fem.GetModel(), api.STpreModel)
    pair = [object(), object()]
    vals = api.STpreFemodel(FakeDispatch(pair)).GetValueArray()
    assert len(vals) == 2
    assert all(isinstance(v, api.STpreValue) and v.raw is pair[i]
               for i, v in enumerate(vals))
