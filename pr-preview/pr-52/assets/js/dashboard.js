/**
 * Main dashboard application.
 * Loads project config + JSON data, renders weekly stats, contributors, and cards.
 */

(async function init() {
  const projects = await fetchJSON("_data/projects.json");
  if (!projects || !projects.projects) {
    document.getElementById("dashboard").innerHTML =
      '<p class="empty">Failed to load project data.</p>';
    return;
  }

  // Load all project data in parallel
  const names = Object.keys(projects.projects);
  const dataMap = {};

  const fetches = names.map(async (name) => {
    const [prs, issues, releases, testResults, activity, parityReport, buildTimes] = await Promise.all([
      fetchJSON("data/" + name + "/prs.json"),
      fetchJSON("data/" + name + "/issues.json"),
      fetchJSON("data/" + name + "/releases.json"),
      fetchJSON("data/" + name + "/test_results.json"),
      fetchJSON("data/" + name + "/activity.json"),
      fetchJSON("data/" + name + "/parity_report.json"),
      fetchJSON("data/" + name + "/build_times.json"),
    ]);
    dataMap[name] = { prs, issues, releases, testResults, activity, parityReport, buildTimes };
  });

  // Also load trend history + parity history
  const historyIndex = fetchJSON("data/history/index.json");
  const parityHistPromise = fetchJSON("data/pytorch/parity_history.json");
  const opCoveragePromise = fetchJSON("_data/op-coverage.json");

  await Promise.all(fetches);
  const histIdx = await historyIndex;

  // Load history snapshots
  var historyData = [];
  if (histIdx && histIdx.weeks) {
    var histFetches = histIdx.weeks.map(function (w) {
      return fetchJSON("data/history/" + w + ".json");
    });
    historyData = await Promise.all(histFetches);
    historyData = historyData.filter(function (h) { return h != null; });
  }

  // Find latest collected_at for header
  let latestTs = null;
  for (const name of names) {
    const d = dataMap[name];
    for (const src of [d.prs, d.issues, d.releases, d.testResults, d.activity]) {
      if (src && src.collected_at) {
        if (!latestTs || src.collected_at > latestTs) {
          latestTs = src.collected_at;
        }
      }
    }
  }
  document.getElementById("last-updated").textContent = latestTs
    ? "Last updated: " + relativeTime(latestTs) + " (" + formatDate(latestTs) + ")"
    : "Last updated: unknown";

  const parityHistData = await parityHistPromise;
  const opCoverageData = await opCoveragePromise;

  // Render all views
  renderWeeklySummary(dataMap);
  renderCards(projects.projects, dataMap);
  renderParityView(projects.projects, dataMap, parityHistData);
  renderActivityView(projects.projects, dataMap);
  renderTrendsView(projects.projects, dataMap, historyData);
  renderOpCoverage(opCoverageData);
  try {
    renderBuildsView(projects.projects, dataMap, historyData);
  } catch (e) {
    console.error("renderBuildsView error:", e);
    document.getElementById("builds-view").innerHTML = '<p class="empty">Error rendering builds: ' + e.message + '</p>';
  }

  // Tab switching
  function switchTab(target) {
    document.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
    document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
    var btn = document.querySelector('.tab-btn[data-tab="' + target + '"]');
    if (btn) btn.classList.add("active");
    var panel = document.getElementById("tab-" + target);
    if (panel) panel.classList.add("active");
  }

  var tabBtns = document.querySelectorAll(".tab-btn");
  for (var i = 0; i < tabBtns.length; i++) {
    tabBtns[i].addEventListener("click", function () {
      var target = this.getAttribute("data-tab");
      switchTab(target);
      history.replaceState(null, "", "#" + target);
      // Render dagre graph when Builds tab becomes visible
      if (target === "builds" && window._depGraphPending) {
        var dg = window._depGraphPending;
        setTimeout(function() {
          renderDagreGraph(dg.graphId, dg.graphNodes, dg.projectsCfg, dg.nodeInfo);
        }, 50);
      }
    });
  }

  // Activate tab from URL hash on load
  var hash = location.hash.replace("#", "");
  if (hash && document.getElementById("tab-" + hash)) {
    switchTab(hash);
  }
})();

function renderWeeklySummary(dataMap) {
  let totalOpened = 0;
  let totalMerged = 0;
  let totalIssues = 0;
  let totalReleases = 0;

  for (const d of Object.values(dataMap)) {
    const prs = (d.prs && d.prs.prs) || [];
    const issues = (d.issues && d.issues.issues) || [];
    const releases = (d.releases && d.releases.releases) || [];
    const stats = getWeeklyStats(prs, issues, releases);
    totalOpened += stats.prsOpened;
    totalMerged += stats.prsMerged;
    totalIssues += stats.issuesOpened;
    totalReleases += stats.newReleases;
  }

  const el = document.getElementById("weekly-summary");
  el.innerHTML =
    '<h2>This Week</h2>' +
    '<div class="weekly-boxes">' +
    '<div class="weekly-box weekly-box-opened"><div class="weekly-num">' + totalOpened + '</div><div class="weekly-label">PRs Opened</div></div>' +
    '<div class="weekly-box weekly-box-merged"><div class="weekly-num">' + totalMerged + '</div><div class="weekly-label">PRs Merged</div></div>' +
    '<div class="weekly-box weekly-box-issues"><div class="weekly-num">' + totalIssues + '</div><div class="weekly-label">Issues</div></div>' +
    '<div class="weekly-box weekly-box-releases"><div class="weekly-num">' + totalReleases + '</div><div class="weekly-label">Releases</div></div>' +
    '</div>';
}

function renderCards(projectsCfg, dataMap) {
  const dashboard = document.getElementById("dashboard");
  dashboard.innerHTML = "";

  for (const [name, cfg] of Object.entries(projectsCfg)) {
    const d = dataMap[name] || {};
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = buildCard(name, cfg, d);
    dashboard.appendChild(card);
  }

  if (!dashboard.children.length) {
    dashboard.innerHTML = '<p class="empty">No projects found.</p>';
  }
}

