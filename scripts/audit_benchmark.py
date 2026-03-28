#!/usr/bin/env python3
"""
Benchmark Audit Tool — Systematic validation of operator benchmark results.

7-step audit methodology learned from MI355X vs B300 dashboard development.
Run this before publishing any new benchmark data.

Usage:
    python3 audit_benchmark.py --data docs/_data/op-perf.json
    python3 audit_benchmark.py --data results.json --threshold 5.0
"""
import argparse, json, math, sys
from collections import defaultdict

def step1_ratio_sanity(data, threshold_high=5.0, threshold_low=0.2):
    """Step 1: Flag any ratio >threshold_high or <threshold_low as likely bugs."""
    print("\n=== Step 1: Ratio Sanity Check ===")
    issues = []
    for cat in data.get("categories", []):
        for r in cat.get("results", []):
            a = r.get("amd_tflops") or r.get("amd_bw") or 0
            n = r.get("nv_tflops") or r.get("nv_bw") or 0
            if a > 0 and n > 0:
                ratio = a / n
                if ratio > threshold_high or ratio < threshold_low:
                    issues.append({
                        "cat": cat["id"], "model": r.get("model",""),
                        "label": r.get("label",""), "M": r.get("M",0),
                        "ratio": ratio, "amd": a, "nv": n,
                    })
    
    if issues:
        print(f"  FOUND {len(issues)} suspicious ratios (>{threshold_high}x or <{threshold_low}x):")
        for i in sorted(issues, key=lambda x: x["ratio"])[:10]:
            print(f"    {i['cat']:<20} {i['model']:<20} M={i['M']:<5} ratio={i['ratio']:.2f}x  AMD={i['amd']:.1f} NV={i['nv']:.1f}")
        if len(issues) > 10:
            print(f"    ... and {len(issues)-10} more")
    else:
        print(f"  OK — no ratios outside [{threshold_low}x, {threshold_high}x]")
    return issues

def step2_check_versions(data):
    """Step 2: Verify software stack versions are documented."""
    print("\n=== Step 2: Software Stack Verification ===")
    warnings = []
    
    # Check if data has version info
    if "gpus" not in data:
        warnings.append("No GPU info in data — add 'gpus' field")
    if "lastUpdated" not in data:
        warnings.append("No lastUpdated timestamp")
    
    print("  Known issues to check:")
    print("    - B300 cuDNN: must be 9.19+ (9.10 broken for Conv2D on Blackwell)")
    print("    - B300 PyTorch: must be 2.11+ (bundles cuDNN 9.19)")
    print("    - MI355X AITER: use pensun-aiter-bench container (full CK, not CK-free)")
    
    for w in warnings:
        print(f"  WARNING: {w}")
    return warnings

def step3_algorithm_mismatch(data):
    """Step 3: Check for algorithm class mismatches."""
    print("\n=== Step 3: Algorithm Class Check ===")
    issues = []
    
    for cat in data.get("categories", []):
        for r in cat.get("results", []):
            # Check if backend info is present
            backend = r.get("amd_backend", "")
            
            # Flag decode attention without paged attention
            if cat["id"] == "attention" and r.get("mode") == "decode":
                if "paged" not in str(r.get("op","")).lower() and "pa" not in str(r.get("label","")).lower():
                    a = r.get("amd_tflops", 0)
                    n = r.get("nv_tflops", 0)
                    if a > 0 and n > 0 and a/n > 3:
                        issues.append(f"Decode attention {r.get('model','')} ratio={a/n:.1f}x — check if both sides use paged attention")
    
    if issues:
        print(f"  FOUND {len(issues)} potential mismatches:")
        for i in issues[:5]:
            print(f"    {i}")
    else:
        print("  OK — no obvious algorithm mismatches detected")
    return issues

