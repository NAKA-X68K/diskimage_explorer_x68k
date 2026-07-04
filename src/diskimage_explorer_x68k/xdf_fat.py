"""FAT ファイルシステム操作（XEiJ 分析に基づく実装）。

X68000 の FAT12/FAT16 ファイルシステムを解析・操作するモジュール。
"""

import struct
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

from xdf_format import MediaProfile, BPBFields


# ディレクトリエントリの属性フラグ
ATTR_READONLY = 0x01      # 読み込み専用
ATTR_HIDDEN = 0x02        # 隠しファイル
ATTR_SYSTEM = 0x04        # システムファイル
ATTR_VOLUME = 0x08        # ボリューム名
ATTR_DIRECTORY = 0x10     # ディレクトリ
ATTR_ARCHIVE = 0x20       # アーカイブ/ファイル
ATTR_LINK = 0x40          # シンボリックリンク
ATTR_EXECUTABLE = 0x80    # 実行可能


@dataclass
class DirectoryEntry:
    """ディレクトリエントリ（32バイト）。"""
    filename: str          # ファイル名（ドット記法、例: "FILE.TXT"）
    extension: str         # 拡張子（3バイト）
    attributes: int        # 属性フラグ
    created_time: int      # 作成時刻
    created_date: int      # 作成日付
    accessed_date: int     # アクセス日付
    start_cluster: int     # 開始クラスタ
    file_size: int         # ファイルサイズ（ディレクトリは0）
    write_time: int        # 更新時刻
    write_date: int        # 更新日付
    
    @property
    def is_directory(self) -> bool:
        """ディレクトリかどうか."""
        return bool(self.attributes & ATTR_DIRECTORY)
    
    @property
    def is_file(self) -> bool:
        """ファイルかどうか."""
        return bool(self.attributes & ATTR_ARCHIVE) and not self.is_directory
    
    @property
    def is_hidden(self) -> bool:
        """隠しファイルかどうか."""
        return bool(self.attributes & ATTR_HIDDEN)
    
    def full_name(self) -> str:
        """フルファイル名（拡張子付き）を返す."""
        if self.extension:
            return f"{self.filename}.{self.extension}"
        return self.filename


