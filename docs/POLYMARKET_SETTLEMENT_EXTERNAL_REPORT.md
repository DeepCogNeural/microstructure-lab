# Polymarket settlement value and external BTC study

P1 is complete for the measurable subset. P2 is in progress; this checkpoint is not the complete overnight deliverable.

## P1: gross value relative to settlement

Three exposed 08 UTC development hours only. The primary weighting is share-weighted within event, equal events within day, then equal days. Mean gross value is **-0.273206 cents/share**; pooling all shares gives **-0.735121 cents/share**. These values exclude inventory cost basis, fees, rebates, hedges, interim exits and capital costs. They are not maker account profit or avoidable adverse selection.

| UTC day | Active / measured events | Joined groups | Legs | Shares | Event-equal cents/share | Share-weighted cents/share |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07-28 | 8 / 8 | 7179 | 15346 | 219429.284419 | 0.178156 | 0.272263 |
| 2026-07-29 | 11 / 11 | 14067 | 28647 | 554530.896809 | -0.915637 | -1.507844 |
| 2026-07-30 | 13 / 12 | 25246 | 50236 | 731865.993129 | -0.082138 | -0.451669 |

All 94,229 inherited joined legs connect to the verified both-token CTF identity and payout cache. No duplicate legs or group exclusions arose. Only the original 24 structural examples (41 legs) have independent input/receipt support; the remainder use the inherited event-derived mechanism. Cross-condition or unknown-token groups are rejected by the new analysis.

The original active denominator remains 32. One July 30 event has nine prints and no joined group; all nine are in the unjoined set. The three hours have 3 / 484 / 683 unjoined prints respectively. Their missing maker-leg quantities are unknown, so no population-wide loss bound is reported. There are no missing payments among measurable legs.

## Fixed strata and concentration

| Up-equivalent stratum | Events | Legs | Shares | Day-equal cents/share |
|---|---:|---:|---:|---:|
| up_equivalent_buy | 31 | 47793 | 710794.637428 | 6.960771268760058 |
| up_equivalent_sell | 31 | 46436 | 795031.536929 | -5.4828405488119065 |
| [.2,.4) | 21 | 16497 | 187909.123151 | 0.9556879635472382 |
| [.4,.6) | 28 | 21367 | 256514.809061 | -1.1583379469318091 |
| [.6,.8) | 20 | 14194 | 164874.042308 | -3.263655441674611 |
| [.8,1] | 17 | 23036 | 532440.762929 | -3.478706756787533 |
| [0,.2) | 16 | 19135 | 364087.436908 | 1.224258715940033 |

Strata overlap across events and are descriptive; directions and price bins are separate, not crossed into searched cells. Cells with fewer than five events do not establish a stable pattern. Full per-day strata, event aggregates and denominators are in `settlement_aggregate.json`.

Removing the largest-share event changes the primary value to **-0.200212 cents/share**. Removing the largest absolute total-value event changes it to **-0.505378 cents/share**; the same event also has the largest absolute contribution under primary weights. The largest event accounts for 11.10% of measured shares. These checks do not supply long-run confidence from three dates.

## Correctness and resources

Eleven focused synthetic tests pass: buy/sell arithmetic, complementary-token invariance, invalid inputs, fixed price boundaries, payout direction, hierarchical weights, unresolved payments, duplicate conflicts, taker exclusion, unknown-token quarantine and identical duplicate handling. Actual execution rechecked six frozen cache hashes. No hourly raw files or network responses were reread for P1. Cached input size: 111,314,096 bytes; scoring wall time 3.904 s and CPU 3.876 s, macOS peak process RSS 624,852,992 bytes. Preparation/tests are not included in that timed scorer.

Reproduction: run `python scripts/polymarket_settlement_value.py --repo . --public <new-aggregate-json> --private <private-row-json>` with the frozen private caches. The program refuses to replace outputs. Run `python tests/test_polymarket_settlement_value.py` for synthetic checks. Row-level values and identifiers remain private.

Original A remains `STOP / DATA_GATED`; old quantity expansion remains stopped. No independent final data were opened.