function renderParityView(projectsCfg, dataMap, parityHistData) {
  var el = document.getElementById("parity-view");
  var hasAny = false;

  for (var name in dataMap) {
    if (dataMap[name].testResults || dataMap[name].parityReport) { hasAny = true; break; }
  }

  if (!hasAny) {
    el.innerHTML = '<h2>ROCm vs CUDA Test Parity</h2><p class="parity-no-data">No test result data available yet.</p>';
    return;
  }

  var html = '<h2>ROCm vs CUDA Test Parity</h2>';
  html += '<div class="parity-grid">';

  for (var name in projectsCfg) {
    var cfg = projectsCfg[name];
    var d = dataMap[name] || {};
    var tr = d.testResults;
    if (!tr && !d.parityReport) continue;

    // Enhanced PyTorch card when parityReport is available
    if (name === "pytorch" && d.parityReport) {
      html += buildPytorchParityCard(name, cfg, d.parityReport, parityHistData);
      continue;
    }

    if (!tr) continue;

    var rocm = tr.rocm;
    var cuda = tr.cuda;
    var repoUrl = "https://github.com/" + cfg.repo;

    html += '<div class="parity-card">';

    // Header with project name and overall conclusion
    html += '<div class="parity-card-header">';
    html += '<a href="' + repoUrl + '" target="_blank">' + escapeHtml(name) + '</a>';
    var conclParts = [];
    if (rocm) conclParts.push("ROCm: " + (rocm.conclusion || "?"));
    if (cuda) conclParts.push("CUDA: " + (cuda.conclusion || "?"));
    if (conclParts.length) {
      html += '<span class="parity-conclusion">' + escapeHtml(conclParts.join(" | ")) + '</span>';
    }
    html += '</div>';

    // CUDA Parity bar (primary)
    if (tr.cuda_parity) {
      html += buildParityBar(tr.cuda_parity);
    }

    // Per-platform pass rates (secondary)
    html += '<div class="parity-bars">';
    if (rocm && rocm.summary) html += buildPassRateBar("ROCm", rocm.summary, rocm.run_url);
    if (cuda && cuda.summary) html += buildPassRateBar("CUDA", cuda.summary, cuda.run_url);
    html += '</div>';

    // Stats line
    html += '<div class="parity-stats">';
    if (rocm && rocm.summary) {
      var rs = rocm.summary;
      html += '<span>ROCm: <span class="stat-num">' + (rs.passed || 0) + '</span> passed';
      if (rs.failed) html += ', <span class="stat-num">' + rs.failed + '</span> failed';
      if (rs.skipped) html += ', ' + rs.skipped + ' skipped';
      html += '</span>';
    }
    if (cuda && cuda.summary) {
      var cs = cuda.summary;
      html += '<span>CUDA: <span class="stat-num">' + (cs.passed || 0) + '</span> passed';
      if (cs.failed) html += ', <span class="stat-num">' + cs.failed + '</span> failed';
      if (cs.skipped) html += ', ' + cs.skipped + ' skipped';
      html += '</span>';
    }
    html += '</div>';

    // Suite detail table (collapsible)
    var suiteHtml = buildSuiteTable(rocm, cuda);
    if (suiteHtml) {
      var suiteCount = ((rocm && rocm.suites) ? rocm.suites.length : 0) + ((cuda && cuda.suites) ? cuda.suites.length : 0);
      html += '<details><summary>Test Suites (' + suiteCount + ')</summary>' + suiteHtml + '</details>';
    }

    // Freshness line
    var dates = [];
    if (rocm && rocm.run_date) dates.push("ROCm: " + relativeTime(rocm.run_date));
    if (cuda && cuda.run_date) dates.push("CUDA: " + relativeTime(cuda.run_date));
    if (dates.length) {
      html += '<div class="test-meta">Runs: ' + dates.join(", ");
      if (tr.source === "manual") html += " (manual)";
      html += '</div>';
    }

    html += '</div>'; // parity-card
  }

  html += '</div>'; // parity-grid
  el.innerHTML = html;

  // Init parity mini chart if history available
  if (parityHistData && parityHistData.length > 1) {
    drawParityMiniChart('chart-pytorch-parity', parityHistData);
  }
}

function buildPytorchParityCard(name, cfg, report, history) {
  var repoUrl = "https://github.com/" + cfg.repo;
  var s = report.summary;
  var pct = s.parity_pct;
  var colorClass = pct >= 90 ? "rate-good-text" : pct >= 70 ? "rate-warn-text" : "rate-bad-text";
  var barColorClass = pct >= 90 ? "rate-good" : pct >= 70 ? "rate-warn" : "rate-bad";

  var html = '<div class="parity-card">';

  // Header
  html += '<div class="parity-card-header">';
  html += '<a href="' + repoUrl + '" target="_blank">' + escapeHtml(name) + '</a>';
  html += '<span class="parity-arch-badge">' + escapeHtml(report.arch.toUpperCase()) + '</span>';
  html += '</div>';

  // Big parity number
  html += '<div class="parity-primary">';
  html += '<div class="parity-big-num ' + colorClass + '">' + pct.toFixed(1) + '%</div>';
  html += '<div class="parity-big-label">CUDA Parity (1-to-1 test-name matching)</div>';
  html += '</div>';

  // Parity bar
  var barWidth = Math.min(pct, 100);
  html += '<div class="pass-rate-row">';
  html += '<span class="pass-rate-label">Parity</span>';
  html += '<div class="pass-rate-bar-bg"><div class="pass-rate-bar-fill ' + barColorClass + '" style="width:' + barWidth + '%"></div></div>';
  html += '<span class="pass-rate-pct">' + s.total_rocm + ' / ' + s.total_cuda + '</span>';
  html += '</div>';

  // Gap breakdown
  html += '<div class="parity-gap-breakdown">';
  html += '<span class="gap-item">Skipped: <strong>' + s.skipped + '</strong></span>';
  html += '<span class="gap-item">Missed: <strong>' + s.missed + '</strong></span>';
  html += '<span class="gap-item">Gap: <strong>' + s.gap + '</strong></span>';
  html += '<span class="gap-item">ROCm-only: <strong>' + s.rocmonly + '</strong></span>';
  html += '</div>';

  // Per-workflow table
  var wfs = report.by_workflow;
  if (wfs && Object.keys(wfs).length > 0) {
    html += '<table class="parity-workflow-table">';
    html += '<tr><th>Workflow</th><th>ROCm</th><th>CUDA</th><th>Skipped</th><th>Missed</th><th>ROCm-only</th><th>Parity</th></tr>';
    for (var wf in wfs) {
      var w = wfs[wf];
      var wGap = w.skipped + w.missed;
      var wParity = w.cuda > 0 ? ((1 - wGap / w.cuda) * 100).toFixed(1) : "N/A";
      var wPctClass = w.cuda > 0 ? (parseFloat(wParity) >= 90 ? "rate-good-text" : parseFloat(wParity) >= 70 ? "rate-warn-text" : "rate-bad-text") : "";
      html += '<tr>';
      html += '<td class="project-name">' + escapeHtml(wf) + '</td>';
      html += '<td>' + w.rocm + '</td>';
      html += '<td>' + w.cuda + '</td>';
      html += '<td>' + w.skipped + '</td>';
      html += '<td>' + w.missed + '</td>';
      html += '<td>' + w.rocmonly + '</td>';
      html += '<td class="' + wPctClass + '">' + wParity + '%</td>';
      html += '</tr>';
    }
    html += '</table>';
  }

  // Top skip reasons (collapsible)
  var reasons = report.top_skip_reasons;
  if (reasons && reasons.length > 0) {
    html += '<details>';
    html += '<summary>Top Skip Reasons (' + reasons.length + ')</summary>';
    html += '<div class="skip-reasons-list">';
    for (var i = 0; i < reasons.length; i++) {
      html += '<div class="skip-reason-item">';
      html += '<span class="skip-reason-name">' + escapeHtml(reasons[i].reason) + '</span>';
      html += '<span class="skip-reason-count">' + reasons[i].count + '</span>';
      html += '</div>';
    }
    html += '</div></details>';
  }

  // Mini trend chart
  if (history && history.length > 1) {
    html += '<div class="parity-trend">';
    html += '<h4>Parity Trend</h4>';
    html += '<canvas id="chart-pytorch-parity" height="120"></canvas>';
    html += '</div>';
  }

  // Metadata line
  html += '<div class="parity-meta">';
  var shaShort = report.commit_sha ? report.commit_sha.slice(0, 8) : "?";
  var shaUrl = "https://github.com/" + cfg.repo + "/commit/" + report.commit_sha;
  html += 'Commit: <a href="' + shaUrl + '" target="_blank">' + shaShort + '</a>';
  html += ' &middot; Collected: ' + formatDate(report.collected_at);
  if (report.running_time) {
    html += ' &middot; ROCm: ' + formatSeconds(report.running_time.rocm_seconds);
    html += ' / CUDA: ' + formatSeconds(report.running_time.cuda_seconds);
  }
  html += '</div>';

  html += '</div>'; // parity-card
  return html;
}

