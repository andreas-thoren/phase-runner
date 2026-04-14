// ---------------------------------------------------------------------------
// FIT file upload module — parses .fit files client-side and POSTs to the
// Django upload API. Loaded as type="module" on the upload page.
// ---------------------------------------------------------------------------

const container = document.getElementById("upload-container");
if (container) {
  const sdkUrl = container.dataset.sdkUrl;
  const uploadUrl = container.dataset.uploadUrl;
  const csrfToken = container.dataset.csrfToken;

  const fileInput = document.getElementById("fit-file-input");
  const parseStatus = document.getElementById("parse-status");
  const previewFigure = document.getElementById("preview-figure");
  const previewBody = document.getElementById("preview-body");
  const uploadActions = document.getElementById("upload-actions");
  const uploadBtn = document.getElementById("upload-btn");
  const uploadResults = document.getElementById("upload-results");

  const csvImportBtn = document.getElementById("csv-import-btn");
  const csvFileInput = document.getElementById("csv-file-input");
  const csvDialog = document.getElementById("csv-dialog");
  const csvNameCol = document.getElementById("csv-name-col");
  const csvDatetimeCol = document.getElementById("csv-datetime-col");
  const csvDialogApply = document.getElementById("csv-dialog-apply");
  const csvDialogCancel = document.getElementById("csv-dialog-cancel");
  const csvDialogClose = document.getElementById("csv-dialog-close");

  // -- Sport mapping (parallel to FIT_SPORT_MAP in enums.py) ----------------

  const SPORT_MAP = {
    running: "running",
    trailRunning: "running",
    cycling: "cycling",
    eBiking: "cycling",
    swimming: "swimming",
    openWaterSwimming: "swimming",
    crossCountrySkiing: "skiing",
    alpineSkiing: "skiing",
    training: "strength",
    fitnessEquipment: "strength",
  };

  const SPORT_LABELS = {
    running: "Run",
    cycling: "Ride",
    swimming: "Swim",
    skiing: "Ski",
    strength: "Strength",
  };

  // -- Helpers --------------------------------------------------------------

  function timeOfDay(hour) {
    if (hour >= 5 && hour < 12) return "Morning";
    if (hour >= 12 && hour < 17) return "Afternoon";
    if (hour >= 17 && hour < 21) return "Evening";
    return "Night";
  }

  function formatDuration(seconds) {
    if (seconds == null) return "";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.round(seconds % 60);
    if (h > 0) {
      return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function formatDistance(meters) {
    if (meters == null) return "";
    return (meters / 1000).toFixed(2) + " km";
  }

  function readFileAsArrayBuffer(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
      reader.readAsArrayBuffer(file);
    });
  }

  function makeCell(text, label) {
    const td = document.createElement("td");
    td.textContent = text;
    td.dataset.label = label;
    return td;
  }

  function appendText(parent, text, className) {
    const el = document.createElement("div");
    el.textContent = text;
    if (className) el.className = className;
    parent.appendChild(el);
  }

  // -- CSV helpers -----------------------------------------------------------

  function detectDelimiter(firstLine) {
    const commas = (firstLine.match(/,/g) || []).length;
    const semicolons = (firstLine.match(/;/g) || []).length;
    return semicolons > commas ? ";" : ",";
  }

  function parseCSV(text) {
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    if (lines.length === 0) return { headers: [], rows: [] };

    const delimiter = detectDelimiter(lines[0]);

    function parseLine(line) {
      const fields = [];
      let current = "";
      let inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (inQuotes) {
          if (ch === '"') {
            if (i + 1 < line.length && line[i + 1] === '"') {
              current += '"';
              i++;
            } else {
              inQuotes = false;
            }
          } else {
            current += ch;
          }
        } else if (ch === '"') {
          inQuotes = true;
        } else if (ch === delimiter) {
          fields.push(current.trim());
          current = "";
        } else {
          current += ch;
        }
      }
      fields.push(current.trim());
      return fields;
    }

    const headers = parseLine(lines[0]);
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const values = parseLine(lines[i]);
      const row = {};
      for (let j = 0; j < headers.length; j++) {
        row[headers[j]] = values[j] || "";
      }
      rows.push(row);
    }
    return { headers, rows };
  }

  let csvData = null;

  function matchCSVToWorkouts(csvRows, nameCol, datetimeCol) {
    const matched = new Set();
    let matchCount = 0;

    for (const csvRow of csvRows) {
      const rawDatetime = csvRow[datetimeCol];
      if (!rawDatetime) continue;

      // Parse as browser local time — the Date constructor applies the correct
      // DST offset for each individual date automatically.
      const isoStr = rawDatetime.trim().replace(" ", "T");
      const parsed = new Date(isoStr);
      if (isNaN(parsed.getTime())) continue;

      // Round to nearest second
      const utcDate = new Date(Math.round(parsed.getTime() / 1000) * 1000);

      for (let i = 0; i < parsedWorkouts.length; i++) {
        if (matched.has(i)) continue;

        const wTime = new Date(parsedWorkouts[i].start_time);
        if (Math.abs(wTime.getTime() - utcDate.getTime()) <= 1000) {
          const csvName = (csvRow[nameCol] || "").trim();
          if (csvName) {
            parsedWorkouts[i]._display.name = csvName;
            matchCount++;
          }
          matched.add(i);
          break;
        }
      }
    }

    return { matchCount, csvTotal: csvRows.length };
  }

  // -- Parse FIT files ------------------------------------------------------

  let parsedWorkouts = [];

  async function parseFiles(files) {
    const { Decoder, Stream } = await import(sdkUrl);

    parsedWorkouts = [];
    const warnings = [];

    for (const file of files) {
      try {
        const buffer = await readFileAsArrayBuffer(file);
        const stream = Stream.fromArrayBuffer(buffer);
        const decoder = new Decoder(stream);

        if (!decoder.isFIT()) {
          warnings.push(`${file.name}: not a valid FIT file.`);
          continue;
        }

        const { messages, errors } = decoder.read({
          convertTypesToStrings: true,
          convertDateTimesToDates: true,
        });

        if (errors.length > 0) {
          warnings.push(`${file.name}: ${errors[0].message || errors[0]}`);
        }

        const sessions = messages.sessionMesgs || [];
        if (sessions.length === 0) {
          warnings.push(`${file.name}: no session data found.`);
          continue;
        }

        for (const session of sessions) {
          const fitSport = session.sport || "";
          const subtype = SPORT_MAP[fitSport];
          if (!subtype) {
            warnings.push(
              `${file.name}: unknown sport "${fitSport}", skipping.`
            );
            continue;
          }

          const startTime = session.startTime instanceof Date
            ? session.startTime
            : new Date(session.startTime);
          const NON_DISTANCE_SUBTYPES = new Set(["strength", "mobility"]);
          const durationSeconds = session.totalElapsedTime || null;
          const distanceMeters =
            !NON_DISTANCE_SUBTYPES.has(subtype) && session.totalDistance != null
              ? Math.round(session.totalDistance)
              : null;

          const label = SPORT_LABELS[subtype] || "Workout";
          const name = `${timeOfDay(startTime.getUTCHours())} ${label}`;

          const guiFields = {};
          if (session.avgHeartRate != null) guiFields.avg_hr = session.avgHeartRate;
          if (session.maxHeartRate != null) guiFields.max_hr = session.maxHeartRate;
          if (session.avgCadence != null) guiFields.cadence = session.avgCadence;
          if (session.trainingLoadPeak != null) {
            guiFields.load_garmin = Math.round(session.trainingLoadPeak);
          }

          parsedWorkouts.push({
            subtype,
            start_time: startTime.toISOString(),
            duration_seconds: durationSeconds,
            distance_meters: distanceMeters,
            gui_fields: Object.keys(guiFields).length > 0 ? guiFields : undefined,
            _display: { name, startTime, label },
          });
        }
      } catch (err) {
        warnings.push(`${file.name}: ${err.message}`);
      }
    }

    return warnings;
  }

  // -- Render preview -------------------------------------------------------

  function renderPreview() {
    previewBody.replaceChildren();
    for (const w of parsedWorkouts) {
      const d = w._display;
      const tr = document.createElement("tr");
      tr.appendChild(makeCell(d.startTime.toLocaleDateString(), "Date"));
      tr.appendChild(
        makeCell(
          d.startTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          "Time"
        )
      );
      tr.appendChild(makeCell(d.label, "Activity"));
      tr.appendChild(makeCell(d.name, "Name"));
      tr.appendChild(makeCell(formatDuration(w.duration_seconds), "Duration"));
      tr.appendChild(makeCell(formatDistance(w.distance_meters), "Distance"));
      tr.appendChild(makeCell(w.gui_fields?.avg_hr?.toString() ?? "", "Avg HR"));
      previewBody.appendChild(tr);
    }
    previewFigure.hidden = parsedWorkouts.length === 0;
    uploadActions.hidden = parsedWorkouts.length === 0;
  }

  function showStatus(message, type) {
    parseStatus.hidden = false;
    parseStatus.textContent = message;
    parseStatus.className = type === "error" ? "upload-error" : "";
  }

  function showWarnings(warnings) {
    if (warnings.length === 0) {
      parseStatus.hidden = true;
      return;
    }
    parseStatus.hidden = false;
    parseStatus.replaceChildren();
    for (const w of warnings) {
      appendText(parseStatus, w, "upload-warning");
    }
  }

  // -- File input handler ---------------------------------------------------

  fileInput.addEventListener("change", async () => {
    const files = fileInput.files;
    if (files.length === 0) return;

    // Reset UI
    uploadResults.hidden = true;
    uploadResults.replaceChildren();
    parseStatus.hidden = true;
    previewFigure.hidden = true;
    uploadActions.hidden = true;
    uploadBtn.disabled = false;

    showStatus(`Parsing ${files.length} file(s)...`, "");

    try {
      const warnings = await parseFiles(files);
      showWarnings(warnings);
      renderPreview();

      if (parsedWorkouts.length === 0 && warnings.length === 0) {
        showStatus("No workouts found in the selected files.", "error");
      }
    } catch (err) {
      showStatus(`Error: ${err.message}`, "error");
    }
  });

  // -- CSV dialog handlers --------------------------------------------------

  csvImportBtn.addEventListener("click", () => csvFileInput.click());

  csvFileInput.addEventListener("change", async () => {
    const file = csvFileInput.files[0];
    if (!file) return;

    const text = await file.text();
    csvData = parseCSV(text);

    if (csvData.headers.length === 0) {
      showStatus("CSV file is empty or has no headers.", "error");
      csvFileInput.value = "";
      return;
    }

    // Populate select elements
    for (const select of [csvNameCol, csvDatetimeCol]) {
      select.replaceChildren();
      for (const header of csvData.headers) {
        const opt = document.createElement("option");
        opt.value = header;
        opt.textContent = header;
        select.appendChild(opt);
      }
    }

    // Pre-select likely columns (case-insensitive, with Swedish fallbacks)
    const lowerHeaders = csvData.headers.map((h) => h.toLowerCase());
    const nameIdx = lowerHeaders.findIndex((h) => h === "name" || h === "namn");
    if (nameIdx !== -1) csvNameCol.selectedIndex = nameIdx;
    const dateIdx = lowerHeaders.findIndex((h) => h === "date" || h === "datum");
    if (dateIdx !== -1) csvDatetimeCol.selectedIndex = dateIdx;

    csvDialog.showModal();
    csvFileInput.value = "";
  });

  csvDialogApply.addEventListener("click", () => {
    if (!csvData) return;

    const nameCol = csvNameCol.value;
    const datetimeCol = csvDatetimeCol.value;

    const { matchCount, csvTotal } = matchCSVToWorkouts(
      csvData.rows, nameCol, datetimeCol
    );

    csvDialog.close();
    renderPreview();
    showStatus(
      `Matched ${matchCount} of ${csvTotal} CSV row(s) to ${parsedWorkouts.length} workout(s).`,
      ""
    );
  });

  csvDialogCancel.addEventListener("click", () => csvDialog.close());
  csvDialogClose.addEventListener("click", () => csvDialog.close());

  // -- Upload handler -------------------------------------------------------

  uploadBtn.addEventListener("click", async () => {
    if (parsedWorkouts.length === 0) return;

    uploadBtn.setAttribute("aria-busy", "true");
    uploadBtn.disabled = true;

    // Strip _display, include name from display
    const payload = parsedWorkouts.map(({ _display, ...rest }) => ({
      ...rest,
      name: _display.name,
    }));

    try {
      const response = await fetch(uploadUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });

      const body = await response.json();
      uploadResults.hidden = false;
      uploadResults.replaceChildren();

      if (response.ok) {
        if (body.created > 0) {
          appendText(uploadResults, `${body.created} workout(s) created.`, "upload-success");
        }
        if (body.skipped > 0) {
          appendText(uploadResults, `${body.skipped} duplicate(s) skipped.`);
        }
        for (const e of body.errors) {
          appendText(uploadResults, e, "upload-error");
        }

        // Clear preview on success
        if (body.created > 0) {
          parsedWorkouts = [];
          previewFigure.hidden = true;
          uploadActions.hidden = true;
        }
      } else {
        appendText(uploadResults, body.error || "Upload failed.", "upload-error");
        uploadBtn.disabled = false;
      }
    } catch (err) {
      uploadResults.hidden = false;
      uploadResults.replaceChildren();
      appendText(uploadResults, `Network error: ${err.message}`, "upload-error");
      uploadBtn.disabled = false;
    } finally {
      uploadBtn.removeAttribute("aria-busy");
    }
  });
}
