"""
Скрипт для тестирования подключения к Hyperliquid Testnet
"""

from hyperliquid_api import hl_api
from config import USE_TESTNET, HYPERLIQUID_ACCOUNT_ADDRESS
import time

def test_connection():
    print("="*60)
    print("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К HYPERLIQUID")
    print("="*60)
    
    # Проверка настроек
    if not HYPERLIQUID_ACCOUNT_ADDRESS:
        print("\n❌ ОШИБКА: HYPERLIQUID_ACCOUNT_ADDRESS не установлен в .env")
        print("\n📝 Добавьте в .env файл:")
        print("   HYPERLIQUID_ACCOUNT_ADDRESS=0xВашАдресКошелька")
        print("\n💡 Как получить адрес:")
        print("   1. Откройте MetaMask или другой EVM кошелёк")
        print("   2. Скопируйте адрес (начинается с 0x...)")
        print("   3. Добавьте в .env файл")
        if USE_TESTNET:
            print("\n🌐 Для testnet:")
            print("   1. Зайдите на https://app.hyperliquid-testnet.xyz/")
            print("   2. Подключите кошелёк")
            print("   3. Получите тестовые токены из faucet")
        return
    
    # 1. Проверяем баланс
    print("\n1️⃣ Получение баланса...")
    balance = hl_api.get_balance()
    
    if balance > 0:
        print(f"   ✅ Баланс получен: ${balance:.2f}")
    else:
        print(f"   ⚠️ Баланс: ${balance:.2f}")
        if USE_TESTNET:
            print(f"\n   💡 Как получить тестовые токены:")
            print(f"   1. Зайдите на https://app.hyperliquid-testnet.xyz/")
            print(f"   2. Подключите кошелёк с адресом: {HYPERLIQUID_ACCOUNT_ADDRESS}")
            print(f"   3. Найдите раздел 'Faucet' или попросите в Discord")
            print(f"   4. Запросите тестовые USDC")
    
    # 2. Получаем информацию о рынках
    print("\n2️⃣ Получение информации о рынках...")
    markets = hl_api.get_market_info()
    
    if markets:
        print(f"   ✅ Доступно {len(markets)} рынков")
        
        # Показываем популярные рынки
        popular = ["BTC", "ETH", "SOL", "BNB", "AVAX"]
        print(f"\n   📊 Популярные рынки:")
        for market in markets:
            if market.get("name") in popular:
                sz_decimals = market.get("szDecimals", 0)
                print(f"      - {market.get('name')}: минимальный размер 0.{'0'*(sz_decimals-1)}1")
    else:
        print(f"   ❌ Не удалось получить информацию о рынках")
    
    # 3. Получаем открытые позиции
    print("\n3️⃣ Получение открытых позиций...")
    positions = hl_api.get_open_positions()
    
    if positions:
        print(f"   📊 Открытых позиций: {len(positions)}")
        for pos in positions:
            pnl_color = "🟢" if pos['side'] == "long" else "🔴"
            print(f"      {pnl_color} {pos['symbol']}: {pos['side']} {abs(pos['size'])} @ ${pos['entry_price']:.2f}")
    else:
        print(f"   ✅ Открытых позиций нет")
    
    # 4. Тест получения свечей (опционально)
    print("\n4️⃣ Тестирование получения свечей для ETH...")
    candles = hl_api.get_candles("ETH", interval="1h", lookback=10)
    if candles:
        print(f"   ✅ Получено свечей для ETH")
        if isinstance(candles, list) and len(candles) > 0:
            last_candle = candles[-1]
            print(f"      Последняя свеча: O={last_candle.get('o')} H={last_candle.get('h')} L={last_candle.get('l')} C={last_candle.get('c')}")
    
    # 5. Тест стакана ордеров (опционально)
    print("\n5️⃣ Получение стакана для BTC...")
    l2_book = hl_api.get_l2_book("BTC")
    if l2_book:
        levels = l2_book.get("levels", [])
        if levels and len(levels) >= 2:
            bids = levels[0]  # Покупки
            asks = levels[1]  # Продажи
            if bids and asks:
                best_bid = bids[0] if bids else None
                best_ask = asks[0] if asks else None
                if best_bid and best_ask:
                    print(f"   ✅ Лучший bid: ${best_bid.get('px')} x {best_bid.get('sz')}")
                    print(f"   ✅ Лучший ask: ${best_ask.get('px')} x {best_ask.get('sz')}")
    
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("="*60)
    
    # Итоговая сводка
    print("\n📋 ИТОГИ:")
    if HYPERLIQUID_ACCOUNT_ADDRESS:
        print(f"   ✅ Адрес кошелька настроен: {HYPERLIQUID_ACCOUNT_ADDRESS}")
    else:
        print(f"   ❌ Адрес кошелька НЕ настроен")
    
    if markets:
        print(f"   ✅ Подключение к API работает")
    else:
        print(f"   ❌ Проблемы с подключением к API")
    
    if balance > 0:
        print(f"   ✅ Баланс: ${balance:.2f}")
    else:
        print(f"   ⚠️ Нулевой баланс (нужны тестовые токены)")
    
    print("\n💡 Следующие шаги:")
    if not HYPERLIQUID_ACCOUNT_ADDRESS:
        print("   1. Добавьте HYPERLIQUID_ACCOUNT_ADDRESS в .env")
    elif balance == 0:
        print("   1. Получите тестовые токены на https://app.hyperliquid-testnet.xyz/")
        print("   2. Или попросите в Discord сообществе Hyperliquid")
    else:
        print("   1. ✅ Всё готово для запуска бота!")
        print("   2. Запустите: python3 trading_bot.py")
        print("   3. Бот будет в TEST_MODE (симуляция, без реальных ордеров)")
        print("   4. Для реальных ордеров нужна реализация подписи транзакций")

if __name__ == "__main__":
    test_connection()
