const filterBar = document.getElementById("filter-bar");

function setFilterBarHidden(hidden) {
  filterBar.hidden = hidden;
  const url = new URL(window.location);
  if (hidden) url.searchParams.delete("show_filters");
  else url.searchParams.set("show_filters", "1");
  history.replaceState(null, "", url);
}

document.getElementById("toggle-filters").addEventListener("click", () => {
  setFilterBarHidden(!filterBar.hidden);
});

const filterClose = filterBar.querySelector("[data-filter-close]");
if (filterClose) {
  filterClose.addEventListener("click", () => setFilterBarHidden(true));
}
const filterSubmit = document.getElementById("filter-submit");

function updateFilterButton() {
  const hasValue = Array.from(filterBar.elements).some(
    el => el !== filterSubmit && el.name !== "show_filters" && el.value
  );
  filterSubmit.disabled = !hasValue;
}

filterBar.addEventListener("input", updateFilterButton);
filterBar.addEventListener("change", updateFilterButton);

const filterClear = document.getElementById("filter-clear");
if (filterClear) {
  filterClear.addEventListener("click", () => {
    window.location.href = filterClear.dataset.clearUrl;
  });
}

// Export button — navigates to export URL with current filter params
const exportBtn = document.getElementById("export-csv");
if (exportBtn) {
  exportBtn.addEventListener("click", () => {
    const baseUrl = exportBtn.dataset.exportUrl;
    const params = new URLSearchParams(window.location.search);
    params.delete("show_filters");
    params.delete("page");
    const qs = params.toString();
    window.location.href = qs ? `${baseUrl}?${qs}` : baseUrl;
  });
}

// Clickable rows are handled by clickable_rows.js (loaded separately).
