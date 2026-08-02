"""P2: Parasolid text-transmit partial extraction + VTK box builders."""

import os

import cab_vtk
import parasolid
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")


def _xt_bytes() -> bytes:
    arch = CabArchive.parse(open(CAB, "rb").read())
    for m in arch.fill_member_data():
        if m.name == "_ex4_e_all.x_t":
            return m.data
    raise AssertionError("x_t member missing")


def test_parasolid_header_attributes():
    s = parasolid.parse_transmit(_xt_bytes())
    assert s.header["FRU"] == "Software Cradle Co.Ltd."
    assert s.header["APPL"] == "STREAM V2023"
    assert s.header["SITE"] == "Osaka Japan"
    assert s.header["FORMAT"] == "text"
    assert s.header["DATE"].startswith("2023/10/31")
    assert s.header["FILE"].endswith("_ex4_e_all.x_t")


def test_parasolid_version_schema():
    s = parasolid.parse_transmit(_xt_bytes())
    assert s.version == 340115323
    assert s.schema == "SCH_3401153_34101_1300"


def test_parasolid_schema_fields():
    s = parasolid.parse_transmit(_xt_bytes())
    fields = set(s.field_names)
    for expected in ("lattice", "mesh", "polyline", "owner",
                     "boundary_lattice", "boundary_mesh", "boundary_polyline",
                     "index_map_offset", "index_map", "node_id_index_map",
                     "schema_embedding_map", "child", "lowest_node_id",
                     "mesh_offset_data", "list_type", "notransmit",
                     "finger_index", "finger_block", "frame", "legal_owners",
                     "Partlist"):
        assert expected in fields, expected


def test_parasolid_records_and_sdl():
    s = parasolid.parse_transmit(_xt_bytes())
    assert s.record_count >= 20
    assert "SDL/TYSA_NAME" in s.sdl_attributes
    assert "SDL/TYSA_UNAME" in s.sdl_attributes
    assert "speaker" in s.part_names
    assert "speaker" in s.summary()


def _model() -> StpreModel:
    arch = CabArchive.parse(open(CAB, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return StpreModel(parse_stpre(members["ex4_e.xml"]))


def test_part_boxes_in_domain():
    model = _model()
    boxes = cab_vtk.part_boxes(model)
    assert len(boxes) == 31
    frame = cab_vtk.domain_frame(model)
    assert frame is not None
    fx0, fy0, fz0, fx1, fy1, fz1 = frame.bounds
    assert abs(fx0 + 0.1) < 1e-9 and abs(fx1 - 0.15) < 1e-9
    by_name = {b.name: b for b in boxes}
    battery = by_name["battery"]
    assert battery.bounds[0] >= fx0 - 1e-6
    assert battery.bounds[3] <= fx1 + 1e-6
    assert battery.bounds[5] - battery.bounds[2] > 1e-4
    # color parsed from XML RGBA
    assert 0.0 <= battery.color[0] <= 1.0


def test_vtk_scene_build_and_offscreen_render(tmp_path):
    if not cab_vtk._HAS_VTK:
        import pytest
        pytest.skip("vtk not installed")
    import vtk
    model = _model()
    boxes = cab_vtk.part_boxes(model)
    scene = cab_vtk.build_scene(boxes, wireframe=False)
    assert len(scene) == len(boxes)
    renderer = vtk.vtkRenderer()
    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(320, 240)
    render_window.AddRenderer(renderer)
    for pd, color, opacity in scene:
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetOpacity(opacity)
        renderer.AddActor(actor)
    renderer.ResetCamera()
    render_window.Render()
    image = vtk.vtkWindowToImageFilter()
    image.SetInput(render_window)
    image.Update()
    dims = image.GetOutput().GetDimensions()
    assert dims[0] == 320 and dims[1] == 240
