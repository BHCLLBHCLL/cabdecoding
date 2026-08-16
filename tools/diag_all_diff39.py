# P0 diagnostic round 39: generic disassembler for STpreBase_Bx64.dll.
import sys
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    rva = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    b = lief.parse(DLL)
    ib = b.imagebase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    md.skipdata = True
    exports = {e.address: e.name for e in b.exported_functions if e.name}
    # import name-table RVAs for slot-style targets
    iat = {}
    for lib in b.imports:
        for e in lib.entries:
            if e.name:
                va = e.iat_value if e.iat_value >= ib else e.iat_value + ib
                iat[va] = lib.name.split('.')[0] + "!" + e.name
    data = bytes(b.get_content_from_virtual_address(rva, count * 20))
    for ins in md.disasm(data, ib + rva, count=count):
        tgt = ""
        op = ins.op_str
        if ins.mnemonic in ("call", "jmp") and op.startswith("0x"):
            t = int(op, 16) - ib
            if t in exports:
                tgt = "  ; " + exports[t].split('@')[0]
            else:
                tgt = f"  ; rva {hex(t)}"
        elif "[" in op and "rip" in op and (ins.mnemonic.startswith("call")):
            try:
                if "rip + " in op:
                    disp = int(op.split("rip + ")[1].rstrip("]"), 16)
                else:
                    disp = -int(op.split("rip - ")[1].rstrip("]"), 16)
                slot = ins.address + ins.size + disp
                nm = iat.get(slot)
                if not nm:
                    raw = bytes(b.get_content_from_virtual_address(slot - ib, 8))
                    import struct
                    nt = struct.unpack("<Q", raw)[0]
                    if 0 < nt < ib:
                        d2 = bytes(b.get_content_from_virtual_address(nt, 120))
                        nm = "slot->" + d2[2:d2.find(b'\0', 2)].decode('ascii', 'replace')
                if nm:
                    tgt = "  ; " + nm.split('!')[-1][:60]
            except Exception:
                pass
        print(f"{ins.address-ib:08x}:  {ins.mnemonic:8s} {op:46s}{tgt}")

if __name__ == "__main__":
    main()
