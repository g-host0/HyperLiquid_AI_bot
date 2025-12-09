import requests
import time
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

from config import (
    PERPLEXITY_API_KEY, PERPLEXITY_MODEL, PERPLEXITY_BASE_URL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL,
    USE_PERPLEXITY, USE_OPENROUTER, SIGNAL_STRATEGY,
    SYMBOLS, LIMIT_1D, LIMIT_1H, LIMIT_1M, INTERVAL, USE_HYPERLIQUID,
    AI_PROMPT_TEMPLATE
)

def get_market_data(symbols):
    """Получает данные для list символов только из Hyperliquid."""
    from hyperliquid_api import hl_api
    data_dict_outer = {}
    current_time = int(time.time() * 1000)
    
    for symbol in symbols:
        coin = symbol[:-4] if symbol.endswith("USDT") else symbol
        data_dict = {}
        
        intervals = {
            '1d': (LIMIT_1D, 86400),
            '1h': (LIMIT_1H, 3600),
            '1m': (LIMIT_1M, 60)
        }
        
        for interval, (limit, seconds_per_candle) in intervals.items():
            start_time = current_time - (limit * seconds_per_candle * 1000)
            
            try:
                if hl_api.info:
                    candles = hl_api.info.candles_snapshot(
                        coin, interval, start_time, current_time
                    )
                    
                    if candles and len(candles) > 0:
                        data_dict[interval] = [{
                            "t": int(c.get('t', 0)) / 1000,
                            "o": float(c.get('o', 0)),
                            "h": float(c.get('h', 0)),
                            "l": float(c.get('l', 0)),
                            "c": float(c.get('c', 0)),
                            "v": float(c.get('v', 0))
                        } for c in candles]
                        print(f"✅ Hyperliquid: {symbol} {interval} - получено {len(candles)} свечей")
                    else:
                        data_dict[interval] = []
                        print(f"⚠️ Hyperliquid: {symbol} {interval} - нет данных")
                else:
                    data_dict[interval] = []
                    print(f"❌ Hyperliquid info API недоступен")
            except Exception as e:
                print(f"❌ Ошибка Hyperliquid для {symbol} {interval}: {e}")
                data_dict[interval] = []
        
        data_dict_outer[symbol] = data_dict
    
    return data_dict_outer

def compress_market_data(data_dict_outer):
    """Сжимает рыночные данные для уменьшения длины промпта"""
    compressed = []
    
    for symbol, tf_data in data_dict_outer.items():
        summary = f"{symbol}:"
        
        for interval in ['1d', '1h', '1m']:
            if interval in tf_data:
                candles = tf_data[interval]
                if candles:
                    first = candles[0]
                    last = candles[-1]
                    trend = "▲" if last['c'] > first['o'] else "▼"
                    high_max = max(c['h'] for c in candles)
                    low_min = min(c['l'] for c in candles)
                    avg_volume = sum(c['v'] for c in candles) / len(candles) if candles else 0
                    
                    summary += (
                        f"\n  {interval}: {trend} O:{last['o']:.4f} H:{last['h']:.4f} "
                        f"L:{last['l']:.4f} C:{last['c']:.4f} | "
                        f"MaxH:{high_max:.4f} MinL:{low_min:.4f} Vol:{avg_volume:.2f} "
                        f"({len(candles)} свеч)"
                    )
                else:
                    summary += f"\n  {interval}: Нет данных"
        
        compressed.append(summary)
    
    return "\n\n".join(compressed)

def calculate_atr(candles, period=14):
    """Рассчитывает Average True Range (ATR) для списка свечей"""
    if len(candles) < period + 1:
        return 0.0
    
    tr_values = []
    for i in range(1, len(candles)):
        high = candles[i]['h']
        low = candles[i]['l']
        prev_close = candles[i-1]['c']
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
        tr_values.append(tr)
    
    atr = sum(tr_values[:period]) / period
    
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    
    return atr

def call_ai_api(api_url, headers, payload, api_name):
    """Универсальная функция для вызова AI API"""
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=120)
        
        if response.status_code != 200:
            print(f"Ошибка API {api_name}: {response.status_code}")
            print(f"Ответ: {response.text[:500]}")
            return None, f'Ошибка API: {response.status_code}'
        
        result_json = response.json()
        result = result_json['choices'][0]['message']['content'].strip()
        
        # Парсинг результата
        action_line, reason_line = None, None
        for line in result.split('\n'):
            if line.startswith('Action:'):
                action_line = line.split('Action:')[1].strip()
            elif line.startswith('Reason:'):
                reason_line = line.split('Reason:')[1].strip()
        
        if not action_line or not reason_line:
            return None, f'Неверный формат ответа: {result}'
        
        return action_line, reason_line
    
    except Exception as e:
        print(f"Ошибка {api_name} AI: {e}")
        import traceback
        traceback.print_exc()
        return None, f'Ошибка анализа: {str(e)[:50]}'

