import requests
import time
from dotenv import load_dotenv
import os
load_dotenv()

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL, SYMBOLS, LIMIT_1D, LIMIT_1H, LIMIT_1M, INTERVAL, USE_HYPERLIQUID
from openai import OpenAI

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL
)

def get_market_data(symbols):
    """Получает данные для list символов (HL attempts если enabled, иначе direct Binance). Возвращает {symbol: {'1d': [...], '1h': [...], '1m': [...]}}."""
    data_dict_outer = {}
    
    for symbol in symbols:
        coin = symbol[:-4] if symbol.endswith("USDT") else symbol  # HL coin (ETH for ETHUSDT)
        binance_symbol = symbol.upper()
        data_dict = {}
        intervals = {'1d': LIMIT_1D, '1h': LIMIT_1H, '1m': LIMIT_1M}
        
        for interval, limit in intervals.items():
            data_source = "Binance"  # Default
            
            if USE_HYPERLIQUID:
                # Attempts HL если enabled — отключено по умолчанию для скорости
                payloads = [
                    {"type": "candles", "coin": coin, "interval": interval, "startTime": int(time.time() - (limit * (86400 if interval=='1d' else 3600 if interval=='1h' else 60))), "endTime": int(time.time())},
                    {"type": "candles", "req": {"coin": coin, "interval": interval, "startTime": int(time.time() - (limit * (86400 if interval=='1d' else 3600 if interval=='1h' else 60))), "endTime": int(time.time())}},
                    {"type": "candle_snapshot", "coin": coin, "interval": interval}
                ]
                
                for idx, hl_payload in enumerate(payloads):
                    try:
                        hl_url = "https://api.hyperliquid.xyz/info"
                        response = requests.post(hl_url, json=hl_payload, timeout=10)
                        if response.status_code == 200:
                            hl_data = response.json()
                            if isinstance(hl_data, list) and hl_data:
                                data_dict[interval] = [{"t": int(c.get('t', 0)), "o": float(c.get('o', 0)), "h": float(c.get('h', 0)), "l": float(c.get('l', 0)), "c": float(c.get('c', 0)), "v": float(c.get('v', 0))} for c in hl_data[-limit:]]
                                data_source = f"HL (attempt {idx+1})"
                                break
                    except Exception as e:
                        print(f"HL attempt {idx+1} для {symbol} {interval}: {e}")
                
                if interval not in data_dict:
                    # Fallback если fail
                    pass
            # Binance (allase if not HL or as fallback)
            if interval not in data_dict:
                bin_url = "https://api.binance.com/api/v3/klines"
                params = {"symbol": binance_symbol, "interval": interval, "limit": limit}
                response = requests.get(bin_url, params=params, timeout=10)
                if response.status_code == 200:
                    bin_data = response.json()
                    data_dict[interval] = [{"t": int(k[0]) / 1000, "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in bin_data] if bin_data else []
                else:
                    data_dict[interval] = []
            
            print(f"Источник для {symbol} {interval}: {data_source}")
        
        data_dict_outer[symbol] = data_dict  # {symbol: {'1d': [...], '1h': [...], '1m': [...]}}
    
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
                        f"\n  {interval}: {trend} O:{last['o']:.4f} H:{last['h']:.4f} L:{last['l']:.4f} C:{last['c']:.4f} | "
                        f"MaxH:{high_max:.4f} MinL:{low_min:.4f} Vol:{avg_volume:.2f} ({len(candles)} свеч)"
                    )
                else:
                    summary += f"\n  {interval}: Нет данных"
        compressed.append(summary)
    return "\n\n".join(compressed)

def analyze_with_deepseek(data_dict_outer):
    """Анализирует данные всех символов одним запросом"""
    if not data_dict_outer or not any(any(tf_data for tf, tf_data in sym_data.items()) for sym_data in data_dict_outer.values()):
        return 'hold', 'Нет данных для анализа'
    
    compressed_data = compress_market_data(data_dict_outer)
    
    prompt = f"""Проанализируй крипторынки и дай торговый сигнал. Данные:

{compressed_data}

### Анализ:
1. Оцени общий тренд по каждому символу на трех таймфреймах (1d, 1h, 1m)
2. Глубоко проанализируй тренды, учитывая объёмы, сезонность, 10EMA, 20EMA, 50EMA, 100EMA, 200EMA, повторяющиеся закономерности и паттерны.
3. Определи самый сильный сигнал среди всех символов
4. Рассмотри объёмы, волатильность и динамику цен

### Правила:
- Выбери только ОДИН символ с наиболее четким сигналом
- Если сигналы противоречивые или слабые - выбирай 'hold'
- Строго следуй формату ответа

### Формат ответа:
Action: buy_ETHUSDT | sell_BTCUSDT | hold
Reason: [Очень краткое обоснование на русском]"""

    try:
        completion = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3,
            stop=["\n\n"]
        )
        result = completion.choices[0].message.content.strip()
        
        # Парсинг результата
        action_line, reason_line = None, None
        for line in result.split('\n'):
            if line.startswith('Action:'):
                action_line = line.split('Action:')[1].strip()
            elif line.startswith('Reason:'):
                reason_line = line.split('Reason:')[1].strip()
        
        if not action_line or not reason_line:
            return 'hold', f'Неверный формат ответа: {result}'
        
        if action_line.startswith('buy_') or action_line.startswith('sell_'):
            symbol = action_line.split('_')[1].upper()
            if symbol in data_dict_outer:
                return action_line, reason_line
        
        return 'hold', reason_line
        
    except Exception as e:
        print(f"Ошибка AI: {e}")
        return 'hold', f'Ошибка анализа: {str(e)[:50]}'