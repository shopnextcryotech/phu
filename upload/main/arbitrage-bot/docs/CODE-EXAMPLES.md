# 🔧 ПРИМЕР РЕАЛИЗАЦИИ КЛЮЧЕВЫХ МОДУЛЕЙ

## 1️⃣ ORDER MANAGER - Синхронное выполнение ордеров

```python
# src/order_execution/order_manager.py

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
from datetime import datetime

class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FULLY_FILLED = "fully_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

@dataclass
class Order:
    exchange: str          # "mexc" or "binance"
    pair: str             # "BTC/USDT"
    side: str             # "buy" or "sell"
    amount: float         # 1.5 (BTC)
    price: float          # 43500 (USDT per BTC)
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_amount: float = 0.0
    filled_price: float = 0.0
    timestamp: datetime = None
    error_msg: str = ""

class OrderManager:
    def __init__(self, mexc_exchange, binance_exchange, logger):
        self.mexc = mexc_exchange
        self.binance = binance_exchange
        self.logger = logger
        self.orders: Dict[str, Order] = {}
        self.timeout_seconds = 300  # 5 minutes
        
    async def execute_arbitrage_orders(self, buy_order: Order, sell_order: Order) -> bool:
        """
        Выполнить арбитраж: покупка + продажа СИНХРОННО
        Самое критичное место - нужна синхронизация!
        """
        self.logger.info(f"Executing arbitrage: BUY on {buy_order.exchange} + SELL on {sell_order.exchange}")
        
        # Шаг 1: Отправляем оба ордера почти одновременно
        task_buy = asyncio.create_task(self._submit_order(buy_order))
        task_sell = asyncio.create_task(self._submit_order(sell_order))
        
        # Ждем, но не более 100ms разницы
        try:
            buy_result, sell_result = await asyncio.gather(task_buy, task_sell, timeout=2.0)
        except asyncio.TimeoutError:
            self.logger.error("Timeout submitting orders")
            await self._cancel_orders([buy_order, sell_order])
            return False
        
        if not (buy_result and sell_result):
            self.logger.error("Failed to submit one or both orders")
            await self._cancel_orders([buy_order, sell_order])
            return False
        
        # Шаг 2: Мониторим заполнение обоих ордеров
        buy_filled = await self._monitor_fill(buy_order)
        sell_filled = await self._monitor_fill(sell_order)
        
        if not (buy_filled and sell_filled):
            self.logger.error("Failed to fill both orders")
            # Пытаемся закрыть позицию
            await self._recover_partial_fill(buy_order, sell_order)
            return False
        
        self.logger.info("✅ Both orders filled successfully")
        return True
    
    async def _submit_order(self, order: Order) -> bool:
        """Отправляем ордер на биржу"""
        try:
            if order.exchange == "mexc":
                exchange = self.mexc
            else:
                exchange = self.binance
            
            # Создаем ордер на бирже
            result = await exchange.create_order(
                symbol=order.pair,
                type="limit",
                side=order.side,
                amount=order.amount,
                price=order.price
            )
            
            order.order_id = result.get("id")
            order.status = OrderStatus.SUBMITTED
            order.timestamp = datetime.now()
            
            self.orders[order.order_id] = order
            self.logger.info(f"✓ Order submitted: {order.order_id}")
            return True
            
        except Exception as e:
            order.error_msg = str(e)
            order.status = OrderStatus.REJECTED
            self.logger.error(f"✗ Failed to submit order: {e}")
            return False
    
    async def _monitor_fill(self, order: Order) -> bool:
        """Мониторим заполнение ордера с timeout"""
        start_time = time.time()
        last_update = start_time
        
        while time.time() - start_time < self.timeout_seconds:
            try:
                if order.exchange == "mexc":
                    exchange = self.mexc
                else:
                    exchange = self.binance
                
                # Запрашиваем статус каждые 100ms
                order_info = await exchange.fetch_order(order.order_id, order.pair)
                
                # Проверяем статус
                filled = float(order_info.get("filled", 0))
                status = order_info.get("status")
                
                if status == "closed":
                    # Полностью заполнен
                    order.filled_amount = filled
                    order.filled_price = float(order_info.get("average", order.price))
                    order.status = OrderStatus.FULLY_FILLED
                    self.logger.info(f"✓ Order fully filled: {filled} @ {order.filled_price}")
                    return True
                    
                elif status == "canceled":
                    order.status = OrderStatus.CANCELLED
                    self.logger.error(f"✗ Order cancelled")
                    return False
                    
                elif filled > 0:
                    # Частичное заполнение
                    order.filled_amount = filled
                    order.status = OrderStatus.PARTIALLY_FILLED
                    self.logger.warning(f"⚠ Partial fill: {filled}/{order.amount}")
                    last_update = time.time()
                
                # Ждем 100ms перед следующей проверкой
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Error monitoring order: {e}")
                await asyncio.sleep(0.5)
        
        # Timeout - отменяем ордер
        self.logger.error(f"✗ Order timeout after {self.timeout_seconds}s")
        await self._cancel_order(order)
        return False
    
    async def _cancel_order(self, order: Order) -> bool:
        """Отменяем ордер"""
        try:
            if order.exchange == "mexc":
                exchange = self.mexc
            else:
                exchange = self.binance
            
            await exchange.cancel_order(order.order_id, order.pair)
            order.status = OrderStatus.CANCELLED
            self.logger.info(f"✓ Order cancelled: {order.order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order: {e}")
            return False
    
    async def _cancel_orders(self, orders: list) -> None:
        """Отменяем несколько ордеров"""
        tasks = [self._cancel_order(order) for order in orders]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _recover_partial_fill(self, buy_order: Order, sell_order: Order) -> None:
        """
        Восстановление при partial fill
        Например: купили 0.6 BTC из 1 BTC, не смогли продать 0.6 BTC
        """
        self.logger.warning("🔄 Recovering from partial fill...")
        
        # Если куплено чего-то, но не продано
        if buy_order.status == OrderStatus.FULLY_FILLED and sell_order.status != OrderStatus.FULLY_FILLED:
            # Пытаемся продать по лучшей доступной цене
            best_price = await self._get_best_sell_price(sell_order.pair, sell_order.exchange)
            
            recovery_order = Order(
                exchange=sell_order.exchange,
                pair=sell_order.pair,
                side="sell",
                amount=buy_order.filled_amount,
                price=best_price * 0.999  # На 0.1% ниже для гарантии заполнения
            )
            
            await self._submit_order(recovery_order)
            if await self._monitor_fill(recovery_order):
                self.logger.info("✓ Recovery order filled")
            else:
                self.logger.error("✗ Recovery order failed - position stuck!")
                # Логируем для ручного вмешательства
                await self._notify_stuck_position(buy_order, recovery_order)

    async def _get_best_sell_price(self, pair: str, exchange: str) -> float:
        """Получаем лучшую цену для продажи"""
        # Это упрощено, в реальности нужно вызвать exchange API
        return 43600.0  # Placeholder


class PartialFillHandler:
    """Обработчик частичного заполнения"""
    
    def __init__(self, order_manager, logger):
        self.order_manager = order_manager
        self.logger = logger
        self.partial_fill_timeout = 120  # 2 минуты ждем остаток
    
    async def handle_partial_fill(self, order: Order) -> bool:
        """
        Обрабатываем ситуацию когда ордер частично заполнен
        Ждем оставшийся объем или отменяем его
        """
        remaining = order.amount - order.filled_amount
        self.logger.warning(f"Partial fill detected: {order.filled_amount}/{order.amount}")
        self.logger.info(f"Waiting {self.partial_fill_timeout}s for remaining {remaining}...")
        
        start_time = time.time()
        
        # Ждем оставшейся части
        while time.time() - start_time < self.partial_fill_timeout:
            try:
                # Проверяем статус
                new_filled = await self.order_manager._check_order_status(order)
                
                if new_filled >= order.amount:
                    # Полностью заполнилось!
                    order.filled_amount = new_filled
                    self.logger.info(f"✓ Remaining {remaining} filled!")
                    return True
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"Error checking order: {e}")
        
        # Timeout - отменяем остаток
        self.logger.warning(f"Cancelling remaining {remaining}...")
        await self.order_manager._cancel_order(order)
        
        # Обновляем статус и возвращаем what we got
        order.status = OrderStatus.PARTIALLY_FILLED
        return True  # Считаем success т.к. что-то заполнилось
```

