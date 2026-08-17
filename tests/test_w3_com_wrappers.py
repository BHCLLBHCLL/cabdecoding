"""W3: typed Sketch/Property/Table COM wrappers + SetParam packing."""
from __future__ import annotations

import cab_stpre_api as api


class _Dummy:
    def __init__(self):
        self.calls = []

    def _FlagAsMethod(self, name):
        self.calls.append(("flag", name))

    def __getattr__(self, name):
        def _fn(*args):
            self.calls.append((name, args))
            return args[0] if args else 1
        return _fn


def test_pack_set_param_pads_zeros():
    assert api.pack_set_param("flow") == ("flow", 0, 0, 0)
    assert api.pack_set_param("flow", 1.5) == ("flow", 1.5, 0, 0)
    assert api.pack_set_param("flow", 1, 2, 3) == ("flow", 1, 2, 3)


def test_typed_wrappers_and_setparam():
    raw = _Dummy()
    sk = api.STpreSketch(raw)
    assert sk.SetClose("T") == "T"
    assert ("SetClose", ("T",)) in raw.calls

    doc = api.STpreDoc(raw)
    sk2 = doc.GetSketcher()
    assert isinstance(sk2, api.STpreSketch)
    tbl = doc.GetTable("t1")
    assert isinstance(tbl, api.STpreTable)
    prop = doc.GetPropertyEntity("air")
    assert isinstance(prop, api.STpreProperty)

    val = api.STpreValue(raw)
    val.SetParam("uv")
    assert ("SetParam", ("uv", 0, 0, 0)) in raw.calls
    val.SetParam3(1, 2)
    assert ("SetParam3", (1, 2, 0)) in raw.calls
    t2 = val.GetTable("uv")
    assert isinstance(t2, api.STpreTable)

    assert api.API_MEMBER_COUNTS["Sketch"] == 12
    assert api.API_MEMBER_COUNTS["Property"] == 22
    assert api.API_MEMBER_COUNTS["Table"] == 12
    for cls, names in (("Sketch", api.API_CATALOG["Sketch"]),
                       ("Property", api.API_CATALOG["Property"]),
                       ("Table", api.API_CATALOG["Table"])):
        wrapper = {"Sketch": api.STpreSketch, "Property": api.STpreProperty,
                   "Table": api.STpreTable}[cls]
        for n in names:
            assert hasattr(wrapper, n), n
