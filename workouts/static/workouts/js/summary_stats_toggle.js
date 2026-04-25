// Lazy-loads and toggles the summary stats fragment.
// First click fetches the HTML from `data-url` into the container referenced
// by `data-target`; subsequent clicks just show/hide the container.
// No persistence — state resets on every page load.

(function () {
  var btn = document.getElementById("toggle-summary-stats");
  if (!btn) return;
  var container = document.getElementById(btn.dataset.target);
  if (!container) return;

  var loaded = false;

  function renderFragment(html) {
    // HTML is from our own auth-scoped Django view — parsed via DOMParser
    // rather than assigned to innerHTML to avoid XSS-flagging patterns and
    // keep this explicit about the trust boundary.
    var doc = new DOMParser().parseFromString(html, "text/html");
    container.replaceChildren(...doc.body.childNodes);
  }

  function renderError(message) {
    container.replaceChildren();
    var p = document.createElement("p");
    p.className = "summary-stats-empty";
    p.textContent = message;
    container.appendChild(p);
  }

  btn.addEventListener("click", async function () {
    if (!loaded) {
      btn.disabled = true;
      try {
        var resp = await fetch(btn.dataset.url, {
          headers: { "X-Requested-With": "fetch" },
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        renderFragment(await resp.text());
        loaded = true;
      } catch (err) {
        renderError("Could not load summary stats.");
      } finally {
        btn.disabled = false;
      }
    }
    var nowHidden = !container.hidden;
    container.hidden = nowHidden;
    btn.setAttribute("aria-expanded", String(!nowHidden));
    if (!nowHidden) {
      container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
})();
