"""
FINAL Cross-Exchange BTC/USDC Arbitrage Strategy
Асинхронная архитектура с точной эмуляцией маркет-филла и повторной верификацией окна. Работа через ccxt и полноценный контроль глубины и доходности.
"""
import asyncio
from typing import Sequence
import ccxt.async_support as ccxt
from dataclasses import dataclass

@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    amount: float

def simulate_fill(levels: Sequence[OrderBookLevel], target_amount: float) -> tuple[float, float, float]:
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
        worst_price = level.price
    if filled < target_amount:
        raise ValueError("Недостаточная глубина стакана для требуемого объёма.")
    avg_price = cost / filled
    return filled, cost, worst_price

class FinalCrossExchangeUSDCBTCStrategy:
    def __init__(self, mexc: ccxt.Exchange, bingx: ccxt.Exchange, symbol: str, amount: float, min_profit_usd: float = 0.0, min_spread_bps: float = 0.0, depth: int = 25, refresh_interval: float = 0.5):
        self.mexc = mexc
        self.bingx = bingx
        self.symbol = symbol
        self.target_size_btc = amount
        self.min_profit_usd = min_profit_usd
        self.min_spread_bps = min_spread_bps
        self.depth = depth
        self.refresh_interval = refresh_interval
        self._running = False

    async def fetch_levels(self, exchange, side: str) -> list[OrderBookLevel]:
        book = await exchange.fetch_order_book(self.symbol, limit=self.depth)
        key = 'asks' if side == 'ask' else 'bids'
        return [OrderBookLevel(float(price), float(amount)) for price, amount in book[key]]

    async def run(self):
        self._running = True
        while self._running:
            try:
                await self._attempt_cycle()
            except Exception as exc:
                print(f"[final-cross] error: {exc}")
            await asyncio.sleep(self.refresh_interval)

    async def stop(self):
        self._running = False

    async def _attempt_cycle(self):
        mexc_asks = await self.fetch_levels(self.mexc, 'ask')
        bingx_bids = await self.fetch_levels(self.bingx, 'bid')

        filled_buy, buy_cost, buy_worst = simulate_fill(mexc_asks, self.target_size_btc)
        filled_sell, sell_sum, sell_worst = simulate_fill(bingx_bids, self.target_size_btc)
        avg_buy = buy_cost / filled_buy
        avg_sell = sell_sum / filled_sell
        profit = sell_sum - buy_cost
        spread_bps = (avg_sell - avg_buy) / avg_buy * 10000

        if profit < self.min_profit_usd:
            raise ValueError(f"Профит $ {profit:.2f} ниже порога {self.min_profit_usd}")
        if spread_bps < self.min_spread_bps:
            raise ValueError(f"Cпpед {spread_bps:.2f} б.п. ниже минимального {self.min_spread_bps}")

        # Повторная reconfirm перед сделкой
        mexc_asks_top = await self.fetch_levels(self.mexc, 'ask')
        bingx_bids_top = await self.fetch_levels(self.bingx, 'bid')
        if bingx_bids_top[0].price <= mexc_asks_top[0].price:
            raise ValueError("Окно арбитража закрылось при повторной проверке.")

        # ТВЁРДО выполнять сделки: строго маркет-продажа на BingX, лимит/маркет-покупка на MEXC (по крайней цене заполнения)
        buy_order = await self.mexc.create_limit_buy_order(self.symbol, filled_buy, buy_worst)
        sell_order = await self.bingx.create_market_sell_order(self.symbol, filled_sell)
        print(f"Стратегия исполнена! Покупка на MEXC: {filled_buy} BTC по ср. {avg_buy}, продажа на BingX: {filled_sell} BTC по ср. {avg_sell}, прибыль: {profit:.2f} USDC")
        return buy_order, sell_order
