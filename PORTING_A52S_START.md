# iOS on Galaxy A52s: Getting Started

This document is your starting point for the Galaxy A52s porting project. Read it first, then follow the links to the detailed analysis documents.

## TL;DR

We are adapting the **ios-sweet** project (iOS 16 on Redmi Note 10 Pro) to run on the **Samsung Galaxy A52s 5G**. The same iOS 16 userland (iPhone X), same CPU-only rendering, same experimental bring-up philosophy.

**Estimated effort:** 8–14 days to get iOS running on the home screen.

**Code reuse:** ~95% of patches and tools will work unchanged; only machine config and MMIO addresses need adaptation.

**Current status:** Analysis complete, ready to begin Phase 0 (hardware extraction).

---

## What You're About to Do

1. **Analyze the existing ios-sweet project** to understand how it works
2. **Extract Galaxy A52s hardware facts** from its device tree (DTB)
3. **Create machine config** for the A52s SoC (SM7325)
4. **Build and test kernel** on QEMU for smoke testing
5. **Boot real iOS on an A52s phone** via fastboot (temporary boot, no flashing)
6. **Bring up the GUI** (lock screen, home screen, Settings)
7. **Optimize and document** the final working system

---

## Generated Analysis Documents

I have created four comprehensive guides for this project. Read them in this order:

### 1. **Complete Project Summary** (START HERE)
- Project overview, timeline, and success criteria
- High-level architecture and what will/won't work
- Quick reference for commands and next steps

