"""Render small scientific figures from public aggregate CSVs only."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt


def markdown_table(frame, columns):
    header = "| " + " | ".join(columns.values()) + " |\n"
    separator = "| " + " | ".join("---" for _ in columns) + " |\n"
    rows = []
    for record in frame.to_dict("records"):
        values = []
        for key in columns:
            value = record[key]
            if pd.isna(value): value = "NA"
            elif isinstance(value, (float, np.floating)): value = f"{value:.6f}"
            values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return header + separator + "\n".join(rows)


def render_report(root):
    manifest = json.loads((root/"run_manifest.json").read_text())
    robust = pd.read_csv(root/"paired_model_robustness.csv")
    overall = robust[robust.scope=="overall"]
    summary = pd.read_csv(root/"summary.csv")
    primary = summary[summary.control_seed.isna()]
    instant = primary[primary.latency==0]
    controls = summary[summary.control_seed.notna()]
    minimums = robust[robust.scope.isin(["leave_one_symbol","leave_one_month"])].groupby(["horizon","scope"],as_index=False).mean_delta_ic.min()
    lines = ["# Execution-Aware Robustness — WSELOB 2017", "",
        "## Result", "",
        "The small XGBoost improvement in midpoint IC survives the paired stock/month checks. It does **not** establish an executable trading edge: all primary model/horizon/latency headline top-decile long, bottom-decile short, and fixed-threshold crossed-book markouts are negative. Delay worsens the primary headline markouts. No primary block has the full expected ten-decile ordering after crossing.", "",
        "These are historical visible-quote diagnostics, not realized PnL. A negative execution result is retained without changing the models, thresholds, holdouts, or latency grid.", "",
        "## Completed scope", "",
        f"Phases 0–2: {manifest['prediction_tasks']}/{manifest['prediction_tasks']} reused prediction tasks and {manifest['execution_blocks']}/{manifest['expected_execution_blocks']} execution cells completed. The prediction denominator is 60 Linear + 60 XGBoost + 17 shuffled-label XGBoost controls. No retraining was used for these phases. Existing published benchmark artifacts are unchanged.", "",
        "Five stocks (KGHM, PKNORLEN, PKOBP, PZU, PEKAO), four fixed test months (April, June, September, November 2017), horizons 10/20/50 original messages, latency offsets 0/1/5 original messages. Models use the same five frozen causal features and expanding, strictly earlier training days.", "",
        "## Paired midpoint robustness", "",
        markdown_table(overall,{"horizon":"Horizon","mean_delta_ic":"Mean IC delta","median_delta_ic":"Median delta","wins":"Wins / 20","descriptive_lower":"Descriptive 2.5%","descriptive_upper":"Descriptive 97.5%"}), "",
        "Each observation is a paired stock/month IC difference, XGBoost minus Linear. The interval uses 10,000 resamples of the 20 paired blocks, seed 20260914. Shared stocks, months, and overlapping labels mean these blocks are not guaranteed independent. These are **descriptive robustness intervals**, not formal significance tests or row-count p-values.", "",
        "All leave-one-stock and leave-one-month mean deltas remain positive. The minimum across each deletion family is:", "",
        markdown_table(minimums,{"horizon":"Horizon","scope":"Deletion family","mean_delta_ic":"Minimum retained mean delta"}), "",
        "Per-stock, per-month, individual paired blocks, and every leave-one-out value are in [paired_model_robustness.csv](../results/wselob_execution_robustness_v1/paired_model_robustness.csv) and [paired_block_deltas.csv](../results/wselob_execution_robustness_v1/paired_block_deltas.csv).", "",
        "![Paired IC deltas](../results/wselob_execution_robustness_v1/paired_ic_delta.png)", "",
        "## Crossed-book outcomes", "",
        "At decision event t, entry uses the ask for a long and bid for a short at t+d. Exit uses the opposite quote at exactly t+d+h. Both outcomes use the entry midpoint as denominator:", "",
        "```text", "long_bps  = 10000 × (bid[t+d+h] − ask[t+d]) / midpoint[t+d]", "short_bps = 10000 × (bid[t+d] − ask[t+d+h]) / midpoint[t+d]", "```", "",
        "All lookups stay inside the same stock, trading day, and uninterrupted valid book segment. Event gaps are rejected rather than interpreted as the next valid quote. The prediction remains fixed at t; future prices only define outcomes. Saved prediction checksums, timestamps, original event indices, and original midpoint labels must match the cached rows exactly.", "",
        "For each stock/month/horizon, the intersection of valid rows across all three latencies is used for both models and all controls. Thus delay comparisons use identical rows, fixed predictions, fixed bins, and fixed threshold coverage. The common primary row counts per model are 16,845,687 / 16,804,885 / 16,693,438 at 10/20/50 messages. Removed tail rows and original denominators are recorded per task in run_manifest.json and block_metrics.csv.", "",
        "The existing fixed threshold is strictly |prediction| > 1 bp. Positive predictions select long, negative predictions short; zero selects no direction. Coverage is the equal-weight mean of the 20 block coverage fractions, not a pooled fraction. Markouts are equal-weight block means, not row-weighted means.", "",
        "### Zero-delay headline", "",
        markdown_table(instant,{"model":"Model","horizon":"Horizon","top_decile_long_bps":"Top-decile long bps","bottom_decile_short_bps":"Bottom-decile short bps","sign_selected_bps":"Threshold-selected bps","coverage":"Threshold coverage fraction"}), "",
        "XGBoost's larger midpoint IC does not make it a universal winner under crossing. Its threshold-selected zero-delay result improves on Linear at 10 messages, but is worse at 20 and 50 messages. The two models select different subsets under the same 1 bp rule; coverage is therefore reported alongside this conditional comparison. Both are evaluated on the same eligible base rows.", "",
        "### Delay sensitivity", "",
        markdown_table(primary,{"model":"Model","horizon":"Horizon","latency":"Delay (messages)","sign_selected_bps":"Threshold-selected bps","ordered_deciles":"Fraction fully ordered"}), "",
        "Deciles use within-block prediction quantiles with equal predictions kept together. Full expected ordering requires all nine adjacent long differences to be nonnegative and all nine short differences nonpositive. It holds in 0/20 primary blocks for every horizon and latency. This strict measure does not imply there is no local relation between prediction and outcome. The full curves show the spread-dependent shape.", "",
        "![Crossed-book deciles](../results/wselob_execution_robustness_v1/crossed_markout_deciles.png)", "",
        "Absolute latency changes are in [latency_summary.csv](../results/wselob_execution_robustness_v1/latency_summary.csv); paired Linear/XGBoost differences on identical eligible rows are in [paired_execution_differences.csv](../results/wselob_execution_robustness_v1/paired_execution_differences.csv).", "",
        "## Negative controls", "",
        "All 17 original shuffled-label controls were reused: all five stocks in June at three horizons, seed 7, plus PEKAO June 20-message seeds 17 and 29. All control cells lack full decile ordering. None selects any observation under the fixed 1 bp threshold, so selected markout is **undefined**, not zero. Aggregate extreme-decile crossed outcomes are negative. There is no retained control success requiring a stronger-claim investigation; the primary execution conclusion remains negative.", "",
        markdown_table(controls[controls.latency==0],{"horizon":"Horizon","control_seed":"Seed","blocks":"Blocks","top_decile_long_bps":"Top long bps","bottom_decile_short_bps":"Bottom short bps","selected_rows":"Selected rows"}), "",
        "## Scientific identity and reproducibility", "",
        "Version-2 scientific task IDs include dataset/session definitions, features, split and metric rules, model hyperparameters, control seeds, scientific outcome settings, and content hashes of input partitions. Device, worker count, paths, telemetry, runtime limits, and publication settings are excluded. Cache manifests created by the updated pipeline use the same scientific config view. Legacy caches and prediction receipts retain their original identities as immutable provenance; the new experiment checks their content and row identity explicitly. Source hashes are recorded separately from task identity.", "",
        "Only aggregate artifacts and input checksums are public. Raw data, row-level predictions, private checkpoint folders, and local telemetry remain outside Git. Reuse requires the original private prediction receipts and matching licensed cache; alternatively regenerate the baseline with its frozen scientific settings and retain its original row identities. This version's reuse runner deliberately requires the published legacy task IDs, so a fresh baseline must supply its own matching metrics and prediction receipts rather than pretending to reproduce the original device's exact numerical predictions.", "",
        "```bash",
        "PYTHONPATH=src python scripts/run_execution_robustness.py \\",
        "  --config configs/wselob_execution_robustness_v1.json \\",
        "  --metrics results/wselob_xgboost_application_v1/model_metrics_by_symbol_month.csv \\",
        "  --cache \"$CACHE\" --prediction-roots \"$LINEAR_RUNS\" \"$XGBOOST_RUNS\" \\",
        "  --work \"$PRIVATE_CHECKPOINTS\" --out results/wselob_execution_robustness_v1",
        "python scripts/render_execution_robustness.py",
        "```",
        "",
        "[run_manifest.json](../results/wselob_execution_robustness_v1/run_manifest.json) binds each reused prediction file to the new scientific task ID and records complete denominators. Checkpoint reuse requires unchanged scientific settings, input hashes, prediction hashes, and analysis implementation. Incomplete or mismatched tasks fail aggregation.", "",
        "## Validation", "",
        "The implementation passed 60 local tests. Coverage includes hand-calculated long/short formulas, exact latency indices, day/segment boundaries, execution-independent scientific IDs, changed scientific settings, matching paired blocks, incomplete denominators, and transfer chronology/held-out-stock exclusion. The public privacy check passed. The implementation CI passed on Python 3.10 and 3.12; subsequent publication commits run the same workflow. No numerical significance or real trading claim is inferred from these software checks.", "",
        "## Optional stock transfer", ""]
    transfer_path = root/"transfer_summary.csv"
    if transfer_path.exists():
        transfer = pd.read_csv(transfer_path)
        headline = transfer[(transfer.scope=="overall") & transfer.control_seed.isna()].iloc[0]
        control = transfer[(transfer.scope=="overall") & transfer.control_seed.notna()].iloc[0]
        lines += [f"The pooled-other-stock model retains comparable midpoint IC: {headline.mean_transfer_ic:.6f} versus {headline.mean_within_stock_ic:.6f} within-stock, a mean difference of {headline.mean_delta_ic:+.6f}, with {int(headline.wins)}/20 block wins. This is a small descriptive difference, not evidence that transfer is universally better. The June shuffled transfer control averages {control.mean_transfer_ic:.6f} IC: substantially weaker, but not zero. No significance is inferred from the row count.", "",
            "Phase 3 completed 20 primary tasks and five June shuffled-label controls at the fixed 20-message horizon. Each task trains on strictly earlier data from the other four stocks, using the original five features and XGBoost hyperparameters. Controls shuffle within each training stock/day with seed 7. Test row identities and labels match the original within-stock comparator exactly. No model or threshold tuning was performed.", "",
            markdown_table(transfer,{"scope":"Scope","member":"Member","control_seed":"Control seed","blocks":"Blocks","mean_transfer_ic":"Transfer IC","mean_within_stock_ic":"Within-stock IC","mean_delta_ic":"Transfer minus within","wins":"Wins"}), "",
            "![Transfer versus within-stock IC](../results/wselob_execution_robustness_v1/transfer_vs_within_stock.png)", "",
            "Transfer is a midpoint prediction diagnostic. It does not overturn the negative crossed-book results above. Primary and shuffled transfer denominators are separate; the control comparison is descriptive."]
    else:
        lines += ["The mandatory Phase 0–2 result is complete. The optional fixed 20-message transfer experiment is running separately and is not included in the results above."]
    lines += ["", "## Limits and attribution", "",
        "Visible-quote crossing excludes fees/rebates, hidden liquidity, fills, queue position, impact, and inventory constraints. Event latency is measured in messages, not a fixed number of milliseconds. Holdout blocks were already used in the published benchmark; this robustness extension is not a new untouched confirmation sample. The findings concern five Polish equities in 2017, not current crypto-market profitability.", "",
        "Source: Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1, CC BY 4.0. Modifications: reconstructed book features, frozen predictions, paired robustness and crossed-book aggregation. Provided as-is; no endorsement. See [license and source details](WSELOB_LICENSE.md).", ""]
    Path("docs/EXECUTION_AWARE_ROBUSTNESS_REPORT.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/wselob_execution_robustness_v1")
    args = parser.parse_args()
    root = Path(args.results)
    paired = pd.read_csv(root/"paired_block_deltas.csv")
    horizons = sorted(paired.horizon.unique())
    fig, axes = plt.subplots(1, len(horizons), figsize=(11,3.7), constrained_layout=True)
    bound = max(abs(paired.delta_ic).max(), .001)
    for ax, horizon in zip(np.atleast_1d(axes), horizons):
        table = paired[paired.horizon==horizon].pivot(index="symbol",columns="month",values="delta_ic")
        plot = ax.imshow(table, cmap="RdBu", vmin=-bound, vmax=bound, aspect="auto")
        ax.set_xticks(range(len(table.columns)), [month[5:] for month in table.columns])
        ax.set_yticks(range(len(table.index)),table.index)
        ax.set_title(f"{horizon} messages")
        ax.set_xlabel("Test month (2017)")
        for y in range(len(table.index)):
            for x in range(len(table.columns)):
                value = table.iloc[y,x]
                ax.text(x,y,f"{value:+.3f}",ha="center",va="center",fontsize=8,
                        color="white" if abs(value)>.65*bound else "black")
    fig.colorbar(plot,ax=axes,label="XGBoost − Linear IC",shrink=.8)
    fig.suptitle("Paired stock/month uplift: same held-out blocks")
    fig.savefig(root/"paired_ic_delta.png",dpi=160)
    plt.close(fig)

    deciles = pd.read_csv(root/"prediction_deciles.csv")
    deciles = deciles[deciles.control_seed.isna()]
    fig, axes = plt.subplots(2,len(horizons),figsize=(12,7),constrained_layout=True)
    for col,horizon in enumerate(horizons):
        for row,(metric,label) in enumerate([("long_crossed_bps","Long: future bid − entry ask"),("short_crossed_bps","Short: entry bid − future ask")]):
            ax = axes[row,col]
            for model,color in [("linear","#2563eb"),("xgboost","#d97706")]:
                for latency,style in [(0,"-"),(1,"--"),(5,":")]:
                    part = deciles[(deciles.horizon==horizon)&(deciles.model==model)&(deciles.latency==latency)]
                    ax.plot(part.decile,part[metric],linestyle=style,color=color,label=f"{model}, delay {latency}",linewidth=1.6)
            ax.axhline(0,color="black",linewidth=.8)
            ax.set_title(f"{horizon} messages after entry")
            ax.set_xlabel("Within-block prediction decile")
            ax.set_ylabel(label+" (bps)")
            ax.grid(alpha=.15)
    handles,labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=3,fontsize=9)
    fig.suptitle("Visible crossed-book outcomes: equal-weight stock/month means\nHistorical quote diagnostics; not realized PnL")
    fig.savefig(root/"crossed_markout_deciles.png",dpi=160)
    plt.close(fig)

    transfer_path = root/"transfer_block_metrics.csv"
    if transfer_path.exists():
        transfer = pd.read_csv(transfer_path)
        transfer = transfer[transfer.control_seed.isna()]
        fig,ax = plt.subplots(figsize=(6,5),constrained_layout=True)
        lower=min(transfer.ic.min(),transfer.within_stock_ic.min())-.02
        upper=max(transfer.ic.max(),transfer.within_stock_ic.max())+.02
        ax.plot([lower,upper],[lower,upper],color="gray",linestyle="--",label="Equal IC")
        for symbol,part in transfer.groupby("symbol"):
            ax.scatter(part.within_stock_ic,part.ic,label=symbol,s=45)
        ax.set(xlabel="Within-stock XGBoost IC",ylabel="Other-four-stocks transfer IC",
               title="Leave-one-stock-out transfer: 20 messages",xlim=(lower,upper),ylim=(lower,upper))
        ax.legend(fontsize=9)
        fig.savefig(root/"transfer_vs_within_stock.png",dpi=160)
        plt.close(fig)

    render_report(root)


if __name__ == "__main__":
    main()
