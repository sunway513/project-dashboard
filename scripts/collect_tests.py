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

# Workflow IDs per project — maps project name to {rocm: id, cuda: id}
WORKFLOW_IDS = {
    "pytorch": {
        "rocm": 139700577,  # rocm-mi300
        "cuda": 16535519,  # trunk
    },
    "sglang": {
        "rocm": 158870224,  # Nightly Test (AMD)
        "cuda": 115218617,  # PR Test
    },
    "triton": {
        "rocm": 158326442,  # Integration Tests AMD
        "cuda": 158326443,  # Integration Tests CUDA
    },
}

# Workflow display names
WORKFLOW_NAMES = {
    "pytorch": {"rocm": "rocm-mi300", "cuda": "trunk"},
    "sglang": {"rocm": "Nightly Test (AMD)", "cuda": "PR Test"},
    "triton": {"rocm": "Integration Tests AMD", "cuda": "Integration Tests CUDA"},
}


def gh_api(endpoint, method="GET"):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint, "--method", method]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: gh api {endpoint} failed: {e.stderr.strip()}", file=sys.stderr)
        return {}
    except json.JSONDecodeError:
        print(f"  WARNING: could not parse response for {endpoint}", file=sys.stderr)
        return {}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# GitHub Actions helpers
# ---------------------------------------------------------------------------


def get_latest_run(repo, workflow_id, max_pages=3):
    """Get the latest completed (success or failure) run, skipping cancelled."""
    for page in range(1, max_pages + 1):
        data = gh_api(
            f"/repos/{repo}/actions/workflows/{workflow_id}/runs"
            f"?per_page=10&page={page}"
        )
        for run in data.get("workflow_runs", []):
            if run.get("status") == "completed" and run.get("conclusion") in (
                "success",
                "failure",
            ):
                return run
    return None


def get_test_jobs(repo, run_id):
    """Get jobs from a workflow run, filtered to test-related jobs."""
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
    # Filter to test jobs (heuristic: name contains "test" case-insensitive)
    test_jobs = [j for j in jobs if "test" in j.get("name", "").lower()]
    # If no jobs match "test", return all jobs
    if not test_jobs:
        test_jobs = jobs
    return test_jobs


def summarize_jobs(jobs):
    """Summarize job conclusions into pass/fail/skip counts and pass rate."""
    total = len(jobs)
    passed = sum(1 for j in jobs if j.get("conclusion") == "success")
    failed = sum(1 for j in jobs if j.get("conclusion") == "failure")
    skipped = sum(
        1 for j in jobs if j.get("conclusion") in ("skipped", "cancelled", "neutral")
    )
    # Pass rate excludes skipped jobs (they didn't run)
    ran = passed + failed
    pass_rate = round(passed / ran * 100, 1) if ran > 0 else 0
    return {
        "total_jobs": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": pass_rate,
    }


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
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        return True
    except (subprocess.CalledProcessError, zipfile.BadZipFile) as e:
        print(f"  WARNING: Failed to download artifact {artifact_id}: {e}", file=sys.stderr)
        return False


