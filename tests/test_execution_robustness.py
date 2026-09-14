import copy
import runpy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from cloblab.execution_labels import crossed_labels
from cloblab.robustness import paired_robustness, summarize_predictions
from cloblab.scientific_identity import scientific_task_id
from cloblab.scale_common import read_json
from cloblab.scale_runner import expand_tasks

ROOT = Path(__file__).parents[1]


def book():
    return pd.DataFrame(dict(symbol=["A"]*6, day=["2017-01-02"]*6, segment=[1]*6,
        event_index=np.arange(10,16), timestamp_ns=np.arange(6),
        bid_px_1=[99.,100.,102.,101.,104.,103.], ask_px_1=[101.,103.,104.,104.,106.,107.]))


def test_crossed_formulas_and_exact_offsets():
    data = book()
    result = crossed_labels(data, 2, 1)
    # t=10 -> entry=11: bid100 ask103; exit=13: bid101 ask104.
    assert result.long_crossed_bps.iloc[0] == pytest.approx(1e4*(101-103)/101.5)
    assert result.short_crossed_bps.iloc[0] == pytest.approx(1e4*(100-104)/101.5)
    assert result.long_crossed_bps.iloc[-3:].isna().all()
    instant = crossed_labels(data, 2, 0)
    assert instant.long_crossed_bps.iloc[0] == pytest.approx(100.)
    assert instant.short_crossed_bps.iloc[0] == pytest.approx(-500.)


@pytest.mark.parametrize("boundary", ["day", "segment"])
def test_no_cross_boundary_future_lookup(boundary):
    data = book()
    data.loc[3:, boundary] = "2017-01-03" if boundary == "day" else 2
    result = crossed_labels(data, 2, 0)
    assert result.long_crossed_bps.iloc[[1,2,4,5]].isna().all()
    assert result.long_crossed_bps.iloc[[0,3]].notna().all()


def test_latency_only_changes_outcomes_not_decision_data():
    data = book()
    original = data.copy(deep=True)
    first = crossed_labels(data, 1, 1)
    changed = data.copy()
    changed.loc[2, ["bid_px_1", "ask_px_1"]] += 1
    second = crossed_labels(changed, 1, 1)
    pd.testing.assert_frame_equal(data, original)
    assert first.long_crossed_bps.iloc[0] != second.long_crossed_bps.iloc[0]
    pd.testing.assert_series_equal(first.event_index, data.event_index)
    pd.testing.assert_series_equal(first.timestamp_ns, data.timestamp_ns)


def test_event_gap_does_not_become_next_valid_quote():
    data = book().drop(index=2)
    with pytest.raises(ValueError, match="gaps"):
        crossed_labels(data, 1, 0)


@pytest.mark.parametrize("horizon,latency", [(0,0), (1,-1), (1,0.5), (1.5,0)])
def test_invalid_offsets(horizon, latency):
    with pytest.raises(ValueError):
        crossed_labels(book(), horizon, latency)


def identity_inputs():
    config = read_json(ROOT/"configs/wselob_execution_robustness_v1.json")
    task = dict(symbol="PEKAO", month="2017-06", horizon=20, model="xgboost", control_seed=None)
    manifest = {"partitions": [{"symbol":"PEKAO", "day":"2017-06-01", "features_sha256":"a", "snapshots_sha256":"b"}]}
    return config, task, manifest


def test_execution_settings_do_not_change_scientific_identity():
    config, task, manifest = identity_inputs()
    before = scientific_task_id(config, task, manifest)
    changed = copy.deepcopy(config)
    changed.update(execution={"workers":12, "device":"cuda", "max_hours":1}, publication={"enabled":False})
    changed["models"]["xgboost"].update(device="cpu", n_jobs=20, telemetry=True)
    moved = {**manifest, "config_hash":"legacy", "source_hash":"telemetry-only-change", "workers":24, "path":"elsewhere"}
    assert scientific_task_id(changed, task, moved) == before


@pytest.mark.parametrize("change", ["feature", "horizon", "month", "parameter", "seed", "input"])
def test_scientific_changes_change_identity(change):
    config, task, manifest = identity_inputs()
    before = scientific_task_id(config, task, manifest)
    if change == "feature": config["features"]["primary_set"].append("another_feature")
    elif change == "horizon": task["horizon"] = 50
    elif change == "month": task["month"] = "2017-11"
    elif change == "parameter": config["models"]["xgboost"]["max_depth"] = 6
    elif change == "seed": task["control_seed"] = 29
    else: manifest["partitions"][0]["features_sha256"] = "changed"
    assert scientific_task_id(config, task, manifest) != before


