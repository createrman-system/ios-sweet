#!/usr/bin/env python3
"""
Extract register (reg) properties from Device Tree Binary files.
Properly parses DTB structure to extract MMIO addresses.
"""

import struct
import sys
import os

DTB_MAGIC = 0xd00dfeed
FDT_BEGIN_NODE = 0x00000001
FDT_END_NODE = 0x00000002
FDT_PROP = 0x00000003
FDT_NOP = 0x00000004
FDT_END = 0x00000009

class DTBParser:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        
        # Parse header
        if len(data) < 40:
            raise ValueError("DTB too small")
        
        header = struct.unpack('>8I', data[0:32])
        (self.magic, self.totalsize, self.off_dt_struct, self.off_dt_strings,
         self.off_mem_rsvmap, self.version, self.last_comp_version,
         self.boot_cpuid_phys) = header
        
        if self.magic != DTB_MAGIC:
            raise ValueError(f"Invalid magic: 0x{self.magic:x}")
        
        (self.size_dt_strings, self.size_dt_struct) = struct.unpack(
            '>II', data[32:40])
        
        self.struct_pos = self.off_dt_struct
        self.strings_offset = self.off_dt_strings
    
    def get_string(self, offset):
        """Get string from string table"""
        pos = self.strings_offset + offset
        end = self.data.find(b'\x00', pos)
        if end == -1:
            end = len(self.data)
        return self.data[pos:end].decode('utf-8', errors='ignore')
    
    def read_be32(self, offset):
        """Read big-endian 32-bit value"""
        return struct.unpack('>I', self.data[offset:offset+4])[0]
    
    def read_be64(self, offset):
        """Read big-endian 64-bit value"""
        return struct.unpack('>Q', self.data[offset:offset+8])[0]
    
    def align(self, pos, alignment=4):
        """Align position"""
        if pos % alignment != 0:
            pos += alignment - (pos % alignment)
        return pos
    
    def parse_struct(self):
        """Parse device tree structure"""
        pos = self.off_dt_struct
        devices = {}
        stack = [{'name': '/', 'regs': []}]  # Root node
        
        while pos < self.off_dt_struct + self.size_dt_struct:
            pos = self.align(pos)
            
            token = self.read_be32(pos)
            pos += 4
            
            if token == FDT_BEGIN_NODE:
                # Read node name (null-terminated string)
                name_end = self.data.find(b'\x00', pos)
                name = self.data[pos:name_end].decode('utf-8', errors='ignore')
                pos = name_end + 1
                pos = self.align(pos)
                
                node = {'name': name, 'regs': [], 'children': {}}
                stack.append(node)
                
            elif token == FDT_PROP:
                # Property
                prop_len = self.read_be32(pos)
                pos += 4
                name_offset = self.read_be32(pos)
                pos += 4
                prop_data = self.data[pos:pos+prop_len]
                pos += prop_len
                pos = self.align(pos)
                
                prop_name = self.get_string(name_offset)
                
                if stack:
                    if prop_name == 'reg':
                        # Parse reg property (array of addresses/sizes)
                        # Format: 32-bit or 64-bit addresses and sizes depending on #address-cells and #size-cells
                        try:
                            regs = []
                            # Try parsing as 64-bit pairs (address, size)
                            for i in range(0, len(prop_data), 16):
                                if i + 16 <= len(prop_data):
                                    addr = struct.unpack('>Q', prop_data[i:i+8])[0]
                                    size = struct.unpack('>Q', prop_data[i+8:i+16])[0]
                                    regs.append((addr, size))
                            if not regs and len(prop_data) >= 8:
                                # Try 32-bit pairs
                                for i in range(0, len(prop_data), 8):
                                    if i + 8 <= len(prop_data):
                                        addr = struct.unpack('>I', prop_data[i:i+4])[0]
                                        size = struct.unpack('>I', prop_data[i+4:i+8])[0]
                                        regs.append((addr, size))
                            stack[-1]['regs'] = regs
                        except Exception as e:
                            pass
                    
                    stack[-1][prop_name] = prop_data[:20]  # Store first 20 bytes for ref
                
            elif token == FDT_END_NODE:
                if len(stack) > 1:
                    node = stack.pop()
                    if len(stack) > 0:
                        parent = stack[-1]
                        parent['children'][node['name']] = node
                        # If this node has regs and a useful name, record it
                        if node['regs'] and any(kw in node['name'].lower() for kw in
                                                 ['gic', 'ufs', 'mdss', 'dsi', 'timer', 'pmic', 'spmi', 'touch', 'i2c', 'qup']):
                            devices['/'.join([n.get('name', '?') for n in stack] + [node['name']])] = node
            
            elif token == FDT_END:
                break
            
            elif token == FDT_NOP:
                continue
            else:
                # Unknown token, try to recover
                pass
        
        return devices

def find_interesting_regs(dtb_path):
    """Find interesting register addresses in DTB"""
    with open(dtb_path, 'rb') as f:
        data = f.read()
    
    parser = DTBParser(data)
    devices = parser.parse_struct()
    
    print(f"\n{'='*80}")
    print(f"DTB: {os.path.basename(dtb_path)}")
    print(f"{'='*80}\n")
    
    # Sort and display
    keywords = ['gic', 'interrupt', 'ufs', 'mdss', 'dsi', 'timer', 'pmic', 'spmi', 'touch', 'i2c', 'qup']
    interesting = {}
    
    for path, node in devices.items():
        name_lower = node['name'].lower()
        if any(kw in name_lower for kw in keywords):
            interesting[path] = node
    
    # Print results
    for path in sorted(interesting.keys()):
        node = interesting[path]
        print(f"[{node['name']}]")
        if node['regs']:
            for addr, size in node['regs']:
                print(f"  reg: 0x{addr:x}, size: 0x{size:x}")
        print()
    
    return interesting

def main():
    dtbo_dir = sys.argv[1] if len(sys.argv) > 1 else 'dtb/a52s-dtbo'
    
    dtb_files = sorted([f for f in os.listdir(dtbo_dir) if f.endswith('.dtb')])
    
    all_devices = {}
    for dtb_file in dtb_files:
        dtb_path = os.path.join(dtbo_dir, dtb_file)
        try:
            devices = find_interesting_regs(dtb_path)
            for path, node in devices.items():
                if path not in all_devices:
                    all_devices[path] = []
                all_devices[path].append((dtb_file, node))
        except Exception as e:
            print(f"[!] Error parsing {dtb_file}: {e}\n")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY: Devices found across all DTBs")
    print(f"{'='*80}\n")
    
    for path in sorted(all_devices.keys()):
        print(f"{path}:")
        for dtb_file, node in all_devices[path]:
            if node['regs']:
                for addr, size in node['regs']:
                    print(f"  [{dtb_file}] 0x{addr:x} (size: 0x{size:x})")
        print()

if __name__ == '__main__':
    main()
