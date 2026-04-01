"""
单一模型测试脚本

用于测试单一模型在 LiveCodeBench 数据集上的代码生成能力。
与多智能体协作系统对比，验证多模型协作是否优于单一模型。

用法:
    python test_single_model.py                                    # 交互式选择模型
    python test_single_model.py --model "Qwen/Qwen2.5-14B-Instruct"  # 指定模型
    python test_single_model.py --model "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B" --limit 10
    python test_single_model.py --output results_single.csv
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

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import call_api
from config import MODELS


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="单一模型测试")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定要测试的模型（默认为 MODELS[0] 主持人模型）"
    )
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
        default="test_results_single.csv",
        help="结果输出文件"
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="起始索引"
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
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="列出可用模型并退出"
    )
    return parser.parse_args()


def list_available_models():
    """列出所有可用模型"""
    print("可用模型列表：")
    for i, model in enumerate(MODELS):
        print(f"  [{i}] {model}")
    return MODELS


def select_model(model_name=None):
    """选择要测试的模型"""
    if model_name:
        # 验证模型是否在列表中
        if model_name in MODELS:
            return model_name
        else:
            print(f"警告：指定模型 '{model_name}' 不在 MODELS 列表中，将使用该模型（可能不在硅基流动支持列表中）")
            return model_name
    
    # 交互式选择
    print("\n请选择要测试的模型：")
    for i, model in enumerate(MODELS):
        print(f"  [{i}] {model}")
    
    try:
        choice = int(input("\n请输入模型编号: ").strip())
        if 0 <= choice < len(MODELS):
            return MODELS[choice]
        else:
            print(f"无效编号，将使用默认模型 {MODELS[0]}")
            return MODELS[0]
    except ValueError:
        print(f"输入无效，将使用默认模型 {MODELS[0]}")
        return MODELS[0]


def load_livecodebench_dataset(data_dir):
    """
    加载 LiveCodeBench 数据集
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
                    q_data = json.loads(line)
                    
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
                        "language": "cpp",
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
                    
                    # 优先使用 private_test_cases
                    if private_tc:
                        test_cases = [{"input": tc.get("input", ""), "output": tc.get("output", "")} for tc in private_tc]
                    else:
                        test_cases = [{"input": tc.get("input", ""), "output": tc.get("output", "")} for tc in public_tc]
                    
                    problem["test_cases"] = test_cases
                    questions.append(problem)
        
        return questions
    
    raise FileNotFoundError(f"无法在 {data_dir} 找到 LiveCodeBench 数据")


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


