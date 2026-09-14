import pandas as pd

from cloblab.coinbase_normalize import normalize_coinbase_messages, replay_coinbase_book_events


def test_normalize_book_and_trade_messages():
    messages = [
        {
            "type": "snapshot",
            "product_id": "BTC-USD",
            "time": "2026-01-01T00:00:00Z",
            "bids": [["100", "2"]],
            "asks": [["101", "3"]],
        },
        {
            "type": "l2update",
            "product_id": "BTC-USD",
            "time": "2026-01-01T00:00:01Z",
            "changes": [["buy", "100", "4"]],
        },
        {
            "type": "match",
            "product_id": "BTC-USD",
            "time": "2026-01-01T00:00:02Z",
            "trade_id": 7,
            "price": "101",
            "size": "0.5",
            "side": "sell",
        },
    ]
    books, trades = normalize_coinbase_messages(messages)
    assert len(books) == 3
    assert len(trades) == 1
    assert set(books["side"]) == {"buy", "sell"}
    assert trades.loc[0, "aggressor_sign"] == 1
    assert pd.api.types.is_datetime64tz_dtype(books["event_ts"])


def test_normalize_collector_envelope_preserves_receipt_order_and_trade_side():
    records = [
        {
            "local_ts": "2026-01-01T00:00:00.100Z",
            "message": {
                "type": "snapshot",
                "product_id": "BTC-USD",
                "time": "2026-01-01T00:00:00Z",
                "bids": [["100", "2"]],
                "asks": [["101", "3"]],
            },
        },
        {
            "local_ts": "2026-01-01T00:00:01.100Z",
            "message": {
                "type": "match",
                "product_id": "BTC-USD",
                "time": "2026-01-01T00:00:01Z",
                "trade_id": 8,
                "price": "101",
                "size": "0.5",
                "side": "sell",
            },
        },
    ]

    books, trades = normalize_coinbase_messages(records)

    assert books["local_receive_index"].unique().tolist() == [1]
    assert books.loc[0, "local_ts"] == pd.Timestamp("2026-01-01T00:00:00.100Z")
    assert trades.loc[0, "side"] == "buy"
    assert trades.loc[0, "source_side"] == "sell"


def test_replay_coinbase_batches_uses_snapshot_then_atomic_updates():
    records = [
        {
            "local_ts": "2026-01-01T00:00:00.100Z",
            "message": {
                "type": "snapshot",
                "product_id": "BTC-USD",
                "time": "2026-01-01T00:00:00Z",
                "bids": [["100", "2"], ["99", "1"]],
                "asks": [["101", "3"], ["102", "1"]],
            },
        },
        {
            "local_ts": "2026-01-01T00:00:01.100Z",
            "message": {
                "type": "l2update",
                "product_id": "BTC-USD",
                "time": "2026-01-01T00:00:01Z",
                "changes": [["buy", "100", "0"], ["buy", "100.5", "4"]],
            },
        },
    ]

    books, _ = normalize_coinbase_messages(records)
    replay = replay_coinbase_book_events(books)

    assert len(replay.snapshots) == 2
    assert replay.snapshots.loc[1, "best_bid"] == 100.5
    assert replay.snapshots["local_receive_index"].tolist() == [1, 2]
