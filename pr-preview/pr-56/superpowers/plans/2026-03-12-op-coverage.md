# Op Coverage Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Op Coverage" tab to project-dashboard showing AMD vs NV operator coverage across 11 categories with ~120 operators.

**Architecture:** New tab in existing static site. Single JSON data file drives a JS render function that builds accordion sections with comparison tables. No new libraries — pure HTML/CSS/JS extending existing patterns.

**Tech Stack:** Vanilla JS, HTML `<details>/<summary>` for accordion, CSS extending `dashboard.css`.

**Spec:** `docs/superpowers/specs/2026-03-12-op-coverage-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `docs/_data/op-coverage.json` | Create | All operator data (categories, operators, coverage) |
| `docs/index.html` | Modify | Add tab button + panel div |
| `docs/assets/js/op-coverage.js` | Create | Render logic for op coverage view |
| `docs/assets/js/dashboard.js` | Modify | Load op-coverage data + call render + load script |
| `docs/assets/css/dashboard.css` | Modify | Add op-coverage styles |

Rationale for separate `op-coverage.js`: dashboard.js is already 1000+ lines. Following the pattern of focused files, op-coverage rendering gets its own file. dashboard.js only loads data and delegates.

---

## Chunk 1: Data + HTML Shell

### Task 1: Create op-coverage.json data file

**Files:**
- Create: `docs/_data/op-coverage.json`

- [ ] **Step 1: Create the complete JSON data file**

Create `docs/_data/op-coverage.json` with all 11 categories and ~120 operators. Structure:

```json
{
  "lastUpdated": "2026-03-12",
  "categories": [
    {
      "id": "attention",
      "name": "Attention",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer", "FlashMLA"],
      "operators": [
        { "name": "MHA Prefill (FP16/BF16)", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "MHA Prefill (FP8)", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "MHA Decode", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "MHA Varlen", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "MLA Decode", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": true } },
        { "name": "MLA Prefill", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "Paged Attention Decode", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "Paged Attention Prefill", "coverage": { "Aiter": true, "FlashInfer": true, "FlashMLA": false } },
        { "name": "Paged Attention Ragged", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "Cascade Attention", "coverage": { "Aiter": false, "FlashInfer": true, "FlashMLA": false } },
        { "name": "Sparse MLA", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "SAGE Attention (MXFP4)", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "HSTU Attention", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "POD Attention", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "Lean Attention", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } },
        { "name": "Unified Attention", "coverage": { "Aiter": true, "FlashInfer": false, "FlashMLA": false } }
      ]
    },
    {
      "id": "gemm",
      "name": "GEMM",
      "amd_projects": ["Aiter", "hipBLASLt"],
      "nv_projects": ["cuBLASLt"],
      "operators": [
        { "name": "GEMM FP16/BF16", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM FP8 (per-tensor)", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM FP8 blockscale", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM INT8", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM FP4/MXFP4", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM A16W8 blockscale", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "GEMM A16WFP4", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "GEMM A8WFP4", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "Batched GEMM BF16", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "Batched GEMM FP8", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "Batched GEMM FP4", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "Grouped GEMM (MoE)", "coverage": { "Aiter": true, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM + Bias fusion", "coverage": { "Aiter": false, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "GEMM + ReLU/GELU/SiLU fusion", "coverage": { "Aiter": false, "hipBLASLt": true, "cuBLASLt": true } },
        { "name": "DeepGEMM", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "Fused GEMM (multi-stage)", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "Feed-Forward Fused", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } },
        { "name": "B-preshuffle GEMM", "coverage": { "Aiter": true, "hipBLASLt": false, "cuBLASLt": false } }
      ]
    },
    {
      "id": "moe",
      "name": "MoE",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "Fused MoE BF16", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Fused MoE FP8", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Fused MoE FP8 blockscale", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Fused MoE MXFP4", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Fused MoE INT8 SmoothQuant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Fused MoE A8W4", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Fused MoE A4W4", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MoE + SiLU fused", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MoE + GELU fused", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MoE 2-stage (CK/CKTile)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "TopK Softmax", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "TopK Sigmoid", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Biased Grouped TopK", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MoE Sorting", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MoE Align Block Size", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "MoE Routing (bitmatrix)", "coverage": { "Aiter": true, "FlashInfer": false } }
      ]
    },
    {
      "id": "normalization",
      "name": "Normalization",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "RMSNorm", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "RMSNorm + Add (fused)", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "RMSNorm + Quant (fused)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "RMSNorm + Add + Quant (fused)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "RMSNorm + SmoothQuant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "LayerNorm", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "LayerNorm + Add", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "LayerNorm + SmoothQuant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "GroupNorm", "coverage": { "Aiter": true, "FlashInfer": false } }
      ]
    },
    {
      "id": "quantization",
      "name": "Quantization",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "Static per-tensor quant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Dynamic per-tensor quant", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Dynamic per-token quant", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Per-group FP4 quant", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "SmoothQuant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "MXFP4 quant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Fused FP8 quant", "coverage": { "Aiter": true, "FlashInfer": false } }
      ]
    },
    {
      "id": "positional-encoding",
      "name": "Positional Encoding",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "RoPE (NEOX/GPT-J)", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "RoPE cached (cos/sin)", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "RoPE 2-channel (Q+K)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "RoPE THD (varlen)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "RoPE 2D (vision)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "RoPE + positions + offsets", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Batched RoPE", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "LLaMA 3.1 RoPE", "coverage": { "Aiter": false, "FlashInfer": true } }
      ]
    },
    {
      "id": "sampling",
      "name": "Sampling",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "Greedy sampling", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Random sampling", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Top-K sampling", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Top-P sampling", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Top-K + Top-P joint", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "Min-P sampling", "coverage": { "Aiter": false, "FlashInfer": true } },
        { "name": "Speculative sampling", "coverage": { "Aiter": false, "FlashInfer": true } }
      ]
    },
    {
      "id": "elementwise",
      "name": "Elementwise / Activation",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "SiLU and mul", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "GELU and mul", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "GELU-Tanh and mul", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Scaled SiLU and mul", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "add / sub / mul / div", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "sigmoid / tanh", "coverage": { "Aiter": true, "FlashInfer": false } }
      ]
    },
    {
      "id": "kv-cache",
      "name": "KV Cache Management",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "reshape_and_cache", "coverage": { "Aiter": true, "FlashInfer": true } },
        { "name": "reshape_and_cache FP8/INT8", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "reshape_and_cache block quant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "swap_blocks", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "copy_blocks", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "concat_and_cache MLA", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Fused QK+RoPE+Cache+Quant", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Paged KV append", "coverage": { "Aiter": false, "FlashInfer": true } }
      ]
    },
    {
      "id": "communication",
      "name": "Communication",
      "amd_projects": ["Aiter", "Mori", "RCCL"],
      "nv_projects": ["DeepEP", "NCCL"],
      "operators": [
        { "name": "AllReduce", "coverage": { "Aiter": true, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "AllReduce + RMSNorm (fused)", "coverage": { "Aiter": true, "Mori": false, "RCCL": false, "DeepEP": false, "NCCL": false } },
        { "name": "ReduceScatter", "coverage": { "Aiter": true, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "AllGather", "coverage": { "Aiter": true, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "AllToAll", "coverage": { "Aiter": false, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "Broadcast", "coverage": { "Aiter": false, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "Send / Recv", "coverage": { "Aiter": false, "Mori": false, "RCCL": true, "DeepEP": false, "NCCL": true } },
        { "name": "EP Dispatch (IntraNode)", "coverage": { "Aiter": true, "Mori": true, "RCCL": false, "DeepEP": true, "NCCL": false } },
        { "name": "EP Dispatch (InterNode)", "coverage": { "Aiter": true, "Mori": true, "RCCL": false, "DeepEP": true, "NCCL": false } },
        { "name": "EP Combine (IntraNode)", "coverage": { "Aiter": true, "Mori": true, "RCCL": false, "DeepEP": true, "NCCL": false } },
        { "name": "EP Combine (InterNode)", "coverage": { "Aiter": true, "Mori": true, "RCCL": false, "DeepEP": true, "NCCL": false } },
        { "name": "EP Low-Latency (LL)", "coverage": { "Aiter": false, "Mori": true, "RCCL": false, "DeepEP": true, "NCCL": false } },
        { "name": "RDMA Read/Write (P2P)", "coverage": { "Aiter": false, "Mori": true, "RCCL": false, "DeepEP": false, "NCCL": false } },
        { "name": "RDMA Batch IO", "coverage": { "Aiter": false, "Mori": true, "RCCL": false, "DeepEP": false, "NCCL": false } },
        { "name": "Shmem (symmetric memory)", "coverage": { "Aiter": false, "Mori": true, "RCCL": false, "DeepEP": false, "NCCL": false } },
        { "name": "ReduceScatter+RMSNorm+Quant+AllGather (fused)", "coverage": { "Aiter": true, "Mori": false, "RCCL": false, "DeepEP": false, "NCCL": false } }
      ]
    },
    {
      "id": "other",
      "name": "Other",
      "amd_projects": ["Aiter"],
      "nv_projects": ["FlashInfer"],
      "operators": [
        { "name": "Causal Conv1D", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Gated Delta Net (SSM)", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Weight Shuffle/Preshuffle", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Ragged Layout Transform", "coverage": { "Aiter": true, "FlashInfer": false } },
        { "name": "Softmax", "coverage": { "Aiter": true, "FlashInfer": false } }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('docs/_data/op-coverage.json')); print('Valid JSON')"`
Expected: `Valid JSON`

- [ ] **Step 3: Commit**

```bash
git add docs/_data/op-coverage.json
git commit -m "feat: add op-coverage data file with 11 categories and ~120 operators"
```

---

### Task 2: Add HTML shell for Op Coverage tab

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add tab button and panel to index.html**

In `docs/index.html`, add a new tab button after the "Trends" button (line 19):

```html
<button class="tab-btn" data-tab="op-coverage">Op Coverage</button>
```

Add a new panel div after `#tab-trends` (after line 37):

```html
<div id="tab-op-coverage" class="tab-panel">
  <section id="op-coverage-view"></section>
</div>
```

Add script tag before closing `</body>` (after line 45, before `dashboard.js`):

```html
<script src="assets/js/op-coverage.js"></script>
```

- [ ] **Step 2: Verify the HTML is valid by opening in browser**

Run: `open docs/index.html` (or verify manually that the tab appears)

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add Op Coverage tab shell to index.html"
```

---

## Chunk 2: CSS Styles

### Task 3: Add op-coverage CSS styles

**Files:**
- Modify: `docs/assets/css/dashboard.css`

- [ ] **Step 1: Append op-coverage styles to dashboard.css**

Add at the end of `docs/assets/css/dashboard.css`:

```css
/* ---------------------------------------------------------------------------
   Op Coverage View (Tab 5)
   --------------------------------------------------------------------------- */

#op-coverage-view h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-muted);
}

/* Summary bar */
.oc-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.oc-summary-box {
  flex: 1;
  min-width: 140px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-top: 3px solid var(--accent-blue);
  border-radius: 8px;
  padding: 12px 16px;
  text-align: center;
}

.oc-summary-num {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.oc-summary-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Category accordion */
.oc-categories {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.oc-category {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.oc-category summary {
  padding: 12px 16px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 12px;
}

.oc-category summary::before {
  content: "\25B6";
  font-size: 10px;
  flex-shrink: 0;
  transition: transform 0.15s;
}

.oc-category[open] summary::before {
  transform: rotate(90deg);
}

.oc-category summary:hover {
  background: var(--hover);
}

.oc-cat-name {
  flex: 1;
}

.oc-cat-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
}

.oc-cat-badges {
  display: flex;
  gap: 6px;
}

.oc-badge-amd,
.oc-badge-nv {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  color: #fff;
}

.oc-badge-amd {
  background: #ed1c24;
}

.oc-badge-nv {
  background: #76b900;
}

/* Coverage table */
.oc-table-wrap {
  padding: 0 16px 16px;
}

.oc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.oc-table th {
  text-align: center;
  padding: 6px 10px;
  border-bottom: 2px solid var(--border);
  color: var(--text-muted);
  font-weight: 500;
  font-size: 12px;
  white-space: nowrap;
}

.oc-table th:first-child {
  text-align: left;
}

.oc-table th.oc-th-sep {
  border-left: 2px solid var(--border);
}

.oc-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  text-align: center;
}

.oc-table td:first-child {
  text-align: left;
  font-weight: 500;
}

.oc-table td.oc-td-sep {
  border-left: 2px solid var(--border);
}

.oc-table tr:last-child td {
  border-bottom: none;
}

.oc-table tr:hover td {
  background: var(--hover);
}

/* Coverage icons */
.oc-yes {
  color: var(--accent-green);
  font-weight: 700;
}

.oc-no {
  color: var(--text-muted);
}

.oc-partial {
  color: var(--accent-orange);
}

/* Updated timestamp */
.oc-updated {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 16px;
  text-align: right;
}
```

- [ ] **Step 2: Commit**

```bash
git add docs/assets/css/dashboard.css
git commit -m "feat: add op-coverage CSS styles"
```

---

## Chunk 3: JavaScript Rendering

### Task 4: Create op-coverage.js render function

**Files:**
- Create: `docs/assets/js/op-coverage.js`

- [ ] **Step 1: Create the render function**

Create `docs/assets/js/op-coverage.js`:

```javascript
/**
 * Op Coverage view — renders AMD vs NV operator comparison tables.
 * Called from dashboard.js after data is loaded.
 */

function renderOpCoverage(data) {
  var el = document.getElementById("op-coverage-view");
  if (!data || !data.categories) {
    el.innerHTML = '<h2>Op Coverage</h2><p class="empty">No op coverage data available.</p>';
    return;
  }

  var cats = data.categories;
  var totalOps = 0;
  var totalAmd = 0;
  var totalNv = 0;

  // Pre-compute stats
  for (var i = 0; i < cats.length; i++) {
    var ops = cats[i].operators;
    var amdProjects = cats[i].amd_projects;
    var nvProjects = cats[i].nv_projects;
    totalOps += ops.length;
    for (var j = 0; j < ops.length; j++) {
      var cov = ops[j].coverage;
      var hasAmd = amdProjects.some(function (p) { return cov[p] === true; });
      var hasNv = nvProjects.some(function (p) { return cov[p] === true; });
      if (hasAmd) totalAmd++;
      if (hasNv) totalNv++;
    }
  }

  var html = '<h2>Op Coverage — AMD vs NV Ecosystem</h2>';

  // Summary boxes
  html += '<div class="oc-summary">';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalOps + '</div><div class="oc-summary-label">Total Operators</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalAmd + '</div><div class="oc-summary-label">AMD Covered</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + totalNv + '</div><div class="oc-summary-label">NV Covered</div></div>';
  html += '<div class="oc-summary-box"><div class="oc-summary-num">' + cats.length + '</div><div class="oc-summary-label">Categories</div></div>';
  html += '</div>';

  // Accordion categories
  html += '<div class="oc-categories">';
  for (var i = 0; i < cats.length; i++) {
    html += buildOcCategory(cats[i]);
  }
  html += '</div>';

  // Updated timestamp
  if (data.lastUpdated) {
    html += '<div class="oc-updated">Data last updated: ' + escapeHtml(data.lastUpdated) + '</div>';
  }

  el.innerHTML = html;
}

function buildOcCategory(cat) {
  var ops = cat.operators;
  var amdProjects = cat.amd_projects;
  var nvProjects = cat.nv_projects;

  // Compute per-category stats
  var amdCount = 0;
  var nvCount = 0;
  for (var i = 0; i < ops.length; i++) {
    var cov = ops[i].coverage;
    if (amdProjects.some(function (p) { return cov[p] === true; })) amdCount++;
    if (nvProjects.some(function (p) { return cov[p] === true; })) nvCount++;
  }

  var amdLabel = amdProjects.join(", ");
  var nvLabel = nvProjects.join(", ");

  var html = '<details class="oc-category">';

  // Summary line
  html += '<summary>';
  html += '<span class="oc-cat-name">' + escapeHtml(cat.name) + '</span>';
  html += '<span class="oc-cat-count">' + ops.length + ' ops</span>';
  html += '<span class="oc-cat-badges">';
  html += '<span class="oc-badge-amd">AMD: ' + amdCount + '/' + ops.length + '</span>';
  html += '<span class="oc-badge-nv">NV: ' + nvCount + '/' + ops.length + '</span>';
  html += '</span>';
  html += '</summary>';

  // Table
  html += '<div class="oc-table-wrap">';
  html += '<table class="oc-table">';

  // Header row
  html += '<tr>';
  html += '<th>Operator</th>';
  for (var a = 0; a < amdProjects.length; a++) {
    html += '<th>' + escapeHtml(amdProjects[a]) + '</th>';
  }
  // Separator + NV columns
  for (var n = 0; n < nvProjects.length; n++) {
    html += '<th class="' + (n === 0 ? 'oc-th-sep' : '') + '">' + escapeHtml(nvProjects[n]) + '</th>';
  }
  html += '</tr>';

  // Data rows
  for (var i = 0; i < ops.length; i++) {
    var op = ops[i];
    html += '<tr>';
    html += '<td>' + escapeHtml(op.name) + '</td>';
    for (var a = 0; a < amdProjects.length; a++) {
      html += '<td>' + coverageIcon(op.coverage[amdProjects[a]]) + '</td>';
    }
    for (var n = 0; n < nvProjects.length; n++) {
      html += '<td class="' + (n === 0 ? 'oc-td-sep' : '') + '">' + coverageIcon(op.coverage[nvProjects[n]]) + '</td>';
    }
    html += '</tr>';
  }

  html += '</table>';
  html += '</div>';
  html += '</details>';
  return html;
}

function coverageIcon(val) {
  if (val === true) return '<span class="oc-yes">&#10003;</span>';
  if (val === "partial") return '<span class="oc-partial">&#9881;</span>';
  return '<span class="oc-no">&mdash;</span>';
}
```

- [ ] **Step 2: Commit**

```bash
git add docs/assets/js/op-coverage.js
git commit -m "feat: add op-coverage.js render function"
```

---

### Task 5: Wire up data loading in dashboard.js

**Files:**
- Modify: `docs/assets/js/dashboard.js`

- [ ] **Step 1: Add op-coverage data fetch and render call**

In `docs/assets/js/dashboard.js`, add the op-coverage data loading. After line 32 (where `parityHistPromise` is defined), add:

```javascript
const opCoveragePromise = fetchJSON("_data/op-coverage.json");
```

After line 63 (where `parityHistData` is awaited), add:

```javascript
const opCoverageData = await opCoveragePromise;
```

After line 70 (after `renderTrendsView`), add:

```javascript
renderOpCoverage(opCoverageData);
```

- [ ] **Step 2: Verify the page loads correctly**

Open `docs/index.html` in a browser and click the "Op Coverage" tab. All 11 categories should render as accordion sections with comparison tables.

- [ ] **Step 3: Commit**

```bash
git add docs/assets/js/dashboard.js
git commit -m "feat: wire up op-coverage data loading and rendering"
```

---

## Chunk 4: Final Verification

### Task 6: End-to-end verification and commit

- [ ] **Step 1: Open the dashboard and verify all tabs work**

Open `docs/index.html` in browser. Check:
1. "Op Coverage" tab appears in nav
2. Clicking it shows the op coverage view
3. Summary boxes show correct counts
4. All 11 categories render as accordion sections
5. Clicking a category expands it to show the table
6. AMD columns (red header) and NV columns (green header) are visually separated
7. Checkmarks (green) and dashes (gray) render correctly
8. Other tabs (Projects, Test Parity, Activity, Trends) still work

- [ ] **Step 2: Verify JSON data accuracy**

Run: `python3 -c "import json; d=json.load(open('docs/_data/op-coverage.json')); print(sum(len(c['operators']) for c in d['categories']), 'operators across', len(d['categories']), 'categories')"`
Expected: `~120 operators across 11 categories`

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: op-coverage final adjustments"
```
