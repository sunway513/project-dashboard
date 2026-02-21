#!/usr/bin/env python3
"""Collect activity metrics for each project: PR velocity, contributor activity,
issue health, CI health, release cadence, and time-to-CI-signal."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
DATA = ROOT / "data"

# Reuse workflow IDs from collect_tests.py for CI health metrics
WORKFLOW_IDS = {
    "pytorch": {
        "rocm": 139700577,
        "cuda": 16535519,
    },
    "sglang": {
        "rocm": 158870224,
        "cuda": 115218617,
    },
    "triton": {
        "rocm": 158326442,
        "cuda": 158326443,
    },
    "xla": {
        "rocm": 203835682,
        "cuda": 140570787,
    },
}


def gh_api(endpoint, method="GET"):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint, "--method", method]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except subprocess.CalledProcessError as e:
        print(
            f"  WARNING: gh api {endpoint} failed: {e.stderr.strip()}", file=sys.stderr
        )
        return {}
    except json.JSONDecodeError:
        print(f"  WARNING: could not parse response for {endpoint}", file=sys.stderr)
        return {}


def gh_api_list(endpoint):
    """Call GitHub API and handle paginated list responses."""
    cmd = ["gh", "api", endpoint, "--method", "GET", "--paginate"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
        if not raw:
            return []
        # --paginate can return concatenated JSON arrays
        if raw.startswith("[") and "][" in raw:
            raw = raw.replace("][", ",")
        return json.loads(raw)
    except subprocess.CalledProcessError as e:
        print(
            f"  WARNING: gh api {endpoint} failed: {e.stderr.strip()}", file=sys.stderr
        )
        return []
    except json.JSONDecodeError:
        print(f"  WARNING: could not parse response for {endpoint}", file=sys.stderr)
        return []


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    """Parse ISO timestamp to datetime."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def hours_between(iso_start, iso_end):
    """Return hours between two ISO timestamps, or None."""
    s = parse_iso(iso_start)
    e = parse_iso(iso_end)
    if s and e:
        return round((e - s).total_seconds() / 3600, 1)
    return None


# ---------------------------------------------------------------------------
# PR Velocity
# ---------------------------------------------------------------------------


