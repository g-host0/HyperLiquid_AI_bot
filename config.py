import os
from dotenv import load_dotenv

load_dotenv()

HYPERLIQUID_API_KEY = os.getenv("HYPERLIQUID_API_KEY")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY")
HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if HYPERLIQUID_ACCOUNT_ADDRESS:
    print(f"✅ Config: адрес загружен {HYPERLIQUID_ACCOUNT_ADDRESS[:10]}...")
else:
    print(f"⚠️ Config: адрес НЕ загружен из .env")

# Настройки бота
SYMBOLS = ["ETHUSDT", "BTCUSDT", "BNBUSDT", "SOLUSDT"]
MAX_SYMBOLS = 5
POSITION_SIZE_PERCENT = 100.0
MAX_TOTAL_POSITION_PERCENT = 400.0
LIMIT_1D = 360
LIMIT_1H = 168
LIMIT_1M = 1440
INTERVAL = 60
TEST_MODE = False
TEST_BALANCE = 1000.0
USE_HYPERLIQUID = True

# Настройки риска
TAKE_PROFIT_1_PERCENT = 1.0  # TP1: 1% прибыли
TAKE_PROFIT_1_SIZE_PERCENT = 30.0  # TP1: 30% позиции
TAKE_PROFIT_2_PERCENT = 2.5  # TP2: 2.5% прибыли
TAKE_PROFIT_2_SIZE_PERCENT = 30.0  # TP2: 30% оставшейся позиции
ATR_MULTIPLIER = 1.5

# AI настройки
USE_PERPLEXITY = False
USE_OPENROUTER = True
PERPLEXITY_MODEL = "sonar"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
OPENROUTER_MODEL = "deepseek/deepseek-chat"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SIGNAL_STRATEGY = "any"

# Промпт для AI (универсальный для всех сетей)
AI_PROMPT_TEMPLATE = """Ты профессиональный криптотрейдер. Проанализируй крипторынки и дай торговый сигнал. Данные:

{market_data}

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
Reason: [Очень краткое обоснование на русском, не более 20 слов]"""

# Hyperliquid настройки
USE_TESTNET = True
HYPERLIQUID_MAINNET_API = "https://api.hyperliquid.xyz"
HYPERLIQUID_TESTNET_API = "https://api.hyperliquid-testnet.xyz"
HYPERLIQUID_API_URL = HYPERLIQUID_TESTNET_API if USE_TESTNET else HYPERLIQUID_MAINNET_API
