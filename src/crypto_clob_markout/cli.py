from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_clob_markout.collectors import collect_coinbase_websocket_sync
from crypto_clob_markout.evaluation import run_baseline
from crypto_clob_markout.features import build_features
from crypto_clob_markout.io import write_csv, write_parquet
from crypto_clob_markout.labels import build_markout_labels
from crypto_clob_markout.samples import make_synthetic_order_book
from crypto_clob_markout.schema import render_schema_markdown


DEFAULT_FEATURES = ["top_imbalance", "depth_imbalance", "spread_bps", "recent_trade_imbalance"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crypto CLOB markout benchmark MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("make-sample", help="Run deterministic sample pipeline")
    sample.add_argument("--out", default="data/sample", help="output directory")
    sample.add_argument("--rows", type=int, default=120)
    sample.add_argument("--levels", type=int, default=3)
    sample.add_argument("--horizon", type=int, default=10)
    sample.add_argument("--cost-bps", type=float, default=1.0)

    collect = subparsers.add_parser("collect-coinbase", help="Collect public Coinbase Exchange WebSocket JSONL")
    collect.add_argument("--symbols", nargs="+", default=["BTC-USD"], help="product ids")
    collect.add_argument("--seconds", type=float, default=30.0)
    collect.add_argument("--out", default="data/raw/coinbase/messages.jsonl", help="output JSONL path")
    collect.add_argument("--channels", nargs="+", default=["level2_batch", "matches"])

    schema = subparsers.add_parser("schema", help="Print or write schema markdown")
    schema.add_argument("--out", help="optional output markdown path")

    args = parser.parse_args(argv)
    if args.command == "make-sample":
        paths = run_sample_pipeline(
            out_dir=Path(args.out),
            rows=args.rows,
            levels=args.levels,
            horizon=args.horizon,
            cost_bps=args.cost_bps,
        )
        print(json.dumps({name: str(path) for name, path in paths.items()}, indent=2, sort_keys=True))
        return 0
    if args.command == "collect-coinbase":
        path = collect_coinbase_websocket_sync(
            symbols=args.symbols,
            seconds=args.seconds,
            output_path=args.out,
            channels=args.channels,
        )
        print(path)
        return 0
    if args.command == "schema":
        text = render_schema_markdown()
        if args.out:
            output = Path(args.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
            print(output)
        else:
            print(text)
        return 0
    raise ValueError(f"unknown command: {args.command}")


def run_sample_pipeline(
    *,
    out_dir: Path,
    rows: int,
    levels: int,
    horizon: int,
    cost_bps: float,
) -> dict[str, Path]:
    snapshots, trades = make_synthetic_order_book(rows=rows, levels=levels)
    features = build_features(snapshots, trades, depth_levels=levels)
    labels = build_markout_labels(features, horizons_seconds=(1, 5, 10, 60))
    label_col = f"markout_bps_{horizon}s"
    eval_frame = labels.dropna(subset=[label_col])
    test_size = max(5, min(20, len(eval_frame) // 4))
    min_train_size = max(10, len(eval_frame) - 2 * test_size)
    result = run_baseline(
        eval_frame,
        feature_cols=DEFAULT_FEATURES,
        label_col=label_col,
        min_train_size=min_train_size,
        test_size=test_size,
        n_splits=2,
        cost_bps=cost_bps,
        random_seed=7,
    )

    raw_dir = out_dir / "raw"
    processed_dir = out_dir / "processed"
    report_dir = out_dir / "reports"
    paths = {
        "snapshots": write_parquet(snapshots, raw_dir / "snapshots.parquet"),
        "trades": write_parquet(trades, raw_dir / "trades.parquet"),
        "features": write_parquet(features, processed_dir / "features.parquet"),
        "labels": write_parquet(labels, processed_dir / "labels.parquet"),
        "buckets": write_csv(pd.DataFrame(result["buckets"]), report_dir / "bucket_markouts.csv"),
    }
    summary_path = report_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(_clean_json(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["summary"] = summary_path
    return paths


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    return value


if __name__ == "__main__":
    raise SystemExit(main())

