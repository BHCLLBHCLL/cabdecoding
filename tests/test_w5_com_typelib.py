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
    assert rows["TOTAL"]["manual"] == 1404
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
