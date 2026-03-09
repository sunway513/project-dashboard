#!/usr/bin/env python3
"""Collect CI workflow build times from GitHub Actions API.

For each project with build_workflows configured (or auto-discovered),
fetches the last 20 completed runs and computes duration statistics.

Output: data/{project}/build_times.json
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
DATA = ROOT / "data"


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


def minutes_between(iso_start, iso_end):
    """Return minutes between two ISO timestamps, or None."""
    s = parse_iso(iso_start)
    e = parse_iso(iso_end)
    if s and e:
        return round((e - s).total_seconds() / 60, 1)
    return None


def compute_stats(values):
    """Compute median, p90, min, max from a list of numbers."""
    if not values:
        return None
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2 == 0 and n > 1:
        median = round((values[mid - 1] + values[mid]) / 2, 1)
    else:
        median = values[mid]
    p90_idx = int(n * 0.9)
    if p90_idx >= n:
        p90_idx = n - 1
    return {
        "sample_size": n,
        "median_minutes": median,
        "p90_minutes": values[p90_idx],
        "min_minutes": values[0],
        "max_minutes": values[-1],
    }


def discover_workflows(repo):
    """Auto-discover workflows for a repo. Returns list of {name, id}."""
    data = gh_api(f"/repos/{repo}/actions/workflows")
    workflows = data.get("workflows", [])
    if not workflows:
        return []
    # Return all active workflows
    return [
        {"name": w["name"], "id": w["id"]}
        for w in workflows
        if w.get("state") == "active"
    ]


def resolve_workflow_id(repo, wf_config):
    """Resolve workflow ID from config. If id is set, use it. Otherwise match by name."""
    if wf_config.get("id"):
        return wf_config["id"]
    # Search by name
    data = gh_api(f"/repos/{repo}/actions/workflows")
    for w in data.get("workflows", []):
        if w["name"] == wf_config["name"]:
            return w["id"]
    return None


def collect_workflow_build_times(repo, wf_id, wf_name, target_minutes=None):
    """Collect build time data for a single workflow."""
    # Fetch last 20 completed runs on default branch
    data = gh_api(
        f"/repos/{repo}/actions/workflows/{wf_id}/runs"
        f"?status=completed&per_page=20"
    )
    runs = data.get("workflow_runs", [])
    if not runs:
        return None

    durations = []
    recent_runs = []

    for run in runs:
        started = run.get("run_started_at") or run.get("created_at")
        updated = run.get("updated_at")
        dur = minutes_between(started, updated)
        if dur is not None and dur > 0:
            durations.append(dur)
            recent_runs.append(
                {
                    "id": run["id"],
                    "conclusion": run.get("conclusion"),
                    "duration_minutes": dur,
                    "date": (run.get("run_started_at") or run.get("created_at", ""))[
                        :10
                    ],
                }
            )

    if not durations:
        return None

    # Latest run details
    latest = runs[0]
    latest_started = latest.get("run_started_at") or latest.get("created_at")
    latest_dur = minutes_between(latest_started, latest.get("updated_at"))

    result = {
        "workflow_id": wf_id,
        "latest_run": {
            "id": latest["id"],
            "conclusion": latest.get("conclusion"),
            "duration_minutes": latest_dur,
            "started_at": latest_started,
            "html_url": latest.get("html_url", ""),
        },
        "stats": compute_stats(durations),
        "recent_runs": recent_runs[:20],
    }

    if target_minutes is not None:
        result["target_minutes"] = target_minutes

    # Fetch jobs for latest run to find bottleneck
    jobs_data = gh_api(f"/repos/{repo}/actions/runs/{latest['id']}/jobs?per_page=50")
    jobs = jobs_data.get("jobs", [])
    if jobs:
        longest_job = None
        longest_dur = 0
        for job in jobs:
            if job.get("conclusion") and job.get("started_at") and job.get("completed_at"):
                job_dur = minutes_between(job["started_at"], job["completed_at"])
                if job_dur and job_dur > longest_dur:
                    longest_dur = job_dur
                    longest_job = job
        if longest_job:
            result["bottleneck_job"] = {
                "name": longest_job["name"],
                "duration_minutes": longest_dur,
            }

    return result


def collect_project_build_times(name, cfg):
    """Collect build times for a single project."""
    repo = cfg["repo"]
    build_workflows = cfg.get("build_workflows", [])

    print(f"Collecting build times for {name} ({repo})...")

    workflows_result = {}

    if build_workflows:
        for wf_config in build_workflows:
            wf_name = wf_config["name"]
            wf_id = resolve_workflow_id(repo, wf_config)
            if not wf_id:
                print(f"  WARNING: Could not resolve workflow '{wf_name}' for {repo}")
                continue
            target = wf_config.get("target_minutes")
            print(f"  Workflow: {wf_name} (id={wf_id})...")
            result = collect_workflow_build_times(repo, wf_id, wf_name, target)
            if result:
                workflows_result[wf_name] = result
                stats = result.get("stats", {})
                print(
                    f"    Median: {stats.get('median_minutes')}m, "
                    f"P90: {stats.get('p90_minutes')}m"
                )
    else:
        # Auto-discover: find workflows and pick the longest-running one
        discovered = discover_workflows(repo)
        if not discovered:
            print(f"  No workflows found for {repo}")
            return None

        # Try each discovered workflow, keep ones with data
        for wf in discovered[:3]:  # Limit to 3 to avoid API abuse
            print(f"  Auto-discovered workflow: {wf['name']} (id={wf['id']})...")
            result = collect_workflow_build_times(repo, wf["id"], wf["name"])
            if result:
                workflows_result[wf["name"]] = result

    if not workflows_result:
        return None

    return {
        "collected_at": now_iso(),
        "workflows": workflows_result,
    }


def main():
    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    for name, cfg in config["projects"].items():
        try:
            build_times = collect_project_build_times(name, cfg)
            if build_times:
                out_dir = DATA / name
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / "build_times.json", "w") as f:
                    json.dump(build_times, f, indent=2)
                wf_count = len(build_times.get("workflows", {}))
                print(f"  Saved {wf_count} workflow(s) to data/{name}/build_times.json")
            else:
                print(f"  No build time data for {name}")
        except Exception as e:
            print(f"  ERROR collecting build times for {name}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()

    print("Build time collection complete.")


if __name__ == "__main__":
    main()
