"""Disassemble STpreBase_Bx64.dll grid functions for B5 root-cause."""
import sys
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    rva = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    bin_ = lief.parse(DLL)
    ib = bin_.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    sections = list(bin_.sections)
    def section_for(r):
        for s in sections:
            if s.virtual_address <= r < s.virtual_address + s.size:
                return s
        return None
    s = section_for(rva)
    print(f"# RVA {hex(rva)} -> section {s.name if s else None}")
    data = bin_.get_content_from_virtual_address(rva, count * 16)
    code = bytes(data)
    for ins in md.disasm(code, ib + rva, count=count):
        # resolve branch targets
        tgt = ""
        if ins.mnemonic.startswith("call") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm - ib
            tgt = f"  ; -> RVA {hex(t)}"
        elif ins.mnemonic in ("jmp",) and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm - ib
            tgt = f"  ; -> RVA {hex(t)}"
        print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {ins.op_str:40s}{tgt}")

if __name__ == "__main__":
    main()
