# Q3 bounded robustness and visible crossing

This is a retrospective continuation of the five-stock WSELOB-2017 sequence study, using the precommitted `configs/sequence_ml_q3_v1.json` and `docs/SEQUENCE_ML_Q3_PROTOCOL.md`. All evaluation dates had prior research exposure. The fixed Q2 model choice was historical XGBoost B* versus one-layer GRU S0 with seeds 7/17/29. These results do not establish independent prediction or trading profit.

## Denominators and checks

All **15/15** planned rolling stock/month refits completed: June, September and November × five stocks, each comparing B* and all three GRU seeds. Every updated score was paired to the fixed Q2 model on the **same 625,118 original-event scoring rows** across **315 stock/day cells**. A source-event, day and h20-label mismatch would have stopped a task. The state and crossing diagnostics rehashed the source feature partitions and private Q2 prediction artifacts against their public receipts. Every one of the 625,118 scoring rows had a matched original event+20 inside the same segment with finite current and future spread. Two synthetic tests passed for exact feature-based crossing equivalence to the existing quote evaluator and for rejecting event/segment gaps.

## One decision-time state split

The state rule used elapsed time over the already observed 32-state context, with each stock's cutoff frozen at the median of its sampled Jan–Mar training endpoints. Shorter positive duration means higher past activity; this is a descriptive decision-time state, not an unseen regime. Both slices have **315/315 defined stock/day IC cells**:

| State | Scored rows | B* mean IC | GRU three-prediction mean IC | Paired ΔIC |
| --- | ---: | ---: | ---: | ---: |
| Higher past activity | 297,926 | 0.239156 | 0.252849 | +0.013693 |
| Lower past activity | 327,192 | 0.290237 | 0.293519 | +0.003282 |

This uses the IC of the arithmetic mean of the three seed predictions, whereas Q2's primary seed mean averaged three seed-specific ICs. They answer related but different aggregation questions. The larger high-activity gap is historical state-conditioned robustness, not evidence of crisis generalization or an independently validated regime selector.

## Fixed versus frozen-rule updates

The fixed model's information cutoff includes April dev. Updates used equal 20,000-endpoint per-stock training caps and the same model settings, with Feb–Apr/May dev before June, May–Jul/Aug dev before September, and Jul–Sep/Oct dev before November. Each comparison has **105 stock/day cells** per month and identical evaluation rows.

| Evaluation month | B* updated − fixed IC | GRU seed 7 | GRU seed 17 | GRU seed 29 |
| --- | ---: | ---: | ---: | ---: |
| June | +0.001533 | +0.001299 | −0.003502 | −0.002888 |
| September | +0.003002 | +0.003559 | −0.000646 | +0.003365 |
| November | +0.009208 | +0.006911 | +0.006308 | +0.008905 |

November's fixed scores were lower than September's for both models, and updated models improved in November, but the change cannot be called causal temporal decay: calendar conditions, newer training information and the changed training window move together. Negative update differences in June/September GRU seeds are preserved. The 15 updates consumed **1,040.09 seconds total wall time** on local CPU with four configured threads per task and **0 GPU-hours**. Actual CPU core-hours were not measured. Eight updated seed/stock/month fits across five stock/month cells reached the 15-epoch cap with best dev loss at the last epoch; their exact identities and curves remain in the JSON receipts.

## Fixed crossing at one unit

At each original event t, the unchanged strict `|prediction| > 1 bp` rule crosses visible ask/bid immediately and exits at the opposite quote at event t+20 in the same segment. The cache supplies an exact algebraic reconstruction from current spread, event+20 spread and midpoint markout. No fees, market impact, queue, inventory, actual fills or cash PnL were modeled. All rules share **625,118 eligible decision opportunities**:

| Prediction used for action | Selected | Coverage | Equal-stock/day visible crossed markout | Pooled selected markout, descriptive |
| --- | ---: | ---: | ---: | ---: |
| B* | 43,122 | 6.90% | −7.818 bp | −7.778 bp |
| GRU seed-mean prediction | 30,590 | 4.89% | −6.352 bp | −6.210 bp |

All **315/315** stock/day selected-markout cells were defined for each primary action. On the **14,989 opportunities selected by both** rules, pooled visible crossed markout was −5.991 bp for B* and −5.994 bp for the GRU mean; both remained negative. The two models ordinarily select different opportunities and coverage, so the all-selected difference is not a causal effect of replacing one model. Even on common selected opportunities, no profitable crossing claim follows. Per-seed negative results and all cell counts are retained in `results/sequence_ml_v1/q3_summary.json` and the five diagnostic receipts.

## Model and stage boundary

Q2's modest positive historical predictive difference survives this one state split, but it does not pay the fixed visible crossing rule. Updated fits offer mixed time effects and add more training-limit receipts. LOSO was not run: this stage had no frozen source-only inner chronological selection contract for five outer held-out stocks, and adding it after observed scores would widen the study beyond the bounded protocol. The Q4 Transformer gate must be evaluated from every stated condition; positive retrospective IC alone is insufficient. Independent confirmation remains pending.
