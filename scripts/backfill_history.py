#!/usr/bin/env python3
"""Backfill weekly historical snapshots for the past N weeks.

Uses GitHub Search API with date ranges to reconstruct per-week metrics:
  - PRs opened / merged / closed per week
  - Issues opened / closed per week
  - Active contributors per week (from PR + commit data)
  - CI workflow run duration (time-to-CI-signal) per week
  - CI success rate per week
  - Contributor stats from /repos/stats/contributors (weekly breakdown)

Writes to data/history/YYYY-WW.json for each week.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
DATA = ROOT / "data"
HISTORY = DATA / "history"

WORKFLOW_IDS = {
    "pytorch": {"rocm": 139700577, "cuda": 16535519},
    "sglang": {"rocm": 158870224, "cuda": 115218617},
    "triton": {"rocm": 158326442, "cuda": 158326443},
    "xla": {"rocm": 203835682, "cuda": 140570787},
}

# Rate-limit tracking
_api_calls = 0


def gh_api(endpoint, method="GET"):
    """Call GitHub API via gh CLI with search rate-limit awareness."""
    global _api_calls
    _api_calls += 1

    # Search API has a 30/min limit — throttle search calls
    is_search = "/search/" in endpoint
    if is_search:
        time.sleep(2.5)  # ~24 calls/min, safely under 30/min
    elif _api_calls % 20 == 0:
        time.sleep(1)

    cmd = ["gh", "api", endpoint, "--method", method]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()
        if "rate limit" in stderr.lower() or "403" in stderr or "secondary" in stderr.lower():
            wait = 65 if is_search else 30
            print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)
            return gh_api(endpoint, method)
        print(f"  WARNING: {endpoint}: {stderr}", file=sys.stderr)
        return {}
    except json.JSONDecodeError:
        return {}


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def iso_week_range(year, week):
    """Return (monday, sunday) dates for ISO week."""
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def week_key(year, week):
    return f"{year}-W{week:02d}"


def is_bot(author):
    if not author:
        return True
    a = author.lower()
    return "bot" in a or "copybara" in a or a == "web-flow"


# ---------------------------------------------------------------------------
# Per-project, per-week data collection
# ---------------------------------------------------------------------------


def search_count(query):
    """Run a search query and return total_count."""
    data = gh_api(f"/search/issues?q={quote(query, safe='+:')}&per_page=1")
    return data.get("total_count", 0)


def search_items(query, per_page=100):
    """Run a search query and return (total_count, items list)."""
    data = gh_api(
        f"/search/issues?q={quote(query, safe='+:')}&per_page={min(per_page, 100)}"
    )
    return data.get("total_count", 0), data.get("items", [])


def search_prs_with_authors(query, max_results=100):
    """Run a search query and return list of PR authors."""
    data = gh_api(
        f"/search/issues?q={quote(query, safe='+:')}&per_page={min(max_results, 100)}"
    )
    authors = set()
    for item in data.get("items", []):
        login = item.get("user", {}).get("login", "")
        if login and not is_bot(login):
            authors.add(login)
    return authors


def compute_median(values):
    """Return median of a list of numbers, or None if empty."""
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2 == 0:
        return round((s[mid - 1] + s[mid]) / 2, 1)
    return round(s[mid], 1)


def load_existing_snap(wk, project_name):
    """Load existing snapshot data for a project-week."""
    snapshot_file = HISTORY / f"{wk}.json"
    if not snapshot_file.exists():
        return {}
    try:
        with open(snapshot_file) as f:
            data = json.load(f)
        return data.get("projects", {}).get(project_name, {})
    except (json.JSONDecodeError, OSError):
        return {}


def collect_week_pr_velocity(repo, start_date, end_date, role, project_name, cfg):
    """Collect PR velocity for a specific week."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    if role == "active_dev":
        # For our repos, count all PRs
        opened = search_count(f"repo:{repo}+is:pr+created:{start_str}..{end_str}")
        merged = search_count(
            f"repo:{repo}+is:pr+is:merged+merged:{start_str}..{end_str}"
        )
        closed = search_count(
            f"repo:{repo}+is:pr+is:closed+is:unmerged+closed:{start_str}..{end_str}"
        )
    else:
        # For upstream, count only AMD/ROCm-relevant PRs
        keywords = cfg.get("track_keywords", [])
        labels = cfg.get("track_labels", [])
        scope = cfg.get("keyword_scope", "")
        scope_q = f"+in:{scope}" if scope else ""

        opened = 0
        merged = 0
        closed = 0
        for kw in keywords:
            opened += search_count(
                f"{kw}{scope_q}+repo:{repo}+is:pr+created:{start_str}..{end_str}"
            )
            merged += search_count(
                f"{kw}{scope_q}+repo:{repo}+is:pr+is:merged+merged:{start_str}..{end_str}"
            )
        for label in labels:
            opened += search_count(
                f'repo:{repo}+is:pr+label:"{label}"+created:{start_str}..{end_str}'
            )
            merged += search_count(
                f'repo:{repo}+is:pr+is:merged+label:"{label}"+merged:{start_str}..{end_str}'
            )

    return {
        "prs_opened": opened,
        "prs_merged": merged,
        "prs_closed": closed,
    }


