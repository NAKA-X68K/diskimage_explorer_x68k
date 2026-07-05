"""
FAT Direct Editor for TwentyOne Support

FAT ディレクトリセクタを直接編集して TwentyOne エントリを生成・書き込みする
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Tuple, BinaryIO
import struct
import io

from .twentyone import (
    TwentyOneName,
    TwentyOneEntry,
    FAT_ENTRY_SIZE,
    FAT_DIRENT_FREE,
)


@dataclass
class DirectoryEntry:
    """FAT ディレクトリエントリの情報"""
    
    cluster: int        # 簇番号
    entry_idx: int      # 簇内のエントリインデックス（0-15）
    data: bytes         # 32バイトのエントリデータ
    
    @property
    def offset_in_cluster(self) -> int:
        """簇内のバイトオフセット"""
        return self.entry_idx * FAT_ENTRY_SIZE
    
    def is_free(self) -> bool:
        """フリーエントリかチェック"""
        return self.data[0] == FAT_DIRENT_FREE
    
    def is_empty(self) -> bool:
        """未使用エントリかチェック（0x00）"""
        return self.data[0] == 0x00
    
    def is_lfn(self) -> bool:
        """LFN エントリかチェック"""
        return self.data[11] == 0x0F
    
    def __str__(self) -> str:
        return f"DirectoryEntry(cluster={self.cluster}, idx={self.entry_idx}, free={self.is_free()})"


class DirectoryEditor:
    """FAT ディレクトリセクタを直接操作"""
    
    def __init__(
        self,
        fat_fs,  # PyFatBytesIOFS インスタンス
        bytes_per_cluster: int = 1024
    ):
        """初期化
        
        Args:
            fat_fs: PyFatBytesIOFS インスタンス（マウント済み）
            bytes_per_cluster: 1クラスタのバイト数（通常 512 または 1024）
        """
        self.fat_fs = fat_fs
        self.bytes_per_cluster = bytes_per_cluster
        self.entries_per_cluster = bytes_per_cluster // FAT_ENTRY_SIZE  # 32 or 16
    
    def read_directory_cluster(self, cluster: int) -> bytes:
        """ディレクトリクラスタを読み込む
        
        Args:
            cluster: 簇番号
            
        Returns:
            クラスタのバイナリデータ
        """
        # PyFatFS の内部構造を利用して直接読み込む
        try:
            pyfat = getattr(self.fat_fs, 'fs', None)
            f = getattr(pyfat, '_PyFat__fp', None)
            if pyfat is None or f is None:
                return None

            bytes_per_sector = int(pyfat.bpb_header['BPB_BytsPerSec'])

            # FAT12/16 ROOT は固定領域
            if cluster == 0:
                root_addr = pyfat.root_dir_sector * bytes_per_sector
                root_size = pyfat.root_dir_sectors * bytes_per_sector
                f.seek(root_addr)
                return f.read(root_size)

            # 通常ディレクトリはクラスタ領域
            addr = pyfat.get_data_cluster_address(cluster)
            f.seek(addr)
            return f.read(pyfat.bytes_per_cluster)
        except Exception:
            pass

        return None
    
    def write_directory_cluster(self, cluster: int, data: bytes) -> bool:
        """ディレクトリクラスタに書き込む
        
        Args:
            cluster: 簇番号
            data: 書き込むバイナリデータ（クラスタサイズ）
            
        Returns:
            成功時 True
        """
        try:
            pyfat = getattr(self.fat_fs, 'fs', None)
            f = getattr(pyfat, '_PyFat__fp', None)
            if pyfat is None or f is None:
                return False

            bytes_per_sector = int(pyfat.bpb_header['BPB_BytsPerSec'])

            if cluster == 0:
                root_addr = pyfat.root_dir_sector * bytes_per_sector
                root_size = pyfat.root_dir_sectors * bytes_per_sector
                f.seek(root_addr)
                f.write(data[:root_size])
            else:
                addr = pyfat.get_data_cluster_address(cluster)
                f.seek(addr)
                f.write(data)

            return True
        except Exception:
            pass
        
        return False
    
    def find_free_entries(
        self,
        parent_cluster: int,
        count: int = 4
    ) -> List[DirectoryEntry]:
        """連続した空きエントリを検索
        
        Args:
            parent_cluster: 親ディレクトリの簇番号
            count: 必要なエントリ数（デフォルト: 4 = TwentyOne用）
            
        Returns:
            空きエントリのリスト、見つからなかった場合は空リスト
        """
        cluster_data = self.read_directory_cluster(parent_cluster)
        if cluster_data is None:
            return []
        
        free_entries = []
        
        total_entries = len(cluster_data) // FAT_ENTRY_SIZE
        for idx in range(total_entries):
            offset = idx * FAT_ENTRY_SIZE
            entry_data = cluster_data[offset:offset + FAT_ENTRY_SIZE]
            
            entry = DirectoryEntry(
                cluster=parent_cluster,
                entry_idx=idx,
                data=entry_data
            )
            
            # フリーまたは未使用エントリをカウント
            if entry.is_free() or entry.is_empty():
                free_entries.append(entry)
                if len(free_entries) == count:
                    return free_entries
            else:
                # 連続でない場合はリセット
                free_entries = []
        
        # 見つからなかった場合
        return []
    
    def write_entries(
        self,
        entries_to_write: List[Tuple[DirectoryEntry, bytes]]
    ) -> bool:
        """複数のエントリを書き込む
        
        Args:
            entries_to_write: [(DirectoryEntry, bytes), ...] のリスト
                            同一クラスタ内のエントリが想定される
            
        Returns:
            成功時 True
        """
        if not entries_to_write:
            return False
        
        # すべてのエントリが同じクラスタにあるかチェック
        first_cluster = entries_to_write[0][0].cluster
        if not all(entry[0].cluster == first_cluster for entry in entries_to_write):
            raise ValueError("All entries must be in the same cluster")
        
        # クラスタデータを読み込む
        cluster_data = self.read_directory_cluster(first_cluster)
        if cluster_data is None:
            return False
        
        # バイナリを更新
        cluster_data = bytearray(cluster_data)
        
        for entry, new_data in entries_to_write:
            offset = entry.offset_in_cluster
            cluster_data[offset:offset + FAT_ENTRY_SIZE] = new_data
        
        # クラスタに書き込む
        return self.write_directory_cluster(first_cluster, bytes(cluster_data))


class TwentyOneWriter:
    """TwentyOne ファイルを FAT に書き込む"""
    
    def __init__(self, fat_fs, bytes_per_cluster: int = 1024):
        """初期化
        
        Args:
            fat_fs: PyFatBytesIOFS インスタンス
            bytes_per_cluster: クラスタサイズ
        """
        self.fat_fs = fat_fs
        self.editor = DirectoryEditor(fat_fs, bytes_per_cluster)
    
    def write_file(
        self,
        parent_path: str,
        filename: str,
        file_data: bytes,
        create_time: int = 0,
        create_date: int = 0
    ) -> bool:
        """TwentyOne ファイルを書き込む
        
        Args:
            parent_path: 親ディレクトリのパス（例："/DIR1"）
            filename: ファイル名（最大21文字）
            file_data: ファイルのバイナリデータ
            create_time: 作成時刻（DOS形式）
            create_date: 作成日付（DOS形式）
            
        Returns:
            成功時 True
        """
        try:
            # TwentyOne 名を検証・解析
            TwentyOneName.validate(filename)

            twentyone_name = TwentyOneName.parse(filename)
            sfn_name = twentyone_name.sfn_name
            sfn_path = f"{parent_path.rstrip('/')}/{sfn_name}" if parent_path != '/' else f"/{sfn_name}"

            # まず SFN 名でファイルを作成
            with self.fat_fs.openbin(sfn_path, 'w') as f:
                f.write(file_data)

            # XEiJ 互換 TwentyOne 形式:
            # SFN エントリの 12..21 バイトに secondary(10) を埋め込む。
            parent_cluster = self._get_dir_cluster(parent_path)
            if parent_cluster is None:
                return True

            cluster_data = self.editor.read_directory_cluster(parent_cluster)
            if cluster_data is None:
                return True

            sfn_upper = sfn_name.upper()
            mutable = bytearray(cluster_data)
            total_entries = len(mutable) // FAT_ENTRY_SIZE

            for idx in range(total_entries):
                off = idx * FAT_ENTRY_SIZE
                entry = mutable[off:off + FAT_ENTRY_SIZE]
                if len(entry) < FAT_ENTRY_SIZE:
                    continue
                if entry[0] in (0x00, FAT_DIRENT_FREE):
                    continue
                if entry[11] == 0x0F:
                    continue

                name = bytes(entry[0:8]).decode('ascii', errors='ignore').rstrip()
                ext = bytes(entry[8:11]).decode('ascii', errors='ignore').rstrip()
                cur = f"{name}.{ext}" if ext else name
                if cur.upper() != sfn_upper:
                    continue

                secondary = twentyone_name.secondary.encode('ascii', errors='ignore')[:10].ljust(10, b' ')
                mutable[off + 12:off + 22] = secondary
                # XEiJ 側と揃えるため archive 属性を明示
                mutable[off + 11] = 0x20
                self.editor.write_directory_cluster(parent_cluster, bytes(mutable))
                break
            
            return True
        
        except Exception as e:
            print(f"Error writing TwentyOne file: {e}")
            return False
    
    def _get_dir_cluster(self, dir_path: str) -> Optional[int]:
        """ディレクトリの簇番号を取得
        
        Args:
            dir_path: ディレクトリパス
            
        Returns:
            簇番号、見つからない場合は None
        """
        try:
            pyfat = getattr(self.fat_fs, 'fs', None)
            if pyfat is None:
                return None

            if dir_path == '/':
                return 0

            rel = dir_path.strip('/')
            entry = pyfat.root_dir.get_entry(rel)
            return int(entry.get_cluster())
        except Exception:
            pass

        if dir_path == '/':
            return 0

        return None


def demo_twentyone_writer():
    """TwentyOneWriter のデモンストレーション"""
    print("=== TwentyOneWriter Demo ===\n")
    
    from .backend import FatImageBackend
    from pathlib import Path
    
    image_path = Path('/Users/taknakam/X68000/TEST_DATA/SCSI_restored.HDS')
    
    backend = FatImageBackend()
    
    try:
        backend.mount(str(image_path))
        print("✓ Mounted SCSI_restored.HDS\n")
        
        # ファイルシステムを取得
        if hasattr(backend, 'fs') and backend.fs:
            writer = TwentyOneWriter(backend.fs)
            
            # テストファイルを書き込む
            test_data = b"This is a test file for TwentyOne support."
            
            print("Attempting to write TwentyOne file...")
            result = writer.write_file(
                parent_path="/DIR1",
                filename="longfilename123456.x",
                file_data=test_data
            )
            
            if result:
                print("✓ TwentyOne file written successfully!")
            else:
                print("✗ Failed to write TwentyOne file")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        backend.close()


if __name__ == "__main__":
    demo_twentyone_writer()
