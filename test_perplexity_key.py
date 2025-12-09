from dotenv import load_dotenv
import os
import requests

load_dotenv()

api_key = os.getenv("PERPLEXITY_API_KEY")

print(f"API ключ загружен: {api_key[:10]}..." if api_key else "API ключ НЕ загружен!")
print(f"Длина ключа: {len(api_key)}" if api_key else "Ключ отсутствует")

if api_key:
    # Тестовый запрос с актуальной моделью
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Тестируем разные модели
    models_to_test = ["sonar", "sonar-pro", "sonar-reasoning"]
    
    for model in models_to_test:
        print(f"\n{'='*50}")
        print(f"Тестирую модель: {model}")
        print('='*50)
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Say 'API works!' in Russian"}],
            "max_tokens": 20,
            "temperature": 0.2
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            print(f"Код ответа: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                print(f"✅ Ответ: {content}")
                print(f"✅ Модель '{model}' работает!")
                break  # Нашли рабочую модель
            else:
                print(f"❌ Ошибка: {response.json()}")
        except Exception as e:
            print(f"❌ Исключение: {e}")
