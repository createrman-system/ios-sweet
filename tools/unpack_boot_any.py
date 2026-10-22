#!/usr/bin/env python3
"""Unpack Android boot.img header v0–v4 (handles page_size=0 for v3/v4)."""
import struct, sys, os

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
b = open(src, 'rb').read()

if b[:8] != b'ANDROID!':
    raise SystemExit("Not an ANDROID! boot image")

# Common header fields (v0–v2 layout)
(ks, ka, rs, ra, ss, sa, ta, ps, ver, osv) = struct.unpack_from('<10I', b, 8)

# Header v3/v4 use a different layout and fixed page size
if ver >= 3:
    # v3/v4 header starts the same for magic + kernel/ramdisk sizes
    # but page_size is hardcoded to 4096 and many fields moved
    ks, rs = struct.unpack_from('<II', b, 8)          # kernel_size, ramdisk_size
    osv = struct.unpack_from('<I', b, 16)[0]          # os_version
    # page size is always 4096 for v3/v4
    ps = 4096
    # kernel and ramdisk are the only payload parts for pure boot.img v3/v4
    # (dtb lives in vendor_boot or dtbo)
    ka = ra = sa = ta = ss = 0
    print(f"[*] Detected header version {ver} → forcing page_size = 4096")

cmd = b[64:64+512].split(b'\0')[0]
if ver < 3:
    cmd += b[608:608+1024].split(b'\0')[0]

info = dict(
    kernel_size=ks, kernel_addr=hex(ka),
    ramdisk_size=rs, ramdisk_addr=hex(ra),
    second_size=ss, tags_addr=hex(ta),
    page_size=ps, header_version=ver,
    os_version=hex(osv),
    name=b[48:64].split(b'\0')[0].decode(errors='ignore'),
    cmdline=cmd.decode(errors='ignore')
)

rnd = lambda n: (n + ps - 1) // ps * ps if ps else n
off = ps if ver < 3 else 4096          # header occupies one page

parts = [('kernel', ks), ('ramdisk', rs), ('second', ss)]

if ver == 1 or ver == 2:
    rds, rdo, hs = struct.unpack_from('<IQI', b, 1632)
    parts.append(('recovery_dtbo', rds))
    info['header_size'] = hs
if ver == 2:
    ds, da = struct.unpack_from('<IQ', b, 1648)
    parts.append(('dtb', ds))
    info['dtb_addr'] = hex(da)

for name, sz in parts:
    if sz:
        open(f'{out}/{name}', 'wb').write(b[off:off+sz])
    info[name + '_offset'] = off
    off += rnd(sz)

with open(f'{out}/header.txt', 'w') as f:
    for k, v in info.items():
        f.write(f'{k}: {v}\n')

print(open(f'{out}/header.txt').read())
print(f"\n[*] Extracted to {out}/")