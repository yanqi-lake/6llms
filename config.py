# config.py
import os

# ------------------- 必需配置 -------------------
# 从环境变量读取 API 密钥，如果未设置则使用默认值（请替换为你的密钥）
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-frbpfmrjdbcipawssjhvqmbhoswtleulmprysrhjzdlavgdd")

# 硅基流动 API 基础地址
BASE_URL = "https://api.siliconflow.cn/v1"

# ------------------- 模型列表 -------------------
# 索引顺序：0=主持人，1~5=五位成员
# 你可以根据需求替换为硅基流动支持的其他模型
MODELS = [
    "Qwen/Qwen2.5-Coder-7B-Instruct",      # 主持人（较强模型）
    "Qwen/Qwen2.5-Coder-7B-Instruct",       
    "Qwen/Qwen2.5-Coder-7B-Instruct",      
    "Qwen/Qwen2.5-Coder-7B-Instruct"    
]



# ------------------- 可选配置 -------------------
# 请求超时时间（秒）
TIMEOUT = 60

# API 调用失败时的最大重试次数
MAX_RETRIES = 3

# 模型生成参数（可根据需要调整）
TEMPERATURE = 0.7          # 温度，控制随机性
MAX_TOKENS = 8196          # 最大生成 token 数
TOP_P = 0.9                # 核采样参数
FREQUENCY_PENALTY = 0.0    # 频率惩罚
PRESENCE_PENALTY = 0.0     # 存在惩罚

# ------------------- 使用说明 -------------------
# 如需使用环境变量，请在终端设置：
# export SILICONFLOW_API_KEY="你的密钥"  (Linux/Mac)
# set SILICONFLOW_API_KEY=你的密钥        (Windows)
#
# 或者直接修改上面的 API_KEY 变量。