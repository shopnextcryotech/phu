"""
Финальная стратегия кросс-биржевого арбитража BTC/USDC

Особенности:
- 0% комиссии на BTC/USDC (maker/taker)
- Limit order на первой бирже (по аску) + Market на второй
- Проверка глубины стакана перед исполнением
- Fallback механизм при ошибках
- Защита от неожиданных проскальзываний
- One-shot режим: 1 круг арбитража → стоп
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class Direction(Enum):
    """Направление арбитража"""
    MEXC_TO_BINGX = "mexc_to_bingx"
    BINGX_TO_MEXC = "bingx_to_mexc"


class ExecutionStatus(Enum):
    """Статус исполнения"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class OrderBookLevel:
    """Уровень в стакане"""
    price: Decimal
    amount: Decimal


@dataclass
class ArbitrageResult:
    """Результат арбитражной сделки"""
    status: ExecutionStatus
    direction: Direction
    buy_exchange: str
    sell_exchange: str
    volume_btc: Decimal
    buy_price: Decimal
    sell_price: Decimal
    expected_profit: Decimal
    actual_profit: Optional[Decimal]
    buy_order_id: Optional[str]
    sell_order_id: Optional[str]
    error_message: Optional[str]
    timestamp: datetime
    
    def __str__(self) -> str:
        status_emoji = {
            ExecutionStatus.SUCCESS: "✅",
            ExecutionStatus.PARTIAL: "⚠️",
            ExecutionStatus.FAILED: "❌",
            ExecutionStatus.ABORTED: "🛑"
        }
        
        return (
            f"{status_emoji[self.status]} Arbitrage {self.direction.value}\n"
            f"  Buy:  {self.volume_btc} BTC @ {self.buy_exchange} for {self.buy_price} USDC\n"
            f"  Sell: {self.volume_btc} BTC @ {self.sell_exchange} for {self.sell_price} USDC\n"
            f"  Expected profit: ${self.expected_profit:.2f}\n"
            f"  Actual profit: ${self.actual_profit:.2f if self.actual_profit else 'N/A'}\n"
            f"  Status: {self.status.value}"
        )


