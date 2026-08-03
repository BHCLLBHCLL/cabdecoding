"""P5: cross-sample scan over every cab found under ``tests/**/*.cab``.

Each sample must satisfy the structural invariants that were pinned down on
``ex4_e`` (see CAB_FORMAT_SPEC.md). When an official ``<stem>.s`` /
``<stem>.xemt`` export pair sits next to the cab, export parity is checked
as well. Unknown/unverified variants are reported, never silently assumed.
"""

import glob
import os
import re

import pytest

import parasolid
import xemt_export
from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
from s_export import build_sdat


HERE = os.path.dirname(__file__)


def _cabs() -> list[str]:
    return sorted(glob.glob(os.path.join(HERE, "**", "*.cab"),
                            recursive=True))


def _floats(line: str) -> list[float]:
    return [float(x) for x in line.split()
            if re.fullmatch(r"[+-]?[\d.eE+-]+", x)]


def _archive(path: str) -> CabArchive:
    with open(path, "rb") as fh:
        arch = CabArchive.parse(fh.read())
    arch.fill_member_data()
    return arch


def _member_names(path: str) -> tuple[str, str, str]:
    arch = _archive(path)
    names = [m.name for m in arch.members]
    xml_name = next(n for n in names if not n.startswith("_"))
    prop_name = next(n for n in names if n.endswith("_property.xml"))
    xt_name = next(n for n in names if n.endswith("_all.x_t"))
    return (xml_name, prop_name, xt_name)


def test_samples_present():
    cabs = _cabs()
    assert cabs, "no tests/**/*.cab samples found"


@pytest.mark.parametrize("cab", _cabs(),
                         ids=[os.path.basename(c) for c in _cabs()])
def test_container_invariants(cab):
    arch = _archive(cab)
    # header layout observed on ex4_e (Cradle variant)
    assert arch.version_minor == 3 and arch.version_major == 1
    assert len(arch.folders) == 1
    folder = arch.folders[0]
    assert folder.type_compress == 1                 # MSZIP
    assert folder.c_cfdata > 0
    # exactly three known members named after the project
    xml_name, prop_name, xt_name = _member_names(cab)
    assert [m.name for m in arch.members] == [xml_name, prop_name, xt_name]
    # member offsets are contiguous
    off = 0
    for m in arch.members:
        assert m.uoff_folder_start == off
        off += m.cb_file
    stream = arch.folder_stream()
    assert len(stream) == off
    # magic checks
    members = {m.name: m.data for m in arch.members}
    xml_name, prop_name, xt_name = _member_names(cab)
    assert members[xml_name][:3] == b"\xef\xbb\xbf"
    assert members[prop_name][:3] == b"\xef\xbb\xbf"
    assert members[xt_name][:2] == b"**"


@pytest.mark.parametrize("cab", _cabs(),
                         ids=[os.path.basename(c) for c in _cabs()])
def test_xml_roundtrip(cab):
    arch = _archive(cab)
    members = {m.name: m.data for m in arch.members}
    xml_name, prop_name, _ = _member_names(cab)
    for name in (xml_name, prop_name):
        doc = parse_stpre(members[name]) \
            if name == xml_name else parse_property(members[name])
        assert doc.serialize() == members[name]


@pytest.mark.parametrize("cab", _cabs(),
                         ids=[os.path.basename(c) for c in _cabs()])
def test_rebuild_roundtrip(cab):
    raw = open(cab, "rb").read()
    arch = CabArchive.parse(raw)
    assert arch.to_bytes(preserve_source_blocks=True) == raw


@pytest.mark.parametrize("cab", _cabs(),
                         ids=[os.path.basename(c) for c in _cabs()])
def test_parasolid_partial_extract(cab):
    arch = _archive(cab)
    members = {m.name: m.data for m in arch.members}
    _, _, xt_name = _member_names(cab)
    s = parasolid.parse_transmit(members[xt_name])
    assert s.header.get("FORMAT") == "text"
    assert s.schema and s.schema.startswith("SCH_")
    assert s.version
    assert s.field_names


@pytest.mark.parametrize("cab", _cabs(),
                         ids=[os.path.basename(c) for c in _cabs()])
def test_export_parity_or_smoke(cab):
    stem = os.path.splitext(cab)[0]
    if not (os.path.isfile(stem + ".s") and os.path.isfile(stem + ".xemt")):
        pytest.skip("no official .s/.xemt pair for this sample")
    arch = _archive(cab)
    members = {m.name: m.data for m in arch.members}
    xml_name, prop_name, _ = _member_names(cab)
    model = StpreModel(parse_stpre(members[xml_name]))
    props = PropertyModel(parse_property(members[prop_name]))
    ours_s = build_sdat(model, props)
    ours_x = xemt_export.build_emt(model, props)
    assert ours_s.startswith("SDAT") and ours_s.endswith("GOGO\r\n")
    assert "<EMT>" in ours_x
    official_s = open(stem + ".s", encoding="utf-8-sig").read()
    official_x = open(stem + ".xemt", encoding="utf-8-sig").read()
    a, b = official_s.splitlines(), ours_s.splitlines()
    assert len(a) == len(b)
    structural = 0
    for x, y in zip(a, b):
        if x == y:
            continue
        fx, fy = _floats(x), _floats(y)
        if len(fx) == len(fy) and fx and all(
                abs(p - q) < 1e-12 for p, q in zip(fx, fy)):
            continue
        structural += 1
    assert structural == 0
    ax = [ln for ln in ours_x.splitlines() if "date/time" not in ln]
    bx = [ln for ln in official_x.splitlines() if "date/time" not in ln]
    assert ax == bx
