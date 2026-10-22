#!/usr/bin/env python3
"""Build the Apple Device Tree for A52SXQ (Samsung Galaxy A52s 5G, SM7325).

Uses verified MMIO addresses from live FDT. Presents the device to iOS as
iPhone X (iPhone10,3 / D22AP) so it uses the standard iOS 16 userland.

Usage: mkadt-a52sxq.py OUT.adt [--dump] [--qemu] [--highmem]
"""
import hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# Kernel-managed RAM: above Qualcomm carve-outs (same as sweet SM7150)
PHYS_BASE = 0xb0000000
MEM_SIZE = 0x4d000000
PANIC_LOG_SIZE = 0x100000

# High memory for --highmem flag
HIGH_PHYS_BASE = 0x100000000
HIGH_MEM_SIZE = 0xfcc00000

# SOC base for /arm-io children
SOC_BASE = 0x01000000

# A52SXQ verified hardware addresses (from live FDT on Samsung Galaxy A52s)
GICD, GICD_SIZE = 0x17a00000, 0x10000
GICR, GICR_SIZE = 0x17a60000, 0x100000
FB, FB_SIZE = 0x9c000000, 0x1700000
FB_W, FB_H, FB_STRIDE = 1080, 2400, 1080 * 4

# Synthetic ECID (not the phone's real ECID; kept private)
A52SXQ_ECID = 0x4135325350583051  # 'A52SXQ0' + 1

# UFS host (internal storage)
UFS, UFS_SIZE = 0x01d84000, 0x3000

# Timebase (same as all Qualcomm)
TIMEBASE = 19200000
VTIMER_INTID = 19

# QEMU virt parameters (for testing ADT structure on QEMU)
QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE = 0x08000000, 0x080a0000, 62500000
QEMU_VTIMER_INTID = 27

BOOT_MANIFEST_HASH = hashlib.sha384(b'a52sxq boot manifest').digest()

# iPhone X (D22AP) ADT from the IPSW for /product node (Apple proprietary)
D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt')


def d22ap_product(path=D22AP_ADT):
    """/product properties from real D22AP device tree (iPhone X)."""
    if not os.path.exists(path):
        print(f'warning: {path} missing, no /product node', file=sys.stderr)
        return None
    root, _ = adt.parse(open(path, 'rb').read())
    for c in root.children:
        if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
            return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    raise SystemExit(f'{path}: no /product node')

u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None, qemu=False, highmem=False):
    """Build ADT for A52SXQ.
    
    qemu=True: use QEMU virt's GIC addresses and CNTFRQ for testing.
    highmem=True: expose high DDR bank (0x100000000–0x1cc000000).
    """
    phys_base, mem_size = (HIGH_PHYS_BASE, HIGH_MEM_SIZE) if highmem else (PHYS_BASE, MEM_SIZE)
    panic_base = phys_base + mem_size - PANIC_LOG_SIZE
    mem_size -= PANIC_LOG_SIZE
    gicd, gicr, timebase = (QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE) if qemu else (GICD, GICR, TIMEBASE)
    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('embedded-panic-log-size', u32(PANIC_LOG_SIZE)),
        ('firmware-version', cstr('a52sxq-shim')),
        ('system-firmware-version', cstr('a52sxq-shim')),
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        ('crypto-hash-method', cstr('sha2-384')),
        ('display-scale', u32(3)),
        # A52SXQ synthetic ECID + iPhone X chip ID (0x8015 = A11)
        ('unique-chip-id', struct.pack('<Q', A52SXQ_ECID)),
        ('chip-id', u32(0x8015)),
        # Security: dev-fused, undemoted board
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])

    # A52SXQ CPU topology: 1× A78 Prime (core 0) + 3× A78 Gold (1–3) + 4× A55 Silver (4–7)
    # Kryo 670 cores, no PAC, ARMv8.2.
    cpu_nodes = []
    for core in range(1 if qemu else 8):
        # Core ID determines frequency: 0 & 1–3 are A78 @ 2.4 GHz, 4–7 are A55 @ 1.9 GHz
        is_a78 = (core < 4)
        freq = 2400000000 if is_a78 else 1900000000
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('qcom,kryo670') + cstr('ARM,v8')),
            ('reg', u32(core << 8)),
            ('cpu-id', u32(core)),
            ('cluster-id', u32(0)),
            ('cluster-type', u32(0)),
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(core)),
            ('l3-cache-id', u32(0)),
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(freq)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    # GICv3: Group 1 only (TrustZone owns Group 0)
    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(QEMU_VTIMER_INTID if qemu else VTIMER_INTID)),
        ('reg', u64(gicd - SOC_BASE, GICD_SIZE, gicr - SOC_BASE, GICR_SIZE)),
    ])
    
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('a52sxq-io')),
        ('compatible', cstr('a52sxq-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('a52sxq,display')),
            ('canvas-width', u32(1125)),
            ('canvas-height', u32(2436)),
        ])])

    # Framebuffer passed from ABL bootloader
    fbcon = node('a52sxq-fbcon', [
        ph(),
        ('reg', u64(FB, FB_SIZE)),
        ('width', u32(FB_W)),
        ('height', u32(FB_H)),
        ('stride', u32(FB_STRIDE)),
    ])

    # UFS internal storage host (UFSHCI 2.1)
    ufs = node('a52sxq-ufs', [
        ph(),
        ('compatible', cstr('qcom,ufshc')),
        ('reg', u64(UFS, UFS_SIZE)),
    ])

    # ASID management
    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    # Buttons
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    product_props = d22ap_product()
    product = [node('product', [ph()] + product_props)] if product_props else []

    # Panic log
    pram = node('pram', [ph(), ('reg', u64(panic_base) + u64(PANIC_LOG_SIZE))])

    # Root device tree: A52SXQ hardware, but iPhone10,3 identity
    return node('device-tree', [
        ph(),
        ('compatible', cstr('D22AP') + cstr('iPhone10,3') + cstr('samsung,a52sxq') + cstr('qcom,sm7325') + cstr('AppleARM')),
        ('model', cstr('iPhone10,3')),
        ('target-type', cstr('D22')),
        ('target-sub-type', cstr('D22AP')),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons, pram] + product + ([] if qemu else [ufs]))


if __name__ == '__main__':
    root = build(qemu='--qemu' in sys.argv, highmem='--highmem' in sys.argv)
    blob = adt.serialize(root)
    open(sys.argv[1], 'wb').write(blob)
    if '--dump' in sys.argv:
        adt.dump(adt.parse(blob)[0])
    print(f'{sys.argv[1]}: {len(blob)} bytes', file=sys.stderr)
