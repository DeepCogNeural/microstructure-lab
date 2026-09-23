"""Public Polymarket L2 row checks; independent of the equity event loader."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Any


@dataclass(frozen=True)
class BookFlags:
    empty_bid: bool
    empty_ask: bool
    ladder_length_mismatch: bool
    bid_order_error: bool
    ask_order_error: bool
    nonpositive_size: bool
    invalid_price: bool
    top_mismatch: bool
    crossed: bool
    locked: bool
    crossed_flag_mismatch: bool
    valid_midpoint: bool


def _valid_number(value: Any) -> bool:
    return isinstance(value, (float, int)) and math.isfinite(value)


def audit_snapshot(row: Mapping[str, Any]) -> BookFlags:
    """Check one archived token book without inventing missing sides or a fill."""
    bp = row['bid_prices'] or []
    bs = row['bid_sizes'] or []
    ap = row['ask_prices'] or []
    ass = row['ask_sizes'] or []
    empty_bid, empty_ask = len(bp) == 0, len(ap) == 0
    length_mismatch = len(bp) != len(bs) or len(ap) != len(ass)
    bid_order_error = any(not (_valid_number(a) and _valid_number(b) and a > b)
                          for a, b in zip(bp, bp[1:]))
    ask_order_error = any(not (_valid_number(a) and _valid_number(b) and a < b)
                          for a, b in zip(ap, ap[1:]))
    nonpositive_size = any(not _valid_number(s) or s <= 0 for s in (*bs, *ass))
    invalid_price = any(not _valid_number(p) or not 0 <= p <= 1 for p in (*bp, *ap))
    best_bid, best_ask = row['best_bid'], row['best_ask']
    top_mismatch = (best_bid != (bp[0] if bp else None) or best_ask != (ap[0] if ap else None))
    two_sided = not empty_bid and not empty_ask
    crossed = bool(two_sided and bp[0] > ap[0])
    locked = bool(two_sided and bp[0] == ap[0])
    derived_crossed = crossed or locked
    crossed_flag_mismatch = bool(row['crossed']) != derived_crossed
    valid_midpoint = bool(two_sided and not (length_mismatch or bid_order_error or ask_order_error
                          or nonpositive_size or invalid_price or top_mismatch or derived_crossed))
    return BookFlags(empty_bid, empty_ask, length_mismatch, bid_order_error, ask_order_error,
                     nonpositive_size, invalid_price, top_mismatch, crossed, locked,
                     crossed_flag_mismatch, valid_midpoint)
