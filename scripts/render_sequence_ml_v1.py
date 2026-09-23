"""Rebuild four public figures and a cost table from aggregate receipts only."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np


ROOT = Path("results/sequence_ml_v1")
FIGURES = ROOT / "figures"
BLUE, TEAL, ORANGE = "#3855a6", "#087f72", "#c96b26"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / name
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def header(ax, title):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.2)


def main():
    q2_path, q3_path = ROOT/"q2_summary.json", ROOT/"q3_summary.json"
    q2, q3 = json.loads(q2_path.read_text()), json.loads(q3_path.read_text())
    outputs = []
    # 1. Current-state and history-matched model comparison.
    names = ["A0\ncurrent Ridge", "A1\ncurrent XGB", "B0\nhistory Ridge",
             "B1\nhistory XGB", "S0\nhistory GRU"]
    keys = ["A0_current_ridge", "A1_current_xgboost", "B0_history_ridge", "B1_history_xgboost"]
    values = [q2["evaluation_mean_ic"][k] for k in keys]
    values.append(float(np.mean([q2["evaluation_mean_ic"][f"S0_history_gru_seed{s}"] for s in (7,17,29)])))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(names, values, color=["#aab5c9", "#7187b9", "#98c5bf", BLUE, TEAL])
    for bar, val in zip(bars, values):
        ax.text(bar.get_x()+bar.get_width()/2, val+.002, f"{val:.3f}", ha="center", fontsize=9)
    ax.set_ylim(0, max(values)*1.16)
    ax.set_ylabel("Equal stock/day Spearman IC")
    header(ax, "1  Same endpoints: current state, matched history, GRU")
    ax.text(.01, -.22, "WSELOB-2017 retrospective; S0 bar averages three seed ICs. 315 shared stock/day cells per arm.",
            transform=ax.transAxes, fontsize=8, color="#555")
    outputs.append(save(fig, "01_history_matched_models.png"))
    # 2. Fixed information cutoff versus frozen-rule updates.
    months = ["2017-06", "2017-09", "2017-11"]
    x = np.arange(3)
    b_fixed = [q3["time_fixed_vs_updated"][m]["B1_history_xgboost"]["fixed_ic"] for m in months]
    b_update = [q3["time_fixed_vs_updated"][m]["B1_history_xgboost"]["updated_ic"] for m in months]
    g_fixed = [np.mean([q3["time_fixed_vs_updated"][m][f"S0_history_gru_seed{s}"]["fixed_ic"] for s in (7,17,29)]) for m in months]
    g_update = [np.mean([q3["time_fixed_vs_updated"][m][f"S0_history_gru_seed{s}"]["updated_ic"] for s in (7,17,29)]) for m in months]
    fig, ax = plt.subplots(figsize=(8, 4.7))
    for series, color, style, label in ((b_fixed, BLUE, "-", "B* fixed"),
                                        (b_update, BLUE, "--", "B* updated"),
                                        (g_fixed, TEAL, "-", "GRU fixed"),
                                        (g_update, TEAL, "--", "GRU updated")):
        ax.plot(x, series, linestyle=style, marker="o", color=color, linewidth=2, label=label)
    ax.set_xticks(x, ["Jun", "Sep", "Nov"])
    ax.set_ylabel("Equal stock/day Spearman IC")
    ax.legend(ncol=2, frameon=False)
    header(ax, "2  Same dates: fixed model versus later frozen-rule refits")
    ax.text(.01, -.22, "Exposed 2017 periods; updates use later data. Calendar effects and information gains are confounded.",
            transform=ax.transAxes, fontsize=8, color="#555")
    outputs.append(save(fig, "02_fixed_vs_updated_time.png"))
    # 3. Full stock and one predeclared decision-time state breakdown.
    stock = q2["paired_vs_selected_history"]["S0_seed_mean"]["stock_delta"]
    symbols = q2["symbols"]
    changes = [stock[s] for s in symbols]
    states = q3["state"]
    state_vals = [states["high_activity"]["paired_delta_ic"]["full_denominator_mean"],
                  states["low_activity"]["paired_delta_ic"]["full_denominator_mean"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), gridspec_kw={"width_ratios": [1.6, 1]})
    axes[0].bar(symbols, changes, color=[TEAL if v >= 0 else ORANGE for v in changes])
    axes[0].axhline(0, color="#444", linewidth=.8)
    axes[0].set_ylabel("GRU seed-mean − B* IC")
    header(axes[0], "Across all five stocks")
    axes[1].bar(["High past\nactivity", "Low past\nactivity"], state_vals, color=[TEAL, "#6caaa0"])
    axes[1].set_ylabel("GRU prediction-mean − B* IC")
    header(axes[1], "One frozen state split")
    fig.suptitle("3  Historical heterogeneity: PZU is negative", x=.02, ha="left", fontsize=13, fontweight="bold")
    fig.subplots_adjust(top=.78)
    fig.text(.02, -.015, "Stock panel averages seed-specific ICs; state panel scores averaged predictions. Both are retrospective.", fontsize=8, color="#555")
    outputs.append(save(fig, "03_stock_and_state_breakdown.png"))
    # 4. Visible crossing costs and rule coverage on common opportunities.
    components = {}
    for model in ("B1_history_xgboost", "S0_seed_mean"):
        rows = []
        for symbol in q2["symbols"]:
            report = json.loads((ROOT/f"q3_diagnostic_{symbol}.json").read_text())
            rows.extend(r for r in report["execution"] if r["model"] == model)
        count = sum(r["selected"] for r in rows)
        if len(rows) != 315 or count == 0:
            raise ValueError("incomplete crossing denominator")
        components[model] = {key: sum(r[key]*r["selected"] for r in rows)/count
                             for key in ("gross_midpoint_bps", "entry_half_spread_bps", "exit_half_spread_bps", "crossed_bps")}
        components[model]["coverage"] = count/625118
        if abs(components[model]["gross_midpoint_bps"]-components[model]["entry_half_spread_bps"]
               -components[model]["exit_half_spread_bps"]-components[model]["crossed_bps"]) > 1e-8:
            raise ValueError("crossing cost identity failed")
    fig, (ax, cov) = plt.subplots(1, 2, figsize=(9.6, 4.6), gridspec_kw={"width_ratios": [2, 1]})
    labels = ["B*", "GRU mean"]
    models = list(components)
    x = np.arange(2)
    width = .19
    for j, (key, label, color, sign) in enumerate((("gross_midpoint_bps", "Gross mid", TEAL, 1),
                                                    ("entry_half_spread_bps", "Entry half-spread", "#d3a356", -1),
                                                    ("exit_half_spread_bps", "Exit half-spread", ORANGE, -1),
                                                    ("crossed_bps", "Visible crossed", BLUE, 1))):
        ax.bar(x+(j-1.5)*width, [components[m][key]*sign for m in models], width=width, label=label, color=color)
    ax.axhline(0, color="#444", linewidth=.8)
    ax.set_xticks(x, labels)
    ax.set_ylabel("bp per selected opportunity")
    ax.legend(frameon=False, fontsize=8)
    header(ax, "Prediction movement versus spread costs")
    cov.bar(labels, [100*components[m]["coverage"] for m in models], color=[BLUE, TEAL])
    cov.set_ylabel("Selected / common opportunities, %")
    header(cov, "Coverage")
    fig.suptitle("4  Higher historical IC did not pay fixed visible crossing", x=.02, ha="left", fontsize=13, fontweight="bold")
    fig.subplots_adjust(top=.78)
    fig.text(.02, -.015, "One-share, zero-delay, |prediction|>1 bp; 625,118 common opportunities. No fees, impact or actual fills.",
             fontsize=8, color="#555")
    outputs.append(save(fig, "04_prediction_vs_crossing.png"))
    # Exact aggregate cost table; no claimed CPU core-hours without process CPU telemetry.
    table = ROOT/"cost_table.csv"
    with table.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["arm", "q2_fit_seconds_five_stocks", "q2_inference_seconds_five_stocks",
                         "q3_updated_fit_seconds_fifteen_stock_month_tasks", "device", "gpu_hours"])
        for arm, fit in q2["fit_seconds_by_arm"].items():
            updated = q3["updated_fit_seconds"].get(arm)
            writer.writerow([arm, f"{fit:.6f}", f"{q2['inference_seconds_by_arm'][arm]:.6f}",
                             f"{updated:.6f}" if updated is not None else "", "local CPU", 0])
    manifest = ROOT/"q6_render_manifest.json"
    manifest.write_text(json.dumps({"source_aggregate_sha256": {"q2_summary": sha(q2_path), "q3_summary": sha(q3_path)},
                                    "figures_sha256": {p.name: sha(p) for p in outputs},
                                    "cost_table_sha256": sha(table),
                                    "limits": "All figures are from previously exposed 2017 aggregate receipts; no new final or PnL claim."},
                                   indent=2, sort_keys=True)+"\n")
    print(json.dumps({"figures": [p.name for p in outputs], "cost_table": table.name,
                      "manifest_sha256": sha(manifest)}))


if __name__ == "__main__":
    main()
