#!/usr/bin/env python3
"""Debug: Check why file size is 0 after write."""

import sys
from pathlib import Path

# Add XDF directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'XDF'))

from xdf_filesystem import XDFFileSystem
from xdf_format import MEDIA_PROFILES, MediaType
import struct

def create_test_disk():
    """Create a blank 2HD XDF disk."""
    test_disk_path = Path('/tmp/test_disk_debug.xdf')
    
    profile = MEDIA_PROFILES[MediaType.MEDIA_2HD]
    disk_size = profile.sector_size * profile.total_sectors
    
    # Create blank disk
    disk_data = bytearray(disk_size)
    
    # Write X68000 boot sector
    disk_data[0:2] = b'\x60\x1C'
    disk_data[3:11] = b'X68IPL30'
    
    # Write big-endian BPB
    disk_data[0x12:0x14] = struct.pack('>H', profile.sector_size)
    disk_data[0x14] = 1  # sectors_per_cluster
    disk_data[0x15] = 2  # fat_count
    disk_data[0x16:0x18] = struct.pack('>H', 1)  # reserved_sectors
    disk_data[0x18:0x1A] = struct.pack('>H', 192)  # root_entries
    disk_data[0x1A:0x1C] = struct.pack('>H', profile.total_sectors)
    disk_data[0x1C] = profile.media_byte
    disk_data[0x1D] = 2  # fat_sectors
    
    with open(test_disk_path, 'wb') as f:
        f.write(disk_data)
    
    return test_disk_path

def debug_write():
    """Debug write and read."""
    print("=" * 70)
    print("DEBUG: Write and Read Operations")
    print("=" * 70)
    
    disk_path = create_test_disk()
    fs = XDFFileSystem(disk_path)
    
    # Write a simple file
    test_content = b'Hello World!'
    print(f"\n📝 Writing file...")
    print(f"   Content length: {len(test_content)} bytes")
    print(f"   Content: {test_content}")
    
    fs.write_file('\\HELLO.TXT', test_content)
    print("   ✅ Written to \\HELLO.TXT")
    
    # Check directory entries immediately after write
    print(f"\n📁 Root directory entries after write:")
    entries = fs.dir_reader.read_root_directory()
    for e in entries:
        print(f"   - {e.full_name()}")
        print(f"     Start cluster: {e.start_cluster}")
        print(f"     File size: {e.file_size}")
        print(f"     Is directory: {e.is_directory}")
    
    # Try to find the entry manually
    print(f"\n🔍 Finding entry 'HELLO.TXT'...")
    result = fs._find_entry('\\HELLO.TXT')
    if result:
        entry, parent_cluster = result
        print(f"   ✅ Found!")
        print(f"   Start cluster: {entry.start_cluster}")
        print(f"   File size: {entry.file_size}")
        print(f"   Is directory: {entry.is_directory}")
    else:
        print(f"   ❌ Not found!")
    
    # Try to read
    print(f"\n📖 Reading file...")
    try:
        read_data = fs.read_file('\\HELLO.TXT')
        print(f"   ✅ Read {len(read_data)} bytes")
        print(f"   Content: {read_data}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Save and reload
    print(f"\n💾 Saving disk...")
    fs.save()
    print("   ✅ Saved")
    
    print(f"\n🔄 Reloading filesystem...")
    fs2 = XDFFileSystem(disk_path)
    
    print(f"\n📁 Root directory entries after reload:")
    entries = fs2.dir_reader.read_root_directory()
    for e in entries:
        print(f"   - {e.full_name()}")
        print(f"     Start cluster: {e.start_cluster}")
        print(f"     File size: {e.file_size}")
    
    print(f"\n📖 Reading file after reload...")
    try:
        read_data = fs2.read_file('\\HELLO.TXT')
        print(f"   ✅ Read {len(read_data)} bytes")
        print(f"   Content: {read_data}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == '__main__':
    try:
        debug_write()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
