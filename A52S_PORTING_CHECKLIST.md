# Galaxy A52s iOS Porting: Master Checklist

This is the master checklist for the entire A52s porting project. Tick items as they complete.

---

## PHASE 0: Hardware Analysis & Extraction

**Objective:** Extract A52s device tree and MMIO addresses from stock firmware.

### 0.1: Obtain Stock A52s Boot Image
- [ ] Get stock Samsung A52s boot.img (any variant: a52sxq, a52sxqzt, a52sxqks, a528b, a528n)
- [ ] Source: Samsung firmware, TWRP, or LineageOS builds
- [ ] Save to: `backup/a52s-boot.img` (or any working location)

### 0.2: Extract & Parse Device Tree
- [ ] Run: `python3 tools/unpack_bootv2.py backup/a52s-boot.img dtb/a52s-unpacked/`
- [ ] Check output: `dtb/a52s-unpacked/dtb` exists and is valid
- [ ] Copy: `cp dtb/a52s-unpacked/dtb dtb/a52s-live.dtb`
- [ ] Verify: `file dtb/a52s-live.dtb` outputs "Device Tree Blob"

### 0.3: Extract MMIO Addresses from DTB
- [ ] GIC GICD address (expect 0x17a00000, confirm from DTB)
- [ ] GIC GICR address (expect 0x17a60000, confirm from DTB)
- [ ] UFS controller address (expect 0x01d84000, confirm from DTB)
- [ ] Framebuffer address and size (expect 0x9c000000 with 1080×2400, confirm)
- [ ] Touch I²C controller address (GENI SE7 at 0xa84000, confirm)
- [ ] Touch IC I²C slave address (expect 0x5d for Goodix GT9896, confirm or identify)
- [ ] PMIC SPMI SID configuration (confirm PM6150/PM6150L map)
- [ ] Timer frequency (expect 19.2 MHz, confirm)

### 0.4: Cross-Check Against Kernel Sources
- [ ] Inspect `GalaxyA52sFolders/android_kernel_samsung_sm7325/drivers/ufs/` for UFS config
- [ ] Check `drivers/input/touchscreen/` for touch controller driver
- [ ] Look for device tree source files (*.dtsi, *.dts) confirming MMIO values
- [ ] Note any SM7325-specific quirks (Gear 4, DMA limits, PMIC differences)

### 0.5: Document All Findings
- [ ] Create file: `research/a52sxq-hardware-facts.md`
- [ ] Fill table:
  | Component | Address | Value | Confirmed/TBD |
  |-----------|---------|-------|---------|
  | GIC GICD | | 0x17a00000 | |
  | GIC GICR | | 0x17a60000 | |
  | UFS | | 0x01d84000 | |
  | Framebuffer | | 0x9c000000 | |
  | Touch I²C Bus | | 0xa84000 | |
  | Touch IC Addr | | 0x5d | |
  | Touch Power Rail | | L11C | |
  | PMIC PON | | 0x810 (SID0) | |
  | Timer Freq | | 19200000 Hz | |
- [ ] Compare with SM7150 NOTES.md → flag any differences
- [ ] Add notes on any A52s-specific findings

### 0.6: Prepare Comparison Document
- [ ] Create: `research/SM7150-vs-SM7325-MMIO.md` (optional, but helpful)
- [ ] List all identical addresses → these need no changes
- [ ] List all different addresses → these need new constants/patches
- [ ] Estimate number of patches to modify (likely 5-10)

**Phase 0 DONE when:** ✅ `research/a52sxq-hardware-facts.md` complete with all MMIO values confirmed

---

## PHASE 1: Machine Config & Build System

**Objective:** Create A52S machine config, adapt shim and tools, compile kernel for QEMU.

### 1.1: Create A52S Config Header
- [ ] Create file: `xnu/sweet-a52s-config.h`
- [ ] Define constants from Phase 0:
  ```c
  #define A52S_GICD_PADDR    [from Phase 0]
  #define A52S_GICR_PADDR    [from Phase 0]
  #define A52S_FB_PADDR      [from Phase 0]
  #define A52S_UFS_PADDR     [from Phase 0]
  #define A52S_TIMER_FREQ    [from Phase 0]
  // ... others
  ```
