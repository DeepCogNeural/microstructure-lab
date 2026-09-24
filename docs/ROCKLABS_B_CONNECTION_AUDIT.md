# Rocklabs B connection audit: fixed BTC 5-minute cohort

**Decision:** A post hoc label plus a received-time quote can be assembled for **20/32** fixed events using direct BBO, and **25/32** using a separate full-book top. This supports a bounded development-data connection. It does **not** restore the passive-maker Quote or Pull claim: the maker execution time, contemporaneous causally certified L2, and label publication time remain unverified. No model, score, PnL, or strategy was fit.

## Fixed design and evidence

The 32 active events (8, 11, 13) and 64 observed tokens came from only the 2026-07-28/29/30 08 UTC Rocklabs files. The private roster hash and source hashes were frozen in `results/rocklabs_qop_b_connection_v1/manifest.json` at commit `9c66dec7e47e6214499ed10446be07fda026573c`, before the official API and CTF queries. No event/date replacement or final data was used. This is an availability-selected cohort, not a random or complete market sample.

For every event, the embedded slug supplied a provisional 5-minute window. Current official Gamma event and market records corroborated the event slug, condition ID, both observed tokens, `Up`/`Down` outcome order, and planned end time. Current CLOB by-token results for both tokens corroborated the condition and token pair. CTF `getCollectionId` index sets 1/2 and `getPositionId` with USDC.e corroborated each token's outcome index. CTF `payoutNumerators(0,1)` and `payoutDenominator` at `latest` gave a binary payout in every case. Current Gamma data was used only to verify identity and the planned end; `outcomePrices`, `closed`, and last trade were not labels or historical features. The time when each terminal label became publicly available is unknown.

The decision time was planned end minus 120 seconds. A direct BBO candidate came from the **last received** raw `price_change` record for the verified Up token at or before that time, requiring age ≤1,000 ms, numeric prices, and `0 < bid < ask < 1`. The separate snapshot top came from the last received `book` record, requiring age ≤5,000 ms, nonempty valid sides, and an uncrossed book. Two different values with the same latest receive millisecond failed closed. An older valid row could not replace a failed latest row. No exchange-time resorting or neighboring-hour download was used. These are observed record states, not an independently certified state at each maker match.

| Rocklabs UTC date | Fixed events | Identity + binary payout | Direct BBO valid | Snapshot top valid | BBO conflicts / stale | Snapshot conflicts / stale |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07-28 | 8 | 8 | 1 | 2 | 4 / 3 | 1 / 5 |
| 2026-07-29 | 11 | 11 | 9 | 11 | 2 / 0 | 0 / 0 |
| 2026-07-30 | 13 | 13 | 10 | 12 | 2 / 1 | 0 / 1 |
| **Total** | **32** | **32** | **20** | **25** | **8 / 4** | **1 / 6** |

All 20 direct-BBO rows also have a valid snapshot top. Valid direct-BBO age ranged from 0 to 115 ms; valid snapshot age ranged from 12 to 1,569 ms. Payout labels were 18 Up and 14 Down across the 32. These are coverage diagnostics only; no performance inference follows from this small selected cohort.

The private 32-row table has per-event source date, slug, condition/token identity, both outcome bindings, official planned end, decision time, latest quote values and age or conflict/failure reason, CTF payout vector, and each gate. It is gitignored. The public aggregate and its private-table SHA-256 are in `results/rocklabs_qop_b_connection_v1/summary.json`. The reproducible extractor is `scripts/rocklabs_b_connection.py`. It made 102 read-only HTTP requests in its successful audit run. Preflight queries and a first run stopped by a local iteration error consumed approximately 104 additional read-only requests, keeping the total below the 300-request cap. The three source files were checksum-verified before both phases.

Official endpoint semantics: [Gamma event by slug](https://docs.polymarket.com/api-reference/events/get-event-by-slug), [CLOB market by token](https://docs.polymarket.com/api-reference/markets/get-market-by-token). CTF payout/token verification uses read-only Polygon `eth_call` against the CTF contract; the exact selectors and collateral address are in the extractor.

## Research implication

B now has an exact identity and post hoc settlement join for this fixed small cohort, plus an explicit quote-availability gate. This does **not** establish point-in-time terminal-label availability or a passive-maker execution clock. The earlier CLOB daily token-index overlap failure was specific to that index route; it did not rule out the Gamma/CLOB/CTF identity route verified here. The A-side unresolved supplier questions about exchange timestamp and L2 semantics still control any adverse-selection claim. Stop this bounded B computation here and seek Advisor review against the fixed hashes and failure counts.
