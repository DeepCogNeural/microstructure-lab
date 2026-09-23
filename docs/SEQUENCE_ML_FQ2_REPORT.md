# FQ2 formal GPU training-scale result

Date: 2026-09-23. This is a retrospective study on already exposed WSELOB-2017 periods, not independent confirmation. The original 20k/15-epoch Q2/Q3 and Q6 package remain preserved as pilot/superseded for the main analysis.

## Frozen comparison and denominator

The pre-fit protocol is `configs/sequence_ml_fq2_v1.json` (SHA-256 `7f8015ac6161f306b0b3633dac1cab97a021a02aa85859973dfab861775ab669`) and `docs/SEQUENCE_ML_FQ2_PROTOCOL.md`. Scientific runner commit `0da90c97a753a09f94c7b30724a6e76bf992e9a6`; cache manifest SHA-256 `6b426a633bda5d1d767a6346f5838a9df4cc1df2e0f0589b88ae27c56ba7988d`. Five stocks were each fitted at 50k, 100k and 200k Jan–Mar training endpoints. Within each stock/size, B1 history XGBoost and all three S0 GRU seeds used identical endpoint identities. All 15 runs reported the target training count, source/config hashes and row identities.

April was dev; June, September and November were retrospective evaluation. Every size and arm scored the same 210,290 April rows and 625,118 historical rows, yielding 90 and 315 complete stock/day IC cells respectively. No planned cell was undefined. The paired statistic is equal-stock/date Spearman IC difference, S0 three-seed mean minus same-size B1, with a five-day date-block bootstrap conditional on these fitted models and exposed periods.

| Training endpoints per stock | April B1 IC | April S0 seed-mean IC | Historical B1 IC | Historical S0 seed-mean IC | Paired ΔIC, 95% date-block interval |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50,000 | 0.276197 | 0.280253 | 0.279559 | 0.285223 | +0.005664 [0.003888, 0.007231] |
| 100,000 | 0.281019 | 0.283558 | 0.285240 | 0.291252 | +0.006012 [0.004160, 0.007916] |
| 200,000 | 0.282900 | 0.289596 | 0.286437 | 0.297506 | +0.011069 [0.008850, 0.013381] |

The 200k level was designated for FQ3 before these outcomes and is carried forward regardless of gain. At 200k, GRU seed 7/17/29 paired ΔICs were +0.012405/+0.009880/+0.010921. Seed-mean month differences were June +0.013243, September +0.007209, November +0.012755. Stock differences were KGHM +0.005921, PEKAO +0.013948, PKNORLEN **−0.001384**, PKOBP +0.013286, PZU +0.023573; the negative stock is retained. The leave-one-stock-out aggregate difference stayed positive for each omitted stock, as recorded in `fq2_summary.json`. At 100k PKNORLEN was more negative, and seed 29's September month was −0.000354; the ladder is not uniformly positive in every stratum. The 20k pilot is a reference with different optimization budget, not a pooled level or clean causal scaling point.

## Optimization and cost

The one-layer hidden-64 GRU retained its frozen optimizer, features, h20 original-event target and context 32; max epochs increased to 60 with patience 8. Across 15 stock/seed fits at each size, epoch ranges were 15–27 (50k), 18–26 (100k), 15–23 (200k); best-epoch ranges were 7–19, 10–18 and 7–15 respectively. **Zero of 45** formal GRU fits had their best checkpoint at epoch 60 or were flagged training-limited. Full learning curves and each model/prediction hash are in the per-stock receipts. This resolves the pilot's capped-training concern under the stated stopping diagnostic; it does not establish optimal architecture or global optimizer convergence.

Fifteen one-GPU task allocations totaled **0.9567 allocated GPU-hours** from scheduler start-to-completion timestamps; summed task process wall time was 3,391.6 seconds and synchronized GRU fit/inference device-occupancy sections totaled 3,056.8 seconds. One earliest completed task has a completion marker and aggregate hash but lacks an explicit exit-code line in its original wrapper; the other 14 have explicit zero exit codes. All 15 public reports and zero-byte stderr logs were verified. Peak process RSS across tasks was 1.76 GiB; peak framework allocated GPU memory was 133.9 MB. These are task/process measurements, not GPU utilization or hardware capacity. The infrastructure-neutral allocation receipt is `results/sequence_ml_fq2_v1/fq2_gpu_allocation.json`; private scheduler logs remain outside Git. One pre-fit runtime repair installed CUDA PyTorch in an isolated task environment after a synthetic GPU smoke test. No formal failed attempt or sample-size reduction occurred.

## Interpretation and next step

Within this fixed, retrospective protocol, the 200k GRU advantage is larger than the 50k and 100k points and no GRU fit is training-limited by the frozen diagnostic. This remains conditional on one historical source, five stocks, repeated exposure of the evaluation months and the chosen train sampling rule. Row overlap and model selection history prevent an unseen-generalization claim; the confidence interval only describes date variation conditional on these fits. No actual execution profit follows from IC.

Proceed to the already frozen FQ3 200k B1/S0 robustness and fixed visible-crossing protocol, then re-evaluate the Transformer gate. Do not edit résumé/PDF automatically. The strict machine aggregate `results/sequence_ml_fq2_v1/fq2_summary.json` (SHA-256 `1d2ae71efe63f41055c2767788d7c6fd5548ba11bcac0967f7fd80b7d366e180`) preserves every score cell and receipt hash. Public run JSONs remove the private GPU model-name field; each records the SHA-256 of its unredacted private original. Raw licensed data, models, row predictions and scheduler logs are outside Git.
