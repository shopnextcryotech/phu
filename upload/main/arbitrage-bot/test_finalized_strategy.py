#!/usr/bin/env python3
"""
Тестовый скрипт для финальной стратегии арбитража

Запуск:
    python test_finalized_strategy.py
    
Режим:
    DRY_RUN - безопасное тестирование без реальных сделок
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from decimal import Decimal

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

import ccxt.async_support as ccxt
from strategies.finalized_arbitrage_strategy import (
    FinalizedArbitrageStrategy,
    ExecutionStatus
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('arbitrage_test.log')
    ]
)

logger = logging.getLogger(__name__)


def load_config():
    """Загрузить конфигурацию API ключей"""
    
    # Проверяем переменные окружения
    mexc_api_key = os.getenv('ARB_MEXC_API_KEY')
    mexc_api_secret = os.getenv('ARB_MEXC_API_SECRET')
    bingx_api_key = os.getenv('ARB_BINGX_API_KEY')
    bingx_api_secret = os.getenv('ARB_BINGX_API_SECRET')
    
    if not all([mexc_api_key, mexc_api_secret, bingx_api_key, bingx_api_secret]):
        logger.warning(
            "⚠️ API ключи не найдены в переменных окружения!\n"
            "Используется тестовый режим с публичными данными."
        )
        return None, None
    
    return {
        'mexc': {'apiKey': mexc_api_key, 'secret': mexc_api_secret},
        'bingx': {'apiKey': bingx_api_key, 'secret': bingx_api_secret}
    }, True


async def test_strategy():
    """
    Тестирование финальной стратегии
    
    Шаги:
    1. Инициализация коннекторов MEXC и BingX
    2. Создание стратегии с DRY_RUN режимом
    3. Выполнение ONE-SHOT арбитража
    4. Вывод результатов
    """
    
    logger.info("\n" + "="*80)
    logger.info("🚀 ТЕСТИРОВАНИЕ ФИНАЛЬНОЙ СТРАТЕГИИ АРБИТРАЖА")
    logger.info("="*80)
    
    # Загрузка конфигурации
    config, has_credentials = load_config()
    
    # Инициализация коннекторов
    mexc = ccxt.mexc({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    bingx = ccxt.bingx({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    # Если есть API ключи - используем их
    if config:
        mexc.apiKey = config['mexc']['apiKey']
        mexc.secret = config['mexc']['secret']
        bingx.apiKey = config['bingx']['apiKey']
        bingx.secret = config['bingx']['secret']
        logger.info("✅ API ключи загружены")
    else:
        logger.info("ℹ️ Работа в режиме только с публичными данными")
    
    try:
        # Создание стратегии
        logger.info("\n📋 Параметры стратегии:")
        
        strategy = FinalizedArbitrageStrategy(
            mexc_connector=mexc,
            bingx_connector=bingx,
            symbol="BTC/USDC",
            min_profit_usd=Decimal("1.0"),      # Минимум $1 прибыли
            target_volume_btc=Decimal("0.01"),  # 0.01 BTC (~$1000)
            max_volume_btc=Decimal("0.1"),      # Максимум 0.1 BTC
            min_orderbook_depth=3,              # Минимум 3 уровня в стакане
            max_slippage_bps=Decimal("10"),     # Максимум 0.10% slippage
            order_timeout_sec=30,               # 30 сек timeout
            dry_run=True                        # DRY_RUN режим
        )
        
        # Выполнение ONE-SHOT арбитража
        logger.info("\n🎯 Запуск ONE-SHOT арбитража...")
        logger.info("-" * 80)
        
        result = await strategy.execute_one_shot()
        
        # Анализ результатов
        logger.info("\n" + "="*80)
        logger.info("📊 РЕЗУЛЬТАТЫ ТЕСТА")
        logger.info("="*80)
        
        if result is None:
            logger.warning("⚠️ Арбитражная возможность не найдена")
            logger.info("\nВозможные причины:")
            logger.info("  • Недостаточный спред между биржами")
            logger.info("  • Спред < $1.00 (минимальная прибыль)")
            logger.info("  • Недостаточная ликвидность в orderbook")
            logger.info("  • Проблемы с подключением к биржам")
        else:
            if result.status == ExecutionStatus.SUCCESS:
                logger.info("\n✅ ТЕСТ УСПЕШНО ЗАВЕРШЁН!")
                logger.info(f"\n{result}")
                logger.info("\nСтатистика:")
                logger.info(f"  • Направление: {result.direction.value}")
                logger.info(f"  • Объём: {result.volume_btc} BTC")
                logger.info(f"  • Цена покупки: {result.buy_price} USDC")
                logger.info(f"  • Цена продажи: {result.sell_price} USDC")
                logger.info(f"  • Спред: {result.sell_price - result.buy_price} USDC")
                logger.info(f"  • Ожидаемая прибыль: ${result.expected_profit:.2f}")
                logger.info(f"  • Фактическая прибыль: ${result.actual_profit:.2f}")
            else:
                logger.error(f"\n❌ ТЕСТ ЗАВЕРШЁН С ОШИБКОЙ: {result.status.value}")
                if result.error_message:
                    logger.error(f"Ошибка: {result.error_message}")
        
        logger.info("\n" + "="*80)
        logger.info("🏁 Тест завершён. Скрипт остановлен.")
        logger.info("="*80 + "\n")
        
        # Рекомендации
        if result and result.status == ExecutionStatus.SUCCESS:
            logger.info("\n💡 Следующие шаги:")
            logger.info("  1. Проверить логи в arbitrage_test.log")
            logger.info("  2. Убедиться, что параметры стратегии оптимальны")
            logger.info("  3. Для реальной торговли изменить dry_run=False")
            logger.info("  4. Начать с минимальных объёмов (0.001 BTC)")
            logger.info("  5. Постепенно увеличивать объёмы после успешных тестов\n")
        
        return result
        
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}", exc_info=True)
        return None
        
    finally:
        # Закрытие соединений
        await mexc.close()
        await bingx.close()
        logger.info("🔌 Соединения с биржами закрыты")


async def main():
    """Главная функция"""
    try:
        result = await test_strategy()
        
        # Exit code
        if result and result.status == ExecutionStatus.SUCCESS:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\n⏸️ Прервано пользователем")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Проверка версии Python
    if sys.version_info < (3, 10):
        print("❌ Требуется Python 3.10 или выше")
        sys.exit(1)
    
    # Запуск
    asyncio.run(main())
