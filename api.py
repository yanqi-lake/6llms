# api.py
import openai
import time
from config import API_KEY, BASE_URL, API_TIMEOUT, MODELS, TEMPERATURE, MAX_TOKENS, TOP_P, FREQUENCY_PENALTY, PRESENCE_PENALTY

# API 重试配置（单次等待）
MAX_API_RETRIES = 1  # 只等待一次
RETRY_DELAY = [120]  # 等待120秒

def call_api(messages, model=None, max_retries=MAX_API_RETRIES):
    """
    调用大模型 API，支持重试机制。
    """
    if model is None:
        model = MODELS[0]

    for attempt in range(max_retries):
        try:
            client = openai.OpenAI(
                api_key=API_KEY,
                base_url=BASE_URL,
                timeout=API_TIMEOUT
            )
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                top_p=TOP_P,
                frequency_penalty=FREQUENCY_PENALTY,
                presence_penalty=PRESENCE_PENALTY
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API 错误（尝试 {attempt+1}/{max_retries}）: {str(e)[:50]}")
            if attempt < max_retries - 1:
                sleep_time = RETRY_DELAY[attempt] if attempt < len(RETRY_DELAY) else 60
                print(f"  等待{sleep_time}秒后重试...")
                time.sleep(sleep_time)
            else:
                print(f"  已达到最大重试次数")
                return ""
    
    return ""