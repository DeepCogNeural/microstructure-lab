# Q8 matched-context sensitivity — formal retrospective report

Status: **complete; April selected 128 causal states**. This experiment used the prefit Q8 protocol and code at commit `003d24944b9a6f47ba6e7bf6cb8813e4f992c20d`. The WSELOB-2017 V1 source feature-cache manifest is `6b426a633bda5d1d767a6346f5838a9df4cc1df2e0f0589b88ae27c56ba7988d`. All outcomes and all five stocks had prior researcher exposure; June, September and November are retrospective, not independent confirmation.

## Identity and decision rule

For each stock, all three contexts use exactly the same 200,000 Jan–March **context128-eligible** training endpoints and the same April and June/Sep/Nov scoring endpoints. The 8- and 32-state inputs are trailing slices of those 128-state windows. B1 history XGBoost and S0 one-layer GRU see the same five causal features and information length within each context; GRU seeds are 7/17/29. This common cohort differs from FQ2's original context32-eligible cohort, so these IC values must not be pooled with FQ2 as if the denominator were unchanged. April equal-stock/day mean of the three GRU seed ICs selected the highest value, with a within-1e-6 shorter-context tie rule. No June/Sep/Nov score entered that choice.

All 15 stock×context jobs reported explicit zero exit, empty stderr and a public receipt. Their endpoint identity hashes match across contexts for every stock. Each context has 90 April and 315 evaluation stock/day cells per arm, with 204,650 April and 615,488 evaluation rows across stocks, 1,000,000 sampled training endpoints, and **zero undefined IC cells**. No GRU seed fit met the frozen training-limited flag.

## Matched results

| Context | April S0 mean IC | Historical B1 IC | Historical S0 mean IC | S0−B1 paired IC | Five-day date-block 95% interval |
|---:|---:|---:|---:|---:|---:|
| 8 | 0.275971 | 0.278558 | 0.280545 | +0.001987 | [+0.001208, +0.003476] |
| 32 | 0.288835 | 0.285890 | 0.295841 | +0.009951 | [+0.007966, +0.011828] |
| **128** | **0.301415** | 0.286654 | **0.308477** | **+0.021823** | **[+0.019158, +0.024109]** |

The same-row retrospective S0 seed-IC difference for 128−32 is +0.012637 (five-day date-block interval [+0.011245, +0.013362]); 32−8 is +0.015296 ([+0.013138, +0.016583]). These date-block intervals condition on fitted models and exposed historical dates, so they do not establish prospective generalization.

At the April-selected 128-state context, individual S0 seed-minus-B1 ICs were +0.022165 (7), +0.021300 (17), and +0.022004 (29). The month effects were +0.022574 (June), +0.016267 (September), and +0.026630 (November). Stock effects were +0.018496 KGHM, +0.022089 PEKAO, **−0.000997 PKNORLEN**, +0.027736 PKOBP, and +0.041792 PZU. The negative PKNORLEN effect is retained; the full receipt and summary also retain every other seed, month, stock and date.

The 15 tasks used 1.521 allocated GPU-hours; allocation includes loading and scheduler wall time and is not utilization. Summed model-reported device occupancy was 4,801.5 seconds, with overlapping GPU tasks. The per-task model hashes, curves, epochs, timings, feature hashes, endpoint identities and all cells are in `results/sequence_ml_q8_v1/`. Original rows, predictions, model weights, raw files and scheduler logs remain private.

## Next scientific check

Q8's longer-context gain is a within-stock historical result. The next strict transfer stage must fit only the other four source stocks for each held-out fold, make all context and checkpoint choices from source April data, and score the held-out stock only after fitting. This directly tests whether the apparent longer-history advantage persists outside its own stock's training data. No model family, horizon, feature or retrospective threshold search is added.