def analyze_with_perplexity(data_dict_outer):
    """Анализирует данные всех символов через Perplexity AI"""
    if not data_dict_outer or not any(any(tf_data for tf, tf_data in sym_data.items()) for sym_data in data_dict_outer.values()):
        return 'hold', 'Нет данных для анализа'
    
    compressed_data = compress_market_data(data_dict_outer)
    prompt = AI_PROMPT_TEMPLATE.format(market_data=compressed_data)
    
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        print("❌ PERPLEXITY_API_KEY не найден в переменных окружения!")
        return 'hold', 'API ключ не найден'
    
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3
    }
    
    action_line, reason_line = call_ai_api(url, headers, payload, "Perplexity")
    
    if not action_line:
        return 'hold', reason_line
    
    if action_line.startswith('buy_') or action_line.startswith('sell_'):
        symbol = action_line.split('_')[1].upper()
        if symbol in data_dict_outer:
            return action_line, reason_line
    
    return 'hold', reason_line

def analyze_with_openrouter(data_dict_outer):
    """Анализирует данные всех символов через OpenRouter (DeepSeek)"""
    if not data_dict_outer or not any(any(tf_data for tf, tf_data in sym_data.items()) for sym_data in data_dict_outer.values()):
        return 'hold', 'Нет данных для анализа'
    
    compressed_data = compress_market_data(data_dict_outer)
    prompt = AI_PROMPT_TEMPLATE.format(market_data=compressed_data)
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY не найден в переменных окружения!")
        return 'hold', 'API ключ не найден'
    
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3
    }
    
    action_line, reason_line = call_ai_api(url, headers, payload, "OpenRouter")
    
    if not action_line:
        return 'hold', reason_line
    
    if action_line.startswith('buy_') or action_line.startswith('sell_'):
        symbol = action_line.split('_')[1].upper()
        if symbol in data_dict_outer:
            return action_line, reason_line
    
    return 'hold', reason_line

def combine_ai_signals(perplexity_signal, openrouter_signal, strategy):
    """Объединяет сигналы от двух AI согласно выбранной стратегии"""
    pplx_action, pplx_reason = perplexity_signal
    or_action, or_reason = openrouter_signal
    
    if strategy == "unanimous":
        if pplx_action == or_action:
            return pplx_action, f"Perplexity: {pplx_reason} | OpenRouter: {or_reason}"
        else:
            return 'hold', f"Сигналы расходятся. Perplexity: {pplx_action} ({pplx_reason}) | OpenRouter: {or_action} ({or_reason})"
    
    elif strategy == "priority_perplexity":
        if pplx_action != 'hold':
            if or_action == pplx_action:
                return pplx_action, f"✓ Подтверждено обоими: {pplx_reason}"
            else:
                return pplx_action, f"⚠ Perplexity: {pplx_reason} (OpenRouter не подтвердил: {or_action})"
        return 'hold', f"Perplexity: hold | OpenRouter: {or_action}"
    
    elif strategy == "priority_openrouter":
        if or_action != 'hold':
            if pplx_action == or_action:
                return or_action, f"✓ Подтверждено обоими: {or_reason}"
            else:
                return or_action, f"⚠ OpenRouter: {or_reason} (Perplexity не подтвердил: {pplx_action})"
        return 'hold', f"OpenRouter: hold | Perplexity: {pplx_action}"
    
    elif strategy == "any":
        if pplx_action != 'hold':
            return pplx_action, f"Perplexity: {pplx_reason}"
        elif or_action != 'hold':
            return or_action, f"OpenRouter: {or_reason}"
        return 'hold', "Оба AI рекомендуют hold"
    
    return 'hold', 'Неизвестная стратегия'

def analyze_with_ai(data_dict_outer):
    """Основная функция анализа - использует включенные AI и объединяет сигналы"""
    signals = []
    
    if USE_PERPLEXITY:
        print("📊 Запрос к Perplexity AI...")
        perplexity_signal = analyze_with_perplexity(data_dict_outer)
        print(f"  Perplexity: {perplexity_signal[0]} - {perplexity_signal[1]}")
        signals.append(('perplexity', perplexity_signal))
    
    if USE_OPENROUTER:
        print("📊 Запрос к OpenRouter (DeepSeek)...")
        openrouter_signal = analyze_with_openrouter(data_dict_outer)
        print(f"  OpenRouter: {openrouter_signal[0]} - {openrouter_signal[1]}")
        signals.append(('openrouter', openrouter_signal))
    
    if not signals:
        return 'hold', 'Нет активных AI для анализа (проверьте USE_PERPLEXITY и USE_OPENROUTER в config)'
    
    if len(signals) == 1:
        return signals[0][1]
    
    perplexity_signal = next((s[1] for s in signals if s[0] == 'perplexity'), ('hold', ''))
    openrouter_signal = next((s[1] for s in signals if s[0] == 'openrouter'), ('hold', ''))
    
    return combine_ai_signals(perplexity_signal, openrouter_signal, SIGNAL_STRATEGY)
