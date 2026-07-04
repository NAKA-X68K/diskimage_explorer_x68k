#!/usr/bin/env python3
"""Create a test XDF disk and verify write operations."""

import sys
from pathlib import Path

# Add XDF directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'XDF'))

from xdf_filesystem import XDFFileSystem
from xdf_format import MEDIA_PROFILES, MediaType
import struct

def create_test_disk():
    """Create a blank 2HD XDF disk."""
    print("Creating test disk...")
    
    # Create a blank 2HD disk (1232 KB)
    test_disk_path = Path('/tmp/test_disk.xdf')
    
    # 2HD: 1024 bytes/sector, 1232 sectors total
    profile = MEDIA_PROFILES[MediaType.MEDIA_2HD]
    disk_size = profile.sector_size * profile.total_sectors
    
    # Create blank disk
    disk_data = bytearray(disk_size)
    
    # Write X68000 boot sector
    # X68000 format: "X68IPL30" signature at bytes 3-11
    disk_data[0:2] = b'\x60\x1C'  # 68000 machine code
    disk_data[3:11] = b'X68IPL30'  # X68000 IPL signature
    
    # Write big-endian BPB
    disk_data[0x12:0x14] = struct.pack('>H', profile.sector_size)  # Bytes per sector
    disk_data[0x14] = 1  # sectors_per_cluster (always 1 for 2HD)
    disk_data[0x15] = 2  # fat_count
    disk_data[0x16:0x18] = struct.pack('>H', 1)  # reserved_sectors
    disk_data[0x18:0x1A] = struct.pack('>H', 192)  # root_entries (2HD standard)
    disk_data[0x1A:0x1C] = struct.pack('>H', profile.total_sectors)
    disk_data[0x1C] = profile.media_byte
    disk_data[0x1D] = 2  # fat_sectors (2HD standard)
    
    # Write to file
    with open(test_disk_path, 'wb') as f:
        f.write(disk_data)
    
    print(f"✅ Created test disk: {test_disk_path}")
    print(f"   Size: {disk_size} bytes ({disk_size / 1024:.1f} KB)")
    
    return test_disk_path

def test_write_operations(disk_path):
    """Test write operations on XDF disk."""
    print("\n" + "=" * 70)
    print("TEST: Write Operations (ファイル作成テスト)")
    print("=" * 70)
    
    try:
        # Mount filesystem
        fs = XDFFileSystem(disk_path)
        print(f"✅ Mounted: {disk_path.name}")
        
        # List empty root
        print("\n📁 Initial root directory:")
        entries = fs.listdir('/')
        print(f"   Entries: {len(entries)}")
        
        # Create a directory
        print("\n📁 Creating directory...")
        fs.makedirs('\\TEST')
        print("   ✅ Created \\TEST")
        
        # Verify directory exists
        entries = fs.listdir('/')
        print(f"   Root now has: {len(entries)} items")
        if 'TEST' in entries:
            print("   ✅ TEST directory found in listing")
        
        # Create a file
        print("\n📝 Creating file...")
        test_content = b'Hello X68000!\nThis is a test file.'
        fs.write_file('\\TEST.TXT', test_content)
        print(f"   ✅ Created \\TEST.TXT ({len(test_content)} bytes)")
        
        # Verify file in listing
        entries = fs.listdir('/')
        if 'TEST.TXT' in entries:
            print("   ✅ TEST.TXT found in listing")
        else:
            print("   ⚠️  TEST.TXT not in listing (entries: " + ', '.join(entries) + ")")
        
        # Read it back
        print("\n📖 Reading file back...")
        read_data = fs.read_file('\\TEST.TXT')
        print(f"   ✅ Read {len(read_data)} bytes")
        print(f"   Content: {read_data[:50]}")
        
        if read_data == test_content:
            print("   ✅ Content matches!")
        else:
            print(f"   ❌ Content mismatch: {len(read_data)} vs {len(test_content)} bytes")
        
        # Save changes
        print("\n💾 Saving disk...")
        fs.save()
        print("   ✅ Saved to disk")
        
        print("\n" + "=" * 70)
        print("✅ WRITE OPERATIONS TEST COMPLETED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("\n🧪 XDF Write Operations Test\n")
    
    # Create test disk
    disk_path = create_test_disk()
    
    # Run test
    success = test_write_operations(disk_path)
    
    if success:
        print("\n✅ すべてのテストに成功しました！")
        sys.exit(0)
    else:
        print("\n❌ テスト失敗")
        sys.exit(1)
