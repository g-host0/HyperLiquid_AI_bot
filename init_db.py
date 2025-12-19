import sqlite3

def init_db():
    conn = sqlite3.connect("positions.db")
    cursor = conn.cursor()
    
    cursor.execute("""
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
            tp1_hit INTEGER DEFAULT 0,
            tp2_hit INTEGER DEFAULT 0,
            tp2_count INTEGER DEFAULT 0,
            last_known_size REAL DEFAULT 0,
            status TEXT DEFAULT 'open',
            profit REAL DEFAULT 0.0,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            last_tp_hit_at TIMESTAMP,
            sl_triggered INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

if __name__ == "__main__":
    init_db()
