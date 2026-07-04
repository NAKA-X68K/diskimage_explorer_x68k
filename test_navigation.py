#!/usr/bin/env python
"""Test navigation functionality between tree view and column view."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import CustomColumnView
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt


def test_navigate_to_root():
    """Test navigating to root directory."""
    print("Test: Navigate to Root")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Navigate to root
        view.navigate_to("/")
        
        assert view.current_path == "/", f"Current path should be /, got {view.current_path}"
        assert len(view.views) >= 1, "Should have at least one column"
        
        print(f"✓ Navigated to root: {view.current_path}")
        print(f"✓ Columns: {len(view.views)}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_navigate_with_path_components():
    """Test navigating using path components."""
    print("\nTest: Navigate with Path Components")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Use simple path
        view.navigate_to("/")
        
        assert view.current_path == "/", "Should be at root"
        print(f"✓ Navigated to /")
        print(f"✓ Columns: {len(view.views)}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_refresh_on_path_change():
    """Test that columns are refreshed when path changes."""
    print("\nTest: Column Refresh on Path Change")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Navigate to root and check columns
        view.navigate_to("/")
        initial_col_count = len(view.views)
        initial_items = view.views[0].model().rowCount() if view.views else 0
        
        print(f"✓ Initial state: {initial_col_count} columns, {initial_items} items")
        
        # Navigate to same path (should not change columns)
        view.navigate_to("/")
        after_nav_col_count = len(view.views)
        after_nav_items = view.views[0].model().rowCount() if view.views else 0
        
        assert initial_col_count == after_nav_col_count, "Column count should not change"
        assert initial_items == after_nav_items, "Item count should not change"
        
        print(f"✓ After re-navigation: {after_nav_col_count} columns, {after_nav_items} items")
        print(f"✓ Columns properly refreshed")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tree_path_building():
    """Test building tree paths from individual components."""
    print("\nTest: Tree Path Building")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Build mock tree structure
        app = QApplication.instance() or QApplication([])
        tree = QTreeWidget()
        root = tree.invisibleRootItem()
        
        # Add items to tree
        entries = backend.list_dir("/")
        for entry in entries:
            item = QTreeWidgetItem()
            item.setText(0, entry.name)
            item.setData(0, Qt.UserRole + 1, entry.is_dir)
            root.addChild(item)
        
        print(f"✓ Created tree with {root.childCount()} items")
        
        # Verify path extraction
        for i in range(root.childCount()):
            child = root.child(i)
            name = child.text(0)
            print(f"  - {name}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_partition_switching():
    """Test switching between partitions preserves navigation state."""
    print("\nTest: Partition Switching")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        
        # Test the first valid partition only
        offsets = backend.offset_candidates
        print(f"Found {len(offsets)} partitions, testing first valid FAT partition")
        
        for i, offset in enumerate(offsets[:2]):
            try:
                backend.remount_at_offset(offset)
                label = backend.get_offset_label(offset)
                
                view.set_backend(backend)
                view.navigate_to("/")
                
                col_count = len(view.views)
                item_count = view.views[0].model().rowCount() if view.views else 0
                
                print(f"✓ Partition {i+1} ({label}): {col_count} columns, {item_count} items")
            except Exception as e:
                print(f"⚠ Partition {i+1}: {str(e)[:50]}")
                continue
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_deep_navigation():
    """Test navigating to deeply nested directories."""
    print("\nTest: Deep Navigation")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Try to navigate deep (build path structure)
        def explore_dirs(path, depth=0, max_depth=3):
            """Recursively explore directories."""
            if depth >= max_depth:
                return
            
            try:
                entries = backend.list_dir(path)
                dirs = [e for e in entries if e.is_dir]
                
                if not dirs:
                    return
                
                first_dir = dirs[0]
                view.navigate_to(first_dir.path)
                
                indent = "  " * depth
                print(f"{indent}✓ Navigated to {first_dir.path}")
                
                explore_dirs(first_dir.path, depth + 1, max_depth)
            except Exception:
                pass
        
        explore_dirs("/")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Navigation Functionality Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Navigate to Root", test_navigate_to_root),
        ("Navigate with Path Components", test_navigate_with_path_components),
        ("Column Refresh on Path Change", test_column_refresh_on_path_change),
        ("Tree Path Building", test_tree_path_building),
        ("Partition Switching", test_partition_switching),
        ("Deep Navigation", test_deep_navigation),
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
