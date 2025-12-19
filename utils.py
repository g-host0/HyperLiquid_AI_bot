import os
import time
import requests
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from config import (
<<<<<<< HEAD
    PERPLEXITY_API_KEY,
    PERPLEXITY_MODEL,
    PERPLEXITY_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_ENABLE_CACHE_CONTROL,
    ENABLE_TWO_LEVEL_VERIFICATION,
    OPENROUTER_MODEL_LEVEL1,
    OPENROUTER_MODEL_LEVEL2,
    USE_PERPLEXITY,
    USE_OPENROUTER,
    SIGNAL_STRATEGY,
    SYMBOLS,
    LIMIT_1D,
    LIMIT_1H,
    LIMIT_1M,
    INTERVAL,
    USE_HYPERLIQUID,
    AI_PROMPT_TEMPLATE,
    AI_SYSTEM_PROMPT,
    AI_USER_DATA_TEMPLATE,
)


# ---------- Получение данных с Hyperliquid ----------
def get_market_data(symbols: list):
    """Получение свечей с Hyperliquid + расчёт индикаторов"""
    if not USE_HYPERLIQUID:
        return {}

=======
    PERPLEXITY_API_KEY, PERPLEXITY_MODEL, PERPLEXITY_BASE_URL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL,
    OPENROUTER_ENABLE_CACHE_CONTROL, ENABLE_TWO_LEVEL_VERIFICATION,
    OPENROUTER_MODEL_LEVEL1, OPENROUTER_MODEL_LEVEL2,
    USE_PERPLEXITY, USE_OPENROUTER, SIGNAL_STRATEGY,
    SYMBOLS, LIMIT_1D, LIMIT_1H, LIMIT_1M, USE_HYPERLIQUID,
    AI_SYSTEM_PROMPT, AI_USER_DATA_TEMPLATE,
    RSI_OVERBOUGHT, RSI_OVERSOLD, STOCH_OVERBOUGHT, STOCH_OVERSOLD,
    WILLR_OVERBOUGHT, WILLR_OVERSOLD
)

# ========== Получение данных ==========
def get_market_data(symbols: list):
    """Получение свечей с Hyperliquid."""
    if not USE_HYPERLIQUID:
        return {}
    
>>>>>>> 4ad6bb2 (upd)
    from hyperliquid_api import hl_api

    data_dict_outer = {}
    current_time = int(time.time() * 1000)
<<<<<<< HEAD

    for symbol in symbols:
        coin = symbol[:-4] if symbol.endswith("USDT") else symbol
        data_dict = {}
        intervals = {
            "1d": (LIMIT_1D, 86400),
            "1h": (LIMIT_1H, 3600),
            "1m": (LIMIT_1M, 60),
        }

        for interval, (limit, seconds_per_candle) in intervals.items():
            start_time = current_time - (limit * seconds_per_candle * 1000)
            candles = hl_api.get_candles_snapshot(
                coin, interval, start_time, current_time
            )
            if candles:
                data_dict[interval] = [
                    {
                        "t": int(c.get("t", 0)) / 1000,
                        "o": float(c.get("o", 0)),
                        "h": float(c.get("h", 0)),
                        "l": float(c.get("l", 0)),
                        "c": float(c.get("c", 0)),
                        "v": float(c.get("v", 0)),
                    }
                    for c in candles
                ]
            else:
=======
    intervals = {
        "1d": (LIMIT_1D, 86400),
        "1h": (LIMIT_1H, 3600),
        "1m": (LIMIT_1M, 60),
    }
    
    for symbol in symbols:
        coin = symbol[:-4] if symbol.endswith("USDT") else symbol
        data_dict = {}
        
        for interval, (limit, seconds_per_candle) in intervals.items():
            start_time = current_time - (limit * seconds_per_candle * 1000)
            try:
                if hl_api.info:
                    candles = hl_api.info.candles_snapshot(coin, interval, start_time, current_time)
                    if candles:
                        data_dict[interval] = [
                            {
                                "t": int(c.get("t", 0)) / 1000,
                                "o": float(c.get("o", 0)),
                                "h": float(c.get("h", 0)),
                                "l": float(c.get("l", 0)),
                                "c": float(c.get("c", 0)),
                                "v": float(c.get("v", 0)),
                            }
                            for c in candles
                        ]
                    else:
                        data_dict[interval] = []
                else:
                    data_dict[interval] = []
            except Exception:
