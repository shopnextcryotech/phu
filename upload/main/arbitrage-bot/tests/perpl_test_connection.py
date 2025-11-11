"""
perpl_test_connection.py — тестовый скрипт быстрой проверки соединения c MEXC и BingX через perpl_exchange_connector и perpl_config
"""
import asyncio
from config.perpl_config import load_perpl_settings
from src.exchanges.perpl_exchange_connector import PerplExchangeConnector

async def main():
    settings = load_perpl_settings()

    mexc = PerplExchangeConnector('mexc', {
        'apiKey': settings.mexc.api_key,
        'secret': settings.mexc.api_secret
    })
    bingx = PerplExchangeConnector('bingx', {
        'apiKey': settings.bingx.api_key,
        'secret': settings.bingx.api_secret
    })

    print('--- MEXC ---')
    await mexc.test_connection()
    print(await mexc.fetch_balance())
    print(await mexc.fetch_order_book('BTC/USDC', depth=5))

    print('--- BINGX ---')
    await bingx.test_connection()
    print(await bingx.fetch_balance())
    print(await bingx.fetch_order_book('BTC/USDC', depth=5))

    await mexc.close()
    await bingx.close()

if __name__ == '__main__':
    asyncio.run(main())
