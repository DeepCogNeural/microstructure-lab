from datetime import datetime, timedelta, timezone

from cloblab.polymarket_pm1a import book_features, market_opportunities, select_opportunity


END = datetime(2026, 8, 21, 0, 5, tzinfo=timezone.utc)


def row(seconds_before_end, **changes):
    result = {'captured_at': END - timedelta(seconds=seconds_before_end),
              'market_end_at': END,
              'bid_prices': [.49, .48], 'bid_sizes': [2., 3.],
              'ask_prices': [.51, .52], 'ask_sizes': [4., 5.],
              'best_bid': .49, 'best_ask': .51, 'crossed': False}
    result.update(changes)
    return result


def test_history_uses_only_captures_at_or_before_decision():
    rows = sorted([row(s) for s in range(200, 55, -5)], key=lambda r: r['captured_at'])
    decision = END - timedelta(seconds=90)
    p, x = select_opportunity(rows, [r['captured_at'] for r in rows], decision, END,
                              history_length=8, max_age=15, max_lookback=120,
                              probability_clip=1e-4)
    assert p == .5 and x.shape == (8, 11)
    assert x[-1, -1] == 0
    assert all(r['captured_at'] <= decision for r in rows if r['captured_at'] <= decision)
    assert x[0, -1] == 35


def test_invalid_latest_or_stale_capture_has_no_opportunity():
    valid = [row(s) for s in range(165, 85, -10)]
    invalid = sorted(valid + [row(90, ask_prices=[.48], ask_sizes=[5.], best_ask=.48, crossed=True)],
                     key=lambda r: r['captured_at'])
    decision = END - timedelta(seconds=90)
    assert select_opportunity(invalid, [r['captured_at'] for r in invalid], decision, END,
                              history_length=8, max_age=15, max_lookback=120,
                              probability_clip=1e-4) is None
    stale = sorted([row(s) for s in range(200, 105, -10)],key=lambda r:r['captured_at'])
    assert select_opportunity(stale,[r['captured_at'] for r in stale],decision,END,
                              history_length=8,max_age=15,max_lookback=120,
                              probability_clip=1e-4) is None


def test_close_anchored_cadence_and_probability_feature():
    rows = [row(s) for s in range(240, 49, -5)]
    opportunities = market_opportunities(rows,decision_step=30,min_seconds_to_close=60,
                                          history_length=8,max_age=15,max_lookback=120,
                                          probability_clip=1e-4)
    assert opportunities
    assert all((END-decision).total_seconds() % 30 == 0 for decision,_,_ in opportunities)
    assert all((END-decision).total_seconds() >= 60 for decision,_,_ in opportunities)
    p, features = book_features(row(90),END-timedelta(seconds=90),END)
    assert p == .5 and features[0] == 0 and features[1] > 0