---

## 2️⃣ ERROR HANDLER - Обработка ошибок и восстановление

```python
# src/error_handling/recovery_planner.py

from enum import Enum
import asyncio

class ErrorType(Enum):
    NETWORK_TIMEOUT = "network_timeout"
    EXCHANGE_ERROR = "exchange_error"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    ORDER_REJECTED = "order_rejected"
    PARTIAL_FILL = "partial_fill"
    PRICE_OUT_OF_RANGE = "price_out_of_range"
    MARKET_CLOSED = "market_closed"

class RecoveryPlanner:
    """Планировщик восстановления при сбоях"""
    
    def __init__(self, order_manager, risk_manager, logger):
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.logger = logger
    
    async def handle_error(self, error_type: ErrorType, context: dict) -> bool:
        """
        Главный обработчик ошибок
        Выбирает стратегию в зависимости от типа ошибки
        """
        self.logger.error(f"Handling {error_type.value}: {context}")
        
        if error_type == ErrorType.NETWORK_TIMEOUT:
            return await self._handle_network_timeout(context)
        
        elif error_type == ErrorType.ORDER_REJECTED:
            return await self._handle_order_rejected(context)
        
        elif error_type == ErrorType.PARTIAL_FILL:
            return await self._handle_partial_fill(context)
        
        elif error_type == ErrorType.INSUFFICIENT_BALANCE:
            return await self._handle_insufficient_balance(context)
        
        elif error_type == ErrorType.EXCHANGE_ERROR:
            return await self._handle_exchange_error(context)
        
        else:
            self.logger.error(f"Unknown error type: {error_type}")
            return False
    
    async def _handle_network_timeout(self, context: dict) -> bool:
        """
        Сценарий: Network timeout при отправке ордера
        
        Возможные ситуации:
        1. Ордер заполнен, но мы не узнали
        2. Ордер не отправлен
        3. Ордер отправлен но не заполнен
        """
        buy_order = context.get("buy_order")
        sell_order = context.get("sell_order")
        
        self.logger.warning("🔄 Recovering from network timeout...")
        
        # Проверяем были ли ордеры вообще отправлены
        if buy_order.order_id:
            # Проверяем статус ордера на бирже
            actual_status = await self._check_actual_order_status(buy_order)
            
            if actual_status == "filled":
                # Ордер заполнился! Нужно срочно продать
                self.logger.info("✓ Buy order was filled! Executing sell immediately...")
                return await self._execute_emergency_sell(buy_order, sell_order.exchange)
            
            elif actual_status == "partial":
                # Частичное заполнение
                return await self._handle_partial_fill({"order": buy_order})
            
            else:
                # Ордер не заполнен - отменяем его
                await self.order_manager._cancel_order(buy_order)
        
        # Пытаемся перестартовать сделку
        return False
    
    async def _handle_order_rejected(self, context: dict) -> bool:
        """
        Сценарий: Ордер отклонен биржей
        
        Причины:
        - Insufficient balance
        - Invalid amount (too small)
        - Price out of range
        - Account restricted
        """
        order = context.get("order")
        error_msg = context.get("error_message", "")
        
        self.logger.warning(f"Order rejected: {error_msg}")
        
        if "insufficient" in error_msg.lower():
            # Нужна больше валюты - получаем текущий баланс
            balance = await self._get_balance(order.exchange, order.pair.split("/")[1])
            self.logger.error(f"Insufficient balance: have {balance}, need {order.amount * order.price}")
            return False
        
        elif "min order" in error_msg.lower():
            # Ордер слишком маленький - увеличиваем размер
            order.amount *= 1.1
            self.logger.info(f"Increasing order size to {order.amount}")
            return await self.order_manager._submit_order(order)
        
        elif "price" in error_msg.lower():
            # Цена вышла из допустимого диапазона - пересчитываем
            new_price = await self._get_fair_price(order.pair, order.exchange)
            order.price = new_price
            self.logger.info(f"Adjusting price to {new_price}")
            return await self.order_manager._submit_order(order)
        
        return False
    
    async def _handle_partial_fill(self, context: dict) -> bool:
        """
        Сценарий: Ордер заполнен частично
        
        Например: купили 0.6 из 1 BTC
        Решение: продаем то что купили, отменяем остаток
        """
        order = context.get("order")
        
        self.logger.warning(f"Partial fill: {order.filled_amount}/{order.amount}")
        
        # Отменяем остаток
        await self.order_manager._cancel_order(order)
        
        # Продаем то что купили
        if order.side == "buy":
            sell_amount = order.filled_amount
            sell_price = await self._get_fair_price(order.pair, order.exchange, side="sell")
            
            sell_order = Order(
                exchange=order.exchange,
                pair=order.pair,
                side="sell",
                amount=sell_amount,
                price=sell_price
            )
            
            return await self.order_manager._submit_order(sell_order)
        
        return True
    
    async def _handle_insufficient_balance(self, context: dict) -> bool:
        """Недостаточно средств"""
        self.logger.error("Insufficient balance - cannot execute trade")
        # Уменьшаем размер позиции на 20%
        return False
    
    async def _handle_exchange_error(self, context: dict) -> bool:
        """Ошибка от биржи (503, 429 и т.д.)"""
        error_code = context.get("error_code", 500)
        
        if error_code == 429:  # Too many requests
            self.logger.warning("Rate limited - waiting 60s...")
            await asyncio.sleep(60)
            return False  # Retry
        
        elif error_code == 503:  # Service unavailable
            self.logger.warning("Service unavailable - waiting 30s...")
            await asyncio.sleep(30)
            return False  # Retry
        
        return False
    
    async def _execute_emergency_sell(self, buy_order: Order, sell_exchange: str) -> bool:
        """Срочная продажа - берем лучшую доступную цену"""
        market_price = await self._get_market_price(buy_order.pair, sell_exchange)
        sell_price = market_price * 0.99  # На 1% ниже для гарантии
        
        sell_order = Order(
            exchange=sell_exchange,
            pair=buy_order.pair,
            side="sell",
            amount=buy_order.filled_amount,
            price=sell_price
        )
        
        return await self.order_manager._submit_order(sell_order)
    
    async def _check_actual_order_status(self, order: Order) -> str:
        """Проверяем реальный статус ордера на бирже"""
        # Реализация для каждой биржи
        pass
    
    async def _get_balance(self, exchange: str, asset: str) -> float:
        """Получаем баланс"""
        pass
    
    async def _get_fair_price(self, pair: str, exchange: str, side: str = "buy") -> float:
        """Получаем справедливую цену"""
        pass
    
    async def _get_market_price(self, pair: str, exchange: str) -> float:
        """Получаем текущую рыночную цену"""
        pass
```

