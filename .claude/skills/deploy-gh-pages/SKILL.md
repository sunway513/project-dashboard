# Skill: deploy-gh-pages

Deploy the project-dashboard site to GitHub Pages using the `peaceiris/actions-gh-pages` branch-based approach.

## When to Use

- After merging changes that affect `docs/` (HTML, CSS, JS) or `data/`
- When the site isn't reflecting latest changes (stale CDN)
- When setting up or debugging GitHub Pages deployment

## Architecture

- **Production deploy**: `deploy-pages.yml` → pushes `_site/` to `gh-pages` branch root on merge to `main`
- **PR preview**: `pr-preview.yml` → pushes to `gh-pages` under `pr-preview/pr-{N}/` on PR events
- **Pages source**: Branch-based (`build_type: legacy`), reading from `gh-pages` / `/ (root)`

## Site Assembly

```
_site/
├── index.html          ← from docs/
├── assets/css/         ← from docs/
├── assets/js/          ← from docs/
├── _data/projects.json ← from docs/
└── data/               ← from data/ (project JSON files)
```

## Steps to Deploy Manually

```bash
# 1. Push changes to main
git push origin main

# 2. Wait for deploy-pages.yml to complete
gh run list --workflow=deploy-pages.yml --limit=1

# 3. If CDN stale, trigger a Pages build
gh api "repos/sunway513/project-dashboard/pages/builds" -X POST

# 4. Verify (wait ~30s for CDN)
curl -sI "https://sunway513.github.io/project-dashboard/index.html" | grep x-cache
curl -sL "https://sunway513.github.io/project-dashboard/index.html" | head -30
```

## Troubleshooting Checklist

### Site not updating after deploy workflow succeeds

1. **Check `build_type`** — must be `"legacy"`, not `"workflow"`:
   ```bash
   gh api repos/sunway513/project-dashboard/pages --jq '{build_type, source}'
   ```
   If wrong, fix with:
   ```bash
   gh api repos/sunway513/project-dashboard/pages -X PUT --input - <<'EOF'
   {"build_type":"legacy","source":{"branch":"gh-pages","path":"/"}}
   EOF
   ```

2. **Trigger a Pages build** — switching `build_type` or source doesn't auto-build:
   ```bash
   gh api "repos/sunway513/project-dashboard/pages/builds" -X POST
   ```

3. **CDN cache** — GitHub Pages CDN caches aggressively. After triggering a build, wait 30-60s. Check headers:
   ```bash
   curl -sI "https://sunway513.github.io/project-dashboard/" | grep "x-cache\|last-modified"
   ```
   `x-cache: MISS` means fresh content is being served.

4. **Verify gh-pages branch content** — confirm the files are actually there:
   ```bash
   gh api repos/sunway513/project-dashboard/contents/index.html?ref=gh-pages --jq '.content' | base64 -d | head -30
   ```

### `keep_files: true` behavior

- `keep_files: true` in `deploy-pages.yml` preserves files on gh-pages that are NOT in `_site/` (e.g., `pr-preview/` dirs)
- It DOES overwrite files that exist in both `_site/` and gh-pages — this is correct behavior
- Do NOT remove `keep_files: true` or PR preview directories will be wiped on every production deploy

## Lessons Learned

- **`build_type: workflow` vs `legacy`**: Setting Pages source to a branch via API changes `source` but does NOT change `build_type`. You must explicitly set `"build_type":"legacy"` in the same PUT call. Without this, Pages ignores the branch content.
- **Manual build trigger required**: After changing Pages config, call `POST /pages/builds` to force a rebuild. The change alone doesn't trigger one.
- **Git API vs CDN**: `gh api repos/.../contents/file?ref=gh-pages` reads from Git directly. `curl https://...github.io/...` reads from CDN. These can differ for minutes after a deploy. Always verify both when debugging.
