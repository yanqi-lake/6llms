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
import json
import os
import os
import datetime
import concurrent.futures
from collections import Counter

from api import call_api
from config import MODELS
from prompts import (
    PROMPT_FORMAT_QUESTION,
    SYSTEM_MEMBER,
    PROMPT_GET_IDEA,
    PROMPT_SELECT_IDEA,
    PROMPT_WRITE_CODE,
    PROMPT_SELECT_CODE,
    PROMPT_HOST_REVIEW_CODE,
    PROMPT_HOST_FIX_CODE,
    PROMPT_HOST_CLEANUP_CODE,
    PROMPT_HOST_GENERATE_TESTCASES,
    PROMPT_RETURN_TO_MEMBER,
    PROMPT_REVIEW_TESTCASES
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


# Details folder for debugging
DETAILS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'details')


def save_detail(stage_name, content, subname=''):
    """
    保存调试信息到 details 文件夹
    
    Args:
        stage_name: 阶段名称 (如 stage0, stage1 等)
        content: 要保存的内容
        subname: 子名称（可选，用于区分同一阶段的不同部分）
    """
    os.makedirs(DETAILS_DIR, exist_ok=True)
    if subname:
        filename = f"{stage_name}_{subname}.txt"
    else:
        filename = f"{stage_name}.txt"
    filepath = os.path.join(DETAILS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(str(content))
    print(f"    [DEBUG] 已保存 {filename}")


ANSWER_FILE = "ans.txt"

# 动态获取成员数量（排除主持人和问题分析员）
# MODELS[0]=主持人, MODELS[1:~]=成员, MODELS[-1]=问题分析员
MEMBER_COUNT = len(MODELS) - 2
if MEMBER_COUNT < 1:
    raise ValueError("config.py 中必须至少定义一个成员模型（MODELS 长度至少为3：主持人+成员+分析员）")

# 问题分析员模型
REVIEWER_MODEL = MODELS[-1]

print("=" * 50)
print(f"多智能体协作编程系统启动")
print(f"  成员数量：{MEMBER_COUNT}")
print(f"模型分配：")
print(f"  主持人：{MODELS[0]}")
for i in range(MEMBER_COUNT):
    print(f"  成员 {i+1}：{MODELS[i+1]}")
print(f"  问题分析员：{REVIEWER_MODEL}")
print("=" * 50)


def log_message(step, content, log_file=LOG_FILE):
    """将步骤和内容记录到日志文件"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] 步骤：{step}\n")
        f.write(f"{content}\n")
        f.flush()



def format_question(question):
    from prompts import PROMPT_FORMAT_QUESTION
    
    print("\n[步骤0] 主持人格式化题目...")
    
    prompt = PROMPT_FORMAT_QUESTION.format(original_question=question)
    messages = [
        {"role": "system", "content": SYSTEM_MEMBER},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = call_api(messages, model=MODELS[0])
        log_message("主持人格式化题目", "原始题目：\n" + question + "\n\n格式化结果：\n" + response)
        save_detail("stage0", response, "api_response")
        
        response_clean = re.sub(r'^```json\s*\n', '', response, flags=re.MULTILINE)
        response_clean = re.sub(r'^```\s*\n', '', response_clean, flags=re.MULTILINE)
        response_clean = re.sub(r'\n```\s*$', '', response_clean, flags=re.MULTILINE)
        
        try:
            # 处理不合法的转义字符
            response_clean = response_clean.replace('\\', '\\\\')
            response_clean = response_clean.replace('\$', '\\$')
            response_clean = response_clean.replace('\%', '\\%')
            response_clean = response_clean.replace('\{', '\\{')
            response_clean = response_clean.replace('\}', '\\}')
            # 移除所有无法处理的控制字符
            response_clean = re.sub(r'[\x00-\x1f]', '', response_clean)
            formatted = json.loads(response_clean)
            title = formatted.get("question_title", "")
            difficulty = formatted.get("difficulty", "")
            platform = formatted.get("platform", "")
            print("    题目标题: " + title)
            print("    难度: " + difficulty)
            print("    平台: " + platform)
            
            public_tc = formatted.get("public_test_cases", [])
            if public_tc:
                print("    提取到 " + str(len(public_tc)) + " 个测试用例")
            
            full_question = build_question_from_formatted(formatted)
            save_detail("stage0", json.dumps(formatted, ensure_ascii=False, indent=2), "parsed_json")
            save_detail("stage0", full_question, "formatted_question")
            return formatted, full_question
        except json.JSONDecodeError as e:
            print("    解析JSON失败: " + str(e))
            # 尝试使用正则表达式提取关键信息
            try:
                title_match = re.search(r'"question_title"\s*:\s*"([^"]+)"', response_clean)
                content_match = re.search(r'"question_content"\s*:\s*"([^"]+)"', response_clean)
                tc_match = re.search(r'"public_test_cases"\s*:\s*(\[.*\])', response_clean, re.DOTALL)
                
                formatted = {}
                if title_match:
                    formatted["question_title"] = title_match.group(1)
                if content_match:
                    formatted["question_content"] = content_match.group(1)
                if tc_match:
                    try:
                        formatted["public_test_cases"] = json.loads(tc_match.group(1))
                    except:
                        pass
                
                if formatted:
                    print("    提取到部分信息")
                    full_question = build_question_from_formatted(formatted)
                    return formatted, full_question
            except:
                pass
            print("    使用原始问题继续")
            return {}, question
    except Exception as e:
        print("    格式化失败: " + str(e))
        log_message("格式化题目失败", str(e))
        return {}, question


def build_question_from_formatted(formatted):
    parts = []
    
    title = formatted.get("question_title", "")
    if title:
        parts.append("题目标题: " + title + "\n")
    
    content = formatted.get("question_content", "")
    if content:
        parts.append("题目描述:\n" + content + "\n")
    
    inp_fmt = formatted.get("input_format", "")
    if inp_fmt:
        parts.append("输入格式:\n" + inp_fmt + "\n")
    
    out_fmt = formatted.get("output_format", "")
    if out_fmt:
        parts.append("输出格式:\n" + out_fmt + "\n")
    
    sample_in = formatted.get("sample_input", "")
    sample_out = formatted.get("sample_output", "")
    if sample_in and sample_out:
        parts.append("样例输入:\n" + sample_in + "\n")
        parts.append("样例输出:\n" + sample_out + "\n")
    
    constraints = formatted.get("constraints", "")
    if constraints:
        parts.append("约束条件:\n" + constraints + "\n")
    
    return "\n".join(parts)



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
    
    print("\n[步骤1] 成员生成解题思路...")
    save_detail("stage1", "开始生成解题思路", "start")
    
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
    
    # 保存思路结果
    ideas_text = "\n\n".join([f"成员 {i+1}: {ideas[i]}" if ideas[i] else f"成员 {i+1}: <空>" for i in range(len(ideas))])
    save_detail("stage1", ideas_text, "all_ideas")
    
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
    
    save_detail("stage2", f"投票结果: {selections}\n最佳思路编号: {best_idx}", "vote_result")
    
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
    
    print("\n[步骤3] 成员根据最佳思路编写代码...")
    save_detail("stage3", f"解题思路: {solution[:500]}...", "solution")
    
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
    
    # 保存代码结果
    codes_text = "\n\n".join([f"成员 {i+1} 代码:\n{codes[i]}" if codes[i] else f"成员 {i+1}: <空>" for i in range(len(codes))])
    save_detail("stage3", codes_text, "all_codes")
    
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
    
    save_detail("stage4", f"投票结果: {selections}\n最佳代码编号: {best_idx}", "vote_result")
    
    return valid_codes[best_idx - 1] + 1  # 转换为1-based


# 全局变量保存测试用例和最佳思路
current_test_cases = []
current_best_idea = ""


def solve_problem(question, test_cases=None):
    """
    解决单个编程问题的主流程
    
    Args:
        question: 编程问题描述
        test_cases: 测试用例列表 [{"input": "...", "output": "..."}]（可选）
    
    Returns:
        str: 生成的最终代码（经过主持人审查清理）
    """
    global current_test_cases, current_best_idea
    
    # 步骤0：主持人格式化题目
    formatted_question, formatted_question_str = format_question(question)
    
    # 使用格式化后的问题描述，如果没有格式化则使用原始问题
    if formatted_question_str:
        question_to_use = formatted_question_str
    else:
        question_to_use = question
    
    # 如果没有传入test_cases，尝试从格式化结果中获取
    if not test_cases and formatted_question.get("public_test_cases"):
        test_cases = formatted_question.get("public_test_cases")
    
    log_message("初始问题", "问题内容：\n" + question_to_use)
    print("\n问题：" + question_to_use[:200] + "...")
    
    # 保存测试用例供后续使用
    current_test_cases = test_cases if test_cases else []
    current_best_idea = ""

    # 步骤1：生成思路
    print("\n[步骤1] 成员生成解题思路...")
    ideas, failed_ideas = get_ideas(question_to_use)
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
    current_best_idea = best_idea  # 保存供后续使用
    log_message("思路投票结果", f"最佳思路编号：{best_idea_idx}\n内容：{best_idea}")
    preview = best_idea[:100] + "..." if len(best_idea) > 100 else best_idea
    print(f"  最佳思路是方案 {best_idea_idx}：{preview}")

    # 步骤3：编写代码
    print("\n[步骤3] 成员根据最佳思路编写代码...")
    codes, failed_codes = generate_codes(question_to_use, best_idea)
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

    # 步骤5：简化版主持人审查（使用public_test_cases）
    print("\n[步骤5] 主持人审查代码...")
    save_detail("stage5", "开始主持人审查", "start")
    final_code = host_review_code_simple(best_code, best_code_idx, question, current_test_cases, question_to_use)
    log_message("主持人最终代码", final_code)
    
    return final_code


# 全局变量保存测试用例和最佳思路
current_test_cases = []
current_best_idea = ""


# 删除测试用例审查相关代码，使用简化的单阶段审查


def host_review_code_simple(best_code, best_idx, question, test_cases, question_to_use=None):
    save_detail("stage5", f"best_code_idx: {best_idx}\ntest_cases: {test_cases}", "input")
    """
    简化版主持人审查代码
    
    只使用题目自带的 public_test_cases 进行测试
    循环测试 - 编译 - 修复，最多1轮返回给成员
    
    Args:
        best_code: 投票选出的最佳代码
        best_idx: 最佳代码编号
        question: 题目描述
        test_cases: 题目自带的测试用例
    
    Returns:
        str: 审查后的代码
    """
    from prompts import PROMPT_ANALYZE_ERROR
    
    current_code = best_code
    max_refine_rounds = 1  # 最多返回给成员修复1轮
    
    for round_num in range(max_refine_rounds + 1):
        print(f"\n  === 第{round_num + 1}轮审查 ===")
        
        # 步骤1: 编译代码
        print(f"  正在编译代码...")
        compile_success = False
        for compile_attempt in range(3):
            compile_result = try_compile(current_code)
            if compile_result["success"]:
                print(f"    ✓ 编译成功（第{compile_attempt + 1}次尝试）")
                compile_success = True
                break
            else:
                print(f"    ✗ 编译失败（第{compile_attempt + 1}次尝试）")
                current_code = host_fix_code(current_code, compile_result["error"])
        
        if not compile_success:
            print(f"    ✗ 无法编译，使用原始代码")
            current_code = best_code
            break
        
        # 步骤2: 运行测试
        if compile_success and test_cases:
            run_result = run_test_cases(current_code, test_cases)
            
            if run_result["success"]:
                print(f"    ✓ 测试通过 ({len(run_result['test_results'])}个)")
                break
            else:
                failed_count = sum(1 for tr in run_result["test_results"] if not tr["passed"])
                print(f"    ✗ 测试失败 ({failed_count}/{len(test_cases)}个用例)")
                
                # 步骤3: 问题分析
                print(f"  正在分析错误原因...")
                error_details = []
                for tr in run_result["test_results"]:
                    if not tr["passed"]:
                        error_details.append(
                            f"输入: {tr.get('input', '')[:200]}\n"
                            f"预期: {tr.get('expected', '')}\n"
                            f"实际: {tr.get('actual', '')}"
                        )
                
                error_summary = "\n\n---\n\n".join(error_details[:3])  # 最多3个
                
                analyze_prompt = PROMPT_ANALYZE_ERROR.format(
                    question=question,
                    code=current_code,
                    error_summary=error_summary
                )
                
                try:
                    analyze_response = call_api(
                        [{"role": "system", "content": SYSTEM_MEMBER},
                         {"role": "user", "content": analyze_prompt}],
                        model=MODELS[0]
                    )
                    log_message("问题分析", analyze_response)
                    print(f"    分析: {analyze_response[:150]}...")
                except:
                    pass
                
                # 如果还有轮次，让成员重新生成
                if round_num < max_refine_rounds:
                    print(f"  正在让成员重新生成代码...")
                    new_codes, _ = generate_codes(question_to_use if question_to_use else question, current_best_idea)
                    new_best_idx = select_best_code(new_codes)
                    current_code = new_codes[new_best_idx - 1]
                else:
                    print(f"  已达到最大轮数，使用当前代码")
        elif compile_success and not test_cases:
            print(f"    ⚠ 无测试用例，仅验证编译")
            break
    
    # 清理代码
    current_code = cleanup_code(current_code)
    print(f"  审查完成，代码长度: {len(current_code)} 字符")
    
    save_detail("stage5", current_code, "final_code")
    
    return current_code


def host_generate_testcases(question):
    """
    让主持人根据题目描述生成测试用例，然后让问题分析员审查
    
    分析员只删除错误的测试用例，不尝试修改
    
    Args:
        question: 题目描述
    
    Returns:
        list: [{"input": "...", "output": "..."}, ...]
    """
    from prompts import PROMPT_HOST_GENERATE_TESTCASES, PROMPT_REVIEW_TESTCASES
    
    prompt = PROMPT_HOST_GENERATE_TESTCASES.format(question=question)
    messages = [
        {"role": "system", "content": SYSTEM_MEMBER},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = call_api(messages, model=MODELS[0])
        
        # 记录主持人生成测试用例的对话
        log_message("主持人生成测试用例", f"题目描述：{question}\n\n生成的测试用例：\n{response}")
        
        test_cases = parse_testcases_from_response(response)
        if test_cases:
            print(f"    主持人生成了 {len(test_cases)} 个测试用例")
            # 记录解析后的测试用例
            log_message("解析后的测试用例", str(test_cases))
            
            # 让问题分析员审查
            print(f"    问题分析员正在审查...")
            test_cases_text = ""
            for i, tc in enumerate(test_cases):
                test_cases_text += f"测试用例{i+1}:\n输入:\n{tc.get('input', '')}\n预期输出:\n{tc.get('output', '')}\n\n"
            
            review_prompt = PROMPT_REVIEW_TESTCASES.format(
                question=question,
                test_cases=test_cases_text
            )
            review_messages = [
                {"role": "system", "content": SYSTEM_MEMBER},
                {"role": "user", "content": review_prompt}
            ]
            review_response = call_api(review_messages, model=REVIEWER_MODEL)
            
            # 记录审查结果
            log_message("测试用例审查结果", f"分析员回复：\n{review_response}")
            print(f"    审查结果: {review_response[:100]}...")
            
            # 如果审查发现问题，删除错误的测试用例
            if "正确" not in review_response and review_response.strip():
                print(f"    审查发现问题，删除错误的测试用例...")
                
                # 尝试解析分析员标记的需要删除的测试用例
                # 分析员应该返回 "删除: 测试用例X" 格式
                deleted_indices = []
                for line in review_response.split('\n'):
                    if '删除' in line or '删除' in line:
                        # 尝试提取测试用例编号
                        import re
                        nums = re.findall(r'\d+', line)
                        if nums:
                            deleted_indices.append(int(nums[0]) - 1)  # 转为0索引
                
                # 删除标记的测试用例
                if deleted_indices:
                    original_count = len(test_cases)
                    test_cases = [tc for i, tc in enumerate(test_cases) if i not in deleted_indices]
                    print(f"    分析员删除了 {original_count - len(test_cases)} 个错误测试用例，保留 {len(test_cases)} 个")
            
            return test_cases
    except Exception as e:
        print(f"    生成测试用例失败: {e}")
        log_message("生成测试用例失败", str(e))
    
    return []


def parse_testcases_from_response(response):
    """
    从模型响应中解析出测试用例
    
    Args:
        response: 模型生成的测试用例文本
    
    Returns:
        list: [{"input": "...", "output": "..."}, ...]
    """
    import re
    
    test_cases = []
    # 简单的解析：查找 "测试用例" 和 "预期输出:" 之间的内容
    blocks = re.split(r'测试用例\d+:', response)
    
    for block in blocks[1:]:  # 跳过第一块（可能是空或标题）
        input_match = re.search(r'输入:\s*\n?(.*?)(?=预期输出:|$)', block, re.DOTALL)
        output_match = re.search(r'预期输出:\s*\n?(.*?)(?:```|$)', block, re.DOTALL)
        
        if input_match and output_match:
            output = output_match.group(1).strip()
            # 清理输出中的反引号和 markdown 标记
            output = re.sub(r'```', '', output).strip()
            
            test_cases.append({
                "input": input_match.group(1).strip(),
                "output": output
            })
    
    return test_cases


def run_test_cases(code, test_cases, timeout=30):
    """
    运行测试用例 - 每个测试用例单独编译和运行
    
    Args:
        code: C++ 源代码
        test_cases: 测试用例列表 [{"input": "...", "output": "..."}]
        timeout: 超时时间
    
    Returns:
        dict: {
            "success": bool,
            "test_results": [{"input": "...", "expected": "...", "actual": "...", "passed": bool}, ...]
        }
    """
    import subprocess
    import tempfile
    from pathlib import Path
    
    result = {"success": False, "test_results": []}
    
    if not test_cases:
        result["success"] = True
        return result
    
    # 每个测试用例单独编译和运行，避免状态污染
    for idx, tc in enumerate(test_cases):
        print(f"\n[TEST DEBUG] ===== 处理测试用例 {idx + 1}/{len(test_cases)} =====")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "solution.cpp"
            exe_file = Path(tmpdir) / "solution"
            
            # 写入代码
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            # 编译
            compile_result = subprocess.run(
                ["g++", str(src_file), "-o", str(exe_file), "-std=c++17"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            print(f"[TEST DEBUG] 编译 returncode: {compile_result.returncode}")
            if compile_result.returncode != 0:
                print(f"[TEST DEBUG] 编译错误: {compile_result.stderr}")
                result["test_results"].append({
                    "input": tc.get("input", ""),
                    "expected": tc.get("output", ""),
                    "actual": "COMPILE_ERROR: " + compile_result.stderr,
                    "passed": False
                })
                continue
            
            # 运行测试用例
            try:
                # 修复输入中的 \\n -> \n (JSON解析导致的问题)
                raw_input = tc.get("input", "")
                input_str = raw_input.replace('\\n', '\n') + '\n'
                
                print(f"[TEST DEBUG] ===== 测试用例开始 =====")
                print(f"[TEST DEBUG] input_str: {repr(input_str)}")
                print(f"[TEST DEBUG] expected output: {repr(tc.get('output', ''))}")
                
                run_result = subprocess.run(
                    [str(exe_file)],
                    input=input_str,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                actual_output = run_result.stdout.strip()
                expected_output = tc.get("output", "").strip()
                
                print(f"[TEST DEBUG] actual output: {repr(actual_output)}")
                print(f"[TEST DEBUG] ===== 测试用例结束 =====")
                
                # 比较结果
                actual_normalized = actual_output.rstrip('\n')
                expected_normalized = expected_output.rstrip('\n')
                
                actual_lines = [line.strip() for line in actual_output.split('\n') if line.strip()]
                expected_lines = [line.strip() for line in expected_output.split('\n') if line.strip()]
                
                test_passed = actual_normalized == expected_normalized or actual_lines == expected_lines
                print(f"[TEST DEBUG] passed: {test_passed}")
                
                result["test_results"].append({
                    "input": tc.get("input", ""),
                    "expected": expected_output,
                    "actual": actual_output,
                    "passed": test_passed
                })
            except subprocess.TimeoutExpired:
                result["test_results"].append({
                    "input": tc.get("input", ""),
                    "expected": tc.get("output", ""),
                    "actual": "TIMEOUT",
                    "passed": False
                })
            except Exception as e:
                result["test_results"].append({
                    "input": tc.get("input", ""),
                    "expected": tc.get("output", ""),
                    "actual": str(e),
                    "passed": False
                })
    
    result["success"] = all(tr["passed"] for tr in result["test_results"])
    return result


def return_to_members_and_refine(code, question, test_cases, generated_tc, 
                                  run_result, generated_run_result, max_rounds):
    """
    返回给成员修复代码，并在修复后重新进行一轮投票选出最佳代码
    
    流程：
    1. 将错误信息发送回各个成员
    2. 各个成员重新生成代码
    3. 重新投票选出最佳代码
    4. 重复审查流程（第二轮）
    
    Args:
        code: 当前代码
        question: 题目描述
        test_cases: 现有测试用例
        generated_tc: 主持人生成的测试用例
        run_result: 现有测试用例的运行结果
        generated_run_result: 生成测试用例的运行结果
        max_rounds: 最大轮数（第一轮和第二轮）
    
    Returns:
        str: 修复后的代码
    """
    from prompts import PROMPT_RETURN_TO_MEMBER
    
    current_code = code
    
    for round_num in range(1, max_rounds + 1):
        print(f"\n    === 第{round_num}轮审查 ===")
        
        # 收集所有失败的测试用例信息
        failed_info = []
        
        # 现有测试用例的失败信息
        for tr in run_result["test_results"]:
            if not tr["passed"]:
                failed_info.append(f"测试用例: 输入={tr['input'][:50]}... 预期输出={tr['expected']} 实际输出={tr['actual']}")
        
        # 生成测试用例的失败信息
        for tr in generated_run_result["test_results"]:
            if not tr["passed"]:
                failed_info.append(f"生成测试: 输入={tr['input'][:50]}... 预期输出={tr['expected']} 实际输出={tr['actual']}")
        
        # 构建测试用例文本
        test_cases_text = ""
        for i, tc in enumerate(test_cases + generated_tc):
            test_cases_text += f"测试用例{i+1}:\n输入:\n{tc.get('input', '')}\n预期输出:\n{tc.get('output', '')}\n\n"
        
        # 构建预期输出和实际输出
        expected_text = "\n".join([tr['expected'] for tr in run_result['test_results'] + generated_run_result['test_results'] if not tr['passed']])
        actual_text = "\n".join([tr['actual'] for tr in run_result['test_results'] + generated_run_result['test_results'] if not tr['passed']])
        
        # 调用成员修复
        prompt = PROMPT_RETURN_TO_MEMBER.format(
            question=question,
            code=current_code,
            test_cases=test_cases_text,
            expected_output=expected_text,
            actual_output=actual_text
        )
        
        log_message(f"第{round_num}轮-返回给成员修复", 
                   f"题目：{question}\n\n当前代码：\n{current_code}\n\n测试用例：\n{test_cases_text}\n\n预期输出：\n{expected_text}\n\n实际输出：\n{actual_text}")
        
        messages = [
            {"role": "system", "content": SYSTEM_MEMBER},
            {"role": "user", "content": prompt}
        ]
        
        # 重新让所有成员生成代码（使用之前保存的最佳思路）
        print(f"    正在让所有成员重新生成代码...")
        new_codes, failed_members = generate_codes(question_to_use if question_to_use else question, current_best_idea if current_best_idea else "")
        
        # 投票选出新最佳代码
        print(f"    正在投票选出新最佳代码...")
        best_new_code_idx = select_best_code(new_codes, failed_members)
        current_code = new_codes[best_new_code_idx - 1]
        
        log_message(f"第{round_num}轮-新最佳代码", f"代码：\n{current_code}")
        print(f"    新最佳代码: 方案 {best_new_code_idx}")
        
        # 编译检查
        if not try_compile(current_code)["success"]:
            print(f"    第{round_num}轮: 编译失败")
            if round_num == max_rounds:
                print(f"    已达到最大轮数，直接输出当前代码")
                return current_code
            # 继续下一轮
            run_result = {"success": False, "test_results": []}
            generated_run_result = {"success": False, "test_results": []}
            continue
        
        # 运行测试
        run_result = run_test_cases(current_code, test_cases)
        generated_run_result = run_test_cases(current_code, generated_tc)
        
        all_passed = run_result["success"] and generated_run_result["success"]
        
        if all_passed:
            print(f"    ✓ 第{round_num}轮: 所有测试通过!")
            return current_code
        else:
            failed_count = sum(1 for tr in run_result['test_results'] + generated_run_result['test_results'] if not tr['passed'])
            print(f"    ✗ 第{round_num}轮: 仍有 {failed_count} 个测试失败")
            
            if round_num == max_rounds:
                print(f"    已达到最大轮数，跳过第二阶段，直接输出当前代码")
                return current_code
    
    return current_code


def host_review_code(best_code, best_idx):
    """
    步骤5：主持人审查并清理最佳代码（保留兼容性）
    
    Args:
        best_code: 投票选出的最佳代码
        best_idx: 最佳代码的编号
    
    Returns:
        str: 清理后的代码
    """
    # 兼容旧接口，直接调用新的两阶段审查
    return host_two_stage_review(best_code, best_idx, "", [])


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
        
        # 记录主持人修复编译错误的对话
        log_message("主持人修复编译错误", f"错误信息：{error_msg}\n\n修复后的代码：\n{fixed_code}")
        
        cleaned = extract_code_from_response(fixed_code)
        if cleaned:
            return cleaned
    except Exception as e:
        print(f"  修复失败: {e}")
        log_message("修复编译错误失败", str(e))
    
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
        
        # 记录主持人清理代码的对话
        log_message("主持人清理代码", f"原始代码：\n{code}\n\n清理后的代码：\n{cleaned}")
        
        result = extract_code_from_response(cleaned)
        if result:
            return result
    except Exception as e:
        log_message("清理代码失败", str(e))
    
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
    save_detail("stage5", best_code, "final_result")
    
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