class FATTable:
    """FAT テーブル管理クラス."""
    
    @staticmethod
    def create_default_bpb(profile: MediaProfile) -> BPBFields:
        """メディアプロファイルからデフォルトBPBを作成。
        
        IPL形式などでBPBが読み込めない場合の代替。
        
        Args:
            profile: メディアプロファイル
        
        Returns:
            BPBFields
        """
        return BPBFields(
            bytes_per_sector=profile.sector_size,
            sectors_per_cluster=1,
            reserved_sectors=1,
            fat_count=2,
            root_entries=192 if profile.name == "2HD" else 224,
            total_sectors_16=profile.total_sectors,
            media_descriptor=profile.media_byte,
            sectors_per_fat=2,
            sectors_per_track=profile.sectors_per_track,
            heads=profile.sides,
            hidden_sectors=0,
            total_sectors_32=0,
        )
    
    def __init__(self, disk_data: bytes, bpb: Optional[BPBFields], profile: MediaProfile):
        """初期化。
        
        Args:
            disk_data: ディスク全体のデータ（読み込み用）
            bpb: BIOS パラメータブロック（Noneの場合はデフォルトを使用）
            profile: メディアプロファイル
        """
        # 書き込み可能にするため bytearray に変換
        self.disk_data = bytearray(disk_data) if isinstance(disk_data, bytes) else disk_data
        self.profile = profile
        
        # BPBがない場合はプロファイルからデフォルトを作成
        if bpb is None:
            self.bpb = self.create_default_bpb(profile)
        else:
            self.bpb = bpb
        
        # レイアウト計算
        self.fat_start_byte = (self.bpb.reserved_sectors << 10)  # セクタ→バイト
        self.fat_sectors = self.bpb.sectors_per_fat
        self.root_start_byte = self.fat_start_byte + (self.fat_sectors * self.bpb.fat_count * self.bpb.bytes_per_sector)
        self.root_sectors = (self.bpb.root_entries * 32 + self.bpb.bytes_per_sector - 1) // self.bpb.bytes_per_sector
        self.data_start_byte = self.root_start_byte + (self.root_sectors * self.bpb.bytes_per_sector)
        
        # FAT12 vs FAT16 判定
        fat_size = self.fat_sectors * self.bpb.fat_count
        root_dir_sectors = self.root_sectors
        total_sectors = self.bpb.total_sectors
        data_sectors = total_sectors - (self.bpb.reserved_sectors + fat_size + root_dir_sectors)
        data_clusters = data_sectors // self.bpb.sectors_per_cluster
        
        self.is_fat12 = data_clusters < 4085
        self.fat_tail_code = 0xFFF if self.is_fat12 else 0xFFFF
        self.data_clusters_plus_2 = data_clusters + 2
    
    def read_fat_entry(self, cluster: int) -> int:
        """FAT エントリを読み込む（ビッグエンディアン）。
        
        Args:
            cluster: クラスタ番号
        
        Returns:
            次のクラスタ番号（チェーン終端は fat_tail_code）
        """
        if self.is_fat12:
            # FAT12: 3 バイトで 2 つのエントリ
            byte_offset = self.fat_start_byte + 3 * (cluster >> 1)
            
            if cluster & 1 == 0:  # 偶数クラスタ
                # バイト順序: [L][M.H.] → [H][M][L]
                hi = (self.disk_data[byte_offset + 1] & 0x0F) << 8
                lo = self.disk_data[byte_offset] & 0xFF
                return hi | lo
            else:  # 奇数クラスタ
                # バイト順序: [...][..l.hm][m...]
                hi = (self.disk_data[byte_offset + 2] & 0xFF) << 4
                lo = (self.disk_data[byte_offset + 1] >> 4) & 0x0F
                return hi | lo
        else:
            # FAT16: 2 バイトで 1 つのエントリ（ビッグエンディアン）
            byte_offset = self.fat_start_byte + cluster * 2
            hi = self.disk_data[byte_offset] & 0xFF
            lo = self.disk_data[byte_offset + 1] & 0xFF
            return (hi << 8) | lo
    
    def get_cluster_byte_offset(self, cluster: int) -> int:
        """クラスタ番号からディスク上のバイト位置を計算。
        
        Args:
            cluster: クラスタ番号
        
        Returns:
            ディスク上のバイト位置
        """
        if cluster < 2:
            raise ValueError(f"Invalid cluster number: {cluster}")
        
        bytes_per_cluster = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
        offset = self.data_start_byte + ((cluster - 2) * bytes_per_cluster)
        return offset
    
    def follow_cluster_chain(self, start_cluster: int, max_clusters: Optional[int] = None) -> List[int]:
        """クラスタチェーンをたどる。
        
        Args:
            start_cluster: 開始クラスタ
            max_clusters: 最大クラスタ数（無限ループ検出用）
        
        Returns:
            クラスタ番号のリスト
        """
        if max_clusters is None:
            max_clusters = self.data_clusters_plus_2
        
        chain = []
        current = start_cluster
        
        while current < self.fat_tail_code and len(chain) < max_clusters:
            if current < 2 or current >= self.data_clusters_plus_2:
                raise ValueError(f"Invalid cluster: {current}")
            
            chain.append(current)
            current = self.read_fat_entry(current)
        
        if len(chain) >= max_clusters:
            raise ValueError("Circular FAT chain detected")
        
        return chain
    
    def read_cluster_data(self, cluster: int) -> bytes:
        """クラスタのデータを読み込む。
        
        Args:
            cluster: クラスタ番号
        
        Returns:
            クラスタデータ
        """
        offset = self.get_cluster_byte_offset(cluster)
        size = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
        return bytes(self.disk_data[offset:offset + size])
    
    def write_fat_entry(self, cluster: int, next_cluster: int) -> None:
        """FAT エントリを書き込む（ビッグエンディアン）。
        
        Args:
            cluster: クラスタ番号
            next_cluster: 次のクラスタ番号（チェーン終端は fat_tail_code）
        """
        if self.is_fat12:
            # FAT12: 3 バイトで 2 つのエントリ
            byte_offset = self.fat_start_byte + 3 * (cluster >> 1)
            
            if cluster & 1 == 0:  # 偶数クラスタ
                # バイト順序: [L][M.H.] → [H][M][L]
                self.disk_data[byte_offset] = next_cluster & 0xFF
                self.disk_data[byte_offset + 1] = (self.disk_data[byte_offset + 1] & 0xF0) | ((next_cluster >> 8) & 0x0F)
            else:  # 奇数クラスタ
                # バイト順序: [...][..l.hm][m...]
                self.disk_data[byte_offset + 1] = (self.disk_data[byte_offset + 1] & 0x0F) | ((next_cluster & 0x0F) << 4)
                self.disk_data[byte_offset + 2] = (next_cluster >> 4) & 0xFF
        else:
            # FAT16: 2 バイトで 1 つのエントリ（ビッグエンディアン）
            byte_offset = self.fat_start_byte + cluster * 2
            self.disk_data[byte_offset] = (next_cluster >> 8) & 0xFF
            self.disk_data[byte_offset + 1] = next_cluster & 0xFF
        
        # 複製 FAT にも同じ値を書き込む
        for fat_num in range(1, self.bpb.fat_count):
            fat_copy_offset = self.fat_start_byte + (fat_num * self.fat_sectors * self.bpb.bytes_per_sector)
            
            if self.is_fat12:
                byte_offset = fat_copy_offset + 3 * (cluster >> 1)
                if cluster & 1 == 0:
                    self.disk_data[byte_offset] = next_cluster & 0xFF
                    self.disk_data[byte_offset + 1] = (self.disk_data[byte_offset + 1] & 0xF0) | ((next_cluster >> 8) & 0x0F)
                else:
                    self.disk_data[byte_offset + 1] = (self.disk_data[byte_offset + 1] & 0x0F) | ((next_cluster & 0x0F) << 4)
                    self.disk_data[byte_offset + 2] = (next_cluster >> 4) & 0xFF
            else:
                byte_offset = fat_copy_offset + cluster * 2
                self.disk_data[byte_offset] = (next_cluster >> 8) & 0xFF
                self.disk_data[byte_offset + 1] = next_cluster & 0xFF
    
    def find_free_cluster(self) -> Optional[int]:
        """空きクラスタを探す。
        
        Returns:
            空きクラスタ番号、または None（空きがない）
        """
        for cluster in range(2, self.data_clusters_plus_2):
            entry = self.read_fat_entry(cluster)
            if entry == 0:  # 空きクラスタ
                return cluster
        return None
    
    def write_cluster_data(self, cluster: int, data: bytes) -> None:
        """クラスタにデータを書き込む。
        
        Args:
            cluster: クラスタ番号
            data: 書き込むデータ
        """
        offset = self.get_cluster_byte_offset(cluster)
        size = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
        
        if len(data) > size:
            raise ValueError(f"Data too large for cluster: {len(data)} > {size}")
        
        # クラスタサイズ分のゼロパディング
        padded = data + b'\x00' * (size - len(data))
        self.disk_data[offset:offset + size] = padded
    
    def allocate_clusters_for_data(self, data: bytes, existing_chain: Optional[List[int]] = None) -> List[int]:
        """データ用にクラスタを割り当てる。
        
        Args:
            data: 書き込むデータ
            existing_chain: 既存のクラスタチェーン（更新する場合）
        
        Returns:
            割り当てたクラスタ番号のリスト
        
        Raises:
            ValueError: 空きクラスタが不足している場合
        """
        bytes_per_cluster = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
        needed_clusters = (len(data) + bytes_per_cluster - 1) // bytes_per_cluster
        
        if existing_chain is None:
            chain = []
        else:
            chain = existing_chain.copy()
        
        # 既存チェーンが必要クラスタ以上の場合は再利用
        if len(chain) > needed_clusters:
            # 余分なクラスタを解放
            for cluster in chain[needed_clusters:]:
                self.write_fat_entry(cluster, 0)
            chain = chain[:needed_clusters]
        
        # 不足分を割り当て
        # 各クラスタを見つけた直後に FAT を更新することで、
        # 次の find_free_cluster が同じクラスタを返さないようにする
        while len(chain) < needed_clusters:
            free_cluster = self.find_free_cluster()
            if free_cluster is None:
                raise ValueError("No free clusters available")
            chain.append(free_cluster)
            
            # 前のクラスタがあれば、それを新しいクラスタにリンク
            if len(chain) >= 2:
                prev_cluster = chain[-2]
                self.write_fat_entry(prev_cluster, free_cluster)
            
            # 新しいクラスタを一時的にマーク
            # (最後のクラスタは後で fat_tail_code に更新される)
            self.write_fat_entry(free_cluster, self.fat_tail_code)
        
        # 最後のクラスタはすでに fat_tail_code でマークされている
        # 中間のクラスタが正しくリンクされていることを確認
        for i in range(len(chain) - 1):
            self.write_fat_entry(chain[i], chain[i + 1])
        
        return chain
    
    def write_data_to_clusters(self, data: bytes, cluster_chain: List[int]) -> None:
        """データをクラスタチェーンに書き込む。
        
        Args:
            data: 書き込むデータ
            cluster_chain: クラスタ番号のリスト
        """
        bytes_per_cluster = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
        
        for i, cluster in enumerate(cluster_chain):
            offset = i * bytes_per_cluster
            chunk_size = min(bytes_per_cluster, len(data) - offset)
            chunk = data[offset:offset + chunk_size]
            self.write_cluster_data(cluster, chunk)



