import os

HYPERLIQUID_API_KEY = os.getenv("HYPERLIQUID_API_KEY")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY")
HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Настройки бота
SYMBOLS = ["ETHUSDT", "BTCUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]  # До 5 символов
MAX_SYMBOLS = 5  # Максимум одновременно анализируемых пар
QUANTITY = 0.01  # Размер позиции
LIMIT_1D = 360    # год дневных данных
LIMIT_1H = 168   # 1 неделя часовых данных (24*7)
LIMIT_1M = 1440  # 1 день минутных данных (24*60)
INTERVAL = 60    # Секунд между проверками
TEST_MODE = True
USE_HYPERLIQUID = False  # Использовать HyperLiquid как источник данных

# Настройки риска
TAKE_PROFIT_PERCENT = 2.0
STOP_LOSS_PERCENT = 1.0

# OpenRouter
OPENROUTER_MODEL = "deepseek/deepseek-chat-v3-0324"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"