# Queue-Aware Passive Execution — Final Research Track

Status: **Sections 0–8 completed on 2026-09-14 as conditional diagnostics under the documented data-identification limit**. All 822 cells completed; see [results and limitations](QUEUE_AWARE_EXECUTION_REPORT.md). The optional C++20 port remains unimplemented. Original preregistration follows. This track starts from the completed midpoint, crossed-book, latency, and leave-one-stock-out results already published in this repository. Do not alter those results.

## Research question

The current project establishes two facts:

1. short-horizon midpoint moves are predictably ranked out of sample, including across held-out stocks;
2. immediately crossing the visible spread produces negative historical crossed-book outcomes, and small message-count latency makes them worse.

The remaining market-microstructure question is therefore:

> Can the same frozen predictive information improve **passive execution quality** once visible queue position, fill uncertainty, time-to-fill, and post-fill adverse selection are modeled explicitly?

This is the final scientific extension of the WSELOB project. Do **not** add new model families, tune the existing XGBoost model, search prediction thresholds, or change the fixed stock/month holdouts to obtain a favorable result.

---

## 0. Hard gates before implementation

### 0.1 Preserve the existing benchmark

Treat the following as immutable evidence:

- `results/wselob_xgboost_application_v1/`
- `results/wselob_execution_robustness_v1/`
- the frozen five causal features;
- existing Linear/XGBoost predictions and model parameters;
- fixed test months: April, June, September, November 2017;
- horizons: 10/20/50 original messages.

Start a new experiment version. Never overwrite prior result files.

### 0.2 Audit WSELOB order-event semantics first

Before claiming queue position or fills, verify the raw message semantics against the depositor's source notebook/code and document the evidence for:

- `A`, `Y`, `M`, `D`, and `F` actions;
- whether `Y` is an execution/trade-related order update or another event type;
- how partial fills are represented;
- how cancellations/deletions are represented;
- whether an order modification preserves or loses time priority for:
  - volume decrease;
  - volume increase;
  - price change;
- whether the raw sequence contains enough information to order same-price resting orders reliably;
- session reset behavior and any auction/non-continuous-trading cases relevant to the 10:00–16:00 research window.

Write the evidence and resulting assumptions into `docs/WSELOB_QUEUE_SEMANTICS.md` with citations/links to the public source material used.

**Stop condition:** if exact price-time priority cannot be reconstructed from the available messages with defensible rules, do not invent an exact fill simulator. Implement the conservative queue bounds described below and label them explicitly as bounds/diagnostics.

### 0.3 Public-repository privacy

Follow `CONTRIBUTING.md` as a hard gate. No hostnames, hardware inventory, scheduler metadata, absolute home paths, environment dumps, private compute details, raw market data, or row-level predictions may be committed.

---

# 1. Queue reconstruction

## 1.1 Order-level queue state

Extend the existing order-level replay so that, for every visible priced order, the research engine can recover at minimum:

- symbol;
- day/session segment;
- side;
- price;
- visible remaining quantity;
- original order identifier;
- priority rank or a documented conservative proxy for rank;
- event index at which the order entered its current priority state.

Maintain an ordered queue for each `(side, price)` rather than only aggregate depth.

The existing aggregate `OrderBook` behavior must remain available and must produce the same ten-level snapshots as before.

## 1.2 Replay parity

For every sampled day used in tests and for a bounded full-data verification pass:

- aggregate quantity from the queue-aware book must equal the existing aggregate-depth replay at every valid checked event;
- best bid/ask and ten-level sizes must match exactly;
- reset/segment boundaries must match;
- negative depth, duplicate live orders, impossible removals, or priority-state contradictions must fail loudly.

Do not silently repair malformed events.

## 1.3 Modification rules

Encode modification-priority behavior only after the Phase-0 semantics audit. Unit tests must cover each supported modification case.

If priority behavior is ambiguous, provide at least two documented interpretations:

- **optimistic bound**: ambiguous same-price modification keeps priority when plausible;
- **conservative bound**: ambiguous modification loses priority / moves behind existing same-price orders.

The primary public conclusion must be robust to the chosen interpretation or explicitly report the range between bounds.

---

# 2. Virtual passive-order experiment

## 2.1 Frozen decision signal

Reuse the existing frozen prediction at decision event `t`.

Do not retrain or tune based on passive-execution results.

Primary model comparisons:

- Linear;
- XGBoost;
- existing shuffled-label XGBoost controls where available.

## 2.2 Fixed placement policy

For each decision event and placement latency `d`, define a virtual unit-size passive order using only information available at placement time `t+d`.

Primary latency grid:

- `d = 0, 1, 5` original messages.

Primary quote policy:

- positive prediction: join the **best bid** at `t+d`;
- negative prediction: join the **best ask** at `t+d`;
- zero prediction: no order.

The virtual order joins at the **back of the currently visible queue** at that price under the primary conservative policy.

Do not improve the entry price using future information.

If the chosen best price changes before placement because of latency, use the best price actually visible at `t+d`.

