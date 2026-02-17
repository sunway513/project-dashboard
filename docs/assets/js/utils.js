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
