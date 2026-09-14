# Interview packet

All numbers refer to the historical WSELOB study. Use [claims and evidence](CLAIMS_EVIDENCE.md) for exact artifact locations. The packaging work adds no scientific experiment.

## 30-second answer

I tested whether simple order-book features contain stable short-horizon information. I reconstructed about 86 million messages into 57 million causal depth rows across five equities, then compared linear and boosted-tree models on fixed chronological holdouts. XGBoost gave a modest ranking improvement. But paying the visible spread and adding delay produced negative crossed-book outcomes. The useful result was both a reproducible research system and a clear distinction between predicting price and demonstrating a tradable edge.

## 90-second answer

The question was whether simple, interpretable order-book state could predict short-horizon midpoint changes without using future information. I used licensed 2017 data from five Warsaw-listed equities: roughly 86 million order messages and 57 million causal ten-level rows.

The five features were spread, top and depth imbalance, normalized order-flow imbalance, and microprice displacement. I fixed horizons at 10, 20 and 50 original messages, trained only on earlier days, and evaluated four fixed months. Linear and XGBoost used the same inputs and test rows. I also ran a matched June HistGradientBoosting comparison and shuffled training-label controls.

XGBoost's equal-weight held-out Spearman IC improved from roughly 0.228 to 0.237 at 10 messages, with smaller positive gains at the other horizons. The paired block and leave-one-stock/month checks were supportive, but I treated them as descriptive because the observations overlap.

The engineering work made this repeatable: partitioned Parquet caches, content hashes, fixed task manifests, atomic writes and resumable execution. I then reused predictions for spread and delay diagnostics. Those outcomes were negative, so I do not describe the project as a profitable strategy. A later passive-queue study also made the data-identification limit explicit: deletions do not uniquely tell us whether an order traded or was cancelled.

## Five-minute technical deep dive

### 1. Data reconstruction and book invariants

The input is order-level WSE message data, not ready-made independent feature rows. Orders use date and ID within an instrument; adds, modifications, deletions, resets and retransmissions update visible state. The replay rejects invalid updates and retains ten-level snapshots only in valid priced, uncrossed segments. Raw messages, cached partitions and scientific tasks retain content provenance. Full-source engineering coverage includes 15 later stock/day partitions that do not alter the fixed scientific sample.

### 2. Causal features and labels

Spread, top/depth imbalance and microprice are current-state quantities. Normalized OFI measures changes in top-level supply and demand using current and previous states. Labels look exactly 10, 20 or 50 source messages forward within the same uninterrupted segment. Future fields are outcomes only. This exact-message definition differs from the older synthetic clock-time demo.

### 3. Split design and leakage control

Training expands through strictly earlier days, with at least 40 preceding trading days. April, June, September and November are fixed test months. Models share the same features and rows. Controls shuffle within training day, leaving test chronology intact. I did not select parameters from final-test performance or treat repeated testing on the same holdout as fresh confirmation.

### 4. Model comparison

Linear is a strong baseline for imbalance and microprice. XGBoost adds nonlinear interactions and saturation effects with fixed parameters. Its mean IC exceeds Linear by about 0.00837, 0.00645 and 0.00617 across the three horizons. HistGradientBoosting is competitive on the matched June subset and slightly stronger at the longest June horizon, so there is no universal winner.

### 5. Negative controls and block robustness

Seed-7 shuffled XGBoost controls have IC around 0.012, 0.034 and 0.044, far below primary results but not exactly zero. I average stock/month blocks equally and inspect paired differences, wins and deletion checks. XGBoost wins 20/20, 18/20 and 18/20 paired blocks; every leave-one-stock/month mean remains positive. Bootstrap intervals are descriptive because blocks can share dependencies.

### 6. Experiment architecture

The expensive reusable step is a symbol/day Parquet feature cache. Tasks have deterministic identities, content hashes, file locks and atomic completion artifacts. A resumed run accepts completed work only when identities and hashes match; aggregation rejects missing or conflicting tasks. All 152 original tasks completed. Fixed-workload comparisons measured 17.26× training and 9.07× task-wall acceleration; two independent accelerator workers improved throughput 1.606×. These are measured workload ratios, not a universal performance promise.

### 7. Execution-aware stress test

The crossed-book extension reuses 137 prediction tasks over 411 cells. It enters and exits at opposite visible quotes, with 0/1/5-message latency and a fixed 1 bp prediction threshold. Primary headline outcomes are negative and worsen with delay. The 822-cell passive study models individual visible queues under explicit removal assumptions, but the source does not identify exact fills. Strong signals can be harder to fill, and favorable passive-price diagnostics occur even under shuffled controls. Positive hypothetical spread capture is not enough to claim alpha.

### 8. What comes next with genuinely new data

