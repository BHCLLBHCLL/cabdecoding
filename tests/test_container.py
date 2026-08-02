"""P0: MSCF container parsing, MSZIP decompression and round-trip writing."""

import hashlib
import os
import struct
import zlib

import pytest

import cab_container
from cab_container import CabArchive, CabFormatError, mszip_compress, mszip_decompress


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")

GOLDEN = {
    # md5 verified against Windows `expand` extraction of tests/ex4_e.cab
    "ex4_e.xml": (104926, "f732319bba1a90325831078238775066"),
    "_ex4_e_property.xml": (69987, "9935df6eda80dd1445469cd2a9e581ae"),
    "_ex4_e_all.x_t": (802665, "abafdca343203b12c596cadbb712c135"),
}


@pytest.fixture(scope="module")
def archive() -> CabArchive:
    with open(CAB, "rb") as fh:
        return CabArchive.parse(fh.read())


def test_header_layout(archive: CabArchive):
    assert archive.version_minor == 3
    assert archive.version_major == 1
    assert len(archive.folders) == 1
    assert len(archive.members) == 3
    assert archive.set_id == 12345
    assert archive.flags == 0
    folder = archive.folders[0]
    assert folder.coff_cab_start == 137
    assert folder.c_cfdata == 30
    assert folder.type_compress == 1  # MSZIP


def test_member_table(archive: CabArchive):
    table = [(m.name, m.cb_file, m.uoff_folder_start, m.date, m.time) for m in archive.members]
    assert table == [
        ("ex4_e.xml", 104926, 0, 0x575F, 0xA32D),
        ("_ex4_e_property.xml", 69987, 104926, 0x575F, 0xA32D),
        ("_ex4_e_all.x_t", 802665, 174913, 0x575F, 0xA32D),
    ]


def test_extract_md5(archive: CabArchive):
    for m in archive.fill_member_data():
        size, md5 = GOLDEN[m.name]
        assert m.cb_file == size
        assert hashlib.md5(m.data).hexdigest() == md5


def test_folder_stream_contiguous(archive: CabArchive):
    stream = archive.folder_stream()
    assert len(stream) == sum(m.cb_file for m in archive.members)
    off = 0
    for m in archive.members:
        assert stream[off : off + m.cb_file] == archive.extract_members()[archive.members.index(m)].data
        off += m.cb_file


def test_roundtrip_byte_identical(archive: CabArchive, tmp_path):
    archive.fill_member_data()
    original = open(CAB, "rb").read()
    rebuilt = archive.to_bytes(preserve_source_blocks=True)
    assert rebuilt == original


def test_roundtrip_recompress(archive: CabArchive):
    archive.fill_member_data()
    rebuilt = archive.to_bytes()
    re_arch = CabArchive.parse(rebuilt)
    assert re_arch.folders[0].c_cfdata == 30
    for m, rm in zip(archive.members, re_arch.extract_members()):
        assert m.data == rm.data


def test_bad_signature():
    with pytest.raises(CabFormatError):
        CabArchive.parse(b"PK\x03\x04" + b"\x00" * 80)


def test_mszip_roundtrip_various_sizes():
    rng = zlib.compressobj(9, zlib.DEFLATED, -15)  # deterministic pseudo-random-ish data
    blob = rng.compress(b"x" * 100000) + rng.flush() + bytes(range(256)) * 600
    blocks, total = mszip_compress(blob)
    assert total == len(blob)
    assert all(b[:2] == b"CK" for b in blocks)
    assert all(len(b) <= 0xFFFF for b in blocks)
    assert mszip_decompress(blocks) == blob


def test_mszip_shared_history_decode():
    # Cradle-written blocks reference previous blocks via the shared 32 KiB
    # window; our decoder must prime each block with the prior output.
    data = (b"0123456789abcdef" * 4000) + b"tail-" + (b"0123456789abcdef" * 2000)
    blocks, _ = mszip_compress(data)
    assert mszip_decompress(blocks) == data


def test_cli_summary(tmp_path, capsys=None):
    import cab_parser

    assert cab_parser.main([CAB, "--json"]) == 0
    import json as _json

    out_dir = tmp_path / "ext"
    assert cab_parser.main([CAB, "--extract", str(out_dir)]) == 0
    for name in GOLDEN:
        with open(out_dir / name, "rb") as fh:
            assert hashlib.md5(fh.read()).hexdigest() == GOLDEN[name][1]

    rebuilt = tmp_path / "rebuilt.cab"
    assert cab_parser.main([CAB, "--rebuild", str(rebuilt)]) == 0
    assert open(rebuilt, "rb").read() == open(CAB, "rb").read()