- [ ] Compare with SM7150 constants (likely identical)
- [ ] Add comments explaining each value's source

### 1.2: Create Machine Config Patch
- [ ] Create: `xnu/patches/0019-sweet-a52s-machine-config.patch`
- [ ] Adds A52S conditional config to XNU build system
- [ ] Keeps existing SWEET (SM7150) config intact
- [ ] Syntax check: `python3 tools/xnu-cc.py research/run28.log research/bt28 xnu/sweet-a52s-config.h`

### 1.3: Update Shim for A52S MMIO
- [ ] Modify: `shim/shim.c` → add A52S MMIO region mapping
- [ ] Modify: `shim/mmu.c` → add A52S memory regions (if needed)
- [ ] Define early MMIO map (same logic as SWEET, just different addresses)
- [ ] Add conditional: `#ifdef __APPLE_A52S__` or use config-based approach
- [ ] Compile check: `cd shim && make MACHINE=a52s`

### 1.4: Update mkadt.py for Device Selection
- [ ] Modify: `tools/mkadt.py`
- [ ] Add `--device` parameter: `--device sweet` (default) or `--device a52s`
- [ ] Create `DEVICES` dict with sweet & a52s config
- [ ] Update build() function to accept device parameter
- [ ] Test: `python3 tools/mkadt.py shim/out/test.adt --device a52s`

### 1.5: Verify Compilation
- [ ] Compile shim: `cd shim && make clean && make`
- [ ] No warnings or errors
- [ ] Shim binary produced: `shim/shim`
- [ ] [Optional] Compile kernel locally (if not using CI): verify no errors

### 1.6: Build for QEMU Smoke Test
- [ ] Run: `python3 tools/mkadt.py shim/out/a52s-qemu.adt --device a52s`
- [ ] Generate payload: `python3 tools/mkpayload.py xnu/out-NNNN/kernel.development.a52s shim/out/a52s-qemu.adt shim/out/payload-qemu.bin --cmdline "debug=0xc serial=3 cpus=1 rd=md0 -enable_kprintf_spam"`
- [ ] Build boot image: `cd shim && ./build.sh ../shim/out/payload-qemu.bin && cp out/shim-boot.img out/shim-boot-a52s-qemu.img`
- [ ] QEMU smoke test: `python3 tools/qemu-sweet.py --kernel xnu/out-NNNN/kernel.development.a52s --adt shim/out/a52s-qemu.adt --secs 10`
- [ ] Expected output: Kernel boots, GIC initialized, no panic

**Phase 1 DONE when:** ✅ Kernel compiles for A52s and passes QEMU smoke test

---

## PHASE 2: Display & Framebuffer

**Objective:** Verify display driver works with A52S framebuffer address.

### 2.1: Verify Framebuffer Configuration
- [ ] Check Phase 0 result: framebuffer address, width, height, stride
- [ ] Update mkadt.py `DEVICES['a52s']` with correct framebuffer values
- [ ] Confirm: resolution is 1080×2400, stride is 4320 bytes (1080×4)

### 2.2: Display Driver Patches (Reuse)
- [ ] Patches 0046 (IOSurface + IOMobileFramebuffer) — apply as-is
- [ ] Patch 0056 (throttled present) — apply as-is
- [ ] Patch 0061 (1125×2436) — apply as-is (same as SWEET)
- [ ] Patch 0079 (display power) — apply as-is
- [ ] No new patches needed (display logic is generic)

### 2.3: Compile & Verify
- [ ] Kernel with display patches compiles without errors
- [ ] No warnings related to framebuffer or display addresses

**Phase 2 DONE when:** ✅ Display patches apply cleanly, no compilation issues

---

## PHASE 3: Storage (UFS Root)