I would first establish data rights, message semantics, session boundaries and usable execution labels. Before inspecting final outcomes, I would fix the instruments, chronological split, features, horizons, models, thresholds and economic assumptions. I would retain a fresh confirmation period and state whether the goal is prediction or actual execution quality. I would not retune the inspected WSE holdouts and present the result as new evidence.

## Q&A bank

### Why use message-time horizons instead of seconds?

Message counts tie the horizon to observed book activity and preserve the original replay sequence. They are not fixed wall-clock delays: 20 messages can span different durations across stocks and periods. I would need a separately declared clock-time study to make millisecond execution claims.

### Why is Linear already strong?

Imbalance and microprice already encode directional pressure in compact variables. A linear model can capture a large share of that relationship without many degrees of freedom. The relevant question is incremental value over this baseline, not whether a nonlinear model has positive IC alone.

### Why XGBoost?

It can represent interactions and nonlinear responses in a small tabular feature set. It also provides a practical fixed CPU/accelerator comparison. The results justify a modest improvement in this sample, not selecting it as a universally best model.

### Why no large hyperparameter search?

The fixed holdouts were intended to evaluate a research question, not to become a search objective. A large post-hoc search would make the final comparison harder to interpret. If tuning were required on new data, I would separate tuning periods from a genuinely untouched final sample.

### How did you prevent leakage?

Features use only current and earlier book state. Labels stay inside valid day/segment boundaries, and training days precede each test month. Saved prediction indices, timestamps and labels must match the frozen cache before execution diagnostics can reuse them.

### Why not trust 57 million rows as independent samples?

Adjacent rows share order-book state, and their future horizons overlap. Stocks and months can also share market conditions. I report stock/month aggregates and descriptive paired checks rather than row-count p-values.

### What exactly does Spearman IC mean here?

It is the rank correlation between predicted and observed future midpoint changes within a held-out block. The headline averages those block correlations equally. It measures predictive ordering, not profit, execution probability or the fraction of correct trades.

### Why did midpoint IC not translate to crossed-book PnL?

The original target is a midpoint change, which does not pay the visible spread. Crossing both sides changes the price at which entry and exit are evaluated. The resulting historical markouts are negative; even those are diagnostics, not actual realized PnL.

### What role did spread play?

Spread is both a causal feature and an explicit cost in the crossed-book calculation. A forecast can rank small midpoint moves correctly while those moves remain insufficient to cover bid/ask crossing. That is why the execution result can be negative despite positive IC.

### What happens with one- and five-message latency?

The crossed-book primary headline becomes more negative at those fixed delays. Predictions stay fixed at the decision event, while entry and exit use the delayed exact-message quotes. The comparison uses common eligible rows across latency settings, avoiding a changing-sample explanation.

### How were negative controls constructed?

Training labels were shuffled within each training day while preserving the fixed test months and model settings. The main control scope covers five stocks in June at all three horizons, with extra PEKAO seeds. Controls are weaker but not assumed to have exactly zero IC or to define a formal null distribution.

### How did you ensure CPU/GPU results were scientifically equivalent?

The comparison fixes data, model parameters and task definition, then checks prediction and metric drift. Prediction Spearman was 0.999242 and absolute IC drift about 0.000084. That supports numerical alignment for this workload, not bitwise equality across all devices.

### What did caching, resume and hash validation solve?

They prevented repeated preparation of the same features and let interrupted tasks reuse verified completed work. Hashes detect changed inputs or artifacts; task manifests make missing work visible. This addresses reproducibility and recovery rather than improving the forecast directly.

### Why not Dask or Ray?

The workflow consists of independent tasks over partitioned local files, so bounded processes and manifests were sufficient for the measured workload. Adding a distributed framework was not necessary to establish the scientific result. A different data or scheduling bottleneck could justify it later, but this project does not claim such a system.

### What failed or surprised you?

A stable midpoint-ranking gain did not become positive crossed-book outcomes. The passive study added another caution: conditional spread diagnostics can be positive even for shuffled signals. These results pushed the interpretation toward identifying what the data and experiment actually support.

### If you had a new market tomorrow, what would you freeze first?

I would fix the data/version rights, instruments, session rules, train/test dates, features, target horizons, baseline models and controls. Execution studies would additionally fix quote placement, latency, size, cancellation rules and fee assumptions. I would reserve a final sample before exploring outcomes.

### What would you need before calling this a trading strategy?

I would need credible fills, venue-specific costs, latency, queue/hidden-liquidity treatment, impact and inventory constraints. I would also need out-of-sample confirmation and operational risk controls tied to a concrete execution policy. The current project supplies research diagnostics, not that complete evidence.

### Did the queue extension solve exact passive fills?

No. It tracks visible individual orders, but a deletion does not distinguish a cancellation from a complete execution. The reported nonzero fills assume a specific interpretation of removals; the unconditional identified lower fill probability is zero. Agreement between two priority scenarios does not remove that identification limit.
