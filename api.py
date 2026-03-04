# api.py
import openai
import time
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
        except Exception as e:
            print(f"API 调用失败（尝试 {attempt+1}/{max_retries}）: {e}")
            if attempt == max_retries - 1:
                raise e  # 最后一次失败则抛出异常
            time.sleep(2)  # 等待后重试