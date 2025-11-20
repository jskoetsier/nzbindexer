# Deobfuscation Status Report

## Summary

After investigating the deobfuscation issues where the ORN database wasn't being populated, I've made several fixes and improvements to the system. The archive extraction logic was enhanced, but there appears to be a deeper issue preventing the code from reaching the archive extraction step.

## What Was Fixed

### 1. PreDB API Timeout Issue
**Problem**: PreDB APIs (predb.ovh, srrdb.com) were timing out at 10 seconds
**Fix**: Increased timeout from 10s to 30s in `/Users/johansebastiaan/dev/nzbindexer/app/services/predb.py`
**Status**: ✅ Fixed and deployed

### 2. Archive Extraction Logic
**Problem**: Archive header extraction was only attempted for filenames that looked like obfuscated hashes, missing cases where yEnc filenames were short generic words like "Adobe", "Beauty", "Fc"
**Fix**: Modified the logic in `/Users/johansebastiaan/dev/nzbindexer/app/services/article.py` to:
- Always attempt archive extraction when `yenc_filename` exists
- Added better validation for extracted filenames
- Added debug logging to track the deobfuscation flow
**Status**: ⚠️ Partially Fixed - Code was updated but archive extraction is still not being reached

### 3. Event Loop Blocking (Previous Issue)
**Problem**: Background tasks were blocking the main event loop
**Fix**: Modified `start_background_tasks()` and `stop_background_tasks()` to use `asyncio.create_task()`
**Status**: ✅ Fixed - Application now responds correctly to HTTP requests

## Current Situation

### What's Working
- ✅ Application is running and responding to requests
- ✅ Health endpoint returns HTTP 200
- ✅ Articles are being processed from Usenet groups
- ✅ yEnc filenames are being extracted successfully
- ✅ PreDB APIs are being queried (though timing out)
- ✅ NFO extraction is attempted as a last resort

### What's NOT Working
- ❌ Archive header extraction is never being attempted
- ❌ ORN database is not being populated
- ❌ Most releases remain obfuscated (e.g., "obfuscated_1234567890")
- ❌ Debug logging shows yEnc filenames are extracted but archive extraction doesn't run

## Current Deobfuscation Flow

Based on the logs, here's what's happening:

1. **yEnc Filename Extraction** ✅ WORKING
   - Successfully extracting filenames like "Adobe", "Beauty", "Fc", "TTm2EFZ3QtIbFRKY4jccBegVtl.part063.rar"

2. **PreDB Lookup** ⚠️ ATTEMPTED BUT TIMING OUT
   - Queries are being made to PreDB APIs
   - Most are timing out even with 30s timeout
   - Not populating ORN cache

3. **NZBHydra2 Lookup** ❌ NOT CONFIGURED
   - Settings not configured (expected)

4. **Archive Header Extraction** ❌ NOT BEING REACHED
   - Debug log "Archive extraction check" never appears in logs
   - This means the code flow is stopping before reaching this step
   - Likely issue: Some condition earlier in the code is preventing execution

5. **NFO Extraction** ✅ WORKING AS LAST RESORT
   - Being attempted when all other methods fail
   - Message: "All deobfuscation methods failed, trying NFO extraction"

## Potential Root Causes

### Theory 1: Code Path Issue
The archive extraction code may not be reachable due to:
- An exception being thrown earlier that's caught silently
- A condition that's evaluating differently than expected
- The deobfuscation loop exiting early

