#!/usr/bin/env python3
"""Take weekly snapshots of key metrics for trend tracking.

Reads activity.json and test_results.json for each project and appends
a summary to data/history/YYYY-WW.json (ISO week number).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_week_key():
    """Return YYYY-WW string for current ISO week."""
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def snapshot_project(name):
    """Extract key metrics from a project's data files."""
    project_dir = DATA / name
    activity = load_json(project_dir / "activity.json")
    test_results = load_json(project_dir / "test_results.json")
    prs_data = load_json(project_dir / "prs.json")
    issues_data = load_json(project_dir / "issues.json")

    snap = {}

    # PR counts
    if prs_data:
        prs = prs_data.get("prs", [])
        snap["open_prs"] = sum(1 for p in prs if p.get("state") == "open")
        snap["total_prs"] = len(prs)

    # Issue counts
    if issues_data:
        snap["open_issues"] = len(issues_data.get("issues", []))

    # Activity metrics
    if activity:
        pv = activity.get("pr_velocity", {})
        tw = pv.get("this_week", {})
        snap["prs_opened"] = tw.get("opened", 0)
        snap["prs_merged"] = tw.get("merged", 0)
        snap["median_ttm_hours"] = pv.get("median_time_to_merge_hours")
        snap["stale_prs"] = pv.get("stale_prs", 0)

        contrib = activity.get("contributors", {})
        snap["active_contributors"] = contrib.get("active_this_week", 0)
        snap["bus_factor"] = contrib.get("bus_factor")

        ih = activity.get("issue_health", {})
        snap["issues_opened"] = ih.get("opened_this_week", 0)
        snap["issues_closed"] = ih.get("closed_this_week", 0)

        ci_signal = activity.get("ci_signal_time")
        if ci_signal:
            for platform in ("rocm", "cuda"):
                pd = ci_signal.get(platform)
                if pd:
                    snap[f"ci_signal_{platform}_median_min"] = pd.get("median_minutes")

    # Test pass rates
    if test_results:
        for platform in ("rocm", "cuda"):
            pd = test_results.get(platform)
            if pd and pd.get("summary"):
                snap[f"test_pass_rate_{platform}"] = pd["summary"].get("pass_rate")

    # Parity report (from collect_parity.py)
    parity_report = load_json(project_dir / "parity_report.json")
    if parity_report and parity_report.get("summary"):
        ps = parity_report["summary"]
        snap["parity_pct"] = ps.get("parity_pct")
        snap["parity_gap"] = ps.get("gap")

    return snap


def main():
    HISTORY.mkdir(parents=True, exist_ok=True)
    week_key = get_week_key()
    snapshot_file = HISTORY / f"{week_key}.json"

    # Load existing snapshot if we're updating within the same week
    existing = load_json(snapshot_file) or {"week": week_key, "projects": {}}

    # Discover all projects
    project_dirs = sorted(
        [d.name for d in DATA.iterdir() if d.is_dir() and d.name != "history"]
    )

    for name in project_dirs:
        print(f"Snapshotting {name}...")
        snap = snapshot_project(name)
        if snap:
            existing["projects"][name] = snap

    existing["snapshot_at"] = now_iso()

    with open(snapshot_file, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Snapshot saved to {snapshot_file}")

    # Also maintain an index of all snapshots for easy frontend loading
    index = []
    for sf in sorted(HISTORY.glob("*-W*.json")):
        index.append(sf.stem)

    with open(HISTORY / "index.json", "w") as f:
        json.dump({"weeks": index}, f, indent=2)

    print(f"Index updated: {len(index)} weeks")


if __name__ == "__main__":
    main()
