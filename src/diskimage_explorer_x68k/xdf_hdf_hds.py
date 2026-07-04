"""HDF/HDS ハードディスクイメージ対応モジュール。

X68000 SASI/SCSI ハードディスクイメージの読み書き対応。
"""

import struct
from pathlib import Path
from typing import Optional, List, Tuple, NamedTuple
from dataclasses import dataclass


class PartitionInfo(NamedTuple):
    """パーティション情報。"""
    index: int                  # パーティション番号
    kind: str                   # 'sasi' または 'scsi'
    offset_sectors: int         # パーティション開始セクタ（SCSI の場合）
    offset_records: int         # パーティション開始レコード（SASI の場合）
    sectors_or_records: int     # パーティションサイズ
    byte_offset: int            # ファイル内のバイトオフセット
    label: str                  # パーティション説明


class HDFHDSReader:
    """HDF/HDS ハードディスクイメージリーダー。"""
    
    # パーティションテーブルシグネチャ
    SASI_SIGNATURE = b'X68K'
    SASI_HUMAN_SIG = b'Human68k'
    SCSI_SIGNATURE = b'X68K'
    SCSI_HUMAN_SIG = b'Human68k'
    
    # パーティションテーブルのオフセット
    SASI_TABLE_OFFSET = 0x400      # 1024 バイト
    SCSI_TABLE_OFFSET = 0x800      # 2048 バイト
    
    # パーティション情報オフセット
    SASI_PART_TABLE_OFFSET = 0x418  # シグネチャ後
    SCSI_PART_TABLE_OFFSET = 0x818  # シグネチャ後
    
    def __init__(self, image_path: Path):
        """初期化。
        
        Args:
            image_path: ハードディスクイメージファイルパス
        """
        self.image_path = Path(image_path)
        self.kind = None  # 'sasi', 'scsi' or None
        self.partitions: List[PartitionInfo] = []
        
        self._detect_format()
    
    def _detect_format(self) -> None:
        """HDF/HDS フォーマットを検出。"""
        data = self.image_path.read_bytes()
        
        # SASI フォーマットのチェック
        if len(data) >= 0x420 and data[0x400:0x404] == self.SASI_SIGNATURE:
            if data[0x410:0x418] == self.SASI_HUMAN_SIG:
                self.kind = 'sasi'
                self._parse_sasi_partitions(data)
                return
        
        # SCSI フォーマットのチェック
        if len(data) >= 0x820 and data[0x800:0x804] == self.SCSI_SIGNATURE:
            if data[0x810:0x818] == self.SCSI_HUMAN_SIG:
                self.kind = 'scsi'
                self._parse_scsi_partitions(data)
                return
    
    def _parse_sasi_partitions(self, data: bytes) -> None:
        """SASI パーティションテーブルを解析。
        
        SASI format:
        - 0x400: "X68K" signature
        - 0x410: "Human68k" signature  
        - 0x418: Partition table (16 entries, 8 bytes each)
          Each entry: [start_record (3 bytes + 1 reserved), size_records (4 bytes)]
        """
        self.partitions = []
        
        for i in range(16):
            entry_offset = self.SASI_PART_TABLE_OFFSET + i * 8
            if entry_offset + 8 > len(data):
                break
            
            # Extract partition info
            start_record = struct.unpack('>I', data[entry_offset:entry_offset + 4])[0] & 0x00FFFFFF
            size_records = struct.unpack('>I', data[entry_offset + 4:entry_offset + 8])[0]
            
            if start_record == 0 or size_records == 0:
                continue
            
            # 256 バイト単位 (SASI)
            byte_offset = start_record * 256
            
            self.partitions.append(PartitionInfo(
                index=i + 1,
                kind='sasi',
                offset_sectors=0,
                offset_records=start_record,
                sectors_or_records=size_records,
                byte_offset=byte_offset,
                label=f"SASI partition #{i + 1} @ 0x{byte_offset:08X} ({size_records * 256 // 1024} KB)"
            ))
    
    def _parse_scsi_partitions(self, data: bytes) -> None:
        """SCSI パーティションテーブルを解析。
        
        SCSI format:
        - 0x800: "X68K" signature
        - 0x810: "Human68k" signature
        - 0x818: Partition table (16 entries, 8 bytes each)
          Each entry: [start_sector (3 bytes + 1 reserved), size_sectors (4 bytes)]
        """
        self.partitions = []
        
        for i in range(16):
            entry_offset = self.SCSI_PART_TABLE_OFFSET + i * 8
            if entry_offset + 8 > len(data):
                break
            
            # Extract partition info
            start_sector = struct.unpack('>I', data[entry_offset:entry_offset + 4])[0] & 0x00FFFFFF
            size_sectors = struct.unpack('>I', data[entry_offset + 4:entry_offset + 8])[0]
            
            if start_sector == 0 or size_sectors == 0:
                continue
            
            # 1024 バイト単位 (SCSI)
            byte_offset = start_sector * 1024
            
            self.partitions.append(PartitionInfo(
                index=i + 1,
                kind='scsi',
                offset_sectors=start_sector,
                offset_records=0,
                sectors_or_records=size_sectors,
                byte_offset=byte_offset,
                label=f"SCSI partition #{i + 1} @ 0x{byte_offset:08X} ({size_sectors * 1024 // 1024} KB)"
            ))
    
    def get_partitions(self) -> List[PartitionInfo]:
        """パーティション情報を取得。
        
        Returns:
            パーティション情報リスト
        """
        return self.partitions
    
    def is_valid(self) -> bool:
        """有効なパーティションテーブルを持つかチェック。
        
        Returns:
            有効な場合 True
        """
        return self.kind is not None and len(self.partitions) > 0
    
    @staticmethod
    def detect_hdf_hds_file(image_path: Path) -> Optional[str]:
        """HDF/HDS ファイルかどうかを検出。
        
        Args:
            image_path: ファイルパス
        
        Returns:
            'hdf' (SASI), 'hds' (SCSI), None
        """
        data = image_path.read_bytes()
        
        # SASI HDF チェック
        if len(data) >= 0x420 and data[0x400:0x404] == b'X68K':
            if data[0x410:0x418] == b'Human68k':
                return 'hdf'
        
        # SCSI HDS チェック
        if len(data) >= 0x820 and data[0x800:0x804] == b'X68K':
            if data[0x810:0x818] == b'Human68k':
                return 'hds'
        
        return None