def collect_pr_velocity(repo, role, is_filtered=True):
    """Collect PR velocity metrics: opened/merged/closed this week + last week,
    median time-to-merge, stale PRs, PR review latency."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    week_ago_iso = week_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    two_weeks_ago_iso = two_weeks_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    thirty_days_ago = now - timedelta(days=30)

    # For active_dev: use repo API directly. For upstream_watch: use search API.
    if role == "active_dev":
        # Recently updated PRs (covers opened, merged, closed in last 2 weeks)
        prs = gh_api_list(
            f"/repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100"
        )
        # Filter to those updated in last 2 weeks
        recent_prs = []
        for pr in prs:
            updated = parse_iso(pr.get("updated_at"))
            if updated and updated >= two_weeks_ago:
                recent_prs.append(pr)
            elif updated and updated < two_weeks_ago:
                break  # sorted by updated desc, can stop
    else:
        # For upstream_watch, we already have filtered PR data — load from data/
        prs_file = DATA / _current_project_name / "prs.json"
        if prs_file.exists():
            with open(prs_file) as f:
                prs_data = json.load(f)
            recent_prs = []
            for pr in prs_data.get("prs", []):
                # Synthesize minimal PR structure for analysis
                recent_prs.append(
                    {
                        "created_at": pr.get("created_at", ""),
                        "updated_at": pr.get("updated_at", ""),
                        "merged_at": pr.get("updated_at") if pr.get("merged") else None,
                        "closed_at": (
                            pr.get("updated_at")
                            if pr.get("state") == "closed" and not pr.get("merged")
                            else None
                        ),
                        "state": pr.get("state", ""),
                        "user": {"login": pr.get("author", "")},
                        "number": pr.get("number"),
                        "draft": pr.get("draft", False),
                    }
                )
        else:
            recent_prs = []

    # Count this week vs last week
    this_week_opened = 0
    this_week_merged = 0
    this_week_closed = 0
    last_week_opened = 0
    last_week_merged = 0
    last_week_closed = 0

    merge_times_hours = []  # time-to-merge for recently merged PRs
    stale_prs = 0  # open > 30 days no activity

    for pr in recent_prs:
        created = parse_iso(pr.get("created_at"))
        merged_at = parse_iso(pr.get("merged_at"))
        closed_at = parse_iso(pr.get("closed_at"))
        updated = parse_iso(pr.get("updated_at"))

        if created:
            if created >= week_ago:
                this_week_opened += 1
            elif created >= two_weeks_ago:
                last_week_opened += 1

        if merged_at:
            if merged_at >= week_ago:
                this_week_merged += 1
            elif merged_at >= two_weeks_ago:
                last_week_merged += 1
            # Time-to-merge
            if created:
                ttm = (merged_at - created).total_seconds() / 3600
                merge_times_hours.append(ttm)
        elif closed_at:
            if closed_at >= week_ago:
                this_week_closed += 1
            elif closed_at >= two_weeks_ago:
                last_week_closed += 1

    # Stale PRs: open PRs with no update in 30 days
    if role == "active_dev":
        open_prs = gh_api_list(
            f"/repos/{repo}/pulls?state=open&sort=updated&direction=asc&per_page=100"
        )
        for pr in open_prs:
            updated = parse_iso(pr.get("updated_at"))
            if updated and updated < thirty_days_ago:
                stale_prs += 1
    else:
        # Count from cached data
        prs_file = DATA / _current_project_name / "prs.json"
        if prs_file.exists():
            with open(prs_file) as f:
                prs_data = json.load(f)
            for pr in prs_data.get("prs", []):
                if pr.get("state") == "open":
                    updated = parse_iso(pr.get("updated_at"))
                    if updated and updated < thirty_days_ago:
                        stale_prs += 1

    # Median time-to-merge
    median_ttm = None
    if merge_times_hours:
        merge_times_hours.sort()
        mid = len(merge_times_hours) // 2
        if len(merge_times_hours) % 2 == 0 and len(merge_times_hours) > 1:
            median_ttm = round(
                (merge_times_hours[mid - 1] + merge_times_hours[mid]) / 2, 1
            )
        else:
            median_ttm = round(merge_times_hours[mid], 1)

    return {
        "this_week": {
            "opened": this_week_opened,
            "merged": this_week_merged,
            "closed": this_week_closed,
        },
        "last_week": {
            "opened": last_week_opened,
            "merged": last_week_merged,
            "closed": last_week_closed,
        },
        "median_time_to_merge_hours": median_ttm,
        "merge_count": len(merge_times_hours),
        "stale_prs": stale_prs,
    }


# ---------------------------------------------------------------------------
# Contributor Activity
# ---------------------------------------------------------------------------


def collect_contributors(repo, role):
    """Collect contributor activity: active/new contributors, top contributors."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    if role == "active_dev":
        # Get recent commits for contributor analysis
        since = month_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        commits = gh_api_list(f"/repos/{repo}/commits?since={since}&per_page=100")
    else:
        commits = []

    # Analyze from cached PR data (works for both roles)
    prs_file = DATA / _current_project_name / "prs.json"
    pr_authors = {}
    if prs_file.exists():
        with open(prs_file) as f:
            prs_data = json.load(f)
        for pr in prs_data.get("prs", []):
            author = pr.get("author", "")
            if not author or _is_bot(author):
                continue
            if author not in pr_authors:
                pr_authors[author] = {
                    "prs_submitted": 0,
                    "prs_merged": 0,
                    "first_seen": pr.get("created_at", ""),
                }
            pr_authors[author]["prs_submitted"] += 1
            if pr.get("merged"):
                pr_authors[author]["prs_merged"] += 1

    # Commit authors (for active_dev)
    commit_authors = {}
    for c in commits:
        author = c.get("author", {})
        login = author.get("login", "") if author else ""
        if not login or _is_bot(login):
            continue
        date = c.get("commit", {}).get("committer", {}).get("date", "")
        if login not in commit_authors:
            commit_authors[login] = {"commits": 0, "last_commit": date}
        commit_authors[login]["commits"] += 1

    # Active contributors this week (from PRs)
    active_this_week = set()
    for pr in prs_data.get("prs", []) if prs_file.exists() else []:
        author = pr.get("author", "")
        if _is_bot(author):
            continue
        created = parse_iso(pr.get("created_at"))
        updated = parse_iso(pr.get("updated_at"))
        if (created and created >= week_ago) or (updated and updated >= week_ago):
            active_this_week.add(author)

    # Top contributors (by PRs submitted)
    top = sorted(pr_authors.items(), key=lambda x: x[1]["prs_submitted"], reverse=True)[
        :10
    ]
    top_contributors = [
        {
            "author": author,
            "prs_submitted": data["prs_submitted"],
            "prs_merged": data["prs_merged"],
            "commits": commit_authors.get(author, {}).get("commits", 0),
        }
        for author, data in top
    ]

    # Bus factor: number of people responsible for 50% of merged PRs
    merged_counts = sorted(
        [d["prs_merged"] for d in pr_authors.values() if d["prs_merged"] > 0],
        reverse=True,
    )
    total_merged = sum(merged_counts)
    bus_factor = 0
    cumulative = 0
    for count in merged_counts:
        cumulative += count
        bus_factor += 1
        if cumulative >= total_merged * 0.5:
            break

    return {
        "active_this_week": len(active_this_week),
        "total_contributors": len(pr_authors),
        "top_contributors": top_contributors,
        "bus_factor": bus_factor if total_merged > 0 else None,
    }


