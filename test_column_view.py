#!/usr/bin/env python
"""Column view feature test."""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from diskimage_explorer_x68k.column_view import (
    DiskFileInfo,
    ColumnViewModel,
    CustomColumnView,
)
from diskimage_explorer_x68k.backend import FatImageBackend

def test_disk_file_info():
    """Test DiskFileInfo formatting."""
    info = DiskFileInfo(
        name="test.txt",
        is_dir=False,
        size=1024,
        modified="2024-01-15 10:30:00"
    )
    
    assert info.name == "test.txt"
    assert info.size == 1024
    assert info.size_str() == "1KB"
    assert info.date_str() == "2024-01-15 10:30"
    print("✓ DiskFileInfo formatting works correctly")


def test_column_view_with_real_disk():
    """Test column view with real disk image."""
    # Mount FD.2hd
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    backend.mount(image_path)
    
    # Test listing root directory
    entries = backend.list_dir("/")
    print(f"✓ Found {len(entries)} entries in root")
    
    for entry in entries:
        print(f"  - {entry.name} (dir={entry.is_dir}, size={entry.size})")
    
    # Create mock view for testing
    class MockColumn:
        def __init__(self):
            self.items = []
    
    # Test ColumnViewModel
    mock_list_view = Mock()
    model = ColumnViewModel(backend, "/")
    
    assert model.rowCount() > 0, "Should have at least one entry"
    print(f"✓ ColumnViewModel has {model.rowCount()} rows")
    
    # Test navigation to first directory if available
    for entry in entries:
        if entry.is_dir:
            model2 = ColumnViewModel(backend, entry.path)
            print(f"✓ Can navigate to subdirectory: {entry.path} ({model2.rowCount()} entries)")
            break
    
    backend.unmount()
    print("✓ Disk unmounted successfully")


def test_column_view_navigation():
    """Test column view navigation logic."""
    # Create a mock backend
    backend = Mock()
    backend.list_dir = Mock(return_value=[
        Mock(name="folder1", is_dir=True, path="/folder1", size=0, modified="2024-01-15"),
        Mock(name="folder2", is_dir=True, path="/folder2", size=0, modified="2024-01-15"),
        Mock(name="file1.txt", is_dir=False, path="/file1.txt", size=512, modified="2024-01-15"),
    ])
    
    model = ColumnViewModel(backend, "/")
    assert model.rowCount() == 3, "Should have 3 items"
    print("✓ ColumnViewModel navigation works correctly")


if __name__ == "__main__":
    print("Testing Column View Implementation")
    print("=" * 50)
    
    try:
        test_disk_file_info()
        test_column_view_navigation()
        test_column_view_with_real_disk()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
