"""M44: FEM 真单元生成（R9-A）。

COM 探针实证（tools/probe_fem.py → tools/probe_work/fem_probe.json，
STpre 2025.2）：

* ``Model.CreateFEM(length, scale, edge)`` 4 组合全部成功，返回新
  Model；原实体件保留，主 XML 新增 ``fem_<原名>`` 的
  ``<parts type="mesh_body">``（attribute=fe-model、file=xfem）；
* ``<body_files>`` 追加 ``<file type="fem">``，cab 包新增 ``.xfem``
  成员（XML：<femodel><model><node><n>x,y,z,flag 与
  <element><e kind="4">n1,n2,n3,n4，坐标米制，kind=4 四面体）；
* .s 无 FEM 段（单元数据只在 .xfem）。

本文件覆盖：cabxml 的 fem_parts/part_fem/set_part_fem 读 API、
parse_femodel/femodel_bytes 往返、build_fem_hexa 离线六面体→四面体
生成，以及 COM 可用时的探针级 e2e（建件→CreateFEM→存→重开→读回）。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from cabxml import (FEM_KIND_TET4, StpreModel, _first, build_fem_hexa,
                    femodel_bytes, new_stpre_bytes, parse_femodel,
                    parse_stpre)

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"

# COM 探针实测的 .xfem 成员样例（fem_F_T 组合，10mm 立方 / 2mm 单元）
_XFEM_SAMPLE = (
    '<?xml version="1.0" encoding="UTF-8" ?>\r\n'
    '<femodel>\r\n'
    '   <version> 14 </version>\r\n'
    '   <unit> m,C </unit>\r\n'
    '   <model name="fem_FemBox" temp_type="0">\r\n'
    '      <node num="4">\r\n'
    '         <n no="1" org="1"> 0,0,0,0 </n>\r\n'
    '         <n no="2" org="2"> 0.01,0,0,0 </n>\r\n'
    '         <n no="3" org="3"> 0,0.01,0,0 </n>\r\n'
    '         <n no="4" org="4"> 0,0,0.01,0 </n>\r\n'
    '      </node>\r\n'
    '      <element num="1">\r\n'
    '         <e no="1" kind="4"> 1,2,3,4 </e>\r\n'
    '      </element>\r\n'
    '   </model>\r\n'
    '</femodel>\r\n'
).encode("utf-8")


def _model_with_fem_part() -> StpreModel:
    """带一个 mesh_body FEM 部件的主 XML 模型（实证格式）。"""
    text = new_stpre_bytes().decode("utf-8").replace(
        "</stpre>",
        '   <parts type="mesh_body">\r\n'
        '      <name> fem_FemBox </name>\r\n'
        '      <attribute> fe-model </attribute>\r\n'
        '      <color> 191,191,191,255 </color>\r\n'
        '      <mode> global </mode>\r\n'
        '      <visible_count> 1 </visible_count>\r\n'
        '      <tree_expand> F </tree_expand>\r\n'
        '      <layer> 1 </layer>\r\n'
        '      <rad_group_num> 0 </rad_group_num>\r\n'
        '      <mesh_divide> none </mesh_divide>\r\n'
        '      <heat_balance> F,F </heat_balance>\r\n'
        '      <VF_balance> F </VF_balance>\r\n'
        '      <file> xfem </file>\r\n'
        '   </parts>\r\n'
        '   <body_files unit="m">\r\n'
        '      <file type="xt"> _x_all.x_t </file>\r\n'
        '      <file type="fem"> _x_all.xfem </file>\r\n'
        '   </body_files>\r\n'
        '</stpre>')
    return StpreModel(parse_stpre(text.encode("utf-8")))


# -- parse_femodel：实证格式解析 ---------------------------------------------

def test_parse_femodel_probe_format():
    models = parse_femodel(_XFEM_SAMPLE)
    assert len(models) == 1
    m = models[0]
    assert m["name"] == "fem_FemBox"
    assert m["temp_type"] == "0"
    assert m["nodes"] == [(0.0, 0.0, 0.0), (0.01, 0.0, 0.0),
                          (0.0, 0.01, 0.0), (0.0, 0.0, 0.01)]
    assert m["elements"] == [(4, 1, 2, 3, 4)]
    assert m["element_kinds"] == [4]


def test_parse_femodel_ignores_malformed_rows():
    # 坏行跳过、kind 缺省为 4（实证唯一 kind）
    text = _XFEM_SAMPLE.decode("utf-8").replace(
        '<n no="3" org="3"> 0,0.01,0,0 </n>',
        '<n no="3" org="3"> bad,row </n>').replace('kind="4"', "")
    models = parse_femodel(text.encode("utf-8"))
    m = models[0]
    assert len(m["nodes"]) == 3          # 坏行被跳过
    assert m["elements"] == [(4, 1, 2, 3, 4)]
    assert m["element_kinds"] == [FEM_KIND_TET4]


# -- part_fem / fem_parts 读 API ----------------------------------------------

def test_part_fem_metadata_without_xfem():
    m = _model_with_fem_part()
    assert m.fem_parts() == ["fem_FemBox"]
    info = m.part_fem("fem_FemBox")
    assert info is not None
    assert info["type"] == "mesh_body"
    assert info["file"] == "xfem"
    # 未给 .xfem 成员数据：单元数据降级为 None（存储在 cab 另一成员）
    assert info["nodes"] is None
    assert info["elements"] is None


def test_part_fem_with_xfem_data():
    m = _model_with_fem_part()
    info = m.part_fem("fem_FemBox", xfem_data=_XFEM_SAMPLE)
    assert info is not None
    assert len(info["nodes"]) == 4
    assert len(info["elements"]) == 1
    assert info["elements"][0] == (4, 1, 2, 3, 4)
    assert info["element_kinds"] == [4]


def test_part_fem_rejects_non_fem_parts():
    m = _model_with_fem_part()
    # 普通 body 部件 / 不存在的部件名 → None
    assert m.part_fem("box") is None
    assert m.part_fem("Nope") is None


# -- set_part_fem 写 API + 往返 ------------------------------------------------

def test_set_part_fem_roundtrip():
    m = StpreModel(parse_stpre(new_stpre_bytes("Proj")))
    fem = {"nodes": [(0.0, 0.0, 0.0), (0.01, 0.0, 0.0),
                     (0.0, 0.01, 0.0), (0.0, 0.0, 0.01)],
           "elements": [(4, 1, 2, 3, 4)]}
    assert m.set_part_fem("fem_Box", fem) is True
    assert m.fem_parts() == ["fem_Box"]
    # 主 XML 落盘格式与实证一致（type/attribute/file/mesh_divide）
    el = m.find_part("fem_Box")
    assert el.attrib.get("type") == "mesh_body"
    assert (_first(el, "attribute").text or "").strip() == "fe-model"
    assert (_first(el, "file").text or "").strip() == "xfem"
    assert (_first(el, "mesh_divide").text or "").strip() == "none"
    # body_files 注册 type="fem" 条目（默认 _<工程>_all.xfem）
    bf = _first(m.root, "body_files")
    fem_files = [c for c in bf if c.attrib.get("type") == "fem"]
    assert len(fem_files) == 1
    assert (fem_files[0].text or "").strip() == "_Proj_all.xfem"
    # 序列化往返后仍可读回（.xfem 数据由调用方写入 archive）
    again = StpreModel(parse_stpre(m.doc.serialize()))
    info = again.part_fem("fem_Box")
    assert info is not None and info["file"] == "xfem"
    # 删除
    assert again.set_part_fem("fem_Box", None) is True
    assert again.fem_parts() == []


def test_set_part_fem_validation():
    m = _model_with_fem_part()
    # 同名部件已存在（含 mesh_body 自身）→ False
    assert m.set_part_fem("fem_FemBox", {"nodes": [], "elements": []}) \
        is False
    # 删除不存在的 FEM 部件 → False
    assert m.set_part_fem("fem_Ghost", None) is False


# -- femodel_bytes 生成器与解析同构 -------------------------------------------

def test_femodel_bytes_roundtrip():
    fem = build_fem_hexa((10.0, 20.0, 30.0), (10.0, 10.0, 10.0),
                         divide=(2, 1, 1))
    data = femodel_bytes("fem_Box", fem)
    assert data.startswith(b"\xef\xbb\xbf")            # UTF-8 BOM
    assert b"\r\n" in data                             # CRLF（实证）
    assert b'<version> 14 </version>' in data
    assert b'<unit> m,C </unit>' in data
    models = parse_femodel(data)
    assert len(models) == 1
    m = models[0]
    assert m["name"] == "fem_Box"
    assert len(m["nodes"]) == len(fem["nodes"])
    assert m["elements"] == fem["elements"]
    assert m["element_kinds"] == [4]


# -- build_fem_hexa 离线生成 ---------------------------------------------------

def _tets_volume(nodes, elements) -> float:
    """所有四面体体积和（节点号 1-based）。"""
    total = 0.0
    for el in elements:
        assert el[0] == FEM_KIND_TET4
        a, b, c, d = (nodes[n - 1] for n in el[1:])
        det = (b[0] - a[0]) * ((c[1] - a[1]) * (d[2] - a[2])
                               - (c[2] - a[2]) * (d[1] - a[1])) \
            - (b[1] - a[1]) * ((c[0] - a[0]) * (d[2] - a[2])
                               - (c[2] - a[2]) * (d[0] - a[0])) \
            + (b[2] - a[2]) * ((c[0] - a[0]) * (d[1] - a[1])
                               - (c[1] - a[1]) * (d[0] - a[0]))
        total += abs(det) / 6.0
    return total


def test_build_fem_hexa_topology():
    fem = build_fem_hexa((0.0, 0.0, 0.0), (20.0, 20.0, 20.0),
                         divide=(2, 2, 2))
    # 2x2x2 六面体 × 6 tets = 48 单元；节点 (3)^3 = 27（共享节点）
    assert len(fem["elements"]) == 2 * 2 * 2 * 6
    assert len(fem["nodes"]) == 3 * 3 * 3
    # 节点号都在范围内且为 1-based
    n_max = max(max(el[1:]) for el in fem["elements"])
    assert 1 <= n_max <= len(fem["nodes"])
    # Kuhn 剖分体积守恒：体积和 == 盒体积（20mm 边 = 0.02m）
    assert _tets_volume(fem["nodes"], fem["elements"]) \
        == pytest.approx(0.02 ** 3)
    # 坐标为米制（实证 unit=m）
    xs = sorted({n[0] for n in fem["nodes"]})
    assert xs == pytest.approx([0.0, 0.01, 0.02])


def test_build_fem_hexa_single_cell():
    fem = build_fem_hexa((10.0, 10.0, 10.0), (10.0, 10.0, 10.0))
    assert len(fem["nodes"]) == 8
    assert len(fem["elements"]) == 6
    assert _tets_volume(fem["nodes"], fem["elements"]) \
        == pytest.approx(0.01 ** 3)


# -- COM e2e：建件 → CreateFEM → 存 → 重开 → part_fem 读回 -------------------

def _stpre_ready() -> bool:
    try:
        import cab_stpre_api
        return cab_stpre_api.api_available()
    except Exception:
        return False


@pytest.fixture(scope="module")
def _fem_e2e_cab(tmp_path_factory):
    """COM 探针级 e2e：返回 (cab 路径, xfem 字节)。"""
    pytest.importorskip("cab_stpre_api")
    if not _stpre_ready():
        pytest.skip("STpre COM not registered")
    import cab_stpre_api
    from cab_container import CabArchive
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    model = StpreModel(parse_stpre(members[xml_name]))
    src = tmp_path_factory.mktemp("fem_e2e") / "fem_in.cab"
    assert cab_stpre_api.build_relay_cab(model, archive, src)
    session = cab_stpre_api.STpreSession()
    out = src.with_name("fem_out.cab")
    try:
        assert session.ensure_open(src)
        doc = session.doc
        # 建实体件（手册签名 name,bx,by,bz,sx,sy,sz）→ FEM 转换
        cube = doc.call("CreateCubeModel", "FemBox",
                        0.0, 0.0, 0.0, 10.0, 10.0, 10.0)
        assert cube is not None
        cube_wrap = session.model("FemBox")
        assert cube_wrap is not None and cube_wrap.raw is not None
        fem_model = cube_wrap.CreateFEM(2.0, "F", "T")
        assert fem_model is not None
        assert session.save(out)
    finally:
        session.close()
    arch = CabArchive.parse(out.read_bytes())
    arch.fill_member_data()
    xfem = next((m.data for m in arch.members if m.name.endswith(".xfem")),
                None)
    xml = next(m.data for m in arch.members
               if m.name.endswith(".xml") and not m.name.startswith("_"))
    return xml, xfem


@pytest.mark.skipif(not _stpre_ready(), reason="STpre COM not registered")
def test_fem_e2e_roundtrip(_fem_e2e_cab):
    xml, xfem = _fem_e2e_cab
    m = StpreModel(parse_stpre(xml))
    # 原实体件保留 + 新增 fem_FemBox 部件（实证布局）
    assert "FemBox" in [p.name for p in m.parts()]
    assert m.fem_parts() == ["fem_FemBox"]
    # body_files 注册了 type="fem" 条目
    bf = _first(m.root, "body_files")
    assert any(c.attrib.get("type") == "fem" and c.text
               for c in bf if c.tag == "file")
    # .xfem 成员存在且为实证 femodel 格式
    assert xfem is not None
    info = m.part_fem("fem_FemBox", xfem_data=xfem)
    assert info is not None
    assert len(info["nodes"]) > 0
    assert len(info["elements"]) > 0
    assert info["element_kinds"] == [FEM_KIND_TET4]   # 4 节点四面体
    # 每个 tet 引用 4 个有效节点号
    n_nodes = len(info["nodes"])
    for el in info["elements"][:50]:
        assert len(el) == 5
        assert all(1 <= n <= n_nodes for n in el[1:])
    # 节点坐标在 0..0.01m（10mm 立方体，实证 unit=m）
    for x, y, z in info["nodes"][:50]:
        assert -1e-9 <= x <= 0.01 + 1e-9
        assert -1e-9 <= y <= 0.01 + 1e-9
        assert -1e-9 <= z <= 0.01 + 1e-9
