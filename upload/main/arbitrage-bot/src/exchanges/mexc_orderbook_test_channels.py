"""
🔥 MEXC - Тест ВСЕХ возможных форматов каналов
"""
import asyncio
import json
import websockets


CHANNELS_TO_TEST = [
    # Варианты из документации
    "spot@public.limit.depth.v3.api@BTCUSDC@20",
    "spot@public.increase.depth.v3.api@BTCUSDC",
    "spot@public.bookTicker.v3.api@BTCUSDC",
    
    # Короткие варианты
    "BTCUSDC@depth20",
    "BTCUSDC@depth",
    "btcusdc@depth20",
    
    # Как в примере deals (может depth тоже так?)
    "spot@public.limit.depth.v3.api.pb@BTCUSDC@20",
    
    # Совсем короткие
    "depth@BTCUSDC",
    "orderbook@BTCUSDC",
]


async def test_channel(channel: str):
    """Тест одного канала"""
    try:
        print(f"\n{'='*80}")
        print(f"🔍 Тестирую канал: {channel}")
        print(f"{'='*80}")
        
        async with websockets.connect("wss://wbs-api.mexc.com/ws", ping_interval=None) as ws:
            # Подписка
            subscription = {"method": "SUBSCRIPTION", "params": [channel]}
            await ws.send(json.dumps(subscription))
            print(f"📤 Подписка отправлена")
            
            # Ждём ответ 5 секунд
            try:
                for i in range(5):
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    
                    if isinstance(message, str):
                        data = json.loads(message)
                        print(f"📩 Ответ #{i+1}: {json.dumps(data, indent=2)}")
                        
                        # Проверяем успешность
                        if data.get("code") == 0 and "Not Subscribed" not in data.get("msg", ""):
                            print(f"✅ КАНАЛ РАБОТАЕТ: {channel}")
                            return True
                        elif data.get("code") != 0:
                            print(f"❌ Ошибка: {data.get('msg')}")
                            return False
                            
                    elif isinstance(message, bytes):
                        print(f"📩 Получен protobuf (bytes) - длина: {len(message)}")
                        
            except asyncio.TimeoutError:
                print(f"⏱️  Timeout - нет ответа")
                return False
                
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    
    return False


async def main():
    print("\n" + "="*90)
    print("🔥 MEXC - ТЕСТ ВСЕХ КАНАЛОВ ORDERBOOK".center(90))
    print("="*90 + "\n")
    
    working_channels = []
    
    for channel in CHANNELS_TO_TEST:
        success = await test_channel(channel)
        if success:
            working_channels.append(channel)
        await asyncio.sleep(2)  # Пауза между тестами
    
    print("\n" + "="*90)
    print("📊 РЕЗУЛЬТАТЫ".center(90))
    print("="*90)
    
    if working_channels:
        print("\n✅ РАБОЧИЕ КАНАЛЫ:")
        for ch in working_channels:
            print(f"   - {ch}")
    else:
        print("\n❌ НЕТ РАБОЧИХ КАНАЛОВ")
    
    print("\n" + "="*90 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
