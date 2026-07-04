"""PyFatFS互換のファイルシステムAPI実装。

XDF/HDF/HDS ディスクイメージを統一インターフェースで操作。
"""

import struct
from pathlib import Path
from typing import Optional, List, Dict, BinaryIO, Tuple
from datetime import datetime
from io import BytesIO

from .xdf_format import MediaProfile, BPBFields, MEDIA_PROFILES, MediaType
from .xdf_reader import XDFReader
from .xdf_fat import FATTable, DirectoryReader, DirectoryEntry, ATTR_DIRECTORY, ATTR_ARCHIVE
from .xdf_path import PathParser
from .xdf_hdf_hds import HDFHDSReader, PartitionInfo


class FileInfo:
    """ファイル/ディレクトリ情報。"""
    
    def __init__(self, name: str, is_dir: bool, size: int, modified: datetime):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.modified = modified
    
    def __repr__(self):
        type_str = "[DIR]" if self.is_dir else "[FILE]"
        return f"{type_str} {self.name} ({self.size} bytes)"


class XDFFile:
    """ファイルポインタ互換オブジェクト。"""
    
    def __init__(self, fs: 'XDFFileSystem', path: str, mode: str = 'rb'):
        """初期化。
        
        Args:
            fs: ファイルシステム
            path: ファイルパス
            mode: 'rb' (読み込み) または 'wb' (書き込み)
        """
        self.fs = fs
        self.path = path
        self.mode = mode
        self.buffer = BytesIO()
        self.closed = False
        
        if 'r' in mode:
            # 読み込みモード
            data = fs.read_file(path)
            self.buffer.write(data)
            self.buffer.seek(0)
    
    def read(self, size: int = -1) -> bytes:
        """読み込み。"""
        if 'w' in self.mode:
            raise IOError("not readable")
        return self.buffer.read(size)
    
    def write(self, data: bytes) -> int:
        """書き込み。"""
        if 'r' in self.mode:
            raise IOError("not writable")
        return self.buffer.write(data)
    
    def seek(self, offset: int, whence: int = 0) -> int:
        """シーク。"""
        return self.buffer.seek(offset, whence)
    
    def tell(self) -> int:
        """現在位置取得。"""
        return self.buffer.tell()
    
    def close(self):
        """クローズ。"""
        if 'w' in self.mode:
            # 書き込みモードの場合、ファイルに保存
            self.buffer.seek(0)
            data = self.buffer.read()
            self.fs.write_file(self.path, data)
        
        self.buffer.close()
        self.closed = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class XDFFileSystem:
    """XDF/HDF/HDS ファイルシステムAPI (PyFatFS互換)。"""
    
    def __init__(self, image_path: Path, partition: int = 0):
        """初期化。
        
        Args:
            image_path: ディスクイメージファイルパス
            partition: HDF/HDS ファイルの場合、マウントするパーティション番号（0 = 最初）
        """
        self.image_path = Path(image_path)
        self.partition_index = partition
        self.hdf_hds_reader: Optional[HDFHDSReader] = None
        self.partition_info: Optional[PartitionInfo] = None
        
        if not self.image_path.exists():
            raise FileNotFoundError(f"Image not found: {self.image_path}")
        
        # ディスクイメージを読み込み
        with open(self.image_path, 'rb') as f:
            full_disk_data = bytearray(f.read())
        
        # HDF/HDS パーティションテーブルを検出
        self.hdf_hds_reader = HDFHDSReader(self.image_path)
        
        # パーティション選択
        partition_offset = 0
        if self.hdf_hds_reader.is_valid():
            partitions = self.hdf_hds_reader.get_partitions()
            if partition >= len(partitions):
                raise ValueError(f"Partition {partition} not found. Available: {len(partitions)}")
            
            self.partition_info = partitions[partition]
            partition_offset = self.partition_info.byte_offset
        
        # パーティション内のデータを抽出
        if partition_offset > 0:
            # HDF/HDS パーティション
            partition_end = min(partition_offset + 10 * 1024 * 1024, len(full_disk_data))
            self.disk_data = full_disk_data[partition_offset:partition_end]
        else:
            # XDF や FDD
            self.disk_data = full_disk_data
        
        # メディアプロファイルと BPB を検出
        self.profile = None
        self.bpb = None
        
        if partition_offset > 0:
            # HDF/HDS パーティション: BPB は標準位置から直接読み込む
            self.bpb = self._read_bpb_from_partition_data(self.disk_data)
            
            if self.bpb is not None:
                # BPB から推定メディアプロファイルを決定
                self.profile = self._detect_profile_from_bpb(self.bpb)
        else:
            # XDF: 既存のロジックを使用
            with XDFReader(self.image_path) as reader:
                self.profile = reader.detect_media_type()
                self.bpb = reader.read_bpb()
        
        if self.profile is None:
            raise ValueError(f"Unknown media format: {self.image_path}")
        
        # BPB が見つからない場合はデフォルトを作成
        if self.bpb is None:
            self.bpb = FATTable.create_default_bpb(self.profile)
        
        # FAT テーブルとディレクトリリーダーを初期化
        self.fat_table = FATTable(self.disk_data, self.bpb, self.profile)
        self.dir_reader = DirectoryReader(self.fat_table.disk_data, self.fat_table, self.bpb)
    
    def _read_bpb_from_partition_data(self, disk_data: bytes) -> Optional[BPBFields]:
        """パーティション内のデータから BPB を読み込む。
        
        Args:
            disk_data: パーティション内のデータ
        
        Returns:
            BPBFields または None
        """
        if len(disk_data) < 32:
            return None
        
        try:
            # リトルエンディアン FAT BPB から読み込み
            bps = struct.unpack('<H', disk_data[0x0B:0x0D])[0]
            spc = disk_data[0x0D]
            rsvd = struct.unpack('<H', disk_data[0x0E:0x10])[0]
            fats = disk_data[0x10]
            root = struct.unpack('<H', disk_data[0x11:0x13])[0]
            tot16 = struct.unpack('<H', disk_data[0x13:0x15])[0]
            media = disk_data[0x15]
            fatsz = struct.unpack('<H', disk_data[0x16:0x18])[0]
            spt = struct.unpack('<H', disk_data[0x18:0x1A])[0] if len(disk_data) >= 0x1A else 0
            heads = struct.unpack('<H', disk_data[0x1A:0x1C])[0] if len(disk_data) >= 0x1C else 0
            
            tot32 = 0
            if len(disk_data) >= 0x24:
                tot32 = struct.unpack('<I', disk_data[0x20:0x24])[0]
            
            # 検証
            if bps not in (512, 1024, 2048, 4096):
                return None
            if spc == 0 or spc > 128 or (spc & (spc - 1)) != 0:
                return None
            if fats not in (1, 2):
                return None
            if rsvd == 0:
                return None
            
            total_sectors = tot16 if tot16 != 0 else tot32
            if total_sectors == 0:
                return None
            
            return BPBFields(
                bytes_per_sector=bps,
                sectors_per_cluster=spc,
                reserved_sectors=rsvd,
                fat_count=fats,
                root_entries=root,
                total_sectors_16=tot16,
                media_descriptor=media,
                sectors_per_fat=fatsz,
                sectors_per_track=spt,
                heads=heads,
                hidden_sectors=0,
                total_sectors_32=tot32,
            )
        except Exception:
            return None
    
    def _detect_profile_from_bpb(self, bpb: BPBFields) -> Optional[MediaProfile]:
        """BPB からメディアプロファイルを推定。
        
        Args:
            bpb: BIOS パラメータブロック
        
        Returns:
            MediaProfile または None
        """
        if not bpb:
            return None
        
        # まずは任意のプロファイルを使用（ハードディスク向け）
        # HDF/HDS はサイズが大きいため、メディアプロファイルは参考値
        return MediaProfile(
            name=f"HDF/HDS ({bpb.total_sectors_16 or bpb.total_sectors_32} sectors)",
            media_byte=bpb.media_descriptor,
            cylinders=0,
            sides=bpb.heads if bpb.heads > 0 else 1,
            sectors_per_track=bpb.sectors_per_track if bpb.sectors_per_track > 0 else 1,
            sector_size=bpb.bytes_per_sector,
            sector_scale=0,
            total_sectors=bpb.total_sectors_16 or bpb.total_sectors_32,
        )
    
    def get_partitions(self) -> List[PartitionInfo]:
        """HDF/HDS パーティション情報を取得。
        
        Returns:
            パーティション情報リスト
        """
        if self.hdf_hds_reader:
            return self.hdf_hds_reader.get_partitions()
        return []
    
    def save(self):
        """ディスクイメージに変更を保存。"""
        with open(self.image_path, 'wb') as f:
            f.write(bytes(self.disk_data))
    
    # ==================== 読み込み操作 ====================
    
    def _find_entry(self, path: str) -> Optional[tuple]:
        """ファイル/ディレクトリエントリを検索。
        
        Returns:
            (entry, parent_cluster) or None
        """
        parts = PathParser.split_path(path)
        if not parts:
            # ルートディレクトリ
            return (None, None)
        
        # ルートディレクトリから開始
        current_entries = self.dir_reader.read_root_directory()
        current_cluster = None
        
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            
            # ディレクトリ内でエントリを検索
            entry = self.dir_reader.find_entry_by_name(current_entries, part)
            
            if entry is None:
                return None
            
            if is_last:
                return (entry, current_cluster)
            
            # ディレクトリでなければエラー
            if not entry.is_directory:
                raise ValueError(f"Not a directory: {part}")
            
            # 次のディレクトリを読み込み
            current_cluster = entry.start_cluster
            current_entries = self.dir_reader.read_subdirectory(entry.start_cluster)
        
        return None
    
    def getinfo(self, path: str) -> FileInfo:
        """ファイル/ディレクトリ情報を取得。
        
        Args:
            path: ファイルパス
        
        Returns:
            FileInfo オブジェクト
        """
        from .xdf_fat import format_timestamp
        
        result = self._find_entry(path)
        if result is None:
            raise FileNotFoundError(f"Not found: {path}")
        
        entry, _ = result
        
        is_dir = entry.is_directory
        size = 0 if is_dir else entry.file_size
        
        try:
            timestamp_str = format_timestamp(entry.write_time, entry.write_date)
            modified = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError):
            # タイムスタンプが無効な場合は現在時刻を使用
            modified = datetime.now()
        
        return FileInfo(entry.full_name(), is_dir, size, modified)
    
    def listdir(self, path: str = '\\') -> List[str]:
        """ディレクトリをリスト。
        
        Args:
            path: ディレクトリパス
        
        Returns:
            ファイル名リスト
        """
        parts = PathParser.split_path(path)
        
        if not parts:
            # ルートディレクトリ
            entries = self.dir_reader.read_root_directory()
        else:
            result = self._find_entry(path)
            if result is None:
                raise FileNotFoundError(f"Not found: {path}")
            
            entry, _ = result
            
            if not entry.is_directory:
                raise ValueError(f"Not a directory: {path}")
            
            entries = self.dir_reader.read_subdirectory(entry.start_cluster)
        
        return [e.full_name() for e in entries]
    
    def read_file(self, path: str) -> bytes:
        """ファイルを読み込む。
        
        Args:
            path: ファイルパス
        
        Returns:
            ファイルデータ
        """
        result = self._find_entry(path)
        if result is None:
            raise FileNotFoundError(f"Not found: {path}")
        
        entry, _ = result
        
        if entry.is_directory:
            raise ValueError(f"Is a directory: {path}")
        
        if entry.file_size == 0:
            return b''
        
        # クラスタチェーンをたどる
        chain = self.fat_table.follow_cluster_chain(entry.start_cluster)
        
        # クラスタデータを連結
        data = b''
        for cluster in chain:
            data += self.fat_table.read_cluster_data(cluster)
        
        # ファイルサイズ分のみを返す
        return data[:entry.file_size]
    
    def open(self, path: str, mode: str = 'rb') -> XDFFile:
        """ファイルを開く。
        
        Args:
            path: ファイルパス
            mode: 'rb' (読み込み) または 'wb' (書き込み)
        
        Returns:
            ファイルポインタ互換オブジェクト
        """
        if mode == 'rb':
            return XDFFile(self, path, mode)
        elif mode == 'wb':
            return XDFFile(self, path, mode)
        else:
            raise ValueError(f"Unsupported mode: {mode}")
    
    # ==================== 書き込み操作 ====================
    
    def write_file(self, path: str, data: bytes) -> None:
        """ファイルを書き込む（新規作成または上書き）。
        
        Args:
            path: ファイルパス
            data: 書き込むデータ
        """
        parts = PathParser.split_path(path)
        if not parts:
            raise ValueError("Cannot write to root directory")
        
        filename = parts[-1]
        
        # 親ディレクトリを取得
        if len(parts) == 1:
            # ルートディレクトリ配下
            parent_cluster = None
            parent_entries = self.dir_reader.read_root_directory()
        else:
            parent_path = '\\' + '\\'.join(parts[:-1])
            result = self._find_entry(parent_path)
            
            if result is None:
                raise FileNotFoundError(f"Parent directory not found: {parent_path}")
            
            parent_entry, _ = result
            
            if not parent_entry.is_directory:
                raise ValueError(f"Not a directory: {parent_path}")
            
            parent_cluster = parent_entry.start_cluster
            parent_entries = self.dir_reader.read_subdirectory(parent_cluster)
        
        # 既存ファイルを確認
        existing_entry = self.dir_reader.find_entry_by_name(parent_entries, filename)
        
        # クラスタを割り当て
        if existing_entry is None:
            # 新規ファイル
            chain = self.fat_table.allocate_clusters_for_data(data)
        else:
            # 既存ファイルを上書き
            chain = self.fat_table.allocate_clusters_for_data(
                data,
                existing_chain=[existing_entry.start_cluster] if existing_entry.start_cluster > 0 else None
            )
        
        # クラスタにデータを書き込み
        self.fat_table.write_data_to_clusters(data, chain)
        
        # ディレクトリエントリを作成/更新
        now = datetime.now()
        dos_time = ((now.hour & 0x1F) << 11) | ((now.minute & 0x3F) << 5) | ((now.second >> 1) & 0x1F)
        dos_date = (((now.year - 1980) & 0x7F) << 9) | ((now.month & 0x0F) << 5) | (now.day & 0x1F)
        
        # ファイル名と拡張子を分割
        if '.' in filename:
            name_parts = filename.rsplit('.', 1)
            short_name = name_parts[0][:8]
            ext = name_parts[1][:3]
        else:
            short_name = filename[:8]
            ext = ''
        
        entry = DirectoryEntry(
            filename=short_name,
            extension=ext,
            attributes=ATTR_ARCHIVE,
            created_time=dos_time,
            created_date=dos_date,
            accessed_date=dos_date,
            start_cluster=chain[0] if chain else 0,
            file_size=len(data),
            write_time=dos_time,
            write_date=dos_date,
        )
        
        if existing_entry is None:
            # 新規エントリを追加
            self.dir_reader.add_directory_entry(parent_cluster, entry)
        else:
            # 既存エントリを更新
            # (実装簡略化のため削除後に再追加)
            self.dir_reader.remove_directory_entry(parent_cluster, filename)
            self.dir_reader.add_directory_entry(parent_cluster, entry)
    
    def makedirs(self, path: str) -> None:
        """ディレクトリを作成（親ディレクトリも作成）。
        
        Args:
            path: ディレクトリパス
        """
        parts = PathParser.split_path(path)
        if not parts:
            raise ValueError("Cannot create root directory")
        
        # 親ディレクトリから順に作成
        for i in range(len(parts)):
            current_path = '\\' + '\\'.join(parts[:i+1])
            
            try:
                self.getinfo(current_path)
                # 既に存在
                continue
            except FileNotFoundError:
                # 作成が必要
                self._mkdir_single(current_path)
    
    def _mkdir_single(self, path: str) -> None:
        """単一ディレクトリを作成。
        
        Args:
            path: ディレクトリパス
        """
        parts = PathParser.split_path(path)
        dirname = parts[-1]
        
        # 親ディレクトリを取得
        if len(parts) == 1:
            parent_cluster = None
            parent_entries = self.dir_reader.read_root_directory()
        else:
            parent_path = '\\' + '\\'.join(parts[:-1])
            result = self._find_entry(parent_path)
            
            if result is None:
                raise FileNotFoundError(f"Parent directory not found: {parent_path}")
            
            parent_entry, _ = result
            
            if not parent_entry.is_directory:
                raise ValueError(f"Not a directory: {parent_path}")
            
            parent_cluster = parent_entry.start_cluster
            parent_entries = self.dir_reader.read_subdirectory(parent_cluster)
        
        # 既に存在するか確認
        if self.dir_reader.find_entry_by_name(parent_entries, dirname) is not None:
            raise FileExistsError(f"Directory already exists: {path}")
        
        # ディレクトリ用クラスタを割り当て
        dir_cluster = self.fat_table.find_free_cluster()
        if dir_cluster is None:
            raise ValueError("No free clusters for directory")
        
        # FAT を更新
        self.fat_table.write_fat_entry(dir_cluster, self.fat_table.fat_tail_code)
        
        # ディレクトリクラスタを初期化
        dir_data = bytearray(self.fat_table.bpb.bytes_per_sector * self.fat_table.bpb.sectors_per_cluster)
        self.fat_table.write_cluster_data(dir_cluster, bytes(dir_data))
        
        # ディレクトリエントリを作成
        now = datetime.now()
        dos_time = ((now.hour & 0x1F) << 11) | ((now.minute & 0x3F) << 5) | ((now.second >> 1) & 0x1F)
        dos_date = (((now.year - 1980) & 0x7F) << 9) | ((now.month & 0x0F) << 5) | (now.day & 0x1F)
        
        entry = DirectoryEntry(
            filename=dirname[:8],
            extension='',
            attributes=ATTR_DIRECTORY,
            created_time=dos_time,
            created_date=dos_date,
            accessed_date=dos_date,
            start_cluster=dir_cluster,
            file_size=0,
            write_time=dos_time,
            write_date=dos_date,
        )
        
        self.dir_reader.add_directory_entry(parent_cluster, entry)
    
    def remove(self, path: str) -> None:
        """ファイルを削除。
        
        Args:
            path: ファイルパス
        """
        result = self._find_entry(path)
        if result is None:
            raise FileNotFoundError(f"Not found: {path}")
        
        entry, parent_cluster = result
        
        if entry.is_directory:
            raise ValueError(f"Is a directory: {path}")
        
        # クラスタチェーンを解放
        if entry.start_cluster > 0:
            chain = self.fat_table.follow_cluster_chain(entry.start_cluster)
            for cluster in chain:
                self.fat_table.write_fat_entry(cluster, 0)
        
        # ディレクトリエントリを削除
        self.dir_reader.remove_directory_entry(parent_cluster, entry.full_name())
    
    def removetree(self, path: str) -> None:
        """ディレクトリを再帰的に削除。
        
        Args:
            path: ディレクトリパス
        """
        result = self._find_entry(path)
        if result is None:
            raise FileNotFoundError(f"Not found: {path}")
        
        entry, parent_cluster = result
        
        if not entry.is_directory:
            raise ValueError(f"Not a directory: {path}")
        
        # ディレクトリ内のエントリを列挙
        try:
            entries = self.dir_reader.read_subdirectory(entry.start_cluster)
        except ValueError:
            entries = []
        
        # 各エントリを削除
        for sub_entry in entries:
            sub_path = path.rstrip('\\') + '\\' + sub_entry.full_name()
            
            if sub_entry.is_directory:
                self.removetree(sub_path)
            else:
                self.remove(sub_path)
        
        # ディレクトリクラスタを解放
        if entry.start_cluster > 0:
            chain = self.fat_table.follow_cluster_chain(entry.start_cluster)
            for cluster in chain:
                self.fat_table.write_fat_entry(cluster, 0)
        
        # ディレクトリエントリを削除
        self.dir_reader.remove_directory_entry(parent_cluster, entry.full_name())
    
    def flush(self) -> None:
        """メモリ内の変更をディスク ファイルに保存。"""
        try:
            if self.partition_info is not None:
                # HDF/HDS パーティション: パーティション領域のデータを保存
                with open(self.image_path, 'r+b') as f:
                    # パーティションのデータをファイルに書き込み
                    f.seek(self.partition_info.byte_offset)
                    f.write(self.disk_data)
                    f.flush()
            else:
                # XDF: ファイル全体を保存
                with open(self.image_path, 'wb') as f:
                    f.write(self.disk_data)
        except IOError as e:
            raise IOError(f"Failed to flush changes to {self.image_path}: {e}")
    
    def close(self) -> None:
        """ファイルシステムをクローズ（変更を保存）。"""
        self.flush()
