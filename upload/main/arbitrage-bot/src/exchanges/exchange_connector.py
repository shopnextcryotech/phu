"""
ExchangeConnector
Универсальная обёртка для ccxt async: инициализация, хранение API ключей, базовые методы (balance, orderbook).
Поддержка бирж: MEXC, BingX.
"""
import os
import ccxt.async_support as ccxt

class ExchangeConnector:
    def __init__(self, name: str, api_key: str, secret: str, password: str = None):
        exchanges = {
            'mexc': ccxt.mexc,
            'bingx': ccxt.bingx,
        }
        if name.lower() not in exchanges:
            raise ValueError(f"Unknown exchange: {name}")
        self.api = exchanges[name.lower()]({
            'apiKey': api_key,
            'secret': secret,
        })
        if password:
            self.api.password = password
        self.name = name

    async def fetch_balance(self):
        return await self.api.fetch_balance()

    async def fetch_order_book(self, symbol: str, depth: int = 10):
        return await self.api.fetch_order_book(symbol, limit=depth)

    async def test_connection(self):
        try:
            balance = await self.fetch_balance()
            print(f"{self.name} connected: balance fetched.")
            return True
        except Exception as exc:
            print(f"{self.name} connection failed: {exc}")
            return False

    async def close(self):
        await self.api.close()

# Шаблон использования:
# from config import API_KEYS
# mexc = ExchangeConnector('mexc', API_KEYS['MEXC_KEY'], API_KEYS['MEXC_SECRET'])
# bingx = ExchangeConnector('bingx', API_KEYS['BINGX_KEY'], API_KEYS['BINGX_SECRET'])
