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
        
        # Таблица событий для TP/SL
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
    """Логирование торговых событий (TP/SL)"""
    with sqlite3.connect("positions.db") as conn:
        conn.execute(
            "INSERT INTO trade_events (symbol, event_type, side, details) VALUES (?, ?, ?, ?)",
            (symbol, event_type, side, details),
        )
        conn.commit()


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
    """Проверка возможности открытия позиции после SL"""
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


# ---------- Синхронизация с биржей ----------
def sync_positions_with_exchange():
    """Синхронизация позиций с биржей и отслеживание SL"""
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
                
                # Получаем данные позиции из БД для проверки
                pos_data = cur.execute(
                    """
                    SELECT original_quantity, tp1_hit, close_reason FROM positions WHERE id=?
                    """,
                    (pos_id,),
                ).fetchone()
                orig_qty = pos_data[0] if pos_data else qty
                was_tp1_hit = pos_data[1] if pos_data else 0
                
                # Определяем причину закрытия: проверяем TP и SL ордера
                tp_triggers = [
                    o for o in ex_orders if o["symbol"] == hl_sym and o.get("tpsl") == "tp"
                ]
                sl_triggers = [
                    o for o in ex_orders if o["symbol"] == hl_sym and o.get("tpsl") == "sl"
                ]
                
                # Проверяем историю событий для более точного определения
                recent_tp = conn.execute(
                    """
                    SELECT event_time FROM trade_events
                    WHERE symbol = ? AND event_type = 'tp' AND side = ?
                    ORDER BY event_time DESC LIMIT 1
                    """,
                    (sym_db, direction),
                ).fetchone()
                
                # Если был недавний TP (в последние 5 минут) и нет SL-триггеров - считаем TP
                # Также проверяем: если позиция была частично закрыта (был TP1), то полное закрытие может быть TP
                if recent_tp:
                    tp_time = datetime.fromisoformat(recent_tp[0])
                    if (datetime.now() - tp_time).total_seconds() < 300:
                        if sl_triggers:
                            # Есть SL-триггеры - значит закрылось по SL
                            close_reason = "sl"
                            log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                            print(f"🔴 {sym_db}: SL сработал для {direction}")
                        else:
                            # Недавний TP и нет SL - значит закрылось по TP
                            close_reason = "tp"
                            print(f"🟢 {sym_db}: Позиция закрыта по TP для {direction}")
                    elif sl_triggers:
                        close_reason = "sl"
                        log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                        print(f"🔴 {sym_db}: SL сработал для {direction}")
                    else:
                        close_reason = "manual"
                elif sl_triggers:
                    # Есть активные SL-триггеры - значит закрылось по SL
                    close_reason = "sl"
                    log_trade_event(sym_db, "sl", direction, "Position closed by SL")
                    print(f"🔴 {sym_db}: SL сработал для {direction}")
                elif was_tp1_hit:
                    # Позиция была частично закрыта по TP, теперь закрылась полностью - вероятно TP
                    close_reason = "tp"
                    print(f"🟢 {sym_db}: Позиция закрыта по TP для {direction}")
                else:
                    close_reason = "manual"
                
                cur.execute(
                    "UPDATE positions SET status='closed', closed_at=datetime('now'), close_reason=? WHERE id=?",
                    (close_reason, pos_id),
                )
        
        # Добавляем/обновляем актуальные позиции
        for hl_sym, p in ex_pos_dict.items():
            sym_db = hl_sym + "USDT"
            side_db = "buy" if p["side"] == "long" else "sell"
            current_value = abs(p["size"]) * p["entry_price"]
            
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
                        abs(p["size"]),
                        p["entry_price"],
                        current_value,
                        abs(p["size"]),
                        abs(p["size"]),
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
                        abs(p["size"]),
                        p["entry_price"],
                        abs(p["size"]),
                        existing[0],
                    ),
                )
        
        # Удаляем триггер-ордера по закрытым позициям
        for o in ex_orders:
            coin = o["symbol"]
            if coin not in open_syms and o["is_trigger"]:
                hl_api.cancel_order(coin, o["oid"])
        
        conn.commit()


