// Intercept mutation form submissions: use location.replace() for the redirect
// so the form page doesn't stay in browser history.
const form = document.getElementById("main-form");
const submitBtn = form?.querySelector('button[type="submit"]');
const errorBanner = document.getElementById("form-error");

function showError(text) {
  if (!errorBanner) return;
  errorBanner.textContent = text;
  errorBanner.hidden = false;
}

function hideError() {
  if (!errorBanner) return;
  errorBanner.textContent = "";
  errorBanner.hidden = true;
}

if (form && submitBtn) {
  form.addEventListener("submit", e => {
    e.preventDefault();
    hideError();
    submitBtn.setAttribute("aria-busy", "true");

    fetch(form.action || location.href, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
    })
      .then(res => {
        if (res.redirected) {
          location.replace(res.url);
        } else if (res.ok) {
          // 200 means validation errors (server did not mutate).
          // Resubmit so the browser renders the form with errors.
          form.submit();
        } else {
          // 4xx/5xx — do not re-POST; that would duplicate any partial
          // side effects from the first request.
          submitBtn.removeAttribute("aria-busy");
          showError(`Server error (HTTP ${res.status}). Please try again or reload the page.`);
        }
      })
      .catch(() => {
        submitBtn.removeAttribute("aria-busy");
        showError("Network error. Please check your connection and try again.");
      });
  });

  // Ctrl+S / Cmd+S → Save (skip delete views)
  if (submitBtn.id !== "delete-btn") {
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        submitBtn.click();
      }
    });
  }
}

// E → Edit on detail views (no submit button means it's a detail view)
const editLink = document.querySelector('.form-actions a[aria-label="Edit"]');
if (editLink && !submitBtn) {
  document.addEventListener("keydown", e => {
    if (e.key === "e" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      editLink.click();
    }
  });
}
