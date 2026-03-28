# Op Coverage Dashboard — Design Spec

## Overview

Add an "Op Coverage" tab to the existing project-dashboard that displays a systematic comparison of AI operator coverage across AMD and NV ecosystems. The view focuses on functional coverage (not performance), organized as a layered accordion with per-category comparison tables.

## Goals

- Systematically categorize all operators from Aiter, Mori, and comparable NV-side projects
- Provide an AMD vs NV ecosystem comparison matrix per category
- Integrate into the existing project-dashboard as a new tab
- Data is hand-maintained via a single JSON file

## Non-Goals

- Performance benchmarking
- Automated operator detection/scanning (future enhancement)
- Search/filter functionality (keep simple, add later if needed)

---

## Architecture

### Data Source

Single JSON file: `docs/_data/op-coverage.json`

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
        {
          "name": "MHA Prefill (FP16/BF16)",
          "coverage": {
            "Aiter": true,
            "FlashInfer": true,
            "FlashMLA": false
          }
        }
      ]
    }
  ]
}
```

Coverage values: `true` (supported), `false` (not supported), `"partial"` (partial support).

Each category has its own `amd_projects` and `nv_projects` lists — column count varies by category.

### UI Components

**Tab**: New "Op Coverage" button in `#tab-bar`, new `#tab-op-coverage` panel.

**Summary bar** (top of panel):
- Total operator count
- Per-category coverage rate badges (colored)

**Accordion sections** (11 total):
- **Header**: Category name + op count + AMD/NV project tags + coverage badges
- **Body** (collapsed by default): Comparison table
  - Columns grouped: AMD side | NV side (visual separator)
  - Cells: checkmark / dash / wrench icon
  - Row hover highlight

### File Changes

| File | Change |
|------|--------|
| `docs/index.html` | Add tab button + panel div |
| `docs/assets/js/dashboard.js` | Add op-coverage rendering logic |
| `docs/assets/css/dashboard.css` | Add accordion + coverage table styles |
| `docs/_data/op-coverage.json` | New file — all operator data |

No new JS/CSS files — extend existing ones to maintain consistency.

---

## Operator Categories & Comparison Columns

### 1. Attention
AMD: Aiter | NV: FlashInfer, FlashMLA

| Operator | Aiter | FlashInfer | FlashMLA |
|----------|-------|------------|----------|
| MHA Prefill (FP16/BF16) | true | true | false |
| MHA Prefill (FP8) | true | true | false |
| MHA Decode | true | true | false |
| MHA Varlen | true | true | false |
| MLA Decode | true | true | true |
| MLA Prefill | true | false | false |
| Paged Attention Decode | true | true | false |
| Paged Attention Prefill | true | true | false |
| Paged Attention Ragged | true | false | false |
| Cascade Attention | false | true | false |
| Sparse MLA | true | false | false |
| SAGE Attention (MXFP4) | true | false | false |
| HSTU Attention | true | false | false |
| POD Attention | true | false | false |
| Lean Attention | true | false | false |
| Unified Attention | true | false | false |

### 2. GEMM
AMD: Aiter, hipBLASLt | NV: cuBLASLt

| Operator | Aiter | hipBLASLt | cuBLASLt |
|----------|-------|-----------|----------|
| GEMM FP16/BF16 | true | true | true |
| GEMM FP8 (per-tensor) | true | true | true |
| GEMM FP8 blockscale | true | true | true |
| GEMM INT8 | true | true | true |
| GEMM FP4/MXFP4 | true | true | true |
| GEMM A16W8 blockscale | true | false | false |
| GEMM A16WFP4 | true | false | false |
| GEMM A8WFP4 | true | false | false |
| Batched GEMM BF16 | true | true | true |
| Batched GEMM FP8 | true | true | true |
| Batched GEMM FP4 | true | false | false |
| Grouped GEMM (MoE) | true | true | true |
| GEMM + Bias fusion | false | true | true |
| GEMM + ReLU/GELU/SiLU fusion | false | true | true |
| DeepGEMM | true | false | false |
| Fused GEMM (multi-stage) | true | false | false |
| Feed-Forward Fused | true | false | false |
| B-preshuffle GEMM | true | false | false |

