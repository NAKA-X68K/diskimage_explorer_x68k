from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
from pathlib import Path, PurePosixPath
import shutil
from typing import Iterable

from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS, PyFatBytesIOFS


@dataclass
class ImageEntry:
    path: str
    name: str
    is_dir: bool
    size: int
    modified: str


class ImageMountError(RuntimeError):
    pass


@dataclass
class MountCandidate:
    kind: str
    offset: int
    label: str


@dataclass(frozen=True)
class X68kFloppyProfile:
    name: str
    bytes_per_sector: int
    sectors_per_cluster: int
    fat_count: int
    reserved_sectors: int
    root_entries: int
    total_sectors: int
    media: int
    fat_sectors: int
    fat_type: int

    @property
    def file_size(self) -> int:
        return self.bytes_per_sector * self.total_sectors


X68K_XDF_PROFILES: tuple[X68kFloppyProfile, ...] = (
    X68kFloppyProfile("2HD (1232KB)", 1024, 1, 2, 1, 192, 1232, 0xFE, 2, PyFat.FAT_TYPE_FAT12),
    X68kFloppyProfile("2HC (1200KB)", 512, 1, 2, 1, 224, 2400, 0xFD, 7, PyFat.FAT_TYPE_FAT12),
    X68kFloppyProfile("2DD (640KB)", 512, 2, 2, 1, 112, 1280, 0xFB, 2, PyFat.FAT_TYPE_FAT12),
    X68kFloppyProfile("2DD (720KB)", 512, 2, 2, 1, 112, 1440, 0xFC, 3, PyFat.FAT_TYPE_FAT12),
    X68kFloppyProfile("2HQ (1440KB)", 512, 1, 2, 1, 224, 2880, 0xFA, 9, PyFat.FAT_TYPE_FAT12),
)

X68K_DEFAULT_XDF_PROFILE = X68K_XDF_PROFILES[0]


def _clean_fs_path(path: str) -> str:
    p = PurePosixPath(path)
    if not str(p).startswith("/"):
        p = PurePosixPath("/") / p
    return str(p)


def _join_fs_path(base: str, name: str) -> str:
    if base == "/":
        return f"/{name}"
    return f"{base.rstrip('/')}/{name}"


def _looks_like_fat_boot_sector(buf: bytes) -> bool:
    if len(buf) < 512:
        return False
    if buf[510:512] != b"\x55\xaa":
        return False

    bps = int.from_bytes(buf[11:13], "little")
    spc = buf[13]
    reserved = int.from_bytes(buf[14:16], "little")
    fats = buf[16]
    total_16 = int.from_bytes(buf[19:21], "little")
    total_32 = int.from_bytes(buf[32:36], "little")

    if bps not in (512, 1024, 2048, 4096):
        return False
    if spc == 0 or spc > 128 or (spc & (spc - 1)) != 0:
        return False
    if reserved < 1:
        return False
    if fats not in (1, 2):
        return False
    if total_16 == 0 and total_32 == 0:
        return False
    return True


def detect_fat_offsets(image_path: Path, max_scan_bytes: int = 16 * 1024 * 1024) -> list[int]:
    file_size = image_path.stat().st_size
    scan_size = min(file_size, max_scan_bytes)
    offsets: list[int] = []

    with image_path.open("rb") as fp:
        block = fp.read(scan_size)

    for off in range(0, max(0, len(block) - 512), 512):
        sector = block[off : off + 512]
        if _looks_like_fat_boot_sector(sector):
            offsets.append(off)

    if 0 not in offsets:
        offsets.insert(0, 0)

    seen: set[int] = set()
    unique = []
    for off in offsets:
        if off not in seen:
            seen.add(off)
            unique.append(off)
    return unique


def detect_image_hint(image_path: Path) -> str:
    with image_path.open("rb") as fp:
        head = fp.read(4096)

    if b"X68000 HARD DISK IPL MENU" in head:
        return "x68000_ipl"
    if b"X68000 SCSI DISK IPL MENU" in head:
        return "x68000_scsi_ipl"
    return "unknown"


