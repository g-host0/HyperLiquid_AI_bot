import time
import sqlite3
from datetime import datetime
from config import *
from utils import get_market_data, analyze_with_ai, calculate_atr
from hyperliquid_api import hl_api

# ---------- База данных ----------
def init_db():
    conn = sqlite3.connect("positions.db")
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(positions)")
    cols = cur.fetchall()
    names = [c[1] for c in cols]
    
    if not names:
        conn.execute("""
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
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        extra = [
            ("atr", "REAL"),
            ("stop_loss", "REAL"),
            ("stop_loss_percent", "REAL"),
            ("original_quantity", "REAL"),
            ("tp1_hit", "INTEGER DEFAULT 0"),
            ("tp2_hit", "INTEGER DEFAULT 0"),
            ("tp2_count", "INTEGER DEFAULT 0"),
            ("last_known_size", "REAL DEFAULT 0"),
        ]
        
        for n, t in extra:
            if n not in names:
                try:
                    conn.execute(f"ALTER TABLE positions ADD COLUMN {n} {t}")
                except:
                    pass
    
    conn.commit()
    conn.close()

def sync_positions_with_exchange():
    """Синхронизация позиций с биржей"""
    if TEST_MODE:
        return
    
    ex_positions = hl_api.get_open_positions()
    ex_orders = hl_api.get_open_orders()
    
    conn = sqlite3.connect("positions.db")
    local = conn.execute(
        "SELECT id, symbol, side, quantity FROM positions WHERE status='open'"
    ).fetchall()
    
    ex_pos_dict = {p["symbol"]: p for p in ex_positions}
    open_syms = set(ex_pos_dict.keys())
    
    # Закрываем позиции которых больше нет на бирже
    for pos_id, sym_db, side, qty in local:
        hl_sym = sym_db.replace("USDT", "")
        if hl_sym not in ex_pos_dict:
            conn.execute(
                "UPDATE positions SET status='closed', profit=0.0 WHERE id=?",
                (pos_id,),
            )
    
    # Добавляем новые позиции с биржи И ОБНОВЛЯЕМ position_value
    for hl_sym, p in ex_pos_dict.items():
        sym_db = hl_sym + "USDT"
        side_db = "buy" if p["side"] == "long" else "sell"
        exist = conn.execute(
            "SELECT id FROM positions WHERE symbol=? AND side=? AND status='open'",
            (sym_db, side_db),
        ).fetchone()
        
        current_value = abs(p["size"]) * p["entry_price"]
        
        if not exist:
            conn.execute(
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
            # ОБНОВЛЯЕМ position_value для существующих позиций
            conn.execute(
                "UPDATE positions SET position_value=?, quantity=?, entry_price=? WHERE id=?",
                (current_value, abs(p["size"]), p["entry_price"], exist[0])
            )
    
    # Удаляем ордера для закрытых позиций
    for o in ex_orders:
        coin = o["symbol"]
        if coin not in open_syms:
            hl_api.cancel_order(coin, o["oid"])
    
    conn.commit()
    conn.close()

# ---------- Отчёт по позициям ----------
def display_positions_summary():
    # Получаем текущее время
    now = datetime.now()
    timestamp = now.strftime("%H:%M %d.%m.%Y")
    
    if TEST_MODE:
        print("\n" + "=" * 60)
        print(f"📊 ОТКРЫТЫЕ ПОЗИЦИИ (ТЕСТ) на {timestamp}")
        print("=" * 60)
        conn = sqlite3.connect("positions.db")
        rows = conn.execute(
            "SELECT symbol, side, quantity, entry_price FROM positions WHERE status='open'"
        ).fetchall()
        conn.close()
        
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
        for p in positions:
            sym = p["symbol"]
            side = p["side"].upper()
            size = abs(p["size"])
            entry = p["entry_price"]
            position_value = size * entry
            
            # Расчёт процента от баланса
            bal = get_balance()
            pos_pct = (position_value / bal * 100) if bal > 0 else 0
            
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
                    f"  {sym} {side}: {size:.4f} @ ${entry:.2f} (${position_value:.0f}, {pos_pct:.0f}% баланса) | "
                    f"${cur:.2f} | P&L {pnl_pct:+.2f}% (${pnl:+.2f})"
                )
            else:
                print(f"  {sym} {side}: {size:.4f} @ ${entry:.2f} (${position_value:.0f}, {pos_pct:.0f}% баланса)")
            
            trig = [o for o in orders if o["symbol"] == sym and o["is_trigger"]]
            if trig:
                for o in trig:
                    tpsl = o.get("tpsl")
                    if tpsl == "tp":
                        t = "TP"
                    elif tpsl == "sl":
                        t = "SL"
                    else:
                        t = "TRIG"
                    
                    sz = o["size"]
                    trig_px = o.get("trigger_price")
                    limit_px = o.get("limit_price")
                    pct = (sz / size * 100) if size > 0 else 0
                    
                    price_display = trig_px if trig_px else limit_px
                    
                    if price_display:
                        print(f"    └─ {t}: ${price_display:.2f} ({pct:.0f}%, объём {sz:.4f})")
                    else:
                        print(f"    └─ {t}: ({pct:.0f}%, объём {sz:.4f})")
    
    print("=" * 60 + "\n")

# ---------- Утилиты рынка ----------
def get_balance():
    return TEST_BALANCE if TEST_MODE else hl_api.get_balance()

def get_current_price(symbol):
    hl_sym = symbol.replace("USDT", "")
    try:
        mid = hl_api.get_mid_price(hl_sym)
        if mid:
            return mid
        return 0.0
    except:
        return 0.0

def get_symbol_atr(symbol, data_dict_outer):
    if symbol not in data_dict_outer or "1h" not in data_dict_outer[symbol]:
        return 0.0
    return calculate_atr(data_dict_outer[symbol]["1h"])

def calculate_position_size(symbol, data_dict_outer):
    bal = get_balance()
    if bal <= 0:
        return 0.0, 0.0
    
    price = get_current_price(symbol)
    if price <= 0:
        return 0.0, 0.0
    
    conn = sqlite3.connect("positions.db")
    row = conn.execute(
        "SELECT SUM(position_value) FROM positions WHERE symbol=? AND status='open'",
        (symbol,),
    ).fetchone()
    conn.close()
    
    existing = row[0] if row[0] else 0.0
    max_val = bal * (MAX_TOTAL_POSITION_PERCENT / 100.0)
    
    # Проверяем превышение лимита
    if existing >= max_val:
        print(f"⚠️ {symbol}: Лимит позиции достигнут (${existing:.0f} >= ${max_val:.0f})")
        return 0.0, 0.0
    
    avail = max_val - existing
    pos_val = min(avail, bal * (POSITION_SIZE_PERCENT / 100.0))
    
    # Дополнительная проверка: не превышаем баланс
    if pos_val > bal:
        print(f"⚠️ {symbol}: Размер позиции ограничен балансом (${pos_val:.0f} -> ${bal:.0f})")
        pos_val = bal
    
    qty = pos_val / price
    atr = get_symbol_atr(symbol, data_dict_outer)
    
    print(f"📊 {symbol}: Расчёт позиции - Есть: ${existing:.0f}, Доступно: ${avail:.0f}, Новая: ${pos_val:.0f}")
    
    return qty, atr

# ---------- Работа с позициями в БД ----------
def merge_positions(symbol, side, new_qty, new_price, new_atr):
    conn = sqlite3.connect("positions.db")
    row = conn.execute(
        "SELECT id, quantity, atr, original_quantity "
        "FROM positions WHERE symbol=? AND side=? AND status='open'",
        (symbol, side),
    ).fetchone()
    
    if row:
        pos_id, old_qty, old_atr, old_orig = row
        total = old_qty + new_qty
        atr = (
            (old_qty * old_atr + new_qty * new_atr) / total
            if old_atr
            else new_atr
        )
        
        # При доборе позиции увеличиваем original_quantity
        new_orig = (old_orig or old_qty) + new_qty
        
        # ОБНОВЛЯЕМ position_value!
        new_position_value = total * new_price
        
        conn.execute(
            """
            UPDATE positions
            SET quantity=?, atr=?, original_quantity=?, last_known_size=?, position_value=?
            WHERE id=?
            """,
            (
                total,
                atr,
                new_orig,
                total,
                new_position_value,
                pos_id,
            ),
        )
        
        print(f"📊 {symbol}: Добор позиции. Новый размер: {total:.4f} (было {old_qty:.4f}), стоимость: ${new_position_value:.0f}")
    else:
        position_value = new_qty * new_price
        conn.execute(
            """
            INSERT INTO positions (
                symbol, side, quantity, atr, original_quantity, last_known_size, position_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                side,
                new_qty,
                new_atr,
                new_qty,
                new_qty,
                position_value,
            ),
        )
    
    conn.commit()
    conn.close()

