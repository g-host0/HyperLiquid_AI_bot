# test_env.py
from dotenv import load_dotenv
import os

print("="*60)
print("ПРОВЕРКА ЗАГРУЗКИ .env")
print("="*60)

# Загружаем .env
load_dotenv()

# Проверяем переменные
account = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
perplexity = os.getenv("PERPLEXITY_API_KEY")
openrouter = os.getenv("OPENROUTER_API_KEY")

print(f"\n📁 Текущая директория: {os.getcwd()}")
print(f"📄 .env файл существует: {os.path.exists('.env')}")

print("\n🔑 Загруженные переменные:")
print(f"   HYPERLIQUID_ACCOUNT_ADDRESS: {account if account else '❌ НЕ ЗАГРУЖЕНО'}")
print(f"   HYPERLIQUID_PRIVATE_KEY: {'✅ Загружено' if private_key else '❌ НЕ ЗАГРУЖЕНО'}")
print(f"   PERPLEXITY_API_KEY: {'✅ Загружено' if perplexity else '❌ НЕ ЗАГРУЖЕНО'}")
print(f"   OPENROUTER_API_KEY: {'✅ Загружено' if openrouter else '❌ НЕ ЗАГРУЖЕНО'}")

if not account:
    print("\n❌ ПРОБЛЕМА: Переменные не загружаются из .env")
    print("\n💡 Возможные причины:")
    print("   1. .env файл не в той же папке, что и скрипты")
    print("   2. Неправильный формат .env файла")
    print("   3. Пробелы вокруг знака '='")
    
    print("\n📝 Правильный формат .env:")
    print("   HYPERLIQUID_ACCOUNT_ADDRESS=0xВашАдрес")
    print("   HYPERLIQUID_PRIVATE_KEY=ВашКлюч")
    print("   (БЕЗ пробелов вокруг =)")
else:
    print(f"\n✅ ВСЁ РАБОТАЕТ!")
    print(f"   Адрес: {account}")
