"""Element division = structured mesh lines on occupancy boxes."""
from __future__ import annotations

from pathlib import Path

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre
import cab_vtk

ROOT = Path(__file__).resolve().parents[1]
CURVED = ROOT / "tests" / "curvedbox.cab"


def _model(path: Path) -> StpreModel:
    raw = path.read_bytes()
    archive = CabArchive.parse(raw)
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml = next(v for k, v in members.items()
               if k.endswith(".xml") and "property" not in k
               and not k.startswith("_"))
    return StpreModel(parse_stpre(xml))


def test_element_division_lines_curvedbox():
    model = _model(CURVED)
    pd = cab_vtk.element_division_lines(model, "curvedbox")
    assert pd is not None
    # Dense mesh lines (not just ~1k occupancy-box edges)
    assert pd.GetNumberOfLines() > 5_000
    assert pd.GetNumberOfPoints() > 5_000


def test_element_division_empty_without_boxes():
    model = _model(CURVED)
    assert cab_vtk.element_division_lines(model, "no_such_part") is None


def test_domain_analysis_boxes_and_lines():
    model = _model(CURVED)
    assert "Domain(cuboid)" in model.analysis_names()
    boxes = model.analysis_boxes("Domain(cuboid)")
    assert boxes and len(boxes[0]) >= 6
    # Full domain brick ~ RootBlock
    assert boxes[0][1] >= 200 and boxes[0][3] >= 100
    pd = cab_vtk.element_division_lines(
        model, boxes=boxes, interior_stride=0)
    assert pd is not None
    assert pd.GetNumberOfLines() > 1_000
    shell = cab_vtk.element_division_shell(model, boxes=boxes)
    assert shell is not None
    assert shell.GetNumberOfPolys() > 1_000
