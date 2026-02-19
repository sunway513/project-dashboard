#!/usr/bin/env python3
"""Collect unit test pass rate data (ROCm vs CUDA) from GitHub Actions and manual sources."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
MANUAL_CONFIG = ROOT / "config" / "test_results_manual.yaml"
DATA = ROOT / "data"

# ---------------------------------------------------------------------------
# Per-project CI workflow configuration
# ---------------------------------------------------------------------------
# Each platform entry can have:
#   workflow_id  — GHA workflow ID
#   name         — display name
#   job_filter   — only count jobs matching this substring (case-insensitive)
#   prefer_success — prefer successful runs (avoids partial artifacts)
#   skip_all_skipped — skip runs where every test job was skipped

WORKFLOWS = {
    "pytorch": {
        "rocm": {
            "workflow_id": 139700577,
            "name": "rocm-mi300",
        },
        "cuda": {
            "workflow_id": 16535519,
            "name": "trunk",
            "prefer_success": True,  # trunk failures have partial artifacts
        },
    },
    "sglang": {
        "rocm": {
            "workflow_id": 158870224,
            "name": "Nightly Test (AMD)",
        },
        "cuda": {
            "workflow_id": 115218617,
            "name": "PR Test",
        },
    },
    "triton": {
        # Single workflow with both AMD and NVIDIA jobs — split by job name
        "rocm": {
            "workflow_id": 157867169,
            "name": "Integration Tests",
            "job_filter": "integration-tests-amd",
        },
        "cuda": {
            "workflow_id": 157867169,
            "name": "Integration Tests",
            "job_filter": "integration-tests-nvidia",
        },
    },
    "jax": {
        "rocm": {
            "workflow_id": 228445771,
            "name": "CI - Bazel ROCm tests",
        },
        "cuda": {
            "workflow_id": 166880050,
            "name": "CI - Bazel H100 and B200 CUDA tests",
            "skip_all_skipped": True,  # runs often have only changed_files job
        },
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


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# GitHub Actions helpers
# ---------------------------------------------------------------------------


def get_latest_run(repo, workflow_id, prefer_success=False, max_pages=3):
    """Get the latest completed (success or failure) run.

    When prefer_success=True, search for the latest successful run first.
    Falls back to the latest failure if no success found within max_pages.
    """
    fallback = None
    for page in range(1, max_pages + 1):
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{workflow_id}/runs"
            f"?per_page=10&page={page}"
        )
        for run in data.get("workflow_runs", []):
            if run.get("status") != "completed":
                continue
            conclusion = run.get("conclusion")
            if conclusion not in ("success", "failure"):
                continue
            if prefer_success and conclusion == "success":
                return run
            if not prefer_success:
                return run  # return first completed run
            if fallback is None:
                fallback = run  # remember first failure
    return fallback


def get_all_jobs(repo, run_id):
    """Get ALL jobs from a workflow run (paginated)."""
    jobs = []
    page = 1
    while True:
        data = gh_api(
            f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100&page={page}"
        )
        batch = data.get("jobs", [])
        if not batch:
            break
        jobs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return jobs


def filter_test_jobs(jobs, job_filter=None):
    """Filter jobs to test-relevant ones.

    If job_filter is set, only include jobs whose name contains that string.
    Otherwise, use heuristic: jobs with "test" in name, falling back to all jobs.
    Excludes setup/gate/changed_files jobs.
    """
    exclude_names = {"changed_files", "check-all-jobs", "check-changes"}

    if job_filter:
        return [
            j
            for j in jobs
            if job_filter.lower() in j.get("name", "").lower()
            and j.get("name", "").lower() not in exclude_names
        ]

    # Heuristic: prefer jobs with "test" in name
    test_jobs = [
        j
        for j in jobs
        if "test" in j.get("name", "").lower()
        and j.get("name", "").lower() not in exclude_names
    ]
    if test_jobs:
        return test_jobs

    # Fallback: all jobs except known non-test ones
    return [j for j in jobs if j.get("name", "").lower() not in exclude_names]


def summarize_jobs(jobs):
    """Summarize job conclusions into pass/fail/skip counts and pass rate."""
    total = len(jobs)
    passed = sum(1 for j in jobs if j.get("conclusion") == "success")
    failed = sum(1 for j in jobs if j.get("conclusion") == "failure")
    skipped = sum(
        1 for j in jobs if j.get("conclusion") in ("skipped", "cancelled", "neutral")
    )
    ran = passed + failed
    pass_rate = round(passed / ran * 100, 2) if ran > 0 else None
    return {
        "total_jobs": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": pass_rate,
    }


def find_run_with_real_tests(repo, workflow_id, job_filter=None, max_runs=15):
    """Find the latest completed run where at least one test job actually executed.

    Skips runs where all test jobs were skipped/cancelled (e.g. JAX CUDA
    workflows that gate on changed_files).
    """
    page = 1
    checked = 0
    while checked < max_runs:
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{workflow_id}/runs"
            f"?per_page=10&page={page}&status=completed"
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            break
        for run in runs:
            if run.get("conclusion") not in ("success", "failure"):
                continue
            checked += 1
            if checked > max_runs:
                break
            all_jobs = get_all_jobs(repo, run["id"])
            test_jobs = filter_test_jobs(all_jobs, job_filter)
            # Check if any test job actually ran (not just skipped)
            ran_jobs = [
                j
                for j in test_jobs
                if j.get("conclusion") in ("success", "failure")
            ]
            if ran_jobs:
                return run, test_jobs
        page += 1
    return None, []


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------


def download_artifact(repo, artifact_id, dest_dir):
    """Download and unzip a GitHub Actions artifact."""
    url = f"/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    zip_path = os.path.join(dest_dir, f"artifact-{artifact_id}.zip")
    cmd = [
        "gh",
        "api",
        url,
        "--method",
        "GET",
        "-H",
        "Accept: application/vnd.github+json",
    ]
    try:
        with open(zip_path, "wb") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        return True
    except (subprocess.CalledProcessError, zipfile.BadZipFile) as e:
        print(
            f"  WARNING: Failed to download artifact {artifact_id}: {e}",
            file=sys.stderr,
        )
        return False


def parse_junit_xml(path):
    """Parse a JUnit XML file and return suite-level stats."""
    suites = []
    try:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        if root.tag == "testsuites":
            elements = root.findall("testsuite")
        elif root.tag == "testsuite":
            elements = [root]
        else:
            return suites

        for ts in elements:
            name = ts.get("name", os.path.basename(path))
            tests = int(ts.get("tests", 0))
            failures = int(ts.get("failures", 0))
            errors = int(ts.get("errors", 0))
            skipped_count = int(ts.get("skipped", ts.get("skip", 0)))
            passed = tests - failures - errors - skipped_count
            suites.append(
                {
                    "name": name,
                    "tests": tests,
                    "passed": max(passed, 0),
                    "failed": failures + errors,
                    "skipped": skipped_count,
                    "errors": errors,
                }
            )
    except (ElementTree.ParseError, Exception) as e:
        print(f"  WARNING: Failed to parse {path}: {e}", file=sys.stderr)
    return suites


# ---------------------------------------------------------------------------
# PyTorch: JUnit XML from GHA artifacts
# ---------------------------------------------------------------------------


def collect_pytorch_suites(repo, run_id):
    """Download test-reports artifacts and parse JUnit XMLs."""
    artifacts = []
    page = 1
    while True:
        data = gh_api(
            f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100&page={page}"
        )
        batch = data.get("artifacts", [])
        if not batch:
            break
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    test_artifacts = [a for a in artifacts if "test-reports" in a.get("name", "")]

    if not test_artifacts:
        print(f"  No test-reports artifacts found for run {run_id}")
        return []

    all_suites = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for artifact in test_artifacts:
            art_dir = os.path.join(tmpdir, str(artifact["id"]))
            os.makedirs(art_dir, exist_ok=True)
            if not artifact.get("expired", False):
                if download_artifact(repo, artifact["id"], art_dir):
                    for root_dir, _, files in os.walk(art_dir):
                        for fname in files:
                            if fname.endswith(".xml"):
                                xml_path = os.path.join(root_dir, fname)
                                suites = parse_junit_xml(xml_path)
                                parent_name = os.path.basename(root_dir)
                                for s in suites:
                                    if (
                                        s["name"] == "pytest"
                                        and parent_name != "test-reports"
                                    ):
                                        s["name"] = parent_name
                                all_suites.extend(suites)

    # Aggregate suites with the same name (shards)
    agg = {}
    for s in all_suites:
        key = s["name"]
        if key not in agg:
            agg[key] = {
                "name": key,
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
            }
        for field in ("tests", "passed", "failed", "skipped", "errors"):
            agg[key][field] += s[field]

    return sorted(agg.values(), key=lambda s: s["name"])


def collect_pytorch(cfg):
    """Collect PyTorch test results for both ROCm and CUDA."""
    repo = cfg["repo"]
    result = {"collected_at": now_iso(), "source": "automated"}

    for platform in ("rocm", "cuda"):
        wf_cfg = WORKFLOWS["pytorch"][platform]
        wf_id = wf_cfg["workflow_id"]
        wf_name = wf_cfg["name"]
        prefer_success = wf_cfg.get("prefer_success", False)
        print(f"  Fetching {platform} ({wf_name})...")

        run = get_latest_run(repo, wf_id, prefer_success=prefer_success)
        if not run:
            print(f"  No completed run found for {wf_name}")
            result[platform] = None
            continue

        run_id = run["id"]
        run_url = run["html_url"]
        run_date = run.get("updated_at") or run.get("created_at", "")
        conclusion = run.get("conclusion", "")

        all_jobs = get_all_jobs(repo, run_id)
        test_jobs = filter_test_jobs(all_jobs)
        summary = summarize_jobs(test_jobs)

        # Try JUnit XML for detailed suite data
        suites = collect_pytorch_suites(repo, run_id)

        if suites:
            total_tests = sum(s["tests"] for s in suites)
            total_passed = sum(s["passed"] for s in suites)
            total_failed = sum(s["failed"] for s in suites)
            total_skipped = sum(s["skipped"] for s in suites)
            ran = total_passed + total_failed
            suite_pass_rate = round(total_passed / ran * 100, 2) if ran > 0 else None
            summary = {
                "total_jobs": len(test_jobs),
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "skipped": total_skipped,
                "pass_rate": suite_pass_rate,
            }

        result[platform] = {
            "workflow_name": wf_name,
            "run_id": run_id,
            "run_url": run_url,
            "run_date": run_date,
            "conclusion": conclusion,
            "summary": summary,
            "suites": suites if suites else None,
        }

    return result


# ---------------------------------------------------------------------------
# Generic job-level collector (SGLang, Triton, JAX)
# ---------------------------------------------------------------------------


def collect_job_level(project_name, cfg):
    """Collect test results using job-level conclusions from GHA API.

    Handles:
    - Job name filtering (triton: split AMD/NVIDIA from one workflow)
    - Skipped-job detection (jax CUDA: skip runs where tests didn't fire)
    - Zero-job runs (sglang ROCm: skip runs with no jobs)
    """
    repo = cfg["repo"]
    result = {"collected_at": now_iso(), "source": "automated"}

    for platform in ("rocm", "cuda"):
        wf_cfg = WORKFLOWS[project_name][platform]
        wf_id = wf_cfg["workflow_id"]
        wf_name = wf_cfg["name"]
        job_filter = wf_cfg.get("job_filter")
        prefer_success = wf_cfg.get("prefer_success", False)
        skip_all_skipped = wf_cfg.get("skip_all_skipped", False)
        print(f"  Fetching {platform} ({wf_name})...")

        run = None
        test_jobs = []

        if skip_all_skipped:
            # Need to find a run where tests actually executed
            run, test_jobs = find_run_with_real_tests(
                repo, wf_id, job_filter=job_filter, max_runs=30
            )
        else:
            run = get_latest_run(repo, wf_id, prefer_success=prefer_success)
            if run:
                all_jobs = get_all_jobs(repo, run["id"])
                test_jobs = filter_test_jobs(all_jobs, job_filter)

                # If no test jobs found, try the next run
                if not test_jobs:
                    print(f"    Run {run['id']} has 0 matching jobs, searching older runs...")
                    run2, test_jobs2 = find_run_with_real_tests(
                        repo, wf_id, job_filter=job_filter, max_runs=10
                    )
                    if run2 and test_jobs2:
                        run = run2
                        test_jobs = test_jobs2

        if not run:
            print(f"  No usable run found for {wf_name}")
            result[platform] = None
            continue

        if not test_jobs:
            print(f"  Run {run['id']} has no test jobs")
            result[platform] = None
            continue

        run_id = run["id"]
        run_url = run["html_url"]
        run_date = run.get("updated_at") or run.get("created_at", "")
        conclusion = run.get("conclusion", "")

        summary = summarize_jobs(test_jobs)

        suites = []
        for j in test_jobs:
            suites.append(
                {
                    "name": j.get("name", "unknown"),
                    "conclusion": j.get("conclusion", ""),
                    "tests": None,
                    "passed": None,
                    "failed": None,
                    "skipped": None,
                    "errors": None,
                }
            )

        result[platform] = {
            "workflow_name": wf_name,
            "run_id": run_id,
            "run_url": run_url,
            "run_date": run_date,
            "conclusion": conclusion,
            "summary": summary,
            "suites": suites if suites else None,
        }

    return result


# ---------------------------------------------------------------------------
# Manual fallback
# ---------------------------------------------------------------------------


def collect_manual(name):
    """Read manual test results from YAML config."""
    if not MANUAL_CONFIG.exists():
        return None

    with open(MANUAL_CONFIG) as f:
        manual = yaml.safe_load(f) or {}

    project_data = manual.get(name)
    if not project_data:
        return None

    has_data = False
    for platform in ("rocm", "cuda"):
        if project_data.get(platform) and project_data[platform].get("run_url"):
            has_data = True
            break

    if not has_data:
        return None

    result = {"collected_at": now_iso(), "source": "manual"}
    for platform in ("rocm", "cuda"):
        pdata = project_data.get(platform)
        if pdata:
            result[platform] = {
                "workflow_name": pdata.get("workflow_name", ""),
                "run_id": None,
                "run_url": pdata.get("run_url", ""),
                "run_date": pdata.get("run_date", ""),
                "conclusion": pdata.get("conclusion", ""),
                "summary": pdata.get("summary", {}),
                "suites": None,
            }
        else:
            result[platform] = None

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

AUTOMATED_PROJECTS = {
    "pytorch": collect_pytorch,
    "sglang": lambda cfg: collect_job_level("sglang", cfg),
    "triton": lambda cfg: collect_job_level("triton", cfg),
    "jax": lambda cfg: collect_job_level("jax", cfg),
}

MANUAL_PROJECTS = ["vllm"]


def main():
    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    projects = config.get("projects", {})

    for name in AUTOMATED_PROJECTS:
        if name not in projects:
            continue
        cfg = projects[name]
        print(f"Collecting test results for {name}...")
        try:
            result = AUTOMATED_PROJECTS[name](cfg)
            if result:
                out_dir = DATA / name
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / "test_results.json", "w") as f:
                    json.dump(result, f, indent=2)
                for platform in ("rocm", "cuda"):
                    pd = result.get(platform)
                    if pd and pd.get("summary"):
                        s = pd["summary"]
                        rate = s.get("pass_rate")
                        rate_str = f"{rate}%" if rate is not None else "N/A"
                        detail = f" ({s.get('passed', '?')}/{s.get('passed', 0) + s.get('failed', 0)} passed)"
                        print(f"  {platform}: {rate_str}{detail}")
                    else:
                        print(f"  {platform}: no data")
        except Exception as e:
            print(f"  ERROR collecting {name}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()

    for name in MANUAL_PROJECTS:
        print(f"Collecting test results for {name} (manual)...")
        result = collect_manual(name)
        if result:
            out_dir = DATA / name
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / "test_results.json", "w") as f:
                json.dump(result, f, indent=2)
            print(f"  Loaded manual data")
        else:
            print(f"  No manual data available")

    print("Test result collection complete.")


if __name__ == "__main__":
    main()
