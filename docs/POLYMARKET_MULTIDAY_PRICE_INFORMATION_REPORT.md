# Polymarket BTC-5m multiday price information: input budget stop

**Status: `ACCESS_OR_BUDGET_BLOCKED` (2026-09-24 UTC).** The frozen 2026-07-27 through 2026-08-02 UTC window cannot be extracted under the authorized 96 GiB compressed-source limit. The complete private source manifest lists **356 objects / 111,190,706,438 bytes**, exceeding **103,079,215,104 bytes** by **8,111,491,334 bytes**. The 168 canonical CLOB hourly objects alone total **104,620,375,984 bytes**, already **1,541,160,880 bytes** above the limit. No date, hour, variant, model, or threshold was removed to force a result.

| UTC day | Frozen role | CLOB objects / bytes | All listed objects / bytes |
|---|---|---:|---:|
| 07-27 | train | 24 / 16,589,467,438 | 50 / 17,431,944,919 |
| 07-28 | train | 25 / 15,870,661,995 | 53 / 16,778,686,730 |
| 07-29 | train | 24 / 17,127,430,555 | 50 / 18,079,996,705 |
| 07-30 | calibration | 24 / 15,559,547,314 | 50 / 16,427,958,811 |
| 07-31 | forward check 1 | 24 / 14,788,819,468 | 50 / 15,684,014,216 |
| 08-01 | forward check 2 | 25 / 12,837,401,708 | 53 / 13,771,711,853 |
| 08-02 | forward check 3 | 24 / 12,172,216,007 | 50 / 13,016,393,204 |

The remaining manifest objects are 172 on-chain objects / 6,073,991,705 bytes and 14 daily index objects / 171,170,248 bytes. The two noncanonical CLOB objects are included in the total. This is a **manifest count**, not proof of readable content, continuous capture, or an event roster. A local size-only check matched 12 of these 356 objects (three CLOB, three on-chain, six indexes; 1,718,042,410 bytes); Drive availability was not checked and is not inferred from this local count.

The stop occurred before market-object decompression or event extraction. Therefore confirmed events, Up-token identity, CTF settlement labels, end-minus-120-second BBO, 30-second history, and valid snapshot counts are **unknown**, not zero. The planned minimums (train ≥400, calibration ≥100, each of three checks ≥100; both train and calibration contain both labels) were not evaluated. R0 raw price, R1 calibrated price, R2 price/spread/move and the R3 snapshot-depth increment were **not fitted or scored**. There is no R3-versus-R2 finding and no evidence for or against continuing the quantity direction. No protected final data were opened. The existing Quote-or-Pull A decision remains **`STOP / DATA_GATED`**.

## Reproduction and limits

`results/polymarket_multiday_price_v1/preflight.json` records the frozen roles, per-day and per-kind counts, exact budget comparison, source ZIP SHA-256 `705c873ee9cd0f31fa455bc167dbf725218f69a03ae7fa933b19af3dbd710674`, and manifest SHA-256 `db969fce2d2bf554743fbe486e6537066b826326771c4de48ec41f4b2019e109`. The manifest was read from the existing private Rocklabs ZIP using `scripts/polymarket_multiday_price_preflight.py`; URLs never enter the public output. Two synthetic parser/budget tests passed. This batch read **zero CLOB/on-chain compressed objects**, made **zero official identity/settlement requests**, fitted **zero models**, and used **zero GPU**. Raw data, signed URLs, event-level prices/labels and predictions remain private. The manifest comes from the Rocklabs academic research source; path and size metadata do not certify content or upstream integrity.

The protocol's explicit response to this over-budget fixed window is to stop extraction and report the exact bytes. Any later study would require a separately authorized budget or source plan; this report does not release a final cohort or change A's gate.