function drawParityMiniChart(canvasId, history) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;

  var labels = history.map(function (h) { return h.date; });
  var data = history.map(function (h) { return h.parity_pct; });

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Parity %',
        data: data,
        borderColor: '#58a6ff',
        backgroundColor: '#58a6ff33',
        tension: 0.3,
        pointRadius: 3,
        borderWidth: 2,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', font: { size: 10 } },
          grid: { color: '#30363d' }
        },
        y: {
          min: 0,
          max: 100,
          ticks: { color: '#8b949e', font: { size: 10 }, callback: function (v) { return v + '%'; } },
          grid: { color: '#30363d' }
        }
      }
    }
  });
}

function buildCard(name, cfg, d) {
  const repoUrl = "https://github.com/" + cfg.repo;
  const prs = (d.prs && d.prs.prs) || [];
  const issues = (d.issues && d.issues.issues) || [];
  const releases = (d.releases && d.releases.releases) || [];

  const openPrs = prs.filter((p) => p.state === "open");
  const latestRelease = releases.length ? releases[0].tag_name : "-";

  let html = "";

  // Header (no role badge)
  html += '<div class="card-header">';
  html += '<a href="' + repoUrl + '" target="_blank">' + escapeHtml(name) + "</a>";
  html += "</div>";

  // Stats
  html += '<div class="stats">';
  html += "<span>PRs: <span class='stat-value'>" + openPrs.length + "</span></span>";
  html += "<span>Issues: <span class='stat-value'>" + issues.length + "</span></span>";
  html += "<span>Release: <span class='stat-value'>" + escapeHtml(latestRelease) + "</span></span>";
  html += "</div>";

  // Test Results section (ROCm vs CUDA)
  if (d.testResults) {
    html += buildTestSection(d.testResults, d.parityReport);
  }

  // This Week section
  html += buildWeekSection(prs, issues, releases, cfg);

  // Top Contributors section
  html += buildContributorSection(prs);

  // PRs section
  html += buildPRSection(openPrs);

  // Issues section
  html += buildIssueSection(issues);

  // Releases section
  html += buildReleaseSection(releases);

  return html;
}

function buildWeekSection(prs, issues, releases, cfg) {
  const stats = getWeeklyStats(prs, issues, releases);
  const recentPrs = prs.filter(
    (p) => isThisWeek(p.created_at) || (p.merged && isThisWeek(p.updated_at))
  );

  // Build stat summary line
  const parts = [];
  if (stats.prsOpened) parts.push(stats.prsOpened + " opened");
  if (stats.prsMerged) parts.push(stats.prsMerged + " merged");
  if (stats.issuesOpened) parts.push(stats.issuesOpened + " new issue" + (stats.issuesOpened > 1 ? "s" : ""));
  if (stats.newReleases) parts.push(stats.newReleases + " release" + (stats.newReleases > 1 ? "s" : ""));

  const summaryText = parts.length ? parts.join(", ") : "No activity";

  let html = '<details class="week-activity" open>';
  html += '<summary>This Week <span class="week-summary-inline">' + escapeHtml(summaryText) + '</span></summary>';

  if (recentPrs.length) {
    html += '<table><tr><th>#</th><th>Title</th><th>Author</th><th>Status</th></tr>';
    for (const pr of recentPrs.slice(0, 10)) {
      html += "<tr>";
      html += '<td><a href="' + pr.html_url + '" target="_blank">#' + pr.number + "</a></td>";
      html += '<td class="td-title" title="' + escapeHtml(pr.title) + '">' + escapeHtml(pr.title.slice(0, 60)) + "</td>";
      html += "<td>" + escapeHtml(effectiveAuthor(pr)) + "</td>";
      html += "<td>" + statusBadge(pr) + "</td>";
      html += "</tr>";
    }
    if (recentPrs.length > 10) {
      html += '<tr><td colspan="4" class="empty">...and ' + (recentPrs.length - 10) + " more</td></tr>";
    }
    html += "</table>";
  } else {
    html += '<p class="empty">No PRs this week</p>';
  }

  html += "</details>";
  return html;
}

function buildContributorSection(prs) {
  const contributors = getProjectContributors(prs, 10);
  if (!contributors.length) {
    return "<details><summary>Top Contributors (0)</summary><p class='empty'>None</p></details>";
  }

  let html = "<details><summary>Top Contributors (" + contributors.length + ")</summary>";
  html += '<table><tr><th>#</th><th>Author</th><th>Submitted</th><th>Merged</th></tr>';

  for (let i = 0; i < contributors.length; i++) {
    const c = contributors[i];
    html += "<tr>";
    html += '<td class="contrib-rank">' + (i + 1) + "</td>";
    html += '<td><a href="https://github.com/' + encodeURIComponent(c.author) + '" target="_blank">' + escapeHtml(c.author) + "</a></td>";
    html += '<td class="contrib-count">' + c.submitted + "</td>";
    html += '<td class="contrib-count">' + c.merged + "</td>";
    html += "</tr>";
  }

  html += "</table></details>";
  return html;
}

function buildPRSection(prs) {
  if (!prs.length) {
    return "<details><summary>Pull Requests (0)</summary><p class='empty'>None</p></details>";
  }

  let html = "<details><summary>Pull Requests (" + prs.length + ")</summary>";
  html += "<table><tr><th>#</th><th>Title</th><th>Author</th><th>Status</th><th>Updated</th></tr>";

  for (const pr of prs.slice(0, 50)) {
    html += "<tr>";
    html += '<td><a href="' + pr.html_url + '" target="_blank">#' + pr.number + "</a></td>";
    html += '<td class="td-title" title="' + escapeHtml(pr.title) + '">' + escapeHtml(pr.title.slice(0, 60)) + "</td>";
    html += "<td>" + escapeHtml(effectiveAuthor(pr)) + "</td>";
    html += "<td>" + statusBadge(pr) + "</td>";
    html += "<td>" + relativeTime(pr.updated_at) + "</td>";
    html += "</tr>";
  }

  if (prs.length > 50) {
    html += '<tr><td colspan="5" class="empty">...and ' + (prs.length - 50) + " more</td></tr>";
  }

  html += "</table></details>";
  return html;
}

function buildIssueSection(issues) {
  if (!issues.length) {
    return "<details><summary>Issues (0)</summary><p class='empty'>None</p></details>";
  }

  let html = "<details><summary>Issues (" + issues.length + ")</summary>";
  html += "<table><tr><th>#</th><th>Title</th><th>Author</th><th>Updated</th></tr>";

  for (const issue of issues.slice(0, 50)) {
    html += "<tr>";
    html += '<td><a href="' + issue.html_url + '" target="_blank">#' + issue.number + "</a></td>";
    html += '<td class="td-title" title="' + escapeHtml(issue.title) + '">' + escapeHtml(issue.title.slice(0, 60)) + "</td>";
    html += "<td>" + escapeHtml(issue.author) + "</td>";
    html += "<td>" + relativeTime(issue.updated_at) + "</td>";
    html += "</tr>";
  }

  if (issues.length > 50) {
    html += '<tr><td colspan="4" class="empty">...and ' + (issues.length - 50) + " more</td></tr>";
  }

  html += "</table></details>";
  return html;
}

function buildReleaseSection(releases) {
  if (!releases.length) {
    return "<details><summary>Releases (0)</summary><p class='empty'>None</p></details>";
  }

  let html = "<details><summary>Releases (" + releases.length + ")</summary>";
  html += "<table><tr><th>Tag</th><th>Published</th></tr>";

  for (const r of releases) {
    html += "<tr>";
    html += '<td><a href="' + r.html_url + '" target="_blank">' + escapeHtml(r.tag_name) + "</a></td>";
    html += "<td>" + formatDate(r.published_at) + "</td>";
    html += "</tr>";
  }

  html += "</table></details>";
  return html;
}

