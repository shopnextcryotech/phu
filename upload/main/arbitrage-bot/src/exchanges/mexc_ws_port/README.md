# MEXC WebSocket Module

Порт уникализированного клиента MEXC из основного арбитражного проекта. Папка `mexc_ws_port` содержит всё необходимое, чтобы быстро интегрировать публичные WebSocket‑потоки MEXC (агрегированные сделки и лимитный стакан) в любой другой проект.

## Состав каталога

- `mexc_client.py` — самостоятельный класс `MEXCClient` с минимальными зависимостями. Внутри определены все необходимые модели (`TradeTick`, `OrderBookSnapshot`, `OrderBookLevel`) и расширенный логгинг подключения.
- `proto/mexc_deals.proto` и сгенерированный `proto/mexc_deals_pb2.py` — protobuf-схема и Python-стерты для канала `spot@public.aggre.deals`. Директория помечена как пакет (`__init__.py`), поэтому модуль можно импортировать как `from proto import mexc_deals_pb2`.
- `test_mexc_ws.py` — простой ручной тест: подключается к `BTCUSDT`, выводит хэндшейк (уровень DEBUG `websockets`) и первую пачку сделок, затем мягко закрывает соединение.
- `requirements.txt` — список зависимостей (`websockets`, `protobuf`). Python 3.10+.

## Быстрый старт

```powershell
cd mexc_ws_port
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python test_mexc_ws.py
```

В выводе появится полный WebSocket-хэндшейк: HTTP `GET /ws`, `101 Switching Protocols`, ACK на подписку `spot@public.aggre.deals…`, затем бинарные payload'ы с реальными сделками.

## Использование в другом проекте

1. Скопируйте папку `mexc_ws_port` целиком либо установите её как подмодуль.
2. Импортируйте клиент:  
   ```python
   from mexc_ws_port.mexc_client import MEXCClient
   ```
3. Запускайте корутины `subscribe_trades("BTCUSDT")` и/или `subscribe_orderbook("BTC-USDT", depth=20)` внутри вашего event loop. На выходе — либо список `TradeTick`, либо `OrderBookSnapshot`.
4. Для параллельного чтения используйте `asyncio.create_task` (пример в исходном арбитражном сервисе).

## Логирование и диагностика

- `mexc_client.py` логирует события `mexc.ws.connect`, `mexc.ws.connected`, `mexc.ws.retry` — этим легко отследить конечную точку и переподключения.
- Тестовый скрипт поднимает детализацию до `DEBUG` для `websockets.client/protocol`, поэтому видно каждую стадию рукопожатия, отправку SUBSCRIPTION и бинарные сообщения.
- При необходимости сохраните лог в файл, например:
  ```python
  logging.basicConfig(
      level=logging.INFO,
      filename="mexc_ws.log",
      format="%(asctime)s %(levelname)s %(name)s - %(message)s",
  )
  ```

## Снятие сетевого трафика (опционально)

1. Запустите PowerShell от имени администратора.
2. Включите захват:
   ```powershell
   pktmon start --capture --pkt-size 0 --tracefile C:\temp\mexc.etl
   ```
3. Выполните `python test_mexc_ws.py` или ваш собственный сценарий.
4. Остановите запись и конвертируйте в PCAP:
   ```powershell
   pktmon stop
   pktmon pcapng C:\temp\mexc.etl -o C:\temp\mexc.pcapng
   ```
5. Откройте `mexc.pcapng` в Wireshark — увидите один TLS‑поток на `wbs-api.mexc.com:443` с фреймами WebSocket.

## Настройка конечных точек

Список `WS_ENDPOINTS` объявлен прямо в `mexc_client.py`. Можно переопределить:

```python
client = MEXCClient(endpoints=["wss://wbs-api.mexc.com/ws"])
```

или изменить интервал пингов `MEXCClient(ping_interval=20)`. Любая ошибка на сокете приводит к логированию `mexc.ws.retry …` и переподключению на следующий URL в списке.

---

Эта папка автономна: перенесите её в другой репозиторий, установите зависимости и подключайте MEXC WebSocket без необходимости тянуть остальной арбитражный код.
