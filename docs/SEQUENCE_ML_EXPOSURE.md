# Sequence ML v1: development-data exposure and Q1 pilot

This record is for the retrospective WSELOB-2017 sequence study. It is not a new sealed holdout or a claim of future-market confirmation.

## Source and exposure

- Source: Marszałek, Adam (2023), WSELOB-2017 V1, DOI `10.17632/3g4mhdp899.1`, CC BY 4.0; the public source registry is `configs/wselob_sources_v1.json`. Replay, causal features and diagnostics are modifications. Raw files and row-level model data stay outside Git.
- Existing development cache: `data/cache/wselob_application/manifest.json`, SHA-256 `6b426a633bda5d1d767a6346f5838a9df4cc1df2e0f0589b88ae27c56ba7988d`; 1,235 stock/day partitions, five stocks, 2017-01-02 through 2017-12-22. The cache records source hash `7919375bb0b82faba250a0e1adc1c18704a494fa766591f39b5f93e9220d8ebb` and configuration hash `2457a7f5f20dc552bbe9479d9c8769e38256c209ff699f00b2b4690287bc6cc7`. The Q1 pilot freshly verified the SHA-256 of all 1,235 feature files against this manifest. The manifest's five raw-file hashes are inherited receipts; this pilot did not freshly rehash all five raw files.
- The original prediction study used April, June, September and November as test months, with earlier dates supplying training history. The explanatory audit, execution work and later December 27–29 confirmation exposed additional outcomes; see `docs/SIGNAL_EXECUTION_DIAGNOSTICS_REPORT.md` and `docs/LATER_PARTITIONS_CONFIRMATION_REPORT.md`. The latter three dates are **three shared trading days**, and are no longer available as a new independent final set. No 2017 WSE date is represented here as newly sealed.
- The Q1 sequence study uses the previously inspected 2017 cache for development. Any new train/dev/evaluation split is chronological but remains retrospective/exploratory. Five stock/day partitions on 2017-01-02 were opened for the Q1 resource/correctness pilot; that date was already part of the exposed development period.
- This cache has original event identity and `markout_20` in the same Parquet files. The new window builder reads the states in original order before considering endpoint label eligibility. `scale_runner.load_fold` is unsuitable for rolling windows because it drops rows with missing future labels first.

## Q1 correctness and measured denominator

The implementation uses 32 consecutive, finite causal states from the existing five-feature set within one symbol/day/segment. It retains original `event_index` and `timestamp_ns`; the h20 label remains an offset of original messages. It never carries recurrent hidden state between endpoints. The same eligible endpoints and historical information will be used by all history arms. Current-state arms use those same endpoints. Stride-20 scoring anchors on original `event_index` and is outcome independent.

The five-stock 2017-01-02 pilot read **215,604 states**, found **214,449 valid 32-state windows**, **213,972 scorable endpoints** and **10,698 stride-20 scored endpoints**. These are one-day engineering denominators, not training set sizes or independent observations. Per-stock counts and cached-file hashes are in `results/sequence_ml_v1/q1_pilot.json`. The pilot wall time was 1.44 seconds on the local CPU process; its peak RSS is recorded in bytes in the JSON. No real-data model was fit and no GPU hours were spent.

Eight focused tests passed: future labels do not change window token selection, future state changes do not change past windows, event gaps/nonfinite states break windows, stride uses source event identity, duplicate identities fail, and model round-trip, parameter update/tiny-batch overfit and no carried GRU state work on synthetic data. A synthetic control is a code check, not empirical validation. The full five-arm training remains Q2.

## Remaining boundary

No independent confirmation data has been qualified. A new source would require provenance, license, schema, date and non-exposure checks before final labels or outcomes are viewed. The legacy historical non-exposure claim for Dec 27–29 does not transfer to this new experiment.