**Objective:** Verify UFS driver works on A52S and can mount HFS+ root.

### 3.1: Verify UFS Address & Gear
- [ ] Check Phase 0: UFS address (expect 0x01d84000)
- [ ] Note UFS Gear level from kernel source (Gear 3? Gear 4?)
- [ ] Document any A52S-specific UFS quirks

### 3.2: UFS Driver Patches (Mostly Reuse)
- [ ] Patches 0028–0034 (UFS driver) — apply as-is if address is 0x01d84000
- [ ] If address differs → create new patch with A52S_UFS_PADDR constant
- [ ] If Gear 4 or special quirks → may need new patch (reference Codex study in NOTES.md)

### 3.3: Compile & Prepare Root Image
- [ ] Kernel with UFS patches compiles
- [ ] Build iOS root image: `python3 tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root-a52s.img 16G`
- [ ] Tweak root: `sudo mount -t hfsplus -o loop,force ios16-root-a52s.img /mnt/iosroot && sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot && sudo umount /mnt/iosroot`
- [ ] Create sparse image: `img2simg ios16-root-a52s.img ios16-root-a52s.simg`
- [ ] Save: `shim/out/ios16-root-a52s.simg`

### 3.4: First Real Boot (Preliminary)
- [ ] Generate payload: `python3 tools/mkpayload.py xnu/out-NNNN/kernel.development.a52s shim/out/a52s.adt shim/out/payload-ufs.bin --cmdline "debug=0xc serial=3 cpus=1 rd=ufsroot0 ufsrw=1 rootrw=1 -enable_kprintf_spam -noprogress"`
- [ ] Build boot image: `cd shim && ./build.sh ../shim/out/payload-ufs.bin && cp out/shim-boot.img out/shim-boot-a52s-ufs.img`
- [ ] [On A52s] Boot: `fastboot boot shim/out/shim-boot-a52s-ufs.img`
- [ ] Watch console output for:
  - [ ] "UFS probe OK" or similar
  - [ ] "Found root filesystem at ..."
  - [ ] "Mounting HFS+ root ..."
  - [ ] No panic/hang at UFS init

### 3.5: Read Log & Debug if Needed
- [ ] Boot recovery: `fastboot boot recovery/recovery.img` (OrangeFox temporary)
- [ ] Pull log: `tools/sweet-log-pull.sh logs/boot-a52s-ufs.txt`
- [ ] Review for UFS errors, address mismatches, or panics
- [ ] If UFS fails → compare with SM7150 NOTES.md debug process, adapt driver

**Phase 3 DONE when:** ✅ UFS probes successfully and HFS+ root mounts without errors

---

## PHASE 4: Input (Touch + Keys)

**Objective:** Get touchscreen and power/volume buttons working.

### 4.1: Verify Touch & PMIC Configuration
- [ ] Check Phase 0: Touch IC address (expect 0x5d for Goodix GT9896)
- [ ] Check Phase 0: Touch I²C bus (GENI SE7 at 0xa84000)
- [ ] Check Phase 0: Touch power rail (expect L11C from PM6150L)
- [ ] Check Phase 0: PMIC PON address (expect 0x810 SID0)
- [ ] Check Phase 0: Volume key GPIO (expect PM6150L GPIO2 SID4)

### 4.2: SPMI Keys Driver (Adapt if Needed)
- [ ] Review patch 0060 (sweet-keys-touch-drivers.patch)
- [ ] If PMIC SID/address matches SM7150 → apply as-is
- [ ] If different → create `0060-a52s-keys-touch.patch` with new constants
- [ ] Compare PMIC configuration: PON 0x810, RESIN 0x81b, GPIO registers

### 4.3: Touch Driver (Adapt if Needed)
- [ ] Review patch 0063 (goodix-geni-packing.patch)
- [ ] If touch IC is Goodix GT9896 at 0x5d → apply as-is
- [ ] If different IC (Focaltech, Samsung STM) → may need new driver
  - [ ] Reference kernel `drivers/input/touchscreen/` for IC protocol
  - [ ] Create new patch with correct I²C address and initialization
