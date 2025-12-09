# test_perplexity.py
from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai"
)

try:
    response = client.chat.completions.create(
        model="sonar-deep-research",
        messages=[{"role": "user", "content": "Привет! Это тест."}],
        max_tokens=50
    )
    print("✅ Подключение к Perplexity AI успешно!")
    print("Ответ:", response.choices[0].message.content)
except Exception as e:
    print("❌ Ошибка подключения:", e)
