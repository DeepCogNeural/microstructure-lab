# Later-period confirmation protocol

Preregistered before outcome access on 2026-09-21. Audit: `e82a75de2ed02d8bf6f3f84fd602dc9b13ddcc81`. Scientific settings are in `configs/wselob_later_confirmation_v1.json`; existing definitions refer to source at that audit commit. This is a specification, not a runnable legacy monthly configuration. Implementation and reveal require subsequent review authorization.

## Evidence and questions

This is a **pre-registered later-period confirmation set**, not a cryptographically blinded or independently proven never-seen holdout. No contaminating scientific use was found; published tasks excluded these dates; operator attestation supports historical non-exposure; label-bearing prepared caches existed. Preserve this caveat in the final report.

The frozen questions are: (1) does short-horizon predictive ranking persist, with a modest XGBoost advantage over Linear; (2) does visible spread crossing still eliminate the apparent midpoint edge; (3) under conditional queue depletion, does signal strength retain a trade-off with fill probability and adverse selection after filling? Each finding may replicate, weaken, disappear or reverse. No favorable result is required.

## Dataset and training

Include the full Cartesian product of KGHM, PEKAO, PKNORLEN, PKOBP, PZU and 2017-12-27, 2017-12-28, 2017-12-29. All 15 remain together. **15 partitions = 5 symbols × 3 shared calendar dates, not 15 independent time periods.** Source filenames and full-file SHA256 values are frozen in the configuration, with the audit's partition inventory as provenance.

For each stock, horizon and model, train once on all eligible own-stock observations from 2017-01-01 through **2017-12-22 inclusive**, with at least 40 trading days. Freeze that fit across all three confirmation days. No cross-symbol pooling, daily refits, confirmation labels in training, subsampling of training rows, early stopping or parameter search. This deliberately replaces monthly expanding refits with historical research → frozen model → future confirmation period. Within-day labels must remain inside the training cutoff as well as the existing valid segment.

Use the existing five features, in order: `spread_bps`, `top_imbalance`, `depth_imbalance`, `ofi_l1_norm`, `microprice_minus_mid_bps`. Preserve existing replay/session/feature definitions: ten levels, 10:00 inclusive to 16:00 exclusive Warsaw time, exact original-message horizons, and rejection of invalid/gapped/cross-day label paths. Drop nonfinite required features/labels using existing eligibility, identically for the two models and control at each horizon. Report the exclusions.

Linear uses the existing `_fit_predict_linear`, ridge 1e-6 and training-only standardization. XGBoost uses `reg:squarederror`, histogram trees, 800 estimators, depth 4, learning rate .03, minimum child weight 50, subsample .8, column sample .8, lambda 10, alpha .1, max_bin 256 and seed 7. No other model family. Freeze CPU XGBoost for this small confirmation to avoid selecting between numerically differing devices after seeing results; bounded thread allocation is operational. Record software/code versions. Python is the queue oracle; native execution is permissible only with byte-exact parity, without selecting results between backends.

## Prediction endpoints and aggregation

The primary horizon is **20 original messages**. Concatenate each stock's three days in date/event order and compute existing `_spearman_corr` separately for Linear and XGBoost. Do not average daily ICs to obtain a stock-period IC. Publish five paired deltas, their equal-weight mean, median and strict-positive win count out of five; also publish equal-weight model IC means. Ties are not wins.

Horizon 10 and 50 predictions are secondary and cannot replace the primary headline. Retain existing nonzero direction accuracy, strict `abs(prediction) > 1 bp` coverage and the existing 1 bp selected-midpoint diagnostic. These are not executable returns.

Publish all 15 stock-day descriptive blocks, five stock-period summaries and three date summaries. Recompute daily metrics on each day; date summaries equally weight the five daily stock metrics. Do not pool stocks' rows for a headline. All execution headlines likewise average the five stock-period metrics, rather than weighting by rows, fills or number of days. No p-values, bootstrap or headline confidence intervals: shared dates, stocks and overlapping labels preclude treating row or partition counts as independent evidence.

An undefined metric remains null with its denominator and defined-block count. A required undefined block makes the strict five-stock headline undefined; no silent complete-case headline or replacement with zero. Missing inputs/tasks stop completion and are reported, never substituted or dropped for poor results.

## Aggressive execution

Reuse `execution_labels` and `robustness.summarize_predictions` semantics. Primary: horizon 20, latency zero, strict 1 bp selection. At decision t and delay d, long markout is `10000*(bid[t+d+h]-ask[t+d])/mid[t+d]`; short is `10000*(bid[t+d]-ask[t+d+h])/mid[t+d]`. Positive predictions select long, negative short, zero none.

