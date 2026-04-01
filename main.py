"""
6llms - 多智能体协作编程系统

一个基于多模型协作的代码生成系统，采用类似"编程会议"的模式：
- 多个成员模型并行生成解题思路
- 成员投票选出最佳思路
- 多模型根据最佳思路编写代码
- 成员投票选出最佳代码

Architecture:
    Main (主持流程) -> Members (并行) -> Voting (投票) -> Output
"""

import re
import os
import datetime
import concurrent.futures
from collections import Counter

from api import call_api
from config import MODELS
from prompts import (
    SYSTEM_MEMBER,
    PROMPT_GET_IDEA,
    PROMPT_SELECT_IDEA,
    PROMPT_WRITE_CODE,
    PROMPT_SELECT_CODE,
    PROMPT_HOST_REVIEW_CODE
)


def extract_code_from_response(response):
    """
    从模型响应中提取 C++ 代码
    """
    if not response:
        return ""
    
    # 移除 markdown 代码块标记
    code = re.sub(r'^```cpp\s*\n', '', response, flags=re.MULTILINE)
    code = re.sub(r'^```c\+\+\s*\n', '', code, flags=re.MULTILINE)
    code = re.sub(r'^```\s*\n', '', code, flags=re.MULTILINE)
    code = re.sub(r'\n```\s*$', '', code, flags=re.MULTILINE)
    
    # 移除可能的行号前缀
    code = re.sub(r'^\d+\s+', '', code, flags=re.MULTILINE)
    
    return code.strip()

LOG_FILE = "communication.txt"
ANSWER_FILE = "ans.txt"

# 动态获取成员数量
MEMBER_COUNT = len(MODELS) - 1
if MEMBER_COUNT < 1:
    raise ValueError("config.py 中必须至少定义一个成员模型（MODELS 长度至少为2）")

print("=" * 50)
print(f"多智能体协作编程系统启动（成员数量：{MEMBER_COUNT}）")
print("模型分配：")
print(f"  主持人：{MODELS[0]}")
for i in range(MEMBER_COUNT):
    print(f"  成员 {i+1}：{MODELS[i+1]}")
print("=" * 50)


