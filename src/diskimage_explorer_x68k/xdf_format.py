"""XDF (X68000 Disk Format) format definitions based on XEiJ analysis."""

from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple


class MediaType(IntEnum):
    """X68000 media types from FDMedia.java"""
    MEDIA_2HD = 0xFE     # 2HD: 1232 KB, 1024 bytes/sector
    MEDIA_2HC = 0xFD     # 2HC: 1200 KB, 512 bytes/sector
    MEDIA_2DD_640 = 0xFB  # 2DD: 640 KB, 512 bytes/sector (80 cylinders)
    MEDIA_2DD_720 = 0xFC  # 2DD: 720 KB, 512 bytes/sector (77 cylinders)
    MEDIA_2HQ = 0xFA     # 2HQ: 1440 KB, 512 bytes/sector
    MEDIA_2HD_IDE = 0x70  # 2HD IDE
    MEDIA_2HDE = 0x20    # 2HDE
    MEDIA_2HS = 0xF0     # 2HS


class SectorScale(IntEnum):
    """Sector scale definitions: sectorScale = log2(sectorSize) - 7"""
    SCALE_128 = 0    # 128 bytes
    SCALE_256 = 1    # 256 bytes
    SCALE_512 = 2    # 512 bytes
    SCALE_1024 = 3   # 1024 bytes


@dataclass
class MediaProfile:
    """Complete XDF media profile based on XEiJ FDMedia specifications."""
    name: str
    media_byte: int
    cylinders: int
    sides: int
    sectors_per_track: int
    sector_size: int
    sector_scale: int
    total_sectors: int
    
    @property
    def file_size(self) -> int:
        """Total file size in bytes."""
        return self.sector_size * self.total_sectors
    
    @property
    def capacity_kb(self) -> int:
        """Capacity in KB."""
        return self.file_size // 1024
    
    @property
    def total_tracks(self) -> int:
        """Total number of tracks."""
        return self.cylinders * self.sides
    
    def offset_to_chs(self, offset: int) -> tuple[int, int, int]:
        """Convert file offset to CHS (Cylinder, Head, Sector) address.
        
        Args:
            offset: Byte offset in the file
        
        Returns:
            (cylinder, head/side, sector) tuple
        """
        sector_num = offset // self.sector_size
        track = sector_num // self.sectors_per_track
        sector = sector_num % self.sectors_per_track + 1  # Sectors are 1-indexed
        
        cylinder = track // self.sides
        head = track % self.sides
        
        return cylinder, head, sector
    
    def chs_to_offset(self, cylinder: int, head: int, sector: int) -> int:
        """Convert CHS address to file offset.
        
        Args:
            cylinder: Cylinder number (0-based)
            head: Head/side number (0-based)
            sector: Sector number (1-based)
        
        Returns:
            Byte offset in the file
        """
        track = cylinder * self.sides + head
        sector_num = track * self.sectors_per_track + (sector - 1)
        return sector_num * self.sector_size


# Standard media profiles from XEiJ FDMedia.java
MEDIA_PROFILES = {
    MediaType.MEDIA_2HD: MediaProfile(
        name="2HD",
        media_byte=0xFE,
        cylinders=77,
        sides=2,
        sectors_per_track=8,
        sector_size=1024,
        sector_scale=3,
        total_sectors=1232,
    ),
    MediaType.MEDIA_2HC: MediaProfile(
        name="2HC",
        media_byte=0xFD,
        cylinders=77,
        sides=2,
        sectors_per_track=15,
        sector_size=512,
        sector_scale=2,
        total_sectors=2310,
    ),
    MediaType.MEDIA_2DD_640: MediaProfile(
        name="2DD (640KB)",
        media_byte=0xFB,
        cylinders=80,
        sides=2,
        sectors_per_track=8,
        sector_size=512,
        sector_scale=2,
        total_sectors=1280,
    ),
    MediaType.MEDIA_2DD_720: MediaProfile(
        name="2DD (720KB)",
        media_byte=0xFC,
        cylinders=77,
        sides=2,
        sectors_per_track=9,
        sector_size=512,
        sector_scale=2,
        total_sectors=1386,
    ),
    MediaType.MEDIA_2HQ: MediaProfile(
        name="2HQ",
        media_byte=0xFA,
        cylinders=80,
        sides=2,
        sectors_per_track=18,
        sector_size=512,
        sector_scale=2,
        total_sectors=2880,
    ),
}


@dataclass
class BPBFields:
    """BIOS Parameter Block fields from X68000 XDF files.
    
    X68000 uses big-endian byte order (68000 native format).
    """
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    root_entries: int
    total_sectors_16: int  # 0 if > 65535
    media_descriptor: int
    sectors_per_fat: int
    sectors_per_track: int
    heads: int
    hidden_sectors: int
    total_sectors_32: int  # Used if total_sectors_16 == 0
    
    @property
    def total_sectors(self) -> int:
        """Get total sectors (using 16-bit or 32-bit field)."""
        return self.total_sectors_16 if self.total_sectors_16 != 0 else self.total_sectors_32


# IPL Signature constants
IPL_SIGNATURE_2HD = b"X68IPL30"      # 2HD format
IPL_SIGNATURE_2HDE = b"2HDE v1.1"    # 2HDE format
IPL_SIGNATURE_2HS = b"9SCFMT IPL"    # 2HS format

# Offset constants
IPL_SIGNATURE_OFFSET = 3              # Location of IPL signature
BOOT_CODE_SIZE = 512                  # Boot sector size
BPB_OFFSET = 0x0B                     # Standard BPB offset
BPB_OFFSET_2 = 0x2162                 # Alternate BPB location
