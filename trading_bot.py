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
                sl_set INTEGER DEFAULT 0,
                tp1_set INTEGER DEFAULT 0,
                tp2_set INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                profit REAL DEFAULT 0.0,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Таблица positions создана")
    else:
        extra = [
            ("atr", "REAL"),
            ("stop_loss", "REAL"),
            ("stop_loss_percent", "REAL"),
            ("original_quantity", "REAL"),
            ("tp1_hit", "INTEGER DEFAULT 0"),
            ("tp2_hit", "INTEGER DEFAULT 0"),
            ("sl_set", "INTEGER DEFAULT 0"),
            ("tp1_set", "INTEGER DEFAULT 0"),
            ("tp2_set", "INTEGER DEFAULT 0"),
        ]
        
        for n, t in extra:
            if n not in names:
                try:
                    conn.execute(f"ALTER TABLE positions ADD COLUMN {n} {t}")
                    print(f"Добавлен столбец {n}")
                except Exception as e:
                    print(f"Ошибка добавления столбца {n}: {e}")
    
    conn.commit()
    conn.close()

def sync_positions_with_exchange():
    """Синхронизация позиций и БД + удаление ордеров по символам без позиции."""
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
    
    # Закрываем позиции в БД, которых нет на бирже
    for pos_id, sym_db, side, qty in local:
        hl_sym = sym_db.replace("USDT", "")
        if hl_sym not in ex_pos_dict:
            conn.execute(
                "UPDATE positions SET status='closed', profit=0.0 WHERE id=?",
                (pos_id,),
            )
    
    # Добавляем позиции с биржи, которых нет в БД
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
                    atr, stop_loss, stop_loss_percent, original_quantity,
                    sl_set, tp1_set, tp2_set
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, 0, 0, 0)
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
    
    # Удаляем ордера для символов без открытой позиции
    for o in ex_orders:
        coin = o["symbol"]
        if coin not in open_syms:
            print(f"  🗑️ Удаление ордера для {coin} (нет позиции)")
            hl_api.cancel_order(coin, o["oid"])
    
    conn.commit()
    conn.close()
    print("Синхронизация с биржей завершена")

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
    print("📊 ОТКРЫТЫЕ ПОЗИЦИИ НА БИРЖЕ")
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
                    f"Текущая: ${cur:.2f} | P&L {pnl_pct:.2f}% (${pnl:.2f})"
                )
            else:
                print(f"  {sym} {side}: {size:.4f} @ ${entry:.2f}")
            
            # Показываем только SL/TP ордера
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
                    trig_px = o.get("trigger_price", 0)
                    pct = (sz / size * 100) if size > 0 else 0
                    print(f"    └─ {t}: ${trig_px:.2f} ({pct:.0f}% позиции, oid={o['oid']})")
    
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
    except Exception as e:
        print(f"Ошибка цены {symbol}: {e}")
        return 0.0

def get_symbol_atr(symbol, data_dict_outer):
    if symbol not in data_dict_outer or "1h" not in data_dict_outer[symbol]:
        return 0.0
    return calculate_atr(data_dict_outer[symbol]["1h"])