def collect_week_issues(repo, start_date, end_date, role, cfg):
    """Collect issue stats for a specific week."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    if role == "active_dev":
        opened = search_count(f"repo:{repo}+is:issue+created:{start_str}..{end_str}")
        closed = search_count(f"repo:{repo}+is:issue+closed:{start_str}..{end_str}")
    else:
        keywords = cfg.get("track_keywords", [])
        labels = cfg.get("track_labels", [])
        scope = cfg.get("keyword_scope", "")
        scope_q = f"+in:{scope}" if scope else ""

        opened = 0
        closed = 0
        for kw in keywords:
            opened += search_count(
                f"{kw}{scope_q}+repo:{repo}+is:issue+created:{start_str}..{end_str}"
            )
            closed += search_count(
                f"{kw}{scope_q}+repo:{repo}+is:issue+closed:{start_str}..{end_str}"
            )
        for label in labels:
            opened += search_count(
                f'repo:{repo}+is:issue+label:"{label}"+created:{start_str}..{end_str}'
            )
            closed += search_count(
                f'repo:{repo}+is:issue+label:"{label}"+closed:{start_str}..{end_str}'
            )

    return {
        "issues_opened": opened,
        "issues_closed": closed,
    }


def collect_week_contributors(repo, start_date, end_date, role, cfg):
    """Collect active contributor count for a specific week."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    authors = set()

    if role == "active_dev":
        # Get PR authors
        authors |= search_prs_with_authors(
            f"repo:{repo}+is:pr+created:{start_str}..{end_str}"
        )
        authors |= search_prs_with_authors(
            f"repo:{repo}+is:pr+is:merged+merged:{start_str}..{end_str}"
        )
    else:
        keywords = cfg.get("track_keywords", [])
        labels = cfg.get("track_labels", [])
        scope = cfg.get("keyword_scope", "")
        scope_q = f"+in:{scope}" if scope else ""

        for kw in keywords:
            authors |= search_prs_with_authors(
                f"{kw}{scope_q}+repo:{repo}+is:pr+created:{start_str}..{end_str}"
            )
        for label in labels:
            authors |= search_prs_with_authors(
                f'repo:{repo}+is:pr+label:"{label}"+created:{start_str}..{end_str}'
            )

    return len(authors)


def collect_week_ci(repo, project_name, start_date, end_date):
    """Collect CI signal time and success rate for a specific week."""
    if project_name not in WORKFLOW_IDS:
        return {}

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    result = {}

    for platform, wf_id in WORKFLOW_IDS[project_name].items():
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{wf_id}/runs"
            f"?created={start_str}..{end_str}&status=completed&per_page=30"
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            continue

        succeeded = sum(1 for r in runs if r.get("conclusion") == "success")
        failed = sum(1 for r in runs if r.get("conclusion") == "failure")
        total = len(runs)

        durations = []
        for run in runs:
            created = parse_iso(run.get("created_at"))
            updated = parse_iso(run.get("updated_at"))
            if created and updated:
                dur = (updated - created).total_seconds() / 60
                if dur > 0:
                    durations.append(dur)

        durations.sort()
        median_dur = None
        if durations:
            mid = len(durations) // 2
            median_dur = round(durations[mid], 1)

        ran = succeeded + failed
        success_rate = round(succeeded / ran * 100, 1) if ran > 0 else None

        result[platform] = {
            "success_rate": success_rate,
            "median_signal_min": median_dur,
            "total_runs": total,
        }

    return result


