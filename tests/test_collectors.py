from __future__ import annotations

import unittest
from unittest.mock import patch

from crypto_clob_markout.collectors import collect_coinbase_websocket_sync


class _FakeWebSocket:
    async def send(self, payload: str) -> None:
        self.payload = payload

    async def recv(self) -> str:
        raise TimeoutError


class _FakeConnect:
    async def __aenter__(self) -> _FakeWebSocket:
        return _FakeWebSocket()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class CollectorTests(unittest.TestCase):
    def test_coinbase_collector_allows_large_l2_snapshots(self) -> None:
        with patch("crypto_clob_markout.collectors.websockets.connect", return_value=_FakeConnect()) as connect:
            collect_coinbase_websocket_sync(
                symbols=["BTC-USD"],
                seconds=0.1,
                output_path="/tmp/coinbase_collector_test.jsonl",
            )

        self.assertGreaterEqual(connect.call_args.kwargs["max_size"], 16 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

