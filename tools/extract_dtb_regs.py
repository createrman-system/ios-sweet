#!/usr/bin/env python3
"""Extract specific hardware register addresses from DTB files.

This tool searches DTB string tables for key hardware identifiers and their
associated 'reg' properties (physical addresses).
"""

import struct
import sys
import os
import re

DTB_MAGIC = 0xd00dfeed

def parse_dtb_header(data):
    """Parse DTB header."""
    if len(data) < 40:
        return None
    
    header = struct.unpack('>8I', data[0:32])
    magic, totalsize, off_dt_struct, off_dt_strings, off_mem_rsvmap, version, last_comp_version, boot_cpuid_phys = header
    size_dt_strings = struct.unpack('>I', data[32:36])[0]
    size_dt_struct = struct.unpack('>I', data[36:40])[0]
    
    if magic != DTB_MAGIC:
        return None
    
    return {
        'magic': magic,
        'totalsize': totalsize,
        'off_dt_struct': off_dt_struct,
        'off_dt_strings': off_dt_strings,
        'off_mem_rsvmap': off_mem_rsvmap,
        'version': version,
        'size_dt_strings': size_dt_strings,
        'size_dt_struct': size_dt_struct,
    }

def extract_strings(data, offset, size):
    """Extract null-terminated strings from a region."""
    strings = []
    pos = offset
    end = offset + size
    while pos < end:
        null_pos = data.find(b'\x00', pos)
        if null_pos == -1 or null_pos >= end:
            break
        s = data[pos:null_pos].decode('utf-8', errors='ignore')
        if s:
            strings.append(s)
        pos = null_pos + 1
    return strings

def extract_u32_be(data, offset):
    """Extract 32-bit big-endian value."""
    if offset + 4 > len(data):
        return None
    return struct.unpack('>I', data[offset:offset+4])[0]

def extract_u64_be(data, offset):
    """Extract 64-bit big-endian value."""
    if offset + 8 > len(data):
        return None
    return struct.unpack('>Q', data[offset:offset+8])[0]

def find_hardware_addresses(dtb_path):
    """Extract hardware register addresses from DTB."""
    with open(dtb_path, 'rb') as f:
        data = f.read()
    
    header = parse_dtb_header(data)
    if header is None:
        return {}
    
    # Extract all strings
    strings = extract_strings(data, header['off_dt_strings'], header['size_dt_strings'])
    
    # Search for key hardware identifiers
    hw_keywords = {
        'gic': ['gic', 'interrupt-controller', 'arm,gic-v3'],
        'ufs': ['ufshc', 'ufs', 'ufshc_mem', 'ufsphy'],
        'display': ['framebuffer', 'simple-framebuffer', 'mdss', 'dsi', 'display-subsystem', 'continuous-splash'],
        'timer': ['timer', 'arm,armv8-timer', 'cntpct'],
        'pmic': ['pmic', 'spmi', 'qcom,spmi-pmic', 'pm6150', 'pm7325', 'pm8350'],
        'touch': ['touch', 'goodix', 'synaptics', 'stm', 'sec_ts', 'fts', 'gt9'],
        'i2c': ['i2c', 'qcom,i2c', 'qup', 'geni', 'se7'],
    }
    
    results = {}
    for category, keywords in hw_keywords.items():
        results[category] = []
        for s in strings:
            s_lower = s.lower()
            for kw in keywords:
                if kw in s_lower:
                    results[category].append(s)
                    break
    
    return results

def scan_dtb_for_addresses(dtb_path):
    """Scan DTB structure for address patterns."""
    with open(dtb_path, 'rb') as f:
        data = f.read()
    
    header = parse_dtb_header(data)
    if header is None:
        return []
    
    # Look for 'reg' property followed by large addresses (MMIO base addresses)
    # DTB format: property name string (null-terminated) + value
    # 'reg' property often contains physical addresses
    
    addresses = []
    
    # Scan struct area for 32/64-bit addresses that look like MMIO bases
    struct_start = header['off_dt_struct']
    struct_end = struct_start + header['size_dt_struct']
    
    pos = struct_start
    while pos < struct_end - 4:
        # Look for 32-bit values starting with 0x0 or 0x1 (common Qualcomm MMIO)
        val = struct.unpack('>I', data[pos:pos+4])[0]
        
        # Check if this looks like a Qualcomm MMIO address
        # Typical range: 0x00000000 - 0x01000000 (SoC), 0x80000000+ (RAM)
        if (val >= 0x00000000 and val <= 0x02000000) or (val >= 0x17000000 and val <= 0x18000000) or (val >= 0xa0000000 and val <= 0xb0000000):
            addresses.append((pos - struct_start, val, hex(val)))
        
        pos += 1
    
    return addresses

def analyze_dtb(dtb_path):
    """Full DTB analysis with hardware address extraction."""
    print(f"\n{'='*80}")
    print(f"DTB: {os.path.basename(dtb_path)}")
    print(f"{'='*80}")
    
    with open(dtb_path, 'rb') as f:
        data = f.read()
    
    header = parse_dtb_header(data)
    if header is None:
        print("[!] Invalid DTB header")
        return
    
    print(f"\nHeader Info:")
    print(f"  Total size: {header['totalsize']:,} bytes")
    print(f"  Version: {header['version']}")
    print(f"  Strings size: {header['size_dt_strings']:,} bytes")
    print(f"  Struct size: {header['size_dt_struct']:,} bytes")
    
    # Extract hardware identifiers
    hw_addrs = find_hardware_addresses(dtb_path)
    
    print(f"\nHardware Identifiers Found:")
    for category, items in hw_addrs.items():
        if items:
            print(f"\n  {category.upper()}:")
            for item in sorted(set(items)):
                print(f"    - {item}")
    
    # Scan for address values
    print(f"\nAddress-like Values in DTB (potential MMIO bases):")
    addresses = scan_dtb_for_addresses(dtb_path)
    
    # Group and deduplicate
    unique_addrs = {}
    for offset, val, hex_val in addresses:
        if hex_val not in unique_addrs:
            unique_addrs[hex_val] = val
    
    for hex_val in sorted(unique_addrs.keys(), key=lambda x: int(x, 16)):
        val = unique_addrs[hex_val]
        print(f"  {hex_val} ({val:,} decimal)")
    
    return header, hw_addrs

def main():
    dtbo_dir = sys.argv[1] if len(sys.argv) > 1 else 'dtb/a52s-dtbo'
    
    dtb_files = sorted([f for f in os.listdir(dtbo_dir) if f.endswith('.dtb')])
    
    print(f"\n[*] Analyzing {len(dtb_files)} DTB files in {dtbo_dir}")
    
    for dtb_file in dtb_files:
        dtb_path = os.path.join(dtbo_dir, dtb_file)
        try:
            analyze_dtb(dtb_path)
        except Exception as e:
            print(f"[!] Error analyzing {dtb_file}: {e}")
    
    print(f"\n{'='*80}")
    print(f"[*] Analysis complete. Check output above for hardware addresses.")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()
