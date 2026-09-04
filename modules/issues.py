#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P032 系统问题管理模块"""

import os, uuid
from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime, timedelta, date as _date
from init_db import get_db
import json

from modules.auth import login_required

issues_bp = Blueprint('issues', __name__, url_prefix='/issues')

STATUS_ORDER = ['未开始','评估中','改善中','已解决','非问题']
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
        expected_resolve_date, assessed_at, improving_at,
        attachments, resolve_attachments,
        need_sop, sop_task_id,
        created_at, updated_at FROM issues ORDER BY id ASC''').fetchall()
    data = []
    for r in rows:
        d = dict(r)
        d['issue_id'] = 'ISS-{:06d}'.format(d['id'])
        # Resolve SOP task_no from tasks table
        if d.get('sop_task_id'):
            t = conn.execute('SELECT task_no FROM tasks WHERE id=?', (d['sop_task_id'],)).fetchone()
            d['sop_task_no'] = t['task_no'] if t else ''
        else:
            d['sop_task_no'] = ''
        if d['status'] not in ('已解决','已关闭'):
            d['days_open'] = _calc_days_open(d['found_date'], d['resolve_date'], d['status'])
        data.append(d)
    conn.close()
    return jsonify({'success': True, 'data': data})

@issues_bp.route('/api/issues/<int:issue_id>', methods=['GET'])
@login_required
def api_issues_get(issue_id):
    conn = get_db()
    r = conn.execute('''SELECT id, title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, photo, days_open,
        expected_resolve_date, assessed_at, improving_at,
        attachments, resolve_attachments,
        need_sop, sop_task_id,
        created_at, updated_at FROM issues WHERE id=?''', (issue_id,)).fetchone()
    if not r:
        conn.close()
        return jsonify({'success': False, 'message': '不存在'}), 404
    d = dict(r)
    d['issue_id'] = 'ISS-{:06d}'.format(d['id'])
    if d.get('sop_task_id'):
        t = conn.execute('SELECT task_no FROM tasks WHERE id=?', (d['sop_task_id'],)).fetchone()
        d['sop_task_no'] = t['task_no'] if t else ''
    else:
        d['sop_task_no'] = ''
    conn.close()
    return jsonify({'success': True, 'data': d})

@issues_bp.route('/api/issues', methods=['POST'])
@login_required
def api_issues_create():
    body = request.get_json(force=True)
    title = body.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'message': '标题必填'})
    found_date = body.get('found_date', '')
    resolve_date = body.get('resolve_date', '')
    status = body.get('status', '未开始')
    days_open = _calc_days_open(found_date, resolve_date, status)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO issues (title, detail, case_type, reporter, found_date, location,
        is_common, priority, status, resolve_date, solution, impact, assignee, photo, days_open,
        expected_resolve_date, assessed_at, improving_at,
        attachments)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (title, body.get('detail',''), body.get('case_type',''), body.get('reporter',''),
         found_date, body.get('location',''), int(body.get('is_common',0)),
         body.get('priority','中'), status, resolve_date, body.get('solution',''),
         body.get('impact',''), body.get('assignee',''), body.get('photo',''), days_open,
         body.get('attachments','')))
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
    status = body.get('status','未开始')
    days_open = _calc_days_open(found_date, resolve_date, status)
    conn.execute('''UPDATE issues SET title=?, detail=?, case_type=?, reporter=?, found_date=?,
        location=?, is_common=?, priority=?, status=?, resolve_date=?, solution=?,
        impact=?, assignee=?, photo=?, days_open=?, expected_resolve_date=?,
        assessed_at=?, improving_at=?, attachments=?, resolve_attachments=?,
        need_sop=?, sop_task_id=?, updated_at=datetime('now','localtime')
        WHERE id=?''',
        (body.get('title',r['title']), body.get('detail',r['detail']), body.get('case_type',r['case_type']),
         body.get('reporter',r['reporter']), found_date, body.get('location',r['location']),
         int(body.get('is_common',r['is_common'])), body.get('priority',r['priority']), status, resolve_date,
         body.get('solution',r['solution']), body.get('impact',r['impact']), body.get('assignee',r['assignee']),
         body.get('photo',r['photo']), days_open,
         body.get('expected_resolve_date', r['expected_resolve_date'] or ''),
         body.get('assessed_at', r['assessed_at'] or ''),
         body.get('improving_at', r['improving_at'] or ''),
         body.get('attachments', r['attachments'] or ''),
         body.get('resolve_attachments', r['resolve_attachments'] or ''),
         body.get('need_sop', r['need_sop'] or ''),
         body.get('sop_task_id', r['sop_task_id']),
         issue_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})



def _gen_task_no(conn):
    """Generate task number: WK+yyyyMMdd-NNN"""
    today = datetime.now().strftime('%Y%m%d')
    prefix = 'WK' + today + '-'
    row = conn.execute(
        'SELECT task_no FROM tasks WHERE task_no LIKE ? ORDER BY task_no DESC LIMIT 1',
        (prefix + '%',)
    ).fetchone()
    if row and row['task_no']:
        seq = int(row['task_no'].split('-')[-1]) + 1
    else:
        seq = 1
    return prefix + str(seq).zfill(3)

@issues_bp.route('/api/issues/<int:issue_id>/create-sop-task', methods=['POST'])
@login_required
def api_issues_create_sop_task(issue_id):
    """为问题创建SOP任务，同步回写sop_task_id"""
    body = request.get_json()
    conn = get_db()
    try:
        issue = conn.execute('SELECT id, title, status, sop_task_id FROM issues WHERE id=?', (issue_id,)).fetchone()
        if not issue:
            conn.close()
            return jsonify({'success': False, 'message': '问题不存在'}), 404
        if issue['sop_task_id']:
            conn.close()
            return jsonify({'success': False, 'message': '该问题已关联SOP任务'}), 400

        task_no = _gen_task_no(conn)

        cur = conn.execute("""INSERT INTO tasks (title, executor_id, description, materials_json,
                              estimated_minutes, expected_end, status, created_by, task_no, start_time,
                              related_issue_id, is_sop)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.get('title', 'SOP: ' + (issue['title'] or '')),
             body.get('executor_id'),
             body.get('description', ''),
             body.get('materials_json', ''),
             body.get('estimated_minutes', 30),
             body.get('expected_end'),
             'pending',
             session.get('user_id'),
             task_no,
             body.get('start_time'),
             issue_id,
             1))
        task_id = cur.lastrowid

        try:
            from modules.work_mgmt import _book_task_instance
            _book_task_instance(task_id, conn, confirmed_slot=body.get('confirmed_slot'))
        except Exception:
            pass

        conn.execute('UPDATE issues SET sop_task_id=?, need_sop=?, updated_at=datetime("now","localtime") WHERE id=?',
                     (task_id, '是', issue_id))
        conn.commit()

        return jsonify({'success': True, 'task_id': task_id, 'task_no': task_no})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


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


UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'issue_attachments')
ALLOWED_EXT = {'png','jpg','jpeg','gif','bmp','webp','pdf','doc','docx','xls','xlsx','ppt','pptx','txt','csv','zip','rar'}

@issues_bp.route('/api/issues/upload', methods=['POST'])
@login_required
def api_issues_upload():
    """上传问题附件，图片自动压缩"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'success': False, 'message': 'Empty filename'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'success': False, 'message': f'Unsupported file type: {ext}'}), 400
    fname = f.filename
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    IMG_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    if ext in IMG_EXT:
        try:
            from PIL import Image
            img = Image.open(f.stream)
            # Convert RGBA/P to RGB for JPEG output
            original_mode = img.mode
            if original_mode in ('RGBA', 'P', 'LA', 'PA'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if original_mode == 'P':
                    img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            # Resize: max dimension 1200px
            max_dim = 1200
            w, h = img.size
            if max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            # Always save as JPEG for best compression
            unique_name = f"{uuid.uuid4().hex[:8]}.jpg"
            save_path = os.path.join(UPLOAD_FOLDER, unique_name)
            img.save(save_path, 'JPEG', quality=80, optimize=True)
        except Exception:
            # Fallback: save original if PIL fails
            f.stream.seek(0)
            unique_name = f"{uuid.uuid4().hex[:8]}.{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, unique_name)
            f.save(save_path)
    else:
        unique_name = f"{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, unique_name)
        f.save(save_path)

    url = f"/uploads/issue_attachments/{unique_name}"
    return jsonify({'success': True, 'url': url, 'filename': fname})


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