function buildTestSection(testResults, parityReport) {
  var rocm = testResults.rocm;
  var cuda = testResults.cuda;

  // Build summary text for the <summary> line
  var summaryText = "";
  if (parityReport && parityReport.summary) {
    summaryText = "Parity: " + parityReport.summary.parity_pct.toFixed(1) + "% (matched)";
  } else if (testResults.cuda_parity) {
    summaryText = "Parity: " + testResults.cuda_parity.ratio.toFixed(1) + "%";
  } else {
    var parts = [];
    if (rocm && rocm.summary) {
      parts.push("ROCm: " + (rocm.summary.pass_rate != null ? rocm.summary.pass_rate.toFixed(1) + "%" : "N/A"));
    }
    if (cuda && cuda.summary) {
      parts.push("CUDA: " + (cuda.summary.pass_rate != null ? cuda.summary.pass_rate.toFixed(1) + "%" : "N/A"));
    }
    summaryText = parts.length ? parts.join(" | ") : "No data";
  }

  var html = '<details class="test-results">';
  html += '<summary>Test Results <span class="test-summary-inline">' + escapeHtml(summaryText) + "</span></summary>";

  // Pass rate bars
  if (rocm && rocm.summary) {
    html += buildPassRateBar("ROCm", rocm.summary, rocm.run_url);
  }
  if (cuda && cuda.summary) {
    html += buildPassRateBar("CUDA", cuda.summary, cuda.run_url);
  }

  // Suite detail table
  html += buildSuiteTable(rocm, cuda);

  // Freshness line
  var dates = [];
  if (rocm && rocm.run_date) dates.push("ROCm: " + relativeTime(rocm.run_date));
  if (cuda && cuda.run_date) dates.push("CUDA: " + relativeTime(cuda.run_date));
  if (dates.length) {
    html += '<div class="test-meta">Runs: ' + dates.join(", ");
    if (testResults.source === "manual") html += " (manual)";
    html += "</div>";
  }

  html += "</details>";
  return html;
}

// ---------------------------------------------------------------------------
// Activity View (Tab 3)
// ---------------------------------------------------------------------------

function renderActivityView(projectsCfg, dataMap) {
  var el = document.getElementById("activity-view");
  var html = "";

  // Activity summary boxes (cross-project)
  html += buildActivitySummary(dataMap);

  // Per-section views
  html += '<div class="activity-sections">';
  html += buildPRVelocitySection(projectsCfg, dataMap);
  html += buildCISignalSection(projectsCfg, dataMap);
  html += buildCIHealthSection(projectsCfg, dataMap);
  html += buildContributorSection2(projectsCfg, dataMap);
  html += buildIssueHealthSection(projectsCfg, dataMap);
  html += buildReleaseCadenceSection(projectsCfg, dataMap);
  html += '</div>';

  el.innerHTML = html;
}

function buildActivitySummary(dataMap) {
  var totalOpened = 0, totalMerged = 0, totalActive = 0, totalStale = 0;
  var ttms = [];

  for (var name in dataMap) {
    var a = (dataMap[name] || {}).activity;
    if (!a) continue;
    var pv = a.pr_velocity || {};
    var tw = pv.this_week || {};
    totalOpened += tw.opened || 0;
    totalMerged += tw.merged || 0;
    totalStale += pv.stale_prs || 0;
    if (pv.median_time_to_merge_hours != null) ttms.push(pv.median_time_to_merge_hours);
    var c = a.contributors || {};
    totalActive += c.active_this_week || 0;
  }

  var avgTTM = ttms.length > 0 ? ttms.reduce(function (a, b) { return a + b; }, 0) / ttms.length : null;

  var html = '<h2>Activity Overview</h2>';
  html += '<div class="activity-boxes">';
  html += '<div class="activity-box activity-box-opened"><div class="activity-num">' + totalOpened + '</div><div class="activity-label">PRs Opened (week)</div></div>';
  html += '<div class="activity-box activity-box-merged"><div class="activity-num">' + totalMerged + '</div><div class="activity-label">PRs Merged (week)</div></div>';
  html += '<div class="activity-box activity-box-ttm"><div class="activity-num">' + formatHours(avgTTM) + '</div><div class="activity-label">Avg Time-to-Merge</div></div>';
  html += '<div class="activity-box activity-box-contributors"><div class="activity-num">' + totalActive + '</div><div class="activity-label">Active Contributors</div></div>';
  html += '<div class="activity-box activity-box-stale"><div class="activity-num">' + totalStale + '</div><div class="activity-label">Stale PRs (>30d)</div></div>';
  html += '</div>';
  return html;
}

function buildPRVelocitySection(projectsCfg, dataMap) {
  var html = '<div class="activity-section">';
  html += '<h3>PR Velocity</h3>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Opened</th><th>Merged</th><th>Closed</th>';
  html += '<th>Time-to-Merge</th><th>Stale</th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a) continue;
    var pv = a.pr_velocity || {};
    var tw = pv.this_week || {};
    var lw = pv.last_week || {};

    html += '<tr>';
    html += '<td class="project-name">' + escapeHtml(name) + '</td>';
    html += '<td>' + (tw.opened || 0) + deltaArrow(tw.opened, lw.opened) + '</td>';
    html += '<td>' + (tw.merged || 0) + deltaArrow(tw.merged, lw.merged) + '</td>';
    html += '<td>' + (tw.closed || 0) + '</td>';
    html += '<td>' + formatHours(pv.median_time_to_merge_hours) + '</td>';
    html += '<td>' + (pv.stale_prs > 0 ? '<span class="stale-count">' + pv.stale_prs + '</span>' : '0') + '</td>';
    html += '</tr>';
  }

  html += '</table></div>';
  return html;
}

function buildCISignalSection(projectsCfg, dataMap) {
  // Only show projects that have CI signal data
  var hasData = false;
  for (var name in dataMap) {
    if (dataMap[name].activity && dataMap[name].activity.ci_signal_time) {
      hasData = true;
      break;
    }
  }
  if (!hasData) return '';

  var html = '<div class="activity-section">';
  html += '<h3>Time to CI Signal</h3>';
  html += '<p class="section-desc">Median time from workflow trigger to completion (last 20 runs)</p>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Platform</th><th>Median</th><th>P90</th><th>Min</th><th>Max</th><th></th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a || !a.ci_signal_time) continue;

    var validPlatforms = Object.keys(a.ci_signal_time).filter(function (p) { return a.ci_signal_time[p] != null; });
    if (validPlatforms.length === 0) continue;
    var first = true;
    for (var pi = 0; pi < validPlatforms.length; pi++) {
      var platform = validPlatforms[pi];
      var d = a.ci_signal_time[platform];

      html += '<tr>';
      if (first) {
        html += '<td class="project-name" rowspan="' + validPlatforms.length + '">' + escapeHtml(name) + '</td>';
        first = false;
      }
      html += '<td><span class="platform-label platform-' + platform + '">' + platform.toUpperCase() + '</span></td>';
      html += '<td class="ci-signal-val">' + formatMinutes(d.median_minutes) + '</td>';
      html += '<td>' + formatMinutes(d.p90_minutes) + '</td>';
      html += '<td>' + formatMinutes(d.min_minutes) + '</td>';
      html += '<td>' + formatMinutes(d.max_minutes) + '</td>';
      // Visual bar: median relative to 6 hours (360 min)
      var pct = Math.min(100, (d.median_minutes / 360) * 100);
      var barColor = d.median_minutes < 60 ? 'rate-good' : d.median_minutes < 180 ? 'rate-warn' : 'rate-bad';
      html += '<td class="ci-signal-bar-cell"><div class="ci-signal-bar-bg"><div class="ci-signal-bar-fill ' + barColor + '" style="width:' + pct + '%"></div></div></td>';
      html += '</tr>';
    }
  }

  html += '</table></div>';
  return html;
}

