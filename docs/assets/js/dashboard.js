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
    const [prs, issues, releases] = await Promise.all([
      fetchJSON("data/" + name + "/prs.json"),
      fetchJSON("data/" + name + "/issues.json"),
      fetchJSON("data/" + name + "/releases.json"),
    ]);
    dataMap[name] = { prs, issues, releases };
  });

  await Promise.all(fetches);

  // Find latest collected_at for header
  let latestTs = null;
  for (const name of names) {
    const d = dataMap[name];
    for (const src of [d.prs, d.issues, d.releases]) {
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

  // Render weekly summary, then project cards
  renderWeeklySummary(dataMap);
  renderCards(projects.projects, dataMap);
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
      html += "<td>" + escapeHtml(pr.author) + "</td>";
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
    html += "<td>" + escapeHtml(pr.author) + "</td>";
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
