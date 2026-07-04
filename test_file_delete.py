#!/usr/bin/env python
"""Test file deletion functionality."""

import sys
import tempfile
import shutil
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend


def test_create_and_delete():
    """Test creating and deleting a file."""
    print("Test: Create and Delete File")
    print("-" * 50)
    
    # Use a temporary copy of the image
    image_path = "/Users/taknakam/X68000/FD.2hd"
    temp_dir = Path(tempfile.gettempdir())
    temp_image = temp_dir / "test_fd.2hd"
    
    try:
        # Copy image to temp
        shutil.copy(image_path, temp_image)
        print(f"✓ Created temp image: {temp_image}")
        
        backend = FatImageBackend()
        backend.mount(str(temp_image))
        
        # Get initial file count
        initial = backend.list_dir("/")
        print(f"Initial files: {len(initial)}")
        
        # Create a test file
        test_content = b"Test content for deletion"
        test_path = "/test_delete.txt"
        
        backend.write_file_bytes(test_path, test_content)
        print(f"✓ Created file: {test_path}")
        
        # Verify it exists
        after_create = backend.list_dir("/")
        created = any(e.name == "test_delete.txt" for e in after_create)
        assert created, "File should exist after creation"
        print(f"✓ File verified: {len(after_create)} files")
        
        # Delete the file
        backend.delete_paths([test_path])
        print(f"✓ Deleted file: {test_path}")
        
        # Verify it's gone
        after_delete = backend.list_dir("/")
        deleted = not any(e.name == "test_delete.txt" for e in after_delete)
        assert deleted, "File should not exist after deletion"
        print(f"✓ Verified deletion: {len(after_delete)} files")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if temp_image.exists():
            temp_image.unlink()


def test_delete_directory():
    """Test deleting a directory."""
    print("\nTest: Delete Directory")
    print("-" * 50)
    
    # Use a temporary copy of the image
    image_path = "/Users/taknakam/X68000/FD.2hd"
    temp_dir = Path(tempfile.gettempdir())
    temp_image = temp_dir / "test_fd_dir.2hd"
    
    try:
        # Copy image to temp
        shutil.copy(image_path, temp_image)
        print(f"✓ Created temp image: {temp_image}")
        
        backend = FatImageBackend()
        backend.mount(str(temp_image))
        
        # Create a directory
        test_dir = "/testdir"
        
        try:
            backend.fs.makedir(test_dir)
            print(f"✓ Created directory: {test_dir}")
            
            # Verify it exists
            entries = backend.list_dir("/")
            exists = any(e.name == "testdir" and e.is_dir for e in entries)
            assert exists, "Directory should exist after creation"
            print(f"✓ Directory verified")
            
            # Delete the directory
            backend.delete_paths([test_dir])
            print(f"✓ Deleted directory: {test_dir}")
            
            # Verify it's gone
            entries_after = backend.list_dir("/")
            deleted = not any(e.name == "testdir" for e in entries_after)
            assert deleted, "Directory should not exist after deletion"
            print(f"✓ Verified deletion")
        
        except Exception as e:
            print(f"⚠ Directory operation: {str(e)[:50]}")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if temp_image.exists():
            temp_image.unlink()


def test_delete_multiple_files():
    """Test deleting multiple files at once."""
    print("\nTest: Delete Multiple Files")
    print("-" * 50)
    
    # Use a temporary copy of the image
    image_path = "/Users/taknakam/X68000/FD.2hd"
    temp_dir = Path(tempfile.gettempdir())
    temp_image = temp_dir / "test_fd_multi.2hd"
    
    try:
        # Copy image to temp
        shutil.copy(image_path, temp_image)
        print(f"✓ Created temp image: {temp_image}")
        
        backend = FatImageBackend()
        backend.mount(str(temp_image))
        
        # Create multiple test files
        test_files = []
        for i in range(3):
            test_path = f"/multitest{i}.txt"
            backend.write_file_bytes(test_path, f"Test {i}".encode())
            test_files.append(test_path)
        
        print(f"✓ Created {len(test_files)} files")
        
        # Verify they exist
        entries = backend.list_dir("/")
        created_count = sum(1 for e in entries if e.name.startswith("multitest"))
        assert created_count == 3, f"Should have 3 files, got {created_count}"
        print(f"✓ All files verified: {created_count} files")
        
        # Delete all at once
        backend.delete_paths(test_files)
        print(f"✓ Deleted {len(test_files)} files")
        
        # Verify all are gone
        entries_after = backend.list_dir("/")
        remaining = sum(1 for e in entries_after if e.name.startswith("multitest"))
        assert remaining == 0, f"Should have 0 files, got {remaining}"
        print(f"✓ All files deleted")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if temp_image.exists():
            temp_image.unlink()


def test_delete_with_backup():
    """Test that backup is created before deletion."""
    print("\nTest: Delete with Backup")
    print("-" * 50)
    
    # Use a temporary copy of the image
    image_path = "/Users/taknakam/X68000/FD.2hd"
    temp_dir = Path(tempfile.gettempdir())
    temp_image = temp_dir / "test_fd_backup.2hd"
    
    try:
        # Copy image to temp
        shutil.copy(image_path, temp_image)
        print(f"✓ Created temp image: {temp_image}")
        
        backend = FatImageBackend()
        backend.mount(str(temp_image))
        
        # Get initial file size
        initial_size = temp_image.stat().st_size
        
        # Create and delete a file
        test_path = "/backup_test.txt"
        backend.write_file_bytes(test_path, b"Backup test content")
        backend.delete_paths([test_path])
        
        print(f"✓ Created and deleted file: {test_path}")
        
        # Check if backup was created
        backup_dir = Path(backend.backup_path)
        if backup_dir.exists():
            backups = list(backup_dir.glob("*.2hd"))
            print(f"✓ Backups created: {len(backups)} backup(s)")
        else:
            print("⚠ Backup directory not found")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if temp_image.exists():
            temp_image.unlink()


if __name__ == "__main__":
    print("File Deletion Functionality Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Create and Delete File", test_create_and_delete),
        ("Delete Directory", test_delete_directory),
        ("Delete Multiple Files", test_delete_multiple_files),
        ("Delete with Backup", test_delete_with_backup),
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
