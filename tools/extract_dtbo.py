#!/usr/bin/env python3
"""Extract individual DTBs from DTBO (Device Tree Blob Overlay) image.

DTBO format: header + entries, each with offset/size to a DTB or DT overlay.
DTB magic: 0xd00dfeed (big-endian)
"""

import struct
import sys
import os

DTB_MAGIC = 0xd00dfeed
DTBO_HEADER_SIZE = 120  # Standard DTBO header

def find_dtb_offsets(data):
    """Find all DTB magic numbers in the binary data."""
    offsets = []
    magic_bytes = struct.pack('>I', DTB_MAGIC)
    pos = 0
    while True:
        pos = data.find(magic_bytes, pos)
        if pos == -1:
            break
        offsets.append(pos)
        pos += 1
    return offsets

def read_dtb_size(data, offset):
    """Read the total size of a DTB from its header.
    
    DTB header structure:
      offset 0: magic (0xd00dfeed)
      offset 4: totalsize (big-endian u32)
    """
    if offset + 8 > len(data):
        return None
    magic = struct.unpack('>I', data[offset:offset+4])[0]
    if magic != DTB_MAGIC:
        return None
    size = struct.unpack('>I', data[offset+4:offset+8])[0]
    if size < 32 or size > len(data) - offset:
        return None
    return size

def extract_dtbs(dtbo_path, output_dir):
    """Extract DTBs from DTBO image."""
    with open(dtbo_path, 'rb') as f:
        data = f.read()
    
    print(f"[*] Read {len(data):,} bytes from {dtbo_path}")
    
    # Find all DTB offsets
    offsets = find_dtb_offsets(data)
    print(f"[*] Found {len(offsets)} potential DTB magic values at offsets: {[hex(o) for o in offsets[:10]]}")
    
    # Extract each DTB
    os.makedirs(output_dir, exist_ok=True)
    extracted = []
    
    for idx, offset in enumerate(offsets):
        size = read_dtb_size(data, offset)
        if size is None:
            print(f"[!] Offset {hex(offset)}: invalid DTB header or size")
            continue
        
        end = offset + size
        if end > len(data):
            print(f"[!] Offset {hex(offset)}: DTB extends past file end ({hex(end)} > {hex(len(data))})")
            continue
        
        dtb_data = data[offset:end]
        output_path = os.path.join(output_dir, f'dtb-{idx:02d}.dtb')
        
        with open(output_path, 'wb') as f:
            f.write(dtb_data)
        
        print(f"[+] Extracted dtb-{idx:02d}.dtb: offset {hex(offset)}, size {size:,} bytes")
        extracted.append((output_path, offset, size))
    
    return extracted

def analyze_dtb(dtb_path):
    """Print basic info about a DTB."""
    with open(dtb_path, 'rb') as f:
        header = f.read(40)
    
    if len(header) < 40:
        return "Too small"
    
    magic = struct.unpack('>I', header[0:4])[0]
    totalsize = struct.unpack('>I', header[4:8])[0]
    off_dt_struct = struct.unpack('>I', header[8:12])[0]
    off_dt_strings = struct.unpack('>I', header[12:16])[0]
    off_mem_rsvmap = struct.unpack('>I', header[16:20])[0]
    version = struct.unpack('>I', header[20:24])[0]
    last_comp_version = struct.unpack('>I', header[24:28])[0]
    boot_cpuid_phys = struct.unpack('>I', header[28:32])[0]
    size_dt_strings = struct.unpack('>I', header[32:36])[0]
    size_dt_struct = struct.unpack('>I', header[36:40])[0]
    
    return (f"magic={hex(magic)}, size={totalsize}, version={version}, "
            f"strings_size={size_dt_strings}, struct_size={size_dt_struct}")

if __name__ == '__main__':
    dtbo_path = sys.argv[1] if len(sys.argv) > 1 else 'dtb/a52s-dtbo/dtbo.img'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'dtb/a52s-dtbo'
    
    extracted = extract_dtbs(dtbo_path, output_dir)
    
    print(f"\n[*] Extracted {len(extracted)} DTBs to {output_dir}")
    print("\n[*] DTB analysis:")
    for path, offset, size in extracted:
        info = analyze_dtb(path)
        print(f"  {os.path.basename(path)}: {info}")
