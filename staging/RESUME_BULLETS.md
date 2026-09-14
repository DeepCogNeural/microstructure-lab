# Role-targeted resume bullets

Use only the version fitting the available space. Compact variants target roughly two lines, but actual wrapping depends on font and column width. All claims are linked in [the evidence registry](CLAIMS_EVIDENCE.md). These variants describe the same completed work; they do not imply employer affiliation.

## DV / market-microstructure QR

**A — compact**

- Reconstructed 85.8M order messages across five equities; benchmarked causal order-book signals with Linear/XGBoost and tested their limits under spread and latency.

**B — detailed**

- Reconstructed 85.8M messages into 56.9M causal L2 rows; compared imbalance, OFI and microprice signals with Linear/XGBoost under fixed chronological holdouts, finding modest IC gains across three horizons.
- Built a hash-verified, resumable Parquet workflow; measured 17.3× training and 9.1× end-to-end accelerator speedups on a fixed task and retained negative crossed-book results.

Why: leads with order-book mechanics, tree models and execution realism; engineering supports the research result.

## AQR-style QR

**A — compact**

- Evaluated five-equity order-book signals with frozen chronological holdouts and shuffled controls; modest XGBoost IC gains survived leave-one-stock/month checks.

**B — detailed**

- Designed a five-equity chronological study over 56.9M causal L2 rows, using within-day shuffled controls and equal-weight stock/month evaluation without final-test hyperparameter search.
- Measured XGBoost–Linear IC gains of 0.0064–0.0084 at 10/20 messages and 0.0062 at 50; reported paired robustness and negative spread/latency diagnostics without significance or profitability claims.

Why: emphasizes statistical discipline, baseline strength and restrained interpretation. Accelerator timing is secondary.

## PIMCO-style quantitative research

**A — compact**

- Built a reproducible time-series research pipeline over 85.8M market events, with partitioned caching and chronological Linear/XGBoost comparisons across five instruments.

**B — detailed**

- Processed 85.8M historical events into 56.9M causal feature rows across five instruments; compared linear and boosted-tree forecasts using fixed out-of-sample periods and negative controls.
- Implemented deterministic experiment manifests, hashed Parquet partitions and resumable tasks; separated modest forecast-ranking improvements from execution costs and model limitations.

Why: stresses large-scale historical research and reproducibility, with less high-frequency trading vocabulary.

## General Quant Research

**A — compact**

- Built an 85.8M-event microstructure pipeline; compared Linear/XGBoost with chronological holdouts and controls, then stress-tested spread, latency and held-out-stock transfer.

**B — detailed**

- Constructed 56.9M causal order-book rows across five equities; XGBoost modestly improved held-out rank correlation over Linear at three fixed message horizons.
- Built a restartable, hash-verified experiment system with 152 completed benchmark tasks; added paired robustness, spread/latency diagnostics and 25 held-out-stock transfer tasks.

Why: balances research design, measurable results and systems ownership.

## Quant Trading

**A — compact**

- Tested imbalance, OFI and microprice signals across five equities; positive midpoint ranking did not produce positive crossed-book outcomes after spread and latency.

**B — detailed**

- Studied short-horizon order-book signals across five equities, comparing Linear/XGBoost on fixed historical holdouts and tracing how spread and delay changed outcomes.
- Built a resumable 85.8M-message research pipeline; used negative execution results to distinguish predictive rankings from a demonstrated trading opportunity.

Why: leads with market intuition and execution judgment. Do not substitute “profitable strategy” or “realized alpha.”

## Wording boundaries

Do not write that 56.9M rows are independent observations, all 1,250 partitions entered model evaluation, the timing ratios generalize to arbitrary hardware, or the passive study identifies real fills. The optional queue detail belongs in an interview answer with its identification caveat, not an unqualified resume claim.
