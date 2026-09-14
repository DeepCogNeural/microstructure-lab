from types import SimpleNamespace

import pytest

from cloblab.wselob import OrderBook


def row(action, oid=1, side=1, price=12345, volume=10):
    return SimpleNamespace(action_type=action, order_date=20170102,
        order_id=oid, side=side, price=price, volume=volume, price_level=2)


def test_replay_scaling_missing_modification_and_retransmit():
    book = OrderBook()
    book.apply(row("A"))
    book.apply(row("Y", volume=12))
    assert book.levels[1][123.45] == 12
    book.apply(row("M", side=-1, price=-1, volume=7))
    assert book.levels[1][123.45] == 7
    book.apply(row("D", side=-1, price=-1, volume=-1))
    assert not book.orders and not book.levels[1]
    with pytest.raises(ValueError, match="unknown order"):
        book.apply(row("D"))


def test_snapshot_excludes_unpriced_and_clear():
    book = OrderBook()
    for i in range(10):
        book.apply(row("A", oid=i, price=10000-i))
        book.apply(row("A", oid=100+i, side=2, price=10002+i))
    assert book.snapshot()["ask_px_1"] == 100.02
    book.apply(row("A", oid=200, price=0))
    assert book.snapshot() is None
    book.apply(row("D", oid=200))
    assert book.snapshot() is not None
    book.apply(row("F"))
    assert book.snapshot() is None and not book.orders
