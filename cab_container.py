#!/usr/bin/env python3
"""
MSCF (Microsoft Cabinet) container reader/writer for Cradle scSTREAM Pre .cab
project files.

Observed container layout (Cradle variant of [MS-CAB], see CAB_FORMAT_SPEC.md):

    offset  size  field
    0       4     "MSCF"
    4       4     reserved1
    8       4     cbCabinet (u32 LE, total archive size)
    12      4     reserved2
    16      4     coffFiles (u32 LE, absolute offset of first CFFILE)
    20      4     0x00 x4  (reserved; standard layout has version fields here)
    24      1     versionMinor (observed 3)
    25      1     versionMajor (observed 1)
    26      2     cFolders (observed 1)
    28      2     cFiles (observed 3)
    30      2     flags (observed 0)
    32      2     setID (observed 12345)
    34      2     iCabinet (observed 0)
    36      8*    CFFOLDER entries
    44      -     CFFILE entries

    CFFOLDER: coffCabStart u32 + cCFData u16 + typeCompress u16
              typeCompress 1 = MSZIP
    CFFILE:   cbFile u32 + uoffFolderStart u32 + iFolder u16 + date u16 +
              time u16 + attribs u16 + szName (NUL terminated)
    CFDATA:   csum u32 + cbData u16 + cbUncomp u16 + payload
              payload = 'CK' + raw DEFLATE (MSZIP block); the LZ77 history
              window is shared across blocks (see mszip_decompress).
"""

from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass, field
from typing import BinaryIO, Iterable, Optional

MSCF_SIGNATURE = b"MSCF"
TYPE_MSZIP = 1
MSZIP_BLOCK_SIZE = 32768
_MSZIP_MAGIC = b"CK"


class CabFormatError(ValueError):
    """Raised when a .cab archive does not match the observed Cradle layout."""


def mszip_decompress(blocks: Iterable[bytes]) -> bytes:
    """Decompress MSZIP blocks ('CK' + raw DEFLATE) with a shared 32 KiB
    LZ77 window carried across block boundaries.

    Each block is fed to a fresh :class:`zlib.decompressobj` primed with the
    previously decompressed window; Cradle-written blocks may reference
    history from earlier blocks.
    """
    out = bytearray()
    for i, blk in enumerate(blocks):
        if not blk.startswith(_MSZIP_MAGIC):
            raise CabFormatError("MSZIP block does not start with b'CK'")
        dec = (
            zlib.decompressobj(-15)
            if i == 0
            else zlib.decompressobj(-15, zdict=bytes(out[-MSZIP_BLOCK_SIZE:]))
        )
        out += dec.decompress(blk[2:])
        out += dec.flush()
    return bytes(out)


def mszip_compress_chunk(chunk: bytes) -> bytes:
    """Compress one <= 32 KiB chunk as a self-contained MSZIP block.

    Blocks are written without cross-block references (valid MSZIP; Windows
    tools decompress it).  The 32 KiB history is intentionally not carried
    across blocks to keep the encoder pure-Python and deterministic.
    """
    co = zlib.compressobj(6, zlib.DEFLATED, -15)
    return _MSZIP_MAGIC + co.compress(chunk) + co.flush()


def mszip_compress(data: bytes) -> tuple[list[bytes], int]:
    """Split *data* into 32 KiB chunks and compress each into an MSZIP block.

    Returns ``(blocks, uncompressed_total)``.  A chunk whose compressed size
    would exceed the u16 limit is split recursively.
    """
    blocks: list[bytes] = []
    total = 0

    def _push(chunk: bytes) -> None:
        nonlocal total
        blk = mszip_compress_chunk(chunk)
        if len(blk) > 0xFFFF and len(chunk) > 1:
            mid = len(chunk) // 2
            _push(chunk[:mid])
            _push(chunk[mid:])
            return
        blocks.append(blk)
        total += len(chunk)

    for off in range(0, len(data), MSZIP_BLOCK_SIZE):
        _push(data[off : off + MSZIP_BLOCK_SIZE])
    return blocks, total


