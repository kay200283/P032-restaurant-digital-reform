#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统管理模块"""

from flask import Blueprint, render_template, request, jsonify, session, redirect
import sqlite3
import os
import hashlib

system_bp = Blueprint('system', __name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@system_bp.route('/system')
def system_page():
    if 'user' not in session:
        return redirect('/login')
    return render_template('system.html')

@system_bp.route('/api/system/users', methods=['GET'])
def api_list_users():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, display_name, role, must_change_password, created_at, updated_at FROM users ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

@system_bp.route('/api/system/users', methods=['POST'])
def api_create_user():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'carrier')
    display_name = data.get('display_name', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6位'}), 400
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, display_name, role, must_change_password)
            VALUES (?, ?, ?, ?, 1)
        ''', (username, password_hash, display_name, role))
        conn.commit()
        return jsonify({'success': True, 'message': '创建成功'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': '用户名已存在'}), 400
    finally:
        conn.close()

@system_bp.route('/api/system/users/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': '不能删除当前登录账号'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '删除成功'})

@system_bp.route('/api/system/users/<int:user_id>/reset_password', methods=['POST'])
def api_reset_password(user_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '110808')
    password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET password_hash = ?, must_change_password = 1,
        login_attempts = 0, locked_until = NULL, updated_at = datetime("now","localtime")
        WHERE id = ?
    ''', (password_hash, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '密码已重置，用户下次登录需修改密码'})

@system_bp.route('/api/system/logs', methods=['GET'])
def api_list_logs():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT 100')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})
