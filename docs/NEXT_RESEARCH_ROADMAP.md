# Next Research Roadmap — Execution-Aware Robustness

**Completed 2026-09-14: Phases 0–3.** All 411 execution cells and all 25 transfer tasks completed. See [the measured results and limitations](EXECUTION_AWARE_ROBUSTNESS_REPORT.md). The plan below is retained as the original specification; it is not pending work.

## Current status and remaining priorities

**Completed 2026-09-21: preregistered later-period confirmation.** All 35 fits and the planned prediction, crossed-book and conditional queue cells completed across five stocks on December 27–29, 2017. See the [pre-confirmation audit](LATER_PARTITIONS_UNTOUCHED_AUDIT.md), [frozen protocol](LATER_PARTITIONS_CONFIRMATION_PROTOCOL.md) and [final report](LATER_PARTITIONS_CONFIRMATION_REPORT.md). This task is complete and is not next work.

The narrow confirmation replicated positive prediction ranking and the XGBoost advantage, the negative primary aggressive spread-crossing conclusion, and lower conditional fill probability in stronger signal tails. Average five-message post-fill midpoint markouts remained adverse, but stronger-tail adverse-selection ordering did not consistently replicate. Three shared dates are not broad temporal evidence, and the queue outputs remain conditional diagnostics.

The project is scientifically mature for application/portfolio purposes within these limits. Additional model-zoo comparisons or tuning on the same inspected WSELOB sample are low priority. No new research task is scheduled here; further confirmation should await genuinely new independent data, with provenance and a protocol established before outcome inspection.

## Archived execution-aware plan

Everything below is the completed original plan, retained for provenance rather than as pending instructions.

### Original motivation

The current benchmark already establishes a reproducible five-stock, full-year microstructure workflow and a modest XGBoost improvement over a linear baseline. The largest remaining scientific weakness is not model complexity: the headline target is future **midpoint** movement rather than an execution-aware outcome.

The next version should answer a harder question:

> Does the signal remain informative after explicit bid/ask crossing and modest decision latency, and is the XGBoost-vs-Linear uplift robust across the preregistered stock/month blocks?

This is a higher-value extension than adding LightGBM, CatBoost, neural networks, or a large hyperparameter search.

## Scope and time budget

Target: one focused working day of implementation + bounded computation.

Mandatory phases: 0–2 below. Phase 3 is a stretch goal only if the mandatory work finishes cleanly within the same day.

Do not change the existing published benchmark results. Start a new experiment version and preserve the current aggregate artifacts as immutable evidence.

## Phase 0 — Separate scientific identity from execution identity

The public repository intentionally removed private infrastructure/orchestration fields after the completed benchmark. Future task identity must therefore depend only on **scientific settings**, not on where/how a task is executed.

Implement a canonical scientific-config view containing only fields that can change scientific output:

- dataset identity and date/session boundaries;
- symbols and horizons;
- feature definitions;
- train/test split rules;
- model hyperparameters and seeds;
- negative-control definitions;
- metric definitions.

Exclude from scientific hashes/task IDs:

- worker counts;
- device selection;
- host or scheduler information;
- local paths;
- runtime limits;
- telemetry settings;
- publication/privacy settings.

Acceptance tests must prove that changing execution-only settings does **not** change a scientific task ID, while changing a feature, horizon, test month, model parameter, or control seed **does**.

## Phase 1 — Paired robustness of XGBoost vs Linear

Use the already published 5-stock × 4-month blocks. No retraining is required for this phase.

For each horizon (10/20/50 messages), compute paired block differences:

`delta_ic = IC_XGBoost - IC_Linear`

Publish:

- mean and median paired delta;
- XGBoost win count out of 20 stock/month blocks;
- per-stock mean delta;
- per-month mean delta;
- leave-one-stock-out headline delta;
- leave-one-month-out headline delta;
- a paired stock/month block bootstrap interval for the mean delta.

Because the 20 blocks are not guaranteed IID, label the bootstrap as a descriptive robustness interval, not a formal significance test. Do not convert row count into p-values.

Required artifact:

`results/wselob_execution_robustness_v1/paired_model_robustness.csv`

and a concise summary table in the final report.

## Phase 2 — Execution-aware crossed-book markouts

### Goal

Evaluate the existing signal against outcomes that pay the visible spread at entry and exit.

For a decision at event `t`, latency offset `d`, and holding horizon `h`:

- long entry price = best ask at `t + d`;
- long exit price = best bid at `t + d + h`;
- short entry price = best bid at `t + d`;
- short exit price = best ask at `t + d + h`.

Define crossing-adjusted markouts in basis points using the entry-time midpoint as the denominator:

`long_crossed_bps = 1e4 * (future_bid - entry_ask) / entry_mid`

`short_crossed_bps = 1e4 * (entry_bid - future_ask) / entry_mid`

For a model prediction formed at `t`, the sign-selected crossed markout is:

- positive prediction -> long crossed markout;
- negative prediction -> short crossed markout;
- zero prediction -> no directional selection.