def _be16(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off : off + 2], "big")


def _be32(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off : off + 4], "big")


def _x68k_bpb_at(image_bytes: bytes, part_offset: int) -> dict[str, int] | None:
    if part_offset < 0 or part_offset + 0x24 >= len(image_bytes):
        return None

    bps = _be16(image_bytes, part_offset + 0x12)
    spc = image_bytes[part_offset + 0x14]
    fats = image_bytes[part_offset + 0x15]
    rsvd = _be16(image_bytes, part_offset + 0x16)
    root = _be16(image_bytes, part_offset + 0x18)
    tot16 = _be16(image_bytes, part_offset + 0x1A)
    media = image_bytes[part_offset + 0x1C]
    fatsz = image_bytes[part_offset + 0x1D]
    tot32 = _be32(image_bytes, part_offset + 0x1E)

    if bps not in (512, 1024, 2048, 4096):
        return None
    if spc == 0 or spc > 128 or (spc & (spc - 1)) != 0:
        return None
    if fats not in (1, 2):
        return None
    if rsvd == 0:
        return None
    if fatsz == 0:
        return None

    total_sectors = tot16 if tot16 != 0 else tot32
    if total_sectors == 0:
        return None

    return {
        "bytes_per_sector": bps,
        "sectors_per_cluster": spc,
        "fat_count": fats,
        "reserved_sectors": rsvd,
        "root_entries": root,
        "total_sectors": total_sectors,
        "media": media,
        "fat_sectors": fatsz,
    }


def detect_x68k_partition_candidates(image_path: Path) -> list[MountCandidate]:
    data = image_path.read_bytes()
    found: list[MountCandidate] = []

    # SASI style table
    if (
        len(data) >= 0x500
        and data[0x400:0x404] == b"X68K"
        and data[0x410:0x414] == b"Huma"
        and data[0x414:0x418] == b"n68k"
    ):
        for i in range(16):
            entry = 0x418 + i * 8
            if entry + 8 > len(data):
                break
            start_record = _be32(data, entry) & 0x00FFFFFF
            part_records = _be32(data, entry + 4)
            if start_record == 0 or part_records == 0:
                continue
            part_offset = start_record * 256
            bpb = _x68k_bpb_at(data, part_offset)
            if bpb is None:
                continue
            found.append(
                MountCandidate(
                    kind="x68k-be-bpb",
                    offset=part_offset,
                    label=f"X68K SASI part#{i + 1} @ 0x{part_offset:08X}",
                )
            )

    # SCSI style table
    if (
        len(data) >= 0x900
        and data[0x800:0x804] == b"X68K"
        and data[0x810:0x814] == b"Huma"
        and data[0x814:0x818] == b"n68k"
    ):
        for i in range(16):
            entry = 0x818 + i * 8
            if entry + 8 > len(data):
                break
            start_sector = _be32(data, entry) & 0x00FFFFFF
            part_sectors = _be32(data, entry + 4)
            if start_sector == 0 or part_sectors == 0:
                continue
            part_offset = start_sector * 1024
            bpb = _x68k_bpb_at(data, part_offset)
            if bpb is None:
                continue
            found.append(
                MountCandidate(
                    kind="x68k-be-bpb",
                    offset=part_offset,
                    label=f"X68K SCSI part#{i + 1} @ 0x{part_offset:08X}",
                )
            )

    uniq: list[MountCandidate] = []
    seen: set[tuple[str, int]] = set()
    for c in found:
        k = (c.kind, c.offset)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def detect_x68k_floppy_candidate(image_path: Path) -> MountCandidate | None:
    file_size = image_path.stat().st_size
    with image_path.open("rb") as fp:
        head = fp.read(512)

    # Check for X68000 IPL boot sector signature ("X68IPL30")
    # The X68000 68000 machine code and IPL signature are at the start:
    # 60 3c 90 | 58 36 38 49 50 4c 33 30  (IPL code | "X68IPL30")
    has_x68k_ipl = len(head) >= 11 and head[3:11] == b"X68IPL30"

    bpb = _x68k_bpb_at(head, 0)
    if bpb is None:
        # If BPB parsing failed but we have X68000 IPL signature, try to match by file size
        if not has_x68k_ipl:
            return None
        # Fall through to file-size matching below
    else:
        # Standard BPB parsing succeeded, match profile
        for profile in X68K_XDF_PROFILES:
            if file_size != profile.file_size:
                continue
            if bpb["bytes_per_sector"] != profile.bytes_per_sector:
                continue
            if bpb["sectors_per_cluster"] != profile.sectors_per_cluster:
                continue
            if bpb["fat_count"] != profile.fat_count:
                continue
            if bpb["reserved_sectors"] != profile.reserved_sectors:
                continue
            if bpb["root_entries"] != profile.root_entries:
                continue
            if bpb["total_sectors"] != profile.total_sectors:
                continue
            if bpb["media"] != profile.media:
                continue
            if bpb["fat_sectors"] != profile.fat_sectors:
                continue
            return MountCandidate(
                kind="x68k-be-bpb",
                offset=0,
                label=f"X68K floppy {profile.name} @ 0x00000000",
            )
        return None

    # If we reach here, either BPB parsing failed but X68000 IPL signature is present,
    # or we need to match by file size alone. This handles non-standard BPB layouts.
    if has_x68k_ipl:
        for profile in X68K_XDF_PROFILES:
            if file_size != profile.file_size:
                continue
            # Found a profile matching this file size and X68000 IPL signature
            return MountCandidate(
                kind="x68k-be-bpb",
                offset=0,
                label=f"X68K floppy {profile.name} @ 0x00000000 (IPL)",
            )

    return None


