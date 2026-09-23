from cloblab.polymarket_l2 import audit_snapshot


def row(**changes):
    base = {'bid_prices': [.49, .48], 'bid_sizes': [2., 3.],
            'ask_prices': [.51, .52], 'ask_sizes': [4., 5.],
            'best_bid': .49, 'best_ask': .51, 'crossed': False}
    base.update(changes)
    return base


def test_valid_and_one_sided_have_distinct_midpoint_status():
    assert audit_snapshot(row()).valid_midpoint
    one = audit_snapshot(row(ask_prices=[], ask_sizes=[], best_ask=None))
    assert one.empty_ask and not one.valid_midpoint and not one.crossed


def test_stale_crossed_and_locked_books_remain_flagged():
    crossed = audit_snapshot(row(ask_prices=[.48, .52], best_ask=.48, crossed=True))
    assert crossed.crossed and not crossed.valid_midpoint
    locked = audit_snapshot(row(ask_prices=[.49, .52], best_ask=.49, crossed=True))
    assert locked.locked and not locked.valid_midpoint
    assert audit_snapshot(row(ask_prices=[.49, .52], best_ask=.49)).crossed_flag_mismatch


def test_ladder_and_size_corruption_are_not_silently_cleaned():
    bad = audit_snapshot(row(bid_prices=[.48, .49], bid_sizes=[1.], best_bid=.48,
                             ask_sizes=[0., 5.]))
    assert bad.ladder_length_mismatch and bad.bid_order_error and bad.nonpositive_size
    assert not bad.valid_midpoint