### 3. MoE
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| Fused MoE BF16 | true | true |
| Fused MoE FP8 | true | true |
| Fused MoE FP8 blockscale | true | false |
| Fused MoE MXFP4 | true | true |
| Fused MoE INT8 SmoothQuant | true | false |
| Fused MoE A8W4 | true | false |
| Fused MoE A4W4 | true | false |
| MoE + SiLU fused | true | false |
| MoE + GELU fused | true | false |
| MoE 2-stage (CK/CKTile) | true | false |
| TopK Softmax | true | false |
| TopK Sigmoid | true | false |
| Biased Grouped TopK | true | false |
| MoE Sorting | true | false |
| MoE Align Block Size | true | true |
| MoE Routing (bitmatrix) | true | false |

### 4. Normalization
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| RMSNorm | true | true |
| RMSNorm + Add (fused) | true | true |
| RMSNorm + Quant (fused) | true | false |
| RMSNorm + Add + Quant (fused) | true | false |
| RMSNorm + SmoothQuant | true | false |
| LayerNorm | true | true |
| LayerNorm + Add | true | false |
| LayerNorm + SmoothQuant | true | false |
| GroupNorm | true | false |

### 5. Quantization
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| Static per-tensor quant | true | false |
| Dynamic per-tensor quant | true | true |
| Dynamic per-token quant | true | true |
| Per-group FP4 quant | true | true |
| SmoothQuant | true | false |
| MXFP4 quant | true | false |
| Fused FP8 quant | true | false |

### 6. Positional Encoding
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| RoPE (NEOX/GPT-J) | true | true |
| RoPE cached (cos/sin) | true | true |
| RoPE 2-channel (Q+K) | true | false |
| RoPE THD (varlen) | true | false |
| RoPE 2D (vision) | true | false |
| RoPE + positions + offsets | true | true |
| Batched RoPE | true | false |
| LLaMA 3.1 RoPE | false | true |

### 7. Sampling
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| Greedy sampling | true | false |
| Random sampling | true | false |
| Top-K sampling | true | true |
| Top-P sampling | true | true |
| Top-K + Top-P joint | true | true |
| Min-P sampling | false | true |
| Speculative sampling | false | true |

### 8. Elementwise / Activation
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| SiLU and mul | true | true |
| GELU and mul | true | false |
| GELU-Tanh and mul | true | false |
| Scaled SiLU and mul | true | false |
| add / sub / mul / div | true | false |
| sigmoid / tanh | true | false |

### 9. KV Cache Management
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| reshape_and_cache | true | true |
| reshape_and_cache FP8/INT8 | true | false |
| reshape_and_cache block quant | true | false |
| swap_blocks | true | false |
| copy_blocks | true | false |
| concat_and_cache MLA | true | false |
| Fused QK+RoPE+Cache+Quant | true | false |
| Paged KV append | false | true |

### 10. Communication
AMD: Aiter, Mori, RCCL | NV: DeepEP, NCCL

| Operator | Aiter | Mori | RCCL | DeepEP | NCCL |
|----------|-------|------|------|--------|------|
| AllReduce | true | false | true | false | true |
| AllReduce + RMSNorm (fused) | true | false | false | false | false |
| ReduceScatter | true | false | true | false | true |
| AllGather | true | false | true | false | true |
| AllToAll | false | false | true | false | true |
| Broadcast | false | false | true | false | true |
| Send / Recv | false | false | true | false | true |
| EP Dispatch (IntraNode) | true | true | false | true | false |
| EP Dispatch (InterNode) | true | true | false | true | false |
| EP Combine (IntraNode) | true | true | false | true | false |
| EP Combine (InterNode) | true | true | false | true | false |
| EP Low-Latency (LL) | false | true | false | true | false |
| RDMA Read/Write (P2P) | false | true | false | false | false |
| RDMA Batch IO | false | true | false | false | false |
| Shmem (symmetric memory) | false | true | false | false | false |
| ReduceScatter+RMSNorm+Quant+AllGather (fused) | true | false | false | false | false |

### 11. Other
AMD: Aiter | NV: FlashInfer

| Operator | Aiter | FlashInfer |
|----------|-------|------------|
| Causal Conv1D | true | false |
| Gated Delta Net (SSM) | true | false |
| Weight Shuffle/Preshuffle | true | false |
| Ragged Layout Transform | true | false |
| Softmax | true | false |

---

## Implementation Notes

- Extend existing `dashboard.js` with a new `renderOpCoverage()` function
- Reuse existing tab switching logic
- CSS: accordion uses `details/summary` HTML elements for simplicity (no JS needed for expand/collapse)
- Coverage stats computed dynamically from JSON data
- Color scheme: green (supported), gray (not supported), yellow (partial)
