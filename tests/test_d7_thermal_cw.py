"""D7 thermal part attrs + Condition Wizard deeper write-back."""

from __future__ import annotations

from cab_parts import register_primitive, tess_for_spec
from cabxml import StpreModel, _first, new_stpre_bytes, parse_stpre


def _model() -> StpreModel:
    return StpreModel(parse_stpre(new_stpre_bytes()))


def test_peltier_registers_thermal_fields():
    m = _model()
    assert register_primitive(
        m, name="Peltier1", kind="peltier",
        params={
            "base": (0, 0, 0), "size": (20, 20, 4),
            "peltier_current": 2.5, "peltier_delta_t": 35.0,
            "peltier_hot_face": "+Z",
            "heat_source": 10.0, "heat_source_unit": "W",
            "initial_temperature": 25.0,
            "monitor": True, "virtual": False,
        },
        material="Solid", attribute="Solid",
        monitor=True, virtual=False)
    el = m.find_part("Peltier1")
    assert el is not None
    assert float((_first(el, "peltier_current").text or "").strip()) == 2.5
    assert float((_first(el, "heat_source").text or "").strip()) == 10.0
    assert (_first(el, "monitor").text or "").strip() == "T"


def test_two_resistor_and_fin_fields():
    m = _model()
    assert register_primitive(
        m, name="TR1", kind="two_resistor",
        params={"base": (0, 0, 0), "size": (10, 10, 2),
                "rjc": 1.2, "rjb": 4.5, "package_power": 3.0},
        attribute="Solid")
    el = m.find_part("TR1")
    assert float((_first(el, "rjc").text or "").strip()) == 1.2
    assert register_primitive(
        m, name="Fin1", kind="plate_fin",
        params={"base": (0, 0, 0), "size": (40, 20, 10),
                "fin_count": 8, "fin_thickness": 0.8},
        attribute="Solid")
    t = tess_for_spec("plate_fin", {
        "base": (0, 0, 0), "size": (40, 20, 10),
        "fin_count": 8, "fin_thickness": 0.8})
    assert t.triangles.size > 0
    el2 = m.find_part("Fin1")
    assert float((_first(el2, "fin_thickness").text or "").strip()) == 0.8


def test_fan_condition_extras_persisted():
    m = _model()
    assert register_primitive(
        m, name="Fan1", kind="fan",
        params={
            "center": (0, 0, 0), "base": (-5, -5, -1), "size": (10, 10, 0),
            "direction": "+Z", "outer_radius": 5.0, "inner_radius": 1.0,
            "thickness": 2.0, "flow_mode": "pq",
            "pq_curve": "@T:pq-curve1",
            "setting_location": "boundary",
            "inflow_temperature": 22.0,
            "external_pressure": 101325.0,
            "flow_straightening": True,
            "straighten_by": "panel",
            "virtual": True,
        },
        attribute="Fan", virtual=True)
    el = m.find_part("Fan1")
    assert (_first(el, "pq_curve").text or "").strip() == "@T:pq-curve1"
    assert float((_first(el, "inflow_temperature").text or "").strip()) == 22.0
    assert (_first(el, "flow_straightening").text or "").strip() == "T"
    assert (_first(el, "virtual").text or "").strip() == "T"


def test_cw_humidity_porous_rad_writeback():
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    from cab_cwizard_pages import (
        _CwHumidityPage, _CwPorousPage, _CwRadiationGroupingPage,
    )
    m = _model()
    # seed a solid part for rad grouping / porous bind
    register_primitive(
        m, name="Box1", kind="cube",
        params={"base": (0, 0, 0), "size": (10, 10, 10)},
        attribute="Solid")

    hum = _CwHumidityPage(m)
    hum.enable.setChecked(True)
    hum.rh.setValue(55.0)
    hum.bind_domain.setChecked(True)
    hum.apply()
    assert m.analysis_set_value("humidity") == "1"
    assert m.find_value("Humidity_RH_default") is not None
    assert m.condition_value("analysis", m.domain_name() or "Domain") \
        == "Humidity_RH_default"

    por = _CwPorousPage(m)
    por.enable.setChecked(True)
    por.alpha.setValue(100.0)
    por.beta.setValue(0.5)
    i = por.target_part.findText("Box1")
    assert i >= 0
    por.target_part.setCurrentIndex(i)
    por.apply()
    assert m.analysis_set_value("porous_media") == "1"
    assert m.find_value("Porous_default") is not None
    assert m.condition_value("parts", "Box1") == "Porous_default"

    rad = _CwRadiationGroupingPage(m)
    rad.enable.setChecked(True)
    rad.group_num.setValue(3)
    rad.apply_all.setChecked(True)
    rad.apply()
    el = m.find_part("Box1")
    assert (_first(el, "rad_group_num").text or "").strip() == "3"


def test_attribute_panel_condition_values():
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    from cab_dialogs import AttributePanel
    p = AttributePanel(
        None, attributes=["Solid", "Obstacle"],
        heat_source=True, virtual_part=True, full_stpre=True)
    p.init_temp_chk.setChecked(True)
    p.init_temp.setValue(30.0)
    p.heat_chk.setChecked(True)
    p.heat.setValue(5.0)
    vals = p.condition_values()
    assert vals["initial_temperature"] == 30.0
    assert vals["heat_source"] == 5.0
    assert vals["monitor"] is False or isinstance(vals["monitor"], bool)