class DirectoryReader:
    """ディレクトリ読み込みクラス."""
    
    def __init__(self, disk_data: bytes, fat_table: FATTable, bpb: BPBFields):
        """初期化。
        
        Args:
            disk_data: ディスク全体のデータ
            fat_table: FAT テーブル
            bpb: BIOS パラメータブロック
        """
        self.disk_data = disk_data
        self.fat_table = fat_table
        self.bpb = bpb
    
    def parse_directory_entry(self, data: bytes, offset: int) -> Optional[DirectoryEntry]:
        """ディレクトリエントリをパース（ビッグエンディアン）。
        
        Args:
            data: ディレクトリデータ
            offset: エントリ内のオフセット
        
        Returns:
            DirectoryEntry、または None（終端/削除エントリ）
        """
        if offset + 32 > len(data):
            return None
        
        entry_data = data[offset:offset + 32]
        
        # 終端判定（0x00）
        if entry_data[0] == 0x00:
            return None
        
        # 削除判定（0xE5）
        if (entry_data[0] & 0xFF) == 0xE5:
            return None
        
        # ファイル名抽出（8バイト）
        filename = entry_data[0:8].decode('ascii', errors='ignore').rstrip()
        
        # 拡張子抽出（3バイト）
        extension = entry_data[8:11].decode('ascii', errors='ignore').rstrip()
        
        # 属性
        attributes = entry_data[11] & 0xFF
        
        # タイムスタンプ（リトルエンディアン）
        created_time = struct.unpack('<H', entry_data[14:16])[0]
        created_date = struct.unpack('<H', entry_data[16:18])[0]
        accessed_date = struct.unpack('<H', entry_data[18:20])[0]
        write_time = struct.unpack('<H', entry_data[22:24])[0]
        write_date = struct.unpack('<H', entry_data[24:26])[0]
        
        # 開始クラスタ、ファイルサイズ（リトルエンディアン）
        start_cluster = struct.unpack('<H', entry_data[26:28])[0]
        file_size = struct.unpack('<I', entry_data[28:32])[0]
        
        return DirectoryEntry(
            filename=filename,
            extension=extension,
            attributes=attributes,
            created_time=created_time,
            created_date=created_date,
            accessed_date=accessed_date,
            start_cluster=start_cluster,
            file_size=file_size,
            write_time=write_time,
            write_date=write_date,
        )
    
    def read_root_directory(self) -> List[DirectoryEntry]:
        """ルートディレクトリを読み込む。
        
        Returns:
            ディレクトリエントリのリスト
        """
        entries = []
        root_size = self.bpb.root_entries * 32
        root_data = self.disk_data[self.fat_table.root_start_byte:self.fat_table.root_start_byte + root_size]
        
        for i in range(self.bpb.root_entries):
            entry = self.parse_directory_entry(root_data, i * 32)
            if entry is None:
                break  # 終端に到達
            entries.append(entry)
        
        return entries
    
    def read_subdirectory(self, start_cluster: int) -> List[DirectoryEntry]:
        """サブディレクトリを読み込む。
        
        Args:
            start_cluster: ディレクトリの開始クラスタ
        
        Returns:
            ディレクトリエントリのリスト
        """
        entries = []
        
        try:
            chain = self.fat_table.follow_cluster_chain(start_cluster)
        except ValueError:
            return entries
        
        for cluster in chain:
            data = self.fat_table.read_cluster_data(cluster)
            
            for offset in range(0, len(data), 32):
                entry = self.parse_directory_entry(data, offset)
                if entry is None:
                    break  # この クラスタ内で終了
                entries.append(entry)
        
        return entries
    
    def find_entry_by_name(self, directory_entries: List[DirectoryEntry], 
                          name: str, case_sensitive: bool = False) -> Optional[DirectoryEntry]:
        """ディレクトリ内でエントリを検索。
        
        Args:
            directory_entries: ディレクトリエントリリスト
            name: 検索ファイル名（大文字のみ、8.3 形式）
            case_sensitive: 大文字小文字を区別するか
        
        Returns:
            見つかったエントリ、または None
        """
        search_name = name if case_sensitive else name.upper()
        
        for entry in directory_entries:
            entry_name = entry.full_name() if entry.extension else entry.filename
            entry_name_cmp = entry_name if case_sensitive else entry_name.upper()
            
            if entry_name_cmp == search_name:
                return entry
        
        return None
    
    def find_entries_by_pattern(self, directory_entries: List[DirectoryEntry],
                               pattern: str) -> List[DirectoryEntry]:
        """ワイルドカード検索。
        
        Args:
            directory_entries: ディレクトリエントリリスト
            pattern: 検索パターン（* と ? をサポート）
        
        Returns:
            マッチしたエントリのリスト
        """
        import fnmatch
        pattern_upper = pattern.upper()
        
        matches = []
        for entry in directory_entries:
            entry_name = entry.full_name() if entry.extension else entry.filename
            if fnmatch.fnmatch(entry_name.upper(), pattern_upper):
                matches.append(entry)
        
        return matches
    
    def write_entry_to_bytes(self, entry: DirectoryEntry) -> bytes:
        """DirectoryEntry を 32 バイトのディレクトリエントリに変換。
        
        Args:
            entry: ディレクトリエントリ
        
        Returns:
            32 バイトのエントリデータ
        """
        # ファイル名と拡張子を 8+3 バイトにパディング（Human68k は小文字をそのまま格納可能）
        filename_bytes = entry.filename.encode('ascii')[:8].ljust(8)
        ext_bytes = entry.extension.encode('ascii')[:3].ljust(3)
        
        # タイムスタンプ（リトルエンディアン）
        created_time = struct.pack('<H', entry.created_time)
        created_date = struct.pack('<H', entry.created_date)
        accessed_date = struct.pack('<H', entry.accessed_date)
        write_time = struct.pack('<H', entry.write_time)
        write_date = struct.pack('<H', entry.write_date)
        
        # クラスタ、サイズ（リトルエンディアン）
        start_cluster = struct.pack('<H', entry.start_cluster)
        file_size = struct.pack('<I', entry.file_size)
        
        # 32 バイトのエントリを組み立て
        entry_bytes = (
            filename_bytes +           # 0x00-0x07 (8 bytes)
            ext_bytes +                # 0x08-0x0A (3 bytes)
            bytes([entry.attributes]) +  # 0x0B (1 byte)
            b'\x00' +                  # 0x0C (1 byte) - 予約バイト
            b'\x00' +                  # 0x0D (1 byte) - 作成時刻(ミリ秒) 
            created_time +             # 0x0E-0x0F (2 bytes)
            created_date +             # 0x10-0x11 (2 bytes)
            accessed_date +            # 0x12-0x13 (2 bytes)
            b'\x00\x00' +              # 0x14-0x15 (2 bytes) - 予約/ファイルサイズ高位ワード
            write_time +               # 0x16-0x17 (2 bytes)
            write_date +               # 0x18-0x19 (2 bytes)
            start_cluster +            # 0x1A-0x1B (2 bytes)
            file_size                  # 0x1C-0x1F (4 bytes)
        )
        
        return entry_bytes
    
    def add_directory_entry(self, directory_cluster_or_root: Optional[int], entry: DirectoryEntry) -> None:
        """ディレクトリにエントリを追加。
        
        Args:
            directory_cluster_or_root: ディレクトリのクラスタ番号、または None（ルートディレクトリ）
            entry: 追加するエントリ
        
        Raises:
            ValueError: ディレクトリが満杯の場合
        """
        if directory_cluster_or_root is None:
            # ルートディレクトリ
            root_size = self.bpb.root_entries * 32
            root_data = bytearray(self.fat_table.disk_data[self.fat_table.root_start_byte:self.fat_table.root_start_byte + root_size])
            
            # 空のスロットを探す
            for i in range(self.bpb.root_entries):
                offset = i * 32
                if root_data[offset] == 0x00 or root_data[offset] == 0xE5:
                    # 空のスロット
                    entry_bytes = self.write_entry_to_bytes(entry)
                    root_data[offset:offset + 32] = entry_bytes
                    self.fat_table.disk_data[self.fat_table.root_start_byte:self.fat_table.root_start_byte + root_size] = root_data
                    return
            
            raise ValueError("Root directory is full")
        else:
            # サブディレクトリ
            try:
                chain = self.fat_table.follow_cluster_chain(directory_cluster_or_root)
            except ValueError:
                raise ValueError(f"Invalid directory cluster: {directory_cluster_or_root}")
            
            entry_bytes = self.write_entry_to_bytes(entry)
            bytes_per_cluster = self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster
            
            # 各クラスタを検索
            for cluster in chain:
                data = bytearray(self.fat_table.read_cluster_data(cluster))
                
                for offset in range(0, len(data), 32):
                    if data[offset] == 0x00 or data[offset] == 0xE5:
                        # 空のスロット
                        data[offset:offset + 32] = entry_bytes
                        self.fat_table.write_cluster_data(cluster, bytes(data))
                        return
            
            # 新しいクラスタが必要
            new_cluster = self.fat_table.find_free_cluster()
            if new_cluster is None:
                raise ValueError("No free clusters for directory expansion")
            
            # 最後のクラスタのチェーンを更新
            last_cluster = chain[-1]
            self.fat_table.write_fat_entry(last_cluster, new_cluster)
            self.fat_table.write_fat_entry(new_cluster, self.fat_table.fat_tail_code)
            
            # 新しいクラスタにエントリを書き込む
            new_cluster_data = bytearray(bytes_per_cluster)
            new_cluster_data[:32] = entry_bytes
            self.fat_table.write_cluster_data(new_cluster, bytes(new_cluster_data))
    
    def remove_directory_entry(self, directory_cluster_or_root: Optional[int], entry_name: str) -> bool:
        """ディレクトリからエントリを削除。
        
        Args:
            directory_cluster_or_root: ディレクトリのクラスタ番号、または None（ルートディレクトリ）
            entry_name: 削除するエントリ名（8.3 形式）
        
        Returns:
            削除できた場合 True、見つからない場合 False
        """
        if directory_cluster_or_root is None:
            # ルートディレクトリ
            root_size = self.bpb.root_entries * 32
            root_data = bytearray(self.fat_table.disk_data[self.fat_table.root_start_byte:self.fat_table.root_start_byte + root_size])
            
            for i in range(self.bpb.root_entries):
                offset = i * 32
                if root_data[offset] == 0x00:
                    break  # 終端に到達
                if root_data[offset] == 0xE5:
                    continue  # 既に削除されている
                
                # エントリ名を確認
                entry_data = root_data[offset:offset + 32]
                filename = entry_data[0:8].decode('ascii', errors='ignore').rstrip()
                extension = entry_data[8:11].decode('ascii', errors='ignore').rstrip()
                full_name = f"{filename}.{extension}" if extension else filename
                
                if full_name.upper() == entry_name.upper():
                    # 削除マーク
                    root_data[offset] = 0xE5
                    self.fat_table.disk_data[self.fat_table.root_start_byte:self.fat_table.root_start_byte + root_size] = root_data
                    return True
            
            return False
        else:
            # サブディレクトリ
            try:
                chain = self.fat_table.follow_cluster_chain(directory_cluster_or_root)
            except ValueError:
                return False
            
            for cluster in chain:
                data = bytearray(self.fat_table.read_cluster_data(cluster))
                
                for offset in range(0, len(data), 32):
                    if data[offset] == 0x00:
                        break  # 終端に到達
                    if data[offset] == 0xE5:
                        continue  # 既に削除されている
                    
                    # エントリ名を確認
                    entry_data = data[offset:offset + 32]
                    filename = entry_data[0:8].decode('ascii', errors='ignore').rstrip()
                    extension = entry_data[8:11].decode('ascii', errors='ignore').rstrip()
                    full_name = f"{filename}.{extension}" if extension else filename
                    
                    if full_name.upper() == entry_name.upper():
                        # 削除マーク
                        data[offset] = 0xE5
                        self.fat_table.write_cluster_data(cluster, bytes(data))
                        return True
            
            return False


def format_timestamp(time_val: int, date_val: int) -> str:
    """タイムスタンプを整形。
    
    Args:
        time_val: 時刻フィールド（MS-DOS形式）
        date_val: 日付フィールド（MS-DOS形式）
    
    Returns:
        整形文字列 "YYYY-MM-DD HH:MM:SS"
    """
    # 時刻: [時(5bit)][分(6bit)][秒/2(5bit)]
    hour = (time_val >> 11) & 0x1F
    minute = (time_val >> 5) & 0x3F
    second = (time_val & 0x1F) * 2
    
    # 日付: [(年-1980)(7bit)][月(4bit)][日(5bit)]
    year = ((date_val >> 9) & 0x7F) + 1980
    month = (date_val >> 5) & 0x0F
    day = date_val & 0x1F
    
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
