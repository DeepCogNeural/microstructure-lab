# PM2 structural as-of provenance gate

Status: **ASOF_STRIKE_PROVENANCE_UNVERIFIED**. This is a source-only gate on the free OutcomeTick `samples-2026-09-08` archive, SHA-256 `9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506`, already pinned in PM0. No model was fitted, no final model outcome opened, and no paid data was obtained.

The audit joined the 292 market metadata records to the first **received** book event for each slug. Book events covered 290 markets; two metadata markets had no book event. All 290 matched metadata snapshots have `updatedAt` after both their first received book and scheduled close. Eighteen matched markets have no `strike_value`. The matched records share one settlement description and one Chainlink TWAP-60 resolution URL. These facts document source fields; they do **not** establish when a market participant could observe a particular strike or any historical version of the rule.

The metadata file is therefore unsuitable as a decision-time strike/rule table without an independently timestamped historical as-of record. Feeding its post-close fields into a structural model would risk hindsight leakage. The archive includes Chainlink raw and TWAP streams with timestamps, but this audit does not validate a clean as-of join of strike, underlying, rule, token, decision state and settlement stream. PM2 structural models remain gated pending that full provenance; no structural fair-value or residual-information result is claimed. PM3 exact-fill evidence is separate.

Reproduce the aggregate receipt with `scripts/audit_polymarket_pm2_asof.py --archive <OutcomeTick-free-sample.tar.gz> --out <new-result.json>`. The public receipt has counts and source hash only; no raw rows or per-market data are published.
