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
    PROMPT_HOST_REVIEW_CODE,
    PROMPT_HOST_FIX_CODE,
    PROMPT_HOST_CLEANUP_CODE
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
        tuple: (ideas列表, 失败的成员索引列表)
    """
    ideas = [None] * MEMBER_COUNT
    failed_members = []  # 记录失败的成员索引
    
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
                result = future.result()
                if result and result.strip():
                    ideas[idx] = result
                else:
                    print(f"警告：成员 {idx+1} 返回了空内容")
                    failed_members.append(idx)
            except Exception as e:
                print(f"获取成员 {idx+1} 的思路时出错: {e}")
                failed_members.append(idx)
                ideas[idx] = ""
    
    return ideas, failed_members


def select_best_idea(ideas, failed_members=None):
    """
    步骤2：成员投票选出最佳思路
    
    Args:
        list: 所有成员的解题思路列表
        failed_members: 失败的成员索引列表（这些成员的思路不参与投票）
    
    Returns:
        int: 最佳思路的编号（1-based）
    """
    if failed_members is None:
        failed_members = []
    
    # 过滤掉失败的成员的思路
    valid_ideas = []
    for i in range(MEMBER_COUNT):
        if i not in failed_members and ideas[i] and ideas[i].strip():
            valid_ideas.append(i)
    
    if not valid_ideas:
        raise ValueError("所有成员的思路都失败了，无法选择最佳思路")
    
    print(f"  有效参与思路投票的成员: {[i+1 for i in valid_ideas]}")
    
    # 只让有效成员参与投票
    selections = []
    
    def call_vote(member_idx):
        member_idea = ideas[member_idx]
        # 构建投票文本，只包含有效方案
        valid_ideas_text = "\n\n".join([f"方案{j+1}：{ideas[j]}" for j in valid_ideas])
        messages = [
            {"role": "system", "content": SYSTEM_MEMBER},
            {"role": "user", "content": PROMPT_SELECT_IDEA.format(
                count=len(valid_ideas), ideas=valid_ideas_text)}
        ]
        return call_member_api(messages, member_idx)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(valid_ideas)) as executor:
        future_to_index = {}
        for idx in valid_ideas:
            future_to_index[executor.submit(call_vote, idx)] = idx

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                response = future.result()
                # 使用相对编号（1到有效成员数）
                numbers = re.findall(r'\b([1-' + str(len(valid_ideas)) + r'])\b', response)
                if numbers:
                    # 转换为绝对索引
                    selected_relative = int(numbers[0])
                    selected_absolute = valid_ideas[selected_relative - 1]
                    selections.append(selected_absolute)
                    print(f"  成员 {idx+1} 投票选择了方案 {selected_absolute + 1}")
                else:
                    # 默认选第一个有效方案
                    selections.append(valid_ideas[0])
                    print(f"  成员 {idx+1} 投票响应无法解析，默认选择方案 {valid_ideas[0] + 1}")
            except Exception as e:
                print(f"  成员 {idx+1} 投票时出错: {e}")
                # 出错时默认选第一个有效方案
                if valid_ideas:
                    selections.append(valid_ideas[0])
    
    if not selections:
        raise ValueError("没有成员成功完成投票")
    
    counter = Counter(selections)
    # 平局时选择编号较小的
    best_idx = max(range(len(valid_ideas)), key=lambda x: counter[valid_ideas[x]]) + 1
    return valid_ideas[best_idx - 1] + 1  # 转换为1-based


def generate_codes(question, solution):
    """
    步骤3：成员根据最终方案编写代码
    
    Args:
        question: 原始编程问题描述
        solution: 选定的解题思路
    
    Returns:
        tuple: (codes列表, 失败的成员索引列表)
    """
    codes = [None] * MEMBER_COUNT
    failed_members = []
    
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
                result = future.result()
                if result and result.strip():
                    codes[idx] = result
                else:
                    model_name = MODELS[idx + 1]
                    print(f"警告：成员 {idx+1}（模型：{model_name}）返回了空内容")
                    failed_members.append(idx)
            except Exception as e:
                model_name = MODELS[idx + 1]
                print(f"❌ 成员 {idx+1}（模型：{model_name}）写代码失败: {e}")
                failed_members.append(idx)
                codes[idx] = ""
    
    return codes, failed_members


def select_best_code(codes, failed_members=None):
    """
    步骤4：成员投票选出最佳代码
    
    Args:
        list: 所有成员生成的代码列表
        failed_members: 失败的成员索引列表（这些成员的代码不参与投票）
    
    Returns:
        int: 最佳代码的编号（1-based）
    """
    if failed_members is None:
        failed_members = []
    
    # 过滤掉失败的成员的代码
    valid_codes = []
    for i in range(MEMBER_COUNT):
        if i not in failed_members and codes[i] and codes[i].strip():
            valid_codes.append(i)
    
    if not valid_codes:
        raise ValueError("所有成员的代码都失败了，无法选择最佳代码")
    
    print(f"  有效参与代码投票的成员: {[i+1 for i in valid_codes]}")
    
    # 只让有效成员参与投票
    selections = []
    
    def call_vote(member_idx):
        member_code = codes[member_idx]
        # 构建投票文本，只包含有效代码
        valid_codes_text = "\n\n".join([f"代码{j+1}：\n{codes[j]}" for j in valid_codes])
        messages = [
            {"role": "system", "content": SYSTEM_MEMBER},
            {"role": "user", "content": PROMPT_SELECT_CODE.format(
                count=len(valid_codes), codes=valid_codes_text)}
        ]
        return call_member_api(messages, member_idx)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(valid_codes)) as executor:
        future_to_index = {}
        for idx in valid_codes:
            future_to_index[executor.submit(call_vote, idx)] = idx

        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                response = future.result()
                # 使用相对编号（1到有效成员数）
                numbers = re.findall(r'\b([1-' + str(len(valid_codes)) + r'])\b', response)
                if numbers:
                    # 转换为绝对索引
                    selected_relative = int(numbers[0])
                    selected_absolute = valid_codes[selected_relative - 1]
                    selections.append(selected_absolute)
                    print(f"  成员 {idx+1} 投票选择了代码 {selected_absolute + 1}")
                else:
                    # 默认选第一个有效代码
                    selections.append(valid_codes[0])
                    print(f"  成员 {idx+1} 投票响应无法解析，默认选择代码 {valid_codes[0] + 1}")
            except Exception as e:
                print(f"  成员 {idx+1} 投票时出错: {e}")
                if valid_codes:
                    selections.append(valid_codes[0])
    
    if not selections:
        raise ValueError("没有成员成功完成投票")
    
    counter = Counter(selections)
    # 平局时选择编号较小的
    best_idx = max(range(len(valid_codes)), key=lambda x: counter[valid_codes[x]]) + 1
    return valid_codes[best_idx - 1] + 1  # 转换为1-based


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
    ideas, failed_ideas = get_ideas(question)
    ideas_log = "\n".join([f"成员 {i+1} 思路：\n{ideas[i] if ideas[i] else '<空>'}" for i in range(MEMBER_COUNT)])
    log_message("成员解题思路", ideas_log)
    for i, idea in enumerate(ideas):
        if idea and idea.strip():
            preview = idea[:100] + "..." if len(idea) > 100 else idea
            print(f"  成员 {i+1} 思路预览：{preview}")
        else:
            print(f"  成员 {i+1} 思路：<空>")

    # 步骤2：投票选思路
    print("\n[步骤2] 成员投票选择最佳思路...")
    best_idea_idx = select_best_idea(ideas, failed_ideas)
    best_idea = ideas[best_idea_idx - 1]
    log_message("思路投票结果", f"最佳思路编号：{best_idea_idx}\n内容：{best_idea}")
    preview = best_idea[:100] + "..." if len(best_idea) > 100 else best_idea
    print(f"  最佳思路是方案 {best_idea_idx}：{preview}")

    # 步骤3：编写代码
    print("\n[步骤3] 成员根据最佳思路编写代码...")
    codes, failed_codes = generate_codes(question, best_idea)
    codes_log = "\n".join([f"成员 {i+1} 代码：\n{codes[i]}" for i in range(MEMBER_COUNT)])
    log_message("成员生成的代码", codes_log)
    for i, code in enumerate(codes):
        if code and code.strip():
            preview = code[:100].replace('\n', ' ') + "..." if len(code) > 100 else code
            print(f"  成员 {i+1} 代码预览：{preview}")
        else:
            print(f"  成员 {i+1} 代码：<空>")

    # 步骤4：投票选代码
    print("\n[步骤4] 成员投票选择最佳代码...")
    best_code_idx = select_best_code(codes, failed_codes)
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
    current_code = best_code
    max_attempts = 3  # 最多尝试修复3次
    
    for attempt in range(max_attempts):
        # 尝试编译当前代码
        compile_result = try_compile(current_code)
        
        if compile_result["success"]:
            print(f"  ✓ 代码编译成功（第{attempt + 1}次尝试）")
            break
        else:
            print(f"  ✗ 代码编译失败（第{attempt + 1}次尝试）: {compile_result['error'][:100]}...")
            
            if attempt < max_attempts - 1:
                # 让主持人尝试修复
                print(f"  尝试修复编译错误...")
                current_code = host_fix_code(current_code, compile_result["error"])
            else:
                print(f"  多次尝试后仍无法编译，使用原始代码")
                current_code = best_code
    
    # 最后再清理一次代码（去除注释等）
    current_code = cleanup_code(current_code)
    print(f"  主持人审查完成，代码长度: {len(current_code)} 字符")
    return current_code


def try_compile(code):
    """
    尝试编译代码，返回编译结果
    
    Returns:
        dict: {"success": bool, "error": str}
    """
    import subprocess
    import tempfile
    from pathlib import Path
    
    result = {"success": False, "error": ""}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = Path(tmpdir) / "solution.cpp"
        exe_file = Path(tmpdir) / "solution"
        
        with open(src_file, "w", encoding="utf-8") as f:
            f.write(code)
        
        compile_result = subprocess.run(
            ["g++", str(src_file), "-o", str(exe_file), "-std=c++17", "-Wall"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if compile_result.returncode == 0:
            result["success"] = True
        else:
            result["error"] = compile_result.stderr
    
    return result


def host_fix_code(code, error_msg):
    """
    让主持人修复编译错误
    
    Args:
        code: 有问题的代码
        error_msg: 编译错误信息
    
    Returns:
        str: 修复后的代码
    """
    from prompts import PROMPT_HOST_FIX_CODE
    
    prompt = PROMPT_HOST_FIX_CODE.format(code=code, error=error_msg)
    messages = [
        {"role": "system", "content": SYSTEM_MEMBER},
        {"role": "user", "content": prompt}
    ]
    
    try:
        fixed_code = call_api(messages, model=MODELS[0])
        cleaned = extract_code_from_response(fixed_code)
        if cleaned:
            return cleaned
    except Exception as e:
        print(f"  修复失败: {e}")
    
    return code  # 如果修复失败，返回原代码


def cleanup_code(code):
    """
    清理代码，移除不必要的注释和格式问题
    """
    from prompts import PROMPT_HOST_CLEANUP_CODE
    
    prompt = PROMPT_HOST_CLEANUP_CODE.format(code=code)
    messages = [
        {"role": "system", "content": SYSTEM_MEMBER},
        {"role": "user", "content": prompt}
    ]
    
    try:
        cleaned = call_api(messages, model=MODELS[0])
        result = extract_code_from_response(cleaned)
        if result:
            return result
    except:
        pass
    
    return code


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
