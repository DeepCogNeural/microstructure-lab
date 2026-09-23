# PM1A terminal calibration — frozen before final scoring

Date: 2026-09-23. The public data source, market-grouped chronological split and primary feature/cadence list were frozen in PM0 (`docs/POLYMARKET_PM0_DATA_AUDIT.md`, `configs/polymarket_pm1a_v1.json`). PM1A model details are `configs/polymarket_pm1a_model_v1.json` (SHA-256 `6eedd161eecf81ad56294abf8541dca77af63ff26c926e6827abfd529b0a7cd3`). This document records the train/dev result and the one-time final procedure before final labels or scores are used.

## Opportunity and model contract

Use the Up token only. At fixed 30-second steps backward from scheduled market end, require at least 60 seconds to close, a latest captured book at or before decision with age at most 15 seconds, and eight distinct preceding captured books within 120 seconds. All eight must have valid two-sided, unlocked, uncrossed ladders. The snapshot has collector time, not exchange event time. Its feature time-to-close is measured at each capture; the separate age feature lets history models see staleness. No one-sided midpoint or fill is imputed. P0–P4 score identical eligible opportunities.

P0 is the current market midpoint probability. P1 is fixed logistic calibration of current logit midpoint and log time to close. P2 uses ten current-state features in a fixed 200-tree XGBoost classifier. P3 flattens the same eight-by-eleven history tensor used by a one-layer hidden-32 GRU P4; the eleventh feature is capture age. GRU seeds are 7/17/29, max 60 epochs, patience 8. Fit weights give each market equal total mass despite unequal snapshot counts. Primary scores first average log loss and Brier within market, then equally across markets; paired differences resample whole markets. Negative paired log-loss difference means the second model improves. No date-block interval is credible with only one dev date.

The frozen split contains train 431, dev 241, final 122 whole markets, with 11 purged at UTC boundaries. Causal eligibility left **405 train markets / 16,947 opportunities** and **236 dev markets / 8,749 opportunities**. Train and dev market IDs are disjoint. The 4-hour contracts contribute most opportunities (12,421 train; 5,824 dev), which is why scoring and fitting weight markets equally. The source and private input hashes are in `results/polymarket_pm1a_v1/train_dev_build_manifest.json`; private row arrays are not public.

## Dev result, final still closed

| Arm | Dev market-mean log loss | Dev market-mean Brier |
| --- | ---: | ---: |
| P0 raw midpoint | **0.498128** | **0.167035** |
| P1 calibrated midpoint/time | 0.498935 | 0.167587 |
| P2 current-state XGBoost | 0.510326 | 0.173008 |
| P3 history XGBoost | 0.509730 | 0.172058 |
| P4 GRU seed 7 | 0.501751 | 0.168829 |
| P4 GRU seed 17 | 0.503910 | 0.170478 |
| P4 GRU seed 29 | 0.501664 | 0.169175 |
| P4 three-seed probability mean | 0.501050 | 0.168880 |

Raw market price beat every fitted arm on dev. P4 seed-mean minus P3 paired market log loss was −0.008680, market-bootstrap 95% interval [−0.019208,+0.001589]. Relative to P0, the P4 seed-mean difference was **+0.002922** [−0.010909,+0.016715]: better than P3 but worse than raw price in point estimate, both uncertain. Preserve this simple-baseline win. The three GRU seeds stopped at epochs 13/20/15 with best epochs 5/12/7 and none flagged training-limited. The result is from one dev UTC day in a sampled four-day source, not a generalization claim.

The public aggregate is `results/polymarket_pm1a_v1/dev_result.json` (SHA-256 `c0a32cae9b3d4b11926e60eff98dbb2cbe057cc94d9e70b009bf690a871b9b42`). It contains all arm and negative results, per-model fit times and learning curves, model hashes and no row predictions. Fitted models, train/dev arrays and dev row predictions remain private.

## One-time final procedure

The code and model configuration must be pushed before opening the final block. The final evaluator `scripts/eval_polymarket_pm1a_final.py` verifies the frozen config, train/dev input hashes, dev report, fitted model hashes and disjoint market IDs. Build only the 122 final markets with the same source audit/split/eligibility code; then score all P0–P4 arms once, without changing features, hyperparameters, weights, threshold or primary P3–P4 comparison. Report P0 and every null/negative result. Cluster uncertainty by market, label the final as a partial one-day exploratory block, and do not call it independent confirmation of WSELOB or realized trading profit.
