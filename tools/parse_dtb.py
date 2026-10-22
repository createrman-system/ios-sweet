#!/usr/bin/env python3
"""
FDT (Flattened Device Tree) binary parser for extracting hardware register information.
Follows the DeviceTree specification for binary format parsing.
"""

import struct
import sys
from pathlib import Path
from collections import defaultdict

# FDT token values
FDT_BEGIN_NODE = 0x1
FDT_END_NODE = 0x2
FDT_PROP = 0x3
FDT_NOP = 0x4
FDT_END = 0x9

# Components of interest
INTERESTING_COMPATIBLES = {
    'arm,gic-v3', 'arm,gic-400', 'gic', 'interrupt-controller',
    'qcom,ufshc', 'ufshc',
    'qcom,mdss', 'mdss', 'sde_mdss',
    'qcom,dsi-ctrl', 'mdss_dsi',
    'arm,armv8-timer', 'arm,armv7-timer',
    'qcom,spmi', 'spmi_bus',
    'qcom,qupv3', 'qcom,i2c-geni',
    'stm_ts', 'goodix', 'synaptics', 'sec_ts', 'fts_ts',
    'simple-framebuffer', 'framebuffer',
    'qcom,msm-imem', 'qcom,msm-id', 'qcom,board-id',
    'qcom,dwc-usb3', 'snps,dwc3',
}

class FDTParser:
    def __init__(self, filepath):
        self.filepath = filepath
        with open(filepath, 'rb') as f:
            self.data = f.read()
        self.parse_header()
        self.nodes = []
        self.current_node = None
        
    def parse_header(self):
        """Parse FDT header."""
        if len(self.data) < 40:
            raise ValueError(f"File too small to be a valid FDT")
        
        magic, = struct.unpack('>I', self.data[0:4])
        if magic != 0xd00dfeed:
            raise ValueError(f"Invalid FDT magic: {magic:08x}")
        
        totalsize, off_dt_struct, off_dt_strings, off_mem_rsvmap, version, last_comp_version = \
            struct.unpack('>6I', self.data[4:28])
        
        self.totalsize = totalsize
        self.off_dt_struct = off_dt_struct
        self.off_dt_strings = off_dt_strings
        self.off_mem_rsvmap = off_mem_rsvmap
        self.version = version
        self.last_comp_version = last_comp_version
        
    def read_string(self, offset):
        """Read null-terminated string from strings block."""
        start = self.off_dt_strings + offset
        end = self.data.find(b'\0', start)
        if end == -1:
            end = start + 256
        return self.data[start:end].decode('ascii', errors='replace')
    
    def parse_cells(self, data, address_cells, size_cells, cell_size=4):
        """Parse reg data into address/size tuples based on #address-cells and #size-cells."""
        results = []
        offset = 0
        cell_bytes = cell_size
        
        while offset + (address_cells + size_cells) * cell_bytes <= len(data):
            addr_bytes = data[offset:offset + address_cells * cell_bytes]
            offset += address_cells * cell_bytes
            
            size_bytes = data[offset:offset + size_cells * cell_bytes]
            offset += size_cells * cell_bytes
            
            # Parse address
            if address_cells == 1:
                addr, = struct.unpack('>I', addr_bytes)
            elif address_cells == 2:
                addr, = struct.unpack('>Q', addr_bytes)
            else:
                addr = int.from_bytes(addr_bytes, 'big')
            
            # Parse size
            if size_cells == 1:
                size, = struct.unpack('>I', size_bytes)
            elif size_cells == 2:
                size, = struct.unpack('>Q', size_bytes)
            else:
                size = int.from_bytes(size_bytes, 'big')
            
            results.append((addr, size))
        
        return results
    
    def walk_tree(self):
        """Walk the FDT structure block and extract nodes."""
        offset = self.off_dt_struct
        node_stack = []
        current_path = ''
        current_compatibles = []
        current_props = {}
        address_cells = 2
        size_cells = 1
        
        while offset < self.off_dt_strings:
            token, = struct.unpack('>I', self.data[offset:offset + 4])
            offset += 4
            
            if token == FDT_BEGIN_NODE:
                # Read node name
                name_start = offset
                name_end = self.data.find(b'\0', name_start)
                node_name = self.data[name_start:name_end].decode('ascii', errors='replace')
                offset = name_end + 1
                
                # Align to 4-byte boundary
                offset = (offset + 3) & ~3
                
                # Update path
                if node_name:
                    current_path = current_path + '/' + node_name if current_path else '/' + node_name
                else:
                    current_path = '/'
                
                node_stack.append((current_path, current_compatibles[:], current_props.copy()))
                current_compatibles = []
                current_props = {}
                
            elif token == FDT_END_NODE:
                # Save current node
                if node_stack:
                    parent_path, parent_compat, parent_props = node_stack[-1]
                    self.nodes.append({
                        'path': current_path,
                        'compatibles': current_compatibles,
                        'props': current_props,
                    })
                    current_compatibles, current_props = parent_compat, parent_props
                    current_path = parent_path if node_stack else '/'
                    node_stack.pop()
                    
            elif token == FDT_PROP:
                # Read property
                length, = struct.unpack('>I', self.data[offset:offset + 4])
                offset += 4
                nameoff, = struct.unpack('>I', self.data[offset:offset + 4])
                offset += 4
                
                prop_name = self.read_string(nameoff)
                prop_data = self.data[offset:offset + length]
                offset += length
                
                # Align to 4-byte boundary
                offset = (offset + 3) & ~3
                
                current_props[prop_name] = prop_data
                
                # Track compatible strings
                if prop_name == 'compatible':
                    compatibles = prop_data.rstrip(b'\0').split(b'\0')
                    current_compatibles = [c.decode('ascii', errors='replace') for c in compatibles]
                
                # Track address/size cells for parsing child reg properties
                if prop_name == '#address-cells':
                    address_cells, = struct.unpack('>I', prop_data[:4])
                if prop_name == '#size-cells':
                    size_cells, = struct.unpack('>I', prop_data[:4])
                    
            elif token == FDT_NOP:
                pass
            elif token == FDT_END:
                break
            else:
                break
    
    def get_interesting_nodes(self):
        """Filter nodes with interesting compatible strings or key properties."""
        interesting = []
        for node in self.nodes:
            has_interesting_compat = any(
                compat_frag in compat 
                for compat in node['compatibles']
                for compat_frag in INTERESTING_COMPATIBLES
            )
            has_reg = 'reg' in node['props']
            
            if (has_interesting_compat or has_reg) and node['props']:
                interesting.append(node)
        
        return interesting
    
    def format_reg(self, reg_data, address_cells=2, size_cells=1):
        """Format reg data for display."""
        hex_str = ' '.join(f'{b:02x}' for b in reg_data)
        
        # Try to parse as addresses
        try:
            if len(reg_data) >= (address_cells + size_cells) * 4:
                pairs = self.parse_cells(reg_data, address_cells, size_cells)
                parsed = ', '.join(f'0x{addr:x} size=0x{size:x}' for addr, size in pairs)
                return f"raw: {hex_str}\n        decoded: {parsed}"
        except:
            pass
        
        return f"raw: {hex_str}"


