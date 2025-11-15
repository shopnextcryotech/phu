"""
Price Aggregator - Агрегатор рыночных данных с MEXC и BingX через WebSocket

Основные функции:
- Подключение к WebSocket обеих бирж одновременно
- Агрегация orderbook данных в реальном времени
- Предоставление синхронизированных данных для стратегий
- Автоматическое переподключение при обрыве связи
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Уровень в стакане (цена + объём)"""
    price: Decimal
    amount: Decimal

    def __post_init__(self):
        self.price = Decimal(str(self.price))
        self.amount = Decimal(str(self.amount))


@dataclass
class OrderBook:
    """Полный стакан ордеров"""
    symbol: str
    exchange: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def best_bid(self) -> Optional[Decimal]:
        """Лучшая цена покупки"""
        return self.bids[0].price if self.bids else None
    
    @property
    def best_ask(self) -> Optional[Decimal]:
        """Лучшая цена продажи"""
        return self.asks[0].price if self.asks else None
    
    @property
    def spread(self) -> Optional[Decimal]:
        """Спред между bid и ask"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def mid_price(self) -> Optional[Decimal]:
        """Средняя цена"""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None


class PriceAggregator:
    """
    Агрегатор цен с нескольких бирж
    
    Usage:
        aggregator = PriceAggregator(symbol="BTC/USDC")
        await aggregator.start()
        
        # Получить orderbook
        mexc_book = aggregator.get_orderbook("mexc")
        bingx_book = aggregator.get_orderbook("bingx")
        
        # Подписаться на обновления
        await aggregator.subscribe(callback_function)
    """
    
    def __init__(
        self,
        symbol: str,
        mexc_ws_connector=None,
        bingx_ws_connector=None,
        depth: int = 20
    ):
        self.symbol = symbol
        self.depth = depth
        
        # WebSocket коннекторы (будут инициализированы позже)
        self.mexc_ws = mexc_ws_connector
        self.bingx_ws = bingx_ws_connector
        
        # Хранилище последних orderbook
        self._orderbooks: Dict[str, OrderBook] = {}
        
        # Подписчики на обновления
        self._subscribers: List[callable] = []
        
        # Флаг работы
        self._running = False
        
        # Блокировка для thread-safe операций
        self._lock = asyncio.Lock()
        
        logger.info(f"PriceAggregator инициализирован для {symbol}")
    
    async def start(self):
        """Запуск агрегатора и подключение к WebSocket"""
        if self._running:
            logger.warning("PriceAggregator уже запущен")
            return
        
        self._running = True
        logger.info("Запуск PriceAggregator...")
        
        # Запускаем WebSocket потоки параллельно
        tasks = []
        
        if self.mexc_ws:
            tasks.append(self._start_mexc_stream())
        
        if self.bingx_ws:
            tasks.append(self._start_bingx_stream())
        
        if not tasks:
            logger.error("Не указаны WebSocket коннекторы!")
            return
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop(self):
        """Остановка агрегатора"""
        logger.info("Остановка PriceAggregator...")
        self._running = False
        
        # Закрываем WebSocket соединения
        if self.mexc_ws:
            await self.mexc_ws.close()
        
        if self.bingx_ws:
            await self.bingx_ws.close()
    
    async def _start_mexc_stream(self):
        """Запуск потока данных от MEXC"""
        logger.info("Подключение к MEXC WebSocket...")
        
        while self._running:
            try:
                async for orderbook_data in self.mexc_ws.subscribe_orderbook(
                    self.symbol, 
                    depth=self.depth
                ):
                    await self._update_orderbook("mexc", orderbook_data)
            except Exception as e:
                logger.error(f"Ошибка MEXC WebSocket: {e}")
                await asyncio.sleep(5)  # Переподключение через 5 сек
    
    async def _start_bingx_stream(self):
        """Запуск потока данных от BingX"""
        logger.info("Подключение к BingX WebSocket...")
        
        while self._running:
            try:
                async for orderbook_data in self.bingx_ws.subscribe_orderbook(
                    self.symbol,
                    depth=self.depth
                ):
                    await self._update_orderbook("bingx", orderbook_data)
            except Exception as e:
                logger.error(f"Ошибка BingX WebSocket: {e}")
                await asyncio.sleep(5)
    
    async def _update_orderbook(self, exchange: str, data: dict):
        """Обновление orderbook от биржи"""
        async with self._lock:
            try:
                # Парсим bids и asks
                bids = [
                    OrderBookLevel(price=bid[0], amount=bid[1])
                    for bid in data.get("bids", [])[:self.depth]
                ]
                
                asks = [
                    OrderBookLevel(price=ask[0], amount=ask[1])
                    for ask in data.get("asks", [])[:self.depth]
                ]
                
                # Создаём новый orderbook
                orderbook = OrderBook(
                    symbol=self.symbol,
                    exchange=exchange,
                    bids=bids,
                    asks=asks,
                    timestamp=datetime.now()
                )
                
                # Сохраняем
                self._orderbooks[exchange] = orderbook
                
                # Уведомляем подписчиков
                await self._notify_subscribers(exchange, orderbook)
                
                logger.debug(
                    f"{exchange.upper()}: best_bid={orderbook.best_bid}, "
                    f"best_ask={orderbook.best_ask}, spread={orderbook.spread}"
                )
                
            except Exception as e:
                logger.error(f"Ошибка обновления orderbook для {exchange}: {e}")
    
    async def _notify_subscribers(self, exchange: str, orderbook: OrderBook):
        """Уведомление всех подписчиков об обновлении"""
        for callback in self._subscribers:
            try:
                await callback(exchange, orderbook)
            except Exception as e:
                logger.error(f"Ошибка в callback подписчика: {e}")
    
    def get_orderbook(self, exchange: str) -> Optional[OrderBook]:
        """Получить последний orderbook биржи"""
        return self._orderbooks.get(exchange)
    
    def get_all_orderbooks(self) -> Dict[str, OrderBook]:
        """Получить все последние orderbook"""
        return self._orderbooks.copy()
    
    async def subscribe(self, callback: callable):
        """
        Подписаться на обновления orderbook
        
        Args:
            callback: async функция с сигнатурой (exchange: str, orderbook: OrderBook)
        """
        self._subscribers.append(callback)
        logger.info(f"Добавлен подписчик: {callback.__name__}")
    
    def unsubscribe(self, callback: callable):
        """Отписаться от обновлений"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.info(f"Удалён подписчик: {callback.__name__}")
    
    def get_spread_between_exchanges(
        self, 
        buy_exchange: str, 
        sell_exchange: str
    ) -> Optional[Decimal]:
        """
        Рассчитать спред между биржами для арбитража
        
        Args:
            buy_exchange: Биржа для покупки
            sell_exchange: Биржа для продажи
        
        Returns:
            Спред в USDC или None если данных нет
        """
        buy_book = self.get_orderbook(buy_exchange)
        sell_book = self.get_orderbook(sell_exchange)
        
        if not buy_book or not sell_book:
            return None
        
        if not buy_book.best_ask or not sell_book.best_bid:
            return None
        
        # Спред = цена продажи - цена покупки
        return sell_book.best_bid - buy_book.best_ask
    
    def is_arbitrage_opportunity(
        self,
        buy_exchange: str,
        sell_exchange: str,
        min_spread: Decimal = Decimal("0")
    ) -> bool:
        """
        Проверка наличия арбитражной возможности
        
        Args:
            buy_exchange: Биржа для покупки
            sell_exchange: Биржа для продажи
            min_spread: Минимальный спред для profitable арбитража
        
        Returns:
            True если есть возможность арбитража
        """
        spread = self.get_spread_between_exchanges(buy_exchange, sell_exchange)
        
        if spread is None:
            return False
        
        return spread > min_spread


