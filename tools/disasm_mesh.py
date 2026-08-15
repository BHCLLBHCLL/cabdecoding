# Dump MeshFineDivide + full MeshFineExecute with IAT annotations.
import sys, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

dll = Path(r'C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\STpreMesh_Bx64.dll')
data = dll.read_bytes()
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt = e_lfanew + 24
image_base = struct.unpack_from('<Q', data, opt + 24)[0]
sections = []
off = opt + struct.unpack_from('<H', data, e_lfanew + 20)[0]
for _ in range(nsec):
    name = data[off:off + 8].rstrip(b'\x00').decode('ascii', 'replace')
    vsize = struct.unpack_from('<I', data, off + 8)[0]
    va = struct.unpack_from('<I', data, off + 12)[0]
    raw_size = struct.unpack_from('<I', data, off + 16)[0]
    raw = struct.unpack_from('<I', data, off + 20)[0]
    sections.append((name, va, vsize, raw, raw_size))
    off += 40

def va_to_off(va):
    for name, sva, vsize, raw, raw_size in sections:
        if sva <= va < sva + max(vsize, raw_size):
            return raw + (va - sva)
    raise ValueError(hex(va))

def dump(va_rva, nbytes, label):
    off = va_to_off(va_rva)
    code = data[off:off + nbytes]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    print(f'; ---- {label} RVA {va_rva:#x} ----')
    for ins in md.disasm(code, va_rva):
        ops = ins.op_str
        if 'rip +' in ops or 'rip -' in ops:
            try:
                disp = int(ops.split('[')[1].split(']')[0]
                           .replace('rip + ', '').replace('rip - ', '-')
                           .replace('rip+', '').replace('rip-', '-'), 0)
                target = ins.address + ins.size + disp
                ops = ops + f'   ; -> {target:#x}'
            except Exception:
                pass
        print(f'{ins.address:#10x}: {ins.mnemonic:8s} {ops}')
    print()

dump(0x25570, 0x120, 'MeshFineDivide')
dump(0x25690, 0x600, 'MeshFineExecute')
