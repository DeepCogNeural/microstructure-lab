# Methodology

## Current WSELOB benchmark

The question is whether current visible order-book state ranks future midpoint changes under fixed chronological evaluation. The primary evidence concerns five WSE equities in 2017, not the synthetic demo or Coinbase captures.

Order identities and action messages reconstruct ten visible price levels. Valid rows must lie in the 10:00–16:00 Warsaw window and an uninterrupted uncrossed, priced, sufficiently deep book segment. Invalid states and day boundaries prevent feature/label paths from continuing across gaps.

The five frozen causal features are spread in basis points, top imbalance, ten-level depth imbalance, normalized Level-1 order-flow imbalance (OFI), and microprice displacement from midpoint. OFI uses current and previous visible state; no future quote enters a decision feature. The primary experiment does not add trade-flow features or select a feature set after inspecting held-out outcomes.

Labels are midpoint changes at **exactly 10, 20 or 50 original messages** after the decision, inside the same valid segment. They are not seconds and not the next available valid row after a gap.

Training uses expanding strictly earlier days, with at least 40 prior trading days. The four fixed test months are April, June, September and November. Linear and XGBoost share features, horizons and test rows; HistGradientBoosting uses the matched June subset. Model parameters are fixed, and negative controls shuffle training labels within each training day. No hyperparameter search was performed on the final holdouts.

The primary metric is held-out Spearman information coefficient (IC): rank correlation between predicted and observed midpoint changes. Headline means weight stock/month blocks equally. Paired model differences, leave-one-stock/month means and block-bootstrap intervals describe robustness, not formal significance. Overlapping labels and shared stocks/months prevent interpreting millions of rows as independent evidence.

## Execution and transfer extensions

The [crossed-book study](EXECUTION_AWARE_ROBUSTNESS_REPORT.md) reuses frozen predictions and evaluates opposite bid/ask entry and exit quotes with 0/1/5-message placement delay. Exact source indices and a shared eligible-row intersection protect model and latency comparisons. A fixed absolute prediction threshold of 1 bp is not retuned.

The held-out-stock study trains only on strictly earlier rows from the other four stocks, using the same five features and XGBoost parameters. It is a midpoint-transfer diagnostic, not new execution evidence.

The [queue study](QUEUE_AWARE_EXECUTION_REPORT.md) joins the back of visible best-price queues for one dataset-native unit. Order identities track queue ahead. Ambiguous removal and modification semantics require conditional diagnostics; a decline in aggregate depth alone never proves a fill. See [audited source semantics](WSELOB_QUEUE_SEMANTICS.md).

## Earlier synthetic/collector scaffold

The generic `labels` module supports clock-time midpoint labels at the first timestamp at or after an offset, and the generic walk-forward evaluator purges training labels reaching the test window. This is distinct from the WSELOB exact-message protocol above.

The scaffold also supports backward-looking trade-flow/activity features and visible-depth cost sweeps. They are software capabilities, not additional features or results in the frozen five-stock benchmark. The deterministic offline demo does not establish empirical market performance.
