# Information Beyond Price — v4 development research package

**Verdict (2026-09-23 batch, America/New_York).** A's receive-clock fill filter has a small, unstable within-event advantage at a 1-second information cutoff and no advantage at 5 seconds; 65% of late joined shares are outside the common test set, and the true match/cancel clock is unavailable. Stop model and threshold expansion. B's richer current book and 30-second history do not stably beat a price calibration model on the one exposed day. Stop same-day model expansion; a new-date confirmation cohort is the decisive input if B remains a research priority. Neither result is executable trading P&L or fresh-final confirmation.

## Question, source, and frozen method

The common question is whether information beyond price improves (A) the selection of observed passive fills or (B) one-event terminal probability estimates. The studies use the pinned OutcomeTick `samples-2026-09-08` BTC-5m archive, SHA-256 `9ded382d298476c6061bfa13ed675d9147216b817dc0800fe84eb62937831506`, but different units. A uses the previously frozen 96-event fill sample and old predictions; B uses all 288 daily event candidates. No new market date, price final, private account record, order, or fee assumption was introduced.

The initial [batch manifest](../results/prediction_market_v4_development/batch_manifest.json) was pushed before A calculations. B's [pre-extraction config](../configs/prediction_market_v4_b.json) and [code](../scripts/polymarket_v4_b_extract.py) were pushed before label extraction; [model scoring code](../scripts/polymarket_v4_b_fit.py) was pushed before fitting. The CTF payout vector and ordered token IDs were independently read from the Polygon contract; 288/288 candidates had a verified binary payout and both token IDs matched the sample identities. The capture's historical label-publication timestamp is unknown, so B is `DEVELOPMENT_PRICING_REPLICATION / WITHIN_DAY_RETROSPECTIVE`.

## A — economic closeout of the old fill cohort

For event e, V is all previously joined target-leg shares; U is common model-ready shares; J is the observed retained gross receive-clock midpoint value divided by V. The event-conditioned random baseline retains each observed fill package with the same expected fraction π of U: `E[J_random,e] = π_e J_all_observed,e`. The within-event selection contribution is `S_e = J_e − E[J_random,e]`. The main table is the frozen 75% calibration threshold. The [machine aggregate](../results/prediction_market_v4_development/a_economics.json) preserves 50/75/90/100% for every old model and both information cutoffs. No model or threshold was refit. M0 is the least rich existing A model, but includes price, spread, timing and snapshot depth; the old A batch did not freeze a pure price-only arm, so A cannot isolate that narrower contrast.

| Old model / receive cutoff | J | Event-matched random J | Within-event S | Raw-share retention | Positive value abandoned |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0 least rich, 1s | −0.339 | −0.488 | +0.150 | 25.2% | +0.108 |
| M1 current/history, 1s | −0.165 | −0.335 | +0.170 | 18.0% | +0.272 |
| M2 richer flow, 1s | −0.388 | −0.488 | +0.099 | 20.2% | +0.270 |
| M2 shallow, 1s | −0.147 | −0.199 | +0.052 | 21.7% | +0.198 |
| M0 least rich, 5s | −0.489 | −0.352 | −0.138 | 22.0% | +0.344 |
| M1 current/history, 5s | −0.472 | −0.362 | −0.109 | 21.7% | +0.273 |
| M2 richer flow, 5s | −0.467 | −0.396 | −0.071 | 22.8% | +0.269 |
| M2 shallow, 5s | −0.337 | −0.343 | +0.006 | 17.4% | +0.347 |

All J/S amounts are **cents per original joined sampled share, averaged equally over 24 late events**. `J_all_observed = −0.898` on only the old common set. U/V averages 35.1%; there are 178 common late legs and 1,961.646 common shares versus 5,596.419 joined late shares. The 35 unjoined transactions have unknown target share volume and are outside V, not zero-valued trades. The 75% threshold does not imply 75% of raw shares retained. One old shallow arm at the secondary 50% threshold gives positive J, but it was not chosen prospectively from late data.

The M0 1s improvement over unscreened common legs is `J−J_all = +0.559`; of this, +0.150 is within-event selection versus event-matched random retention. A separate +0.194 cents/raw share comes from *between-event participation covariance* (`mean(π_e J_all,e) − mean(π_e)mean(J_all,e)`); the remaining change is reduced overall participation. This decomposition prevents fewer trades in adverse events from being described as fine-grained fill selection. At 5s, M0 within-event S flips to −0.138 despite +0.271 from between-event participation. The richer 1s models do not improve S over M0; the shallow arm's S is smaller.

