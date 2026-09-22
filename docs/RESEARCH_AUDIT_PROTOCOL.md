# WSELOB explanatory research audit v1

Frozen before this audit's new fits, September 22, 2026. All underlying WSE
periods have already been inspected. This is implementation and explanatory
research, **not a new independent holdout or preregistration of unseen data**.
The original three-day confirmation protocol and results remain immutable.

The executable definition is [the configuration](../configs/wselob_research_audit_v1.json).
There are 150 control cells: five stocks, own-stock June / leave-one-stock-out
June / frozen December 27–29, S0 within stock/day and S1 within stock across
training history, and seeds 7, 17, 29, 43, 71. Model seed stays 7. No seed is
added or discarded based on outcomes. The later fit ends December 22; monthly
fits use strictly earlier months. Transfer excludes the target stock.

There are 200 ablation cells: five stocks, April/June/September/November,
Linear/XGBoost, F1–F5. All use the full-five-feature finite-row intersection
and the original 20-message label and hyperparameters. F5 retains the original
feature order. Reduced groups follow their declared order. Training-only
scaling is unchanged. Existing predictions may be reused only with matching
settings, hashes, event/time identities and labels. Fresh CPU/device results
are explicitly distinguished from the original predictions.

State diagnostics use training-only 1/3 and 2/3 quantiles of spread and top
imbalance, linear interpolation, with equal boundary values assigned to the
lower bin. All nine Cartesian bins are retained, even when ties leave empty
bins. Test labels only score the frozen assignments. Feature contrasts are
F2−F1, F3−F2, F4−F2, F5−F3, F5−F4, and XGBoost−Linear within every group.

Block Spearman IC and equal-weight daily IC are separate statistics. Daily
prediction/label means and standard deviations diagnose between-day structure;
differences between pooled and daily IC are not an additive contribution
decomposition. Five shuffle seeds are sensitivity checks, not a p-value sample.
Constant predictions give undefined IC. Every strict summary propagates missing
values and reports expected/defined counts; available-case means are separate.

Execution reuses all original 137 tasks and all 35 later fits when receipts
permit, at horizons 10/20/50 and delays 0/1/5. Exact index joins and the
cross-delay common intersection precede the strict absolute prediction >1 bp
selection. Signed midpoint movement minus entry and exit half-spreads equals
crossed markout, all divided by entry midpoint. The fixed-exit supplement uses
exit t+20 and entry t+d, separately from the original moving-exit t+d+h rule.
The former shortens holding time; the latter moves the whole holding window.
Neither isolates pure hardware latency. Event-time summaries use exact source
message indices, never distances between filtered rows, and never cross a day
or invalid segment. Quantiles are p10/p50/p90/p99; zero and invalid counts stay.

Passive results reuse both priority interpretations and observable-outcome
denominators. The existing spread diagnostic is twice the signed future-midpoint
minus passive-price difference divided by passive price. Half that diagnostic
is the passive-price-to-midpoint markout, not an actual single-trade profit.
Post-fill midpoint markouts use fill midpoint as denominator. Different models
select different filled subsets; comparisons are descriptive, not causal.

Old result hashes are captured before work. New receipts bind configuration,
implementation, input manifests and coordinates, excluding runtime paths,
workers and device. Interrupted incomplete tasks are restarted explicitly;
completed hashed receipts resume without fitting. Aggregate-only execution
rejects an incomplete or duplicate task denominator. Row data and operational
records remain private; only stock/day or coarser aggregates are public.

## Numerical backend and evidence compatibility — correction after v1

A scientific task ID identifies the question, configuration, input rows and
implementation. It is **not a numerical-equivalence certificate**. CPU/CUDA,
library/build changes, accelerator architecture and numerical-library settings
can change predictions even when that scientific question is unchanged.

The completed v1 run at `55c346fe1559db52a5f15c3bf9b74ffe7d851a73`
recorded device/threads privately but did not enforce a numerical compatibility
check on resume. Its 350 task IDs and aggregate results remain frozen. The
manifest identifies that evidence as legacy, artifact-bound, with no certified
cross-backend equivalence. Do not infer prediction identity from equal IC,
matching task IDs or a requested device. No missing backend attestation is
retroactively fabricated. Original artifact aggregation uses that archived
implementation and the original hash-verified receipts; it is not a new fit.

The corrected runner requires `--numerical-profile PRIVATE_PROFILE.json` for
run/resume. Its exact JSON schema has five keys: `schema` (1), `device` (the
requested device string), `threads` (the requested integer), `packages` (exact
installed versions for `numpy`, `pandas`, `xgboost`), and
`numerical_environment_sha256` (a lowercase SHA256 of a privately retained
numerical-environment record). The operator must capture and attest the actual
library/build identities, CPU/accelerator architecture, compiler/driver/runtime,
BLAS/OpenMP implementation and numerical/precision/thread settings in that
private record. It is an explicit attestation, not automatic hardware discovery;
do not reuse its digest after those properties change. Worker count, data paths
and scheduler identifiers alone do not define numerical compatibility.

The runner checks device, threads and installed package versions, binds the
entire profile into each new receipt, and rejects missing or unequal contracts
before reading a completed prediction. A changed environment requires a separate
private work directory/evidence realization; never overwrite old receipts or
edit their contract to bypass rejection. The source correction changes the
implementation hash, so the corrected runner intentionally cannot masquerade
as the completed v1 implementation. It does not invalidate the archived results
or require those 350 cells to be rerun.

A matching profile is a necessary resume condition, **not proof that another
fit will be byte-identical**. The prediction artifact SHA256 identifies the
actual saved evidence. New manifests retain that hash, the profile hash and
origin per task. Verified archived predictions remain explicitly archived
artifact references, not fresh fits on the requested backend; their source hash
is retained and their producer profile is not inferred from the reuse runtime.
Aggregation may combine declared producer profiles for the fixed experiment,
but must retain those evidence identities rather than claiming backend parity.
Only an explicit matched-output comparison could establish a stated numerical
agreement scope. No such new comparison or experiment is performed here.
