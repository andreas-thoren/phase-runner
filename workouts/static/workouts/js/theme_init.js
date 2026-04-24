// Applies the saved theme preference before the page paints.
// Loaded SYNCHRONOUSLY in <head> (no `defer`) — running before DOM parses
// the body avoids a flash-of-wrong-theme on reload.
(function () {
  var saved = null;
  try { saved = localStorage.getItem("phaserunner.theme"); } catch (_) {}
  if (saved === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  }
  // Otherwise keep the SSR default of data-theme="dark".
})();
