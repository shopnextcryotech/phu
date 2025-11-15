"""
Проверка балансов MEXC и BingX
Загружает API-ключи из config/.env
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import ccxt.async_support as ccxt

# Загружаем .env из папки config
env_path = Path(__file__).resolve().parents[1] / "config" / ".env"
load_dotenv(env_path)

async def test_balances():
    print("=== ПРОВЕРКА БАЛАНСОВ ===\n")
    
    # Получаем ключи из .env
    mexc_key = os.getenv("MEXC_API_KEY")
    mexc_secret = os.getenv("MEXC_SECRET")
    bingx_key = os.getenv("BINGX_API_KEY")
    bingx_secret = os.getenv("BINGX_SECRET")
    
    # Проверка загрузки ключей
    print(f"MEXC API Key loaded: {'Yes' if mexc_key else 'No'}")
    print(f"BingX API Key loaded: {'Yes' if bingx_key else 'No'}\n")
    
    if not mexc_key or not bingx_key:
        print(f"❌ ERROR: API keys not found!")
        print(f"Looking for .env at: {env_path}")
        return
    
    # Инициализация бирж
    mexc = ccxt.mexc({
        'apiKey': mexc_key,
        'secret': mexc_secret,
        'enableRateLimit': True
    })
    
    bingx = ccxt.bingx({
        'apiKey': bingx_key,
        'secret': bingx_secret,
        'enableRateLimit': True
    })
    
    try:
        # MEXC Balance
        print("--- MEXC Balance ---")
        balance_mexc = await mexc.fetch_balance()
        usdc_mexc = balance_mexc.get('USDC', {})
        btc_mexc = balance_mexc.get('BTC', {})
        print(f"USDC: {usdc_mexc.get('total', 0)} (free: {usdc_mexc.get('free', 0)})")
        print(f"BTC: {btc_mexc.get('total', 0)} (free: {btc_mexc.get('free', 0)})")
        
        # BingX Balance
        print("\n--- BingX Balance ---")
        balance_bingx = await bingx.fetch_balance()
        usdc_bingx = balance_bingx.get('USDC', {})
        btc_bingx = balance_bingx.get('BTC', {})
        print(f"USDC: {usdc_bingx.get('total', 0)} (free: {usdc_bingx.get('free', 0)})")
        print(f"BTC: {btc_bingx.get('total', 0)} (free: {btc_bingx.get('free', 0)})")
        
        print("\n✅ BALANCE CHECK COMPLETED")
        
    finally:
        await mexc.close()
        await bingx.close()

if __name__ == '__main__':
    asyncio.run(test_balances())
