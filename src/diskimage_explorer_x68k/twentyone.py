"""
TwentyOne File Naming Support for X68000

TwentyOne は X68000 の Human68k 拡張で、以下をサポート：
- 最大 21 文字のファイル名（18 + 3 拡張子）
- 複数ピリオド対応（foo.tar.gz など）

ファイル名フォーマット：
  <primary 8> + <secondary 10> + <extension 3> = 21 文字
  
内部的には標準 FAT の SFN エントリ + TwentyOne エントリで実装

参考：http://retropc.net/x68000/software/disk/filename/twentyone/
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import struct


# TwentyOne 定数
TWENTYONE_PRIMARY_MAX = 8
TWENTYONE_SECONDARY_MAX = 10
TWENTYONE_BASE_MAX = TWENTYONE_PRIMARY_MAX + TWENTYONE_SECONDARY_MAX  # 18
TWENTYONE_EXT_MAX = 3
# Full filename length includes the dot between base and extension.
# 18(base) + 1(dot) + 3(ext) = 22
TWENTYONE_NAME_MAX = TWENTYONE_BASE_MAX + 1 + TWENTYONE_EXT_MAX  # 22

# Magic identifiers for TwentyOne
MAGIC_TWEN = b'Twen'  # 4 bytes
MAGIC_TY = b'ty'      # 2 bytes

# FAT directory entry constants
FAT_ENTRY_SIZE = 32
FAT_LFN_ATTR = 0x0F  # LFN エントリの属性値
FAT_SFN_ATTR_ARCHIVE = 0x20  # アーカイブ属性
FAT_DIRENT_FREE = 0xE5  # 削除済みエントリ

# Allowed characters for TwentyOne file names
VALID_FILENAME_CHARS = set(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '0123456789'
    '._-'
)

# Forbidden characters (these will cause errors on X68000)
FORBIDDEN_CHARS = set(' /\\:;,[]<>|?*"')


@dataclass
class TwentyOneName:
    """TwentyOne ファイル名の解析と生成"""
    
    primary: str      # 最初の 8 文字
    secondary: str    # 追加の 10 文字
    extension: str    # 拡張子（3 文字まで）
    
    def __post_init__(self):
        """バリデーション"""
        if len(self.primary) > TWENTYONE_PRIMARY_MAX:
            raise ValueError(f"Primary name too long: {len(self.primary)} > {TWENTYONE_PRIMARY_MAX}")
        if len(self.secondary) > TWENTYONE_SECONDARY_MAX:
            raise ValueError(f"Secondary name too long: {len(self.secondary)} > {TWENTYONE_SECONDARY_MAX}")
        if len(self.extension) > TWENTYONE_EXT_MAX:
            raise ValueError(f"Extension too long: {len(self.extension)} > {TWENTYONE_EXT_MAX}")
    
    @classmethod
    def parse(cls, filename: str) -> TwentyOneName:
        """ファイル名を解析して TwentyOneName を生成
        
        Args:
            filename: ファイル名（最大22文字: 18+1+3）
            
        Returns:
            TwentyOneName オブジェクト
            
        Raises:
            ValueError: ファイル名が無効な場合
        """
        # バリデーション
        cls.validate(filename)
        
        # 拡張子を分割（最後のピリオド以降が拡張子）
        if '.' in filename:
            last_dot_idx = filename.rfind('.')
            name_part = filename[:last_dot_idx]
            ext_part = filename[last_dot_idx + 1:]
        else:
            name_part = filename
            ext_part = ''
        
        # 拡張子が3文字を超える場合は全体を名前とみなす
        if len(ext_part) > TWENTYONE_EXT_MAX:
            name_part = filename
            ext_part = ''
        
        # 名前部分を primary + secondary に分割
        # 最初の8文字が primary、残りが secondary
        primary = name_part[:TWENTYONE_PRIMARY_MAX].ljust(TWENTYONE_PRIMARY_MAX)
        secondary = name_part[TWENTYONE_PRIMARY_MAX:TWENTYONE_PRIMARY_MAX + TWENTYONE_SECONDARY_MAX]
        
        # 拡張子を3文字にパディング
        ext = ext_part[:TWENTYONE_EXT_MAX].ljust(TWENTYONE_EXT_MAX)
        
        return cls(
            primary=primary,
            secondary=secondary,
            extension=ext
        )
    
    @classmethod
    def validate(cls, filename: str) -> bool:
        """ファイル名が有効かチェック
        
        Args:
            filename: チェックするファイル名
            
        Returns:
            有効な場合 True
            
        Raises:
            ValueError: 無効な場合、エラーメッセージを含む
        """
        if not filename:
            raise ValueError("Filename cannot be empty")
        
        if len(filename) > TWENTYONE_NAME_MAX:
            raise ValueError(f"Filename too long: {len(filename)} > {TWENTYONE_NAME_MAX}")
        
        # 禁止文字をチェック
        for char in filename:
            if char in FORBIDDEN_CHARS:
                raise ValueError(f"Forbidden character '{char}' in filename")
        
        return True
    
    def to_bytes(self) -> Tuple[bytes, bytes, bytes]:
        """TwentyOne パーツをバイト列に変換
        
        Returns:
            (primary_bytes, secondary_bytes, extension_bytes)
        """
        # 大文字に正規化
        primary = self.primary.upper()[:TWENTYONE_PRIMARY_MAX].ljust(TWENTYONE_PRIMARY_MAX)
        secondary = self.secondary.upper()[:TWENTYONE_SECONDARY_MAX]
        extension = self.extension.upper()[:TWENTYONE_EXT_MAX].ljust(TWENTYONE_EXT_MAX)
        
        return (
            primary.encode('ascii'),
            secondary.encode('ascii'),
            extension.encode('ascii')
        )
    
    def __str__(self) -> str:
        """ファイル名を文字列で返す"""
        name = self.primary + self.secondary
        if self.extension.strip():
            return f"{name}.{self.extension.strip()}"
        return name.rstrip()
    
    @property
    def full_name(self) -> str:
        """完全なファイル名を返す"""
        return str(self)
    
    @property
    def sfn_name(self) -> str:
        """SFN（8.3）形式の名前を返す"""
        return f"{self.primary.rstrip()}.{self.extension.rstrip()}"
    
    @property
    def name_display(self) -> str:
        """GUI表示用に分割を表示"""
        p = self.primary.rstrip()
        s = self.secondary.rstrip()
        e = self.extension.rstrip()
        return f"{p} + {s} | {e}" if e else f"{p} + {s}"


def calculate_sfn_checksum(sfn_entry: bytes) -> int:
    """SFN (8+3 = 11 bytes) のチェックサムを計算
    
    X68000 の FAT 実装で使用されるチェックサム計算アルゴリズム
    
    Args:
        sfn_entry: SFN エントリの先頭11バイト（8文字 + 3文字拡張子）
                   各バイトは大文字で ASCII であること
    
    Returns:
        チェックサム値（0-255の1バイト）
    """
    checksum = 0
    
    for byte_val in sfn_entry[:11]:
        # ローテーション右シフト（Rotate Right）
        checksum = ((checksum & 1) << 7) | ((checksum & 0xFE) >> 1)
        # バイト値を加算
        checksum = (checksum + byte_val) & 0xFF
    
    return checksum


@dataclass
class TwentyOneEntry:
    """TwentyOne FAT ディレクトリエントリの生成
    
    標準 SFN エントリ + TwentyOne 拡張エントリで構成
    """
    
    twentyone_name: TwentyOneName
    sfn_checksum: int
    create_time: int = 0  # DOS 形式のタイムスタンプ（デフォルト: 0）
    create_date: int = 0  # DOS 形式の日付
    access_date: int = 0
    write_time: int = 0
    write_date: int = 0
    start_cluster: int = 0  # ファイルの開始簇
    file_size: int = 0      # ファイルサイズ
    
    @classmethod
    def from_twentyone(
        cls,
        filename: str,
        create_time: int = 0,
        create_date: int = 0,
        start_cluster: int = 0,
        file_size: int = 0
    ) -> TwentyOneEntry:
        """ファイル名から TwentyOneEntry を生成
        
        Args:
            filename: 22文字以下のファイル名（18+1+3）
            create_time: 作成時刻（DOS形式、デフォルト: 0）
            create_date: 作成日付（DOS形式、デフォルト: 0）
            start_cluster: ファイルの開始簇
            file_size: ファイルサイズ
            
        Returns:
            TwentyOneEntry オブジェクト
        """
        twentyone_name = TwentyOneName.parse(filename)
        
        # SFN のチェックサムを計算
        sfn_bytes = twentyone_name.to_bytes()
        sfn_entry = sfn_bytes[0] + sfn_bytes[2]  # primary + extension
        sfn_checksum = calculate_sfn_checksum(sfn_entry)
        
        return cls(
            twentyone_name=twentyone_name,
            sfn_checksum=sfn_checksum,
            create_time=create_time,
            create_date=create_date,
            start_cluster=start_cluster,
            file_size=file_size
        )
    
    def generate_sfn_entry(self) -> bytes:
        """SFN（8.3）ディレクトリエントリを生成
        
        Returns:
            32バイトのディレクトリエントリ
        """
        entry = bytearray(32)
        
        primary, secondary, extension = self.twentyone_name.to_bytes()
        
        # 0-7: Primary name (8 bytes)
        entry[0:8] = primary
        
        # 8-10: Extension (3 bytes)
        entry[8:11] = extension
        
        # 11: Attributes (0x20 = Archive)
        entry[11] = FAT_SFN_ATTR_ARCHIVE
        
        # 12: Reserved (NT reserved)
        entry[12] = 0
        
        # 13: Creation time (deciseconds)
        entry[13] = 0
        
        # 14-15: Creation time (hours, minutes, seconds)
        entry[14:16] = struct.pack('<H', self.create_time)
        
        # 16-17: Creation date
        entry[16:18] = struct.pack('<H', self.create_date)
        
        # 18-19: Last access date
        entry[18:20] = struct.pack('<H', self.access_date)
        
        # 20-21: High word of first cluster (FAT32, usually 0 for FAT12/16)
        entry[20:22] = struct.pack('<H', 0)
        
        # 22-23: Write time
        entry[22:24] = struct.pack('<H', self.write_time)
        
        # 24-25: Write date
        entry[24:26] = struct.pack('<H', self.write_date)
        
        # 26-27: First cluster (low word)
        entry[26:28] = struct.pack('<H', self.start_cluster & 0xFFFF)
        
        # 28-31: File size
        entry[28:32] = struct.pack('<I', self.file_size)
        
        return bytes(entry)
    
    def generate_twentyone_entries(self) -> list[bytes]:
        """TwentyOne 拡張エントリを生成
        
        TwentyOne は secondary（10文字）と extension（3文字）を
        複数のエントリに分割して格納する
        
        Returns:
            32バイトエントリのリスト（3エントリ）
        """
        entries = []
        
        primary, secondary, extension = self.twentyone_name.to_bytes()
        
        # Entry 3: Magic ID エントリ（一番上）
        # シーケンス番号: 0x83 (bit 7=1で開始フラグ、bit 6-0=3)
        entry3 = bytearray(32)
        entry3[0] = 0x83  # Start flag + sequence 3
        entry3[1:5] = MAGIC_TWEN  # "Twen"
        entry3[5] = 0xFF  # Padding
        entry3[6:8] = MAGIC_TY  # "ty"
        entry3[8:14] = b'\xFF' * 6  # Padding
        entry3[11] = FAT_LFN_ATTR  # LFN attribute
        entry3[14] = self.sfn_checksum  # Checksum
        entry3[15:32] = b'\xFF' * 17  # Padding
        entries.append(bytes(entry3))
        
        # Entry 2: Secondary と Extension パート
        entry2 = bytearray(32)
        entry2[0] = 0x02  # Sequence 2
        # Secondary の後半10文字を分割格納
        entry2[1:11] = secondary  # 10 bytes
        entry2[11] = FAT_LFN_ATTR
        entry2[12:14] = b'\xFF' * 2  # Reserved
        entry2[14] = self.sfn_checksum
        entry2[15:27] = extension + b'\xFF' * 10  # Extension + padding
        entry2[27:32] = b'\xFF' * 5  # Reserved
        entries.append(bytes(entry2))
        
        # Entry 1: Secondary パート
        entry1 = bytearray(32)
        entry1[0] = 0x01  # Sequence 1
        entry1[1:11] = secondary  # 10 bytes
        entry1[11] = FAT_LFN_ATTR
        entry1[12:14] = b'\xFF' * 2  # Reserved
        entry1[14] = self.sfn_checksum
        entry1[15:32] = b'\xFF' * 17  # Padding
        entries.append(bytes(entry1))
        
        return entries
    
    def get_all_entries(self) -> list[bytes]:
        """SFN エントリと TwentyOne エントリをすべて取得
        
        Returns:
            ディレクトリエントリのリスト（4エントリ）
            [TwentyOne Entry 3, Entry 2, Entry 1, SFN Entry]
        """
        all_entries = []
        all_entries.extend(self.generate_twentyone_entries())
        all_entries.append(self.generate_sfn_entry())
        return all_entries


# テスト用ヘルパー関数
def test_twentyone_parsing():
    """TwentyOne ファイル名解析のテスト"""
    test_cases = [
        "test.txt",
        "verylongfilename.tar",  # 20文字（8+10+2）
        "foo.tar.gz",  # 11文字（3+4+2）
        "longfilename123456.x",  # 20文字（18+2）
    ]
    
    for filename in test_cases:
        try:
            tw = TwentyOneName.parse(filename)
            print(f"✓ {filename:40} → {tw.sfn_name:15} | {tw.name_display}")
        except ValueError as e:
            print(f"✗ {filename:40} → ERROR: {e}")


def test_checksum():
    """チェックサム計算のテスト"""
    # SFN "TEST    TXT" のチェックサムを計算
    sfn = b"TEST    TXT"
    checksum = calculate_sfn_checksum(sfn)
    print(f"Checksum for '{sfn.decode('ascii')}': 0x{checksum:02x}")


if __name__ == "__main__":
    print("=== TwentyOne File Naming Support ===\n")
    
    print("Testing file name parsing:")
    test_twentyone_parsing()
    
    print("\nTesting checksum calculation:")
    test_checksum()
    
    print("\nTesting entry generation:")
    entry = TwentyOneEntry.from_twentyone("verylongfilename.tar")
    sfn = entry.generate_sfn_entry()
    twentyone = entry.generate_twentyone_entries()
    
    print(f"SFN entry: {len(sfn)} bytes")
    print(f"TwentyOne entries: {len(twentyone)} entries × {len(twentyone[0])} bytes")
