import requests
import time
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

from config import (
    PERPLEXITY_API_KEY,
    PERPLEXITY_MODEL,
    PERPLEXITY_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
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
)


# ---------- Получение данных с Hyperliquid ----------
def get_market_data(symbols: list):
    """Получение свечей с Hyperliquid + расчёт индикаторов"""
    if not USE_HYPERLIQUID:
        return {}

    from hyperliquid_api import hl_api

    data_dict_outer = {}
    current_time = int(time.time() * 1000)

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
                data_dict[interval] = []
        data_dict_outer[symbol] = data_dict

    return data_dict_outer


# ---------- Расчёт индикаторов ----------
def calculate_ema(prices, period):
    """Экспоненциальная скользящая средняя"""
    if len(prices) < period:
        return None
    prices_arr = np.array(prices)
    ema = np.zeros_like(prices_arr)
    ema[period - 1] = np.mean(prices_arr[:period])
    multiplier = 2 / (period + 1)
    for i in range(period, len(prices_arr)):
        ema[i] = (prices_arr[i] - ema[i - 1]) * multiplier + ema[i - 1]
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
    ema_fast[fast - 1] = np.mean(prices_arr[:fast])
    ema_slow[slow - 1] = np.mean(prices_arr[:slow])
    mult_fast = 2 / (fast + 1)
    mult_slow = 2 / (slow + 1)
    for i in range(max(fast, slow), len(prices_arr)):
        if i >= fast:
            ema_fast[i] = (prices_arr[i] - ema_fast[i - 1]) * mult_fast + ema_fast[i - 1]
        if i >= slow:
            ema_slow[i] = (prices_arr[i] - ema_slow[i - 1]) * mult_slow + ema_slow[i - 1]
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


def calculate_indicators(candles):
    """Расчёт всех индикаторов для таймфрейма"""
    if not candles or len(candles) < 200:
        return {}
    closes = [c["c"] for c in candles]
    indicators = {
        "ema10": calculate_ema(closes, 10),
        "ema20": calculate_ema(closes, 20),
        "ema50": calculate_ema(closes, 50),
        "ema100": calculate_ema(closes, 100),
        "ema200": calculate_ema(closes, 200),
        "rsi": calculate_rsi(closes, 14),
    }
    macd, macd_signal, macd_hist = calculate_macd(closes)
    indicators["macd"] = macd
    indicators["macd_signal"] = macd_signal
    indicators["macd_hist"] = macd_hist
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
        return 0.0
    tr_values = []
    for i in range(1, len(candles)):
        high = candles[i]["h"]
        low = candles[i]["l"]
        prev_close = candles[i - 1]["c"]
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
        tr_values.append(tr)
    atr = sum(tr_values[-period:]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr


# ---------- AI API ----------
def call_ai_api(api_url, headers, payload, api_name):
    """Универсальный вызов AI API"""
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=120)
        if response.status_code != 200:
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
            return None, f"❌ {api_name} формат ответа некорректен:\n{result}"
        return action_line, reason_line
    except Exception as e:
        return None, f"❌ {api_name} ошибка: {str(e)[:50]}"

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
def analyze_with_openrouter(data_dict_outer):
    """Анализ через OpenRouter (DeepSeek)"""
    if not data_dict_outer or not any(
        any(tf_data for tf, tf_data in sym_data.items())
        for sym_data in data_dict_outer.values()
    ):
        return ("hold", "Нет данных")

    compressed_data = compress_market_data(data_dict_outer)
    prompt = AI_PROMPT_TEMPLATE.format(market_data=compressed_data)
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return ("hold", "❌ OpenRouter API ключ не найден")

    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3,
    }
    action_line, reason_line = call_ai_api(url, headers, payload, "OpenRouter")
    if not action_line:
        return ("hold", reason_line)

    if action_line.startswith("buy") or action_line.startswith("sell"):
        symbol = action_line.split("_", 1)[1].upper()
        if symbol in data_dict_outer:
            return (action_line, reason_line)
    return ("hold", reason_line)


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
        print(f" Действие: {perplexity_signal[0]}")
        print(f" Причина: {perplexity_signal[1]}")

    if USE_OPENROUTER:
        print("🤖 OpenRouter (DeepSeek) анализирует...")
        openrouter_signal = analyze_with_openrouter(data_dict_outer)
        signals.append(("openrouter", openrouter_signal))
        print(f" Действие: {openrouter_signal[0]}")
        print(f" Причина: {openrouter_signal[1]}")

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
