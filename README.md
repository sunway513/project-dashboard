# Project Dashboard

Auto-updated tracking of AMD GPU ecosystem projects. Last updated: **2026-03-19 08:17 UTC**

## Overview

| Project | Role | Latest Release | Open PRs | Open Issues | Links |
|---------|------|----------------|----------|-------------|-------|
| **llvm** | watch | llvmorg-22.1.1 | 30 | 30 | [repo](https://github.com/llvm/llvm-project) |
| **pytorch** | watch | v2.10.0 | 52 | 52 | [repo](https://github.com/pytorch/pytorch) |
| **jax** | watch | jax-v0.9.2 | 13 | 33 | [repo](https://github.com/jax-ml/jax) |
| **vllm** | watch | v0.17.1 | 74 | 54 | [repo](https://github.com/vllm-project/vllm) / [fork](https://github.com/sunway513/vllm) |
| **sglang** | watch | v0.5.9 | 67 | 3 | [repo](https://github.com/sgl-project/sglang) |
| **xla** | watch | - | - | 8 | [repo](https://github.com/openxla/xla) |
| **triton** | watch | v3.6.0 | 30 | 14 | [repo](https://github.com/triton-lang/triton) |
| **migraphx** | dev | rocm-7.2.0 | 87 | 238 | [repo](https://github.com/ROCm/AMDMIGraphX) |
| **aiter** | dev | v0.1.9 | 159 | 112 | [repo](https://github.com/ROCm/aiter) / [fork](https://github.com/sunway513/aiter) |
| **atom** | dev | - | 42 | 15 | [repo](https://github.com/ROCm/ATOM) / [fork](https://github.com/sunway513/ATOM) |
| **mori** | dev | - | 11 | 10 | [repo](https://github.com/ROCm/mori) / [fork](https://github.com/sunway513/mori) |
| **flydsl** | dev | exp_i8smooth_v0.1 | 8 | 15 | [repo](https://github.com/ROCm/FlyDSL) / [fork](https://github.com/sunway513/FlyDSL) |

## Live Dashboard

Interactive dashboard with 4 views: **Projects**, **Test Parity**, **Activity**, and **Trends**.

Hosted on GitHub Pages — deployed automatically on every push to main.

## Views

| View | Description |
|------|-------------|
| **Projects** | Per-project cards with PRs, issues, releases, and weekly activity |
| **Test Parity** | ROCm vs CUDA test pass rates with CUDA parity ratio |
| **Activity** | PR velocity, CI health, CI signal time, contributor stats, issue health, release cadence |
| **Trends** | Weekly trend charts (PRs merged, open issues, contributors, TTM, CI signal, test pass rate) |

## Markdown Dashboards

- [PR Tracker](dashboards/pr-tracker.md) — all tracked PRs across projects
- [Weekly Digest](dashboards/weekly-digest.md) — weekly summary of releases, PRs, and issues

## Data Collection

Data is collected daily at 8am UTC via GitHub Actions (`daily-update.yml`).

| Script | Purpose |
|--------|---------|
| `scripts/collect.py` | PRs, issues, releases from GitHub API |
| `scripts/collect_tests.py` | ROCm/CUDA test results from CI artifacts (JUnit XML + job-level) |
| `scripts/collect_activity.py` | PR velocity, CI health, contributor stats, issue health |
| `scripts/snapshot.py` | Weekly trend snapshots for historical charts |
| `scripts/render.py` | Generate markdown dashboards and site data |

To run manually:

```bash
pip install pyyaml
python scripts/collect.py
python scripts/collect_tests.py
python scripts/collect_activity.py
python scripts/snapshot.py
python scripts/render.py
```

Configure tracked projects in [`config/projects.yaml`](config/projects.yaml).