class FinalizedArbitrageStrategy:
    """
    Финальная стратегия арбитража BTC/USDC между MEXC и BingX
    
    Параметры:
    - Комиссии: 0% (maker/taker на BTC/USDC)
    - Исполнение: Limit на первой бирже + Market на второй
    - Режим: One-shot (1 успешный круг → стоп)
    
    Usage:
        strategy = FinalizedArbitrageStrategy(
            mexc_connector=mexc,
            bingx_connector=bingx,
            symbol="BTC/USDC",
            min_profit_usd=Decimal("1.0"),
            target_volume_btc=Decimal("0.01")
        )
        
        result = await strategy.execute_one_shot()
    """
    
    def __init__(
        self,
        mexc_connector,
        bingx_connector,
        symbol: str = "BTC/USDC",
        min_profit_usd: Decimal = Decimal("1.0"),
        target_volume_btc: Decimal = Decimal("0.01"),
        max_volume_btc: Decimal = Decimal("0.1"),
        min_orderbook_depth: int = 3,
        max_slippage_bps: Decimal = Decimal("10"),
        order_timeout_sec: int = 30,
        dry_run: bool = True
    ):
        self.mexc = mexc_connector
        self.bingx = bingx_connector
        self.symbol = symbol
        
        # Параметры сделки
        self.min_profit_usd = min_profit_usd
        self.target_volume_btc = target_volume_btc
        self.max_volume_btc = max_volume_btc
        
        # Параметры безопасности
        self.min_orderbook_depth = min_orderbook_depth
        self.max_slippage_bps = max_slippage_bps
        self.order_timeout = order_timeout_sec
        
        # Режим
        self.dry_run = dry_run
        
        # Комиссии (0% для BTC/USDC)
        self.mexc_maker_fee = Decimal("0.0000")
        self.mexc_taker_fee = Decimal("0.0000")
        self.bingx_maker_fee = Decimal("0.0000")
        self.bingx_taker_fee = Decimal("0.0000")
        
        logger.info(
            f"🚀 Стратегия инициализирована:\n"
            f"  Symbol: {symbol}\n"
            f"  Min profit: ${min_profit_usd}\n"
            f"  Target volume: {target_volume_btc} BTC\n"
            f"  Max slippage: {max_slippage_bps} bps\n"
            f"  Mode: {'DRY_RUN' if dry_run else 'LIVE'}\n"
            f"  Fees: 0% (maker/taker)"
        )
    
    async def execute_one_shot(self) -> Optional[ArbitrageResult]:
        """
        Выполнить ОДИН цикл арбитража и остановиться
        
        Returns:
            ArbitrageResult если успешно, None если не найдена возможность
        """
        logger.info("\n" + "="*60)
        logger.info("🎯 Запуск ONE-SHOT арбитража")
        logger.info("="*60)
        
        try:
            # Шаг 1: Получить orderbooks
            logger.info("📊 Шаг 1/5: Получение orderbooks...")
            mexc_book, bingx_book = await self._fetch_orderbooks()
            
            if not mexc_book or not bingx_book:
                logger.error("❌ Не удалось получить orderbooks")
                return None
            
            # Шаг 2: Найти лучшую возможность
            logger.info("🔍 Шаг 2/5: Поиск арбитражной возможности...")
            opportunity = self._find_best_opportunity(
                mexc_book=mexc_book,
                bingx_book=bingx_book
            )
            
            if not opportunity:
                logger.warning("⚠️ Арбитражная возможность не найдена")
                return None
            
            direction, buy_exchange, sell_exchange, buy_price, sell_price, volume = opportunity
            
            logger.info(
                f"✨ Найдена возможность:\n"
                f"  Направление: {direction.value}\n"
                f"  Купить:  {volume} BTC @ {buy_exchange} за {buy_price} USDC\n"
                f"  Продать: {volume} BTC @ {sell_exchange} за {sell_price} USDC\n"
                f"  Спред: {sell_price - buy_price} USDC\n"
                f"  Ожидаемая прибыль: ${(sell_price - buy_price) * volume:.2f}"
            )
            
            # Шаг 3: Проверить глубину стакана
            logger.info("📏 Шаг 3/5: Проверка глубины стакана...")
            if not self._validate_orderbook_depth(mexc_book, bingx_book, direction, volume):
                logger.error("❌ Недостаточная глубина стакана")
                return None
            
            logger.info("✅ Глубина стакана достаточна")
            
            # Шаг 4: Реконфирмация перед исполнением
            logger.info("🔄 Шаг 4/5: Реконфирмация цен...")
            if not await self._reconfirm_opportunity(direction, buy_price, sell_price):
                logger.warning("⚠️ Окно арбитража закрылось при реконфирмации")
                return None
            
            logger.info("✅ Реконфирмация успешна")
            
            # Шаг 5: Исполнение
            logger.info("⚡ Шаг 5/5: Исполнение сделки...")
            result = await self._execute_arbitrage(
                direction=direction,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                volume=volume
            )
            
            # Вывод результата
            logger.info("\n" + "="*60)
            logger.info("📈 РЕЗУЛЬТАТ:")
            logger.info(str(result))
            logger.info("="*60 + "\n")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
            return ArbitrageResult(
                status=ExecutionStatus.FAILED,
                direction=Direction.MEXC_TO_BINGX,
                buy_exchange="unknown",
                sell_exchange="unknown",
                volume_btc=Decimal("0"),
                buy_price=Decimal("0"),
                sell_price=Decimal("0"),
                expected_profit=Decimal("0"),
                actual_profit=None,
                buy_order_id=None,
                sell_order_id=None,
                error_message=str(e),
                timestamp=datetime.now()
            )
    
    async def _fetch_orderbooks(self) -> Tuple[Optional[dict], Optional[dict]]:
        """Получить orderbooks с обеих бирж"""
        try:
            mexc_book, bingx_book = await asyncio.gather(
                self.mexc.fetch_order_book(self.symbol, limit=20),
                self.bingx.fetch_order_book(self.symbol, limit=20),
                return_exceptions=True
            )
            
            if isinstance(mexc_book, Exception):
                logger.error(f"MEXC orderbook error: {mexc_book}")
                return None, None
            
            if isinstance(bingx_book, Exception):
                logger.error(f"BingX orderbook error: {bingx_book}")
                return None, None
            
            return mexc_book, bingx_book
            
        except Exception as e:
            logger.error(f"Ошибка получения orderbooks: {e}")
            return None, None
    
    def _find_best_opportunity(
        self,
        mexc_book: dict,
        bingx_book: dict
    ) -> Optional[Tuple[Direction, str, str, Decimal, Decimal, Decimal]]:
        """
        Найти лучшую арбитражную возможность
        
        Returns:
            (direction, buy_exchange, sell_exchange, buy_price, sell_price, volume)
        """
        
        # Направление 1: MEXC → BingX
        mexc_ask = Decimal(str(mexc_book['asks'][0][0])) if mexc_book['asks'] else None
        bingx_bid = Decimal(str(bingx_book['bids'][0][0])) if bingx_book['bids'] else None
        
        # Направление 2: BingX → MEXC
        bingx_ask = Decimal(str(bingx_book['asks'][0][0])) if bingx_book['asks'] else None
        mexc_bid = Decimal(str(mexc_book['bids'][0][0])) if mexc_book['bids'] else None
        
        if not all([mexc_ask, bingx_bid, bingx_ask, mexc_bid]):
            logger.error("Отсутствуют цены в orderbook")
            return None
        
        # Рассчитать профит для обоих направлений
        profit_mexc_to_bingx = (bingx_bid - mexc_ask) * self.target_volume_btc
        profit_bingx_to_mexc = (mexc_bid - bingx_ask) * self.target_volume_btc
        
        logger.info(
            f"💰 Анализ возможностей:\n"
            f"  MEXC→BingX: buy@{mexc_ask}, sell@{bingx_bid}, profit=${profit_mexc_to_bingx:.2f}\n"
            f"  BingX→MEXC: buy@{bingx_ask}, sell@{mexc_bid}, profit=${profit_bingx_to_mexc:.2f}"
        )
        
        # Выбрать лучшее направление
        if profit_mexc_to_bingx >= self.min_profit_usd and profit_mexc_to_bingx >= profit_bingx_to_mexc:
            return (
                Direction.MEXC_TO_BINGX,
                "mexc",
                "bingx",
                mexc_ask,
                bingx_bid,
                self.target_volume_btc
            )
        elif profit_bingx_to_mexc >= self.min_profit_usd:
            return (
                Direction.BINGX_TO_MEXC,
                "bingx",
                "mexc",
                bingx_ask,
                mexc_bid,
                self.target_volume_btc
            )
        else:
            logger.warning(
                f"Недостаточная прибыль. Минимум: ${self.min_profit_usd}, "
                f"Лучший вариант: ${max(profit_mexc_to_bingx, profit_bingx_to_mexc):.2f}"
            )
            return None
    
    def _validate_orderbook_depth(
        self,
        mexc_book: dict,
        bingx_book: dict,
        direction: Direction,
        volume: Decimal
    ) -> bool:
        """
        Проверить достаточную глубину стакана для исполнения
        
        Требования:
        1. Минимум N уровней в стакане
        2. Суммарный объём >= требуемому объёму
        3. Защита от slippage
        """
        
        if direction == Direction.MEXC_TO_BINGX:
            buy_book = mexc_book['asks']
            sell_book = bingx_book['bids']
        else:
            buy_book = bingx_book['asks']
            sell_book = mexc_book['bids']
        
        # Проверка 1: Минимальное количество уровней
        if len(buy_book) < self.min_orderbook_depth or len(sell_book) < self.min_orderbook_depth:
            logger.error(
                f"Недостаточная глубина: buy={len(buy_book)}, sell={len(sell_book)}, "
                f"требуется минимум {self.min_orderbook_depth}"
            )
            return False
        
        # Проверка 2: Суммарный объём
        total_buy_volume = sum(Decimal(str(level[1])) for level in buy_book[:5])
        total_sell_volume = sum(Decimal(str(level[1])) for level in sell_book[:5])
        
        if total_buy_volume < volume or total_sell_volume < volume:
            logger.error(
                f"Недостаточный объём: buy={total_buy_volume}, sell={total_sell_volume}, "
                f"требуется {volume}"
            )
            return False
        
        # Проверка 3: Защита от slippage
        buy_price_first = Decimal(str(buy_book[0][0]))
        buy_price_third = Decimal(str(buy_book[2][0])) if len(buy_book) > 2 else buy_price_first
        
        slippage_bps = ((buy_price_third - buy_price_first) / buy_price_first) * Decimal("10000")
        
        if slippage_bps > self.max_slippage_bps:
            logger.error(
                f"Слишком большой slippage: {slippage_bps:.2f} bps, "
                f"максимум {self.max_slippage_bps} bps"
            )
            return False
        
        logger.info(
            f"✅ Валидация стакана:\n"
            f"  Глубина: buy={len(buy_book)}, sell={len(sell_book)}\n"
            f"  Объём: buy={total_buy_volume:.4f}, sell={total_sell_volume:.4f}\n"
            f"  Slippage: {slippage_bps:.2f} bps"
        )
        
        return True
    
    async def _reconfirm_opportunity(
        self,
        direction: Direction,
        initial_buy_price: Decimal,
        initial_sell_price: Decimal
    ) -> bool:
        """
        Реконфирмация возможности перед исполнением
        
        Защита от изменения цен между анализом и исполнением
        """
        
        try:
            # Получить свежие orderbooks
            mexc_book, bingx_book = await self._fetch_orderbooks()
            
            if not mexc_book or not bingx_book:
                return False
            
            # Проверить текущие цены
            if direction == Direction.MEXC_TO_BINGX:
                current_buy = Decimal(str(mexc_book['asks'][0][0]))
                current_sell = Decimal(str(bingx_book['bids'][0][0]))
            else:
                current_buy = Decimal(str(bingx_book['asks'][0][0]))
                current_sell = Decimal(str(mexc_book['bids'][0][0]))
            
            # Проверка: окно всё ещё открыто?
            if current_sell <= current_buy:
                logger.warning(
                    f"Окно закрылось: sell={current_sell} <= buy={current_buy}"
                )
                return False
            
            # Проверка: цены не ухудшились значительно?
            buy_change = abs(current_buy - initial_buy_price) / initial_buy_price * Decimal("10000")
            sell_change = abs(current_sell - initial_sell_price) / initial_sell_price * Decimal("10000")
            
            max_price_change_bps = Decimal("20")  # 0.20%
            
            if buy_change > max_price_change_bps or sell_change > max_price_change_bps:
                logger.warning(
                    f"Слишком большое изменение цен: "
                    f"buy={buy_change:.2f} bps, sell={sell_change:.2f} bps"
                )
                return False
            
            logger.info(
                f"✅ Реконфирмация OK:\n"
                f"  Buy: {initial_buy_price} → {current_buy} (Δ{buy_change:.2f} bps)\n"
                f"  Sell: {initial_sell_price} → {current_sell} (Δ{sell_change:.2f} bps)"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка реконфирмации: {e}")
            return False
    
    async def _execute_arbitrage(
        self,
        direction: Direction,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: Decimal,
        sell_price: Decimal,
        volume: Decimal
    ) -> ArbitrageResult:
        """
        Исполнить арбитражную сделку
        
        Логика:
        1. Limit order на бирже покупки (по аску)
        2. Market order на бирже продажи (одновременно)
        3. Fallback при ошибках
        """
        
        buy_connector = self.mexc if buy_exchange == "mexc" else self.bingx
        sell_connector = self.bingx if sell_exchange == "bingx" else self.mexc
        
        expected_profit = (sell_price - buy_price) * volume
        
        # DRY RUN режим
        if self.dry_run:
            logger.info(
                f"[DRY_RUN] Симуляция исполнения:\n"
                f"  Buy:  {volume} BTC @ {buy_exchange} limit {buy_price}\n"
                f"  Sell: {volume} BTC @ {sell_exchange} market\n"
                f"  Expected profit: ${expected_profit:.2f}"
            )
            
            await asyncio.sleep(1)  # Имитация задержки
            
            return ArbitrageResult(
                status=ExecutionStatus.SUCCESS,
                direction=direction,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                volume_btc=volume,
                buy_price=buy_price,
                sell_price=sell_price,
                expected_profit=expected_profit,
                actual_profit=expected_profit,  # В dry_run = expected
                buy_order_id="DRY_RUN_BUY",
                sell_order_id="DRY_RUN_SELL",
                error_message=None,
                timestamp=datetime.now()
            )
        
        # LIVE исполнение
        buy_order_id = None
        sell_order_id = None
        actual_buy_price = None
        actual_sell_price = None
        
        try:
            # Одновременное размещение ордеров
            logger.info("⚡ Размещение ордеров одновременно...")
            
            buy_result, sell_result = await asyncio.gather(
                buy_connector.create_limit_buy_order(
                    self.symbol,
                    float(volume),
                    float(buy_price)
                ),
                sell_connector.create_market_sell_order(
                    self.symbol,
                    float(volume)
                ),
                return_exceptions=True
            )
            
            # Проверка результатов
            if isinstance(buy_result, Exception):
                raise Exception(f"Buy order failed: {buy_result}")
            
            if isinstance(sell_result, Exception):
                # FALLBACK: отменить buy order
                logger.error(f"❌ Sell order failed: {sell_result}")
                await self._fallback_cancel_order(buy_connector, buy_result.get('id'))
                raise Exception(f"Sell order failed, buy order cancelled")
            
            buy_order_id = buy_result.get('id')
            sell_order_id = sell_result.get('id')
            
            logger.info(
                f"✅ Ордера размещены:\n"
                f"  Buy ID: {buy_order_id}\n"
                f"  Sell ID: {sell_order_id}"
            )
            
            # Ожидание исполнения
            logger.info("⏳ Ожидание исполнения...")
            
            buy_filled, sell_filled = await asyncio.gather(
                self._wait_for_fill(buy_connector, buy_order_id, self.symbol),
                self._wait_for_fill(sell_connector, sell_order_id, self.symbol)
            )
            
            if not buy_filled or not sell_filled:
                raise Exception("Не все ордера исполнены")
            
            # Получить фактические цены исполнения
            actual_buy_price = Decimal(str(buy_filled.get('average', buy_price)))
            actual_sell_price = Decimal(str(sell_filled.get('average', sell_price)))
            actual_profit = (actual_sell_price - actual_buy_price) * volume
            
            logger.info(
                f"✅ Исполнение завершено:\n"
                f"  Buy price: {actual_buy_price}\n"
                f"  Sell price: {actual_sell_price}\n"
                f"  Actual profit: ${actual_profit:.2f}"
            )
            
            return ArbitrageResult(
                status=ExecutionStatus.SUCCESS,
                direction=direction,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                volume_btc=volume,
                buy_price=actual_buy_price,
                sell_price=actual_sell_price,
                expected_profit=expected_profit,
                actual_profit=actual_profit,
                buy_order_id=buy_order_id,
                sell_order_id=sell_order_id,
                error_message=None,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка исполнения: {e}")
            
            return ArbitrageResult(
                status=ExecutionStatus.FAILED,
                direction=direction,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                volume_btc=volume,
                buy_price=buy_price,
                sell_price=sell_price,
                expected_profit=expected_profit,
                actual_profit=None,
                buy_order_id=buy_order_id,
                sell_order_id=sell_order_id,
                error_message=str(e),
                timestamp=datetime.now()
            )
    
    async def _wait_for_fill(self, connector, order_id: str, symbol: str, timeout: int = 30) -> Optional[dict]:
        """Ожидание исполнения ордера"""
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            try:
                order = await connector.fetch_order(order_id, symbol)
                
                if order['status'] == 'closed':
                    return order
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка проверки статуса ордера: {e}")
                break
        
        logger.error(f"Timeout: ордер {order_id} не исполнен за {timeout} сек")
        return None
    
    async def _fallback_cancel_order(self, connector, order_id: str):
        """Fallback: отменить ордер при ошибке"""
        try:
            logger.warning(f"🛑 FALLBACK: Отмена ордера {order_id}...")
            await connector.cancel_order(order_id, self.symbol)
            logger.info(f"✅ Ордер {order_id} отменён")
        except Exception as e:
            logger.error(f"❌ Не удалось отменить ордер: {e}")


if __name__ == "__main__":
    # Пример использования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Для теста нужны реальные коннекторы MEXC и BingX
    print("✅ Финальная стратегия загружена и готова к использованию!")
    print("\nОсобенности:")
    print("  • 0% комиссии на BTC/USDC")
    print("  • Limit на первой бирже + Market на второй")
    print("  • Проверка глубины стакана")
    print("  • Fallback механизм")
    print("  • One-shot: 1 успешный круг → стоп")