Concentration is material: for M0 1s, four sequential six-hour blocks have S `+0.107/+0.042/−0.086/+0.537`; removing the largest raw-share event changes S only +0.150→+0.156, but does not cure temporal inconsistency. M0 5s block S is `−0.196/−0.029/+0.035/−0.361`. These are one-day descriptive blocks, not independent dates or confidence intervals. A conditional random draw would only measure the randomization mechanism; the analytic expectation above is exact and needs no Monte Carlo p-value.

Unknown outcomes dominate extrapolation. Giving every *known joined but common-set-missing* late leg a possible terminal midpoint in [0,1] produces an event-equal gross-value range of **[−28.344,+36.553] cents/raw share** for the full known joined late cohort; this bound excludes the 35 unjoined transactions. The older full-day primary measurement bound on all known target legs was [−7.888,+10.161] cents/share. Neither bound licenses extending S to missing observations. G includes pre-receipt motion; N is a gross receive-clock mark, not a verified match-clock return, cancellation gain, executable exit, or net profit. Original actionability stays `BLOCKED_WITH_EVIDENCE`: no independently bounded per-leg match timestamp, deterministic public-print/maker-leg key for a new source, ordered exact-token L2, or cancellation effectiveness.

**A decision:** current observation permits a narrow, inconsistent L2 selection hint and substantial participation reduction, but does not establish a stable incremental filter. End further model work on this cohort. If the original action question matters, request only the sample-period per-leg match time and deterministic join key, then qualify exact-token book/action clocks; otherwise close the action claim.

## B — terminal probability replication

At scheduled end minus 120 seconds, the latest raw Up-token BBO is chosen by receive time before validity checks. Its maximum age is 1,000 ms. Full book snapshots have a separate 5,000 ms age bound; they are snapshots, not complete delta replay. The 30-second history is fixed. Invalid/empty/conflicting/stale observations are explicit; no future or old-valid fallback. B0 is the raw midpoint. B1 is three-degree natural-spline price calibration plus shared quality/missingness controls. B2 adds spread, log touch depth, and imbalance. B3 adds 30-second price and imbalance changes. All learned arms use the same L2 offset-logistic fit, train-only transforms, C in {0.1,1,10} chosen on the calibration segment, and the same eligible events. Zero correction returns exactly B0. Every event receives one vote.

The [coverage receipt](../results/prediction_market_v4_development/b_coverage.json) shows 288 candidates → 254 valid decision BBO and verified labels. Five BBOs had same-time conflicts, five invalid sides, and 24 were stale. The original candidate order was split before exclusions: train/calibration/late 127/63/64 eligible events. All 288 labels and 288 pairs of token IDs passed on-chain verification, recorded separately in [token identity](../results/prediction_market_v4_development/b_token_identity.json). Missing book/history features stayed on the primary sample with train-only imputation and common indicators; the complete-feature late intersection is 57 events.

| Primary late arm | Event log loss ↓ | Brier ↓ | Change in log loss |
| --- | ---: | ---: | ---: |
| B0 raw market midpoint | 0.445331 | 0.144364 | reference |
| B1 calibrated price + quality | 0.445676 | 0.144951 | B1−B0 +0.000344 |
| B2 + current book | 0.447932 | 0.143577 | **B2−B1 +0.002257** |
| B3 + 30s summaries | 0.477587 | 0.152612 | B3−B2 +0.029655 |

Positive changes are worse. B2's Brier difference versus B1 is −0.001374 even while its primary log loss is worse; that conflict is retained. On the complete-feature intersection, the same arm ordering and exact scores are in [B scoring](../results/prediction_market_v4_development/b_scoring.json), along with bid/ask probability gaps, paired event loss signs, candidate penalties, and chronological quartile contributions. No trade was simulated from those gaps.

| Prespecified forward split | Eligible train/cal/score | B0 | B1 | B2 | B3 | B2−B1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0–40/40–50/50–60% | 101/26/23 | 0.307679 | 0.318394 | 0.300665 | 0.295697 | −0.017729 |
| 0–50/50–60/60–75% | 127/23/40 | 0.467482 | 0.496421 | 0.793427 | 0.775061 | +0.297006 |
| 0–60/60–75/75–100% | 150/40/64 | 0.445331 | 0.453907 | 0.460589 | 0.494599 | +0.006682 |