def _build_x68k_synthetic_boot_sector(raw_first_sector: bytes) -> bytes:
    out = bytearray(512)
    out[0:3] = b"\xEB\x3C\x90"
    out[3:11] = b"X68KFAT "

    bps = int.from_bytes(raw_first_sector[0x12:0x14], "big")
    spc = raw_first_sector[0x14]
    fats = raw_first_sector[0x15]
    rsvd = int.from_bytes(raw_first_sector[0x16:0x18], "big")
    root = int.from_bytes(raw_first_sector[0x18:0x1A], "big")
    tot16 = int.from_bytes(raw_first_sector[0x1A:0x1C], "big")
    media = raw_first_sector[0x1C]
    # pyfatfs rejects 0xF7 although X68000 SCSI images commonly use it.
    media_for_mount = 0xF8 if media == 0xF7 else media
    fatsz = raw_first_sector[0x1D]
    tot32_be = int.from_bytes(raw_first_sector[0x1E:0x22], "big")
    total = tot16 if tot16 != 0 else tot32_be

    out[0x0B:0x0D] = bps.to_bytes(2, "little")
    out[0x0D] = spc
    out[0x0E:0x10] = rsvd.to_bytes(2, "little")
    out[0x10] = fats
    out[0x11:0x13] = root.to_bytes(2, "little")

    if total <= 0xFFFF:
        out[0x13:0x15] = total.to_bytes(2, "little")
        out[0x20:0x24] = (0).to_bytes(4, "little")
    else:
        out[0x13:0x15] = (0).to_bytes(2, "little")
        out[0x20:0x24] = total.to_bytes(4, "little")

    out[0x15] = media_for_mount
    out[0x16:0x18] = fatsz.to_bytes(2, "little")
    out[0x18:0x1A] = (0).to_bytes(2, "little")
    out[0x1A:0x1C] = (0).to_bytes(2, "little")
    out[0x1C:0x20] = (0).to_bytes(4, "little")

    out[0x24] = 0x80
    out[0x25] = 0
    out[0x26] = 0x29
    out[0x27:0x2B] = (0x58463830).to_bytes(4, "little")
    out[0x2B:0x36] = b"X68K VOL   "
    out[0x36:0x3E] = b"FAT16   "
    out[510:512] = b"\x55\xAA"
    return bytes(out)


