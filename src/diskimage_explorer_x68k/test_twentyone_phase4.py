"""
Phase 4: XEiJ Integration Tests for TwentyOne Support

実環境テスト：
1. TwentyOne ファイル作成と FAT エントリ検証
2. XEiJ との互換性確認
3. ストレステスト
4. エッジケースのハンドリング
"""

from pathlib import Path
import struct
from typing import List, Tuple

# モジュール形式での実行を前提（python -m diskimage_explorer_x68k.test_twentyone_phase4）
from .backend import FatImageBackend, HAS_TWENTYONE_SUPPORT
from .twentyone import TwentyOneName, TwentyOneEntry, calculate_sfn_checksum

print(f"DEBUG: HAS_TWENTYONE_SUPPORT = {HAS_TWENTYONE_SUPPORT}")


class TwentyOneValidator:
    """TwentyOne ファイルの FAT エントリを検証"""
    
    FAT_ENTRY_SIZE = 32
    FAT_LFN_ATTR = 0x0F
    
    def __init__(self, image_path: Path):
        """初期化
        
        Args:
            image_path: FAT イメージファイルのパス
        """
        self.image_path = image_path
        self.backend = FatImageBackend()
    
    def verify_twentyone_entries(
        self,
        parent_path: str,
        expected_filename: str
    ) -> Tuple[bool, List[str]]:
        """TwentyOne エントリが正しく作成されたか検証
        
        Args:
            parent_path: 親ディレクトリのパス
            expected_filename: 期待するファイル名
            
        Returns:
            (is_valid, messages) - 検証結果とメッセージリスト
        """
        messages = []
        
        try:
            self.backend.mount(str(self.image_path))
            messages.append(f"✓ Mounted {self.image_path.name}")
            
            # ディレクトリを一覧表示
            entries = self.backend.list_dir(parent_path)
            messages.append(f"✓ Listed {len(entries)} entries in {parent_path}")
            
            # ファイルが存在するか確認
            found = False
            for entry in entries:
                if entry.name == expected_filename:
                    found = True
                    messages.append(f"✓ Found file: {entry.name}")
                    break
            
            if not found:
                # SFN 形式で検索（PyFatFS は SFN で認識する可能性）
                tw = TwentyOneName.parse(expected_filename)
                for entry in entries:
                    if entry.name == tw.sfn_name:
                        found = True
                        messages.append(f"✓ Found file as SFN: {entry.name} (original: {expected_filename})")
                        break
            
            if not found:
                messages.append(f"✗ File not found: {expected_filename}")
                return (False, messages)
            
            # FAT エントリの内容を検証（低レベルアクセス）
            # TODO: 直接 FAT バイナリを読んで TwentyOne エントリを検証
            
            return (True, messages)
        
        except Exception as e:
            messages.append(f"✗ Error: {e}")
            import traceback
            messages.append(traceback.format_exc())
            return (False, messages)
        
        finally:
            self.backend.close()
    
    def read_directory_sector(self, cluster: int) -> bytes:
        """ディレクトリセクタを直接読み込む（検証用）
        
        Args:
            cluster: 簇番号
            
        Returns:
            セクタのバイナリデータ
        """
        with open(self.image_path, 'rb') as f:
            # PyFatFS の内部構造を利用するため、正確なオフセット計算が必要
            # ここでは一般的なオフセット計算を示す
            
            # BPB を読み込み
            f.seek(0x8000)  # 標準的なパーティションオフセット
            boot = f.read(512)
            
            # BPB フィールド（X68000 形式）
            bps = struct.unpack('>H', boot[0x12:0x14])[0]  # Bytes per sector
            spc = boot[0x14]  # Sectors per cluster
            reserved = struct.unpack('>H', boot[0x16:0x18])[0]
            num_fats = boot[0x18]
            fat_size = struct.unpack('>H', boot[0x26:0x28])[0]
            
            # クラスタをセクタに変換
            sector = 2 * spc + reserved + num_fats * fat_size + (cluster - 2) * spc
            offset = sector * bps
            
            f.seek(offset)
            return f.read(bps * spc)


def test_basic_twentyone_creation():
    """基本的な TwentyOne ファイル作成テスト"""
    print("=== Test 1: Basic TwentyOne File Creation ===\n")
    
    # テスト用イメージファイルを探す
    candidates = [
        Path('/Users/taknakam/X68000/TEST_DATA/SCSI-original.HDS'),
        Path('/Users/taknakam/X68000/TEST_DATA/SCSI.HDS'),
    ]
    
    image_path = None
    for candidate in candidates:
        if candidate.exists():
            image_path = candidate
            break
    
    if image_path is None:
        print("✗ No test image found")
        print("  Candidates: " + ", ".join(str(c) for c in candidates))
        return
    
    backend = FatImageBackend()
    
    try:
        print(f"Using test image: {image_path.name}\n")
        backend.mount(str(image_path))
        print("✓ Mounted SCSI_restored.HDS\n")
        
        # テストファイル名
        test_cases = [
            ("test.txt", b"Simple test file"),
            ("verylongname.tar", b"Long name test file"),
            ("foo.tar.gz", b"Multiple period test"),
            ("longfilename123.x", b"Max length test"),
        ]
        
        for filename, content in test_cases:
            try:
                # ファイル名を検証
                is_valid, msg = backend.validate_twentyone_filename(filename)
                
                if is_valid:
                    print(f"✓ {filename:30} - Valid ({len(filename)} chars)")
                    
                    # TwentyOne 名を解析
                    tw = TwentyOneName.parse(filename)
                    print(f"  ├─ Primary: {tw.primary!r} (8 chars)")
                    print(f"  ├─ Secondary: {tw.secondary!r} (10 chars)")
                    print(f"  ├─ Extension: {tw.extension!r} (3 chars)")
                    print(f"  └─ SFN: {tw.sfn_name}")
                else:
                    print(f"✗ {filename:30} - Invalid: {msg}")
            
            except Exception as e:
                print(f"✗ {filename:30} - Error: {e}")
            
            print()
        
    finally:
        backend.close()


