#!/usr/bin/env python3
"""
Extract all reg properties from DTB files, highlighting hardware nodes.
"""

import struct
import sys

def scan_dtb_for_regs(dtb_file):
    """Parse DTB and return all reg properties."""
    
    with open(dtb_file, 'rb') as f:
        data = f.read()
    
    # Find DTB magic
    magic_idx = data.find(bytes.fromhex('d00dfeed'))
    if magic_idx == -1:
        return []
    
    # Parse header (big-endian)
    try:
        magic, totalsize, dt_struct_off, dt_strings_off = struct.unpack(
            '>4I', data[magic_idx:magic_idx+16])
    except:
        return []
    
    # Scan structure section
    struct_start = magic_idx + dt_struct_off
    strings_start = magic_idx + dt_strings_off
    
    results = []
    pos = struct_start
    node_name_stack = []
    
    while pos < magic_idx + dt_strings_off and pos < len(data) - 4:
        try:
            token = struct.unpack('>I', data[pos:pos+4])[0]
        except:
            break
        pos += 4
        
        # FDT_BEGIN_NODE (0x1)
        if token == 0x00000001:
            name_end = data.find(b'\x00', pos)
            if name_end != -1:
                node_name = data[pos:name_end].decode('utf-8', errors='ignore')
                node_name_stack.append(node_name)
                pos = name_end + 1
                while pos % 4 != 0:
                    pos += 1
        
        # FDT_PROP (0x3)
        elif token == 0x00000003:
            try:
                prop_len = struct.unpack('>I', data[pos:pos+4])[0]
                name_offset = struct.unpack('>I', data[pos+4:pos+8])[0]
                pos += 8
                
                # Get property name from string table
                str_pos = strings_start + name_offset
                str_end = data.find(b'\x00', str_pos)
                if str_end == -1:
                    str_end = strings_start + 10000
                prop_name = data[str_pos:str_end].decode('utf-8', errors='ignore')
                
                if prop_name == 'reg':
                    prop_data = data[pos:pos+prop_len]
                    node_path = '/'.join(node_name_stack)
                    
                    # Try 64-bit pairs first
                    addrs = []
                    for i in range(0, len(prop_data) - 7, 16):
                        try:
                            addr = struct.unpack('>Q', prop_data[i:i+8])[0]
                            size = struct.unpack('>Q', prop_data[i+8:i+16])[0]
                            addrs.append((addr, size, '64-bit'))
                        except:
                            pass
                    
                    # If no 64-bit, try 32-bit
                    if not addrs and len(prop_data) >= 8:
                        for i in range(0, len(prop_data) - 3, 8):
                            try:
                                addr = struct.unpack('>I', prop_data[i:i+4])[0]
                                size = struct.unpack('>I', prop_data[i+4:i+8])[0]
                                addrs.append((addr, size, '32-bit'))
                            except:
                                pass
                    
                    if addrs:
                        results.append({
                            'node': node_path,
                            'addresses': addrs,
                            'prop_len': prop_len
                        })
                
                pos += prop_len
                while pos % 4 != 0:
                    pos += 1
            except Exception as e:
                pass
        
        # FDT_END_NODE (0x2)
        elif token == 0x00000002:
            if node_name_stack:
                node_name_stack.pop()
        
        # FDT_END (0x9)
        elif token == 0x00000009:
            break
    
    return results

def main():
    output = []
    
    # Parse all DTBs
    for dtb_num in range(3):
        dtb_name = f'dtb-{dtb_num:02d}'
        dtb_file = f'dtb/a52s-dtbo/{dtb_name}.dtb'
        
        output.append(f'\n========== {dtb_name}.dtb ==========\n')
        
        try:
            results = scan_dtb_for_regs(dtb_file)
            output.append(f'Found {len(results)} nodes with reg properties\n')
            
            # Hardware keywords
            hw_keywords = ['gic', 'interrupt', 'ufs', 'mdss', 'dsi', 'timer',
                           'pmic', 'spmi', 'touch', 'i2c', 'qup', 'usb', 'dwc',
                           'qcom', 'pm', 'power']
            
            # Filter for interesting nodes
            hw_nodes = []
            for r in results:
                node_lower = r['node'].lower()
                if any(kw in node_lower for kw in hw_keywords):
                    hw_nodes.append(r)
            
            output.append(f'Hardware-related nodes: {len(hw_nodes)}\n')
            
            for r in hw_nodes:
                output.append(f'[{r["node"]}]')
                for addr, size, fmt in r['addresses']:
                    output.append(f'  0x{addr:x} (size: 0x{size:x}) [{fmt}]')
                output.append('')
        
        except Exception as e:
            output.append(f'Error: {e}\n')
    
    # Write output
    with open('dtb-parsed-regs.txt', 'w') as f:
        f.write('\n'.join(output))
    
    print(f'Parsed DTBs and wrote to dtb-parsed-regs.txt')
    print(f'Total lines: {len(output)}')

if __name__ == '__main__':
    main()
