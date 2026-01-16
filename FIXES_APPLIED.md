# e-flow - Fixed Issues Summary

**Date:** January 16, 2026

## Problems Fixed

### ✅ Issue 1: No Site/Device Selection Available
**Problem:** The dashboard had no devices to select because they weren't being initialized in the database.

**Solution:**
- Modified `app.py` to automatically initialize devices from `config.py` on startup using `@st.cache_resource`
- Devices are now created in the database when the dashboard first loads
- Improved error messages to show expected devices if none are found

### ✅ Issue 2: Data Not Being Extracted from Website
**Problem:** The scraper couldn't extract depth, velocity, and flow values from the USRIOT dashboard website.

**Solution:**
- Rewrote `extract_data_from_page()` in `scraper.py` with multiple data extraction methods:
  1. JavaScript window object inspection
  2. Regex pattern matching on page text
  3. DOM element searching with data attributes
- Added `import re` for robust pattern matching
- Increased wait time from 2000ms to 3000ms for better page loading

**New extraction methods:**
- Pattern `(?:depth|D)[\s:]*(\d+\.?\d*)\s*(?:mm|m)` for depth values
- Pattern `(?:velocity|V)[\s:]*(\d+\.?\d*)\s*(?:m/s|mps|m)` for velocity values  
- Pattern `(?:flow|F)[\s:]*(\d+\.?\d*)\s*(?:L/s|lps|l/s)` for flow values

### ✅ Issue 3: Data Recording Interval & Parsing
**Problem:** Monitor.py had placeholder code (0.0 values) and didn't properly parse extracted values.

**Solution:**
- Updated `monitor.py` check_for_updates() to:
  - Actually parse extracted float values from the scraper
  - Only store measurements if at least one value was successfully extracted
  - Handle both direct float values and string values with units
  - Log extracted values for debugging
  - Only record if data changes from the previous reading

### ✅ Issue 4: 1-Minute Recording Interval
**Problem:** Config was set to record every 60 seconds, but wasn't explicitly documented.

**Solution:**
- Confirmed `MONITOR_INTERVAL = 60` in `config.py`
- Increased `SCRAPER_WAIT_AFTER_LOAD` from 2000ms to 3000ms for better stability
- Updated documentation in `RUNNING.md`

## Files Modified

1. **app.py**
   - Added device initialization via `@st.cache_resource`
   - Improved device selector UI
   - Better error messages

2. **scraper.py**
   - Added `import re` for pattern matching
   - Completely rewrote `extract_data_from_page()` with 3 extraction methods
   - Better logging for debugging

3. **monitor.py**
   - Rewrote `check_for_updates()` to properly parse values
   - Handle None values gracefully
   - Only store if data was actually extracted
   - Added detailed logging

4. **config.py**
   - Increased `SCRAPER_WAIT_AFTER_LOAD` from 2000 to 3000ms
   - Added comments about the 1-minute interval

## New Files

1. **test_extraction.py**
   - Test script to verify data extraction works
   - Run with: `python test_extraction.py`
   - Shows extracted values and tests storage

2. **RUNNING.md**
   - Complete guide on how to run the system
   - Instructions for both monitor and dashboard
   - Troubleshooting tips

## How It Works Now

1. **Dashboard startup** (`app.py`):
   ```
   Load → Initialize devices from config → Create in database → Show selector
   ```

2. **Monitor service** (`monitor.py`):
   ```
   Every 60 seconds:
     → Fetch website
     → Extract depth/velocity/flow
     → Parse values from text/JSON
     → Store if changed
     → Log results
   ```

3. **Data flow**:
   ```
   Website → Scraper (extract) → Monitor (parse) → Database → Dashboard (display)
   ```

## Testing the Fix

### Quick Test
```bash
python test_extraction.py
```

### Full Test
1. Terminal 1: `python monitor.py`
2. Terminal 2: `streamlit run app.py`
3. Open dashboard, select device, see data appear

## Expected Behavior

✅ Monitor runs every 1 minute
✅ Extracts depth (mm), velocity (m/s), flow (L/s)
✅ Only stores data when values change
✅ Dashboard shows device in selector immediately
✅ Charts update as new data arrives
✅ Can export as CSV/JSON

## Configuration

To change settings, edit `config.py`:
- `MONITOR_INTERVAL = 60` - Change recording interval
- `MONITOR_URL` - Change target website
- `DEVICES` - Add/remove devices
- `SCRAPER_WAIT_AFTER_LOAD` - Adjust for slower pages

## Next Steps (Optional Enhancements)

- [ ] Add multiple device support
- [ ] Add user authentication
- [ ] Add alerts for abnormal values
- [ ] Add data aggregation/statistics
- [ ] Add mobile app support
- [ ] Add SMS/email notifications
