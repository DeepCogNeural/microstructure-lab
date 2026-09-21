# Limitations

The measured evidence is historical research over five WSE equities in 2017. Its 56.9M rows overlap in time and do not constitute independent statistical observations. The final holdouts have been inspected; further tuning would require a new declared experiment and new confirmation data.

Linear and XGBoost were compared over four fixed months; HistGradientBoosting used June only. Modest positive midpoint IC differences and descriptive block intervals do not establish significance or a universal model winner. Accelerator ratios describe fixed measured workloads, not a hardware-independent speed guarantee. Native replay/queue ratios use medians of three summed per-day kernel timings, not end-to-end pipeline speedups. Byte-exact parity preserves conditional assumptions; it does not establish actual exchange fills.

Crossed-book outcomes remain negative after the visible spread, and the headline worsens with message latency. These calculations exclude fees, rebates, impact, inventory constraints and actual order fills.

The conditional queue study tracks visible orders but cannot identify exact executions from ambiguous deletion messages. Retransmission is not a trade. Matching phase, hidden liquidity and modification priority have limits; positive passive-price diagnostics are not realized profit. Zero identified fills imply undefined conditional markouts, not zero markouts.

The completed [preregistered later-period confirmation](LATER_PARTITIONS_CONFIRMATION_REPORT.md) covers only December 27–29, 2017: **three shared calendar dates across five stocks**. The 15 symbol-day partitions are not 15 independent time periods. Historical non-exposure partly relies on operator attestation; label-bearing caches already existed, and a complete technical access ledger was unavailable. The [audit](LATER_PARTITIONS_UNTOUCHED_AUDIT.md) records this provenance boundary.

The confirmation's single frozen full-history refit through December 22 differs from the older monthly expanding-window study, including its block aggregation. Changes in IC or markout magnitude cannot be attributed causally to model improvement. Positive prediction ranking, negative primary crossed-book markouts and lower conditional fill probability in stronger signal tails replicated only within this narrow later period. Stronger-tail adverse-selection ordering did not consistently replicate; adverse average post-fill markouts do not imply that stronger signals necessarily have worse post-fill outcomes.

Later-period queue fills remain conditional historical diagnostics. They do not identify actual exchange fills or trading profit, and there is no full fees/rebates, impact, hidden-liquidity or inventory model. The later passive spread diagnostic is not monotonically decreasing with latency, so the aggressive latency conclusion above must not be generalized to every passive outcome.

The offline demo is synthetic. Coinbase feed code is engineering-only, and its captures are not empirical ML evidence. Raw licensed data, row-level predictions and private compute information are not redistributed. See [data terms](DATA_TERMS.md) and [source semantics](WSELOB_QUEUE_SEMANTICS.md).
