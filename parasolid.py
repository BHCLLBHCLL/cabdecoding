"""P2: lightweight partial extraction of Parasolid *text* transmit streams.

scSTREAM Pre stores geometry as a plain-text ``.x_t`` Parasolid transmit
file (in contrast to the binary ``.x_b`` streams inside scFLOW's
``main.sctsnapshot``). This module extracts the parts that are useful for
metadata browsing without a Parasolid kernel:

- ``**PART1`` header attribute block (MC / FRU / APPL / SITE / KEY / FILE /
  DATE ...);
- ``**PART2`` base schema and the T51 line (modeller version + full schema);
- schema field names from the text field table (``[token][count] name[len]``
  frames, names may wrap across lines with an inserted space);
- record markers and SDL attributes (``SDL/TYSA_NAME`` / ``SDL/TYSA_UNAME``)
  with part names carried either as literal text or as space-separated ASCII
  character codes.

Full B-rep topology restore stays out of scope (see DEV_SUMMARY.md §2.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# [token][count] then name[len]; names may be wrapped mid-word by a space.
_FIELD_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*\d)\s+"
    r"([A-Za-z_$][A-Za-z_/$]*(?: [A-Za-z_$][A-Za-z_/$]*)*)(?=\d)")
_ASCII_RUN_RE = re.compile(r"(?:[1-9][0-9]{1,2}\s+){3,}")
_RECORD_RE = re.compile(r"\bT\d+\b")


@dataclass
class ParasolidStream:
    """Partial-extraction result for a text transmit file."""

    size: int
    version: Optional[int] = None
    schema: Optional[str] = None        # e.g. SCH_3401153_34101_1300
    header: dict[str, str] = field(default_factory=dict)
    field_names: list[str] = field(default_factory=list)
    record_count: int = 0
    sdl_attributes: list[str] = field(default_factory=list)
    part_names: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Parasolid text transmit: {self.size} B"
                 f" version={self.version} schema={self.schema}"]
        lines.append("header: " + ", ".join(
            f"{k}={v}" for k, v in self.header.items()))
        lines.append(f"schema fields ({len(self.field_names)}): "
                     + ", ".join(self.field_names))
        lines.append(f"records: {self.record_count}  "
                     f"SDL: {', '.join(self.sdl_attributes) or '-'}")
        if self.part_names:
            lines.append("SDL part names: " + ", ".join(self.part_names))
        return "\n".join(lines)


def _decode_ascii_codes(text: str) -> list[str]:
    """Decode runs like '115 112 101 97 107 101 114' into strings."""
    out: list[str] = []
    for run in _ASCII_RUN_RE.findall(text):
        nums = [int(x) for x in run.split()]
        # split into maximal printable sub-runs (record data pollutes the
        # raw match with following indices)
        chunk: list[int] = []
        for v in nums:
            if 32 <= v < 127:
                chunk.append(v)
            else:
                if len(chunk) >= 3:
                    out.append(bytes(chunk).decode("ascii"))
                chunk = []
        if len(chunk) >= 3:
            out.append(bytes(chunk).decode("ascii"))
    return out


def parse_transmit(data: bytes) -> ParasolidStream:
    text = data.decode("utf-8", "replace")
    result = ParasolidStream(size=len(data))

    # -- **PART1 header attributes ----------------------------------------
    part1 = text.find("**PART1;")
    part2 = text.find("**PART2;")
    if part1 >= 0 and part2 > part1:
        for line in text[part1:part2].splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().strip("*")
            if not key:
                continue
            result.header[key] = value.strip().rstrip(";").strip()

    # -- schema / version --------------------------------------------------
    sch = re.search(r"SCH=\s*(SCH_\d+_\d+_\d+)", text)
    result.schema = sch.group(1) if sch else None
    t51 = re.search(r"T51\s*:\s*TRANSMIT FILE created by modeller version "
                    r"(\d+)\s+(SCH_\d+_\d+_\d+)", text)
    if t51:
        result.version = int(t51.group(1))
        result.schema = t51.group(2)

    # -- schema field names ------------------------------------------------
    idx = text.find("T51 :")
    region = text[idx:idx + 7000].replace("\n", " ") if idx >= 0 else text
    seen: list[str] = []
    for m in _FIELD_RE.finditer(region):
        name = m.group(2).replace(" ", "")
        if len(name) >= 3 and name not in seen:
            seen.append(name)
    result.field_names = seen

    result.record_count = len(_RECORD_RE.findall(text))
    result.sdl_attributes = sorted(set(
        m.group(0) for m in re.finditer(r"SDL/TYSA_[A-Z]+", text)))
    names: list[str] = []
    for sd in re.finditer(r"SDL/TYSA_(?:NAME|UNAME)", text):
        ctx = text[sd.start():sd.start() + 500]
        for cand in _decode_ascii_codes(ctx):
            if cand not in names:
                names.append(cand)
        for word in re.findall(r"[A-Za-z_]{3,40}", ctx):
            if (word.isascii() and word not in names
                    and word not in ("SDL", "TYSA", "NAME", "UNAME")):
                names.append(word)
    result.part_names = names
    return result


def parse_file(path: str) -> ParasolidStream:
    with open(path, "rb") as fh:
        return parse_transmit(fh.read())
