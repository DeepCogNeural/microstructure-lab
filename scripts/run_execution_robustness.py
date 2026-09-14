"""Reuse frozen prediction receipts for paired crossed-book diagnostics.

Row data and checkpoints stay in the explicitly supplied private work directory.
Only aggregate CSV/JSON outputs are written to --out.
"""
from __future__ import annotations
import argparse
import itertools
from pathlib import Path
import numpy as np
import pandas as pd
from cloblab.execution_labels import crossed_labels
from cloblab.robustness import paired_robustness, summarize_predictions
from cloblab.scale_common import atomic_json, digest, file_hash, read_json
from cloblab.scientific_identity import scientific_config, scientific_task_id


KEYS = ["symbol", "month", "horizon", "model", "control_seed"]


def expected_keys(config):
    keys = set()
    controls = config["negative_controls"]
    for symbol, month, horizon in itertools.product(config["dataset"]["symbols"], config["evaluation"]["fixed_test_months"], config["dataset"]["horizons_events"]):
        for model in ("linear", "xgboost"):
            keys.add((symbol, month, horizon, model, None))
        if month == controls["representative_month"]:
            keys.add((symbol, month, horizon, "xgboost", controls["seed"]))
        extra = controls["extra_seed_check"]
        if (symbol, month, horizon) == (extra["symbol"], extra["month"], extra["horizon_events"]):
            keys.update((symbol, month, horizon, "xgboost", seed) for seed in extra["seeds"])
    return keys


def collect_receipts(roots, config):
    found = {}
    expected = expected_keys(config)
    for root in roots:
        for path in sorted(Path(root).glob("tasks/*/status.json")):
            receipt = read_json(path)
            task = receipt["task"]
            key = tuple(task[k] for k in KEYS)
            if key not in expected or receipt["state"] != "complete":
                continue
            for name in ("predictions.npz", "metrics.json"):
                if file_hash(path.parent/name) != receipt["artifacts"][name]:
                    raise ValueError("prediction or metric content differs from completed receipt")
            if key in found and found[key][1]["artifacts"]["predictions.npz"] != receipt["artifacts"]["predictions.npz"]:
                raise ValueError("conflicting duplicate predictions")
            found[key] = (path.parent, receipt)
    if set(found) != expected:
        raise ValueError(f"incomplete prediction denominator: {len(found)}/{len(expected)}")
    return found


def load_month(cache, manifest, symbol, month, features, horizon):
    pieces, quotes = [], []
    # Preserve the legacy manifest order used to create saved prediction arrays.
    for part in manifest["partitions"]:
        if part["symbol"] != symbol or part["day"][:7] != month:
            continue
        folder = Path(cache)/f"symbol={symbol}"/f"day={part['day']}"
        for name in ("features", "snapshots"):
            if file_hash(folder/f"{name}.parquet") != part[f"{name}_sha256"]:
                raise ValueError("input partition hash mismatch")
        columns = ["symbol", "day", "segment", "event_index", "timestamp_ns"]
        f = pd.read_parquet(folder/"features.parquet", columns=columns+features+[f"markout_{horizon}"])
        pieces.append(f.replace([np.inf, -np.inf], np.nan).dropna(subset=features+[f"markout_{horizon}"]))
        quotes.append(pd.read_parquet(folder/"snapshots.parquet", columns=columns+["bid_px_1", "ask_px_1"]))
    if not pieces:
        raise ValueError("missing fixed test month")
    return pd.concat(pieces, ignore_index=True), pd.concat(quotes, ignore_index=True)


