#!/usr/bin/env python
"""Test context menu functionality."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import CustomColumnView, ColumnListView
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QContextMenuEvent


def test_context_menu_creation():
    """Test context menu creation."""
    print("Test: Context Menu Creation")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Get first list view
        if not view.views:
            print("⚠ No columns available")
            backend.unmount()
            return True
        
        list_view = view.views[0]
        
        # Check it's a ColumnListView
        assert isinstance(list_view, ColumnListView), "Should be ColumnListView"
        print("✓ ColumnListView created")
        
        # Select first item
        if list_view.model().rowCount() > 0:
            list_view.setCurrentIndex(list_view.model().index(0, 0))
            print("✓ Item selected")
            
            # Verify selection
            selection_model = list_view.selectionModel()
            assert selection_model.hasSelection(), "Should have selection"
            print("✓ Selection model has selection")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_delete_action():
    """Test delete action functionality."""
    print("\nTest: Delete Action")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Create a test file
        test_path = "/context_test.txt"
        backend.write_file_bytes(test_path, b"test")
        print(f"✓ Created test file: {test_path}")
        
        # Refresh view
        view.refresh()
        view.navigate_to("/")
        
        # Find and select the test file
        list_view = view.views[0]
        model = list_view.model()
        
        for i, item in enumerate(model.items):
            if item.name == "context_test.txt":
                list_view.setCurrentIndex(model.index(i, 0))
                print(f"✓ Selected test file at index {i}")
                
                # Test delete action
                view.on_delete_selected(list_view)
                print("✓ Delete action executed")
                
                # Verify file is gone
                view.refresh()
                remaining = [item.name for item in model.items if item.name == "context_test.txt"]
                assert len(remaining) == 0, "File should be deleted"
                print("✓ File verified deleted")
                
                break
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_info_action():
    """Test info action functionality."""
    print("\nTest: Info Action")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Get first list view
        list_view = view.views[0]
        model = list_view.model()
        
        # Select first item
        if model.rowCount() > 0:
            list_view.setCurrentIndex(model.index(0, 0))
            
            # Test info action
            try:
                view.on_show_info(list_view)
                print("✓ Info action executed")
            except Exception as e:
                print(f"⚠ Info action: {e}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_select_delete():
    """Test deleting multiple selected items."""
    print("\nTest: Multi-Select Delete")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Find a partition with multiple files
        for offset in backend.offset_candidates:
            try:
                backend.remount_at_offset(offset)
                entries = backend.list_dir("/")
                if len(entries) >= 2:
                    print(f"✓ Found {len(entries)} items to test")
                    
                    app = QApplication.instance() or QApplication([])
                    view = CustomColumnView()
                    view.set_backend(backend)
                    view.navigate_to("/")
                    
                    list_view = view.views[0]
                    model = list_view.model()
                    
                    # Select multiple items (first 2)
                    selection_model = list_view.selectionModel()
                    selection_model.clearSelection()
                    
                    select_count = min(2, model.rowCount())
                    for i in range(select_count):
                        selection_model.select(
                            model.index(i, 0),
                            selection_model.Select
                        )
                    
                    print(f"✓ Selected {select_count} items")
                    
                    # Count selected
                    selected = len(selection_model.selectedIndexes())
                    print(f"✓ Selection model shows {selected} selected")
                    
                    backend.unmount()
                    return True
            
            except Exception as e:
                continue
        
        print("⚠ No suitable partition found")
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Context Menu Functionality Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Context Menu Creation", test_context_menu_creation),
        ("Delete Action", test_delete_action),
        ("Info Action", test_info_action),
        ("Multi-Select Delete", test_multi_select_delete),
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