def _build_x68k_raw_boot_sector(profile: X68kFloppyProfile) -> bytes:
    out = bytearray(512)
    out[0:2] = b"\x60\x1C"
    out[2:16] = b"diskimage-x68k"
    out[0x12:0x14] = profile.bytes_per_sector.to_bytes(2, "big")
    out[0x14] = profile.sectors_per_cluster
    out[0x15] = profile.fat_count
    out[0x16:0x18] = profile.reserved_sectors.to_bytes(2, "big")
    out[0x18:0x1A] = profile.root_entries.to_bytes(2, "big")
    if profile.total_sectors <= 0xFFFF:
        out[0x1A:0x1C] = profile.total_sectors.to_bytes(2, "big")
        out[0x1E:0x22] = (0).to_bytes(4, "big")
    else:
        out[0x1A:0x1C] = (0).to_bytes(2, "big")
        out[0x1E:0x22] = profile.total_sectors.to_bytes(4, "big")
    out[0x1C] = profile.media
    out[0x1D] = profile.fat_sectors
    return bytes(out)


def _build_x68k_raw_boot_sector_from_fat_boot(raw_first_sector: bytes, media_byte: int) -> bytes:
    out = bytearray(512)
    out[0:2] = b"\x60\x1C"
    out[2:16] = b"diskimage-x68k"

    out[0x12:0x14] = raw_first_sector[0x0B:0x0D][::-1]
    out[0x14] = raw_first_sector[0x0D]
    out[0x15] = raw_first_sector[0x10]
    out[0x16:0x18] = raw_first_sector[0x0E:0x10][::-1]
    out[0x18:0x1A] = raw_first_sector[0x11:0x13][::-1]
    out[0x1A:0x1C] = raw_first_sector[0x13:0x15][::-1]
    out[0x1C] = media_byte
    out[0x1D] = raw_first_sector[0x16]
    out[0x1E:0x22] = raw_first_sector[0x20:0x24][::-1]
    return bytes(out)


def _fat_entry_size(fat_type: int) -> int:
    return 2 if fat_type == PyFat.FAT_TYPE_FAT16 else 3


def _initialize_empty_fat_tables(image: bytearray, fat_offset: int, fat_size_bytes: int, fat_count: int, media: int, fat_type: int) -> None:
    if fat_type == PyFat.FAT_TYPE_FAT16:
        init = bytes((media, 0xFF, 0xFF, 0xFF))
    else:
        init = bytes((media, 0xFF, 0xFF))

    for fat_index in range(fat_count):
        start = fat_offset + fat_index * fat_size_bytes
        image[start : start + len(init)] = init