def evaluate_block(config, manifest, cache, found, symbol, month, horizon):
    features = config["features"]["primary_set"]
    rows, quotes = load_month(cache, manifest, symbol, month, features, horizon)
    latencies = config["execution_labels"]["latency_events"]
    labels = {}
    index_keys = ["symbol", "day", "segment", "event_index", "timestamp_ns"]
    row_index = pd.MultiIndex.from_frame(rows[index_keys])
    common = np.ones(len(rows), dtype=bool)
    for latency in latencies:
        target = crossed_labels(quotes, horizon, latency).set_index(index_keys).reindex(row_index)
        labels[latency] = target[["long_crossed_bps", "short_crossed_bps"]].to_numpy()
        common &= np.isfinite(labels[latency]).all(axis=1)
    summaries, deciles, evidence = [], [], []
    keys = sorted((k for k in found if k[:3] == (symbol, month, horizon)), key=lambda k: (k[3], -1 if k[4] is None else k[4]))
    for key in keys:
        folder, receipt = found[key]
        task = dict(zip(KEYS, key))
        task_id = scientific_task_id(config, task, manifest)
        with np.load(folder/"predictions.npz", allow_pickle=False) as saved:
            if not np.array_equal(saved["timestamp_ns"], rows.timestamp_ns) or not np.array_equal(saved["event_index"], rows.event_index):
                raise ValueError("saved predictions do not match exact decision row identities")
            if not np.array_equal(saved["actual"], rows[f"markout_{horizon}"]):
                raise ValueError("saved prediction label differs from frozen cache")
            prediction = saved["prediction"][common]
        identity = {**task, "task_id": task_id}
        evidence.append({**identity, "legacy_task_id": receipt["task"]["task_id"],
                         "prediction_sha256": receipt["artifacts"]["predictions.npz"],
                         "original_rows": len(rows), "common_rows": int(common.sum())})
        for latency in latencies:
            long, short = labels[latency][common].T
            summary, quantiles = summarize_predictions(prediction, long, short, config["execution_labels"]["threshold_bps"])
            ident = {**identity, "latency": latency}
            summaries.append({**ident, "original_rows": len(rows), **summary})
            deciles.extend({**ident, **record} for record in quantiles.to_dict("records"))
    return summaries, deciles, evidence