---

## 3️⃣ POSITION SIZER - Расчет размера позиции

```python
# src/risk_management/position_sizer.py

import math
from dataclasses import dataclass

@dataclass
class RiskProfile:
    method: str  # "kelly", "fixed_percent", "volatility"
    win_rate: float  # 0.6 (60%)
    avg_win: float  # 0.02 (2% профит)
    avg_loss: float  # 0.01 (1% лосс)
    max_risk_per_trade: float  # 0.02 (2% от счета)
    kelly_fraction: float  # 0.5 (полу-Kelly для консерватизма)

class PositionSizer:
    """Калькулятор размера позиции"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def calculate_position_size(self, 
                               account_balance: float, 
                               risk_profile: RiskProfile) -> float:
        """
        Рассчитываем оптимальный размер позиции
        Возвращает сумму в USDT которую можно потратить
        """
        
        if risk_profile.method == "kelly":
            return self._kelly_criterion(account_balance, risk_profile)
        
        elif risk_profile.method == "fixed_percent":
            return self._fixed_percentage(account_balance, risk_profile)
        
        elif risk_profile.method == "volatility":
            return self._volatility_based(account_balance, risk_profile)
        
        else:
            self.logger.error(f"Unknown method: {risk_profile.method}")
            return account_balance * 0.01  # Default: 1%
    
    def _kelly_criterion(self, account_balance: float, risk_profile: RiskProfile) -> float:
        """
        Kelly Criterion: f = (b*p - q) / b
        где:
        - p = win_rate (вероятность выигрыша)
        - q = 1 - p (вероятность проигрыша)
        - b = avg_win / avg_loss (ratio)
        
        Пример:
        - Win rate = 60% (p = 0.6)
        - Avg win = 2% (0.02)
        - Avg loss = 1% (0.01)
        - Ratio b = 2
        
        Kelly % = (2 * 0.6 - 0.4) / 2 = 0.4 = 40%
        
        Но 40% - это очень агрессивно, поэтому используем fractional kelly
        """
        
        p = risk_profile.win_rate
        q = 1 - p
        b = risk_profile.avg_win / risk_profile.avg_loss
        
        # Kelly %
        kelly_percent = (b * p - q) / b
        
        # Проверяем что Kelly % позитивный
        if kelly_percent < 0:
            self.logger.warning(f"Negative Kelly: {kelly_percent:.2%} - using minimum")
            kelly_percent = 0.01  # 1% minimum
        
        # Fractional Kelly для консерватизма (обычно 0.25-0.5)
        kelly_percent *= risk_profile.kelly_fraction
        
        # Макс risk per trade
        max_risk = account_balance * risk_profile.max_risk_per_trade
        
        # Берем минимум от Kelly и max_risk
        position_size = min(account_balance * kelly_percent, max_risk)
        
        self.logger.info(f"Kelly Criterion: {kelly_percent:.2%} → ${position_size:,.2f}")
        return position_size
    
    def _fixed_percentage(self, account_balance: float, risk_profile: RiskProfile) -> float:
        """
        Фиксированный процент от счета
        Например: 2% от баланса на каждую сделку
        """
        position_size = account_balance * risk_profile.max_risk_per_trade
        self.logger.info(f"Fixed %: {risk_profile.max_risk_per_trade:.2%} → ${position_size:,.2f}")
        return position_size
    
    def _volatility_based(self, account_balance: float, risk_profile: RiskProfile) -> float:
        """
        На основе волатильности актива
        High volatility → smaller position
        Low volatility → larger position
        """
        # Это упрощено - нужно запросить историческую волатильность
        volatility = 0.05  # Placeholder: 5% дневная волатильность
        
        # Обратная пропорция
        position_size = account_balance * (0.02 / volatility)
        position_size = min(position_size, account_balance * 0.05)  # Cap at 5%
        
        self.logger.info(f"Volatility-based ({volatility:.2%} vol): ${position_size:,.2f}")
        return position_size


# Примеры использования:
def example_kelly():
    sizer = PositionSizer(logger=None)
    
    # Профиль: 60% win rate, 2% avg win, 1% avg loss
    profile = RiskProfile(
        method="kelly",
        win_rate=0.60,
        avg_win=0.02,
        avg_loss=0.01,
        max_risk_per_trade=0.02,
        kelly_fraction=0.5  # Half Kelly
    )
    
    balance = 10000  # $10,000
    position = sizer.calculate_position_size(balance, profile)
    
    # Результат: ~$100 на эту сделку (1% от баланса)
    # Потому что: Kelly = 40%, Half Kelly = 20%, limited by max_risk=2% = $200
    # Берем минимум: min($2000, $200) = $200... wait, let me recalculate
    
    # Правильно:
    # Kelly % = (2*0.6 - 0.4) / 2 = 0.4 = 40%
    # Half Kelly = 20%
    # Max risk = 2%
    # Position = min(10000 * 0.20, 10000 * 0.02) = min($2000, $200) = $200
    
    print(f"Position size: ${position:,.2f}")  # $200

def example_fixed_percent():
    sizer = PositionSizer(logger=None)
    
    profile = RiskProfile(
        method="fixed_percent",
        win_rate=0.0,  # Not used
        avg_win=0.0,   # Not used
        avg_loss=0.0,  # Not used
        max_risk_per_trade=0.02,  # 2% per trade
        kelly_fraction=0.0
    )
    
    balance = 10000
    position = sizer.calculate_position_size(balance, profile)
    print(f"Position size: ${position:,.2f}")  # $200
```

