import sqlite3

# Создание БД с обновленной схемой
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
print("База данных создана.")