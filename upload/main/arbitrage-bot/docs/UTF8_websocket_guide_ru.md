# Руководство по WebSocket-подключениям MEXC и BingX

## Где реализовано
- `arbitrage/exchanges/mexc.py` — потоковые подписки на стакан и сделки MEXC, включая protobuf-декодер `mexc_deals_pb2`.
- `arbitrage/exchanges/bingx.py` — подписка на публичный стакан BingX и разбор gzip-сообщений.
- `arbitrage/marketdata/service.py` — координация обоих клиентов, проброс снапшотов слушателям и REST-фолбэк.
- `mexc_deals.proto`, `mexc_deals_pb2.py`, `mexc_websocket_parsed.py` — описание структуры агрегированных сделок и пример офлайн-парсинга.

## Общие требования
1. Python 3.11+, зависимости `websockets`, `aiohttp`, `protobuf` уже перечислены в `pyproject.toml`.
2. Все подключения запускаются внутри `asyncio` цикла; при использовании в скриптах вызывайте `asyncio.run(...)`.
3. Символы задаются в едином виде `BTC-USDC`, но для MEXC перед отправкой каналов дефисы удаляются, а для BingX используется `to_exchange_symbol` из `arbitrage/exchanges/symmap.py`.
4. Для production-режима параметры частоты пинга и глубины стакана контролируются аргументами клиентов и ключами из `config.yml` (`mexc_rest_fallback`, `mexc_stale_ms`, `mexc_rest_max_deviation`, `bingx_price_offset`, `bingx_top_epsilon`).

## Подключение к MEXC
### Точки доступа и основные параметры
| Элемент | Файл/ключ | Назначение |
| --- | --- | --- |
| `WS_ENDPOINTS` | `arbitrage/exchanges/mexc.py` | Список первичных WebSocket URL (`wss://wbs-api.mexc.com/ws`, `wss://wbs.mexc.com/ws`). Клиент перебирает их по кругу при реконнектах. |
| `MEXCClient(ping_interval=30, endpoints=None)` | `arbitrage/exchanges/mexc.py:33` | `ping_interval` определяет частоту ручного `PING`; `endpoints` позволяет задать собственный список URL. |
| `subscribe_orderbook(symbol, depth=20)` | `arbitrage/exchanges/mexc.py:45` | Канал `spot@public.limit.depth.v3.api@{SYMBOL}@{depth}` возвращает отсортированный стакан. |
| `subscribe_trades(symbol, interval_ms=100)` | `arbitrage/exchanges/mexc.py:64` | Канал `spot@public.aggre.deals.v3.api.pb@{interval}ms@{SYMBOL}` возвращает protobuf-пакеты агрегированных сделок. |
| `mexc_rest_fallback`, `mexc_stale_ms`, `mexc_rest_max_deviation` | `arbitrage/marketdata/service.py` + `config.yml` | Управляют HTTP-бэкапом, если WebSocket молчит дольше заданного порога, и фильтруют REST-данные по допустимому отклонению от потока. |

### Пошаговая последовательность для стакана
1. Нормализовать символ: `BTC-USDC` → `BTCUSDC` (метод `_normalize_mexc_symbol`).
2. Собрать канал `spot@public.limit.depth.v3.api@BTCUSDC@20` и отправить `{"method": "SUBSCRIPTION", "params": [channel]}`.
3. Обрабатывать ответы JSON, извлекать поле `data` → `bids`/`asks`. Метод `_parse_levels` сортирует уровни согласно стороне.
4. Контролировать `updateTime` как `update_id`. Это используется при сравнении с REST-бэкапом.

### Подписка на агрегированные сделки
- Сервис получает бинарные protobuf-сообщения, описанные в `mexc_deals.proto` (`PushDataV3ApiWrapper`).
- Метод `_decode_message` различает JSON-ACK/PONG и бинарные данные; для бинарного блока создаётся `TradeTick` с полями `price`, `quantity`, `side`, `timestamp`.
- MEXC шлёт сделки батчами за интервал `interval_ms`. Значение 100 мс — компромисс между латентностью и нагрузкой.

```python
import asyncio
from arbitrage.exchanges.mexc import MEXCClient

async def stream_mexc():
    client = MEXCClient(ping_interval=20)
    async for snapshot in client.subscribe_orderbook("BTC-USDC", depth=20):
        best_bid = snapshot.bids[0].price if snapshot.bids else None
        best_ask = snapshot.asks[0].price if snapshot.asks else None
        print("MEXC depth", best_bid, best_ask)
        break

asyncio.run(stream_mexc())
```

