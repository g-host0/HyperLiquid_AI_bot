import time
import sqlite3
import requests
from config import *

# Импорт функций
from utils import get_market_data, analyze_with_deepseek

# Инициализация БД
def init_db():
    conn = sqlite3.connect('positions.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT,
            quantity REAL,
            entry_price REAL,
            status TEXT DEFAULT 'open',
            profit REAL DEFAULT 0.0,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def place_order(symbol, side, quantity):
    """Открывает позицию."""
    current_price = get_current_price(symbol)
    if TEST_MODE:
        print(f"[TEST] {side.upper()} {quantity} {symbol} at {current_price}")
        conn = sqlite3.connect('positions.db')
        conn.execute('INSERT INTO positions (symbol, side, quantity, entry_price) VALUES (?, ?, ?, ?)',
                     (symbol, side, quantity, current_price))
        conn.commit()
        conn.close()
        return
    
    # Реальный ордер на HL (update с symbol mapping)
    url = "https://api.hyperliquid.xyz/api/order"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {HYPERLIQUID_API_KEY}"}
    payload = {
        "account": HYPERLIQUID_ACCOUNT_ADDRESS,
        "symbol": f"{symbol[:-4]}USD:USD",  # e.g., ETHUSD:USD для ETHUSDT
        "side": side.upper(),
        "type": "MARKET",
        "quantity": str(quantity)
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                print(f"Ордер размещён: {side} {quantity} {symbol}")
                conn = sqlite3.connect('positions.db')
                conn.execute('INSERT INTO positions (symbol, side, quantity, entry_price) VALUES (?, ?, ?, ?)',
                             (symbol, side, quantity, current_price))
                conn.commit()
                conn.close()
            else:
                print(f"Ошибка ордера: {data.get('error')}")
        else:
            print(f"HTTP ошибка: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Ошибка запроса: {e}")

def check_positions():
    """Проверяет открытые позиции для всех символов."""
    conn = sqlite3.connect('positions.db')
    positions = conn.execute('SELECT * FROM positions WHERE status = ?', ('open',)).fetchall()
    
    for pos in positions:
        pos_id, symbol, side, quantity, entry_price, _, _, _ = pos
        current_price = get_current_price(symbol)
        profit_percent = (current_price - entry_price) / entry_price * 100 if side == 'buy' else (entry_price - current_price) / entry_price * 100
        
        # Закрыть по take-profit/stop-loss
        if profit_percent >= TAKE_PROFIT_PERCENT or profit_percent <= -STOP_LOSS_PERCENT:
            close_position(pos_id, profit_percent)
    
    conn.close()

def close_position(pos_id, profit):
    """Закрывает по ID."""
    if TEST_MODE:
        print(f"[TEST] Closed position {pos_id} with profit {profit}%")
        conn = sqlite3.connect('positions.db')
        conn.execute('UPDATE positions SET status = ?, profit = ? WHERE id = ?',
                     ('closed', profit, pos_id))
        conn.commit()
        conn.close()
        return
    
    # Реальная реализация закрытия для HL
    # ... (ваш код для закрытия позиций на Hyperliquid)

def get_current_price(symbol):
    """Получает цену для symbol."""
    binance_symbol = symbol.upper()
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": binance_symbol}
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            return float(response.json()['price'])
    except Exception:
        pass
    return 0.0

def main():
    init_db()
    print("Запуск бота...")
    while True:
        try:
            # Получаем данные только для первых MAX_SYMBOLS символов
            symbols_to_check = SYMBOLS[:MAX_SYMBOLS]
            data_dict_outer = get_market_data(symbols_to_check)
            
            # Фильтруем символы с полными данными
            valid_data = {
                symbol: data for symbol, data in data_dict_outer.items()
                if all(data.get(tf) for tf in ['1d', '1h', '1m'])
            }
            
            if not valid_data:
                print("Нет данных для анализа")
                time.sleep(INTERVAL)
                continue
                
            decision, reason = analyze_with_deepseek(valid_data)
            print(f"Рекомендация: {decision} | Причина: {reason}")
            
            if decision.startswith('buy_') or decision.startswith('sell_'):
                parts = decision.split('_')
                if len(parts) == 2:
                    action, symbol = parts[0], parts[1]
                    if symbol in valid_data:
                        place_order(symbol, action, QUANTITY)
            
            check_positions()
            time.sleep(INTERVAL)
            
        except KeyboardInterrupt:
            print("Остановка бота...")
            break
        except Exception as e:
            print(f"Критическая ошибка: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()