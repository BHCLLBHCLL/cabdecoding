"""Find UTF-8/UTF-16 strings matching a substring in a DLL."""
import sys, lief

DLL = r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreBase_Bx64.dll"

def main():
    sub = sys.argv[1]
    bin_ = lief.parse(DLL)
    import re
    for s in bin_.sections:
        data = bytes(s.content)
        # utf-8 ascii
        for m in re.finditer(re.escape(sub.encode()), data):
            print(f"ascii @ rva 0x{s.virtual_address + m.start():08x}: ...{data[max(0,m.start()-40):m.end()+40]!r}")
        # utf-16le
        pat = sub.encode("utf-16le")
        for m in re.finditer(re.escape(pat), data):
            print(f"utf16 @ rva 0x{s.virtual_address + m.start():08x}")

if __name__ == "__main__":
    main()
