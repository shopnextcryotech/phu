"""
Profit Calculator - Точный расчёт прибыли для арбитражных сделок

Учитывает:
- Комиссии бирж (maker/taker)
- Slippage (проскальзывание цены)
- Комиссии за вывод (опционально)
- Gas fees (для DeFi, опционально)
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradingFees:
    """Комиссии биржи"""
    maker_fee: Decimal  # Maker комиссия (например, 0.001 = 0.1%)
    taker_fee: Decimal  # Taker комиссия
    withdrawal_fee: Decimal = Decimal("0")  # Комиссия за вывод


# Комиссии бирж (по умолчанию)
EXCHANGE_FEES: Dict[str, TradingFees] = {
    "mexc": TradingFees(
        maker_fee=Decimal("0.0000"),  # MEXC: 0.00% maker (VIP 0)
        taker_fee=Decimal("0.0020"),  # MEXC: 0.20% taker
        withdrawal_fee=Decimal("0.0005")  # Примерная комиссия за вывод BTC
    ),
    "bingx": TradingFees(
        maker_fee=Decimal("0.0002"),  # BingX: 0.02% maker
        taker_fee=Decimal("0.0004"),  # BingX: 0.04% taker
        withdrawal_fee=Decimal("0.0005")  # Примерная комиссия за вывод BTC
    ),
    "binance": TradingFees(
        maker_fee=Decimal("0.001"),   # Binance: 0.10% maker
        taker_fee=Decimal("0.001"),   # Binance: 0.10% taker
        withdrawal_fee=Decimal("0.0005")
    )
}


@dataclass
class ProfitBreakdown:
    """Детальный расчёт прибыли"""
    # Основные параметры
    volume_btc: Decimal
    buy_price: Decimal
    sell_price: Decimal
    
    # Валовая прибыль
    gross_profit_usd: Decimal
    
    # Комиссии
    buy_fee_usd: Decimal
    sell_fee_usd: Decimal
    withdrawal_fee_usd: Decimal
    total_fees_usd: Decimal
    
    # Slippage
    slippage_cost_usd: Decimal
    
    # Чистая прибыль
    net_profit_usd: Decimal
    
    # Проценты
    profit_percentage: Decimal
    roi_percentage: Decimal  # Return on Investment
    
    def __str__(self) -> str:
        return (
            f"ProfitBreakdown("
            f"volume={self.volume_btc} BTC, "
            f"gross=${self.gross_profit_usd:.2f}, "
            f"fees=${self.total_fees_usd:.2f}, "
            f"slippage=${self.slippage_cost_usd:.2f}, "
            f"net=${self.net_profit_usd:.2f} ({self.profit_percentage:.2f}%), "
            f"ROI={self.roi_percentage:.2f}%"
            f")"
        )
    
    def is_profitable(self, min_profit: Decimal = Decimal("0")) -> bool:
        """Проверка прибыльности"""
        return self.net_profit_usd >= min_profit


class ProfitCalculator:
    """
    Калькулятор прибыли для арбитражных сделок
    
    Usage:
        calculator = ProfitCalculator()
        
        result = calculator.calculate(
            buy_price=Decimal("100000"),
            sell_price=Decimal("100050"),
            volume_btc=Decimal("0.01"),
            buy_exchange="mexc",
            sell_exchange="bingx"
        )
        
        print(f"Net Profit: ${result.net_profit_usd}")
    """
    
    def __init__(
        self,
        custom_fees: Optional[Dict[str, TradingFees]] = None,
        default_slippage_bps: Decimal = Decimal("5"),  # 0.05%
        include_withdrawal_fees: bool = False
    ):
        """
        Args:
            custom_fees: Пользовательские комиссии бирж
            default_slippage_bps: Slippage по умолчанию в basis points
            include_withdrawal_fees: Учитывать комиссии за вывод
        """
        self.fees = custom_fees if custom_fees else EXCHANGE_FEES
        self.default_slippage_bps = default_slippage_bps
        self.include_withdrawal_fees = include_withdrawal_fees
        
        logger.info(
            f"ProfitCalculator инициализирован: "
            f"slippage={default_slippage_bps} bps, "
            f"withdrawal_fees={include_withdrawal_fees}"
        )
    
    def calculate(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        volume_btc: Decimal,
        buy_exchange: str,
        sell_exchange: str,
        custom_slippage_bps: Optional[Decimal] = None,
        use_maker_orders: bool = True
    ) -> ProfitBreakdown:
        """
        Рассчитать прибыль от арбитражной сделки
        
        Args:
            buy_price: Цена покупки (USDC)
            sell_price: Цена продажи (USDC)
            volume_btc: Объём сделки (BTC)
            buy_exchange: Биржа для покупки
            sell_exchange: Биржа для продажи
            custom_slippage_bps: Пользовательский slippage
            use_maker_orders: Использовать maker ордера (иначе taker)
        
        Returns:
            Детальный расчёт прибыли
        """
        
        # 1. Валовая прибыль (без комиссий)
        buy_cost = buy_price * volume_btc
        sell_revenue = sell_price * volume_btc
        gross_profit = sell_revenue - buy_cost
        
        # 2. Комиссии на покупку
        buy_fees = self.fees.get(buy_exchange.lower(), self.fees["mexc"])
        buy_fee_rate = buy_fees.maker_fee if use_maker_orders else buy_fees.taker_fee
        buy_fee_usd = buy_cost * buy_fee_rate
        
        # 3. Комиссии на продажу
        sell_fees = self.fees.get(sell_exchange.lower(), self.fees["bingx"])
        sell_fee_rate = sell_fees.maker_fee if use_maker_orders else sell_fees.taker_fee
        sell_fee_usd = sell_revenue * sell_fee_rate
        
        # 4. Комиссии за вывод (опционально)
        withdrawal_fee_usd = Decimal("0")
        if self.include_withdrawal_fees:
            # Комиссия в BTC, конвертируем в USD
            withdrawal_fee_btc = buy_fees.withdrawal_fee + sell_fees.withdrawal_fee
            withdrawal_fee_usd = withdrawal_fee_btc * sell_price
        
        # 5. Slippage
        slippage_bps = custom_slippage_bps if custom_slippage_bps else self.default_slippage_bps
        slippage_rate = slippage_bps / Decimal("10000")  # bps в десятичную дробь
        slippage_cost = (buy_cost + sell_revenue) / 2 * slippage_rate
        
        # 6. Общие издержки
        total_fees = buy_fee_usd + sell_fee_usd + withdrawal_fee_usd
        total_costs = total_fees + slippage_cost
        
        # 7. Чистая прибыль
        net_profit = gross_profit - total_costs
        
        # 8. Проценты
        profit_percentage = (net_profit / buy_cost) * Decimal("100") if buy_cost > 0 else Decimal("0")
        roi_percentage = (net_profit / buy_cost) * Decimal("100") if buy_cost > 0 else Decimal("0")
        
        result = ProfitBreakdown(
            volume_btc=volume_btc,
            buy_price=buy_price,
            sell_price=sell_price,
            gross_profit_usd=gross_profit,
            buy_fee_usd=buy_fee_usd,
            sell_fee_usd=sell_fee_usd,
            withdrawal_fee_usd=withdrawal_fee_usd,
            total_fees_usd=total_fees,
            slippage_cost_usd=slippage_cost,
            net_profit_usd=net_profit,
            profit_percentage=profit_percentage,
            roi_percentage=roi_percentage
        )
        
        logger.debug(f"Расчёт прибыли: {result}")
        
        return result
    
    def calculate_breakeven_spread(
        self,
        buy_price: Decimal,
        volume_btc: Decimal,
        buy_exchange: str,
        sell_exchange: str,
        use_maker_orders: bool = True
    ) -> Decimal:
        """
        Рассчитать минимальный спред для безубыточности
        
        Args:
            buy_price: Цена покупки
            volume_btc: Объём
            buy_exchange: Биржа покупки
            sell_exchange: Биржа продажи
            use_maker_orders: Maker или taker
        
        Returns:
            Минимальный спред в USDC
        """
        
        # Получаем комиссии
        buy_fees = self.fees.get(buy_exchange.lower(), self.fees["mexc"])
        sell_fees = self.fees.get(sell_exchange.lower(), self.fees["bingx"])
        
        buy_fee_rate = buy_fees.maker_fee if use_maker_orders else buy_fees.taker_fee
        sell_fee_rate = sell_fees.maker_fee if use_maker_orders else sell_fees.taker_fee
        
        # Общая комиссия
        total_fee_rate = buy_fee_rate + sell_fee_rate
        
        # Slippage
        slippage_rate = self.default_slippage_bps / Decimal("10000")
        
        # Комиссия за вывод
        withdrawal_rate = Decimal("0")
        if self.include_withdrawal_fees:
            withdrawal_fee_btc = buy_fees.withdrawal_fee + sell_fees.withdrawal_fee
            withdrawal_rate = withdrawal_fee_btc / volume_btc if volume_btc > 0 else Decimal("0")
        
        # Общий необходимый спред (в долях от цены)
        breakeven_rate = total_fee_rate + slippage_rate + withdrawal_rate
        
        # Конвертируем в USDC
        breakeven_spread = buy_price * breakeven_rate
        
        return breakeven_spread
    
    def calculate_min_profitable_price(
        self,
        buy_price: Decimal,
        volume_btc: Decimal,
        buy_exchange: str,
        sell_exchange: str,
        min_profit_usd: Decimal,
        use_maker_orders: bool = True
    ) -> Decimal:
        """
        Рассчитать минимальную цену продажи для заданной прибыли
        
        Args:
            buy_price: Цена покупки
            volume_btc: Объём
            buy_exchange: Биржа покупки
            sell_exchange: Биржа продажи
            min_profit_usd: Желаемая прибыль
            use_maker_orders: Maker или taker
        
        Returns:
            Минимальная цена продажи
        """
        
        # Безубыточный спред
        breakeven_spread = self.calculate_breakeven_spread(
            buy_price=buy_price,
            volume_btc=volume_btc,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            use_maker_orders=use_maker_orders
        )
        
        # Дополнительный спред для прибыли
        profit_per_btc = min_profit_usd / volume_btc if volume_btc > 0 else Decimal("0")
        
        # Минимальная цена продажи
        min_sell_price = buy_price + breakeven_spread + profit_per_btc
        
        return min_sell_price
    
    def simulate_profit_range(
        self,
        buy_price: Decimal,
        volume_btc: Decimal,
        buy_exchange: str,
        sell_exchange: str,
        sell_price_min: Decimal,
        sell_price_max: Decimal,
        step: Decimal = Decimal("10")
    ) -> list:
        """
        Симуляция прибыли для диапазона цен продажи
        
        Полезно для визуализации и анализа
        """
        results = []
        
        current_price = sell_price_min
        while current_price <= sell_price_max:
            profit = self.calculate(
                buy_price=buy_price,
                sell_price=current_price,
                volume_btc=volume_btc,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange
            )
            
            results.append({
                "sell_price": current_price,
                "net_profit": profit.net_profit_usd,
                "profit_percentage": profit.profit_percentage
            })
            
            current_price += step
        
        return results


if __name__ == "__main__":
    # Пример использования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    calculator = ProfitCalculator(
        default_slippage_bps=Decimal("5"),
        include_withdrawal_fees=False
    )
    
    # Пример расчёта
    result = calculator.calculate(
        buy_price=Decimal("100000"),
        sell_price=Decimal("100100"),
        volume_btc=Decimal("0.01"),
        buy_exchange="mexc",
        sell_exchange="bingx",
        use_maker_orders=True
    )
    
    print(f"\n✅ Результат расчёта:")
    print(f"   {result}")
    print(f"\n   Валовая прибыль: ${result.gross_profit_usd:.2f}")
    print(f"   Комиссии: ${result.total_fees_usd:.2f}")
    print(f"   Slippage: ${result.slippage_cost_usd:.2f}")
    print(f"   Чистая прибыль: ${result.net_profit_usd:.2f}")
    print(f"   ROI: {result.roi_percentage:.2f}%")
    
    # Безубыточный спред
    breakeven = calculator.calculate_breakeven_spread(
        buy_price=Decimal("100000"),
        volume_btc=Decimal("0.01"),
        buy_exchange="mexc",
        sell_exchange="bingx"
    )
    
    print(f"\n⚖️ Безубыточный спред: ${breakeven:.2f}")
