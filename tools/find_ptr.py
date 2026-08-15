"""Find absolute-VA pointers to target RVAs (vtable/function-pointer refs)."""
import sys, lief, struct

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    targets = [int(x, 16) for x in sys.argv[1:]]
    bin_ = lief.parse(DLL)
    ib = bin_.imagebase
    for tgt in targets:
        va = ib + tgt
        hits = []
        # 8-byte little-endian absolute pointer
        for s in bin_.sections:
            data = bytes(s.content)
            pat = struct.pack("<Q", va)
            start = 0
            while True:
                i = data.find(pat, start)
                if i < 0: break
                hits.append((s.name, s.virtual_address + i))
                start = i + 1
        print(f"target {hex(tgt)} (VA {hex(va)}): {len(hits)} ptr refs")
        for h in hits[:40]:
            print(f"   {h[0]} @ rva {h[1]:08x}")

if __name__ == "__main__":
    main()
