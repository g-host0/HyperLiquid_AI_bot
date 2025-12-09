import time
import sqlite3
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
    """Синхронизация позиций и БД"""
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
    
    for pos_id, sym_db, side, qty in local:
        hl_sym = sym_db.replace("USDT", "")
        if hl_sym not in ex_pos_dict:
            conn.execute(
                "UPDATE positions SET status='closed', profit=0.0 WHERE id=?",
                (pos_id,),
            )
    
    for hl_sym, p in ex_pos_dict.items():
        sym_db = hl_sym + "USDT"
        side_db = "buy" if p["side"] == "long" else "sell"
        exist = conn.execute(
            "SELECT id FROM positions WHERE symbol=? AND side=? AND status='open'",
            (sym_db, side_db),
        ).fetchone()
        
        if not exist:
            conn.execute(
                """
                INSERT INTO positions (
                    symbol, side, quantity, entry_price, position_value,
                    atr, stop_loss, stop_loss_percent, original_quantity
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)
                """,
                (
                    sym_db,
                    side_db,
                    abs(p["size"]),
                    p["entry_price"],
                    abs(p["size"]) * p["entry_price"],
                    abs(p["size"]),
                ),
            )
    
    for o in ex_orders:
        coin = o["symbol"]
        if coin not in open_syms:
            hl_api.cancel_order(coin, o["oid"])
    
    conn.commit()
    conn.close()

# ---------- Отчёт по позициям ----------
def display_positions_summary():
    if TEST_MODE:
        print("\n" + "=" * 60)
        print("📊 ОТКРЫТЫЕ ПОЗИЦИИ (ТЕСТ)")
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
    print("📊 ОТКРЫТЫЕ ПОЗИЦИИ")
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
                    f"  {sym} {side}: {size:.4f} @ ${entry:.2f} | "
                    f"${cur:.2f} | P&L {pnl_pct:+.2f}% (${pnl:+.2f})"
                )
            else:
                print(f"  {sym} {side}: {size:.4f} @ ${entry:.2f}")
            
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
                        print(f"    └─ {t}: ${price_display:.2f} ({pct:.0f}%)")
                    else:
                        print(f"    └─ {t}: ({pct:.0f}%)")
    
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
    
    if existing >= max_val:
        return 0.0, 0.0
    
    avail = max_val - existing
    pos_val = min(avail, bal * (POSITION_SIZE_PERCENT / 100.0))
    qty = pos_val / price
    atr = get_symbol_atr(symbol, data_dict_outer)
    
    return qty, atr