def compile_and_run(code, test_cases, timeout=30, language="cpp"):
    """
    编译并运行代码，返回测试结果
    """
    result = {
        "success": False,
        "compilation_error": None,
        "runtime_error": None,
        "test_results": []
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        if language == "cpp":
            src_file = Path(tmpdir) / "solution.cpp"
            exe_file = Path(tmpdir) / "solution"
            
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            compile_result = subprocess.run(
                ["g++", str(src_file), "-o", str(exe_file), "-std=c++17"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if compile_result.returncode != 0:
                result["compilation_error"] = compile_result.stderr
                return result
            
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
    
    result["success"] = all(tr["passed"] for tr in result["test_results"])
    
    return result


def generate_code_single_model(question, model, verbose=False):
    """
    使用单一模型直接生成代码
    
    Args:
        question: 问题描述
        model: 模型名称
        verbose: 是否显示详细信息
    
    Returns:
        str: 生成的代码
    """
    # 构造提示词（类似于多智能体系统中的写代码步骤，但更完整）
    prompt = f"""原始问题：{question}

请根据以上问题，编写完整的C++代码实现。要求：
1. 代码应包含必要的注释，解释关键部分。
2. 考虑边界条件和错误处理。
3. 代码风格清晰，符合C++规范，必须保证编译过程不出任何错误
4. 仅返回代码，不要包含任何额外解释或标记（如```cpp```），不要产生额外的文本输出。
5. 如果题目中有要求的输入输出格式要严格按照输入输出格式处理输入和输出。
"""
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    if verbose:
        print(f"  调用模型: {model}")
    
    try:
        response = call_api(messages, model=model)
        code = extract_code_from_response(response)
        return code
    except Exception as e:
        print(f"  API 调用失败: {e}")
        return ""


def test_single_problem(problem, model, timeout=30, verbose=False):
    """
    测试单个问题（使用单一模型）
    """
    problem_id = problem.get("id", problem.get("problem_id", "unknown"))
    title = problem.get("title", "")
    description = problem.get("description", problem.get("prompt", ""))
    test_cases = problem.get("test_cases", [])
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
    
    # 调用单一模型生成代码
    if verbose:
        print(f"  正在调用模型 {model} 生成代码...")
    code = generate_code_single_model(full_question, model, verbose=verbose)
    
    if verbose:
        print(f"  生成代码长度: {len(code)} 字符")
        if code:
            print(f"  代码预览:\n{code[:300]}...")
    
    if not code:
        return {
            "problem_id": problem_id,
            "title": title,
            "generated_code": "",
            "test_result": {
                "success": False,
                "compilation_error": "模型未能生成代码",
                "runtime_error": None,
                "test_results": []
            }
        }
    
    # 编译并运行
    if verbose:
        print(f"  正在编译和运行...")
    test_result = compile_and_run(code, test_cases, timeout=timeout, language=language)
    
    return {
        "problem_id": problem_id,
        "title": title,
        "generated_code": code,
        "test_result": test_result
    }


def run_batch_test(model, data_dir, limit=None, start_index=0, timeout=30, output="results.csv", verbose=False):
    """
    批量测试主函数
    """
    print("=" * 60)
    print("单一模型批量测试")
    print("=" * 60)
    print(f"测试模型: {model}")
    print(f"数据目录: {data_dir}")
    
    # 加载数据
    print("\n加载数据集...")
    try:
        problems = load_livecodebench_dataset(data_dir)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("\n请将 LiveCodeBench 数据放入指定目录。")
        return
    
    total = len(problems)
    print(f"共加载 {total} 道问题")
    
    # 限制测试数量
    if limit:
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
            result = test_single_problem(problem, model, timeout=timeout, verbose=verbose)
            results.append(result)
            
            # 统计
            if result["test_result"]["success"]:
                passed_count += 1
                print(f"  ✓ 测试通过!")
            else:
                failed_count = sum(1 for tr in result["test_result"]["test_results"] if not tr["passed"])
                print(f"  ✗ 测试失败 ({failed_count} 个用例)")
                # 显示每个测试点的通过情况
                test_results = result["test_result"]["test_results"]
                for tr in test_results:
                    status = "✓" if tr["passed"] else "✗"
                    test_id = tr.get("test_id", "?")
                    print(f"    测试点 {test_id}: {status}")
                    if not tr["passed"]:
                        # 显示期望输出和实际输出的对比（截断）
                        expected = tr.get("expected", "")[:50]
                        actual = tr.get("actual", "")[:50]
                        print(f"      期望: {expected}")
                        print(f"      实际: {actual}")
                
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
    print(f"测试模型: {model}")
    print(f"总题数: {total_count}")
    print(f"通过: {passed_count}")
    print(f"失败: {total_count - passed_count}")
    print(f"通过率: {passed_count/total_count*100:.2f}%")
    print(f"总耗时: {elapsed/60:.2f} 分钟")
    print(f"平均每题: {elapsed/total_count:.2f} 秒")
    
    # 保存 CSV 结果
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "problem_id", "title", "passed", "test_count", 
            "compilation_error", "runtime_error", "code_length", "model"
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
                len(r.get("generated_code", "")),
                model
            ])
    
    print(f"\n结果已保存到: {output}")
    
    # 保存详细 JSON 结果（包含每个测试点的详细信息）
    json_output = output.replace(".csv", "_details.json")
    with open(json_output, "w", encoding="utf-8") as f:
        # 自定义序列化，保留完整的测试结果信息
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"详细结果已保存到: {json_output}")
    
    # 生成人类可读的测试报告
    report_output = output.replace(".csv", "_report.txt")
    with open(report_output, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("单一模型测试报告\n")
        f.write("=" * 70 + "\n")
        f.write(f"测试模型: {model}\n")
        f.write(f"测试题数: {total_count}\n")
        f.write(f"通过数量: {passed_count}\n")
        f.write(f"失败数量: {total_count - passed_count}\n")
        f.write(f"通过率: {passed_count/total_count*100:.2f}%\n")
        f.write(f"总耗时: {elapsed/60:.2f} 分钟\n")
        f.write("=" * 70 + "\n\n")
        
        for r in results:
            problem_id = r.get("problem_id", "unknown")
            title = r.get("title", "")
            tr = r.get("test_result", {})
            passed = tr.get("success", False)
            
            f.write(f"问题: {problem_id} - {title}\n")
            f.write(f"状态: {'✓ 通过' if passed else '✗ 失败'}\n")
            
            test_results = tr.get("test_results", [])
            for t in test_results:
                test_id = t.get("test_id", "?")
                status = "✓" if t.get("passed") else "✗"
                f.write(f"  测试点 {test_id}: {status}\n")
                if not t.get("passed"):
                    f.write(f"    期望输出: {t.get('expected', '')}\n")
                    f.write(f"    实际输出: {t.get('actual', '')}\n")
            
            if tr.get("compilation_error"):
                f.write(f"编译错误: {tr.get('compilation_error', '')[:200]}...\n")
            
            f.write("\n")
    
    print(f"测试报告已保存到: {report_output}")
    
    return results


def main():
    """主入口"""
    args = parse_args()
    
    # 列出模型
    if args.list_models:
        list_available_models()
        return
    
    # 选择模型
    model = select_model(args.model)
    print(f"\n选定的测试模型: {model}")
    
    run_batch_test(
        model=model,
        data_dir=args.data_dir,
        limit=args.limit,
        start_index=args.start_index,
        timeout=args.timeout,
        output=args.output,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()