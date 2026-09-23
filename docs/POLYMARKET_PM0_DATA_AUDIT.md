# Polymarket public L2 PM0 audit

Date: 2026-09-23. Stage: PM0. No model was fitted and no terminal outcome was inspected to select the split or features.

## Pinned sources

| Source | Exact version and provenance | Contents used | Limits |
| --- | --- | --- | --- |
| [PolyOrderbooks Zenodo](https://doi.org/10.5281/zenodo.22084977) | v1.0.1, record 22084977, CC BY 4.0; file MD5 checked against Zenodo and SHA-256 recorded in `results/polymarket_pm0_v1/polyorderbooks_audit.json` | Three Parquet files: 5m, 15m, 4h crypto Up/Down books | Collector snapshots, sparse changed-book cadence; sampled markets over four UTC days. Collector time is not exchange event time. |
| [OutcomeTick free sample](https://github.com/Ligengxin96/polymarket-data-samples) | GitHub release `samples-2026-09-08`, release id 386891317, archive SHA-256 `9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506`; eight file SHA-256 values in `outcometick_sample_audit.json` | One-day BTC 5m book, delta, top, trade, metadata, and Chainlink price/TWAP feeds | Parser/provenance audit only. A one-day sample cannot support a broad final study. |

Public raw source files remain outside Git. These machine-readable manifests contain aggregate counts, schema, hashes, and frozen market IDs; they contain no private live-account events. Reproduce with `scripts/audit_polymarket_pm0.py`, `scripts/audit_outcometick_sample.py`, and `scripts/freeze_polymarket_pm1_split.py`.

## PolyOrderbooks identity and integrity

| Item | Audited value |
| --- | ---: |
| Rows / markets / tokens | 897,192 / 805 / 1,610 |
| Assets / contract lengths | 8 / 5m, 15m, 4h |
| Markets by length | 471 / 265 / 69 |
| Capture window, UTC | 2026-08-21 00:14:09 to 2026-08-24 12:29:59 |
| Valid two-sided, unlocked, uncrossed midpoint rows | 824,091 (91.85%) |
| Valid midpoint and strictly before scheduled market end | 824,075 |
| Empty bid / empty ask flags | 26,465 / 26,447 |
| Strictly crossed / locked book flags | 15,489 / 4,700 |
| At or after scheduled end | 748 |
| Exactly 1-second / over 1-second within-token capture gaps | 515,920 / 379,662 |
| Clean same-capture Up/Down quote pairs | 407,738 |
| Pair bid-sum above 1 / ask-sum below 1 | 38 / 35 |

Flags can overlap. No duplicate token/capture identities, ladder length/order errors, nonpositive sizes, invalid prices, top-of-book mismatches, or provider crossed-flag mismatches were observed by the audit. A gap above one second is not automatically missing data: the source records changed books sparsely. Opposite-token quote checks describe snapshots, not executable arbitrage or fills. Raw terminal labels were not used in PM0.

The two-sided pre-close count is an upper bound for PM1 eligibility. Market-level fixed-cadence selection, minimum time to close, and complete causal history will reduce it. No midpoint is imputed for a one-sided or crossed row.

## Frozen PM1A split and feasibility

The market-ID manifest `results/polymarket_pm0_v1/pm1a_split_v1.json` was generated without terminal outcomes. Whole markets with scheduled end by 2026-08-23 00:00 UTC are train (431); markets starting at/after that cutoff and ending by 2026-08-24 00:00 UTC are dev (241); markets starting at/after Aug 24 00:00 UTC are final (122). Eleven boundary-spanning markets are purged. The sets are disjoint. Each group includes all eight assets and all three lengths, but final covers only about half of Aug 24 UTC. It supports a narrow chronological pilot, not durable out-of-time generalization.

PM1A terminal calibration is technically feasible because the open source has terminal labels and pre-close quote observations, subject to the frozen eligibility/cadence contract in `configs/polymarket_pm1a_v1.json`. P0 raw market midpoint remains the required benchmark. PM1B repricing is technically possible but requires a separate denominator audit and one frozen horizon before fitting; sparse captures are not a regular 1-second panel. PM2 is **not yet cleared**: the open Parquet has no native strike/underlying time series, and the OutcomeTick one-day sample has strike missing for 18 of 292 metadata rows. The sample contains price/TWAP feeds but exact as-of market-strike-settlement joins were not validated by this audit. PM3 is **not cleared** by snapshots; the public one-day event/trade sample supports only a bounded parser/replay feasibility check. No paid data is authorized.

## OutcomeTick free sample audit

The free sample includes 141,402 full book rows, 3,516,537 price-change messages, 1,314,078 best-bid/ask messages, 480,491 trade prints, 292 metadata rows, and 81,970 raw / 81,946 30-second TWAP / 81,969 60-second TWAP Chainlink rows. Event streams cover 290 slugs, while the metadata file has 292; this difference has not been resolved into a complete join. The sample audit checks field types, timestamps, row counts, release hashes and selected metadata coverage. It does not prove a replay or settlement calculation. Provider claims about settlement accuracy remain provider claims.

## Research boundary

No independent confirmation of the equity microstructure results is claimed. PM1A will evaluate one token per market, market-clustered uncertainty, and fixed evaluation opportunities. Short date span and market selection make even a positive final result exploratory. Preserve a raw-price win, failed model, or null result. Snapshot markouts cannot be described as realized P&L.
