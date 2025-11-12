"""
🔥 BingX Order Book WebSocket Module
📊 Получение данных стакана в реальном времени через WebSocket
⚡ С поддержкой gzip декомпрессии
"""
import asyncio
import json
import gzip
from datetime import datetime
from uuid import uuid4
from typing import Optional, Dict, List
import websockets


class BingXOrderBook:
    """
    WebSocket клиент для получения order book с BingX
    """
    
    # WebSocket URL для BingX spot
    WS_URL = "wss://open-api-ws.bingx.com/market"
    
    def __init__(self, symbol: str = "BTC-USDC", depth: int = 50):
        """
        Инициализация WebSocket клиента
        
        Args:
            symbol: Торговая пара (BTC-USDC для spot)
            depth: Глубина стакана (5, 10, 20, 50, 100)
        """
        self.symbol = symbol
        self.depth = depth
        self.ws = None
        self.req_id = None
        self.orderbook = {
            'bids': [],  # [[price, amount], ...]
            'asks': [],  # [[price, amount], ...]
            'timestamp': None,
            'last_update_id': None,
            'last_update': None
        }
        self.running = False
        
    def _decode(self, message: bytes) -> Dict:
        """
        Декодирование gzip-сжатого JSON сообщения
        
        Args:
            message: Сырые байты от WebSocket
            
        Returns:
            Распарсенный JSON
        """
        try:
            # BingX отправляет gzip-сжатые данные
            decompressed = gzip.decompress(message)
            return json.loads(decompressed.decode('utf-8'))
        except Exception as e:
            print(f"❌ Ошибка декодирования: {e}")
            return {}
        
    async def connect(self):
        """Подключение к WebSocket"""
        try:
            print(f"🔌 Подключение к BingX WebSocket...")
            
            # Подключаемся с встроенным ping/pong
            self.ws = await websockets.connect(
                self.WS_URL,
                ping_interval=15,
                ping_timeout=10
            )
            
            print(f"✅ Подключено к BingX WebSocket")
            
            # Генерируем уникальный ID для подписки
            self.req_id = uuid4().hex
            
            # Подписка на order book
            subscribe_message = {
                "id": self.req_id,
                "reqType": "sub",
                "dataType": f"{self.symbol}@depth{self.depth}"
            }
            
            await self.ws.send(json.dumps(subscribe_message))
            print(f"📊 Подписка на order book для {self.symbol} (depth={self.depth})\n")
            
            self.running = True
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
    
    async def listen(self):
        """Прослушивание обновлений order book"""
        try:
            async for raw_message in self.ws:
                # Декодируем gzip-сжатое сообщение
                data = self._decode(raw_message)
                
                # Проверяем успешность ответа
                if data.get('code') == 0 and 'data' in data:
                    self.update_orderbook(data['data'])
                elif 'code' in data and data['code'] != 0:
                    print(f"⚠️  Ошибка от сервера: {data}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("⚠️  Соединение закрыто")
            self.running = False
        except Exception as e:
            print(f"❌ Ошибка при получении данных: {e}")
            self.running = False
    
    def update_orderbook(self, data: Dict):
        """
        Обновление локального стакана
        
        Args:
            data: Данные от WebSocket
        """
        if 'bids' in data:
            # Сортируем bids по цене (от большей к меньшей)
            self.orderbook['bids'] = sorted(
                [[float(p), float(a)] for p, a in data['bids']],
                key=lambda x: x[0],
                reverse=True
            )
        
        if 'asks' in data:
            # Сортируем asks по цене (от меньшей к большей)
            self.orderbook['asks'] = sorted(
                [[float(p), float(a)] for p, a in data['asks']],
                key=lambda x: x[0]
            )
        
        self.orderbook['last_update_id'] = data.get('lastUpdateId')
        self.orderbook['timestamp'] = data.get('ts')
        self.orderbook['last_update'] = datetime.now().isoformat()
    
    def get_best_bid(self) -> Optional[float]:
        """
        Получить лучшую цену bid (покупка)
        
        Returns:
            Лучшая цена bid или None
        """
        if self.orderbook['bids']:
            return self.orderbook['bids'][0][0]
        return None
    
    def get_best_ask(self) -> Optional[float]:
        """
        Получить лучшую цену ask (продажа)
        
        Returns:
            Лучшая цена ask или None
        """
        if self.orderbook['asks']:
            return self.orderbook['asks'][0][0]
        return None
    
    def get_spread(self) -> Optional[float]:
        """
        Получить спред (разница между ask и bid)
        
        Returns:
            Спред или None
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return best_ask - best_bid
        return None
    
    def get_mid_price(self) -> Optional[float]:
        """
        Получить среднюю цену (mid price)
        
        Returns:
            Средняя цена или None
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return (best_bid + best_ask) / 2
        return None
    
    def get_orderbook_snapshot(self) -> Dict:
        """
        Получить снимок стакана
        
        Returns:
            Словарь с данными стакана
        """
        return {
            'exchange': 'BingX',
            'symbol': self.symbol,
            'best_bid': self.get_best_bid(),
            'best_ask': self.get_best_ask(),
            'mid_price': self.get_mid_price(),
            'spread': self.get_spread(),
            'bids_depth': len(self.orderbook['bids']),
            'asks_depth': len(self.orderbook['asks']),
            'last_update_id': self.orderbook['last_update_id'],
            'timestamp': self.orderbook['timestamp'],
            'last_update': self.orderbook['last_update']
        }
    
    async def close(self):
        """Закрытие WebSocket соединения"""
        self.running = False
        if self.ws:
            await self.ws.close()
            print("\n🔒 BingX WebSocket закрыт")


# ========== ТЕСТИРОВАНИЕ ==========
async def test_bingx_orderbook():
    """Тест для проверки работы BingX order book"""
    print("\n" + "="*90)
    print("🔥 ТЕСТ BingX ORDER BOOK WEBSOCKET".center(90))
    print("="*90 + "\n")
    
    # Создаём клиент
    orderbook = BingXOrderBook(symbol="BTC-USDC", depth=50)
    
    # Подключаемся
    connected = await orderbook.connect()
    
    if not connected:
        print("❌ Не удалось подключиться")
        return
    
    # Запускаем прослушивание в фоне
    listen_task = asyncio.create_task(orderbook.listen())
    
    try:
        # Ждём 10 секунд и показываем данные каждую секунду (в одну строку)
        for i in range(10):
            await asyncio.sleep(1)
            
            snapshot = orderbook.get_orderbook_snapshot()
            
            # Компактный вывод в одну строку
            print(f"⏱️  [{i+1:2d}/10] 🟢 Bid: ${snapshot['best_bid']:>10,.2f} | 🔴 Ask: ${snapshot['best_ask']:>10,.2f} | 💰 Mid: ${snapshot['mid_price']:>10,.2f} | 📊 Spread: ${snapshot['spread']:>6.2f} | Depth: {snapshot['bids_depth']}/{snapshot['asks_depth']}")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
    
    finally:
        await orderbook.close()
        listen_task.cancel()
        
        print("\n" + "="*90)
        print("✅ ТЕСТ ЗАВЕРШЁН".center(90))
        print("="*90 + "\n")


if __name__ == '__main__':
    asyncio.run(test_bingx_orderbook())
