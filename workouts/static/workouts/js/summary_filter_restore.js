// Restores and persists per-device, per-macro summary filter state.
// Loaded SYNCHRONOUSLY in <head> (no `defer`) so the redirect happens
// before the DOM paints — this is a deliberate exception to the general
// defer-everything rule, because this script must run pre-DOM.
(function () {
  var script = document.currentScript;
  var macroPk = script && script.dataset.macroPk;
  if (!macroPk) return;

  var STORAGE_KEY = "phaserunner.summaryFilters.v1";
  // Applied on first visit to a plan's summary (no saved entry yet).
  // Matches SummaryFilterForm.COL_CHOICES keys and WorkoutStatus values.
  var DEFAULT_FILTER = {
    cols: ["comment"],
    statuses: ["planned", "completed", "cancelled", "postponed"],
  };
  var url = new URL(location.href);
  var params = url.searchParams;

  function readStore() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch (_) {
      return {};
    }
  }
  function writeStore(obj) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    } catch (_) {
      // quota / disabled — give up silently
    }
  }

  if (params.has("filtered")) {
    var store = readStore();
    store[macroPk] = {
      cols: params.getAll("cols"),
      statuses: params.getAll("statuses"),
    };
    writeStore(store);
    return;
  }

  var saved = readStore()[macroPk];
  // Clear button saved `{ cleared: true }` — render unfiltered, no redirect.
  if (saved && saved.cleared) return;
  if (!saved) saved = DEFAULT_FILTER;

  params.set("filtered", "1");
  (saved.cols || []).forEach(function (c) { params.append("cols", c); });
  (saved.statuses || []).forEach(function (s) { params.append("statuses", s); });
  location.replace(url.toString());
})();
