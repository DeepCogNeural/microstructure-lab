from datetime import datetime, timedelta, timezone

from scripts.audit_polymarket_pm1b_horizons import future_book_index


DECISION=datetime(2026,8,21,0,0,tzinfo=timezone.utc)


def book(offset, **changes):
    row={'captured_at':DECISION+timedelta(seconds=offset),
         'bid_prices':[.49,.48],'bid_sizes':[2.,3.],
         'ask_prices':[.51,.52],'ask_sizes':[4.,5.],
         'best_bid':.49,'best_ask':.51,'crossed':False}
    row.update(changes)
    return row


def test_future_lookup_never_uses_predecision_or_post_horizon_capture():
    rows=[book(-1),book(16)]
    index,reason=future_book_index([r['captured_at'] for r in rows],rows,DECISION,15)
    assert index is None and reason=='no_strictly_future_capture'
    rows=[book(-1),book(12)]
    index,reason=future_book_index([r['captured_at'] for r in rows],rows,DECISION,15)
    assert index==1 and reason is None


def test_future_lookup_rejects_stale_and_crossed_books():
    rows=[book(1)]
    index,reason=future_book_index([r['captured_at'] for r in rows],rows,DECISION,15)
    assert index is None and reason=='future_stale'
    rows=[book(12,ask_prices=[.48],ask_sizes=[5.],best_ask=.48,crossed=True)]
    index,reason=future_book_index([r['captured_at'] for r in rows],rows,DECISION,15)
    assert index is None and reason=='future_invalid_book'
