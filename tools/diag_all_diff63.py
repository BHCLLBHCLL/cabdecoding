# P0 round 63: find callers of MeshGetEdgeEps / SelectSetVertexNum /
# SelectSetVertex / SelectCheckEdge / get_vertex@PreBody across
# STpreMesh .text; then disassemble MeshGetEdgeEps callers' context.
import sys
import lief
import capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP, X86_OP_IMM

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
slots = {va: nm for va, nm in iat.items()
         if any(t in nm for t in targets)}
print("slots:", {hex(k): v for k, v in slots.items()})

text = next(s for s in b.sections if s.name == ".text")
data = bytes(text.content)
base = ib + text.virtual_address
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
hits = {}
for ins in md.disasm(data, base):
    if ins.mnemonic not in ("call", "jmp"):
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            if tgt in slots:
                hits.setdefault(slots[tgt], []).append(
                    (ins.address - ib, ins.mnemonic))
for nm, lst in hits.items():
    print(f"\n{nm}: {len(lst)} call sites")
    print("  ", [hex(r) for r, _ in lst[:24]])
