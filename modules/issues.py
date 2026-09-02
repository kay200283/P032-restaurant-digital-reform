#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P032 系统问题管理模块"""

from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime, timedelta, date as _date
from init_db import get_db
import json

from modules.auth import login_required

issues_bp = Blueprint('issues', __name__, url_prefix='/issues')

STATUS_ORDER = ['未开始','评估中','解决中','改善中','控制中','已解决','已关闭']
PRIORITY_ORDER = ['P0','P1','P2','P3']
CASE_TYPES = ['数据','POS-IT设备','合规','效期管理','商品管理','会员小程序','原料报损','点单管理','发票','功能需求','收银对账']

def _calc_days_open(found_date, resolve_date, status):
    if not found_date:
        return 0
    try:
        fd = datetime.strptime(found_date[:10], '%Y-%m-%d')
        if status in ('已解决','已关闭') and resolve_date:
            rd = datetime.strptime(resolve_date[:10], '%Y-%m-%d')
            return (rd - fd).days
        return (datetime.now() - fd).days
    except:
        return 0

@issues_bp.route('')
@login_required
def issues_page():
    return render_template('work_issues.html')

@issues_bp.route('/api/issues', methods=['GET'])
@login_required
def api_issues_list():
    conn = get_db()
    rows = conn.execute('''SELECT id, title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, photo, days_open,
        expected_resolve_date, assessed_at, improving_at,
        created_at, updated_at FROM issues ORDER BY id ASC''').fetchall()
    conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d['issue_id'] = 'ISS-{:06d}'.format(d['id'])
        if d['status'] not in ('已解决','已关闭'):
            d['days_open'] = _calc_days_open(d['found_date'], d['resolve_date'], d['status'])
        data.append(d)
    return jsonify({'success': True, 'data': data})

@issues_bp.route('/api/issues/<int:issue_id>', methods=['GET'])
@login_required
def api_issues_get(issue_id):
    conn = get_db()
    r = conn.execute('''SELECT id, title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, photo, days_open,
        created_at, updated_at FROM issues WHERE id=?''', (issue_id,)).fetchone()
    conn.close()
    if not r:
        return jsonify({'success': False, 'message': '不存在'}), 404
    d = dict(r)
    d['issue_id'] = 'ISS-{:06d}'.format(d['id'])
    return jsonify({'success': True, 'data': d})

@issues_bp.route('/api/issues', methods=['POST'])
@login_required
def api_issues_create():
    body = request.get_json(force=True)
    title = body.get('title',r['title']).strip()
    if not title:
        return jsonify({'success': False, 'message': '标题必填'})
    found_date = body.get('found_date',r['found_date'])
    resolve_date = body.get('resolve_date',r['resolve_date'])
    status = body.get('status','未解决')
    days_open = _calc_days_open(found_date, resolve_date, status)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO issues (title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, photo, days_open)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (title, body.get('detail',r['detail']), body.get('case_type',r['case_type']), body.get('reporter',r['reporter']),
         found_date, body.get('location',r['location']), int(body.get('is_common',r['is_common'])),
         body.get('priority',r['priority']), status, resolve_date, body.get('solution',r['solution']),
         body.get('impact',r['impact']), body.get('assignee',r['assignee']), body.get('photo',r['photo']), days_open))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id, 'issue_id': 'ISS-{:06d}'.format(new_id)})

@issues_bp.route('/api/issues/<int:issue_id>', methods=['PUT'])
@login_required
def api_issues_update(issue_id):
    body = request.get_json(force=True)
    conn = get_db()
    r = conn.execute('SELECT * FROM issues WHERE id=?', (issue_id,)).fetchone()
    if not r:
        conn.close()
        return jsonify({'success': False, 'message': '不存在'}), 404
    found_date = body.get('found_date',r['found_date'])
    resolve_date = body.get('resolve_date',r['resolve_date'])
    status = body.get('status','未解决')
    days_open = _calc_days_open(found_date, resolve_date, status)
    conn.execute('''UPDATE issues SET title=?, detail=?, case_type=?, reporter=?, found_date=?,
        location=?, is_common=?, priority=?, status=?, resolve_date=?, solution=?,
        impact=?, assignee=?, photo=?, days_open=?, updated_at=datetime('now','localtime')
        WHERE id=?''',
        (body.get('title',r['title']), body.get('detail',r['detail']), body.get('case_type',r['case_type']),
         body.get('reporter',r['reporter']), found_date, body.get('location',r['location']),
         int(body.get('is_common',r['is_common'])), body.get('priority',r['priority']), status, resolve_date,
         body.get('solution',r['solution']), body.get('impact',r['impact']), body.get('assignee',r['assignee']),
         body.get('photo',r['photo']), days_open, issue_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@issues_bp.route('/api/issues/<int:issue_id>', methods=['DELETE'])
@login_required
def api_issues_delete(issue_id):
    conn = get_db()
    conn.execute('DELETE FROM issues WHERE id=?', (issue_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@issues_bp.route('/api/issues/stats', methods=['GET'])
@login_required
def api_issues_stats():
    conn = get_db()
    status_rows = conn.execute('SELECT status, COUNT(*) as cnt FROM issues GROUP BY status').fetchall()
    prio_rows = conn.execute('''SELECT priority, COUNT(*) as cnt FROM issues
        WHERE status NOT IN ('已解决','已关闭') GROUP BY priority''').fetchall()
    type_rows = conn.execute('''SELECT case_type, COUNT(*) as cnt FROM issues
        WHERE status NOT IN ('已解决','已关闭') GROUP BY case_type''').fetchall()
    total = conn.execute('SELECT COUNT(*) FROM issues').fetchone()[0]
    open_cnt = conn.execute('''SELECT COUNT(*) FROM issues WHERE status NOT IN ('已解决','已关闭')''').fetchone()[0]
    avg_days = conn.execute('''SELECT AVG(days_open) FROM issues WHERE status IN ('已解决','已关闭') AND days_open > 0''').fetchone()[0]
    resolved_cnt = conn.execute("SELECT COUNT(*) FROM issues WHERE status='已解决'").fetchone()[0]
    nonissue_cnt = conn.execute("SELECT COUNT(*) FROM issues WHERE status='非问题'").fetchone()[0]
    completion_rate = round(resolved_cnt / total * 100, 1) if total > 0 else 0
    conn.close()
    return jsonify({
        'success': True,
        'data': {
            'by_status': {r['status']: r['cnt'] for r in status_rows},
            'by_priority_open': {r['priority']: r['cnt'] for r in prio_rows},
            'by_type_open': {r['case_type']: r['cnt'] for r in type_rows},
            'total': total,
            'open': open_cnt, 'resolved': resolved_cnt, 'nonissue': nonissue_cnt, 'completion_rate': completion_rate,
            'avg_resolve_days': round(avg_days, 1) if avg_days else 0
        }
    })

@issues_bp.route('/api/issues/export', methods=['GET'])
@login_required
def api_issues_export():
    conn = get_db()
    rows = conn.execute('''SELECT id, title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, days_open
        FROM issues ORDER BY id ASC''').fetchall()
    conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d['issue_id'] = 'ISS-{:06d}'.format(d['id'])
        d['is_common'] = '是' if d['is_common'] else '否'
        data.append(d)
    return jsonify({'success': True, 'data': data})
