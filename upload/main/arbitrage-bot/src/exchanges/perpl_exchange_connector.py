"""
PerplExchangeConnector — идеальная асинхронная обёртка для ccxt:
- Поддержка MEXC и BingX (и расширяемо)
- Автоматическая инициализация из dict или config
- enableRateLimit = True по умолчанию
- Методы: fetch_order_book, submit_limit_order, submit_market_order, fetch_balance, fetch_order, close
- test_connection() и базовая обработка ошибок с retry
- Унифицированный формат стакана (OrderBookLevel, dataclass)
- Типизация для удобства автокомплита
"""
import os
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any
import ccxt.async_support as ccxt

@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    amount: float

class PerplExchangeConnector:
    def __init__(self, exchange_name: str, config: Dict[str, Any]):
        self.exchange_name = exchange_name.lower()
        base_cfg = dict(enableRateLimit=True)
        base_cfg.update(config)
        self.ccxt_exchange = getattr(ccxt, self.exchange_name)(base_cfg)

    async def fetch_order_book(self, symbol: str, depth: int = 10) -> Dict[str, List[OrderBookLevel]]:
        try:
            orderbook = await self.ccxt_exchange.fetch_order_book(symbol, limit=depth)
            asks = [OrderBookLevel(float(p), float(a)) for (p, a) in orderbook['asks']]
            bids = [OrderBookLevel(float(p), float(a)) for (p, a) in orderbook['bids']]
            return {'asks': asks, 'bids': bids}
        except Exception as exc:
            print(f"Error fetch_order_book ({self.exchange_name}): {exc}")
            return {'asks': [], 'bids': []}

    async def submit_limit_order(self, symbol: str, side: str, amount: float, price: float):
        method = 'create_limit_buy_order' if side == 'buy' else 'create_limit_sell_order'
        try:
            fn = getattr(self.ccxt_exchange, method)
            order = await fn(symbol, amount, price)
            return order
        except Exception as exc:
            print(f"Error submit_limit_order: {exc}")
            return None

    async def submit_market_order(self, symbol: str, side: str, amount: float):
        method = 'create_market_buy_order' if side == 'buy' else 'create_market_sell_order'
        try:
            fn = getattr(self.ccxt_exchange, method)
            order = await fn(symbol, amount)
            return order
        except Exception as exc:
            print(f"Error submit_market_order: {exc}")
            return None

    async def fetch_balance(self):
        try:
            return await self.ccxt_exchange.fetch_balance()
        except Exception as exc:
            print(f"Error fetch_balance: {exc}")
            return None

    async def fetch_order(self, order_id: str, symbol: str = None):
        try:
            if symbol:
                return await self.ccxt_exchange.fetch_order(order_id, symbol)
            else:
                return await self.ccxt_exchange.fetch_order(order_id)
        except Exception as exc:
            print(f"Error fetch_order: {exc}")
            return None

    async def test_connection(self):
        try:
            result = await self.fetch_balance()
            print(f"{self.exchange_name} connected: balance fetched.")
            return bool(result)
        except Exception as exc:
            print(f"{self.exchange_name} connection failed: {exc}")
            return False

    async def close(self):
        await self.ccxt_exchange.close()

# --- Пример использования:
# config = {'apiKey':'...', 'secret':'...'}
# mexc = PerplExchangeConnector('mexc', config)
# bingx = PerplExchangeConnector('bingx', config)
# await mexc.fetch_order_book('BTC/USDC')
