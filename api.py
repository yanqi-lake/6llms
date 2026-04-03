# api.py
import openai
import time
import random
from config import API_KEY, BASE_URL, TIMEOUT, MAX_RETRIES, MODELS, TEMPERATURE, MAX_TOKENS, TOP_P, FREQUENCY_PENALTY, PRESENCE_PENALTY

# 初始化 OpenAI 客户端（兼容硅基流动）
client = openai.OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=TIMEOUT
)

def call_api(messages, model=None, max_retries=MAX_RETRIES):
    """
    调用大模型 API，支持重试机制。
    messages: 消息列表，格式如 [{"role": "user", "content": "..."}]
    model: 指定模型，若为 None 则使用 config.MODELS 的第一个模型（主持人模型）
    max_retries: 最大重试次数
    """
    if model is None:
        model = MODELS[0]  # 默认使用主持人模型

    last_error = None
    for attempt in range(max_retries):
        try:
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
        except openai.APIError as e:
            last_error = e
            print(f"API 错误（尝试 {attempt+1}/{max_retries}）: {e}")
            if attempt < max_retries - 1:
                # 指数退避 + 随机抖动
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"  等待 {sleep_time:.2f} 秒后重试...")
                time.sleep(sleep_time)
        except Exception as e:
            last_error = e
            print(f"API 调用失败（尝试 {attempt+1}/{max_retries}）: {e}")
            if attempt == max_retries - 1:
                raise e  # 最后一次失败则抛出异常
            time.sleep(2)  # 等待后重试
    
    # 所有重试都失败
    raise last_error