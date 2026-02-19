#!/usr/bin/env python3
"""Parse PyTorch UT parity CSV from frameworks-internal and produce dashboard JSON.

Usage:
    python3 scripts/collect_parity.py \
        --csv /path/to/all_tests_status.csv \
        --sha <pytorch_commit_sha> \
        [--arch mi300] [--date 2026-02-19]

Inputs:
    CSV produced by frameworks-internal/pytorch-unit-test-scripts/parity.sh
    with columns: test_file, test_class, test_name, work_flow_name,
    skip_reason, assignee, comments, status_set1, message_set1,
    running_time_set1, status_set2, message_set2, running_time_set2, ...

Outputs:
    data/pytorch/parity_report.json  — latest snapshot
    data/pytorch/parity_history.json — append-only trend history
"""

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "pytorch"


def parse_csv(csv_path):
    """Read CSV and compute parity metrics matching summarize_xml_testreports.py logic."""

    workflows = {}  # workflow_name -> counters dict
    skip_reasons = Counter()
    total_time_rocm = 0.0
    total_time_cuda = 0.0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s1 = row.get("status_set1", "").strip()
            s2 = row.get("status_set2", "").strip()
            wf = row.get("work_flow_name", "").strip() or "unknown"

            if wf not in workflows:
                workflows[wf] = {
                    "rocm": 0,
                    "cuda": 0,
                    "skipped": 0,
                    "missed": 0,
                    "rocmonly": 0,
                }

            wc = workflows[wf]

            # ROCm has the test if not MISSED
            if s1 != "MISSED":
                wc["rocm"] += 1
            # CUDA has the test if not MISSED
            if s2 != "MISSED":
                wc["cuda"] += 1

            # SKIPPED: ROCm skips but CUDA doesn't skip
            if s1 == "SKIPPED" and s2 != "SKIPPED":
                wc["skipped"] += 1
                reason = row.get("skip_reason", "").strip()
                if reason:
                    skip_reasons[reason] += 1

            # MISSED: ROCm missing but CUDA has it
            if s1 == "MISSED" and s2 != "MISSED":
                wc["missed"] += 1
                reason = row.get("skip_reason", "").strip()
                if reason:
                    skip_reasons[reason] += 1

            # ROCMONLY: ROCm passes but CUDA doesn't pass (and CUDA isn't just missing)
            if s1 == "PASSED" and s2 not in ("PASSED", "MISSED", ""):
                wc["rocmonly"] += 1

            # Running times
            rt1 = row.get("running_time_set1", "").strip()
            rt2 = row.get("running_time_set2", "").strip()
            if rt1:
                try:
                    total_time_rocm += float(rt1)
                except ValueError:
                    pass
            if rt2:
                try:
                    total_time_cuda += float(rt2)
                except ValueError:
                    pass

    return workflows, skip_reasons, total_time_rocm, total_time_cuda


def build_report(workflows, skip_reasons, time_rocm, time_cuda, sha, arch, date_str):
    """Build parity_report.json structure."""
    total_rocm = sum(w["rocm"] for w in workflows.values())
    total_cuda = sum(w["cuda"] for w in workflows.values())
    total_skipped = sum(w["skipped"] for w in workflows.values())
    total_missed = sum(w["missed"] for w in workflows.values())
    total_rocmonly = sum(w["rocmonly"] for w in workflows.values())
    gap = total_skipped + total_missed
    parity_pct = (1 - gap / total_cuda) * 100 if total_cuda > 0 else 0

    by_workflow = {}
    for wf, wc in sorted(workflows.items()):
        by_workflow[wf] = {
            "rocm": wc["rocm"],
            "cuda": wc["cuda"],
            "skipped": wc["skipped"],
            "missed": wc["missed"],
            "rocmonly": wc["rocmonly"],
        }

    top_reasons = [
        {"reason": r, "count": c}
        for r, c in skip_reasons.most_common(20)
        if r  # skip empty
    ]

    return {
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_sha": sha,
        "arch": arch,
        "summary": {
            "total_rocm": total_rocm,
            "total_cuda": total_cuda,
            "skipped": total_skipped,
            "missed": total_missed,
            "rocmonly": total_rocmonly,
            "gap": gap,
            "parity_pct": round(parity_pct, 1),
        },
        "by_workflow": by_workflow,
        "top_skip_reasons": top_reasons,
        "running_time": {
            "rocm_seconds": round(time_rocm, 1),
            "cuda_seconds": round(time_cuda, 1),
        },
    }


def update_history(report, date_str):
    """Append to parity_history.json, dedup by date."""
    history_file = DATA / "parity_history.json"
    history = []
    if history_file.exists():
        with open(history_file) as f:
            history = json.load(f)

    s = report["summary"]
    entry = {
        "date": date_str,
        "commit_sha": report["commit_sha"],
        "parity_pct": s["parity_pct"],
        "skipped": s["skipped"],
        "missed": s["missed"],
        "rocmonly": s["rocmonly"],
        "total_rocm": s["total_rocm"],
        "total_cuda": s["total_cuda"],
    }

    # Dedup: replace existing entry for same date
    history = [h for h in history if h.get("date") != date_str]
    history.append(entry)
    history.sort(key=lambda h: h["date"])

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)
    print(f"History updated: {len(history)} entries in {history_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Parse PyTorch UT parity CSV and produce dashboard JSON"
    )
    parser.add_argument(
        "--csv", required=True, help="Path to *_all_tests_status.csv from parity.sh"
    )
    parser.add_argument("--sha", required=True, help="PyTorch commit SHA")
    parser.add_argument(
        "--arch", default="mi300", help="GPU architecture (default: mi300)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Override date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}")
        return 1

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"Parsing {csv_path} ...")
    workflows, skip_reasons, time_rocm, time_cuda = parse_csv(csv_path)

    report = build_report(
        workflows, skip_reasons, time_rocm, time_cuda, args.sha, args.arch, date_str
    )

    # Print summary
    s = report["summary"]
    print(
        f"Summary: ROCm={s['total_rocm']} CUDA={s['total_cuda']} "
        f"Skipped={s['skipped']} Missed={s['missed']} ROCmOnly={s['rocmonly']} "
        f"Gap={s['gap']} Parity={s['parity_pct']}%"
    )
    for wf, wc in report["by_workflow"].items():
        print(
            f"  {wf}: ROCm={wc['rocm']} CUDA={wc['cuda']} "
            f"Skipped={wc['skipped']} Missed={wc['missed']} ROCmOnly={wc['rocmonly']}"
        )

    # Write report
    DATA.mkdir(parents=True, exist_ok=True)
    report_file = DATA / "parity_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report written to {report_file}")

    # Update history
    update_history(report, date_str)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
