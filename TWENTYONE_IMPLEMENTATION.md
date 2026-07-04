# TwentyOne File Name Extension - Implementation Plan

## Overview
Support X68000 TwentyOne format: 21-character file names (18 + 3 extension)
- Main name: up to 18 characters
- Extension: up to 3 characters (after last period)
- Multiple periods supported (e.g., foo.tar.gz)

## File Name Format
```
<name1+name2>.<ext>
where:
  name1+name2 = up to 18 characters (split as 8 + 10 in FAT entries)
  ext = 0-3 characters
```

## Storage in FAT Directory Entry
Structure from TwentyOne source:
```c
struct {
  unsigned char primary[8];       // First 8 chars
  unsigned char secondary[10];    // Additional 10 chars
  unsigned char extendary[3];     // Extension (up to 3 chars)
}
```

## Implementation Approach

### Option 1: Custom FAT Entry Handler (RECOMMENDED)
- Override PyFatFS file name handling
- Store 18-char name + 3-char extension
- Preserve TwentyOne format when reading/writing
- Maintain backward compatibility with standard FAT

### Option 2: Native PyFatFS Support
- Check if PyFatFS already supports extended naming
- Minimal code changes if available
- May require checking PyFatFS version/configuration

### Option 3: LFN-Style Multiple Entries
- Use extended directory entries (like Windows LFN)
- TwentyOne driver would handle translation
- More complex but potentially more compatible

## Key Challenges

1. **PyFatFS Compatibility**: Need to verify if/how PyFatFS handles TwentyOne format
2. **LFN Conflicts**: Standard FAT uses LFN for long names - avoid conflicts
3. **Backward Compatibility**: Ensure standard FAT files still work
4. **GUI Integration**: 21-character file name input in UI

## Implementation Phases

### Phase 1: Research & Documentation
- [ ] Analyze TwentyOne source code in detail
- [ ] Verify FAT entry structure used by TwentyOne
- [ ] Test PyFatFS behavior with TwentyOne files
- [ ] Document exact format specification

### Phase 2: Backend Support
- [ ] Create TwentyOne file name handler class
- [ ] Implement name splitting logic (8+10+3)
- [ ] Add validation for TwentyOne format
- [ ] Update backend.py with TwentyOne support

### Phase 3: GUI Integration
- [ ] Add 21-character file name input field
- [ ] Implement real-time validation
- [ ] Show name format split (8/10 + 3)
- [ ] Display warnings for standard FAT limitations

### Phase 4: Testing & Refinement
- [ ] Create test cases for various file names
- [ ] Verify compatibility with XEiJ
- [ ] Test round-trip (create/read/modify)
- [ ] Performance testing with large directories

## Files to Modify

### Backend
- `src/diskimage_explorer_x68k/backend.py` - Add TwentyOne handler
- `src/diskimage_explorer_x68k/xdf_fat.py` - Or use existing custom FAT support

### GUI (if needed)
- `src/diskimage_explorer_x68k/main.py` - File creation dialog
- Update file name input validation

## TwentyOne Source Code Reference
- Location: `/Users/taknakam/X68000/XEiJ_BOOT/tmp/TW136C14/Source/`
- Key files:
  - `namecheck.h/c` - Name parsing logic
  - `vfat.h/c` - VFAT support (VTwentyOne)
  - `filenames.doc` - Format specification

## Critical Questions Remaining

1. How does TwentyOne store 18-char names in standard FAT entries?
   - Does it use reserved fields in directory entry?
   - Does it use multiple entries like LFN?
   - What's the exact byte layout?

2. Can PyFatFS read/write TwentyOne files without modification?

3. What happens when TwentyOne files are accessed on standard FAT systems?

4. Are there any conflicts with other naming extensions (LFN, VFAT)?

## Next Action
Investigate TwentyOne source code to understand exact FAT entry structure and storage mechanism.
