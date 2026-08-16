# P0 diagnostic round 37: slots hold import-name-table RVAs (2-byte hint
# + ASCIIZ).  Read the symbol names directly.
import struct
import lief

MDLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"
SLOTS = {
    0x1adc4: 0x61d06, 0x1ae4c: 0x61c96, 0x1ae5d: 0x61c5d,
    0x1ae76: 0x61614, 0x1aea9: 0x614e1, 0x1aeea: 0x61580,
    0x1af29: 0x61551, 0x1b0ab: 0x613c7, 0x1b0e5: 0x619e5,
    0x1b108: 0x61aaa, 0x1b135: 0x6121d, 0x1b14b: 0x6120f,
    0x1b17a: 0x61210, 0x1b1aa: 0x611e0, 0x1b238: 0x6197a,
}

def main():
    b = lief.parse(MDLL)
    ib = b.imagebase
    for site, disp in sorted(SLOTS.items()):
        slot_rva = site + 6 + disp
        raw = bytes(b.get_content_from_virtual_address(slot_rva, 8))
        nt_rva = struct.unpack("<Q", raw)[0]
        if nt_rva <= 0 or nt_rva > ib:
            print(f"call@{hex(site)}: slot->{hex(nt_rva)} (not a name RVA?)")
            continue
        data = bytes(b.get_content_from_virtual_address(nt_rva, 100))
        hint = struct.unpack_from("<H", data)[0]
        name = data[2:data.find(b'\0', 2)].decode('ascii', 'replace')
        if len(name) > 64:
            name = name[:64] + "..."
        print(f"call@{hex(site)}: hint={hint} {name}")

if __name__ == "__main__":
    main()
