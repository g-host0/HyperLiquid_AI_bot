import sqlite3


def init_db():
    with sqlite3.connect("positions.db") as conn:
        cur = conn.cursor()
        # Таблица positions — совпадает с торговым ботом
        cur.execute(
            """
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
                close_reason TEXT
            )
            """
        )

        # Таблица cooldowns для запретов добора/переоткрытия
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS cooldowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,      -- 'long'/'short'
                event_type TEXT NOT NULL, -- 'tp'/'sl'
                ts REAL NOT NULL,
                details TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cooldowns_lookup
                ON cooldowns(symbol, side, event_type, ts DESC);
            """
        )

        # Перенос старых событий из trade_events, если таблица есть
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO cooldowns (symbol, side, event_type, ts, details)
                SELECT symbol, side, event_type, strftime('%s', event_time), details
                FROM trade_events
                """
            )
        except Exception:
            pass

        conn.commit()