>>>>>>> 4ad6bb2 (upd)
                data_dict[interval] = []
        data_dict_outer[symbol] = data_dict

    return data_dict_outer

<<<<<<< HEAD

# ---------- Расчёт индикаторов ----------
def calculate_ema(prices, period):
    """Экспоненциальная скользящая средняя"""
    if len(prices) < period:
        return None
    prices_arr = np.array(prices)
=======
# ========== Расчёт индикаторов ==========
def calculate_ema(prices, period: int):
    """Exponential Moving Average."""
    if prices is None or len(prices) < period:
        return None
    prices_arr = np.asarray(prices, dtype=float)
>>>>>>> 4ad6bb2 (upd)
    ema = np.zeros_like(prices_arr)
    ema[period - 1] = np.mean(prices_arr[:period])
    multiplier = 2 / (period + 1)
    for i in range(period, len(prices_arr)):
        ema[i] = (prices_arr[i] - ema[i - 1]) * multiplier + ema[i - 1]
<<<<<<< HEAD
    return ema[-1]


def calculate_rsi(prices, period=14):
    """Индекс относительной силы"""
    if len(prices) < period + 1:
        return None
    prices_arr = np.array(prices)
    deltas = np.diff(prices_arr)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """MACD индикатор"""
    if len(prices) < slow + signal:
        return None, None, None
    prices_arr = np.array(prices)
    ema_fast = np.zeros_like(prices_arr)
    ema_slow = np.zeros_like(prices_arr)
=======
    return float(ema[-1])