def _is_bot(author):
    if not author:
        return True
    a = author.lower()
    return "bot" in a or "copybara" in a or a == "web-flow"


# ---------------------------------------------------------------------------
# Issue Health
# ---------------------------------------------------------------------------


def collect_issue_health(repo, role):
    """Collect issue health: opened/closed this week, unanswered, backlog."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    seven_days_ago = now - timedelta(days=7)

    # Load cached issues
    issues_file = DATA / _current_project_name / "issues.json"
    cached_issues = []
    if issues_file.exists():
        with open(issues_file) as f:
            issues_data = json.load(f)
        cached_issues = issues_data.get("issues", [])

    total_open = len(cached_issues)

    # Issues opened this week (from cached, which are open issues)
    opened_this_week = 0
    unanswered = 0
    for issue in cached_issues:
        created = parse_iso(issue.get("created_at"))
        if created and created >= week_ago:
            opened_this_week += 1
        # Unanswered: open > 7 days with no update beyond creation
        updated = parse_iso(issue.get("updated_at"))
        if created and updated:
            # If updated_at ≈ created_at (within 1 hour), likely no response
            if (updated - created).total_seconds() < 3600 and created < seven_days_ago:
                unanswered += 1

    # Closed issues this week — search API
    week_ago_str = week_ago.strftime("%Y-%m-%d")
    closed_search = gh_api(
        f"/search/issues?q=repo:{repo}+is:issue+is:closed+closed:>{week_ago_str}&per_page=1"
    )
    closed_this_week = closed_search.get("total_count", 0)

    return {
        "total_open": total_open,
        "opened_this_week": opened_this_week,
        "closed_this_week": closed_this_week,
        "unanswered": unanswered,
    }


# ---------------------------------------------------------------------------
# CI Health
# ---------------------------------------------------------------------------


def collect_ci_health(repo, project_name):
    """Collect CI build success rate from recent workflow runs."""
    if project_name not in WORKFLOW_IDS:
        return None

    results = {}
    for platform, wf_id in WORKFLOW_IDS[project_name].items():
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{wf_id}/runs?per_page=20&status=completed"
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            results[platform] = None
            continue

        total = len(runs)
        succeeded = sum(1 for r in runs if r.get("conclusion") == "success")
        failed = sum(1 for r in runs if r.get("conclusion") == "failure")
        success_rate = round(succeeded / total * 100, 1) if total > 0 else 0

        results[platform] = {
            "total_runs": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": success_rate,
        }

    return results


# ---------------------------------------------------------------------------
# Time to CI Signal
# ---------------------------------------------------------------------------


def collect_ci_signal_time(repo, project_name):
    """Collect time-to-CI-signal: how long from workflow trigger to completion.
    This measures the feedback loop speed for developers."""
    if project_name not in WORKFLOW_IDS:
        return None

    results = {}
    for platform, wf_id in WORKFLOW_IDS[project_name].items():
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{wf_id}/runs?per_page=20&status=completed"
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            results[platform] = None
            continue

        durations_min = []
        for run in runs:
            created = parse_iso(run.get("created_at"))
            updated = parse_iso(run.get("updated_at"))
            if created and updated:
                dur = (updated - created).total_seconds() / 60
                if dur > 0:
                    durations_min.append(round(dur, 1))

        if not durations_min:
            results[platform] = None
            continue

        durations_min.sort()
        mid = len(durations_min) // 2
        if len(durations_min) % 2 == 0 and len(durations_min) > 1:
            median = round((durations_min[mid - 1] + durations_min[mid]) / 2, 1)
        else:
            median = durations_min[mid]

        results[platform] = {
            "sample_size": len(durations_min),
            "median_minutes": median,
            "p90_minutes": durations_min[int(len(durations_min) * 0.9)],
            "min_minutes": durations_min[0],
            "max_minutes": durations_min[-1],
        }

    return results


# ---------------------------------------------------------------------------
# Release Cadence
# ---------------------------------------------------------------------------


def collect_release_cadence(repo):
    """Collect release cadence: days since last release, avg interval."""
    releases_file = DATA / _current_project_name / "releases.json"
    if not releases_file.exists():
        return None

    with open(releases_file) as f:
        releases_data = json.load(f)

    releases = releases_data.get("releases", [])
    if not releases:
        return {"days_since_last": None, "avg_interval_days": None, "total_releases": 0}

    now = datetime.now(timezone.utc)

    # Days since last release
    latest = parse_iso(releases[0].get("published_at"))
    days_since = round((now - latest).total_seconds() / 86400, 1) if latest else None

    # Average interval between releases
    intervals = []
    sorted_releases = [r for r in releases if r.get("published_at")]
    for i in range(len(sorted_releases) - 1):
        d1 = parse_iso(sorted_releases[i].get("published_at"))
        d2 = parse_iso(sorted_releases[i + 1].get("published_at"))
        if d1 and d2:
            interval = (d1 - d2).total_seconds() / 86400
            if interval > 0:
                intervals.append(interval)

    avg_interval = round(sum(intervals) / len(intervals), 1) if intervals else None

    return {
        "days_since_last": days_since,
        "avg_interval_days": avg_interval,
        "total_releases": len(releases),
        "latest_tag": releases[0].get("tag_name", ""),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Global used to pass current project name to functions that read cached data
_current_project_name = ""


def collect_project_activity(name, cfg):
    """Collect all activity metrics for a single project."""
    global _current_project_name
    _current_project_name = name

    repo = cfg["repo"]
    role = cfg.get("role", "upstream_watch")

    print(f"Collecting activity for {name} ({repo})...")

    activity = {"collected_at": now_iso(), "project": name, "repo": repo}

    # PR Velocity
    print(f"  PR velocity...")
    activity["pr_velocity"] = collect_pr_velocity(repo, role)

    # Contributor Activity
    print(f"  Contributors...")
    activity["contributors"] = collect_contributors(repo, role)

    # Issue Health
    print(f"  Issue health...")
    activity["issue_health"] = collect_issue_health(repo, role)

    # CI Health
    print(f"  CI health...")
    ci_health = collect_ci_health(repo, name)
    activity["ci_health"] = ci_health

    # Time to CI Signal
    print(f"  CI signal time...")
    ci_signal = collect_ci_signal_time(repo, name)
    activity["ci_signal_time"] = ci_signal

    # Release Cadence
    print(f"  Release cadence...")
    activity["release_cadence"] = collect_release_cadence(repo)

    return activity


def main():
    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    for name, cfg in config["projects"].items():
        try:
            activity = collect_project_activity(name, cfg)
            out_dir = DATA / name
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / "activity.json", "w") as f:
                json.dump(activity, f, indent=2)

            # Print summary
            pv = activity.get("pr_velocity", {})
            tw = pv.get("this_week", {})
            print(
                f"  PRs: {tw.get('opened', 0)} opened, {tw.get('merged', 0)} merged | "
                f"TTM: {pv.get('median_time_to_merge_hours', 'N/A')}h | "
                f"Stale: {pv.get('stale_prs', 0)}"
            )
        except Exception as e:
            print(f"  ERROR collecting activity for {name}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()

    print("Activity collection complete.")


if __name__ == "__main__":
    main()
