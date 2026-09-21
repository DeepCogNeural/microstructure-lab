# Later-partition scientific exposure audit

Audit date: 2026-09-21. Baseline: `bb28882c1d043a757447ff0f9d8883d812616d38`.

## Decision and scope

The operator confirmed on 2026-09-21, after being informed of the provenance gaps, that these 15 partitions had not been used for scientific analysis. The confirmation was supplied before any new outcomes were opened. Together with the documented exclusion from published scientific tasks, this supports accepting all 15 partitions as scientifically untouched on the basis of operator attestation. Historical non-exposure is not independently established by a complete technical access ledger; exclusion from the scientific cache alone would not have been sufficient.

This audit inspected documentation, code, history, date/task metadata, counts and hashes. It did not load later-partition raw records, Parquet values or row-level predictions; fit a model; compute later labels, correlations, markouts or queue outcomes; or select partitions using outcomes. Existing published earlier-period results were read for context. No confirmation protocol or results have been created. Following the operator confirmation, the user explicitly requested recording the decision and returning, so this turn stops after the audit.

## Exact proposed partitions

The authoritative published inventory is `results/wselob_xgboost_application_v1/engineering_day_coverage.csv`, introduced with `dab9079400801d231cd170042d5df68bab9fba8d`. These are inventory counts, not confirmation evaluation denominators.

| Symbol | Trading date | HDF5 key | Raw messages | Prepared rows |
| --- | --- | --- | ---: | ---: |
| KGHM | 2017-12-27 | d20171227/table | 45386 | 22405 |
| KGHM | 2017-12-28 | d20171228/table | 53900 | 35101 |
| KGHM | 2017-12-29 | d20171229/table | 43913 | 29710 |
| PEKAO | 2017-12-27 | d20171227/table | 26704 | 13613 |
| PEKAO | 2017-12-28 | d20171228/table | 28217 | 16347 |
| PEKAO | 2017-12-29 | d20171229/table | 22370 | 13053 |
| PKNORLEN | 2017-12-27 | d20171227/table | 42842 | 29566 |
| PKNORLEN | 2017-12-28 | d20171228/table | 54745 | 27594 |
| PKNORLEN | 2017-12-29 | d20171229/table | 53874 | 41023 |
| PKOBP | 2017-12-27 | d20171227/table | 38297 | 22639 |
| PKOBP | 2017-12-28 | d20171228/table | 61201 | 37734 |
| PKOBP | 2017-12-29 | d20171229/table | 62425 | 42187 |
| PZU | 2017-12-27 | d20171227/table | 139549 | 82706 |
| PZU | 2017-12-28 | d20171228/table | 54595 | 34943 |
| PZU | 2017-12-29 | d20171229/table | 55870 | 38127 |

Total: **15 partitions, 783,888 source messages and 486,748 prepared rows**. Eligible primary-horizon and execution denominators have not been computed. These are only three shared trading dates, not 15 independent time periods.

## Raw-source identity

WSELOB-2017 V1, DOI `10.17632/3g4mhdp899.1`, Marszałek, Adam (2023), CC BY 4.0. Each date above is a group within the corresponding full-year file. These are full-file hashes recorded in `configs/wselob_sources_v1.json`, not separate daily raw hashes or a fresh raw-file rehash in this audit.

| Symbol | Source filename | SHA256 |
| --- | --- | --- |
| KGHM | KGHM_lob_2017_zlib.h5 | `0246f994b42af04c65deb38f28f64988b7b6fa71d0fb83e41bda8487afff4c5c` |
| PEKAO | PEKAO_lob_2017_zlib.h5 | `3c418a55a492ebe2e39c8513cd7fc7e3e6827dc1a176af09fdcaad9f3485bae6` |
| PKNORLEN | PKNORLEN_lob_2017_zlib.h5 | `5b8f394144b8a3dace3e08bb2b4228d63231a12ae21f5f27aa662a8d09f3fa40` |
| PKOBP | PKOBP_lob_2017_zlib.h5 | `ecf94a905b04836442c9124c7f7d7edc5b7d98e7236ca4026f0ec37b9407407e` |
| PZU | PZU_lob_2017_zlib.h5 | `4ca8f7c136c940d71b271cc427d641c3881857e01b43555792d484d9eb2f4b8c` |