def log_message(step, content, log_file=LOG_FILE):
    """将步骤和内容记录到日志文件"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] 步骤：{step}\n")
        f.write(f"{content}\n")
        f.flush()


def read_question_from_file(filepath="question.txt"):
    """从文件读取问题，如果文件不存在或为空则返回 None"""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            question = f.read().strip()
        if question:
            return question
        else:
            print(f"警告：{filepath} 文件为空。")
            return None
    else:
        print(f"提示：{filepath} 不存在。")
        return None


def call_member_api(messages, member_index):
    """调用指定成员（索引从0开始）的API"""
    model = MODELS[member_index + 1]  # MODELS[0]是主持人
    return call_api(messages, model=model)


def get_ideas(question):
    """
    步骤1：所有成员分别给出解题思路
    
    Args:
        question: 需要解决的编程问题描述
    
    Returns:
        list: 每个成员生成的解题思路列表
    """
    ideas = [None] * MEMBER_COUNT
    with concurrent.futures.ThreadPoolExecutor(max_workers=MEMBER_COUNT) as executor:
        future_to_index = {}
        for i in range(MEMBER_COUNT):
            messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": PROMPT_GET_IDEA.format(question=question)}
            ]
            future_to_index[executor.submit(call_member_api, messages, i)] = i

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                ideas[idx] = future.result()
            except Exception as e:
                print(f"获取成员 {idx+1} 的思路时出错: {e}")
                ideas[idx] = ""
    return ideas


def select_best_idea(ideas):
    """
    步骤2：成员投票选出最佳思路
    
    Args:
        list: 所有成员的解题思路列表
    
    Returns:
        int: 最佳思路的编号（1-based）
    """
    # 构建带编号的思路文本
    ideas_text = "\n\n".join([f"方案{i+1}：{ideas[i]}" for i in range(MEMBER_COUNT)])
    selections = [None] * MEMBER_COUNT

    with concurrent.futures.ThreadPoolExecutor(max_workers=MEMBER_COUNT) as executor:
        future_to_index = {}
        for i in range(MEMBER_COUNT):
            messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": PROMPT_SELECT_IDEA.format(
                    count=MEMBER_COUNT, ideas=ideas_text)}
            ]
            future_to_index[executor.submit(call_member_api, messages, i)] = i

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                response = future.result()
                # 改进：使用更精确的正则，只匹配 1-MEMBER_COUNT 范围内的单个数字
                numbers = re.findall(r'\b([1-' + str(MEMBER_COUNT) + r'])\b', response)
                if numbers:
                    selected = int(numbers[0])
                    selections[idx] = selected
                    print(f"  成员 {idx+1} 投票选择了方案 {selected}")
                else:
                    selections[idx] = 1
                    print(f"  成员 {idx+1} 投票响应无法解析，已默认选择方案1")
            except Exception as e:
                print(f"  成员 {idx+1} 投票时出错: {e}")
                selections[idx] = 1

    counter = Counter(selections)
    # 平局时选择编号较小的（也可改为随机）
    best_idx = max(range(1, MEMBER_COUNT+1), key=lambda x: counter[x])
    return best_idx


def generate_codes(question, solution):
    """
    步骤3：成员根据最终方案编写代码
    
    Args:
        question: 原始编程问题描述
        solution: 选定的解题思路
    
    Returns:
        list: 每个成员生成的代码列表
    """
    codes = [None] * MEMBER_COUNT
    with concurrent.futures.ThreadPoolExecutor(max_workers=MEMBER_COUNT) as executor:
        future_to_index = {}
        for i in range(MEMBER_COUNT):
            messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": PROMPT_WRITE_CODE.format(question=question, solution=solution)}
            ]
            future_to_index[executor.submit(call_member_api, messages, i)] = i

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                codes[idx] = future.result()
            except Exception as e:
                model_name = MODELS[idx + 1]
                print(f"❌ 成员 {i+1}（模型：{model_name}）写代码失败: {e}")
                codes[idx] = ""
    return codes


def select_best_code(codes):
    """
    步骤4：成员投票选出最佳代码
    
    Args:
        list: 所有成员生成的代码列表
    
    Returns:
        int: 最佳代码的编号（1-based）
    """
    codes_text = "\n\n".join([f"代码{i+1}：\n{codes[i]}" for i in range(MEMBER_COUNT)])
    selections = [None] * MEMBER_COUNT

    with concurrent.futures.ThreadPoolExecutor(max_workers=MEMBER_COUNT) as executor:
        future_to_index = {}
        for i in range(MEMBER_COUNT):
            messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": PROMPT_SELECT_CODE.format(
                    count=MEMBER_COUNT, codes=codes_text)}
            ]
            future_to_index[executor.submit(call_member_api, messages, i)] = i

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                response = future.result()
                # 改进：使用更精确的正则，只匹配 1-MEMBER_COUNT 范围内的单个数字
                numbers = re.findall(r'\b([1-' + str(MEMBER_COUNT) + r'])\b', response)
                if numbers:
                    selected = int(numbers[0])
                    selections[idx] = selected
                    print(f"  成员 {idx+1} 投票选择了代码 {selected}")
                else:
                    selections[idx] = 1
                    print(f"  成员 {idx+1} 投票响应无法解析，已默认选择代码1")
            except Exception as e:
                print(f"  成员 {idx+1} 投票时出错: {e}")
                selections[idx] = 1

    counter = Counter(selections)
    best_idx = max(range(1, MEMBER_COUNT+1), key=lambda x: counter[x])
    return best_idx


def solve_problem(question):
    """
    解决单个编程问题的主流程
    
    Args:
        question: 编程问题描述
    
    Returns:
        str: 生成的最终代码（经过主持人审查清理）
    """
    log_message("初始问题", f"问题内容：\n{question}")
    print(f"\n问题：{question}")

    # 步骤1：生成思路
    print("\n[步骤1] 成员生成解题思路...")
    ideas = get_ideas(question)
    ideas_log = "\n".join([f"成员 {i+1} 思路：\n{ideas[i]}" for i in range(MEMBER_COUNT)])
    log_message("成员解题思路", ideas_log)
    for i, idea in enumerate(ideas):
        preview = idea[:100] + "..." if len(idea) > 100 else idea
        print(f"  成员 {i+1} 思路预览：{preview}")

    # 步骤2：投票选思路
    print("\n[步骤2] 成员投票选择最佳思路...")
    best_idea_idx = select_best_idea(ideas)
    best_idea = ideas[best_idea_idx - 1]
    log_message("思路投票结果", f"最佳思路编号：{best_idea_idx}\n内容：{best_idea}")
    preview = best_idea[:100] + "..." if len(best_idea) > 100 else best_idea
    print(f"  最佳思路是方案 {best_idea_idx}：{preview}")

    # 步骤3：编写代码
    print("\n[步骤3] 成员根据最佳思路编写代码...")
    codes = generate_codes(question, best_idea)
    codes_log = "\n".join([f"成员 {i+1} 代码：\n{codes[i]}" for i in range(MEMBER_COUNT)])
    log_message("成员生成的代码", codes_log)
    for i, code in enumerate(codes):
        preview = code[:100].replace('\n', ' ') + "..." if len(code) > 100 else code
        print(f"  成员 {i+1} 代码预览：{preview}")

    # 步骤4：投票选代码
    print("\n[步骤4] 成员投票选择最佳代码...")
    best_code_idx = select_best_code(codes)
    best_code = codes[best_code_idx - 1]
    log_message("代码投票结果", f"最佳代码编号：{best_code_idx}\n内容：{best_code}")
    print(f"  最佳代码是方案 {best_code_idx}")

    # 步骤5：主持人审查和清理代码
    print("\n[步骤5] 主持人审查并清理最终代码...")
    final_code = host_review_code(best_code, best_code_idx)
    log_message("主持人最终代码", final_code)
    
    return final_code


def host_review_code(best_code, best_idx):
    """
    步骤5：主持人审查并清理最佳代码
    
    Args:
        best_code: 投票选出的最佳代码
        best_idx: 最佳代码的编号
    
    Returns:
        str: 清理后的代码
    """
    # 使用主持人模型审查代码
    prompt = PROMPT_HOST_REVIEW_CODE.format(best_idx=best_idx, best_code=best_code)
    messages = [
        {"role": "system", "content": SYSTEM_MEMBER},
        {"role": "user", "content": prompt}
    ]
    
    try:
        reviewed_code = call_api(messages, model=MODELS[0])  # 使用主持人模型
        # 提取纯代码
        clean_code = extract_code_from_response(reviewed_code)
        if clean_code:
            print(f"  主持人审查完成，代码长度: {len(clean_code)} 字符")
            return clean_code
        else:
            print(f"  主持人审查未返回有效代码，使用原代码")
            return best_code
    except Exception as e:
        print(f"  主持人审查失败: {e}，使用原代码")
        return best_code


def main():
    """主入口函数"""
    print("=" * 50)
    print(f"多智能体协作编程系统启动（成员数量：{MEMBER_COUNT}）")
    print("=" * 50)

    question = read_question_from_file("question.txt")
    if question is None:
        question = input("请输入编程问题（或创建 question.txt 文件以自动读取）：").strip()
        if not question:
            print("问题不能为空，程序退出。")
            return

    best_code = solve_problem(question)

    # 步骤5：验证并输出最终代码
    print("\n[步骤5] 验证并输出最终代码...")
    if best_code.strip():
        print("\n最终代码：")
        print("=" * 50)
        print(best_code)
        print("=" * 50)
        with open(ANSWER_FILE, "w", encoding="utf-8") as f:
            f.write(best_code)
        print(f"最终答案已保存到 {ANSWER_FILE}")
        log_message("最终答案", best_code)
    else:
        print("生成的代码为空，请检查流程或重试。")
        log_message("错误", "生成的代码为空")

    print(f"\n系统运行完毕。完整沟通记录已保存到 {LOG_FILE}")


if __name__ == "__main__":
    main()
