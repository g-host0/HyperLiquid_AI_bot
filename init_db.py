import sqlite3
import os

# Удаляем старый файл базы данных, если он существует
if os.path.exists('positions.db'):
    os.remove('positions.db')
    print("Старая база данных удалена.")

# Создание БД с обновленной схемой
conn = sqlite3.connect('positions.db')
conn.execute('''
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        side TEXT,
        quantity REAL,
        entry_price REAL,
        position_value REAL,
        atr REAL,
        stop_loss REAL,
        stop_loss_percent REAL,
        original_quantity REAL,
        take_profit_hit INTEGER DEFAULT 0,
        status TEXT DEFAULT 'open',
        profit REAL DEFAULT 0.0,
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()
conn.close()
print("База данных создана с новой схемой.")