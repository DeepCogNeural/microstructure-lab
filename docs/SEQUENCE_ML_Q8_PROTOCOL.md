# Q8 context-length sensitivity, frozen pre-fit protocol

Q7 training adequacy and 50k→100k→200k scaling are supplied by formal FQ2: all 45 GRU fits were not training-limited and B1 remains a meaningful same-information comparator. Q8 therefore tests whether GRU's retrospective gain requires 8, 32 or 128 causal original-event states.

This is a *new common 128-eligible cohort*. Build 128-state windows once, select 200,000 train endpoints per stock using the frozen FQ2 source/date/sampling settings, and take trailing 8/32/128 states from exactly those windows. This keeps train/dev/evaluation endpoint IDs and h20 labels identical across contexts and arms. It changes eligibility relative to FQ2's 32-state primary comparison, so numerical Q8 levels must not be pooled with FQ2 or presented as an independent replication.

Refit B1 history XGBoost and S0 one-layer hidden-64 GRU at every context, using formal FQ2 hyperparameters and seeds 7/17/29. April dev alone selects a preferred context via the highest equal-stock/date GRU seed-mean IC, with shortest-context tie break. June, September and November are retrospective diagnostics only. Report all contexts, seeds, stock/date cells, paired B1→S0 IC, training-limit flags, cost and negative results. No new horizon, feature family or model family is allowed.

Frozen after the formal FQ4 result checkpoint and reviewer control `bf00ef6e3428870c9fb94bc1eb5f7ce4d1791c9f` readback. FQ4 context32 Transformer outcomes did not change this previously drafted 8/32/128 grid, endpoint rule, target, model set or April-only selection. No Q8 model fit occurred before this protocol commit. FQ4 is a separate architecture experiment and is not pooled into this common-128-eligible context study.