def calculate_rsi_series(prices, period: int = 14):
    """RSI series для StochRSI."""
    if prices is None or len(prices) < period + 1:
        return None
    prices_arr = np.asarray(prices, dtype=float)
    deltas = np.diff(prices_arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    rsi_values = []
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        rsi_values.append(rsi)
    
    return np.asarray(rsi_values, dtype=float)

def calculate_rsi(prices, period: int = 14):
    """RSI последнее значение."""
    rsi_series = calculate_rsi_series(prices, period=period)
    return float(rsi_series[-1]) if rsi_series is not None and len(rsi_series) > 0 else None

def calculate_macd(prices, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD: line, signal, histogram."""
    if prices is None or len(prices) < slow + signal:
        return None, None, None
    
    prices_arr = np.asarray(prices, dtype=float)
    ema_fast = np.zeros_like(prices_arr)
    ema_slow = np.zeros_like(prices_arr)
    
>>>>>>> 4ad6bb2 (upd)
    ema_fast[fast - 1] = np.mean(prices_arr[:fast])
    ema_slow[slow - 1] = np.mean(prices_arr[:slow])
    mult_fast = 2 / (fast + 1)
    mult_slow = 2 / (slow + 1)
<<<<<<< HEAD
=======
    
>>>>>>> 4ad6bb2 (upd)
    for i in range(max(fast, slow), len(prices_arr)):
        if i >= fast:
            ema_fast[i] = (prices_arr[i] - ema_fast[i - 1]) * mult_fast + ema_fast[i - 1]
        if i >= slow:
            ema_slow[i] = (prices_arr[i] - ema_slow[i - 1]) * mult_slow + ema_slow[i - 1]
<<<<<<< HEAD
    macd_line = ema_fast - ema_slow
    macd_signal = np.zeros_like(macd_line)
    start_idx = slow + signal - 2
    if start_idx < len(macd_line):
        macd_signal[start_idx] = np.mean(macd_line[slow - 1 : start_idx + 1])
        mult_signal = 2 / (signal + 1)
        for i in range(start_idx + 1, len(macd_line)):
            macd_signal[i] = (macd_line[i] - macd_signal[i - 1]) * mult_signal + macd_signal[i - 1]
    histogram = macd_line - macd_signal
    return macd_line[-1], macd_signal[-1], histogram[-1]
=======
    
    macd_line = ema_fast - ema_slow
    macd_signal = np.zeros_like(macd_line)
    start_idx = slow + signal - 2
    
    if start_idx >= len(macd_line):
        return None, None, None
    
    macd_signal[start_idx] = np.mean(macd_line[slow - 1 : start_idx + 1])
    mult_signal = 2 / (signal + 1)
    
    for i in range(start_idx + 1, len(macd_line)):
        macd_signal[i] = (macd_line[i] - macd_signal[i - 1]) * mult_signal + macd_signal[i - 1]
    
    histogram = macd_line - macd_signal
    return float(macd_line[-1]), float(macd_signal[-1]), float(histogram[-1])

def calculate_stochastic(candles, k_period: int = 14, d_period: int = 3, smooth_k: int = 3):
    """Stochastic Oscillator: %K и %D."""
    if not candles or len(candles) < k_period + max(smooth_k, d_period):
        return None, None
    
    highs = np.asarray([c["h"] for c in candles], dtype=float)
    lows = np.asarray([c["l"] for c in candles], dtype=float)
    closes = np.asarray([c["c"] for c in candles], dtype=float)
    
    raw_k = []
    for i in range(k_period - 1, len(candles)):
        hh = np.max(highs[i - k_period + 1 : i + 1])
        ll = np.min(lows[i - k_period + 1 : i + 1])
        denom = hh - ll
        k = 0.0 if denom == 0 else 100.0 * (closes[i] - ll) / denom
        raw_k.append(k)
    
    raw_k = np.asarray(raw_k, dtype=float)
    if len(raw_k) < smooth_k:
        return None, None
    
    k_smooth = np.convolve(raw_k, np.ones(smooth_k) / smooth_k, mode="valid")
    if len(k_smooth) < d_period:
        return float(k_smooth[-1]), None
    
    d_line = np.convolve(k_smooth, np.ones(d_period) / d_period, mode="valid")
    return float(k_smooth[-1]), float(d_line[-1])

def calculate_williams_r(candles, period: int = 14):
    """Williams %R."""
    if not candles or len(candles) < period:
        return None
    
    highs = np.asarray([c["h"] for c in candles], dtype=float)
    lows = np.asarray([c["l"] for c in candles], dtype=float)
    closes = np.asarray([c["c"] for c in candles], dtype=float)
    
    hh = np.max(highs[-period:])
    ll = np.min(lows[-period:])
    denom = hh - ll
    
    return 0.0 if denom == 0 else float(-100.0 * (hh - closes[-1]) / denom)

def calculate_stoch_rsi(prices, rsi_period: int = 14, stoch_period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    """Stochastic RSI."""
    rsi_series = calculate_rsi_series(prices, period=rsi_period)
    if rsi_series is None or len(rsi_series) < stoch_period + max(smooth_k, smooth_d):
        return None, None
    
    raw = []
    for i in range(stoch_period - 1, len(rsi_series)):
        window = rsi_series[i - stoch_period + 1 : i + 1]
        lo, hi = np.min(window), np.max(window)
        denom = hi - lo
        k = 0.0 if denom == 0 else 100.0 * (rsi_series[i] - lo) / denom
        raw.append(k)
    
    raw = np.asarray(raw, dtype=float)
    if len(raw) < smooth_k:
        return None, None
    
    k_smooth = np.convolve(raw, np.ones(smooth_k) / smooth_k, mode="valid")
    if len(k_smooth) < smooth_d:
        return float(k_smooth[-1]), None
    
    d_line = np.convolve(k_smooth, np.ones(smooth_d) / smooth_d, mode="valid")
    return float(k_smooth[-1]), float(d_line[-1])

def _ob_os_state(value: float, overbought: float, oversold: float, invert: bool = False):
    """Определение состояния OB/OS."""
    if value is None:
        return None
    
    if not invert:
        if value >= overbought:
            return "overbought"
        if value <= oversold:
            return "oversold"
        return "neutral"
    
    # Для Williams %R
    if value >= overbought:
        return "overbought"
    if value <= oversold:
        return "oversold"
    return "neutral"
>>>>>>> 4ad6bb2 (upd)


def calculate_indicators(candles):
    """Расчёт всех индикаторов для таймфрейма."""
    if not candles:
        return {}
    closes = [c["c"] for c in candles]
<<<<<<< HEAD
    indicators = {
        "ema10": calculate_ema(closes, 10),
        "ema20": calculate_ema(closes, 20),
        "ema50": calculate_ema(closes, 50),
        "ema100": calculate_ema(closes, 100),
        "ema200": calculate_ema(closes, 200),
        "rsi": calculate_rsi(closes, 14),
    }
=======
    indicators = {}
    
    # EMA
    for p in (10, 20, 50, 100, 200):
        v = calculate_ema(closes, p)
        if v is not None:
            indicators[f"ema{p}"] = v
    
    # RSI
    rsi = calculate_rsi(closes, 14)
    indicators["rsi"] = rsi
    indicators["rsi_state"] = _ob_os_state(rsi, RSI_OVERBOUGHT, RSI_OVERSOLD)
    
    # MACD
>>>>>>> 4ad6bb2 (upd)
    macd, macd_signal, macd_hist = calculate_macd(closes)
    indicators["macd"] = macd
    indicators["macd_signal"] = macd_signal
    indicators["macd_hist"] = macd_hist
<<<<<<< HEAD
    return indicators


# ---------- Сжатие данных для AI ----------
def compress_market_data(data_dict_outer):
    """Сжатие данных с индикаторами для отправки в AI"""
    compressed = []
    for symbol, tf_data in data_dict_outer.items():
        summary = f"\n{symbol}:"
        for interval in ["1d", "1h"]:
            if interval in tf_data:
                candles = tf_data[interval]
                if candles:
                    last = candles[-1]
                    first = candles[0]
                    trend = "📈" if last["c"] > first["o"] else "📉"
                    high_max = max(c["h"] for c in candles)
                    low_min = min(c["l"] for c in candles)
                    avg_volume = (
                        sum(c["v"] for c in candles) / len(candles) if candles else 0
                    )
                    indicators = calculate_indicators(candles)
                    summary += (
                        f"\n {interval}: {trend} "
                        f"O:{last['o']:.4f} H:{last['h']:.4f} "
                        f"L:{last['l']:.4f} C:{last['c']:.4f} | "
                        f"MaxH:{high_max:.4f} MinL:{low_min:.4f} "
                        f"Vol:{avg_volume:.2f} ({len(candles)})"
                    )
                    if indicators.get("ema10"):
                        summary += (
                            f"\n EMA: 10={indicators['ema10']:.2f} "
                            f"20={indicators['ema20']:.2f} "
                            f"50={indicators['ema50']:.2f} "
                            f"100={indicators['ema100']:.2f} "
                            f"200={indicators['ema200']:.2f}"
                        )
                    if indicators.get("rsi") is not None:
                        summary += f"\n RSI: {indicators['rsi']:.1f}"
                    if indicators.get("macd") is not None:
                        macd_trend = "🟢" if indicators["macd_hist"] > 0 else "🔴"
                        summary += (
                            f"\n MACD: {macd_trend} {indicators['macd']:.2f} "
                            f"Signal:{indicators['macd_signal']:.2f} "
                            f"Hist:{indicators['macd_hist']:.2f}"
                        )
                else:
                    summary += f"\n {interval}: Нет данных"
        compressed.append(summary)
    return "\n".join(compressed)


# ---------- ATR ----------
def calculate_atr(candles, period=14):
    """Average True Range (ATR)"""
    if len(candles) < period + 1:
=======
    
    # Stochastic
    stoch_k, stoch_d = calculate_stochastic(candles, 14, 3, 3)
    indicators["stoch_k"] = stoch_k
    indicators["stoch_d"] = stoch_d
    indicators["stoch_state"] = _ob_os_state(stoch_k, STOCH_OVERBOUGHT, STOCH_OVERSOLD)
    
    # Williams %R
    willr = calculate_williams_r(candles, 14)
    indicators["willr"] = willr
    indicators["willr_state"] = _ob_os_state(willr, WILLR_OVERBOUGHT, WILLR_OVERSOLD, invert=True)
    
    # StochRSI
    stochrsi_k, stochrsi_d = calculate_stoch_rsi(closes, 14, 14, 3, 3)
    indicators["stochrsi_k"] = stochrsi_k
    indicators["stochrsi_d"] = stochrsi_d
    indicators["stochrsi_state"] = _ob_os_state(stochrsi_k, STOCH_OVERBOUGHT, STOCH_OVERSOLD)
    
    return indicators

def calculate_atr(candles, period: int = 14):
    """Average True Range."""
    if not candles or len(candles) < period + 1:
>>>>>>> 4ad6bb2 (upd)
        return 0.0
    tr_values = []
    for i in range(1, len(candles)):
        high = candles[i]["h"]
        low = candles[i]["l"]
        prev_close = candles[i - 1]["c"]
<<<<<<< HEAD
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
=======
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
>>>>>>> 4ad6bb2 (upd)
        tr_values.append(tr)
    atr = sum(tr_values[-period:]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
<<<<<<< HEAD
    return atr


# ---------- AI API ----------
=======
    
    return float(atr)

# ========== Сжатие данных для AI ==========
def compress_market_data(data_dict_outer):
    """Компрессия рыночных данных с индикаторами."""
    compressed = []
    
    for symbol, tf_data in data_dict_outer.items():
        summary = f"\n{symbol}:"
        
        for interval in ["1d", "1h", "1m"]:
            candles = tf_data.get(interval, [])
            if not candles:
                summary += f"\n {interval}: Нет данных"
                continue
            
            last = candles[-1]
            first = candles[0]
            trend = "📈" if last["c"] > first["o"] else "📉"
            high_max = max(c["h"] for c in candles)
            low_min = min(c["l"] for c in candles)
            avg_volume = sum(c["v"] for c in candles) / len(candles)
            
            indicators = calculate_indicators(candles)
            
            summary += (
                f"\n {interval}: {trend} "
                f"O:{last['o']:.4f} H:{last['h']:.4f} "
                f"L:{last['l']:.4f} C:{last['c']:.4f} | "
                f"MaxH:{high_max:.4f} MinL:{low_min:.4f} "
                f"Vol:{avg_volume:.2f} ({len(candles)})"
            )
            
            # EMA
            ema_parts = [f"{p}={indicators[f'ema{p}']:.2f}" 
                        for p in (10, 20, 50, 100, 200) 
                        if f"ema{p}" in indicators and indicators[f"ema{p}"] is not None]
            if ema_parts:
                summary += "\n EMA: " + " ".join(ema_parts)
            
            # RSI + состояние
            if indicators.get("rsi") is not None:
                rsi_state = indicators.get("rsi_state", "neutral")
                summary += f"\n RSI: {indicators['rsi']:.1f} ({rsi_state})"
            
            # Осцилляторы OB/OS
            osc_parts = []
            if indicators.get("stoch_k") is not None:
                st_state = indicators.get("stoch_state", "neutral")
                d_txt = f"/{indicators['stoch_d']:.1f}" if indicators.get("stoch_d") is not None else ""
                osc_parts.append(f"Stoch:{indicators['stoch_k']:.1f}{d_txt}({st_state})")
            
            if indicators.get("stochrsi_k") is not None:
                sr_state = indicators.get("stochrsi_state", "neutral")
                d_txt = f"/{indicators['stochrsi_d']:.1f}" if indicators.get("stochrsi_d") is not None else ""
                osc_parts.append(f"StochRSI:{indicators['stochrsi_k']:.1f}{d_txt}({sr_state})")
            
            if indicators.get("willr") is not None:
                wr_state = indicators.get("willr_state", "neutral")
                osc_parts.append(f"WillR:{indicators['willr']:.1f}({wr_state})")
            
            if osc_parts:
                summary += "\n OB/OS: " + " | ".join(osc_parts)
            
            # MACD
            if indicators.get("macd") is not None and indicators.get("macd_hist") is not None:
                macd_trend = "🟢" if indicators["macd_hist"] > 0 else "🔴"
                summary += (
                    f"\n MACD: {macd_trend} {indicators['macd']:.2f} "
                    f"Signal:{(indicators.get('macd_signal') or 0):.2f} "
                    f"Hist:{indicators['macd_hist']:.2f}"
                )
        
        compressed.append(summary)
    
    return "\n".join(compressed)

# ========== AI API ==========
>>>>>>> 4ad6bb2 (upd)
def call_ai_api(api_url, headers, payload, api_name):
    """Универсальный вызов AI API."""
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=120)
        if response.status_code != 200:
            try:
                error_detail = response.json()
                print(f"❌ {api_name} error: {error_detail.get('error', {}).get('message', 'Unknown error')}")
            except Exception:
                print(f"❌ {api_name} error {response.status_code}: {response.text[:200]}")
            return None, f"❌ {api_name} API error: {response.status_code}"
        result_json = response.json()
        result = result_json["choices"][0]["message"]["content"].strip()
        result = result.replace("**", "").replace("*", "")
        action_line, reason_line = None, None
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("Action"):
                action_line = line.split("Action:", 1)[1].strip()
            elif line.startswith("Reason"):
                reason_line = line.split("Reason:", 1)[1].strip()
        if not action_line or not reason_line:
<<<<<<< HEAD
            return None, f"❌ {api_name} формат ответа некорректен:\n{result}"
=======
            return None, f"❌ {api_name} формат ответа некорректен"
        
>>>>>>> 4ad6bb2 (upd)
        return action_line, reason_line
    except Exception as e:
        return None, f"❌ {api_name} ошибка: {str(e)}"

<<<<<<< HEAD
# ---------- Perplexity AI ----------
def analyze_with_perplexity(data_dict_outer):
    """Анализ через Perplexity AI"""
    if not data_dict_outer or not any(
        any(tf_data for tf, tf_data in sym_data.items())
        for sym_data in data_dict_outer.values()
    ):
        return ("hold", "Нет данных")

    compressed_data = compress_market_data(data_dict_outer)
    prompt = AI_PROMPT_TEMPLATE.format(market_data=compressed_data)
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return ("hold", "❌ Perplexity API ключ не найден")

    url = f"{PERPLEXITY_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3,
    }
    action_line, reason_line = call_ai_api(url, headers, payload, "Perplexity")
    if not action_line:
        return ("hold", reason_line)

    if action_line.startswith("buy") or action_line.startswith("sell"):
        symbol = action_line.split("_", 1)[1].upper()
        if symbol in data_dict_outer:
            return (action_line, reason_line)
    return ("hold", reason_line)


# ---------- OpenRouter (DeepSeek) ----------
def call_openrouter_model(model_name, user_data, api_name="OpenRouter"):
    """Вспомогательная функция для вызова OpenRouter с указанной моделью"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None, f"❌ OpenRouter API ключ не найден"

=======
def call_openrouter_model(model_name, user_data, api_name="OpenRouter"):
    """Вызов OpenRouter с указанной моделью."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None, "❌ OpenRouter API ключ не найден"
    
>>>>>>> 4ad6bb2 (upd)
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
<<<<<<< HEAD
    # Разделяем системный промпт (кэшируется) и пользовательские данные
    system_message = {
        "role": "system",
        "content": AI_SYSTEM_PROMPT
    }
    
    # Добавляем cache_control для явного кэширования (если включено в настройках)
    if OPENROUTER_ENABLE_CACHE_CONTROL:
        system_message["cache_control"] = {"type": "ephemeral"}
    
    messages = [
        system_message,
        {
            "role": "user",
            "content": user_data
        }
    ]
    
=======
    system_message = {"role": "system", "content": AI_SYSTEM_PROMPT}
    if OPENROUTER_ENABLE_CACHE_CONTROL:
        system_message["cache_control"] = {"type": "ephemeral"}
    
    messages = [system_message, {"role": "user", "content": user_data}]
>>>>>>> 4ad6bb2 (upd)
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.3,
    }
    
    return call_ai_api(url, headers, payload, api_name)

<<<<<<< HEAD

def analyze_with_openrouter(data_dict_outer):
    """Анализ через OpenRouter (DeepSeek) с двухуровневой верификацией"""
    if not data_dict_outer or not any(
        any(tf_data for tf, tf_data in sym_data.items())
        for sym_data in data_dict_outer.values()
    ):
        return ("hold", "Нет данных")

    compressed_data = compress_market_data(data_dict_outer)
    user_data = AI_USER_DATA_TEMPLATE.format(market_data=compressed_data)
    
    # Первый уровень - первичный анализ
    print(f"🔍 Уровень 1 ({OPENROUTER_MODEL_LEVEL1}): первичный анализ...")
    action_line, reason_line = call_openrouter_model(
        OPENROUTER_MODEL_LEVEL1, 
        user_data, 
        f"OpenRouter Level1 ({OPENROUTER_MODEL_LEVEL1})"
=======
def analyze_with_openrouter(data_dict_outer):
    """Анализ через OpenRouter с двухуровневой верификацией."""
    if not data_dict_outer or not any(any(tf_data for tf_data in sym_data.values()) for sym_data in data_dict_outer.values()):
        return ("hold", "Нет данных")
    
    compressed_data = compress_market_data(data_dict_outer)
    user_data = AI_USER_DATA_TEMPLATE.format(market_data=compressed_data)
    
    if not ENABLE_TWO_LEVEL_VERIFICATION:
        model_to_use = OPENROUTER_MODEL if OPENROUTER_MODEL else OPENROUTER_MODEL_LEVEL1
        print(f"🔍 Анализ ({model_to_use})...")
        action_line, reason_line = call_openrouter_model(model_to_use, user_data, f"OpenRouter ({model_to_use})")
        
        if not action_line:
            return ("hold", reason_line)
        
        print(f"  Результат: {action_line} | {reason_line}")
        
        if action_line.startswith("buy") or action_line.startswith("sell"):
            symbol = action_line.split("_", 1)[1].upper()
            if symbol in data_dict_outer:
                return (action_line, reason_line)
        
        return ("hold", reason_line)
    
    # Первый уровень
    print(f"🔍 Уровень 1 ({OPENROUTER_MODEL_LEVEL1}): первичный анализ...")
    action_line, reason_line = call_openrouter_model(
        OPENROUTER_MODEL_LEVEL1,
        user_data,
        f"OpenRouter Level1 ({OPENROUTER_MODEL_LEVEL1})",
>>>>>>> 4ad6bb2 (upd)
    )
    
    if not action_line:
        return ("hold", reason_line)
    
<<<<<<< HEAD
    print(f"   Результат: {action_line} | {reason_line}")
    
    # Проверяем, нужна ли верификация второго уровня
    needs_verification = (
        ENABLE_TWO_LEVEL_VERIFICATION and 
        (action_line.startswith("buy") or action_line.startswith("sell"))
    )
    
    if not needs_verification:
        # Если верификация отключена или сигнал "hold" - возвращаем результат первого уровня
        if action_line.startswith("buy") or action_line.startswith("sell"):
            symbol = action_line.split("_", 1)[1].upper()
            if symbol in data_dict_outer:
                return (action_line, reason_line)
        return ("hold", reason_line)
    
    # Второй уровень - подтверждение сигнала
    print(f"✅ Уровень 2 ({OPENROUTER_MODEL_LEVEL2}): подтверждение сигнала...")
    action_line2, reason_line2 = call_openrouter_model(
        OPENROUTER_MODEL_LEVEL2,
        user_data,
        f"OpenRouter Level2 ({OPENROUTER_MODEL_LEVEL2})"
    )
    
    if not action_line2:
        print(f"   ⚠️ Ошибка подтверждения, сигнал отклонен (безопасность)")
        return ("hold", f"Ошибка подтверждения: {reason_line2}")
    
    print(f"   Результат: {action_line2} | {reason_line2}")
    
    # Проверяем согласованность сигналов
    if action_line2.startswith("buy") or action_line2.startswith("sell"):
        symbol2 = action_line2.split("_", 1)[1].upper()
        
        # Проверяем, что оба уровня дали одинаковый сигнал (buy/sell для одного символа)
        if (action_line.startswith("buy") and action_line2.startswith("buy") and 
            action_line.split("_", 1)[1].upper() == symbol2):
            print(f"   ✅ Подтверждено: BUY {symbol2}")
            if symbol2 in data_dict_outer:
                return (action_line2, f"Подтверждено: {reason_line2}")
        elif (action_line.startswith("sell") and action_line2.startswith("sell") and 
              action_line.split("_", 1)[1].upper() == symbol2):
            print(f"   ✅ Подтверждено: SELL {symbol2}")
            if symbol2 in data_dict_outer:
                return (action_line2, f"Подтверждено: {reason_line2}")
        else:
            # Сигналы не совпали
            print(f"   ❌ Сигналы не совпали: Level1={action_line}, Level2={action_line2}")
            return ("hold", f"Сигналы не совпали: {action_line} vs {action_line2}")
    else:
        # Второй уровень дал "hold" - отклоняем сигнал
        print(f"   ❌ Подтверждение отклонено: Level2 дал 'hold'")
        return ("hold", f"Подтверждение отклонено: {reason_line2}")
=======
    print(f"  Результат: {action_line} | {reason_line}")
>>>>>>> 4ad6bb2 (upd)
    
    needs_verification = action_line.startswith("buy") or action_line.startswith("sell")
    if not needs_verification:
        return ("hold", reason_line)
    
    # Второй уровень
    print(f"✅ Уровень 2 ({OPENROUTER_MODEL_LEVEL2}): подтверждение сигнала...")
    action_line2, reason_line2 = call_openrouter_model(
        OPENROUTER_MODEL_LEVEL2,
        user_data,
        f"OpenRouter Level2 ({OPENROUTER_MODEL_LEVEL2})",
    )
    
    if not action_line2:
        print("  ⚠️ Ошибка подтверждения, сигнал отклонен")
        return ("hold", f"Ошибка подтверждения: {reason_line2}")
    
    print(f"  Результат: {action_line2} | {reason_line2}")
    
    if not (action_line2.startswith("buy") or action_line2.startswith("sell")):
        print("  ❌ Подтверждение отклонено: Level2 дал 'hold'")
        return ("hold", f"Подтверждение отклонено: {reason_line2}")
    
    # Проверка совпадения
    sym1 = action_line.split("_", 1)[1].upper() if "_" in action_line else ""
    sym2 = action_line2.split("_", 1)[1].upper() if "_" in action_line2 else ""
    act1 = action_line.split("_", 1)[0]
    act2 = action_line2.split("_", 1)[0]
    
    if act1 == act2 and sym1 == sym2 and sym2 in data_dict_outer:
        print(f"  ✅ Подтверждено: {act2.upper()} {sym2}")
        return (action_line2, f"Подтверждено: {reason_line2}")
    
    print(f"  ❌ Сигналы не совпали: Level1={action_line}, Level2={action_line2}")
    return ("hold", f"Сигналы не совпали")

<<<<<<< HEAD

# ---------- Объединение сигналов ----------
def combine_ai_signals(perplexity_signal, openrouter_signal, strategy):
    """Объединение сигналов от нескольких AI"""
    pplx_action, pplx_reason = perplexity_signal
    or_action, or_reason = openrouter_signal

    if strategy == "unanimous":
        if pplx_action == or_action:
            return pplx_action, f"🤝 Единогласно: {pplx_reason}"
        else:
            return "hold", (
                f"⚠️ Сигналы расходятся: Perplexity={pplx_action}, "
                f"OpenRouter={or_action}"
            )

    elif strategy == "priority_perplexity":
        if pplx_action != "hold":
            if or_action == pplx_action:
                return pplx_action, f"✅ Подтверждено: {pplx_reason}"
            else:
                return pplx_action, f"⚡ Приоритет Perplexity: {pplx_reason}"
        return "hold", f"🔵 Hold: {pplx_reason}"

    elif strategy == "priority_openrouter":
        if or_action != "hold":
            if pplx_action == or_action:
                return or_action, f"✅ Подтверждено: {or_reason}"
            else:
                return or_action, f"⚡ Приоритет OpenRouter: {or_reason}"
        return "hold", f"🔵 Hold: {or_reason}"

    elif strategy == "any":
        if pplx_action != "hold":
            return pplx_action, f"🟢 Perplexity: {pplx_reason}"
        elif or_action != "hold":
            return or_action, f"🟢 OpenRouter: {or_reason}"
        return "hold", "⚪ Hold"

    return "hold", "⚪ Нет сигналов"


# ---------- Основной анализ ----------
def analyze_with_ai(data_dict_outer):
    """Главная функция анализа с отображением ответов AI"""
    signals = []
    print("\n" + "=" * 60)
    print("🧠 АНАЛИЗ AI")
    print("=" * 60)

    if USE_PERPLEXITY:
        print("🔮 Perplexity AI анализирует...")
        perplexity_signal = analyze_with_perplexity(data_dict_outer)
        signals.append(("perplexity", perplexity_signal))

    if USE_OPENROUTER:
        print("🤖 OpenRouter AI анализирует...")
        openrouter_signal = analyze_with_openrouter(data_dict_outer)
        signals.append(("openrouter", openrouter_signal))

    print("=" * 60 + "\n")

    if not signals:
        return "hold", "❌ AI не включены"

    if len(signals) == 1:
        return signals[0][1]

    perplexity_signal = next(
        (s[1] for s in signals if s[0] == "perplexity"), ("hold", "")
    )
    openrouter_signal = next(
        (s[1] for s in signals if s[0] == "openrouter"), ("hold", "")
    )
    return combine_ai_signals(perplexity_signal, openrouter_signal, SIGNAL_STRATEGY)
=======
def analyze_with_ai(data_dict_outer):
    """Главная функция анализа."""
    print("\n" + "=" * 60)
    print("🧠 АНАЛИЗ AI")
    print("=" * 60)
    
    if USE_OPENROUTER:
        print("🤖 OpenRouter AI анализирует...")
        openrouter_signal = analyze_with_openrouter(data_dict_outer)
        print("=" * 60 + "\n")
        return openrouter_signal
    
    print("=" * 60 + "\n")
    return ("hold", "❌ AI не включены")
>>>>>>> 4ad6bb2 (upd)