def aggregate_outputs(blocks, deciles, config):
    expected = {(*key, latency) for key in expected_keys(config) for latency in config["execution_labels"]["latency_events"]}
    actual = set()
    for row in blocks.to_dict("records"):
        actual.add(tuple(None if pd.isna(row[k]) else row[k] for k in KEYS+["latency"]))
    if len(blocks) != len(expected) or actual != expected:
        raise ValueError("incomplete execution block denominator")
    group = ["model", "horizon", "control_seed", "latency"]
    metrics = ["coverage", "sign_selected_bps", "top_decile_long_bps", "bottom_decile_short_bps", "ordered_deciles", "decile_bins"]
    summary = blocks.groupby(group, dropna=False)[metrics].mean().reset_index()
    counts = blocks.groupby(group, dropna=False).agg(blocks=("rows", "size"), total_rows=("rows", "sum"),
        selected_blocks=("sign_selected_bps", "count"), selected_rows=("selected_rows", "sum")).reset_index()
    summary = summary.merge(counts, on=group, validate="one_to_one")
    # Report undefined threshold blocks explicitly; never silently change denominator.
    summary.loc[summary.selected_blocks != summary.blocks, "sign_selected_bps"] = np.nan
    q = deciles.groupby(group+["decile"], dropna=False).agg(
        long_crossed_bps=("long_crossed_bps", "mean"), short_crossed_bps=("short_crossed_bps", "mean"),
        sign_selected_bps=("sign_selected_bps", "mean"), prediction_bps=("prediction_bps", "mean"), blocks=("rows", "size")).reset_index()
    baseline = summary[summary.latency == 0][["model", "horizon", "control_seed"]+metrics]
    latency = summary.merge(baseline, on=["model", "horizon", "control_seed"], suffixes=("", "_latency0"), validate="many_to_one")
    for key in metrics:
        latency[key+"_change_from_latency0"] = latency[key]-latency[key+"_latency0"]
    primary = blocks[blocks.control_seed.isna()]
    left = primary[primary.model == "linear"]
    right = primary[primary.model == "xgboost"]
    paired = left.merge(right, on=["symbol", "month", "horizon", "latency"], suffixes=("_linear", "_xgboost"), validate="one_to_one")
    if not (paired.rows_linear == paired.rows_xgboost).all():
        raise ValueError("unpaired execution rows")
    for key in metrics:
        paired[key+"_delta"] = paired[key+"_xgboost"]-paired[key+"_linear"]
    return summary, q, latency, paired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--prediction-roots", nargs="+", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    config, manifest = read_json(args.config), read_json(Path(args.cache)/"manifest.json")
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    paired, robust = paired_robustness(pd.read_csv(args.metrics), config["dataset"]["symbols"], config["evaluation"]["fixed_test_months"],
            config["dataset"]["horizons_events"], config["robustness"]["bootstrap_seed"], config["robustness"]["bootstrap_draws"])
    paired.to_csv(out/"paired_block_deltas.csv", index=False)
    robust.to_csv(out/"paired_model_robustness.csv", index=False)
    found = collect_receipts(args.prediction_roots, config)
    published = pd.read_csv(args.metrics)
    published_ids = set(published[published.model.isin(["linear", "xgboost"])].task_id)
    if {receipt["task"]["task_id"] for _, receipt in found.values()} != published_ids:
        raise ValueError("saved predictions do not match the published benchmark task IDs")
    # The old prediction/cache identity remains provenance; never overwrite it.
    if {r[1]["task"]["cache_hash"] for r in found.values()} != {digest(manifest)}:
        raise ValueError("predictions are bound to a different cache manifest")
    code_hash = digest({p.name: file_hash(p) for p in [Path(__file__), *[Path(__file__).parents[1]/"src/cloblab"/name for name in ("execution_labels.py", "robustness.py", "scientific_identity.py")]]})
    binding = digest({"science": scientific_config(config), "cache": digest(manifest), "code": code_hash,
                      "predictions": sorted(r[1]["artifacts"]["predictions.npz"] for r in found.values())})
    summaries, deciles, evidence = [], [], []
    for symbol, month, horizon in itertools.product(config["dataset"]["symbols"], config["evaluation"]["fixed_test_months"], config["dataset"]["horizons_events"]):
        checkpoint = work/f"{symbol}-{month}-{horizon}.json"
        if checkpoint.exists():
            saved = read_json(checkpoint)
            if saved["binding"] != binding:
                raise ValueError("stale execution checkpoint")
            s, q, e = saved["summaries"], saved["deciles"], saved["evidence"]
        else:
            s, q, e = evaluate_block(config, manifest, args.cache, found, symbol, month, horizon)
            from cloblab.scale_runner import finite_json
            atomic_json(checkpoint, finite_json(dict(binding=binding, summaries=s, deciles=q, evidence=e)))
        summaries.extend(s); deciles.extend(q); evidence.extend(e)
        print(f"completed {symbol} {month} {horizon}: {len(evidence)}/{len(found)} prediction tasks", flush=True)
    blocks, decile_blocks = pd.DataFrame(summaries), pd.DataFrame(deciles)
    summary, q, latency, comparison = aggregate_outputs(blocks, decile_blocks, config)
    for name, frame in (("summary", summary), ("latency_summary", latency), ("block_metrics", blocks), ("prediction_deciles", q),
                        ("block_prediction_deciles", decile_blocks), ("paired_execution_differences", comparison)):
        frame.to_csv(out/f"{name}.csv", index=False)
    atomic_json(out/"run_manifest.json", dict(complete=True, prediction_tasks=len(found), execution_blocks=len(blocks),
        expected_execution_blocks=len(expected_keys(config))*len(config["execution_labels"]["latency_events"]),
        scientific_config_hash=digest(scientific_config(config)), analysis_source_hash=code_hash, input_binding=binding,
        original_cache_hash=digest(manifest), task_evidence=evidence,
        attribution="Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1; CC BY 4.0. Derived crossed-book aggregates; no endorsement.",
        limitations="Historical visible quotes, not realized PnL. Overlapping observations are dependent; bootstrap is descriptive."))


if __name__ == "__main__":
    main()