def _dos_datetime(year: int, month: int, day: int, hour: int, minute: int, second: int) -> tuple[int, int]:
    date = ((year - 1980) << 9) | (month << 5) | day
    time = (hour << 11) | (minute << 5) | (second // 2)
    return date, time


@dataclass
class CabFolder:
    coff_cab_start: int = 0
    c_cfdata: int = 0
    type_compress: int = TYPE_MSZIP


@dataclass
class CabMember:
    name: str
    cb_file: int
    uoff_folder_start: int
    i_folder: int = 0
    date: int = 0
    time: int = 0
    attribs: int = 0
    #: extracted member payload (uncompressed bytes)
    data: bytes = b""


@dataclass
class CabArchive:
    """Parsed / writable MSCF archive."""

    members: list[CabMember] = field(default_factory=list)
    folders: list[CabFolder] = field(default_factory=list)
    version_minor: int = 3
    version_major: int = 1
    flags: int = 0
    set_id: int = 12345
    i_cabinet: int = 0
    #: optional original CFDATA blocks (8-byte header + payload), kept so a
    #: pristine rebuild can reproduce the source archive byte-for-byte.
    _source_cfdata: list[bytes] = field(default_factory=list, repr=False)

    # -- parsing ---------------------------------------------------------

    @classmethod
    def parse(cls, data: bytes) -> "CabArchive":
        if len(data) < 44 or data[:4] != MSCF_SIGNATURE:
            raise CabFormatError("not an MSCF cabinet (bad signature)")
        (reserved1, cb_cabinet, reserved2, coff_files) = struct.unpack_from("<IIII", data, 4)
        if coff_files != 44:
            raise CabFormatError(f"unexpected coffFiles={coff_files} (only 44 observed)")
        version_minor, version_major = data[24], data[25]
        c_folders, c_files, flags, set_id, i_cabinet = struct.unpack_from("<HHHHH", data, 26)

        folders: list[CabFolder] = []
        off = 36
        for _ in range(c_folders):
            coff_start, c_cfdata, type_compress = struct.unpack_from("<IHH", data, off)
            folders.append(CabFolder(coff_start, c_cfdata, type_compress))
            off += 8
        if off != coff_files:
            raise CabFormatError(
                f"CFFILE table offset mismatch (computed {off}, declared {coff_files})"
            )

        members: list[CabMember] = []
        for _ in range(c_files):
            cb_file, uoff_start, i_folder, date, time, attribs = struct.unpack_from(
                "<IIHHHH", data, off
            )
            name_end = data.index(b"\x00", off + 16)
            name = data[off + 16 : name_end].decode("ascii", "replace")
            members.append(CabMember(name, cb_file, uoff_start, i_folder, date, time, attribs))
            off = name_end + 1

        # CFDATA blocks (full 8-byte header + payload)
        cfdata: list[bytes] = []
        if folders:
            folder = folders[0]
            d = folder.coff_cab_start
            for _ in range(folder.c_cfdata):
                if d + 8 > len(data):
                    raise CabFormatError("truncated CFDATA header")
                csum, cb_data, cb_uncomp = struct.unpack_from("<IHH", data, d)
                payload = data[d + 8 : d + 8 + cb_data]
                if len(payload) != cb_data:
                    raise CabFormatError("truncated CFDATA payload")
                cfdata.append(struct.pack("<IHH", csum, cb_data, cb_uncomp) + payload)
                d += 8 + cb_data
        arch = cls(
            members=members,
            folders=folders,
            version_minor=version_minor,
            version_major=version_major,
            flags=flags,
            set_id=set_id,
            i_cabinet=i_cabinet,
            _source_cfdata=cfdata,
        )
        return arch

    @classmethod
    def from_bytes(cls, data: bytes) -> "CabArchive":
        return cls.parse(data)

    # -- member extraction ----------------------------------------------

    def folder_stream(self) -> bytes:
        """Reconstruct the single-folder uncompressed stream."""
        if not self.folders:
            return b""
        if self.folders[0].type_compress != TYPE_MSZIP:
            raise CabFormatError(
                f"unsupported folder compression type {self.folders[0].type_compress}"
            )
        return mszip_decompress(blk[8:] for blk in self._source_cfdata)

    @staticmethod
    def _member_magic_ok(name: str, payload: bytes) -> bool:
        if payload.startswith(b"\xef\xbb\xbf<?xml"):
            return True
        if payload.startswith(b"**") and (b"**PART1" in payload[:512] or b"TRANSMIT FILE" in payload[:2048]):
            return True
        return False

    def extract_members(self, validate_magic: bool = True) -> list[CabMember]:
        """Extract members, locating them by sequential cbFile accumulation
        (the observed uoffFolderStart field carries a +512 deviation on the
        last member and must not be trusted)."""
        stream = self.folder_stream()
        out: list[CabMember] = []
        offset = 0
        for m in self.members:
            payload = stream[offset : offset + m.cb_file]
            if len(payload) != m.cb_file:
                raise CabFormatError(
                    f"member {m.name!r}: folder stream short ({len(payload)}/{m.cb_file})"
                )
            if validate_magic and not self._member_magic_ok(m.name, payload):
                raise CabFormatError(
                    f"member {m.name!r}: payload magic does not match expectations"
                )
            out.append(
                CabMember(
                    name=m.name,
                    cb_file=m.cb_file,
                    uoff_folder_start=offset,
                    i_folder=m.i_folder,
                    date=m.date,
                    time=m.time,
                    attribs=m.attribs,
                    data=payload,
                )
            )
            offset += m.cb_file
        return out

    def fill_member_data(self) -> list[CabMember]:
        """Extract members and store their payloads back onto the archive."""
        extracted = self.extract_members()
        for m, em in zip(self.members, extracted):
            m.data = em.data
            m.uoff_folder_start = em.uoff_folder_start
        return extracted

    # -- writing ---------------------------------------------------------

    def to_bytes(
        self,
        *,
        preserve_source_blocks: bool = False,
        date: int = 0x575F,
        time: int = 0xA32D,
        attribs: int = 0x00A0,
    ) -> bytes:
        """Serialize the archive.

        With ``preserve_source_blocks=True`` and untouched members, the output
        is byte-identical to the source archive.  Otherwise members are
        re-compressed into MSZIP blocks with a zero checksum field.
        """
        if not self.members:
            raise CabFormatError("cannot write an empty cabinet")

        if preserve_source_blocks and self._source_cfdata:
            if self.folder_stream() != b"".join(m.data for m in self.members):
                raise CabFormatError(
                    "members changed; cannot preserve source CFDATA blocks, "
                    "recompress instead"
                )
            cfdata = list(self._source_cfdata)
        else:
            stream = b"".join(m.data for m in self.members)
            blocks, _ = mszip_compress(stream)
            cfdata = []
            for blk in blocks:
                cb_uncomp = len(zlib.decompress(blk[2:], -15))
                cfdata.append(struct.pack("<IHH", 0, len(blk), cb_uncomp) + blk)
        if not self.folders:
            self.folders = [CabFolder(0, 0, TYPE_MSZIP)]

        folder_data = b"".join(cfdata)

        coff_files = 36 + 8 * len(self.folders)
        header_head = struct.pack(
            "<4sIIII", MSCF_SIGNATURE, 0, 0, 0, coff_files
        )
        header_body = b"\x00\x00\x00\x00" + struct.pack(
            "<BBHHHHH",
            self.version_minor,
            self.version_major,
            len(self.folders),
            len(self.members),
            self.flags,
            self.set_id,
            self.i_cabinet,
        )

        folder_table = b"".join(
            struct.pack("<IHH", f.coff_cab_start, f.c_cfdata, f.type_compress)
            for f in self.folders
        )

        file_table = b""
        offset = 0
        for i, m in enumerate(self.members):
            uoff = m.uoff_folder_start if preserve_source_blocks else offset
            file_table += struct.pack(
                "<IIHHHH",
                m.cb_file,
                uoff,
                m.i_folder,
                date,
                time,
                attribs,
            )
            file_table += m.name.encode("ascii", "replace") + b"\x00"
            offset += m.cb_file

        coff_cab_start = (
            len(header_head) + len(header_body) + len(folder_table) + len(file_table)
        )
        for f in self.folders:
            f.coff_cab_start = coff_cab_start
            f.c_cfdata = len(cfdata)
        folder_table = b"".join(
            struct.pack("<IHH", f.coff_cab_start, f.c_cfdata, f.type_compress)
            for f in self.folders
        )

        out = header_head + header_body + folder_table + file_table + folder_data
        # cbCabinet is the total archive size (field at offset 8)
        out = out[:8] + struct.pack("<I", len(out)) + out[12:]
        return out

    # -- convenience -----------------------------------------------------

    def summary(self) -> dict:
        return {
            "signature": "MSCF",
            "cb_cabinet": None,
            "version": f"{self.version_minor}.{self.version_major}",
            "folders": [{"type": f.type_compress, "blocks": f.c_cfdata} for f in self.folders],
            "set_id": self.set_id,
            "members": [
                {
                    "name": m.name,
                    "size": m.cb_file,
                    "uoff_folder_start": m.uoff_folder_start,
                }
                for m in self.members
            ],
        }


def read_cab(path: str) -> CabArchive:
    with open(path, "rb") as fh:
        return CabArchive.parse(fh.read())


def write_cab(archive: CabArchive, path: str, **kwargs) -> None:
    with open(path, "wb") as fh:
        fh.write(archive.to_bytes(**kwargs))