The source registry also contains the depositor download identifiers/URLs. The published day inventory records individual snapshot and feature SHA256 values for all 15 partitions. Its tail configuration hash is `c4ad1eded24f96cdb7374cac23fad98f1e71f00e24c3abfd265f71ea132cac08`; the original scientific-cache configuration hash is `2457a7f5f20dc552bbe9479d9c8769e38256c209ff699f00b2b4690287bc6cc7`. The later public redaction intentionally changed configuration digests; a digest mismatch alone is not evidence of scientific contamination.

## Why engineering-only

The original configuration ends on 2017-12-24. The locally retained scientific manifest has 1,235 partitions, with observed trading dates 2017-01-02 through 2017-12-22. The official files extend through December 29. The final three dates per stock were prepared separately to complete the 1,250-partition engineering inventory, rather than expanding the 152 frozen scientific tasks. This is corroborated by `preparation_summary.json`, the inventory, and a retained private preparation resource receipt reporting exactly 15 partitions and the counts above.

Crucially, preparation was not label-free. `src/cloblab/scale_cache.py::prepare_day`, both in the archived preparation revision and current code, calls `licensed_experiment.prepare` and saves `markout_10`, `markout_20`, and `markout_50` beside the five features. The private preparation receipt identifies revision `1b984c70f2113af8a5f702dd2ff607e83ee5a025`; that object remains readable locally. Thus future labels were generated and available. Generation without inspection or selection is not itself proof of scientific contamination, but the preparation label does not certify blinding.

## Exposure matrix

| Potential use | Evidence found | Remaining limitation |
| --- | --- | --- |
| Model fitting | Published 152-task manifest contains April, June, September and November only. `scale_runner.load_fold` skips later months. Eighty retained local task status receipts also name only those months. | These receipts cover retained runs, not every historical process or manual read. |
| Hyperparameter selection | Frozen configurations specify fixed settings and no hyperparameter search; documented task scope excludes December. | No complete access/decision ledger for the generated tail labels. |
| Feature selection | Frozen five-feature set; earlier PEKAO ablation metadata is limited to the first ten January trading days. | Cannot rule out unretained exploratory inspection. |
| Threshold selection | Published execution settings keep the fixed 1 bp rule and the original prediction tasks. | A fixed published threshold does not prove nobody inspected tail outcomes. |
| Horizon selection | Published horizons remain 10/20/50; all three tail labels would be created by preparation. | No record certifying these labels were never examined. |
| Transfer experiments | Twenty-five published block identities cover April/June/September/November. Runner filters data later than the maximum test month. | Retained remote model task identities also exclude December; unrecorded manual access remains covered by operator attestation. |
| Execution-aware markouts | All 411 published block identities use the four earlier test months; reused prediction evidence has the same scope. | No complete record of separate ad hoc runs. |
| Queue-aware diagnostics | All 822 published cells use the same earlier months; native benchmark explicitly limits `queue_domain` to those months. | All 15 remote native tail receipts record queue_domain=false and zero queue decisions; retained queue checkpoint names cover only the four earlier months. |
| Figures and tables | Later dates occur in engineering coverage counts/hashes; published predictive/execution block metadata uses earlier months. | Published artifacts cannot enumerate unpublished figures or tables. |
| Exploratory scripts/notebooks | Current tracked scripts and history date searches identify no tail scientific experiment; no local project notebook found in the inventory. | Absence of tracked notebooks is not an access history for private or deleted notebooks. |
| Manual scientific spot checks | No affirmative evidence of tail scientific inspection was identified. | Manual reads are not comprehensively logged in the retained evidence. |
| Benchmarks exposing labels/outcomes | Full-source preparation generated labels. C++ replay covered all 1,250 days; its tail path does not load features or call queue outcomes. Queue timing is PEKAO June. | Label creation and aggregate replay parity do not establish what earlier operators viewed. |

