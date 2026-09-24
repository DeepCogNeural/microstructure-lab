"""Synthetic boundary and conflict tests for the bounded Rocklabs B quote audit."""
import unittest

from rocklabs_b_connection import iso_us, last_record, received_by_decision


class QuoteCloseoutTest(unittest.TestCase):
    def test_half_millisecond_after_decision_is_excluded(self):
        t = iso_us('2026-07-28T08:04:00.000000Z')
        later = iso_us('2026-07-28T08:04:00.000500Z')
        self.assertEqual(later - t, 500)
        self.assertTrue(received_by_decision(t, t // 1000))
        self.assertFalse(received_by_decision(later, t // 1000))

    def test_different_messages_same_bbo_and_numeric_strings(self):
        rows = [(1_000_000, {'best_bid': '0.5', 'best_ask': '0.60', 'hash': 'a'}),
                (1_000_000, {'best_bid': '0.50', 'best_ask': '0.6', 'hash': 'b'})]
        value, status, diag = last_record(rows, 'bbo', 1_000_500, 1000)
        self.assertEqual(status, 'ok')
        self.assertEqual((value['bid'], value['ask']), (0.5, 0.6))
        self.assertEqual(diag['message_variants'], 2)
        self.assertEqual(diag['required_quote_variants'], 1)

    def test_real_top_conflict_fails_closed(self):
        rows = [(1_000_000, {'best_bid': '0.50', 'best_ask': '0.60'}),
                (1_000_000, {'best_bid': '0.51', 'best_ask': '0.60'})]
        value, status, diag = last_record(rows, 'bbo', 1_000_500, 1000)
        self.assertIsNone(value)
        self.assertEqual(status, 'same_receive_time_conflict')
        self.assertEqual(diag['required_quote_variants'], 2)

    def test_book_deep_levels_differ_but_top_same(self):
        rows = [(1_000_000, {'bids': [{'price': '0.5', 'size': '1'}, {'price': '0.4', 'size': '2'}],
                             'asks': [{'price': '0.6', 'size': '1'}]}),
                (1_000_000, {'bids': [{'price': '0.50', 'size': '3'}, {'price': '0.3', 'size': '5'}],
                             'asks': [{'price': '0.60', 'size': '2'}]})]
        value, status, diag = last_record(rows, 'book', 1_000_500, 5000)
        self.assertEqual(status, 'ok')
        self.assertEqual((value['bid'], value['ask']), (0.5, 0.6))
        self.assertEqual(diag['message_variants'], 2)
        self.assertEqual(diag['required_quote_variants'], 1)

    def test_latest_invalid_does_not_fall_back(self):
        rows = [(1_000_000, {'best_bid': '0.5', 'best_ask': '0.6'}),
                (1_000_100, {'best_bid': '0.8', 'best_ask': '0.7'})]
        value, status, _ = last_record(rows, 'bbo', 1_000_500, 1000)
        self.assertIsNone(value)
        self.assertEqual(status, 'invalid_or_crossed_bbo')


if __name__ == '__main__':
    unittest.main()
