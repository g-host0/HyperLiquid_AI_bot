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
        
        print(f"🌐 Hyperliquid API инициализирован: {self.network}")
        print(f"  URL: {self.api_url}")
        print(f"  Account: {self.account_address}")
        
        if not self.account_address:
            print("  ⚠️ HYPERLIQUID_ACCOUNT_ADDRESS не установлен")
        if not self.private_key:
            print("  ⚠️ HYPERLIQUID_PRIVATE_KEY не установлен")
        
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
                
                print("  ✅ SDK инициализирован успешно")
                print(f"  📝 Wallet address: {wallet.address}")
            except Exception as e:
                print(f"  ⚠️ Ошибка инициализации SDK: {e}")
                self.exchange = None
                self.info = None

    # ---------- базовая информация ----------
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
        """openOrders с полем tpsl"""
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
            res = []
            for o in data:
                trigger_px = o.get("triggerPx")
                res.append(
                    {
                        "symbol": o.get("coin", ""),
                        "oid": o.get("oid"),
                        "side": o.get("side"),
                        "size": float(o.get("sz", 0)),
                        "limit_price": float(o.get("limitPx", 0)),
                        "trigger_price": float(trigger_px) if trigger_px else None,
                        "order_type": o.get("orderType", ""),
                        "is_trigger": trigger_px is not None,
                        "tpsl": o.get("tpsl"),  # 'sl' / 'tp' / None
                    }
                )
            return res
        except Exception as e:
            print(f"❌ Ошибка получения ордеров: {e}")
            return []

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

    # ---------- обычные ордера ----------
    def place_order(self, symbol, side, quantity, order_type="Market", price=None):
        if not SDK_AVAILABLE:
            print("❌ SDK не установлен")
            return None
        
        if not self.exchange:
            print("❌ Exchange не инициализирован")
            return None
        
        try:
            print(f"📤 Размещение ордера: {side.upper()} {quantity} {symbol}")
            
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
                print(f"  ❌ Не удалось взять цену {symbol}")
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
            
            print(f"  API result: {res}")
            return res
        
        except Exception as e:
            print(f"❌ Ошибка размещения ордера: {e}")
            import traceback
            traceback.print_exc()
            return None

    def cancel_all_orders(self, symbol):
        if not SDK_AVAILABLE or not self.exchange:
            return False
        
        try:
            orders = self.get_open_orders()
            to_cancel = [o for o in orders if o["symbol"] == symbol]
            
            if not to_cancel:
                return True
            
            print(f"  🗑️ Отмена {len(to_cancel)} ордеров для {symbol}")
            ok = 0
            
            for o in to_cancel:
                try:
                    r = self.exchange.cancel(symbol, o["oid"])
                    if r and r.get("status") == "ok":
                        ok += 1
                    time.sleep(0.2)
                except Exception as e:
                    print(f"  ❌ Ошибка отмены oid={o['oid']}: {e}")
            
            print(f"  ✅ Отменено {ok} из {len(to_cancel)}")
            return ok > 0
        
        except Exception as e:
            print(f"  ❌ Ошибка cancel_all_orders: {e}")
            return False

    def cancel_order(self, symbol, oid):
        if not SDK_AVAILABLE or not self.exchange:
            return None
        
        try:
            return self.exchange.cancel(symbol, oid)
        except Exception as e:
            print(f"❌ Ошибка отмены ордера: {e}")
            return None

    # ---------- установка SL/TP ----------
    def set_position_sltp(
        self,
        symbol,
        stop_loss_price=None,
        take_profit_price=None,
        tp_size_percent=30.0,
    ):
        """
        УСТАРЕВШАЯ ФУНКЦИЯ - оставлена для совместимости.
        Перед установкой новых SL/TP удаляем ВСЕ trigger‑ордера по symbol.
        После этого создаётся максимум 1 SL + 1 TP.
        
        Рекомендуется использовать set_sl_only() и set_tp_only()
        """
        if not SDK_AVAILABLE or not self.exchange:
            print("❌ SDK не инициализирован")
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            
            if not position:
                print(f"  ⚠️ Позиция {symbol} не найдена")
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
            
            sl_price = (
                self.round_to_tick_size(stop_loss_price, tick)
                if stop_loss_price
                else None
            )
            
            tp_price = (
                self.round_to_tick_size(take_profit_price, tick)
                if take_profit_price
                else None
            )
            
            tp_size = None
            if tp_price:
                tp_size = round(size * (tp_size_percent / 100.0), sz_dec)
                if tp_size <= 0:
                    tp_size = round(size * 0.3, sz_dec)
                if tp_size > size:
                    tp_size = size
            
            # Удаляем все существующие trigger-ордера
            existing = self.get_open_orders()
            triggers = [
                o
                for o in existing
                if o["symbol"] == symbol and o["is_trigger"]
            ]
            
            if triggers:
                print(
                    f"  🧹 Полная зачистка {len(triggers)} SL/TP ордеров по {symbol}"
                )
                for o in triggers:
                    try:
                        self.exchange.cancel(symbol, o["oid"])
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"  ❌ Ошибка отмены oid={o['oid']}: {e}")
                
                time.sleep(0.5)
            
            results = {"sl": None, "tp": None}
            
            # Устанавливаем SL
            if sl_price:
                sl_side = not is_long
                print(
                    f"  📍 Новый SL {symbol}: price={sl_price}, size={size}"
                )
                
                try:
                    sl_res = self.exchange.order(
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
                    
                    results["sl"] = sl_res
                    if sl_res and sl_res.get("status") == "ok":
                        print("  ✅ SL установлен")
                    else:
                        print(f"  ❌ Ошибка SL: {sl_res}")
                except Exception as e:
                    print(f"  ❌ Ошибка SL: {e}")
                
                time.sleep(0.3)
            
            # Устанавливаем TP
            if tp_price and tp_size:
                tp_side = not is_long
                print(
                    f"  📍 Новый TP {symbol}: price={tp_price}, size={tp_size}"
                )
                
                try:
                    tp_res = self.exchange.order(
                        symbol,
                        tp_side,
                        tp_size,
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
                    
                    results["tp"] = tp_res
                    if tp_res and tp_res.get("status") == "ok":
                        print("  ✅ TP установлен")
                    else:
                        print(f"  ❌ Ошибка TP: {tp_res}")
                except Exception as e:
                    print(f"  ❌ Ошибка TP: {e}")
            
            return results
        
        except Exception as e:
            print(f"❌ Ошибка set_position_sltp: {e}")
            import traceback
            traceback.print_exc()
            return None

    def set_sl_only(self, symbol, stop_loss_price):
        """
        Устанавливает только SL ордер для позиции.
        Не удаляет существующие ордера - используется для точечной установки.
        """
        if not SDK_AVAILABLE or not self.exchange:
            print("❌ SDK не инициализирован")
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            
            if not position:
                print(f"  ⚠️ Позиция {symbol} не найдена")
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
            
            print(f"  📍 Установка SL {symbol}: price={sl_price}, size={size}")
            
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
            
            if res and res.get("status") == "ok":
                print("  ✅ SL установлен")
            else:
                print(f"  ❌ Ошибка SL: {res}")
            
            return res
        
        except Exception as e:
            print(f"❌ Ошибка set_sl_only: {e}")
            import traceback
            traceback.print_exc()
            return None

    def set_tp_only(self, symbol, take_profit_price, tp_size):
        """
        Устанавливает только TP ордер для позиции.
        Не удаляет существующие ордера - используется для точечной установки.
        
        Args:
            symbol: Символ торговой пары (например, 'ETH')
            take_profit_price: Цена срабатывания TP
            tp_size: Размер ордера в единицах базовой валюты
        """
        if not SDK_AVAILABLE or not self.exchange:
            print("❌ SDK не инициализирован")
            return None
        
        try:
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == symbol), None)
            
            if not position:
                print(f"  ⚠️ Позиция {symbol} не найдена")
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
            
            print(f"  📍 Установка TP {symbol}: price={tp_price}, size={tp_size_rounded}")
            
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
            
            if res and res.get("status") == "ok":
                print("  ✅ TP установлен")
            else:
                print(f"  ❌ Ошибка TP: {res}")
            
            return res
        
        except Exception as e:
            print(f"❌ Ошибка set_tp_only: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(self, symbol):
        """Закрывает позицию по символу"""
        positions = self.get_open_positions()
        for p in positions:
            if p["symbol"] == symbol:
                side = "sell" if p["side"] == "long" else "buy"
                return self.place_order(symbol, side, abs(p["size"]))
        
        print(f"⚠️ Позиция по {symbol} не найдена")
        return None


# Создаём глобальный экземпляр API
hl_api = HyperliquidAPI()
