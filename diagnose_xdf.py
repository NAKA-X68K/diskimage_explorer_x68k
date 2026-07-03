#!/usr/bin/env python3
"""Diagnostic script for X68000 XDF file detection on Windows."""

import sys
from pathlib import Path

# Try to import backend module
try:
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from diskimage_explorer_x68k.backend import (
        detect_x68k_floppy_candidate,
        detect_image_hint,
        _x68k_bpb_at,
        X68K_XDF_PROFILES,
    )
except ImportError as e:
    print(f"❌ Failed to import backend module: {e}")
    print("Make sure you run this from the project root directory.")
    sys.exit(1)


def diagnose_xdf_file(file_path: str) -> None:
    """Diagnose why an XDF file cannot be detected."""
    
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
    print(f"  Size:      {file_size:,} bytes ({file_size / 1024:.0f} KB)")
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
    print(f"  Bytes 3-11:   {ipl_bytes.hex().upper()}")
    print(f"  Expected:     {b'X68IPL30'.hex().upper()}")
    
    has_x68k_ipl = ipl_bytes == b"X68IPL30"
    if has_x68k_ipl:
        print(f"  Result:       ✅ X68000 IPL signature FOUND")
    else:
        print(f"  Result:       ❌ X68000 IPL signature NOT found")
        # Try to decode what's actually there
        try:
            decoded = ipl_bytes.decode('ascii', errors='replace')
            print(f"  Content:      {repr(decoded)}")
        except:
            pass
    
    # Check boot code
    print(f"\n🔍 Boot Code Check:")
    boot_byte = head[0]
    print(f"  Byte 0:       0x{boot_byte:02X}")
    if boot_byte == 0xEB or boot_byte == 0xE9:
        print(f"  Result:       ✅ Standard FAT boot code found")
    else:
        print(f"  Result:       ❌ Not standard FAT boot code")
    
    # Try BPB parsing
    print(f"\n🔍 BPB (BIOS Parameter Block) Parsing:")
    bpb = _x68k_bpb_at(head, 0)
    if bpb:
        print(f"  ✅ BPB parsed successfully:")
        for key, value in bpb.items():
            print(f"    {key:20} = {value}")
    else:
        print(f"  ❌ BPB parsing failed (invalid or non-standard format)")
    
    # Check profile matching
    print(f"\n🔍 Profile Matching:")
    print(f"  File size:    {file_size:,} bytes")
    print(f"  Expected profiles:")
    for profile in X68K_XDF_PROFILES:
        match = "✅ MATCH" if file_size == profile.file_size else "  "
        print(f"    {match} {profile.name:20} = {profile.file_size:,} bytes")
    
    # Run actual detection
    print(f"\n🔍 Actual Detection Result:")
    candidate = detect_x68k_floppy_candidate(p)
    if candidate:
        print(f"  ✅ Detected as:")
        print(f"    Kind:   {candidate.kind}")
        print(f"    Offset: {candidate.offset} (0x{candidate.offset:08X})")
        print(f"    Label:  {candidate.label}")
    else:
        print(f"  ❌ Not detected as X68000 floppy")
        # Check image hint
        hint = detect_image_hint(p)
        if hint:
            print(f"    Image hint: {hint}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_xdf.py <path_to_xdf_file>")
        print("\nExample:")
        print("  python diagnose_xdf.py test.xdf")
        sys.exit(1)
    
    xdf_file = sys.argv[1]
    diagnose_xdf_file(xdf_file)
