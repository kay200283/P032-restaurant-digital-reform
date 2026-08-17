#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask - P032 Restaurant Digital Reform"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory
import os, logging, traceback
from datetime import datetime, timedelta

from init_db import init_database
init_database()

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = 'p032_rdr_7k9m2x4v8b1n5q7w3e6r9t0y2u4i6o8p'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_NAME'] = 'p032_session'
app.permanent_session_lifetime = timedelta(hours=12)

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

app_logger = logging.getLogger('p032')
app_logger.setLevel(logging.INFO)
app_handler = logging.FileHandler(os.path.join(LOG_DIR, 'app.log'), encoding='utf-8')
app_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(message)s'))
app_logger.addHandler(app_handler)

err_logger = logging.getLogger('p032.error')
err_logger.setLevel(logging.ERROR)
err_handler = logging.FileHandler(os.path.join(LOG_DIR, 'error.log'), encoding='utf-8')
err_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(message)s'))
err_logger.addHandler(err_handler)

@app.after_request
def log_request(resp):
    user = session.get('user', 'anonymous')
    app_logger.info(f'{request.method} {request.path} -> {resp.status_code} [user={user}]')
    if resp.content_type and 'text/html' in resp.content_type:
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/') or request.path.startswith('/work-mgmt/api/'):
        return jsonify({'success': False, 'message': 'not found'}), 404
    return render_template('login.html'), 404

@app.errorhandler(500)
def internal_error(e):
    tb = traceback.format_exc()
    user = session.get('user', 'anonymous')
    err_logger.error(f'500 | {request.method} {request.path} | user={user}\n{tb}')
    if request.path.startswith('/api/') or request.path.startswith('/work-mgmt/api/'):
        return jsonify({'success': False, 'message': 'internal error'}), 500
    return render_template('login.html'), 500

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

from modules.auth import auth_bp
from modules.system import system_bp
from modules.work_mgmt import work_mgmt_bp
from modules.dim_date import dim_date_bp
app.register_blueprint(auth_bp)
app.register_blueprint(system_bp)
app.register_blueprint(work_mgmt_bp)
app.register_blueprint(dim_date_bp)

@app.context_processor
def inject_user():
    user = session.get('user')
    role = session.get('role')
    if user and not role:
        try:
            import sqlite3 as _sq2
            _db2 = os.path.join(os.path.dirname(__file__), 'database.db')
            _c2 = _sq2.connect(_db2)
            _c2.row_factory = _sq2.Row
            _r2 = _c2.execute('SELECT role, display_name FROM users WHERE username = ?', (user,)).fetchone()
            _c2.close()
            if _r2:
                role = _r2['role']
                session['role'] = role
                if _r2['display_name'] and not session.get('display_name'):
                    session['display_name'] = _r2['display_name']
        except: pass
    return {'current_user': user, 'current_role': role, 'display_name': session.get('display_name', user or '')}


@app.route('/')
def index():
    return redirect(url_for('work_mgmt.calendar_page'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
