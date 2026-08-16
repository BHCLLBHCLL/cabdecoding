"""R10 WindTool 前置接口测试 — 16 风向 / Weibull / info / 幂律 / 工具定位。"""
from __future__ import annotations

from pathlib import Path

import pytest

import cab_tools
import windtool
from windtool import (
    COND_FREE,
    COND_IN,
    COND_INIT_U,
    COND_INIT_V,
    COND_OUT,
    WIND_DIRECTIONS,
    build_windtool_info,
    default_weibull,
    load_weibull_table,
    power_law_params,
    wind_direction_boundary,
    wind_theta,
)


def test_wind_theta_16_directions():
    assert wind_theta(1) == 202.5
    assert wind_theta(5) == 292.5
    assert wind_theta(8) == 0.0
    assert wind_theta(12) == 90.0
    assert wind_theta(16) == 180.0
    for i in range(1, 17):
        t = wind_theta(i)
        assert 0.0 <= t < 360.0
    assert wind_theta(2) - wind_theta(1) == 22.5
    with pytest.raises(ValueError):
        wind_theta(0)
    with pytest.raises(ValueError):
        wind_theta(17)


def test_default_weibull_tokyo():
    table = default_weibull()
    assert len(table) == 16
    assert list(table) == WIND_DIRECTIONS
    assert table["NNE"] == pytest.approx((4.270, 5.948, 4.416))
    assert table["N"] == pytest.approx((9.061, 6.961, 2.882))
    assert sum(t[0] for t in table.values()) == pytest.approx(100.0, abs=1e-6)


_CSV_TEXT = (
    "POINT,Tokyo\n"
    "DIRECTION,NNE,NE,ENE,E,ESE,SE,SSE,S,SSW,SW,WSW,W,WNW,NW,NNW,N\n"
    "FREQ,4.270,5.940,6.844,3.887,3.942,1.889,0.876,16.890,3.285,10.129,"
    "0.411,0.164,0.493,4.708,27.211,9.061\n"
    "CPARAM,5.948,5.975,5.891,5.756,5.468,4.983,4.673,6.312,6.915,7.309,"
    "5.078,8.042,6.345,7.797,7.556,6.961\n"
    "KPARAM,4.416,5.332,5.296,6.050,5.526,7.606,6.216,4.421,3.712,4.008,"
    "6.108,2.484,2.608,3.275,4.387,2.882\n"
    "POINT,Nagoya\n"
    "DIRECTION,NNE,NE,ENE,E,ESE,SE,SSE,S,SSW,SW,WSW,W,WNW,NW,NNW,N\n"
    "FREQ,1.861,1.040,1.095,0.219,0.602,4.489,12.291,10.813,2.327,1.615,"
    "1.177,1.506,16.151,21.272,15.412,8.130\n"
    "CPARAM,3.926,3.522,3.346,3.984,4.248,6.171,7.338,6.750,4.338,4.417,"
    "4.298,6.367,7.636,7.407,6.811,5.347\n"
    "KPARAM,3.599,4.892,8.453,3.235,2.023,2.219,2.438,4.035,5.815,3.748,"
    "2.873,4.220,4.803,3.652,4.076,3.413\n"
    "POINT,Osaka\n"
    "DIRECTION,NNE,NE,ENE,E,ESE,SE,SSE,S,SSW,SW,WSW,W,WNW,NW,NNW,N\n"
    "FREQ,17.520,5.365,4.270,1.615,0.931,0.712,0.438,0.493,1.779,13.633,"
    "19.491,12.757,2.053,3.011,6.953,8.979\n"
    "CPARAM,5.028,5.094,6.180,6.066,6.228,4.770,4.486,5.495,7.031,6.514,"
    "6.066,6.682,6.105,5.556,5.596,5.629\n"
    "KPARAM,4.314,4.033,3.656,3.509,4.589,2.623,2.575,2.618,2.415,3.464,"
    "4.257,4.000,2.959,4.349,5.308,4.189\n"
)


def test_load_weibull_table_csv_text():
    table = load_weibull_table(_CSV_TEXT)
    assert set(table) == {"Tokyo", "Nagoya", "Osaka"}
    assert table["Tokyo"]["NNE"] == pytest.approx((4.270, 5.948, 4.416))
    assert table["Nagoya"]["NNE"] == pytest.approx((1.861, 3.926, 3.599))
    assert table["Osaka"]["NNE"] == pytest.approx((17.520, 5.028, 4.314))
    assert table["Tokyo"] == default_weibull()


