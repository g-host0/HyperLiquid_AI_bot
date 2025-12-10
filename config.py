import os
from dotenv import load_dotenv

load_dotenv()

HYPERLIQUID_API_KEY = os.getenv("HYPERLIQUID_API_KEY")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY")
HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Настройки бота
SYMBOLS = ["ETHUSDT", "BTCUSDT", "BNBUSDT", "SOLUSDT", "MONUSDT"]
MAX_SYMBOLS = 5
POSITION_SIZE_PERCENT = 100.0 # Размер открытия позиции в % от депозита
MAX_TOTAL_POSITION_PERCENT = 400.0 # Максимальная суммарная позиция в % от депозита по одному символу
LIMIT_1D = 360 # год дневных данных
LIMIT_1H = 168 # 1 неделя часовых данных (24*7)
LIMIT_1M = 1440 # 1 день минутных данных (24*60)
INTERVAL = 60 # Секунд между прогонками
TEST_MODE = False # Симуляция
TEST_BALANCE = 1000.0
USE_HYPERLIQUID = True # Использовать HyperLiquid как источник данных

# Настройки риска
TAKE_PROFIT_1_PERCENT = 1.0 # TP1 тейк, после него ставится SL в б/у
TAKE_PROFIT_1_SIZE_PERCENT = 30.0 # Размер позиции для TP1
TAKE_PROFIT_2_PERCENT = 3.0 # TP2 и последующие
TAKE_PROFIT_2_SIZE_PERCENT = 20.0 # Размер позиции для TP2
ATR_MULTIPLIER = 1.5 # Мультипликатор ATR 1h свечей для начального SL

# AI настройки
USE_PERPLEXITY = False # Использовать Perplexity AI
USE_OPENROUTER = True # Использовать OpenRouter (DeepSeek)
PERPLEXITY_MODEL = "sonar"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
OPENROUTER_MODEL = "deepseek/deepseek-chat"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Стратегия объединения сигналов при использовании обоих AI
# "unanimous" - оба AI должны дать одинаковый сигнал
# "priority_perplexity" - приоритет Perplexity, OpenRouter для подтверждения
# "priority_openrouter" - приоритет OpenRouter, Perplexity для подтверждения
# "any" - любой сигнал от любого AI
SIGNAL_STRATEGY = "any"

# Промпт для AI (универсальный для всех сетей)
AI_PROMPT_TEMPLATE = """Ты профессиональный криптотрейдер. Проанализируй крипторынки и дай торговый сигнал. Данные:

{market_data}

### Анализ:
1. ПЕРВИЧНЫЙ ОСМОТР: Оцени по каждому символу на трех таймфреймах (1d, 1h, 1m) цены и объёмы. Ищи аномальные всплески объема.
2. ТЕХНИЧЕСКИЙ АНАЛИЗ: Используй предоставленные данные EMA(10,20,50,100,200), MACD и RSI на таймфреймах 1d, 1h. Определи, где цена находится относительно ключевых уровней поддержки, сопротивления.  
3. ПАТТЕРНЫ: Найди повторяющиеся закономерности и паттерны, реакции цены на поддержку и сопротивление, подтверждённую объёмами. Определи наиболее вероятные и сильные тренды по всем символам.
4. РЕШЕНИЕ: Выбери ОДИН актив с самым сильным и очевидным трендом и дай сигнал.

### Правила:
- Выбери только ОДИН символ с наиболее четким сигналом
- Если сигналы противоречивые или слабые - выбирай 'hold'
- Не выдумывай значения индикаторов, если их нет в данных
- СТРОГО следуй формату ответа

### Формат ответа:
Action: buy_ETHUSDT | sell_BTCUSDT | hold
Reason: [Очень краткое обоснование на русском, не более 20 слов, фокус на ключевом факторе]"""

# Hyperliquid настройки
USE_TESTNET = True # True = testnet, False = mainnet
HYPERLIQUID_MAINNET_API = "https://api.hyperliquid.xyz"
HYPERLIQUID_TESTNET_API = "https://api.hyperliquid-testnet.xyz"
HYPERLIQUID_API_URL = HYPERLIQUID_TESTNET_API if USE_TESTNET else HYPERLIQUID_MAINNET_API