class X68kFatAdapter(io.RawIOBase):
    def __init__(self, image_path: Path, partition_offset: int):
        super().__init__()
        self._fp = image_path.open("rb+")
        self._base = partition_offset
        self._pos = 0
        self._closed = False

        self._fp.seek(self._base)
        raw = self._fp.read(512)
        if len(raw) < 512:
            raw = raw + bytes(512 - len(raw))
        self._raw_first = bytearray(raw)
        self._raw_media_original = self._raw_first[0x1C]
        
        # Check if this is an X68000 IPL boot sector (non-standard BPB layout)
        # X68000 IPL files have "X68IPL30" signature at bytes 3-11
        self._is_x68k_ipl = len(raw) >= 11 and raw[3:11] == b"X68IPL30"
        
        if self._is_x68k_ipl:
            # For X68000 IPL XDF files, derive BPB from file size and known profiles
            profile = self._detect_profile_from_file_size()
            if profile:
                # Build a raw boot sector from the profile for reading BPB
                self._raw_first = bytearray(_build_x68k_raw_boot_sector(profile))
                self._raw_media_original = profile.media
            # else: fall back to reading BPB at standard offsets
        
        self._synth_first = bytearray(_build_x68k_synthetic_boot_sector(self._raw_first))
        self._fat_media_byte_offsets = self._build_fat_media_byte_offsets()

    def _detect_profile_from_file_size(self) -> X68kFloppyProfile | None:
        """Detect X68000 XDF profile by file size."""
        try:
            self._fp.seek(0, io.SEEK_END)
            file_size = self._fp.tell() - self._base
            
            for profile in X68K_XDF_PROFILES:
                if file_size == profile.file_size:
                    return profile
        except Exception:
            pass
        return None

    def _build_fat_media_byte_offsets(self) -> list[int]:
        bps = int.from_bytes(self._raw_first[0x12:0x14], "big")
        reserved = int.from_bytes(self._raw_first[0x16:0x18], "big")
        fat_count = self._raw_first[0x15]
        fat_sectors = self._raw_first[0x1D]
        if bps <= 0 or reserved <= 0 or fat_count <= 0 or fat_sectors <= 0:
            return []

        fat_size_bytes = fat_sectors * bps
        fat0 = reserved * bps
        return [fat0 + i * fat_size_bytes for i in range(fat_count)]

    def _enforce_fat_media_descriptor(self) -> None:
        # CRITICAL: For X68000 IPL files, do NOT modify any file system structures on disk.
        # The file system is read-only from the perspective of disk writes.
        if self._is_x68k_ipl:
            return
        
        if not self._fat_media_byte_offsets:
            return

        self._fp.seek(0, io.SEEK_END)
        end = max(0, self._fp.tell() - self._base)
        for off in self._fat_media_byte_offsets:
            if off < 0 or off >= end:
                continue
            self._fp.seek(self._base + off)
            self._fp.write(bytes((self._raw_media_original,)))

    def _sync_synth_to_raw(self) -> None:
        bps = int.from_bytes(self._synth_first[0x0B:0x0D], "little")
        spc = self._synth_first[0x0D]
        rsvd = int.from_bytes(self._synth_first[0x0E:0x10], "little")
        fats = self._synth_first[0x10]
        root = int.from_bytes(self._synth_first[0x11:0x13], "little")
        tot16 = int.from_bytes(self._synth_first[0x13:0x15], "little")
        media = self._synth_first[0x15]
        fatsz16 = int.from_bytes(self._synth_first[0x16:0x18], "little")

        self._raw_first[0x12:0x14] = bps.to_bytes(2, "big")
        self._raw_first[0x14] = spc
        self._raw_first[0x15] = fats
        self._raw_first[0x16:0x18] = rsvd.to_bytes(2, "big")
        self._raw_first[0x18:0x1A] = root.to_bytes(2, "big")
        self._raw_first[0x1A:0x1C] = tot16.to_bytes(2, "big")
        # Always preserve the original X68000 media byte on disk.
        self._raw_first[0x1C] = self._raw_media_original
        self._raw_first[0x1D] = fatsz16 & 0xFF

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = max(0, offset)
        elif whence == io.SEEK_CUR:
            self._pos = max(0, self._pos + offset)
        elif whence == io.SEEK_END:
            self._fp.seek(0, io.SEEK_END)
            end = max(0, self._fp.tell() - self._base)
            self._pos = max(0, end + offset)
        return self._pos

    def read(self, size: int = -1) -> bytes:
        self._fp.seek(0, io.SEEK_END)
        end = max(0, self._fp.tell() - self._base)
        if size is None or size < 0:
            size = max(0, end - self._pos)
        size = min(size, max(0, end - self._pos))

        out = bytearray()
        remain = size
        while remain > 0:
            if self._pos < 512:
                k = min(remain, 512 - self._pos)
                out.extend(self._synth_first[self._pos : self._pos + k])
                self._pos += k
                remain -= k
            else:
                self._fp.seek(self._base + self._pos)
                chunk = self._fp.read(remain)
                if not chunk:
                    break
                out.extend(chunk)
                self._pos += len(chunk)
                remain -= len(chunk)
        return bytes(out)

    def write(self, b: bytes) -> int:
        data = memoryview(b).tobytes()
        n = len(data)
        i = 0

        while i < n:
            if self._pos < 512:
                k = min(n - i, 512 - self._pos)
                seg = data[i : i + k]
                for rel, val in enumerate(seg):
                    idx = self._pos + rel
                    if 0 <= idx < 512:
                        self._synth_first[idx] = val

                self._pos += k
                i += k
            else:
                self._fp.seek(self._base + self._pos)
                w = self._fp.write(data[i:])
                if w is None:
                    w = 0
                self._pos += w
                i += w

        self._sync_synth_to_raw()
        
        # CRITICAL: For X68000 IPL XDF files, DO NOT write the boot sector back to disk.
        # The X68000 68000 machine code at bytes 0-2 and IPL signature are essential for bootability.
        # We only use the synthetic boot sector as a PyFat interface; actual file data lives beyond byte 512.
        if not self._is_x68k_ipl:
            self._fp.seek(self._base)
            self._fp.write(self._raw_first)
        
        self._enforce_fat_media_descriptor()
        return n

    def flush(self) -> None:
        if self._closed:
            return
        self._fp.flush()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.flush()
        finally:
            self._fp.close()
            self._closed = True
        super().close()


