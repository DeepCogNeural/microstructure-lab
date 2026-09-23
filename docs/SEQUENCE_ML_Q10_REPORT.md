# Q10 strict source-only five-stock transfer — formal retrospective result

Status: **complete retrospective transfer on previously exposed WSELOB-2017 dates**. This is a model-level four-source-stock → one untouched held-out-stock experiment. It is distinct from FQ2's leave-one-stock-out recalculation of an aggregate sign. It does not provide independent-period confirmation or a trading-profit result.

## Frozen design and integrity

For each held-out stock, B1 history XGBoost and S0 GRU seeds 7/17/29 were fitted on exactly 200,000 context128-eligible Jan–Mar endpoints from each of the other four stocks (800,000 pooled source endpoints). Source April GRU seed IC, computed without the held-out stock, selected among contexts 8/32/128; the chosen context was shared by B1 and S0. Source April controlled GRU checkpointing and source-only normalization. Held-out Jan–April labels and source June/September/November outcomes were excluded from fit inputs. The held-out June/September/November labels were loaded only after fitting for retrospective scoring. This April context rule favors the neural arm and is not an arm-neutral selection criterion.

All five source-only context choices were 128. Their source April IC evidence is fully retained below:

| Held-out stock | Source April context 8 | 32 | 128 | Retrospective S0−B1 IC |
|---|---:|---:|---:|---:|
| KGHM | 0.271825 | 0.283283 | 0.294923 | +0.018831 |
| PEKAO | 0.275493 | 0.287069 | 0.298187 | +0.023160 |
| PKNORLEN | 0.271526 | 0.285622 | 0.300477 | +0.008758 |
| PKOBP | 0.281062 | 0.295122 | 0.307331 | +0.033681 |
| PZU | 0.279952 | 0.293079 | 0.306158 | +0.048527 |

The five frozen GPU fold jobs returned explicit exit zero, with empty stderr and complete public aggregate receipts. The strict aggregator independently recomputed the four-source April context evidence from the public Q8 source receipts and required all 315 stock/day cells, 615,488 same-row historical evaluation endpoints per arm, and all five arms. There were zero undefined IC cells; 0/15 GRU seed fits were training-limited. The jobs used **2.1172 allocated GPU-hours**. Allocation time includes loading and is not device utilization.

## Retrospective scores

Equal stock/day mean IC was **0.291751** for B1 and **0.318343** for the average of the three S0 seed-specific ICs. The paired S0−B1 difference was **+0.026592**, with five-day date-block interval **[+0.024231,+0.028571]**, conditional on the fitted models and researcher-exposed dates. Individual seed differences were +0.027298 (7), +0.025626 (17), and +0.026851 (29). Month differences were +0.030969 (June), +0.019410 (September), and +0.029397 (November). Every held-out stock difference was positive, with PKNORLEN the smallest at +0.008758.

The distinct estimand formed by averaging the three seed predictions first scored IC **0.327043**, versus B1 0.291751, difference **+0.035292** [ +0.032866, +0.037326 ]. It must not be substituted silently for the predeclared average of seed-specific ICs. The public summary retains per-seed, per-month, per-stock, prediction-mean, context-selection, model-cost and receipt detail. No null or negative Q10 cells arose; negative FQ4 Transformer and FQ3 execution findings remain part of the full research record.

## Interpretation and boundary

The transfer is stricter than an aggregate leave-one-stock-out sign check because held-out stock rows were excluded from training, normalization and April selection for their fold. Yet all five WSE stocks and the historical dates were already exposed to the research process, and source Q8 context scores come from within-source models. The block interval quantifies conditional historical uncertainty, not unseen-stock or future-period generalization. Q10 supports a bounded source-only transfer observation, not independent confirmation or executable alpha. The fixed finalist execution re-check follows before the final research package. Raw market data, row predictions, model weights and scheduler logs remain private.
