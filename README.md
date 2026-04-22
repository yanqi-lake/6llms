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

### 步骤1: 生成解题思路

**步骤1** 是整个协作流程的核心起点，所有成员并行生成解题思路。

#### 1.1 流程概述

1. **输入**：主持人格式化后的题目（JSON格式）
2. **处理**：所有成员（`MEMBER_COUNT`个）并行调用 API 生成思路
3. **输出**：每个成员的解题思路文本

#### 1.2 详细步骤

```
题目输入 → 并行调用各成员API → 收集思路 → 保存结果
```

1. **并行调用**：使用 `ThreadPoolExecutor` 并行调用所有成员
2. **API 调用**：每个成员收到 system prompt (SYSTEM_MEMBER) + 用户问题
3. **提示词**：使用 `PROMPT_GET_IDEA` 模板，包含三步思考法：
   - 第一步：理解问题，从最简单的情形入手
   - 第二步：联想类似问题
   - 第三步：复杂实例与分解
4. **异常处理**：记录失败的成员索引，后续步骤跳过
5. **保存结果**：所有思路保存到 `details/stage1_all_ideas.txt`

#### 1.3 相关函数

- `get_ideas(question)` - 步骤1主函数
- `call_member_api(messages, member_index)` - 成员API调用

#### 1.4 代码片段

```python
def get_ideas(question):
    """步骤1：所有成员分别给出解题思路"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=MEMBER_COUNT) as executor:
        for i in range(MEMBER_COUNT):
            messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": PROMPT_GET_IDEA.format(question=question)}
            ]
            future_to_index[executor.submit(call_member_api, messages, i)] = i
```

---

### 步骤1.5: 思路展示 + 交叉提问

在步骤1生成思路后，增加成员间的交流环节。

#### 1.5A: 广播思路

- 将所有成员的思路展示给每个成员（可以看到除自己外的其他思路）

#### 1.5B: 成员并行提问

- 每个成员针对其他成员的思路提出问题
- 使用 `PROMPT_ASK_QUESTIONS` 提示词

#### 1.5C: 成员并行回答问题

- 被提问的成员回答问题
- 使用 `PROMPT_ANSWER_QUESTIONS` 提示词

---

### 步骤1.6: 成员改进思路

根据步骤1.5的问答结果，成员改进自己的思路。

- 使用 `PROMPT_IMPROVE_IDEA` 提示词
- 每个成员结合自己的思路和其他成员的问答来优化

---

### 步骤2: 投票选思路

成员投票选出最佳解题思路，使用 `PROMPT_SELECT_IDEA` 提示词。

---

### 步骤3: 成员编写代码

所有成员根据选定的最佳思路并行编写代码。

#### 3.1 流程概述

1. **输入**：题目 + 最佳思路
2. **处理**：所有成员并行调用 API 编写代码
3. **输出**：每个成员的代码

#### 3.2 详细步骤

```
题目 + 最佳思路 → 并行调用各成员API → 收集代码 → 保存结果
```

---

### 步骤3.5: 代码展示 + 交叉提问 + 回答

**新增**：在步骤3生成代码后，增加成员间的代码交流环节。

#### 3.5A: 广播代码

- 将所有成员的代码展示给每个成员（可以看到除自己外的其他代码）

#### 3.5B: 成员并行提问

- 每个成员针对其他成员的代码提出问题
- **重点**：提问必须基于题目给出的信息：
  - 输入输出形式
  - 数据范围
  - 最大输入规模
  - 约束条件
- 使用 `PROMPT_ASK_CODE_QUESTIONS` 提示词

#### 3.5C: 成员并行回答问题

- 被提问的成员回答问题
- 使用 `PROMPT_ANSWER_CODE_QUESTIONS` 提示词

---

### 步骤3.6: 成员改进代码

根据步骤3.5的问答结果，成员改进自己的代码。

- 使用 `PROMPT_IMPROVE_CODE` 提示词
- 每个成员结合自己的代码和其他成员的问答来优化

---

### 步骤4: 投票选代码

成员投票选出最佳代码，使用 `PROMPT_SELECT_CODE` 提示词。

---

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