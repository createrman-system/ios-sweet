#!/bin/bash
# Build the shim and wrap it in a boot image for Samsung Galaxy A52s (header version 3).
# Same build as sweet (Xiaomi header v2), but uses Samsung header v3 for A52s bootloader.
#
# Samsung header v3 is used by the A52s ABL (Qualcomm bootloader on this device).
# Structure: like v2, but with additional fields for Samsung-specific boot parameters.
# Usage: build-a52sxq.sh [PAYLOAD_BIN]  (payload defaults to empty cpio)

set -euo pipefail
cd "$(dirname "$0")"
CC=aarch64-linux-gnu-gcc
OBJCOPY=aarch64-linux-gnu-objcopy
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
mkdir -p out

# Compile shim (same as sweet, unchanged)
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done

# Check for absolute relocations
abs=$(aarch64-linux-gnu-readelf -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }

# Link shim binary
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image

# Pad binary to _end (ensures .bss and stacks are zeroed)
size=$(aarch64-linux-gnu-nm out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/Image

# Ramdisk: XNU payload (tools/mkpayload.py result) or empty newc cpio
if [ -n "${1:-}" ]; then
	cp "$1" out/ramdisk.bin
else
	(cd out && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi

# Build boot image with Samsung header v3
# Samsung v3 includes os_version, os_patch_level, and cmdline in the v3 struct.
# mkbootimg from Android 12+ defaults to v4; we explicitly request v3 for A52s compatibility.
mkbootimg --header_version 3 --kernel out/Image --ramdisk out/ramdisk.bin \
	--dtb ../dtb/boot_unpacked/dtb --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
	--tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
	--os_version 14.0.0 --os_patch_level 2024-06 \
	--cmdline "console=null" -o out/shim-boot.img

# Verify the boot image was created and is readable
if [ ! -f out/shim-boot.img ]; then
	echo "error: shim-boot.img not created" >&2
	exit 1
fi

# Host test of console layout
gcc -O1 -Wall -o out/host_test console.c host_test.c && ./out/host_test

ls -l out/Image out/shim-boot.img
echo "Boot image ready for 'fastboot boot' on Samsung Galaxy A52s"
