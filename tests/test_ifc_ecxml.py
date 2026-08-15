"""P2-9: IFC / ECXML import-export tests."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

import cab_ifc
import ecxml
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


SAMPLE_IFC = '''ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('t.ifc','2026-01-01T00:00:00',(''),(''),'x','x','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCCARTESIANPOINT((0.,0.,0.));
#2=IFCDIRECTION((0.,0.,1.));
#3=IFCDIRECTION((1.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#1,#2,#3);
#5=IFCLOCALPLACEMENT($,#4);
#6=IFCCARTESIANPOINT((0.,0.));
#7=IFCAXIS2PLACEMENT2D(#6,$);
#8=IFCRECTANGLEPROFILEDEF(.RECTANGLE.,$,#7,3.,0.2);
#9=IFCEXTRUDEDAREASOLID(#8,#4,#2,4.);
#10=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#9));
#11=IFCPRODUCTDEFINITIONSHAPE($,$,(#10));
#12=IFCWALLSTANDARDCASE('2O2Fr$t4X7Zf8NOew3FLOHV','Wall-1',$,#11,$,$,$,$);
#20=IFCCARTESIANPOINT((10.,0.,0.));
#21=IFCAXIS2PLACEMENT3D(#20,#2,#3);
#22=IFCLOCALPLACEMENT($,#21);
#23=IFCRECTANGLEPROFILEDEF(.RECTANGLE.,$,#7,2.,2.);
#24=IFCEXTRUDEDAREASOLID(#23,#21,#2,0.3);
#25=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#24));
#26=IFCPRODUCTDEFINITIONSHAPE($,$,(#25));
#27=IFCSLAB('3qWj$d1234567890abcdef','Slab-2',$,#26,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;'''


SAMPLE_ECXML = '''<?xml version="1.0"?>
<ECXML version="1.0">
  <Component name="QFP48" kind="two_resistor" manufacturer="ACME">
    <Location x="1" y="2" z="3" unit="mm"/>
    <Size x="10" y="10" z="1.5" unit="mm"/>
    <Thermal><Rjc unit="K/W">1.25</Rjc><Rjb unit="K/W">5.5</Rjb>
    <Power unit="W">2.0</Power></Thermal>
  </Component>
</ECXML>'''


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("demo")))


def test_ifc_parse_extracts_extruded_solids():
    solids = cab_ifc.parse_ifc(SAMPLE_IFC)
    assert len(solids) == 2
    wall = next(s for s in solids if s.entity == "IFCWALLSTANDARDCASE")
    assert wall.name == "Wall-1"
    assert wall.size == pytest.approx((3000.0, 200.0, 4000.0))
    slab = next(s for s in solids if s.entity == "IFCSLAB")
    assert slab.name == "Slab-2"
    assert slab.base == pytest.approx((10000.0, 0.0, 0.0))
    assert slab.size == pytest.approx((2000.0, 2000.0, 300.0))


def test_ifc_register_parts():
    model = _model()
    names = cab_ifc.register_ifc_parts(model, cab_ifc.parse_ifc(SAMPLE_IFC))
    assert names == ["Wall-1", "Slab-2"]
    pinfo = {p.name: p for p in model.parts()}
    assert pinfo["Wall-1"].kind == "cube"
    base = [float(x) for x in pinfo["Wall-1"].base.replace(",", " ").split()]
    assert base == pytest.approx([0.0, 0.0, 0.0])
    size = [float(x) for x in pinfo["Wall-1"].size.replace(",", " ").split()]
    assert size == pytest.approx([3000.0, 200.0, 4000.0])


def test_ifc_export_roundtrip():
    model = _model()
    cab_ifc.register_ifc_parts(model, cab_ifc.parse_ifc(SAMPLE_IFC))
    out = cab_ifc.model_to_ifc(model)
    assert "IFC2X3" in out
    solids = cab_ifc.parse_ifc(out)
    by_name = {s.name: s for s in solids}
    assert "Wall-1" in by_name
    assert by_name["Wall-1"].size == pytest.approx((3000.0, 200.0, 4000.0))
    assert by_name["Slab-2"].base == pytest.approx((10000.0, 0.0, 0.0))


def test_ecxml_parse():
    comps = ecxml.parse_ecxml(SAMPLE_ECXML)
    assert len(comps) == 1
    c = comps[0]
    assert c["name"] == "QFP48"
    assert c["base"] == (1.0, 2.0, 3.0)
    assert c["size"] == (10.0, 10.0, 1.5)
    assert c["rjc"] == 1.25 and c["rjb"] == 5.5
    assert c["package_power"] == 2.0


def test_ecxml_roundtrip():
    model = _model()
    names = ecxml.register_ecxml_parts(model, ecxml.parse_ecxml(SAMPLE_ECXML))
    assert names == ["QFP48"]
    out = ecxml.parts_to_ecxml(model)
    comps = ecxml.parse_ecxml(out)
    assert len(comps) == 1
    assert comps[0]["base"] == (1.0, 2.0, 3.0)
    assert comps[0]["rjc"] == 1.25


def test_ifc_rejects_garbage():
    assert cab_ifc.parse_ifc("not an ifc file at all") == []
    with pytest.raises(Exception):
        ecxml.parse_ecxml("<not-xml")

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_gui_import_ifc_ecxml(qapp):
    import cab_gui
    from cab_container import CabArchive
    from cabxml import PropertyModel, parse_property, parse_stpre
    root = Path(__file__).resolve().parents[1]
    box = root / "tests" / "box.cab"
    archive = CabArchive.parse(box.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    prop_name = next(n for n in members if n.endswith("_property.xml"))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.archive = archive
    viewer.model = StpreModel(parse_stpre(members[xml_name]))
    viewer.props = PropertyModel(parse_property(members[prop_name]))

    class _Tree:
        def populate(self, *args):
            pass

    viewer.tree_view = _Tree()
    viewer._rebuild_scene = lambda: None
    viewer._update_title = lambda: None
    p = root / "tests" / "_tmp_ifc_ecxml.ecxml"
    p2 = root / "tests" / "_tmp_ifc_ecxml.ifc"
    try:
        p.write_text(SAMPLE_ECXML, encoding="utf-8")
        viewer._import_ifc_ecxml(str(p), ".ecxml")
        assert any(pi.name == "QFP48" for pi in viewer.model.parts())
        p2.write_text(SAMPLE_IFC, encoding="utf-8")
        viewer._import_ifc_ecxml(str(p2), ".ifc")
        assert any(pi.name == "Wall-1" for pi in viewer.model.parts())
    finally:
        for f in (p, p2):
            try:
                f.unlink()
            except OSError:
                pass


SAMPLE_ECXML_DELPHI = '''<?xml version="1.0"?>
<ECXML version="1.0">
  <Component name="QFN64" kind="delphi">
    <Location x="0" y="0" z="0" unit="mm"/>
    <Size x="9" y="9" z="1.0" unit="mm"/>
    <Thermal>
      <Rjc unit="K/W">1.0</Rjc><Rjb unit="K/W">3.0</Rjb>
      <Power unit="W">1.5</Power>
      <Node name="Top" r="2.5"/>
      <Node name="Bottom" r="3.5"/>
      <Node name="Leads" r="9.0"/>
      <Node name="Sides" r="14.0"/>
    </Thermal>
  </Component>
</ECXML>'''


def test_ecxml_delphi_nodes_roundtrip():
    """P2: Delphi thermal-circuit node network round-trip."""
    m = _model()
    comps = ecxml.parse_ecxml(SAMPLE_ECXML_DELPHI)
    assert comps[0]['nodes'] == [("Top", 2.5), ("Bottom", 3.5),
                                 ("Leads", 9.0), ("Sides", 14.0)]
    names = ecxml.register_ecxml_parts(m, comps)
    assert names == ["QFN64"]
    p = m.find_part("QFN64")
    assert p is not None
    nodes = p.findall("thermal_node")
    assert len(nodes) == 4
    from cabxml import _first
    assert (_first(nodes[0], "name").text or "").strip() == "Top"
    res0 = _first(nodes[0], "resistance")
    assert abs(float((res0.text or "").strip()) - 2.5) < 1e-9
    assert res0.attrib.get("unit") == "C/W"
    # export -> parse -> same network
    out = ecxml.parts_to_ecxml(m)
    comps2 = ecxml.parse_ecxml(out)
    assert comps2[0]['nodes'] == comps[0]['nodes']


def test_register_delphi_nodes_persistence():
    """P2: register_primitive delphi with nodes writes thermal_node list."""
    from cab_parts import register_primitive
    m = _model()
    ok = register_primitive(
        m, name="Delphi1", kind="delphi",
        params={"base": (0, 0, 0), "size": (5, 5, 1),
                "nodes": [("Top", 1.0), ("Bottom", 2.0)]})
    assert ok
    p = m.find_part("Delphi1")
    nodes = p.findall("thermal_node")
    assert [n.attrib.get("no") for n in nodes] == ["1", "2"]
    from cabxml import _first
    assert [( (_first(n, "name").text or "").strip(),
              float((_first(n, "resistance").text or "0").strip()))
            for n in nodes] == [("Top", 1.0), ("Bottom", 2.0)]


SAMPLE_IFC_CIRCLE = '''ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('c.ifc','2026-01-01T00:00:00',(''),(''),'x','x','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCCARTESIANPOINT((0.,0.,0.));
#2=IFCDIRECTION((0.,0.,1.));
#3=IFCDIRECTION((1.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#1,#2,#3);
#5=IFCLOCALPLACEMENT($,#4);
#6=IFCCARTESIANPOINT((0.,0.));
#7=IFCAXIS2PLACEMENT2D(#6,$);
#8=IFCCIRCLEPROFILEDEF(.CIRCLE.,$,#7,0.5);
#9=IFCEXTRUDEDAREASOLID(#8,#4,#2,3.);
#10=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#9));
#11=IFCPRODUCTDEFINITIONSHAPE($,$,(#10));
#12=IFCCOLUMN('2O2Fr$t4X7Zf8NOew3FLOHV','Col-1',$,#11,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;'''


def test_ifc_circle_profile_column():
    """P2-9: IFC circular profile extrusion -> cylinder part."""
    solids = cab_ifc.parse_ifc(SAMPLE_IFC_CIRCLE)
    assert len(solids) == 1
    s = solids[0]
    assert s.kind == "cylinder"
    assert s.radius == pytest.approx(500.0)
    assert s.size == pytest.approx((1000.0, 1000.0, 3000.0))
    m = _model()
    names = cab_ifc.register_ifc_parts(m, solids)
    assert names == ["Col-1"]
    from cabxml import _first
    p = m.find_part("Col-1")
    assert p is not None
    assert (_first(p, "radius").text or "").strip() == "500"
    assert (_first(p, "height").text or "").strip() == "3000"
    assert (_first(p, "direction").text or "").strip() == "+Z"