# ---------- Отображение позиций ----------
def display_positions_summary():
    now = datetime.now()
    timestamp = now.strftime("%H:%M %d.%m.%Y")
    
    if TEST_MODE:
        print("\n" + "=" * 60)
        print(f"📊 ОТКРЫТЫЕ ПОЗИЦИИ (ТЕСТ) на {timestamp}")
        print("=" * 60)
        with sqlite3.connect("positions.db") as conn:
            rows = conn.execute(
                "SELECT symbol, side, quantity, entry_price FROM positions WHERE status='open'"
            ).fetchall()
        if not rows:
            print("  Нет открытых позиций")
        else:
            for sym, side, qty, price in rows:
                print(f"  {sym} {side.upper()}: {qty:.4f} @ ${price:.2f}")
        print("=" * 60 + "\n")
        return
    
    sync_positions_with_exchange()
    
    print("\n" + "=" * 60)
    print(f"📊 ОТКРЫТЫЕ ПОЗИЦИИ на {timestamp}")
    print("=" * 60)
    
    positions = hl_api.get_open_positions()
    orders = hl_api.get_open_orders()
    
    if not positions:
        print("  Нет открытых позиций")
    else:
        # Получаем original_quantity из БД для правильного расчёта процента TP
        with sqlite3.connect("positions.db") as conn:
            orig_qty_map = {}
            for p in positions:
                sym = p["symbol"]
                sym_db = sym + "USDT"
                side_db = "buy" if p["side"] == "long" else "sell"
                row = conn.execute(
                    """
                    SELECT original_quantity FROM positions
                    WHERE symbol=? AND side=? AND status='open'
                    ORDER BY opened_at DESC LIMIT 1
                    """,
                    (sym_db, side_db),
                ).fetchone()
                if row:
                    orig_qty_map[sym] = row[0]
        
        for p in positions:
            sym = p["symbol"]
            side = p["side"].upper()
            size = abs(p["size"])
            entry = p["entry_price"]
            position_value = size * entry
            
            bal = get_balance()
            pos_pct = (position_value / bal * 100) if bal > 0 else 0
            
            # Получаем original_quantity для правильного расчёта процента TP
            orig_qty = orig_qty_map.get(sym, size)
            
            cur = hl_api.get_mid_price(sym)
            if cur:
                pnl_pct = (
                    (cur - entry) / entry * 100
                    if side == "LONG"
                    else (entry - cur) / entry * 100
                )
                pnl = (
                    size * (cur - entry)
                    if side == "LONG"
                    else size * (entry - cur)
                )
                print(
                    f"  {sym} {side}: {size:.4f} @ ${entry:.2f} "
                    f"(${position_value:.0f}, {pos_pct:.0f}% баланса) | "
                    f"${cur:.2f} | P&L {pnl_pct:+.2f}% (${pnl:+.2f})"
                )
            else:
                print(
                    f"  {sym} {side}: {size:.4f} @ ${entry:.2f} "
                    f"(${position_value:.0f}, {pos_pct:.0f}% баланса)"
                )
            
            trig = [o for o in orders if o["symbol"] == sym and o["is_trigger"]]
            if trig:
                for o in trig:
                    tpsl = o.get("tpsl")
                    if tpsl == "tp":
                        t = "TP"
                        # Процент TP считаем от original_quantity, а не от текущего размера
                        pct = (o["size"] / orig_qty * 100) if orig_qty > 0 else 0
                    elif tpsl == "sl":
                        t = "SL"
                        # Процент SL считаем от текущего размера (всегда 100% или близко)
                        pct = (o["size"] / size * 100) if size > 0 else 0
                        # Предупреждение, если объём SL значительно отличается от позиции
                        if pct > 105 or pct < 95:
                            t = "SL ⚠️"  # Маркер некорректного объёма
                    else:
                        t = "TRIG"
                        pct = (o["size"] / size * 100) if size > 0 else 0
                    
                    sz = o["size"]
                    trig_px = o.get("trigger_price")
                    limit_px = o.get("limit_price")
                    
                    # ✅ КРИТИЧНО: Для trigger ордеров приоритет trigger_price
                    # Если trigger_price есть - используем его (это правильная цена с биржи)
                    # Если нет - используем limit_px, но проверяем разумность
                    if o.get("is_trigger"):
                        if trig_px:
                            price_display = trig_px
                        elif limit_px and limit_px > 0:
                            # Проверяем разумность limit_px относительно entry
                            # Для LONG: TP должен быть выше entry, SL ниже
                            # Для SHORT: наоборот
                            price_is_valid = False
                            if side == "LONG":
                                if tpsl == "tp":
                                    price_is_valid = limit_px > entry * 1.001 and limit_px < entry * 3.0
                                else:  # sl
                                    price_is_valid = limit_px < entry * 0.999 and limit_px > entry * 0.1
                            else:  # SHORT
                                if tpsl == "tp":
                                    price_is_valid = limit_px < entry * 0.999 and limit_px > entry * 0.1
                                else:  # sl
                                    price_is_valid = limit_px > entry * 1.001 and limit_px < entry * 3.0
                            
                            if price_is_valid:
                                price_display = limit_px
                            else:
                                # limit_px неправильный (например, $100.00 для SOL)
                                price_display = None
                        else:
                            price_display = None
                    else:
                        # Для обычных ордеров используем limit_px
                        price_display = limit_px if limit_px else trig_px
                    
                    if price_display:
                        print(f"   └─ {t}: ${price_display:.2f} ({pct:.0f}%, объём {sz:.4f})")
                    else:
                        print(f"   └─ {t}: ⚠️ Цена недоступна (триггер={trig_px}, лимит={limit_px}) ({pct:.0f}%, объём {sz:.4f})")
    
    print("=" * 60 + "\n")


# ---------- Вспомогательные функции ----------
def get_balance():
    return TEST_BALANCE if TEST_MODE else hl_api.get_balance()


