#!/usr/bin/env python3
"""Render Markdown dashboards from collected JSON data."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "projects.yaml"
DATA = ROOT / "data"
DASHBOARDS = ROOT / "dashboards"
SITE_DATA = ROOT / "docs" / "_data"


def load_json(path):
    """Load JSON file, return empty dict if missing."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_all_data(config):
    """Load all project data."""
    data = {}
    for name in config["projects"]:
        project_dir = DATA / name
        data[name] = {
            "prs": load_json(project_dir / "prs.json"),
            "issues": load_json(project_dir / "issues.json"),
            "releases": load_json(project_dir / "releases.json"),
        }
    return data


def render_readme(config, data):
    """Generate README.md overview dashboard."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Project Dashboard",
        "",
        f"Auto-updated tracking of AMD GPU ecosystem projects. Last updated: **{now}**",
        "",
        "## Overview",
        "",
        "| Project | Role | Latest Release | Open PRs | Open Issues | Links |",
        "|---------|------|----------------|----------|-------------|-------|",
    ]

    for name, cfg in config["projects"].items():
        d = data.get(name, {})
        role = "dev" if cfg["role"] == "active_dev" else "watch"

        # Latest release
        releases = d.get("releases", {}).get("releases", [])
        latest = releases[0]["tag_name"] if releases else "-"

        # Open PRs count
        prs = d.get("prs", {}).get("prs", [])
        open_prs = sum(1 for p in prs if p["state"] == "open")
        pr_str = str(open_prs) if open_prs else "-"

        # Open issues count
        issues = d.get("issues", {}).get("issues", [])
        open_issues = len(issues)
        issue_str = str(open_issues) if open_issues else "-"

        # Links
        repo_url = f"https://github.com/{cfg['repo']}"
        links = f"[repo]({repo_url})"
        if cfg.get("fork"):
            links += f" / [fork](https://github.com/{cfg['fork']})"

        lines.append(
            f"| **{name}** | {role} | {latest} | {pr_str} | {issue_str} | {links} |"
        )

    lines += [
        "",
        "## Live Dashboard",
        "",
        "Interactive dashboard with 4 views: **Projects**, **Test Parity**, **Activity**, and **Trends**.",
        "",
        "Hosted on GitHub Pages — deployed automatically on every push to main.",
        "",
        "## Views",
        "",
        "| View | Description |",
        "|------|-------------|",
        "| **Projects** | Per-project cards with PRs, issues, releases, and weekly activity |",
        "| **Test Parity** | ROCm vs CUDA test pass rates with CUDA parity ratio |",
        "| **Activity** | PR velocity, CI health, CI signal time, contributor stats, issue health, release cadence |",
        "| **Trends** | Weekly trend charts (PRs merged, open issues, contributors, TTM, CI signal, test pass rate) |",
        "",
        "## Markdown Dashboards",
        "",
        "- [PR Tracker](dashboards/pr-tracker.md) — all tracked PRs across projects",
        "- [Weekly Digest](dashboards/weekly-digest.md) — weekly summary of releases, PRs, and issues",
        "",
        "## Data Collection",
        "",
        "Data is collected daily at 8am UTC via GitHub Actions (`daily-update.yml`).",
        "",
        "| Script | Purpose |",
        "|--------|---------|",
        "| `scripts/collect.py` | PRs, issues, releases from GitHub API |",
        "| `scripts/collect_tests.py` | ROCm/CUDA test results from CI artifacts (JUnit XML + job-level) |",
        "| `scripts/collect_activity.py` | PR velocity, CI health, contributor stats, issue health |",
        "| `scripts/snapshot.py` | Weekly trend snapshots for historical charts |",
        "| `scripts/render.py` | Generate markdown dashboards and site data |",
        "",
        "To run manually:",
        "",
        "```bash",
        "pip install pyyaml",
        "python scripts/collect.py",
        "python scripts/collect_tests.py",
        "python scripts/collect_activity.py",
        "python scripts/snapshot.py",
        "python scripts/render.py",
        "```",
        "",
        "Configure tracked projects in [`config/projects.yaml`](config/projects.yaml).",
        "",
    ]

    readme_path = ROOT / "README.md"
    readme_path.write_text("\n".join(lines))
    print(f"Generated {readme_path}")


def render_pr_tracker(config, data):
    """Generate PR tracker dashboard."""
    lines = [
        "# PR Tracker",
        "",
        "All tracked PRs across projects, grouped by project.",
        "",
    ]

    for name, cfg in config["projects"].items():
        d = data.get(name, {})
        prs = d.get("prs", {}).get("prs", [])
        collected = d.get("prs", {}).get("collected_at", "unknown")

        role_label = "Active Development" if cfg["role"] == "active_dev" else "Upstream Watch"
        lines.append(f"## {name} ({role_label})")
        lines.append(f"Repo: `{cfg['repo']}` | Last collected: {collected}")
        lines.append("")

        if not prs:
            lines.append("_No tracked PRs._")
            lines.append("")
            continue

        lines.append("| # | Title | Author | Status | Created | Updated |")
        lines.append("|---|-------|--------|--------|---------|---------|")

        for pr in prs:
            num = pr["number"]
            title = pr["title"][:60]
            if len(pr["title"]) > 60:
                title += "..."
            author = pr["author"]
            url = pr["html_url"]

            if pr.get("merged"):
                status = "merged"
            elif pr["state"] == "closed":
                status = "closed"
            elif pr.get("draft"):
                status = "draft"
            else:
                status = "open"

            created = pr["created_at"][:10]
            updated = pr["updated_at"][:10]

            lines.append(
                f"| [#{num}]({url}) | {title} | @{author} | {status} | {created} | {updated} |"
            )

        lines.append("")

    DASHBOARDS.mkdir(parents=True, exist_ok=True)
    path = DASHBOARDS / "pr-tracker.md"
    path.write_text("\n".join(lines))
    print(f"Generated {path}")


def render_weekly_digest(config, data):
    """Generate weekly digest dashboard."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    week_ago_str = week_ago.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d")

    lines = [
        "# Weekly Digest",
        "",
        f"Week of {week_ago_str} to {now_str}",
        "",
    ]

    # New releases this week
    lines.append("## New Releases")
    lines.append("")
    any_releases = False
    for name, cfg in config["projects"].items():
        d = data.get(name, {})
        releases = d.get("releases", {}).get("releases", [])
        for r in releases:
            pub = r.get("published_at", "")
            if pub and pub[:10] >= week_ago_str:
                tag = r["tag_name"]
                url = r.get("html_url", "")
                link = f"[{tag}]({url})" if url else tag
                lines.append(f"- **{name}**: {link}")
                any_releases = True
    if not any_releases:
        lines.append("_No new releases this week._")
    lines.append("")

    # PRs opened/merged this week
    lines.append("## PRs This Week")
    lines.append("")
    any_prs = False
    for name, cfg in config["projects"].items():
        d = data.get(name, {})
        prs = d.get("prs", {}).get("prs", [])

        opened = [p for p in prs if p["created_at"][:10] >= week_ago_str]
        merged = [
            p
            for p in prs
            if p.get("merged") and p["updated_at"][:10] >= week_ago_str
        ]

        if opened or merged:
            any_prs = True
            lines.append(f"### {name}")
            for p in opened:
                lines.append(
                    f"- Opened: [#{p['number']}]({p['html_url']}) {p['title'][:60]} (@{p['author']})"
                )
            for p in merged:
                if p not in opened:
                    lines.append(
                        f"- Merged: [#{p['number']}]({p['html_url']}) {p['title'][:60]} (@{p['author']})"
                    )
            lines.append("")

    if not any_prs:
        lines.append("_No PR activity this week._")
        lines.append("")

    # New issues this week
    lines.append("## New Issues This Week")
    lines.append("")
    any_issues = False
    for name, cfg in config["projects"].items():
        d = data.get(name, {})
        issues = d.get("issues", {}).get("issues", [])
        recent = [i for i in issues if i["created_at"][:10] >= week_ago_str]
        if recent:
            any_issues = True
            lines.append(f"### {name}")
            for i in recent:
                lines.append(
                    f"- [#{i['number']}]({i['html_url']}) {i['title'][:60]} (@{i['author']})"
                )
            lines.append("")

    if not any_issues:
        lines.append("_No new tracked issues this week._")
        lines.append("")

    DASHBOARDS.mkdir(parents=True, exist_ok=True)
    path = DASHBOARDS / "weekly-digest.md"
    path.write_text("\n".join(lines))
    print(f"Generated {path}")


def render_site_data(config):
    """Generate docs/_data/projects.json for the GitHub Pages dashboard."""
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = {"projects": {}}
    for name, cfg in config["projects"].items():
        out["projects"][name] = {
            "repo": cfg["repo"],
            "role": cfg["role"],
        }
        if cfg.get("fork"):
            out["projects"][name]["fork"] = cfg["fork"]
    path = SITE_DATA / "projects.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Generated {path}")


def main():
    with open(CONFIG) as f:
        config = yaml.safe_load(f)

    data = load_all_data(config)

    render_readme(config, data)
    render_pr_tracker(config, data)
    render_weekly_digest(config, data)
    render_site_data(config)

    print("Rendering complete.")


if __name__ == "__main__":
    main()
