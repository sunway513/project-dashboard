# Primus-Turbo Evaluation for Operator Performance Dashboard

## Objective
Evaluated whether Primus-Turbo (v0.2.0) provides incremental operator performance gains that should be reflected in the MI355X vs B300 operator benchmark dashboard.

## Methodology
Ran Primus-Turbo's benchmark suite side-by-side with our current AITER baseline on the same MI355X hardware. Compared three operator categories: GEMM, FlashAttention, and Grouped GEMM (MoE).

## Results

### 1. BF16 GEMM: Turbo vs hipBLASLt
- **84 configs** across 7 models (Llama-2/3, Qwen2.5, Mistral)
- **GeoMean speedup: 0.998x** — within measurement noise
- Both use the same hipBLASLt backend via `torch.matmul`
- Range: 0.982x to 1.021x
- **Conclusion: No difference**

### 2. FlashAttention Forward: Turbo vs AITER CK FA
Ran identical configs on the same machine using causal-adjusted TFLOPS:

| Config | AITER CK FA | Primus Turbo | Ratio |
|---|---|---|---|
| Llama3-8B (B=1, S=4096, HQ=32) | 0.146ms | 0.149ms | 0.98x |
| Llama3-8B (B=4, S=4096, HQ=32) | 0.589ms | 0.581ms | 1.01x |
| DeepSeek MLA (B=1, S=4096, HQ=128) | 0.706ms | 0.707ms | 1.00x |
| Llama3-405B (B=1, S=8192, HQ=128) | 1.964ms | 1.971ms | 1.00x |
| Qwen3-Coder (B=1, S=4096, HQ=96) | 0.400ms | 0.421ms | 0.95x |

Source code inspection confirmed this is expected:
```python
# primus_turbo/pytorch/kernels/attention/attention_csrc_impl.py
from aiter.ops.mha import _flash_attn_forward   # Same AITER CK kernel

def attention_aiter_csrc_forward_impl(...):
    return _flash_attn_forward(q, k, v, ...)     # Direct passthrough
```

Primus-Turbo wraps AITER's `_flash_attn_forward` in a `torch.library.custom_op` for torch.compile compatibility. The forward kernel is identical. The `PRIMUS_TURBO_ATTN_V3_ATOMIC_FP32` flag only affects the backward pass (training).

- **Conclusion: Same kernel, no difference for inference**

### 3. Grouped GEMM (MoE): Turbo CK grouped_gemm vs AITER fused_moe_silu

Primus-Turbo's grouped GEMM showed 22x speedup over PyTorch baseline, but this is **not comparable** to AITER fused_moe_silu:

| Operation | Primus grouped_gemm | AITER fused_moe_silu |
|---|---|---|
| Token routing | Not included | Included |
| Expert dispatch/scatter | Pre-sorted input | Handles sorting |
| Matrix multiply | Yes | Yes |
| SiLU activation | Not included | Fused |
| Gate * Up multiply | Not included | Fused |
| Routing weight sum | Not included | Included |

AITER fused_moe_silu performs the complete MoE forward pass (routing + GEMM + activation + gating) in a single fused kernel. Primus grouped_gemm only does the batched matrix multiply portion. The 1.5-2.5x "gap" is accounted for by the additional operations AITER performs.

- **Conclusion: Not comparable — different scope of operations**

## Summary

| Operator | Primus-Turbo vs AITER | Incremental for Dashboard? |
|---|---|---|
| BF16 GEMM | 0.998x (identical) | No |
| FlashAttention fwd | 1.00x (same kernel) | No |
| Grouped GEMM | Not comparable | No |

## Recommendation
The dashboard should continue using AITER kernels directly. Primus-Turbo is a valuable integration layer for training workflows (torch.compile support, USP attention, backward pass optimizations), but its inference-relevant operators are pass-through wrappers on AITER with no additional optimization.

As the Primus-Turbo project evolves, particularly around FP8 attention and MoE optimizations, we should periodically re-evaluate for new capabilities that may benefit inference benchmarking.
