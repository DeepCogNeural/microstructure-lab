"""Day-separated evaluation of explicitly licensed, event-indexed snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from cloblab.advanced_features import add_microstructure_features
from cloblab.evaluation import _fit_predict_linear, _score_predictions
from cloblab.models import TreeModelConfig, fit_predict_tree

FEATURE_SETS = {
    "spread": ["spread_bps"],
    "imbalance": ["spread_bps", "top_imbalance", "depth_imbalance"],
    "ofi": ["spread_bps", "top_imbalance", "depth_imbalance", "ofi_l1_norm"],
    "microprice": ["spread_bps", "top_imbalance", "depth_imbalance", "ofi_l1_norm", "microprice_minus_mid_bps"],
}


def prepare(frame, horizons):
    required = ["symbol", "day", "event_index"] + [
        f"{side}_{kind}_{level}" for side in ("bid", "ask")
        for kind in ("px", "sz") for level in range(1, 11)]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"missing snapshot columns: {missing}")
    if frame[required].isna().any().any() or frame.duplicated(["symbol", "day", "event_index"]).any():
        raise ValueError("missing values or duplicate event identities")
    pieces = []
    groups = ["symbol", "day"] + (["segment"] if "segment" in frame else [])
    for _, group in frame.groupby(groups, sort=True):
        if not group.event_index.is_monotonic_increasing:
            raise ValueError("non-monotonic event order")
        if not group.event_index.diff().dropna().eq(1).all():
            raise ValueError("event gaps require distinct segments")
        if (group.ask_px_1 <= group.bid_px_1).any():
            raise ValueError("crossed or locked book")
        out = add_microstructure_features(group.reset_index(drop=True))
        out["spread_bps"] = 1e4 * out.spread / out.midpoint
        bid = out[[f"bid_sz_{i}" for i in range(1, 11)]].sum(axis=1)
        ask = out[[f"ask_sz_{i}" for i in range(1, 11)]].sum(axis=1)
        out["top_imbalance"] = (out.bid_sz_1-out.ask_sz_1)/(out.bid_sz_1+out.ask_sz_1)
        out["depth_imbalance"] = (bid-ask)/(bid+ask)
        for h in horizons:
            out[f"markout_{h}"] = 1e4*(out.midpoint.shift(-h)/out.midpoint-1)
        pieces.append(out)
    return pd.concat(pieces, ignore_index=True)


def prediction_quantiles(predictions, bins=10):
    pieces = []
    for fold, group in predictions.groupby("fold", sort=True):
        group = group.copy()
        unique = group.prediction_bps.nunique()
        group["prediction_quantile"] = 1 if unique < 2 else pd.qcut(
            group.prediction_bps, q=min(bins, unique), labels=False, duplicates="drop")+1
        pieces.append(group)
    assigned = pd.concat(pieces, ignore_index=True)
    aggregation = dict(count=("prediction_bps", "size"),
        avg_prediction_bps=("prediction_bps", "mean"),
        avg_realized_markout_bps=("realized_markout_bps", "mean"))
    per_fold = assigned.groupby(["fold", "prediction_quantile"], as_index=False).agg(**aggregation)
    aggregate = assigned.groupby("prediction_quantile", as_index=False).agg(
        **aggregation, fold_count=("fold", "nunique"))
    return aggregate, per_fold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--license-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--horizons", nargs="+", type=int, default=[10, 20, 50])
    parser.add_argument("--cost-bps", type=float, default=1.0)
    parser.add_argument("--random-seed", type=int, default=7)
    args = parser.parse_args()
    manifest = json.loads(args.license_manifest.read_text())
    for key in ("dataset", "source_url", "license", "attribution", "boundary_evidence"):
        if not manifest.get(key):
            raise ValueError(f"manifest requires {key}")
    if not all(manifest.get(k) is True for k in ("ml_use_permitted", "aggregate_publication_permitted")):
        raise ValueError("documented ML and publication permission required")
    if "coinbase" in json.dumps(manifest).lower():
        raise ValueError("Coinbase data are excluded")
    if args.input.suffix != ".parquet" or min(args.horizons) <= 0 or args.cost_bps < 0:
        raise ValueError("require Parquet, positive horizons and nonnegative cost")
    data = prepare(pd.read_parquet(args.input), args.horizons)
    metrics, daily, quantiles, fold_quantiles, folds = [], [], [], [], []
    for symbol, stock in data.groupby("symbol", sort=True):
        days = sorted(stock.day.unique())
        if len(days) < 3:
            raise ValueError("at least three documented days required")
        for horizon in args.horizons:
            label = f"markout_{horizon}"
            common = stock.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURE_SETS["microprice"]+[label])
            for feature_set, features in FEATURE_SETS.items():
                for model in ("linear", "tree"):
                    identity = dict(symbol=symbol, horizon_events=horizon, feature_set=feature_set, model=model)
                    pieces = []
                    rng = np.random.default_rng(args.random_seed)
                    for fold, day in enumerate(days[1:], start=1):
                        train, test = common[common.day < day], common[common.day == day]
                        if len(train) < 30 or test.empty:
                            raise ValueError("insufficient fold rows")
                        shuffled = train.copy()
                        shuffled[label] = rng.permutation(train[label].to_numpy())
                        def predict(training):
                            if model == "linear":
                                return _fit_predict_linear(training, test, features, label)
                            return fit_predict_tree(training, test, feature_cols=features, label_col=label,
                                config=TreeModelConfig(random_state=args.random_seed))
                        part = pd.DataFrame({"fold": fold, "prediction_bps": predict(train),
                            "control_prediction_bps": predict(shuffled), "realized_markout_bps": test[label].to_numpy()})
                        pieces.append(part)
                        for control, column in ((False,"prediction_bps"),(True,"control_prediction_bps")):
                            daily.append({**identity,"fold":fold,"day":str(day),"negative_control":control,
                                **_score_predictions(part[column].tolist(),part.realized_markout_bps.tolist(),args.cost_bps)})
                        if feature_set == "microprice" and model == "linear":
                            folds.append({"symbol":symbol,"horizon_events":horizon,"fold":fold,
                                "train_days":[str(x) for x in days if x < day],"test_day":str(day),
                                "train_n":len(train),"test_n":len(test)})
                    pred = pd.concat(pieces,ignore_index=True)
                    for control,column in ((False,"prediction_bps"),(True,"control_prediction_bps")):
                        metrics.append({**identity,"negative_control":control,"test_day_count":len(days)-1,
                            **_score_predictions(pred[column].tolist(),pred.realized_markout_bps.tolist(),args.cost_bps)})
                    if feature_set == "microprice":
                        agg, per_fold = prediction_quantiles(pred)
                        quantiles.extend(agg.assign(**identity).to_dict("records"))
                        fold_quantiles.extend(per_fold.assign(**identity).to_dict("records"))
                    print(json.dumps({**identity, "completed_folds":len(pieces)}), flush=True)
    args.out.mkdir(parents=True,exist_ok=True)
    table = pd.DataFrame(metrics)
    table.to_csv(args.out/"feature_ablation.csv",index=False)
    table[table.feature_set == "microprice"].to_csv(args.out/"model_metrics.csv",index=False)
    pd.DataFrame(daily).to_csv(args.out/"daily_metrics.csv",index=False)
    pd.DataFrame(quantiles).to_csv(args.out/"prediction_quantiles.csv",index=False)
    pd.DataFrame(fold_quantiles).to_csv(args.out/"prediction_quantiles_by_fold.csv",index=False)
    with args.input.open("rb") as handle:
        digest = hashlib.sha256()
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    metadata = {"license":manifest,"input_sha256":digest.hexdigest(),"folds":folds,
        "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        "horizons_events":args.horizons,"tree_config":asdict(TreeModelConfig(random_state=args.random_seed)),
        "seed":args.random_seed,"cost_bps":args.cost_bps,"feature_sets":FEATURE_SETS,
        "label_contract":"consecutive message-event offsets within each stock/day/segment; training days strictly precede test day",
        "limitations":"Overlapping labels are dependent; no IID significance claim. Thresholded midpoint markout is not realized PnL."}
    (args.out/"experiment_metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    qframe = pd.DataFrame(quantiles)
    symbols = sorted(qframe.symbol.unique())
    fig, axes = plt.subplots(len(symbols),len(args.horizons),squeeze=False,
        figsize=(4*len(args.horizons),3*len(symbols)))
    for row,symbol in enumerate(symbols):
        for col,horizon in enumerate(args.horizons):
            ax = axes[row,col]
            subset = qframe[(qframe.symbol == symbol)&(qframe.horizon_events == horizon)]
            for model,group in subset.groupby("model"):
                ax.plot(group.prediction_quantile,group.avg_realized_markout_bps,marker="o",label=model)
            ax.set_title(f"{symbol}: {horizon} events")
            ax.set_xlabel("Within-fold prediction quantile")
            ax.set_ylabel("Midpoint markout (bps)")
            ax.legend()
    fig.tight_layout()
    fig.savefig(args.out/"prediction_quantile_markout.png",dpi=160)
    plt.close(fig)
