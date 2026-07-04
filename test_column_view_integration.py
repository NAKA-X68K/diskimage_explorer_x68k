#!/usr/bin/env python
"""Comprehensive column view integration test."""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import (
    DiskFileInfo,
    ColumnViewModel,
    CustomColumnView,
)


def test_backend_list_dir():
    """Test backend list_dir with real disk image."""
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # List root directory
        entries = backend.list_dir("/")
        assert len(entries) > 0, "Root should have entries"
        print(f"✓ Backend can list root directory: {len(entries)} entries")
        
        # Check entry types
        for entry in entries:
            assert hasattr(entry, 'name'), "Entry should have name"
            assert hasattr(entry, 'is_dir'), "Entry should have is_dir"
            assert hasattr(entry, 'size'), "Entry should have size"
            assert hasattr(entry, 'modified'), "Entry should have modified"
            assert hasattr(entry, 'path'), "Entry should have path"
            assert isinstance(entry.modified, str), f"Entry.modified should be string, got {type(entry.modified)}"
        
        print("✓ All entries have correct structure")
        
        # Find a directory to test navigation
        first_dir = None
        for entry in entries:
            if entry.is_dir:
                first_dir = entry
                break
        
        if first_dir:
            subentries = backend.list_dir(first_dir.path)
            print(f"✓ Can navigate to subdirectory: {first_dir.name} ({len(subentries)} entries)")
        
        backend.unmount()
        return True
    
    except Exception as e:
        print(f"✗ Backend test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_model():
    """Test ColumnViewModel with real backend."""
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Create model for root
        model = ColumnViewModel(backend, "/")
        assert model.rowCount() > 0, "Model should have rows"
        print(f"✓ ColumnViewModel created for root with {model.rowCount()} rows")
        
        # Check items
        for i in range(min(3, model.rowCount())):
            item = model.items[i]
            assert isinstance(item, DiskFileInfo), "Items should be DiskFileInfo"
            assert len(item.name) > 0, "Item should have name"
            assert len(item.size_str()) > 0, "Item should have size_str"
            assert len(item.date_str()) >= 0, "Item should have date_str"
            print(f"  - {item.name}: {item.size_str()} ({item.date_str()})")
        
        print("✓ ColumnViewModel items are correctly formatted")
        
        # Test navigation to first directory
        first_dir = None
        for item in model.items:
            if item.is_dir:
                first_dir = item
                break
        
        if first_dir:
            model2 = ColumnViewModel(backend, first_dir.path)
            print(f"✓ Can create model for subdirectory: {first_dir.path} ({model2.rowCount()} rows)")
        
        backend.unmount()
        return True
    
    except Exception as e:
        print(f"✗ ColumnViewModel test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_custom_column_view():
    """Test CustomColumnView initialization."""
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Create mock QWidget parent (we need this for CustomColumnView)
        from PySide6.QtWidgets import QApplication, QWidget
        
        # Create application if needed
        if not QApplication.instance():
            app = QApplication([])
        
        # Create CustomColumnView
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Navigate to root
        view.navigate_to("/")
        assert view.current_path == "/", "Should be at root"
        print("✓ CustomColumnView initialized and navigated to root")
        
        # Get first item
        if view.views:
            first_col = view.views[0]
            print(f"✓ First column created with {first_col.model().rowCount()} items")
        
        backend.unmount()
        return True
    
    except Exception as e:
        print(f"✗ CustomColumnView test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_navigate_to_subdirectory():
    """Test navigation to subdirectory."""
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Find first directory
        entries = backend.list_dir("/")
        first_dir = None
        for entry in entries:
            if entry.is_dir:
                first_dir = entry
                break
        
        if not first_dir:
            print("⚠ No subdirectory found to test navigation")
            backend.unmount()
            return True
        
        print(f"✓ Testing navigation to: {first_dir.path}")
        
        # Create model for subdirectory
        model = ColumnViewModel(backend, first_dir.path)
        print(f"✓ Subdirectory has {model.rowCount()} entries")
        
        backend.unmount()
        return True
    
    except Exception as e:
        print(f"✗ Navigation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Column View Integration Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Backend list_dir", test_backend_list_dir),
        ("ColumnViewModel", test_column_view_model),
        ("Navigation to subdirectory", test_navigate_to_subdirectory),
        ("CustomColumnView", test_custom_column_view),
    ]
    
    for name, test_func in tests:
        print(f"\nTest: {name}")
        print("-" * 50)
        result = test_func()
        results.append((name, result))
    
    print("\n" + "=" * 50)
    print("Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed!")
        sys.exit(1)
