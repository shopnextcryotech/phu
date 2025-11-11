"""
perpl_websocket_manager.py — асинхронный менеджер многоканальных WebSocket MEXC/BingX для получения real-time стаканов
Включает подписку, reconnection, push delivery в стратегию (коллбек).
"""
import asyncio
from arbitrage.exchanges.mexc import MEXCClient
from arbitrage.exchanges.bingx import BingXClient

class PerplWebSocketManager:
    def __init__(self, symbols, depth_mexc=20, depth_bingx=50):
        self.symbols = symbols
        self.clients = {
            "mexc": MEXCClient(ping_interval=20),
            "bingx": BingXClient(depth=depth_bingx, ping_interval=15)
        }
        self._listeners = []
        self._tasks = []

    def add_orderbook_listener(self, func):
        """Регистрирует функцию-обработчик: func(market, symbol, orderbook)"""
        self._listeners.append(func)

    async def start(self):
        for symbol in self.symbols:
            self._tasks.append(asyncio.create_task(self._run_mexc_orderbook(symbol)))
            self._tasks.append(asyncio.create_task(self._run_bingx_orderbook(symbol)))

    async def _run_mexc_orderbook(self, symbol):
        async for snapshot in self.clients["mexc"].subscribe_orderbook(symbol, depth=20):
            for listener in self._listeners:
                listener("mexc", symbol, snapshot)

    async def _run_bingx_orderbook(self, symbol):
        async for snapshot in self.clients["bingx"].subscribe_orderbook(symbol):
            for listener in self._listeners:
                listener("bingx", symbol, snapshot)

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.sleep(0)  # дать задачам закрыться
