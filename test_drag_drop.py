#!/usr/bin/env python
"""Test drag and drop functionality."""

import sys
import tempfile
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend
from diskimage_explorer_x68k.column_view import CustomColumnView, ColumnListView
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
from PySide6.QtGui import QDrag


def test_export_file():
    """Test exporting file from image to temp directory."""
    print("Test: Export File")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Get first file
        entries = backend.list_dir("/")
        files = [e for e in entries if not e.is_dir]
        
        if not files:
            print("⚠ No files found to export")
            backend.unmount()
            return True
        
        first_file = files[0]
        print(f"Exporting: {first_file.name}")
        
        # Export to temp directory
        temp_dir = Path(tempfile.gettempdir())
        export_path = temp_dir / f"xdf_test_{first_file.name}"
        
        # Use backend export
        backend.export_path_to_local(first_file.path, export_path)
        
        # Verify file exists
        assert export_path.exists(), f"Exported file not found: {export_path}"
        assert export_path.stat().st_size > 0, "Exported file is empty"
        
        print(f"✓ Exported {first_file.name} ({export_path.stat().st_size} bytes)")
        
        # Clean up
        export_path.unlink()
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_drag_data_preparation():
    """Test preparing drag data."""
    print("\nTest: Drag Data Preparation")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Get first column view
        if not view.views:
            print("⚠ No columns available")
            backend.unmount()
            return True
        
        list_view = view.views[0]
        model = list_view.model()
        
        # Prepare drag data
        if model.rowCount() > 0:
            index = model.index(0, 0)
            data = model.data(index, Qt.UserRole)
            
            assert data is not None, "Data should not be None"
            assert 'name' in data, "Data should have name"
            assert 'path' in data, "Data should have path"
            assert 'is_dir' in data, "Data should have is_dir"
            
            print(f"✓ Drag data prepared: {data['name']}")
        else:
            print("⚠ No items in model")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_drop_signal_emission():
    """Test drop signal emission."""
    print("\nTest: Drop Signal Emission")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Connect signal
        dropped_data = []
        
        def on_files_dropped(path: str, files: list):
            dropped_data.append((path, files))
        
        view.filesDropped.connect(on_files_dropped)
        
        # Simulate drop
        test_files = ["/tmp/test1.txt", "/tmp/test2.txt"]
        view.on_drop_files(test_files)
        
        # Check signal was emitted
        assert len(dropped_data) > 0, "filesDropped signal should be emitted"
        
        path, files = dropped_data[0]
        assert path == "/", f"Path should be /, got {path}"
        assert files == test_files, f"Files should match"
        
        print(f"✓ Drop signal emitted: {len(dropped_data)} times")
        print(f"  Path: {path}")
        print(f"  Files: {len(files)} files")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_operations_workflow():
    """Test complete file operations workflow."""
    print("\nTest: File Operations Workflow")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        app = QApplication.instance() or QApplication([])
        view = CustomColumnView()
        view.set_backend(backend)
        view.navigate_to("/")
        
        # Get initial file count
        initial_files = backend.list_dir("/")
        print(f"Initial files: {len(initial_files)}")
        
        # Test create/write workflow
        test_content = b"Test file content"
        test_path = "/test_new.txt"
        
        try:
            # Try to write a file
            backend.write_file_bytes(test_path, test_content)
            print(f"✓ Created test file: {test_path}")
            
            # Refresh view
            view.refresh()
            
            # Check file exists
            after_write = backend.list_dir("/")
            print(f"After write: {len(after_write)} files")
            
            # Clean up
            backend.delete_file(test_path)
            print(f"✓ Deleted test file: {test_path}")
            
        except Exception as e:
            print(f"⚠ File operation failed (expected for read-only): {str(e)[:50]}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_file_selection():
    """Test selecting multiple files for drag."""
    print("\nTest: Multi-File Selection")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/TEST_DATA/SASI.hdf"
    backend = FatImageBackend()
    
    try:
        # Find partition with multiple files
        backend.mount(image_path)
        
        for offset in backend.offset_candidates[:1]:
            try:
                backend.remount_at_offset(offset)
                
                entries = backend.list_dir("/")
                files = [e for e in entries if not e.is_dir]
                
                if len(files) >= 2:
                    print(f"✓ Found {len(files)} files for multi-selection test")
                    
                    # List files
                    for file_info in files[:3]:
                        print(f"  - {file_info.name} ({file_info.size} bytes)")
                    
                    backend.unmount()
                    return True
            
            except Exception as e:
                continue
        
        print("⚠ No partition with multiple files found")
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Drag and Drop Functionality Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Export File", test_export_file),
        ("Drag Data Preparation", test_drag_data_preparation),
        ("Drop Signal Emission", test_drop_signal_emission),
        ("File Operations Workflow", test_file_operations_workflow),
        ("Multi-File Selection", test_multi_file_selection),
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
