"""Strategies module for arbitrage opportunities."""

from .cto_cross_exchange_usdcbtc import (
    CrossExchangeUSDCBTCStrategy,
    TradeOpportunity,
    ExecutionResult,
    OrderBook,
    OrderBookLevel,
)

__all__ = [
    "CrossExchangeUSDCBTCStrategy",
    "TradeOpportunity",
    "ExecutionResult",
    "OrderBook",
    "OrderBookLevel",
]