- [ ] Verify power rail name (L11C or other)

### 4.4: Compile & Boot Test
- [ ] Kernel with input patches compiles
- [ ] Generate payload: `python3 tools/mkpayload.py ... --cmdline "... sweetkeys=1 sweettouch=1 ... sweethidtest=15"`
- [ ] `sweethidtest=15` sends fake Home button press every 15 seconds for testing
- [ ] Boot: `fastboot boot shim/out/shim-boot-a52s-input.img`
- [ ] Watch console for:
  - [ ] "SWEET HID: power key ..." (key driver initialized)
  - [ ] "SWEET TOUCH: ..." (touch driver initialized)
  - [ ] Fake Home presses triggered (should see in log)

### 4.5: Real Input Test (Once GUI is up)
- [ ] [After Phase 6] Boot with iOS GUI
- [ ] Test power button: press to lock/unlock
- [ ] Test vol+ / vol− : verify Control Center or other responses
- [ ] Test touch: tap, swipe, multi-touch
- [ ] Log should show: `SWEET HID: key press/release, SWEET TOUCH: X Y ...`

**Phase 4 DONE when:** ✅ Fake HID test passes, drivers initialize without error, real input works in Phase 6

---

## PHASE 5: Device Tree & ADT Generation

**Objective:** Generate correct Apple Device Tree for A52S and verify on real hardware.

### 5.1: Update mkadt.py with A52S Addresses
- [ ] mkadt.py updated with `--device a52s` support (done in Phase 1)
- [ ] DEVICES dict has all A52S MMIO values from Phase 0
- [ ] mkadt.py CPU topology: 8 cores (2×A78 + 6×A55), same as SM7150

### 5.2: Generate ADT for A52S
- [ ] Run: `python3 tools/mkadt.py shim/out/a52s.adt --device a52s --highmem`
- [ ] Output: `shim/out/a52s.adt` (Apple Device Tree binary)
- [ ] Verify: `python3 tools/adt.py dump shim/out/a52s.adt | grep -A3 "gic\|ufs\|framebuffer"`
- [ ] Check output contains correct addresses and sizes

### 5.3: Boot on Real A52S
- [ ] Create boot image with real ADT:
  - [ ] `python3 tools/mkpayload.py xnu/out-NNNN/kernel.development.a52s shim/out/a52s.adt shim/out/payload-real.bin --cmdline "debug=0xc serial=3 cpus=6 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30"`
  - [ ] `cd shim && ./build.sh ../shim/out/payload-real.bin && cp out/shim-boot.img out/shim-boot-a52s.img`
- [ ] Boot on A52S: `fastboot boot shim/out/shim-boot-a52s.img`
- [ ] Watch for:
  - [ ] "GIC enabled at GICD [address]" (should match Phase 0)
  - [ ] "UFS init: host at [address]" (should match Phase 0)
  - [ ] "Framebuffer: [address] [resolution]" (should match Phase 0)
  - [ ] "Platform Expert: found [N] CPUs" (should be 6 or 8)
  - [ ] No address mismatch panics

### 5.4: Read Log & Verify Addresses
- [ ] Boot recovery, pull log: `tools/sweet-log-pull.sh logs/boot-a52s-real.txt`
- [ ] Grep for MMIO initialization: `grep -i "paddr\|address\|base" logs/boot-a52s-real.txt`
- [ ] Cross-check with Phase 0 facts
- [ ] If mismatch → debug and fix ADT/config

**Phase 5 DONE when:** ✅ Real A52S boots with correct ADT addresses, kernel initializes GIC/UFS/display

---

## PHASE 6: iOS GUI Bringup

**Objective:** Boot iOS and get the home screen working.

### 6.1: Flash iOS Root Image
- [ ] [On A52S in fastboot]
- [ ] Flash: `fastboot -S 512M flash userdata shim/out/ios16-root-a52s.simg` (~7–10 minutes)
- [ ] If fastboot hangs at the end → re-enter fastboot (Power+VolDown) and proceed

