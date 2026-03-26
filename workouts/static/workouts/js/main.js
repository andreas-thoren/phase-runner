// ---------------------------------------------------------------------------
// Global scripts loaded on every page via base.html
// ---------------------------------------------------------------------------

// -- Navigation helpers -----------------------------------------------------

// data-back: navigate back via history.back()
document.querySelectorAll("[data-back]").forEach(el =>
  el.addEventListener("click", () => history.back())
);

// data-replace: navigate via location.replace() so the current page is
// removed from browser history (used by mutation-view links).
document.querySelectorAll("a[data-replace]").forEach(el =>
  el.addEventListener("click", e => {
    e.preventDefault();
    location.replace(el.getAttribute("href"));
  })
);

// -- Sidebar ----------------------------------------------------------------

const sidebar = document.getElementById("sidebar-menu");
if (sidebar) {
  document.querySelectorAll("[data-sidebar-open]").forEach((btn) => {
    btn.addEventListener("click", () => sidebar.classList.add("is-open"));
  });

  document.querySelectorAll("[data-sidebar-close]").forEach((btn) => {
    btn.addEventListener("click", () => sidebar.classList.remove("is-open"));
  });

  // Close on nav link click (mobile)
  sidebar.querySelectorAll("nav a").forEach((link) => {
    link.addEventListener("click", () => sidebar.classList.remove("is-open"));
  });

  // Close on Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") sidebar.classList.remove("is-open");
  });

  // Sticky breadcrumb shadow
  const breadcrumb = document.getElementById("sidebar-breadcrumb");
  if (breadcrumb) {
    const observer = new IntersectionObserver(
      ([entry]) => breadcrumb.classList.toggle("is-sticky", !entry.isIntersecting),
      { threshold: 1 }
    );
    observer.observe(breadcrumb);
  }
}

// -- Logout -----------------------------------------------------------------

// Submit the hidden logout form when the logout link is clicked.
const logoutLink = document.querySelector("a[data-logout]");
const logoutForm = document.getElementById("logout-form");
if (logoutLink && logoutForm) {
  logoutLink.addEventListener("click", e => {
    e.preventDefault();
    logoutForm.submit();
  });
}
