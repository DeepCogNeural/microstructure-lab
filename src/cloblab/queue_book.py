"""Visible order queues; recorded priority plus explicit amendment sensitivity."""
from dataclasses import dataclass
from sortedcontainers import SortedDict
from cloblab.wselob import OrderBook


@dataclass(frozen=True)
class QueueOrder:
    side: int
    price: float
    quantity: int
    priority: int
    entered: int


class QueueBook(OrderBook):
    def __init__(self, interpretation='retain'):
        super().__init__()
        if interpretation not in ('retain', 'reset'):
            raise ValueError('unknown priority interpretation')
        self.interpretation = interpretation
        self.visible = {}
        self.queues = {}
        self.event = -1

    def apply(self, row):
        action = row.action_type.decode() if isinstance(row.action_type, bytes) else row.action_type
        self.event += 1
        if action == 'F':
            event, interpretation = self.event, self.interpretation
            self.__init__(interpretation)
            self.event = event
            return None, None
        key = (int(row.order_date), int(row.order_id))
        old = self.visible.get(key)
        super().apply(row)
        if old is not None:
            q = self.queues[(old.side, old.price)]
            del q[(old.priority, old.entered, key)]
            if not q:
                del self.queues[(old.side, old.price)]
        new = None
        if action != 'D':
            side, price, size = self.orders[key]
            reported = int(getattr(row, 'priority_date', -1))
            priority = reported if reported != -1 else (old.priority if old else int(row.time))
            changed = old is None or (old.side, old.price) != (side, price)
            changed |= old is not None and reported != -1 and reported != old.priority
            changed |= old is not None and action == 'M' and reported == -1 and self.interpretation == 'reset'
            if changed and reported == -1:
                priority = int(row.time)
            entered = self.event if changed else old.entered
            new = QueueOrder(side, price, size, priority, entered)
            self.visible[key] = new
            self.queues.setdefault((side, price), SortedDict())[(priority, entered, key)] = size
        else:
            del self.visible[key]
        return old, new

    def queue(self, side, price):
        return tuple(self.queues.get((side, price), {}).items())

    def assert_parity(self, reference):
        if self.orders != reference.orders or self.levels != reference.levels or self.unpriced != reference.unpriced:
            raise ValueError('queue and reference order replay disagree')
        totals = {1: {}, 2: {}}
        for (side, price), queue in self.queues.items():
            quantity = sum(queue.values())
            if price > 0 and quantity:
                totals[side][price] = quantity
        if totals != {side: dict(levels) for side, levels in self.levels.items()}:
            raise ValueError('ordered queue and aggregate depth disagree')
