// Summary table navigation: three clickable zones per row
// - .meso-header (th) → mesocycle detail
// - .zone-planned (td) → microcycle detail
// - .zone-actual (td) → workout list filtered by date range
//
// Hover on any cell highlights its zone siblings in the same row.
// Tab lands on the first cell of each zone (the one with tabindex="0").
// Focus on that cell highlights the entire zone in its row.
// Hash-based focus restoration on back navigation (zone-planned only).

(function () {
  function getZoneSiblings(cell) {
    var row = cell.closest("tr");
    var cls = cell.classList.contains("zone-planned")
      ? "zone-planned"
      : cell.classList.contains("zone-actual")
        ? "zone-actual"
        : null;
    if (!cls) return [];
    return Array.from(row.querySelectorAll("." + cls));
  }

  function storeHash(td) {
    if (td.classList.contains("zone-planned")) {
      var anchor = td.closest("tr").querySelector(".zone-planned[id]");
      if (anchor) history.replaceState(null, "", "#" + anchor.id);
    } else {
      history.replaceState(null, "", location.pathname + location.search);
    }
  }

  function navigate(href) {
    if (href) window.location = href;
  }

  // Click handler for zone cells
  document.querySelectorAll(".zone-planned, .zone-actual").forEach(function (td) {
    td.addEventListener("click", function () {
      storeHash(td);
      navigate(td.dataset.href);
    });
  });

  // Hover: highlight zone siblings
  document.querySelectorAll(".zone-planned, .zone-actual").forEach(function (td) {
    td.addEventListener("mouseenter", function () {
      getZoneSiblings(td).forEach(function (s) { s.classList.add("zone-hover"); });
    });
    td.addEventListener("mouseleave", function () {
      getZoneSiblings(td).forEach(function (s) { s.classList.remove("zone-hover"); });
    });
  });

  // Focus/blur on tabindex cells: highlight zone siblings
  document.querySelectorAll(".zone-planned[tabindex], .zone-actual[tabindex]").forEach(function (td) {
    td.addEventListener("focus", function () {
      getZoneSiblings(td).forEach(function (s) { s.classList.add("zone-focus"); });
    });
    td.addEventListener("blur", function () {
      getZoneSiblings(td).forEach(function (s) { s.classList.remove("zone-focus"); });
    });
    td.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        storeHash(td);
        navigate(td.dataset.href);
      }
    });
  });

  // Meso header: already an <a> link, but add hover effect
  document.querySelectorAll(".meso-header").forEach(function (th) {
    th.style.cursor = "pointer";
    th.addEventListener("click", function (e) {
      if (th.id) history.replaceState(null, "", "#" + th.id);
      if (e.target.closest("a")) return; // let the <a> handle it
      var a = th.querySelector("a");
      if (a) navigate(a.href);
    });
  });

  // Export button — navigates to export URL
  var exportBtn = document.getElementById("export-csv");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      window.location.href = exportBtn.dataset.exportUrl;
    });
  }

  // Filter bar: toggle, enable/disable submit, clear
  var toggleBtn = document.getElementById("toggle-summary-filters");
  var filterBar = document.getElementById("filter-bar");
  if (toggleBtn && filterBar) {
    toggleBtn.addEventListener("click", function () {
      filterBar.hidden = !filterBar.hidden;
      var url = new URL(window.location);
      if (filterBar.hidden) url.searchParams.delete("show_filters");
      else url.searchParams.set("show_filters", "1");
      history.replaceState(null, "", url);
    });

    var submit = document.getElementById("filter-submit");
    var clearBtn = document.getElementById("filter-clear");
    var allCols = ["comment", "x", "str", "load"];

    function differsFromDefault() {
      var checked = Array.from(
        filterBar.querySelectorAll('input[name="cols"]:checked')
      ).map(function (el) { return el.value; });
      if (checked.length !== allCols.length) return true;
      return !allCols.every(function (c) { return checked.indexOf(c) !== -1; });
    }
    function refresh() {
      var changed = differsFromDefault();
      if (submit) submit.disabled = !changed;
      if (clearBtn) clearBtn.disabled = !changed;
    }
    filterBar.addEventListener("input", refresh);
    filterBar.addEventListener("change", refresh);

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        window.location.href = clearBtn.dataset.clearUrl;
      });
    }
  }

  // Restore focus from URL hash on back navigation
  function focusHashTarget() {
    if (!location.hash) return;
    var target = document.querySelector(location.hash);
    if (!target) return;
    var focusable = target.querySelector("a") || target;
    focusable.focus();
    getZoneSiblings(target).forEach(function (s) { s.classList.add("zone-focus"); });
  }
  focusHashTarget();
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) focusHashTarget();
  });
})();