def calculate_stop_loss(entry_price, side, atr):
    return (
        entry_price - atr * ATR_MULTIPLIER
        if side == "buy"
        else entry_price + atr * ATR_MULTIPLIER
    )

# ---------- Размещение ордера ----------
def place_order(symbol, side, quantity, atr):
    if quantity <= 0:
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
    if res:
        print("✅ Ордер исполнен")
        merge_positions(symbol, side, quantity, price, atr)

# ---------- Проверка и управление SL/TP ----------
def check_positions():
    """Проверка позиций и динамическое управление SL/TP с учётом реальных объёмов биржи"""
    if TEST_MODE:
        return
    
    hl_api.cleanup_duplicate_orders()
    
    ex_positions = hl_api.get_open_positions()
    
    if not ex_positions:
        return
    
    time.sleep(0.5)
    
    ex_orders = hl_api.get_open_orders()
    
    conn = sqlite3.connect("positions.db")
    
    updated_count = 0
    
    for pos in ex_positions:
        sym = pos["symbol"]
        sym_db = sym + "USDT"
        current_size = abs(pos["size"])
        side = "buy" if pos["side"] == "long" else "sell"
        entry_price = pos["entry_price"]
        
        db_row = conn.execute(
            """
            SELECT id, original_quantity, atr, tp1_hit, tp2_hit, tp2_count, last_known_size
            FROM positions 
            WHERE symbol=? AND status='open' 
            ORDER BY opened_at DESC LIMIT 1
            """,
            (sym_db,),
        ).fetchone()
        
        if not db_row:
            continue
        
        pos_id, orig_qty, atr, tp1_hit, tp2_hit, tp2_count, last_known_size = db_row
        
        if not orig_qty or orig_qty == 0:
            orig_qty = current_size
            conn.execute(
                "UPDATE positions SET original_quantity=?, last_known_size=? WHERE id=?",
                (orig_qty, current_size, pos_id),
            )
            conn.commit()
        
        position_increased = False
        if last_known_size and current_size > last_known_size * 1.05:
            size_increase = current_size - last_known_size
            new_orig = orig_qty + size_increase
            
            print(f"📊 {sym}: Обнаружен добор позиции +{size_increase:.4f}")
            print(f"   Средняя цена обновлена биржей: ${entry_price:.2f}")
            
            conn.execute(
                "UPDATE positions SET original_quantity=?, last_known_size=? WHERE id=?",
                (new_orig, current_size, pos_id),
            )
            conn.commit()
            orig_qty = new_orig
            position_increased = True
            
            triggers = [o for o in ex_orders if o["symbol"] == sym and o["is_trigger"]]
            if triggers:
                print(f"   🗑️ Удаление {len(triggers)} старых ордеров для пересоздания...")
                for o in triggers:
                    hl_api.cancel_order(sym, o["oid"])
                    time.sleep(0.2)
                time.sleep(0.5)
                ex_orders = hl_api.get_open_orders()
        
        if abs(current_size - (last_known_size or 0)) > 0.01:
            conn.execute(
                "UPDATE positions SET last_known_size=? WHERE id=?",
                (current_size, pos_id),
            )
            conn.commit()
        
        remaining_pct = (current_size / orig_qty * 100) if orig_qty > 0 else 100
        
        triggers = [o for o in ex_orders if o["symbol"] == sym and o["is_trigger"]]
        
        sl_orders = [o for o in triggers if o.get("tpsl") == "sl"]
        tp_orders = [o for o in triggers if o.get("tpsl") == "tp"]
        
        needs_sl_update = False
        needs_tp_update = False
        
        if sl_orders:
            for sl_order in sl_orders:
                sl_size = sl_order["size"]
                sl_price = sl_order.get("trigger_price") or sl_order.get("limit_price")
                
                if abs(sl_size - current_size) > current_size * 0.01:
                    print(f"⚠️ {sym}: Некорректный объём SL ({sl_size:.4f} != {current_size:.4f})")
                    needs_sl_update = True
                
                if tp1_hit:
                    if sl_price and abs(sl_price - entry_price) > entry_price * 0.005:
                        print(f"⚠️ {sym}: SL не в безубытке (${sl_price:.2f} != ${entry_price:.2f})")
                        needs_sl_update = True
                else:
                    if atr and atr > 0:
                        expected_sl = calculate_stop_loss(entry_price, side, atr)
                        if sl_price and abs(sl_price - expected_sl) > expected_sl * 0.01:
                            print(f"⚠️ {sym}: Некорректная цена SL (${sl_price:.2f} != ${expected_sl:.2f})")
                            needs_sl_update = True
                
                if needs_sl_update:
                    hl_api.cancel_order(sym, sl_order["oid"])
                    time.sleep(0.3)
        else:
            needs_sl_update = True
        
        if tp_orders:
            for tp_order in tp_orders:
                tp_price = tp_order.get("trigger_price") or tp_order.get("limit_price")
                tp_size = tp_order["size"]
                
                if side == "buy":
                    if tp_price and tp_price < entry_price:
                        print(f"⚠️ {sym}: TP ниже entry (${tp_price:.2f} < ${entry_price:.2f})")
                        needs_tp_update = True
                else:
                    if tp_price and tp_price > entry_price:
                        print(f"⚠️ {sym}: TP выше entry (${tp_price:.2f} > ${entry_price:.2f})")
                        needs_tp_update = True
                
                if not tp1_hit:
                    expected_tp_size = orig_qty * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
                    if abs(tp_size - expected_tp_size) > expected_tp_size * 0.05:
                        print(f"⚠️ {sym}: Некорректный размер TP1 ({tp_size:.4f} != {expected_tp_size:.4f})")
                        needs_tp_update = True
                
                if needs_tp_update:
                    hl_api.cancel_order(sym, tp_order["oid"])
                    time.sleep(0.3)
        else:
            needs_tp_update = True
        
        if remaining_pct <= 75 and not tp1_hit:
            print(f"✅ {sym}: TP1 сработал ({remaining_pct:.1f}% осталось), SL → безубыток @ ${entry_price:.2f}")
            
            conn.execute(
                "UPDATE positions SET tp1_hit=1 WHERE id=?",
                (pos_id,),
            )
            conn.commit()
            tp1_hit = 1
            needs_sl_update = True
            needs_tp_update = True
        
        if remaining_pct <= 45 and tp1_hit and not tp2_hit:
            print(f"✅ {sym}: TP2 сработал ({remaining_pct:.1f}% осталось), установка следующего TP2")
            
            conn.execute(
                "UPDATE positions SET tp2_hit=1, tp2_count=tp2_count+1 WHERE id=?",
                (pos_id,),
            )
            conn.commit()
            tp2_hit = 1
            tp2_count += 1
            needs_tp_update = True
        
        if needs_sl_update:
            if tp1_hit:
                result = hl_api.set_sl_only(sym, entry_price)
                if result and result.get("status") == "ok":
                    print(f"   ✅ SL установлен в безубыток @ ${entry_price:.2f}")
                    updated_count += 1
            else:
                if atr and atr > 0:
                    sl_price = calculate_stop_loss(entry_price, side, atr)
                    result = hl_api.set_sl_only(sym, sl_price)
                    if result and result.get("status") == "ok":
                        print(f"   ✅ SL установлен по ATR @ ${sl_price:.2f}")
                        updated_count += 1
            time.sleep(0.5)
        
        if needs_tp_update:
            if not tp1_hit:
                if side == "buy":
                    tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100)
                else:
                    tp1_price = entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
                
                tp1_size = orig_qty * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
                result = hl_api.set_tp_only(sym, tp1_price, tp1_size)
                if result and result.get("status") == "ok":
                    print(f"   ✅ TP1 установлен @ ${tp1_price:.2f} ({TAKE_PROFIT_1_SIZE_PERCENT}%)")
                    updated_count += 1
            
            elif tp1_hit and remaining_pct > 45:
                if side == "buy":
                    tp2_price = entry_price * (1 + (TAKE_PROFIT_2_PERCENT * (tp2_count + 1)) / 100)
                else:
                    tp2_price = entry_price * (1 - (TAKE_PROFIT_2_PERCENT * (tp2_count + 1)) / 100)
                
                tp2_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
                result = hl_api.set_tp_only(sym, tp2_price, tp2_size)
                if result and result.get("status") == "ok":
                    print(f"   ✅ TP2 установлен @ ${tp2_price:.2f} ({TAKE_PROFIT_2_SIZE_PERCENT}%)")
                    updated_count += 1
            
            time.sleep(0.5)
    
    conn.close()
    
    if updated_count > 0:
        print(f"✅ Управление позициями: обновлено {updated_count}")

# ---------- Главный цикл ----------
def main():
    init_db()
    
    print("=" * 60)
    print("🤖 ТОРГОВЫЙ БОТ")
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
            
            if decision.startswith("buy_") or decision.startswith("sell_"):
                act, sym = decision.split("_", 1)
                if sym in valid:
                    qty, atr = calculate_position_size(sym, valid)
                    if qty > 0 and atr > 0:
                        place_order(sym, act, qty, atr)
            
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
            import traceback
            traceback.print_exc()
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
