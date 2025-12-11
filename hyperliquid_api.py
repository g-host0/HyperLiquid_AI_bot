"""
Модуль для работы с Hyperliquid API через официальный SDK
pip install hyperliquid-python-sdk
"""

try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    print("⚠️ hyperliquid-python-sdk не установлен")

import requests
import time
from eth_account import Account
from decimal import Decimal, ROUND_HALF_UP
from config import (
    HYPERLIQUID_API_URL,
    HYPERLIQUID_ACCOUNT_ADDRESS,
    HYPERLIQUID_PRIVATE_KEY,
    USE_TESTNET,
    MARKET_SLIPPAGE_PERCENT,
)


class HyperliquidAPI:
    def __init__(self):
        self.api_url = HYPERLIQUID_API_URL
        self.account_address = HYPERLIQUID_ACCOUNT_ADDRESS
        self.private_key = HYPERLIQUID_PRIVATE_KEY
        self.network = "Testnet" if USE_TESTNET else "Mainnet"
        print(f"🌐 Hyperliquid: {self.network}")
        
        self.exchange = None
        self.info = None
        
        # Кэш
        self._meta_cache = None
        self._meta_cache_ts = 0.0
        self._mids_cache = {}
        self._mids_ts = 0.0
        self._user_state_cache = None
        self._user_state_ts = 0.0
        self._last_sdk_init_ts = 0.0
        
        self._ensure_sdk_clients(initial=True)

    def _ensure_sdk_clients(self, initial=False):
        """Переинициализация SDK при сбоях"""
        if not SDK_AVAILABLE or not self.account_address or not self.private_key:
            return
        
        now = time.time()
        if self.info and self.exchange:
            return
        if not initial and (now - self._last_sdk_init_ts) < 5:
            return  # не спамим попытками
        
        self._last_sdk_init_ts = now
        try:
            pk = (
                self.private_key
                if self.private_key.startswith("0x")
                else "0x" + self.private_key
            )
            wallet = Account.from_key(pk)
            base_url = constants.TESTNET_API_URL if USE_TESTNET else constants.MAINNET_API_URL
            self.exchange = Exchange(wallet=wallet, base_url=base_url)
            self.info = Info(base_url=base_url, skip_ws=True)
            if initial:
                print("✅ SDK инициализирован")
            else:
                print("ℹ️ SDK переинициализирован")
        except Exception as e:
            if initial:
                print(f"⚠️ Ошибка SDK: {e}")
            else:
                print(f"⚠️ Ошибка повторной инициализации SDK: {e}")
            self.exchange = None
            self.info = None

    # ---------- Кэширование ----------
    def _get_meta_universe(self, ttl=300):
        """Кэшируем meta с обработкой tickSz"""
        self._ensure_sdk_clients()
        now = time.time()
        if (
            SDK_AVAILABLE
            and self.info
            and (not self._meta_cache or (now - self._meta_cache_ts) > ttl)
        ):
            try:
                meta = self.info.meta()
                universe = meta.get("universe", [])
                processed = []
                for u in universe:
                    u_copy = u.copy()
                    if "tickSz" in u_copy:
                        u_copy["tickSz"] = float(u_copy["tickSz"])
                    processed.append(u_copy)
                self._meta_cache = processed
                self._meta_cache_ts = now
            except Exception as e:
                print(f"⚠️ meta через SDK недоступно: {e}")
        
        if self._meta_cache:
            return self._meta_cache
        
        # Fallback REST
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "meta"}
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                universe = r.json().get("universe", [])
                processed = []
                for u in universe:
                    u_copy = u.copy()
                    if "tickSz" in u_copy:
                        u_copy["tickSz"] = float(u_copy["tickSz"])
                    processed.append(u_copy)
                return processed
        except Exception as e:
            print(f"⚠️ meta через REST недоступно: {e}")
        return []

    def _get_all_mids_cached(self, ttl=1.5):
        self._ensure_sdk_clients()
        now = time.time()
        if SDK_AVAILABLE and self.info and (now - self._mids_ts) > ttl:
            try:
                mids = self.info.all_mids()
                if isinstance(mids, dict):
                    self._mids_cache = mids
                    self._mids_ts = now
            except Exception as e:
                print(f"⚠️ mids через SDK недоступно: {e}")
        return self._mids_cache or {}

    def _get_user_state_cached(self, ttl=2.0):
        """Кэшированный user_state"""
        self._ensure_sdk_clients()
        now = time.time()
        if (
            SDK_AVAILABLE
            and self.info
            and (not self._user_state_cache or (now - self._user_state_ts) > ttl)
        ):
            try:
                self._user_state_cache = self.info.user_state(self.account_address)
                self._user_state_ts = now
            except Exception as e:
                print(f"⚠️ user_state через SDK недоступно: {e}")
        return self._user_state_cache

    def get_market(self, symbol: str):
        """Получить market info для symbol"""
        markets = self._get_meta_universe()
        for m in markets:
            if m.get("name") == symbol:
                return m
        return None

    # ---------- Основные методы ----------
    def get_user_state(self):
        if not self.account_address:
            return None
        
        if SDK_AVAILABLE and self.info:
            try:
                return self._get_user_state_cached()
            except Exception as e:
                print(f"⚠️ get_user_state SDK ошибка: {e}")
                self._ensure_sdk_clients()
        
        # Fallback REST
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "clearinghouseState", "user": self.account_address}
            r = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"⚠️ get_user_state REST ошибка: {e}")
        return None

    def get_balance(self):
        state = self.get_user_state()
        if not state:
            return 0.0
        try:
            margin = state.get("marginSummary", {})
            return float(margin.get("accountValue", 0))
        except Exception:
            return 0.0

    def get_open_positions(self):
        state = self.get_user_state()
        if not state:
            return []
        try:
            res = []
            for p in state.get("assetPositions", []):
                pos = p.get("position", {})
                szi = float(pos.get("szi", "0"))
                if szi != 0:
                    res.append(
                        {
                            "symbol": pos.get("coin", ""),
                            "size": szi,
                            "entry_price": float(pos.get("entryPx", 0)),
                            "side": "long" if szi > 0 else "short",
                        }
                    )
            return res
        except Exception:
            return []

    def get_open_orders(self):
        if not self.account_address:
            return []
        
        data = None
        if SDK_AVAILABLE and self.info:
            try:
                data = self.info.open_orders(self.account_address)
            except Exception as e:
                print(f"⚠️ open_orders SDK ошибка: {e}")
        
        if data is None:
            try:
                url = f"{self.api_url}/info"
                payload = {"type": "openOrders", "user": self.account_address}
                r = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=5,
                )
                if r.status_code == 200:
                    data = r.json()
            except Exception as e:
                print(f"⚠️ open_orders REST ошибка: {e}")
        
        if not data:
            return []
        
        positions = self.get_open_positions()
        pos_sizes = {p["symbol"]: abs(p["size"]) for p in positions}
        
        res = []
        for o in data:
            is_reduce_only = o.get("reduceOnly", False)
            coin = o.get("coin", "")
            size = float(o.get("sz", 0))
            tpsl = None
            is_trigger = False
            
            if is_reduce_only and coin in pos_sizes:
                is_trigger = True
                pos_size = pos_sizes[coin]
                if size >= pos_size * 0.95:
                    tpsl = "sl"
                else:
                    tpsl = "tp"
            
            trigger_px = o.get("triggerPx")
            limit_px = o.get("limitPx")
            order_type = o.get("orderType", "Limit" if not is_reduce_only else "Stop/TP")
            
            res.append(
                {
                    "symbol": coin,
                    "oid": o.get("oid"),
                    "side": o.get("side"),
                    "size": size,
                    "limit_price": float(limit_px) if limit_px else 0.0,
                    "trigger_price": float(trigger_px) if trigger_px else None,
                    "order_type": order_type,
                    "is_trigger": is_trigger,
                    "tpsl": tpsl,
                    "reduce_only": is_reduce_only,
                }
            )
        return res

    def cleanup_duplicate_orders(self):
        """Удаление дублей TP/SL и ордеров по закрытым символам"""
        if not SDK_AVAILABLE or not self.exchange:
            return
        
        orders = self.get_open_orders()
        positions = self.get_open_positions()
        pos_symbols = {p["symbol"] for p in positions}
        
        trigger_orders = [o for o in orders if o["is_trigger"]]
        if not trigger_orders:
            return
        
        from collections import defaultdict
        
        grouped = defaultdict(lambda: {"sl": [], "tp": []})
        for o in trigger_orders:
            sym = o["symbol"]
            tpsl = o.get("tpsl")
            if tpsl == "sl":
                grouped[sym]["sl"].append(o)
            elif tpsl == "tp":
                grouped[sym]["tp"].append(o)
        
        total_deleted = 0
        for sym, types in grouped.items():
            # Сначала удаляем все триггеры по символам, которых уже нет в позициях
            if sym not in pos_symbols:
                for tpsl_type in ["sl", "tp"]:
                    for o in types[tpsl_type]:
                        try:
                            self.exchange.cancel(sym, o["oid"])
                            total_deleted += 1
                        except Exception:
                            pass
                continue
            
            # Затем чистим дубли, оставляя самый свежий по oid
            for tpsl_type in ["sl", "tp"]:
                orders_list = types[tpsl_type]
                if len(orders_list) > 1:
                    orders_list.sort(key=lambda x: int(x["oid"]), reverse=True)
                    to_delete = orders_list[1:]
                    for o in to_delete:
                        try:
                            result = self.exchange.cancel(sym, o["oid"])
                            if result and result.get("status") == "ok":
                                total_deleted += 1
                        except Exception:
                            pass
        
        if total_deleted > 0:
            print(f"✅ Очистка дублей: удалено {total_deleted}")

    def get_mid_price(self, symbol):
        self._ensure_sdk_clients()
        mids = self._get_all_mids_cached()
        px = mids.get(symbol)
        if px is not None:
            return float(px)
        
        if SDK_AVAILABLE and self.info:
            try:
                ob = self.info.l2_snapshot(symbol)
                levels = ob.get("levels")
                if levels and len(levels) >= 2 and levels[0] and levels[1]:
                    bid = float(levels[0][0]["px"])
                    ask = float(levels[1][0]["px"])
                    if bid > 0 and ask > 0:
                        return (bid + ask) / 2
            except Exception:
                pass
        
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "l2Book", "coin": symbol}
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                levels = r.json().get("levels", [])
                if len(levels) >= 2 and levels[0] and levels[1]:
                    bid = float(levels[0][0]["px"])
                    ask = float(levels[1][0]["px"])
                    if bid > 0 and ask > 0:
                        return (bid + ask) / 2
        except Exception:
            pass
        return None

    def get_candles_snapshot(self, coin: str, interval: str, start_ms: int, end_ms: int, retries: int = 2):
        """
        Короткий геттер свечей с SDK и REST-фолбэком.
        Возвращает список свечей или [].
        """
        self._ensure_sdk_clients()
        # SDK путь
        if SDK_AVAILABLE and self.info:
            for _ in range(max(1, retries)):
                try:
                    candles = self.info.candles_snapshot(coin, interval, start_ms, end_ms)
                    if candles:
                        return candles
                except Exception as e:
                    print(f"⚠️ candles_snapshot SDK ошибка: {e}")
                    time.sleep(0.2)
        
        # REST фолбэк
        try:
            url = f"{self.api_url}/info"
            payload = {
                "type": "candleSnapshot",
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            }
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                candles = r.json()
                if isinstance(candles, list):
                    return candles
        except Exception as e:
            print(f"⚠️ candles_snapshot REST ошибка: {e}")
        return []

    def round_to_tick_size(self, price, tick_size):
        """Округление цены с высокой точностью (без погрешности float)"""
        if tick_size <= 0:
            return price
        
        # Используем Decimal для точного округления
        price_decimal = Decimal(str(price))
        tick_decimal = Decimal(str(tick_size))
        
        # Округляем до ближайшего tick_size
        rounded = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_decimal
        
        # Возвращаем float, но без погрешности
        return float(rounded)

    def normalize_price(self, price, tick_size, sigfigs=5):
        """
        Приводим цену к требованиям биржи:
        - кратность tick_size
        - не более sigfigs значимых цифр (HL: 5 значащих)
        """
        rounded = self.round_to_tick_size(price, tick_size)
        d = Decimal(str(rounded))
        if d == 0:
            return 0.0
        shift = sigfigs - d.adjusted() - 1
        quant = Decimal(f"1e{shift}")
        d = d.quantize(quant, rounding=ROUND_HALF_UP)
        return float(d)

    def place_order(self, symbol, side, quantity, order_type="Market", price=None):
        """Чистый отправитель ордера, без логики TP/SL/cooldown"""
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            market = self.get_market(symbol)
            if not market:
                return None
            
            sz_decimals = market.get("szDecimals", 4)
            tick_sz = market.get("tickSz", 0.1)
            qty = round(quantity, sz_decimals)
            
            mid = self.get_mid_price(symbol)
            if not mid:
                return None
            
            is_buy = side.lower() == "buy"
            
            if order_type == "Market":
                # Эмулируем market через IOC-limit с контролируемым слиппеджем
                slip_pct = max(0.01, MARKET_SLIPPAGE_PERCENT) / 100.0
                limit = mid * (1 + slip_pct) if is_buy else mid * (1 - slip_pct)
                limit = self.round_to_tick_size(limit, tick_sz)
                
                res = self.exchange.order(
                    symbol,
                    is_buy,
                    qty,
                    limit,
                    {"limit": {"tif": "Ioc"}},
                    reduce_only=False,
                )
                return res
            elif order_type == "Limit" and price is not None:
                limit = self.round_to_tick_size(price, tick_sz)
                res = self.exchange.order(
                    symbol,
                    is_buy,
                    qty,
                    limit,
                    {"limit": {"tif": "Gtc"}},
                    reduce_only=False,
                )
                return res
            
            return None
        except Exception:
            return None

    def cancel_order(self, symbol, oid):
        if not SDK_AVAILABLE or not self.exchange:
            return None
        try:
            return self.exchange.cancel(symbol, oid)
        except Exception:
            return None

    def set_sl_only(self, symbol, stop_loss_price):
        """Установка только SL ордера через SDK (с учётом текущей цены)"""
        if not SDK_AVAILABLE or not self.exchange:
            print(f"    ⚠️ SDK недоступен")
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            if not position:
                print(f"    ⚠️ Позиция {symbol} не найдена")
                return None
            
            size = abs(position["size"])
            entry_price = position["entry_price"]
            is_long = position["side"] == "long"
            
            # Получаем текущую mark price
            current_price = self.get_mid_price(symbol)
            if not current_price:
                print(f"    ⚠️ Не удалось получить текущую цену {symbol}")
                return None
            
            market = self.get_market(symbol)
            if not market:
                print(f"    ⚠️ Market info для {symbol} не найден")
                return None
            
            sz_decimals = market.get("szDecimals", 4)
            tick_sz = market.get("tickSz", 0.1)
            
            # Точное округление trigger price
            trigger_px = self.normalize_price(stop_loss_price, tick_sz)
            
            # ✅ КРИТИЧНО: Проверяем направление триггера относительно ТЕКУЩЕЙ цены
            if is_long:
                # LONG: SL должен быть НИЖЕ текущей цены
                if trigger_px >= current_price:
                    print(f"    ⚠️ SL для LONG ({trigger_px}) >= текущая цена ({current_price})")
                    # Используем минимум из расчётного и безубыток
                    trigger_px = min(trigger_px, entry_price * 0.995, current_price * 0.999)
                    trigger_px = self.round_to_tick_size(trigger_px, tick_sz)
                    print(f"    🔧 Скорректирован SL: {trigger_px}")
            else:
                # SHORT: SL должен быть ВЫШЕ текущей цены
                if trigger_px <= current_price:
                    print(f"    ⚠️ SL для SHORT ({trigger_px}) <= текущая цена ({current_price})")
                    # Используем максимум из расчётного и безубыток
                    trigger_px = max(trigger_px, entry_price * 1.005, current_price * 1.001)
                    trigger_px = self.round_to_tick_size(trigger_px, tick_sz)
                    print(f"    🔧 Скорректирован SL: {trigger_px}")
            
            # Определяем is_buy для закрытия позиции
            is_buy = not is_long
            
            # Для SL используем limitPx = triggerPx (market-style), чтобы избежать валидации цены
            limit_px = self.normalize_price(trigger_px, tick_sz)
            
            print(f"    📝 SL: current={current_price:.2f}, entry={entry_price:.2f}, trigger={trigger_px}, limit={limit_px}, is_buy={is_buy}")
            
            order_result = self.exchange.order(
                symbol,
                is_buy,
                round(size, sz_decimals),
                limit_px,
                {
                    "trigger": {
                        "triggerPx": trigger_px,
                        "isMarket": True,
                        "tpsl": "sl",
                    }
                },
                reduce_only=True,
            )
            
            print(f"    📋 Ответ биржи: {order_result}")
            return order_result
            
        except Exception as e:
            print(f"    ❌ Исключение в set_sl_only: {e}")
            import traceback
            traceback.print_exc()
            return None

    def set_tp_only(self, symbol, take_profit_price, tp_size):
        """Установка только TP ордера через SDK (с учётом текущей цены)"""
        if not SDK_AVAILABLE or not self.exchange:
            print(f"    ⚠️ SDK недоступен")
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            if not position:
                print(f"    ⚠️ Позиция {symbol} не найдена")
                return None
            
            is_long = position["side"] == "long"
            entry_price = position["entry_price"]
            
            # Получаем текущую mark price
            current_price = self.get_mid_price(symbol)
            if not current_price:
                print(f"    ⚠️ Не удалось получить текущую цену {symbol}")
                return None
            
            market = self.get_market(symbol)
            if not market:
                print(f"    ⚠️ Market info для {symbol} не найден")
                return None
            
            sz_decimals = market.get("szDecimals", 4)
            tick_sz = market.get("tickSz", 0.1)
            
            # Точное округление trigger price
            trigger_px = self.normalize_price(take_profit_price, tick_sz)
            
            tp_size_rounded = round(tp_size, sz_decimals)
            
            # ✅ КРИТИЧНО: Проверяем направление триггера относительно ТЕКУЩЕЙ цены
            if is_long:
                # LONG: TP должен быть ВЫШЕ текущей цены
                if trigger_px <= current_price:
                    print(f"    ⚠️ TP для LONG ({trigger_px}) <= текущая цена ({current_price})")
                    # TP уже достигнут, устанавливаем новый выше текущей
                    trigger_px = max(current_price * 1.002, entry_price * 1.005)
                    trigger_px = self.round_to_tick_size(trigger_px, tick_sz)
                    print(f"    🔧 Скорректирован TP: {trigger_px}")
            else:
                # SHORT: TP должен быть НИЖЕ текущей цены
                if trigger_px >= current_price:
                    print(f"    ⚠️ TP для SHORT ({trigger_px}) >= текущая цена ({current_price})")
                    # TP уже достигнут, устанавливаем новый ниже текущей
                    trigger_px = min(current_price * 0.998, entry_price * 0.995)
                    trigger_px = self.round_to_tick_size(trigger_px, tick_sz)
                    print(f"    🔧 Скорректирован TP: {trigger_px}")
            
            # Определяем is_buy для закрытия позиции
            is_buy = not is_long
            
            # Для TP ставим limitPx = triggerPx (market-style), чтобы пройти валидацию цены
            limit_px = self.normalize_price(trigger_px, tick_sz)
            
            print(f"    📝 TP: current={current_price:.2f}, entry={entry_price:.2f}, trigger={trigger_px}, limit={limit_px}, is_buy={is_buy}")
            
            order_result = self.exchange.order(
                symbol,
                is_buy,
                tp_size_rounded,
                limit_px,
                {
                    "trigger": {
                        "triggerPx": trigger_px,
                        "isMarket": True,
                        "tpsl": "tp",
                    }
                },
                reduce_only=True,
            )
            
            print(f"    📋 Ответ биржи: {order_result}")
            return order_result
            
        except Exception as e:
            print(f"    ❌ Исключение в set_tp_only: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(self, symbol):
        positions = self.get_open_positions()
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if pos:
            close_side = "sell" if pos["side"] == "long" else "buy"
            return self.place_order(symbol, close_side, abs(pos["size"]))
        return None

    def get_market_info(self):
        return self._get_meta_universe(ttl=300)


hl_api = HyperliquidAPI()