def parse_junit_xml(path):
    """Parse a JUnit XML file and return suite-level stats."""
    suites = []
    try:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        # Handle both <testsuites> wrapper and direct <testsuite>
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
    # List artifacts for this run
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

    # Filter to test-reports artifacts
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
                    # Find all XML files
                    for root_dir, _, files in os.walk(art_dir):
                        for fname in files:
                            if fname.endswith(".xml"):
                                xml_path = os.path.join(root_dir, fname)
                                suites = parse_junit_xml(xml_path)
                                # Use parent directory as suite name (contains module name)
                                # e.g. test-reports/python-pytest/inductor.test_aot_inductor/...xml
                                parent_name = os.path.basename(root_dir)
                                for s in suites:
                                    if s["name"] == "pytest" and parent_name != "test-reports":
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
        wf_id = WORKFLOW_IDS["pytorch"][platform]
        wf_name = WORKFLOW_NAMES["pytorch"][platform]
        print(f"  Fetching {platform} ({wf_name})...")

        run = get_latest_run(repo, wf_id)
        if not run:
            print(f"  No completed run found for {wf_name}")
            result[platform] = None
            continue

        run_id = run["id"]
        run_url = run["html_url"]
        run_date = run.get("updated_at") or run.get("created_at", "")
        conclusion = run.get("conclusion", "")

        # Get job-level summary
        jobs = get_test_jobs(repo, run_id)
        summary = summarize_jobs(jobs)

        # Try to get suite-level detail from JUnit XML artifacts
        suites = collect_pytorch_suites(repo, run_id)

        # If we got suite data, recompute summary from suites
        if suites:
            total_tests = sum(s["tests"] for s in suites)
            total_passed = sum(s["passed"] for s in suites)
            total_failed = sum(s["failed"] for s in suites)
            total_skipped = sum(s["skipped"] for s in suites)
            # Pass rate excludes skipped tests
            ran = total_passed + total_failed
            suite_pass_rate = (
                round(total_passed / ran * 100, 1) if ran > 0 else 0
            )
            summary = {
                "total_jobs": len(jobs),
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
# SGLang: Job-level conclusions from GHA API
# ---------------------------------------------------------------------------


def collect_sglang(cfg):
    """Collect SGLang test results for both ROCm and CUDA."""
    repo = cfg["repo"]
    result = {"collected_at": now_iso(), "source": "automated"}

    for platform in ("rocm", "cuda"):
        wf_id = WORKFLOW_IDS["sglang"][platform]
        wf_name = WORKFLOW_NAMES["sglang"][platform]
        print(f"  Fetching {platform} ({wf_name})...")

        run = get_latest_run(repo, wf_id)
        if not run:
            print(f"  No completed run found for {wf_name}")
            result[platform] = None
            continue

        run_id = run["id"]
        run_url = run["html_url"]
        run_date = run.get("updated_at") or run.get("created_at", "")
        conclusion = run.get("conclusion", "")

        jobs = get_test_jobs(repo, run_id)
        summary = summarize_jobs(jobs)

        # Build suite-like entries from jobs (no per-test counts)
        suites = []
        for j in jobs:
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
# Triton: Job-level conclusions from GHA API
# ---------------------------------------------------------------------------


def collect_triton(cfg):
    """Collect Triton test results for both AMD and CUDA."""
    repo = cfg["repo"]
    result = {"collected_at": now_iso(), "source": "automated"}

    for platform in ("rocm", "cuda"):
        wf_id = WORKFLOW_IDS["triton"][platform]
        wf_name = WORKFLOW_NAMES["triton"][platform]
        print(f"  Fetching {platform} ({wf_name})...")

        run = get_latest_run(repo, wf_id)
        if not run:
            print(f"  No completed run found for {wf_name}")
            result[platform] = None
            continue

        run_id = run["id"]
        run_url = run["html_url"]
        run_date = run.get("updated_at") or run.get("created_at", "")
        conclusion = run.get("conclusion", "")

        jobs = get_test_jobs(repo, run_id)
        summary = summarize_jobs(jobs)

        suites = []
        for j in jobs:
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

    # Check if there's any actual data (not just empty/commented entries)
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

# Projects with automated test collection
AUTOMATED_PROJECTS = {
    "pytorch": collect_pytorch,
    "sglang": collect_sglang,
    "triton": collect_triton,
}

# Projects with manual-only test data
MANUAL_PROJECTS = ["vllm", "jax"]


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
                # Print summary
                for platform in ("rocm", "cuda"):
                    pd = result.get(platform)
                    if pd and pd.get("summary"):
                        rate = pd["summary"].get("pass_rate", "?")
                        print(f"  {platform}: {rate}% pass rate")
                    else:
                        print(f"  {platform}: no data")
        except Exception as e:
            print(f"  ERROR collecting {name}: {e}", file=sys.stderr)

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
