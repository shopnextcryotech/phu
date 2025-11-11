"""????????? ????????? ????????? BTC/USDC ????? MEXC ? BingX.

????????:
1. ???????? BTC ?? USDC ?? MEXC (???????? ?????, ????????? ???????).
2. ??????? BTC ?? USDC ?? BingX ?? ???????, ???????? ?????????? ?? ???????.
3. ???????? ????????? ????????, ???????? ??? ????????? ?? ??????.
4. ????? ?????? ??????? ?????? ????????????? ???????, ????? ?? ???? ? ?????.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence

try:
    import ccxt  # type: ignore
except Exception:  # noqa: BLE001
    ccxt = None  # type: ignore

LOGGER = logging.getLogger("final_codex_cross")


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    amount: float


class OrderBookProvider(Protocol):
    async def fetch_order_book(
        self, symbol: str, depth: int
    ) -> dict[str, Sequence[OrderBookLevel]]:
        ...

    async def submit_limit_order(
        self, symbol: str, side: str, amount: float, price: float
    ) -> str:
        ...

    async def submit_market_order(
        self, symbol: str, side: str, amount: float
    ) -> str:
        ...

    async def fetch_balance(self, asset: str) -> float:
        ...


@dataclass
class FillComputation:
    filled: float
    cost: float
    average_price: float
    worst_price: float


@dataclass
class ExecutionResult:
    buy_order_id: str
    sell_order_id: str
    spread_bps: float
    estimated_profit: float


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
        raise ValueError("???????????? ??????????? ??? ?????????? ??????.")
    avg_price = cost / filled
    return FillComputation(filled=filled, cost=cost, average_price=avg_price, worst_price=worst_price)


def compute_spread_bps(bid_price: float, ask_price: float) -> float:
    return (bid_price - ask_price) / ask_price * 10_000


class CCXTAdapter(OrderBookProvider):
    def __init__(self, client: "ccxt.Exchange") -> None:  # type: ignore[name-defined]
        if ccxt is None:
            raise RuntimeError("ccxt ?? ?????????? – ??????????? ???? ??????? OrderBookProvider.")
        self._client = client

    async def fetch_order_book(self, symbol: str, depth: int) -> dict[str, Sequence[OrderBookLevel]]:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, lambda: self._client.fetch_order_book(symbol, depth))
        return {
            "bids": [OrderBookLevel(price=p, amount=amt) for p, amt in raw["bids"]],
            "asks": [OrderBookLevel(price=p, amount=amt) for p, amt in raw["asks"]],
        }

    async def submit_limit_order(self, symbol: str, side: str, amount: float, price: float) -> str:
        loop = asyncio.get_running_loop()
        order = await loop.run_in_executor(
            None, lambda: self._client.create_limit_order(symbol, side, amount, price)
        )
        return str(order.get("id", "unknown-limit-id"))

    async def submit_market_order(self, symbol: str, side: str, amount: float) -> str:
        loop = asyncio.get_running_loop()
        order = await loop.run_in_executor(
            None, lambda: self._client.create_market_order(symbol, side, amount)
        )
        return str(order.get("id", "unknown-market-id"))

    async def fetch_balance(self, asset: str) -> float:
        loop = asyncio.get_running_loop()
        balance = await loop.run_in_executor(None, self._client.fetch_balance)
        return float(balance.get(asset, {}).get("free", 0.0))


class FinalCodexCrossExchangeUSDCBTCStrategy:
    symbol = "BTC/USDC"

    def __init__(
        self,
        mexc: OrderBookProvider,
        bingx: OrderBookProvider,
        target_size_btc: float,
        min_spread_bps: float = 5.0,
        min_profit_usd: float = 5.0,
        depth: int = 25,
        confirm_depth: int = 1,
        refresh_interval: float = 0.75,
        dry_run: bool = True,
    ) -> None:
        self.mexc = mexc
        self.bingx = bingx
        self.target_size_btc = target_size_btc
        self.min_spread_bps = min_spread_bps
        self.min_profit_usd = min_profit_usd
        self.depth = depth
        self.confirm_depth = confirm_depth
        self.refresh_interval = refresh_interval
        self.dry_run = dry_run
        self._running = False

    async def run(self) -> None:
        self._running = True
        LOGGER.info("????????? ????????, ??????? ????? %.6f BTC.", self.target_size_btc)
        while self._running:
            try:
                result = await self._attempt_cycle()
                if result:
                    LOGGER.info(
                        "?????? ?????????: buy=%s sell=%s spread=%.2f ?.?. profit˜%.2f USDC",
                        result.buy_order_id,
                        result.sell_order_id,
                        result.spread_bps,
                        result.estimated_profit,
                    )
            except ValueError as exc:
                LOGGER.debug("??????? ?? ?????????: %s", exc)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("??????????? ?????? ?????: %s", exc)
            await asyncio.sleep(self.refresh_interval)

    async def stop(self) -> None:
        self._running = False

    async def _attempt_cycle(self) -> Optional[ExecutionResult]:
        mexc_book, bingx_book = await asyncio.gather(
            self.mexc.fetch_order_book(self.symbol, self.depth),
            self.bingx.fetch_order_book(self.symbol, self.depth),
        )

        buy_quote = simulate_fill(mexc_book["asks"], self.target_size_btc)
        sell_quote = simulate_fill(bingx_book["bids"], self.target_size_btc)

        spread_bps = compute_spread_bps(sell_quote.average_price, buy_quote.average_price)
        if spread_bps < self.min_spread_bps:
            raise ValueError(f"????? {spread_bps:.2f} ?.?. ???? ?????? {self.min_spread_bps:.2f}")

        estimated_profit = sell_quote.cost - buy_quote.cost
        if estimated_profit < self.min_profit_usd:
            raise ValueError(f"??????? {estimated_profit:.2f} ???? ???????? {self.min_profit_usd:.2f} USDC")

        await self._ensure_balances(buy_quote)
        await self._confirm_books()

        if self.dry_run:
            LOGGER.info(
                "DRY-RUN: buy %.6f BTC ?? MEXC @ %.2f, sell ?? BingX @ avg %.2f (spread %.2f ?.?.).",
                buy_quote.filled,
                buy_quote.worst_price,
                sell_quote.average_price,
                spread_bps,
            )
            return ExecutionResult("dry-run", "dry-run", spread_bps, estimated_profit)

        buy_id = await self.mexc.submit_limit_order(
            symbol=self.symbol,
            side="buy",
            amount=buy_quote.filled,
            price=buy_quote.worst_price,
        )
        sell_id = await self.bingx.submit_market_order(
            symbol=self.symbol,
            side="sell",
            amount=sell_quote.filled,
        )
        return ExecutionResult(buy_id, sell_id, spread_bps, estimated_profit)

    async def _ensure_balances(self, buy_quote: FillComputation) -> None:
        usdc_needed = buy_quote.cost
        btc_needed = buy_quote.filled
        mexc_usdc, bingx_btc = await asyncio.gather(
            self.mexc.fetch_balance("USDC"),
            self.bingx.fetch_balance("BTC"),
        )
        if mexc_usdc < usdc_needed:
            raise ValueError(
                f"???????? USDC ?? MEXC: ????????? {usdc_needed:.2f}, ???????? {mexc_usdc:.2f}"
            )
        if bingx_btc < btc_needed:
            raise ValueError(
                f"???????? BTC ?? BingX: ????????? {btc_needed:.6f}, ???????? {bingx_btc:.6f}"
            )

    async def _confirm_books(self) -> None:
        mexc_top, bingx_top = await asyncio.gather(
            self.mexc.fetch_order_book(self.symbol, self.confirm_depth),
            self.bingx.fetch_order_book(self.symbol, self.confirm_depth),
        )
        best_ask = mexc_top["asks"][0].price
        best_bid = bingx_top["bids"][0].price
        if best_bid <= best_ask:
            raise ValueError("??????????? ???? ????????? ??? ????????? ????????.")