def step4_backend_failures(data):
    """Step 4: Check for configs where one side might be using fallback kernel."""
    print("\n=== Step 4: Backend Failure Detection ===")
    
    known_cudnn_issues = {
        72: "cuDNN doesn't support head_dim=72 (PixArt-Sigma)",
        112: "cuDNN doesn't support head_dim=112 (Kimi-K2.5)",
    }
    
    issues = []
    for cat in data.get("categories", []):
        if "attention" not in cat["id"]: continue
        for r in cat.get("results", []):
            hd = r.get("head_dim", 0)
            hq = r.get("hq", 0)
            if hd in known_cudnn_issues:
                issues.append(f"{r.get('model','')} head_dim={hd}: {known_cudnn_issues[hd]}")
            if hq == 20:
                issues.append(f"{r.get('model','')} H=20: cuDNN segfaults on Blackwell for H=20")
    
    if issues:
        seen = set()
        print(f"  Known cuDNN limitations affecting {len(set(issues))} configs:")
        for i in sorted(set(issues)):
            print(f"    {i}")
    else:
        print("  OK — no known backend failure patterns")
    return issues

def step5_geomean_weighting(data):
    """Step 5: Check if per-model geomean uses inference weights (not equal-weight)."""
    print("\n=== Step 5: Geomean Weighting Check ===")
    
    per_model = data.get("summary", {}).get("per_model", [])
    if not per_model:
        print("  WARNING: No per_model data in summary")
        return []
    
    has_inference = any("geomean" in m and "geomean_equal" in m for m in per_model)
    if has_inference:
        # Check for large divergences
        divergent = []
        for m in per_model:
            inf = m.get("geomean", 0)
            eq = m.get("geomean_equal", 0)
            if inf > 0 and eq > 0 and abs(inf - eq) / eq > 0.2:
                divergent.append(f"{m['model']}: inf={inf:.3f}x eq={eq:.3f}x ({(inf/eq-1)*100:+.0f}%)")
        
        print(f"  OK — inference-weighted geomean present")
        if divergent:
            print(f"  {len(divergent)} models with >20% divergence between equal/inference weight:")
            for d in divergent[:5]:
                print(f"    {d}")
    else:
        print("  WARNING: Only equal-weight geomean found — add inference weights!")
    return []

def step6_config_completeness(data):
    """Step 6: Check for models with incomplete operator coverage."""
    print("\n=== Step 6: Model Completeness Check ===")
    
    model_cats = defaultdict(set)
    for cat in data.get("categories", []):
        for r in cat.get("results", []):
            m = r.get("model", "")
            if m:
                model_cats[m].add(cat["id"])
    
    required_llm = {"gemm", "attention"}
    incomplete = []
    for m, cats in model_cats.items():
        if len(cats) == 1:
            incomplete.append(f"{m}: only has {cats}")
    
    if incomplete:
        print(f"  {len(incomplete)} models with single-category data:")
        for i in incomplete[:5]:
            print(f"    {i}")
    else:
        print(f"  OK — all {len(model_cats)} models have multi-category coverage")
    return incomplete

def main():
    parser = argparse.ArgumentParser(description="Benchmark Audit Tool")
    parser.add_argument("--data", required=True, help="Path to op-perf.json")
    parser.add_argument("--threshold", type=float, default=5.0, help="Ratio threshold for sanity check")
    args = parser.parse_args()
    
    with open(args.data) as f:
        data = json.load(f)
    
    total = sum(len(c.get("results",[])) for c in data.get("categories",[]))
    cats = len(data.get("categories",[]))
    models = len(data.get("summary",{}).get("per_model",[]))
    
    print("=" * 60)
    print(f"BENCHMARK AUDIT: {total} configs, {cats} categories, {models} models")
    print("=" * 60)
    
    all_issues = []
    all_issues.extend(step1_ratio_sanity(data, args.threshold))
    all_issues.extend(step2_check_versions(data))
    all_issues.extend(step3_algorithm_mismatch(data))
    all_issues.extend(step4_backend_failures(data))
    step5_geomean_weighting(data)
    all_issues.extend(step6_config_completeness(data))
    
    print("\n" + "=" * 60)
    if all_issues:
        print(f"AUDIT RESULT: {len(all_issues)} issues found — review before publishing")
    else:
        print("AUDIT RESULT: PASS — no issues found")
    print("=" * 60)
    
    return 1 if all_issues else 0

if __name__ == "__main__":
    sys.exit(main())