### 6.2: Boot to Setup.app / Lock Screen
- [ ] Boot kernel: `fastboot boot shim/out/shim-boot-a52s.img`
- [ ] Watch display for:
  - [ ] Apple logo (white on black background)
  - [ ] Setup.app "Hello" screen (or lock screen)
  - [ ] Status bar with time
- [ ] If black screen → check console log for crash, verify framebuffer address

### 6.3: Verify Basic GUI Response
- [ ] Power button locks/unlocks (screen goes black/on)
- [ ] Touch responds (at least kernel console or kernel panic changes)
- [ ] No immediate SpringBoard crash (confirmed by persistent log)
- [ ] System boots without hanging (give 2–3 minutes for first boot)

### 6.4: Test User Interaction
- [ ] Swipe up to unlock (or press Home if Setup still showing)
- [ ] Navigate Setup or go to home screen
- [ ] Open Settings (if available)
- [ ] Verify touch and buttons work throughout

### 6.5: Check for Daemons
- [ ] Log should show launchd launching daemons
- [ ] backboardd should be running (GUI server)
- [ ] SpringBoard should be running (home screen)
- [ ] Some daemons may crash (expected for missing hardware)

### 6.6: Build Image Versions
- [ ] Keep reference images:
  - [ ] `shim/out/ios16-root-a52s-v1.img` (first working version)
  - [ ] `shim/out/shim-boot-a52s.img` (first working boot image)
- [ ] Document: kernel version (e.g., 0000), ADT version, boot-args used

**Phase 6 DONE when:** ✅ iOS GUI appears on screen, user can interact with lock screen and/or home screen

---

## PHASE 7: CPU & Performance Optimization

**Objective:** Enable more cores and optimize performance.

### 7.1: SMP via PSCI (A55 Cores)
- [ ] Patch 0065 (smp-psci.patch) already supports 8 cores
- [ ] Test with `cpus=6` (6 A55 cores) — should be stable
- [ ] Measure performance: boot time, frame rate, responsiveness
- [ ] Verify log shows PSCI CPU_ON succeeding for cores 1–5

### 7.2: A78 Cores (High-Performance)
- [ ] If confident with A55 stability: test `cpus=8` (add 2 A78 cores)
- [ ] Watch for PSCI errors or CPU hangs
- [ ] If successful: benchmark difference (should see faster app launch, scrolling)
- [ ] If unstable: revert to `cpus=6`

### 7.3: UFS Performance Tuning
- [ ] Reference: Codex UFS study in original NOTES.md
- [ ] Current boot takes ~4–5 minutes → target is ~3–4 minutes
- [ ] Optional: apply Codex patch 0058 (UFS batching, caching, ufscache=1)
- [ ] Test with boot-arg variations: `ufscache=1`, `ufswait=1`
- [ ] Measure boot time and disk throughput

### 7.4: Display Refresh Tuning
- [ ] Current: `sweetfb_hz=30` (30 Hz CPU copy to framebuffer)
- [ ] Test `sweetfb_hz=20` (slower, might save CPU)
- [ ] Test `sweetfb_hz=40` (faster, might improve UI feel but use more CPU)
- [ ] Choose based on responsiveness vs. thermal/power

**Phase 7 DONE when:** ✅ 6 or 8 cores stable, UFS boot time optimized, display refresh appropriate

---

## PHASE 8: Documentation & Final Testing

**Objective:** Document all findings and verify complete system stability.

### 8.1: Create README-a52s.md
- [ ] Copy structure from original `README.md`
- [ ] Update device details:
  - [ ] Device name: Samsung Galaxy A52s 5G (a52sxq)
  - [ ] SoC: Qualcomm SM7325 (Snapdragon 778G 5G)
  - [ ] Display: 6.5" 1080×2400 Super AMOLED
  - [ ] CPU: 2×A78 @ 2.4 GHz + 6×A55 @ 1.9 GHz
  - [ ] Storage: UFS 2.1