def get_current_price(symbol):
    hl_sym = symbol.replace("USDT", "")
    try:
        mid = hl_api.get_mid_price(hl_sym)
        if mid:
            return mid
        return 0.0
    except Exception:
        return 0.0


def get_symbol_atr(symbol, data_dict_outer):
    """Получение ATR из 1h свечей для символа"""
    if symbol not in data_dict_outer or "1h" not in data_dict_outer[symbol]:
        return 0.0
    candles_1h = data_dict_outer[symbol]["1h"]
    atr = calculate_atr(candles_1h, period=14)
    return atr


# ---------- Расчёт размера позиции ----------
def calculate_position_size(symbol, data_dict_outer):
    """Расчёт размера позиции с учётом запрета добора и лимитов"""
    bal = get_balance()
    if bal <= 0:
        return 0.0, 0.0
    
    price = get_current_price(symbol)
    if price <= 0:
        return 0.0, 0.0
    
    with sqlite3.connect("positions.db") as conn:
        existing_pos = conn.execute(
            """
            SELECT SUM(position_value), side
            FROM positions
            WHERE symbol=? AND status='open'
            GROUP BY side
            """,
            (symbol,),
        ).fetchall()
    
    total_existing = sum(row[0] for row in existing_pos if row[0]) if existing_pos else 0.0
    has_position = len(existing_pos) > 0
    
    # Если есть позиция - проверяем возможность добора
    if has_position:
        can_add, add_reason = can_add_to_position(symbol)
        if not can_add:
            print(f"🚫 {symbol}: {add_reason}")
            return 0.0, 0.0
    
    # Проверяем лимит позиции
    max_val = bal * (MAX_TOTAL_POSITION_PERCENT / 100.0)
    if total_existing >= max_val:
        print(f"⚠️ {symbol}: Лимит позиции достигнут (${total_existing:.0f} >= ${max_val:.0f})")
        return 0.0, 0.0
    
    avail = max_val - total_existing
    
    # И при открытии новой позиции, и при доборе используем лимит POSITION_SIZE_PERCENT (100% баланса)
    # но не более доступного места до общего лимита MAX_TOTAL_POSITION_PERCENT (400%)
    max_single_order = bal * (POSITION_SIZE_PERCENT / 100.0)
    pos_val = min(avail, max_single_order)
    
    if pos_val > bal:
        print(f"⚠️ {symbol}: Размер позиции ограничен балансом (${pos_val:.0f} -> ${bal:.0f})")
        pos_val = bal
    
    qty = pos_val / price
    atr = get_symbol_atr(symbol, data_dict_outer)
    
    print(
        f"📊 {symbol}: Расчёт позиции - Есть: ${total_existing:.0f}, "
        f"Доступно: ${avail:.0f}, Новая: ${pos_val:.0f}"
    )
    
    return qty, atr


# ---------- Учёт позиции в БД ----------
def merge_positions(symbol, side, new_qty, new_price, new_atr):
    with sqlite3.connect("positions.db") as conn:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT id, quantity, atr, original_quantity
            FROM positions
            WHERE symbol=? AND side=? AND status='open'
            """,
            (symbol, side),
        ).fetchone()
        
        if row:
            pos_id, old_qty, old_atr, old_orig = row
            total = old_qty + new_qty
            atr = (old_qty * old_atr + new_qty * new_atr) / total if old_atr else new_atr
            new_orig = (old_orig or old_qty) + new_qty
            new_position_value = total * new_price
            
            cur.execute(
                """
                UPDATE positions
                SET quantity=?, atr=?, original_quantity=?,
                    last_known_size=?, position_value=?
                WHERE id=?
                """,
                (total, atr, new_orig, total, new_position_value, pos_id),
            )
            
            print(
                f"📊 {symbol}: Добор позиции. Новый размер: {total:.4f} "
                f"(было {old_qty:.4f}), стоимость: ${new_position_value:.0f}"
            )
        else:
            position_value = new_qty * new_price
            cur.execute(
                """
                INSERT INTO positions (
                    symbol, side, quantity, atr,
                    original_quantity, last_known_size, position_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, side, new_qty, new_atr, new_qty, new_qty, position_value),
            )
        
        conn.commit()


def calculate_stop_loss(entry_price, side, atr):
    return (
        entry_price - atr * ATR_MULTIPLIER
        if side == "buy"
        else entry_price + atr * ATR_MULTIPLIER
    )


