# Quote-or-Pull R0: measurement gate

**STOP — the inspected development archive does not support the specified 5-second passive-fill estimand.** This is a data-validity result. No model was fit, no markout or candidate outcome was inspected, and no fresh confirmation price path was opened. R1 remains unauthorized.

## Label-blind choice

At metadata/schema level, two non-political binary families were considered: archived weather temperature brackets and sports markets. The sports archive has broader date coverage but its public-trade schema does not retain order ID, maker/taker role or exchange match time. Weather has own GTC order/fill/lot associations and partial match-time telemetry. Applying the predefined rights → role/clock observability → development coverage → extraction-cost order, weather YES tokens were selected as the R0 diagnostic family without inspecting markouts. This source choice does **not** imply that role or clock gates passed. Redistribution rights for raw private data or third-party sports rows were not assumed.

The fixed two-day development window supplied the requested 20 candidate YES-token buy-fill traces. The row-level trace and analysis script remain in ignored local `_private/`; their SHA-256 hashes are respectively `d78a1f13b0b07457889370ebd9e7247e92158be692ae03da892948add701b501` and `8fe3030b87e12eceb1b36d4083dcc2e2f9ca19be625b6e06a2394cedcbb9331f`. The private index maps all 20 traces to source rows and records order/lot/trade, partial-fill, clock-anchor and BBO checks. No account/order IDs, prices, sizes or row-level data are published.

## R0 gates

| Gate | Evidence from the fixed 20-leg trace | Result |
|---|---|---|
| G1 actual passive role | All 20 have local exact-order, active-order, lot and own-trade joins, but none has an independently retained exchange maker-side receipt. The historical code accepts an order found as either taker or maker and stores only its time. A repeated order shows partial fills; counterparty-level one-to-many structure cannot be recovered. No verified passive sell leg is present in this source. | 0 independently verified maker; 20 role-unknown. **FAIL** |
| G2 match/receive time | Local `filled_at` is booking `Date.now()`. Only two of 20 have a nearby order-level `match` anchor; these anchors are whole-second values. In the larger two-token window, eight `match` anchors lag local detection by 16.330–114.933 s; repeated fills are collapsed to the latest order-level match time. No validated subsecond offset/error bound. | 5-second horizon and lead time **FAIL** |
| G3 BBO/target state | A city+temperature proxy yields both sides for 16/20; four are incomplete. The complete prior quotes are 0.467–26.374 s old (median 21.343 s); only two are at most 5 s old. Only three legs have a new complete snapshot within the following 5 s. Snapshots lack condition/token ID and sequence/reset evidence; no book-tape samples join the traced legs. | Contract identity, replay and 5-second target **FAIL** |
| G4 timely flow | The same-window source does not contain side-validated, prospectively received public aggressor flow. The separate weather L2 raw dates do not overlap this fill window. Ex-post trade direction cannot be promoted to a feature. | **NO** for M2 |
| G5 intersection | None of the 20 candidates is certified across true maker role, match clock, exact-token BBO and valid 5-second target. Unknowns were not assigned zero outcomes. | 0/20 measurable; **FAIL** |
| G6 final | Prior weather/sports and public pilot samples remain development-exposed. A later pmxt block is metadata-only `POTENTIALLY_FRESH_PENDING_AUDIT`; HEAD-only availability checks failed local DNS. No price/target/outcome access and zero new data bytes. | Future confirmation unqualified |

The decisive failure is semantic, not statistical: the source's order-ID join proves an accounting chain but not historical passive role; its match lookup retains neither maker/taker classification nor leg-level time, and the sparse market-level snapshots do not prove exact-token BBO. A longer horizon, new parser, or model fit would change the approved research question. **STOP this source/path and wait for reviewer direction.**

## Lineage and limits

- Source snapshot SHA-256: weather `latest.db` `0ddc1894c5e7371e2d66b9efae01b8ad6c5469fe66e8470f8140e24bb57e0c52`; second weather compressed backup `d0227b59ac5c02d9a6d284f9f715c684e7b822ed956fc4d9dec55b70a30aa9f1`; sports research compressed archive `3aea24e26b018f1df3b3a6e75eb7e4f80e3c09fbfd11c4cac1353a6ac9262d53`.
- Historical fill-path source commit `8fed65ddcadde03f5b92cd25c736630d2d9a5e8d`; fill source SHA-256 `8ab7ed7b443cb75b157b090898103ca0d4bde854878e39c59910661c1bc68352`; book-tape source SHA-256 `1c59002351353f7e92f13f62607ffc6b2d44d5b6309fcf9ada5503f7a35`. V3 plan SHA-256 `8b3d289ba287a0a5df3ef283ff732257f866293bcbaf2ae229bea71f55d89e76`, reviewed design commit `653ed37da7f4942178a8d24b011cec5d58dfabc3`. R0 has no model configuration.
- CPU/I/O only, 0 GPU, 0 new data bytes, no AWS restart, live order mutation, paid acquisition or fitting. This R0 does not establish label accuracy or a performance result.
