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
        
        return jsonify({
            'success': True,
            'title': formatted.get('question_title', ''),
            'test_cases_count': len(test_cases)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/ideas', methods=['POST'])
def ideas():
    try:
        # 使用之前格式化的题目
        question = state.question_to_use if state.question_to_use else state.question
        
        ideas, failed = get_ideas(question)
        state.ideas = ideas
        
        valid_count = sum(1 for i in ideas if i and i.strip())
        
        return jsonify({
            'success': True,
            'count': valid_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/select_idea', methods=['POST'])
def select_idea():
    try:
        best_idx = select_best_idea(state.ideas)
        state.best_idea_idx = best_idx
        
        return jsonify({
            'success': True,
            'best_idx': best_idx
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
        
        return jsonify({
            'success': True,
            'count': valid_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/select_code', methods=['POST'])
def select_code():
    try:
        best_idx = select_best_code(state.codes)
        state.best_code_idx = best_idx
        
        return jsonify({
            'success': True,
            'best_idx': best_idx
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/review', methods=['POST'])
def review():
    try:
        best_code = state.codes[state.best_code_idx - 1] if state.best_code_idx and state.codes else ''
        
        final_code = host_review_code_simple(
            best_code, 
            state.best_code_idx, 
            state.question,
            state.current_test_cases,
            state.question_to_use
        )
        
        state.final_code = final_code
        
        return jsonify({
            'success': True,
            'code': final_code
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    print("=" * 50)
    print("6LLMs 前端服务启动")
    print("访问 http://localhost:5000 查看前端")
    print("=" * 50)
    app.run(debug=True, port=5000)