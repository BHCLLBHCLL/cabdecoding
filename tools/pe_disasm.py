# Generic x64 PE disassembler: dump a range of any Cradle DLL with
# IAT/export annotation.
# usage: python tools/pe_disasm.py <dll-path> <rva-hex> <bytes> [<label>]
import sys, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

dll = Path(sys.argv[1])
rva = int(sys.argv[2], 16)
nbytes = int(sys.argv[3], 0)
label = sys.argv[4] if len(sys.argv) > 4 else f'{rva:#x}'
data = dll.read_bytes()
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt = e_lfanew + 24
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
    return None

def off_to_va(foff):
    for name, sva, vsize, raw, raw_size in sections:
        if raw <= foff < raw + raw_size:
            return sva + (foff - raw)
    return None

dd = opt + 112
imp_rva, imp_size = struct.unpack_from('<II', data, dd + 8)
off = va_to_off(imp_rva)
iat = {}
while off is not None:
    oft = struct.unpack_from('<I', data, off)[0]
    name_rva = struct.unpack_from('<I', data, off + 12)[0]
    first_thunk = struct.unpack_from('<I', data, off + 16)[0]
    if name_rva == 0:
        break
    noff = va_to_off(name_rva)
    dll_name = data[noff:noff + 80].split(b'\x00')[0].decode()
    oft_off = va_to_off(oft) if oft else va_to_off(first_thunk)
    ft_off = va_to_off(first_thunk)
    i = 0
    while True:
        hint = struct.unpack_from('<Q', data, oft_off + i * 8)[0]
        thunk = struct.unpack_from('<Q', data, ft_off + i * 8)[0]
        if hint == 0 and thunk == 0:
            break
        if hint & 0x8000000000000000:
            name = '#%d' % (hint & 0xFFFF)
        else:
            n = va_to_off(hint)
            name = (data[n + 2:n + 120].split(b'\x00')[0].decode('ascii',
                                                                   'replace')
                    if n is not None else '?')
        va = off_to_va(ft_off + i * 8)
        if va is not None:
            iat[va] = name.split('@')[0]
        i += 1
    off += 20

exp_rva, exp_size = struct.unpack_from('<II', data, dd)
eoff = va_to_off(exp_rva)
if eoff is not None:
    n_names = struct.unpack_from('<I', data, eoff + 24)[0]
    addr_rva = struct.unpack_from('<I', data, eoff + 28)[0]
    nameptr_rva = struct.unpack_from('<I', data, eoff + 32)[0]
    ord_rva = struct.unpack_from('<I', data, eoff + 36)[0]
    addr_off = va_to_off(addr_rva)
    nameptr_off = va_to_off(nameptr_rva)
    ord_off = va_to_off(ord_rva)
else:
    n_names = 0
exp = {}
for i in range(n_names):
    ord_ = struct.unpack_from('<H', data, ord_off + i * 2)[0]
    rva2 = struct.unpack_from('<I', data, addr_off + ord_ * 4)[0]
    np_rva = struct.unpack_from('<I', data, nameptr_off + i * 4)[0]
    noff = va_to_off(np_rva)
    nm = data[noff:noff + 200].split(b'\x00')[0].decode('ascii', 'replace')
    exp[rva2] = nm

md = Cs(CS_ARCH_X86, CS_MODE_64)
code = data[va_to_off(rva):va_to_off(rva) + nbytes]
print(f'; ---- {label} RVA {rva:#x} ({nbytes} bytes) ----')
for ins in md.disasm(code, rva):
    ops = ins.op_str
    if 'rip +' in ops or 'rip -' in ops:
        try:
            disp = int(ops.split('[')[1].split(']')[0]
                       .replace('rip + ', '').replace('rip - ', '-')
                       .replace('rip+', '').replace('rip-', '-'), 0)
            target = ins.address + ins.size + disp
            nm = iat.get(target) or exp.get(target)
            ops = ops + ('   ; ' + nm if nm else f'   ; -> {target:#x}')
        except Exception:
            pass
    elif ins.mnemonic.startswith('call') and ops.startswith('0x'):
        try:
            t = int(ops, 16)
            nm = exp.get(t)
            if nm:
                ops = ops + '   ; ' + nm
        except Exception:
            pass
    print(f'{ins.address:#10x}: {ins.mnemonic:8s} {ops}')
