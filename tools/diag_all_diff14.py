# P0 diagnostic round 14: locate the part-type switch that references the
# jump table at RVA 0x1cba0 inside the collector (0x1ab90..), dump the table
# entries and disassemble the dispatch.
import struct
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
TABLE = 0x1cba0

b = lief.parse(DLL)
ib = b.imagebase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

def read(va, n):
    return bytes(b.get_content_from_virtual_address(va, n))

exports = {e.address: e.name for e in b.exported_functions if e.name}

def dis(rva, count=200, quiet=False):
    out = []
    data = read(rva, count * 16)
    for ins in md.disasm(data, ib + rva, count=count):
        tgt = ""
        if ins.mnemonic in ("call", "jmp") and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm - ib
            nm = exports.get(t)
            tgt = f"  ; -> {nm}" if nm else f"  ; -> RVA {hex(t)}"
        if not quiet:
            print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str:48s}{tgt}")
        out.append(ins)
    return out

# 1) scan 0x1ab90..0x1cba0 for rip-relative refs to TABLE
scan_start, scan_len = 0x1ab90, 0x1cba0 - 0x1ab90
data = read(scan_start, scan_len)
hits = []
for ins in md.disasm(data, ib + scan_start):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            tgt_rva = ins.address + ins.size - ib + op.mem.disp
            if tgt_rva == TABLE or TABLE <= tgt_rva < TABLE + 0x200:
                hits.append((ins.address - ib, ins.mnemonic, ins.op_str, tgt_rva))
print("refs to table region:")
for h in hits:
    print(f"  {h[0]:08x}: {h[1]} {h[2]}  -> {h[3]:08x}")

# 2) dump table entries (assume DWORD rel offsets to table base)
ents = struct.unpack_from("<42i", read(TABLE, 42 * 4), 0)
print("\ntable entries (target RVA = TABLE + off):")
for i, e in enumerate(ents):
    print(f"  type 0x{0x10f+i:x}: off={e:+#x} -> RVA {TABLE + e:08x}"
          f"  ({exports.get(TABLE + e, '')})")