function buildCIHealthSection(projectsCfg, dataMap) {
  var hasData = false;
  for (var name in dataMap) {
    if (dataMap[name].activity && dataMap[name].activity.ci_health) {
      hasData = true;
      break;
    }
  }
  if (!hasData) return '';

  var html = '<div class="activity-section">';
  html += '<h3>CI Health</h3>';
  html += '<p class="section-desc">Build success rate from last 20 workflow runs</p>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>ROCm</th><th></th><th>CUDA</th><th></th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a || !a.ci_health) continue;
    var rocm = a.ci_health.rocm;
    var cuda = a.ci_health.cuda;

    html += '<tr>';
    html += '<td class="project-name">' + escapeHtml(name) + '</td>';

    if (rocm) {
      html += '<td>' + ciHealthBadge(rocm.success_rate) + '</td>';
      html += '<td class="ci-detail">' + rocm.succeeded + '/' + rocm.total_runs + ' passed</td>';
    } else {
      html += '<td colspan="2" class="text-muted">N/A</td>';
    }

    if (cuda) {
      html += '<td>' + ciHealthBadge(cuda.success_rate) + '</td>';
      html += '<td class="ci-detail">' + cuda.succeeded + '/' + cuda.total_runs + ' passed</td>';
    } else {
      html += '<td colspan="2" class="text-muted">N/A</td>';
    }

    html += '</tr>';
  }

  html += '</table></div>';
  return html;
}

function buildContributorSection2(projectsCfg, dataMap) {
  var html = '<div class="activity-section">';
  html += '<h3>Contributor Activity</h3>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Active (week)</th><th>Total</th><th>Bus Factor</th><th>Top Contributor</th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a) continue;
    var c = a.contributors || {};
    var top = (c.top_contributors && c.top_contributors.length > 0) ? c.top_contributors[0] : null;

    html += '<tr>';
    html += '<td class="project-name">' + escapeHtml(name) + '</td>';
    html += '<td>' + (c.active_this_week || 0) + '</td>';
    html += '<td>' + (c.total_contributors || 0) + '</td>';
    html += '<td>' + (c.bus_factor != null ? '<span class="bus-factor' + (c.bus_factor <= 2 ? ' bus-factor-warn' : '') + '">' + c.bus_factor + '</span>' : 'N/A') + '</td>';
    html += '<td>' + (top ? '<a href="https://github.com/' + encodeURIComponent(top.author) + '" target="_blank">' + escapeHtml(top.author) + '</a> (' + top.prs_submitted + ' PRs)' : 'N/A') + '</td>';
    html += '</tr>';
  }

  html += '</table></div>';
  return html;
}

function buildIssueHealthSection(projectsCfg, dataMap) {
  var html = '<div class="activity-section">';
  html += '<h3>Issue Health</h3>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Open</th><th>Opened (week)</th><th>Closed (week)</th><th>Net</th><th>Unanswered</th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a) continue;
    var ih = a.issue_health || {};
    var net = (ih.opened_this_week || 0) - (ih.closed_this_week || 0);
    var netClass = net > 0 ? 'delta-up' : net < 0 ? 'delta-down' : 'delta-flat';
    var netStr = (net > 0 ? '+' : '') + net;

    html += '<tr>';
    html += '<td class="project-name">' + escapeHtml(name) + '</td>';
    html += '<td>' + (ih.total_open || 0) + '</td>';
    html += '<td>' + (ih.opened_this_week || 0) + '</td>';
    html += '<td>' + (ih.closed_this_week || 0) + '</td>';
    html += '<td><span class="delta ' + netClass + '">' + netStr + '</span></td>';
    html += '<td>' + (ih.unanswered > 0 ? '<span class="unanswered-count">' + ih.unanswered + '</span>' : '0') + '</td>';
    html += '</tr>';
  }

  html += '</table></div>';
  return html;
}

function buildReleaseCadenceSection(projectsCfg, dataMap) {
  var html = '<div class="activity-section">';
  html += '<h3>Release Cadence</h3>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Latest</th><th>Days Ago</th><th>Avg Interval</th><th>Total Releases</th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var a = (dataMap[name] || {}).activity;
    if (!a) continue;
    var rc = a.release_cadence;
    if (!rc) {
      html += '<tr><td class="project-name">' + escapeHtml(name) + '</td><td colspan="4" class="text-muted">No releases</td></tr>';
      continue;
    }

    var daysAgoClass = '';
    if (rc.days_since_last != null) {
      daysAgoClass = rc.days_since_last > 90 ? ' release-stale' : rc.days_since_last > 30 ? ' release-aging' : '';
    }

    html += '<tr>';
    html += '<td class="project-name">' + escapeHtml(name) + '</td>';
    html += '<td>' + escapeHtml(rc.latest_tag || '-') + '</td>';
    html += '<td class="' + daysAgoClass + '">' + (rc.days_since_last != null ? Math.round(rc.days_since_last) + 'd' : 'N/A') + '</td>';
    html += '<td>' + (rc.avg_interval_days != null ? Math.round(rc.avg_interval_days) + 'd' : 'N/A') + '</td>';
    html += '<td>' + (rc.total_releases || 0) + '</td>';
    html += '</tr>';
  }

  html += '</table></div>';
  return html;
}

// ---------------------------------------------------------------------------
// Trends View (Tab 4)
// ---------------------------------------------------------------------------

function renderTrendsView(projectsCfg, dataMap, historyData) {
  var el = document.getElementById("trends-view");

  if (!historyData || historyData.length === 0) {
    el.innerHTML = '<h2>Trends</h2><p class="empty">No historical data yet. Trends will appear after multiple weekly snapshots.</p>';
    return;
  }

  var html = '<h2>Trends</h2>';
  html += '<p class="section-desc">Weekly snapshots across projects. More data points will appear over time.</p>';

  // Chart containers
  html += '<div class="trends-grid">';
  html += '<div class="trend-card"><h4>PRs Merged per Week</h4><canvas id="chart-prs-merged"></canvas></div>';
  html += '<div class="trend-card"><h4>Open Issues</h4><canvas id="chart-open-issues"></canvas></div>';
  html += '<div class="trend-card"><h4>Active Contributors</h4><canvas id="chart-active-contributors"></canvas></div>';
  html += '<div class="trend-card"><h4>Time-to-Merge (median, hours)</h4><canvas id="chart-ttm"></canvas></div>';
  html += '<div class="trend-card"><h4>CI Signal Time - ROCm (median, min)</h4><canvas id="chart-ci-signal-rocm"></canvas></div>';
  html += '<div class="trend-card"><h4>Test Pass Rate - ROCm (%)</h4><canvas id="chart-test-rate-rocm"></canvas></div>';
  html += '<div class="trend-card"><h4>CUDA Parity - PyTorch (%)</h4><canvas id="chart-parity-pct"></canvas></div>';
  html += '</div>';

  el.innerHTML = html;

  // Build charts
  var weeks = historyData.map(function (h) { return h.week; });
  var projectNames = Object.keys(projectsCfg);
  var colors = [
    '#58a6ff', '#f78166', '#7ee787', '#d2a8ff', '#ffd33d',
    '#ff7b72', '#79c0ff', '#a5d6ff', '#d29922', '#8b949e'
  ];

  buildTrendChart('chart-prs-merged', weeks, historyData, projectNames, 'prs_merged', colors);
  buildTrendChart('chart-open-issues', weeks, historyData, projectNames, 'open_issues', colors);
  buildTrendChart('chart-active-contributors', weeks, historyData, projectNames, 'active_contributors', colors);
  buildTrendChart('chart-ttm', weeks, historyData, projectNames, 'median_ttm_hours', colors);
  buildTrendChart('chart-ci-signal-rocm', weeks, historyData, projectNames, 'ci_signal_rocm_median_min', colors);
  buildTrendChart('chart-test-rate-rocm', weeks, historyData, projectNames, 'test_pass_rate_rocm', colors);
  buildTrendChart('chart-parity-pct', weeks, historyData, ['pytorch'], 'parity_pct', ['#58a6ff']);
}

