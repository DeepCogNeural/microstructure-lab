# Final WSELOB sequence-ML research package

Status: **formal historical program complete; `PENDING_INDEPENDENT_CONFIRMATION`**. The current reviewer control requires WSE only. Polymarket waits for genuinely fresh chronological data. No résumé/PDF, LLM Track or Exp06 work is part of this package.

## Research answer

- FQ2: history-matched GRU improved retrospective h20 ranking versus history XGBoost as formal per-stock training grew from 50k to 200k endpoints.
- FQ4: the frozen context32 Transformer underperformed GRU (paired S1−S0 IC −0.009788). This negative result was retained without rescue tuning.
- Q8: 8/32/128-state sensitivity used one common context128-eligible endpoint cohort. April alone selected 128; historical S0−B1 IC was +0.021823. PKNORLEN's within-stock effect was −0.000997.
- Q10: five true four-source-stock → one-held-out-stock folds trained, normalized and selected context on source stocks alone. Historical S0−B1 IC was +0.026592 over 315 stock/day cells, conditional on already exposed stocks/dates. Source-April GRU context selection favors the neural arm.
- Q11: the unchanged strict >1 bp visible quote crossing with 0/1/5-message entry delays and fixed t+20 exit was negative for both finalists, in both within-stock and source-only predictions at all delays. At zero delay, equal stock/day crossed results were Q8 B1/S0 −7.019/−7.165 bp and Q10 B1/S0 −6.781/−7.354 bp. These are research quote diagnostics, not fills or PnL.

The [five-minute brief](SEQUENCE_ML_FINAL_RESEARCH_BRIEF.md) states the design and interpretation. Detailed stage reports: [FQ2](SEQUENCE_ML_FQ2_REPORT.md), [FQ3](SEQUENCE_ML_FQ3_REPORT.md), [FQ4](SEQUENCE_ML_FQ4_REPORT.md), [Q8](SEQUENCE_ML_Q8_REPORT.md), [Q10](SEQUENCE_ML_Q10_REPORT.md), [Q11](SEQUENCE_ML_Q11_REPORT.md). The prior 20k Q2/Q3/Q6 package remains an archived pilot, not final evidence.

## Reproducibility and cost

`results/sequence_ml_final_v1/figures/` contains four publication-ready figures: matched-history/context comparison; monthly fixed-versus-updated comparison; complete stock and preset activity-state decomposition; and ranking/visible-crossing cost plus coverage. `cost_table.csv` records 7.912 allocated GPU-hours across FQ2/FQ3/FQ4/Q8/Q10 and 1.264 allocated CPU core-hours for Q11, with the small FQ3 CPU diagnostic wall allocation separately identified. Allocation is not utilization.

From the scientific task branch and public aggregate receipts, `python3 scripts/recompute_sequence_ml_final.py --out /tmp/wse-recompute.json` reruns all six formal aggregators and requires byte-for-byte equality. `python3 scripts/render_sequence_ml_final_brief.py --out /tmp/wse-brief.md` and `python3 scripts/render_sequence_ml_final.py --out /tmp/wse-package` regenerate the brief, four figures and cost table. `python3 scripts/verify_sequence_ml_final.py --manifest-out /tmp/wse-scientific-manifest.json` independently verifies receipt/parent/source/model hashes and writes a fresh manifest. The committed `recomputation.json` records six byte-identical aggregate reruns; `scientific_manifest.json` inventories 65 run receipts, 215 model hashes, source/partition hashes and all output hashes. Original licensed WSE rows, row predictions, model weights and scheduler logs remain private.

## Claim boundary

All June/September/November observations and all five stocks were previously exposed to the research process. Date-block intervals condition on fitted models and historical dates. The Q5 source/access audit qualified zero genuinely new WSE original-event h20 final days. The supported claim is a reproducible **retrospective research method and result**, including the failed Transformer and negative visible execution. Independent generalization or profitable execution requires new qualified data and a separately frozen confirmation protocol. Résumé/PDF editing remains a separate reviewer decision.