class FatImageBackend:
    _max_backups_per_image = 3

    def __init__(self) -> None:
        self.image_path: Path | None = None
        self.offset_candidates: list[int] = []
        self.mount_candidates: list[MountCandidate] = []
        self._offset_kind_map: dict[int, str] = {}
        self._offset_label_map: dict[int, str] = {}
        self.current_offset: int = 0
        self.fs: PyFatFS | None = None
        self._adapter: X68kFatAdapter | None = None
        self._mount_kind: str = "fat"
        self._backup_path: Path | None = None
        self._backup_done = False

    @property
    def backup_path(self) -> Path | None:
        return self._backup_path

    def close(self) -> None:
        if self.fs is not None:
            self.fs.close()
            self.fs = None
        self._adapter = None

    def unmount(self) -> None:
        self.close()
        self.image_path = None
        self.offset_candidates = []
        self.mount_candidates = []
        self._offset_kind_map = {}
        self._offset_label_map = {}
        self.current_offset = 0
        self._mount_kind = "fat"
        self._backup_path = None
        self._backup_done = False

    def get_offset_label(self, offset: int) -> str:
        return self._offset_label_map.get(offset, f"{offset} (0x{offset:08X})")

    def create_backup_now(self) -> Path:
        self._ensure_backup()
        if self._backup_path is None:
            raise ImageMountError("Backup creation failed")
        return self._backup_path

    def _mount_with_kind(self, image_path: Path, offset: int, kind: str) -> None:
        if kind == "x68k-be-bpb":
            self._adapter = X68kFatAdapter(image_path, offset)
            self.fs = PyFatBytesIOFS(
                fp=self._adapter,
                offset=0,
                preserve_case=True,
                lazy_load=True,
            )
        else:
            self.fs = PyFatFS(
                filename=str(image_path),
                offset=offset,
                preserve_case=True,
                read_only=False,
                lazy_load=True,
            )
        self.current_offset = offset
        self._mount_kind = kind

    def mount(self, image_file: str | Path) -> None:
        image_path = Path(image_file)
        if not image_path.exists():
            raise ImageMountError(f"Image not found: {image_path}")

        self.close()
        self.image_path = image_path
        image_hint = detect_image_hint(image_path)
        self.offset_candidates = []
        self.mount_candidates = []
        self._offset_kind_map = {}
        self._offset_label_map = {}

        floppy_candidate = detect_x68k_floppy_candidate(image_path)
        fat_candidates: list[MountCandidate] = []
        x68k_candidates = detect_x68k_partition_candidates(image_path)

        fat_offsets = detect_fat_offsets(image_path)
        for off in fat_offsets:
            fat_candidates.append(MountCandidate(kind="fat", offset=off, label=f"FAT @ 0x{off:08X}"))

        # Prefer native X68000 mappings for hard disk images and floppy images.
        suffix = image_path.suffix.lower()
        if suffix in (".hds", ".hdf") and x68k_candidates:
            self.mount_candidates.extend(x68k_candidates)
            self.mount_candidates.extend(fat_candidates)
        elif suffix in (".xdf", ".2hd", ".2dd"):
            if floppy_candidate is not None:
                self.mount_candidates.append(floppy_candidate)
            self.mount_candidates.extend(fat_candidates)
        else:
            if floppy_candidate is not None:
                self.mount_candidates.append(floppy_candidate)
            self.mount_candidates.extend(fat_candidates)
            self.mount_candidates.extend(x68k_candidates)

        for c in self.mount_candidates:
            if c.offset not in self.offset_candidates:
                self.offset_candidates.append(c.offset)
                self._offset_kind_map[c.offset] = c.kind
                self._offset_label_map[c.offset] = c.label
                continue

            # If both FAT and X68000 candidates point to the same offset,
            # keep the X68000 label/kind so remount uses the adapter path.
            old_kind = self._offset_kind_map.get(c.offset)
            if old_kind == "fat" and c.kind != "fat":
                self._offset_kind_map[c.offset] = c.kind
                self._offset_label_map[c.offset] = c.label

        if 0 not in self._offset_kind_map:
            self._offset_kind_map[0] = "fat"
            self._offset_label_map[0] = "FAT @ 0x00000000"

        self._backup_path = None
        self._backup_done = False

        mounted = False
        errors: list[str] = []
        for c in self.mount_candidates:
            try:
                self._mount_with_kind(image_path, c.offset, c.kind)
                mounted = True
                break
            except Exception as exc:
                errors.append(f"{c.label}: {exc}")
                if self._adapter is not None:
                    self._adapter.close()
                    self._adapter = None

        if not mounted:
            hint = ""
            if image_hint == "x68000_ipl":
                hint = (
                    "\nHint: This image contains X68000 IPL data and is likely not a plain FAT volume. "
                    "Tried native X68000 partition mapping as well, but mount still failed."
                )
            raise ImageMountError(
                "Could not mount FAT filesystem. Tried offsets: "
                + ", ".join(str(x) for x in self.offset_candidates)
                + "\n"
                + "\n".join(errors)
                + hint
            )

    def remount_at_offset(self, offset: int) -> None:
        if self.image_path is None:
            raise ImageMountError("No image is mounted")

        kind = self._offset_kind_map.get(offset, "fat")
        self.close()
        self._mount_with_kind(self.image_path, offset, kind)

    def _require_fs(self) -> PyFatFS:
        if self.fs is None:
            raise ImageMountError("No image is mounted")
        return self.fs

    def _ensure_backup(self) -> None:
        if self._backup_done:
            return
        if self.image_path is None:
            raise ImageMountError("No image is mounted")

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = self.image_path.with_suffix(self.image_path.suffix + f".bak-{ts}")
        shutil.copy2(self.image_path, bak)
        self._prune_old_backups(self.image_path)
        self._backup_done = True
        self._backup_path = bak

    def _prune_old_backups(self, image_path: Path) -> None:
        pattern = f"{image_path.name}.bak-*"
        backups = [p for p in image_path.parent.glob(pattern) if p.is_file()]
        backups.sort(key=lambda p: p.name, reverse=True)

        for old in backups[self._max_backups_per_image :]:
            try:
                old.unlink()
            except OSError:
                # Keep processing remaining files even if one deletion fails.
                continue

    def _is_dir(self, path: str) -> bool:
        fs = self._require_fs()
        info = fs.getinfo(path, namespaces=["details"])
        return info.is_dir

    def list_dir(self, dir_path: str = "/") -> list[ImageEntry]:
        fs = self._require_fs()
        dpath = _clean_fs_path(dir_path)
        names = fs.listdir(dpath)
        out: list[ImageEntry] = []
        for name in sorted(names, key=str.lower):
            child = _join_fs_path(dpath, name)
            info = fs.getinfo(child, namespaces=["details"])
            details = info.raw.get("details", {})
            size = int(details.get("size", 0))
            modified = details.get("modified")
            if hasattr(modified, "isoformat"):
                mod_text = modified.isoformat(sep=" ", timespec="seconds")
            elif isinstance(modified, (int, float)):
                mod_text = datetime.fromtimestamp(modified).isoformat(sep=" ", timespec="seconds")
            else:
                mod_text = ""

            out.append(
                ImageEntry(
                    path=child,
                    name=name,
                    is_dir=info.is_dir,
                    size=size,
                    modified=mod_text,
                )
            )
        return out

    def import_local_path(self, local_path: Path, dest_dir: str) -> None:
        fs = self._require_fs()
        self._ensure_backup()
        target_dir = _clean_fs_path(dest_dir)

        if local_path.is_dir():
            dst = _join_fs_path(target_dir, local_path.name)
            fs.makedir(dst, recreate=True)
            for child in local_path.iterdir():
                self.import_local_path(child, dst)
            return

        target_file = _join_fs_path(target_dir, local_path.name)
        with local_path.open("rb") as src, fs.openbin(target_file, "w") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)

    def replace_file(self, fs_file_path: str, local_file: Path) -> None:
        fs = self._require_fs()
        target = _clean_fs_path(fs_file_path)
        if self._is_dir(target):
            raise ImageMountError("Cannot replace a directory with file content")

        self._ensure_backup()
        with local_file.open("rb") as src, fs.openbin(target, "w") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)

    def create_dir(self, fs_dir_path: str) -> None:
        fs = self._require_fs()
        self._ensure_backup()
        fs.makedir(_clean_fs_path(fs_dir_path), recreate=False)

    def create_empty_file(self, fs_file_path: str) -> None:
        fs = self._require_fs()
        self._ensure_backup()
        with fs.openbin(_clean_fs_path(fs_file_path), "w"):
            pass

    def delete_paths(self, paths: Iterable[str]) -> None:
        fs = self._require_fs()
        self._ensure_backup()

        for p in paths:
            cp = _clean_fs_path(p)
            if self._is_dir(cp):
                fs.removetree(cp)
            else:
                fs.remove(cp)

    def read_file_bytes(self, fs_file_path: str) -> bytes:
        fs = self._require_fs()
        with fs.openbin(_clean_fs_path(fs_file_path), "r") as fp:
            return fp.read()

    def write_file_bytes(self, fs_file_path: str, data: bytes) -> None:
        fs = self._require_fs()
        target = _clean_fs_path(fs_file_path)
        if self._is_dir(target):
            raise ImageMountError("Cannot write bytes to a directory")

        self._ensure_backup()
        with fs.openbin(target, "w") as fp:
            fp.write(data)

    def export_path_to_local(self, fs_path: str, local_target: Path) -> None:
        fs = self._require_fs()
        src = _clean_fs_path(fs_path)

        if self._is_dir(src):
            local_target.mkdir(parents=True, exist_ok=True)
            for entry in self.list_dir(src):
                self.export_path_to_local(entry.path, local_target / entry.name)
            return

        local_target.parent.mkdir(parents=True, exist_ok=True)
        with fs.openbin(src, "r") as src_fp, local_target.open("wb") as dst_fp:
            shutil.copyfileobj(src_fp, dst_fp, length=1024 * 1024)
