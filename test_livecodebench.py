"""
LiveCodeBench 批量测试脚本

用于在 LiveCodeBench 数据集上批量测试多智能体协作编程系统的效果。

用法:
    python test_livecodebench.py                    # 使用默认配置
    python test_livecodebench.py --data-dir ./data  # 指定数据目录
    python test_livecodebench.py --limit 10         # 只测试前10道题
    python test_livecodebench.py --output results.csv  # 指定输出文件
"""

import argparse
import base64
import csv
import json
import os
import pickle
import re
import sys
import subprocess
import tempfile
import zlib
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import solve_problem, MEMBER_COUNT, REVIEWER_MODEL
from config import MODELS


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="LiveCodeBench 批量测试")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="/home/lll/workspace/testbench",
        help="LiveCodeBench 数据目录"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制测试的问题数量"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_results.csv",
        help="结果输出文件"
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="起始索引（从第几个题目开始，0-based）"
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=None,
        help="结束索引（测试到第几个题目结束，0-based，不包含）"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="单个问题测试超时时间（秒）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细输出"
    )
    return parser.parse_args()


def load_livecodebench_dataset(data_dir, limit=None):
    """
    加载 LiveCodeBench 数据集
    
    Args:
        data_dir: 数据目录
        limit: 限制加载的问题数量（可选）
    
    期望目录结构:
        data_dir/
            questions/          # 问题描述 JSON 文件
            test_cases/        # 测试用例 JSON 文件
            starter_code/      # 起始代码
            solutions/        # 解决方案（可选，用于对比）
    
    或者支持单文件格式:
        data_dir/
            livecodebench.json  # 包含所有问题的 JSON 文件
            test_v5_*.jsonl     # jsonl 格式的测试集
    
    Returns:
        list: 问题列表，每个问题包含 id, title, description, test_cases 等字段
    """
    data_path = Path(data_dir)
    
    # 尝试加载 jsonl 格式（优先）
    jsonl_files = list(data_path.glob("test_v5_*.jsonl"))
    if jsonl_files:
        jsonl_file = jsonl_files[0]
        print(f"从 jsonl 文件加载: {jsonl_file}")
        questions = []
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    # 如果设置了 limit 且已达到，停止加载
                    if limit and len(questions) >= limit:
                        break
                        
                    q_data = json.loads(line)
                    
                    # 字段映射：jsonl -> 内部格式
                    # starter_code 可能是空字符串，需要转为空字典
                    starter = q_data.get("starter_code", "")
                    problem = {
                        "id": q_data.get("question_id", ""),
                        "problem_id": q_data.get("question_id", ""),
                        "title": q_data.get("question_title", ""),
                        "description": q_data.get("question_content", ""),
                        "prompt": q_data.get("question_content", ""),
                        "platform": q_data.get("platform", ""),
                        "contest_id": q_data.get("contest_id", ""),
                        "contest_date": q_data.get("contest_date", ""),
                        "starter_code": {"cpp": starter} if starter else {},
                        "difficulty": q_data.get("difficulty", ""),
                        "language": "cpp",  # 默认 C++
                    }
                    
                    # 解析 public_test_cases（JSON 字符串）
                    public_tc = q_data.get("public_test_cases", "[]")
                    if isinstance(public_tc, str):
                        try:
                            public_tc = json.loads(public_tc)
                        except:
                            public_tc = []
                    
                    # 解析 private_test_cases（base64 + zlib + pickle + JSON）
                    private_tc_raw = q_data.get("private_test_cases", "")
                    private_tc = []
                    if private_tc_raw:
                        try:
                            decoded = base64.b64decode(private_tc_raw)
                            decompressed = zlib.decompress(decoded)
                            private_tc_str = pickle.loads(decompressed)
                            private_tc = json.loads(private_tc_str)
                        except Exception as e:
                            print(f"  警告：解析 private_test_cases 失败: {e}")
                    
                    # 优先使用 private_test_cases（更完整），如果没有则用 public
                    if private_tc:
                        test_cases = [{"input": tc.get("input", ""), "output": tc.get("output", "")} for tc in private_tc]
                    else:
                        test_cases = [{"input": tc.get("input", ""), "output": tc.get("output", "")} for tc in public_tc]
                    
                    # 保存 public_test_cases（主持人审查用）和 private_test_cases（最终评测用）
                    problem["public_test_cases"] = [{"input": tc.get("input", ""), "output": tc.get("output", "")} for tc in public_tc]
                    problem["private_test_cases"] = test_cases  # 保持原有名称用于最终评测
                    problem["test_cases"] = test_cases  # 兼容旧代码
                    questions.append(problem)
        
        return questions
    
    # 尝试加载单文件格式
    single_file = data_path / "livecodebench.json"
    if single_file.exists():
        print(f"从单文件加载: {single_file}")
        with open(single_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 尝试加载目录格式
    questions_dir = data_path / "questions"
    test_cases_dir = data_path / "test_cases"
    
    if questions_dir.exists() and test_cases_dir.exists():
        print(f"从目录加载: {questions_dir}")
        questions = []
        for q_file in sorted(questions_dir.glob("*.json")):
            with open(q_file, "r", encoding="utf-8") as f:
                q_data = json.load(f)
            
            # 尝试加载对应的测试用例
            tc_file = test_cases_dir / q_file.name
            if tc_file.exists():
                with open(tc_file, "r", encoding="utf-8") as f:
                    q_data["test_cases"] = json.load(f)
            else:
                q_data["test_cases"] = []
            
            questions.append(q_data)
        return questions
    
    raise FileNotFoundError(f"无法在 {data_dir} 找到 LiveCodeBench 数据")


def extract_code_from_response(response):
    """
    从模型响应中提取 C++ 代码
    
    Args:
        response: 模型生成的原始响应
    
    Returns:
        str: 提取出的 C++ 代码
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


def compile_and_run(code, test_cases, timeout=30, language="cpp"):
    """
    编译并运行代码，返回测试结果
    
    Args:
        code: C++ 源代码
        test_cases: 测试用例列表 [{"input": "...", "output": "..."}]
        timeout: 超时时间（秒）
        language: 编程语言
    
    Returns:
        dict: {
            "success": bool,           # 是否所有测试通过
            "compilation_error": str,  # 编译错误信息（如果有）
            "runtime_error": str,      # 运行时错误（如果有）
            "test_results": list       # 每个测试用例的结果
        }
    """
    result = {
        "success": False,
        "compilation_error": None,
        "runtime_error": None,
        "test_results": []
    }
    
    # 创建临时文件
    with tempfile.TemporaryDirectory() as tmpdir:
        if language == "cpp":
            src_file = Path(tmpdir) / "solution.cpp"
            exe_file = Path(tmpdir) / "solution"
            
            # 写入源代码
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            # 编译
            compile_result = subprocess.run(
                ["g++", str(src_file), "-o", str(exe_file), "-std=c++17"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if compile_result.returncode != 0:
                result["compilation_error"] = compile_result.stderr
                return result
            
            # 运行测试用例
            for i, tc in enumerate(test_cases):
                try:
                    run_result = subprocess.run(
                        [str(exe_file)],
                        input=tc.get("input", ""),
                        capture_output=True,
                        text=True,
                        timeout=timeout
                    )
                    
                    actual_output = run_result.stdout.strip()
                    expected_output = tc.get("output", "").strip()
                    
                    test_passed = actual_output == expected_output
                    
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": expected_output,
                        "actual": actual_output,
                        "passed": test_passed
                    })
                except subprocess.TimeoutExpired:
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": tc.get("output", ""),
                        "actual": "TIMEOUT",
                        "passed": False
                    })
                except Exception as e:
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": tc.get("output", ""),
                        "actual": str(e),
                        "passed": False
                    })
        
        elif language == "python":
            src_file = Path(tmpdir) / "solution.py"
            
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            for i, tc in enumerate(test_cases):
                try:
                    run_result = subprocess.run(
                        ["python3", str(src_file)],
                        input=tc.get("input", ""),
                        capture_output=True,
                        text=True,
                        timeout=timeout
                    )
                    
                    actual_output = run_result.stdout.strip()
                    expected_output = tc.get("output", "").strip()
                    
                    test_passed = actual_output == expected_output
                    
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": expected_output,
                        "actual": actual_output,
                        "passed": test_passed
                    })
                except subprocess.TimeoutExpired:
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": tc.get("output", ""),
                        "actual": "TIMEOUT",
                        "passed": False
                    })
                except Exception as e:
                    result["test_results"].append({
                        "test_id": i + 1,
                        "input": tc.get("input", ""),
                        "expected": tc.get("output", ""),
                        "actual": str(e),
                        "passed": False
                    })
    
    # 判断是否全部通过
    result["success"] = all(tr["passed"] for tr in result["test_results"])
    
    return result


def test_single_problem(problem, timeout=30, verbose=False):
    """
    测试单个问题
    
    Args:
        problem: 问题数据字典
        timeout: 超时时间
    
    Returns:
        dict: 测试结果
    """
    problem_id = problem.get("id", problem.get("problem_id", "unknown"))
    title = problem.get("title", "")
    description = problem.get("description", problem.get("prompt", ""))
    test_cases = problem.get("test_cases", [])  # private_test_cases 用于最终评测
    public_test_cases = problem.get("public_test_cases", [])  # public_test_cases 用于主持人审查
    starter_code = problem.get("starter_code", {}).get("cpp", "")
    language = problem.get("language", "cpp")
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"问题 {problem_id}: {title}")
        print(f"描述: {description[:200]}..." if len(description) > 200 else f"描述: {description}")
        print(f"测试用例数量: {len(test_cases)}")
    
    # 构建完整问题描述
    full_question = f"题目: {title}\n\n{description}"
    if starter_code:
        full_question += f"\n\n参考代码:\n{starter_code}"
    
    # 调用多智能体系统生成代码（传入 public_test_cases 用于主持人审查）
    print(f"  正在调用 {len(MODELS)-1} 个成员模型生成代码...")
    raw_code = solve_problem(full_question, test_cases=public_test_cases)
    
    # 提取纯代码
    code = extract_code_from_response(raw_code)
    
    if verbose:
        print(f"  生成代码长度: {len(code)} 字符")
        print(f"  代码预览:\n{code[:300]}...")
    
    # 编译并运行（使用 private_test_cases 进行最终评测）
    print(f"  正在编译和运行...")
    test_result = compile_and_run(code, test_cases, timeout=timeout, language=language)
    
    return {
        "problem_id": problem_id,
        "title": title,
        "generated_code": code,
        "test_result": test_result
    }


def run_batch_test(data_dir, limit=None, start_index=0, end_index=None, timeout=30, output="results.csv", verbose=False):
    """
    批量测试主函数
    
    Args:
        data_dir: 数据目录
        limit: 限制测试数量（与 end-index 二选一）
        start_index: 起始索引（从第几个题目开始，0-based）
        end_index: 结束索引（测试到第几个题目结束，0-based，不包含）
        timeout: 单题超时时间
        output: 输出文件
        verbose: 详细输出
    """
    print("=" * 60)
    print("LiveCodeBench 批量测试")
    print("=" * 60)
    print(f"数据目录: {data_dir}")
    print(f"主持人：{MODELS[0]}")
    print(f"成员: {[MODELS[i+1] for i in range(MEMBER_COUNT)]}")
    print(f"测试用例审查员: {REVIEWER_MODEL}")
    
    # 加载数据（先加载全部，后面再用 limit 或范围限制）
    print("\n加载数据集...")
    try:
        problems = load_livecodebench_dataset(data_dir, limit=None)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("\n请将 LiveCodeBench 数据放入指定目录。")
        print("可以从此处下载: https://livecodebench.github.io/")
        return
    
    total = len(problems)
    print(f"共加载 {total} 道问题")
    
    # 限制测试数量
    if end_index is not None:
        # 指定范围 [start_index, end_index)
        problems = problems[start_index:end_index]
        print(f"测试范围: 第 {start_index+1} - {end_index} 题 (共 {len(problems)} 题)")
    elif limit:
        problems = problems[start_index:start_index + limit]
        print(f"测试范围: 第 {start_index+1} - {start_index + len(problems)} 题")
    elif start_index > 0:
        problems = problems[start_index:]
        print(f"测试范围: 第 {start_index+1} - {total} 题")
    
    # 测试结果
    results = []
    passed_count = 0
    total_count = len(problems)
    
    # 创建结果目录
    output_dir = Path(output).parent
    if output_dir and not output_dir.exists():
        output_dir.mkdir(parents=True)
    
    start_time = datetime.now()
    
    for i, problem in enumerate(problems):
        problem_id = problem.get("id", problem.get("problem_id", f"problem_{i}"))
        print(f"\n[{i+1}/{total_count}] 测试问题: {problem_id}")
        
        try:
            result = test_single_problem(problem, timeout=timeout, verbose=verbose)
            results.append(result)
            
            # 统计
            if result["test_result"]["success"]:
                passed_count += 1
                print(f"  ✓ 测试通过!")
            else:
                failed_count = sum(1 for tr in result["test_result"]["test_results"] if not tr["passed"])
                print(f"  ✗ 测试失败 ({failed_count} 个用例)")
                
                if verbose and result["test_result"]["compilation_error"]:
                    print(f"  编译错误: {result['test_result']['compilation_error'][:200]}")
        
        except Exception as e:
            print(f"  ✗ 测试出错: {e}")
            results.append({
                "problem_id": problem_id,
                "title": problem.get("title", ""),
                "generated_code": "",
                "test_result": {"success": False, "error": str(e)}
            })
    
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    # 输出统计
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    print(f"总题数: {total_count}")
    print(f"通过: {passed_count}")
    print(f"失败: {total_count - passed_count}")
    if total_count > 0:
        print(f"通过率: {passed_count/total_count*100:.2f}%")
    else:
        print("通过率: N/A (无测试题目)")
    print(f"总耗时: {elapsed/60:.2f} 分钟")
    print(f"平均每题: {elapsed/total_count:.2f} 秒")
    
    # 保存 CSV 结果
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "problem_id", "title", "passed", "test_count", 
            "compilation_error", "runtime_error", "code_length"
        ])
        
        for r in results:
            tr = r.get("test_result", {})
            writer.writerow([
                r["problem_id"],
                r["title"],
                tr.get("success", False),
                len(tr.get("test_results", [])),
                tr.get("compilation_error", "")[:100] if tr.get("compilation_error") else "",
                tr.get("runtime_error", "")[:100] if tr.get("runtime_error") else "",
                len(r.get("generated_code", ""))
            ])
    
    print(f"\n结果已保存到: {output}")
    
    # 保存详细 JSON 结果
    json_output = output.replace(".csv", "_details.json")
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"详细结果已保存到: {json_output}")
    
    return results


def main():
    """主入口"""
    args = parse_args()
    run_batch_test(
        data_dir=args.data_dir,
        limit=args.limit,
        start_index=args.start_index,
        end_index=args.end_index,
        timeout=args.timeout,
        output=args.output,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