def test_load_weibull_table_from_path(tmp_path):
    p = tmp_path / "Weibull.csv"
    p.write_text(_CSV_TEXT, encoding="utf-8")
    table = load_weibull_table(p)
    assert set(table) == {"Tokyo", "Nagoya", "Osaka"}
    assert table["Tokyo"]["N"] == pytest.approx((9.061, 6.961, 2.882))


def test_build_windtool_info():
    flds = [f"C:/out/wind_{i}.fld" for i in range(1, 17)]
    info = build_windtool_info(
        flds, gust_factor="AUTO", boundary_velocity=3.0,
        reference_velocity=5.0)
    for section in ("INPUT_FLD_FILES", "GUST_FACTOR",
                    "REFERENCE_VELOCITY", "WEIBULL_PARAMETER"):
        assert section in info
    for p in flds:
        assert p in info
    assert info.endswith("/")
    assert info.encode("utf-8").decode("utf-8") == info

    lines = info.splitlines()
    assert lines.count("/") == 2
    assert "AUTO" in lines
    wb = lines.index("WEIBULL_PARAMETER")
    for ln in lines[wb + 1:wb + 4]:
        assert len(ln.split(",")) == 16
    fld_lines = lines[1:17]
    assert all(l.split(",", 1)[0] == str(i) for i, l in
               enumerate(fld_lines, 1))

    info2 = build_windtool_info(flds, gust_factor=2.0, reference_velocity=5.0)
    assert "AUTO" not in info2.splitlines()
    assert "2" in info2.splitlines()

    with pytest.raises(ValueError):
        build_windtool_info(flds[:15])
    with pytest.raises(ValueError):
        build_windtool_info(flds, gust_factor="AUTO", boundary_velocity=None)
    with pytest.raises(ValueError):
        build_windtool_info(flds, weibull=[(1.0, 2.0, 3.0)] * 15)


def test_wind_direction_boundary():
    b = wind_direction_boundary(0.0)
    assert b["xmin"] == COND_FREE and b["xmax"] == COND_FREE
    assert b["ymin"] == COND_IN and b["ymax"] == COND_OUT
    assert b["init_u"] is None and b["init_v"] == COND_INIT_V

    b = wind_direction_boundary(90.0)
    assert b["xmin"] == COND_IN and b["xmax"] == COND_OUT
    assert b["ymin"] == COND_FREE and b["ymax"] == COND_FREE
    assert b["init_u"] == COND_INIT_U and b["init_v"] is None

    b = wind_direction_boundary(180.0)
    assert b["xmin"] == COND_FREE and b["xmax"] == COND_FREE
    assert b["ymin"] == COND_OUT and b["ymax"] == COND_IN
    assert b["init_u"] is None and b["init_v"] == COND_INIT_V

    b = wind_direction_boundary(270.0)
    assert b["xmin"] == COND_OUT and b["xmax"] == COND_IN
    assert b["ymin"] == COND_FREE and b["ymax"] == COND_FREE
    assert b["init_u"] == COND_INIT_U and b["init_v"] is None

    b = wind_direction_boundary(45.0)
    assert b["xmin"] == COND_IN and b["xmax"] == COND_OUT
    assert b["ymin"] == COND_IN and b["ymax"] == COND_OUT
    assert b["init_u"] == COND_INIT_U and b["init_v"] == COND_INIT_V

    b = wind_direction_boundary(90.0, north_angle=45.0)
    assert b["xmin"] == COND_IN and b["xmax"] == COND_OUT
    assert b["ymin"] == COND_OUT and b["ymax"] == COND_IN

    b = wind_direction_boundary(360.0)
    assert b["ymin"] == COND_IN and b["ymax"] == COND_OUT


def test_power_law_params_defaults_and_validation():
    p = power_law_params()
    assert p["exponent"] == pytest.approx(3.7037)
    assert p["ref_vel"] == pytest.approx(5.0)
    assert p["grd_hei"] == pytest.approx(0.0)
    assert p["ref_hei"] == pytest.approx(74.5)
    assert p["turb_type"] == "zg"
    assert p["ke_param1"] == 550
    assert p["ke_param2"] == 0
    assert p["north_angle"] == 0.0
    assert p["roughness"] == 0.0

    bad = [
        dict(exponent=0), dict(exponent=-1),
        dict(ref_vel=0), dict(ref_vel=-2),
        dict(ref_hei=0), dict(ref_hei=-1),
        dict(grd_hei=-1),
        dict(ke_param1=-1), dict(ke_param2=-1),
        dict(turb_type=""), dict(turb_type=123),
    ]
    for kw in bad:
        with pytest.raises(ValueError):
            power_law_params(**kw)