Evaluate horizons 10/20/50 and delays 0/1/5. For each stock/horizon use the common eligible-row intersection across delays and models/control, with every lookup inside the same day and uninterrupted segment. This execution sample may be smaller than the IC sample; publish both denominators. Freeze per-stock three-day prediction-bin assignments across delays using existing qcut/tie handling, including its constant-prediction fallback. Report selected markout, coverage, highest-bin long, lowest-bin short, complete curves and actual bin count. Label reduced-bin extremes honestly; do not pretend ten bins exist. Report the existing strict nine-adjacent-difference ordering only with all ten bins.

These are **historical visible-quote diagnostics**, excluding fees/rebates, hidden liquidity, impact and inventory, not realized P&L or measured slippage. Day-level decile diagnostics slice the fixed stock-period assignments rather than fitting new daily cutoffs.

## Secondary passive queue confirmation

Reuse `queue_book`, `passive_execution.passive_paths`, `queue_metrics.summarize/deciles` and existing replay semantics. Size is one dataset-native displayed unit, joining the back of the bid for a positive signal or ask for a negative signal; zero places no order. No repricing. Lifetime is horizon after placement, with horizons 10/20/50 and delays 0/1/5. Report both retain and reset priority interpretations, neither selected as a winner.

Preserve the conditional assumption that D and same-price M reductions are executions. Final-ahead-order removal alone cannot fill the virtual order; an additional assumed execution unit behind it is needed. Y is retransmission, not a trade, and breaks the diagnostic path. No crossing day/segment/reset boundaries. Adverse movement is one tick against the placement midpoint, using the running minimum positive visible price difference through placement. Simultaneous events are separate from fill-before-adverse.

Queue eligibility follows the existing per-delay valid same-segment placement rule, shared across models/control within a horizon/delay/interpretation. Unlike aggressive execution, do not impose a new common-across-delays intersection or require a fully observable future lifetime. Report per-delay denominators and acknowledge differing eligible samples. Full-path and post-fill invalidation follow the existing code.

At horizon 20, lead with zero-delay conditional fill probability, fill-before-adverse probability, mean fill time in messages, five-message post-fill side-adjusted midpoint markout and realized-spread diagnostic, for both interpretations. All other frozen grid cells remain secondary. Probability denominators include every eligible decision, including zero signals; also report placed orders and fills. Fill-time means condition on fills. Each post-fill mean uses only its observable filled outcomes, with its own count. No fills imply undefined conditional means. Offsets are 1/5/10 and remaining original horizon (`decision event + horizon`); preserve existing midpoint and passive-price denominators.

Report full prediction-decile and queue-ahead-decile curves, using existing qcut with ties retained and duplicate edges dropped. Prediction bins are computed within each stock-period/model/horizon/delay/interpretation; queue bins use nonzero directions. Daily slices retain those bin assignments. To examine the prespecified signal/fill/adverse-selection tension, compare each outer prediction bin against the equal-weight mean of bins 5 and 6 when ten bins exist, for fill probability and post-fill markout. Otherwise publish the available curve without forcing a tail contrast. Publish signs and magnitudes even when they contradict the previous pattern; no pass/fail significance threshold or outcome-dependent alternative contrast.

All fills remain **historical / conditional**, never actual or live fills. Realized-spread diagnostics are not realized P&L. The identified lower fill bound remains zero with undefined conditional markout. Models can choose different directions and filled subsets, so paired diagnostics do not identify a causal execution advantage.

## Control, identities and completeness

Add exactly five secondary XGBoost controls: one per stock, horizon 20, seed 7, with the existing within-training-day label permutation on sorted historical day/event rows. Same frozen parameters and test rows; no confirmation labels are shuffled into training. Evaluate the controls through prediction, aggressive and queue grids without redefining primary endpoints.

Expected fits: 30 primary (5 stocks × 3 horizons × 2 models), plus 5 controls. Expected stock-period prediction blocks: 35; stock-day blocks: 105. Aggressive cells: 105 stock-period / 315 stock-day. Queue cells: 210 stock-period / 630 stock-day. These include controls, not decile expansion. Undefined metrics do not remove cells.

Future manifests must bind this configuration, audit/reference/preregistration commits, source and partition hashes, fit coordinates and prediction identities. Runtime paths, threads and telemetry do not define scientific task identity; record implementation/version/device information separately. Preserve original event/day/segment identity in joins. Report raw, prepared, training-eligible, prediction-eligible, execution-intersection, threshold-selected, queue-eligible, placed, filled and observable-post-fill counts, and each mechanical exclusion. Verify completeness before any headline; do not invent evaluation denominators from engineering row counts.

## Publication and stop

Future outputs belong under `results/wselob_later_confirmation_v1/`, with a confirmation report comparing all three questions against the old study. Preserve old published artifacts. Publish aggregate tables only, with complete negative/null results and limitations; exclude raw licensed data, row-level predictions, private paths, hosts, hardware IDs and scheduler information. The three shared year-end dates cannot establish broad temporal replication or current-market profitability.

Phase B creates only this protocol and its JSON configuration. **No December 27–29 outcomes were loaded, inspected, printed or computed during this phase.** Commit the preregistration separately and stop for review before implementation, reveal or execution.
