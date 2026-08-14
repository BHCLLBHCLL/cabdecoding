"""B4: run-length box encoding (_merge_boxes) — convex single box + round-trip."""
import numpy as np
import pytest

from cab_mesh import _boxes_from_mask, _merge_boxes, cell_mask_from_boxes


def test_merge_boxes_convex_single_box():
    # A filled convex region collapses to one 1-based inclusive box, matching
    # STpre's PARTS run encoding for a box ("20 39 20 39 20 39" in box_bm.s).
    mask = np.ones((20, 20, 20), dtype=bool)
    boxes = _merge_boxes(mask)
    assert boxes == [(1, 20, 1, 20, 1, 20)], boxes


def test_merge_boxes_roundtrip_l_shape():
    # An L-shaped region (bottom-left block + a j-extension) must round-trip
    # exactly through boxes -> mask, i.e. encoding is lossless.
    mask = np.zeros((10, 10, 3), dtype=bool)
    mask[0:5, 0:5, :] = True      # bottom-left 5x5 block
    mask[5:10, 0:3, :] = True     # j-extension 5x3
    boxes = _merge_boxes(mask)
    assert boxes, "no boxes produced"
    rebuilt = cell_mask_from_boxes(10, 10, 3, [list(b) for b in boxes])
    assert np.array_equal(rebuilt, mask), f"round-trip mismatch: {boxes}"


def test_merge_boxes_roundtrip_random():
    rng = np.random.default_rng(7)
    mask = rng.random((8, 9, 6)) < 0.4
    boxes = _merge_boxes(mask)
    rebuilt = cell_mask_from_boxes(8, 9, 6, [list(b) for b in boxes])
    assert np.array_equal(rebuilt, mask), "random round-trip mismatch"
