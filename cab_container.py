"""P0: Microsoft Cabinet (MSCF) container with Cradle's MSZIP payload.

Cradle scSTREAM Pre `.cab` files are standard MS Cabinet archives whose
CFDATA block header deviates from [MS-CAB]: the two size fields are u16
instead of u32 (8-byte header: csum u32 + cbData u16 + cbUncomp u16).
Folder payloads are MSZIP: a sequence of 'CK' + raw DEFLATE blocks that
share a single 32 KiB LZ77 history window across block boundaries.

See CAB_FORMAT_SPEC.md §2 for the reverse-engineered layout.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional


class CabFormatError(ValueError):
    """Raised when bytes do not look like a supported Cradle CAB."""


MSZIP_BLOCK_SIZE = 32768          # MSZIP decompresses at most 32 KiB per block
_MAX_BLOCK_COMP = 0xFFFF          # cbData is a u16 in this variant


# --------------------------------------------------------------------------
# MSZIP codec (pure Python, shared-history window across blocks)
# --------------------------------------------------------------------------

def mszip_compress(data: bytes, level: int = 6,
                   chunk: int = MSZIP_BLOCK_SIZE) -> tuple[list[bytes], int]:
    """Compress *data* into MSZIP blocks ('CK' + raw DEFLATE).

    Each block references the previous 32 KiB of output via zlib's ``zdict``
    parameter, mirroring how Cradle / makecab share the LZ77 window across
    blocks. Returns ``(blocks, len(data))``.
    """
    blocks: list[bytes] = []
    out_so_far = b""
    for start in range(0, len(data), chunk):
        piece = data[start:start + chunk]
        if out_so_far:
            co = zlib.compressobj(level, zlib.DEFLATED, -15, 8, 0,
                                  out_so_far[-MSZIP_BLOCK_SIZE:])
        else:
            co = zlib.compressobj(level, zlib.DEFLATED, -15)
        payload = co.compress(piece) + co.flush()
        block = b"CK" + payload
        if len(block) > _MAX_BLOCK_COMP:
            raise CabFormatError(
                f"MSZIP block too large ({len(block)} > {_MAX_BLOCK_COMP}); "
                "chunking assumption violated")
        blocks.append(block)
        out_so_far += piece
    return blocks, len(data)


def mszip_decompress(blocks: list[bytes]) -> bytes:
    """Decompress MSZIP blocks, priming each with the previous output."""
    out = b""
    for i, block in enumerate(blocks):
        if block[:2] != b"CK":
            raise CabFormatError(f"MSZIP block {i} missing 'CK' marker")
        if i == 0:
            dec = zlib.decompressobj(-15)
        else:
            dec = zlib.decompressobj(-15, zdict=out[-MSZIP_BLOCK_SIZE:])
        out += dec.decompress(block[2:]) + dec.flush()
    return out


# --------------------------------------------------------------------------
# Container model
# --------------------------------------------------------------------------

@dataclass
class CabFolder:
    coff_cab_start: int          # absolute offset of first CFDATA block
    c_cfdata: int                # number of CFDATA blocks
    type_compress: int           # 0 = stored, 1 = MSZIP


@dataclass
class CabMember:
    name: str
    cb_file: int
    uoff_folder_start: int
    i_folder: int
    date: int
    time: int
    attribs: int
    data: Optional[bytes] = None


@dataclass
class _CfdataBlock:
    csum: int
    cb_data: int
    cb_uncomp: int
    payload: bytes             # 'CK' + deflate (or raw for stored folders)

    def to_bytes(self) -> bytes:
        return struct.pack("<IHH", self.csum, self.cb_data, self.cb_uncomp) \
            + self.payload


class CabArchive:
    """Parsed Cradle CAB archive with read + write support."""

    def __init__(self) -> None:
        self.version_minor = 0
        self.version_major = 0
        self.cfolders = 0
        self.cfiles = 0
        self.flags = 0
        self.set_id = 0
        self.i_cabinet = 0
        self.folders: list[CabFolder] = []
        self.members: list[CabMember] = []
        self._blocks: list[_CfdataBlock] = []
        self._raw: bytes = b""
        self._prefix: bytes = b""          # header + folder/file tables
        self._trailing: bytes = b""

    # -- parsing ----------------------------------------------------------

    @classmethod
    def parse(cls, data: bytes) -> "CabArchive":
        if len(data) < 48 or data[:4] != b"MSCF":
            raise CabFormatError("not a Microsoft Cabinet archive (no MSCF)")
        arch = cls()
        arch._raw = data
        arch.version_minor = data[24]
        arch.version_major = data[25]
        arch.cfolders = struct.unpack_from("<H", data, 26)[0]
        arch.cfiles = struct.unpack_from("<H", data, 28)[0]
        arch.flags = struct.unpack_from("<H", data, 30)[0]
        arch.set_id = struct.unpack_from("<H", data, 32)[0]
        arch.i_cabinet = struct.unpack_from("<H", data, 34)[0]
        coff_files = struct.unpack_from("<I", data, 16)[0]

        folder_off = coff_files - 8 * arch.cfolders
        if folder_off < 36:
            raise CabFormatError("inconsistent folder/file table offsets")
        for i in range(arch.cfolders):
            start, n, ctype = struct.unpack_from("<IHH", data, folder_off + 8 * i)
            arch.folders.append(CabFolder(start, n, ctype))

        off = coff_files
        for _ in range(arch.cfiles):
            cb_file, uoff, ifolder, date, time, attribs = \
                struct.unpack_from("<IIHHHH", data, off)
            name_end = data.index(b"\x00", off + 16)
            name = data[off + 16:name_end].decode("ascii", "replace")
            arch.members.append(CabMember(
                name, cb_file, uoff, ifolder, date, time, attribs))
            off = name_end + 1

        # CFDATA blocks follow the CFFILE table (single folder in samples).
        pos = arch.folders[0].coff_cab_start
        arch._prefix = data[:pos]
        for i in range(arch.folders[0].c_cfdata):
            if pos + 8 > len(data):
                raise CabFormatError(f"CFDATA block {i} truncated")
            csum, cb_data, cb_uncomp = struct.unpack_from("<IHH", data, pos)
            payload = data[pos + 8:pos + 8 + cb_data]
            if len(payload) != cb_data:
                raise CabFormatError(f"CFDATA block {i} payload truncated")
            arch._blocks.append(_CfdataBlock(csum, cb_data, cb_uncomp, payload))
            pos += 8 + cb_data
        arch._trailing = data[pos:]
        return arch

    # -- decompression ----------------------------------------------------

    def folder_stream(self) -> bytes:
        """Decompressed (concatenated) folder payload."""
        folder = self.folders[0]
        if folder.type_compress == 0:
            return b"".join(b.payload for b in self._blocks)
        if folder.type_compress == 1:
            return mszip_decompress([b.payload for b in self._blocks])
        raise CabFormatError(
            f"unsupported folder compression type {folder.type_compress}")

    def fill_member_data(self) -> list[CabMember]:
        """Slice member payloads out of the folder stream (idempotent)."""
        if all(m.data is not None for m in self.members):
            return self.members
        stream = self.folder_stream()
        for m in self.members:
            end = m.uoff_folder_start + m.cb_file
            if end > len(stream):
                raise CabFormatError(
                    f"member {m.name!r} out of folder stream bounds")
            m.data = stream[m.uoff_folder_start:end]
        return self.members

    def extract_members(self) -> list[CabMember]:
        self.fill_member_data()
        return self.members

    # -- writing ----------------------------------------------------------

    def to_bytes(self, preserve_source_blocks: bool = True) -> bytes:
        """Rebuild the archive.

        ``preserve_source_blocks=True`` reproduces the original file
        byte-for-byte (raw CFDATA blocks are kept verbatim); otherwise the
        folder stream (built from the current member payloads, so edited
        member data is honoured) is re-compressed with :func:`mszip_compress`.
        """
        if preserve_source_blocks and self._raw:
            return self._prefix + b"".join(
                b.to_bytes() for b in self._blocks) + self._trailing

        if any(m.data is None for m in self.members):
            self.fill_member_data()
        stream = b"".join(m.data or b"" for m in self.members)
        blocks, _ = mszip_compress(stream)
        return self._build_prefix(len(blocks), stream) + b"".join(
            struct.pack("<IHH", 0, len(blk),
                        min(len(stream) - 32768 * i, 32768))
            + blk for i, blk in enumerate(blocks))

    def _build_prefix(self, n_blocks: int, stream: bytes) -> bytes:
        """Header + CFFOLDER + CFFILE table for a re-compressed archive."""
        coff_files = 36 + 8 * len(self.folders)
        table_size = 0
        for m in self.members:
            table_size += 16 + len(m.name.encode("ascii", "replace")) + 1
        coff_cab_start = coff_files + table_size

        header = b"MSCF" \
            + struct.pack("<I", 0) \
            + struct.pack("<I", coff_cab_start + len(stream)) \
            + struct.pack("<I", 0) \
            + struct.pack("<I", coff_files) \
            + b"\x00\x00\x00\x00" \
            + bytes([self.version_minor, self.version_major]) \
            + struct.pack("<HHHHH", len(self.folders), len(self.members),
                          self.flags, self.set_id, self.i_cabinet)
        folder_table = b"".join(
            struct.pack("<IHH", coff_cab_start, n_blocks,
                        f.type_compress if i == 0 else 0)
            for i, f in enumerate(self.folders))
        # offset of folder stream is identical for every folder in a
        # single-folder archive; multi-folder re-packing is out of P0 scope.
        assert len(self.folders) == 1, "multi-folder rebuild not supported"
        file_table = b""
        off = 0
        for m in self.members:
            size = len(m.data) if m.data is not None else m.cb_file
            file_table += struct.pack("<IIHHHH", size, off, m.i_folder,
                                      m.date, m.time, m.attribs)
            file_table += m.name.encode("ascii", "replace") + b"\x00"
            off += size
        return header + folder_table + file_table

    # -- helpers ----------------------------------------------------------

    def summary(self) -> dict:
        self.fill_member_data()
        import hashlib
        return {
            "version": f"{self.version_minor}.{self.version_major}",
            "folders": [
                {"coff_cab_start": f.coff_cab_start,
                 "c_cfdata": f.c_cfdata,
                 "type_compress": f.type_compress}
                for f in self.folders],
            "members": [
                {"name": m.name,
                 "size": m.cb_file,
                 "offset": m.uoff_folder_start,
                 "date": f"{m.date:04x}",
                 "time": f"{m.time:04x}",
                 "md5": hashlib.md5(m.data or b"").hexdigest()}
                for m in self.members],
        }
