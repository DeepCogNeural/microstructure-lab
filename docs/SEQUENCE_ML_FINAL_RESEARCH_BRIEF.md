# Final WSELOB sequence-ML research brief

**Status:** formal historical research complete; independent confirmation **pending**. The 2017 WSE stocks and months used here were researcher-exposed. This brief does not claim unseen-stock or future-period generalization, actual fills or trading profit. The old Q2/Q3/Q6 20k/15-epoch work remains archived as a pilot; FQ2–FQ4, Q8, Q10 and Q11 are the final bounded retrospective record.

## Question and design

Can causal original-event limit-order-book history improve h20 midpoint-change ranking beyond a history-matched cheap baseline, and does a small Transformer add value beyond a sufficiently trained GRU? Five causal book features, fixed original-event endpoints, source hashes and public aggregate receipts bind the experiment. Jan–Mar trained models; April alone selected checkpoints/context; June, September and November supplied historical diagnostics. The cheap baseline is B1 history XGBoost, S0 is a one-layer GRU with seeds 7/17/29, and FQ4 S1 is a small Transformer on the unchanged context32 FQ2 cohort.

## Historical model evidence

| FQ2 train endpoints/stock | B1 history IC | S0 seed-specific IC mean | Paired S0−B1 IC | Five-day block interval |
|---|---:|---:|---:|---:|
| 50k | 0.279559 | 0.285223 | +0.005664 | [+0.003889, +0.007231] |
| 100k | 0.285240 | 0.291252 | +0.006012 | [+0.004160, +0.007916] |
| 200k | 0.286437 | 0.297506 | +0.011069 | [+0.008850, +0.013381] |

FQ4's fixed context32 Transformer lost to S0: S1−S0 **-0.009788** IC, date-block interval **[-0.011398,-0.008567]** on all 315 retrospective stock/day cells. All three seed and all five stock effects were negative. No post-result Transformer retuning was used.

Q8 tested 8/32/128 history states on **one common context128-eligible cohort**, with 200k train endpoints per stock, 90 April and 315 historical stock/day cells and exact same endpoints across contexts. April selected **128**. On its historical evaluation, B1 IC **0.286654**, S0 seed IC mean **0.308477**, paired difference **+0.021823** [+0.019158,+0.024109]. Q8's cohort is different from FQ2 and their scores are never pooled. PKNORLEN's within-stock S0−B1 difference was **-0.000997**, a retained negative effect.

Q10 was actual **train on four stocks → test the fifth** transfer, repeated for all five held-out stocks. Training, normalization, April context choice and checkpoints used only the four source stocks; each fold trained on 800k source endpoints. All folds selected 128 from source April scores, and the choice used GRU IC, favoring the neural arm. On 615,488 held-out historical rows/315 cells, B1 IC was **0.291751** and S0 seed IC mean **0.318343**, paired difference **+0.026592** [+0.024231,+0.028571]. All five stock differences were positive; PKNORLEN was the smallest at **+0.008758**. FQ2's older leave-one-stock-out aggregate-sign check was not this transfer design. Averaging predictions before scoring IC is a distinct estimand, fully reported in Q10 receipts.

FQ3's fifteen rolling refits and fixed-model high/low prior-activity split remain in the public record. Newer training information and calendar conditions change together, so fixed-versus-updated differences are not causal decay estimates.

## Fixed visible-quote execution re-check

Q11 reused frozen Q8 and Q10 private predictions without fitting. At original event t, strict `abs(prediction)>1 bp` selected direction; entry was the visible ask/bid at t+0/1/5 messages and exit was the opposite quote at fixed t+20. Exact original-event, segment and valid-quote identities were required across all delays and both arms. The table uses **pooled selected descriptive** crossed bp because the arms can select different opportunities; full equal stock/day values and any undefined cells are in the public summary.

| Population | Entry delay | Common rows | B1 / S0 selected | B1 / S0 crossed bp | B1 / S0 undefined cells |
|---|---:|---:|---:|---:|---:|
| within-stock Q8 | 0 | 615,488 | 31,634 / 75,562 | -6.830 / -7.287 | 0 / 0 |
| within-stock Q8 | 1 | 615,488 | 31,634 / 75,562 | -7.328 / -7.761 | 0 / 0 |
| within-stock Q8 | 5 | 615,488 | 31,634 / 75,562 | -7.987 / -8.531 | 0 / 0 |
| source-only Q10 | 0 | 615,488 | 27,080 / 83,363 | -6.463 / -7.556 | 0 / 0 |
| source-only Q10 | 1 | 615,488 | 27,080 / 83,363 | -7.014 / -8.036 | 0 / 0 |
| source-only Q10 | 5 | 615,488 | 27,080 / 83,363 | -7.721 / -8.808 | 0 / 0 |

The both-selected subset is published separately. The prior FQ3 zero-delay historical B1/S0 visible crossing was **-6.949 / -6.700 bp**, and remains in the record; it uses the different FQ2 cohort. Q11 is one-share quote arithmetic with no actual fills, fees, queue, impact, inventory or realized PnL. A positive ranking score does not imply executable profit.

## Cost, reproducibility and claim boundary

FQ2/FQ3/FQ4/Q8/Q10 used **7.912 allocated GPU-hours** total; Q11 used **1.264 allocated CPU core-hours**. These are scheduler allocations, not utilization. `results/sequence_ml_final_v1/` contains four figures, a cost table, public run/model/source/data hashes and an aggregate recomputation manifest. Licensed raw records, row predictions, weights and private scheduler logs stay outside Git.

The Q5 source audit found no legally usable, genuinely uninspected WSE original-event h20 cohort. Therefore `PENDING_INDEPENDENT_CONFIRMATION` remains the final boundary. A résumé-safe method description would require separate editing authorization; no résumé or PDF was changed by this research run. An independent performance or profit claim requires qualified new data and its own frozen protocol.
