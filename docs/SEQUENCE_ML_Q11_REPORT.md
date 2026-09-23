# Q11 fixed finalist visible-crossing re-check — formal retrospective result

Status: **complete fixed research diagnostic, negative visible crossing throughout**. No model was fitted, checkpointed, recalibrated or retuned in Q11. The frozen B1 history XGBoost and S0 GRU three-seed mean predictions came from two separately labelled populations: Q8 within-stock and Q10 strict four-source-to-one-held-out-stock transfer. Every prediction file, parent public report and aggregate SHA was verified before quote arithmetic.

## Source and denominator

Five original WSELOB-2017 files matched their public source-registry full-file SHA-256. Each evaluation day's original-event quotes were privately reconstructed and its snapshot Parquet SHA-256 matched the frozen cache manifest. Prediction day/event/h20-label arrays matched across Q8/Q10 and the reconstructed original event identity. The frozen rule used strict `abs(prediction_bps)>1` at event t, visible ask/bid entry at t+0, t+1 or t+5 original messages, and opposite visible quote exit at the same fixed t+20 event. Exact segment and quote validity for **all** delays produced **615,488 common opportunities** over **315 stock/day cells**; zero additional Q11 quote/event exclusions and zero undefined crossing cells. Selection coverage differs by model, so arm differences in selected-population means are descriptive rather than paired opportunity effects. Both-selected results are separately retained.

## Full 315-cell historical execution summary

The equal stock/day mean is the complete-cell primary description. The pooled selected mean weights by selected opportunity counts and is a separate descriptive quantity. All numbers below are basis points after visible bid/ask crossing, before unmodeled fees, fills, queue, impact and inventory.

| Prediction source | Arm | Selected / common | Coverage | Entry delay | Equal stock/day crossed | Pooled selected crossed |
|---|---|---:|---:|---:|---:|---:|
| Q8 within-stock | B1 | 31,634 / 615,488 | 5.14% | 0 | −7.019 | −6.830 |
| Q8 within-stock | B1 | 31,634 / 615,488 | 5.14% | 1 | −7.541 | −7.328 |
| Q8 within-stock | B1 | 31,634 / 615,488 | 5.14% | 5 | −8.189 | −7.987 |
| Q8 within-stock | S0 mean | 75,562 / 615,488 | 12.28% | 0 | −7.165 | −7.287 |
| Q8 within-stock | S0 mean | 75,562 / 615,488 | 12.28% | 1 | −7.634 | −7.761 |
| Q8 within-stock | S0 mean | 75,562 / 615,488 | 12.28% | 5 | −8.392 | −8.531 |
| Q10 source-only | B1 | 27,080 / 615,488 | 4.40% | 0 | −6.781 | −6.463 |
| Q10 source-only | B1 | 27,080 / 615,488 | 4.40% | 1 | −7.332 | −7.014 |
| Q10 source-only | B1 | 27,080 / 615,488 | 4.40% | 5 | −8.012 | −7.721 |
| Q10 source-only | S0 mean | 83,363 / 615,488 | 13.54% | 0 | −7.354 | −7.556 |
| Q10 source-only | S0 mean | 83,363 / 615,488 | 13.54% | 1 | −7.819 | −8.036 |
| Q10 source-only | S0 mean | 83,363 / 615,488 | 13.54% | 5 | −8.568 | −8.808 |

At zero delay, the pooled selected signed gross midpoint move minus entry and exit half-spreads reproduced the crossed result to numerical tolerance:

| Source / arm | Gross midpoint move | Entry half-spread | Exit half-spread | Crossed |
|---|---:|---:|---:|---:|
| Q8 / B1 | +1.666 | 4.037 | 4.459 | −6.830 |
| Q8 / S0 mean | +1.609 | 4.129 | 4.768 | −7.287 |
| Q10 / B1 | +1.779 | 3.901 | 4.341 | −6.463 |
| Q10 / S0 mean | +1.649 | 4.296 | 4.908 | −7.556 |

On the **both-selected** subset, Q8 had 19,992 opportunities and Q10 had 19,043, shared by B1/S0 within each mode. At delays 0/1/5 the Q8 B1 versus S0 pooled crossed values were −6.070/−6.046, −6.829/−6.813 and −7.677/−7.667 bp. Q10 both-selected B1 versus S0 values were −6.039/−5.991, −6.809/−6.768 and −7.677/−7.650 bp. Every both-selected value was negative. The public per-stock/day receipt retains every gross, half-spread, crossed, coverage and undefined field for all modes/arms/delays.

## Integrity, cost and interpretation

Five CPU tasks returned explicit zero exit and empty stderr, using **1.2644 allocated CPU core-hours**; allocation is not utilization. Independent aggregation required all stock/day/mode/arm/delay cells, parent source hashes and common opportunities. The same-row Q8/Q10 comparison and daily snapshot/source checks passed. Private raw files, row predictions and scheduler logs remain outside Git.

Q11 repeats the predeclared visible crossing rule on already exposed historical dates. It is quote arithmetic, not an actual fill or realized cash PnL study. The fixed t+20 exit and one-share convention omit fees, queue priority, impact, latency distribution, inventory and participation. The prior FQ3 zero-delay result remains published for its different context32 cohort. Q10's positive historical ranking score did not survive visible spreads under any Q11 finalist/delay population. No independent confirmation can be claimed; the final package follows with Q5 still pending.
