# P0 diagnostic round 16: precise IAT slot resolution for the collector calls
# + relevant STpreBase exports.
import lief

MESH = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
BASE = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

b = lief.parse(MESH)
ib = b.imagebase
iat = {}
for e in b.imports:
    for f in e.entries:
        if f.name:
            nm = f.name.decode() if isinstance(f.name, bytes) else f.name
            iat[e.name + "!" + nm] = ib + f.iat_address
by_va = {v & 0xffffffffffff: k for k, v in iat.items()}

SLOTS = {
    "0x1b6f3": 0x7CA50, "0x1b71f": 0x7CB00, "0x1b735": 0x7BF90,
    "0x1b789": 0x7CB00, "0x1b79d": 0x7C690, "0x1b7b8": 0x7C9C0,
    "0x1b7cf": 0x7CA20, "0x1b84b": 0x7CC80, "0x1b87f": 0x7C660,
    "0x1b899": 0x7CAC0, "0x1b8a9": 0x7C660, "0x1b8e1": 0x7C378,
}
for site, slot in SLOTS.items():
    print(f"call@{site} -> iat {slot:#x} = {by_va.get(ib + slot, '??')}")

print("\n--- STpreBase exports (vertex/coord/part related) ---")
bb = lief.parse(BASE)
keys = ("PreBody", "PreFace", "PreEdge", "PreVertex", "VertexArray",
        "QueryPreParts", "Coord", "GetPoint", "PointArray", "Facet")
for e in bb.exported_functions:
    n = e.name or ""
    if any(k in n for k in keys):
        print(f"  {e.address:08x}  {n}")
