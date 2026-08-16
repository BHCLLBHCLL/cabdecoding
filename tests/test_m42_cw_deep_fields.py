"""M42: Condition Wizard 深度字段页（R8-A）。

五类深字段的 XML 往返与 UI load/commit 往返：
1. Radiation Monte Carlo（<analysis_set>/<radiation> 子元素）
2. Free surface MARS/VOF（<analysis_etc>/<free_surf> 属性）
3. Particle 完整模型（<value type='particle'> kv 扩展）
4. Reaction 多步速率（<value type='reaction'> Reaction_step{N}）
5. Output series 间隔表（analysis_set timeseries_interval/fields）
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("cab_gui")


def _model():
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain()
    return m


def _reserialize(model):
    """serialize → parse 重建模型（验证序列化往返稳定）。"""
    from cabxml import StpreModel, parse_stpre
    return StpreModel(parse_stpre(model.doc.serialize()))


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


# ---------------------------------------------------------------------------
# 1. Radiation Monte Carlo / VF 深字段
# ---------------------------------------------------------------------------

def test_radiation_xml_roundtrip():
    m = _model()
    assert m.set_radiation_type("mc")
    for tag, val in (("max_particle", "50000"),
                     ("max_reflection", "200"),
                     ("smrt_rays", "30000"),
                     ("max_group_num", "4000"),
                     ("calc_cycle", "10"),
                     ("solver_eps", "0.001"),
                     ("space_cycle", "5")):
        assert m.set_radiation_param(tag, val)
    m2 = _reserialize(m)
    assert m2.radiation_type() == "mc"
    assert m2.radiation_param("max_particle") == "50000"
    assert m2.radiation_param("max_reflection") == "200"
    assert m2.radiation_param("smrt_rays") == "30000"
    assert m2.radiation_param("calc_cycle") == "10"
    assert m2.radiation_param("solver_eps") == "0.001"
    assert m2.radiation_param("space_cycle") == "5"
    # 未知子元素容错：不影响已有参数读取
    assert m2.radiation_param("nonexistent", "dft") == "dft"


def test_radiation_page_ui_roundtrip(qapp):
    from cab_cwizard_pages import _CwRadiationGroupingPage
    m = _model()
    page = _CwRadiationGroupingPage(m)
    page.rad_type.setCurrentIndex(page.rad_type.findData("mc"))
    page.mc_rays.setValue(50000)
    page.mc_reflect.setValue(200)
    page.smrt_rays.setValue(30000)
    page.calc_cycle.setValue(10)
    page.solver_eps.setValue(0.001)
    page.space_cycle.setValue(5)
    page.apply()
    assert m.radiation_type() == "mc"
    assert m.radiation_param("max_particle") == "50000"
    assert m.radiation_param("max_reflection") == "200"
    assert m.radiation_param("smrt_rays") == "30000"
    assert m.radiation_param("calc_cycle") == "10"
    assert m.radiation_param("solver_eps") == "0.001"
    assert m.radiation_param("space_cycle") == "5"
    # 重建页面：控件从 XML 恢复
    page2 = _CwRadiationGroupingPage(_reserialize(m))
    assert page2.rad_type.currentData() == "mc"
    assert page2.mc_rays.value() == 50000
    assert page2.mc_reflect.value() == 200
    assert page2.calc_cycle.value() == 10


# ---------------------------------------------------------------------------
# 2. Free surface MARS/VOF 深字段
# ---------------------------------------------------------------------------

def test_free_surf_xml_roundtrip():
    m = _model()
    assert m.set_free_surf_attr("type", "vof")
    assert m.set_free_surf_attr("cutoff", "0.0002,0.5,1e-06")
    assert m.set_free_surf_attr("surface_set", "2")
    assert m.set_free_surf_attr("flow_list", "4")
    assert m.set_free_surf_attr("hydro_pres", "1")
    m2 = _reserialize(m)
    assert m2.free_surf_type() == "vof"
    assert m2.free_surf_attr("cutoff") == "0.0002,0.5,1e-06"
    assert m2.free_surf_attr("surface_set") == "2"
    assert m2.free_surf_attr("flow_list") == "4"
    assert m2.free_surf_attr("hydro_pres") == "1"
    # MARS 侧属性同样稳定
    assert m.set_free_surf_attr("fractional_step", "8", type_="mars")
    m3 = _reserialize(m)
    assert m3.free_surf_attr("fractional_step") == "8"


def test_evaporation_page_free_surf_roundtrip(qapp):
    from cab_cwizard_pages import _CwEvaporationPage
    m = _model()
    page = _CwEvaporationPage(m)
    page.fs_enable.setChecked(True)
    page.fs_method.setCurrentIndex(page.fs_method.findData("vof"))
    page.fs_contact.setValue(45)
    page.fs_cutoff.setValue(2e-4)
    page.fs_check_cycle.setValue(7)
    page.fs_frac_step.setValue(8)
    page.fs_flow_list.setValue(4)
    page.fs_hydro.setCurrentIndex(1)
    page.apply()
    assert m.free_surf_type() == "vof"
    assert m.free_surf_attr("contact") == "45"
    # cutoff 三元组：仅第 1 值被替换，后两值保留样本默认
    assert m.free_surf_attr("cutoff") == "0.0002,0.5,1e-06"
    assert m.free_surf_attr("vof_list_cycle") == "7"
    assert m.free_surf_attr("fractional_step") == "8"
    assert m.free_surf_attr("flow_list") == "4"
    assert m.free_surf_attr("hydro_pres") == "1"
    # 重建页面：控件从 XML 恢复
    page2 = _CwEvaporationPage(_reserialize(m))
    assert page2.fs_enable.isChecked()
    assert page2.fs_method.currentData() == "vof"
    assert page2.fs_contact.value() == 45
    assert page2.fs_cutoff.value() == pytest.approx(2e-4)
    assert page2.fs_frac_step.value() == 8


def test_evaporation_page_free_surf_disable_removes(qapp):
    from cab_cwizard_pages import _CwEvaporationPage
    m = _model()
    m.set_free_surf_attr("type", "mars")
    page = _CwEvaporationPage(m)
    page.enable.setChecked(False)   # 蒸发关闭不影响自由面
    page.fs_enable.setChecked(False)
    page.apply()
    assert m.analysis_etc_section("free_surf") is None


# ---------------------------------------------------------------------------
# 3. Particle 完整模型深字段
# ---------------------------------------------------------------------------

def test_particle_deep_roundtrip(qapp):
    from cab_cwizard_pages import _CwParticlePage
    m = _model()
    page = _CwParticlePage(m)
    page.dia_dist.setCurrentIndex(page.dia_dist.findData("1"))  # Log-normal
    page.dia_min.setValue(1e-6)
    page.dia_max.setValue(2e-4)
    page.dia_mean.setValue(5e-5)
    page.dia_sigma.setValue(0.42)
    page.drag.setCurrentIndex(page.drag.findData("2"))          # Newton
    page.restitution_n.setValue(0.8)
    page.restitution_t.setValue(0.7)
    page.turb_diff.setCurrentIndex(1)                           # random walk
    page.turb_tries.setValue(20)
    page.apply()
    pf = m.value_fields("particle", "Particle_default")
    assert pf["particle_distribution"] == "1"
    assert float(pf["particle_dia_min"]) == pytest.approx(1e-6)
    assert float(pf["particle_dia_max"]) == pytest.approx(2e-4)
    assert float(pf["particle_sigma"]) == pytest.approx(0.42)
    assert pf["drag_model"] == "2"
    assert float(pf["wall_restitution_normal"]) == pytest.approx(0.8)
    assert float(pf["wall_restitution_tangent"]) == pytest.approx(0.7)
    assert pf["turbulent_diffusion"] == "1"
    assert pf["turbulent_tries"] == "20"
    # 序列化往返 + 重建页面恢复
    page2 = _CwParticlePage(_reserialize(m))
    assert page2.dia_dist.currentData() == "1"
    assert page2.drag.currentData() == "2"
    assert page2.dia_min.value() == pytest.approx(1e-6)
    assert page2.restitution_n.value() == pytest.approx(0.8)
    assert page2.turb_tries.value() == 20


def test_particle_page_defaults(qapp):
    from cab_cwizard_pages import _CwParticlePage
    m = _model()
    page = _CwParticlePage(m)
    assert page.dia_dist.currentData() == "0"       # Uniform
    assert page.drag.currentData() == "3"           # Schiller-Naumann
    assert page.turb_diff.currentData() == "1"      # random walk 默认开
    page.apply()
    pf = m.value_fields("particle", "Particle_default")
    assert pf["particle_distribution"] == "0"
    assert pf["drag_model"] == "3"
    # 未知旧字段容错：预置未知 kv 不影响读写
    m.upsert_value("particle", "Particle_default",
                   [("legacy_unknown", "x", None)])
    page3 = _CwParticlePage(_reserialize(m))
    page3.apply()
    assert m.value_fields("particle", "Particle_default")[
        "legacy_unknown"] == "x"


# ---------------------------------------------------------------------------
# 4. Reaction 多步速率深字段
# ---------------------------------------------------------------------------

def test_reaction_steps_roundtrip(qapp):
    from PyQt5.QtWidgets import QTableWidgetItem
    from cab_cwizard_pages import _CwReactionPage
    m = _model()
    page = _CwReactionPage(m)
    # 3 步：A / n / E / Tref / order（Arrhenius 三参数 + 级数）
    rows = [("1.5", "0", "1e4", "0", "1"),
            ("2.5", "0.5", "2e4", "300", "2"),
            ("3.5", "1", "3e4", "0", "1.5")]
    for r in rows:
        page._step_insert(page.step_table.rowCount(),
                          *[float(x) for x in r])
    page.apply()
    names = []
    for v in m.values_of_type("reaction"):
        n = next((c for c in v if c.tag == "name"), None)
        name = (n.text or "").strip() if n is not None else ""
        if name.startswith("Reaction_step"):
            names.append(name)
    assert len(names) == 3
    f2 = m.value_fields("reaction", "Reaction_step2")
    assert float(f2["rate_constant"]) == pytest.approx(2.5)
    assert float(f2["temp_exponent"]) == pytest.approx(0.5)
    assert float(f2["activation_energy"]) == pytest.approx(2e4)
    assert float(f2["ref_temp"]) == pytest.approx(300)
    assert float(f2["reaction_order"]) == pytest.approx(2)
    # 步数减少到 2：多余第 3 步应被删除
    page._step_remove_last()
    page.apply()
    assert m.value_fields("reaction", "Reaction_step3") == {}
    assert m.value_fields("reaction", "Reaction_step2")["rate_constant"] \
        == "2.5"


def test_reaction_page_load_from_xml(qapp):
    from cab_cwizard_pages import _CwReactionPage
    m = _model()
    m.upsert_value("reaction", "Reaction_step1",
                   [("rate_constant", "1.5", "1/s"),
                    ("temp_exponent", "0", None),
                    ("activation_energy", "1e4", "J/mol"),
                    ("ref_temp", "0", "K"),
                    ("reaction_order", "1", None)])
    m.upsert_value("reaction", "Reaction_step2",
                   [("rate_constant", "9.9", "1/s"),
                    ("temp_exponent", "0", None),
                    ("activation_energy", "0", "J/mol"),
                    ("ref_temp", "0", "K"),
                    ("reaction_order", "1", None)])
    page = _CwReactionPage(_reserialize(m))
    assert page.step_table.rowCount() == 2
    assert page.step_table.item(0, 0).text() == "1.5"
    assert page.step_table.item(1, 0).text() == "9.9"


# ---------------------------------------------------------------------------
# 5. Output series 间隔表深字段
# ---------------------------------------------------------------------------

def test_output_series_xml_roundtrip():
    m = _model()
    m.set_analysis_set_value("timeseries_interval", "25")
    m.set_analysis_set_value(
        "timeseries_fields", "Temperature;Pressure")
    m2 = _reserialize(m)
    assert m2.analysis_set_value("timeseries_interval") == "25"
    assert m2.analysis_set_value("timeseries_fields") \
        == "Temperature;Pressure"


def test_output_series_page_ui_roundtrip(qapp):
    from PyQt5.QtWidgets import QTableWidgetItem
    from cab_cwizard_pages import _CwOutputSeriesPage
    m = _model()
    page = _CwOutputSeriesPage(m)
    page.ts_interval.setValue(25)
    # 只保留前两个字段输出，其余 No
    for i in range(page.ts_fields.rowCount()):
        page.ts_fields.setItem(
            i, 1, QTableWidgetItem("Yes" if i < 2 else "No"))
    page.apply()
    assert m.analysis_set_value("timeseries_interval") == "25"
    assert m.analysis_set_value("timeseries_fields") \
        == "Temperature;Pressure"
    # 重建页面：间隔恢复、字段表 Yes/No 恢复
    page2 = _CwOutputSeriesPage(_reserialize(m))
    assert page2.ts_interval.value() == 25
    assert page2.ts_fields.item(0, 1).text() == "Yes"
    assert page2.ts_fields.item(2, 1).text() == "No"
