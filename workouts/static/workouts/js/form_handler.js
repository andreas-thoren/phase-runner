// Intercept mutation form submissions: use location.replace() for the redirect
// so the form page doesn't stay in browser history.
const form = document.getElementById("main-form");
const submitBtn = form?.querySelector('button[type="submit"]');

if (form && submitBtn) {
  form.addEventListener("submit", e => {
    e.preventDefault();
    submitBtn.setAttribute("aria-busy", "true");

    fetch(form.action || location.href, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
    })
      .then(res => {
        if (res.redirected) {
          location.replace(res.url);
        } else {
          // Validation errors — resubmit normally to render server-side errors.
          form.submit();
        }
      })
      .catch(() => {
        form.submit();
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