**[Read: iOS on Galaxy A52s: Complete Project Summary](kiro-artifact://c2a8f0f9-3949-4044-bd51-157402f0403e)**

### 2. **Hardware Comparison & Porting Analysis**
- Detailed side-by-side comparison of SM7150 (sweet) vs SM7325 (A52s)
- Identifies what's the same (reusable) and what's different (needs adaptation)
- Risk assessment and phased implementation plan

**[Read: iOS on Galaxy A52s: Porting Analysis and Comparison](kiro-artifact://75696c7f-b6ac-4547-b79d-e605e76f0859)**

### 3. **Implementation Roadmap (8 Phases)**
- Detailed phase-by-phase plan with specific files and code changes
- Build commands and verification steps for each milestone
- Success criteria and estimated timeline per phase

**[Read: iOS on Galaxy A52s: Implementation Roadmap](kiro-artifact://568b199e-ff9d-4a95-bdf4-d5f0f6c304f1)**

### 4. **Phase 0 & 1 Execution Guide**
- Immediate next steps: extract A52s DTB from stock boot.img
- Hardware facts checklist (MMIO addresses, touch, PMIC, etc.)
- Machine config setup and compilation

**[Read: Phase 0 & 1 Execution Guide](kiro-artifact://f39e0e94-d70b-4a3b-8025-e6c8f9628085)**

---

## Quick Start (Phase 0 - Hardware Extraction)

### Before You Code

You need to extract the Galaxy A52s device tree (DTB) to learn its hardware addresses. This is **critical** — all MMIO values depend on it.

#### Option 1: Extract from Stock Samsung Firmware
1. Obtain a stock Samsung A52s `boot.img` (any variant: a52sxq, a52sxqzt, etc.)
2. On Linux, unpack it:
   ```bash
   cd d:\ios\ios-sweet\
   python3 tools/unpack_bootv2.py <path-to-boot.img> dtb/a52s_boot_unpacked/
   cp dtb/a52s_boot_unpacked/dtb dtb/a52s-live.dtb
   ```
3. Save the DTB: `d:\ios\ios-sweet\dtb\a52s-live.dtb`

#### Option 2: Extract from Live A52s Phone (if you have one)
1. Boot the phone into fastboot or recovery
2. Dump the boot partition:
   ```bash
   adb shell "dd if=/dev/block/mmcblk0boot0 of=/sdcard/boot.img"
   adb pull /sdcard/boot.img
   # Then follow Option 1
   ```

#### Option 3: Use TWRP Recovery
The cloned TWRP tree has prebuilt DTB files:
```bash
ls -la GalaxyA52sFolders/android_device_samsung_a52sxq_twrp/prebuilt/dtb
# Compare with the TWRP DTB to SM7150's live FDT
```

### After You Extract the DTB

Fill in the hardware facts document:
1. Create file: `research/a52sxq-hardware-facts.md`
2. Fill in the table with extracted MMIO addresses:
   - GIC GICD / GICR
   - UFS controller
   - Framebuffer address and size
   - Touch I²C controller
   - PMIC / SPMI configuration

**Template:** See Phase 0 & 1 guide above.

### Then: Phase 1 (Machine Config)

Once you have the hardware facts:
1. Create `xnu/sweet-a52s-config.h` with extracted constants
2. Create machine config patch `0019-sweet-a52s-machine-config.patch`
3. Update `tools/mkadt.py` to support `--device a52s`
4. Compile kernel and test on QEMU

---

## Directory Structure

```
d:\ios\ios-sweet\
├── README.md                          ← Original ios-sweet overview
├── NOTES.md                           ← Original engineering log (VERY detailed)
├── AGENTS.md                          ← Working guidelines
├── PORTING_A52S_START.md              ← THIS FILE
├── README-a52s.md                     ← (to be created) A52s-specific guide
├── NOTES-a52s.md                      ← (to be created) A52s engineering log
│
├── research/
│   ├── a52sxq-hardware-facts.md       ← (TBD) Hardware extraction results
│   ├── SM7150-vs-SM7325.md            ← (optional) Detailed comparison
│   └── ipsw-x/                        ← iPhone X device tree (D22AP.adt)
│
├── dtb/
│   ├── a52s-live.dtb                  ← (TBD) Extracted A52s device tree
│   ├── sweet-live.dtb                 ← (reference) SM7150 live DTB
│
├── xnu/
│   ├── sweet-a52s-config.h            ← (to be created) A52S MMIO constants
│   ├── patches/
│   │   ├── 0001-0018/                 ← (reused) Generic patches
│   │   ├── 0019-sweet-a52s-machine-config.patch    ← (NEW) A52S config
│   │   └── 0020-0081/                 ← (reused) Rest of patches
│   │
│   └── out-0000/                      ← (to be created) First compiled kernel
│       └── kernel.development.a52s
│
├── shim/
│   ├── shim.c, mmu.c, etc.            ← (modify) Add A52S MMIO setup
│   └── out/
│       ├── a52s.adt                   ← (to be created) Generated ADT
│       └── shim-boot-a52s.img         ← (to be created) Boot image
│
├── tools/
│   ├── mkadt.py                       ← (modify) Add --device a52s support
│   ├── mkpayload.py                   ← (reuse) No changes
│   ├── mkiosroot.sh                   ← (reuse) No changes
│   └── sweet-root-tweaks.py           ← (reuse) No changes
│
└── GalaxyA52sFolders/
    ├── android_device_samsung_a52sxq/
    ├── android_device_samsung_a52sxq_twrp/
    ├── android_kernel_samsung_sm7325/
    └── extra/
```

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `NOTES.md` | Original ios-sweet engineering log (read this first to understand how ios-sweet works) |
| `README.md` | Original ios-sweet overview |
| `xnu/patches/0001-*.patch` through `0081-*.patch` | 81 XNU patches (mostly reused, ~5-10 adapted for A52s) |
| `tools/mkadt.py` | Generates Apple Device Tree from MMIO layout (to be adapted) |
| `tools/mkiosroot.sh` | Builds iOS root image from IPSW (reused as-is) |
| `shim/` | Bare-metal boot shim (to be adapted for A52s MMIO) |
| `research/ipsw-x/d22ap.adt` | iPhone X device tree (needed for /product node, same for A52s) |

---

## What Happens Next (Workflow)

### Your Part (User)
1. Extract A52s DTB and fill in hardware facts document
2. Review the analysis documents and ask questions
3. Validate milestones and GUI testing on the real A52s phone
4. Provide stock A52s boot.img, kernel sources, or live phone for hardware fact verification

### My Part (Agent)
1. Create machine config and patches based on your hardware facts
2. Modify tools and shim for A52s
3. Build kernel, test on QEMU, report results
4. Debug any failures and adapt drivers as needed
5. Bring up iOS GUI on the real phone
6. Document findings and create A52s-specific README/NOTES
7. Hand off the working project with clear instructions for reproduction

---

## Success Timeline

| When | What |
|------|------|
| **Now** | ✅ Analysis complete, documents created |
| **+1–2 days** | Phase 0: Extract A52s DTB, fill hardware facts |
| **+1 day** | Phase 1: Machine config, compile for QEMU |
| **+1 day** | Phase 2–3: Display and storage verified |
| **+1–2 days** | Phase 4: Input (touch, keys) working |
| **+1 day** | Phase 5: ADT generation, kernel boots real A52s |
| **+2–3 days** | Phase 6: iOS GUI up and responsive |
| **+1–2 days** | Phase 7–8: Optimization, documentation, final testing |
| **TOTAL: 8–14 days** | ✅ iOS 16 running on Galaxy A52s home screen |

---

## Questions Before You Start?

- **"How does the boot process work?"** → See NOTES.md in the original project (detailed engineering log)
- **"Why these specific addresses?"** → They come from the live device tree; Phase 0 extracts them
- **"What if addresses differ?"** → We create new constants and patches; the roadmap accounts for this
- **"Can I use this without an A52s phone?"** → Yes, QEMU testing works; but final GUI testing needs real hardware
- **"How much code do I have to write?"** → ~200–300 lines total (mostly config constants and MMIO updates)

---

## Resources Inside This Workspace

All the tools and references you need are already here:

- **ios-sweet source:** Root directory of this workspace
- **A52s kernel sources:** `GalaxyA52sFolders/android_kernel_samsung_sm7325/`
- **A52s device tree:** `GalaxyA52sFolders/android_device_samsung_a52sxq/` (LineageOS device config)
- **TWRP tree:** `GalaxyA52sFolders/android_device_samsung_a52sxq_twrp/` (boot format reference)
- **XNU patches:** `xnu/patches/0001-*.patch` (70+ patches to reuse/adapt)
- **iPhone X device tree:** `research/ipsw-x/d22ap.adt` (for /product node)

---

## Next Action

1. **Read the Complete Project Summary** (linked above)
2. **Read the Hardware Comparison** to see what's the same vs. different
3. **Start Phase 0: Extract A52s DTB** using the Phase 0/1 guide
4. **Report back with hardware facts**, and I'll implement Phase 1 (machine config)

---

## Final Note

This is **experimental bring-up**, same as ios-sweet. Security is off, GPU doesn't work, no cellular/Wi-Fi/sensors. But you'll have real iOS running on real Samsung hardware with CPU rendering, touch input, and all the stock apps. That's the whole point: **prove that iOS can run on other ARM SoCs without modification to the userland.**

Good luck! 🚀