def test_expanded_ids_ignore_execution_config():
    config, _, _ = identity_inputs()
    manifest = {"partitions":[{"symbol":s,"day":str(d.date())} for s in config["dataset"]["symbols"] for d in pd.bdate_range("2017-01-02","2017-12-22")]}
    first = expand_tasks(config, manifest)
    config["models"]["xgboost"]["device"] = "cuda:1"
    config["time_budget"] = {"max_hours":1}
    assert expand_tasks(config, manifest) == first


def paired_fixture():
    return pd.DataFrame([dict(symbol=s,month=m,horizon=20,model=model,control_seed=np.nan,
        ic=value+(0.1 if model=="xgboost" else 0)) for s,value in [("A",0.1),("B",0.7)]
        for m in ["2017-04","2017-06"] for model in ["linear","xgboost"]])


def test_paired_blocks_match_and_are_equal_weighted():
    frame = paired_fixture().sample(frac=1, random_state=1)
    paired, summary = paired_robustness(frame,["A","B"],["2017-04","2017-06"],[20],draws=100)
    assert np.allclose(paired.delta_ic,0.1)
    overall = summary[summary.scope=="overall"].iloc[0]
    assert overall.mean_delta_ic == pytest.approx(.1)
    assert overall.wins == 4
    assert overall.descriptive_lower == pytest.approx(.1)


def test_missing_or_duplicate_pair_fails():
    frame = paired_fixture()
    for broken in (frame.iloc[1:],pd.concat([frame,frame.iloc[:1]])):
        with pytest.raises(ValueError,match="denominator"):
            paired_robustness(broken,["A","B"],["2017-04","2017-06"],[20])


def test_threshold_and_direction_selection():
    summary, quantiles = summarize_predictions(np.array([-2.,0.,2.]), np.array([-4.,-2.,3.]), np.array([4.,-2.,-3.]),1.)
    assert summary["coverage"] == pytest.approx(2/3)
    assert summary["sign_selected_bps"] == 3.5
    assert summary["ordered_deciles"] == 0  # insufficient distinct deciles


def test_execution_aggregation_rejects_missing_tasks():
    functions = runpy.run_path(str(ROOT/"scripts/run_execution_robustness.py"))
    config, _, _ = identity_inputs()
    frame = pd.DataFrame([dict(symbol="PEKAO",month="2017-06",horizon=20,model="linear",control_seed=None,latency=0)])
    with pytest.raises(ValueError,match="denominator"):
        functions["aggregate_outputs"](frame,pd.DataFrame(),config)


def test_transfer_fold_excludes_stock_and_future_and_preserves_shuffle_groups(tmp_path):
    from cloblab.transfer import load_transfer_fold
    parts = []
    for symbol in ("A","B","C"):
        for day in ("2017-03-01","2017-04-01","2017-05-01"):
            part = {"symbol":symbol,"day":day}
            parts.append(part)
            folder = tmp_path/f"symbol={symbol}"/f"day={day}"
            folder.mkdir(parents=True)
            pd.DataFrame(dict(symbol=[symbol]*5,day=[day]*5,event_index=np.arange(5),timestamp_ns=np.arange(5),
                feature=np.arange(5),markout_20=np.arange(5,dtype=float))).to_parquet(folder/"features.parquet",index=False)
    train,test = load_transfer_fold(tmp_path,{"partitions":parts},"A","2017-04",["feature"])
    shuffled,_ = load_transfer_fold(tmp_path,{"partitions":parts},"A","2017-04",["feature"],seed=7)
    assert set(train.symbol)=={"B","C"}
    assert set(train.day)=={"2017-03-01"}
    assert set(test.symbol)=={"A"} and set(test.day)=={"2017-04-01"}
    assert not np.array_equal(train.markout_20,shuffled.markout_20)
    for key, group in train.groupby(["symbol","day"]):
        other=shuffled[(shuffled.symbol==key[0]) & (shuffled.day==key[1])]
        np.testing.assert_array_equal(np.sort(group.markout_20),np.sort(other.markout_20))


def test_v2_cache_config_ignores_device_and_workers(tmp_path):
    from cloblab.scale_cache import validate_cache
    from cloblab.scale_common import atomic_json, digest, source_hash
    from cloblab.scientific_identity import scientific_config
    config,_,_ = identity_inputs()
    manifest = dict(version=2,config_hash=digest(scientific_config(config)),source_hash=source_hash(),partial=False,partitions=[])
    atomic_json(tmp_path/"manifest.json",manifest)
    config["models"]["xgboost"]["device"]="cpu"
    config["engineering"]={"workers":24}
    assert validate_cache(tmp_path,config)==manifest
