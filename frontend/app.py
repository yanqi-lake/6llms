# frontend/app.py
# Flask API 后端服务

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request
import json

app = Flask(__name__, template_folder='.')

# 导入主系统的函数
from main import (
    format_question,
    get_ideas,
    select_best_idea,
    generate_codes,
    select_best_code,
    host_review_code_simple,
    current_test_cases,
    current_best_idea,
    MODELS,
    MEMBER_COUNT,
    REVIEWER_MODEL
)

# 全局状态
class State:
    def __init__(self):
        self.question = None
        self.formatted_question = None
        self.question_to_use = None
        self.ideas = []
        self.best_idea_idx = None
        self.codes = []
        self.best_code_idx = None
        self.final_code = None
        self.current_test_cases = []
        self.idea_votes = {}  # 记录思路投票
        self.code_votes = {}  # 记录代码投票
        self.review_details = {}  # 记录审查详情
        
state = State()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config')
def config():
    return jsonify({
        'success': True,
        'host_model': MODELS[0],
        'member_count': MEMBER_COUNT,
        'reviewer_model': REVIEWER_MODEL,
        'member_models': [MODELS[i+1] for i in range(MEMBER_COUNT)]
    })


@app.route('/api/format', methods=['POST'])
def format():
    try:
        data = request.json
        question = data.get('question', '')
        
        state.question = question
        formatted, question_str = format_question(question)
        
        state.formatted_question = formatted
        state.question_to_use = question_str if question_str else question
        
        # 提取测试用例
        test_cases = formatted.get('public_test_cases', []) if formatted else []
        state.current_test_cases = test_cases
        
        print(f"[FORMAT API] 提取的 test_cases: {test_cases}")
        
        return jsonify({
            'success': True,
            'title': formatted.get('question_title', ''),
            'difficulty': formatted.get('difficulty', ''),
            'platform': formatted.get('platform', ''),
            'constraints': formatted.get('constraints', ''),
            'input_format': formatted.get('input_format', ''),
            'output_format': formatted.get('output_format', ''),
            'sample_input': formatted.get('sample_input', ''),
            'sample_output': formatted.get('sample_output', ''),
            'test_cases_count': len(test_cases),
            'test_cases': test_cases,
            'full_question': state.question_to_use
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/ideas', methods=['POST'])
def ideas():
    try:
        print(f"[IDEAS API] state.current_test_cases: {state.current_test_cases}")
        
        # 使用之前格式化的题目
        question = state.question_to_use if state.question_to_use else state.question
        
        ideas, failed = get_ideas(question)
        state.ideas = ideas
        
        valid_count = sum(1 for i in ideas if i and i.strip())
        
        # 格式化每个成员的思路
        ideas_detail = []
        for i, idea in enumerate(ideas):
            ideas_detail.append({
                'member': i + 1,
                'model': MODELS[i+1],
                'idea': idea if idea else '',
                'failed': i in failed
            })
        
        return jsonify({
            'success': True,
            'count': valid_count,
            'ideas': ideas_detail,
            'failed_members': [i+1 for i in failed]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/select_idea', methods=['POST'])
def select_idea():
    try:
        # 先执行投票
        best_idx = select_best_idea(state.ideas)
        state.best_idea_idx = best_idx
        
        # 读取投票详情（投票执行后才会有结果）
        import os
        details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
        vote_detail = ''
        vote_file = os.path.join(details_dir, 'stage2_vote_result.txt')
        if os.path.exists(vote_file):
            with open(vote_file, 'r', encoding='utf-8') as f:
                vote_detail = f.read()
        
        # 解析投票结果
        votes = {}
        if vote_detail:
            import re
            match = re.search(r'投票结果: \[(.*?)\]', vote_detail)
            if match:
                vote_list = match.group(1).split(',')
                for v in vote_list:
                    v = v.strip()
                    if v:
                        votes[int(v)] = votes.get(int(v), 0) + 1
        
        return jsonify({
            'success': True,
            'best_idx': best_idx,
            'vote_detail': vote_detail,
            'votes': votes,
            'best_idea': state.ideas[best_idx - 1] if state.ideas and best_idx else ''
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/code', methods=['POST'])
def code():
    try:
        question = state.question_to_use if state.question_to_use else state.question
        solution = state.ideas[state.best_idea_idx - 1] if state.best_idea_idx else ''
        
        codes, failed = generate_codes(question, solution)
        state.codes = codes
        
        valid_count = sum(1 for c in codes if c and c.strip())
        
        # 格式化每个成员的代码
        codes_detail = []
        for i, code in enumerate(codes):
            codes_detail.append({
                'member': i + 1,
                'model': MODELS[i+1],
                'code': code if code else '',
                'failed': i in failed
            })
        
        return jsonify({
            'success': True,
            'count': valid_count,
            'codes': codes_detail,
            'failed_members': [i+1 for i in failed]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/select_code', methods=['POST'])
def select_code():
    try:
        # 先执行投票
        best_idx = select_best_code(state.codes)
        state.best_code_idx = best_idx
        
        # 读取投票详情（投票执行后才会有结果）
        import os
        details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
        vote_detail = ''
        vote_file = os.path.join(details_dir, 'stage4_vote_result.txt')
        if os.path.exists(vote_file):
            with open(vote_file, 'r', encoding='utf-8') as f:
                vote_detail = f.read()
        
        # 解析投票结果
        votes = {}
        if vote_detail:
            import re
            match = re.search(r'投票结果: \[(.*?)\]', vote_detail)
            if match:
                vote_list = match.group(1).split(',')
                for v in vote_list:
                    v = v.strip()
                    if v:
                        votes[int(v)] = votes.get(int(v), 0) + 1
        
        return jsonify({
            'success': True,
            'best_idx': best_idx,
            'vote_detail': vote_detail,
            'votes': votes,
            'best_code': state.codes[best_idx - 1] if state.codes and best_idx else ''
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/review', methods=['POST'])
def review():
    try:
        best_code = state.codes[state.best_code_idx - 1] if state.best_code_idx and state.codes else ''
        
        # 读取审查详情
        import os
        details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
        review_detail = ''
        input_file = os.path.join(details_dir, 'stage5_input.txt')
        final_file = os.path.join(details_dir, 'stage5_final_code.txt')
        
        if os.path.exists(input_file):
            with open(input_file, 'r', encoding='utf-8') as f:
                review_detail = f.read()
        
        # 调试：打印接收到的 test_cases
        print(f"[REVIEW API] 接收到的 test_cases: {state.current_test_cases}")
        
        final_code = host_review_code_simple(
            best_code, 
            state.best_code_idx, 
            state.question,
            state.current_test_cases,
            state.question_to_use
        )
        
        state.final_code = final_code
        
        # 读取最终代码
        final_code_detail = ''
        if os.path.exists(final_file):
            with open(final_file, 'r', encoding='utf-8') as f:
                final_code_detail = f.read()
        
        return jsonify({
            'success': True,
            'code': final_code,
            'code_length': len(final_code),
            'review_detail': review_detail,
            'best_code_idx': state.best_code_idx,
            'test_cases_count': len(state.current_test_cases)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    print("=" * 50)
    print("6LLMs 前端服务启动")
    print("访问 http://localhost:5000 查看前端")
    print("=" * 50)
    app.run(debug=True, port=5000)


@app.route('/api/stage/<int:stage_num>', methods=['GET'])
def get_stage_detail(stage_num):
    """获取指定阶段的详细信息"""
    try:
        if stage_num == 0:
            # 格式化题目阶段
            return jsonify({
                'success': True,
                'stage': 0,
                'title': '主持人格式化题目',
                'formatted': state.formatted_question,
                'full_question': state.question_to_use,
                'test_cases': state.current_test_cases
            })
        elif stage_num == 1:
            # 生成思路阶段
            ideas_detail = []
            for i, idea in enumerate(state.ideas):
                ideas_detail.append({
                    'member': i + 1,
                    'model': MODELS[i+1] if i+1 < len(MODELS) else 'Unknown',
                    'idea': idea if idea else ''
                })
            return jsonify({
                'success': True,
                'stage': 1,
                'title': '成员生成解题思路',
                'ideas': ideas_detail
            })
        elif stage_num == 2:
            # 思路投票阶段
            import os
            details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
            vote_detail = ''
            vote_file = os.path.join(details_dir, 'stage2_vote_result.txt')
            if os.path.exists(vote_file):
                with open(vote_file, 'r', encoding='utf-8') as f:
                    vote_detail = f.read()
            
            return jsonify({
                'success': True,
                'stage': 2,
                'title': '投票选择最佳思路',
                'best_idx': state.best_idea_idx,
                'best_idea': state.ideas[state.best_idea_idx - 1] if state.best_idea_idx and state.ideas else '',
                'vote_detail': vote_detail,
                'all_ideas': state.ideas
            })
        elif stage_num == 3:
            # 编写代码阶段
            codes_detail = []
            for i, code in enumerate(state.codes):
                codes_detail.append({
                    'member': i + 1,
                    'model': MODELS[i+1] if i+1 < len(MODELS) else 'Unknown',
                    'code': code if code else ''
                })
            return jsonify({
                'success': True,
                'stage': 3,
                'title': '成员编写代码',
                'codes': codes_detail
            })
        elif stage_num == 4:
            # 代码投票阶段
            import os
            details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
            vote_detail = ''
            vote_file = os.path.join(details_dir, 'stage4_vote_result.txt')
            if os.path.exists(vote_file):
                with open(vote_file, 'r', encoding='utf-8') as f:
                    vote_detail = f.read()
            
            return jsonify({
                'success': True,
                'stage': 4,
                'title': '投票选择最佳代码',
                'best_idx': state.best_code_idx,
                'best_code': state.codes[state.best_code_idx - 1] if state.best_code_idx and state.codes else '',
                'vote_detail': vote_detail,
                'all_codes': state.codes
            })
        elif stage_num == 5:
            # 审查代码阶段
            import os
            details_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'details')
            review_detail = ''
            final_code = ''
            input_file = os.path.join(details_dir, 'stage5_input.txt')
            final_file = os.path.join(details_dir, 'stage5_final_code.txt')
            
            if os.path.exists(input_file):
                with open(input_file, 'r', encoding='utf-8') as f:
                    review_detail = f.read()
            if os.path.exists(final_file):
                with open(final_file, 'r', encoding='utf-8') as f:
                    final_code = f.read()
            
            return jsonify({
                'success': True,
                'stage': 5,
                'title': '主持人审查代码',
                'final_code': final_code or state.final_code,
                'code_length': len(final_code or state.final_code or ''),
                'review_detail': review_detail,
                'test_cases': state.current_test_cases,
                'best_code_idx': state.best_code_idx
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid stage number'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})