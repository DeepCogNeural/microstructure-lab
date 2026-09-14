"""Reconstruct the licensed WSELOB-2017 PEKAO benchmark without pickle loading.

Field semantics follow the depositor's order_data.ipynb/orderbook2.py.
See docs/WSELOB_LICENSE.md for attribution, source and modifications.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sortedcontainers import SortedDict

SOURCE_SHA256 = "3c418a55a492ebe2e39c8513cd7fc7e3e6827dc1a176af09fdcaad9f3485bae6"
# Depositor order_data.ipynb ASSETS mapping (Mendeley V1).
SYMBOL_IDS = {"KGHM": 10783, "PKNORLEN": 11319, "PKOBP": 11314, "PZU": 10735, "PEKAO": 11322}


class OrderBook:
    def __init__(self):
        self.orders = {}
        self.levels = {1: SortedDict(), 2: SortedDict()}
        self.unpriced = 0

    def _adjust(self, order, sign):
        side, price, volume = order
        if price <= 0:
            self.unpriced += sign
            return
        levels = self.levels[side]
        quantity = levels.get(price, 0) + sign * volume
        if quantity < 0:
            raise ValueError("negative reconstructed depth")
        if quantity:
            levels[price] = quantity
        else:
            levels.pop(price, None)

    def apply(self, row):
        action = row.action_type.decode() if isinstance(row.action_type, bytes) else row.action_type
        if action == "F":
            self.__init__()
            return
        key = (int(row.order_date), int(row.order_id))
        previous = self.orders.get(key)
        if action not in ("A", "Y", "M", "D"):
            raise ValueError(f"unknown action {action}")
        if action in ("M", "D") and previous is None:
            raise ValueError(f"{action} for unknown order {key}")
        if action == "A" and previous is not None:
            raise ValueError(f"duplicate add {key}")
        if previous is not None:
            self._adjust(previous, -1)
        if action == "D":
            del self.orders[key]
            return
        side = int(row.side)
        side = 2 if side == 5 else side
        if side == -1 and previous is not None:
            side = previous[0]
        price = previous[1] if row.price == -1 and previous is not None else float(row.price) / 10**int(row.price_level)
        volume = previous[2] if row.volume == -1 and previous is not None else int(row.volume)
        if side not in (1, 2) or volume < 0:
            raise ValueError("invalid order side or volume")
        order = (side, price, volume)
        self.orders[key] = order
        self._adjust(order, 1)

    def snapshot(self):
        bids, asks = self.levels[1], self.levels[2]
        if self.unpriced or len(bids) < 10 or len(asks) < 10:
            return None
        if bids.peekitem(-1)[0] >= asks.peekitem(0)[0]:
            return None
        out = {}
        for side, levels, indexes in (("bid", bids, range(-1, -11, -1)), ("ask", asks, range(10))):
            for level, index in enumerate(indexes, 1):
                price, size = levels.peekitem(index)
                out[f"{side}_px_{level}"] = price
                out[f"{side}_sz_{level}"] = size
        return out


def reconstruct(records, day, symbol="PEKAO"):
    if not np.all(np.diff(records["time"]) >= 0):
        raise ValueError("non-monotonic source message time")
    if not np.all(records["symbol_idx"] == SYMBOL_IDS[symbol]):
        raise ValueError("unexpected instrument")
    times = pd.to_datetime(records["time"], unit="ns", utc=True).tz_convert("Europe/Warsaw")
    if set(times.strftime("%Y-%m-%d")) != {day}:
        raise ValueError("source day key and timestamps disagree")
    lower = pd.Timestamp(day + " 10:00", tz="Europe/Warsaw")
    upper = pd.Timestamp(day + " 16:00", tz="Europe/Warsaw")
    book, rows, counts = OrderBook(), [], Counter()
    segment, previous_event = 0, None
    initialized = False
    for event, row in enumerate(pd.DataFrame.from_records(records).itertuples(index=False)):
        action = row.action_type.decode()
        counts[action] += 1
        if action == "F":
            initialized = True
            previous_event = None
        if not initialized:
            raise ValueError("day does not begin with an explicit book reset")
        book.apply(row)
        if times[event] < lower or times[event] >= upper:
            counts["outside_window"] += 1
            continue
        snap = book.snapshot()
        if snap is None:
            counts["invalid_book"] += 1
            previous_event = None
            continue
        if previous_event is None or event != previous_event + 1:
            segment += 1
        rows.append({"symbol":symbol, "day":day, "segment":segment,
            "event_index":event, "timestamp_ns":int(row.time), **snap})
        previous_event = event
    counts.update({"source_rows":len(records), "snapshot_rows":len(rows), "segments":segment})
    if not rows:
        raise ValueError("no valid snapshots")
    return pd.DataFrame(rows), {"day":day, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    digest = hashlib.sha256()
    with args.input.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SOURCE_SHA256:
        raise ValueError("input does not match the official PEKAO file hash")
    import h5py
    pieces, audit = [], []
    with h5py.File(args.input, "r") as source:
        keys = sorted(source)[:10]
        for key in keys:
            day = pd.Timestamp(key[1:]).strftime("%Y-%m-%d")
            frame, counts = reconstruct(source[key + "/table"][:], day)
            pieces.append(frame)
            audit.append(counts)
            print(json.dumps(counts), flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.concat(pieces, ignore_index=True).to_parquet(args.out/"snapshots.parquet", index=False)
    manifest = {"dataset":"WSELOB-2017 PEKAO first ten trading days", "source_url":"https://data.mendeley.com/datasets/3g4mhdp899/1",
        "license":"CC-BY-4.0", "license_url":"https://creativecommons.org/licenses/by/4.0/",
        "attribution":"Marszałek, Adam (2023), WSELOB-2017, Mendeley Data V1, DOI 10.17632/3g4mhdp899.1; as-is, no warranty or endorsement",
        "boundary_evidence":"Depositor order_data.ipynb: PEKAO symbol_idx=11322; /dYYYYMMDD HDF5 keys and nanosecond timestamps; checked for agreement",
        "ml_use_permitted":True, "aggregate_publication_permitted":True,
        "raw_sha256":SOURCE_SHA256, "day_keys":keys,
        "modifications":"Order-level replay to ten-level snapshots, 10:00 <= local Warsaw time < 16:00, no unpriced orders or locked/crossed/shallow books; invalid gaps reset feature/label segments. Horizons count original message rows within uninterrupted valid segments.",
        "reconstruction":audit}
    (args.out/"license_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    main()
