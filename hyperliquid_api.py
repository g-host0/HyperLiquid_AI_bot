# -*- coding: utf-8 -*-
"""
Модуль для работы с Hyperliquid API через официальный SDK
"""

import time
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account
from decimal import Decimal, ROUND_DOWN

from config import (
    HYPERLIQUID_API_URL,
    HYPERLIQUID_ACCOUNT_ADDRESS,
    HYPERLIQUID_PRIVATE_KEY,
    USE_TESTNET,
)


class HyperliquidAPI:
    def __init__(self):
        """Инициализация Hyperliquid API."""
        self.info = None
        self.exchange = None
        self.account = None
        self.address = HYPERLIQUID_ACCOUNT_ADDRESS
        self.asset_info = {}
        self._last_orders_fetch = 0
        self._orders_cache = []

        if not self.address or not HYPERLIQUID_PRIVATE_KEY:
            print("⚠️ Hyperliquid credentials не установлены")
            return

        try:
            self.info = Info(HYPERLIQUID_API_URL, skip_ws=True)
            self.account = Account.from_key(HYPERLIQUID_PRIVATE_KEY)
            
            base_url = constants.TESTNET_API_URL if USE_TESTNET else constants.MAINNET_API_URL
            self.exchange = Exchange(
                wallet=self.account,
                base_url=base_url,
                account_address=self.address
            )
            
            self._load_asset_metadata()
            
            env = "Testnet" if USE_TESTNET else "Mainnet"
            print(f"🌐 Hyperliquid: {env}")
            print(f"📍 API URL: {HYPERLIQUID_API_URL}")
            print("✅ SDK инициализирован")
            
        except Exception as e:
            print(f"❌ Ошибка инициализации Hyperliquid SDK: {e}")
            import traceback
            traceback.print_exc()

    def _load_asset_metadata(self):
        """Загрузка метаданных активов."""
        try:
            if not self.info:
                return
            
            meta = self.info.meta()
            if meta and "universe" in meta:
                for asset in meta["universe"]:
                    coin = asset.get("name", "")
                    sz_decimals = asset.get("szDecimals", 8)
                    max_lev_obj = asset.get("maxLeverage", 50)
                    
                    if isinstance(max_lev_obj, dict):
                        max_leverage = int(max_lev_obj.get("value", 50))
                    else:
                        max_leverage = int(max_lev_obj)
                    
                    self.asset_info[coin] = {
                        "sz_decimals": sz_decimals,
                        "max_leverage": max_leverage,
                    }
        except Exception as e:
            print(f"⚠️ Ошибка загрузки метаданных: {e}")

    def round_size(self, coin, size):
        """Округление размера позиции."""
        if coin not in self.asset_info:
            return round(size, 4)
        
        sz_decimals = self.asset_info[coin]["sz_decimals"]
        return round(size, sz_decimals)

    def round_price_sig_figs(self, price, max_sig_figs=5):
        """Округление цены до максимального числа значащих цифр."""
        if price == 0:
            return 0.0
        
        from math import log10, floor
        
        price_decimal = Decimal(str(price))
        magnitude = floor(log10(abs(float(price))))
        scale = max_sig_figs - 1 - magnitude
        rounded = round(float(price_decimal), int(scale))
        
        return rounded

    def get_balance(self):
        """Получение баланса."""
        try:
            if not self.info or not self.address:
                return 0.0
            
            user_state = self.info.user_state(self.address)
            if user_state and "marginSummary" in user_state:
                return float(user_state["marginSummary"]["accountValue"])
            return 0.0
        except Exception as e:
            print(f"❌ Ошибка получения баланса: {e}")
            return 0.0

    def get_available_balance(self):
        """Получение доступного для торговли баланса."""
        try:
            if not self.info or not self.address:
                return 0.0
            
            user_state = self.info.user_state(self.address)
            if user_state and "marginSummary" in user_state:
                margin_summary = user_state["marginSummary"]
                # Available = accountValue - totalMarginUsed
                account_value = float(margin_summary.get("accountValue", 0))
                total_margin_used = float(margin_summary.get("totalMarginUsed", 0))
                available = account_value - total_margin_used
                return max(0.0, available)
            return 0.0
        except Exception as e:
            print(f"❌ Ошибка получения доступного баланса: {e}")
            return 0.0

    def get_mid_price(self, coin):
        """Получение средней цены."""
        try:
            if not self.info:
                return None
            
            all_mids = self.info.all_mids()
            if all_mids and coin in all_mids:
                return float(all_mids[coin])
            return None
        except Exception as e:
            print(f"❌ Ошибка получения цены {coin}: {e}")
            return None

    def get_open_positions(self):
        """Получение открытых позиций."""
        try:
            if not self.info or not self.address:
                return []
            
            user_state = self.info.user_state(self.address)
            if not user_state or "assetPositions" not in user_state:
                return []
            
            positions = []
            for pos in user_state["assetPositions"]:
                position_data = pos.get("position", {})
                if not position_data:
                    continue
                
                coin = position_data.get("coin", "")
                szi = float(position_data.get("szi", 0))
                
                if szi == 0:
                    continue
                
                lev_obj = position_data.get("leverage", {})
                if isinstance(lev_obj, dict):
                    leverage = float(lev_obj.get("value", 1))
                else:
                    leverage = float(lev_obj) if lev_obj else 1.0
                
                positions.append({
                    "symbol": coin,
                    "side": "long" if szi > 0 else "short",
                    "size": abs(szi),
                    "entry_price": float(position_data.get("entryPx", 0)),
                    "unrealized_pnl": float(position_data.get("unrealizedPnl", 0)),
                    "leverage": leverage,
                })
            
            return positions
        except Exception as e:
            print(f"❌ Ошибка получения позиций: {e}")
            return []

    def get_open_orders(self, force_refresh=False):
        """Получение открытых ордеров с кешированием."""
        try:
            current_time = time.time()
            
            if not force_refresh and (current_time - self._last_orders_fetch) < 2.0:
                return self._orders_cache
            
            if not self.info or not self.address:
                return []
            
            time.sleep(1.0)
            
            open_orders = self.info.open_orders(self.address)
            if not open_orders:
                self._orders_cache = []
                self._last_orders_fetch = current_time
                return []
            
            positions = self.get_open_positions()
            pos_dict = {p["symbol"]: p for p in positions}
            
            orders = []
            for order in open_orders:
                coin = order.get("coin", "")
                oid = order.get("oid", 0)
                side = order.get("side", "")
                size = abs(float(order.get("sz", 0)))
                limit_px = float(order.get("limitPx", 0))
                is_reduce_only = order.get("reduceOnly", False)
                
                order_type_data = order.get("orderType", {})
                is_trigger = False
                tpsl = None
                trigger_price = None
                
                if isinstance(order_type_data, dict):
                    if "trigger" in order_type_data:
                        is_trigger = True
                        trigger_info = order_type_data["trigger"]
                        if isinstance(trigger_info, dict):
                            trigger_price = trigger_info.get("triggerPx")
                            if trigger_price:
                                trigger_price = float(trigger_price)
                            tpsl = trigger_info.get("tpsl")
                            if tpsl == "":
                                tpsl = None
                    elif "limit" in order_type_data:
                        is_trigger = False
                    elif "triggerPx" in order_type_data:
                        is_trigger = True
                        trigger_price = float(order_type_data.get("triggerPx", 0))
                        tpsl = order_type_data.get("tpsl")
                        if tpsl == "":
                            tpsl = None
                
                if is_reduce_only and tpsl is None and coin in pos_dict:
                    position = pos_dict[coin]
                    pos_side = position["side"]
                    pos_size = position["size"]
                    current_price = self.get_mid_price(coin)
                    
                    if trigger_price and current_price:
                        if pos_side == "long":
                            tpsl = "tp" if trigger_price > current_price else "sl"
                        else:
                            tpsl = "tp" if trigger_price < current_price else "sl"
                    elif size >= pos_size * 0.95:
                        tpsl = "sl"
                    else:
                        tpsl = "tp"
                
                if not is_trigger and tpsl:
                    is_trigger = True
                    trigger_price = limit_px
                
                order_data = {
                    "symbol": coin,
                    "oid": oid,
                    "side": side,
                    "size": size,
                    "limit_price": limit_px,
                    "trigger_price": trigger_price if trigger_price else limit_px,
                    "is_trigger": is_trigger or is_reduce_only,
                    "tpsl": tpsl,
                    "reduce_only": is_reduce_only,
                }
                
                orders.append(order_data)
            
            self._orders_cache = orders
            self._last_orders_fetch = current_time
            return orders
        
        except Exception as e:
            print(f"❌ Ошибка получения ордеров: {e}")
            import traceback
            traceback.print_exc()
            return []

    def place_order(self, coin, side, size, order_type="Market", limit_price=None):
        """Размещение ордера."""
        try:
            if not self.exchange:
                print("❌ Exchange не инициализирован")
                return None
            
            if coin not in self.asset_info:
                print(f"❌ Информация о {coin} не найдена")
                return None
            
            sz_decimals = self.asset_info[coin]["sz_decimals"]
            size = round(size, sz_decimals)
            
            is_buy = side.lower() == "buy"
            
            mid = self.get_mid_price(coin)
            if not mid:
                print(f"❌ Не удалось получить цену {coin}")
                return None
            
            if order_type == "Market":
                best_bid, best_ask = None, None
                try:
                    if self.info:
                        ob = self.info.l2_snapshot(coin)
                        levels = ob.get("levels", [])
                        if levels and len(levels) >= 2:
                            if levels[0] and len(levels[0]) > 0:
                                best_bid = float(levels[0][0]["px"])
                            if levels[1] and len(levels[1]) > 0:
                                best_ask = float(levels[1][0]["px"])
                except Exception:
                    pass
                
                if is_buy:
                    limit = best_ask * 1.002 if (best_ask and best_ask > 0) else mid * 1.002
                else:
                    limit = best_bid * 0.998 if (best_bid and best_bid > 0) else mid * 0.998
                
                limit_final = self.round_price_sig_figs(limit, max_sig_figs=5)
                
                print(f"  🔍 {coin}: mid={mid:.4f}, target={limit:.4f} → final={limit_final:.4f}")
                
                result = self.exchange.order(
                    coin,
                    is_buy,
                    size,
                    limit_final,
                    {"limit": {"tif": "Gtc"}},
                )
            
            elif order_type == "Limit" and limit_price:
                limit_final = self.round_price_sig_figs(limit_price, max_sig_figs=5)
                
                result = self.exchange.order(
                    coin,
                    is_buy,
                    size,
                    limit_final,
                    {"limit": {"tif": "Gtc"}},
                )
            
            else:
                print("❌ Неправильный тип ордера")
                return None
            
            if result:
                if result.get("status") == "ok":
                    response = result.get("response", {})
                    if response.get("type") == "order":
                        data = response.get("data", {})
                        statuses = data.get("statuses", [])
                        if statuses:
                            status = statuses[0]
                            
                            if "error" in status:
                                error_msg = status.get("error", "")
                                print(f"❌ Ошибка ордера: {error_msg}")
                                return None
                            
                            if "filled" in status:
                                filled_info = status["filled"]
                                total_sz = float(filled_info.get("totalSz", 0))
                                avg_px = float(filled_info.get("avgPx", 0))
                                
                                if total_sz > 0:
                                    print(f"✅ Исполнено: {total_sz} @ ${avg_px:.2f}")
                                    return result
                                else:
                                    print(f"⚠️ Ордер не исполнен")
                                    return None
                            else:
                                print(f"✅ Ордер размещён")
                                return result
                else:
                    print(f"❌ Статус: {result.get('status')}")
                    return None
            else:
                print("❌ Нет ответа от API")
                return None
        
        except Exception as e:
            print(f"❌ Ошибка ордера: {e}")
            import traceback
            traceback.print_exc()
            return None

    def cancel_order(self, coin, oid):
        """Отмена ордера."""
        try:
            if not self.exchange:
                return None
            
            result = self.exchange.cancel(coin, oid)
            self._last_orders_fetch = 0
            return result
        except Exception as e:
            print(f"❌ Ошибка отмены ордера: {e}")
            return None

    def set_sl_only(self, coin, trigger_price, size=None):
        """✅ ИСПРАВЛЕНО: Установка Stop Loss с явным размером."""
        try:
            if not self.exchange:
                return None
            
            # ✅ КРИТИЧНО: Сбрасываем кеш перед проверкой
            self._last_orders_fetch = 0
            
            time.sleep(1.5)
            orders = self.get_open_orders(force_refresh=True)
            existing_sl = [o for o in orders if o["symbol"] == coin and o.get("tpsl") == "sl"]
            
            if existing_sl:
                for old_order in existing_sl:
                    self.cancel_order(coin, old_order["oid"])
                time.sleep(0.2)
            
            time.sleep(1.0)
            
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == coin), None)
            
            if not position:
                return None
            
            # ✅ КРИТИЧНО: Используем size из параметра или из позиции
            position_size = size if size is not None else position["size"]
            entry_price = position["entry_price"]
            is_long = position["side"] == "long"
            
            current_price = self.get_mid_price(coin)
            if not current_price:
                return None
            
            if coin not in self.asset_info:
                return None
            
            sz_decimals = self.asset_info[coin]["sz_decimals"]
            trigger_px = self.round_price_sig_figs(trigger_price, max_sig_figs=5)
            
            if is_long:
                if trigger_px >= current_price * 0.999:
                    trigger_px = min(trigger_px, entry_price * 0.995, current_price * 0.997)
                    trigger_px = self.round_price_sig_figs(trigger_px, max_sig_figs=5)
                    if trigger_px >= current_price * 0.998:
                        print(f"⚠️ SL слишком близко: {trigger_px:.4f} >= {current_price:.4f}")
                        return None
            else:
                if trigger_px <= current_price * 1.001:
                    trigger_px = max(trigger_px, entry_price * 1.005, current_price * 1.003)
                    trigger_px = self.round_price_sig_figs(trigger_px, max_sig_figs=5)
                    if trigger_px <= current_price * 1.002:
                        print(f"⚠️ SL слишком близко: {trigger_px:.4f} <= {current_price:.4f}")
                        return None
            
            sl_size = round(position_size, sz_decimals)
            
            order_type = {
                "trigger": {
                    "triggerPx": trigger_px,
                    "isMarket": True,
                    "tpsl": "sl"
                }
            }
            
            result = self.exchange.order(
                coin,
                not is_long,
                sl_size,
                trigger_px,
                order_type,
                reduce_only=True
            )
            
            self._last_orders_fetch = 0
            return result
        
        except Exception as e:
            print(f"❌ Ошибка установки SL: {e}")
            import traceback
            traceback.print_exc()
            return None

    def set_tp_only(self, coin, trigger_price, size):
        """Установка Take Profit."""
        try:
            if not self.exchange:
                return None
            
            # ✅ КРИТИЧНО: Сбрасываем кеш перед проверкой
            self._last_orders_fetch = 0
            
            time.sleep(1.5)
            orders = self.get_open_orders(force_refresh=True)
            existing_tp = [o for o in orders if o["symbol"] == coin and o.get("tpsl") == "tp"]
            
            if existing_tp:
                for old_order in existing_tp:
                    self.cancel_order(coin, old_order["oid"])
                time.sleep(0.2)
            
            time.sleep(1.0)
            
            positions = self.get_open_positions()
            position = next((p for p in positions if p["symbol"] == coin), None)
            
            if not position:
                return None
            
            is_long = position["side"] == "long"
            entry_price = position["entry_price"]
            
            current_price = self.get_mid_price(coin)
            if not current_price:
                return None
            
            if coin not in self.asset_info:
                return None
            
            sz_decimals = self.asset_info[coin]["sz_decimals"]
            trigger_px = self.round_price_sig_figs(trigger_price, max_sig_figs=5)
            tp_size = round(size, sz_decimals)
            
            if is_long:
                if trigger_px <= current_price * 1.001:
                    trigger_px = max(current_price * 1.003, entry_price * 1.005)
                    trigger_px = self.round_price_sig_figs(trigger_px, max_sig_figs=5)
                    if trigger_px <= current_price * 1.002:
                        print(f"⚠️ TP слишком близко: {trigger_px:.4f} <= {current_price:.4f}")
                        return None
            else:
                if trigger_px >= current_price * 0.999:
                    trigger_px = min(current_price * 0.997, entry_price * 0.995)
                    trigger_px = self.round_price_sig_figs(trigger_px, max_sig_figs=5)
                    if trigger_px >= current_price * 0.998:
                        print(f"⚠️ TP слишком близко: {trigger_px:.4f} >= {current_price:.4f}")
                        return None
            
            order_type = {
                "trigger": {
                    "triggerPx": trigger_px,
                    "isMarket": True,
                    "tpsl": "tp"
                }
            }
            
            result = self.exchange.order(
                coin,
                not is_long,
                tp_size,
                trigger_px,
                order_type,
                reduce_only=True
            )
            
            self._last_orders_fetch = 0
            return result
        
        except Exception as e:
            print(f"❌ Ошибка установки TP: {e}")
            import traceback
            traceback.print_exc()
            return None


hl_api = HyperliquidAPI()
