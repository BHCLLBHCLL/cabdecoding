# P0 diagnostic round 31: find call sites of PreFace::PushLine /
# PreFace::GetVertex inside STpreMesh_Bx64.dll via IAT scan, then
# disassemble around each call site to reveal the push condition.
import sys
import lief
import capstone

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll"

TARGETS = ["PushLine@PreFace", "GetVertex@PreFace", "PreVertex"]

def main():
    b = lief.parse(DLL)
    ib = b.imagebase
    slots = {}
    for lib in b.imports:
        for e in lib.entries:
            if e.name and any(t in e.name for t in TARGETS):
                # lief iat_value here is an RVA on this build -> VA
                slot = e.iat_value if e.iat_value >= ib else e.iat_value + ib
                slots[slot] = e.name
                print(f"import {e.name}  iat_rva={hex(e.iat_value)} va={hex(slot)}")
    if not slots:
        print("no matching imports found")
        return

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    text = None
    for s in b.sections:
        if s.name == ".text":
            text = s
            break
    base = ib + text.virtual_address
    content = bytes(text.content)
    print(f".text va={hex(base)} size={hex(len(content))}")

    hits = []
    i = 0
    while True:
        i = content.find(b"\xff\x15", i)
        if i < 0:
            break
        # rip-relative disp32
        import struct
        disp = struct.unpack_from("<i", content, i + 2)[0]
        tgt = base + i + 6 + disp
        if tgt in slots:
            hits.append((base + i, slots[tgt]))
        i += 2
    print(f"\ncall sites ({len(hits)}):")
    for va, name in hits:
        print(f"  rva={hex(va - ib)}  {name}")
    return hits

if __name__ == "__main__":
    main()
