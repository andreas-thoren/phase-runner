document.querySelectorAll("tr[data-href]").forEach(row => {
  row.addEventListener("click", () => {
    history.replaceState(null, "", "#" + row.id);
    window.location = row.dataset.href;
  });
  row.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      history.replaceState(null, "", "#" + row.id);
      window.location = row.dataset.href;
    }
  });
});

// Focus the row from URL hash on initial load and bfcache restoration (browser back)
function focusHashTarget() {
  if (location.hash) {
    const target = document.querySelector(location.hash);
    if (target) target.focus({ focusVisible: true });
  }
}
focusHashTarget();
window.addEventListener("pageshow", e => {
  if (e.persisted) focusHashTarget();
});
