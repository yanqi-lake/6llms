"""
并行多模型测试脚本

用于同时测试多个模型在 LiveCodeBench 数据集上的代码生成能力。
每个模型在独立的进程中运行，互不干扰。

用法:
    python test_parallel_models.py                              # 并行测试所有模型
    python test_parallel_models.py --models "model1" "model2" # 指定模型列表
    python test_parallel_models.py --limit 10             # 每模型测试10道题
    python test_parallel_models.py --parallel 3           # 最多并行3个
"""

import argparse
import multiprocessing as mp
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MODELS


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="并行多模型测试")
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=None,
        help="指定要测试的模型列表（默认为 MODELS 中的所有模型）"
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
        help="限制每个模型测试的问题数量"
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
        "--api-timeout",
        type=int,
        default=120,
        help="API 调用超时时间（秒）"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=None,
        help="最大并行数（默认为模型数量）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细输出"
    )
    return parser.parse_args()


def run_single_model_test(model, data_dir, limit, start_index, timeout, api_timeout, verbose, base_output_dir):
    """
    在独立进程中运行单个模型的测试
    """
    # 构建输出文件名
    model_short = model.split("/")[-1].replace("-", "_")
    output_file = os.path.join(base_output_dir, f"results_{model_short}.csv")
    log_file = os.path.join(base_output_dir, f"log_{model_short}.txt")
    
    # 构建命令
    cmd = [
        sys.executable,
        "single_llm/test_single_model.py",
        "--model", model,
        "--data-dir", data_dir,
        "--output", output_file,
        "--timeout", str(timeout)
    ]
    
    if limit:
        cmd.extend(["--limit", str(limit)])
    
    if start_index > 0:
        cmd.extend(["--start-index", str(start_index)])
    
    if verbose:
        cmd.append("--verbose")
    
    print(f"[{model}] 启动测试进程...")
    print(f"[{model}] 命令: {' '.join(cmd)}")
    print(f"[{model}] 输出: {output_file}")
    print(f"[{model}] 日志: {log_file}")
    
    # 启动进程
    with open(log_file, "w") as log_f:
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=base_output_dir,
            env={**os.environ, "API_TIMEOUT": str(api_timeout)}
        )
    
    return proc, model, output_file, log_file


def monitor_processes(procs_info, check_interval=30):
    """
    监控所有进程的运行状态
    """
    print("\n" + "=" * 60)
    print("监控所有测试进程...")
    print("=" * 60)
    
    while True:
        all_done = True
        for proc, model, output_file, log_file in procs_info:
            if proc.poll() is None:
                # 进程仍在运行
                all_done = False
                # 尝试读取日志文件的最后几行
                try:
                    with open(log_file, "r") as f:
                        lines = f.readlines()
                        if lines:
                            last_lines = lines[-5:]
                            print(f"\n[{model}] 最近输出:")
                            for line in last_lines:
                                print(f"  {line.rstrip()}")
                except:
                    pass
            else:
                # 进程已结束
                returncode = proc.returncode
                if returncode == 0:
                    print(f"[{model}] ✓ 测试完成")
                else:
                    print(f"[{model}] ✗ 测试异常退出 (返回码: {returncode})")
        
        if all_done:
            print("\n所有模型测试完成!")
            break
        
        time.sleep(check_interval)


def main():
    """主入口"""
    args = parse_args()
    
    # 确定要测试的模型
    models = args.models if args.models else MODELS
    print(f"将测试 {len(models)} 个模型:")
    for m in models:
        print(f"  - {m}")
    
    # 确定并行数
    parallel = args.parallel if args.parallel else len(models)
    print(f"最大并行数: {parallel}")
    
    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(__file__), f"parallel_test_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}")
    
    # 使用信号量控制并行数
    semaphore = mp.Semaphore(parallel)
    
    # 启动所有模型的测试进程
    procs_info = []
    
    for model in models:
        # 获取信号量（阻塞直到可用）
        print(f"\n启动模型 {model} 的测试...")
        
        proc, model_name, output_file, log_file = run_single_model_test(
            model=model,
            data_dir=args.data_dir,
            limit=args.limit,
            start_index=args.start_index,
            timeout=args.timeout,
            api_timeout=args.api_timeout,
            verbose=args.verbose,
            base_output_dir=output_dir
        )
        
        procs_info.append((proc, model_name, output_file, log_file))
        
        # 如果达到并行上限，等待一下
        if len(procs_info) >= parallel:
            print(f"已达到并行上限 {parallel}，等待进程启动...")
            time.sleep(2)
    
    print(f"\n已启动所有 {len(models)} 个测试进程")
    print("=" * 60)
    
    # 等待所有进程完成
    try:
        monitor_processes(procs_info, check_interval=60)
    except KeyboardInterrupt:
        print("\n\n检测到 Ctrl+C，是否终止所有测试进程? (y/n)")
        if input().strip().lower() == 'y':
            for proc, model, _, _ in procs_info:
                if proc.poll() is None:
                    print(f"终止 {model}...")
                    proc.terminate()
            print("所有进程已终止")
        else:
            print("继续等待...")
            monitor_processes(procs_info, check_interval=60)
    
    # 输出汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for proc, model, output_file, log_file in procs_info:
        returncode = proc.wait()
        status = "✓ 完成" if returncode == 0 else f"✗ 异常 ({returncode})"
        print(f"{model}: {status}")
        print(f"  结果: {output_file}")
        print(f"  日志: {log_file}")
    
    print(f"\n所有测试完成！结果目录: {output_dir}")
    
    return output_dir


if __name__ == "__main__":
    main()