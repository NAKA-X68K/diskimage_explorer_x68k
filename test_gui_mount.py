#!/usr/bin/env python
"""GUI backend test - verify column view integration without displaying window."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Suppress QT warnings
import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import CustomColumnView


def test_backend_mount_fd():
    """Test backend mounting FD.2hd."""
    print("Test 1: Mount FD.2hd with Backend")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        print(f"✓ Image mounted: {image_path}")
        print(f"  Image path: {backend.image_path}")
        print(f"  FS type: {type(backend.fs).__name__}")
        
        # List root
        entries = backend.list_dir("/")
        print(f"✓ Root directory has {len(entries)} entries")
        
        for entry in entries[:5]:
            print(f"  - {entry.name} (size={entry.size}, is_dir={entry.is_dir})")
        
        backend.unmount()
        print("✓ Image unmounted")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backend_mount_sasi():
    """Test backend mounting SASI.hdf (HDF partition)."""
    print("\nTest 2: Mount SASI.hdf (HDF Partition)")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        print(f"✓ Image mounted: {image_path}")
        
        # List partitions
        offsets = backend.offset_candidates
        print(f"✓ Found {len(offsets)} partitions")
        
        for offset in offsets[:3]:
            label = backend.get_offset_label(offset)
            print(f"  - {label} (offset: {offset})")
        
        backend.unmount()
        print("✓ Image unmounted")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backend_mount_scsi():
    """Test backend mounting SCSI.HDS (HDS partition)."""
    print("\nTest 3: Mount SCSI.HDS (HDS Partition)")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SCSI.HDS"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        print(f"✓ Image mounted: {image_path}")
        
        # List partitions
        offsets = backend.offset_candidates
        print(f"✓ Found {len(offsets)} partitions")
        
        for offset in offsets[:3]:
            label = backend.get_offset_label(offset)
            print(f"  - {label} (offset: {offset})")
        
        backend.unmount()
        print("✓ Image unmounted")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_integration():
    """Test column view integration with backend."""
    print("\nTest 4: Column View Integration")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Create column view (without GUI)
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        
        view = CustomColumnView()
        view.set_backend(backend)
        
        print("✓ Column view created")
        
        # Navigate to root
        view.navigate_to("/")
        print(f"✓ Navigate to root: current_path = {view.current_path}")
        
        # Check first column
        if view.views:
            first_col = view.views[0]
            row_count = first_col.model().rowCount()
            print(f"✓ First column has {row_count} items")
            
            # List items
            for item in first_col.model().items[:3]:
                print(f"  - {item.name} ({item.size_str()})")
        
        backend.unmount()
        print("✓ Column view and backend cleaned up")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("GUI Component Backend Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Mount FD.2hd", test_backend_mount_fd),
        ("Mount SASI.hdf", test_backend_mount_sasi),
        ("Mount SCSI.HDS", test_backend_mount_scsi),
        ("Column View Integration", test_column_view_integration),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 50)
    print("Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        sys.exit(1)