def collect_contributor_stats(repo):
    """Fetch /repos/stats/contributors for weekly breakdown.
    Returns dict: {unix_week_ts: {author: commits, ...}, ...}
    GitHub may return 202 (processing) - retry up to 3 times."""
    for attempt in range(3):
        data = gh_api(f"/repos/{repo}/stats/contributors")
        if isinstance(data, list) and len(data) > 0:
            break
        if isinstance(data, dict) and data.get("message"):
            print(f"    Stats API: {data.get('message')}, retrying...", file=sys.stderr)
        time.sleep(5)
    else:
        return {}

    if not isinstance(data, list):
        return {}

    weeks_map = {}
    for contributor in data:
        author = contributor.get("author")
        login = author.get("login", "") if author else ""
        if not login or is_bot(login):
            continue
        for w in contributor.get("weeks", []):
            ts = w.get("w", 0)
            commits = w.get("c", 0)
            if commits > 0:
                if ts not in weeks_map:
                    weeks_map[ts] = {}
                weeks_map[ts][login] = commits
    return weeks_map


def collect_week_open_issues(repo, end_date, role, cfg):
    """Estimate number of open issues at end of week.

    Uses: count(created <= end_date) - count(is:closed AND closed <= end_date).
    For upstream_watch, uses a single representative filter to avoid double-counting.
    """
    end_str = end_date.strftime("%Y-%m-%d")

    if role == "active_dev":
        total_created = search_count(f"repo:{repo}+is:issue+created:<={end_str}")
        total_closed = search_count(
            f"repo:{repo}+is:issue+is:closed+closed:<={end_str}"
        )
    else:
        # Use one representative filter (prefer label, then keyword)
        labels = cfg.get("track_labels", [])
        keywords = cfg.get("track_keywords", [])
        scope = cfg.get("keyword_scope", "")

        if labels:
            filt = f'+label:"{labels[0]}"'
        elif keywords:
            scope_q = f"+in:{scope}" if scope else ""
            filt = f"+{keywords[0]}{scope_q}"
        else:
            filt = ""

        total_created = search_count(
            f"repo:{repo}+is:issue{filt}+created:<={end_str}"
        )
        total_closed = search_count(
            f"repo:{repo}+is:issue+is:closed{filt}+closed:<={end_str}"
        )

    return max(0, total_created - total_closed)


