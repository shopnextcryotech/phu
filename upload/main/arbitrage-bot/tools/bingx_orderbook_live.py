import asyncio
import json
import gzip
from datetime import datetime
from uuid import uuid4
from typing import Optional, Dict
import websockets

EMOJI_TITLE = "🔥"
EMOJI_WS = "🔌"
EMOJI_OK = "✅"
EMOJI_BOOK = "📊"
EMOJI_SUB = "📝"
EMOJI_BID = "🟢"
EMOJI_ASK = "🔴"
EMOJI_ARROWUP = "🡅"
EMOJI_ARROWDOWN = "🡇"
EMOJI_LINE = "━"
EMOJI_BLOCK = "▓"
EMOJI_CLOCK = "⏱️"
EMOJI_DEPTH = "🌊"
EMOJI_MID = "💰"
EMOJI_SPREAD = "🧮"
EMOJI_BINGX = "🦈"
EMOJI_SNAPSHOT = "🖼️"
EMOJI_SEPARATOR = EMOJI_BLOCK*4

def emoji_row(n, emoji1, emoji2):
    return (emoji1+emoji2) * (n//2) + (emoji1 if n%2 else "")

class BingXOrderBook:
    WS_URL = "wss://open-api-ws.bingx.com/market"

    def __init__(self, symbol: str = "BTC-USDC", depth: int = 50):
        self.symbol = symbol
        self.depth = depth
        self.ws = None
        self.req_id = None
        self.orderbook = {
            'bids': [],
            'asks': [],
            'timestamp': None,
            'last_update_id': None,
            'last_update': None
        }
        self.running = False

    def _decode(self, message: bytes) -> Dict:
        try:
            decompressed = gzip.decompress(message)
            return json.loads(decompressed.decode('utf-8'))
        except Exception as e:
            print(f"{EMOJI_BLOCK} Ошибка декодирования: {e}")
            return {}

    async def connect(self):
        try:
            print(f"{EMOJI_WS} Подключение к BingX WebSocket...")
            self.ws = await websockets.connect(
                self.WS_URL,
                ping_interval=15,
                ping_timeout=10
            )
            print(f"{EMOJI_OK} Подключено к BingX WebSocket")
            self.req_id = uuid4().hex
            subscribe_message = {
                "id": self.req_id,
                "reqType": "sub",
                "dataType": f"{self.symbol}@depth{self.depth}"
            }
            await self.ws.send(json.dumps(subscribe_message))
            print(f"{EMOJI_BOOK} Подписка на order book для {self.symbol} ({EMOJI_DEPTH} depth={self.depth})\n")
            self.running = True
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    async def listen(self):
        try:
            async for raw_message in self.ws:
                data = self._decode(raw_message)
                if data.get('code') == 0 and 'data' in data:
                    self.update_orderbook(data['data'])
        except websockets.exceptions.ConnectionClosed:
            print("⚠️  Соединение закрыто")
            self.running = False
        except Exception as e:
            print(f"❌ Ошибка при получении данных: {e}")
            self.running = False

    def update_orderbook(self, data: Dict):
        if 'bids' in data:
            self.orderbook['bids'] = sorted(
                [[float(p), float(a)] for p, a in data['bids']],
                key=lambda x: x[0], reverse=True
            )
        if 'asks' in data:
            self.orderbook['asks'] = sorted(
                [[float(p), float(a)] for p, a in data['asks']],
                key=lambda x: x[0]
            )
        self.orderbook['last_update_id'] = data.get('lastUpdateId')
        self.orderbook['timestamp'] = data.get('ts')
        self.orderbook['last_update'] = datetime.now().isoformat()

    def get_best_bid(self) -> Optional[float]:
        if self.orderbook['bids']:
            return self.orderbook['bids'][0][0]
        return None

    def get_best_ask(self) -> Optional[float]:
        if self.orderbook['asks']:
            return self.orderbook['asks'][0][0]
        return None

    def get_spread(self) -> Optional[float]:
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return best_ask - best_bid
        return None

    def get_mid_price(self) -> Optional[float]:
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return (best_bid + best_ask) / 2
        return None

    def print_orderbook(self, max_levels: int = None):
        if max_levels is None:
            max_levels = self.depth

        print("\n" + (EMOJI_BLOCK * 28) + f" {EMOJI_SNAPSHOT} SNAPSHOT! {EMOJI_BLOCK * 28}")
        print(f"{EMOJI_BINGX} Стакан {self.symbol} | {EMOJI_DEPTH} Depth: {len(self.orderbook['bids'])}/{len(self.orderbook['asks'])}")
        print(f"{EMOJI_ARROWUP*3} ASK-сайд   {EMOJI_LINE * 54}")
        asks = self.orderbook['asks'][:max_levels]
        for i, (price, amount) in enumerate(reversed(asks)):
            print(f"{EMOJI_ASK} ASK [{len(asks)-i:2d}]: {EMOJI_ARROWUP} Цена: {price:>12,.2f} | {EMOJI_BLOCK} Объём: {amount:>10,.6f}")
        print(EMOJI_SEPARATOR*5)
        print(f"{EMOJI_SPREAD} Spread: {self.get_spread():.8f}   |   {EMOJI_MID} Mid: {self.get_mid_price():.2f}  | {EMOJI_CLOCK} {datetime.now().strftime('%H:%M:%S')}")
        print(EMOJI_SEPARATOR*5)
        print(f"{EMOJI_ARROWDOWN*3} BID-сайд   {EMOJI_LINE * 54}")
        bids = self.orderbook['bids'][:max_levels]
        for i, (price, amount) in enumerate(bids):
            print(f"{EMOJI_BID} BID [{i+1:2d}]: {EMOJI_ARROWDOWN} Цена: {price:>12,.2f} | {EMOJI_BLOCK} Объём: {amount:>10,.6f}")
        print(EMOJI_LINE*72 + "\n")

    async def close(self):
        self.running = False
        if self.ws:
            await self.ws.close()
            print(
                f"\n{EMOJI_WS} BingX WebSocket закрыт {EMOJI_OK*3}"
            )

async def test_bingx_orderbook(depth=5):
    print("\n" + EMOJI_LINE*90)
    print(f"{EMOJI_TITLE*3} ТЕСТ BingX ORDERBOOK — GLHF {EMOJI_TITLE*3}".center(90))
    print(EMOJI_LINE*90 + "\n")

    orderbook = BingXOrderBook(symbol="BTC-USDC", depth=depth)
    connected = await orderbook.connect()
    if not connected:
        print("❌ Ошибка подключения")
        return

    listen_task = asyncio.create_task(orderbook.listen())

    try:
        await asyncio.sleep(2)
        for i in range(3):
            print(f"\n{EMOJI_SNAPSHOT} Снапшот {i+1}/3")
            print(emoji_row(10+(i%2), EMOJI_OK, EMOJI_BLOCK))
            orderbook.print_orderbook()
            print(emoji_row(22, EMOJI_BINGX, EMOJI_LINE))
            await asyncio.sleep(3)
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
    finally:
        await orderbook.close()
        listen_task.cancel()
        print(EMOJI_BLOCK*14 + f" {EMOJI_OK} ТЕСТ ЗАВЕРШЁН {EMOJI_BLOCK*14}")

if __name__ == '__main__':
    import sys
    d = 5
    if len(sys.argv) > 1:
        try:
            d = int(sys.argv[1])
        except:
            pass
    asyncio.run(test_bingx_orderbook(depth=d))
