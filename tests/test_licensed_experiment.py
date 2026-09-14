import numpy as np
import pandas as pd

from cloblab.licensed_experiment import prepare, prediction_quantiles


def test_labels_and_ofi_reset_at_stock_day_boundaries():
    rows = []
    for symbol in ("A", "B"):
        for day in ("2010-06-01", "2010-06-02"):
            for event in range(4):
                row = dict(symbol=symbol, day=day, event_index=event)
                for level in range(1, 11):
                    row.update({f"bid_px_{level}":100+event-level,
                        f"ask_px_{level}":100+event+level,
                        f"bid_sz_{level}":2.,f"ask_sz_{level}":1.})
                rows.append(row)
    out = prepare(pd.DataFrame(rows), [2])
    for _, group in out.groupby(["symbol", "day"]):
        assert group.markout_2.tail(2).isna().all()
        assert np.isnan(group.ofi_l1_norm.iloc[0])
        assert np.isclose(group.markout_2.iloc[0],200.)


def test_quantiles_are_assigned_within_each_fold():
    frame = pd.DataFrame({"fold":[1]*10+[2]*10,
        "prediction_bps":list(range(10))+list(range(100,110)),
        "realized_markout_bps":list(range(10))*2})
    aggregate, per_fold = prediction_quantiles(frame)
    assert (aggregate.fold_count == 2).all()
    assert (aggregate["count"] == 2).all()
    assert len(per_fold) == 20
    assert aggregate.avg_realized_markout_bps.tolist() == list(range(10))
