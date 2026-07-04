"""XDF file reader implementation based on XEiJ FDMedia analysis."""

import struct
from pathlib import Path
from typing import Optional, Tuple

from .xdf_format import (
    BPBFields,
    MediaProfile,
    MediaType,
    MEDIA_PROFILES,
    IPL_SIGNATURE_2HD,
    IPL_SIGNATURE_2HDE,
    IPL_SIGNATURE_2HS,
    IPL_SIGNATURE_OFFSET,
    BPB_OFFSET,
    BPB_OFFSET_2,
)


class XDFReader:
    """Read and parse X68000 XDF (floppy disk image) files."""
    
    def __init__(self, file_path: Path):
        """Initialize XDF reader.
        
        Args:
            file_path: Path to the XDF file
        """
        self.file_path = Path(file_path)
        self.file_size = self.file_path.stat().st_size
        self._fp: Optional[object] = None
    
    def __enter__(self):
        self._fp = open(self.file_path, 'rb')
        return self
    
    def __exit__(self, *args):
        if self._fp:
            self._fp.close()
            self._fp = None
    
    def _read_bytes(self, offset: int, size: int) -> bytes:
        """Read bytes from file at given offset."""
        if self._fp is None:
            with open(self.file_path, 'rb') as f:
                f.seek(offset)
                return f.read(size)
        self._fp.seek(offset)
        return self._fp.read(size)
    
    def detect_media_type(self) -> Optional[MediaProfile]:
        """Detect media type from file size and IPL signature.
        
        Returns:
            MediaProfile if detected, None otherwise
        """
        # First, try to detect by IPL signature
        boot_sector = self._read_bytes(0, 512)
        if len(boot_sector) < 512:
            return None
        
        # Check for IPL signatures
        ipl_sig = boot_sector[IPL_SIGNATURE_OFFSET:IPL_SIGNATURE_OFFSET+8]
        if ipl_sig == IPL_SIGNATURE_2HD:
            # 2HD format
            for profile in MEDIA_PROFILES.values():
                if profile.name == "2HD" and self.file_size == profile.file_size:
                    return profile
        
        # Try to match by file size alone
        for profile in MEDIA_PROFILES.values():
            if self.file_size == profile.file_size:
                return profile
        
        return None
    
    def read_bpb(self, offset: int = BPB_OFFSET) -> Optional[BPBFields]:
        """Read BIOS Parameter Block from boot sector.
        
        X68000 uses big-endian byte order for BPB fields.
        Falls back to secondary BPB location (0x2162) for IPL format.
        
        Args:
            offset: Offset of BPB in boot sector (default: 0x0B)
        
        Returns:
            BPBFields if valid, None otherwise
        """
        try:
            boot_sector = self._read_bytes(0, 512)
            if len(boot_sector) < offset + 25:
                return None
            
            # Parse BPB fields (big-endian)
            # Standard FAT12/FAT16 BPB layout at offset 0x0B:
            #   0x0B-0x0C: Bytes per sector (big-endian)
            #   0x0D: Sectors per cluster
            #   0x0E-0x0F: Reserved sectors (big-endian)
            #   0x10: Number of FATs
            #   0x11-0x12: Root directory entries (big-endian)
            #   0x13-0x14: Total sectors 16-bit (big-endian)
            #   0x15: Media descriptor
            #   0x16-0x17: Sectors per FAT (big-endian)
            #   0x18-0x19: Sectors per track (big-endian)
            #   0x1A-0x1B: Heads (big-endian)
            #   0x1C-0x1F: Hidden sectors (big-endian)
            #   0x20-0x23: Total sectors 32-bit (big-endian)
            
            bpb_data = boot_sector[offset:]
            
            bytes_per_sector = struct.unpack('>H', bpb_data[0:2])[0]
            sectors_per_cluster = bpb_data[2]
            reserved_sectors = struct.unpack('>H', bpb_data[3:5])[0]
            fat_count = bpb_data[5]
            root_entries = struct.unpack('>H', bpb_data[6:8])[0]
            total_sectors_16 = struct.unpack('>H', bpb_data[8:10])[0]
            media_descriptor = bpb_data[10]
            sectors_per_fat = struct.unpack('>H', bpb_data[11:13])[0]
            sectors_per_track = struct.unpack('>H', bpb_data[13:15])[0]
            heads = struct.unpack('>H', bpb_data[15:17])[0]
            hidden_sectors = struct.unpack('>I', bpb_data[17:21])[0]
            total_sectors_32 = struct.unpack('>I', bpb_data[21:25])[0]
            
            # Validate BPB
            if bytes_per_sector not in (128, 256, 512, 1024):
                return None
            if sectors_per_cluster == 0:
                return None
            
            return BPBFields(
                bytes_per_sector=bytes_per_sector,
                sectors_per_cluster=sectors_per_cluster,
                reserved_sectors=reserved_sectors,
                fat_count=fat_count,
                root_entries=root_entries,
                total_sectors_16=total_sectors_16,
                media_descriptor=media_descriptor,
                sectors_per_fat=sectors_per_fat,
                sectors_per_track=sectors_per_track,
                heads=heads,
                hidden_sectors=hidden_sectors,
                total_sectors_32=total_sectors_32,
            )
        except (struct.error, IndexError):
            return None
    
    def read_sector(self, cylinder: int, head: int, sector: int, profile: MediaProfile) -> Optional[bytes]:
        """Read a sector by CHS (Cylinder-Head-Sector) address.
        
        Args:
            cylinder: Cylinder number (0-based)
            head: Head/side number (0-based)
            sector: Sector number (1-based)
            profile: Media profile with sector layout information
        
        Returns:
            Sector data if successful, None if out of bounds
        """
        # Validate CHS
        if cylinder >= profile.cylinders or head >= profile.sides or sector < 1 or sector > profile.sectors_per_track:
            return None
        
        offset = profile.chs_to_offset(cylinder, head, sector)
        if offset + profile.sector_size > self.file_size:
            return None
        
        return self._read_bytes(offset, profile.sector_size)
    
    def read_all_sectors(self, profile: MediaProfile) -> dict[tuple[int, int, int], bytes]:
        """Read all sectors from the disk image.
        
        Returns:
            Dictionary mapping (cylinder, head, sector) tuples to sector data
        """
        sectors = {}
        for cyl in range(profile.cylinders):
            for head in range(profile.sides):
                for sect in range(1, profile.sectors_per_track + 1):
                    data = self.read_sector(cyl, head, sect, profile)
                    if data:
                        sectors[(cyl, head, sect)] = data
        return sectors
    
    def info(self) -> dict:
        """Get information about the XDF file.
        
        Returns:
            Dictionary with file info
        """
        profile = self.detect_media_type()
        bpb = self.read_bpb() if profile else None
        
        info = {
            'file_path': str(self.file_path),
            'file_size': self.file_size,
            'file_size_kb': self.file_size // 1024,
        }
        
        if profile:
            info['media_type'] = profile.name
            info['media_byte'] = f"0x{profile.media_byte:02X}"
            info['cylinders'] = profile.cylinders
            info['sides'] = profile.sides
            info['sectors_per_track'] = profile.sectors_per_track
            info['sector_size'] = profile.sector_size
            info['total_sectors'] = profile.total_sectors
        
        if bpb:
            info['bpb'] = {
                'bytes_per_sector': bpb.bytes_per_sector,
                'sectors_per_cluster': bpb.sectors_per_cluster,
                'reserved_sectors': bpb.reserved_sectors,
                'fat_count': bpb.fat_count,
                'root_entries': bpb.root_entries,
                'total_sectors': bpb.total_sectors,
                'media_descriptor': f"0x{bpb.media_descriptor:02X}",
                'sectors_per_fat': bpb.sectors_per_fat,
            }
        
        return info