function buildTrendChart(canvasId, weeks, historyData, projectNames, metric, colors) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;

  var datasets = [];
  for (var i = 0; i < projectNames.length; i++) {
    var name = projectNames[i];
    var data = weeks.map(function (w, idx) {
      var snap = historyData[idx];
      if (!snap || !snap.projects || !snap.projects[name]) return null;
      var val = snap.projects[name][metric];
      return val != null ? val : null;
    });
    // Only include if there's at least one data point
    if (data.some(function (v) { return v != null; })) {
      datasets.push({
        label: name,
        data: data,
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '33',
        tension: 0.3,
        pointRadius: 3,
        borderWidth: 2,
        spanGaps: true,
      });
    }
  }

  if (datasets.length === 0) {
    canvas.parentElement.style.display = 'none';
    return;
  }

  new Chart(canvas, {
    type: 'line',
    data: { labels: weeks, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#e6edf3', font: { size: 11 } }
        }
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', font: { size: 11 } },
          grid: { color: '#30363d' }
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#8b949e', font: { size: 11 } },
          grid: { color: '#30363d' }
        }
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Builds View (Tab 5)
// ---------------------------------------------------------------------------

function renderBuildsView(projectsCfg, dataMap, historyData) {
  var el = document.getElementById("builds-view");
  var html = '<h2>Builds & Dependencies</h2>';

  // Dependency graph
  html += buildDependencyGraph(projectsCfg, dataMap);

  // Build time summary boxes
  html += buildBuildTimeSummary(projectsCfg, dataMap);

  // Build time details table
  html += buildBuildTimeDetails(projectsCfg, dataMap);

  // Trend chart
  if (historyData && historyData.length > 0) {
    html += '<div class="build-details">';
    html += '<h3>Build Time Trends</h3>';
    html += '<div class="trends-grid">';
    html += '<div class="trend-card"><h4>Build Duration (median, min)</h4><canvas id="chart-build-duration"></canvas></div>';
    html += '</div>';
    html += '</div>';
  }

  el.innerHTML = html;

  // Render trend chart
  if (historyData && historyData.length > 0) {
    buildBuildTrendChart(projectsCfg, dataMap, historyData);
  }
}

function buildDependencyGraph(projectsCfg, dataMap) {
  var graphId = "dep-graph-" + Math.random().toString(36).substr(2, 6);

  // Separate standalone projects (no deps AND not depended upon)
  var depended = {};
  for (var name in projectsCfg) {
    var deps = projectsCfg[name].depends_on || [];
    for (var i = 0; i < deps.length; i++) depended[deps[i]] = true;
  }
  var graphNodes = [];
  var standaloneNodes = [];
  for (var name in projectsCfg) {
    var deps = projectsCfg[name].depends_on || [];
    if (deps.length === 0 && !depended[name]) {
      standaloneNodes.push(name);
    } else {
      graphNodes.push(name);
    }
  }

  // Build node info for badge text/color
  var nodeInfo = {};
  for (var name in projectsCfg) {
    var d = dataMap[name] || {};
    var bt = d.buildTimes;
    var badgeText = "";
    var status = "none";
    if (bt && bt.workflows) {
      var wfNames = Object.keys(bt.workflows);
      if (wfNames.length > 0) {
        var wf = bt.workflows[wfNames[0]];
        var median = wf.stats ? wf.stats.median_minutes : null;
        var target = wf.target_minutes;
        if (median != null) {
          badgeText = formatMinutes(median);
          if (target) {
            if (median <= target) status = "good";
            else if (median <= target * 1.2) status = "warn";
            else status = "bad";
          }
        }
      }
    }
    var roleLabel = (projectsCfg[name].role === "active_dev") ? "core" : "upstream";
    nodeInfo[name] = { badge: badgeText, status: status, role: roleLabel };
  }

  // Build HTML container: SVG for dagre graph + standalone section
  var html = '<div class="dep-graph" id="' + graphId + '">';
  html += '<h3>Project Dependencies</h3>';
  html += '<div class="dep-graph-svg-wrap"><svg id="' + graphId + '-svg"></svg></div>';

  if (standaloneNodes.length > 0) {
    html += '<div class="dep-standalone"><span class="dep-standalone-label">Standalone</span>';
    for (var si = 0; si < standaloneNodes.length; si++) {
      var sname = standaloneNodes[si];
      var sni = nodeInfo[sname];
      var scfg = projectsCfg[sname];
      html += '<a href="https://github.com/' + scfg.repo + '" target="_blank" class="dep-standalone-node dep-standalone-' + sni.role + '">';
      html += escapeHtml(sname);
      if (sni.badge) html += ' <span class="dep-node-badge dep-badge-' + sni.status + '">' + sni.badge + '</span>';
      html += '</a>';
    }
    html += '</div>';
  }
  html += '</div>';

  // Store render info for when the tab becomes visible
  window._depGraphPending = {
    graphId: graphId,
    graphNodes: graphNodes,
    projectsCfg: projectsCfg,
    nodeInfo: nodeInfo
  };

  return html;
}

function renderDagreGraph(graphId, graphNodes, projectsCfg, nodeInfo) {
  var svgEl = document.getElementById(graphId + "-svg");
  if (!svgEl || !window.dagre || !window.d3) return;
  // Avoid double-render
  if (svgEl.getAttribute("data-rendered")) return;
  svgEl.setAttribute("data-rendered", "1");

  var g = new dagre.graphlib.Graph().setGraph({
    rankdir: "TB",
    nodesep: 50,
    ranksep: 60,
    marginx: 20,
    marginy: 20
  }).setDefaultEdgeLabel(function() { return {}; });

  var NODE_W = 120, NODE_H = 44;

  // Add nodes
  for (var i = 0; i < graphNodes.length; i++) {
    var name = graphNodes[i];
    g.setNode(name, { label: name, width: NODE_W, height: NODE_H });
  }

  // Add edges (dependency → dependent, i.e. top to bottom)
  for (var i = 0; i < graphNodes.length; i++) {
    var name = graphNodes[i];
    var deps = projectsCfg[name].depends_on || [];
    for (var j = 0; j < deps.length; j++) {
      if (g.hasNode(deps[j])) {
        g.setEdge(deps[j], name);
      }
    }
  }

  dagre.layout(g);

  var gGraph = g.graph();
  var svgW = gGraph.width + 40;
  var svgH = gGraph.height + 40;
  var svg = d3.select(svgEl)
    .attr("width", svgW)
    .attr("height", svgH)
    .attr("viewBox", "0 0 " + svgW + " " + svgH);

  // Clear any previous content
  svg.selectAll("*").remove();

  var defs = svg.append("defs");
  // Arrowhead marker
  defs.append("marker")
    .attr("id", "dep-arrow")
    .attr("viewBox", "0 0 12 12")
    .attr("refX", 10).attr("refY", 6)
    .attr("markerWidth", 10).attr("markerHeight", 10)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M2,2 L10,6 L2,10 L4,6 Z")
    .attr("fill", "#8b949e");

  // Glow filter for hover
  var filter = defs.append("filter").attr("id", "dep-glow");
  filter.append("feGaussianBlur").attr("stdDeviation", "2").attr("result", "blur");
  var merge = filter.append("feMerge");
  merge.append("feMergeNode").attr("in", "blur");
  merge.append("feMergeNode").attr("in", "SourceGraphic");

  // Assign colors to source nodes (nodes that have outgoing edges)
  var edgeColors = [
    "#58a6ff", // blue
    "#f0883e", // orange
    "#8957e5", // purple
    "#238636", // green
    "#da3633", // red
    "#d29922", // yellow
    "#3fb950", // bright green
    "#bc8cff", // lavender
    "#f778ba", // pink
    "#79c0ff", // light blue
  ];
  var sourceNodes = {};
  g.edges().forEach(function(e) { sourceNodes[e.v] = true; });
  var sourceList = Object.keys(sourceNodes).sort();
  var sourceColorMap = {};
  for (var si = 0; si < sourceList.length; si++) {
    sourceColorMap[sourceList[si]] = edgeColors[si % edgeColors.length];
  }

  // Create per-source arrowhead markers
  for (var si = 0; si < sourceList.length; si++) {
    var color = sourceColorMap[sourceList[si]];
    defs.append("marker")
      .attr("id", "dep-arrow-" + sourceList[si])
      .attr("viewBox", "0 0 12 12")
      .attr("refX", 10).attr("refY", 6)
      .attr("markerWidth", 10).attr("markerHeight", 10)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M2,2 L10,6 L2,10 L4,6 Z")
      .attr("fill", color);
  }

  var container = svg.append("g").attr("transform", "translate(20,20)");

  // Render edges first (behind nodes)
  var edgeGroup = container.append("g").attr("class", "dep-edges");
  g.edges().forEach(function(e) {
    var edge = g.edge(e);
    var points = edge.points;
    var color = sourceColorMap[e.v] || "#30363d";
    var line = d3.line()
      .x(function(p) { return p.x; })
      .y(function(p) { return p.y; })
      .curve(d3.curveBasis);
    edgeGroup.append("path")
      .attr("d", line(points))
      .attr("class", "dep-edge-path")
      .attr("data-from", e.v)
      .attr("data-to", e.w)
      .attr("data-color", color)
      .attr("stroke", color)
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", 0.6)
      .attr("fill", "none")
      .attr("marker-end", "url(#dep-arrow-" + e.v + ")");
  });

  // Render nodes
  var nodeGroup = container.append("g").attr("class", "dep-nodes");
  g.nodes().forEach(function(name) {
    var node = g.node(name);
    var ni = nodeInfo[name];
    var cfg = projectsCfg[name];
    var x = node.x - NODE_W / 2;
    var y = node.y - NODE_H / 2;

    var roleClass = ni.role === "core" ? "dep-svg-core" : "dep-svg-upstream";
    var statusColor = { good: "#238636", warn: "#d29922", bad: "#da3633", none: null }[ni.status];

    var ng = nodeGroup.append("g")
      .attr("class", "dep-svg-node " + roleClass)
      .attr("transform", "translate(" + x + "," + y + ")")
      .attr("data-node", name)
      .style("cursor", "pointer");

    // Node rectangle
    var rect = ng.append("rect")
      .attr("width", NODE_W).attr("height", NODE_H)
      .attr("rx", 8).attr("ry", 8)
      .attr("class", "dep-svg-rect");

    // Left accent bar for status
    if (statusColor) {
      ng.append("rect")
        .attr("x", 0).attr("y", 0)
        .attr("width", 3).attr("height", NODE_H)
        .attr("rx", 1.5)
        .attr("fill", statusColor);
    }

    // Project name
    ng.append("text")
      .attr("x", NODE_W / 2).attr("y", ni.badge ? 18 : 24)
      .attr("text-anchor", "middle")
      .attr("class", "dep-svg-name")
      .text(name);

    // Badge (build time)
    if (ni.badge) {
      ng.append("text")
        .attr("x", NODE_W / 2).attr("y", 34)
        .attr("text-anchor", "middle")
        .attr("class", "dep-svg-badge")
        .attr("fill", statusColor || "#8b949e")
        .text(ni.badge);
    }

    // Click to open repo
    ng.on("click", function() {
      var n = d3.select(this).attr("data-node");
      window.open("https://github.com/" + projectsCfg[n].repo, "_blank");
    });

    // Hover: highlight connected edges, dim others
    ng.on("mouseenter", function() {
      var n = d3.select(this).attr("data-node");
      d3.select(this).select(".dep-svg-rect").attr("filter", "url(#dep-glow)");
      edgeGroup.selectAll(".dep-edge-path").each(function() {
        var el = d3.select(this);
        if (el.attr("data-from") === n || el.attr("data-to") === n) {
          el.attr("stroke-width", 2.5).attr("stroke-opacity", 1);
        } else {
          el.attr("stroke-opacity", 0.1);
        }
      });
    });
    ng.on("mouseleave", function() {
      d3.select(this).select(".dep-svg-rect").attr("filter", null);
      edgeGroup.selectAll(".dep-edge-path").each(function() {
        var el = d3.select(this);
        el.attr("stroke-width", 1.5).attr("stroke-opacity", 0.6);
      });
    });
  });
}

function buildBuildTimeSummary(projectsCfg, dataMap) {
  var totalWorkflows = 0;
  var metTarget = 0;
  var missedTarget = 0;
  var allMedians = [];

  for (var name in projectsCfg) {
    var d = dataMap[name] || {};
    var bt = d.buildTimes;
    if (!bt || !bt.workflows) continue;

    for (var wfName in bt.workflows) {
      var wf = bt.workflows[wfName];
      totalWorkflows++;
      var median = wf.stats ? wf.stats.median_minutes : null;
      if (median != null) allMedians.push(median);
      var target = wf.target_minutes;
      if (target && median != null) {
        if (median <= target) {
          metTarget++;
        } else {
          missedTarget++;
        }
      }
    }
  }

  var avgDuration = allMedians.length > 0
    ? Math.round(allMedians.reduce(function (a, b) { return a + b; }, 0) / allMedians.length)
    : "N/A";

  var html = '<div class="build-summary-boxes">';
  html += '<div class="build-summary-box build-summary-box-total"><div class="build-summary-num">' + totalWorkflows + '</div><div class="build-summary-label">Workflows Tracked</div></div>';
  html += '<div class="build-summary-box build-summary-box-met"><div class="build-summary-num">' + metTarget + '</div><div class="build-summary-label">Meeting Target</div></div>';
  html += '<div class="build-summary-box build-summary-box-missed"><div class="build-summary-num">' + missedTarget + '</div><div class="build-summary-label">Over Target</div></div>';
  html += '<div class="build-summary-box build-summary-box-avg"><div class="build-summary-num">' + (typeof avgDuration === 'number' ? avgDuration + 'm' : avgDuration) + '</div><div class="build-summary-label">Avg Build Duration</div></div>';
  html += '</div>';
  return html;
}

function buildBuildTimeDetails(projectsCfg, dataMap) {
  var hasData = false;
  for (var name in dataMap) {
    if (dataMap[name].buildTimes && dataMap[name].buildTimes.workflows) {
      hasData = true;
      break;
    }
  }

  if (!hasData) {
    return '<div class="build-details"><h3>Build Time Details</h3><p class="empty">No build time data available yet. Data will appear after the daily collection runs.</p></div>';
  }

  var html = '<div class="build-details">';
  html += '<h3>Build Time Details</h3>';
  html += '<table class="activity-table"><tr>';
  html += '<th>Project</th><th>Workflow</th><th>Median</th><th>P90</th><th>Target</th><th>Status</th><th>Bottleneck Job</th><th></th>';
  html += '</tr>';

  for (var name in projectsCfg) {
    var d = dataMap[name] || {};
    var bt = d.buildTimes;
    if (!bt || !bt.workflows) continue;

    var wfNames = Object.keys(bt.workflows);
    var first = true;

    for (var wi = 0; wi < wfNames.length; wi++) {
      var wfName = wfNames[wi];
      var wf = bt.workflows[wfName];
      var stats = wf.stats || {};
      var target = wf.target_minutes;
      var median = stats.median_minutes;
      var p90 = stats.p90_minutes;

      // Status based on target
      var statusHtml = '<span class="text-muted">N/A</span>';
      var statusClass = '';
      if (target && median != null) {
        if (median <= target) {
          statusHtml = '<span class="build-target-met">Met</span>';
          statusClass = 'rate-good';
        } else if (median <= target * 1.2) {
          statusHtml = '<span class="build-target-warn">Close</span>';
          statusClass = 'rate-warn';
        } else {
          statusHtml = '<span class="build-target-missed">Over</span>';
          statusClass = 'rate-bad';
        }
      }

      // Bottleneck job
      var bottleneck = wf.bottleneck_job;
      var bottleneckHtml = bottleneck
        ? escapeHtml(bottleneck.name.slice(0, 30)) + ' (' + Math.round(bottleneck.duration_minutes) + 'm)'
        : '<span class="text-muted">-</span>';

      // Visual bar (relative to 120 min)
      var barPct = median != null ? Math.min(100, (median / 120) * 100) : 0;
      var barColor = statusClass || (median != null && median < 30 ? 'rate-good' : median != null && median < 60 ? 'rate-warn' : 'rate-bad');

      html += '<tr>';
      if (first) {
        html += '<td class="project-name" rowspan="' + wfNames.length + '">' + escapeHtml(name) + '</td>';
        first = false;
      }

      var latestUrl = wf.latest_run ? wf.latest_run.html_url : '';
      var wfLink = latestUrl
        ? '<a href="' + latestUrl + '" target="_blank">' + escapeHtml(wfName) + '</a>'
        : escapeHtml(wfName);

      html += '<td>' + wfLink + '</td>';
      html += '<td class="ci-signal-val">' + (median != null ? formatMinutes(median) : 'N/A') + '</td>';
      html += '<td>' + (p90 != null ? formatMinutes(p90) : 'N/A') + '</td>';
      html += '<td>' + (target ? target + 'm' : '<span class="text-muted">-</span>') + '</td>';
      html += '<td>' + statusHtml + '</td>';
      html += '<td>' + bottleneckHtml + '</td>';
      html += '<td class="build-bar-cell"><div class="build-bar-bg"><div class="build-bar-fill ' + barColor + '" style="width:' + barPct + '%"></div></div></td>';
      html += '</tr>';
    }
  }

  html += '</table></div>';
  return html;
}

function buildBuildTrendChart(projectsCfg, dataMap, historyData) {
  var canvas = document.getElementById("chart-build-duration");
  if (!canvas) return;

  var weeks = historyData.map(function (h) { return h.week; });
  var colors = [
    '#58a6ff', '#f78166', '#7ee787', '#d2a8ff', '#ffd33d',
    '#ff7b72', '#79c0ff', '#a5d6ff', '#d29922', '#8b949e'
  ];

  // Find all build_* metric keys across history
  var metricKeys = {};
  for (var i = 0; i < historyData.length; i++) {
    var snap = historyData[i];
    if (!snap || !snap.projects) continue;
    for (var pname in snap.projects) {
      var psnap = snap.projects[pname];
      for (var key in psnap) {
        if (key.indexOf("build_") === 0 && key.indexOf("_median_min") > 0) {
          var label = pname + "/" + key.replace("build_", "").replace("_median_min", "").replace(/_/g, " ");
          metricKeys[pname + ":" + key] = label;
        }
      }
    }
  }

  var datasets = [];
  var ci = 0;
  for (var mkey in metricKeys) {
    var parts = mkey.split(":");
    var pname = parts[0];
    var metric = parts[1];
    var label = metricKeys[mkey];

    var data = weeks.map(function (w, idx) {
      var snap = historyData[idx];
      if (!snap || !snap.projects || !snap.projects[pname]) return null;
      var val = snap.projects[pname][metric];
      return val != null ? val : null;
    });

    if (data.some(function (v) { return v != null; })) {
      datasets.push({
        label: label,
        data: data,
        borderColor: colors[ci % colors.length],
        backgroundColor: colors[ci % colors.length] + '33',
        tension: 0.3,
        pointRadius: 3,
        borderWidth: 2,
        spanGaps: true,
      });
      ci++;
    }
  }

  if (datasets.length === 0) {
    canvas.parentElement.innerHTML = '<p class="empty">Build time trends will appear after multiple snapshots include build data.</p>';
    return;
  }

  new Chart(canvas, {
    type: 'line',
    data: { labels: weeks, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#e6edf3', font: { size: 11 } }
        }
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', font: { size: 11 } },
          grid: { color: '#30363d' }
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: 'Minutes', color: '#8b949e' },
          ticks: { color: '#8b949e', font: { size: 11 } },
          grid: { color: '#30363d' }
        }
      }
    }
  });
}

