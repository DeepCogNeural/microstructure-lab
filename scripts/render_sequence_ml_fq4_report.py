"""Render the conditional formal Transformer result without manual number edits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path,
                    default=Path("results/sequence_ml_fq4_v1/fq4_summary.json"))
    ap.add_argument("--allocation", type=Path,
                    default=Path("results/sequence_ml_fq4_v1/fq4_gpu_allocation.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("docs/SEQUENCE_ML_FQ4_REPORT.md"))
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("preserve existing FQ4 report")
    q = json.loads(args.summary.read_text())
    a = json.loads(args.allocation.read_text())
    dev, ev = q["dev"]["full_denominator_result"], q["evaluation"]["full_denominator_result"]
    if dev is None or ev is None or q["evaluation"]["cells_per_arm"] != 315 or a["task_count"] != 5:
        raise ValueError("formal FQ4 full denominator incomplete")
    b1 = ev["mean_ic"]["B1_history_xgboost"]
    s0, s1 = ev["S0_seed_mean_ic"], ev["S1_seed_mean_ic"]
    d0, d1 = ev["S1_seed_mean_vs_B1"], ev["S1_seed_mean_vs_S0_seed_mean"]
    dev_b1, dev_s0, dev_s1 = dev["mean_ic"]["B1_history_xgboost"], dev["S0_seed_mean_ic"], dev["S1_seed_mean_ic"]
    stock_lines = "\n".join(f"| {s} | {d1['stock_delta_ic'][s]:+.6f} | {d0['stock_delta_ic'][s]:+.6f} |"
                            for s in q["symbols"])
    month_lines = "\n".join(f"| {m} | {d1['month_delta_ic'][m]:+.6f} | {d0['month_delta_ic'][m]:+.6f} |"
                            for m in sorted(d1["month_delta_ic"]))
    seed_lines = "\n".join(f"| {s} | {ev['mean_ic'][f'S1_history_transformer_seed{s}']:.6f} | "
                           f"{ev['S1_each_seed_vs_S0_seed_mean'][str(s)]['mean_delta_ic']:+.6f} |"
                           for s in (7, 17, 29))
    limits = sum(v for arms in q["training_limited"].values() for v in arms.values())
    text = f"""# Formal FQ4 conditional Transformer result

Status: **COMPLETE, RETROSPECTIVE ONLY**. The FQ4 gate receipt passed all seven frozen conditions on formal FQ2 200k and complete FQ3. The unique S1 protocol/model/runner was committed before any fit; one configuration, three seeds 7/17/29 and five per-stock CUDA tasks were run. S1, B1 and S0 used exactly the same 200,000 training endpoint identities per stock, five features, 32 causal states, original-event h20 labels and dev/evaluation rows. No June/September/November outcome selected a configuration. The FQ4 runner used original FQ2 receipts; the public FQ2 copies redact only `gpu_device_name` and bind each original SHA-256 in `private_raw_receipt_sha256`. The strict aggregator checks this mapping and identical endpoint/scoring identities.

## Full-denominator comparison

All five tasks completed; April dev had **{q['dev']['cells_per_arm']} stock/day cells and {q['dev']['rows_per_arm']:,} rows per arm**. The previously exposed June/September/November evaluation had **{q['evaluation']['cells_per_arm']} cells and {q['evaluation']['rows_per_arm']:,} rows per arm**. Undefined IC cells: dev **{len(q['dev']['undefined_cells'])}**, evaluation **{len(q['evaluation']['undefined_cells'])}**. S0 and S1 three-seed means here are arithmetic means of seed-specific cell ICs, not IC of averaged predictions.

| Model | April dev equal-cell IC | Retrospective equal-cell IC |
|---|---:|---:|
| B1 history XGBoost | {dev_b1:.6f} | {b1:.6f} |
| S0 history GRU, three-seed mean | {dev_s0:.6f} | {s0:.6f} |
| S1 small Transformer, three-seed mean | {dev_s1:.6f} | {s1:.6f} |

S1 minus S0 paired IC: **{d1['mean_delta_ic']:+.6f}**, five-day date-block 95% interval **[{d1['ci95_date_block5'][0]:+.6f}, {d1['ci95_date_block5'][1]:+.6f}]**. S1 minus B1: **{d0['mean_delta_ic']:+.6f}**, interval **[{d0['ci95_date_block5'][0]:+.6f}, {d0['ci95_date_block5'][1]:+.6f}]**. These are conditional on fitted models and all-exposed 2017 dates, not independent confirmation.

| S1 seed | Historical IC | Paired S1 seed minus S0 three-seed mean IC |
|---|---:|---:|
{seed_lines}

| Month | S1−S0 IC | S1−B1 IC |
|---|---:|---:|
{month_lines}

| Stock | S1−S0 IC | S1−B1 IC |
|---|---:|---:|
{stock_lines}

All negative, null and heterogeneous rows above are retained; no single selected subgroup replaces the 315-cell primary contrast.

## Training, cost, and limits

**{limits}/15** S1 seed fits had best April checkpoint at the 60-epoch cap. Per-seed learning curves, model hashes, training/inference times, peak GPU allocation and private-prediction hashes are in the five public stock receipts; model weights and row predictions remain private. Allocated GPU time was **{a['allocated_gpu_hours']:.4f} hours** for five single-GPU tasks, with **{a['explicit_zero_exit_count']}/5** explicit zero exits and **{a['nonempty_stderr_count']}** nonempty stderr logs. Summed task wall time was {q['task_wall_seconds']:.1f} seconds; synchronized model fit/inference device occupancy was {q['gpu_device_occupancy_seconds']:.1f} seconds. Allocation wall and device occupancy are not SM utilization.

The FQ3 fixed visible-crossing rule was negative for both B1 and S0, and FQ4 did not invent a Transformer trading policy. No fees, actual fills, queue, impact or inventory are measured here. The Q5 independent-data gate remains pending. Any claim of a durable architecture gain or resume/PDF upgrade requires separate review and a qualified new cohort.
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(json.dumps({"report": str(args.out), "characters": len(text)}))


if __name__ == "__main__":
    main()
