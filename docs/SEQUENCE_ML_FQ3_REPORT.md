# Formal FQ3: bounded retrospective robustness and visible crossing

Status: **COMPLETE, RETROSPECTIVE ONLY**. The 2017 periods were previously exposed. This is the formal 200k-endpoint follow-up to FQ2; the earlier 20k/15-epoch Q3 remains a pilot.

## Frozen comparison and provenance

- Source: WSELOB-2017 V1; verified feature-cache manifest SHA-256 `6b426a633bda5d1d767a6346f5838a9df4cc1df2e0f0589b88ae27c56ba7988d`.
- Formal FQ2 fixed models: B1 history XGBoost and one-layer history GRU, seeds 7/17/29, trained on the same 200,000 Jan–Mar endpoints per stock. FQ2 summary is `results/sequence_ml_fq2_v1/fq2_summary.json`.
- FQ3 protocol: `configs/sequence_ml_fq3_v1.json`, SHA-256 `75b3d9466646c57f4e090af6f840594cf9da0cb672f9332608a72834385fe8d0`, frozen before fitting. Runner source commit `f74034ecf763234675171f78bb1257147a361504`.
- Fifteen update fits: five stocks × June/September/November, each with 200,000 pre-evaluation training endpoints per stock. The frozen past-only month windows, April-style prior-month dev, B1 and three GRU seeds are recorded in the config. Updated-versus-fixed scores use exactly paired original-event rows and labels. Five separate diagnostics use the fixed FQ2 predictions.
- Full public input-receipt hashes, per-day cells, learning curves, model hashes, and private-prediction hashes are recorded in `results/sequence_ml_fq3_v1/`. Raw data, row predictions, weights, and scheduler logs stay private.

## Full-denominator results

All 15 update fits and five diagnostics completed. There are 63 historical dates × five stocks = 315 stock/day cells per comparison and 625,118 common original-event scoring/crossing opportunities. No declared time, state, or primary execution cell was undefined. No updated GRU seed was training-limited at the 60-epoch cap.

| Retrospective month | B1 updated minus fixed IC | GRU seed 7 | GRU seed 17 | GRU seed 29 |
|---|---:|---:|---:|---:|
| June | +0.001256 | +0.000907 | +0.002749 | +0.003541 |
| September | +0.000736 | +0.004304 | +0.006081 | +0.005724 |
| November | +0.007240 | +0.004834 | +0.009339 | +0.006994 |

These are descriptive changes from fixed Jan–Mar fits to later frozen-rule refits. More recent training information and calendar conditions change together, so the table is not a causal decay estimate or independent confirmation.

The sole predeclared decision-time activity split uses the elapsed time inside the causal 32-event window and a per-stock training median. On 297,722 high-activity rows, fixed B1 IC was 0.257955 and IC of the mean of three GRU predictions was 0.278459 (paired +0.020503). On 327,396 low-activity rows, the corresponding values were 0.308703 and 0.321486 (+0.012782). Each slice has 315/315 defined stock/day cells. Here the GRU statistic scores averaged predictions; FQ2's primary comparison averages seed-specific ICs, which is a different estimand.

## Fixed visible crossing rule

Decision is at original event *t*; a prediction with strict absolute value above 1 bp buys at the visible ask or sells at the visible bid, then exits at the opposite visible quote at original event *t*+20 in the same segment. The reported markout is for one share, zero delay, with no fees, impact, inventory, actual fills, or queue model.

| Fixed model | Selected / 625,118 | Coverage | Equal stock/day crossed bp | Pooled selected bp, descriptive |
|---|---:|---:|---:|---:|
| B1 history XGBoost | 34,284 | 5.484% | -6.949 | -6.783 |
| GRU three-seed prediction mean | 71,184 | 11.387% | -6.700 | -6.878 |

Both fixed rules are negative. Coverage and selected event identities differ. On the 22,784 opportunities selected by both, pooled visible markouts were B1 -5.939 bp and GRU -5.914 bp; equal stock/day means were -6.088 and -6.047 bp. None of these values is realized PnL or evidence of a profitable strategy.

## Compute, checks, and limits

All 20 remote tasks had an explicit zero exit and empty stderr. The 15 GPU updates consumed 1.3911 allocated GPU-hours; five CPU diagnostics consumed a separate allocation. Sum of update task wall times was 4,959.66 seconds, and sum of reported GPU device occupancy was 4,604.77 seconds; neither is a utilization percentage. B1 fit time summed 153.59 seconds; the three GRU seeds summed 1,586.90 / 1,440.10 / 1,561.12 seconds for seeds 7/17/29. The public infrastructure-neutral allocation receipt records task-level durations without host or scheduler identifiers.

The strict aggregator rejects missing update/diagnostic files, unmatched score rows, duplicate cells, and incomplete denominators. This report preserves the earlier pilot results, negative crossing observations, retrospective exposure labels, and the lack of qualified independent confirmation. FQ4 must run the frozen Transformer gate on formal FQ2 and FQ3; no Transformer result is implied by FQ3 alone.
