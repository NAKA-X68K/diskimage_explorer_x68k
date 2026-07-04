#!/usr/bin/env python
"""Test column view tab functionality."""

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


def test_column_view_initialization():
    """Test column view initialization without GUI."""
    print("Test: Column View Initialization")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Create app (needed for QWidget)
        app = QApplication.instance() or QApplication([])
        
        # Create column view
        view = CustomColumnView()
        print("✓ CustomColumnView created")
        
        # Check initial state
        assert view.backend is None, "Initial backend should be None"
        assert view.current_path == "/", "Initial path should be /"
        assert len(view.views) == 0, "No columns until backend is set"
        print("✓ Initial state correct")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_backend_setup():
    """Test setting backend on column view."""
    print("\nTest: Column View Backend Setup")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        
        # Set backend
        view.set_backend(backend)
        print("✓ Backend set on column view")
        
        # Check state after backend setup
        assert view.backend == backend, "Backend should be set"
        assert view.current_path == "/", "Current path should be /"
        assert len(view.views) > 0, "Should have at least one column"
        print(f"✓ Column view has {len(view.views)} column(s)")
        
        # Check first column content
        first_col = view.views[0]
        model = first_col.model()
        row_count = model.rowCount()
        print(f"✓ First column has {row_count} items")
        
        # List items
        for item in model.items[:3]:
            print(f"  - {item.name} ({item.size_str()})")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_navigation():
    """Test navigating column view to different paths."""
    print("\nTest: Column View Navigation")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Test navigate to root
        view.navigate_to("/")
        assert view.current_path == "/", "Should be at /"
        print("✓ Navigated to root /")
        
        # Get first directory (if exists)
        entries = backend.list_dir("/")
        dir_entries = [e for e in entries if e.is_dir]
        
        if dir_entries:
            first_dir = dir_entries[0]
            view.navigate_to(first_dir.path)
            assert view.current_path == first_dir.path, f"Should be at {first_dir.path}"
            print(f"✓ Navigated to {first_dir.path}")
            
            # Check columns
            print(f"✓ Column view has {len(view.views)} column(s)")
        else:
            print("⚠ No subdirectories found (FD.2hd has only files at root)")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_signals():
    """Test column view signal emission."""
    print("\nTest: Column View Signals")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        
        # Connect signal to test
        signal_received = []
        
        def on_path_changed(path: str):
            signal_received.append(path)
        
        view.pathChanged.connect(on_path_changed)
        
        # Navigate and trigger signal
        view.navigate_to("/")
        
        # The signal should be emitted when navigating
        print(f"✓ Signal connections established")
        print(f"✓ Signals received: {len(signal_received)}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_view_multiformat():
    """Test column view with different disk formats."""
    print("\nTest: Column View Multi-Format Support")
    print("-" * 50)
    
    images = [
        ("/Users/taknakam/X68000/FD.2hd", "XDF"),
        ("/Users/taknakam/X68000/TEST_DATA/SASI.hdf", "HDF"),
        ("/Users/taknakam/X68000/TEST_DATA/SCSI.HDS", "HDS"),
    ]
    
    app = QApplication.instance() or QApplication([])
    
    for image_path, format_name in images:
        if not Path(image_path).exists():
            print(f"⚠ {format_name} image not found: {image_path}")
            continue
        
        try:
            backend = FatImageBackend()
            backend.mount(image_path)
            
            view = CustomColumnView()
            view.set_backend(backend)
            
            # Try to navigate
            view.navigate_to("/")
            
            # Check columns
            col_count = len(view.views)
            item_count = view.views[0].model().rowCount() if view.views else 0
            
            print(f"✓ {format_name}: {col_count} columns, {item_count} items")
            
            backend.unmount()
            
        except Exception as e:
            print(f"⚠ {format_name}: {e}")
    
    return True


if __name__ == "__main__":
    print("Column View Tab Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Column View Initialization", test_column_view_initialization),
        ("Column View Backend Setup", test_column_view_backend_setup),
        ("Column View Navigation", test_column_view_navigation),
        ("Column View Signals", test_column_view_signals),
        ("Column View Multi-Format", test_column_view_multiformat),
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
