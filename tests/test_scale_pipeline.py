import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cloblab.scale_cache import validate_cache
from cloblab.scale_common import atomic_json, digest, file_hash, read_json, source_hash
from cloblab.scale_runner import completed, expand_tasks, load_fold, model_parameters, run_task, summarize_blocks


@pytest.fixture
def config():
    return read_json(Path(__file__).parents[1]/"configs/wselob_xgboost_application_v1.json")


def test_task_determinism_and_frozen_denominator(config):
    parts = [{"symbol": s, "day": str(d.date())} for s in config["dataset"]["symbols"]
             for d in pd.bdate_range("2017-01-02", "2017-12-22")]
    manifest = {"partitions": parts}
    first = expand_tasks(config, manifest)
    second = expand_tasks(copy.deepcopy(config), copy.deepcopy(manifest))
    assert first == second
    assert len(first["tasks"]) == 152
    assert len({t["task_id"] for t in first["tasks"]}) == 152
    assert sum(t["control_seed"] is not None for t in first["tasks"]) == 17
    assert not first["substitutions"]


def test_month_fallback_is_recorded_before_execution(config):
    parts = [{"symbol": s, "day": str(d.date())} for s in config["dataset"]["symbols"]
             for d in pd.bdate_range("2017-01-02", "2017-12-22") if d.month != 4]
    plan = expand_tasks(config, {"partitions": parts})
    assert len(plan["substitutions"]) == 5
    assert all(s["actual"] == "2017-05" for s in plan["substitutions"])


@pytest.fixture
def cache(tmp_path, config):
    parts = []
    rng = np.random.default_rng(22)
    for day in ("2017-05-30", "2017-05-31", "2017-06-01"):
        f = pd.DataFrame(rng.normal(size=(35, 5)), columns=config["features"]["primary_set"])
        f["day"], f["event_index"], f["timestamp_ns"], f["segment"] = day, np.arange(35), np.arange(35), 1
        f["markout_20"] = f.top_imbalance * 2 + rng.normal(size=35) * 0.1
        path = tmp_path/f"symbol=PEKAO/day={day}/features.parquet"
        path.parent.mkdir(parents=True)
        f.to_parquet(path, index=False)
        parts.append({"symbol": "PEKAO", "day": day, "features_sha256": file_hash(path)})
    manifest = {"partitions": parts, "config_hash": digest(config), "source_hash": source_hash(), "partial": True}
    atomic_json(tmp_path/"manifest.json", manifest)
    return tmp_path, manifest


def tiny_task(config, manifest, model="linear", seed=None):
    task = {"symbol": "PEKAO", "month": "2017-06", "horizon": 20, "model": model,
            "control_seed": seed, "config_hash": digest(config), "cache_hash": digest(manifest), "source_hash": source_hash()}
    return {"task_id": digest(task), **task}


def test_cache_corruption_and_stale_spec_rejected(cache, config):
    root, manifest = cache
    assert validate_cache(root, config, True) == manifest
    with pytest.raises(ValueError, match="partial"):
        validate_cache(root, config)
    changed = copy.deepcopy(config)
    changed["models"]["linear"]["ridge"] = 1
    with pytest.raises(ValueError, match="stale"):
        validate_cache(root, changed, True)
    path = next(root.glob("symbol=*/day=*/features.parquet"))
    with path.open("ab") as f:
        f.write(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_cache(root, config, True)


def test_monthly_causality_and_day_scoped_shuffle(cache, config):
    root, manifest = cache
    task = tiny_task(config, manifest)
    train, test, label = load_fold(root, manifest, task, config["features"]["primary_set"])
    shuffled, _, _ = load_fold(root, manifest, {**task, "control_seed": 7}, config["features"]["primary_set"])
    assert train.day.max() < test.day.min()
    assert set(test.day) == {"2017-06-01"}
    assert not np.array_equal(train[label], shuffled[label])
    for day in train.day.unique():
        np.testing.assert_array_equal(np.sort(train.loc[train.day == day, label]), np.sort(shuffled.loc[shuffled.day == day, label]))


def test_completed_resume_does_no_model_work_and_checks_artifacts(cache, config, tmp_path, monkeypatch):
    root, manifest = cache
    task = tiny_task(config, manifest)
    out = tmp_path/"run"
    assert run_task(task, config, manifest, root, out) == "complete"
    import cloblab.scale_runner as runner
    monkeypatch.setattr(runner, "load_fold", lambda *a: pytest.fail("resume loaded model data"))
    assert run_task(task, config, manifest, root, out, resume=True) == "skipped"
    folder = out/"tasks"/task["task_id"]
    (folder/"metrics.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        completed(folder, task)


def test_equal_weight_blocks_not_rows():
    frame = pd.DataFrame({"model": ["linear", "linear"], "n_test": [100, 100000],
                          **{k: [0.1, 0.9] for k in ("ic", "direction_accuracy", "cost_coverage", "selected_midpoint_diagnostic_bps", "prediction_decile_monotonicity")}})
    out = summarize_blocks(frame, ["model"])
    assert out.iloc[0].ic == 0.5
    assert out.iloc[0].symbol_month_blocks == 2


def test_gpu_assignment_and_frozen_xgboost_config(config):
    assert model_parameters(config, "cuda:1", 2)["device"] == "cuda:1"
    assert model_parameters(config, "cpu", 3)["n_estimators"] == 800
    with pytest.raises(ValueError, match="device"):
        model_parameters(config, "cuda:-1", 1)


def test_xgboost_cpu_fixture(cache, config, tmp_path):
    pytest.importorskip("xgboost")
    root, manifest = cache
    task = tiny_task(config, manifest, "xgboost")
    out = tmp_path/"xgb-run"
    assert run_task(task, config, manifest, root, out) == "complete"
    metrics = read_json(out/"tasks"/task["task_id"]/"metrics.json")
    assert metrics["n_test"] == 35
    assert set(metrics["gain"]) == set(config["features"]["primary_set"])


def test_failed_task_requires_explicit_retry(cache, config, tmp_path):
    root, manifest = cache
    task = tiny_task(config, manifest)
    folder = tmp_path/"failed"/"tasks"/task["task_id"]
    atomic_json(folder/"status.json", {"state": "failed", "task": task, "attempt": 1, "error": "controlled interruption"})
    with pytest.raises(ValueError, match="retry-failed"):
        run_task(task, config, manifest, root, tmp_path/"failed", resume=True)
    assert run_task(task, config, manifest, root, tmp_path/"failed", resume=True, retry_failed=True) == "complete"
    assert read_json(folder/"attempt-1.json")["error"] == "controlled interruption"
