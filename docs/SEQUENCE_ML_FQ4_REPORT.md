# Formal FQ4 conditional Transformer result

Status: **COMPLETE, RETROSPECTIVE ONLY**. The FQ4 gate receipt passed all seven frozen conditions on formal FQ2 200k and complete FQ3. The unique S1 protocol/model/runner was committed before any fit; one configuration, three seeds 7/17/29 and five per-stock CUDA tasks were run. S1, B1 and S0 used exactly the same 200,000 training endpoint identities per stock, five features, 32 causal states, original-event h20 labels and dev/evaluation rows. No June/September/November outcome selected a configuration. The FQ4 runner used original FQ2 receipts; the public FQ2 copies redact only `gpu_device_name` and bind each original SHA-256 in `private_raw_receipt_sha256`. The strict aggregator checks this mapping and identical endpoint/scoring identities.

## Full-denominator comparison

All five tasks completed; April dev had **90 stock/day cells and 210,290 rows per arm**. The previously exposed June/September/November evaluation had **315 cells and 625,118 rows per arm**. Undefined IC cells: dev **0**, evaluation **0**. S0 and S1 three-seed means here are arithmetic means of seed-specific cell ICs, not IC of averaged predictions.

| Model | April dev equal-cell IC | Retrospective equal-cell IC |
|---|---:|---:|
| B1 history XGBoost | 0.282900 | 0.286437 |
| S0 history GRU, three-seed mean | 0.289596 | 0.297506 |
| S1 small Transformer, three-seed mean | 0.286109 | 0.287719 |

S1 minus S0 paired IC: **-0.009788**, five-day date-block 95% interval **[-0.011398, -0.008567]**. S1 minus B1: **+0.001281**, interval **[-0.000243, +0.002475]**. These are conditional on fitted models and all-exposed 2017 dates, not independent confirmation.

| S1 seed | Historical IC | Paired S1 seed minus S0 three-seed mean IC |
|---|---:|---:|
| 7 | 0.287523 | -0.009984 |
| 17 | 0.288485 | -0.009022 |
| 29 | 0.287149 | -0.010357 |

| Month | S1−S0 IC | S1−B1 IC |
|---|---:|---:|
| 2017-06 | -0.008251 | +0.004991 |
| 2017-09 | -0.009744 | -0.002535 |
| 2017-11 | -0.011367 | +0.001388 |

| Stock | S1−S0 IC | S1−B1 IC |
|---|---:|---:|
| KGHM | -0.006297 | -0.000375 |
| PEKAO | -0.012866 | +0.001082 |
| PKNORLEN | -0.002575 | -0.003958 |
| PKOBP | -0.008288 | +0.004998 |
| PZU | -0.018912 | +0.004661 |

All negative, null and heterogeneous rows above are retained; no single selected subgroup replaces the 315-cell primary contrast.

## Training, cost, and limits

**0/15** S1 seed fits had best April checkpoint at the 60-epoch cap. Per-seed learning curves, model hashes, training/inference times, peak GPU allocation and private-prediction hashes are in the five public stock receipts; model weights and row predictions remain private. Allocated GPU time was **1.9261 hours** for five single-GPU tasks, with **5/5** explicit zero exits and **0** nonempty stderr logs. Summed task wall time was 6918.4 seconds; synchronized model fit/inference device occupancy was 6834.0 seconds. Allocation wall and device occupancy are not SM utilization.

The FQ3 fixed visible-crossing rule was negative for both B1 and S0, and FQ4 did not invent a Transformer trading policy. No fees, actual fills, queue, impact or inventory are measured here. The Q5 independent-data gate remains pending. Any claim of a durable architecture gain or resume/PDF upgrade requires separate review and a qualified new cohort.
