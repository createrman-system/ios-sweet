#!/usr/bin/env python3
"""
Parse live FDT from A52s device and extract critical MMIO addresses.
"""

import struct
import sys

def parse_fdt_header(data):
    """Parse FDT header (first 40 bytes)."""
    if len(data) < 40:
        raise ValueError("FDT too small")
    
    header = struct.unpack('>10I', data[0:40])
    (magic, totalsize, off_dt_struct, off_dt_strings, off_mem_rsvmap,
     version, last_comp_version, boot_cpuid_phys, size_dt_strings,
     size_dt_struct) = header
    
    if magic != 0xd00dfeed:
        raise ValueError(f"Invalid FDT magic: 0x{magic:x}")
    
    return {
        'magic': magic,
        'totalsize': totalsize,
        'off_dt_struct': off_dt_struct,
        'off_dt_strings': off_dt_strings,
        'off_mem_rsvmap': off_mem_rsvmap,
        'version': version,
        'last_comp_version': last_comp_version,
        'boot_cpuid_phys': boot_cpuid_phys,
        'size_dt_strings': size_dt_strings,
        'size_dt_struct': size_dt_struct,
    }

class FDTParser:
    def __init__(self, data):
        self.data = data
        self.header = parse_fdt_header(data)
        
        self.struct_start = self.header['off_dt_struct']
        self.struct_end = self.struct_start + self.header['size_dt_struct']
        self.strings_start = self.header['off_dt_strings']
        self.strings_end = self.strings_start + self.header['size_dt_strings']
    
    def get_string(self, offset):
        """Get null-terminated string from strings table."""
        pos = self.strings_start + offset
        if pos >= self.strings_end:
            return f"<out of bounds: {offset}>"
        
        end = self.data.find(b'\x00', pos)
        if end == -1 or end >= self.strings_end:
            end = self.strings_end
        
        return self.data[pos:end].decode('utf-8', errors='ignore')
    
    def read_be32(self, offset):
        """Read big-endian 32-bit value."""
        if offset + 4 > len(self.data):
            return None
        return struct.unpack('>I', self.data[offset:offset+4])[0]
    
    def read_be64(self, offset):
        """Read big-endian 64-bit value."""
        if offset + 8 > len(self.data):
            return None
        return struct.unpack('>Q', self.data[offset:offset+8])[0]
    
    def align(self, pos, alignment=4):
        """Align position to boundary."""
        if pos % alignment != 0:
            pos += alignment - (pos % alignment)
        return pos
    
    def parse_properties(self):
        """Parse FDT and extract all 'reg' and 'interrupts' properties with node context."""
        results = []
        node_stack = []
        pos = self.struct_start
        
        while pos < self.struct_end:
            if pos + 4 > len(self.data):
                break
            
            token = self.read_be32(pos)
            pos += 4
            
            if token == 0x00000001:  # FDT_BEGIN_NODE
                # Read node name
                name_end = self.data.find(b'\x00', pos)
                if name_end == -1 or name_end >= len(self.data):
                    break
                
                node_name = self.data[pos:name_end].decode('utf-8', errors='ignore')
                pos = name_end + 1
                pos = self.align(pos)
                
                node_stack.append(node_name)
                node_path = '/'.join(node_stack) if node_stack else '/'
                
            elif token == 0x00000002:  # FDT_END_NODE
                if node_stack:
                    node_path = '/'.join(node_stack)
                    node_stack.pop()
            
            elif token == 0x00000003:  # FDT_PROP
                if pos + 8 > len(self.data):
                    break
                
                prop_len = self.read_be32(pos)
                name_offset = self.read_be32(pos + 4)
                pos += 8
                
                if prop_len < 0 or pos + prop_len > len(self.data):
                    break
                
                prop_name = self.get_string(name_offset)
                prop_data = self.data[pos:pos+prop_len]
                pos += prop_len
                pos = self.align(pos)
                
                node_path = '/'.join(node_stack) if node_stack else '/'
                
                # Store relevant properties
                if prop_name in ['reg', 'interrupts', 'compatible', 'status', 'clock-frequency', 'arm,psci-conduit']:
                    results.append({
                        'node': node_path,
                        'prop_name': prop_name,
                        'prop_len': prop_len,
                        'prop_data': prop_data,
                    })
            
            elif token == 0x00000009:  # FDT_END
                break
            
            elif token == 0x00000004:  # FDT_NOP
                pass
        
        return results

def format_reg_property(data):
    """Format a reg property as addresses and sizes."""
    addrs = []
    
    # Try 64-bit pairs first (most common for ARM64)
    for i in range(0, len(data) - 7, 16):
        try:
            addr = struct.unpack('>Q', data[i:i+8])[0]
            size = struct.unpack('>Q', data[i+8:i+16])[0]
            addrs.append(f"0x{addr:x} (size: 0x{size:x})")
        except:
            pass
    
    # If no 64-bit pairs, try 32-bit
    if not addrs and len(data) >= 8:
        for i in range(0, len(data) - 3, 8):
            try:
                addr = struct.unpack('>I', data[i:i+4])[0]
                size = struct.unpack('>I', data[i+4:i+8])[0]
                addrs.append(f"0x{addr:x} (size: 0x{size:x})")
            except:
                pass
    
    return addrs if addrs else ["<unparseable>"]

def format_interrupts(data):
    """Format interrupts property."""
    ints = []
    for i in range(0, len(data) - 3, 4):
        try:
            val = struct.unpack('>I', data[i:i+4])[0]
            ints.append(f"0x{val:x} ({val})")
        except:
            pass
    return ints if ints else ["<unparseable>"]

def main():
    with open('live-dtb/live-fdt.dtb', 'rb') as f:
        data = f.read()
    
    print(f"[*] Parsing FDT ({len(data)} bytes)\n")
    
    parser = FDTParser(data)
    props = parser.parse_properties()
    
    # Filter for critical nodes
    hw_keywords = ['gic', 'interrupt-controller', 'ufs', 'ufshc', 'timer', 'arm,armv8',
                   'pmic', 'spmi', 'touch', 'stm', 'i2c', 'qup']
    
    print("="*80)
    print("CRITICAL HARDWARE NODES")
    print("="*80 + "\n")
    
    seen_nodes = set()
    for prop in props:
        node = prop['node']
        node_lower = node.lower()
        
        if any(kw in node_lower for kw in hw_keywords):
            if node not in seen_nodes:
                print(f"[{node}]")
                seen_nodes.add(node)
            
            prop_name = prop['prop_name']
            prop_data = prop['prop_data']
            
            if prop_name == 'reg':
                addrs = format_reg_property(prop_data)
                for addr in addrs:
                    print(f"  reg: {addr}")
            
            elif prop_name == 'interrupts':
                ints = format_interrupts(prop_data)
                for irq in ints:
                    print(f"  interrupt: {irq}")
            
            elif prop_name == 'compatible':
                compat = prop_data.decode('utf-8', errors='ignore').replace('\x00', ', ')
                print(f"  compatible: {compat}")
            
            elif prop_name == 'clock-frequency':
                if len(prop_data) == 4:
                    freq = struct.unpack('>I', prop_data)[0]
                    print(f"  clock-frequency: {freq} Hz ({freq/1e6:.1f} MHz)")
            
            elif prop_name == 'arm,psci-conduit':
                conduit = prop_data.decode('utf-8', errors='ignore').rstrip('\x00')
                print(f"  psci-conduit: {conduit}")
            
            elif prop_name == 'status':
                status = prop_data.decode('utf-8', errors='ignore').rstrip('\x00')
                print(f"  status: {status}")
            
            print()

if __name__ == '__main__':
    main()
