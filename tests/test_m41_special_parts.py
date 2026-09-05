"""M41: special-part parameter surfaces — R7.

Covers the cabxml ``part_params`` / ``set_part_params`` API for the five
special parts (AC Unit / Peltier / Linear Diffuser / Card Guide /
Heat Pipe), the PartDialog ``Parameters`` panel write-back and the
PELTIER_OUT / PELTIER_SET cards in the SDAT exporter (official
exA22-2 evidence; the other four kinds have no verified card syntax
and must not be emitted).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

import pytest

from cabxml import (PropertyModel, _first, new_property_bytes,
                    new_stpre_bytes, parse_property, parse_stpre,
                    StpreModel)

ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _model(*specs) -> StpreModel:
    """Domain + parts given as ``(name, kind)`` (base/size for exporters)."""
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(0, 0, 0), size=(100, 100, 100), material="air")
    m.ensure_domain_faces()
    for name, kind in specs:
        m.add_part(name=name, kind=kind, attribute="obstacle")
        el = m.find_part(name)
        for tag, text in (("base", "10,10,10"), ("size", "30,30,30")):
            e = ET.SubElement(el, tag)
            e.text = f" {text} "
            e.tail = "\n         "
    return m


# -- cabxml API: peltier -------------------------------------------------------

def test_fan_family_params_roundtrip():
    # R3.5a: fan/axial_fan/blower_fan parameter faces (r1/r2/thickness).
    model = _model()
    for kind, params in (
            ("fan", {"r1": 5.0, "r2": 20.0, "thickness": 5.0,
                     "axis": "+Z"}),
            ("axial_fan", {"r1": 4.0, "r2": 18.0, "t1": 5.0, "t2": 5.0,
                          "axis": "+X"}),
            ("blower_fan", {"r1": 6.0, "r2": 22.0, "thickness": 8.0,
                           "axis": "-Z"}),
            ("pin_fin", {"f1": 1.5, "f2": 1.5, "h1": 5.0, "h2": 5.0,
                         "n1": 10, "n2": 10, "axis": "+Y"}),
            ("slit_punching", {"plane": "+X", "thick": 1.0, "count": 8}),
            ("anemostat", {"mode": "horizontal", "type": "round"})):
        model.add_part(name="F", kind=kind, attribute="solid")
        assert model.set_part_params("F", params)
        got = model.part_params("F")
        assert got is not None
        for k, v in params.items():
            assert got.get(k) == v, (kind, k, got)
        model.delete_part("F")

def test_peltier_params_roundtrip():
    m = _model(("Peltier1", "peltier"))
    # add_part 默认写入 def_axis=+Z，识别为专用件即返回 dict
    assert m.part_params("Peltier1") == {"def_axis": "+Z"}
    assert m.set_part_params("Peltier1", {
        "thick": (2.0, 2.0),
        "paramV": (12.0, 7.7, 8.8, 9.9),
        "paramA": (1.5, 1.1, 2.2, 3.3, 27.0),
        "paramQ": (4.0, 4.4, 5.5, 6.6, 47.0),
        "paramT": (60.0, 3.3),
        "def_axis": "+Z",
    })
    p = m.part_params("Peltier1")
    assert p["thick"] == [2.0, 2.0]
    assert p["paramV"] == [12.0, 7.7, 8.8, 9.9]
    assert p["paramA"] == [1.5, 1.1, 2.2, 3.3, 27.0]
    assert p["paramQ"] == [4.0, 4.4, 5.5, 6.6, 47.0]
    assert p["paramT"] == [60.0, 3.3]
    assert p["def_axis"] == "+Z"
    # XML 落盘格式与探针实证一致（thick 带 unit="mm"）
    el = m.find_part("Peltier1")
    assert _first(el, "thick").attrib["unit"] == "mm"
    assert (_first(el, "paramV").text or "").strip() == "12,7.7,8.8,9.9"
    # serialize 往返稳定
    again = StpreModel(parse_stpre(m.doc.serialize()))
    p2 = again.part_params("Peltier1")
    assert p2["paramV"] == [12.0, 7.7, 8.8, 9.9]
    assert p2["paramA"] == [1.5, 1.1, 2.2, 3.3, 27.0]
    assert p2["def_axis"] == "+Z"


def test_card_guide_params_roundtrip():
    m = _model(("CardGuide1", "card_guide"))
    assert m.set_part_params("CardGuide1", {
        "fin": 1.5, "space": (3.0, 3.0), "depth": (2.0, 2.0),
        "nfin": 8, "row_axis": "+X", "def_plane": "+Z"})
    p = m.part_params("CardGuide1")
    assert p["fin"] == 1.5
    assert p["space"] == [3.0, 3.0]
    assert p["depth"] == [2.0, 2.0]
    assert p["nfin"] == 8 and isinstance(p["nfin"], int)
    assert p["row_axis"] == "+X"
    assert p["def_plane"] == "+Z"
    # serialize 往返
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("CardGuide1")["nfin"] == 8
    # 部分写入：只改 nfin，其余字段不动
    assert m.set_part_params("CardGuide1", {"nfin": 12})
    p = m.part_params("CardGuide1")
    assert p["nfin"] == 12
    assert p["fin"] == 1.5
    assert p["space"] == [3.0, 3.0]


def test_ac_unit_params_roundtrip():
    # 部件级 AC 参数按手册降级定义，镜像条件模型
    # <analysis_air_etc><aircon> 的字段名（探针实证）
    m = _model(("ACUnit1", "ac_unit"))
    assert m.set_part_params("ACUnit1", {
        "ac_model": "ACModel1", "operation_type": "cooling",
        "capability": 2500.0, "flow_rate": 15.0,
        "t_limit_type": "minmax", "tmin": 16.0, "tmax": 30.0})
    p = m.part_params("ACUnit1")
    assert p["ac_model"] == "ACModel1"
    assert p["operation_type"] == "cooling"
    assert p["capability"] == 2500.0
    assert p["flow_rate"] == 15.0
    assert p["t_limit_type"] == "minmax"
    assert p["tmin"] == 16.0
    assert p["tmax"] == 30.0
    el = m.find_part("ACUnit1")
    assert _first(el, "capability").attrib["unit"] == "W"
    assert _first(el, "flow_rate").attrib["unit"] == "m3/s"
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("ACUnit1")["capability"] == 2500.0


def test_diffuser_params_flux_mirror():
    m = _model(("Diffuser1", "diffuser"))
    assert m.set_part_params("Diffuser1", {
        "supply_air_angle": 30.0,
        "supply_flow_rate": 0.012,
        "inflow_temperature": 18.5})
    # 角度为部件子元素；风量/温度镜像到绑定的 outlet flux 值（实证存储位）
    el = m.find_part("Diffuser1")
    assert float(_first(el, "supply_air_angle").text) == 30.0
    val = m._part_flux_value("Diffuser1")
    assert val is not None
    assert (_first(val, "kind").text or "").strip() == "outlet"
    assert float(_first(val, "flow_rate").text) == pytest.approx(0.012)
    assert float(_first(val, "temperature").text) == 18.5
    assert m.condition_value("parts", "Diffuser1") == "_outlet1_flux"
    # 合并读回
    p = m.part_params("Diffuser1")
    assert p["supply_air_angle"] == 30.0
    assert p["supply_flow_rate"] == pytest.approx(0.012)
    assert p["inflow_temperature"] == 18.5
    # 更新风量幂等复用同一值（不产生第二个 flux 值）
    assert m.set_part_params("Diffuser1", {"supply_flow_rate": 0.02})
    assert m.condition_value("parts", "Diffuser1") == "_outlet1_flux"
    assert m.part_params("Diffuser1")["supply_flow_rate"] == pytest.approx(0.02)
    flux_vals = [v for v in m.values()
                 if v.attrib.get("type") == "flux" and v is not val]
    assert not flux_vals
    # serialize 往返 + 更名保持 flux 绑定
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("Diffuser1")["supply_flow_rate"] \
        == pytest.approx(0.02)
    assert again.rename_part("Diffuser1", "Supply")
    p2 = again.part_params("Supply")
    assert p2 is not None and p2["inflow_temperature"] == 18.5
    assert again.condition_value("parts", "Supply") == "_outlet1_flux"


def test_ac_unit_extra_fields_roundtrip():
    # P4-1: ac_unit 参数面剩余字段逐字段往返（ac_kind/flow_type/h_limit_type）
    m = _model(("ACUnit1", "ac_unit"))
    assert m.set_part_params("ACUnit1", {
        "ac_model": "ACModel1", "ac_kind": 2,
        "operation_type": "cooling", "flow_type": "area",
        "capability": 2500.0, "flow_rate": 15.0,
        "t_limit_type": "minmax", "tmin": 16.0, "tmax": 30.0,
        "h_limit_type": "no"})
    p = m.part_params("ACUnit1")
    assert p["ac_kind"] == 2 and isinstance(p["ac_kind"], int)
    assert p["flow_type"] == "area"
    assert p["h_limit_type"] == "no"
    # 部分写入：只改 ac_kind，其余字段不动
    assert m.set_part_params("ACUnit1", {"ac_kind": 3})
    p = m.part_params("ACUnit1")
    assert p["ac_kind"] == 3
    assert p["flow_type"] == "area"
    assert p["capability"] == 2500.0
    # serialize 往返
    again = StpreModel(parse_stpre(m.doc.serialize()))
    p2 = again.part_params("ACUnit1")
    assert p2["ac_kind"] == 3
    assert p2["flow_type"] == "area"
    assert p2["h_limit_type"] == "no"


def test_delphi_params_nodes_roundtrip():
    # P4-1: delphi 参数面 = 节点网络（<thermal_node no>/name/resistance,
    # unit C/W）——空字段表，节点经 set/read 专用路径
    m = _model(("Delphi1", "delphi"))
    # 无节点：返回空 dict
    assert m.part_params("Delphi1") == {}
    assert m.set_part_params("Delphi1", {"nodes": [
        ("Top", 2.5), ("Bottom", 3.0), ("Leads", 8.0), ("Sides", 12.0)]})
    p = m.part_params("Delphi1")
    assert p["nodes"] == [("Top", 2.5), ("Bottom", 3.0),
                          ("Leads", 8.0), ("Sides", 12.0)]
    el = m.find_part("Delphi1")
    nodes = el.findall("thermal_node")
    assert [n.attrib.get("no") for n in nodes] == ["1", "2", "3", "4"]
    assert _first(nodes[0], "resistance").attrib["unit"] == "C/W"
    # serialize 往返
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("Delphi1")["nodes"] == [
        ("Top", 2.5), ("Bottom", 3.0), ("Leads", 8.0), ("Sides", 12.0)]
    # 重写节点集：旧节点清空后重建
    assert m.set_part_params("Delphi1", {"nodes": [("Die", 1.2)]})
    p = m.part_params("Delphi1")
    assert p["nodes"] == [("Die", 1.2)]
    # 未知字段仍拒绝
    assert m.set_part_params("Delphi1", {"voltage": 12.0}) is False


def test_heat_pipe_params_roundtrip():
    m = _model(("HeatPipe1", "heat_pipe"), ("Sink", "cube"))
    assert m.set_part_params("HeatPipe1", {
        "cooling_part": "HeatPipe1", "heat_release_part": "Sink",
        "thermal_resistance": 0.05, "max_heat_transport": 50.0})
    p = m.part_params("HeatPipe1")
    assert p["cooling_part"] == "HeatPipe1"
    assert p["heat_release_part"] == "Sink"
    assert p["thermal_resistance"] == 0.05
    assert p["max_heat_transport"] == 50.0
    el = m.find_part("HeatPipe1")
    assert _first(el, "thermal_resistance").attrib["unit"] == "K/W"
    assert _first(el, "max_heat_transport").attrib["unit"] == "W"
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("HeatPipe1")["thermal_resistance"] == 0.05


def test_params_validation():
    m = _model(("Box", "cube"), ("Peltier1", "peltier"))
    # 非专用件：读 None、写 False
    assert m.part_params("Box") is None
    assert m.set_part_params("Box", {"thick": (1.0, 1.0)}) is False
    # 未知部件
    assert m.part_params("Nope") is None
    assert m.set_part_params("Nope", {"thick": (1.0, 1.0)}) is False
    # 未知字段拒绝
    assert m.set_part_params("Peltier1", {"voltage": 12.0}) is False
    # 官方 arity 可变（exA22-2: paramT 4 值）——thick 放宽为 csv；
    # 拒绝路径由未知字段验证（上方 voltage 断言）
    assert m.set_part_params("Peltier1", {"thick": (1.0, 1.0, 1.0)}) is True
    assert m.part_params("Peltier1")["thick"] == [1.0, 1.0, 1.0]


# -- PartDialog Parameters 面板 -------------------------------------------------

def test_part_dialog_special_params_writeback(qapp):
    import cab_dialogs
    m = _model(("Peltier1", "peltier"), ("Box", "cube"))
    dlg = cab_dialogs.PartDialog(m, None, "Peltier1")
    assert dlg.special._kind == "peltier"
    # 普通件不识别参数组
    dlg_box = cab_dialogs.PartDialog(m, None, "Box")
    assert dlg_box.special._kind is None
    dlg_box._on_apply()  # 无参数组时提交不受影响

    dlg.special.edits[("thick", 0)].setValue(2.5)
    dlg.special.edits[("paramV", 0)].setValue(24.0)
    dlg.special.edits[("def_axis", None)].setCurrentText("+Y")
    dlg._on_apply()
    p = m.part_params("Peltier1")
    assert p["thick"][0] == 2.5
    assert p["paramV"][0] == 24.0
    assert p["def_axis"] == "+Y"

    # 重新打开对话框：载入已存参数
    dlg2 = cab_dialogs.PartDialog(m, None, "Peltier1")
    assert dlg2.special.edits[("thick", 0)].value() == pytest.approx(2.5)
    assert dlg2.special.edits[("paramV", 0)].value() == pytest.approx(24.0)
    assert dlg2.special.edits[("def_axis", None)].currentText() == "+Y"


def test_part_dialog_card_guide_writeback(qapp):
    import cab_dialogs
    m = _model(("CardGuide1", "card_guide"))
    dlg = cab_dialogs.PartDialog(m, None, "CardGuide1")
    assert dlg.special._kind == "card_guide"
    dlg.special.edits[("nfin", None)].setValue(12)
    dlg.special.edits[("space", 0)].setValue(4.5)
    dlg._on_apply()
    p = m.part_params("CardGuide1")
    assert p["nfin"] == 12
    assert p["space"][0] == 4.5
    # 重载
    dlg2 = cab_dialogs.PartDialog(m, None, "CardGuide1")
    assert dlg2.special.edits[("nfin", None)].value() == 12


def test_part_dialog_diffuser_writeback(qapp):
    import cab_dialogs
    m = _model(("Diffuser1", "diffuser"))
    dlg = cab_dialogs.PartDialog(m, None, "Diffuser1")
    assert dlg.special._kind == "diffuser"
    dlg.special.edits[("supply_flow_rate", None)].setValue(0.025)
    dlg.special.edits[("inflow_temperature", None)].setValue(22.0)
    dlg._on_apply()
    p = m.part_params("Diffuser1")
    assert p["supply_flow_rate"] == pytest.approx(0.025)
    assert p["inflow_temperature"] == 22.0
    # 镜像的 flux 值已绑定
    assert m.condition_value("parts", "Diffuser1") == "_outlet1_flux"


# -- SDAT 导出 -------------------------------------------------------------------

def _sdat(m: StpreModel) -> str:
    import s_export
    props = PropertyModel(parse_property(new_property_bytes()))
    return s_export.build_sdat(m, props)


def test_s_export_no_special_parts_no_cards():
    # 无参数专用件 / 普通件：不发射任何专用件卡片
    text = _sdat(_model(("Box", "cube"), ("Peltier1", "peltier")))
    assert "PELTIER" not in text
    for kw in ("AIRCON", "DIFFUSER", "CARD_GUIDE", "HEATPIPE", "TCMDL"):
        assert kw not in text


def test_s_export_unverified_specials_not_emitted():
    # AC Unit / Diffuser / Card Guide / Heat Pipe 无 .s 卡片实证：
    # 参数已写盘也不得虚构语法
    m = _model(("ACUnit1", "ac_unit"), ("Diffuser1", "diffuser"),
               ("CardGuide1", "card_guide"), ("HeatPipe1", "heat_pipe"))
    assert m.set_part_params("ACUnit1", {"capability": 2500.0,
                                         "flow_rate": 15.0})
    assert m.set_part_params("Diffuser1", {"supply_flow_rate": 0.012})
    assert m.set_part_params("CardGuide1", {"nfin": 8})
    assert m.set_part_params("HeatPipe1", {"thermal_resistance": 0.05})
    text = _sdat(m)
    for kw in ("PELTIER", "AIRCON", "DIFFUSER", "CARD_GUIDE", "HEATPIPE",
               "TCMDL"):
        assert kw not in text


def test_s_export_peltier_cards():
    m = _model(("Peltier1", "peltier"), ("Peltier2", "peltier"))
    # exA22-2 实证：卡片数值 = paramV 末元素（官方 15.5,17.5,10 → 1.0e+01）
    assert m.set_part_params("Peltier1", {
        "paramV": (12.0, 7.7, 8.8, 9.9), "thick": (2.0, 2.0)})
    assert m.set_part_params("Peltier2", {"paramV": (15.5, 17.5, 5.0, 10.0)})
    text = _sdat(m)
    lines = text.splitlines()
    # PELTIER_OUT 块
    io = lines.index("PELTIER_OUT")
    assert lines[io + 1] == "       0:L"
    assert lines[io + 2] == " basic"
    assert lines[io + 3] == "/"
    # PELTIER_SET：按件顺序编号，电压取 paramV[-1]
    ic = lines.index("PELTIER_SET")
    assert lines[ic + 1] == "    Peltier1"
    assert lines[ic + 2].split() == [
        "9.90000000000000e+00",
        "@S:_peltier1_cr", "@S:_peltier1_qc",
        "@S:_peltier1_qh", "@S:_peltier1_dt"]
    assert lines[ic + 3] == "    Peltier2"
    assert lines[ic + 4].split() == [
        "1.00000000000000e+01",
        "@S:_peltier2_cr", "@S:_peltier2_qc",
        "@S:_peltier2_qh", "@S:_peltier2_dt"]
    assert lines[ic + 5] == "/"
    # 段位置：VFDE 之后、AUTOFIXP 之前（官方 exA22-2 布局）
    assert lines.index("VFDE") < io < lines.index("AUTOFIXP")
    assert io < lines.index("AUTOFIXP")
