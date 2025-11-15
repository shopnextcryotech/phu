"""
Opportunity Finder - Поиск арбитражных возможностей между биржами

Основные функции:
- Анализ спредов между биржами
- Проверка ликвидности
- Фильтрация по минимальному профиту
- Ранжирование возможностей по привлекательности
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Direction(Enum):
    """Направление арбитража"""
    MEXC_TO_BINGX = "mexc_to_bingx"  # Купить на MEXC, продать на BingX
    BINGX_TO_MEXC = "bingx_to_mexc"  # Купить на BingX, продать на MEXC


@dataclass
class ArbitrageOpportunity:
    """Арбитражная возможность"""
    symbol: str
    direction: Direction
    
    # Биржи
    buy_exchange: str
    sell_exchange: str
    
    # Цены
    buy_price: Decimal
    sell_price: Decimal
    
    # Объём
    max_volume_btc: Decimal
    
    # Профит
    gross_profit_usd: Decimal
    net_profit_usd: Decimal
    profit_percentage: Decimal
    
    # Спред
    spread_usd: Decimal
    spread_bps: Decimal  # basis points (0.01%)
    
    # Метаданные
    timestamp: datetime
    confidence_score: float  # 0.0 - 1.0
    
    def __str__(self) -> str:
        return (
            f"ArbitrageOpportunity("
            f"{self.symbol} "
            f"{self.direction.value}: "
            f"buy@{self.buy_exchange}={self.buy_price}, "
            f"sell@{self.sell_exchange}={self.sell_price}, "
            f"profit=${self.net_profit_usd:.2f} ({self.profit_percentage:.2f}%), "
            f"volume={self.max_volume_btc} BTC, "
            f"confidence={self.confidence_score:.2f}"
            f")"
        )
    
    def is_profitable(self, min_profit_usd: Decimal) -> bool:
        """Проверка прибыльности"""
        return self.net_profit_usd >= min_profit_usd
    
    def is_confident(self, min_confidence: float = 0.7) -> bool:
        """Проверка уверенности"""
        return self.confidence_score >= min_confidence


class OpportunityFinder:
    """
    Поиск и анализ арбитражных возможностей
    
    Usage:
        finder = OpportunityFinder(
            symbol="BTC/USDC",
            min_profit_usd=Decimal("5"),
            min_spread_bps=Decimal("10")
        )
        
        opportunities = finder.find_opportunities(
            mexc_orderbook=mexc_book,
            bingx_orderbook=bingx_book,
            mexc_balance=mexc_bal,
            bingx_balance=bingx_bal
        )
    """
    
    def __init__(
        self,
        symbol: str,
        min_profit_usd: Decimal = Decimal("5"),
        min_spread_bps: Decimal = Decimal("10"),
        min_volume_btc: Decimal = Decimal("0.001"),
        max_volume_btc: Decimal = Decimal("0.1"),
        profit_calculator=None
    ):
        self.symbol = symbol
        self.min_profit_usd = min_profit_usd
        self.min_spread_bps = min_spread_bps
        self.min_volume_btc = min_volume_btc
        self.max_volume_btc = max_volume_btc
        self.profit_calculator = profit_calculator
        
        logger.info(
            f"OpportunityFinder инициализирован: "
            f"min_profit=${min_profit_usd}, min_spread={min_spread_bps} bps"
        )
    
    def find_opportunities(
        self,
        mexc_orderbook,
        bingx_orderbook,
        mexc_balance: Optional[dict] = None,
        bingx_balance: Optional[dict] = None
    ) -> List[ArbitrageOpportunity]:
        """
        Найти все арбитражные возможности
        
        Args:
            mexc_orderbook: OrderBook от MEXC
            bingx_orderbook: OrderBook от BingX
            mexc_balance: Баланс на MEXC {"USDC": ..., "BTC": ...}
            bingx_balance: Баланс на BingX {"USDC": ..., "BTC": ...}
        
        Returns:
            Список арбитражных возможностей
        """
        opportunities = []
        
        if not mexc_orderbook or not bingx_orderbook:
            logger.warning("Не указаны orderbooks")
            return opportunities
        
        # Проверяем направление: MEXC -> BingX
        opp_mexc_to_bingx = self._check_direction(
            buy_exchange="mexc",
            sell_exchange="bingx",
            buy_orderbook=mexc_orderbook,
            sell_orderbook=bingx_orderbook,
            buy_balance=mexc_balance,
            sell_balance=bingx_balance,
            direction=Direction.MEXC_TO_BINGX
        )
        
        if opp_mexc_to_bingx and opp_mexc_to_bingx.is_profitable(self.min_profit_usd):
            opportunities.append(opp_mexc_to_bingx)
            logger.info(f"✅ Найдена возможность: {opp_mexc_to_bingx}")
        
        # Проверяем направление: BingX -> MEXC
        opp_bingx_to_mexc = self._check_direction(
            buy_exchange="bingx",
            sell_exchange="mexc",
            buy_orderbook=bingx_orderbook,
            sell_orderbook=mexc_orderbook,
            buy_balance=bingx_balance,
            sell_balance=mexc_balance,
            direction=Direction.BINGX_TO_MEXC
        )
        
        if opp_bingx_to_mexc and opp_bingx_to_mexc.is_profitable(self.min_profit_usd):
            opportunities.append(opp_bingx_to_mexc)
            logger.info(f"✅ Найдена возможность: {opp_bingx_to_mexc}")
        
        # Сортируем по прибыли (убывание)
        opportunities.sort(key=lambda x: x.net_profit_usd, reverse=True)
        
        return opportunities
    
    def _check_direction(
        self,
        buy_exchange: str,
        sell_exchange: str,
        buy_orderbook,
        sell_orderbook,
        buy_balance: Optional[dict],
        sell_balance: Optional[dict],
        direction: Direction
    ) -> Optional[ArbitrageOpportunity]:
        """Проверка арбитража в одном направлении"""
        
        try:
            # Получаем best bid/ask
            buy_price = buy_orderbook.best_ask
            sell_price = sell_orderbook.best_bid
            
            if not buy_price or not sell_price:
                return None
            
            # Проверяем спред
            spread_usd = sell_price - buy_price
            
            if spread_usd <= 0:
                return None  # Нет положительного спреда
            
            # Спред в basis points
            spread_bps = (spread_usd / buy_price) * Decimal("10000")
            
            if spread_bps < self.min_spread_bps:
                return None  # Спред слишком маленький
            
            # Определяем максимальный объём
            max_volume = self._calculate_max_volume(
                buy_orderbook=buy_orderbook,
                sell_orderbook=sell_orderbook,
                buy_balance=buy_balance,
                sell_balance=sell_balance,
                buy_price=buy_price
            )
            
            if max_volume < self.min_volume_btc:
                return None  # Недостаточная ликвидность
            
            # Рассчитываем прибыль
            if self.profit_calculator:
                profit_result = self.profit_calculator.calculate(
                    buy_price=buy_price,
                    sell_price=sell_price,
                    volume_btc=max_volume,
                    buy_exchange=buy_exchange,
                    sell_exchange=sell_exchange
                )
                
                gross_profit = profit_result.get("gross_profit", Decimal("0"))
                net_profit = profit_result.get("net_profit", Decimal("0"))
            else:
                # Упрощённый расчёт без ProfitCalculator
                gross_profit = spread_usd * max_volume
                net_profit = gross_profit  # Без учёта комиссий
            
            if net_profit < self.min_profit_usd:
                return None
            
            # Процент прибыли
            profit_percentage = (net_profit / (buy_price * max_volume)) * Decimal("100")
            
            # Рассчитываем confidence score
            confidence = self._calculate_confidence(
                spread_bps=spread_bps,
                volume=max_volume,
                orderbook_depth_buy=len(buy_orderbook.asks),
                orderbook_depth_sell=len(sell_orderbook.bids)
            )
            
            # Создаём возможность
            opportunity = ArbitrageOpportunity(
                symbol=self.symbol,
                direction=direction,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                max_volume_btc=max_volume,
                gross_profit_usd=gross_profit,
                net_profit_usd=net_profit,
                profit_percentage=profit_percentage,
                spread_usd=spread_usd,
                spread_bps=spread_bps,
                timestamp=datetime.now(),
                confidence_score=confidence
            )
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Ошибка при проверке направления {direction}: {e}")
            return None
    
    def _calculate_max_volume(
        self,
        buy_orderbook,
        sell_orderbook,
        buy_balance: Optional[dict],
        sell_balance: Optional[dict],
        buy_price: Decimal
    ) -> Decimal:
        """Рассчитать максимальный возможный объём сделки"""
        
        # 1. Ликвидность в стакане (первый уровень)
        buy_liquidity = buy_orderbook.asks[0].amount if buy_orderbook.asks else Decimal("0")
        sell_liquidity = sell_orderbook.bids[0].amount if sell_orderbook.bids else Decimal("0")
        
        orderbook_limit = min(buy_liquidity, sell_liquidity)
        
        # 2. Ограничение по балансу
        balance_limit = self.max_volume_btc
        
        if buy_balance:
            usdc_available = Decimal(str(buy_balance.get("USDC", 0)))
            balance_limit_buy = usdc_available / buy_price if buy_price > 0 else Decimal("0")
            balance_limit = min(balance_limit, balance_limit_buy)
        
        if sell_balance:
            btc_available = Decimal(str(sell_balance.get("BTC", 0)))
            balance_limit = min(balance_limit, btc_available)
        
        # 3. Общее ограничение
        max_volume = min(orderbook_limit, balance_limit, self.max_volume_btc)
        
        return max(Decimal("0"), max_volume)
    
    def _calculate_confidence(
        self,
        spread_bps: Decimal,
        volume: Decimal,
        orderbook_depth_buy: int,
        orderbook_depth_sell: int
    ) -> float:
        """
        Рассчитать confidence score (0.0 - 1.0)
        
        Факторы:
        - Величина спреда (больше = лучше)
        - Доступный объём (больше = лучше)
        - Глубина стакана (больше = лучше)
        """
        
        # Спред score (0-40% веса)
        spread_score = min(float(spread_bps) / 100.0, 1.0) * 0.4
        
        # Volume score (0-30% веса)
        volume_score = min(float(volume) / 0.1, 1.0) * 0.3
        
        # Depth score (0-30% веса)
        avg_depth = (orderbook_depth_buy + orderbook_depth_sell) / 2
        depth_score = min(avg_depth / 20.0, 1.0) * 0.3
        
        total_confidence = spread_score + volume_score + depth_score
        
        return min(max(total_confidence, 0.0), 1.0)
    
    def get_best_opportunity(
        self,
        opportunities: List[ArbitrageOpportunity]
    ) -> Optional[ArbitrageOpportunity]:
        """Получить лучшую возможность"""
        
        if not opportunities:
            return None
        
        # Фильтруем по confidence
        confident_opps = [
            opp for opp in opportunities
            if opp.is_confident(min_confidence=0.6)
        ]
        
        if not confident_opps:
            logger.warning("Нет возможностей с достаточной уверенностью")
            return None
        
        # Возвращаем самую прибыльную
        return confident_opps[0]


if __name__ == "__main__":
    # Пример использования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    finder = OpportunityFinder(
        symbol="BTC/USDC",
        min_profit_usd=Decimal("5"),
        min_spread_bps=Decimal("10")
    )
    
    print(f"✅ OpportunityFinder создан и готов к работе!")
