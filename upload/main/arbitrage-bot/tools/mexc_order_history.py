"""
💹 MEXC All Operations - Last 5 Days
Все сделки и ордера в одном списке по времени
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import ccxt.async_support as ccxt


def load_env_file(env_path):
    """Прямое чтение .env файла"""
    env_vars = {}
    
    if not Path(env_path).exists():
        print(f"❌ Файл не найден: {env_path}")
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


async def show_all_operations():
    """Показать ВСЕ операции за последние 5 дней"""
    
    env_path = Path(r'C:\AI\GitHub\phu\upload\main\arbitrage-bot\config\.env')
    env_vars = load_env_file(env_path)
    
    api_key = (
        env_vars.get('MEXC_API_KEY', '').strip() or 
        env_vars.get('ARB_MEXC_API_KEY', '').strip()
    )
    api_secret = (
        env_vars.get('MEXC_API_SECRET', '').strip() or 
        env_vars.get('ARB_MEXC_API_SECRET', '').strip()
    )
    
    if not api_key or not api_secret:
        print("\n❌ API ключи не найдены!")
        return
    
    key_display = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else api_key
    
    print(f"✅ Загружено: {env_path}")
    print(f"✅ API Key: {key_display}\n")
    
    exchange = ccxt.mexc({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True
    })
    
    since = int((datetime.now() - timedelta(days=5)).timestamp() * 1000)
    
    print("="*110)
    print("💹 MEXC ALL OPERATIONS - LAST 5 DAYS".center(110))
    print("="*110 + "\n")
    
    try:
        trades = await exchange.fetch_my_trades('BTC/USDC', since=since)
        closed_orders = await exchange.fetch_closed_orders('BTC/USDC', since=since)
        
        all_ops = []
        
        for trade in trades:
            all_ops.append({
                'timestamp': trade['timestamp'],
                'datetime': datetime.fromtimestamp(trade['timestamp']/1000),
                'type': 'TRADE',
                'side': trade['side'],
                'price': trade['price'],
                'amount': trade['amount'],
                'cost': trade['cost'],
                'fee': trade.get('fee', {}).get('cost', 0),
                'status': 'EXECUTED'
            })
        
        for order in closed_orders:
            if order['status'] == 'canceled':
                all_ops.append({
                    'timestamp': order['timestamp'],
                    'datetime': datetime.fromtimestamp(order['timestamp']/1000),
                    'type': order['type'].upper(),
                    'side': order['side'],
                    'price': order.get('price', 0),
                    'amount': order['amount'],
                    'cost': order.get('cost', 0),
                    'fee': 0,
                    'status': 'CANCELED'
                })
        
        all_ops.sort(key=lambda x: x['timestamp'])
        
        if not all_ops:
            print("📭 Нет операций за последние 5 дней\n")
            return
        
        total_volume = 0
        total_fee = 0
        trades_count = 0
        canceled_count = 0
        
        for i, op in enumerate(all_ops, 1):
            dt = op['datetime'].strftime('%Y-%m-%d %H:%M:%S')
            side = "🟢 BUY " if op['side'] == 'buy' else "🔴 SELL"
            status_icon = "✅" if op['status'] == 'EXECUTED' else "🚫"
            
            if op['status'] == 'EXECUTED':
                print(f"[{i:3d}] {dt} | {side} | {status_icon} TRADE  | Price: ${op['price']:>10,.2f} | "
                      f"Amount: {op['amount']:>10.6f} BTC | Cost: ${op['cost']:>10,.2f}")
                total_volume += op['cost']
                total_fee += op['fee']
                trades_count += 1
            else:
                price_str = f"${op['price']:>10,.2f}" if op['price'] else "MARKET".rjust(12)
                print(f"[{i:3d}] {dt} | {side} | {status_icon} {op['type']:6s} | Price: {price_str} | "
                      f"Amount: {op['amount']:>10.6f} BTC | Status: CANCELED")
                canceled_count += 1
        
        print("\n" + "-"*110)
        print(f"📊 TOTAL: {len(all_ops)} operations | "
              f"✅ Executed: {trades_count} (Vol: ${total_volume:,.2f}, Fee: ${total_fee:,.4f}) | "
              f"🚫 Canceled: {canceled_count}")
        print("="*110 + "\n")
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
    finally:
        await exchange.close()


if __name__ == '__main__':
    asyncio.run(show_all_operations())