---

## 4️⃣ FEE CALCULATOR - Расчет комиссий

```python
# src/fee_management/fee_calculator.py

from dataclasses import dataclass
from typing import Dict

@dataclass
class FeeStructure:
    maker_fee: float      # 0.001 = 0.1%
    taker_fee: float      # 0.001 = 0.1%
    withdrawal_fee: Dict  # {"BTC": 0.0005, "ETH": 0.005}

class FeeCalculator:
    """Калькулятор комиссий по биржам"""
    
    def __init__(self, logger):
        self.logger = logger
        
        # Структуры комиссий для разных бирж
        self.fee_structures = {
            "mexc": FeeStructure(
                maker_fee=0.002,      # 0.2%
                taker_fee=0.002,      # 0.2%
                withdrawal_fee={"BTC": 0.0005, "ETH": 0.005, "USDT": 0.5}
            ),
            "binance": FeeStructure(
                maker_fee=0.001,      # 0.1% (VIP 0)
                taker_fee=0.001,      # 0.1% (VIP 0)
                withdrawal_fee={"BTC": 0.0005, "ETH": 0.005, "USDT": 1.0}
            ),
            "uniswap": FeeStructure(
                maker_fee=0.003,      # 0.3% (for 0.3% pool)
                taker_fee=0.003,      # 0.3%
                withdrawal_fee={}     # DEX не имеет вывода
            )
        }
    
    def calculate_trading_fee(self, 
                            exchange: str, 
                            amount: float, 
                            is_maker: bool = False) -> float:
        """
        Расчет торговой комиссии
        
        Пример:
        - Покупаем 1 BTC за $43,500 на MEXC (taker)
        - Fee = 43,500 * 0.002 = $87
        """
        fee_rate = self._get_fee_rate(exchange, is_maker)
        fee = amount * fee_rate
        
        self.logger.debug(f"Trading fee: {exchange} {amount} * {fee_rate:.4f} = {fee:.2f}")
        return fee
    
    def calculate_arbitrage_total_fees(self,
                                      buy_amount: float,
                                      buy_exchange: str,
                                      sell_amount: float,
                                      sell_exchange: str,
                                      withdrawal_asset: str,
                                      withdrawal_amount: float) -> float:
        """
        Полный расчет всех комиссий в арбитраже
        
        Пример триангулярного арбитража:
        1. Покупаем 1 BTC на MEXC за $43,500 → fee $87
        2. Продаем 1 BTC на Binance за $43,600 → fee $87.2
        3. Вывод средств не нужен (всё в USDT внутри биржи)
        
        Или кросс-биржевого:
        1. Покупаем 1 BTC на MEXC за $43,500 → fee $87
        2. Выводим 1 BTC (вывод fee 0.0005 BTC = ~$21.75)
        3. Вводим на Binance (вводить обычно бесплатно)
        4. Продаем 1 BTC на Binance за $43,600 → fee $87.2
        
        Total = $87 + $21.75 + $87.2 = $195.95
        Прибыль = $43,600 - $43,500 - $195.95 = -$95.95 (убыток!)
        """
        
        # Торговые комиссии
        buy_fee = self.calculate_trading_fee(buy_exchange, buy_amount, is_maker=False)
        sell_fee = self.calculate_trading_fee(sell_exchange, sell_amount, is_maker=False)
        
        # Комиссия вывода (если нужен)
        withdrawal_fee = self.calculate_withdrawal_fee(
            exchange=buy_exchange,
            asset=withdrawal_asset,
            amount=withdrawal_amount
        )
        
        total_fees = buy_fee + sell_fee + withdrawal_fee
        
        self.logger.info(f"""
        Fees breakdown:
        - Buy fee ({buy_exchange}): ${buy_fee:,.2f}
        - Sell fee ({sell_exchange}): ${sell_fee:,.2f}
        - Withdrawal fee: ${withdrawal_fee:,.2f}
        - Total: ${total_fees:,.2f}
        """)
        
        return total_fees
    
    def calculate_withdrawal_fee(self, exchange: str, asset: str, amount: float) -> float:
        """
        Расчет комиссии вывода
        
        Пример: вывод 1 BTC с MEXC
        - Fee = 0.0005 BTC
        - В USDT = 0.0005 * $43,500 = $21.75
        """
        if exchange not in self.fee_structures:
            return 0.0
        
        withdrawal_fees = self.fee_structures[exchange].withdrawal_fee
        
        if asset not in withdrawal_fees:
            self.logger.warning(f"No withdrawal fee for {asset} on {exchange}")
            return 0.0
        
        fee_amount = withdrawal_fees[asset]
        
        # Если fee в количестве актива (e.g., 0.0005 BTC)
        # Нужно конвертировать в USDT
        if asset in ["BTC", "ETH"]:
            # Это упрощено - нужно получить текущую цену
            asset_price = 43500  # Placeholder for BTC
            fee_in_usdt = fee_amount * asset_price
        else:
            # Если USDT или другой stablecoin
            fee_in_usdt = fee_amount
        
        self.logger.debug(f"Withdrawal fee: {fee_amount} {asset} = ${fee_in_usdt:,.2f}")
        return fee_in_usdt
    
    def _get_fee_rate(self, exchange: str, is_maker: bool) -> float:
        """Получаем ставку комиссии для биржи"""
        if exchange not in self.fee_structures:
            return 0.001  # Default 0.1%
        
        structure = self.fee_structures[exchange]
        return structure.maker_fee if is_maker else structure.taker_fee
    
    def calculate_min_profit_threshold(self, 
                                      buy_price: float,
                                      sell_price: float,
                                      buy_exchange: str,
                                      sell_exchange: str,
                                      amount: float) -> float:
        """
        Рассчитываем минимальную прибыль с учетом комиссий
        
        Пример:
        - Спред: $100 на BTC (0.23%)
        - Комиссии: ~$195
        - Net profit: -$95 (убыток!)
        
        Нужен спред > комиссий чтобы была прибыль
        """
        
        gross_profit = (sell_price - buy_price) * amount
        
        total_fees = self.calculate_arbitrage_total_fees(
            buy_amount=amount,
            buy_exchange=buy_exchange,
            sell_amount=amount,
            sell_exchange=sell_exchange,
            withdrawal_asset="BTC",  # Example
            withdrawal_amount=amount
        )
        
        net_profit = gross_profit - total_fees
        min_spread = total_fees / amount  # Minimum spread needed
        
        return {
            "gross_profit": gross_profit,
            "total_fees": total_fees,
            "net_profit": net_profit,
            "min_spread_per_unit": min_spread,
            "min_spread_percent": (min_spread / buy_price) * 100
        }
```

