#!/usr/bin/env python3
"""Collect project data from GitHub API and write to data/ as JSON."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
DATA = ROOT / "data"


def gh_api(endpoint, method="GET", paginate=False):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint, "--method", method]
    if paginate:
        cmd.append("--paginate")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(
            f"  WARNING: gh api {endpoint} failed: {e.stderr.strip()}", file=sys.stderr
        )
        return []
    except json.JSONDecodeError:
        # --paginate can return concatenated JSON arrays
        raw = result.stdout.strip()
        if raw.startswith("[") and "][" in raw:
            raw = raw.replace("][", ",")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(
                f"  WARNING: could not parse response for {endpoint}", file=sys.stderr
            )
            return []


def fetch_prs(repo, authors, labels, keywords):
    """Fetch open and recently merged PRs matching filters."""
    prs = []

    # Fetch PRs by author (all states)
    for author in authors:
        items = gh_api(
            f"/repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30"
        )
        for pr in items:
            if pr.get("user", {}).get("login") == author:
                prs.append(pr)

    # Fetch PRs by label (open + closed/merged)
    for label in labels:
        for state in ["open", "closed"]:
            items = gh_api(
                f"/repos/{repo}/pulls?state={state}&sort=updated&direction=desc&per_page=30"
            )
            for pr in items:
                pr_labels = [l["name"].lower() for l in pr.get("labels", [])]
                if label.lower() in pr_labels and not any(
                    p["number"] == pr["number"] for p in prs
                ):
                    prs.append(pr)

    # Search PRs by keyword (open + merged)
    for kw in keywords:
        for pr_filter in ["is:open", "is:merged"]:
            search_results = gh_api(
                f"/search/issues?q={kw}+repo:{repo}+is:pr+{pr_filter}&sort=updated&per_page=30"
            )
            for pr in search_results.get("items", []):
                if not any(p["number"] == pr["number"] for p in prs):
                    prs.append(pr)

    # Deduplicate by number
    seen = set()
    unique = []
    for pr in prs:
        num = pr["number"]
        if num not in seen:
            seen.add(num)
            unique.append(normalize_pr(pr))
    return sorted(unique, key=lambda p: p["updated_at"], reverse=True)


def normalize_pr(pr):
    """Extract relevant PR fields."""
    return {
        "number": pr["number"],
        "title": pr.get("title", ""),
        "author": pr.get("user", {}).get("login", ""),
        "state": pr.get("state", ""),
        "merged": pr.get("merged_at") is not None
        or pr.get("pull_request", {}).get("merged_at") is not None,
        "created_at": pr.get("created_at", ""),
        "updated_at": pr.get("updated_at", ""),
        "html_url": pr.get("html_url", ""),
        "labels": [l["name"] for l in pr.get("labels", [])],
        "draft": pr.get("draft", False),
    }


def fetch_issues(repo, labels, keywords):
    """Fetch open issues matching filters."""
    issues = []

    for label in labels:
        items = gh_api(
            f"/repos/{repo}/issues?state=open&labels={quote(label)}&sort=updated&direction=desc&per_page=30"
        )
        # Filter out pull requests (GitHub API returns PRs as issues too)
        for item in items:
            if "pull_request" not in item:
                issues.append(item)

    for kw in keywords:
        search_results = gh_api(
            f"/search/issues?q={kw}+repo:{repo}+is:issue+is:open&sort=updated&per_page=30"
        )
        for item in search_results.get("items", []):
            if not any(i["number"] == item["number"] for i in issues):
                issues.append(item)

    seen = set()
    unique = []
    for issue in issues:
        num = issue["number"]
        if num not in seen:
            seen.add(num)
            unique.append(normalize_issue(issue))
    return sorted(unique, key=lambda i: i["updated_at"], reverse=True)


def normalize_issue(issue):
    """Extract relevant issue fields."""
    return {
        "number": issue["number"],
        "title": issue.get("title", ""),
        "author": issue.get("user", {}).get("login", ""),
        "state": issue.get("state", ""),
        "created_at": issue.get("created_at", ""),
        "updated_at": issue.get("updated_at", ""),
        "html_url": issue.get("html_url", ""),
        "labels": [l["name"] for l in issue.get("labels", [])],
    }


def fetch_releases(repo):
    """Fetch latest releases."""
    releases = gh_api(f"/repos/{repo}/releases?per_page=5")
    if not releases:
        # Fallback to tags
        tags = gh_api(f"/repos/{repo}/tags?per_page=3")
        return [
            {"tag_name": t["name"], "published_at": "", "html_url": ""}
            for t in tags[:3]
        ]
    return [
        {
            "tag_name": r["tag_name"],
            "name": r.get("name", ""),
            "published_at": r.get("published_at", ""),
            "html_url": r.get("html_url", ""),
            "prerelease": r.get("prerelease", False),
        }
        for r in releases[:5]
    ]


def fetch_fork_prs(fork_repo, upstream_repo, authors):
    """Fetch PRs from fork to upstream (our PRs to upstream)."""
    prs = []
    for author in authors:
        items = gh_api(
            f"/repos/{upstream_repo}/pulls?state=all&sort=updated&direction=desc&per_page=30"
        )
        for pr in items:
            if pr.get("user", {}).get("login") == author:
                prs.append(normalize_pr(pr))

    seen = set()
    unique = []
    for pr in prs:
        if pr["number"] not in seen:
            seen.add(pr["number"])
            unique.append(pr)
    return sorted(unique, key=lambda p: p["updated_at"], reverse=True)


def fetch_all_open_prs(repo):
    """Fetch all open PRs for a repo (for active_dev projects)."""
    items = gh_api(
        f"/repos/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=100",
        paginate=True,
    )
    if not isinstance(items, list):
        items = []
    return [normalize_pr(pr) for pr in items]


def fetch_recently_merged_prs(repo):
    """Fetch recently merged PRs (most recent 100 closed, filtered to merged)."""
    items = gh_api(
        f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100",
    )
    if not isinstance(items, list):
        items = []
    return [normalize_pr(pr) for pr in items if pr.get("merged_at")]


def fetch_all_open_issues(repo):
    """Fetch all open issues for a repo (for active_dev projects)."""
    items = gh_api(
        f"/repos/{repo}/issues?state=open&sort=updated&direction=desc&per_page=100",
        paginate=True,
    )
    if not isinstance(items, list):
        items = []
    # Filter out pull requests (GitHub API returns PRs as issues too)
    return [normalize_issue(i) for i in items if "pull_request" not in i]


def collect_project(name, cfg):
    """Collect all data for a single project."""
    print(f"Collecting {name} ({cfg['repo']})...")
    project_dir = DATA / name
    project_dir.mkdir(parents=True, exist_ok=True)

    repo = cfg["repo"]
    role = cfg.get("role", "upstream_watch")
    authors = cfg.get("track_authors", [])
    labels = cfg.get("track_labels", [])
    keywords = cfg.get("track_keywords", [])

    # Collect PRs
    if role == "active_dev":
        # For our own projects, fetch ALL open PRs + recently merged
        prs = fetch_all_open_prs(repo)
        merged_prs = fetch_recently_merged_prs(repo)
        existing_nums = {p["number"] for p in prs}
        for mp in merged_prs:
            if mp["number"] not in existing_nums:
                prs.append(mp)
    else:
        # For upstream projects, fetch filtered PRs + recently merged by our authors
        prs = fetch_prs(repo, authors, labels, keywords)
        if authors:
            merged_prs = fetch_recently_merged_prs(repo)
            existing_nums = {p["number"] for p in prs}
            for mp in merged_prs:
                if mp["number"] not in existing_nums and mp["author"] in authors:
                    prs.append(mp)

    # If there's a fork, also collect our PRs to upstream
    fork = cfg.get("fork")
    if fork and authors:
        fork_prs = fetch_fork_prs(fork, repo, authors)
        existing_nums = {p["number"] for p in prs}
        for fp in fork_prs:
            if fp["number"] not in existing_nums:
                prs.append(fp)

    with open(project_dir / "prs.json", "w") as f:
        json.dump({"collected_at": now_iso(), "prs": prs}, f, indent=2)

    # Collect issues
    if role == "active_dev":
        # For our own projects, fetch ALL open issues
        issues = fetch_all_open_issues(repo)
    else:
        # For upstream projects, only fetch issues matching filters
        issues = fetch_issues(repo, labels, keywords)
    with open(project_dir / "issues.json", "w") as f:
        json.dump({"collected_at": now_iso(), "issues": issues}, f, indent=2)

    # Collect releases
    releases = fetch_releases(repo)
    with open(project_dir / "releases.json", "w") as f:
        json.dump({"collected_at": now_iso(), "releases": releases}, f, indent=2)

    print(f"  {len(prs)} PRs, {len(issues)} issues, {len(releases)} releases")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    for name, cfg in config["projects"].items():
        collect_project(name, cfg)

    print("Collection complete.")


if __name__ == "__main__":
    main()
