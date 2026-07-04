#!/usr/bin/env python3
"""XDF CLI - X68000 Disk Format command-line tool.

CLI tool to read, manipulate, and inspect X68000 XDF (floppy disk images).
Based on XEiJ source code analysis (FDMedia.java, FDC.java, HFS.java).
"""

import sys
import json
from pathlib import Path
from typing import Optional

from xdf_reader import XDFReader
from xdf_format import MEDIA_PROFILES
from xdf_fat import FATTable, DirectoryReader, format_timestamp
from xdf_path import PathParser, WildcardMatcher


def cmd_info(args) -> int:
    """Display information about an XDF file.
    
    Usage: xdf_cli.py info <xdf_file>
    """
    if not args.file:
        print("Usage: xdf_cli.py info <xdf_file>", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    try:
        with XDFReader(xdf_path) as reader:
            info = reader.info()
            
            print(f"File: {info['file_path']}")
            print(f"Size: {info['file_size']:,} bytes ({info['file_size_kb']} KB)")
            
            if 'media_type' in info:
                print(f"\nMedia Type: {info['media_type']}")
                print(f"Media Byte: {info['media_byte']}")
                print(f"Cylinders: {info['cylinders']}")
                print(f"Sides: {info['sides']}")
                print(f"Sectors/Track: {info['sectors_per_track']}")
                print(f"Sector Size: {info['sector_size']} bytes")
                print(f"Total Sectors: {info['total_sectors']}")
            else:
                print("\nWarning: Unknown media type (not a standard X68000 XDF file)")
            
            if 'bpb' in info:
                bpb = info['bpb']
                print(f"\nBIOS Parameter Block:")
                print(f"  Bytes/Sector: {bpb['bytes_per_sector']}")
                print(f"  Sectors/Cluster: {bpb['sectors_per_cluster']}")
                print(f"  Reserved Sectors: {bpb['reserved_sectors']}")
                print(f"  FAT Count: {bpb['fat_count']}")
                print(f"  Root Entries: {bpb['root_entries']}")
                print(f"  Total Sectors: {bpb['total_sectors']}")
                print(f"  Media Descriptor: {bpb['media_descriptor']}")
                print(f"  Sectors/FAT: {bpb['sectors_per_fat']}")
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args) -> int:
    """List all media types and their specifications.
    
    Usage: xdf_cli.py list
    """
    print("X68000 XDF Media Types:")
    print("-" * 80)
    print(f"{'Name':<15} {'Size':<12} {'Cylinders':<12} {'Sides':<8} {'Sectors/Track':<15} {'Sector Size'}")
    print("-" * 80)
    
    for profile in sorted(MEDIA_PROFILES.values(), key=lambda p: p.total_sectors):
        print(
            f"{profile.name:<15} {profile.file_size:>10,} B  "
            f"{profile.cylinders:>10}  {profile.sides:>6}  "
            f"{profile.sectors_per_track:>13}  {profile.sector_size:>11}"
        )
    
    return 0