def collect_week_ttm(repo, start_date, end_date, role, name, cfg):
    """Compute median time-to-merge (hours) for PRs merged in this week."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    all_ttm_hours = []
    seen = set()

    def _extract_ttm(items):
        for item in items:
            num = item.get("number")
            if num in seen:
                continue
            seen.add(num)
            created = parse_iso(item.get("created_at"))
            closed = parse_iso(item.get("closed_at"))
            if created and closed:
                ttm = (closed - created).total_seconds() / 3600
                if ttm >= 0:
                    all_ttm_hours.append(ttm)

    if role == "active_dev":
        _, items = search_items(
            f"repo:{repo}+is:pr+is:merged+merged:{start_str}..{end_str}"
        )
        _extract_ttm(items)
    else:
        keywords = cfg.get("track_keywords", [])
        labels = cfg.get("track_labels", [])
        scope = cfg.get("keyword_scope", "")
        scope_q = f"+in:{scope}" if scope else ""

        for kw in keywords:
            _, items = search_items(
                f"{kw}{scope_q}+repo:{repo}+is:pr+is:merged+merged:{start_str}..{end_str}"
            )
            _extract_ttm(items)
        for label in labels:
            _, items = search_items(
                f'repo:{repo}+is:pr+is:merged+label:"{label}"+merged:{start_str}..{end_str}'
            )
            _extract_ttm(items)

    return compute_median(all_ttm_hours)


def collect_week_test_rate(repo, project_name, start_date, end_date):
    """Compute test pass rate from CI job conclusions for the latest run in the week."""
    if project_name not in WORKFLOW_IDS:
        return {}

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    result = {}

    for platform, wf_id in WORKFLOW_IDS[project_name].items():
        # Get completed runs in this week (reuses cached data if CI was already fetched)
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{wf_id}/runs"
            f"?created={start_str}..{end_str}&status=completed&per_page=5"
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            continue

        # Get jobs for the latest run
        latest_run = runs[0]
        jobs_data = gh_api(
            f"/repos/{repo}/actions/runs/{latest_run['id']}/jobs?per_page=100"
        )
        jobs = jobs_data.get("jobs", [])
        if not jobs:
            continue

        # Count jobs with definitive conclusions
        test_jobs = [
            j for j in jobs if j.get("conclusion") in ("success", "failure")
        ]
        if not test_jobs:
            continue

        passed = sum(1 for j in test_jobs if j.get("conclusion") == "success")
        total = len(test_jobs)
        pass_rate = round(passed / total * 100, 1) if total > 0 else None

        if pass_rate is not None:
            result[f"test_pass_rate_{platform}"] = pass_rate

    return result


# ---------------------------------------------------------------------------
# Main backfill
# ---------------------------------------------------------------------------


def backfill_project(name, cfg, weeks_to_fill):
    """Backfill historical data for one project across multiple weeks.

    Smart-skip: checks existing snapshot files and only computes missing metrics.
    """
    repo = cfg["repo"]
    role = cfg.get("role", "upstream_watch")
    print(f"\n  Backfilling {name} ({repo})...")

    # Check if contributor stats are needed for any week
    need_contrib_stats = False
    for year, week_num, monday, sunday in weeks_to_fill:
        wk = week_key(year, week_num)
        existing = load_existing_snap(wk, name)
        if "active_contributors" not in existing:
            need_contrib_stats = True
            break

    if need_contrib_stats and role == "active_dev":
        print(f"    Fetching contributor stats...")
        contrib_stats = collect_contributor_stats(repo)
    else:
        contrib_stats = {}

    results = {}  # week_key -> snapshot dict

    for year, week_num, monday, sunday in weeks_to_fill:
        wk = week_key(year, week_num)
        existing = load_existing_snap(wk, name)

        print(
            f"    {wk} ({monday.strftime('%m/%d')}-{sunday.strftime('%m/%d')})...",
            end=" ",
        )

        snap = {}

        # PR velocity — skip if already present
        if "prs_opened" not in existing:
            pv = collect_week_pr_velocity(repo, monday, sunday, role, name, cfg)
            snap["prs_opened"] = pv["prs_opened"]
            snap["prs_merged"] = pv["prs_merged"]

        # Issues — skip if already present
        if "issues_opened" not in existing:
            iss = collect_week_issues(repo, monday, sunday, role, cfg)
            snap["issues_opened"] = iss["issues_opened"]
            snap["issues_closed"] = iss["issues_closed"]

        # Active contributors — skip if already present
        if "active_contributors" not in existing:
            if role == "active_dev" and contrib_stats:
                monday_ts = int(monday.timestamp())
                active = 0
                for ts, authors in contrib_stats.items():
                    if abs(ts - monday_ts) < 7 * 86400:
                        active = len(authors)
                        break
                snap["active_contributors"] = active
            else:
                snap["active_contributors"] = collect_week_contributors(
                    repo, monday, sunday, role, cfg
                )

        # CI metrics — skip if already present
        if f"ci_signal_rocm_median_min" not in existing and name in WORKFLOW_IDS:
            ci = collect_week_ci(repo, name, monday, sunday)
            for platform in ("rocm", "cuda"):
                if platform in ci:
                    pd = ci[platform]
                    if pd.get("median_signal_min") is not None:
                        snap[f"ci_signal_{platform}_median_min"] = pd[
                            "median_signal_min"
                        ]
                    if pd.get("success_rate") is not None:
                        snap[f"ci_success_{platform}"] = pd["success_rate"]

        # Open issues (historical estimate) — skip if already present
        if "open_issues" not in existing:
            snap["open_issues"] = collect_week_open_issues(repo, sunday, role, cfg)

        # Median time-to-merge — skip if already present
        if "median_ttm_hours" not in existing:
            ttm = collect_week_ttm(repo, monday, sunday, role, name, cfg)
            if ttm is not None:
                snap["median_ttm_hours"] = ttm

        # Test pass rate from CI jobs — skip if already present
        if f"test_pass_rate_rocm" not in existing:
            test_rates = collect_week_test_rate(repo, name, monday, sunday)
            snap.update(test_rates)

        if snap:
            new_keys = [k for k in snap if k not in existing]
            if new_keys:
                print(f"added: {', '.join(new_keys)}")
            else:
                print("(updated)")
        else:
            print("(up to date)")

        results[wk] = snap

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill historical weekly snapshots")
    parser.add_argument(
        "--weeks", type=int, default=12, help="Number of weeks to backfill (default 12)"
    )
    parser.add_argument(
        "--project",
        type=str,
        default="",
        help="Single project to backfill (default all)",
    )
    args = parser.parse_args()

    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    HISTORY.mkdir(parents=True, exist_ok=True)

    # Determine which weeks to backfill
    now = datetime.now(timezone.utc)
    current_iso = now.isocalendar()
    weeks_to_fill = []
    for i in range(args.weeks, 0, -1):
        target = now - timedelta(weeks=i)
        iso = target.isocalendar()
        monday, sunday = iso_week_range(iso[0], iso[1])
        weeks_to_fill.append((iso[0], iso[1], monday, sunday))

    print(
        f"Backfilling {len(weeks_to_fill)} weeks for {len(config['projects'])} projects"
    )
    print(
        f"Date range: {weeks_to_fill[0][2].strftime('%Y-%m-%d')} to {weeks_to_fill[-1][3].strftime('%Y-%m-%d')}"
    )

    projects_to_process = config["projects"]
    if args.project:
        if args.project in projects_to_process:
            projects_to_process = {args.project: projects_to_process[args.project]}
        else:
            print(f"Unknown project: {args.project}")
            sys.exit(1)

    # Collect data per project
    all_project_data = {}
    for name, cfg in projects_to_process.items():
        try:
            all_project_data[name] = backfill_project(name, cfg, weeks_to_fill)
        except Exception as e:
            print(f"  ERROR: {name}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()

    # Write to weekly snapshot files
    for year, week_num, monday, sunday in weeks_to_fill:
        wk = week_key(year, week_num)
        snapshot_file = HISTORY / f"{wk}.json"

        # Load existing or create new
        existing = {}
        if snapshot_file.exists():
            with open(snapshot_file) as f:
                existing = json.load(f)

        if "projects" not in existing:
            existing["projects"] = {}

        existing["week"] = wk
        existing["start_date"] = monday.strftime("%Y-%m-%d")
        existing["end_date"] = sunday.strftime("%Y-%m-%d")

        for name, week_data in all_project_data.items():
            if wk in week_data:
                # Merge with existing data (don't overwrite keys already present)
                if name not in existing["projects"]:
                    existing["projects"][name] = {}
                existing["projects"][name].update(week_data[wk])

        existing["backfilled_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        with open(snapshot_file, "w") as f:
            json.dump(existing, f, indent=2)

    # Update index
    index = sorted([sf.stem for sf in HISTORY.glob("*-W*.json")])
    with open(HISTORY / "index.json", "w") as f:
        json.dump({"weeks": index}, f, indent=2)

    print(f"\nBackfill complete. {len(index)} weekly snapshots in {HISTORY}")
    print(f"Total API calls: {_api_calls}")


if __name__ == "__main__":
    main()
