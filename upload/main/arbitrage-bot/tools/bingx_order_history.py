"""
🔥 Расширенный тест BingX: Последние 8 лимитных + 8 рыночных ордеров
📍 Использует ccxt для совместимости с MEXC тестом
🕐 Время в московском часовом поясе (MSK, UTC+3)
✅ Показывает исполненные и отменённые ордера
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
import ccxt.async_support as ccxt

env_path = Path(__file__).resolve().parents[1] / "config" / ".env"
load_dotenv(env_path)

SYMBOL = "BTC/USDC"
MSK_OFFSET = timedelta(hours=3)

def utc_to_msk(utc_datetime_str):
    """Конвертирует UTC время в московское (MSK)"""
    try:
        utc_time = datetime.fromisoformat(utc_datetime_str.replace('Z', '+00:00'))
        msk_time = utc_time + MSK_OFFSET
        return msk_time.strftime('%Y-%m-%d %H:%M:%S MSK')
    except:
        return utc_datetime_str

def format_price(price):
    """Форматирует цену с разделителями тысяч"""
    if price == 'N/A' or price is None:
        return 'N/A'
    try:
        return f"{float(price):,.2f}"
    except:
        return str(price)

def format_amount(amount):
    """Форматирует количество"""
    try:
        return f"{float(amount):.8f}".rstrip('0').rstrip('.')
    except:
        return str(amount)

async def test_bingx_extended():
    print("\n" + "="*90)
    print("🔥 BingX РАСШИРЕННЫЙ ТЕСТ: Последние 90 дней (MSK TIME) 🔥".center(90))
    print("="*90 + "\n")
    print("📋 Note: BingX позволяет запрашивать историю до 90 дней.\n")
    
    bingx_key = os.getenv("BINGX_API_KEY")
    bingx_secret = os.getenv("BINGX_SECRET")
    
    if not bingx_key:
        print("❌ ERROR: BingX API keys not found!")
        return
    
    print(f"✅ BingX API Key loaded\n")
    
    bingx = ccxt.bingx({
        'apiKey': bingx_key,
        'secret': bingx_secret,
        'enableRateLimit': True
    })
    
    try:
        # Запрос ордеров за последние 90 дней
        since = int((datetime.now() - timedelta(days=90)).timestamp() * 1000)
        
        print(f"🔍 Fetching canceled and closed orders (last 90 days, limit=100)...")
        print(f"   Note: Используем fetch_canceled_and_closed_orders() для всех ордеров.\n")
        
        # ИСПРАВЛЕНО: используем fetch_canceled_and_closed_orders() вместо fetch_closed_orders()
        all_orders = await bingx.fetch_canceled_and_closed_orders(SYMBOL, since=since, limit=100)
        
        print(f"✅ Total orders returned: {len(all_orders)}\n")
        
        # Сортируем ордера по дате (новые сверху)
        all_orders.sort(key=lambda o: o.get('timestamp', 0), reverse=True)
        
        # Разделяем на лимитные и рыночные (ВСЕ, включая отменённые)
        limit_orders = [o for o in all_orders if o.get('type') == 'limit']
        market_orders = [o for o in all_orders if o.get('type') == 'market']
        
        # ========== ЛИМИТНЫЕ ОРДЕРА ==========
        print("=" * 90)
        print(f"📊 LIMIT ORDERS (показаны первые 8 из {len(limit_orders)})".center(90))
        print("=" * 90)
        if len(limit_orders) == 0:
            print("⚠️  Нет лимитных ордеров в истории.")
        print()
        
        for i, order in enumerate(limit_orders[:8], 1):
            msk_time = utc_to_msk(order['datetime'])
            side = order['side']
            side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
            price = format_price(order.get('price', 'N/A'))
            filled = format_amount(order.get('filled', 0))
            amount = format_amount(order['amount'])
            status = order['status']
            
            # Определяем статус с эмоджи
            if status == 'canceled':
                status_emoji = "❌"
                status_text = "canceled"
            elif status == 'closed':
                status_emoji = "✅"
                status_text = "closed"
            else:
                status_emoji = "⏳"
                status_text = status
            
            print(f"{i:2d}. 🕐 {msk_time}")
            print(f"    {side_emoji} Side: {side.upper():4s} | 💰 Price: ${price:>12} USDC")
            print(f"    📦 Filled: {filled}/{amount} BTC | {status_emoji} Status: {status_text}")
            print()
        
        # ========== РЫНОЧНЫЕ ОРДЕРА ==========
        print("=" * 90)
        print(f"⚡ MARKET ORDERS (показаны первые 8 из {len(market_orders)})".center(90))
        print("=" * 90)
        if len(market_orders) == 0:
            print("⚠️  Нет рыночных ордеров в истории.")
        print()
        
        for i, order in enumerate(market_orders[:8], 1):
            msk_time = utc_to_msk(order['datetime'])
            side = order['side']
            side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
            avg_price = format_price(order.get('average', 'N/A'))
            filled = format_amount(order.get('filled', 0))
            amount = format_amount(order['amount'])
            status = order['status']
            
            # Определяем статус с эмоджи
            if status == 'canceled':
                status_emoji = "❌"
                status_text = "canceled"
            elif status == 'closed':
                status_emoji = "✅"
                status_text = "closed"
            else:
                status_emoji = "⏳"
                status_text = status
            
            print(f"{i:2d}. 🕐 {msk_time}")
            print(f"    {side_emoji} Side: {side.upper():4s} | 💰 Avg Price: ${avg_price:>12} USDC")
            print(f"    📦 Filled: {filled}/{amount} BTC | {status_emoji} Status: {status_text}")
            print()
        
        # ========== ИТОГОВАЯ СВОДКА ==========
        print("=" * 90)
        print("🎯 ИТОГОВАЯ СВОДКА".center(90))
        print("=" * 90 + "\n")
        
        # Подсчёт исполненных и отменённых
        executed_limit = len([o for o in limit_orders if o.get('filled', 0) > 0])
        canceled_limit = len([o for o in limit_orders if o['status'] == 'canceled'])
        executed_market = len([o for o in market_orders if o.get('filled', 0) > 0])
        canceled_market = len([o for o in market_orders if o['status'] == 'canceled'])
        
        print(f"📊 Limit orders: {len(limit_orders)} total (✅ {executed_limit} executed, ❌ {canceled_limit} canceled)")
        print(f"⚡ Market orders: {len(market_orders)} total (✅ {executed_market} executed, ❌ {canceled_market} canceled)")
        print(f"\n✅ TEST PASSED")
        print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S MSK')}")
        print("\n" + "=" * 90 + "\n")
        
    except Exception as e:
        print("\n" + "=" * 90)
        print("❌ ОШИБКА".center(90))
        print("=" * 90 + "\n")
        print(f"❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 90 + "\n")
    finally:
        await bingx.close()
        print("🔒 Connection closed\n")

if __name__ == '__main__':
    asyncio.run(test_bingx_extended())