## 2.3 Queue-ahead quantity

At placement, record:

- placement price;
- best bid/ask and spread;
- visible queue-ahead quantity;
- number of orders ahead;
- total visible size at the price;
- top imbalance, OFI, microprice displacement, and existing prediction;
- event index and timestamp.

New same-price orders arriving after placement are behind the virtual order and must not increase queue ahead.

Orders ahead that leave the book reduce queue ahead only according to the audited event semantics.

## 2.4 Fill definition

Use a fixed virtual order size that avoids size optimization. Primary size: **one minimum research unit** (or one dataset-native share/unit if the dataset volume field is already in shares). Document the exact unit.

A fill occurs only when the reconstructed sequence provides sufficient evidence that all queue ahead plus the virtual order's required size would have been consumed under the documented priority rules.

Do not label a fill merely because aggregate best-level depth fell.

For ambiguous data semantics, publish conservative and optimistic fill bounds rather than a false exact fill.

## 2.5 Order lifetime / cancellation policy

Pre-register fixed maximum resting horizons in original-message counts:

- 10 messages;
- 20 messages;
- 50 messages.

These correspond to the existing prediction horizons and are not optimized after inspection.

A virtual order is cancelled at the first of:

1. fill;
2. end of its fixed horizon;
3. session/segment boundary;
4. invalid book state.

Primary experiment does not chase/reprice an unfilled order.

A later optional diagnostic may evaluate one deterministic reprice rule, but it must be clearly secondary and must not replace the primary fixed-quote result.

---

# 3. Outcomes to measure

Do not reduce this experiment to a single PnL number.

## 3.1 Fill statistics

For each model × stock × month × horizon × latency block report:

- fill probability;
- median and mean time-to-fill in message events;
- queue-ahead distribution at placement;
- fill probability conditional on queue-ahead decile;
- fill probability conditional on prediction decile;
- cancellation/unfilled fraction;
- number of eligible decisions.

## 3.2 Post-fill adverse selection

For filled virtual orders, measure midpoint movement after fill at fixed offsets:

- 1 message;
- 5 messages;
- 10 messages;
- and the remaining original prediction horizon when well-defined.

Use side-adjusted markout:

- passive buy: positive if future midpoint rises after the fill;
- passive sell: positive if future midpoint falls after the fill.

Report equal-weight stock/month summaries.

## 3.3 Realized-spread diagnostic

For a filled passive order, compute a visible-quote / midpoint realized-spread diagnostic using the passive fill price and a fixed future midpoint. Clearly label this a **historical execution diagnostic, not realized trading PnL**.

No fees, rebates, market impact, inventory constraints, hidden liquidity, or stochastic queue competition may be silently assumed away.

If maker fees/rebates are not part of the licensed data, do not add venue-specific economics to the headline result.

## 3.4 Fill-versus-adverse-move race

A central result should answer:

> How often does the virtual order fill before the signal becomes adverse?

Define a fixed adverse-move event before looking at results. Recommended primary definition:

- for a passive buy, midpoint falls by at least one observed tick below the placement midpoint before fill;
- for a passive sell, midpoint rises by at least one observed tick above the placement midpoint before fill.

Report:

- `P(fill before adverse move)`;
- `P(adverse move before fill)`;
- no-event / horizon-expiry fraction.

Do not tune the adverse threshold.

## 3.5 Signal-conditioned execution quality

The key scientific question is not just whether passive orders fill, but whether stronger predictions obtain better fills/outcomes.

For each primary block report by prediction decile:

- fill probability;
- median queue ahead;
- post-fill adverse-selection markout;
- realized-spread diagnostic;
- fill-before-adverse probability.

Evaluate whether stronger predicted direction improves or worsens passive execution quality.

This explicitly tests the classic trade-off: stronger alpha may coincide with worse passive fill probability / greater adverse selection.

---

# 4. Fair comparison and controls

## 4.1 Same rows, same placement rules

Linear and XGBoost must use the same eligible decision rows for every paired comparison within a stock/month/horizon/latency block.

If one model has no direction because prediction is exactly zero, keep eligibility accounting explicit rather than silently removing rows from the denominator.

## 4.2 Shuffled controls

Reuse existing shuffled-label predictions wherever available and run the exact same queue experiment.

Controls should report the same fill and adverse-selection metrics.

Do not infer formal p-values from row counts.

## 4.3 Block-level robustness

Headline statistics must be equal-weight over stock/month blocks.

For the main XGBoost-vs-Linear differences report:

- paired mean and median difference;
- block win count;
- leave-one-stock-out mean;
- leave-one-month-out mean;
- descriptive paired block bootstrap interval.

Treat the interval as descriptive, not a formal significance claim.

---

# 5. Required implementation

Names may change if a cleaner architecture is obvious, but keep responsibilities separated.

Suggested files:

