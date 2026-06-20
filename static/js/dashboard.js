/* Dashboard interactivity: charts, company search/filter, tab-hash sync, upload UX */
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    initTabHashSync();
    initCharts();
    initCompanyFilter();
    initResumeUploadPreview();
    initAutoDismissAlerts();
  });

  /* Keep the active sidebar tab in sync with the URL hash so redirects after
     a form POST (e.g. #coding) land the user back on the right section. */
  function initTabHashSync() {
    var hash = window.location.hash;
    if (hash) {
      var trigger = document.querySelector('.nav-pills [data-bs-toggle="pill"][href="' + hash + '"]');
      if (trigger) {
        var tab = new bootstrap.Tab(trigger);
        tab.show();
      }
    }
    document.querySelectorAll('.nav-pills [data-bs-toggle="pill"]').forEach(function (el) {
      el.addEventListener("shown.bs.tab", function (e) {
        history.replaceState(null, "", e.target.getAttribute("href"));
      });
    });
  }

  /* Chart.js: Skill Radar, Application Status Bar, Eligibility Doughnut.
     Data is provided by the dashboard template via window.SPT_CHART_DATA. */
  function initCharts() {
    if (typeof Chart === "undefined" || !window.SPT_CHART_DATA) return;
    var data = window.SPT_CHART_DATA;

    var rootStyles = getComputedStyle(document.documentElement);
    var teal = rootStyles.getPropertyValue("--teal-500").trim() || "#14B8A6";
    var amber = rootStyles.getPropertyValue("--amber-500").trim() || "#F5A524";
    var coral = rootStyles.getPropertyValue("--coral-500").trim() || "#FB7185";
    var navy = rootStyles.getPropertyValue("--navy-700").trim() || "#1E2D4A";
    var muted = rootStyles.getPropertyValue("--text-muted").trim() || "#64748B";
    var gridColor = rootStyles.getPropertyValue("--border").trim() || "#E3E7F0";

    Chart.defaults.font.family = "Inter, sans-serif";
    Chart.defaults.color = muted;

    var radarEl = document.getElementById("skillRadarChart");
    if (radarEl) {
      new Chart(radarEl, {
        type: "radar",
        data: {
          labels: data.radar.labels,
          datasets: [{
            label: "Your readiness (%)",
            data: data.radar.values,
            backgroundColor: "rgba(20, 184, 166, 0.18)",
            borderColor: teal,
            pointBackgroundColor: teal,
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          scales: {
            r: {
              min: 0, max: 100,
              ticks: { stepSize: 25, backdropColor: "transparent" },
              grid: { color: gridColor },
              angleLines: { color: gridColor },
              pointLabels: { font: { size: 11 } },
            },
          },
          plugins: { legend: { display: false } },
        },
      });
    }

    var appsEl = document.getElementById("applicationsChart");
    if (appsEl) {
      new Chart(appsEl, {
        type: "bar",
        data: {
          labels: data.applications.labels,
          datasets: [{
            label: "Applications",
            data: data.applications.values,
            backgroundColor: [amber, "#60A5FA", teal, coral],
            borderRadius: 6,
            maxBarThickness: 46,
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: gridColor } },
            x: { grid: { display: false } },
          },
        },
      });
    }

    var eligEl = document.getElementById("eligibilityChart");
    if (eligEl) {
      new Chart(eligEl, {
        type: "doughnut",
        data: {
          labels: data.eligibility.labels,
          datasets: [{
            data: data.eligibility.values,
            backgroundColor: [teal, gridColor],
            borderWidth: 0,
          }],
        },
        options: {
          responsive: true,
          cutout: "70%",
          plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } } },
        },
      });
    }
  }

  /* Client-side search + "eligible only" filter over the companies grid —
     instant feedback, no server round trip needed for a list this size. */
  function initCompanyFilter() {
    var searchInput = document.getElementById("companySearch");
    var eligibleOnly = document.getElementById("eligibleOnlyToggle");
    var cards = document.querySelectorAll(".company-card-col");
    var emptyState = document.getElementById("companiesEmptyState");
    if (!cards.length) return;

    function applyFilter() {
      var query = (searchInput && searchInput.value || "").trim().toLowerCase();
      var onlyEligible = eligibleOnly && eligibleOnly.checked;
      var visibleCount = 0;

      cards.forEach(function (col) {
        var name = (col.dataset.name || "").toLowerCase();
        var role = (col.dataset.role || "").toLowerCase();
        var isEligible = col.dataset.eligible === "true";
        var matchesQuery = !query || name.indexOf(query) !== -1 || role.indexOf(query) !== -1;
        var matchesEligibility = !onlyEligible || isEligible;
        var show = matchesQuery && matchesEligibility;
        col.style.display = show ? "" : "none";
        if (show) visibleCount++;
      });

      if (emptyState) emptyState.classList.toggle("d-none", visibleCount !== 0);
    }

    if (searchInput) searchInput.addEventListener("input", applyFilter);
    if (eligibleOnly) eligibleOnly.addEventListener("change", applyFilter);
  }

  /* Show the chosen filename + simple drag-over state for the resume upload box */
  function initResumeUploadPreview() {
    var dropZone = document.getElementById("resumeDropZone");
    var input = document.getElementById("resumeInput");
    var fileNameLabel = document.getElementById("resumeFileName");
    if (!dropZone || !input) return;

    dropZone.addEventListener("click", function () { input.click(); });

    input.addEventListener("change", function () {
      if (input.files && input.files.length) {
        fileNameLabel.textContent = input.files[0].name;
        fileNameLabel.classList.remove("d-none");
      }
    });

    ["dragover", "dragleave", "drop"].forEach(function (evt) {
      dropZone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropZone.classList.toggle("dragover", evt === "dragover");
      });
    });

    dropZone.addEventListener("drop", function (e) {
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        fileNameLabel.textContent = e.dataTransfer.files[0].name;
        fileNameLabel.classList.remove("d-none");
      }
    });
  }

  /* Auto-dismiss flash messages after a few seconds */
  function initAutoDismissAlerts() {
    document.querySelectorAll(".alert-auto-dismiss").forEach(function (alertEl) {
      setTimeout(function () {
        var alert = bootstrap.Alert.getOrCreateInstance(alertEl);
        alert.close();
      }, 5000);
    });
  }
})();
