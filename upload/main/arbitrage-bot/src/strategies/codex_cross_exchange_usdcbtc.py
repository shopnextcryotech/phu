"""Cross-exchange BTC/USDC strategy: buy on MEXC, sell on BingX."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    amount: float


class OrderBookProvider(Protocol):
    async def fetch_order_book(self, symbol: str, depth: int) -> dict[str, Sequence[OrderBookLevel]]:
        ...

    async def submit_limit_order(self, symbol: str, side: str, amount: float, price: float) -> str:
        ...

    async def submit_market_order(self, symbol: str, side: str, amount: float) -> str:
        ...


@dataclass
class FillComputation:
    filled: float
    cost: float
    average_price: float
    worst_price: float


def simulate_fill(levels: Iterable[OrderBookLevel], target_amount: float) -> FillComputation:
    filled = 0.0
    cost = 0.0
    worst_price = 0.0
    for level in levels:
        remaining = target_amount - filled
        if remaining <= 0:
            break
        take = min(level.amount, remaining)
        filled += take
        cost += take * level.price
        worst_price = max(worst_price, level.price)
    if filled < target_amount:
        raise ValueError("Недостаточная глубина стакана для требуемого объёма.")
    avg_price = cost / filled
    return FillComputation(filled=filled, cost=cost, average_price=avg_price, worst_price=worst_price)


class CodexCrossExchangeUSDCBTCStrategy:
    symbol = "BTC/USDC"

    def __init__(
        self,
        mexc: OrderBookProvider,
        bingx: OrderBookProvider,
        target_size_btc: float,
        min_spread_bps: float = 5.0,
        depth: int = 25,
        refresh_interval: float = 0.5,
    ) -> None:
        self.mexc = mexc
        self.bingx = bingx
        self.target_size_btc = target_size_btc
        self.min_spread_bps = min_spread_bps
        self.depth = depth
        self.refresh_interval = refresh_interval
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._attempt_cycle()
            except ValueError as exc:
                print(f"[codex-cross] {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"[codex-cross] критическая ошибка: {exc}")
            await asyncio.sleep(self.refresh_interval)

    async def stop(self) -> None:
        self._running = False

    async def _attempt_cycle(self) -> None:
        mexc_book, bingx_book = await asyncio.gather(
            self.mexc.fetch_order_book(self.symbol, self.depth),
            self.bingx.fetch_order_book(self.symbol, self.depth),
        )

        buy_quote = simulate_fill(mexc_book["asks"], self.target_size_btc)
        sell_quote = simulate_fill(bingx_book["bids"], self.target_size_btc)

        spread_bps = (sell_quote.average_price - buy_quote.average_price) / buy_quote.average_price * 10_000
        if spread_bps < self.min_spread_bps:
            raise ValueError(f"спред {spread_bps:.2f} б.п. ниже порога {self.min_spread_bps:.2f}")

        await self._reconfirm_books()

        await self.mexc.submit_limit_order(
            symbol=self.symbol,
            side="buy",
            amount=buy_quote.filled,
            price=buy_quote.worst_price,
        )
        await self.bingx.submit_market_order(
            symbol=self.symbol,
            side="sell",
            amount=sell_quote.filled,
        )

    async def _reconfirm_books(self) -> None:
        mexc_top, bingx_top = await asyncio.gather(
            self.mexc.fetch_order_book(self.symbol, depth=1),
            self.bingx.fetch_order_book(self.symbol, depth=1),
        )
        best_ask = mexc_top["asks"][0].price
        best_bid = bingx_top["bids"][0].price
        if best_bid <= best_ask:
            raise ValueError("Окно арбитража закрылось при повторной проверке.")
