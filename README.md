# HyperLiquid Trading Bot with DeepSeek

Этот бот автоматизирует трейдинг на HyperLiquid, используя DeepSeek через OpenRouter.ai для анализа.

## Установка
1. Установите Python 3.8+.
2. Клонируйте или скачайте файлы.
3. Установите зависимости: `pip install -r requirements.txt`.
4. Создайте `.env` файл с API-ключами (см. `config.py`).
HYPERLIQUID_API_KEY=.....
HYPERLIQUID_PRIVATE_KEY=....
HYPERLIQUID_ACCOUNT_ADDRESS=....
OPENROUTER_API_KEY=.....
OPENAI_API_KEY=OPENROUTER_API_KEY
5. Получите ключи:
   - HyperLiquid: Зарегистрируйтесь на hyperliquid.xyz и сгенерируйте API-ключи.
   - OpenRouter: Зарегистрируйтесь на openrouter.ai и получите ключ.


## Запуск
- В `config.py` установите `TEST_MODE = True` для симуляции.
- Запустите: `python trading_bot.py`.
- Бот будет проверять рынок каждые 60 секунд и действовать на основе рекомендаций DeepSeek.

## Предупреждение
- Используйте на свой страх и риск. Протестируйте на малых суммах.
- Адаптируйте под вашу стратегию (более сложный промпт для DeepSeek).


Основные изменения:
1. Добавлена поддержка OpenRouter API
Функция analyze_with_openrouter() - анализ через DeepSeek

Использует модель deepseek/deepseek-chat

2. Настройки в config.py
USE_PERPLEXITY - включить/выключить Perplexity

USE_OPENROUTER - включить/выключить OpenRouter

SIGNAL_STRATEGY - стратегия объединения сигналов

3. Стратегии объединения сигналов
unanimous - оба AI должны дать одинаковый сигнал (самая безопасная)

priority_perplexity - приоритет Perplexity, OpenRouter для подтверждения

priority_openrouter - приоритет OpenRouter, Perplexity для подтверждения

any - любой сигнал от любого AI

4. Функция analyze_with_ai()
Универсальная функция анализа

Автоматически использует включенные AI

Объединяет сигналы согласно стратегии

Примеры использования:
1. Только Perplexity:

python
USE_PERPLEXITY = True
USE_OPENROUTER = False
2. Только OpenRouter:

python
USE_PERPLEXITY = False
USE_OPENROUTER = True
3. Оба с единогласием:

python
USE_PERPLEXITY = True
USE_OPENROUTER = True
SIGNAL_STRATEGY = "unanimous"  # Оба должны согласиться
4. Оба с приоритетом Perplexity:

python
USE_PERPLEXITY = True
USE_OPENROUTER = True
SIGNAL_STRATEGY = "priority_perplexity"
Теперь запустите бота:

bash
python3 trading_bot.py

