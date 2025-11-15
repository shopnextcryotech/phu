"""
📊 MEXC OrderBook Real-Time Display
Показывает стакан заявок BTC/USDC (10 bid + 10 ask)
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import ccxt.async_support as ccxt

# Загрузка .env
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env_file(env_path):
    """Прямое чтение .env файла"""
    env_vars = {}
    
    if not Path(env_path).exists():
        return env_vars
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    return env_vars


def clear_screen():
    """Очистка экрана"""
    os.system('cls' if os.name == 'nt' else 'clear')


def display_orderbook(bids, asks):
    """
    Красивое отображение стакана
    bids: список [(price, quantity), ...]
    asks: список [(price, quantity), ...]
    """
    clear_screen()
    
    # Заголовок
    print("\n" + "="*85)
    print(f"📊 MEXC ORDER BOOK - BTC/USDC".center(85))
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(85))
    print("="*85 + "\n")
    
    # Берём топ 10 заявок
    top_asks = list(reversed(asks[:10]))  # Переворачиваем asks (самые низкие внизу)
    top_bids = bids[:10]
    
    # Заголовок таблицы
    print(f"{'SIDE':^10} | {'PRICE (USDC)':^18} | {'AMOUNT (BTC)':^18} | {'TOTAL (USDC)':^18}")
    print("-" * 85)
    
    # Показываем ASKS (продажи) - сверху вниз
    for price, qty in top_asks:
        total = price * qty
        print(f"🔴 SELL   | ${price:>16,.2f} | {qty:>16.6f} | ${total:>16,.2f}")
    
    # Разделитель между asks и bids
    print("\n" + "━"*85 + "\n")
    
    # Показываем BIDS (покупки) - сверху вниз
    for price, qty in top_bids:
        total = price * qty
        print(f"🟢 BUY    | ${price:>16,.2f} | {qty:>16.6f} | ${total:>16,.2f}")
    
    # Статистика
    if top_bids and top_asks:
        best_bid = top_bids[0][0]
        best_ask = top_asks[-1][0]
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid) * 100
        
        print("\n" + "="*85)
        print(f"💹 Best Bid: ${best_bid:,.2f} | Best Ask: ${best_ask:,.2f} | Spread: ${spread:.2f} ({spread_pct:.3f}%)")
        print("="*85)
    
    print("\n💡 Обновление каждые 2 секунды... (Ctrl+C для выхода)\n")


async def main():
    """Основной цикл отображения orderbook"""
    
    # Загружаем API ключи
    env_path = ROOT / 'config' / '.env'
    env_vars = load_env_file(env_path)
    
    api_key = (
        env_vars.get('MEXC_API_KEY', '').strip() or 
        env_vars.get('ARB_MEXC_API_KEY', '').strip()
    )
    api_secret = (
        env_vars.get('MEXC_API_SECRET', '').strip() or 
        env_vars.get('ARB_MEXC_API_SECRET', '').strip()
    )
    
    # Создаём exchange (API ключи не обязательны для публичных данных)
    exchange = ccxt.mexc({
        'enableRateLimit': True
    })
    
    print("🔌 Подключение к MEXC...\n")
    
    try:
        while True:
            # Получаем orderbook через REST API
            orderbook = await exchange.fetch_order_book('BTC/USDC', limit=20)
            
            if orderbook:
                bids = orderbook['bids'][:10]  # Топ 10 bid
                asks = orderbook['asks'][:10]  # Топ 10 ask
                
                # Отображаем
                display_orderbook(bids, asks)
            else:
                print("⚠️  Ожидание данных orderbook...")
            
            # Обновляем каждые 2 секунды (чтобы не превысить rate limit)
            await asyncio.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\n👋 Остановка...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
