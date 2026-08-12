"""Domain fit to CAD bounding box (STpre-like Import behaviour)."""
from __future__ import annotations

import numpy as np

from cabxml import StpreModel, new_stpre_bytes, parse_stpre
import cab_domain
import cab_parts


def test_fit_domain_to_parts_updates_base_size():
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(
        name="Domain(cuboid)",
        base=(0.0, 0.0, 0.0),
        size=(100.0, 100.0, 100.0),
        unit="mm",
        material="air(incompressible/20C)",
    )
    ok = cab_parts.register_primitive(
        m, name="Box1", kind="cube",
        params={"base": (10.0, 20.0, 30.0), "size": (40.0, 50.0, 60.0)},
        material="", attribute="Solid", color="180,180,180,255")
    assert ok
    tess = cab_parts.tess_for_spec(
        "cube", {"base": (10.0, 20.0, 30.0), "size": (40.0, 50.0, 60.0)})
    tess.name = "Box1"
    # tess points are metres (cab_parts cube_tess / 1000)
    fitted = cab_domain.fit_domain_to_parts(m, [tess])
    assert fitted is not None
    mn, mx = fitted
    np.testing.assert_allclose(mn, (10.0, 20.0, 30.0), atol=1e-6)
    np.testing.assert_allclose(mx, (50.0, 70.0, 90.0), atol=1e-6)
    base = m.domain_base()
    size = m.domain_size()
    assert base is not None and size is not None
    np.testing.assert_allclose(base, (10.0, 20.0, 30.0), atol=1e-6)
    np.testing.assert_allclose(size, (40.0, 50.0, 60.0), atol=1e-6)
    # RootBlock follows domain
    rb = m.root_block_bounds()
    assert rb is not None
    np.testing.assert_allclose(rb[:3], (10.0, 20.0, 30.0), atol=1e-6)
    np.testing.assert_allclose(rb[3:], (50.0, 70.0, 90.0), atol=1e-6)


def test_fit_domain_empty_returns_none():
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    assert cab_domain.fit_domain_to_parts(m, []) is None
