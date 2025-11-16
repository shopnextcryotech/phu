"""Manual tester for mexc_ws_port.MEXCClient."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from mexc_client import MEXCClient  # noqa: E402


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("websockets.client").setLevel(logging.DEBUG)
    logging.getLogger("websockets.protocol").setLevel(logging.DEBUG)


async def main() -> None:
    _setup_logging()
    client = MEXCClient()
    stream = client.subscribe_trades("BTCUSDC")
    try:
        trades = await stream.__anext__()
        for trade in trades:
            print(
                f"{trade.symbol} {trade.side.value.upper()} "
                f"{trade.quantity} @ {trade.price} ts={trade.timestamp}"
            )
    finally:
        with contextlib.suppress(Exception):
            await stream.aclose()


if __name__ == "__main__":
    asyncio.run(main())