These remain **historical visible-quote diagnostics**, not realized PnL. They do not model fill probability, hidden liquidity, fees/rebates, impact, inventory, or queue priority.

### Fixed latency grid

Use the preregistered latency offsets:

`d = [0, 1, 5]` message events.

Use the existing horizons:

`h = [10, 20, 50]` message events after entry.

Do not add or remove latency settings after inspecting results.

### Evaluation

Reuse the existing fixed stock/month holdouts and the same Linear/XGBoost predictions where row identity permits. If row-level predictions must be regenerated, use the same frozen models/settings and do not tune.

For every model/horizon/latency combination report:

- equal-weight stock/month mean crossed markout by prediction decile;
- top-decile long and bottom-decile short crossed markout;
- fraction of stock/month blocks with the expected decile ordering;
- sign-selected crossed markout for fixed absolute prediction thresholds already defined by the project;
- coverage of those fixed thresholds;
- degradation from latency 0 -> 1 -> 5;
- Linear vs XGBoost differences under identical rows.

Do **not** optimize a new threshold on the fixed test blocks.

### Negative controls

Run the same execution-aware diagnostics for the existing shuffled-label XGBoost controls. The control is expected to lose monotonicity and directional crossed-book performance; if it does not, stop and investigate before publishing a stronger claim.

### Required code/artifacts

Suggested public structure:

- `src/cloblab/execution_labels.py`
- `src/cloblab/robustness.py`
- `scripts/run_execution_robustness.py`
- `configs/wselob_execution_robustness_v1.json`
- `results/wselob_execution_robustness_v1/summary.csv`
- `results/wselob_execution_robustness_v1/latency_summary.csv`
- `results/wselob_execution_robustness_v1/paired_model_robustness.csv`
- `docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md`

Only aggregate outputs belong in Git.

## Phase 3 — Stretch: leave-one-stock-out transfer at 20 messages

Run only if Phases 0–2 are complete, tested, and comfortably within the one-day budget.

Question:

> Does the learned relationship transfer to an equity not used for model fitting?

For each fixed test month and held-out stock:

1. train XGBoost on strictly earlier data from the other four stocks;
2. test on the held-out stock in that fixed month;
3. use the existing five causal features and the already frozen XGBoost hyperparameters;
4. evaluate only the 20-message horizon;
5. compare transfer IC with the existing within-stock XGBoost IC on the same held-out block.

This creates at most 20 primary transfer tasks. Do not tune per stock.

Report:

- mean transfer IC;
- transfer-vs-within-stock delta;
- held-out-stock breakdown;
- month breakdown;
- win count;
- shuffled-label transfer control for a bounded representative subset.

A weak or negative transfer result is publishable and scientifically useful; do not change the experiment after seeing it.

## Tests required before publication

Add tests for:

1. long/short crossed-markout formulas on a hand-checkable book sequence;
2. no cross-day or cross-segment future lookup;
3. latency offset cannot access information at feature time;
4. future bid/ask indices are exactly `t + d + h` within the same valid segment;
5. scientific task IDs ignore execution-only settings;
6. scientific task IDs change when scientific settings change;
7. paired aggregation uses the same stock/month block for both models;
8. incomplete task denominators fail aggregation rather than silently dropping blocks;
9. public outputs contain no hostnames, hardware inventories, device UUIDs, scheduler IDs, absolute home paths, or environment dumps.

All existing tests must remain green.

## Public figures

Keep visualization minimal and recruiter-readable:

1. **Linear vs XGBoost paired IC delta by stock/month**;
2. **crossed-book markout by prediction decile**, latency 0/1/5;
3. optional: transfer IC vs within-stock IC if Phase 3 is completed.

Do not create a dashboard or large plotting framework.

## Claim gate

The final report may claim only what the completed artifacts support.

Potential strong outcomes:

- XGBoost uplift is positive across most stock/month blocks and robust to leave-one-stock/month checks;
- prediction deciles remain ordered after spread crossing;
- crossed-book diagnostics decay gradually rather than collapsing immediately with small latency;
- the signal transfers to held-out stocks.

Potential weak outcomes are equally valid:

- XGBoost uplift is too small/unstable once block uncertainty is considered;
- midpoint predictability mostly disappears after crossing the spread;
- latency rapidly destroys the signal;
- the model is instrument-specific.

Do not hide any of these outcomes.

## Publication/privacy gate

Before pushing, follow `CONTRIBUTING.md`.

In particular, do not commit:

- infrastructure names or hostnames;
- hardware inventory or device identifiers;
- scheduler details;
- local paths or environment dumps;
- raw/row-level market data or predictions;
- internal application/agent notes.

The public repository should contain only scientific code, tests, public-safe configuration, aggregate results, and the final research report.

## Definition of done

The track is complete when:

- Phases 0–2 are fully implemented;
- the fixed denominator is complete or explicitly reports failure;
- tests and CI pass;
- aggregate artifacts reproduce the report;
- privacy checks pass;
- README is updated only with measured results;
- no claim is upgraded from midpoint prediction to realized trading PnL.

Phase 3 is optional and must not delay publication of a clean Phase 0–2 result.