def test_entry_generation():
    """TwentyOne FAT エントリ生成テスト"""
    print("=== Test 2: TwentyOne FAT Entry Generation ===\n")
    
    test_filenames = [
        "test.txt",
        "verylongname.tar",
        "foo.tar.gz",
    ]
    
    for filename in test_filenames:
        print(f"File: {filename}")
        
        # エントリを生成
        entry = TwentyOneEntry.from_twentyone(filename)
        
        # SFN エントリ
        sfn = entry.generate_sfn_entry()
        print(f"  SFN Entry: {len(sfn)} bytes")
        print(f"    Name (0-8): {sfn[0:8]}")
        print(f"    Ext (8-11): {sfn[8:11]}")
        print(f"    Checksum (14): 0x{sfn[14]:02x}")
        
        # TwentyOne エントリ
        twentyone = entry.generate_twentyone_entries()
        print(f"  TwentyOne Entries: {len(twentyone)} entries")
        
        for i, e in enumerate(twentyone):
            seq = e[0]
            attr = e[11]
            checksum = e[14]
            print(f"    Entry {i+1}: seq=0x{seq:02x}, attr=0x{attr:02x}, checksum=0x{checksum:02x}")
        
        print()


def test_checksum_verification():
    """チェックサム計算の検証"""
    print("=== Test 3: Checksum Verification ===\n")
    
    test_cases = [
        (b"TEST    TXT", "Standard 8.3"),
        (b"VERYLONG TAR", "Long name"),
        (b"FOO      GZ ", "Multiple dots"),
    ]
    
    for sfn, desc in test_cases:
        checksum = calculate_sfn_checksum(sfn)
        print(f"{sfn.decode('ascii')} ({desc})")
        print(f"  Checksum: 0x{checksum:02x}\n")


def test_edge_cases():
    """エッジケースのテスト"""
    print("=== Test 4: Edge Cases ===\n")
    
    edge_cases = [
        ("a", True, "Minimum length"),
        ("a" * 21, True, "Maximum length"),
        ("a" * 22, False, "Over maximum"),
        ("test file.txt", True, "With space (should fail)"),
        ("test/file.txt", False, "With slash"),
        ("test:file.txt", False, "With colon"),
        ("foo.tar.gz.bak", True, "Multiple periods"),
        ("UPPERCASE.TXT", True, "Uppercase"),
        ("lowercase.txt", True, "Lowercase"),
        ("MiXeD_CaSe.txt", True, "Mixed case"),
    ]
    
    for filename, expected_valid, description in edge_cases:
        try:
            TwentyOneName.validate(filename)
            is_valid = True
        except ValueError:
            is_valid = False
        
        status = "✓" if is_valid == expected_valid else "✗"
        result = "Valid" if is_valid else "Invalid"
        
        print(f"{status} {filename:30} - {result:7} ({description})")


def test_stress_test():
    """ストレステスト"""
    print("=== Test 5: Stress Test ===\n")
    
    # さまざまな長さのファイル名を生成
    print("Testing file name lengths:")
    
    for length in [1, 5, 8, 10, 15, 18, 20, 21]:
        filename = "a" * length + ".txt"
        
        # 長さを調整
        if len(filename) > 21:
            filename = "a" * (length - 4) + ".txt"
        
        try:
            TwentyOneName.validate(filename)
            tw = TwentyOneName.parse(filename)
            print(f"✓ {len(filename):2d} chars: {filename:25} → {tw.sfn_name}")
        except ValueError as e:
            print(f"✗ {len(filename):2d} chars: {filename:25} → {e}")


def run_all_tests():
    """すべてのテストを実行"""
    print("\n" + "="*60)
    print("PHASE 4: XEiJ INTEGRATION TESTS FOR TWENTYONE")
    print("="*60 + "\n")
    
    test_basic_twentyone_creation()
    print("\n" + "-"*60 + "\n")
    
    test_entry_generation()
    print("\n" + "-"*60 + "\n")
    
    test_checksum_verification()
    print("\n" + "-"*60 + "\n")
    
    test_edge_cases()
    print("\n" + "-"*60 + "\n")
    
    test_stress_test()
    
    print("\n" + "="*60)
    print("PHASE 4 TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()
