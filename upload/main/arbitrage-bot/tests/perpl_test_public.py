"""
perpl_test_public.py — тестовый скрипт для проверки публичных методов MEXC и BingX (без API ключей)
Выводит стакан через REST и WebSocket, а также последние сделки.
"""
import asyncio
import ccxt.async_support as ccxt
from src.connectivity.perpl_websocket_manager import PerplWebSocketManager

SYMBOL = "BTC/USDC"

async def test_rest():
    print("--- REST orderbook MEXC ---")
    async with ccxt.mexc() as mexc:
        ob = await mexc.fetch_order_book(SYMBOL, limit=20)
        print("Asks[0]:", ob["asks"][0], "Bids[0]:", ob["bids"][0])
    print("--- REST orderbook BINGX ---")
    async with ccxt.bingx() as bingx:
        ob = await bingx.fetch_order_book(SYMBOL, limit=20)
        print("Asks[0]:", ob["asks"][0], "Bids[0]:", ob["bids"][0])

async def test_ws():
    print("--- WebSocket orderbook SNAPSHOT (MEXC/BingX, 1 раз) ---")
    results = {}
    def cb(market, symbol, snapshot):
        if market not in results:
            results[market] = snapshot
    mgr = PerplWebSocketManager([SYMBOL], depth_mexc=20, depth_bingx=20)
    mgr.add_orderbook_listener(cb)
    await mgr.start()
    await asyncio.sleep(2)
    await mgr.stop()
    for market, snap in results.items():
        try:
            print(f"{market} best_bid: {snap.bids[0].price}", f"best_ask: {snap.asks[0].price}")
        except Exception as e:
            print(market, "bad snapshot", e)

async def test_trades():
    print("--- Recent trades MEXC ---")
    async with ccxt.mexc() as mexc:
        trades = await mexc.fetch_trades(SYMBOL)
        print(trades[:3])
    print("--- Recent trades BINGX ---")
    async with ccxt.bingx() as bingx:
        trades = await bingx.fetch_trades(SYMBOL)
        print(trades[:3])

async def main():
    await test_rest()
    await test_ws()
    await test_trades()

if __name__ == '__main__':
    asyncio.run(main())
