/**
 * Utility functions for the project dashboard.
 */

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) return null;
  return resp.json();
}

function formatDate(iso) {
  if (!iso) return "-";
  return iso.slice(0, 10);
}

function relativeTime(iso) {
  if (!iso) return "";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffDay > 30) return formatDate(iso);
  if (diffDay > 0) return diffDay + "d ago";
  if (diffHr > 0) return diffHr + "h ago";
  if (diffMin > 0) return diffMin + "m ago";
  return "just now";
}

function statusBadge(pr) {
  if (pr.merged) return '<span class="badge badge-merged">merged</span>';
  if (pr.state === "closed") return '<span class="badge badge-closed">closed</span>';
  if (pr.draft) return '<span class="badge badge-draft">draft</span>';
  return '<span class="badge badge-open">open</span>';
}

function roleBadge(role) {
  if (role === "active_dev") return '<span class="badge badge-dev">dev</span>';
  return '<span class="badge badge-watch">watch</span>';
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function isThisWeek(iso) {
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < 7 * 86400000;
}

function getWeeklyStats(prs, issues, releases) {
  const prsOpened = prs.filter((p) => isThisWeek(p.created_at)).length;
  const prsMerged = prs.filter((p) => p.merged && isThisWeek(p.updated_at)).length;
  const issuesOpened = issues.filter((i) => isThisWeek(i.created_at)).length;
  const newReleases = releases.filter((r) => isThisWeek(r.published_at)).length;
  return { prsOpened, prsMerged, issuesOpened, newReleases };
}

function isBot(author) {
  if (!author) return true;
  var a = author.toLowerCase();
  return a.includes("bot") || a.includes("copybara");
}

function suiteBadge(suite) {
  // If suite has test counts, show "passed/total"
  if (suite.tests != null) {
    var cls = suite.failed > 0 ? "suite-conclusion-failure" : "suite-conclusion-success";
    return '<span class="suite-conclusion ' + cls + '">' + suite.passed + "/" + suite.tests + "</span>";
  }
  // Otherwise show conclusion text
  var conclusion = suite.conclusion || "unknown";
  var cls = "suite-conclusion-" + (conclusion === "success" ? "success" : conclusion === "failure" ? "failure" : "skipped");
  return '<span class="suite-conclusion ' + cls + '">' + escapeHtml(conclusion) + "</span>";
}

function buildPassRateBar(label, summary, runUrl) {
  if (!summary) return "";
  var rate = summary.pass_rate != null ? summary.pass_rate : 0;
  var colorClass = rate >= 95 ? "rate-good" : rate >= 80 ? "rate-warn" : "rate-bad";
  var pctText = rate.toFixed(1) + "%";
  var labelHtml = runUrl
    ? '<a href="' + runUrl + '" target="_blank">' + escapeHtml(label) + "</a>"
    : escapeHtml(label);
  return (
    '<div class="pass-rate-row">' +
    '<span class="pass-rate-label">' + labelHtml + "</span>" +
    '<div class="pass-rate-bar-bg"><div class="pass-rate-bar-fill ' + colorClass + '" style="width:' + rate + '%"></div></div>' +
    '<span class="pass-rate-pct">' + pctText + "</span>" +
    "</div>"
  );
}

function buildParityBar(parity) {
  if (!parity) return "";
  var ratio = parity.ratio;
  var barWidth = Math.min(ratio, 100);
  var colorClass = ratio >= 90 ? "rate-good" : ratio >= 50 ? "rate-warn" : "rate-bad";
  var levelLabel = parity.level === "test" ? "tests" : "jobs";
  var detail = parity.rocm_count + " / " + parity.cuda_count + " " + levelLabel;
  return (
    '<div class="pass-rate-row">' +
    '<span class="pass-rate-label">Parity</span>' +
    '<div class="pass-rate-bar-bg"><div class="pass-rate-bar-fill ' + colorClass + '" style="width:' + barWidth + '%"></div></div>' +
    '<span class="pass-rate-pct">' + ratio.toFixed(1) + '%</span>' +
    '<span class="parity-detail">' + detail + '</span>' +
    '</div>'
  );
}

function deltaArrow(current, previous) {
  if (previous == null || current == null) return "";
  var diff = current - previous;
  if (diff > 0) return ' <span class="delta delta-up">+' + diff + '</span>';
  if (diff < 0) return ' <span class="delta delta-down">' + diff + '</span>';
  return ' <span class="delta delta-flat">0</span>';
}

function formatMinutes(min) {
  if (min == null) return "N/A";
  if (min < 60) return Math.round(min) + "m";
  if (min < 1440) return (min / 60).toFixed(1) + "h";
  return (min / 1440).toFixed(1) + "d";
}

function formatHours(hours) {
  if (hours == null) return "N/A";
  if (hours < 1) return Math.round(hours * 60) + "m";
  if (hours < 24) return hours.toFixed(1) + "h";
  return (hours / 24).toFixed(1) + "d";
}

function formatSeconds(secs) {
  if (secs == null) return "N/A";
  if (secs < 60) return Math.round(secs) + "s";
  if (secs < 3600) return (secs / 60).toFixed(1) + "m";
  return (secs / 3600).toFixed(1) + "h";
}

function ciHealthBadge(rate) {
  if (rate == null) return '<span class="ci-badge ci-badge-unknown">N/A</span>';
  var cls = rate >= 80 ? "ci-badge-good" : rate >= 50 ? "ci-badge-warn" : "ci-badge-bad";
  return '<span class="ci-badge ' + cls + '">' + rate.toFixed(0) + '%</span>';
}

function buildMiniBar(value, max, colorClass) {
  var pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return '<div class="mini-bar-bg"><div class="mini-bar-fill ' + colorClass + '" style="width:' + pct + '%"></div></div>';
}

function getProjectContributors(prs, limit) {
  const map = new Map();
  for (const pr of prs) {
    if (isBot(pr.author)) continue;
    if (!map.has(pr.author)) {
      map.set(pr.author, { author: pr.author, submitted: 0, merged: 0 });
    }
    const entry = map.get(pr.author);
    entry.submitted++;
    if (pr.merged) entry.merged++;
  }
  return Array.from(map.values())
    .sort((a, b) => b.submitted - a.submitted || b.merged - a.merged)
    .slice(0, limit || 10);
}