```text
src/cloblab/queue_book.py
src/cloblab/passive_execution.py
src/cloblab/queue_metrics.py
scripts/run_queue_execution.py
scripts/render_queue_execution.py
configs/wselob_queue_execution_v1.json
docs/WSELOB_QUEUE_SEMANTICS.md
docs/QUEUE_AWARE_EXECUTION_REPORT.md
results/wselob_queue_execution_v1/
```

The experiment config must freeze:

- dataset/symbols;
- fixed months;
- horizons;
- placement latencies;
- virtual order size;
- placement rule;
- maximum resting horizon;
- adverse-move definition;
- model/control scopes;
- aggregation rules;
- queue-priority interpretation.

Scientific task IDs must remain independent of execution hardware and paths.

---

# 6. Required tests

At minimum add hand-checkable tests for:

1. two or more same-price orders preserve audited priority order;
2. a new order after the virtual order is behind it;
3. partial depletion of an ahead order does not prematurely fill the virtual order;
4. cancellation/deletion ahead reduces queue ahead correctly;
5. cancellation behind does not affect queue ahead;
6. each supported modification case applies the audited priority rule;
7. a virtual order fills exactly when queue ahead plus required virtual size is consumed;
8. no fill is inferred from an unrelated price-level change;
9. latency placement uses only `t+d` state;
10. horizon expiry cancels an unfilled virtual order;
11. no queue/fill path crosses day/session/segment boundaries;
12. queue-aware aggregate depth matches the existing book replay;
13. paired model comparisons use identical eligible block denominators;
14. incomplete denominators fail rather than silently drop rows;
15. public artifacts pass the privacy gate.

All existing tests must continue to pass.

---

# 7. Public outputs

Commit only aggregate/public-safe artifacts.

Required outputs:

```text
results/wselob_queue_execution_v1/
  fill_summary.csv
  fill_by_prediction_decile.csv
  fill_by_queue_decile.csv
  adverse_selection_summary.csv
  realized_spread_summary.csv
  fill_adverse_race_summary.csv
  paired_model_differences.csv
  control_summary.csv
  run_manifest.json
```

Recommended recruiter-readable figures:

1. fill probability vs prediction decile;
2. post-fill adverse selection vs prediction decile;
3. fill-before-adverse probability vs queue-ahead decile;
4. one compact Linear-vs-XGBoost comparison figure.

No dashboard.

---

# 8. Interpretation / claim gate

The report must retain unfavorable results.

Possible outcomes include:

- the signal improves passive execution quality and survives conservative queue assumptions;
- the signal predicts price but stronger signals are harder to fill passively;
- fills concentrate precisely where adverse selection is worst;
- passive execution remains negative/unattractive even though midpoint IC is robust;
- results depend strongly on queue-priority ambiguity, making an exact trading conclusion unsupported.

All are valid scientific outcomes.

Do not use the terms `profitable strategy`, `realized alpha`, or `realized PnL` unless the experiment actually models the missing economic mechanisms required for such a statement. This track is a historical queue/execution study.

---

# 9. Optional engineering polish — C++20 core

**Only start this after Sections 0–8 are complete, tested, and reported. Do not delay the scientific queue result to force C++ into the project.**

If time remains, port only the performance-critical replay/queue kernel to modern C++20 and expose it to Python via a minimal binding layer (for example pybind11).

Scope:

```text
raw order messages
  -> C++20 order/queue replay
  -> snapshots / queue state
  -> Python research/evaluation layer
```

Requirements:

- Python implementation remains the reference oracle;
- exact parity tests for book state, queue-ahead state, and fill outcomes on deterministic fixtures;
- bounded full-data parity checks using hashes / aggregate receipts;
- no duplicate research logic in C++;
- no rewrite of XGBoost/evaluation/plotting in C++;
- benchmark replay throughput and peak memory;
- benchmark numbers are reported only if measured on the same input and clearly defined conditions.

Suggested files:

```text
cpp/queue_replay/
  CMakeLists.txt
  queue_book.hpp
  queue_book.cpp
  bindings.cpp
src/cloblab/queue_cpp.py
```

If the C++ port cannot achieve reliable semantic parity quickly, keep the tested Python implementation and report C++ as unfinished rather than weakening correctness.

---

# 10. Definition of done

The **scientific project is complete** when:

- raw order-event semantics and queue-priority assumptions are documented;
- queue-aware replay passes parity tests against the existing aggregate book;
- the frozen passive-order experiment runs on all preregistered eligible stock/month blocks;
- fill, queue, adverse-selection, realized-spread, latency, and control summaries are complete;
- Linear/XGBoost paired comparisons use fixed denominators;
- unfavorable outcomes are retained;
- CI and privacy checks pass;
- `docs/QUEUE_AWARE_EXECUTION_REPORT.md` explains what was learned without claiming realized PnL;
- README is updated only with measured final results.

The **engineering polish is complete** only if the optional C++20 kernel additionally achieves tested semantic parity and a reproducible benchmark.

After this track, do not add more model libraries or tune the same WSELOB holdouts. Further scientific work should require genuinely new data or a materially new preregistered question.
