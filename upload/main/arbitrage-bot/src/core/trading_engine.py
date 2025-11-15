"""
Trading Engine - Центральный движок для исполнения арбитражных сделок

Основные функции:
- Координация всех компонентов
- Dry-run режим для безопасного тестирования
- Исполнение сделок на биржах
- Мониторинг статуса ордеров
- Управление рисками
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Статус ордера"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ExecutionMode(Enum):
    """Режим исполнения"""
    DRY_RUN = "dry_run"  # Имитация без реальных сделок
    LIVE = "live"  # Реальные сделки


@dataclass
class TradeOrder:
    """Ордер на сделку"""
    exchange: str
    symbol: str
    side: str  # "buy" или "sell"
    order_type: str  # "limit", "market"
    price: Optional[Decimal]
    amount: Decimal
    
    # Статус
    status: OrderStatus = OrderStatus.PENDING
    order_id: Optional[str] = None
    
    # Исполнение
    filled_amount: Decimal = Decimal("0")
    average_price: Optional[Decimal] = None
    
    # Метаданные
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    
    def __str__(self) -> str:
        return (
            f"TradeOrder("
            f"{self.side.upper()} {self.amount} {self.symbol} "
            f"@ {self.exchange} "
            f"price={self.price}, "
            f"type={self.order_type}, "
            f"status={self.status.value}"
            f")"
        )


@dataclass
class ArbitrageExecution:
    """Исполнение арбитражной сделки"""
    opportunity_id: str
    buy_order: TradeOrder
    sell_order: TradeOrder
    expected_profit: Decimal
    actual_profit: Optional[Decimal] = None
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class TradingEngine:
    """
    Центральный движок для исполнения арбитражных сделок
    
    Usage:
        # Dry-run режим (безопасное тестирование)
        engine = TradingEngine(
            mode=ExecutionMode.DRY_RUN,
            mexc_connector=mexc,
            bingx_connector=bingx
        )
        
        # Исполнение арбитража
        result = await engine.execute_arbitrage(opportunity)
    """
    
    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
        mexc_connector=None,
        bingx_connector=None,
        price_aggregator=None,
        opportunity_finder=None,
        profit_calculator=None,
        max_slippage_bps: Decimal = Decimal("10"),
        order_timeout_seconds: int = 30
    ):
        self.mode = mode
        self.mexc = mexc_connector
        self.bingx = bingx_connector
        self.price_aggregator = price_aggregator
        self.opportunity_finder = opportunity_finder
        self.profit_calculator = profit_calculator
        
        # Параметры
        self.max_slippage_bps = max_slippage_bps
        self.order_timeout = order_timeout_seconds
        
        # Статистика
        self.executions: List[ArbitrageExecution] = []
        self.total_profit = Decimal("0")
        self.successful_trades = 0
        self.failed_trades = 0
        
        # Флаг работы
        self._running = False
        
        logger.info(
            f"TradingEngine инициализирован: "
            f"mode={mode.value}, "
            f"max_slippage={max_slippage_bps} bps"
        )
    
    async def start(self):
        """Запуск движка"""
        if self._running:
            logger.warning("Движок уже запущен")
            return
        
        self._running = True
        logger.info("🚀 TradingEngine запущен")
        
        # Запускаем PriceAggregator
        if self.price_aggregator:
            await self.price_aggregator.start()
        
        # Основной цикл
        await self._main_loop()
    
    async def stop(self):
        """Остановка движка"""
        logger.info("⏸️ Остановка TradingEngine...")
        self._running = False
        
        if self.price_aggregator:
            await self.price_aggregator.stop()
        
        # Вывод статистики
        self._print_statistics()
    
    async def _main_loop(self):
        """Основной цикл поиска и исполнения арбитража"""
        
        while self._running:
            try:
                # 1. Получаем orderbook
                mexc_book = self.price_aggregator.get_orderbook("mexc")
                bingx_book = self.price_aggregator.get_orderbook("bingx")
                
                if not mexc_book or not bingx_book:
                    await asyncio.sleep(1)
                    continue
                
                # 2. Ищем возможности
                opportunities = self.opportunity_finder.find_opportunities(
                    mexc_orderbook=mexc_book,
                    bingx_orderbook=bingx_book
                )
                
                if not opportunities:
                    await asyncio.sleep(1)
                    continue
                
                # 3. Выбираем лучшую
                best_opp = self.opportunity_finder.get_best_opportunity(opportunities)
                
                if not best_opp:
                    await asyncio.sleep(1)
                    continue
                
                logger.info(f"✨ Найдена возможность: {best_opp}")
                
                # 4. Исполняем
                result = await self.execute_arbitrage(best_opp)
                
                if result:
                    logger.info(f"✅ Арбитраж исполнен успешно")
                else:
                    logger.warning(f"❌ Арбитраж не удался")
                
                # Пауза перед следующей итерацией
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                await asyncio.sleep(5)
    
    async def execute_arbitrage(self, opportunity) -> bool:
        """
        Исполнить арбитражную сделку
        
        Args:
            opportunity: ArbitrageOpportunity от OpportunityFinder
        
        Returns:
            True если успешно, False если нет
        """
        
        if self.mode == ExecutionMode.DRY_RUN:
            return await self._execute_dry_run(opportunity)
        else:
            return await self._execute_live(opportunity)
    
    async def _execute_dry_run(self, opportunity) -> bool:
        """Имитация исполнения (без реальных сделок)"""
        
        logger.info(
            f"[DRY RUN] Исполнение арбитража:\n"
            f"  Покупка: {opportunity.max_volume_btc} BTC @ {opportunity.buy_exchange} "
            f"\u0437\u0430 {opportunity.buy_price} USDC\n"
            f"  Продажа: {opportunity.max_volume_btc} BTC @ {opportunity.sell_exchange} "
            f"\u0437\u0430 {opportunity.sell_price} USDC\n"
            f"  Ожидаемая прибыль: ${opportunity.net_profit_usd:.2f} "
            f"({opportunity.profit_percentage:.2f}%)"
        )
        
        # Имитируем задержку исполнения
        await asyncio.sleep(0.5)
        
        # Обновляем статистику
        self.successful_trades += 1
        self.total_profit += opportunity.net_profit_usd
        
        logger.info(
            f"✅ [DRY RUN] Сделка выполнена успешно! "
            f"Общая прибыль: ${self.total_profit:.2f}"
        )
        
        return True
    
    async def _execute_live(self, opportunity) -> bool:
        """Реальное исполнение сделки"""
        
        logger.info(f"🚨 [LIVE] Исполнение реальной сделки: {opportunity}")
        
        try:
            # Создаём ордера
            buy_order = TradeOrder(
                exchange=opportunity.buy_exchange,
                symbol=opportunity.symbol,
                side="buy",
                order_type="limit",
                price=opportunity.buy_price,
                amount=opportunity.max_volume_btc
            )
            
            sell_order = TradeOrder(
                exchange=opportunity.sell_exchange,
                symbol=opportunity.symbol,
                side="sell",
                order_type="market",
                price=None,
                amount=opportunity.max_volume_btc
            )
            
            # Выполняем одновременно
            buy_result, sell_result = await asyncio.gather(
                self._execute_order(buy_order),
                self._execute_order(sell_order),
                return_exceptions=True
            )
            
            # Проверяем результат
            if buy_result and sell_result:
                self.successful_trades += 1
                logger.info("✅ [LIVE] Оба ордера исполнены!")
                return True
            else:
                self.failed_trades += 1
                logger.error("❌ [LIVE] Ошибка исполнения одного из ордеров")
                return False
                
        except Exception as e:
            logger.error(f"❌ [LIVE] Критическая ошибка: {e}")
            self.failed_trades += 1
            return False
    
    async def _execute_order(self, order: TradeOrder) -> bool:
        """Исполнить один ордер"""
        
        try:
            # Выбираем коннектор
            connector = self.mexc if order.exchange == "mexc" else self.bingx
            
            if not connector:
                raise ValueError(f"Коннектор для {order.exchange} не найден")
            
            # Размещаем ордер
            if order.order_type == "limit":
                result = await connector.create_limit_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount),
                    price=float(order.price)
                )
            else:  # market
                result = await connector.create_market_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount)
                )
            
            order.order_id = result.get("id")
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.now()
            
            logger.info(f"✅ Ордер размещён: {order}")
            
            # Ожидаем исполнения
            await self._wait_for_order_fill(order, connector)
            
            return order.status == OrderStatus.FILLED
            
        except Exception as e:
            logger.error(f"Ошибка исполнения ордера: {e}")
            order.status = OrderStatus.FAILED
            order.error_message = str(e)
            return False
    
    async def _wait_for_order_fill(self, order: TradeOrder, connector) -> bool:
        """Ожидание исполнения ордера"""
        
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < self.order_timeout:
            try:
                # Проверяем статус
                status_result = await connector.fetch_order(
                    order_id=order.order_id,
                    symbol=order.symbol
                )
                
                if status_result.get("status") == "closed":
                    order.status = OrderStatus.FILLED
                    order.filled_amount = Decimal(str(status_result.get("filled", 0)))
                    order.average_price = Decimal(str(status_result.get("average", 0)))
                    logger.info(f"✅ Ордер исполнен: {order.order_id}")
                    return True
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка проверки статуса: {e}")
                break
        
        logger.warning(f"⏰ Timeout: ордер не исполнен вовремя")
        order.status = OrderStatus.FAILED
        return False
    
    def _print_statistics(self):
        """Вывод статистики"""
        
        logger.info("\n" + "="*60)
        logger.info("📊 Статистика TradingEngine:")
        logger.info(f"  Успешных сделок: {self.successful_trades}")
        logger.info(f"  Неудачных сделок: {self.failed_trades}")
        logger.info(f"  Общая прибыль: ${self.total_profit:.2f}")
        
        if self.successful_trades > 0:
            avg_profit = self.total_profit / self.successful_trades
            logger.info(f"  Средняя прибыль: ${avg_profit:.2f}")
        
        logger.info("="*60 + "\n")


if __name__ == "__main__":
    # Пример использования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    engine = TradingEngine(
        mode=ExecutionMode.DRY_RUN
    )
    
    print("✅ TradingEngine создан и готов к работе!")
    print("   Режим: DRY_RUN (безопасное тестирование)")
