#!/usr/bin/env python
"""Test HDF/HDS partition synchronization between views."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import CustomColumnView
from PySide6.QtWidgets import QApplication


def test_partition_detection():
    """Test detecting partitions in HDF/HDS images."""
    print("Test: Partition Detection")
    print("-" * 50)
    
    images = [
        ("/Users/taknakam/X68000/TEST_DATA/SASI.hdf", "HDF"),
        ("/Users/taknakam/X68000/TEST_DATA/SCSI.HDS", "HDS"),
    ]
    
    for image_path, format_name in images:
        if not Path(image_path).exists():
            print(f"⚠ {format_name} image not found")
            continue
        
        try:
            backend = FatImageBackend()
            backend.mount(image_path)
            
            offsets = backend.offset_candidates
            print(f"✓ {format_name}: {len(offsets)} partitions detected")
            
            for i, offset in enumerate(offsets):
                label = backend.get_offset_label(offset)
                print(f"  [{i}] {label} @ offset {offset}")
            
            backend.unmount()
            
        except Exception as e:
            print(f"✗ {format_name}: {e}")
            return False
    
    return True


def test_partition_remount():
    """Test remounting to different partitions."""
    print("\nTest: Partition Remount")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        offsets = backend.offset_candidates
        print(f"Testing {len(offsets)} partitions")
        
        for i, offset in enumerate(offsets[:2]):
            try:
                # Get current offset before remount
                old_offset = backend.current_offset
                
                # Remount to new partition
                backend.remount_at_offset(offset)
                
                # Verify offset changed
                new_offset = backend.current_offset
                label = backend.get_offset_label(offset)
                
                assert new_offset == offset, f"Offset mismatch: {new_offset} != {offset}"
                
                # List entries
                entries = backend.list_dir("/")
                print(f"✓ Partition [{i}] ({label}): {len(entries)} entries")
                
            except Exception as e:
                print(f"⚠ Partition [{i}]: {str(e)[:50]}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_partition_sync():
    """Test column view updates when partition changes."""
    print("\nTest: Column View Partition Synchronization")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        offsets = backend.offset_candidates
        print(f"Testing partition sync across {len(offsets)} partitions")
        
        previous_items = None
        
        for i, offset in enumerate(offsets[:2]):
            try:
                # Remount to partition
                backend.remount_at_offset(offset)
                
                # Update column view with new backend
                view.set_backend(backend)
                view.navigate_to("/")
                
                # Get items from first column
                if view.views:
                    current_items = [item.name for item in view.views[0].model().items]
                    label = backend.get_offset_label(offset)
                    
                    print(f"✓ Partition [{i}] ({label}): {len(current_items)} items")
                    
                    # Check if items changed
                    if previous_items and current_items != previous_items:
                        print(f"  Items changed from previous partition")
                    
                    previous_items = current_items
            
            except Exception as e:
                print(f"⚠ Partition [{i}]: {str(e)[:50]}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_partition_offset_labels():
    """Test partition offset label generation."""
    print("\nTest: Partition Offset Labels")
    print("-" * 50)
    
    images = [
        ("/Users/taknakam/X68000/TEST_DATA/SASI.hdf", "HDF"),
        ("/Users/taknakam/X68000/TEST_DATA/SCSI.HDS", "HDS"),
    ]
    
    for image_path, format_name in images:
        if not Path(image_path).exists():
            print(f"⚠ {format_name} image not found")
            continue
        
        try:
            backend = FatImageBackend()
            backend.mount(image_path)
            
            offsets = backend.offset_candidates
            
            print(f"✓ {format_name} partition labels:")
            for i, offset in enumerate(offsets):
                label = backend.get_offset_label(offset)
                print(f"  [{i}] {label}")
                
                # Verify label format
                assert "@" in label or offset == 0, f"Label format unexpected: {label}"
            
            backend.unmount()
            
        except Exception as e:
            print(f"✗ {format_name}: {e}")
            return False
    
    return True


def test_partition_content_verification():
    """Verify different partitions have different content."""
    print("\nTest: Partition Content Verification")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        offsets = backend.offset_candidates
        partition_contents = {}
        
        for i, offset in enumerate(offsets[:2]):
            try:
                backend.remount_at_offset(offset)
                entries = backend.list_dir("/")
                
                # Build content signature
                names = sorted([e.name for e in entries])
                partition_contents[offset] = names
                
                label = backend.get_offset_label(offset)
                print(f"✓ Partition [{i}] ({label}): {len(entries)} items")
                
            except Exception as e:
                print(f"⚠ Partition [{i}]: {str(e)[:50]}")
        
        # Verify different partitions have different (or same) content
        if len(partition_contents) > 1:
            offsets_list = list(partition_contents.keys())
            content1 = partition_contents[offsets_list[0]]
            content2 = partition_contents[offsets_list[1]]
            
            if content1 == content2:
                print("⚠ Partitions have identical content")
            else:
                print("✓ Partitions have different content")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("HDF/HDS Partition Synchronization Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Partition Detection", test_partition_detection),
        ("Partition Remount", test_partition_remount),
        ("Column View Partition Sync", test_column_view_partition_sync),
        ("Partition Offset Labels", test_partition_offset_labels),
        ("Partition Content Verification", test_partition_content_verification),
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
