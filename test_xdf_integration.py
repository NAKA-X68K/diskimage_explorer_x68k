#!/usr/bin/env python3
"""Test XDF integration with x68k-hdf-editor backend."""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from diskimage_explorer_x68k.backend import FatImageBackend

def test_xdf_mount():
    """Test mounting XDF file."""
    backend = FatImageBackend()
    
    # Use a test XDF file from the XDF directory
    xdf_file = Path('/Users/taknakam/X68000/GCC1.XDF')
    
    if not xdf_file.exists():
        print(f"❌ Test file not found: {xdf_file}")
        return False
    
    print(f"Testing XDF mount: {xdf_file}")
    
    try:
        backend.mount(xdf_file)
        print(f"✅ Mounted successfully")
        print(f"   Mount kind: {backend._mount_kind}")
        print(f"   Offset candidates: {backend.offset_candidates}")
        
        # Try to list root directory
        entries = backend.list_dir('/')
        print(f"✅ Listed {len(entries)} items in root:")
        for entry in entries[:5]:
            print(f"   - {entry.name} ({entry.size} bytes, {'DIR' if entry.is_dir else 'FILE'})")
        
        if len(entries) > 5:
            print(f"   ... and {len(entries) - 5} more items")
        
        backend.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_xdf_mount()
    sys.exit(0 if success else 1)