- [ ] Keep all build/boot procedures (likely identical to SWEET)
- [ ] Add A52S-specific notes (if any quirks found)

### 8.2: Create NOTES-a52s.md
- [ ] Engineering log of A52s bring-up
- [ ] Document each Phase's findings:
  - [ ] Phase 0 hardware facts
  - [ ] Phase 1 machine config
  - [ ] Phase 2–5 driver adaptations
  - [ ] Phase 6 GUI bringup
  - [ ] Phase 7 optimization
- [ ] Record all MMIO addresses and their sources
- [ ] Note any deviations from SM7150
- [ ] Include boot-args used and why

### 8.3: Update AGENTS.md
- [ ] Add section for A52s work
- [ ] Reference new README-a52s.md and NOTES-a52s.md
- [ ] Note that A52S work follows same philosophy as SWEET

### 8.4: Final Full Test Suite
- [ ] QEMU smoke test: `python3 tools/qemu-sweet.py ... --secs 30`
  - [ ] Kernel boots, console output, no panic
- [ ] Real A52S boot: `fastboot boot shim/out/shim-boot-a52s.img`
  - [ ] System boots to lock screen / home screen
  - [ ] GUI responsive to touch and buttons
  - [ ] No crashes in 5-minute session
- [ ] Check kernel log: `tools/sweet-log-pull.sh logs/final-test.txt`
  - [ ] No errors or warnings in critical paths
  - [ ] All drivers initialized successfully
  - [ ] Daemons running or failing gracefully

### 8.5: Create Quickstart Guide
- [ ] Single-page guide for reproducing the A52S boot
- [ ] Build commands (kernel, ADT, payload, boot image)
- [ ] Flash/boot commands
- [ ] Expected output checklist
- [ ] Troubleshooting (common errors and fixes)

### 8.6: Archive & Organize
- [ ] Save reference builds:
  - [ ] `xnu/out-0000/kernel.development.a52s` (final stable kernel)
  - [ ] `shim/out/a52s.adt` (final ADT)
  - [ ] `shim/out/shim-boot-a52s.img` (final boot image)
  - [ ] `shim/out/ios16-root-a52s.simg` (final iOS root)
- [ ] Clean up temporary files (payloads, intermediate builds)
- [ ] Commit to git with message: "iOS 16 on Galaxy A52s: Complete porting (phases 0–8)"

### 8.7: Final Verification
- [ ] README-a52s.md is clear and complete
- [ ] NOTES-a52s.md explains all hardware and patches
- [ ] All MMIO facts documented
- [ ] Reproduction steps tested (from scratch on fresh A52s)
- [ ] No secrets or device identifiers in documentation

**Phase 8 DONE when:** ✅ Full documentation complete, all tests pass, project ready for public sharing

---

## FINAL SUCCESS: iOS 16 on Galaxy A52s 🎉

**When all phases are complete:**

- ✅ Kernel compiles and runs
- ✅ Display shows iOS GUI
- ✅ Touch and buttons respond
- ✅ System boots cleanly without crashes
- ✅ All major daemons running
- ✅ Documentation complete
- ✅ Reproduction steps verified

**The Galaxy A52s will display the iOS 16.7 home screen, fully responsive to user input.**

---

## Quick Reference: Phase Completion Order

1. **Phase 0 ← START HERE** (Hardware extraction)
2. Phase 1 (Machine config)
3. Phase 2 (Display)
4. Phase 3 (Storage)
5. Phase 4 (Input)
6. Phase 5 (ADT & real boot)
7. Phase 6 (GUI)
8. Phase 7 (Optimization)
9. Phase 8 (Documentation) ← FINISH HERE

**Estimated total time: 8–14 days**

---

## Questions?

- See `PORTING_A52S_START.md` for overview
- See generated artifacts for detailed guides (generated at start of this project)
- See original `NOTES.md` for ios-sweet reference implementation
- See `research/` for hardware documentation

Now go extract that A52s DTB! 📱✨
