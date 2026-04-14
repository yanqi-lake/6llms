# 🤖 6LLMs 多智能体协作编程系统

一个基于多模型协作的代码生成系统，采用类似"编程会议"的模式，通过多个AI模型协作完成编程任务。

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## 📋 功能特性

- **多模型协作**: 1个主持人 + 多个成员 + 1个问题分析员
- **步骤0 - 主持人格式化**: 将原始题目标准化为JSON格式
- **步骤1 - 思路生成**: 多成员并行生成解题思路
- **步骤2 - 思路投票**: 成员投票选出最佳思路
- **步骤3 - 代码编写**: 多成员根据最佳思路编写代码
- **步骤4 - 代码投票**: 成员投票选出最佳代码
- **步骤5 - 代码审查**: 主持人审查、编译、测试、清理代码

## 🏗️ 系统架构

```
                    ┌──────────────────┐
                    │   原始问题输入   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  步骤0: 主持人    │ ← 格式化题目
                    │  format_question │   提取测试用例
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
    │ 成员 1  │        │ 成员 2  │   ...  │  成员 N │
    │ 生成思路│        │ 生成思路│        │ 生成思路│
    └────┬────┘        └────┬────┘        └────┬────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  步骤2: 投票      │ ← 选择最佳思路
                    │ select_best_idea │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
    │ 成员 1  │        │ 成员 2  │   ...  │  成员 N │
    │ 写代码  │        │ 写代码  │        │ 写代码  │
    └────┬────┘        └────┬────┘        └────┬────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  步骤4: 投票      │ ← 选择最佳代码
                    │ select_best_code │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  步骤5: 主持人    │ ← 审查代码
                    │ host_review_code │   编译测试清理
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │    最终代码输出   │
                    └──────────────────┘
```

## 📁 项目结构

```
6llms/
├── main.py                 # 主程序入口
├── api.py                 # API 调用封装
├── config.py              # 配置文件（API密钥、模型等）
├── prompts.py             # 提示词模板
├── question.txt          # 输入问题样例
├── ans.txt                # 输出答案
├── communication.txt      # 沟通记录日志
│
├── details/               # 调试信息文件夹（可选）
│   ├── stage0_*.txt       # 步骤0的调试信息
│   ├── stage1_*.txt       # 步骤1的调试信息
│   └── ...
│
├── frontend/             # 前端界面
│   ├── index.html        # 前端页面
│   ├── app.py            # Flask API 后端
│   └── README.md         # 前端说明
│
├── test_livecodebench.py # LiveCodeBench 批量测试脚本
├── test_parallel_models.py
└── venv/                 # Python 虚拟环境
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- OpenAI Python SDK
- SiliconFlow API 密钥

### 安装

```bash
# 1. 克隆或下载项目
cd 6llms

# 2. 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install openai
```

### 配置

编辑 `config.py` 修改 API 密钥：

```python
API_KEY = "your-siliconflow-api-key"
```

### 运行

```bash
# 方式1: 命令行运行
python main.py

# 方式2: 使用前端界面
cd frontend
python app.py
# 然后访问 http://localhost:5000
```

### 测试

```bash
# 测试 100 道题
python test_livecodebench.py --limit 100

# 从第10题开始测试10道题
python test_livecodebench.py --start-index 10 --limit 10
```

## ⚙️ 配置说明

### config.py

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `API_KEY` | SiliconFlow API 密钥 | 需填写 |
| `BASE_URL` | API 基础地址 | SiliconFlow |
| `MODELS[0]` | 主持人模型 | DeepSeek-V3 |
| `MODELS[1:~]` | 成员模型 | V2.5, M2.5, Qwen3 |
| `MODELS[-1]` | 问题分析员 | Qwen2.5-72B |
| `TEMPERATURE` | 生成温度 | 0.7 |
| `MAX_TOKENS` | 最大生成token | 8196 |

## 📊 工作流程详解

### 步骤0: 主持人格式化题目

主持人模型将原始题目转换为标准JSON格式：

```json
{
  "question_title": "题目标题",
  "question_content": "完整题目描述",
  "input_format": "输入格式",
  "output_format": "输出格式",
  "sample_input": "样例输入",
  "sample_output": "样例输出",
  "constraints": "约束条件",
  "difficulty": "easy/medium/hard",
  "platform": "平台",
  "public_test_cases": [{"input": "...", "output": "..."}]
}
```

### 步骤1-4: 协作流程

1. **所有成员并行**生成解题思路
2. **成员投票**选出最佳思路
3. **所有成员并行**根据最佳思路编写代码
4. **成员投票**选出最佳代码
5. **主持人审查**代码（编译、测试、清理）

### 步骤5: 代码审查

- 编译代码（最多3次重试）
- 运行测试用例
- 分析错误原因
- 清理代码

## 🔧 调试功能

启用 `details` 文件夹保存调试信息：

```python
# 在 main.py 中已自动启用
# 会在 details/ 目录下生成各阶段的调试文件
```

## 🌐 前端界面

启动前端服务：

```bash
cd frontend
python app.py
```

访问 http://localhost:5000 查看可视化界面。

功能：
- 实时显示6个阶段的执行状态
- 进度条展示
- 最终代码展示

## 📝 提示词模板

在 `prompts.py` 中定义，包括：

- `PROMPT_GET_IDEA` - 获取解题思路
- `PROMPT_SELECT_IDEA` - 选择最佳思路
- `PROMPT_WRITE_CODE` - 编写代码
- `PROMPT_SELECT_CODE` - 选择最佳代码
- `PROMPT_FORMAT_QUESTION` - 格式化题目
- 等等...

## 📈 性能测试

使用 LiveCodeBench 数据集进行批量测试：

```bash
python test_livecodebench.py --limit 100
```

结果会保存到 `test_results.csv` 和 `test_results_details.json`。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License

## 🙏 致谢

- [SiliconFlow](https://siliconflow.cn/) - 提供 API 服务
- [LiveCodeBench](https://livecodebench.github.io/) - 测试数据集