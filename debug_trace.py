#!/usr/bin/env python3
"""Debug: Add logging to trace file size issue."""

import sys
from pathlib import Path

# Add XDF directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'XDF'))

from xdf_filesystem import XDFFileSystem
from xdf_fat import DirectoryEntry, ATTR_ARCHIVE
from xdf_format import MEDIA_PROFILES, MediaType
import struct
from datetime import datetime

def create_test_disk():
    """Create a blank 2HD XDF disk."""
    test_disk_path = Path('/tmp/test_debug_trace.xdf')
    
    profile = MEDIA_PROFILES[MediaType.MEDIA_2HD]
    disk_size = profile.sector_size * profile.total_sectors
    
    # Create blank disk
    disk_data = bytearray(disk_size)
    
    # Write X68000 boot sector
    disk_data[0:2] = b'\x60\x1C'
    disk_data[3:11] = b'X68IPL30'
    
    # Write big-endian BPB
    disk_data[0x12:0x14] = struct.pack('>H', profile.sector_size)
    disk_data[0x14] = 1
    disk_data[0x15] = 2
    disk_data[0x16:0x18] = struct.pack('>H', 1)
    disk_data[0x18:0x1A] = struct.pack('>H', 192)
    disk_data[0x1A:0x1C] = struct.pack('>H', profile.total_sectors)
    disk_data[0x1C] = profile.media_byte
    disk_data[0x1D] = 2
    
    with open(test_disk_path, 'wb') as f:
        f.write(disk_data)
    
    return test_disk_path

def debug_trace():
    """Trace file size through write process."""
    print("=" * 70)
    print("DEBUG TRACE: File Size Throughout Write Process")
    print("=" * 70)
    
    disk_path = create_test_disk()
    fs = XDFFileSystem(disk_path)
    
    test_content = b'Hello World!'
    print(f"\n1️⃣ Initial content: {len(test_content)} bytes")
    
    # Manually call parts of write_file to trace
    path = '\\HELLO.TXT'
    data = test_content
    
    # Get parent cluster
    from xdf_path import PathParser
    parts = PathParser.split_path(path)
    
    # Create directory entry
    now = datetime.now()
    dos_time = ((now.hour & 0x1F) << 11) | ((now.minute & 0x3F) << 5) | ((now.second >> 1) & 0x1F)
    dos_date = (((now.year - 1980) & 0x7F) << 9) | ((now.month & 0x0F) << 5) | (now.day & 0x1F)
    
    if '.' in 'HELLO.TXT':
        name_parts = 'HELLO.TXT'.rsplit('.', 1)
        short_name = name_parts[0][:8]
        ext = name_parts[1][:3]
    else:
        short_name = 'HELLO.TXT'[:8]
        ext = ''
    
    print(f"\n2️⃣ Creating DirectoryEntry:")
    print(f"   filename: {short_name}")
    print(f"   extension: {ext}")
    print(f"   file_size: {len(data)} (from len(data))")
    
    entry = DirectoryEntry(
        filename=short_name,
        extension=ext,
        attributes=ATTR_ARCHIVE,
        created_time=dos_time,
        created_date=dos_date,
        accessed_date=dos_date,
        start_cluster=3,  # Use cluster 3 for simplicity
        file_size=len(data),
        write_time=dos_time,
        write_date=dos_date,
    )
    
    print(f"\n3️⃣ DirectoryEntry created:")
    print(f"   entry.file_size = {entry.file_size}")
    
    # Convert to bytes
    print(f"\n4️⃣ Converting to bytes:")
    entry_bytes = fs.dir_reader.write_entry_to_bytes(entry)
    print(f"   entry_bytes length: {len(entry_bytes)}")
    print(f"   entry_bytes (hex): {entry_bytes.hex()}")
    
    # Extract file size from bytes
    file_size_from_bytes = struct.unpack('<I', entry_bytes[28:32])[0]
    print(f"   file_size extracted from bytes: {file_size_from_bytes}")
    
    # Add to directory
    print(f"\n5️⃣ Adding to directory:")
    fs.dir_reader.add_directory_entry(None, entry)
    
    # Read back from directory
    print(f"\n6️⃣ Reading back from directory:")
    entries = fs.dir_reader.read_root_directory()
    for e in entries:
        if e.filename.strip() == short_name:
            print(f"   Found entry: {e.full_name()}")
            print(f"   file_size: {e.file_size}")
            print(f"   start_cluster: {e.start_cluster}")

if __name__ == '__main__':
    try:
        debug_trace()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