# ---------- Отправка ордера ----------
def place_order(symbol, side, quantity, atr):
    """Отправка ордера с проверкой направления после SL"""
    if quantity <= 0:
        return
    
    can_open, open_reason = can_open_position_direction(symbol, side)
    if not can_open:
        print(f"🚫 {symbol}: {open_reason}")
        return
    
    price = get_current_price(symbol)
    if price <= 0:
        return
    
    if TEST_MODE:
        print(f"📤 [TEST] {side.upper()} {quantity:.6f} {symbol} @ ${price:.2f}")
        merge_positions(symbol, side, quantity, price, atr)
        return
    
    hl_sym = symbol.replace("USDT", "")
    print(f"📤 {side.upper()} {quantity:.6f} {hl_sym}")
    
    res = hl_api.place_order(hl_sym, side, quantity, "Market")
    
    # Проверяем, что ордер действительно исполнен
    if res and res.get("status") == "ok":
        print(f"📋 Ответ API: {res}")  # Логирование для отладки
        statuses = res.get("response", {}).get("data", {}).get("statuses", [])
        if statuses:
            order_status = statuses[0]
            # Для market ордеров с IOC ожидаем "filled" (исполнен)
            if "filled" in order_status:
                filled_data = order_status.get("filled", {})
                filled_size = filled_data.get("totalSz", "0")
                avg_price = filled_data.get("avgPx", "0")
                print(f"✅ Ордер исполнен: {filled_size} @ ${avg_price}")
                merge_positions(symbol, side, quantity, price, atr)
                # После добора TP/SL будут пересозданы в следующем цикле check_positions()
            elif "resting" in order_status:
                print("⚠️ Ордер размещен, но не исполнен (ожидает исполнения)")
            elif "error" in order_status:
                error_msg = order_status.get("error", "Неизвестная ошибка")
                print(f"❌ Ошибка ордера: {error_msg}")
            else:
                print(f"⚠️ Неожиданный статус ордера: {order_status}")
        else:
            print("⚠️ Нет информации о статусе ордера в ответе")
    elif res:
        print(f"⚠️ Ордер не принят: {res}")
    else:
        print("❌ Не удалось отправить ордер (res = None)")


