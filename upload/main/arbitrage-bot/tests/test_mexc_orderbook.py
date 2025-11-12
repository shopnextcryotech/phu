import asyncio
import logging
import sys
from pathlib import Path

# Добавляем путь к src для импорта модулей
project_root = Path(__file__).parent.parent
exchanges_path = project_root / "src" / "exchanges"
sys.path.insert(0, str(exchanges_path))

# Теперь импортируем из mexc_ws_port
from mexc_ws_port.mexc_client import MEXCClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)

async def test_orderbook(symbol="BTCUSDT", depth=5, duration=10):
    """
    Тест стриминга orderbook.
    
    Args:
        symbol: Торговая пара
        depth: Глубина стакана (5, 10, 20)
        duration: Длительность теста в секундах
    """
    print("=" * 80)
    print(f"ТЕСТ ORDERBOOK: {symbol}, глубина {depth}, {duration} сек")
    print("=" * 80)
    
    client = MEXCClient(ping_interval=30)
    count = 0
    start = asyncio.get_event_loop().time()
    
    try:
        async for snapshot in client.subscribe_orderbook(symbol, depth=depth):
            count += 1
            elapsed = asyncio.get_event_loop().time() - start
            
            print(f"\nSnapshot #{count} | Update: {snapshot.update_id} | Time: {elapsed:.2f}s")
            print("BIDS (покупка):")
            for i, bid in enumerate(snapshot.bids[:3], 1):
                print(f"  {i}. Price: {bid.price:>12} | Size: {bid.size:>12}")
            
            print("ASKS (продажа):")
            for i, ask in enumerate(snapshot.asks[:3], 1):
                print(f"  {i}. Price: {ask.price:>12} | Size: {ask.size:>12}")
            
            # Расчёт спреда
            if snapshot.bids and snapshot.asks:
                best_bid = snapshot.bids[0].price
                best_ask = snapshot.asks[0].price
                spread = best_ask - best_bid
                spread_pct = (spread / best_ask) * 100
                print(f"\nBest Bid: {best_bid} | Best Ask: {best_ask}")
                print(f"Spread: {spread} ({spread_pct:.4f}%)")
            
            print("-" * 80)
            
            if elapsed >= duration:
                print(f"\nТест завершён: {count} снимков за {duration} сек")
                print(f"Частота: {count/duration:.2f} снимков/сек")
                break
                
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    except Exception as exc:
        print(f"\nОшибка: {exc}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_orderbook())
