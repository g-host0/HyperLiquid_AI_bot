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
from config import (
    HYPERLIQUID_API_URL,
    HYPERLIQUID_ACCOUNT_ADDRESS,
    HYPERLIQUID_PRIVATE_KEY,
    USE_TESTNET,
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
        
        if SDK_AVAILABLE and self.account_address and self.private_key:
            try:
                pk = (
                    self.private_key
                    if self.private_key.startswith("0x")
                    else "0x" + self.private_key
                )
                
                wallet = Account.from_key(pk)
                
                self.exchange = Exchange(
                    wallet=wallet,
                    base_url=constants.TESTNET_API_URL
                    if USE_TESTNET
                    else constants.MAINNET_API_URL,
                )
                
                self.info = Info(
                    base_url=constants.TESTNET_API_URL
                    if USE_TESTNET
                    else constants.MAINNET_API_URL,
                    skip_ws=True,
                )
                
                print(f"✅ SDK инициализирован")
            except Exception as e:
                print(f"⚠️ Ошибка SDK: {e}")
                self.exchange = None
                self.info = None

    def get_user_state(self):
        if not self.account_address:
            return None
        
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "clearinghouseState", "user": self.account_address}
            r = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            return None

    def get_balance(self):
        state = self.get_user_state()
        if not state:
            return 0.0
        
        try:
            margin = state.get("marginSummary", {})
            v = float(margin.get("accountValue", 0))
            return v
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
                s = float(pos.get("szi", "0"))
                if s != 0:
                    res.append(
                        {
                            "symbol": pos.get("coin", ""),
                            "size": s,
                            "entry_price": float(pos.get("entryPx", 0)),
                            "side": "long" if s > 0 else "short",
                        }
                    )
            return res
        except Exception:
            return []

    def get_open_orders(self):
        """Получает открытые ордера с определением trigger-ордеров"""
        if not self.account_address:
            return []
        
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "openOrders", "user": self.account_address}
            r = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            
            if r.status_code != 200:
                return []
            
            data = r.json()
            
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
                
                order_info = {
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
                
                res.append(order_info)
            
            return res
        
        except Exception:
            return []

    def cleanup_duplicate_orders(self):
        """Удаляет дублирующиеся SL/TP ордера"""
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
            if sym not in pos_symbols:
                for tpsl_type in ["sl", "tp"]:
                    for o in types[tpsl_type]:
                        try:
                            self.exchange.cancel(sym, o["oid"])
                            total_deleted += 1
                            time.sleep(0.15)
                        except:
                            pass
                continue
            
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
                            time.sleep(0.2)
                        except:
                            pass
        
        if total_deleted > 0:
            print(f"✅ Очистка дублей: удалено {total_deleted}")
            time.sleep(1.5)

    def get_market_info(self):
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "meta"}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                return r.json().get("universe", [])
            return []
        except Exception:
            return []

    def get_mid_price(self, symbol):
        try:
            url = f"{self.api_url}/info"
            payload = {"type": "l2Book", "coin": symbol}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                levels = r.json().get("levels", [])
                if len(levels) >= 2 and levels[0] and levels[1]:
                    bid = float(levels[0][0]["px"]) if levels[0] else 0
                    ask = float(levels[1][0]["px"]) if levels[1] else 0
                    if bid > 0 and ask > 0:
                        return (bid + ask) / 2
            return None
        except Exception:
            return None

    def round_to_tick_size(self, price, tick_size):
        return round(price / tick_size) * tick_size

    def place_order(self, symbol, side, quantity, order_type="Market", price=None):
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            markets = self.get_market_info()
            sz_dec = 4
            tick = 0.1
            
            for m in markets:
                if m.get("name") == symbol:
                    sz_dec = m.get("szDecimals", 4)
                    tick = 0.01 if sz_dec == 5 else 0.1
                    break
            
            qty = round(quantity, sz_dec)
            mid = self.get_mid_price(symbol)
            
            if not mid:
                return None
            
            is_buy = side.lower() == "buy"
            slip = 0.03
            limit = mid * (1 + slip) if is_buy else mid * (1 - slip)
            limit = self.round_to_tick_size(limit, tick)
            
            res = self.exchange.order(
                symbol,
                is_buy,
                qty,
                limit,
                {"limit": {"tif": "Ioc"}},
                reduce_only=False,
            )
            
            return res
        except Exception:
            return None

    def cancel_order(self, symbol, oid):
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            return self.exchange.cancel(symbol, oid)
        except:
            return None

    def set_sl_only(self, symbol, stop_loss_price):
        """Устанавливает только SL ордер"""
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            
            if not position:
                return None
            
            size = abs(position["size"])
            is_long = position["side"] == "long"
            
            markets = self.get_market_info()
            tick = 0.1
            sz_dec = 4
            
            for m in markets:
                if m.get("name") == symbol:
                    sz_dec = m.get("szDecimals", 4)
                    tick = 0.01 if sz_dec == 5 else 0.1
                    break
            
            sl_price = self.round_to_tick_size(stop_loss_price, tick)
            sl_side = not is_long
            
            res = self.exchange.order(
                symbol,
                sl_side,
                size,
                sl_price,
                {
                    "trigger": {
                        "triggerPx": sl_price,
                        "isMarket": True,
                        "tpsl": "sl",
                    }
                },
                reduce_only=True,
            )
            
            return res
        
        except Exception:
            return None

    def set_tp_only(self, symbol, take_profit_price, tp_size):
        """Устанавливает только TP ордер"""
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            
            if not position:
                return None
            
            is_long = position["side"] == "long"
            
            markets = self.get_market_info()
            tick = 0.1
            sz_dec = 4
            
            for m in markets:
                if m.get("name") == symbol:
                    sz_dec = m.get("szDecimals", 4)
                    tick = 0.01 if sz_dec == 5 else 0.1
                    break
            
            tp_price = self.round_to_tick_size(take_profit_price, tick)
            tp_size_rounded = round(tp_size, sz_dec)
            tp_side = not is_long
            
            res = self.exchange.order(
                symbol,
                tp_side,
                tp_size_rounded,
                tp_price,
                {
                    "trigger": {
                        "triggerPx": tp_price,
                        "isMarket": True,
                        "tpsl": "tp",
                    }
                },
                reduce_only=True,
            )
            
            return res
        
        except Exception:
            return None

    def close_position(self, symbol):
        """Закрывает позицию"""
        positions = self.get_open_positions()
        for p in positions:
            if p["symbol"] == symbol:
                side = "sell" if p["side"] == "long" else "buy"
                return self.place_order(symbol, side, abs(p["size"]))
        
        return None


hl_api = HyperliquidAPI()
