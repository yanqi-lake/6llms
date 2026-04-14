# api.py
import openai
import time
from config import API_KEY, BASE_URL, API_TIMEOUT, MODELS, TEMPERATURE, MAX_TOKENS, TOP_P, FREQUENCY_PENALTY, PRESENCE_PENALTY

# API 重试配置
MAX_API_RETRIES = 2  # 最多重试2次
RETRY_DELAY = [1, 60]  # 重试等待时间（秒）

# 全局超时设置（秒）
DEFAULT_TIMEOUT = 120

def call_api(messages, model=None, max_retries=MAX_API_RETRIES, timeout=None):
    """
    调用大模型 API，支持重试机制。
    
    Args:
        messages: API 消息列表
        model: 模型名称
        max_retries: 最大重试次数
        timeout: 超时时间（秒），默认 DEFAULT_TIMEOUT
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    
    if model is None:
        model = MODELS[0]

    for attempt in range(max_retries):
        try:
            client = openai.OpenAI(
                api_key=API_KEY,
                base_url=BASE_URL,
                timeout=timeout
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
            error_msg = str(e)
            print(f"API 错误（尝试 {attempt+1}/{max_retries}）: {error_msg[:50]}")
            # 检查是否是超时错误
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                print(f"  API 调用超时（{timeout}秒）")
                return ""  # 超时直接返回空，不重试
            if attempt < max_retries - 1:
                sleep_time = RETRY_DELAY[attempt] if attempt < len(RETRY_DELAY) else 60
                print(f"  等待{sleep_time}秒后重试...")
                time.sleep(sleep_time)
            else:
                print(f"  已达到最大重试次数")
                return ""
    
    return ""