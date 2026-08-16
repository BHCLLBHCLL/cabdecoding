# P0 diagnostic round 15: full .text scan for refs to the 0x1cba0 table.
import struct
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
TABLE = 0x1cba0

b = lief.parse(DLL)
ib = b.imagebase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

text = None
for s in b.sections:
    if s.name == ".text":
        text = s
        break
print(f".text va={hex(text.virtual_address)} size={hex(text.virtual_size)}")
data = bytes(text.content)
base = text.virtual_address

hits = []
start = base
insn_iter = md.disasm(data, ib + start)
for ins in insn_iter:
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            t = ins.address + ins.size - ib + op.mem.disp
            if TABLE <= t < TABLE + 0x100:
                hits.append((ins.address - ib, ins.mnemonic, ins.op_str, t))
        if op.type == capstone.x86.X86_OP_IMM and op.imm - ib == TABLE:
            hits.append((ins.address - ib, ins.mnemonic, ins.op_str, TABLE))
print("refs:")
for h in hits:
    print(f"  {h[0]:08x}: {h[1]} {h[2]} -> {h[3]:08x}")

# also dump table region bytes to find true extent
td = bytes(b.get_content_from_virtual_address(TABLE - 0x20, 0x100))
print("\nbytes around table:")
for r in range(0, 0x100, 16):
    off = TABLE - 0x20 + r
    print(f"  {off:08x}: " + " ".join(f"{x:02x}" for x in td[r:r+16]))
