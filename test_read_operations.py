#!/usr/bin/env python3
"""Integration test: XDF backend with complete file operations."""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from diskimage_explorer_x68k.backend import FatImageBackend

def test_read_operations():
    """Test all read operations."""
    print("=" * 70)
    print("TEST 1: Read Operations (XDF ネイティブ対応確認)")
    print("=" * 70)
    
    backend = FatImageBackend()
    xdf_file = Path('/Users/taknakam/X68000/GCC1.XDF')
    
    try:
        # Mount
        backend.mount(xdf_file)
        print(f"✅ Mounted: {xdf_file.name}")
        print(f"   Mount kind: {backend._mount_kind}")
        
        # List root
        print("\n📁 Root directory:")
        entries = backend.list_dir('/')
        for entry in entries[:8]:
            type_icon = "📁" if entry.is_dir else "📄"
            print(f"   {type_icon} {entry.name:20} {entry.size:>10} bytes")
        
        if len(entries) > 8:
            print(f"   ... ({len(entries) - 8} more items)")
        
        # Read a file
        print("\n📖 Reading file (AUTOEXEC.BAT):")
        data = backend.read_file_bytes('/AUTOEXEC.BAT')
        print(f"   ✅ Read {len(data)} bytes")
        print(f"   Content (first 100 chars):")
        preview = data[:100].decode('latin-1', errors='ignore').replace('\n', '\\n')
        print(f"   {preview}...")
        
        # Get file info
        print("\n📊 File info (AUTOEXEC.BAT):")
        info = backend.fs.getinfo('/AUTOEXEC.BAT', namespaces=['details'])
        print(f"   Size: {info.raw['details']['size']} bytes")
        print(f"   Is directory: {info.is_dir}")
        
        # List subdirectory
        print("\n📁 Subdirectory (BIN):")
        bin_entries = backend.list_dir('/BIN')
        for entry in bin_entries[:5]:
            type_icon = "📁" if entry.is_dir else "📄"
            print(f"   {type_icon} {entry.name:20} {entry.size:>10} bytes")
        
        if len(bin_entries) > 5:
            print(f"   ... ({len(bin_entries) - 5} more items)")
        
        backend.close()
        print("\n" + "=" * 70)
        print("✅ ALL READ TESTS PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_backend_compatibility():
    """Test backend compatibility with GUI expectations."""
    print("\n" + "=" * 70)
    print("TEST 2: Backend Compatibility (GUI互換性確認)")
    print("=" * 70)
    
    backend = FatImageBackend()
    xdf_file = Path('/Users/taknakam/X68000/GCC1.XDF')
    
    try:
        backend.mount(xdf_file)
        
        # Test mount candidates
        print(f"✅ Mount candidates: {len(backend.mount_candidates)} found")
        for i, cand in enumerate(backend.mount_candidates):
            print(f"   [{i}] {cand.label} (kind={cand.kind}, offset=0x{cand.offset:08X})")
        
        # Test remount
        if backend.offset_candidates:
            offset = backend.offset_candidates[0]
            backend.remount_at_offset(offset)
            print(f"✅ Remount successful at offset 0x{offset:08X}")
        
        # Test getinfo for directory
        info = backend.fs.getinfo('/', namespaces=['details'])
        print(f"✅ Root directory info retrieved (is_dir={info.is_dir})")
        
        # Test openbin for read
        with backend.fs.openbin('/AUTOEXEC.BAT', 'r') as fp:
            data = fp.read()
            print(f"✅ openbin() read mode: {len(data)} bytes")
        
        backend.close()
        print("\n" + "=" * 70)
        print("✅ ALL COMPATIBILITY TESTS PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("\n🧪 X68K HDF Editor - XDF Integration Tests\n")
    
    result1 = test_read_operations()
    result2 = test_backend_compatibility()
    
    if result1 and result2:
        print("\n" + "🎉 " * 20)
        print("✅ すべてのテストに成功！ GUI統合は完全です")
        print("🎉 " * 20)
        sys.exit(0)
    else:
        print("\n❌ テスト失敗")
        sys.exit(1)
