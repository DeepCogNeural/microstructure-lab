# OutcomeTick R0 observer diagnostic — receive-time descriptive measurement

**Verdict: `DIAGNOSTIC_COMPLETE_REVIEW_REQUIRED`; `DEVELOPMENT_OBSERVER_DIAGNOSTIC / NOT_ACTIONABLE_QOP`.** The fixed cached sample supports a narrow gross midprice description after quote receipt. It does not pass the original 5-second match-clock and cancellation-lead study: the prior **0/14 actionable gate remains STOP/DATA_GATED**. No model, prediction score, policy simulation or terminal outcome was opened.

## Frozen scope and correctness repair

The [pre-calculation freeze](POLYMARKET_QOP_OBSERVER_DIAGNOSTIC_FREEZE.md) was pushed at scientific commit `0d3b1aa414cf4acaa413ff59c28d5d2e103b7bd7` before any actual receipt/quote price difference was calculated. The source is the same free OutcomeTick `samples-2026-09-08` archive, SHA-256 `9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506`; no new bytes, dates, markets, hashes or receipts were obtained. The fixed 20 candidates, in 2 of the 3 originally selected markets, remain unchanged. The R0 `288 complete markets` wording referred only to first/last-30-second stream presence, not uninterrupted middle coverage.

The new script filters `OrderFilled` and `OrdersMatched` to the receipt's destination exchange, requires a complete single log page, and consumes one unique maker event per maker input. It reconciles token, side, maker, amount and fee, and derives each leg's shares and price from that leg's asset amounts. All **20/20** receipts still join; all **30** original passive legs remain, **14** on the selected token (13 BUY, 1 SELL), totaling **73.671250 shares**. No role, token, side or size mismatch excluded a candidate. This repairs the old `all(any(...))` reuse risk without pretending the older price comparison proved print semantics.

The public print price is **not an exact per-leg price**: 4/20 prints differ nonzero from the receipt's aggregate taker price (range of print minus taker: `-0.0042785714` to `+0.0000000225` dollars/share), and 1/14 selected-token legs differs from its print by `-0.01` dollars/share. Print price may describe a last fill or rounded/batched representation; this dataset and audit do not establish which. No verified tick/rounding rule supports the former uniform `< $0.011` tolerance. Receipt prices alone enter the diagnostic. Selected maker fee event fields total zero for both sides, and fees are excluded from the gross measure; fee units were not independently interpreted.

The exact-token BBO is validated numerically as finite `0 < bid < ask < 1`. The latest raw record is chosen before validity checks, with no fallback. One target endpoint had conflicting prices at the same receive millisecond and no defensible ordering; one other target quote was 5.142 seconds old. Those legs remain NA. A two-sided string field alone is not a valid quote check. No independently verified feed disconnect or complete message sequence was available; the receive-age restriction selects actively updating observations and is not an uptime certificate. BBO has no touch sizes.

## Gross cents per share, share-weighted

`r` is collector receipt of the associated trade print, not the maker-leg match time. For a passive BUY `d=+1`, SELL `d=-1`, receipt leg price `q` and observed midpoint `m`: `G=100d(m_r-q)`, `D=100d(m_{r+5s}-m_r)`, `N=G+D`. A shared print may anchor multiple maker legs. All figures below are **cents/share**, before any execution costs; the same fill can contribute several correlated legs.

| Quote age at both endpoints | Eligible legs / prints / markets | Shares | G weighted mean [range] | D weighted mean [range] | N weighted mean [range] |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1000 ms primary | 12 / 7 / 1 | 67.051250 | +0.521 [-2.000, +1.000] | +1.504 [-3.000, +7.500] | +2.025 [-2.500, +5.500] |
| 250 ms sensitivity | 5 / 3 / 1 | 29.020000 | +0.551 [-1.000, +1.000] | +1.810 [0, +3.500] | +2.361 [-0.500, +4.500] |

The stricter 250 ms set is exactly the common eligible set; on those same five legs, the 1000 ms calculation is identical, so the mean change above is entirely a **denominator/composition change**. Primary eligible legs comprise 11 BUY and 1 SELL; the 250 ms set comprises 5 BUY and 0 SELL. Market M1 contains 13 selected legs, 12 primary eligible and 5 sensitivity eligible. Market M2 contains 1 selected leg, **0 eligible**, because its target quote is stale; its G/D/N are NA, not zero. Thus the total is a one-market descriptive aggregate and cannot be read as a two-market replication.

The largest eligible leg is **15 shares**. Removing it gives primary G/D/N means **+0.383 / +0.929 / +1.312** cents/share over 11 legs and 52.051250 shares. In the 250 ms set, removal gives **+0.071 / +0.002 / +0.073** over 4 legs and 14.020000 shares. The sensitivity set's apparent positive D and N is therefore dominated by one fill. Ranges, denominator and this removal are descriptions, not inferential tests. No confidence interval, fill bootstrap or significance statistic was calculated.

## Meaning and stop

G includes price movement between execution and public message receipt, so it is not pure spread capture. D starts at message receipt, so it is not complete post-fill adverse selection. N is a 5-second observed midpoint mark, not an attainable exit, cancellation value or strategy P&L. The sample was preselected by print direction and token, has only two candidate markets and one market with valid endpoints, and cannot estimate maker profitability or screening alpha. The positive weighted N on this selected subset does not revive the v3 thesis.

The smallest missing evidence for the original actionable question is an independently verified per-leg exchange match clock with a bounded error small enough to order the quote and trade/withdrawal decision. Size-aware order-book state and a causal decision path would then need separate qualification. The print source-to-receive lag and whole-second chain timestamp do not provide that match-time bound. This checkpoint ends the authorized observer diagnostic and requires reviewer decision before any next stage.

## Reproduction and budget

Run `python3 scripts/qop_observer_diagnostic.py --self-test`, then the frozen script with the pinned sample root/archive and the ignored private 20-receipt and fixed-index files. Aggregate output: `results/polymarket_qop_observer_v1/aggregate.json`; private row-level joins remain ignored in `_private/qop_outcometick_r0/`. Synthetic checks cover BUY/SELL asset arithmetic, invalid and tied quotes, strict endpoint order, staleness and one-to-one event matching. Same-sample execution reported 20 joins, 14 selected legs, 12/5 eligible. One CPU, 0 GPU, 0 new source data and no network receipt fetch. The public aggregate and this report contain no raw transaction hashes, addresses or row-level prices.