```python
import asyncio
from arbitrage.exchanges.mexc import MEXCClient

async def stream_mexc_trades():
    client = MEXCClient()
    async for trades in client.subscribe_trades("BTC-USDC", interval_ms=100):
        for trade in trades:
            print(trade.side, trade.price, trade.quantity)
        break

asyncio.run(stream_mexc_trades())
```

### Пинг/понг и реконнекты
- `_ping` отправляет `{"method": "PING"}` каждые `ping_interval` секунд; ответы `PONG` фильтруются при декодировании.
- `_ws_stream` создаёт задачу пинга, слушает сообщения и при исключениях `websockets.WebSocketException`/`OSError` откладывает повторное подключение на 1 секунду, переключая endpoint.

### REST-фолбэк
`MarketDataService._run_mexc_rest_backfill` включается, если `mexc_rest_fallback=True`. Он:
1. Следит за таймстампами последнего стакана (`_last_mexc_book`).
2. Если WebSocket молчит > `mexc_stale_ms`, запрашивает `https://api.mexc.com/api/v3/depth` с лимитом 20.
3. Сравнивает топовые цены с последним WebSocket-котом и применяет снапшот только если отклонение < `mexc_rest_max_deviation` USDC.

## Подключение к BingX
### Точки доступа и параметры
| Элемент | Файл/ключ | Назначение |
| --- | --- | --- |
| `BingXClient.ws_url` | `arbitrage/exchanges/bingx.py` | Основной URL `wss://open-api-ws.bingx.com/market`. |
| `BingXClient(depth=50, ping_interval=15)` | конструктор | `depth` управляет значением по умолчанию для подписок, `ping_interval` уходит в `websockets.connect` как встроенный ping/pong. |
| `subscribe_orderbook(symbol, depth=None)` | `arbitrage/exchanges/bingx.py:18` | Формирует `dataType = {exchange_symbol}@depth{level}`, где `exchange_symbol` приходит из `to_exchange_symbol` (например `BTC-USDC`). |
| `bingx_price_offset`, `bingx_top_epsilon`, `bingx_max_slippage` | `config.yml` | Балансируют исполнение заявок относительно полученного стакана (актуально при работе `execution/top_hunter.py`). |

### Поток сообщений
1. На каждое подключение генерируется `req_id = uuid4().hex`.
2. После `SUB` BingX отправляет gzip-сжатые JSON. Метод `_decode` сначала делает `gzip.decompress`, затем `json.loads`.
3. Успешный ответ содержит `code == 0` и объект `data` с `bids`/`asks` и `lastUpdateId`.
4. `_parse_levels` строит `OrderBookLevel` и сортирует уровни по цене.

```python
import asyncio
from arbitrage.exchanges.bingx import BingXClient

async def stream_bingx():
    client = BingXClient(depth=50, ping_interval=15)
    async for snapshot in client.subscribe_orderbook("BTC-USDC"):
        print("BingX depth", snapshot.bids[0].price, snapshot.asks[0].price)
        break

asyncio.run(stream_bingx())
```

### Отказоустойчивость
- При сетевых ошибках цикл делает паузу 1 секунду и повторяет подписку с новым `req_id`.
- BingX сам поддерживает ping/pong, поэтому дополнительная задача не создаётся.

## Объединение потоков в MarketDataService
`arbitrage/marketdata/service.py` запускает оба клиента:
1. На каждый символ создаются независимые задачи `_run_bingx_orderbook`, `_run_mexc_orderbook`, `_run_mexc_trades` и опционально `_run_mexc_rest_backfill`.
2. Полученные снапшоты передаются в зарегистрированные коллбеки `add_orderbook_listener`/`add_trades_listener`.
3. Пример инициализации:

```python
from arbitrage.marketdata.service import MarketDataService
from arbitrage.exchanges.bingx import BingXClient
from arbitrage.exchanges.mexc import MEXCClient

service = MarketDataService(
    symbols=["BTC-USDC"],
    bingx=BingXClient(depth=50),
    mexc=MEXCClient(ping_interval=20),
    mexc_rest_fallback=True,
)
```

Чтобы получить данные, зарегистрируйте обработчики и вызовите `await service.start()`. Остановка осуществляется через `await service.stop()`.

## Чек-лист перед запуском
- Проверьте, что `.env` содержит ключи для REST (они не нужны для публичных WebSocket, но понадобятся торговому модулю).
- Убедитесь, что системное время синхронизировано (проверки PING/PONG завязаны на таймеры `asyncio`).
- Настройте `config.yml` под желаемый объём стакана и критерии фолбэка.
- Для отладки можно использовать `mexc_websocket_parsed.py`, чтобы воспроизвести protobuf-пакеты из файла.
