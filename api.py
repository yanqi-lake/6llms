# api.py
import openai
import time
import threading
from config import API_KEY, BASE_URL, API_TIMEOUT, MODELS, TEMPERATURE, MAX_TOKENS, TOP_P, FREQUENCY_PENALTY, PRESENCE_PENALTY

# API 重试配置
MAX_API_RETRIES = 3  # 最多重试3次
RETRY_DELAY = [2, 30, 120]  # 重试等待时间（秒）

# 请求间隔配置（秒）
REQUEST_INTERVAL = 1.5  # 每次请求之间的间隔

# 全局超时设置（秒）
DEFAULT_TIMEOUT = 120

# 全局锁，保证请求间隔
_request_lock = threading.Lock()
_last_request_time = 0

def _wait_for_interval():
    """确保请求之间有足够的时间间隔"""
    global _last_request_time
    with _request_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        _last_request_time = time.time()

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
            # 等待请求间隔
            _wait_for_interval()
            
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
            print(f"API 错误（尝试 {attempt+1}/{max_retries}）: {error_msg[:80]}")
            
            # 检查是否是速率限制错误 (429)
            if "429" in error_msg or "rate" in error_msg.lower() or "quota" in error_msg.lower():
                if attempt < max_retries - 1:
                    # 指数退避：速率限制等待更长时间
                    sleep_time = 60 * (2 ** attempt)  # 60, 120, 240 秒
                    print(f"  检测到速率限制，等待 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
                    continue
            
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