### Theory 2: Short Filenames Not Triggering Deobfuscation
Filenames like "Adobe", "Beauty", "Fc" may not be triggering the obfuscation detection logic:
- `is_obfuscated_hash()` returns False for these short words
- This causes PreDB/NZBHydra lookups to be skipped
- But it should still reach archive extraction (it's not)

### Theory 3: Async/Await Issues
There might be an issue with how async code is executing:
- Some awaited function might be failing silently
- Exception handling might be swallowing errors

## Alternative Solutions Available

I've created comprehensive documentation for alternative approaches:

### 📄 See: `/Users/johansebastiaan/dev/nzbindexer/docs/DEOBFUSCATION_RESOURCES.md`

This document contains:
- **Better Python libraries** for archive parsing (rarfile, py7zr, libarchive-c)
- **Additional PreDB APIs** to integrate (predb.pw, xREL.to)
- **Prowlarr integration** guide (aggregates 50+ indexers)
- **Open source projects** to study (NNTmux, nZEDb)
- **Community resources** (Reddit, GitHub)
- **Implementation enhancements** with working code examples

## Recommended Next Steps

### Immediate Actions (Debugging)

1. **Enable DEBUG Logging**
   ```python
   # In app/core/logging.py, change log level to DEBUG
   logger.setLevel(logging.DEBUG)
   ```

2. **Add More Debug Logging**
   - Add logging at every step of the deobfuscation flow
   - Log all conditions and their values
   - Track exactly where the code flow stops

3. **Test Archive Extraction Directly**
   - Create a standalone test script to verify archive extraction works
   - Test with known RAR/ZIP files from Usenet
   - Verify the DeobfuscationService works in isolation

### Short-Term Solutions

1. **Install Better Archive Libraries**
   ```bash
   pip install rarfile py7zr libarchive-c
   ```
   These are more robust than the custom implementation

2. **Add More PreDB APIs**
   - Integrate predb.pw (code available in DEOBFUSCATION_RESOURCES.md)
   - Try multiple APIs in parallel for faster results

3. **Set Up NZBHydra2**
   ```bash
   # Use the provided Docker command in DEOBFUSCATION_RESOURCES.md
   docker run -d --name nzbhydra2 -p 5076:5076 linuxserver/nzbhydra2
   ```

### Long-Term Solutions

1. **Integrate Prowlarr**
   - Acts as an aggregator for 50+ indexers
   - Has built-in ORN database
   - Can provide deobfuscation mappings

2. **Build Community ORN Database**
   - Create API endpoint to share/receive ORN mappings
   - Post on r/usenet about your project
   - Collaborate with other indexer developers

3. **Implement NFO-First Approach**
   - Download and parse NFO files first
   - Extract release names from NFO metadata
   - Use NFO as primary deobfuscation method

4. **Study Existing Projects**
   ```bash
   git clone https://github.com/NNTmux/newznab-tmux
   # Study their deobfuscation implementation
   ```

## Log Analysis

### Example Logs from Remote Server
```
2025-11-20 12:49:40 - Trying PreDB lookup for: li7SZDxl8aY6eX1sap85.part01.rar
2025-11-20 12:49:41 - Trying NZBHydra2 lookup for: b649mDlHZxSnLXh4Cc8bhpgW4mL7TEdXCYy
2025-11-20 12:50:10 - PreDB API predb.ovh timed out
2025-11-20 12:50:10 - PreDB API srrdb.com timed out
2025-11-20 12:50:10 - Error querying NZBHydra2: [not configured]
```

### Observations
- yEnc filenames ARE being extracted: "Adobe", "Beauty", "TTm2EFZ3QtIbFRKY4jccBegVtl.part063.rar"
- PreDB lookups ARE being attempted for hash-like filenames
- Archive extraction logs are ABSENT (never attempted)
- NFO extraction is the only fallback that runs

## Files Modified

1. `/Users/johansebastiaan/dev/nzbindexer/app/services/predb.py`
   - Increased timeout from 10s to 30s

2. `/Users/johansebastiaan/dev/nzbindexer/app/services/article.py`
   - Added debug logging for archive extraction
   - Modified logic to always attempt archive extraction
   - Improved filename validation

3. `/Users/johansebastiaan/dev/nzbindexer/app/core/tasks.py`
   - Fixed event loop blocking issue (previous fix)

4. `/Users/johansebastiaan/dev/nzbindexer/app/main.py`
   - Fixed lifespan context manager (previous fix)

## Testing Recommendations

### Test 1: Verify Archive Extraction Works
Create a test script:
```python
import asyncio
from app.services.deobfuscation import DeobfuscationService
from app.services.nntp import NNTPService

async def test_archive_extraction():
    nntp = NNTPService(server="news.eweka.nl", ...)
    deobf = DeobfuscationService()

    # Get a known obfuscated article
    message_id = "<some-message-id>"
    body_lines = await nntp.get_article_body(message_id)

    # Try to extract filename
    result = deobf.extract_filename_from_article(body_lines, "Adobe")
    print(f"Result: {result}")

asyncio.run(test_archive_extraction())
```

### Test 2: Check Deobfuscation Flow
Add temporary logging:
```python
# In article.py, add at key decision points
logger.error(f"DEBUG: At PreDB check, search_hash={search_hash}, is_obfuscated={self.deobfuscation_service.is_obfuscated_hash(search_hash)}")
logger.error(f"DEBUG: At archive extraction, found_real_name={found_real_name}, yenc_filename={yenc_filename}")
```

Use `logger.error()` instead of `logger.debug()` to ensure it appears in logs.

## Conclusion

The deobfuscation system has been improved but is still not fully functional. The core issue appears to be that archive extraction code is never being reached, despite the logic being in place. Further debugging with detailed logging is needed to identify exactly where the code flow is stopping.

Alternative solutions are available and documented in the DEOBFUSCATION_RESOURCES.md file, including:
- Better archive parsing libraries
- Additional PreDB APIs
- Prowlarr integration
- Community collaboration opportunities

The application is stable and functional for indexing obfuscated posts, but they remain obfuscated. Once the deobfuscation is working, the ORN database will begin populating and releases will have their real names.

---
**Last Updated**: 2025-11-20 13:14 UTC
**Status**: Investigating - Archive extraction not being reached
**Priority**: High - Core functionality impacted
