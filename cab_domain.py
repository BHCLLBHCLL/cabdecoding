"""M2: computational domain editing (Edit -> Reset Computational Domain).

The domain is stored in ``<analysis_region type="cube">`` with ``<base>`` /
``<size>`` in mm (matching the cab XML).  This module:

- reads the current domain into a :class:`DomainSpec`;
- writes a :class:`DomainSpec` back (keeping the six face_list regions);
- creates a cube domain when the project has none (e.g. tr03);
- computes the world-space part bounds used by "CAD Data Size".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

import cab_vtk
from cabxml import StpreModel


@dataclass
class DomainSpec:
    """Computational domain parameters (coordinates in ``unit``)."""

    coordinate: str = "cartesian"   # cartesian | cylindrical | axial
    unit: str = "mm"
    xyz_min: tuple[float, float, float] = (-100.0, -100.0, -100.0)
    xyz_max: tuple[float, float, float] = (150.0, 300.0, 315.0)
    material: str = ""
    extend: tuple[float, float, float] = (0.0, 0.0, 0.0)
    auto_y_for_axial: bool = False


def domain_from_xml(model: StpreModel) -> Optional[DomainSpec]:
    """Read the current domain; ``None`` when no ``<analysis_region>``."""
    ar = model.analysis_region()
    if ar is None:
        return None
    base = model.domain_base() or (0.0, 0.0, 0.0)
    size = model.domain_size() or (1.0, 1.0, 1.0)
    return DomainSpec(
        coordinate=ar.attrib.get("type", "cube") if ar.attrib.get("type")
        in ("cube", "cylinder") else "cartesian",
        unit=model.domain_unit(),
        xyz_min=base,
        xyz_max=(base[0] + size[0], base[1] + size[1], base[2] + size[2]),
        material=model.domain_material(),
    )


def apply_domain(model: StpreModel, spec: DomainSpec,
                 *, name: str = "Domain(cuboid)") -> bool:
    """Write a domain back to the XML; creates it when missing."""
    base = spec.xyz_min
    size = (spec.xyz_max[0] - base[0],
            spec.xyz_max[1] - base[1],
            spec.xyz_max[2] - base[2])
    model.ensure_domain(
        name=name, base=base, size=size, unit=spec.unit,
        material=spec.material)
    if spec.coordinate != "cartesian":
        ar = model.analysis_region()
        if ar is not None:
            ar.attrib["type"] = "cylinder" if spec.coordinate == "cylindrical" \
                else "cube"
    return True


def part_bounds(model: StpreModel, tess) -> tuple[np.ndarray, np.ndarray]:
    """World-space min/max over every tessellated part (XML transform
    applied).  Returns two (3,) arrays; both are inf when no geometry."""
    transforms = {p.name: p.transform for p in model.parts()}
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    if not tess:
        return lo, hi
    for part in tess:
        pts = np.asarray(part.points, dtype=np.float64)
        if len(pts) == 0:
            continue
        pts = cab_vtk._apply_transform(
            pts, transforms.get(part.name, ""))
        lo = np.minimum(lo, pts.min(0))
        hi = np.maximum(hi, pts.max(0))
    return lo, hi
