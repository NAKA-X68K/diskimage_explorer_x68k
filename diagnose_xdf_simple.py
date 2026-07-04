#!/usr/bin/env python3
"""Simple diagnostic script that doesn't require pyfatfs import."""

import sys
from pathlib import Path
import struct


def diagnose_xdf_file(file_path: str) -> None:
    """Diagnose X68000 XDF file without external dependencies."""
    
    p = Path(file_path)
    
    if not p.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    print("=" * 70)
    print(f"Diagnosing: {p.name}")
    print("=" * 70)
    
    # Check file size
    file_size = p.stat().st_size
    print(f"\n📊 File Information:")
    print(f"  Path:      {p}")
    print(f"  Size:      {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    print(f"  Suffix:    {p.suffix}")
    
    # Read first 512 bytes
    with p.open("rb") as fp:
        head = fp.read(512)
    
    if len(head) < 512:
        print(f"❌ File too small: only {len(head)} bytes (need 512)")
        return
    
    # Check X68000 IPL signature
    print(f"\n🔍 X68000 IPL Signature Detection:")
    ipl_bytes = head[3:11]
    print(f"  Bytes [3:11]: {ipl_bytes.hex().upper()}")
    print(f"  Expected:     {b'X68IPL30'.hex().upper()}")
    
    has_x68k_ipl = ipl_bytes == b"X68IPL30"
    if has_x68k_ipl:
        print(f"  Result:       ✅ X68000 IPL signature FOUND")
    else:
        print(f"  Result:       ❌ X68000 IPL signature NOT found")
        try:
            decoded = ipl_bytes.decode('ascii', errors='replace')
            print(f"  Content:      {repr(decoded)}")
        except:
            pass
    
    # Check boot code
    print(f"\n🔍 Boot Code Check:")
    boot_byte = head[0]
    print(f"  Byte [0]:     0x{boot_byte:02X}")
    if boot_byte == 0xEB or boot_byte == 0xE9:
        print(f"  Result:       ✅ Standard FAT boot code found")
    else:
        print(f"  Result:       ❌ Not standard FAT boot code")
        print(f"    (This is OK for X68000 IPL images)")
    
    # Check first bytes (X68000 machine code)
    print(f"\n🔍 First Bytes (X68000 Machine Code):")
    first_bytes = head[0:3]
    print(f"  Bytes [0:3]:  {first_bytes.hex().upper()}")
    print(f"  Expected:     60 3C 90 (or similar 68000 code)")
    
    # Try to parse BPB at different offsets (big-endian for X68000)
    print(f"\n🔍 BPB (BIOS Parameter Block) at offset 0x12:")
    try:
        bps = struct.unpack(">H", head[0x12:0x14])[0]  # Big-endian
        spc = head[0x13]
        reserved = struct.unpack(">H", head[0x14:0x16])[0]
        fat_count = head[0x10]
        root_entries = struct.unpack(">H", head[0x11:0x13])[0]
        
        print(f"  Bytes Per Sector:     {bps}")
        print(f"  Sectors Per Cluster:  {spc}")
        print(f"  Reserved Sectors:     {reserved}")
        print(f"  FAT Count:            {fat_count}")
        print(f"  Root Entries:         {root_entries}")
        
        # Media descriptor
        media = head[0x1A]
        print(f"  Media Descriptor:     0x{media:02X}")
        print(f"    (0xFE=2HD, 0xFD=2HC, 0xFB/0xFC=2DD, 0xFA=2HQ, 0xF8=HD/FDD)")
    except Exception as e:
        print(f"  ❌ Error parsing BPB: {e}")
    
    # Check profile matching
    print(f"\n🔍 Profile Matching by File Size:")
    profiles = [
        ("2HD (1232KB)",  1232 * 1024, 1261568),
        ("2HC (1200KB)",  1200 * 1024, 1228800),
        ("2DD (640KB)",   640 * 1024,  655360),
        ("2DD (720KB)",   720 * 1024,  737280),
        ("2HQ (1440KB)", 1440 * 1024, 1474560),
    ]
    
    print(f"  File size: {file_size:,} bytes")
    found_match = False
    for name, kb_size, byte_size in profiles:
        if file_size == byte_size:
            print(f"    ✅ MATCH: {name}")
            found_match = True
        else:
            print(f"       {name:20} = {byte_size:,} bytes")
    
    if not found_match:
        print(f"    ❌ No matching profile")
    
    # Summary
    print(f"\n📋 Summary:")
    if has_x68k_ipl and found_match:
        print(f"  ✅ This looks like a valid X68000 XDF file")
        print(f"  ✅ Should be detected as X68000 IPL floppy")
    elif has_x68k_ipl:
        print(f"  ⚠️  Has X68000 IPL signature but file size doesn't match known profiles")
    elif found_match:
        print(f"  ⚠️  File size matches X68000 profile but no IPL signature found")
    else:
        print(f"  ❌ Does not appear to be an X68000 XDF file")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_xdf_simple.py <path_to_xdf_file>")
        print("\nExample:")
        print("  python diagnose_xdf_simple.py test.xdf")
        sys.exit(1)
    
    xdf_file = sys.argv[1]
    diagnose_xdf_file(xdf_file)
