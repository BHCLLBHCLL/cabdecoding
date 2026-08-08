"""STpre standard material library loader.

Primary source (reverse-located under Cradle install)::

    C:\\Program Files\\Cradle\\CradleCFD2025.2\\Programs_x64\\standard_property_ENG.xml

Fallback: vendored copy at ``data/standard_property_ENG.xml`` (same file).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cabxml import PropertyDoc, PropertyModel, parse_property

_CRADLE_CANDIDATES = (
    Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
         r"\standard_property_ENG.xml"),
    Path(os.environ.get("CRADLE_CFD_HOME", "")) / "Programs_x64"
    / "standard_property_ENG.xml",
)
_VENDORED = Path(__file__).resolve().parent / "data" / "standard_property_ENG.xml"

_cached: Optional[bytes] = None


def standard_property_path() -> Optional[Path]:
    """Return the first readable standard_property_ENG.xml path."""
    for p in _CRADLE_CANDIDATES:
        if p and p.is_file():
            return p
    if _VENDORED.is_file():
        return _VENDORED
    return None


def load_standard_property_bytes() -> bytes:
    """Raw UTF-8 BOM bytes of the STpre standard material library."""
    global _cached
    if _cached is not None:
        return _cached
    path = standard_property_path()
    if path is None:
        raise FileNotFoundError(
            "standard_property_ENG.xml not found (Cradle install or data/)")
    _cached = path.read_bytes()
    # ensure BOM for cabxml round-trip consistency
    if not _cached.startswith(b"\xef\xbb\xbf"):
        _cached = b"\xef\xbb\xbf" + _cached
    return _cached


def standard_property_model() -> PropertyModel:
    return PropertyModel(parse_property(load_standard_property_bytes()))


def merge_standard_into(props: PropertyModel) -> int:
    """Append missing standard groups/entries into ``props``.

    Returns the number of entry elements added.
    """
    import copy
    import xml.etree.ElementTree as ET
    from cabxml import _children, _first

    std = standard_property_model()
    existing_groups = {}
    for g in props.groups():
        n = _first(g, "name")
        name = n.text.strip() if n is not None and n.text else ""
        existing_groups[name] = g

    existing_mats = set(props.material_names())
    added = 0
    for sg in std.groups():
        sn = _first(sg, "name")
        gname = sn.text.strip() if sn is not None and sn.text else ""
        if gname not in existing_groups:
            # deepcopy group element into props root
            clone = copy.deepcopy(sg)
            clone.tail = "\n   "
            props.root.append(clone)
            existing_groups[gname] = clone
            added += len(_children(clone, "entry"))
            for ent in _children(clone, "entry"):
                n = _first(ent, "name")
                if n is not None and n.text:
                    existing_mats.add(n.text.strip())
            continue
        # merge missing entries into existing group
        dest = existing_groups[gname]
        for ent in _children(sg, "entry"):
            n = _first(ent, "name")
            name = n.text.strip() if n is not None and n.text else ""
            if not name or name in existing_mats:
                continue
            dest.append(copy.deepcopy(ent))
            existing_mats.add(name)
            added += 1
    return added


def ensure_complete_library(props: Optional[PropertyModel]) -> PropertyModel:
    """Return a property model that includes the full standard library.

    If ``props`` is None, returns a fresh standard model. Otherwise merges
    missing standard materials into ``props`` in-place and returns it.
    """
    if props is None:
        return standard_property_model()
    try:
        merge_standard_into(props)
    except FileNotFoundError:
        pass
    return props