def main():
    dtb_files = [
        'd:/ios/ios-sweet/dtb/a52s-dtbo/dtb-00.dtb',
        'd:/ios/ios-sweet/dtb/a52s-dtbo/dtb-01.dtb',
        'd:/ios/ios-sweet/dtb/a52s-dtbo/dtb-02.dtb',
    ]
    
    research_dir = Path('d:/ios/ios-sweet/research')
    research_dir.mkdir(exist_ok=True)
    
    all_nodes = []
    interesting_nodes = []
    
    # Parse each DTB
    for dtb_path in dtb_files:
        dtb_file = Path(dtb_path)
        if not dtb_file.exists():
            print(f"Warning: {dtb_path} not found")
            continue
        
        print(f"Parsing {dtb_path}...")
        try:
            parser = FDTParser(str(dtb_file))
            parser.walk_tree()
            
            for node in parser.nodes:
                node['source'] = dtb_file.name
                all_nodes.append(node)
                
                if parser.get_interesting_nodes():
                    interesting_nodes.extend(parser.get_interesting_nodes())
            
            print(f"  Found {len(parser.nodes)} nodes")
        except Exception as e:
            print(f"Error parsing {dtb_path}: {e}")
            import traceback
            traceback.print_exc()
    
    # Write all nodes with reg properties to dtb-reg-dump.txt
    with open(research_dir / 'dtb-reg-dump.txt', 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("DTB REG PROPERTY DUMP\n")
        f.write("=" * 80 + "\n\n")
        
        for node in all_nodes:
            if 'reg' not in node['props']:
                continue
            
            f.write(f"NODE: {node['path']}\n")
            if node['compatibles']:
                f.write(f"COMPATIBLE: {', '.join(node['compatibles'])}\n")
            
            reg_data = node['props'].get('reg', b'')
            hex_str = ' '.join(f'{b:02x}' for b in reg_data)
            f.write(f"REG (raw hex): {hex_str}\n")
            
            # Try both 1-cell and 2-cell interpretations
            try:
                pairs_2cell = []
                if len(reg_data) % 8 == 0 and len(reg_data) >= 8:
                    pairs_2cell = parser.parse_cells(reg_data, 2, 1)
                    f.write(f"REG (2-cell addr, 1-cell size): {', '.join(f'0x{addr:x} size=0x{size:x}' for addr, size in pairs_2cell)}\n")
            except:
                pass
            
            try:
                pairs_1cell = []
                if len(reg_data) % 4 == 0 and len(reg_data) >= 4:
                    pairs_1cell = parser.parse_cells(reg_data, 1, 1)
                    f.write(f"REG (1-cell addr, 1-cell size): {', '.join(f'0x{addr:x} size=0x{size:x}' for addr, size in pairs_1cell)}\n")
            except:
                pass
            
            if 'interrupts' in node['props']:
                intr = node['props']['interrupts']
                f.write(f"INTERRUPTS: {' '.join(f'{b:02x}' for b in intr)}\n")
            
            f.write(f"SOURCE: {node.get('source', 'unknown')}\n")
            f.write("\n")
    
    print(f"\nWritten {len([n for n in all_nodes if 'reg' in n['props']])} nodes to dtb-reg-dump.txt")
    
    # Write interesting nodes to dtb-hw-nodes.txt
    interesting_nodes = list({n['path']: n for n in interesting_nodes}.values())
    
    with open(research_dir / 'dtb-hw-nodes.txt', 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("INTERESTING HARDWARE NODES FROM DTBs\n")
        f.write("=" * 80 + "\n\n")
        
        for node in interesting_nodes:
            f.write(f"NODE: {node['path']}\n")
            if node['compatibles']:
                f.write(f"COMPATIBLE: {', '.join(node['compatibles'])}\n")
            
            if 'reg' in node['props']:
                reg_data = node['props']['reg']
                hex_str = ' '.join(f'{b:02x}' for b in reg_data)
                f.write(f"REG (raw hex): {hex_str}\n")
                
                try:
                    pairs_2cell = []
                    if len(reg_data) % 8 == 0 and len(reg_data) >= 8:
                        pairs_2cell = parser.parse_cells(reg_data, 2, 1)
                        f.write(f"REG (2-cell): {', '.join(f'0x{addr:x} size=0x{size:x}' for addr, size in pairs_2cell)}\n")
                except:
                    pass
                
                try:
                    if len(reg_data) % 4 == 0 and len(reg_data) >= 4:
                        pairs_1cell = parser.parse_cells(reg_data, 1, 1)
                        f.write(f"REG (1-cell): {', '.join(f'0x{addr:x} size=0x{size:x}' for addr, size in pairs_1cell)}\n")
                except:
                    pass
            
            if 'interrupts' in node['props']:
                intr = node['props']['interrupts']
                intr_str = ' '.join(f'{b:02x}' for b in intr)
                f.write(f"INTERRUPTS: {intr_str}\n")
            
            if 'clock-frequency' in node['props']:
                freq_data = node['props']['clock-frequency']
                try:
                    freq, = struct.unpack('>I', freq_data[:4])
                    f.write(f"CLOCK-FREQUENCY: {freq} Hz\n")
                except:
                    pass
            
            if 'assigned-clock-rates' in node['props']:
                rates_data = node['props']['assigned-clock-rates']
                f.write(f"ASSIGNED-CLOCK-RATES: {' '.join(f'{b:02x}' for b in rates_data)}\n")
            
            f.write(f"SOURCE: {node.get('source', 'unknown')}\n")
            f.write("\n")
    
    print(f"Written {len(interesting_nodes)} interesting nodes to dtb-hw-nodes.txt")
    
    # Now do more detailed extraction for specific components
    extracted_values = []
    
    # Find GIC
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if 'gic' in compat_str.lower() and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': 'GIC (interrupt-controller)',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find UFS
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if 'ufshc' in compat_str.lower() and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': 'UFS Host Controller',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find MDSS/Display
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if any(x in compat_str.lower() for x in ['mdss', 'dsi', 'display']) and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': f"Display/DSI ({compat_str})",
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find SPMI
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if 'spmi' in compat_str.lower() and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': 'SPMI Bus',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find Touch
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if any(x in compat_str.lower() for x in ['goodix', 'synaptics', 'stm', 'sec_ts']) and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': f"Touch Controller ({compat_str})",
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find Timer
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if 'timer' in compat_str.lower():
            extracted_values.append({
                'component': 'ARM Timer',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': 'N/A (system timer)',
                'source': node.get('source', 'unknown'),
            })
    
    # Find USB
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if any(x in compat_str.lower() for x in ['dwc3', 'usb']) and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': 'USB DWC3',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Find Framebuffer
    for node in all_nodes:
        compat_str = ' '.join(node['compatibles'])
        if 'framebuffer' in compat_str.lower() and 'reg' in node['props']:
            reg_data = node['props']['reg']
            extracted_values.append({
                'component': 'Framebuffer',
                'node': node['path'],
                'compatible': ', '.join(node['compatibles']),
                'reg_hex': ' '.join(f'{b:02x}' for b in reg_data),
                'source': node.get('source', 'unknown'),
            })
    
    # Write extracted values
    with open(research_dir / 'dtb-extracted-values.txt', 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("EXTRACTED HARDWARE COMPONENT VALUES FROM DTBs\n")
        f.write("=" * 80 + "\n\n")
        
        if extracted_values:
            for ev in extracted_values:
                f.write(f"COMPONENT: {ev['component']}\n")
                f.write(f"NODE: {ev['node']}\n")
                f.write(f"COMPATIBLE: {ev['compatible']}\n")
                f.write(f"REG (raw): {ev['reg_hex']}\n")
                f.write(f"SOURCE: {ev['source']}\n")
                f.write("---\n\n")
        else:
            f.write("No specific components found in DTBs.\n")
            f.write("See dtb-hw-nodes.txt and dtb-reg-dump.txt for full node listings.\n")
    
    print(f"Written {len(extracted_values)} extracted values to dtb-extracted-values.txt")
    print("\nParsing complete.")


if __name__ == '__main__':
    main()
