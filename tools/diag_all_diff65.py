# P0 round 65: numpy disp32 scan of whole .text for refs to the
# MeshGetEdgeEps / SelectSetVertex* / get_vertex IAT slots (capstone
# full-section disasm stops early on invalid bytes, misses refs).
import numpy as np
import lief

MESH = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
b = lief.parse(MESH)
ib = b.imagebase

iat = {}
for lib in b.imports:
    for e in lib.entries:
        if e.name:
            va = e.iat_value if e.iat_value >= ib else e.iat_value + ib
            iat[va] = e.name
targets = ["MeshGetEdgeEps", "SelectSetVertexNum", "SelectSetVertex",
           "SelectCheckEdge", "SelectCheckFace", "get_vertex@PreBody",
           "GetPartsFaceAxisPlane"]
slots = {va: nm for va, nm in iat.items() if any(t in nm for t in targets)}

text = next(s for s in b.sections if s.name == ".text")
raw = np.frombuffer(bytes(text.content), dtype=np.uint8)
base = ib + text.virtual_address
n = len(raw)
disp = np.zeros(n - 3, dtype=np.int64)
# little-endian int32 at each offset
b0 = raw[0:n-3].astype(np.int64)
b1 = raw[1:n-2].astype(np.int64)
b2 = raw[2:n-1].astype(np.int64)
b3 = raw[3:n].astype(np.int64)
disp = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
# sign-extend
disp = np.where(disp >= 2**31, disp - 2**32, disp)
off = np.arange(n - 3, dtype=np.int64)
va_of_next_ip = base + off + 4
tgt = va_of_next_ip + disp
for sv, nm in sorted(slots.items()):
    hits = off[(tgt == sv)]
    print(f"{nm}: {len(hits)} raw disp hits at rva " +
          ", ".join(hex(int(h)) for h in hits[:20]))
