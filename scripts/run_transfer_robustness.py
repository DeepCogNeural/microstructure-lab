"""Bounded fixed-parameter transfer experiment; aggregate outputs only."""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
import numpy as np
import pandas as pd
from cloblab.evaluation import _score_predictions
from cloblab.scale_common import atomic_json, digest, file_hash, read_json
from cloblab.scale_runner import finite_json, model_parameters
from cloblab.scientific_identity import scientific_task_id, scientific_config
from cloblab.transfer import load_transfer_fold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--within-predictions", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.threads <= 24:
        raise ValueError("threads must be 1..24")
    config = read_json(args.config)
    manifest = read_json(Path(args.cache)/"manifest.json")
    transfer = config["evaluation"]["transfer"]
    horizon = transfer["horizon_events"]
    months = config["evaluation"]["fixed_test_months"]
    symbols = config["dataset"]["symbols"]
    tasks = [(symbol, month, None) for symbol, month in itertools.product(symbols, months)]
    tasks += [(symbol, transfer["control_month"], transfer["control_seed"]) for symbol in symbols]
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    original = pd.read_csv(args.metrics)
    original = original[(original.model=="xgboost") & original.control_seed.isna() & (original.horizon==horizon)]
    if original.duplicated(["symbol", "month"]).any() or set(original[["symbol", "month"]].itertuples(index=False, name=None)) != set(itertools.product(symbols, months)):
        raise ValueError("incomplete within-stock comparator")
    # Verify all consumed partitions once, before fitting any task.
    for part in manifest["partitions"]:
        if part["day"][:7] > max(months):
            continue
        path = Path(args.cache)/f"symbol={part['symbol']}"/f"day={part['day']}"/"features.parquet"
        if file_hash(path) != part["features_sha256"]:
            raise ValueError("transfer input partition hash mismatch")
    code = digest({p.name:file_hash(p) for p in [Path(__file__), Path(__file__).parents[1]/"src/cloblab/transfer.py"]})
    binding = digest(dict(config=scientific_config(config), cache=digest(manifest), code=code, baseline=file_hash(args.metrics)))
    results = []
    for symbol, month, seed in tasks:
        task = dict(symbol=symbol, month=month, horizon=horizon, model="xgboost_transfer", control_seed=seed)
        task_id = scientific_task_id(config, task, manifest)
        checkpoint = work/f"{task_id}.json"
        if checkpoint.exists():
            saved = read_json(checkpoint)
            if saved["binding"] != binding:
                raise ValueError("stale transfer checkpoint")
            result = saved["result"]
        else:
            train, test = load_transfer_fold(args.cache, manifest, symbol, month, config["features"]["primary_set"], horizon, seed)
            if set(train.symbol) != set(symbols)-{symbol}:
                raise ValueError("transfer training stock denominator mismatch")
            baseline = original[(original.symbol==symbol) & (original.month==month)].iloc[0]
            folder = Path(args.within_predictions)/"tasks"/baseline.task_id
            status = read_json(folder/"status.json")
            if status["task"]["cache_hash"] != digest(manifest) or file_hash(folder/"predictions.npz") != status["artifacts"]["predictions.npz"]:
                raise ValueError("within-stock prediction binding mismatch")
            with np.load(folder/"predictions.npz", allow_pickle=False) as saved:
                if not np.array_equal(saved["timestamp_ns"],test.timestamp_ns) or not np.array_equal(saved["event_index"],test.event_index) or not np.array_equal(saved["actual"],test[f"markout_{horizon}"]):
                    raise ValueError("transfer/within-stock rows differ")
            from xgboost import XGBRegressor
            model = XGBRegressor(**model_parameters(config,args.device,args.threads))
            features = config["features"]["primary_set"]
            model.fit(train[features],train[f"markout_{horizon}"])
            actual_device = json.loads(model.get_booster().save_config())["learner"]["generic_param"]["device"]
            if args.device.startswith("cuda") and not actual_device.startswith("cuda"):
                raise ValueError("requested accelerator unavailable")
            prediction = model.predict(test[features])
            if not np.isfinite(prediction).all():
                raise ValueError("nonfinite transfer predictions")
            result = {**task, "task_id":task_id, "train_rows":len(train), "train_stocks":len(set(train.symbol)),
                "last_training_day":train.day.max(), "first_test_day":test.day.min(),
                **_score_predictions(prediction,test[f"markout_{horizon}"].to_numpy(),1.0),
                "within_stock_ic":float(baseline.ic), "within_stock_task_id":baseline.task_id}
            result["transfer_minus_within_ic"] = result["ic"]-result["within_stock_ic"]
            atomic_json(checkpoint,finite_json(dict(binding=binding,result=result)))
            del train, test, prediction, model
        results.append(result)
        print(f"completed {len(results)}/{len(tasks)} transfer tasks: {symbol}/{month}/{seed}",flush=True)
    frame = pd.DataFrame(results)
    if len(frame) != len(tasks) or frame.duplicated(["symbol","month","control_seed"]).any():
        raise ValueError("incomplete transfer denominator")
    frame.to_csv(out/"transfer_block_metrics.csv",index=False)
    summaries = []
    for seed, group in frame.groupby("control_seed",dropna=False):
        subsets = [("overall","all",group)]
        subsets += [("by_"+key,value,part) for key in ("symbol","month") for value,part in group.groupby(key)]
        for scope,member,part in subsets:
            summaries.append(dict(scope=scope,member=member,control_seed=seed,blocks=len(part),mean_transfer_ic=part.ic.mean(),
                mean_within_stock_ic=part.within_stock_ic.mean(),mean_delta_ic=part.transfer_minus_within_ic.mean(),
                wins=int((part.transfer_minus_within_ic>0).sum())))
    pd.DataFrame(summaries).to_csv(out/"transfer_summary.csv",index=False)
    atomic_json(out/"transfer_manifest.json",dict(complete=True,planned=len(tasks),completed=len(frame),primary_tasks=len(symbols)*len(months),
        control_tasks=len(symbols),input_binding=binding,analysis_source_hash=code,scientific_config_hash=digest(scientific_config(config)),
        horizon_events=horizon,control_shuffle="within_training_symbol_day",model_tuning=False))


if __name__ == "__main__":
    main()
