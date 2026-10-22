#!/usr/bin/env python3
"""
Find hardware device nodes by name and extract their register addresses.
"""

import struct
import sys
import os

def extract_strings_table(dtb_data, header_offset, strings_offset, strings_size):
    """Extract string table from DTB."""
    strings = {}
    pos = header_offset + strings_offset
    end_pos = pos + strings_size
    idx = 0
    
    while pos < end_pos:
        null_pos = dtb_data.find(b'\x00', pos)
        if null_pos == -1 or null_pos >= end_pos:
            break
        string = dtb_data[pos:null_pos].decode('utf-8', errors='ignore')
        if string:
            strings[idx] = string
        pos = null_pos + 1
        idx = pos - (header_offset + strings_offset)
    
    return strings

def parse_dtb_nodes_and_regs(dtb_path):
    """Parse DTB and extract node names and register values."""
    
    with open(dtb_path, 'rb') as f:
        dtb_data = f.read()
    
    # Find DTB magic
    magic_pos = dtb_data.find(bytes.fromhex('d00dfeed'))
    if magic_pos == -1:
        return {}
    
    header_offset = magic_pos
    
    # Parse header
    try:
        (magic, total_size, dt_struct_off, dt_strings_off, 
         mem_rsvmap_off, version, last_comp_version, boot_cpuid_phys,
         size_dt_strings, size_dt_struct) = struct.unpack(
            '>10I', dtb_data[header_offset:header_offset+40])
    except:
        return {}
    
    # Extract strings
    strings = extract_strings_table(dtb_data, header_offset, dt_strings_off, size_dt_strings)
    
    # Parse structure
    struct_start = header_offset + dt_struct_off
    struct_end = header_offset + dt_strings_off
    nodes = {}
    node_stack = []
    current_node = {}
    
    pos = struct_start
    while pos < struct_end:
        # Align to 4-byte boundary
        while pos % 4 != 0:
            pos += 1
        
        if pos >= struct_end:
            break
        
        try:
            token = struct.unpack('>I', dtb_data[pos:pos+4])[0]
        except:
            break
        
        pos += 4
        
        if token == 0x00000001:  # FDT_BEGIN_NODE
            # Read node name
            name_end = dtb_data.find(b'\x00', pos)
            node_name = dtb_data[pos:name_end].decode('utf-8', errors='ignore')
            pos = name_end + 1
            
            # Align
            while pos % 4 != 0:
                pos += 1
            
            node_stack.append(current_node)
            current_node = {'name': node_name, 'regs': [], 'properties': {}}
        
        elif token == 0x00000002:  # FDT_END_NODE
            # Save node
            if node_stack:
                parent = node_stack.pop()
                # Store the node
                node_path = '/'.join([n['name'] for n in node_stack] + [current_node['name']])
                nodes[node_path] = current_node
                current_node = parent
        
        elif token == 0x00000003:  # FDT_PROP
            try:
                prop_len = struct.unpack('>I', dtb_data[pos:pos+4])[0]
                str_offset = struct.unpack('>I', dtb_data[pos+4:pos+8])[0]
                pos += 8
                
                prop_name = strings.get(str_offset, f'unknown@{str_offset}')
                prop_data = dtb_data[pos:pos+prop_len]
                pos += prop_len
                
                # Align
                while pos % 4 != 0:
                    pos += 1
                
                # Store property
                current_node['properties'][prop_name] = prop_data
                
                # If it's a 'reg' property, parse addresses
                if prop_name == 'reg' and len(prop_data) >= 8:
                    # Try 64-bit pairs
                    for i in range(0, len(prop_data) - 7, 16):
                        try:
                            addr = struct.unpack('>Q', prop_data[i:i+8])[0]
                            size = struct.unpack('>Q', prop_data[i+8:i+16])[0]
                            current_node['regs'].append((addr, size))
                        except:
                            pass
                    
                    # If no 64-bit pairs, try 32-bit
                    if not current_node['regs']:
                        for i in range(0, len(prop_data) - 3, 8):
                            try:
                                addr = struct.unpack('>I', prop_data[i:i+4])[0]
                                size = struct.unpack('>I', prop_data[i+4:i+8])[0]
                                current_node['regs'].append((addr, size))
                            except:
                                pass
            except Exception as e:
                # Skip on error
                pass
        
        elif token == 0x00000009:  # FDT_END
            break
        
        elif token == 0x00000004:  # FDT_NOP
            pass
    
    return nodes

def main():
    dtbo_dir = sys.argv[1] if len(sys.argv) > 1 else 'dtb/a52s-dtbo'
    
    dtb_files = sorted([f for f in os.listdir(dtbo_dir) if f.endswith('.dtb')])
    
    # Hardware keywords to search for
    hw_keywords = [
        'gic', 'interrupt-controller', 'ufs', 'ufshc', 'ufsphy',
        'mdss', 'dsi', 'panel', 'framebuffer', 'splash',
        'timer', 'arm,armv8-timer',
        'pmic', 'spmi', 'power',
        'touch', 'ts', 'i2c', 'qup', 'goodix', 'stm', 'synaptics'
    ]
    
    for dtb_file in dtb_files:
        dtb_path = os.path.join(dtbo_dir, dtb_file)
        print(f"\n{'='*80}")
        print(f"DTB: {dtb_file}")
        print(f"{'='*80}\n")
        
        try:
            nodes = parse_dtb_nodes_and_regs(dtb_path)
            
            # Find nodes matching keywords
            interesting = {}
            for node_path, node in nodes.items():
                node_lower = node_path.lower()
                node_name_lower = node['name'].lower()
                
                if any(kw in node_lower or kw in node_name_lower for kw in hw_keywords):
                    interesting[node_path] = node
            
            # Print interesting nodes
            for node_path in sorted(interesting.keys()):
                node = interesting[node_path]
                print(f"[{node_path}]")
                
                if node['regs']:
                    for addr, size in node['regs']:
                        print(f"  reg: 0x{addr:010x}, size: 0x{size:x}")
                
                # Print other useful properties
                if 'compatible' in node['properties']:
                    compat = node['properties']['compatible'][:50]
                    print(f"  compatible: {compat}")
                
                if 'status' in node['properties']:
                    status = node['properties']['status'][:20]
                    print(f"  status: {status}")
                
                print()
            
            if not interesting:
                print("[NO HARDWARE NODES FOUND]\n")
                
        except Exception as e:
            print(f"[ERROR] {e}\n")

if __name__ == '__main__':
    main()
