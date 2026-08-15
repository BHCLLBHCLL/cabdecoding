"""Disassemble STpreBase_Bx64.dll function with constant resolution."""
import sys, lief, capstone, struct

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    rva = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    b = lief.parse(DLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = bytes(b.get_content_from_virtual_address(rva, count * 20))
    for ins in md.disasm(data, ib + rva, count=count):
        note = ""
        # resolve RIP-relative memory operands to constants
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp - ib
                try:
                    raw = bytes(b.get_content_from_virtual_address(tgt, 8))
                    val = struct.unpack("<d", raw)[0]
                    note = f"  ; [rva {tgt:x}] = {val:.17g}"
                except Exception:
                    pass
        print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str:40s}{note}")

if __name__ == "__main__":
    main()