# ---------- ГЛАВНАЯ ФУНКЦИЯ: Управление TP/SL ----------
def check_positions():
    """
    Полный контроль SL/TP для открытых позиций
    """
    if TEST_MODE:
        return
    
    import builtins
    _real_print = builtins.print

    def print(*args, **kwargs):
        # Пропускаем важные логи: успехи, предупреждения, ошибки
        text = " ".join(str(a) for a in args)
        if any(mark in text for mark in ("✅", "⚠️", "❌")):
            _real_print(text, **kwargs)
    
    print("\n🔍 Проверка позиций и ордеров...")
    
    hl_api.cleanup_duplicate_orders()
    
    ex_positions = hl_api.get_open_positions()
    if not ex_positions:
        print("  ℹ️ Нет открытых позиций на бирже")
        return
    
    print(f"  ℹ️ Найдено позиций: {len(ex_positions)}")
    
    time.sleep(0.3)
    ex_orders = hl_api.get_open_orders()
    
    with sqlite3.connect("positions.db") as conn:
        cur = conn.cursor()
        updated_count = 0
        
        for pos in ex_positions:
            sym = pos["symbol"]
            sym_db = sym + "USDT"
            current_size = abs(pos["size"])
            side = "buy" if pos["side"] == "long" else "sell"  # side для БД
            entry_price = pos["entry_price"]
            direction = pos["side"]  # "long" или "short" - направление позиции
            
            print(f"\n  📌 Обработка {sym} {direction.upper()}:")
            
            # Получаем данные из БД
            db_row = cur.execute(
                """
                SELECT id, original_quantity, atr, tp1_hit, tp2_hit, tp2_count, last_known_size, entry_price
                FROM positions
                WHERE symbol=? AND status='open'
                ORDER BY opened_at DESC LIMIT 1
                """,
                (sym_db,),
            ).fetchone()
            
            if not db_row:
                print(f"    ⚠️ Позиция не найдена в БД")
                continue
            
            pos_id, orig_qty, atr, tp1_hit, tp2_hit, tp2_count, last_known_size, db_entry_price = db_row
            
            # ✅ КРИТИЧНО: Обновляем entry_price в БД из биржи (источник истины)
            # При доборе позиции биржа автоматически пересчитывает среднюю цену входа
            db_entry_price_val = db_entry_price if db_entry_price is not None else 0
            if abs(entry_price - db_entry_price_val) > 0.01:
                db_entry_str = f"${db_entry_price:.2f}" if db_entry_price is not None else "None"
                print(f"    🔄 Обновление entry_price: БД={db_entry_str} → Биржа=${entry_price:.2f}")
                cur.execute(
                    "UPDATE positions SET entry_price=?, position_value=? WHERE id=?",
                    (entry_price, current_size * entry_price, pos_id),
                )
                conn.commit()
                print(f"    ✅ entry_price обновлён в БД: ${entry_price:.2f}")
            
            print(f"    ℹ️ БД: orig_qty={orig_qty}, atr={atr}, tp1_hit={tp1_hit}, entry_price=${entry_price:.2f}")
            
            # Если ATR не задан, получаем из рыночных данных (1h свечи)
            if not atr or atr == 0:
                print(f"    🔄 ATR отсутствует, получаю из 1h свечей...")
                try:
                    market_data = get_market_data([sym_db])
                    if sym_db in market_data and "1h" in market_data[sym_db]:
                        candles_1h = market_data[sym_db]["1h"]
                        atr = calculate_atr(candles_1h, period=14)
                        if atr > 0:
                            cur.execute(
                                "UPDATE positions SET atr=? WHERE id=?",
                                (atr, pos_id),
                            )
                            conn.commit()
                            print(f"    ✅ ATR установлен: {atr:.2f}")
                except Exception as e:
                    print(f"    ❌ Ошибка получения ATR: {e}")
            
            # Инициализация original_quantity
            if not orig_qty or orig_qty == 0:
                orig_qty = current_size
                cur.execute(
                    "UPDATE positions SET original_quantity=?, last_known_size=? WHERE id=?",
                    (orig_qty, current_size, pos_id),
                )
                conn.commit()
                print(f"    ✅ original_quantity инициализирован: {orig_qty}")
            
            # Инициализируем флаги обновления ордеров
            needs_sl_update = False
            needs_tp_update = False
            
            # Обнаружение добора - проверяем увеличение размера позиции
            # Используем более чувствительный порог (3% вместо 5%) для раннего обнаружения
            if last_known_size and current_size > last_known_size * 1.03:
                size_increase = current_size - last_known_size
                new_orig = orig_qty + size_increase
                print(f"    📊 Обнаружен добор +{size_increase:.4f} (было {last_known_size:.4f}, стало {current_size:.4f}, увеличение {size_increase/last_known_size*100:.1f}%)")
                cur.execute(
                    "UPDATE positions SET original_quantity=?, last_known_size=? WHERE id=?",
                    (new_orig, current_size, pos_id),
                )
                conn.commit()
                orig_qty = new_orig
                # После добора нужно пересоздать TP/SL на новый размер
                needs_sl_update = True
                needs_tp_update = True
                print(f"    ⚠️ После добора нужно пересоздать TP/SL ордера на новый размер {current_size:.4f}")
            
            # Обновляем last_known_size
            if abs(current_size - (last_known_size or 0)) > 0.01:
                cur.execute(
                    "UPDATE positions SET last_known_size=? WHERE id=?",
                    (current_size, pos_id),
                )
                conn.commit()
            
            remaining_pct = (current_size / orig_qty * 100) if orig_qty > 0 else 100
            
            # Получаем текущие ордера
            triggers = [o for o in ex_orders if o["symbol"] == sym and o["is_trigger"]]
            sl_orders = [o for o in triggers if o.get("tpsl") == "sl"]
            tp_orders = [o for o in triggers if o.get("tpsl") == "tp"]
            
            print(f"    ℹ️ Текущие ордера: SL={len(sl_orders)}, TP={len(tp_orders)}")
            
            # Если флаги не установлены при доборе, проверяем наличие ордеров
            if not needs_sl_update:
                needs_sl_update = len(sl_orders) == 0
            if not needs_tp_update:
                needs_tp_update = len(tp_orders) == 0
            
            # Если TP1 сработал и нет TP ордеров - нужно создать следующий TP2
            if tp1_hit and len(tp_orders) == 0 and remaining_pct > 1.0:
                print(f"    ⚠️ TP1 сработал, но нет TP ордеров - нужно создать следующий TP2 (остаток {remaining_pct:.1f}%, tp2_count={tp2_count})")
                needs_tp_update = True
            
            # Проверка SL - проверяем ВСЕ SL ордера
            if sl_orders:
                # Проверяем каждый SL ордер на корректность
                for sl_order in sl_orders:
                    sl_size = sl_order["size"]
                    sl_price = sl_order.get("trigger_price") or sl_order.get("limit_price")
                    
                    # Проверка объёма - строгая проверка: допуск 1% ИЛИ абсолютная разница > 0.01
                    # SL должен быть на весь текущий размер позиции
                    volume_diff = abs(sl_size - current_size)
                    volume_diff_pct = (volume_diff / current_size * 100) if current_size > 0 else 0
                    print(f"    🔍 Проверка SL: объём ордера={sl_size:.4f}, позиция={current_size:.4f}, разница={volume_diff:.4f} ({volume_diff_pct:.2f}%)")
                    # Проверяем как процентную разницу (1%), так и абсолютную (0.01 для ETH/BTC)
                    if volume_diff > current_size * 0.01 or volume_diff > 0.01:
                        print(f"    ⚠️ Некорректный объём SL ({sl_size:.4f} != {current_size:.4f}, разница {volume_diff:.4f} = {volume_diff_pct:.1f}%)")
                        needs_sl_update = True
                        break  # Достаточно одного некорректного ордера
                    else:
                        print(f"    ✅ Объём SL корректен")
                
                # Если объёмы корректны, проверяем цены (только для первого ордера)
                if not needs_sl_update and sl_orders:
                    sl_order = sl_orders[0]
                    sl_price = sl_order.get("trigger_price") or sl_order.get("limit_price")
                    
                    if tp1_hit:
                        if sl_price and abs(sl_price - entry_price) > entry_price * 0.005:
                            print(f"    ⚠️ SL не в безубытке (${sl_price:.2f} != ${entry_price:.2f})")
                            needs_sl_update = True
                    else:
                        if atr and atr > 0:
                            expected_sl = calculate_stop_loss(entry_price, side, atr)
                            if sl_price and abs(sl_price - expected_sl) > expected_sl * 0.01:
                                print(f"    ⚠️ Некорректная цена SL (${sl_price:.2f} != ${expected_sl:.2f})")
                                needs_sl_update = True
                
                # Если найдено несколько SL ордеров, оставляем только один (самый свежий)
                if len(sl_orders) > 1:
                    print(f"    ⚠️ Найдено {len(sl_orders)} SL ордеров, нужно оставить один")
                    needs_sl_update = True
            
            # Проверка TP
            if tp_orders:
                tp_order = tp_orders[0]
                tp_price = tp_order.get("trigger_price") or tp_order.get("limit_price")
                tp_size = tp_order["size"]
                
                # Проверка корректности цены/объёма TP в соответствии со стратегией
                if tp1_hit:
                    # ожидаемый TP2 = TP1 + n*TP2, где n = tp2_count + 1 (следующий TP2)
                    tp_offset = TAKE_PROFIT_1_PERCENT + TAKE_PROFIT_2_PERCENT * (tp2_count + 1)
                    expected_price = (
                        entry_price * (1 + tp_offset / 100)
                        if direction == "long"
                        else entry_price * (1 - tp_offset / 100)
                    )
                    expected_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
                    
                    print(f"    🔍 Проверка TP2: текущий tp2_count={tp2_count}, ожидаемый offset={tp_offset:.2f}%, цена=${expected_price:.2f}, размер={expected_size:.4f}")
                    
                    if tp_price and abs(tp_price - expected_price) > expected_price * 0.01:
                        print(
                            f"    ⚠️ TP2 цена некорректна (${tp_price:.2f} != ${expected_price:.2f}, разница {abs(tp_price - expected_price):.2f})"
                        )
                        needs_tp_update = True
                    tp2_size_diff = abs(tp_size - expected_size)
                    tp2_size_diff_pct = (tp2_size_diff / expected_size * 100) if expected_size > 0 else 0
                    # Проверяем как процентную разницу (1%), так и абсолютную (0.01)
                    if tp2_size_diff > expected_size * 0.01 or tp2_size_diff > 0.01:
                        print(
                            f"    ⚠️ TP2 размер некорректен ({tp_size:.4f} != {expected_size:.4f}, разница {tp2_size_diff:.4f} = {tp2_size_diff_pct:.1f}%)"
                        )
                        needs_tp_update = True
                    if not needs_tp_update:
                        print(f"    ✅ TP2 корректен (${tp_price:.2f}, объём {tp_size:.4f})")

                # ✅ ИСПРАВЛЕНИЕ: Проверяем направление TP относительно позиции
                if direction == "long":  # LONG: TP должен быть выше entry
                    if tp_price and tp_price < entry_price:
                        print(f"    ⚠️ TP ниже entry для LONG (${tp_price:.2f} < ${entry_price:.2f})")
                        needs_tp_update = True
                else:  # SHORT: TP должен быть ниже entry
                    if tp_price and tp_price > entry_price:
                        print(f"    ⚠️ TP выше entry для SHORT (${tp_price:.2f} > ${entry_price:.2f})")
                        needs_tp_update = True
                
                if not tp1_hit:
                    expected_tp_size = orig_qty * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
                    tp_size_diff = abs(tp_size - expected_tp_size)
                    tp_size_diff_pct = (tp_size_diff / expected_tp_size * 100) if expected_tp_size > 0 else 0
                    print(f"    🔍 Проверка TP1: объём ордера={tp_size:.4f}, ожидаемый={expected_tp_size:.4f} (30% от orig_qty={orig_qty:.4f}), разница={tp_size_diff:.4f} ({tp_size_diff_pct:.2f}%)")
                    # Проверяем как процентную разницу (1%), так и абсолютную (0.01)
                    if tp_size_diff > expected_tp_size * 0.01 or tp_size_diff > 0.01:
                        print(f"    ⚠️ Некорректный размер TP1 ({tp_size:.4f} != {expected_tp_size:.4f}, разница {tp_size_diff:.4f} = {tp_size_diff_pct:.1f}%)")
                        needs_tp_update = True
                    else:
                        print(f"    ✅ Размер TP1 корректен")
            
            # Проверка срабатывания TP1: проверяем уменьшение размера позиции
            # Важно: не срабатывает, если позиция закрылась по SL (проверяем наличие SL ордеров)
            if not tp1_hit and remaining_pct <= 75:
                # Если есть SL ордер на весь размер - значит это не TP, а возможно SL
                # Но если размер уменьшился и нет активных SL - значит это TP
                if len(sl_orders) == 0 or (sl_orders and sl_orders[0]["size"] < current_size * 0.95):
                    print(f"    ✅ TP1 сработал ({remaining_pct:.1f}% осталось)")
                    log_trade_event(sym_db, "tp", direction, f"TP1 triggered, {remaining_pct:.1f}% remaining")
                    cur.execute("UPDATE positions SET tp1_hit=1 WHERE id=?", (pos_id,))
                    conn.commit()
                    tp1_hit = 1
                    needs_sl_update = True
                    needs_tp_update = True
            
            # Проверка срабатывания TP2 (каскадное, по доле из config)
            if tp1_hit:
                base_after_tp1_pct = 100 - TAKE_PROFIT_1_SIZE_PERCENT  # остаток после TP1 (например 70%)
                tp2_fraction = 1 - (TAKE_PROFIT_2_SIZE_PERCENT / 100.0)  # доля остатка после каждого TP2
                target_after_next_tp2 = base_after_tp1_pct * (tp2_fraction ** (tp2_count + 1))
                # небольшая дельта, чтобы учесть округление объёмов
                print(f"    🔍 Проверка TP2: tp2_count={tp2_count}, target={target_after_next_tp2:.2f}%, текущий остаток={remaining_pct:.2f}%")
                if remaining_pct <= target_after_next_tp2 + 0.3:
                    print(f"    ✅ TP2 сработал ({remaining_pct:.1f}% осталось, цель была {target_after_next_tp2:.2f}%)")
                    log_trade_event(sym_db, "tp", direction, f"TP2 triggered, {remaining_pct:.1f}% remaining")
                    cur.execute(
                        "UPDATE positions SET tp2_hit=1, tp2_count=tp2_count+1 WHERE id=?",
                        (pos_id,),
                    )
                    conn.commit()
                    tp2_hit = 1
                    tp2_count += 1
                    needs_tp_update = True
                    needs_sl_update = True  # пересоздать SL на остаток (в б/у)
                    print(f"    📊 TP2 счётчик обновлён: tp2_count={tp2_count}, следующий TP2 будет на уровне {TAKE_PROFIT_1_PERCENT + TAKE_PROFIT_2_PERCENT * (tp2_count + 1):.2f}%")
            
            # Удаление старых ордеров
            if needs_sl_update and sl_orders:
                sizes_str = ", ".join([f"{o['size']:.4f}" for o in sl_orders])
                print(f"    🗑️ Удаление {len(sl_orders)} старых SL ордеров (объёмы: {sizes_str})...")
                for sl_order in sl_orders:
                    result = hl_api.cancel_order(sym, sl_order["oid"])
                    if result and result.get("status") == "ok":
                        print(f"      ✅ Удалён SL ордер {sl_order['oid']} (объём {sl_order['size']:.4f})")
                    else:
                        print(f"      ⚠️ Не удалось удалить SL ордер {sl_order['oid']}")
                time.sleep(0.1)
            
            if needs_tp_update and tp_orders:
                print(f"    🗑️ Удаление старых TP ордеров...")
                for tp_order in tp_orders:
                    hl_api.cancel_order(sym, tp_order["oid"])
                time.sleep(0.1)
            
            # Создание SL
            if needs_sl_update:
                print(f"    🔄 Создание SL...")
                if tp1_hit:
                    result = hl_api.set_sl_only(sym, entry_price)
                    if result and result.get("status") == "ok":
                        response_data = result.get("response", {}).get("data", {})
                        statuses = response_data.get("statuses", [])
                        if statuses and "error" not in statuses[0]:
                            print(f"    ✅ SL установлен в безубыток @ ${entry_price:.2f}")
                            updated_count += 1
                        else:
                            error = statuses[0].get("error", "Unknown error")
                            print(f"    ❌ Ошибка создания SL: {error}")
                else:
                    if atr and atr > 0:
                        sl_price = calculate_stop_loss(entry_price, side, atr)
                        result = hl_api.set_sl_only(sym, sl_price)
                        if result and result.get("status") == "ok":
                            response_data = result.get("response", {}).get("data", {})
                            statuses = response_data.get("statuses", [])
                            if statuses and "error" not in statuses[0]:
                                print(f"    ✅ SL установлен по ATR @ ${sl_price:.2f} (ATR={atr:.4f} × {ATR_MULTIPLIER})")
                                updated_count += 1
                            else:
                                error = statuses[0].get("error", "Unknown error")
                                print(f"    ❌ Ошибка создания SL: {error}")
                    else:
                        print(f"    ⚠️ ATR отсутствует, пропускаю SL")
                
                time.sleep(0.2)
            
            # Создание TP
            if needs_tp_update:
                print(f"    🔄 Создание TP... (tp1_hit={tp1_hit}, tp2_count={tp2_count}, остаток={remaining_pct:.1f}%)")
                if not tp1_hit:
                    # ✅ ИСПРАВЛЕНИЕ: TP расчёт по направлению позиции
                    if direction == "long":
                        tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100)
                    else:  # short
                        tp1_price = entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
                    
                    tp1_size = orig_qty * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
                    result = hl_api.set_tp_only(sym, tp1_price, tp1_size)
                    
                    if result and result.get("status") == "ok":
                        response_data = result.get("response", {}).get("data", {})
                        statuses = response_data.get("statuses", [])
                        if statuses and "error" not in statuses[0]:
                            print(f"    ✅ TP1 установлен @ ${tp1_price:.2f} ({TAKE_PROFIT_1_SIZE_PERCENT}%)")
                            updated_count += 1
                        else:
                            error = statuses[0].get("error", "Unknown error")
                            print(f"    ❌ Ошибка создания TP1: {error}")
                
                elif tp1_hit:
                    # Каскад TP2: уровни идут после TP1, т.е. TP1 + n*TP2
                    # tp2_count - это количество уже сработавших TP2
                    # tp2_number - это номер следующего TP2 для создания (1, 2, 3...)
                    tp2_number = tp2_count + 1
                    tp_offset = TAKE_PROFIT_1_PERCENT + TAKE_PROFIT_2_PERCENT * tp2_number
                    print(f"    📊 Расчёт TP2: tp2_count={tp2_count} (сработало), tp2_number={tp2_number} (создаём), offset={tp_offset:.2f}%")
                    if direction == "long":
                        tp2_price = entry_price * (1 + tp_offset / 100)
                    else:  # short
                        tp2_price = entry_price * (1 - tp_offset / 100)
                    
                    tp2_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
                    
                    print(f"    🔄 Создание TP2 #{tp2_number}: offset={tp_offset:.2f}%, цена=${tp2_price:.2f}, размер={tp2_size:.4f}, остаток={remaining_pct:.1f}%")
                    
                    # Проверяем, что размер позиции достаточен для создания TP2
                    # Минимальный размер TP2 должен быть не менее 0.0001 (защита от слишком маленьких ордеров)
                    if tp2_size < 0.0001 or current_size < 0.0001:
                        print(f"    ⚠️ Позиция слишком мала для TP2 (размер: {current_size:.6f}, TP2: {tp2_size:.6f})")
                    elif remaining_pct < 1.0:
                        print(f"    ⚠️ Осталось менее 1% позиции ({remaining_pct:.2f}%), пропускаем создание TP2")
                    else:
                        result = hl_api.set_tp_only(sym, tp2_price, tp2_size)
                        
                        if result and result.get("status") == "ok":
                            response_data = result.get("response", {}).get("data", {})
                            statuses = response_data.get("statuses", [])
                            if statuses and "error" not in statuses[0]:
                                print(f"    ✅ TP2 #{tp2_number} установлен @ ${tp2_price:.2f} ({TAKE_PROFIT_2_SIZE_PERCENT}%, объём {tp2_size:.4f}, остаток {remaining_pct:.1f}%)")
                                updated_count += 1
                            else:
                                error = statuses[0].get("error", "Unknown error")
                                print(f"    ❌ Ошибка создания TP2 #{tp2_number}: {error}")
                        else:
                            print(f"    ⚠️ Не удалось создать TP2 #{tp2_number} (ответ API: {result})")
                
                time.sleep(0.2)
        
        if updated_count > 0:
            print(f"\n✅ Управление позициями: обновлено {updated_count}")
        else:
            print(f"\n  ℹ️ Все ордера актуальны")


