# P0 round 50: read the ThinOutPolyLine eps constant at .rdata and find
# callers of PreBody::ThinOutPolyLine (0x2a4940) in STpreBase.
import sys
import lief
import capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
import struct

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"
b = lief.parse(DLL)
ib = b.imagebase

# 1) constant used at 0x2a4a11: movsd xmm7, [rip+0x189377]; next ip = 0x2a4a19
const_va = 0x2a4a19 + 0x189377
raw = bytes(b.get_content_from_virtual_address(const_va, 8))
print(f"const @ rva {hex(const_va)} = {struct.unpack('<d', raw)[0]!r}")

# 2) scan .text for direct calls/jmps to 0x2a4940
text = next(s for s in b.sections if s.name == ".text")
data = bytes(text.content)
base = ib + text.virtual_address
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
tgt_rva = 0x2a4940
callers = []
for ins in md.disasm(data, base):
    if ins.mnemonic in ("call", "jmp") and ins.operands \
            and ins.operands[0].type == X86_OP_IMM:
        if ins.operands[0].imm - ib == tgt_rva:
            callers.append((ins.address - ib, ins.mnemonic))
print("callers of ThinOutPolyLine:", [hex(r) for r, _ in callers])

# resolve caller function names from exports
exports = {e.address: e.name for e in b.exported_functions if e.name}
for rva, m in callers:
    print(f"  {hex(rva)} {m}")
