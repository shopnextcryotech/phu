"""
Упрощённый тест REST API без WebSocket
Проверяет стаканы и сделки через ccxt
"""
import asyncio
import ccxt.async_support as ccxt

SYMBOL = "BTC/USDC"

async def test_rest():
    print("=== REST API TEST ===\n")
    
    print("--- MEXC Orderbook ---")
    async with ccxt.mexc() as mexc:
        ob = await mexc.fetch_order_book(SYMBOL, limit=20)
        print(f"Best Ask: {ob['asks'][0]}")
        print(f"Best Bid: {ob['bids'][0]}")
    
    print("\n--- BingX Orderbook ---")
    async with ccxt.bingx() as bingx:
        ob = await bingx.fetch_order_book(SYMBOL, limit=20)
        print(f"Best Ask: {ob['asks'][0]}")
        print(f"Best Bid: {ob['bids'][0]}")
    
    print("\n--- MEXC Recent Trades ---")
    async with ccxt.mexc() as mexc:
        trades = await mexc.fetch_trades(SYMBOL, limit=5)
        for t in trades:
            print(f"{t['datetime']} | {t['side']:4s} | {t['price']} | {t['amount']}")
    
    print("\n--- BingX Recent Trades ---")
    async with ccxt.bingx() as bingx:
        trades = await bingx.fetch_trades(SYMBOL, limit=5)
        for t in trades:
            print(f"{t['datetime']} | {t['side']:4s} | {t['price']} | {t['amount']}")
    
    print("\n✅ TEST PASSED")

if __name__ == '__main__':
    asyncio.run(test_rest())