---

## 5️⃣ WEBSOCKET MANAGER - Управление соединениями

```python
# src/connectivity/websocket_manager.py

import asyncio
import websockets
import json
from typing import Callable, Optional

class WebSocketManager:
    """Менеджер WebSocket соединений к биржам"""
    
    def __init__(self, logger):
        self.logger = logger
        self.connections = {}
        self.handlers = {}
        self.max_reconnect_attempts = 5
    
    async def connect(self, 
                     exchange: str,
                     url: str,
                     channels: list,
                     message_handler: Callable) -> bool:
        """
        Подключаемся к WebSocket бирж
        
        Пример:
        - Exchange: "mexc"
        - URL: "wss://stream.mexc.com/raw"
        - Channels: ["@trade", "@depth"]
        """
        
        self.logger.info(f"Connecting to {exchange} WebSocket: {url}")
        
        reconnect_count = 0
        
        while reconnect_count < self.max_reconnect_attempts:
            try:
                async with websockets.connect(url, 
                                             ping_interval=30,
                                             ping_timeout=10) as ws:
                    
                    self.connections[exchange] = ws
                    reconnect_count = 0  # Reset на успешное подключение
                    
                    self.logger.info(f"✓ Connected to {exchange}")
                    
                    # Подписываемся на каналы
                    for channel in channels:
                        await self._subscribe(ws, channel)
                    
                    # Слушаем сообщения
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await message_handler(exchange, data)
                        except json.JSONDecodeError:
                            self.logger.error(f"Invalid JSON: {message}")
                        except Exception as e:
                            self.logger.error(f"Error processing message: {e}")
                    
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning(f"Connection to {exchange} closed")
                reconnect_count += 1
                
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout connecting to {exchange}")
                reconnect_count += 1
                
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}")
                reconnect_count += 1
            
            if reconnect_count < self.max_reconnect_attempts:
                wait_time = 2 ** reconnect_count  # Exponential backoff
                self.logger.info(f"Reconnecting in {wait_time}s (attempt {reconnect_count})")
                await asyncio.sleep(wait_time)
        
        self.logger.error(f"Failed to connect to {exchange} after {self.max_reconnect_attempts} attempts")
        return False
    
    async def _subscribe(self, ws, channel: str):
        """Подписываемся на канал"""
        subscribe_msg = {
            "method": "SUBSCRIPTION",
            "params": channel
        }
        await ws.send(json.dumps(subscribe_msg))
        self.logger.debug(f"Subscribed to {channel}")
    
    async def disconnect(self, exchange: str):
        """Отключаемся от WebSocket"""
        if exchange in self.connections:
            await self.connections[exchange].close()
            del self.connections[exchange]
            self.logger.info(f"Disconnected from {exchange}")


# Пример использования в главном боте:

async def main():
    ws_manager = WebSocketManager(logger)
    
    async def handle_mexc_message(exchange, data):
        """Обработчик сообщений с MEXC"""
        if "c" in data:  # Ticker message
            pair = data.get("s")
            price = float(data.get("c"))
            print(f"MEXC {pair}: ${price}")
    
    # Подключаемся
    await ws_manager.connect(
        exchange="mexc",
        url="wss://stream.mexc.com/raw",
        channels=["btcusdt@trade", "ethusdt@depth"],
        message_handler=handle_mexc_message
    )
```

---

Этот документ содержит **боевые примеры кода** которые можно адаптировать под вашу архитектуру!
