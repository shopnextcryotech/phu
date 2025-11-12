"""MEXC WebSocket client for real-time orderbook and trades streaming.

Based on mexc_ws_port/mexc_client.py - production-ready implementation.
"""

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

# Import protobuf module for trade aggregation
try:
    from .mexc_ws_port.proto import mexc_deals_pb2 as mexc_pb
except ImportError:
    try:
        from mexc_ws_port.proto import mexc_deals_pb2 as mexc_pb
    except ImportError:
        import sys
        import os
        # Fallback for standalone execution
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mexc_ws_port"))
        from proto import mexc_deals_pb2 as mexc_pb

logger = logging.getLogger(__name__)

__all__ = [
    "MEXCWebSocket",
    "OrderSide",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "TradeTick",
]


class Exchange(str, Enum):
    """Exchange identifier."""
    MEXC = "mexc"


class OrderSide(str, Enum):
    """Order side: buy or sell."""
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderBookLevel:
    """Single price level in the orderbook."""
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Complete orderbook snapshot with bids and asks."""
    exchange: Exchange
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    update_id: int
    timestamp: int = 0


@dataclass(frozen=True)
class TradeTick:
    """Single trade execution."""
    exchange: Exchange
    symbol: str
    price: Decimal
    quantity: Decimal
    side: OrderSide
    timestamp: int


# MEXC WebSocket endpoints (primary and backup)
WS_ENDPOINTS = [
    "wss://wbs-api.mexc.com/ws",
    "wss://wbs.mexc.com/ws",
]


class MEXCWebSocket:
    """
    Production-ready MEXC WebSocket client.
    
    Features:
    - Real-time orderbook depth streaming
    - Aggregated trades (protobuf format)
    - Automatic reconnection with fallback endpoints
    - Built-in ping/pong keepalive
    - Comprehensive error handling and logging
    
    Example:
        >>> client = MEXCWebSocket()
        >>> async for snapshot in client.subscribe_orderbook("BTCUSDT", depth=20):
        ...     print(f"Best bid: {snapshot.bids[0].price}")
    """

    def __init__(
        self,
        ping_interval: int = 30,
        endpoints: list[str] | None = None,
        reconnect_delay: int = 1,
    ) -> None:
        """
        Initialize MEXC WebSocket client.
        
        Args:
            ping_interval: Seconds between ping messages (default: 30)
            endpoints: Custom WebSocket endpoints (default: official MEXC endpoints)
            reconnect_delay: Seconds to wait before reconnecting (default: 1)
        """
        self.ping_interval = ping_interval
        self.endpoints = endpoints or WS_ENDPOINTS[:]
        self.reconnect_delay = reconnect_delay
        self._endpoint_index = 0

    async def subscribe_orderbook(
        self,
        symbol: str,
        depth: int = 20,
    ) -> AsyncIterator[OrderBookSnapshot]:
        """
        Subscribe to orderbook depth updates.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT" or "BTC-USDT")
            depth: Depth levels (5, 10, 20) - default: 20
            
        Yields:
            OrderBookSnapshot objects with top bids/asks
            
        Example:
            >>> async for book in client.subscribe_orderbook("BTCUSDT", depth=20):
            ...     spread = book.asks[0].price - book.bids[0].price
            ...     print(f"Spread: {spread}")
        """
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
        """
        Subscribe to aggregated trade executions.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            interval_ms: Aggregation interval in milliseconds (default: 100)
            
        Yields:
            Lists of TradeTick objects (batched by interval)
            
        Example:
            >>> async for trades in client.subscribe_trades("BTCUSDT"):
            ...     total_volume = sum(t.quantity for t in trades)
            ...     print(f"Batch volume: {total_volume}")
        """
        channel_symbol = symbol.replace("-", "").upper()
        channel = f"spot@public.aggre.deals.v3.api.pb@{interval_ms}ms@{channel_symbol}"
        subscription = {"method": "SUBSCRIPTION", "params": [channel]}

        async for message in self._ws_stream(subscription, channel):
            trades = self._decode_trade_message(message, channel_symbol)
            if trades:
                yield trades

    async def _ping(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Send periodic PING messages to keep connection alive."""
        while True:
            await asyncio.sleep(self.ping_interval)
            try:
                await ws.send(json.dumps({"method": "PING"}))
                logger.debug("mexc.ws.ping_sent")
            except Exception as exc:
                logger.debug("mexc.ws.ping_failed %s", exc)
                return

    def _decode_trade_message(self, message: Any, symbol: str) -> list[TradeTick]:
        """Decode protobuf or JSON trade message."""
        if isinstance(message, bytes):
            stripped = message.lstrip()
            # Check if it's JSON wrapped in bytes
            if stripped.startswith(b"{"):
                return self._handle_text_payload(stripped.decode())
            
            # Parse protobuf message
            try:
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
            except Exception as exc:
                logger.debug("mexc.ws.protobuf_parse_error %s", exc)
                return []

        if isinstance(message, str):
            return self._handle_text_payload(message)

        logger.debug("mexc.ws.unsupported_message_type %s", type(message))
        return []

    def _handle_text_payload(self, text: str) -> list[TradeTick]:
        """Handle JSON text messages (ACK, PONG, errors)."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("mexc.ws.invalid_json %s", text[:100])
            return []
        
        # Handle PONG response
        if payload.get("method") == "PONG":
            logger.debug("mexc.ws.pong_received")
            return []
        
        # Handle subscription ACK or errors
        code = payload.get("code", 0)
        if code != 0:
            logger.warning("mexc.ws.subscription_error code=%s msg=%s", code, payload)
        else:
            msg = payload.get("msg", "")
            if msg:
                logger.info("mexc.ws.subscription_ack %s", msg)
        
        return []

    def _decode_depth_message(
        self, 
        message: Any, 
        symbol: str
    ) -> OrderBookSnapshot | None:
        """Decode orderbook depth message."""
        payload = self._extract_json(message)
        if not payload:
            return None
        
        data = payload.get("data")
        if not data:
            return None
        
        bids = self._parse_levels(data.get("bids", []), is_bid=True)
        asks = self._parse_levels(data.get("asks", []), is_bid=False)
        
        if not bids or not asks:
            logger.debug("mexc.ws.empty_orderbook symbol=%s", symbol)
            return None
        
        update_id = int(data.get("updateTime") or payload.get("ts", 0) or 0)
        
        return OrderBookSnapshot(
            exchange=Exchange.MEXC,
            symbol=symbol,
            bids=bids,
            asks=asks,
            update_id=update_id,
            timestamp=update_id,
        )

    @staticmethod
    def _parse_levels(levels: list[list[str]], is_bid: bool) -> list[OrderBookLevel]:
        """Parse and sort orderbook levels."""
        try:
            parsed = [
                OrderBookLevel(price=Decimal(price), size=Decimal(size))
                for price, size in levels
            ]
            # Sort: bids descending (highest first), asks ascending (lowest first)
            parsed.sort(key=lambda lvl: lvl.price, reverse=is_bid)
            return parsed
        except (ValueError, TypeError) as exc:
            logger.debug("mexc.ws.parse_levels_error %s", exc)
            return []

    @staticmethod
    def _extract_json(message: Any) -> dict | None:
        """Extract JSON dictionary from message."""
        text: str | None = None
        
        if isinstance(message, bytes):
            try:
                text = message.decode("utf-8")
            except UnicodeDecodeError:
                return None
        elif isinstance(message, str):
            text = message
        else:
            return None
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("mexc.ws.json_decode_error %s", text[:100])
            return None

    async def _ws_stream(
        self, 
        subscription: dict, 
        channel: str
    ) -> AsyncIterator[Any]:
        """
        Main WebSocket connection loop with automatic reconnection.
        
        Implements:
        - Endpoint rotation on failure
        - Automatic reconnection with delay
        - Ping task management
        - Graceful shutdown
        """
        while True:
            endpoint = self.endpoints[self._endpoint_index % len(self.endpoints)]
            self._endpoint_index += 1
            
            ping_task = None
            
            try:
                logger.info(
                    "🔌 mexc.ws.connecting endpoint=%s channel=%s",
                    endpoint,
                    channel,
                )
                
                async with websockets.connect(
                    endpoint,
                    ping_interval=None,  # We handle ping manually
                    max_queue=None,
                    close_timeout=5,
                ) as ws:
                    logger.info(
                        "✅ mexc.ws.connected endpoint=%s remote=%s channel=%s",
                        endpoint,
                        getattr(ws, "remote_address", "unknown"),
                        channel,
                    )
                    
                    # Start ping task
                    ping_task = asyncio.create_task(self._ping(ws))
                    
                    # Send subscription
                    await ws.send(json.dumps(subscription))
                    logger.debug("📤 mexc.ws.subscription_sent %s", subscription)
                    
                    # Stream messages
                    async for message in ws:
                        yield message
                        
            except asyncio.CancelledError:
                logger.info("mexc.ws.cancelled channel=%s", channel)
                raise
                
            except (websockets.WebSocketException, OSError, ConnectionError) as exc:
                logger.warning(
                    "⚠️ mexc.ws.connection_error channel=%s error=%s endpoint=%s",
                    channel,
                    exc,
                    endpoint,
                )
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as exc:
                logger.error(
                    "❌ mexc.ws.unexpected_error channel=%s error=%s",
                    channel,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(self.reconnect_delay)
                
            finally:
                # Clean up ping task
                if ping_task and not ping_task.done():
                    ping_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await ping_task


# Convenience alias for backward compatibility
MEXCClient = MEXCWebSocket
