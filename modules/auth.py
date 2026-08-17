#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证模块 - 登录/改密码/防暴力破解"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, make_response
import sqlite3
import hashlib
import os
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@auth_bp.route('/login')
def login():
    if 'user' in session:
        next_url = request.args.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect(url_for('category.list_categories'))
    next_url = request.args.get('next', '')
    resp = make_response(render_template('login.html', next_url=next_url))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # 查询用户
    cursor.execute(
        'SELECT id, username, password_hash, role, display_name, must_change_password, login_attempts, locked_until FROM users WHERE username = ?',
        (username,)
    )
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    # 检查是否被锁定
    if user['locked_until']:
        try:
            locked_until = datetime.fromisoformat(user['locked_until'])
            if datetime.now() < locked_until:
                remaining = int((locked_until - datetime.now()).total_seconds())
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'账号已锁定，请{remaining}秒后再试',
                    'locked': True,
                    'remaining': remaining
                }), 403
            else:
                # 锁定已过期，重置
                cursor.execute(
                    'UPDATE users SET login_attempts = 0, locked_until = NULL WHERE id = ?',
                    (user['id'],)
                )
                conn.commit()
        except (ValueError, TypeError):
            pass

    # 验证密码
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user['password_hash'] != password_hash:
        # 登录失败，增加尝试次数
        new_attempts = (user['login_attempts'] or 0) + 1
        if new_attempts >= 5:
            locked_until = (datetime.now() + timedelta(minutes=5)).isoformat()
            cursor.execute(
                'UPDATE users SET login_attempts = ?, locked_until = ? WHERE id = ?',
                (new_attempts, locked_until, user['id'])
            )
            conn.commit()
            conn.close()
            return jsonify({
                'success': False,
                'message': '密码错误次数过多，账号已锁定5分钟',
                'locked': True,
                'remaining': 300
            }), 403
        else:
            cursor.execute(
                'UPDATE users SET login_attempts = ? WHERE id = ?',
                (new_attempts, user['id'])
            )
            conn.commit()
            conn.close()
            remaining_attempts = 5 - new_attempts
            return jsonify({
                'success': False,
                'message': f'用户名或密码错误，还剩{remaining_attempts}次机会'
            }), 401

    # 登录成功，重置尝试次数
    cursor.execute(
        'UPDATE users SET login_attempts = 0, locked_until = NULL WHERE id = ?',
        (user['id'],)
    )
    conn.commit()
    conn.close()

    # 写入session
    session['user_id'] = user['id']
    session['user'] = user['username']
    session['role'] = user['role']
    session['display_name'] = user['display_name']
    session.permanent = True

    return jsonify({
        'success': True,
        'message': '登录成功',
        'role': user['role'],
        'display_name': user['display_name'],
        'must_change_password': bool(user['must_change_password'])
    })

@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})

@auth_bp.route('/api/change-password', methods=['POST'])
def api_change_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '请填写完整'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少6位'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    old_hash = hashlib.sha256(old_password.encode()).hexdigest()
    if user['password_hash'] != old_hash:
        conn.close()
        return jsonify({'success': False, 'message': '原密码错误'}), 401

    new_hash = hashlib.sha256(new_password.encode()).hexdigest()
    cursor.execute(
        'UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = datetime("now","localtime") WHERE id = ?',
        (new_hash, session['user_id'])
    )
    conn.commit()
    conn.close()

    # Fix18: 同步更新session
    session['must_change_password'] = False

    return jsonify({'success': True, 'message': '密码修改成功'})

@auth_bp.route('/api/current_user')
def current_user():
    if 'user' in session:
        return jsonify({
            'logged_in': True,
            'user': session.get('user'),
            'role': session.get('role'),
            'display_name': session.get('display_name')
        })
    else:
        return jsonify({'logged_in': False})

def login_required(f):
    """登录验证装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(module, level='read'):
    """权限验证装饰器"""
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('auth.login', next=request.path))
            from app import ROLE_PERMISSIONS
            role = session.get('role')
            perms = ROLE_PERMISSIONS.get(role, {})
            perm = perms.get(module, 'none')
            levels = {'none': 0, 'read': 1, 'partial': 2, 'full': 3}
            if levels.get(perm, 0) < levels.get(level, 1):
                return jsonify({'success': False, 'message': '权限不足'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
