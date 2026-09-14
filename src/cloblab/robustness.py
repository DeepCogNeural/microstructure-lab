"""Paired, equal-weight stock/month descriptive robustness summaries."""
import itertools
import numpy as np
import pandas as pd


def paired_robustness(metrics, symbols, months, horizons, seed=20260914, draws=10000):
    primary = metrics[metrics.control_seed.isna() & metrics.model.isin(["linear", "xgboost"])]
    expected = set(itertools.product(symbols, months, horizons, ["linear", "xgboost"]))
    keys = ["symbol", "month", "horizon", "model"]
    if primary.duplicated(keys).any() or set(primary[keys].itertuples(index=False, name=None)) != expected:
        raise ValueError("incomplete or duplicate paired block denominator")
    if not np.isfinite(primary.ic).all():
        raise ValueError("nonfinite block IC")
    paired = primary.pivot(index=keys[:3], columns="model", values="ic").reset_index()
    paired["delta_ic"] = paired.xgboost - paired.linear
    rows = []
    rng = np.random.default_rng(seed)
    for horizon, group in paired.groupby("horizon", sort=True):
        delta = group.delta_ic.to_numpy()
        sampled = delta[rng.integers(0, len(delta), (draws, len(delta)))].mean(axis=1)
        lo, hi = np.quantile(sampled, [.025, .975])
        rows.append(dict(horizon=horizon, scope="overall", member="all", blocks=len(group),
                         mean_delta_ic=delta.mean(), median_delta_ic=np.median(delta), wins=int((delta>0).sum()),
                         descriptive_lower=lo, descriptive_upper=hi))
        for key in ("symbol", "month"):
            for member in sorted(group[key].unique()):
                for leave_out in (False, True):
                    values = group.loc[group[key].ne(member) if leave_out else group[key].eq(member), "delta_ic"]
                    rows.append(dict(horizon=horizon, scope=("leave_one_" if leave_out else "by_")+key,
                                     member=member, blocks=len(values), mean_delta_ic=values.mean(),
                                     median_delta_ic=values.median(), wins=int((values>0).sum())))
    return paired, pd.DataFrame(rows)


def summarize_predictions(prediction, long, short, threshold=1.0):
    prediction, long, short = map(np.asarray, (prediction, long, short))
    if not len(prediction) or not (np.isfinite(prediction).all() and np.isfinite(long).all() and np.isfinite(short).all()):
        raise ValueError("empty or nonfinite paired execution sample")
    # Equal predictions retain equal bins; never break ties using future outcomes.
    decile = pd.qcut(prediction, q=10, labels=False, duplicates="drop")
    if np.isnan(decile).all():
        decile = np.zeros(len(prediction))
    selected = np.where(prediction > 0, long, np.where(prediction < 0, short, np.nan))
    frame = pd.DataFrame(dict(decile=decile+1, prediction=prediction, long=long, short=short, selected=selected))
    q = frame.groupby("decile", as_index=False).agg(rows=("prediction", "size"), prediction_bps=("prediction", "mean"),
            long_crossed_bps=("long", "mean"), short_crossed_bps=("short", "mean"), sign_selected_bps=("selected", "mean"))
    active = abs(prediction) > threshold
    values = selected[active]
    monotonic = len(q) == 10 and q.long_crossed_bps.diff().dropna().ge(0).all() and q.short_crossed_bps.diff().dropna().le(0).all()
    summary = dict(rows=len(prediction), threshold_bps=threshold, coverage=float(active.mean()),
                   selected_rows=int(active.sum()), sign_selected_bps=float(values.mean()) if len(values) else np.nan,
                   top_decile_long_bps=q.long_crossed_bps.iloc[-1], bottom_decile_short_bps=q.short_crossed_bps.iloc[0],
                   ordered_deciles=float(monotonic), decile_bins=len(q))
    return summary, q
