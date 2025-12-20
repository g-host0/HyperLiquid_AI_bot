# -*- coding: utf-8 -*-
"""
Торговый бот для Hyperliquid с полным контролем SL/TP
"""

import time
import sqlite3
from datetime import datetime, timedelta
import traceback

from config import *
from utils import get_market_data, analyze_with_ai, calculate_atr
from hyperliquid_api import hl_api


# Фикс Python 3.12 sqlite3 datetime deprecation
def register_datetime_adapter():
    def adapt_datetime(dt):
        return dt.isoformat()
    sqlite3.register_adapter(datetime, adapt_datetime)

register_datetime_adapter()


# ---------- База данных ----------
def init_db():
    with sqlite3.connect("positions.db") as conn:
        cur = conn.cursor()
        
        # Таблица позиций
        cur.execute("""
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
        """)
        
        # Таблица событий для TP/SL и противоположных сигналов
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            side TEXT NOT NULL,
            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
        """)
        
        # Индекс для быстрых выборок
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_events_symbol_time
        ON trade_events(symbol, event_time DESC)
        """)
        
        # Проверка и добавление недостающих колонок
        cur.execute("PRAGMA table_info(positions)")
        cols = cur.fetchall()
        col_names = [c[1] for c in cols]
        
        new_columns = [
            ("atr", "REAL"),
            ("stop_loss", "REAL"),
            ("stop_loss_percent", "REAL"),
            ("original_quantity", "REAL"),
            ("tp1_hit", "INTEGER DEFAULT 0"),
            ("tp2_hit", "INTEGER DEFAULT 0"),
            ("tp2_count", "INTEGER DEFAULT 0"),
            ("last_known_size", "REAL DEFAULT 0"),
            ("closed_at", "TIMESTAMP"),
            ("close_reason", "TEXT"),
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in col_names:
                try:
                    cur.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
        
        conn.commit()


# ---------- Логирование событий ----------
def log_trade_event(symbol, event_type, side, details=""):
    """Логирование торговых событий (TP/SL/opposite_signal)"""
    with sqlite3.connect("positions.db") as conn:
        conn.execute(
            "INSERT INTO trade_events (symbol, event_type, side, details) VALUES (?, ?, ?, ?)",
            (symbol, event_type, side, details),
        )
        conn.commit()


# ---------- Проверка противоположных сигналов ----------
def count_opposite_signals(symbol, desired_direction):
    """
    Подсчёт противоположных сигналов за последние 30 минут.
    Возвращает количество сигналов.
    """
    cutoff_time = datetime.now() - timedelta(minutes=30)
    
    with sqlite3.connect("positions.db") as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM trade_events
            WHERE symbol = ? AND event_type = 'opposite_signal' AND side = ?
            AND event_time > datetime(?)
            """,
            (symbol, desired_direction, cutoff_time.isoformat()),
        ).fetchone()[0]
    
    return count


# ---------- Cooldown логика ----------
def can_add_to_position(symbol):
    """Проверка возможности добавления к позиции после TP"""
    if not ENABLE_NO_ADD_AFTER_TP:
        return True, ""
    
    cutoff_time = datetime.now() - timedelta(minutes=NO_ADD_AFTER_TP_MINUTES)
    
    with sqlite3.connect("positions.db") as conn:
        recent_tp = conn.execute(
            """
            SELECT event_time, side, details FROM trade_events
            WHERE symbol = ? AND event_type = 'tp'
            AND event_time > datetime(?)
            ORDER BY event_time DESC LIMIT 1
            """,
            (symbol, cutoff_time.isoformat()),
        ).fetchone()
        
        if recent_tp:
            event_time = datetime.fromisoformat(recent_tp[0])
            remaining_minutes = NO_ADD_AFTER_TP_MINUTES - int(
                (datetime.now() - event_time).total_seconds() / 60
            )
            return False, f"⏰ Добор запрещён {remaining_minutes} мин после TP"
    
    return True, ""


def can_open_position_direction(symbol, side):
    """✅ ИСПРАВЛЕНО: Проверка возможности открытия позиции после SL"""
    if not ENABLE_NO_REOPEN_AFTER_SL:
        return True, ""
    
    direction = "long" if side == "buy" else "short"
    cutoff_time = datetime.now() - timedelta(minutes=NO_REOPEN_AFTER_SL_MINUTES)
    
    with sqlite3.connect("positions.db") as conn:
        recent_sl = conn.execute(
            """
            SELECT event_time, side, details FROM trade_events
            WHERE symbol = ? AND event_type = 'sl' AND side = ?
            AND event_time > datetime(?)
            ORDER BY event_time DESC LIMIT 1
            """,
            (symbol, direction, cutoff_time.isoformat()),
        ).fetchone()
        
        if recent_sl:
            event_time = datetime.fromisoformat(recent_sl[0])
            remaining_minutes = NO_REOPEN_AFTER_SL_MINUTES - int(
                (datetime.now() - event_time).total_seconds() / 60
            )
            return False, f"⏰ {direction.upper()} запрещён {remaining_minutes} мин после SL"
    
    return True, ""


# ---------- Проверка противоположной позиции ----------
def has_opposite_position(symbol, side):
    """
    Проверка наличия противоположной позиции.
    Возвращает (has_opposite, opposite_side, opposite_size)
    """
    if TEST_MODE:
        return False, None, 0
    
    coin = symbol.replace("USDT", "")
    ex_positions = hl_api.get_open_positions()
    
    existing = next((p for p in ex_positions if p["symbol"] == coin), None)
    
    if not existing:
        return False, None, 0
    
    existing_side = existing["side"]  # "long" или "short"
    existing_size = existing["size"]
    
    # Определяем желаемое направление
    desired_direction = "long" if side == "buy" else "short"
    
    # Если есть позиция в противоположном направлении
    if existing_side != desired_direction:
        return True, existing_side, existing_size
    
    return False, None, 0


# ---------- Синхронизация с биржей ----------
def sync_positions_with_exchange():
    """✅ ИСПРАВЛЕНО: Синхронизация позиций с логированием SL"""
    if TEST_MODE:
        return
    
    ex_positions = hl_api.get_open_positions()
    ex_orders = hl_api.get_open_orders()
    
    ex_pos_dict = {p["symbol"]: p for p in ex_positions}
    open_syms = set(ex_pos_dict.keys())
    
    with sqlite3.connect("positions.db") as conn:
        cur = conn.cursor()
        
        local_positions = cur.execute(
            "SELECT id, symbol, side, quantity, last_known_size FROM positions WHERE status='open'"
        ).fetchall()
        
        # Проверяем закрытые позиции и логируем SL/TP
        for pos_id, sym_db, side, qty, last_size in local_positions:
            hl_sym = sym_db.replace("USDT", "")
            
            if hl_sym not in ex_pos_dict:
                direction = "long" if side == "buy" else "short"
                
                # Определяем причину закрытия
                pos_data = cur.execute(
                    "SELECT original_quantity, tp1_hit FROM positions WHERE id=?",
                    (pos_id,),
                ).fetchone()
                
                was_tp1_hit = pos_data[1] if pos_data else 0
                
                # Проверяем недавние TP события
                recent_tp = conn.execute(
                    """
                    SELECT event_time FROM trade_events
                    WHERE symbol = ? AND event_type = 'tp' AND side = ?
                    ORDER BY event_time DESC LIMIT 1
                    """,
                    (sym_db, direction),
                ).fetchone()
                
                sl_triggers = [o for o in ex_orders if o["symbol"] == hl_sym and o.get("tpsl") == "sl"]
                
                close_reason = None
                
                if recent_tp:
                    tp_time = datetime.fromisoformat(recent_tp[0])
                    if (datetime.now() - tp_time).total_seconds() < 300:  # 5 минут
                        if sl_triggers:
                            close_reason = "sl"
                            log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                            print(f"🔴 {sym_db}: SL сработал для {direction}")
                        else:
                            close_reason = "tp"
                            print(f"🟢 {sym_db}: Позиция закрыта по TP для {direction}")
                    elif sl_triggers:
                        close_reason = "sl"
                        log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                        print(f"🔴 {sym_db}: SL сработал для {direction}")
                    else:
                        close_reason = "manual"
                elif sl_triggers:
                    close_reason = "sl"
                    log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                    print(f"🔴 {sym_db}: SL сработал для {direction}")
                elif was_tp1_hit:
                    close_reason = "tp"
                    print(f"🟢 {sym_db}: Позиция закрыта по TP для {direction}")
                else:
                    close_reason = "manual"
                
                # ✅ КРИТИЧНО: Если закрыта по SL - логируем событие
                if close_reason == "sl":
                    # Проверяем, не было ли уже логирования
                    existing_sl = conn.execute(
                        """
                        SELECT id FROM trade_events
                        WHERE symbol = ? AND event_type = 'sl' AND side = ?
                        AND event_time > datetime('now', '-5 minutes')
                        """,
                        (sym_db, direction),
                    ).fetchone()
                    
                    if not existing_sl:
                        log_trade_event(sym_db, "sl", direction, f"Position closed by SL")
                        print(f"📝 Логирование SL события для {sym_db} {direction}")
                
                cur.execute(
                    "UPDATE positions SET status='closed', closed_at=datetime('now'), close_reason=? WHERE id=?",
                    (close_reason, pos_id),
                )
        
        # Добавляем/обновляем актуальные позиции
        for hl_sym, p in ex_pos_dict.items():
            sym_db = hl_sym + "USDT"
            side_db = "buy" if p["side"] == "long" else "sell"
            current_value = p["size"] * p["entry_price"]
            
            existing = cur.execute(
                "SELECT id FROM positions WHERE symbol=? AND side=? AND status='open'",
                (sym_db, side_db),
            ).fetchone()
            
            if not existing:
                cur.execute(
                    """
                    INSERT INTO positions (
                        symbol, side, quantity, entry_price, position_value,
                        atr, stop_loss, stop_loss_percent, original_quantity, last_known_size
                    ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                    """,
                    (
                        sym_db,
                        side_db,
                        p["size"],
                        p["entry_price"],
                        current_value,
                        p["size"],
                        p["size"],
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE positions
                    SET position_value=?, quantity=?, entry_price=?, last_known_size=?
                    WHERE id=?
                    """,
                    (
                        current_value,
                        p["size"],
                        p["entry_price"],
                        p["size"],
                        existing[0],
                    ),
                )
        
        # Удаляем триггер-ордера по закрытым позициям
        for o in ex_orders:
            coin = o["symbol"]
            if coin not in open_syms and o.get("is_trigger"):
                hl_api.cancel_order(coin, o["oid"])
        
        conn.commit()


# ---------- Расчёт размера позиции ----------
def calculate_position_size(symbol, data_dict):
    """✅ ИСПРАВЛЕНО: Расчёт размера позиции с учётом доступного баланса"""
    if TEST_MODE:
        balance = TEST_BALANCE
        available = TEST_BALANCE
    else:
        balance = hl_api.get_balance()
        available = hl_api.get_available_balance()
    
    if balance <= 0 or available <= 0:
        print(f"⚠️ Недостаточно средств: баланс ${balance:.2f}, доступно ${available:.2f}")
        return 0, 0
    
    # Используем 1H для ATR
    candles_1h = data_dict.get(symbol, {}).get("1h", [])
    atr = calculate_atr(candles_1h, 14)
    
    if atr <= 0:
        return 0, 0
    
    coin = symbol.replace("USDT", "")
    mid_price = hl_api.get_mid_price(coin) if not TEST_MODE else candles_1h[-1]["c"]
    
    if not mid_price or mid_price <= 0:
        return 0, 0
    
    # Проверка лимита позиции
    ex_positions = hl_api.get_open_positions() if not TEST_MODE else []
    existing_position = next((p for p in ex_positions if p["symbol"] == coin), None)
    
    if existing_position:
        existing_value = existing_position["size"] * mid_price
        max_position_value = balance * (MAX_TOTAL_POSITION_PERCENT / 100)
        
        if existing_value >= max_position_value:
            print(f"⚠️ {symbol}: Достигнут лимит позиции ({MAX_TOTAL_POSITION_PERCENT}%)")
            return 0, 0
    
    # ✅ КРИТИЧНО: Используем доступный баланс вместо полного
    position_value = min(available, balance) * (POSITION_SIZE_PERCENT / 100)
    quantity = position_value / mid_price
    
    # Округление
    if not TEST_MODE:
        quantity = hl_api.round_size(coin, quantity)
    else:
        quantity = round(quantity, 4)
    
    return quantity, atr


# ---------- Расчёт SL ----------
def calculate_stop_loss(entry_price, side, atr):
    """Расчёт цены Stop Loss"""
    if side == "buy":
        return entry_price - (atr * ATR_MULTIPLIER)
    else:
        return entry_price + (atr * ATR_MULTIPLIER)


# ---------- Размещение ордера ----------
def place_order(symbol, side, quantity, atr):
    """✅ ИСПРАВЛЕНО: Размещение ордера с автоматическим переворотом после 2 сигналов"""
    try:
        coin = symbol.replace("USDT", "")
        desired_direction = "long" if side == "buy" else "short"
        
        # ✅ ПРОВЕРКА: Есть ли противоположная позиция?
        has_opposite, opposite_side, opposite_size = has_opposite_position(symbol, side)
        
        if has_opposite:
            opposite_direction = "LONG" if opposite_side == "long" else "SHORT"
            new_direction = "SHORT" if opposite_side == "long" else "LONG"
            
            # Подсчитываем противоположные сигналы за последние 30 минут
            signal_count = count_opposite_signals(symbol, desired_direction)
            
            # Логируем текущий сигнал
            log_trade_event(symbol, "opposite_signal", desired_direction, f"Signal #{signal_count + 1}")
            
            print(f"⚠️ {symbol}: Позиция {opposite_direction} открыта ({opposite_size:.4f})")
            print(f"   🔄 Противоположный сигнал #{signal_count + 1}/2 для переворота в {new_direction}")
            
            if signal_count + 1 < 2:
                print(f"   ⏰ Ожидание ещё {2 - (signal_count + 1)} сигнала(ов) в течение 30 минут")
                return
            
            # ✅ ПЕРЕВОРОТ: 2 сигнала получены
            print(f"   ✅ 2 сигнала получены! Закрываем {opposite_direction} и открываем {new_direction}")
            
            # Закрываем противоположную позицию
            close_side = "sell" if opposite_side == "long" else "buy"
            result = hl_api.place_order(coin, close_side, opposite_size, "Market")
            
            if result and result.get("status") == "ok":
                print(f"✅ Позиция {opposite_direction} закрыта")
                time.sleep(2)
                
                # Закрываем в БД
                with sqlite3.connect("positions.db") as conn:
                    conn.execute(
                        "UPDATE positions SET status='closed', closed_at=datetime('now'), close_reason='flip' WHERE symbol=? AND status='open'",
                        (symbol,)
                    )
                    conn.commit()
                
                # Удаляем старые сигналы переворота
                with sqlite3.connect("positions.db") as conn:
                    conn.execute(
                        "DELETE FROM trade_events WHERE symbol=? AND event_type='opposite_signal'",
                        (symbol,)
                    )
                    conn.commit()
            else:
                print(f"❌ Не удалось закрыть {opposite_direction}, переворот отменён")
                return
        
        # ✅ КРИТИЧНО: Проверка cooldown после SL
        can_open, msg = can_open_position_direction(symbol, side)
        if not can_open:
            print(f"🚫 {symbol}: {msg}")
            return
        
        # Проверка возможности добора (только для той же стороны)
        ex_positions = hl_api.get_open_positions() if not TEST_MODE else []
        existing = next((p for p in ex_positions if p["symbol"] == coin), None)
        
        if existing:
            can_add, msg = can_add_to_position(symbol)
            if not can_add:
                print(f"🚫 {symbol}: {msg}")
                return
        
        print(f"\n📤 {side.upper()} {quantity:.6f} {coin}")
        
        if TEST_MODE:
            print(f"✅ [TEST] Ордер симулирован")
            return
        
        # Размещение ордера
        result = hl_api.place_order(coin, side, quantity, "Market")
        
        if not result or result.get("status") != "ok":
            print(f"❌ Ордер не исполнен")
            return
        
        # Ждём появления позиции
        time.sleep(2)
        
        positions = hl_api.get_open_positions()
        position = next((p for p in positions if p["symbol"] == coin), None)
        
        if not position:
            print(f"❌ Позиция не найдена после ордера")
            return
        
        entry_price = position["entry_price"]
        current_size = position["size"]
        
        # Обновление БД
        with sqlite3.connect("positions.db") as conn:
            cur = conn.cursor()
            
            existing_db = cur.execute(
                "SELECT id, original_quantity FROM positions WHERE symbol=? AND side=? AND status='open'",
                (symbol, side),
            ).fetchone()
            
            if existing_db:
                # Добор к существующей
                pos_id, orig_qty = existing_db
                new_orig_qty = orig_qty + quantity
                
                cur.execute(
                    """
                    UPDATE positions
                    SET quantity=?, entry_price=?, atr=?, original_quantity=?, last_known_size=?, position_value=?
                    WHERE id=?
                    """,
                    (current_size, entry_price, atr, new_orig_qty, current_size, current_size * entry_price, pos_id),
                )
                
                print(f"📊 {symbol}: Добор к позиции, новый размер: {current_size:.4f}")
            else:
                # Новая позиция
                cur.execute(
                    """
                    INSERT INTO positions (
                        symbol, side, quantity, entry_price, position_value, atr,
                        original_quantity, last_known_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, side, current_size, entry_price, current_size * entry_price, atr, current_size, current_size),
                )
            
            conn.commit()
        
        # Установка SL
        sl_price = calculate_stop_loss(entry_price, side, atr)
        result_sl = hl_api.set_sl_only(coin, sl_price)
        
        if result_sl and result_sl.get("status") == "ok":
            print(f"✅ SL установлен по ATR @ ${sl_price:.2f}")
        else:
            print(f"⚠️ SL не установлен")
        
        time.sleep(0.3)
        
        # Установка TP1
        if side == "buy":
            tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100)
        else:
            tp1_price = entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
        
        tp1_size = current_size * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
        
        result_tp = hl_api.set_tp_only(coin, tp1_price, tp1_size)
        
        if result_tp and result_tp.get("status") == "ok":
            print(f"✅ TP1 установлен @ ${tp1_price:.2f} ({TAKE_PROFIT_1_SIZE_PERCENT}%)")
        else:
            print(f"⚠️ TP1 не установлен")
    
    except Exception as e:
        print(f"❌ Ошибка размещения ордера: {e}")
        traceback.print_exc()


# ---------- Получение баланса ----------
def get_balance():
    """Получение баланса с учётом тестового режима"""
    if TEST_MODE:
        return TEST_BALANCE
    else:
        return hl_api.get_balance()


def get_available_balance():
    """Получение доступного баланса"""
    if TEST_MODE:
        return TEST_BALANCE
    else:
        return hl_api.get_available_balance()


# ---------- Управление позициями ----------
def check_positions():
    """✅ ИСПРАВЛЕНО: Проверка с правильным определением TP при доборе"""
    if TEST_MODE:
        return
    
    try:
        ex_positions = hl_api.get_open_positions()
        
        if not ex_positions:
            return
        
        time.sleep(2.0)
        ex_orders = hl_api.get_open_orders(force_refresh=True)
        
        with sqlite3.connect("positions.db") as conn:
            cur = conn.cursor()
            updated_count = 0
            
            for position in ex_positions:
                sym = position["symbol"]
                sym_db = sym + "USDT"
                side = position["side"]
                direction = "long" if side == "long" else "short"
                side_db = "buy" if side == "long" else "sell"
                current_size = position["size"]
                entry_price = position["entry_price"]
                
                pos_data = cur.execute(
                    """
                    SELECT id, original_quantity, tp1_hit, tp2_hit, tp2_count, atr, last_known_size, entry_price
                    FROM positions
                    WHERE symbol=? AND side=? AND status='open'
                    """,
                    (sym_db, side_db),
                ).fetchone()
                
                if not pos_data:
                    continue
                
                pos_id, orig_qty, tp1_hit, tp2_hit, tp2_count, atr, snapshot_size, db_entry_price = pos_data
                
                # Обновляем Entry Price из биржи
                if abs(entry_price - db_entry_price) > 0.01:
                    cur.execute(
                        "UPDATE positions SET entry_price=? WHERE id=?",
                        (entry_price, pos_id)
                    )
                    conn.commit()
                
                # ✅ КРИТИЧНО: При доборе обновляем original_quantity
                if current_size > orig_qty * 1.05:  # Увеличение более чем на 5%
                    print(f"📊 {sym}: Обнаружен добор, обновляем original_quantity: {orig_qty:.4f} → {current_size:.4f}")
                    cur.execute(
                        "UPDATE positions SET original_quantity=?, last_known_size=? WHERE id=?",
                        (current_size, current_size, pos_id)
                    )
                    conn.commit()
                    orig_qty = current_size
                    snapshot_size = current_size
                
                coin_orders = [o for o in ex_orders if o["symbol"] == sym and o.get("reduce_only")]
                sl_orders = [o for o in coin_orders if o.get("tpsl") == "sl"]
                tp_orders = [o for o in coin_orders if o.get("tpsl") == "tp"]
                
                needs_sl_update = False
                needs_tp_update = False
                
                # Проверка SL
                if not sl_orders:
                    needs_sl_update = True
                else:
                    if len(sl_orders) > 1:
                        needs_sl_update = True
                    else:
                        sl_order = sl_orders[0]
                        sl_size = sl_order["size"]
                        
                        if abs(sl_size - current_size) > current_size * 0.02:
                            needs_sl_update = True
                
                # Проверка TP
                if not tp_orders:
                    needs_tp_update = True
                else:
                    if len(tp_orders) > 1:
                        needs_tp_update = True
                
                # ✅ ИСПРАВЛЕНИЕ: Обнаружение срабатывания TP только при УМЕНЬШЕНИИ размера
                if orig_qty > 0 and snapshot_size > 0:
                    remaining_pct = (current_size / orig_qty) * 100
                    
                    # TP1 сработал: размер уменьшился И не было TP1 ранее
                    if not tp1_hit and current_size < snapshot_size * 0.98:  # Уменьшение более чем на 2%
                        if remaining_pct < 75:  # И осталось меньше 75%
                            log_trade_event(sym_db, "tp", direction, f"TP1 triggered")
                            cur.execute("UPDATE positions SET tp1_hit=1, last_known_size=? WHERE id=?", (current_size, pos_id))
                            conn.commit()
                            tp1_hit = 1
                            needs_tp_update = True
                            needs_sl_update = True
                            print(f"✅ {sym}: TP1 сработал ({remaining_pct:.1f}% осталось)")
                            snapshot_size = current_size
                    
                    # TP2 сработал: размер уменьшился после TP1
                    elif tp1_hit and not tp2_hit and current_size < snapshot_size * 0.98:
                        log_trade_event(sym_db, "tp", direction, f"TP2 triggered")
                        cur.execute("UPDATE positions SET tp2_hit=1, tp2_count=tp2_count+1, last_known_size=? WHERE id=?", (current_size, pos_id))
                        conn.commit()
                        tp2_hit = 1
                        tp2_count += 1
                        needs_tp_update = True
                        print(f"✅ {sym}: TP2 сработал ({remaining_pct:.1f}% осталось)")
                        snapshot_size = current_size
                    
                    # TP2 (множественные): размер уменьшился после предыдущего TP2
                    elif tp1_hit and tp2_hit and current_size < snapshot_size * 0.98:
                        log_trade_event(sym_db, "tp", direction, f"TP2 triggered again")
                        cur.execute("UPDATE positions SET tp2_count=tp2_count+1, last_known_size=? WHERE id=?", (current_size, pos_id))
                        conn.commit()
                        tp2_count += 1
                        needs_tp_update = True
                        print(f"✅ {sym}: TP2 #{tp2_count + 1} сработал ({remaining_pct:.1f}% осталось)")
                        snapshot_size = current_size
                
                # Обновляем snapshot при значительном изменении (но не считаем это TP)
                if abs(current_size - snapshot_size) > current_size * 0.05 and current_size >= snapshot_size:
                    cur.execute("UPDATE positions SET last_known_size=? WHERE id=?", (current_size, pos_id))
                    conn.commit()
                
                # Создание новых ордеров
                if needs_sl_update:
                    if tp1_hit:
                        result = hl_api.set_sl_only(sym, entry_price)
                        if result and result.get("status") == "ok":
                            updated_count += 1
                    else:
                        if atr and atr > 0:
                            sl_price = calculate_stop_loss(entry_price, side_db, atr)
                            result = hl_api.set_sl_only(sym, sl_price)
                            if result and result.get("status") == "ok":
                                updated_count += 1
                    
                    time.sleep(1.0)
                
                if needs_tp_update:
                    if not tp1_hit:
                        # TP1: 30% от original_quantity
                        tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100) if direction == "long" else entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
                        tp1_size = orig_qty * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
                        
                        result = hl_api.set_tp_only(sym, tp1_price, tp1_size)
                        if result and result.get("status") == "ok":
                            updated_count += 1
                    
                    else:
                        # TP2: 20% от текущего размера, прогрессивная цена
                        remaining_pct = (current_size / orig_qty) * 100
                        
                        if remaining_pct > 1.0:
                            tp2_number = tp2_count + 1
                            tp_offset = TAKE_PROFIT_1_PERCENT + (TAKE_PROFIT_2_PERCENT * tp2_number)
                            
                            tp2_price = entry_price * (1 + tp_offset / 100) if direction == "long" else entry_price * (1 - tp_offset / 100)
                            tp2_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
                            
                            if tp2_size >= 0.0001:
                                result = hl_api.set_tp_only(sym, tp2_price, tp2_size)
                                if result and result.get("status") == "ok":
                                    updated_count += 1
                    
                    time.sleep(1.0)
            
            if updated_count > 0:
                print(f"✅ Управление позициями: обновлено {updated_count}")
    
    except Exception as e:
        print(f"❌ Ошибка управления позициями: {e}")
        traceback.print_exc()


# ---------- Отображение позиций ----------
def display_positions_summary():
    """Отображение сводки по открытым позициям"""
    try:
        if TEST_MODE:
            print("\n" + "=" * 60)
            print("📊 ТЕСТОВЫЙ РЕЖИМ - позиции не отображаются")
            print("=" * 60)
            return
        
        ex_positions = hl_api.get_open_positions()
        ex_orders = hl_api.get_open_orders()
        
        if not ex_positions:
            print("\n" + "=" * 60)
            print("📊 НЕТ ОТКРЫТЫХ ПОЗИЦИЙ")
            print("=" * 60)
            return
        
        print("\n" + "=" * 60)
        print("📊 ОТКРЫТЫЕ ПОЗИЦИИ")
        print("=" * 60)
        
        for pos in ex_positions:
            sym = pos["symbol"]
            side = pos["side"].upper()
            size = pos["size"]
            entry = pos["entry_price"]
            pnl = pos["unrealized_pnl"]
            leverage = pos["leverage"]
            
            current_price = hl_api.get_mid_price(sym)
            if not current_price:
                continue
            
            position_value = size * current_price
            pnl_pct = (pnl / (size * entry)) * 100 if entry > 0 else 0
            pnl_sign = "+" if pnl >= 0 else ""
            
            print(f"\n{sym} {side}: {size:.4f} @ ${entry:.2f} | ${position_value:.2f} | P&L {pnl_sign}{pnl_pct:.2f}% (${pnl_sign}{pnl:.2f})")
            print(f"  Текущая цена: ${current_price:.2f} | Плечо: {leverage:.0f}x")
            
            # Отображение ордеров
            coin_orders = [o for o in ex_orders if o["symbol"] == sym]
            tp_orders = [o for o in coin_orders if o.get("tpsl") == "tp"]
            sl_orders = [o for o in coin_orders if o.get("tpsl") == "sl"]
            
            if tp_orders:
                for tp in tp_orders:
                    tp_price = tp.get("trigger_price", tp.get("limit_price", 0))
                    tp_size = tp["size"]
                    tp_pct = (tp_size / size) * 100 if size > 0 else 0
                    print(f"  └─ TP: ${tp_price:.2f} ({tp_pct:.0f}%, объём {tp_size:.4f})")
            
            if sl_orders:
                for sl in sl_orders:
                    sl_price = sl.get("trigger_price", sl.get("limit_price", 0))
                    sl_size = sl["size"]
                    sl_pct = (sl_size / size) * 100 if size > 0 else 0
                    print(f"  └─ SL: ${sl_price:.2f} ({sl_pct:.0f}%, объём {sl_size:.4f})")
        
        print("=" * 60)
    
    except Exception as e:
        print(f"❌ Ошибка отображения позиций: {e}")
        traceback.print_exc()


# ---------- main ----------
def main():
    init_db()
    
    print("=" * 60)
    print("🤖 ТОРГОВЫЙ БОТ Hyperliquid")
    print("=" * 60)
    
    if TEST_MODE:
        print("⚠️ ТЕСТОВЫЙ РЕЖИМ")
        print(f"💰 Баланс: ${TEST_BALANCE:.2f} | Доступно: ${TEST_BALANCE:.2f}")
    else:
        print("🔴 РЕАЛЬНЫЙ РЕЖИМ")
        bal = get_balance()
        available = get_available_balance()
        print(f"💰 Баланс: ${bal:.2f} | Доступно: ${available:.2f}")
        
        if bal <= 0:
            print("❌ Недостаточно средств")
            return
        
        sync_positions_with_exchange()
    
    print("=" * 60)
    print(f"📊 TP1: +{TAKE_PROFIT_1_PERCENT}% ({TAKE_PROFIT_1_SIZE_PERCENT}% позиции)")
    print(f"📊 TP2: +{TAKE_PROFIT_2_PERCENT}% ({TAKE_PROFIT_2_SIZE_PERCENT}% остатка)")
    print(f"📊 После TP1: SL → безубыток (Entry Price)")
    print(f"📊 После TP2: новый TP2 на остаток (прогрессия +{TAKE_PROFIT_2_PERCENT}%)")
    print(f"📊 Начальный SL: ATR×{ATR_MULTIPLIER}")
    
    if ENABLE_NO_ADD_AFTER_TP:
        print(f"🚫 Запрет добора после TP: {NO_ADD_AFTER_TP_MINUTES} мин")
    
    if ENABLE_NO_REOPEN_AFTER_SL:
        print(f"🚫 Запрет переоткрытия после SL: {NO_REOPEN_AFTER_SL_MINUTES} мин")
    
    print(f"🔄 Автопереворот: после 2 сигналов в течение 30 мин")
    
    print("=" * 60)
    
    while True:
        try:
            # ✅ Проверка баланса в каждом цикле
            if not TEST_MODE:
                bal = get_balance()
                available = get_available_balance()
                print(f"\n💰 Баланс: ${bal:.2f} | Доступно: ${available:.2f}")
            
            symbols = SYMBOLS[:MAX_SYMBOLS]
            data = get_market_data(symbols)
            
            valid = {
                s: d
                for s, d in data.items()
                if all(d.get(tf) for tf in ["1d", "1h", "1m"])
            }
            
            if not valid:
                time.sleep(INTERVAL)
                continue
            
            decision, reason = analyze_with_ai(valid)
            
            print(f"\n🎯 {decision} | {reason}")
            
            # Обработка решения AI
            if decision.startswith("buy_") or decision.startswith("sell_"):
                act, sym = decision.split("_", 1)
                
                if sym in valid:
                    qty, atr = calculate_position_size(sym, valid)
                    
                    if qty > 0 and atr > 0:
                        place_order(sym, act, qty, atr)
            
            # ВСЕГДА проверяем позиции
            check_positions()
            
            display_positions_summary()
            
            time.sleep(INTERVAL)
        
        except KeyboardInterrupt:
            print("\n" + "=" * 60)
            print("⏹️ ОСТАНОВКА БОТА")
            print("=" * 60)
            display_positions_summary()
            break
        
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            traceback.print_exc()
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
