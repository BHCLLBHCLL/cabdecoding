# P0 round 64: find ANY instruction referencing MeshGetEdgeEps /
# SelectSetVertex* / get_vertex IAT slots (lea/mov/call), then dump
# surrounding context of each hit site.
import sys
import lief
import capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

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
data = bytes(text.content)
base = ib + text.virtual_address
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

# collect all instructions referencing target slots + full disasm for context
insns = []
for ins in md.disasm(data, base):
    ref = None
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            if tgt in slots:
                ref = slots[tgt]
    insns.append((ins.address - ib, ins.mnemonic, ins.op_str, ref))
    if ref:
        print(f"REF {hex(ins.address - ib)}: {ins.mnemonic} {ins.op_str}  -> {ref}")

# context dump: +-12 instructions around each ref
idx_by_rva = {r: i for i, (r, *_ ) in enumerate(insns)}
for i, (r, m, o, ref) in enumerate(insns):
    if ref:
        print(f"\n--- context of {ref} at {hex(r)} ---")
        for j in range(max(0, i - 12), min(len(insns), i + 13)):
            rr, mm, oo, _ = insns[j]
            mark = ">>" if j == i else "  "
            print(f"{mark} {hex(rr)}: {mm} {oo}")
