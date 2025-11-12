"""Standalone WebSocket client for streaming public MEXC spot data."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator

import websockets

try:  # pragma: no cover - allow running from other projects without package install
    from proto import mexc_deals_pb2 as mexc_pb
except ImportError:  # pragma: no cover
    import mexc_deals_pb2 as mexc_pb  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "MEXCClient",
    "OrderSide",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "TradeTick",
]


class Exchange(str, Enum):
    MEXC = "mexc"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderBookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class OrderBookSnapshot:
    exchange: Exchange
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    update_id: int


@dataclass(frozen=True)
class TradeTick:
    exchange: Exchange
    symbol: str
    price: Decimal
    quantity: Decimal
    side: OrderSide
    timestamp: int


WS_ENDPOINTS = [
    "wss://wbs-api.mexc.com/ws",
    "wss://wbs.mexc.com/ws",
]


class MEXCClient:
    """Client that exposes high-level helpers for the public MEXC feeds."""

    def __init__(self, ping_interval: int = 30, endpoints: list[str] | None = None) -> None:
        self.ping_interval = ping_interval
        self.endpoints = endpoints or WS_ENDPOINTS[:]

    async def subscribe_orderbook(
        self,
        symbol: str,
        depth: int = 20,
    ) -> AsyncIterator[OrderBookSnapshot]:
        """Yield top-of-book depth snapshots for the given symbol."""

        channel_symbol = symbol.replace("-", "").upper()
        channel = f"spot@public.limit.depth.v3.api@{channel_symbol}@{depth}"
        subscription = {"method": "SUBSCRIPTION", "params": [channel]}

        async for message in self._ws_stream(subscription, channel):
            snapshot = self._decode_depth_message(message, symbol)
            if snapshot:
                yield snapshot

    async def subscribe_trades(
        self,
        symbol: str,
        interval_ms: int = 100,
    ) -> AsyncIterator[list[TradeTick]]:
        """Yield aggregated deals (trade batches) for the given symbol."""

        channel_symbol = symbol.replace("-", "").upper()
        channel = f"spot@public.aggre.deals.v3.api.pb@{interval_ms}ms@{channel_symbol}"
        subscription = {"method": "SUBSCRIPTION", "params": [channel]}

        async for message in self._ws_stream(subscription, channel):
            trades = self._decode_trade_message(message, channel_symbol)
            if trades:
                yield trades

    async def _ping(self, ws: websockets.WebSocketClientProtocol) -> None:
        while True:
            await asyncio.sleep(self.ping_interval)
            try:
                await ws.send(json.dumps({"method": "PING"}))
            except Exception as exc:  # pragma: no cover - best effort ping
                logger.debug("mexc.ws.ping_failed %s", exc)
                return

    def _decode_trade_message(self, message: Any, symbol: str) -> list[TradeTick]:
        if isinstance(message, bytes):
            stripped = message.lstrip()
            if stripped.startswith(b"{"):
                return self._handle_text_payload(stripped.decode())
            wrapper = mexc_pb.PushDataV3ApiWrapper()
            wrapper.ParseFromString(message)
            if not wrapper.publicAggreDeals.deals:
                return []
            trades: list[TradeTick] = []
            for deal in wrapper.publicAggreDeals.deals:
                side = OrderSide.BUY if deal.tradeType == 1 else OrderSide.SELL
                trades.append(
                    TradeTick(
                        exchange=Exchange.MEXC,
                        symbol=symbol,
                        price=Decimal(deal.price),
                        quantity=Decimal(deal.quantity),
                        side=side,
                        timestamp=int(deal.time),
                    )
                )
            return trades

        if isinstance(message, str):
            return self._handle_text_payload(message)

        logger.debug("mexc.ws.unsupported_message %s", type(message))
        return []

    def _handle_text_payload(self, text: str) -> list[TradeTick]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("mexc.ws.unknown_text %s", text[:50])
            return []
        if payload.get("method") == "PONG":
            return []
        code = payload.get("code", 0)
        if code != 0:
            logger.warning("mexc.ws.error %s", payload)
        else:
            logger.info("mexc.ws.ack %s", payload.get("msg"))
        return []

    def _decode_depth_message(self, message: Any, symbol: str) -> OrderBookSnapshot | None:
        payload = self._extract_json(message)
        if not payload:
            return None
        data = payload.get("data")
        if not data:
            return None
        bids = self._parse_levels(data.get("bids", []), is_bid=True)
        asks = self._parse_levels(data.get("asks", []), is_bid=False)
        if not bids or not asks:
            return None
        update_id = int(data.get("updateTime") or payload.get("ts", 0) or 0)
        return OrderBookSnapshot(
            exchange=Exchange.MEXC,
            symbol=symbol,
            bids=bids,
            asks=asks,
            update_id=update_id,
        )

    @staticmethod
    def _parse_levels(levels: list[list[str]], is_bid: bool) -> list[OrderBookLevel]:
        parsed = [OrderBookLevel(price=Decimal(price), size=Decimal(size)) for price, size in levels]
        parsed.sort(key=lambda lvl: lvl.price, reverse=is_bid)
        return parsed

    @staticmethod
    def _extract_json(message: Any) -> dict | None:
        text: str | None = None
        if isinstance(message, bytes):
            try:
                text = message.decode()
            except UnicodeDecodeError:
                return None
        elif isinstance(message, str):
            text = message
        else:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("mexc.ws.depth_unknown %s", text[:50])
            return None

    async def _ws_stream(self, subscription: dict, channel: str) -> AsyncIterator[Any]:
        endpoints = self.endpoints or WS_ENDPOINTS
        idx = 0
        while True:
            endpoint = endpoints[idx % len(endpoints)]
            idx += 1
            try:
                logger.info("mexc.ws.connect endpoint=%s channel=%s", endpoint, channel)
                async with websockets.connect(
                    endpoint,
                    ping_interval=None,
                    max_queue=None,
                ) as ws:
                    logger.info(
                        "mexc.ws.connected endpoint=%s remote=%s channel=%s",
                        endpoint,
                        getattr(ws, "remote_address", "unknown"),
                        channel,
                    )
                    ping_task = asyncio.create_task(self._ping(ws))
                    await ws.send(json.dumps(subscription))
                    async for message in ws:
                        yield message
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except (websockets.WebSocketException, OSError) as exc:
                logger.warning("mexc.ws.retry %s %s endpoint=%s", channel, exc, endpoint)
                await asyncio.sleep(1)
            finally:
                if "ping_task" in locals():
                    ping_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await ping_task