# ---------- main ----------
def main():
    init_db()
    
    print("=" * 60)
    print("🤖 ТОРГОВЫЙ БОТ Hyperliquid")
    print("=" * 60)
    
    if TEST_MODE:
        print("⚠️ ТЕСТОВЫЙ РЕЖИМ")
        print(f"💰 Баланс: ${TEST_BALANCE:.2f}")
    else:
        print("🔴 РЕАЛЬНЫЙ РЕЖИМ")
        bal = get_balance()
        print(f"💰 Баланс: ${bal:.2f}")
        if bal <= 0:
            print("❌ Недостаточно средств")
            return
    
    sync_positions_with_exchange()
    
    print("=" * 60)
    print(f"📊 TP1: +{TAKE_PROFIT_1_PERCENT}% ({TAKE_PROFIT_1_SIZE_PERCENT}% позиции)")
    print(f"📊 TP2: +{TAKE_PROFIT_2_PERCENT}% ({TAKE_PROFIT_2_SIZE_PERCENT}% остатка)")
    print(f"📊 После TP1: SL → безубыток (Entry Price)")
    print(f"📊 После TP2: новый TP2 на остаток")
    print(f"📊 Начальный SL: ATR×{ATR_MULTIPLIER}")
    if ENABLE_NO_ADD_AFTER_TP:
        print(f"🔒 Запрет добора после TP: {NO_ADD_AFTER_TP_MINUTES} мин")
    if ENABLE_NO_REOPEN_AFTER_SL:
        print(f"🔒 Запрет переоткрытия после SL: {NO_REOPEN_AFTER_SL_MINUTES} мин")
    print("=" * 60)
    
    while True:
        try:
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
            print(f"🎯 {decision} | {reason}")
            
            # Обработка решения AI
            if decision.startswith("buy_") or decision.startswith("sell_"):
                act, sym = decision.split("_", 1)
                if sym in valid:
                    qty, atr = calculate_position_size(sym, valid)
                    if qty > 0 and atr > 0:
                        place_order(sym, act, qty, atr)
            
            # ✅ ВСЕГДА проверяем позиции
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
