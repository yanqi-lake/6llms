# main.py
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
    PROMPT_SELECT_CODE
)

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
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] 步骤：{step}\n")
        f.write(f"{content}\n")
        f.flush()

def read_question_from_file(filepath="question.txt"):
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
    """步骤1：所有成员分别给出解题思路"""
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
    """步骤2：成员投票选出最佳思路，返回最佳编号(1-based)"""
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
                numbers = re.findall(r'\d+', response)
                if numbers:
                    selected = int(numbers[0])
                    # 确保编号在有效范围内
                    if 1 <= selected <= MEMBER_COUNT:
                        selections[idx] = selected
                    else:
                        selections[idx] = 1
                        print(f"成员 {idx+1} 选择了无效编号 {selected}，已默认选择方案1")
                else:
                    selections[idx] = 1
                    print(f"成员 {idx+1} 投票响应无法解析，已默认选择方案1")
            except Exception as e:
                print(f"成员 {idx+1} 投票时出错: {e}")
                selections[idx] = 1

    counter = Counter(selections)
    # 平局时选择编号较小的（也可改为随机）
    best_idx = max(range(1, MEMBER_COUNT+1), key=lambda x: counter[x])
    return best_idx

def generate_codes(question, solution):
    """步骤3：成员根据最终方案编写代码，同时提供原始问题"""
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
                print(f"❌ 成员 {idx+1}（模型：{model_name}）写代码失败: {e}")
                codes[idx] = ""
    return codes

def select_best_code(codes):
    """步骤4：成员投票选出最佳代码，返回最佳编号(1-based)"""
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
                numbers = re.findall(r'\d+', response)
                if numbers:
                    selected = int(numbers[0])
                    if 1 <= selected <= MEMBER_COUNT:
                        selections[idx] = selected
                    else:
                        selections[idx] = 1
                        print(f"成员 {idx+1} 选择了无效编号 {selected}，已默认选择代码1")
                else:
                    selections[idx] = 1
                    print(f"成员 {idx+1} 投票响应无法解析，已默认选择代码1")
            except Exception as e:
                print(f"成员 {idx+1} 投票时出错: {e}")
                selections[idx] = 1

    counter = Counter(selections)
    best_idx = max(range(1, MEMBER_COUNT+1), key=lambda x: counter[x])
    return best_idx

def main():
    print("=" * 50)
    print(f"多智能体协作编程系统启动（成员数量：{MEMBER_COUNT}）")
    print("=" * 50)

    question = read_question_from_file("question.txt")
    if question is None:
        question = input("请输入编程问题（或创建 question.txt 文件以自动读取）：").strip()
        if not question:
            print("问题不能为空，程序退出。")
            return

    log_message("初始问题", f"问题内容：\n{question}")
    print(f"\n问题：{question}")

    print("\n[步骤1] 成员生成解题思路...")
    ideas = get_ideas(question)
    ideas_log = "\n".join([f"成员 {i+1} 思路：\n{ideas[i]}" for i in range(MEMBER_COUNT)])
    log_message("成员解题思路", ideas_log)
    for i, idea in enumerate(ideas):
        print(f"  成员 {i+1} 思路预览：{idea[:100]}..." if len(idea) > 100 else f"  成员 {i+1} 思路：{idea}")

    print("\n[步骤2] 成员投票选择最佳思路...")
    best_idea_idx = select_best_idea(ideas)
    best_idea = ideas[best_idea_idx - 1]
    log_message("思路投票结果", f"最佳思路编号：{best_idea_idx}\n内容：{best_idea}")
    print(f"  最佳思路是方案 {best_idea_idx}：{best_idea[:100]}..." if len(best_idea) > 100 else f"  最佳思路是方案 {best_idea_idx}：{best_idea}")

    print("\n[步骤3] 成员根据最佳思路编写代码...")
    codes = generate_codes(question, best_idea)
    codes_log = "\n".join([f"成员 {i+1} 代码：\n{codes[i]}" for i in range(MEMBER_COUNT)])
    log_message("成员生成的代码", codes_log)
    for i, code in enumerate(codes):
        preview = code[:100].replace('\n', ' ') + "..." if len(code) > 100 else code
        print(f"  成员 {i+1} 代码预览：{preview}")

    print("\n[步骤4] 成员投票选择最佳代码...")
    best_code_idx = select_best_code(codes)
    best_code = codes[best_code_idx - 1]
    log_message("代码投票结果", f"最佳代码编号：{best_code_idx}\n内容：{best_code}")
    print(f"  最佳代码是方案 {best_code_idx}")

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