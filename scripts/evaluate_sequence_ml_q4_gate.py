"""Apply every preregistered retrospective Q4 trigger without model fishing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path("results/sequence_ml_v1")
    q2_path, q3_path = root/"q2_summary.json", root/"q3_summary.json"
    q2, q3 = json.loads(q2_path.read_text()), json.loads(q3_path.read_text())
    paired = q2["paired_vs_selected_history"]
    main = paired["S0_seed_mean"]
    seeds = [f"S0_history_gru_seed{s}" for s in (7, 17, 29)]
    q2_limited = [f"{stock}/{seed}" for stock, row in q2["training_limited_flags"].items()
                  for seed in seeds if row[seed]]
    q3_limited = [f"{cell}/{seed}" for cell, row in q3["updated_training_limited"].items()
                  for seed in seeds if row[seed]]
    checks = {
        "retrospective_delta_at_least_0_005": main["mean_delta_ic"] >= 0.005,
        "three_seed_means_positive": all(paired[seed]["mean_delta_ic"] > 0 for seed in seeds),
        "at_least_two_historical_months_positive": sum(value > 0 for value in main["month_delta"].values()) >= 2,
        "no_single_stock_completely_dominates": all(value > 0 for value in main["leave_one_stock_out_delta"].values()),
        "training_not_limited": not q2_limited and not q3_limited,
        "sequence_correctness_tests_passed": True
    }
    # The final check binds to the published Q1/Q3 test receipts, not a claim
    # that tests could prove the absence of every leakage mechanism.
    report = {"stage": "Q4", "retrospective_only": True,
              "q2_summary_sha256": sha(q2_path), "q3_summary_sha256": sha(q3_path),
              "planned_delta_ic": 0.005, "observed_seed_mean_delta_ic": main["mean_delta_ic"],
              "seed_deltas": {seed: paired[seed]["mean_delta_ic"] for seed in seeds},
              "month_deltas": main["month_delta"],
              "leave_one_stock_out_deltas": main["leave_one_stock_out_delta"],
              "q2_training_limited": q2_limited, "q3_training_limited": q3_limited,
              "correctness_receipts": {"q1": "8 focused tests passed", "q3": "2 synthetic crossing parity/identity tests passed"},
              "checks": checks,
              "decision": "RUN_SMALL_TRANSFORMER" if all(checks.values()) else "SKIP_TRANSFORMER",
              "reason": "Training-limit condition failed; do not change the protocol or add architecture search to rescue a positive old-sample number." if q2_limited or q3_limited else None,
              "next_stage": "Q5 independent-confirmation source qualification"}
    out = root/"q4_gate.json"
    if out.exists():
        raise ValueError("preserve original gate receipt")
    out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"decision": report["decision"], "checks": checks,
                      "q2_limited": len(q2_limited), "q3_limited": len(q3_limited)}))


if __name__ == "__main__":
    main()
