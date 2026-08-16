# P0 round 51: find cross-DLL callers of PreBody::ThinOutPolyLine in
# STpreMesh_Bx64.dll and disassemble the whole function body.
import sys
import lief
import capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
from pathlib import Path

PROG = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
BASE_DLL = PROG + r"\STpreBase_Bx64.dll"
MESH_DLL = PROG + r"\STpreMesh_Bx64.dll"
TARGET = "ThinOutPolyLine"

bb = lief.parse(BASE_DLL)
ib_base = bb.imagebase
exp_rva = None
for e in bb.exported_functions:
    if e.name and TARGET in e.name:
        exp_rva = e.address
        print(f"export {e.name} @ rva {hex(exp_rva)}")
if exp_rva is None:
    sys.exit("export not found")

# (a) imports in STpreMesh referencing the target
d = lief.parse(MESH_DLL)
ib = d.imagebase
slots = {}
for lib in d.imports:
    for en in lib.entries:
        if en.name and TARGET in en.name:
            va = en.iat_value if en.iat_value >= ib else en.iat_value + ib
            slots[va] = f"{lib.name}!{en.name}"
print("import slots:", {hex(k): v for k, v in slots.items()})
if slots:
    text = next(s for s in d.sections if s.name == ".text")
    data = bytes(text.content)
    base = ib + text.virtual_address
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for ins in md.disasm(data, base):
        if ins.mnemonic not in ("call", "jmp"):
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in slots:
                    print(f"MESH call @ rva {hex(ins.address - ib)} "
                          f"{ins.mnemonic} [{slots[tgt]}]")

# (b) function body
print("\n=== ThinOutPolyLine body ===")
text = next(s for s in bb.sections if s.name == ".text")
raw = bytes(text.content)
off = exp_rva - text.virtual_address
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for ins in md.disasm(raw[off:off + 0x220], ib_base + exp_rva):
    print(f"  {ins.address - ib_base:08x}  {ins.mnemonic} {ins.op_str}")
    if ins.mnemonic == "ret":
        break
