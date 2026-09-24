# Rocklabs B quote correctness closeout

**Decision:** The fixed B cohort has verified event/token identity and post hoc binary CTF settlement for 32/32 events. Corrected decision-time direct BBO coverage is **24/32**; the separate full-book **top-price** coverage is **25/32**. This is a data-connection result for a selected development cohort, not a fitted prediction result. The original passive-maker Quote or Pull study remains `STOP / DATA_GATED` pending Rocklabs' match-time and causal L2 semantics.

This closes the single correction requested by Advisor after reviewing science commit `d606417c59bb03600f838d437a92a0d77662a834`. The original v1 report and aggregate remain unchanged in Git. The private v1 32-row table was preserved byte-for-byte at SHA-256 `f928e2b6c392f55c789ad5fda0bd4be2dfd8730ec91d6d3728e73a95df4f81b9`. The new table has SHA-256 `4467d01b17ed5e87e0579b3f51be8127da1d78229de075d0a2d58779743f641c`. Both remain gitignored; public v2 totals and hashes are in `results/rocklabs_qop_b_connection_v2/summary.json`.

## Exact changes

1. The received timestamp now stays at integer **microsecond** precision from the raw ISO field. A record is eligible only when `receive_us <= decision_ms * 1000`. This excludes a record received even 0.5 ms after the decision; no exchange-time or future-snapshot ordering is used. The scanned 32 events had **zero** Up-token BBO/book records in the post-decision submillisecond boundary bucket. Comparing the field-only intermediate audit with the exact-time result gave **zero** status or quote-value changes in these 32 rows. This is a bounded observation, not proof that millisecond truncation is safe generally.
2. Same-receive-time conflicts now compare the **required quote**, after numeric normalization. For `price_change`, this is `(best_bid,best_ask)`. For a `book` snapshot, it is the best bid and ask prices only. Different message hashes, changed levels, or changed sizes alone cannot invalidate equal top prices. If required top prices differ with no reliable order, the event still fails closed. A valid top-price gate never certifies top sizes, depth, or a complete replayed L2.
3. Selection still takes the latest eligible raw record **before** validity and age checks. An invalid or stale latest record cannot be replaced with an older valid record. Direct BBO retains the 1,000 ms limit; snapshot top retains the separate 5,000 ms limit. No identity, payout, cohort, date, source file, or age threshold changed. The correction made **zero new network requests**.

| UTC date | Fixed events | v1 direct BBO | corrected direct BBO | v1 snapshot top | corrected snapshot top |
|---|---:|---:|---:|---:|---:|
| 2026-07-28 | 8 | 1 | 1 | 2 | 2 |
| 2026-07-29 | 11 | 9 | 11 | 11 | 11 |
| 2026-07-30 | 13 | 10 | 12 | 12 | 12 |
| **Total** | **32** | **20** | **24** | **25** | **25** |

Of the **eight** v1 BBO conflicts, four become valid quotes, three become stale once identical top prices are no longer called conflicts, and one remains a true top-price conflict. The sole v1 snapshot conflict had equal top prices but is stale under the unchanged five-second limit. Final direct-BBO failures are **one true conflict and seven stale** (six on 07-28, one on 07-30); final snapshot-top failures are **seven stale**. The very weak 07-28 coverage remains 1/8 direct BBO and 2/8 snapshot top. It must remain separate from the higher coverage on the other two days.

Five synthetic checks in `scripts/test_rocklabs_b_quote_closeout.py` passed: a record 0.5 ms after the cutoff is excluded; different messages with identical top prices pass; real top-price disagreement fails; numerically equal string prices compare equal; the latest invalid record cannot fall back to an older valid one. The three original CLOB source SHA-256 values were checked again by the extractor, and the public-repo privacy guard passed. The v2 manifest records the fixed roster, parent commit, private evidence hashes, and exact correction scope.

**Stop:** No model, score, PnL, additional date, final data, receipt expansion, or new A replay was run. Current Gamma and latest CTF replies still only establish identity and **post hoc** settlement; label publication time and historical rule-version availability remain unknown. The 32 events were selected from observed prints and cannot establish population coverage. Advisor's bounded science closeout is satisfied; any multi-day B study needs a new fixed design and authorization. The Drive archival task continues independently.
