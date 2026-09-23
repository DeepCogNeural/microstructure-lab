# Quote-or-Pull R0 — OutcomeTick source repair audit

**Verdict: STOP for this source at R0.** The public receipts repair the passive-role identification path for the fixed prints, but no defensible subsecond exchange match-time interval or exact-token, size-aware event replay has been established. The specified 5-second maker estimand has **0 certified legs**. No C/A/M effects, markouts, models, terminal outcomes or fresh-final paths were evaluated.

## Pinned development source and blind selection

- Source: OutcomeTick free `samples-2026-09-08` release, BTC 5-minute series. Archive SHA-256 `9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506` (330,215,988 bytes) matched the prior PM0 audit. The five relevant compressed file hashes matched `results/polymarket_pm0_v1/outcometick_sample_audit.json` and are enforced in `scripts/audit_qop_outcometick_r0.py`. No sample re-download.
- Use: the [provider's public sample page](https://github.com/Ligengxin96/polymarket-data-samples) offers this release for free and states that mirrored samples are CC BY 4.0. No source rows or identifiers are redistributed here. The provider explicitly says WebSocket trade prints have **not** been reconciled against on-chain fills; that reconciliation is this audit's question.
- Register the Sep 8 windows as `DEVELOPMENT_SOURCE_AUDIT`. Eligibility used scheduled start/end and book/BBO coverage only: both streams had an observation in the first and last 30 seconds; 288 markets passed. The first three by `(scheduled_start, condition_id)` were selected. Orientation was the first metadata token ID. Before receipt/markout inspection, the fixed candidate rule was first 10 BUY and 10 SELL hash-bearing prints by `(event_ts_ms, slug, transaction_hash)`, merged chronologically. Those 20 happened to occupy two of the three selected markets. Private fixed index SHA-256 `cbde4ec0ac85a9b6e73b6d5c2c4fd4d7f728014ee968e5eb65f445f83d40f054`. No replacement candidates.

## Receipt-to-leg identification

The first five fixed public transactions were checked before expanding to all 20. All 20 have readable transaction inputs and logs from Polygon Blockscout. The verified sample-period contract is `CTFExchange` V2, non-proxy, verified 2026-04-06; its deployed bytecode SHA-256 is `fd185b97a4b11d77246055232d365d6e58a60b2f7487cf4430f84f596fc9519c`. Its decoded `matchOrders` input distinguishes the active `takerOrder` from `makerOrders`; each receipt's `OrdersMatched` taker order hash identifies the active settlement event. Maker `OrderFilled` events were reconciled to input maker orders by maker address, token, side and filled amount. This is stronger than treating the event field named `maker` as a passive label. The [Polymarket V2 contract code](https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/mixins/Trading.sol) describes the active taker and maker-order array; the receipt's own verified ABI/source and immutable deployed bytecode govern the historical interpretation.

| Denominator | Fixed result |
| --- | ---: |
| Print candidates / unique transaction hashes / successful receipt joins | 20 / 20 / 20 |
| Receipt/input/print token, side, size and price contradictions | 0 |
| Actual passive maker-order legs, all tokens | 30 legs / 209.522286 shares |
| Passive legs on the selected token | 14 legs / 73.671250 shares |
| Selected-token passive BUY / SELL | 13 / 1 legs |
| Prints with more than one passive leg | 7 / 20 |
| Distinct maker orders / repeated maker orders / legs of repeated orders | 26 / 2 / 6 |
| Role-ambiguous / unmatched among attempted prints | 0 / 0 |

A public print is the active-side transaction representation, not one passive fill. Several selected-token prints were matched against orders on the complementary token. Raw transaction hashes, addresses, order hashes, sizes and row-level joins stay in the ignored private evidence index. The fixed receipts/index SHA-256 values are `b92d7d641274641e8d7dbd8ac428a685a08e19f45ab3a5e61a58a3352d951f26` and `cbde4ec0ac85a9b6e73b6d5c2c4fd4d7f728014ee968e5eb65f445f83d40f054`.

## Clock and exact-token state

- Source print timestamp to local receive lag: **10 / 14 / 76 ms** min/median/max. Print source timestamp preceded the associated chain block timestamp in **20/20**, by **1.574 / 2.214 / 3.425 s** min/median/max. Chain block timestamps are whole-second settlement anchors. Neither this difference nor millisecond formatting identifies an exchange match-time interval. The [market-stream documentation](https://docs.polymarket.com/market-data/realtime-data) defines the trade print's `timestamp` field but does not certify it as a per-leg matching clock with ≤0.5 s error. The required `u ≤ min(0.5 s, ell/4)` remains **UNKNOWN/FAIL**. Each of the 30 maker legs inherits this uncertainty; a transaction-wide print time was not assigned to them as a proven match time.
- Exact-token causal **print-receive-time** availability: two-sided BBO before all 20, with receive-age **2 / 55.5 / 198 ms**. A new BBO update within the hypothetical following 5 seconds appears for **19/20**; two-sided as-of quote at that hypothetical target exists for 20/20, but one is over 5 seconds old. Full-book snapshots are two-sided before and at the hypothetical target for 20/20; preceding snapshot age **14 / 249.5 / 992 ms**, and 19/20 have a new snapshot within 5 seconds. Price-change updates appear within 5 seconds for 20/20. These are availability checks only; no 5-second price difference was calculated.
- The `best_bid_ask` stream contains no touch size. Full-book rows contain sizes, but the interleaved `price_change` stream has no validated sequence/reset or batch-completeness contract in this audit. Thus **0/20** have certified size-aware, exact-token replay/target state. Print-receive cutoff is a diagnostic proxy, not a verified maker-match cutoff.
- Timely public flow for M2: **UNKNOWN**. Print sides agree with active-order sides in 20/20 and the archive records receive times, but the unresolved match/decision clock prevents a prospective availability proof. Later chain receipts were used only for labels, never earlier features. This M2 finding is separate from the M0/M1 measurement failure.

## Gate and next action

| Gate | Result |
| --- | --- |
| Source integrity / development scope | PASS; exact sample and fixed 20 |
| True passive role and print expansion | PASS for 20 prints, 30 maker legs; 14 on selected token |
| Per-leg match clock/error ≤0.5 s | FAIL/UNKNOWN; 0 certified |
| Exact-token BBO and size-aware 5-second replay | BBO availability observed; touch/replay not certified |
| Timely flow M2 | UNKNOWN |
| Jointly qualified maker + clock + BBO + 5-second target | **0 / 14 selected-token maker legs** |

**One smallest next action for reviewer:** decide whether a lawful source with sample-period per-leg exchange match-time semantics and a bounded error can be obtained; only then consider a separately authorized size-aware book replay qualification. Do not enter R1/model fitting, broaden acquisition, change the 5-second horizon or release fresh final data from this result. One public day would establish only R0 feasibility even if the clock gate later passed.

## Reproduction and cost

`python3 scripts/audit_qop_outcometick_r0.py --sample-root <unpacked-sample>/data/polymarket/daily --archive <pinned-tar.gz> --receipts-private <private-20-receipts.json> --out <new-aggregate.json>` verifies source hashes, reconstructs blind selection, checks transaction roles/amounts, and emits aggregate timing/book availability. The private receipt JSON contains the 20 fixed Blockscout `/api/v2/transactions/{hash}` responses and `/logs` responses; its SHA is above. Aggregate output is `results/polymarket_qop_r0_outcometick_v1/audit.json`. No paid source, live order, AWS restart, GPU or model run. One CPU, under 15 minutes active audit time, under 10 MiB new public-receipt/contract downloads, 0 new sample bytes. No parser/join repair was needed. This is a measurement-validity result, not an economic-performance estimate.