def calculate_position_size(symbol, data_dict_outer):
    bal = get_balance()
    if bal <= 0:
        print(f"Нулевой баланс: {bal}")
        return 0.0, 0.0
    
    price = get_current_price(symbol)
    if price <= 0:
        print(f"Некорректная цена {symbol}: {price}")
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
        print(
            f"Лимит по {symbol}: {existing:.2f} из {max_val:.2f}, "
            f"новая позиция запрещена"
        )
        return 0.0, 0.0
    
    avail = max_val - existing
    pos_val = min(avail, bal * (POSITION_SIZE_PERCENT / 100.0))
    qty = pos_val / price
    atr = get_symbol_atr(symbol, data_dict_outer)
    
    print(f"Баланс: {bal:.2f}, уже в {symbol}: {existing:.2f}, qty={qty:.6f}, ATR={atr:.4f}")
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
        
        print(
            f"Объединена позиция {symbol} {side}: qty={total:.6f}, "
            f"price={avg_price:.2f}, ATR={atr:.4f}"
        )
    else:
        val = new_qty * new_price
        sl = calculate_stop_loss(new_price, side, new_atr)
        sl_pct = abs((sl - new_price) / new_price * 100)
        
        conn.execute(
            """
            INSERT INTO positions (
                symbol, side, quantity, entry_price, position_value,
                atr, stop_loss, stop_loss_percent, original_quantity,
                sl_set, tp1_set, tp2_set
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
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
        
        print(
            f"Новая позиция {symbol} {side}: qty={new_qty:.6f}, "
            f"price={new_price:.2f}, ATR={new_atr:.4f}"
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
        print(f"Некорректный размер {symbol}: {quantity}")
        return
    
    price = get_current_price(symbol)
    if price <= 0:
        print(f"Некорректная цена {symbol}: {price}")
        return
    
    if TEST_MODE:
        print(f"[TEST] {side.upper()} {quantity:.6f} {symbol} @ {price:.2f}")
        merge_positions(symbol, side, quantity, price, atr)
        return
    
    hl_sym = symbol.replace("USDT", "")
    print(f"📤 Ордер на Hyperliquid: {side.upper()} {quantity} {hl_sym}")
    
    res = hl_api.place_order(hl_sym, side, quantity, "Market")
    if res:
        print("✅ Ордер исполнен")
        merge_positions(symbol, side, quantity, price, atr)
    else:
        print(f"❌ Не удалось разместить ордер для {symbol}")

# ---------- Проверка и установка SL/TP ----------
def check_positions():
    """
    Улучшенная логика управления SL/TP:
    1. Проверяем наличие SL - если нет, создаём
    2. Проверяем наличие TP1 - если нет, создаём
    3. Если TP1 сработал (размер позиции уменьшился), создаём TP2
    """
    if TEST_MODE:
        return
    
    ex_positions = hl_api.get_open_positions()
    ex_orders = hl_api.get_open_orders()
    
    if not ex_positions:
        return
    
    conn = sqlite3.connect("positions.db")
    
    for pos in ex_positions:
        sym = pos["symbol"]
        sym_db = sym + "USDT"
        current_size = abs(pos["size"])
        side = "buy" if pos["side"] == "long" else "sell"
        entry_price = pos["entry_price"]
        
        # Получаем данные из БД
        db_row = conn.execute(
            """
            SELECT id, original_quantity, atr, tp1_hit, tp2_hit, 
                   sl_set, tp1_set, tp2_set
            FROM positions 
            WHERE symbol=? AND status='open' 
            ORDER BY opened_at DESC LIMIT 1
            """,
            (sym_db,),
        ).fetchone()
        
        if not db_row:
            continue
        
        pos_id, orig_qty, atr, tp1_hit, tp2_hit, sl_set, tp1_set, tp2_set = db_row
        
        # Проверяем сработал ли TP1 (размер позиции уменьшился)
        if orig_qty and current_size < orig_qty * 0.95:  # 95% от оригинала
            if not tp1_hit:
                print(f"  ✅ TP1 сработал для {sym}: {orig_qty:.4f} → {current_size:.4f}")
                conn.execute(
                    "UPDATE positions SET tp1_hit=1 WHERE id=?",
                    (pos_id,),
                )
                tp1_hit = 1
        
        # Получаем существующие SL/TP ордера
        triggers = [o for o in ex_orders if o["symbol"] == sym and o["is_trigger"]]
        has_sl = any(o.get("tpsl") == "sl" for o in triggers)
        has_tp1 = any(o.get("tpsl") == "tp" for o in triggers)
        
        # Определяем ATR
        if not atr or atr == 0:
            atr = 0.0
        
        # 1. Устанавливаем SL если его нет
        if not has_sl:
            if atr > 0:
                sl_price = calculate_stop_loss(entry_price, side, atr)
                print(f"  ⚙️ Установка SL для {sym}: ${sl_price:.2f}")
                hl_api.set_sl_only(sym, sl_price)
                conn.execute("UPDATE positions SET sl_set=1 WHERE id=?", (pos_id,))
            else:
                print(f"  ⚠️ Не могу установить SL для {sym}: ATR=0")
        
        # 2. Устанавливаем TP1 если его нет и он ещё не сработал
        if not has_tp1 and not tp1_hit:
            if side == "buy":
                tp1_price = entry_price * (1 + TAKE_PROFIT_1_PERCENT / 100)
            else:
                tp1_price = entry_price * (1 - TAKE_PROFIT_1_PERCENT / 100)
            
            tp1_size = current_size * (TAKE_PROFIT_1_SIZE_PERCENT / 100)
            print(f"  ⚙️ Установка TP1 для {sym}: ${tp1_price:.2f}, размер {tp1_size:.4f}")
            hl_api.set_tp_only(sym, tp1_price, tp1_size)
            conn.execute("UPDATE positions SET tp1_set=1 WHERE id=?", (pos_id,))
        
        # 3. Устанавливаем TP2 если TP1 сработал и TP2 ещё нет
        if tp1_hit and not tp2_hit and not has_tp1:
            # TP1 сработал, создаём TP2
            if side == "buy":
                tp2_price = entry_price * (1 + TAKE_PROFIT_2_PERCENT / 100)
            else:
                tp2_price = entry_price * (1 - TAKE_PROFIT_2_PERCENT / 100)
            
            tp2_size = current_size * (TAKE_PROFIT_2_SIZE_PERCENT / 100)
            print(f"  ⚙️ Установка TP2 для {sym}: ${tp2_price:.2f}, размер {tp2_size:.4f}")
            hl_api.set_tp_only(sym, tp2_price, tp2_size)
            conn.execute("UPDATE positions SET tp2_set=1 WHERE id=?", (pos_id,))
    
    conn.commit()
    conn.close()

# ---------- Главный цикл ----------
def main():
    init_db()
    
    print("=" * 60)
    print("ЗАПУСК ТОРГОВОГО БОТА")
    print("=" * 60)
    print(
        f"AI: Perplexity={'✓' if USE_PERPLEXITY else '✗'}, "
        f"OpenRouter={'✓' if USE_OPENROUTER else '✗'}, "
        f"Стратегия={SIGNAL_STRATEGY}"
    )
    
    if TEST_MODE:
        print("⚠️ ТЕСТОВЫЙ РЕЖИМ")
        print(f"Баланс (вирт): {TEST_BALANCE:.2f}")
    else:
        print("🔴 РЕАЛЬНЫЙ РЕЖИМ")
        print(f"🌐 Сеть: {'Testnet' if USE_TESTNET else 'Mainnet'}")
        bal = get_balance()
        print(f"💰 Баланс: {bal:.2f}")
        
        if bal <= 0:
            print("❌ Недостаточно средств")
            if USE_TESTNET:
                print("Получить тестовые токены: https://app.hyperliquid-testnet.xyz/")
            return
        
        sync_positions_with_exchange()
    
    print("=" * 60)
    print(f"📊 TP1: +{TAKE_PROFIT_1_PERCENT}% ({TAKE_PROFIT_1_SIZE_PERCENT}% позиции)")
    print(f"📊 TP2: +{TAKE_PROFIT_2_PERCENT}% ({TAKE_PROFIT_2_SIZE_PERCENT}% оставшейся позиции)")
    print(f"📊 SL: ATR×{ATR_MULTIPLIER}, 100% позиции")
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
                print("Нет данных для анализа")
                time.sleep(INTERVAL)
                continue
            
            decision, reason = analyze_with_ai(valid)
            print(f"🎯 Рекомендация: {decision} | {reason}")
            
            if decision.startswith("buy_") or decision.startswith("sell_"):
                act, sym = decision.split("_", 1)
                if sym in valid:
                    qty, atr = calculate_position_size(sym, valid)
                    if qty > 0 and atr > 0:
                        place_order(sym, act, qty, atr)
                    else:
                        print(f"Размер позиции {sym} не рассчитан / ATR=0")
            
            check_positions()
            display_positions_summary()
            
            time.sleep(INTERVAL)
        
        except KeyboardInterrupt:
            print("\n" + "=" * 60)
            print("ОСТАНОВКА БОТА")
            print("=" * 60)
            display_positions_summary()
            break
        
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