## Search coverage and receipts

Read the README, limitations, methodology, execution and queue reports, scale report and C++ finalization specification. Inspected source configuration, preparation/runner code, native benchmark domain, execution/transfer/queue task selection, source registry, preparation inventory, original task manifest and downstream run manifests. The two requested application-context documents were consulted locally; their private content is not reproduced here.

Fetched origin; the baseline matched origin/main. Searched all 23 branch-reachable revisions for tail dates/engineering-tail references in configs, scripts, source, docs and results, then expanded to 67 revisions reachable through local reflogs. Tail-date matches were limited to engineering coverage/preparation/report/completion documentation. Relevant chronology includes the archived preparation implementation, `dab9079` benchmark publication, `0c58424` execution/transfer implementation, `cbf13df` transfer completion, `2ff81ff` queue implementation, `942fd5b` queue publication, and `3a62939` / `723bed3` native implementation/publication. Date-string searches cannot rule out wildcard/full-year/default-range access.

Private local evidence inspected: scientific and single-stock preparation manifests; tail preparation resource receipt; retained task status identities; preparation/run log inventory and tail-date searches; the retained historical task transcript. Transcript searches did not recover a complete tail preparation-and-access sequence. Logs and private telemetry remain outside Git.

Initial remote archive access attempts failed at connection-name resolution. After connectivity was restored, both archives were accessible and the following metadata was inspected without opening market outcomes:

- The tail preparation configuration spans 2017-12-25 through 2017-12-31, with the existing five stocks and 10/20/50 horizons.
- The remote tail manifest contains exactly 15 partitions and the published tail config hash. All recorded feature/snapshot hashes match the corresponding remote coverage inventory; the config hash and partition counts also match the local published evidence. This compares retained metadata, not fresh Parquet content hashes.
- Fifteen individual tail preparation receipt files exist. The manifest schema explicitly includes all three markout columns.
- All 15 native tail receipts name the expected dates/symbols and record `queue_domain=false`, `queue_decisions=0`, and `measured_queue=false`.
- Retained model status identities in both inspected run roots contain only April, June, September and November. The retained completed queue checkpoint names likewise cover the 20 earlier stock/month blocks.

These records corroborate the engineering-only use and remove the initial remote-access limitation. They do not constitute a complete historical record of manual reads or deleted ad hoc analyses; that remaining non-exposure evidence is the operator attestation below. No remote jobs were started and no settings were changed. Private paths, connection details and telemetry are omitted.


## Operator attestation and next-stage boundary

No contaminating action was identified in the evidence inspected. Before the operator clarification, the audit could not establish non-exposure because the label-bearing caches lacked a complete retained access history. The operator then explicitly confirmed recollection that the proposed partitions had not been used and asked that this be recorded. This is an operator statement about historical scientific use, not a newly discovered technical receipt. The remaining technical limitations in the exposure matrix are preserved rather than retrospectively described as verified.

All 15 partitions are accepted together; no outcome-based subset selection occurred. Before any future confirmation run, commit the frozen protocol and configuration required by the task. This audit does not itself preregister training, aggregation or execution rules, and does not authorize interpreting existing engineering counts as confirmation results. A subsequent report must disclose reliance on operator attestation and the limited three-date period. If conflicting provenance later appears, reassess eligibility before viewing outcomes; use newly acquired, licensed chronological data with recorded non-exposure if these dates cannot remain eligible.

No new IC, crossed-book or queue confirmation value is reported. Earlier published claims are unchanged; this audit supplies no new out-of-sample replication claim.

**PASS — scientifically untouched**
