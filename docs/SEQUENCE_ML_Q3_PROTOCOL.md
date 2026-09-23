# Q3 frozen diagnostic protocol

This is a bounded continuation of Q2 on the already exposed WSELOB-2017 development data. B* is April-selected historical XGBoost; S0 is the same fixed GRU architecture and three seeds. The Q3 configuration is `configs/sequence_ml_q3_v1.json`. No new feature, target, threshold or model search is introduced.

## One decision-time state split

Use the elapsed nanoseconds over the same 32 original-message input window as a past-activity descriptor. For each stock, freeze the median from the same Jan–Mar selected training endpoint IDs as Q2. A valid decision with a shorter positive duration is high activity; otherwise it is low activity. Report all five stocks and each June/September/November date, with undefined cell reasons retained. This is state-conditioned robustness, not an unseen market regime. It is not an extra model input.

## Fixed versus updated models

Keep the original Jan–Mar fit and April dev cutoff as the fixed model for all three evaluation months. At each historical month, refit B* and GRU using the same 20,000 per-stock endpoint cap, same features/context, model configuration, sampling seed and three GRU seeds. June uses Feb–Apr train/May dev; September uses May–Jul train/Aug dev; November uses Jul–Sep train/Oct dev. Original-event eligibility and stride-20 scoring must match fixed Q2 predictions exactly. Compare paired stock/day IC of updated and fixed on the identical rows. The later fits have later information, so a difference cannot be attributed to calendar decay alone. All periods remain exploratory.

## Fixed crossing diagnostic

At event t, enter one share at visible ask for a positive prediction or bid for a negative prediction, with strict `abs(prediction)>1 bp`; abstain otherwise. At original event t+20 in the same segment, exit at the opposite quote. Zero delay; no fee, impact, inventory, actual fill, or cash PnL claim. Both B* and the **arithmetic mean of the three frozen GRU predictions** use the same base opportunities; three individual GRU seeds are secondary sensitivity. Report each rule's selected count/coverage and crossed quote markout. Also report the common-selected subset separately, because different model selections do not make the conditional markout difference causal.

The feature cache does not retain snapshots locally for these months. The exact quote-cost identity can be reconstructed from causal `spread_bps` at t, future spread at original event t+20 and `markout_20`:

`crossed = sign(pred)*markout_20 - spread_bps_t/2 - spread_bps_t_plus_20/2*(1 + markout_20/10000)`.

Require exact event+20/segment matching and finite spread; never take the next filtered model row. Validate this algebra against `crossed_labels` on a synthetic reconstructed book before reading aggregate results. This is still a visible-quote historical diagnostic, not actual execution. The primary model choice remains predictive B* vs S0, not a new strategy selected by execution outcomes.

LOSO is deferred unless a separate source-only inner chronological tuning contract and remaining budget make the five outer folds meaningful. It is not necessary to run a post-hoc five-arm matrix. Any Q4 Transformer gate will use the explicit roadmap conditions, including training diagnostics, not the fact that this diagnostic ran.
