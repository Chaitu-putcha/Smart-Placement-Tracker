/* Theme toggle — shared across all pages.
   The actual "apply theme before paint" snippet lives inline in <head> of each
   template to avoid a flash of the wrong theme; this file just wires the switch. */
(function () {
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("spt-theme", theme);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("themeToggle");
    if (!toggle) return;

    toggle.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") || "light";
      applyTheme(current === "dark" ? "light" : "dark");
    });
  });
})();
