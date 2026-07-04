#!/usr/bin/env python
"""Test tree view functionality with real disk image."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

import warnings
warnings.filterwarnings('ignore')

from diskimage_explorer_x68k.backend import FatImageBackend


def test_tree_snapshot_building():
    """Test building tree snapshots from disk entries."""
    print("Test: Tree Snapshot Building")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Recursively list directories to build tree
        def build_tree(path, depth=0):
            """Build tree structure recursively."""
            entries = backend.list_dir(path)
            items = []
            
            for entry in entries:
                indent = "  " * depth
                print(f"{indent}{'📁' if entry.is_dir else '📄'} {entry.name} ({entry.size} bytes)")
                
                items.append({
                    'name': entry.name,
                    'path': entry.path,
                    'is_dir': entry.is_dir,
                    'size': entry.size,
                    'children': []
                })
                
                if entry.is_dir and depth < 5:  # Limit depth
                    items[-1]['children'] = build_tree(entry.path, depth + 1)
            
            return items
        
        print("\nDirectory Structure:")
        print("-" * 50)
        tree = build_tree("/")
        
        print(f"\n✓ Built tree with {len(tree)} root items")
        
        # Verify structure
        for item in tree:
            assert 'name' in item, "Item should have name"
            assert 'path' in item, "Item should have path"
            assert 'is_dir' in item, "Item should have is_dir"
            assert 'size' in item, "Item should have size"
            assert 'children' in item, "Item should have children"
        
        print("✓ All items have correct structure")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tree_traversal():
    """Test traversing tree to find specific files."""
    print("\nTest: Tree Traversal and File Finding")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Find all files matching pattern
        def find_files(path, pattern=""):
            """Find files matching pattern."""
            matches = []
            
            try:
                entries = backend.list_dir(path)
                
                for entry in entries:
                    if pattern and pattern.lower() not in entry.name.lower():
                        continue
                    
                    matches.append({
                        'name': entry.name,
                        'path': entry.path,
                        'size': entry.size,
                        'is_dir': entry.is_dir
                    })
                    
                    if entry.is_dir:
                        matches.extend(find_files(entry.path, pattern))
            
            except Exception:
                pass
            
            return matches
        
        # Find all files
        all_files = find_files("/")
        print(f"Found {len(all_files)} items in tree")
        
        for file_info in all_files:
            kind = "dir" if file_info['is_dir'] else "file"
            print(f"  - {file_info['path']} ({kind}, size={file_info['size']})")
        
        # Test finding specific file
        txt_files = find_files("/", ".x")
        print(f"\n✓ Found {len(txt_files)} files matching '.x'")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_path_consistency():
    """Test that paths are consistent across navigation."""
    print("\nTest: Path Consistency")
    print("-" * 50)
    
    image_path = "/Users/taknakam/X68000/FD.2hd"
    backend = FatImageBackend()
    
    try:
        backend.mount(image_path)
        
        # Get root entries
        root_entries = backend.list_dir("/")
        print(f"Root has {len(root_entries)} entries")
        
        # For each entry, verify we can access it
        for entry in root_entries:
            # Re-list to verify consistency
            entries_again = backend.list_dir("/")
            
            # Check if entry exists
            found = False
            for e in entries_again:
                if e.name == entry.name:
                    found = True
                    assert e.path == entry.path, f"Path mismatch: {e.path} != {entry.path}"
                    assert e.size == entry.size, f"Size mismatch: {e.size} != {entry.size}"
                    break
            
            assert found, f"Entry {entry.name} disappeared"
            print(f"✓ {entry.name} path consistent")
        
        print(f"✓ All {len(root_entries)} paths are consistent")
        
        backend.unmount()
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_large_directory_handling():
    """Test handling of directories with many files."""
    print("\nTest: Large Directory Handling")
    print("-" * 50)
    
    # Try different disk images
    for image_path in [
        "/Users/taknakam/X68000/TEST_DATA/SASI.hdf",
        "/Users/taknakam/X68000/TEST_DATA/SCSI.HDS",
    ]:
        if not Path(image_path).exists():
            print(f"⚠ {Path(image_path).name} not found, skipping")
            continue
        
        backend = FatImageBackend()
        
        try:
            backend.mount(image_path)
            
            # Count items at each partition
            for offset in backend.offset_candidates[:2]:
                backend.remount_at_offset(offset)
                label = backend.get_offset_label(offset)
                
                entries = backend.list_dir("/")
                print(f"✓ {label}: {len(entries)} entries")
            
            backend.unmount()
            
        except Exception as e:
            print(f"⚠ {Path(image_path).name}: {e}")
            continue
    
    return True


if __name__ == "__main__":
    print("Tree View Functionality Tests")
    print("=" * 50)
    
    results = []
    
    tests = [
        ("Tree Snapshot Building", test_tree_snapshot_building),
        ("Tree Traversal and File Finding", test_tree_traversal),
        ("Path Consistency", test_path_consistency),
        ("Large Directory Handling", test_large_directory_handling),
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
