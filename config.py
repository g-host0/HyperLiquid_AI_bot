import os
from dotenv import load_dotenv

load_dotenv()

# ==================== Hyperliquid ====================
USE_TESTNET = True

HYPERLIQUID_API_URL = (
    "https://api.hyperliquid-testnet.xyz" if USE_TESTNET
    else "https://api.hyperliquid.xyz"
)

HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS", "")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
USE_HYPERLIQUID = True

# ==================== AI API ====================
USE_PERPLEXITY = False
USE_OPENROUTER = True

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = "sonar"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "x-ai/grok-4.1-fast"  
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_ENABLE_CACHE_CONTROL = False

# Двухуровневая верификация
ENABLE_TWO_LEVEL_VERIFICATION = False
OPENROUTER_MODEL_LEVEL1 = "x-ai/grok-4.1-fast"
OPENROUTER_MODEL_LEVEL2 = "deepseek/deepseek-v3.2"

SIGNAL_STRATEGY = "any"

# ==================== Торговые параметры ====================
TEST_MODE = False
TEST_BALANCE = 1000.0

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
MAX_SYMBOLS = 5
INTERVAL = 180  # ✅ 10 минут

# Лимиты свечей
LIMIT_1D = 360
LIMIT_1H = 200
LIMIT_1M = 1440

# Управление позицией
POSITION_SIZE_PERCENT = 100.0
MAX_TOTAL_POSITION_PERCENT = 400.0
ATR_MULTIPLIER = 1.5

# Take Profit
TAKE_PROFIT_1_PERCENT = 1.0
TAKE_PROFIT_1_SIZE_PERCENT = 30.0
TAKE_PROFIT_2_PERCENT = 1.0  # ✅ Шаг 1% для TP2
TAKE_PROFIT_2_SIZE_PERCENT = 20.0

# Защита от переторговки
ENABLE_NO_ADD_AFTER_TP = True
NO_ADD_AFTER_TP_MINUTES = 30

ENABLE_NO_REOPEN_AFTER_SL = True
NO_REOPEN_AFTER_SL_MINUTES = 90

# Пороги перекупленности/перепроданности
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
STOCH_OVERBOUGHT = 80.0
STOCH_OVERSOLD = 20.0
WILLR_OVERBOUGHT = -20.0
WILLR_OVERSOLD = -80.0

# ==================== AI Промпты ====================
AI_SYSTEM_PROMPT = """Ты профессиональный криптотрейдер. Проанализируй данные и дай торговый сигнал.

### Анализ:
1. ПЕРВИЧНЫЙ ОСМОТР: Оцени цены и объёмы на таймфреймах 1d, 1h, 1m. Ищи аномальные всплески объема.
2. ТЕХНИЧЕСКИЙ АНАЛИЗ: Используй EMA(10,20,50,100,200), MACD, RSI и осцилляторы (Stochastic, StochRSI, Williams %R). Отмечай зоны перекупленности/перепроданности и возможные развороты.
3. ПАТТЕРНЫ: Найди закономерности, реакции на поддержку/сопротивление. Определи наиболее вероятные тренды.
4. РЕШЕНИЕ: Выбери ОДИН актив с самым сильным сигналом.

### Правила:
- Выбери только ОДИН символ с наиболее четким сигналом
- Если сигналы слабые - выбирай 'hold'
- Не выдумывай значения индикаторов
- СТРОГО следуй формату ответа

### Формат ответа:
Action: buy_ETHUSDT | sell_BTCUSDT | hold
Reason: [Краткое обоснование, до 20 слов на русском]"""

AI_USER_DATA_TEMPLATE = """Данные рынка:

{market_data}"""

AI_PROMPT_TEMPLATE = AI_SYSTEM_PROMPT + "\n\n" + AI_USER_DATA_TEMPLATE
