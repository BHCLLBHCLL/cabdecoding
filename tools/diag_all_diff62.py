# P0 round 62: inside STpreMesh collector 0x1ab90 (~8KB), find every
# call to STpreBase imports (QueryPreParts / PreBody methods) to
# locate the all-mode vertex collection path.
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
            iat[va] = lib.name.split('.')[0] + "!" + e.name
base_imports = {va: nm for va, nm in iat.items() if "STpreBase" in nm}
print(f"STpreBase imports in mesh dll: {len(base_imports)}")
for va, nm in sorted(base_imports.items()):
    print(f"  {hex(va)}  {nm[:100]}")

text = next(s for s in b.sections if s.name == ".text")
data = bytes(text.content)
base = ib + text.virtual_address
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

LO, HI = 0x1ab90, 0x1ab90 + 0x2000
hits = []
for ins in md.disasm(data, base):
    rva = ins.address - ib
    if rva < LO or rva >= HI:
        continue
    if ins.mnemonic not in ("call", "jmp"):
        continue
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            if tgt in base_imports:
                hits.append((rva, ins.mnemonic, base_imports[tgt]))
print(f"\ncalls inside 0x1ab90..+0x2000 to STpreBase: {len(hits)}")
for rva, m, nm in hits:
    print(f"  {hex(rva)} {m} {nm[:110]}")