def test_find_cradle_tool_never_raises():
    for name in ("stpre", "stsolver", "windtool", "heatpathview",
                 "picls", "scconverter", "stpost"):
        r = cab_tools.find_cradle_tool(name)
        assert r is None or isinstance(r, Path)
    assert cab_tools.find_cradle_tool("does_not_exist") is None


def test_stpre_doc_windtool_wrappers_exist():
    import cab_stpre_api
    doc_methods = vars(cab_stpre_api.STpreDoc)
    for name in ("GetUnit", "SetNorthAngle", "SetFluxPower", "SetFluxPower2"):
        assert name in doc_methods, name
        assert name in cab_stpre_api.API_CATALOG["Doc_high_value"]


def test_stpre_doc_windtool_call_passthrough():
    import cab_stpre_api

    class _Flag:
        def __init__(self):
            self.calls = []

        def _FlagAsMethod(self, name):
            return self

        def __getattr__(self, name):
            def _method(*args):
                self.calls.append((name, args))
                return "ok"
            return _method

    raw = _Flag()
    doc = cab_stpre_api.STpreDoc(raw)
    assert doc.GetUnit("length") == "ok"
    assert doc.SetNorthAngle(12.5) == "ok"
    assert doc.SetFluxPower("n", 1.0) == "ok"
    assert doc.SetFluxPower2(
        "n", 5.0, "N", 202.5, 3.7037, 0.0, 74.5, 0.0, "zg", 550, 0) == "ok"

    assert raw.calls[0] == ("GetUnit", ("length",))
    assert raw.calls[1] == ("SetNorthAngle", (12.5,))
    assert raw.calls[2] == ("SetFluxPower", ("n", 1.0))
    assert raw.calls[3][0] == "SetFluxPower2"
    assert len(raw.calls[3][1]) == 11


def test_power_law_xml_format_probe():
    """COM 探针(tools/probe_windtool.py)实证的 power-law 入口 XML 落盘格式。

    实证结论：``SetFluxPower2`` 落盘为 ``<value type="flux">`` + ``<kind>
    power</kind>``；``power_pow`` 存幂指数**倒数**（3.7037 → 0.27）；
    高度/长度按米存（文档单位 mm 时 74.5mm=0.0745m、550mm=0.55m）；
    ``turbulence_type`` = "ke_power_zg"；条件挂接为 ``<condition><region
    type="face_list">Xmin</region><value>Tool_Flux1_</value></condition>``。
    """
    import xml.etree.ElementTree as ET

    p = power_law_params()
    theta = wind_theta(1)  # 202.5

    value = ET.Element("value", {"type": "flux"})
    ET.SubElement(value, "name").text = COND_IN
    ET.SubElement(value, "kind").text = "power"
    ET.SubElement(value, "power_velocity", {"unit": "m/s"}).text = \
        f"{p['ref_vel']:g}"
    ET.SubElement(value, "power_pow").text = f"{1.0 / p['exponent']:g}"
    ET.SubElement(value, "power_height", {"unit": "m"}).text = \
        "0,0.0745,0.55"  # grd_hei=0, ref_hei=74.5mm, ke_param1=550mm
    ET.SubElement(value, "power_angle").text = f"{theta:g}"
    ET.SubElement(value, "power_angle_kind").text = "0"
    ET.SubElement(value, "turbulence_type").text = "ke_power_zg"

    # XML 往返（序列化 → 解析）
    back = ET.fromstring(ET.tostring(value, encoding="utf-8"))
    assert back.tag == "value" and back.attrib["type"] == "flux"
    assert back.findtext("name") == COND_IN
    assert back.findtext("kind") == "power"
    assert back.findtext("power_velocity") == "5"
    # power_pow 是幂指数的倒数
    assert float(back.findtext("power_pow")) == pytest.approx(
        1.0 / p["exponent"])
    assert back.findtext("power_height") == "0,0.0745,0.55"
    assert back.findtext("power_angle") == "202.5"
    assert back.findtext("turbulence_type") == "ke_power_zg"