# ---------- Работа с позициями в БД ----------
def merge_positions(symbol, side, new_qty, new_price, new_atr):
    conn = sqlite3.connect("positions.db")
    row = conn.execute(
        "SELECT id, quantity, entry_price, atr, original_quantity "
        "FROM positions WHERE symbol=? AND side=? AND status='open'",
        (symbol, side),
    ).fetchone()
    
    if row:
        pos_id, old_qty, old_price, old_atr, old_orig = row
        total = old_qty + new_qty
        avg_price = (old_qty * old_price + new_qty * new_price) / total
        atr = (
            (old_qty * old_atr + new_qty * new_atr) / total
            if old_atr
            else new_atr
        )
        
        sl = calculate_stop_loss(avg_price, side, atr)
        sl_pct = abs((sl - avg_price) / avg_price * 100)
        
        conn.execute(
            """
            UPDATE positions
            SET quantity=?, entry_price=?, position_value=?,
                atr=?, stop_loss=?, stop_loss_percent=?, original_quantity=?
            WHERE id=?
            """,
            (
                total,
                avg_price,
                total * avg_price,
                atr,
                sl,
                sl_pct,
                (old_orig or old_qty) + new_qty,
                pos_id,
            ),
        )
    else:
        val = new_qty * new_price
        sl = calculate_stop_loss(new_price, side, new_atr)
        sl_pct = abs((sl - new_price) / new_price * 100)
        
        conn.execute(
            """
            INSERT INTO positions (
                symbol, side, quantity, entry_price, position_value,
                atr, stop_loss, stop_loss_percent, original_quantity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                side,
                new_qty,
                new_price,
                val,
                new_atr,
                sl,
                sl_pct,
                new_qty,
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

# ---------- Проверка и установка SL/TP ----------
def check_positions():
    """Проверка и установка SL/TP"""
    if TEST_MODE:
        return
    
    hl_api.cleanup_duplicate_orders()
    
    ex_positions = hl_api.get_open_positions()
    
    if not ex_positions:
        return
    
    time.sleep(0.5)
    
    ex_orders = hl_api.get_open_orders()
    
    conn = sqlite3.connect("positions.db")
    
    checked_count = 0
    for pos in ex_positions:
        sym = pos["symbol"]
        sym_db = sym + "USDT"
        current_size = abs(pos["size"])
        side = "buy" if pos["side"] == "long" else "sell"
        entry_price = pos["entry_price"]
        
        db_row = conn.execute(
            """
            SELECT id, original_quantity, atr, tp1_hit, tp2_hit
            FROM positions 
            WHERE symbol=? AND status='open' 
            ORDER BY opened_at DESC LIMIT 1
            """,
            (sym_db,),
        ).fetchone()
        
        if not db_row:
            continue
        
        pos_id, orig_qty, atr, tp1_hit, tp2_hit = db_row
        
        if orig_qty and current_size < orig_qty * 0.95:
            if not tp1_hit:
                conn.execute(
                    "UPDATE positions SET tp1_hit=1 WHERE id=?",
                    (pos_id,),
                )
                conn.commit()
                tp1_hit = 1
        
        triggers = [o for o in ex_orders if o["symbol"] == sym and o["is_trigger"]]
        
        sl_orders = [o for o in triggers if o.get("tpsl") == "sl"]
        tp_orders = [o for o in triggers if o.get("tpsl") == "tp"]
        
        has_sl = len(sl_orders) > 0
        has_tp = len(tp_orders) > 0
        
        if not atr or atr == 0:
            atr = 0.0
        
        if not has_sl:
            if atr > 0:
                sl_price = calculate_stop_loss(entry_price, side, atr)
                result = hl_api.set_sl_only(sym, sl_price)
                if result and result.get("status") == "ok":
                    checked_count += 1
                time.sleep(0.5)
        
        if not has_tp and not tp1_hit:
            if side == "buy":
                tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100)
            else:
                tp1_price = entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
            
            tp1_size = current_size * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
            result = hl_api.set_tp_only(sym, tp1_price, tp1_size)
            if result and result.get("status") == "ok":
                checked_count += 1
            time.sleep(0.5)
        
        if tp1_hit and not tp2_hit and not has_tp:
            if side == "buy":
                tp2_price = entry_price * (1 + TAKE_PROFIT_2_PERCENT / 100)
            else:
                tp2_price = entry_price * (1 - TAKE_PROFIT_2_PERCENT / 100)
            
            tp2_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
            result = hl_api.set_tp_only(sym, tp2_price, tp2_size)
            if result and result.get("status") == "ok":
                checked_count += 1
                conn.execute(
                    "UPDATE positions SET tp2_hit=0 WHERE id=?",
                    (pos_id,),
                )
                conn.commit()
            time.sleep(0.5)
    
    conn.close()
    
    if checked_count > 0:
        print(f"✅ Проверка позиций: обработано {checked_count}")

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
    print(f"📊 TP1: +{TAKE_PROFIT_1_PERCENT}% ({TAKE_PROFIT_1_SIZE_PERCENT}%)")
    print(f"📊 TP2: +{TAKE_PROFIT_2_PERCENT}% ({TAKE_PROFIT_2_SIZE_PERCENT}%)")
    print(f"📊 SL: ATR×{ATR_MULTIPLIER}")
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
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