def cmd_dir(args) -> int:
    """List directory contents.
    
    Usage: xdf_cli.py dir <xdf_file> [path]
    
    Examples:
        xdf_cli.py dir test.xdf                    # List root directory
        xdf_cli.py dir test.xdf "\\BIN"            # List \\BIN directory
        xdf_cli.py dir test.xdf "\\BIN\\*.txt"     # List *.txt in \\BIN
    """
    if not args.file:
        print("Usage: xdf_cli.py dir <xdf_file> [path]", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    # デフォルトパスはルート
    dir_path = getattr(args, 'path', '\\') or '\\'
    
    try:
        with XDFReader(xdf_path) as reader:
            # ディスク全体を読み込み
            disk_data = reader._read_bytes(0, reader.file_size)
            
            # メディアタイプ検出
            profile = reader.detect_media_type()
            if not profile:
                print("Error: Unknown media type", file=sys.stderr)
                return 1
            
            # BPB 読み込み（失敗してもプロファイルから生成）
            bpb = reader.read_bpb()
            
            # FAT テーブルと DirectoryReader 初期化
            fat_table = FATTable(disk_data, bpb, profile)
            dir_reader = DirectoryReader(disk_data, fat_table, fat_table.bpb)
            
            # ディレクトリ読み込み
            if dir_path.upper() in ('\\', '/'):
                # ルートディレクトリ
                entries = dir_reader.read_root_directory()
            else:
                # サブディレクトリまたはパターン
                parts = PathParser.split_path(dir_path)
                current_entries = dir_reader.read_root_directory()
                
                # 最後の要素がワイルドカードか判定
                last_part = parts[-1]
                has_wildcard = '*' in last_part or '?' in last_part
                
                # ツリー走査
                if has_wildcard:
                    # ワイルドカード: 最後の1つ手前まで走査
                    traverse_parts = parts[:-1]
                else:
                    # ワイルドカードなし: 全て走査
                    traverse_parts = parts
                
                for part in traverse_parts:
                    entry = dir_reader.find_entry_by_name(current_entries, part)
                    if not entry:
                        print(f"Error: Not found: {part}", file=sys.stderr)
                        return 1
                    
                    if entry.is_directory:
                        # ディレクトリなら中身を読み込む
                        current_entries = dir_reader.read_subdirectory(entry.start_cluster)
                    else:
                        # ファイルを指定した場合
                        print(f"Error: {part} is a file", file=sys.stderr)
                        return 1
                
                # ワイルドカード検索または最後のエントリ処理
                if has_wildcard:
                    # ワイルドカード: パターンマッチングして全てのマッチを表示
                    entries = dir_reader.find_entries_by_pattern(current_entries, last_part)
                else:
                    # ワイルドカードなし: traverse_parts に全て含まれているので current_entries が答え
                    entries = current_entries
            
            # 出力
            if not entries:
                print("(empty directory)")
                return 0
            
            print(f"Directory: {dir_path}")
            print("-" * 100)
            print(f"{'Name':<20} {'Type':<10} {'Size':>12} {'Date':<19} {'Attributes':<10}")
            print("-" * 100)
            
            for entry in entries:
                entry_type = "[DIR]" if entry.is_directory else "[FILE]"
                size_str = "-" if entry.is_directory else f"{entry.file_size:,}"
                date_str = format_timestamp(entry.write_time, entry.write_date)
                
                # 属性フラグ
                attr_flags = ""
                if entry.is_hidden:
                    attr_flags += "H"
                if entry.attributes & 0x01:  # Read-only
                    attr_flags += "R"
                if entry.attributes & 0x80:  # Executable
                    attr_flags += "X"
                
                print(
                    f"{entry.full_name():<20} {entry_type:<10} {size_str:>12} "
                    f"{date_str:<19} {attr_flags:<10}"
                )
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_ls(args) -> int:
    """Simple directory listing (short format).
    
    Usage: xdf_cli.py ls <xdf_file> [path]
    """
    if not args.file:
        print("Usage: xdf_cli.py ls <xdf_file> [path]", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    dir_path = getattr(args, 'path', '\\') or '\\'
    
    try:
        with XDFReader(xdf_path) as reader:
            disk_data = reader._read_bytes(0, reader.file_size)
            profile = reader.detect_media_type()
            bpb = reader.read_bpb()
            
            if not profile:
                print("Error: Invalid XDF file", file=sys.stderr)
                return 1
            
            fat_table = FATTable(disk_data, bpb, profile)
            dir_reader = DirectoryReader(disk_data, fat_table, fat_table.bpb)
            
            # ディレクトリ読み込み
            if dir_path.upper() in ('\\', '/'):
                entries = dir_reader.read_root_directory()
            else:
                # サブディレクトリまたはパターン
                parts = PathParser.split_path(dir_path)
                current_entries = dir_reader.read_root_directory()
                
                # 最後の要素がワイルドカードか判定
                last_part = parts[-1]
                has_wildcard = '*' in last_part or '?' in last_part
                
                # ツリー走査
                if has_wildcard:
                    # ワイルドカード: 最後の1つ手前まで走査
                    traverse_parts = parts[:-1]
                else:
                    # ワイルドカードなし: 全て走査
                    traverse_parts = parts
                
                for part in traverse_parts:
                    entry = dir_reader.find_entry_by_name(current_entries, part)
                    if not entry:
                        print(f"Error: Not found: {part}", file=sys.stderr)
                        return 1
                    
                    if entry.is_directory:
                        current_entries = dir_reader.read_subdirectory(entry.start_cluster)
                    else:
                        print(f"Error: {part} is a file", file=sys.stderr)
                        return 1
                
                # ワイルドカード検索または最後のエントリ処理
                if has_wildcard:
                    # ワイルドカード: パターンマッチングして全てのマッチを表示
                    entries = dir_reader.find_entries_by_pattern(current_entries, last_part)
                else:
                    # ワイルドカードなし: traverse_parts に全て含まれているので current_entries が答え
                    entries = current_entries
            
            # 短い形式で出力
            for entry in entries:
                prefix = "[D]" if entry.is_directory else "   "
                print(f"{prefix} {entry.full_name()}")
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_cat(args) -> int:
    """Display file contents.
    
    Usage: xdf_cli.py cat <xdf_file> <file_path>
    
    Examples:
        xdf_cli.py cat test.xdf \\README.TXT
        xdf_cli.py cat test.xdf \\BIN\\TEST.X
    """
    if not args.file or not args.path:
        print("Usage: xdf_cli.py cat <xdf_file> <file_path>", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    file_path = args.path
    
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    try:
        with XDFReader(xdf_path) as reader:
            disk_data = reader._read_bytes(0, reader.file_size)
            profile = reader.detect_media_type()
            bpb = reader.read_bpb()
            
            if not profile:
                print("Error: Invalid XDF file", file=sys.stderr)
                return 1
            
            fat_table = FATTable(disk_data, bpb, profile)
            dir_reader = DirectoryReader(disk_data, fat_table, fat_table.bpb)
            
            # ファイルを検索
            parts = PathParser.split_path(file_path)
            current_entries = dir_reader.read_root_directory()
            
            # ツリー走査
            for i, part in enumerate(parts[:-1]):
                entry = dir_reader.find_entry_by_name(current_entries, part)
                if not entry or not entry.is_directory:
                    print(f"Error: Directory not found: {part}", file=sys.stderr)
                    return 1
                
                current_entries = dir_reader.read_subdirectory(entry.start_cluster)
            
            # ファイルを見つける
            filename = parts[-1]
            entry = dir_reader.find_entry_by_name(current_entries, filename)
            
            if not entry:
                print(f"Error: File not found: {filename}", file=sys.stderr)
                return 1
            
            if entry.is_directory:
                print(f"Error: {filename} is a directory", file=sys.stderr)
                return 1
            
            # ファイルデータを読み込み
            chain = fat_table.follow_cluster_chain(entry.start_cluster)
            data = b''
            
            for cluster in chain:
                data += fat_table.read_cluster_data(cluster)
            
            # ファイルサイズに切り詰め
            data = data[:entry.file_size]
            
            # 出力
            try:
                print(data.decode('utf-8', errors='replace'), end='')
            except:
                # バイナリファイルの場合は HEX ダンプ
                print("(Binary file - hex dump):")
                for offset in range(0, len(data), 16):
                    hex_part = ' '.join(f'{b:02X}' for b in data[offset:offset+16])
                    ascii_part = ''.join(
                        chr(b) if 32 <= b < 127 else '.' 
                        for b in data[offset:offset+16]
                    )
                    print(f"{offset:04X}  {hex_part:<48}  {ascii_part}")
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_dump_sector(args) -> int:
    """Dump a sector in hex.
    
    Usage: xdf_cli.py dump-sector <xdf_file> <cylinder> <head> <sector>
    """
    if not args.file or args.cylinder is None or args.head is None or args.sector is None:
        print("Usage: xdf_cli.py dump-sector <xdf_file> <cylinder> <head> <sector>", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    try:
        with XDFReader(xdf_path) as reader:
            profile = reader.detect_media_type()
            if not profile:
                print("Error: Unknown media type", file=sys.stderr)
                return 1
            
            data = reader.read_sector(args.cylinder, args.head, args.sector, profile)
            if data is None:
                print(f"Error: Sector not found (C:{args.cylinder} H:{args.head} S:{args.sector})", file=sys.stderr)
                return 1
            
            print(f"Sector C:{args.cylinder} H:{args.head} S:{args.sector} ({profile.sector_size} bytes)")
            print("-" * 80)
            
            # Hex dump
            for offset in range(0, len(data), 16):
                hex_part = ' '.join(f'{b:02X}' for b in data[offset:offset+16])
                ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[offset:offset+16])
                print(f"{offset:04X}  {hex_part:<48}  {ascii_part}")
            
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_json(args) -> int:
    """Output file information as JSON.
    
    Usage: xdf_cli.py json <xdf_file>
    """
    if not args.file:
        print("Usage: xdf_cli.py json <xdf_file>", file=sys.stderr)
        return 1
    
    xdf_path = Path(args.file)
    if not xdf_path.exists():
        print(f"Error: File not found: {xdf_path}", file=sys.stderr)
        return 1
    
    try:
        with XDFReader(xdf_path) as reader:
            info = reader.info()
            print(json.dumps(info, indent=2))
            return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="XDF CLI - X68000 Disk Format tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:
  xdf_cli.py info test.xdf
  xdf_cli.py list
  xdf_cli.py dir test.xdf                 # List root directory
  xdf_cli.py dir test.xdf \BIN            # List \BIN directory
  xdf_cli.py ls test.xdf \BIN             # Short format listing
  xdf_cli.py cat test.xdf \README.TXT     # Display file contents
  xdf_cli.py dump-sector test.xdf 0 0 1
  xdf_cli.py json test.xdf
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # info command
    info_parser = subparsers.add_parser('info', help='Display XDF file information')
    info_parser.add_argument('file', help='XDF file path')
    info_parser.set_defaults(func=cmd_info)
    
    # list command
    list_parser = subparsers.add_parser('list', help='List media types')
    list_parser.set_defaults(func=cmd_list)
    
    # dir command
    dir_parser = subparsers.add_parser('dir', help='List directory contents')
    dir_parser.add_argument('file', help='XDF file path')
    dir_parser.add_argument('path', nargs='?', default='\\', help='Directory path (default: \\)')
    dir_parser.set_defaults(func=cmd_dir)
    
    # ls command
    ls_parser = subparsers.add_parser('ls', help='List directory (short format)')
    ls_parser.add_argument('file', help='XDF file path')
    ls_parser.add_argument('path', nargs='?', default='\\', help='Directory path (default: \\)')
    ls_parser.set_defaults(func=cmd_ls)
    
    # cat command
    cat_parser = subparsers.add_parser('cat', help='Display file contents')
    cat_parser.add_argument('file', help='XDF file path')
    cat_parser.add_argument('path', help='File path in XDF')
    cat_parser.set_defaults(func=cmd_cat)
    
    # dump-sector command
    dump_parser = subparsers.add_parser('dump-sector', help='Dump sector in hex')
    dump_parser.add_argument('file', help='XDF file path')
    dump_parser.add_argument('cylinder', type=int, help='Cylinder number')
    dump_parser.add_argument('head', type=int, help='Head/side number')
    dump_parser.add_argument('sector', type=int, help='Sector number')
    dump_parser.set_defaults(func=cmd_dump_sector)
    
    # json command
    json_parser = subparsers.add_parser('json', help='Output as JSON')
    json_parser.add_argument('file', help='XDF file path')
    json_parser.set_defaults(func=cmd_json)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
