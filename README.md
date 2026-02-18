# Project Dashboard

Auto-updated tracking of AMD GPU ecosystem projects. Last updated: **2026-02-18 08:15 UTC**

## Overview

| Project | Role | Latest Release | Open PRs | Open Issues | Links |
|---------|------|----------------|----------|-------------|-------|
| **pytorch** | watch | v2.10.0 | 45 | 52 | [repo](https://github.com/pytorch/pytorch) |
| **jax** | watch | jax-v0.9.0.1 | 22 | 57 | [repo](https://github.com/jax-ml/jax) |
| **vllm** | watch | v0.16.0 | 62 | 50 | [repo](https://github.com/vllm-project/vllm) / [fork](https://github.com/sunway513/vllm) |
| **sglang** | watch | v0.5.8 | 63 | 43 | [repo](https://github.com/sgl-project/sglang) |
| **aiter** | dev | v0.1.9 | 197 | 91 | [repo](https://github.com/ROCm/aiter) / [fork](https://github.com/sunway513/aiter) |
| **atom** | dev | - | 25 | 10 | [repo](https://github.com/ROCm/ATOM) / [fork](https://github.com/sunway513/ATOM) |
| **mori** | dev | - | 8 | 10 | [repo](https://github.com/ROCm/mori) / [fork](https://github.com/sunway513/mori) |
| **flydsl** | dev | - | - | - | [repo](https://github.com/sunway513/FlyDSL) |

## Dashboards

- [PR Tracker](dashboards/pr-tracker.md) - All PRs across projects
- [Weekly Digest](dashboards/weekly-digest.md) - Weekly summary

## Setup

Data is collected daily via GitHub Actions. To run manually:

```bash
pip install pyyaml
python scripts/collect.py   # fetch data from GitHub
python scripts/render.py    # generate dashboards
```

Configure tracked projects in [`config/projects.yaml`](config/projects.yaml).
