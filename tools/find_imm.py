"""Disassemble a pskernel range and flag lines with a given immediate."""
import sys, lief, capstone
DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\pskernel.dll"
def main():
    rva = int(sys.argv[1], 16)
    size = int(sys.argv[2], 16)
    imm = int(sys.argv[3])
    b = lief.parse(DLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = bytes(b.get_content_from_virtual_address(rva, size))
    for ins in md.disasm(data, ib + rva):
        if ins.mnemonic.startswith("mov") and ins.operands:
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_IMM and (op.imm & 0xFFFFFFFF) == imm:
                    print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str}")
if __name__ == "__main__":
    main()
