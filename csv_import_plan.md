# CSV Workout Name Import for FIT Upload Page

## Context

FIT files from Garmin devices don't contain user-defined session names — the upload feature auto-generates names like "Morning Run". Many users name their sessions in Garmin Connect or other tools, and that data is exportable as CSV. This feature lets users optionally upload a CSV with workout names and match them to the parsed FIT workouts before importing into the database.

## User Flow

1. User selects `.fit` files → preview table appears (existing)
2. User clicks **"Import names from CSV"** button (new, appears alongside Upload button)
3. User selects a `.csv` file
4. **Modal dialog** opens with 3 fields:
   - **Name column** — `<select>` populated from CSV headers, pre-selects "Name" if found
   - **Datetime column** — `<select>` populated from CSV headers, pre-selects "Date" if found
   - **UTC offset** — `<input type="number">`, pre-filled from browser's timezone offset (e.g. `2` for CEST)
5. User clicks **Apply** → CSV datetimes converted to UTC, matched to FIT workouts by exact `HH:MM:SS` (±1 second tolerance), preview table re-renders with matched names
6. Status message: "Matched X of Y CSV rows to Z workouts"
7. User clicks **Upload** → names included in API payload

## Design Decisions

- **Matching**: Exact `HH:MM:SS` match with ±1 second tolerance. Round sub-second precision to nearest second. Each FIT workout matches at most one CSV row and vice versa. Unmatched workouts keep auto-generated names.
- **Delimiter**: Auto-detect comma vs semicolon by sniffing the first line of the CSV.
- **UTC offset default**: Pre-filled from `new Date().getTimezoneOffset()` (browser's current offset). User can override.
- **Modal**: Native `<dialog>` element — Pico CSS provides styling out of the box. First modal in the codebase.

## Files to Modify

### 1. `workouts/templates/workouts/upload_workouts.html`

Add to `#upload-actions` div (line 43-45):
- A `<label>` styled as a secondary button + hidden `<input type="file" id="csv-file-input" accept=".csv">`
- Place before the existing Upload button

Add after `#upload-actions` div, inside `#upload-container`:
- A `<dialog id="csv-dialog">` with `<article>` wrapper (Pico pattern):
  - `<header>` with close button + title "CSV Column Mapping"
  - Two `<select>` elements for column selection (empty — populated by JS)
  - One `<input type="number" step="0.5">` for UTC offset
  - `<footer>` with Cancel (secondary) and Apply (primary) buttons

### 2. `workouts/static/workouts/js/fit_upload.js`

All additions inside the existing `if (container)` block:

**New DOM references** (after line 18):
- `csvFileInput`, `csvDialog`, `csvNameCol`, `csvDatetimeCol`, `csvUtcOffset`, `csvDialogApply`, `csvDialogCancel`, `csvDialogClose`

**`detectDelimiter(firstLine)`** helper:
- Count commas vs semicolons in the first line
- Return whichever has more occurrences (tie → comma)

**`parseCSV(text)`** helper:
- Detect delimiter from first line
- Split into lines (`/\r?\n/`), filter empty
- Parse headers from first line (split by delimiter, trim, strip quotes)
- Parse each data line into an object keyed by headers
- Handle quoted fields containing the delimiter (RFC 4180 character-by-character parser, parameterized by delimiter)
- Return `{ headers: string[], rows: object[] }`

**`matchCSVToWorkouts(csvRows, nameCol, datetimeCol, utcOffsetHours)`**:
- For each CSV row: parse datetime, subtract UTC offset to get UTC, round to nearest second
- For each CSV entry: iterate `parsedWorkouts`, find exact HH:MM:SS match (±1 sec tolerance = ≤1000ms absolute difference)
- Track matched workout indices in a `Set` to prevent double-matching
- Update `parsedWorkouts[i]._display.name` for matches
- Return `{ matchCount, csvTotal }`

**CSV file input `change` handler**:
- Read file via `file.text()`
- Call `parseCSV()`
- Populate both `<select>` elements from `csvData.headers`
- Pre-select "Name"/"Date" headers (case-insensitive) if found
- Set UTC offset default from `-(new Date().getTimezoneOffset() / 60)` (getTimezoneOffset returns minutes, inverted sign)
- Call `csvDialog.showModal()`
- Reset file input value (so re-selecting same file triggers `change`)

**Dialog Apply handler**:
- Read form values
- Call `matchCSVToWorkouts()`
- Close dialog
- Call `renderPreview()` to refresh table
- Show status with match count via existing `showStatus()`

**Dialog Cancel/Close handlers**: `csvDialog.close()`

**Modify upload payload** (line 254):
```js
// Before:
const payload = parsedWorkouts.map(({ _display, ...rest }) => rest);
// After:
const payload = parsedWorkouts.map(({ _display, ...rest }) => ({
  ...rest,
  name: _display.name,
}));
```

### 3. `workouts/views.py`

**`_validate_item()`** (around line 389-401):
- Accept optional `name` field from the payload
- Validate: if present, must be a non-empty string, max 255 chars
- Pass through in the returned dict: `"name": item.get("name")`

**`_create_workout()`** (lines 415-418):
- Use provided name if truthy, fall back to auto-generated:
```python
name = parsed.get("name") or (
    f"{_time_of_day(start_time.hour)} "
    f"{_UPLOAD_SPORT_LABELS.get(subtype_enum, 'Workout')}"
)
```

### 4. `workouts/tests/test_views.py`

Add to `UploadWorkoutsAPITest`:
- `test_custom_name_accepted` — POST with `"name": "Tempo Run"`, assert `workout.name == "Tempo Run"`
- `test_name_fallback_when_absent` — POST without `name`, assert auto-generated name (existing `test_auto_name_time_of_day` also covers this)
- `test_name_fallback_when_empty` — POST with `"name": ""`, assert fallback to auto-generated
- `test_name_too_long` — POST with 256-char name, assert error in response
- `test_name_non_string` — POST with `"name": 42`, assert error

### 5. `workouts/assets/scss/workouts.scss`

Add after line 107:
```scss
#upload-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
}
```

Remind user to verify SCSS compiler has recompiled after edits.

## Implementation Order

1. Backend: update `_validate_item` and `_create_workout` in `views.py` to accept optional `name`
2. Tests: add API tests for the `name` field
3. Run tests to verify backend changes
4. Template: add CSV input + `<dialog>` to `upload_workouts.html`
5. SCSS: add `#upload-actions` flex layout
6. JavaScript: add all CSV logic to `fit_upload.js`
7. Manual end-to-end test in browser

## Verification

1. `uv run python manage.py test workouts.tests.test_views.UploadWorkoutsAPITest` — all existing + new tests pass
2. `uv run python manage.py test` — full suite green
3. `uv run black .` + `uv run pylint workouts/` — clean
4. Manual browser test:
   - Upload FIT files → preview appears
   - Click "Import names from CSV" → select CSV → modal opens with headers in dropdowns
   - Verify UTC offset pre-filled from browser
   - Click Apply → preview names update for matched rows, status shows match count
   - Click Upload → workouts created with CSV names
   - Upload without CSV → auto-generated names still work