function buildSuiteTable(rocm, cuda) {
  var hasSuites = (rocm && rocm.suites && rocm.suites.length) || (cuda && cuda.suites && cuda.suites.length);
  if (!hasSuites) return "";

  var html = '<table class="suite-table">';
  html += "<tr><th>Suite / Job</th><th>Result</th></tr>";

  // ROCm suites
  if (rocm && rocm.suites && rocm.suites.length) {
    html += '<tr><td colspan="2" class="suite-platform-header">ROCm</td></tr>';
    for (var i = 0; i < rocm.suites.length && i < 20; i++) {
      var s = rocm.suites[i];
      html += "<tr>";
      html += '<td class="td-title" title="' + escapeHtml(s.name) + '">' + escapeHtml(s.name.slice(0, 60)) + "</td>";
      html += "<td>" + suiteBadge(s) + "</td>";
      html += "</tr>";
    }
    if (rocm.suites.length > 20) {
      html += '<tr><td colspan="2" class="empty">...and ' + (rocm.suites.length - 20) + " more</td></tr>";
    }
  }

  // CUDA suites
  if (cuda && cuda.suites && cuda.suites.length) {
    html += '<tr><td colspan="2" class="suite-platform-header">CUDA</td></tr>';
    for (var i = 0; i < cuda.suites.length && i < 20; i++) {
      var s = cuda.suites[i];
      html += "<tr>";
      html += '<td class="td-title" title="' + escapeHtml(s.name) + '">' + escapeHtml(s.name.slice(0, 60)) + "</td>";
      html += "<td>" + suiteBadge(s) + "</td>";
      html += "</tr>";
    }
    if (cuda.suites.length > 20) {
      html += '<tr><td colspan="2" class="empty">...and ' + (cuda.suites.length - 20) + " more</td></tr>";
    }
  }

  html += "</table>";
  return html;
}