# Пример использования
async def example_usage():
    """Пример использования PriceAggregator"""
    
    # Callback для обработки обновлений
    async def on_orderbook_update(exchange: str, orderbook: OrderBook):
        print(f"\n[{exchange.upper()}] Обновление:")
        print(f"  Best Bid: {orderbook.best_bid}")
        print(f"  Best Ask: {orderbook.best_ask}")
        print(f"  Spread: {orderbook.spread}")
        print(f"  Mid Price: {orderbook.mid_price}")
    
    # Создаём агрегатор (коннекторы нужно импортировать отдельно)
    aggregator = PriceAggregator(
        symbol="BTC/USDC",
        # mexc_ws_connector=MexcWebSocketClient(),
        # bingx_ws_connector=BingXWebSocketClient(),
        depth=20
    )
    
    # Подписываемся на обновления
    await aggregator.subscribe(on_orderbook_update)
    
    # Запускаем
    await aggregator.start()
    
    # Работаем 60 секунд
    await asyncio.sleep(60)
    
    # Проверяем арбитраж
    if aggregator.is_arbitrage_opportunity("mexc", "bingx", min_spread=Decimal("10")):
        spread = aggregator.get_spread_between_exchanges("mexc", "bingx")
        print(f"\n🚀 Арбитраж возможен! Спред: {spread} USDC")
    
    # Останавливаем
    await aggregator.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(example_usage())