The three cuts reuse the same day and overlap; they are a fragility diagnostic, not three replications. The second cut selected weakly regularized C=10 on only 23 calibration events and failed badly later. It is kept rather than silently dropped. B3 is occasionally better in early score windows but worse in primary and final forward windows. **B decision:** no stable current-state or 30-second-history improvement over price calibration was established. Even calibration alone did not improve the primary late score. End same-day fitting; only a separately frozen multi-date event cohort with verified payout labels can resolve persistence. A's missing match clock does not invalidate this narrower probability comparison, and B cannot establish A's cancel value.

## Known-truth CPU simulation

The [synthetic result](../results/prediction_market_v4_development/simulation.json) used the frozen B0/B1/B2 pipeline, 100 fixed seeds for each of four mechanisms and n/4n/16n (1,200 complete datasets). The feature distribution was resampled from the **same** 254 eligible events; labels were newly drawn from `logit(q)=a+b logit(p)+βz`, where z is train-standardized snapshot imbalance. Mechanisms are (0,1,0), (0.2,0.8,0), (0.2,0.8,+0.25), and +0.25 in training/calibration followed by −0.25 in score. β=0.25 is a scenario, not an estimated market effect. Detection means B2 improves late log loss by more than a prespecified threshold; thresholds are 0, 0.005, 0.01 nats.

| Mechanism | n=254: improvement >0 / >0.005 | n=1,016 | n=4,064 |
| --- | ---: | ---: | ---: |
| No increment, q=p | 34% / 19% | 31% / 4% | 22% / 0% |
| Calibration bias only | 33% / 18% | 33% / 9% | 32% / 0% |
| Fixed β=+0.25 state increment | 51% / 39% | 59% / 38% | 92% / 46% |
| State coefficient reverses late | 20% / 13% | 2% / 1% | 0% / 0% |

At current n, a rich-model win at the zero threshold occurs about one-third of the time even without a true state increment; the fixed β=0.25 increment is detected only about half the time. More replicated rows improve zero-threshold detection under this generator, while a 0.005-nat requirement remains hard even at 16n. Under the reversal mechanism B2 harms late log loss in 80%, 98%, and 100% of datasets as n grows. These frequencies condition on the exact generator, optimizer and one-day feature distribution; resampling the day does not supply new dates or validate a real β.

## Status, resource use, and research draft

| Item | State | Decision-relevant evidence |
| --- | --- | --- |
| A economic closeout | DONE | All 8 old model/cutoff combinations and 4 thresholds, event random expectation, participation decomposition, missing bound |
| A original action clock | BLOCKED_WITH_EVIDENCE | No independently bounded sample-period maker-leg match time or verified cancel path |
| B terminal probability | DONE | 288/288 payout and token identities; 254 eligible event decisions; four arms and three forward cuts |
| CPU known-truth simulation | DONE | All 1,200 datasets; four local CPU workers, 4.51 s wall, at most 0.0051 allocated core-hours |
| Rocklabs future source | NOT_APPLICABLE | No new authorized source is present in this batch; no wait or email action |
| Independent final/live trading | NOT_APPLICABLE | Outside this development authorization |

Deep and its documented fallback both failed DNS before any allocation could be checked. Local CPU sufficed; no GPU or remote compute job was launched. The simulation's largest observed worker peak RSS was about 86 MB; total batch peak memory and total CPU core-hours outside simulation were not independently metered and are `unknown`. B's instrumented on-chain verification used 32 HTTP requests and 211,681 response bytes; a few initial connectivity probes were separate and still far under the 2,000-request/1-GiB ceiling. The 330 MB archive was reused locally; no new market date was downloaded. Exact commands, source identities, exit codes, and remaining resource fields are in [resource receipt](../results/prediction_market_v4_development/resource_record.json). Scientific output includes only code and aggregates; private event rows, transaction IDs, predictions and receipts remain ignored.

**Short research draft.** We asked whether short-horizon order-book state contains information beyond the market's own price for observed fill selection and ultimate binary payout. On a single exposed BTC-5m day, a receive-clock fill filter showed a modest event-internal advantage at 1 second before public print receipt but not at 5 seconds; participation and missingness explained much of its apparent gain. In an independently assembled event-level terminal task with chain-verified outcomes, current-state and 30-second features did not consistently improve a calibrated-price baseline. Known-truth simulations showed that the present protocol can mistake noise for improvement and has limited power for a modest fixed state effect at the available sample size. These are development observations, not causal cancellation benefits, net returns, independent-date generalization, or a published alpha claim. The next decisive evidence is source-specific match/action clocks for A and a fresh multi-date event cohort for B; no further model family is justified on this day.
