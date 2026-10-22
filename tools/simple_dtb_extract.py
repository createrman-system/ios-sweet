#!/usr/bin/env python3
"""
Simple DTB extractor: search for 'reg' keyword and extract nearby address values.
"""

import struct
import sys
import os

def find_registers_in_dtb(dtb_path):
    """Find 'reg' properties and their values in a DTB."""
    
    with open(dtb_path, 'rb') as f:
        data = f.read()
    
    # Magic number for DTB
    magic_pos = data.find(bytes.fromhex('d00dfeed'))
    if magic_pos == -1:
        return []
    
    # Headers in DTB indicate where device tree structure is
    header_offset = magic_pos
    try:
        magic, total_size, dt_struct_off, dt_strings_off = struct.unpack(
            '>4I', data[header_offset:header_offset+16])
    except:
        return []
    
    # All device tree data is between dt_struct_off and dt_strings_off
    struct_end = dt_strings_off
    struct_data = data[header_offset + dt_struct_off:header_offset + struct_end]
    
    # Search for the string 'reg' in this region
    # It will appear as a property name reference
    results = []
    pos = 0
    
    # Look for property tokens (0x00000003) followed by length and name offset pointing to "reg"
    while pos < len(struct_data) - 8:
        # Token is 4 bytes (big-endian uint32)
        token = struct.unpack('>I', struct_data[pos:pos+4])[0]
        
        if token == 0x00000003:  # FDT_PROP token
            # Next: property length (4 bytes)
            # Next: string offset (4 bytes)
            try:
                prop_len = struct.unpack('>I', struct_data[pos+4:pos+8])[0]
                str_offset = struct.unpack('>I', struct_data[pos+8:pos+12])[0]
                
                # Get property name from string table
                str_offset_abs = header_offset + dt_strings_off + str_offset
                str_end = data.find(b'\x00', str_offset_abs)
                if str_end == -1:
                    str_end = len(data)
                
                prop_name = data[str_offset_abs:str_end].decode('utf-8', errors='ignore')
                
                # Get property data
                prop_data_offset = pos + 12
                prop_data = struct_data[prop_data_offset:prop_data_offset + prop_len]
                
                if prop_name == 'reg' and prop_len > 0:
                    # Parse as 64-bit pairs (or mixed depending on cell size)
                    addrs = []
                    for i in range(0, len(prop_data)-7, 8):
                        addr = struct.unpack('>Q', prop_data[i:i+8])[0]
                        addrs.append(f"0x{addr:x}")
                    
                    results.append({
                        'offset': pos,
                        'prop_len': prop_len,
                        'addresses': addrs
                    })
                
                # Align to next token
                pos += 12 + prop_len
                while pos % 4 != 0:
                    pos += 1
            except Exception as e:
                pos += 4
        else:
            pos += 4
    
    return results

def main():
    dtbo_dir = sys.argv[1] if len(sys.argv) > 1 else 'dtb/a52s-dtbo'
    
    dtb_files = sorted([f for f in os.listdir(dtbo_dir) if f.endswith('.dtb')])
    
    all_addresses = {}
    
    for dtb_file in dtb_files:
        dtb_path = os.path.join(dtbo_dir, dtb_file)
        print(f"\n{'='*80}")
        print(f"Extracting registers from: {dtb_file}")
        print(f"{'='*80}")
        
        try:
            regs = find_registers_in_dtb(dtb_path)
            print(f"Found {len(regs)} 'reg' properties\n")
            
            # Collect all addresses and count occurrences
            for reg in regs:
                for addr in reg['addresses']:
                    if addr not in all_addresses:
                        all_addresses[addr] = 0
                    all_addresses[addr] += 1
        except Exception as e:
            print(f"Error: {e}\n")
    
    # Print interesting addresses (>= 0x01d00000 and  < 0xb0000000, typical MMIO range)
    print(f"\n{'='*80}")
    print("Extracted MMIO Addresses")
    print(f"{'='*80}\n")
    
    interesting = {}
    for addr, count in all_addresses.items():
        try:
            addr_val = int(addr, 16)
            # Filter for typical MMIO ranges: 0x01000000 - 0xb0000000
            if 0x01000000 <= addr_val <= 0xb0000000:
                interesting[addr_val] = count
        except:
            pass
    
    for addr in sorted(interesting.keys()):
        count = interesting[addr]
        print(f"  0x{addr:08x} (appears {count}x)")
    
    # Specific targets
    print(f"\n{'='*80}")
    print("Known MMIO targets (if found):")
    print(f"{'='*80}\n")
    
    targets = {
        'GIC GICD': 0x17a00000,
        'GIC GICR': 0x17a60000,
        'UFS HC': 0x01d84000,
        'Framebuffer': 0x9c000000,
    }
    
    for name, addr in targets.items():
        addr_hex = f"0x{addr:x}"
        if addr_hex in all_addresses:
            print(f"✓ {name}: {addr_hex} (found {all_addresses[addr_hex]}x)")
        else:
            print(f"✗ {name}: {addr_hex} (NOT FOUND)")

if __name__ == '__main__':
    main()
