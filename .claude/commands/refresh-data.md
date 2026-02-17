---
description: Refresh all project dashboard data (collect, render, commit, deploy)
allowed-tools: [Bash, Read, Glob, Grep]
---

# Refresh Dashboard Data

Comprehensive data refresh for the project dashboard. Collects fresh data from GitHub, regenerates dashboards, commits, and pushes to trigger deploy.

## Steps

1. **Ensure clean state**: Check we are on `main` with no uncommitted changes.

```
cd /home/pensun/project-dashboard
git checkout main
git pull origin main
git status
```

2. **Collect fresh data**: Run the collector which fetches PRs (open + recently merged), issues, and releases for all projects via the GitHub API.

```
python3 scripts/collect.py
```

3. **Verify collection**: Spot-check that data looks reasonable — all projects should have non-zero PR counts and merged PRs for active_dev projects.

```
python3 -c "
import json
for name in ['pytorch','jax','vllm','sglang','aiter','atom','mori','flydsl']:
    data = json.load(open(f'data/{name}/prs.json'))
    prs = data['prs']
    merged = sum(1 for p in prs if p.get('merged'))
    open_ = sum(1 for p in prs if p['state'] == 'open')
    print(f'{name}: {len(prs)} total, {open_} open, {merged} merged')
"
```

4. **Regenerate dashboards**: Re-render the Markdown dashboards, README, and site data JSON from the freshly collected data.

```
python3 scripts/render.py
```

5. **Commit and push**: Stage all changed data and generated files, commit, and push to main. This triggers the `deploy-pages.yml` workflow automatically.

```
git add data/ docs/_data/projects.json README.md dashboards/
git commit -m "Refresh dashboard data $(date +%Y-%m-%d)"
git push origin main
```

6. **Verify deploy**: Check that the GitHub Pages deploy workflow triggered and completed.

```
sleep 10
gh api repos/sunway513/project-dashboard/actions/runs --jq '.workflow_runs[0] | {name, status, conclusion, created: .created_at}'
```

## Notes

- The collector fetches open PRs (paginated) + last 100 merged PRs for active_dev projects
- For upstream_watch projects, it searches by labels and keywords for both open and merged PRs
- Bot accounts (pytorchbot, dependabot, etc.) are filtered client-side in the dashboard JS
- GitHub API rate limits: ~5000 requests/hour authenticated. A full collect uses ~50-80 requests.
- If a specific project fails, check `gh auth status` and retry.
