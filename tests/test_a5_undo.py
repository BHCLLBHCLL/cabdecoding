"""A5: undo/redo consistency — archive member snapshot/restore."""
from pathlib import Path

import pytest

from cab_container import (
    CabArchive, CabMember, restore_members, snapshot_members,
)

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


def _box_archive():
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    return archive


def test_member_snapshot_roundtrip():
    archive = _box_archive()
    names0 = [m.name for m in archive.members]
    snap = snapshot_members(archive)
    # simulate a boolean/cut that appends a new STL member
    archive.members.append(CabMember(
        name="result_1.stl", cb_file=3, uoff_folder_start=0, i_folder=0,
        date=0, time=0, attribs=0, data=b"STL"))
    assert [m.name for m in archive.members] == names0 + ["result_1.stl"]
    restore_members(archive, snap)
    assert [m.name for m in archive.members] == names0


def test_restore_preserves_payload():
    archive = _box_archive()
    xt = next(m for m in archive.members if m.name.endswith(".x_t"))
    original = xt.data
    snap = snapshot_members(archive)
    xt.data = b"corrupted"
    restore_members(archive, snap)
    xt2 = next(m for m in archive.members if m.name.endswith(".x_t"))
    assert xt2.data == original
