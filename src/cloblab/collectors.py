from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import websockets


COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
DEFAULT_CHANNELS = ("level2_batch", "matches")
WEBSOCKET_MAX_SIZE_BYTES = 64 * 1024 * 1024


def coinbase_match_side_to_aggressor_side(side: str) -> str:
    """Convert Coinbase `match.side` maker side into aggressor side."""

    maker_side = side.lower()
    if maker_side == "sell":
        return "buy"
    if maker_side == "buy":
        return "sell"
    raise ValueError(f"unknown Coinbase match side: {side}")


async def collect_coinbase_websocket(
    *,
    symbols: Iterable[str],
    seconds: float,
    output_path: str | Path,
    channels: Iterable[str] = DEFAULT_CHANNELS,
) -> Path:
    """Collect raw public Coinbase Exchange WebSocket messages to JSONL.

    This collector subscribes only to public market-data channels. It does not
    accept keys, signatures, wallets, or order-entry inputs.
    """

    symbol_list = list(symbols)
    channel_list = list(channels)
    if not symbol_list:
        raise ValueError("at least one symbol is required")
    if seconds <= 0:
        raise ValueError("seconds must be positive")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subscribe = {
        "type": "subscribe",
        "product_ids": symbol_list,
        "channels": channel_list,
    }
    deadline = time.monotonic() + seconds

    async with websockets.connect(
        COINBASE_WS_URL,
        ping_interval=None,
        max_size=WEBSOCKET_MAX_SIZE_BYTES,
    ) as websocket:
        await websocket.send(json.dumps(subscribe))
        with output.open("w", encoding="utf-8") as handle:
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except TimeoutError:
                    break
                record = {
                    "local_ts": datetime.now(timezone.utc).isoformat(),
                    "message": json.loads(raw),
                }
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    return output


def collect_coinbase_websocket_sync(
    *,
    symbols: Iterable[str],
    seconds: float,
    output_path: str | Path,
    channels: Iterable[str] = DEFAULT_CHANNELS,
) -> Path:
    return asyncio.run(
        collect_coinbase_websocket(
            symbols=symbols,
            seconds=seconds,
            output_path=output_path,
            channels=channels,
        )
    )
