#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P029 专项与周期工作管理模块"""

from flask import Blueprint, render_template, request, jsonify, session, send_from_directory
from datetime import datetime as _g_dt_now, timedelta as _g_td
from init_db import get_db
import json, os, uuid
from werkzeug.utils import secure_filename

work_mgmt_bp = Blueprint('work_mgmt', __name__, url_prefix='/work-mgmt')

# ============ 周期性工作管理 ============

@work_mgmt_bp.route('/recurring')
def recurring_page():
    return render_template('work_recurring.html', current_user_id=session.get('user_id'))


@work_mgmt_bp.route('/api/recurring', methods=['GET'])
def api_recurring_list():
    """获取周期性工作列表"""
    conn = get_db()
    try:
        type_filter = request.args.get('type', '')
        owner_filter = request.args.get('owner', '')
        executor_filter = request.args.get('executor', '')
        active_only = request.args.get('active_only', '0')
        
        sql = '''
            SELECT r.*, 
                   u1.display_name as owner_name,
                   u2.display_name as executor_name
            FROM recurring_tasks r
            LEFT JOIN users u1 ON r.owner_id = u1.id
            LEFT JOIN users u2 ON r.executor_id = u2.id
            WHERE 1=1
        '''
        params = []
        
        if type_filter:
            sql += ' AND r.type = ?'
            params.append(type_filter)
        if owner_filter:
            sql += ' AND r.owner_id = ?'
            params.append(owner_filter)
        if executor_filter:
            sql += ' AND r.executor_id = ?'
            params.append(executor_filter)
        cycle_type_filter = request.args.get('cycle_type', '')
        if cycle_type_filter:
            sql += ' AND r.cycle_type = ?'
            params.append(cycle_type_filter)
        if active_only == '1':
            sql += ' AND r.is_active = 1'
        
        sql += ' ORDER BY r.sort_order, r.id'
        
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'name': r['name'],
                'type': r['type'],
                'cycle_rule': r['cycle_rule'],
                'cycle_weekdays': r['cycle_weekdays'],
                'cycle_month_days': r['cycle_month_days'],
                'cycle_type': r['cycle_type'],
                'cycle_interval': r['cycle_interval'],
                'freq_per_month': r['freq_per_month'],
                'owner_id': r['owner_id'],
                'owner_name': r['owner_name'] or '',
                'executor_id': r['executor_id'],
                'executor_name': r['executor_name'] or '',
                'duration_minutes': r['duration_minutes'],
                'has_sop': r['has_sop'],
                'avg_monthly_hours': r['avg_monthly_hours'],
                'is_active': r['is_active'],
                'sort_order': r['sort_order'],
                'fixed_start_time': r['fixed_start_time'] or '',
                'split_pattern': r['split_pattern'] if 'split_pattern' in r.keys() else None
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring', methods=['POST'])
def api_recurring_create():
    """新增周期性工作"""
    data = request.get_json()
    conn = get_db()
    try:
        freq = _calc_freq_per_month(data.get('cycle_type', 'weekly'),
                                     data.get('cycle_weekdays', ''),
                                     data.get('cycle_month_days', ''),
                                     data.get('cycle_interval', 1),
                                     data.get('freq_per_month'))
        avg_hours = round(freq * data.get('duration_minutes', 0) / 60, 1)
        
        # Compute fixed_end_time from fixed_start_time + duration
        fst = data.get('fixed_start_time') or None
        fet = None
        if fst:
            try:
                from datetime import datetime as _dt_c, timedelta as _td_c
                st_c = _dt_c.strptime(fst, '%H:%M')
                dur_c = data.get('duration_minutes', 0) or 0
                if dur_c > 0:
                    fet = (st_c + _td_c(minutes=dur_c)).strftime('%H:%M')
            except:
                fst = None
        conn.execute('''
            INSERT INTO recurring_tasks 
            (name, type, cycle_rule, cycle_weekdays, cycle_month_days, 
             cycle_target_months, cycle_week_parity,
             cycle_type, cycle_interval, freq_per_month, 
             owner_id, executor_id, duration_minutes, has_sop, avg_monthly_hours, is_active,
             fixed_start_time, fixed_end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'], data.get('type', ''), data.get('cycle_rule', ''),
            data.get('cycle_weekdays', ''), data.get('cycle_month_days', ''),
            data.get('cycle_target_months', ''), data.get('cycle_week_parity', ''),
            data.get('cycle_type', 'weekly'), data.get('cycle_interval', 1),
            freq,
            data.get('owner_id'), data.get('executor_id'),
            data.get('duration_minutes', 0), data.get('has_sop', ''),
            avg_hours, 1,
            fst, fet
        ))
        new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        _book_recurring_instance(new_id, conn)
        conn.commit()
        return jsonify({'success': True, 'message': '新增成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/<int:task_id>', methods=['PUT'])
def api_recurring_update(task_id):
    """编辑周期性工作"""
    data = request.get_json()
    conn = get_db()
    try:
        freq = _calc_freq_per_month(data.get('cycle_type', 'weekly'),
                                     data.get('cycle_weekdays', ''),
                                     data.get('cycle_month_days', ''),
                                     data.get('cycle_interval', 1),
                                     data.get('freq_per_month'))
        avg_hours = round(freq * data.get('duration_minutes', 0) / 60, 1)
        
        # Compute fixed_end_time from fixed_start_time + duration
        fst = data.get('fixed_start_time') or None
        fet = None
        if fst:
            try:
                from datetime import datetime as _dt_u, timedelta as _td_u
                st_u = _dt_u.strptime(fst, '%H:%M')
                dur_u = data.get('duration_minutes', 0) or 0
                if dur_u > 0:
                    fet = (st_u + _td_u(minutes=dur_u)).strftime('%H:%M')
            except:
                fst = None
        conn.execute('''
            UPDATE recurring_tasks SET
                name=?, type=?, cycle_rule=?, cycle_weekdays=?, cycle_month_days=?,
                cycle_target_months=?, cycle_week_parity=?,
                cycle_type=?, cycle_interval=?, freq_per_month=?,
                owner_id=?, executor_id=?, duration_minutes=?, has_sop=?,
                avg_monthly_hours=?, is_active=?, updated_at=datetime('now','localtime'),
                fixed_start_time=?, fixed_end_time=?
            WHERE id=?
        ''', (
            data['name'], data.get('type', ''), data.get('cycle_rule', ''),
            data.get('cycle_weekdays', ''), data.get('cycle_month_days', ''),
            data.get('cycle_target_months', ''), data.get('cycle_week_parity', ''),
            data.get('cycle_type', 'weekly'), data.get('cycle_interval', 1),
            freq,
            data.get('owner_id'), data.get('executor_id'),
            data.get('duration_minutes', 0), data.get('has_sop', ''),
            avg_hours, data.get('is_active', 1), fst, fet, task_id
        ))
        _book_recurring_instance(task_id, conn)
        conn.commit()
        _resp = {'success': True, 'message': '更新成功'}
        return jsonify(_resp)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/<int:task_id>', methods=['DELETE'])
def api_recurring_delete(task_id):
    """删除周期性工作"""
    conn = get_db()
    try:
        conn.execute('DELETE FROM recurring_tasks WHERE id=?', (task_id,))
        conn.commit()
        return jsonify({'success': True, 'message': '删除成功'})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/import', methods=['POST'])
def api_recurring_import():
    """批量导入周期性工作"""
    data = request.get_json()
    items = data.get('items', [])
    conn = get_db()
    try:
        count = 0
        for item in items:
            freq = _calc_freq_per_month(
                item.get('cycle_type', 'weekly'),
                item.get('cycle_weekdays', ''),
                item.get('cycle_month_days', ''),
                item.get('cycle_interval', 1),
                item.get('freq_per_month')
            )
            avg_hours = round(freq * item.get('duration_minutes', 0) / 60, 1)
            
            conn.execute('''
                INSERT INTO recurring_tasks 
                (name, type, cycle_rule, cycle_weekdays, cycle_month_days,
                 cycle_target_months, cycle_week_parity,
                 cycle_type, cycle_interval, freq_per_month,
                 owner_id, executor_id, duration_minutes, has_sop, avg_monthly_hours, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['name'], item.get('type', ''), item.get('cycle_rule', ''),
                item.get('cycle_weekdays', ''), item.get('cycle_month_days', ''),
                item.get('cycle_target_months', ''), item.get('cycle_week_parity', ''),
                item.get('cycle_type', 'weekly'), item.get('cycle_interval', 1),
                freq,
                item.get('owner_id'), item.get('executor_id'),
                item.get('duration_minutes', 0), item.get('has_sop', ''),
                avg_hours, 1
            ))
            count += 1
        conn.commit()
        return jsonify({'success': True, 'message': f'成功导入{count}条'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/export', methods=['GET'])
def api_recurring_export():
    """导出周期性工作"""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT r.*, u1.display_name as owner_name, u2.display_name as executor_name
            FROM recurring_tasks r
            LEFT JOIN users u1 ON r.owner_id = u1.id
            LEFT JOIN users u2 ON r.executor_id = u2.id
            ORDER BY r.sort_order, r.id
        ''').fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'], 'name': r['name'], 'type': r['type'],
                'cycle_rule': r['cycle_rule'], 'cycle_target_months': r['cycle_target_months'] if 'cycle_target_months' in r.keys() else '', 'cycle_week_parity': r['cycle_week_parity'] if 'cycle_week_parity' in r.keys() else '', 'freq_per_month': r['freq_per_month'],
                'owner_name': r['owner_name'] or '', 'executor_name': r['executor_name'] or '',
                'duration_minutes': r['duration_minutes'], 'has_sop': r['has_sop'],
                'avg_monthly_hours': r['avg_monthly_hours'], 'is_active': r['is_active']
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/stats', methods=['GET'])
def api_recurring_stats():
    """月均工时统计"""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT r.executor_id, u.display_name as executor_name,
                   SUM(r.avg_monthly_hours) as total_hours,
                   COUNT(*) as task_count,
                   SUM(CASE WHEN r.is_active=1 THEN 1 ELSE 0 END) as active_count
            FROM recurring_tasks r
            LEFT JOIN users u ON r.executor_id = u.id
            WHERE r.is_active = 1
            GROUP BY r.executor_id
            ORDER BY u.display_name
        ''').fetchall()
        result = []
        for r in rows:
            result.append({
                'executor_id': r['executor_id'], 'executor_name': r['executor_name'] or '',
                'total_hours': round(r['total_hours'] or 0, 1),
                'task_count': r['task_count'],
                'active_count': r['active_count']
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()


# ============ 任务管理 ============


def _gen_task_no(conn):
    """Generate task number: WK+yyyyMMdd-NNN"""
    from datetime import datetime
    today = _g_dt_now.now().strftime('%Y%m%d')
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

@work_mgmt_bp.route('/tasks')
def tasks_page():
    return render_template("work_tasks.html", current_user_id=session.get("user_id"))


@work_mgmt_bp.route('/api/tasks', methods=['GET'])
def api_tasks_list():
    conn = get_db()
    try:
        executor_filter = request.args.get('executor', '')
        status_filter = request.args.get('status', '')
        sql = 'SELECT t.*, u.display_name as executor_name, u2.display_name as creator_name FROM tasks t LEFT JOIN users u ON t.executor_id = u.id LEFT JOIN users u2 ON t.created_by = u2.id WHERE 1=1'
        params = []
        if executor_filter:
            sql += ' AND t.executor_id = ?'
            params.append(executor_filter)
        if status_filter:
            sql += ' AND t.status = ?'
            params.append(status_filter)
        sql += ' ORDER BY t.expected_end, t.id DESC'
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'], 'title': r['title'],
                'executor_id': r['executor_id'], 'executor_name': r['executor_name'] or '',
                'description': r['description'], 'estimated_minutes': r['estimated_minutes'],
                'expected_end': r['expected_end'], 'status': r['status'],
                'completed_at': r['completed_at'],
                'submitted_at': r['submitted_at'],
                'created_by_ai': r['created_by_ai'], 'raw_input': r['raw_input'],
                'created_by': r['created_by'], 'creator_name': r['creator_name'] or '' if r['creator_name'] else '',
                'created_at': r['created_at'],
                'result_text': r['result_text'] or '',
                'started_at': r['started_at'],
                'start_time': r['start_time'] if 'start_time' in r.keys() else None,
                'task_no': r['task_no'] or '',
                'reject_count': r['reject_count'] or 0,
                'last_reject_reason': r['last_reject_reason'] or '',
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/tasks/no/<task_no>', methods=['PUT'])
def api_tasks_update_by_no(task_no):
    """Update task by task_no (工单号) instead of database id"""
    row = get_db().execute('SELECT id FROM tasks WHERE task_no=?', (task_no,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': f'工单号 {task_no} 不存在'}), 404
    # Delegate to the existing update function with the resolved id
    request.view_args['task_id'] = row['id']
    return api_tasks_update(row['id'])



@work_mgmt_bp.route('/api/tasks/validate-schedule', methods=['POST'])
def api_tasks_validate_schedule():
    """Validate task schedule before creation. Returns conflict info and suggested slots."""
    data = request.get_json()
    executor_id = data.get('executor_id')
    expected_end = data.get('expected_end')
    estimated_minutes = data.get('estimated_minutes', 30)
    if not executor_id or not expected_end:
        return jsonify({'success': False, 'message': '缺少执行人或截止时间'}), 400
    conn = get_db()
    try:
        result = _find_task_slot(executor_id, expected_end, estimated_minutes, conn)
        return jsonify({'success': True, 'validation': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()

@work_mgmt_bp.route('/api/tasks', methods=['POST'])
def api_tasks_create():
    data = request.get_json()
    conn = get_db()
    try:
        cur = conn.execute('''
            INSERT INTO tasks (title, executor_id, description, materials_json,
                              estimated_minutes, expected_end, status, created_by, task_no, start_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['title'], data.get('executor_id'), data.get('description', ''),
            data.get('materials_json', ''), data.get('estimated_minutes', 0),
            data.get('expected_end'), 'pending', session.get('user_id'), _gen_task_no(conn),
            data.get('start_time')
        ))
        task_id = cur.lastrowid
        _book_task_instance(task_id, conn, confirmed_slot=data.get('confirmed_slot'))
        conn.commit()
        return jsonify({'success': True, 'message': '任务创建成功', 'id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_tasks_update(task_id):
    data = request.get_json()
    conn = get_db()
    try:
        if data.get('action') == 'start':
            _tst = conn.execute('SELECT start_time FROM tasks WHERE id=?', (task_id,)).fetchone()
            _st_val = _tst['start_time'] if _tst and _tst['start_time'] else None
            if _st_val:
                conn.execute('''UPDATE tasks SET status='in_progress', started_at=?,
                                updated_at=datetime('now','localtime') WHERE id=?''', (_st_val, task_id))
            else:
                conn.execute('''UPDATE tasks SET status='in_progress', started_at=datetime('now','localtime'),
                                updated_at=datetime('now','localtime') WHERE id=?''', (task_id,))
            conn.execute("UPDATE calendar_instances SET status='in_progress', updated_at=datetime('now','localtime') WHERE source_type='task' AND source_id=?", (task_id,))
        elif data.get('action') == 'complete':
            conn.execute('''
                UPDATE tasks SET status='completed', completed_at=datetime('now','localtime'),
                                result_text=?, updated_at=datetime('now','localtime') WHERE id=?
            ''', (data.get('result_text', ''), task_id))
            conn.execute('''
                UPDATE calendar_instances SET completed_at=datetime('now','localtime'), status='completed'
                WHERE source_type='task' AND source_id=?
            ''', (task_id,))
        elif data.get('action') == 'submit_review':
            result_text = data.get('result_text', '')
            attach_rows = conn.execute(
                'SELECT id, filename, filepath, file_type, file_size FROM task_attachments WHERE task_id=? AND attach_type=? ORDER BY id',
                (task_id, 'result')
            ).fetchall()
            attach_snap = json.dumps([dict(r) for r in attach_rows], ensure_ascii=False) if attach_rows else ''
            conn.execute('''
                UPDATE tasks SET status='pending_review',
                                submitted_at=datetime('now','localtime'),
                                result_text=?,
                                pending_result_snapshot=?,
                                pending_attach_snapshot=?,
                                updated_at=datetime('now','localtime') WHERE id=?
            ''', (result_text, result_text, attach_snap, task_id))
            conn.execute("UPDATE calendar_instances SET status='pending_review', updated_at=datetime('now','localtime') WHERE source_type='task' AND source_id=?", (task_id,))
        elif data.get('action') == 'approve':
            conn.execute('''
                UPDATE tasks SET status='completed', completed_at=datetime('now','localtime'),
                                updated_at=datetime('now','localtime') WHERE id=?
            ''', (task_id,))
            conn.execute('''
                UPDATE calendar_instances SET completed_at=datetime('now','localtime'), status='completed'
                WHERE source_type='task' AND source_id=?
            ''', (task_id,))
        elif data.get('action') == 'reject':
            reason = data.get('reason', '')
            conn.execute('''
                UPDATE tasks SET status='in_progress',
                                reject_count=COALESCE(reject_count,0)+1,
                                last_reject_reason=?,
                                updated_at=datetime('now','localtime') WHERE id=?
            ''', (reason, task_id))
            # read snapshot from submission time (not current result_text)
            snap_row = conn.execute('SELECT pending_result_snapshot, pending_attach_snapshot, submitted_at FROM tasks WHERE id=?', (task_id,)).fetchone()
            result_snapshot = (snap_row['pending_result_snapshot'] or '') if snap_row else ''
            attach_snapshot = (snap_row['pending_attach_snapshot'] or '') if snap_row else ''
            submitted_snapshot = snap_row['submitted_at'] if snap_row else ''
            conn.execute('''
                INSERT INTO task_rejection_logs (task_id, reason, rejected_by, rejected_at, result_snapshot, submitted_at_snapshot, attach_snapshot)
                VALUES (?, ?, ?, datetime('now','localtime'), ?, ?, ?)
            ''', (task_id, reason, session.get('user_id'), result_snapshot, submitted_snapshot, attach_snapshot))
            # clear result attachments (already snapshotted above, user will re-upload if needed)
            conn.execute('DELETE FROM task_attachments WHERE task_id=? AND attach_type=?', (task_id, 'result'))
        elif data.get('action') == 'feedback':
            conn.execute('''
                UPDATE tasks SET result_text=?, updated_at=datetime('now','localtime') WHERE id=?
            ''', (data.get('result_text', ''), task_id))
        else:
            # Partial update: only set fields that are provided
            sets = []
            vals = []
            for k, v in [('title', data.get('title')), ('executor_id', data.get('executor_id')),
                         ('description', data.get('description')), ('estimated_minutes', data.get('estimated_minutes')),
                         ('expected_end', data.get('expected_end')), ('status', data.get('status')),
                         ('start_time', data.get('start_time'))]:
                if v is not None:
                    sets.append(f'{k}=?')
                    vals.append(v)
            if sets:
                sets.append("updated_at=datetime('now','localtime')")
                conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals + [task_id])
        _book_task_instance(task_id, conn, confirmed_slot=data.get('confirmed_slot'))
        conn.commit()
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_tasks_delete(task_id):
    conn = get_db()
    try:
        conn.execute('DELETE FROM calendar_instances WHERE source_type=? AND source_id=?', ('task', task_id))
        conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        conn.commit()
        return jsonify({'success': True, 'message': '删除成功'})
    finally:
        conn.close()



# ============ 任务附件 ============


# ============ 审批历史 ============

@work_mgmt_bp.route('/api/tasks/<int:task_id>/rejection-logs', methods=['GET'])
def api_rejection_logs(task_id):
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT r.*, u.display_name as rejected_by_name
            FROM task_rejection_logs r
            LEFT JOIN users u ON r.rejected_by = u.id
            WHERE r.task_id=?
            ORDER BY r.id
        ''', (task_id,)).fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'reason': r['reason'] or '',
                'rejected_by_name': r['rejected_by_name'] or '',
                'rejected_at': r['rejected_at'],
                'result_snapshot': r['result_snapshot'] or '',
                'submitted_at_snapshot': r['submitted_at_snapshot'] or '',
                'attach_snapshot': r['attach_snapshot'] or '',
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'task_attachments')
ALLOWED_EXT = {'png','jpg','jpeg','gif','bmp','webp','pdf','doc','docx','xls','xlsx','ppt','pptx','txt','csv','zip','rar'}

@work_mgmt_bp.route('/api/tasks/<int:task_id>/attachments', methods=['GET'])
def api_task_attachments_list(task_id):
    conn = get_db()
    try:
        rows = conn.execute('SELECT * FROM task_attachments WHERE task_id=? ORDER BY id', (task_id,)).fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'], 'task_id': r['task_id'],
                'filename': r['filename'], 'filepath': r['filepath'],
                'file_type': r['file_type'], 'file_size': r['file_size'],
                'created_at': r['created_at'], 'attach_type': r['attach_type'] or 'material',
            })
        return jsonify({'success': True, 'data': result})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/tasks/<int:task_id>/attachments', methods=['POST'])
def api_task_attachments_upload(task_id):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'success': False, 'message': 'Empty filename'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'success': False, 'message': f'Unsupported file type: {ext}'}), 400
    fname = secure_filename(f.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{fname}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    conn = get_db()
    try:
        cur = conn.execute(
            'INSERT INTO task_attachments (task_id, filename, filepath, file_type, file_size, attach_type) VALUES (?,?,?,?,?,?)',
            (task_id, fname, f'task_attachments/{unique_name}', ext, file_size, request.form.get('attach_type', 'material'))
        )
        conn.commit()
        return jsonify({'success': True, 'id': cur.lastrowid, 'filename': fname, 'filepath': f'task_attachments/{unique_name}', 'file_size': file_size})
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/attachments/<int:att_id>', methods=['DELETE'])
def api_task_attachments_delete(att_id):
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM task_attachments WHERE id=?', (att_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Not found'}), 404
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', row['filepath'])
        conn.execute('DELETE FROM task_attachments WHERE id=?', (att_id,))
        conn.commit()
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': True, 'message': 'Deleted'})
    finally:
        conn.close()


# ============ 日程管理 ============

@work_mgmt_bp.route('/calendar')
def calendar_page():
    return render_template('work_calendar.html')


@work_mgmt_bp.route('/api/calendar', methods=['GET'])
def api_calendar_events():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    executor_id = request.args.get('executor', '')
    conn = get_db()
    try:
        sql = '''SELECT c.*, u.display_name as executor_name
                 FROM calendar_instances c LEFT JOIN users u ON c.executor_id = u.id
                 WHERE c.date >= ? AND c.date <= ?'''
        params = [start, end]
        if executor_id:
            sql += ' AND c.executor_id = ?'
            params.append(executor_id)
        sql += ' ORDER BY c.date, c.start_time'
        rows = conn.execute(sql, params).fetchall()
        events = []
        for r in rows:
            evt = {
                'id': r['id'], 'title': '',
                'start': f"{r['date']}T{r['start_time']}" if r['start_time'] else r['date'],
                'end': f"{r['date']}T{r['end_time']}" if r['end_time'] else None,
                'resourceId': str(r['executor_id']) if r['executor_id'] else None,
                'extendedProps': {
                    'source_type': r['source_type'], 'source_id': r['source_id'],
                    'status': r['status'], 'executor_name': r['executor_name'] or '',
                    'transfer_to_id': r['transfer_to_id'], 'completed_at': r['completed_at'],
                    'is_overtime': r['is_overtime'] if 'is_overtime' in r.keys() else 0,
                    'time_locked': r['time_locked'] if 'time_locked' in r.keys() else 0,
                    'split_index': r['split_index'] if 'split_index' in r.keys() else 1,
                    'split_total': r['split_total'] if 'split_total' in r.keys() else 1
                }
            }
            if r['source_type'] == 'recurring' and r['source_id']:
                rec = conn.execute('SELECT name, fixed_start_time FROM recurring_tasks WHERE id=?', (r['source_id'],)).fetchone()
                evt['title'] = (rec['name'] if rec else '周期性工作') + (f" [{r['split_index']}/{r['split_total']}片]" if 'split_total' in r.keys() and r['split_total'] > 1 else '')
                evt['extendedProps']['has_fixed_time'] = bool(rec and rec['fixed_start_time']) if rec else False
            elif r['source_type'] == 'task' and r['source_id']:
                task = conn.execute('SELECT title, status FROM tasks WHERE id=?', (r['source_id'],)).fetchone()
                evt['title'] = ('✔ ' if r['completed_at'] else '') + (task['title'] if task else '一次性任务')
                if task and task['status']: evt['extendedProps']['status'] = task['status']
            if r['status'] == 'leave':
                evt['backgroundColor'] = '#ccc'; evt['borderColor'] = '#ccc'; evt['textColor'] = '#666'
            elif r['status'] == 'transferred':
                evt['backgroundColor'] = '#ffcccc'; evt['borderColor'] = '#cc0000'
            elif r['completed_at']:
                evt['backgroundColor'] = '#d5f5e3'; evt['borderColor'] = '#2D6A3E'
            is_ot = r['is_overtime'] if 'is_overtime' in r.keys() else 0
            if is_ot:
                evt['borderColor'] = '#E6A23C'
                if not r['completed_at'] and r['status'] != 'leave':
                    evt['backgroundColor'] = '#FFF3E0'
            events.append(evt)
        return jsonify(events)
    finally:
        conn.close()


@work_mgmt_bp.route('/api/calendar/<int:instance_id>', methods=['PUT'])
def api_calendar_update(instance_id):
    data = request.get_json()
    conn = get_db()
    _overlap_warn = None
    try:
        if data.get('action') == 'move':
            # Overlap check: warn if new slot overlaps existing instances for same executor
            _mv_eid = data.get('executor_id')
            if not _mv_eid:
                _mv_inst = conn.execute('SELECT executor_id FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
                if _mv_inst: _mv_eid = _mv_inst['executor_id']
            _overlap_warn = None
            if _mv_eid and data.get('start_time') and data.get('end_time'):
                _ov = conn.execute(
                    "SELECT c.start_time, c.end_time, r.name FROM calendar_instances c LEFT JOIN recurring_tasks r ON c.source_type='recurring' AND c.source_id=r.id WHERE c.executor_id=? AND c.date=? AND c.status != 'leave' AND c.start_time < ? AND c.end_time > ? AND c.id != ?",
                    (_mv_eid, data['date'], data.get('end_time'), data.get('start_time'), instance_id)).fetchone()
                if _ov:
                    _overlap_warn = '与 %s(%s-%s) 时间重叠' % (_ov['name'] or '其他工作', _ov['start_time'], _ov['end_time'])
            conn.execute('''UPDATE calendar_instances SET date=?, start_time=?, end_time=?,
                            is_overtime=?, updated_at=datetime('now','localtime') WHERE id=?''',
                         (data['date'], data.get('start_time'), data.get('end_time'),
                          data.get('is_overtime', 0), instance_id))
            inst = conn.execute('SELECT * FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
            if inst and inst['source_type'] == 'recurring' and inst['source_id']:
                _st = inst['split_total'] if 'split_total' in inst.keys() else 1
                tl = inst['time_locked'] if 'time_locked' in inst.keys() else 0
                if not tl:
                    conn.execute('UPDATE calendar_instances SET time_locked=1 WHERE id=?', (instance_id,))
                scope = data.get('scope', 'longterm')
                if scope == 'longterm':
                    new_start = data.get('start_time')
                    if _st <= 1 and new_start:
                        rec = conn.execute('SELECT duration_minutes FROM recurring_tasks WHERE id=?', (inst['source_id'],)).fetchone()
                        dur = rec['duration_minutes'] if rec and rec['duration_minutes'] else 30
                        from datetime import datetime as _dt_mv, timedelta as _td_mv
                        st = _dt_mv.strptime(new_start, '%H:%M')
                        et = st + _td_mv(minutes=dur)
                        conn.execute("UPDATE recurring_tasks SET fixed_start_time=?, fixed_end_time=?, updated_at=datetime('now','localtime') WHERE id=?",
                                     (new_start, et.strftime('%H:%M'), inst['source_id']))
                        today_str = _g_dt_now.now().strftime('%Y-%m-%d')
                        future = conn.execute(
                            "SELECT id, executor_id, date FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND date >= ? AND id != ?",
                            (inst['source_id'], today_str, instance_id)).fetchall()
                        for fi in future:
                            conflict = conn.execute(
                                "SELECT 1 FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' AND start_time < ? AND end_time > ? AND id != ?",
                                (fi['executor_id'], fi['date'], et.strftime('%H:%M'), new_start, fi['id'])).fetchone()
                            if not conflict:
                                is_ot_f = 1 if et > _dt_mv.strptime('18:30', '%H:%M') else 0
                                conn.execute("UPDATE calendar_instances SET start_time=?, end_time=?, is_overtime=?, time_locked=1, updated_at=datetime('now','localtime') WHERE id=?",
                                             (new_start, et.strftime('%H:%M'), is_ot_f, fi['id']))
                    elif _st > 1:
                        _auto_save_split_pattern(inst, conn)
                executor = inst['executor_id'] if 'executor_id' in inst.keys() else None
                if not executor:
                    eo = conn.execute('SELECT executor_id FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
                    if eo: executor = eo['executor_id']
                # Compact removed from auto-move; only via manual compact button
            # Sync task start_time if set (calendar drag/auto-schedule → task management)
            if inst and inst['source_type'] == 'task' and inst['source_id']:
                _tsk = conn.execute('SELECT start_time FROM tasks WHERE id=?', (inst['source_id'],)).fetchone()
                if _tsk and _tsk['start_time']:
                    _new_st = data['date'] + ' ' + (data.get('start_time') or '')
                    _new_et = data['date'] + ' ' + (data.get('end_time') or '')
                    conn.execute('UPDATE tasks SET start_time=?, expected_end=?, updated_at=datetime("now","localtime") WHERE id=?',
                                 (_new_st, _new_et, inst['source_id']))
        elif data.get('action') == 'leave':
            conn.execute('''UPDATE calendar_instances SET status='leave', transfer_to_id=?,
                            updated_at=datetime('now','localtime') WHERE id=?''',
                         (data.get('transfer_to_id'), instance_id))
        elif data.get('action') == 'complete':
            inst = conn.execute('SELECT source_type, source_id FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
            if inst and inst['source_type'] == 'task' and inst['source_id']:
                t = conn.execute('SELECT status FROM tasks WHERE id=?', (inst['source_id'],)).fetchone()
                if t and t['status'] == 'pending':
                    _tst2 = conn.execute('SELECT start_time FROM tasks WHERE id=?', (inst['source_id'],)).fetchone()
                    _st2 = _tst2['start_time'] if _tst2 and _tst2['start_time'] else None
                    if _st2:
                        conn.execute("UPDATE tasks SET status='in_progress', started_at=?, updated_at=datetime('now','localtime') WHERE id=?", (_st2, inst['source_id']))
                    else:
                        conn.execute("UPDATE tasks SET status='in_progress', started_at=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?", (inst['source_id'],))
                    conn.execute("UPDATE calendar_instances SET status='in_progress', updated_at=datetime('now','localtime') WHERE id=?", (instance_id,))
                elif t and t['status'] == 'in_progress':
                    conn.execute("UPDATE tasks SET status='pending_review', submitted_at=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?", (inst['source_id'],))
                    conn.execute("UPDATE calendar_instances SET status='pending_review', updated_at=datetime('now','localtime') WHERE id=?", (instance_id,))
                elif t and t['status'] == 'pending_review':
                    conn.execute("UPDATE tasks SET status='completed', completed_at=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?", (inst['source_id'],))
                    conn.execute("UPDATE calendar_instances SET completed_at=datetime('now','localtime'), status='completed', updated_at=datetime('now','localtime') WHERE id=?", (instance_id,))
            else:
                conn.execute(
                    "UPDATE calendar_instances SET completed_at=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?",
                    (instance_id,))
        else:
            conn.execute('''UPDATE calendar_instances SET start_time=?, end_time=?, priority=?,
                            is_overtime=?, updated_at=datetime('now','localtime') WHERE id=?''',
                         (data.get('start_time'), data.get('end_time'), data.get('priority', 0),
                          data.get('is_overtime', 0), instance_id))
        conn.commit()
        _resp = {'success': True, 'message': '更新成功'}
        if _overlap_warn: _resp['warning'] = _overlap_warn
        return jsonify(_resp)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/leaves', methods=['POST'])


@work_mgmt_bp.route('/api/calendar/generate', methods=['POST'])
def api_calendar_generate():
    data = request.get_json() or {}
    start_date = data.get('start_date', '')
    end_date = data.get('end_date', '')
    executor_id = data.get('executor_id')
    if not start_date or not end_date:
        today = _g_dt_now.now().strftime('%Y-%m-%d')
        end = (_g_dt_now.now() + _g_td(days=14)).strftime('%Y-%m-%d')
        start_date = start_date or today
        end_date = end_date or end
    result = _generate_instances(start_date, end_date, executor_id)
    return jsonify({'success': True, 'data': result})



@work_mgmt_bp.route('/api/calendar/lock/<int:instance_id>', methods=['POST'])
def api_calendar_lock(instance_id):
    """Lock a calendar instance's time slot. Write back fixed_start_time to recurring_tasks.
    Unlock clears the fixed_start_time."""
    conn = get_db()
    try:
        inst = conn.execute('SELECT * FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
        if not inst:
            return jsonify({'success': False, 'message': 'Instance not found'}), 404
        lock = request.get_json() or {}
        locked = lock.get('locked', True)
        conn.execute("UPDATE calendar_instances SET time_locked=?, updated_at=datetime('now','localtime') WHERE id=?",
                     (1 if locked else 0, instance_id))
        # Write back to recurring_tasks.fixed_start_time (only non-split)
        _st = inst['split_total'] if 'split_total' in inst.keys() else 1
        if inst['source_type'] == 'recurring' and inst['source_id']:
            if _st > 1 and locked:
                _auto_save_split_pattern(inst, conn)
            elif locked and inst['start_time']:
                # Compute fixed_end_time from start_time + duration
                rec = conn.execute('SELECT duration_minutes FROM recurring_tasks WHERE id=?', (inst['source_id'],)).fetchone()
                dur = rec['duration_minutes'] if rec and rec['duration_minutes'] else 30
                from datetime import datetime as _dt_lock, timedelta as _td_lock
                st = _dt_lock.strptime(inst['start_time'], '%H:%M')
                et = st + _td_lock(minutes=dur)
                conn.execute("UPDATE recurring_tasks SET fixed_start_time=?, fixed_end_time=?, updated_at=datetime('now','localtime') WHERE id=?",
                             (inst['start_time'], et.strftime('%H:%M'), inst['source_id']))
                # Sync fixed time to all future un-locked instances of this recurring task
                new_st = inst['start_time']
                new_et = et.strftime('%H:%M')
                today_str = _dt_lock.now().strftime('%Y-%m-%d')
                future = conn.execute(
                    "SELECT id, date, executor_id FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND date >= ? AND id != ?",
                    (inst['source_id'], today_str, instance_id)).fetchall()
                synced = 0
                for fi in future:
                    # Check if the fixed time slot is free on this date (excluding self)
                    conflict = conn.execute(
                        "SELECT 1 FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' AND start_time < ? AND end_time > ? AND id != ?",
                        (fi['executor_id'], fi['date'], new_et, new_st, fi['id'])).fetchone()
                    if not conflict:
                        is_ot = 1 if _dt_lock.strptime(new_et, '%H:%M') > _dt_lock.strptime('18:30', '%H:%M') else 0
                        conn.execute(
                            "UPDATE calendar_instances SET start_time=?, end_time=?, is_overtime=?, time_locked=1, updated_at=datetime('now','localtime') WHERE id=?",
                            (new_st, new_et, is_ot, fi['id']))
                        synced += 1
            elif _st <= 1:
                conn.execute("UPDATE recurring_tasks SET fixed_start_time=NULL, fixed_end_time=NULL, updated_at=datetime('now','localtime') WHERE id=?",
                             (inst['source_id'],))
                # Unlock: clear time_locked on future instances that were auto-locked by sync
                today_str = _g_dt_now.now().strftime('%Y-%m-%d')
                conn.execute(
                    "UPDATE calendar_instances SET time_locked=0, updated_at=datetime('now','localtime') WHERE source_type='recurring' AND source_id=? AND time_locked=1 AND date >= ? AND id != ?",
                    (inst['source_id'], today_str, instance_id))
        conn.commit()
        return jsonify({'success': True, 'message': '已锁定，固定时间已同步' if locked else '已解锁，固定时间已清除'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()

def api_leave_create():
    data = request.get_json()
    conn = get_db()
    try:
        conn.execute('INSERT INTO leaves (staff_id, date, transfer_instructions) VALUES (?, ?, ?)',
                     (data['staff_id'], data['date'], data.get('instructions', '')))
        conn.execute('''UPDATE calendar_instances SET status='leave', updated_at=datetime('now','localtime')
                        WHERE executor_id=? AND date=? AND source_type='recurring' AND status='normal' ''',
                     (data['staff_id'], data['date']))
        conn.commit()
        return jsonify({'success': True, 'message': '请假已登记'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()




@work_mgmt_bp.route('/api/calendar/split/<int:instance_id>', methods=['POST'])
def api_calendar_split(instance_id):
    """Split a recurring instance into multiple pieces."""
    data = request.get_json() or {}
    pieces = data.get('pieces', 2)
    if pieces < 2 or pieces > 10:
        return jsonify({'success': False, 'message': '拆分片数须在2~10之间'}), 400
    conn = get_db()
    try:
        inst = conn.execute('SELECT * FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
        if not inst or inst['source_type'] != 'recurring':
            return jsonify({'success': False, 'message': '只能拆分周期性工作实例'}), 400
        _st = inst['split_total'] if 'split_total' in inst.keys() else 1
        if _st > 1:
            return jsonify({'success': False, 'message': '该实例已被拆分'}), 400
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (inst['source_id'],)).fetchone()
        if not rec:
            return jsonify({'success': False, 'message': '周期性工作不存在'}), 404
        total_dur = rec['duration_minutes'] or 30
        durations = data.get('durations')
        if durations:
            if len(durations) != pieces or sum(durations) != total_dur:
                return jsonify({'success': False, 'message': '各片工时之和须等于总工时{}分钟'.format(total_dur)}), 400
        else:
            base = total_dur // pieces
            durations = [base] * pieces
            durations[-1] += total_dur - base * pieces
        from datetime import datetime as _dt_s, timedelta as _td_s
        st_time = _dt_s.strptime(inst['start_time'], '%H:%M')
        current_date = inst['date']
        new_ids = []
        for i in range(pieces):
            piece_start = st_time.strftime('%H:%M')
            piece_end_time = st_time + _td_s(minutes=durations[i])
            piece_end = piece_end_time.strftime('%H:%M')
            is_ot = 1 if piece_end_time > _dt_s.strptime('18:30', '%H:%M') else 0
            if i == 0:
                conn.execute(
                    "UPDATE calendar_instances SET end_time=?, split_index=1, split_total=?, is_overtime=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (piece_end, pieces, is_ot, instance_id))
                new_ids.append(instance_id)
            else:
                nd = current_date
                for _ in range(i):
                    nw = _next_workday(nd)
                    if not nw:
                        return jsonify({'success': False, 'message': '无法找到足够的工作日'}), 400
                    nd = nw
                slot = _next_available_slot(inst['executor_id'], nd, durations[i], conn)
                if not slot:
                    for _ in range(3):
                        nw = _next_workday(nd)
                        if not nw: break
                        nd = nw
                        slot = _next_available_slot(inst['executor_id'], nd, durations[i], conn)
                        if slot: break
                if not slot:
                    return jsonify({'success': False, 'message': '第{}片无法找到可用时段'.format(i+1)}), 400
                cur = conn.execute(
                    "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, split_index, split_total) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, ?, ?)",
                    ('recurring', inst['source_id'], inst['executor_id'], nd, slot[0], slot[1], slot[2], i+1, pieces))
                new_ids.append(cur.lastrowid)
            st_time = piece_end_time
        conn.commit()
        return jsonify({'success': True, 'message': '已拆分为{}片'.format(pieces), 'new_ids': new_ids})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/calendar/re-split/<int:instance_id>', methods=['POST'])
def api_calendar_resplit(instance_id):
    """Re-split an already-split instance group with new parameters."""
    data = request.get_json() or {}
    pieces = data.get('pieces', 2)
    if pieces < 2 or pieces > 10:
        return jsonify({'success': False, 'message': '拆分片数须在2~10之间'}), 400
    conn = get_db()
    try:
        inst = conn.execute('SELECT * FROM calendar_instances WHERE id=?', (instance_id,)).fetchone()
        if not inst or inst['source_type'] != 'recurring':
            return jsonify({'success': False, 'message': '只能编辑周期性工作的拆分'}), 400
        _st = inst['split_total'] if 'split_total' in inst.keys() else 1
        if _st <= 1:
            return jsonify({'success': False, 'message': '该实例未拆分，请使用拆分功能'}), 400
        recurring_id = inst['source_id']
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (recurring_id,)).fetchone()
        if not rec:
            return jsonify({'success': False, 'message': '周期性工作不存在'}), 404

        # Find all pieces in the same period
        inst_date = inst['date']
        if rec['cycle_type'] in ('weekly', 'biweekly'):
            from datetime import datetime as _dt_rs, timedelta as _td_rs
            dt_obj = _dt_rs.strptime(inst_date, '%Y-%m-%d')
            iso = dt_obj.isocalendar()
            week_start = (dt_obj - _td_rs(days=iso[2]-1)).strftime('%Y-%m-%d')
            week_end = (dt_obj + _td_rs(days=7-iso[2])).strftime('%Y-%m-%d')
            all_pieces = conn.execute(
                "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 AND date >= ? AND date <= ?",
                (recurring_id, week_start, week_end)).fetchall()
        else:
            import calendar as _cal_rs
            month_start = inst_date[:7] + '-01'
            y, m = int(inst_date[:4]), int(inst_date[5:7])
            month_end = "{}-{}".format(inst_date[:7], _cal_rs.monthrange(y, m)[1])
            all_pieces = conn.execute(
                "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 AND date >= ? AND date <= ?",
                (recurring_id, month_start, month_end)).fetchall()

        # Check no piece is locked
        for p in all_pieces:
            if p['time_locked'] if 'time_locked' in p.keys() else 0:
                return jsonify({'success': False, 'message': '请先解锁该周期所有分片再重新拆分'}), 400

        # Delete all old pieces in this period
        piece_ids = [p['id'] for p in all_pieces]
        if piece_ids:
            placeholders = ','.join(['?'] * len(piece_ids))
            conn.execute(f"DELETE FROM calendar_instances WHERE id IN ({placeholders})", piece_ids)

        # Create new split from first piece's date as anchor
        total_dur = rec['duration_minutes'] or 30
        durations = data.get('durations')
        if durations:
            if len(durations) != pieces or sum(durations) != total_dur:
                return jsonify({'success': False, 'message': '各片工时之和须等于总工时{}分钟'.format(total_dur)}), 400
        else:
            base = total_dur // pieces
            durations = [base] * pieces
            durations[-1] += total_dur - base * pieces

        anchor_date = all_pieces[0]['date'] if all_pieces else inst_date
        anchor_start = all_pieces[0]['start_time'] if all_pieces else inst['start_time']
        from datetime import datetime as _dt_rsp, timedelta as _td_rsp
        st_time = _dt_rsp.strptime(anchor_start, '%H:%M')
        new_ids = []
        for i in range(pieces):
            piece_start = st_time.strftime('%H:%M')
            piece_end_time = st_time + _td_rsp(minutes=durations[i])
            piece_end = piece_end_time.strftime('%H:%M')
            is_ot = 1 if piece_end_time > _dt_rsp.strptime('18:30', '%H:%M') else 0
            if i == 0:
                nd = anchor_date
                cur = conn.execute(
                    "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, split_index, split_total) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, ?, ?)",
                    ('recurring', recurring_id, inst['executor_id'], nd, piece_start, piece_end, is_ot, i+1, pieces))
            else:
                nd = anchor_date
                for _ in range(i):
                    nw = _next_workday(nd)
                    if not nw:
                        return jsonify({'success': False, 'message': '无法找到足够的工作日'}), 400
                    nd = nw
                slot = _next_available_slot(inst['executor_id'], nd, durations[i], conn)
                if not slot:
                    for _ in range(3):
                        nw = _next_workday(nd)
                        if not nw: break
                        nd = nw
                        slot = _next_available_slot(inst['executor_id'], nd, durations[i], conn)
                        if slot: break
                if not slot:
                    return jsonify({'success': False, 'message': '第{}片无法找到可用时段'.format(i+1)}), 400
                cur = conn.execute(
                    "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, split_index, split_total) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, ?, ?)",
                    ('recurring', recurring_id, inst['executor_id'], nd, slot[0], slot[1], slot[2], i+1, pieces))
            new_ids.append(cur.lastrowid)
            st_time = piece_end_time
        conn.commit()
        return jsonify({'success': True, 'message': '已重新拆分为{}片'.format(pieces), 'new_ids': new_ids})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/split-pattern/<int:recurring_id>', methods=['GET'])
def api_recurring_get_split_pattern(recurring_id):
    """Get split pattern detail for a recurring task."""
    conn = get_db()
    try:
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (recurring_id,)).fetchone()
        if not rec:
            return jsonify({'success': False, 'message': '周期性工作不存在'}), 404
        import json
        sp = rec['split_pattern'] if 'split_pattern' in rec.keys() else None
        pattern = json.loads(sp) if sp else None
        instances = conn.execute(
            "SELECT id, date, start_time, end_time, split_index, split_total, time_locked FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 ORDER BY date, start_time LIMIT 20",
            (recurring_id,)).fetchall()
        inst_list = []
        for r in instances:
            inst_list.append({
                'id': r['id'], 'date': r['date'], 'start_time': r['start_time'], 'end_time': r['end_time'],
                'split_index': r['split_index'] if 'split_index' in r.keys() else 1,
                'split_total': r['split_total'] if 'split_total' in r.keys() else 1,
                'time_locked': r['time_locked'] if 'time_locked' in r.keys() else 0
            })
        return jsonify({'success': True, 'pattern': pattern, 'duration_minutes': rec['duration_minutes'], 'instances': inst_list})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/recurring/split-pattern/<int:recurring_id>', methods=['PUT'])
def api_recurring_set_split_pattern(recurring_id):
    """Set or clear split pattern for a recurring task from management page."""
    data = request.get_json() or {}
    conn = get_db()
    try:
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (recurring_id,)).fetchone()
        if not rec:
            return jsonify({'success': False, 'message': '周期性工作不存在'}), 404
        import json
        action = data.get('action', 'set')
        if action == 'clear':
            conn.execute("UPDATE recurring_tasks SET split_pattern=NULL, updated_at=datetime('now','localtime') WHERE id=?", (recurring_id,))
            # Merge split instances back: keep first per period, delete rest
            pieces = conn.execute(
                "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 ORDER BY date, start_time",
                (recurring_id,)).fetchall()
            if pieces:
                from datetime import datetime as _dt_cl
                periods_seen = set()
                keep_ids, delete_ids = [], []
                for p in pieces:
                    d = p['date']
                    if rec['cycle_type'] in ('weekly', 'biweekly'):
                        dt_obj = _dt_cl.strptime(d, '%Y-%m-%d')
                        iso = dt_obj.isocalendar()
                        key = "{}-W{:02d}".format(iso[0], iso[1])
                    else:
                        key = d[:7]
                    if key not in periods_seen:
                        periods_seen.add(key)
                        keep_ids.append(p['id'])
                    else:
                        delete_ids.append(p['id'])
                for kid in keep_ids:
                    conn.execute("UPDATE calendar_instances SET split_index=1, split_total=1, updated_at=datetime('now','localtime') WHERE id=?", (kid,))
                if delete_ids:
                    placeholders = ','.join(['?'] * len(delete_ids))
                    conn.execute(f"DELETE FROM calendar_instances WHERE id IN ({placeholders})", delete_ids)
            # Re-generate future instances without split pattern
            conn.execute("DELETE FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND ifnull(time_locked,0)=0", (recurring_id,))
            if pieces:
                first = conn.execute("SELECT start_time FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total=1 ORDER BY date LIMIT 1", (recurring_id,)).fetchone()
                if first:
                    from datetime import datetime as _dt_fs, timedelta as _td_fs
                    st = _dt_fs.strptime(first['start_time'], '%H:%M')
                    et = st + _td_fs(minutes=rec['duration_minutes'] or 30)
                    conn.execute("UPDATE recurring_tasks SET fixed_start_time=?, fixed_end_time=?, updated_at=datetime('now','localtime') WHERE id=?",
                                 (first['start_time'], et.strftime('%H:%M'), recurring_id))
            conn.commit()
            return jsonify({'success': True, 'message': '拆分模式已清除'})
        else:
            pieces_count = data.get('pieces', 2)
            durations = data.get('durations')
            total_dur = rec['duration_minutes'] or 30
            if durations:
                if len(durations) != pieces_count or sum(durations) != total_dur:
                    return jsonify({'success': False, 'message': '各片工时之和须等于总工时{}分钟'.format(total_dur)}), 400
            else:
                base = total_dur // pieces_count
                durations = [base] * pieces_count
                durations[-1] += total_dur - base * pieces_count
            fst = rec['fixed_start_time'] or '09:00'
            from datetime import datetime as _dt_sp, timedelta as _td_sp
            st = _dt_sp.strptime(fst, '%H:%M')
            pattern = []
            for i, dur in enumerate(durations):
                et = st + _td_sp(minutes=dur)
                pattern.append({'day_offset': i, 'start': st.strftime('%H:%M'), 'end': et.strftime('%H:%M')})
                st = _dt_sp.strptime(fst, '%H:%M')  # each piece starts at fixed_start_time
            pattern_json = json.dumps(pattern, ensure_ascii=False)
            conn.execute("UPDATE recurring_tasks SET split_pattern=?, updated_at=datetime('now','localtime') WHERE id=?",
                         (pattern_json, recurring_id))
            _regenerate_split_instances(recurring_id, conn)
            conn.commit()
            return jsonify({'success': True, 'message': '拆分模式已设置', 'pattern': pattern})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


@work_mgmt_bp.route('/api/calendar/save-split-pattern', methods=['POST'])
def api_calendar_save_split_pattern():
    """Save current split arrangement as default pattern for a recurring task."""
    data = request.get_json() or {}
    recurring_id = data.get('recurring_id')
    if not recurring_id:
        return jsonify({'success': False, 'message': '缺少recurring_id'}), 400
    conn = get_db()
    try:
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (recurring_id,)).fetchone()
        if not rec:
            return jsonify({'success': False, 'message': '周期性工作不存在'}), 404
        instances = conn.execute(
            "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 ORDER BY date, start_time",
            (recurring_id,)).fetchall()
        if not instances:
            return jsonify({'success': False, 'message': '该周期性工作尚未拆分'}), 400
        from datetime import datetime as _dt_p
        periods = {}
        for ins in instances:
            d = ins['date']
            if rec['cycle_type'] in ('weekly', 'biweekly'):
                dt_obj = _dt_p.strptime(d, '%Y-%m-%d')
                iso = dt_obj.isocalendar()
                key = "{}-W{:02d}".format(iso[0], iso[1])
            else:
                key = d[:7]
            if key not in periods:
                periods[key] = []
            periods[key].append(ins)
        best_period = None
        for key in sorted(periods.keys(), reverse=True):
            pis = periods[key]
            sp_tot = pis[0]['split_total'] if pis else 1
            if len(pis) >= sp_tot:
                best_period = pis
                break
        if not best_period or len(best_period) < 2:
            return jsonify({'success': False, 'message': '没有完整的拆分周期可保存'}), 400
        base_date = best_period[0]['date']
        import json
        pattern = []
        for pi in best_period:
            offset = _count_workdays(base_date, pi['date'])
            pattern.append({'day_offset': offset, 'start': pi['start_time'], 'end': pi['end_time']})
        pattern_json = json.dumps(pattern, ensure_ascii=False)
        conn.execute("UPDATE recurring_tasks SET split_pattern=?, updated_at=datetime('now','localtime') WHERE id=?",
                     (pattern_json, recurring_id))
        _regenerate_split_instances(recurring_id, conn)
        conn.commit()
        return jsonify({'success': True, 'message': '拆分模式已保存', 'pattern': pattern})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()


def _count_workdays(start_date, end_date):
    """Count workdays between two dates (exclusive of start if different)."""
    from datetime import datetime as _dt_c, timedelta as _td_c
    if start_date == end_date:
        return 0
    count = 0
    cur = _dt_c.strptime(start_date, '%Y-%m-%d')
    end = _dt_c.strptime(end_date, '%Y-%m-%d')
    while cur < end:
        cur += _td_c(days=1)
        if cur.weekday() < 5:
            count += 1
    return count


def _advance_workdays(base_date, offset):
    """Advance base_date by offset workdays."""
    from datetime import datetime as _dt_a, timedelta as _td_a
    if offset == 0:
        return base_date
    cur = _dt_a.strptime(base_date, '%Y-%m-%d')
    remaining = offset
    while remaining > 0:
        cur += _td_a(days=1)
        if cur.weekday() < 5:
            remaining -= 1
    return cur.strftime('%Y-%m-%d')


def _auto_save_split_pattern(inst, conn):
    """Auto-save split pattern when all pieces are locked."""
    try:
        recurring_id = inst['source_id']
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=?', (recurring_id,)).fetchone()
        if not rec: return
        split_total = inst['split_total'] if 'split_total' in inst.keys() else 1
        if split_total <= 1: return
        inst_date = inst['date']
        if rec['cycle_type'] in ('weekly', 'biweekly'):
            dt_obj = _g_dt_now.strptime(inst_date, '%Y-%m-%d')
            iso = dt_obj.isocalendar()
            week_start = (dt_obj - _g_td(days=iso[2]-1)).strftime('%Y-%m-%d')
            week_end = (dt_obj + _g_td(days=7-iso[2])).strftime('%Y-%m-%d')
            all_pieces = conn.execute(
                "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 AND date >= ? AND date <= ?",
                (recurring_id, week_start, week_end)).fetchall()
        else:
            month_start = inst_date[:7] + '-01'
            import calendar as _cal
            y, m = int(inst_date[:4]), int(inst_date[5:7])
            month_end = "{}-{}".format(inst_date[:7], _cal.monthrange(y, m)[1])
            all_pieces = conn.execute(
                "SELECT * FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND split_total > 1 AND date >= ? AND date <= ?",
                (recurring_id, month_start, month_end)).fetchall()
        if len(all_pieces) < split_total: return
        all_locked = all(p['time_locked'] for p in all_pieces if 'time_locked' in p.keys())
        if not all_locked: return
        all_pieces_sorted = sorted(all_pieces, key=lambda x: (x['date'], x['start_time']))
        base_date = all_pieces_sorted[0]['date']
        import json
        pattern = []
        for pi in all_pieces_sorted:
            offset = _count_workdays(base_date, pi['date'])
            pattern.append({'day_offset': offset, 'start': pi['start_time'], 'end': pi['end_time']})
        pattern_json = json.dumps(pattern, ensure_ascii=False)
        conn.execute("UPDATE recurring_tasks SET split_pattern=?, updated_at=datetime('now','localtime') WHERE id=?",
                     (pattern_json, recurring_id))
        _regenerate_split_instances(recurring_id, conn)
    except Exception:
        pass


def _regenerate_split_instances(recurring_id, conn):
    """Delete unlocked instances and regenerate from split_pattern."""
    try:
        rec = conn.execute('SELECT * FROM recurring_tasks WHERE id=? AND is_active=1', (recurring_id,)).fetchone()
        if not rec or 'split_pattern' not in rec.keys() or not rec['split_pattern']: return
        import json
        pattern = json.loads(rec['split_pattern'])
        if not pattern: return
        split_total = len(pattern)
        conn.execute("DELETE FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND ifnull(time_locked,0)=0",
                     (recurring_id,))
        today = _g_dt_now.now().strftime('%Y-%m-%d')
        end = (_g_dt_now.now() + _g_td(days=14)).strftime('%Y-%m-%d')
        task_dates = _expand_dates(rec, today, end)
        for d in task_dates:
            if rec['cycle_type'] in ('daily',):
                exists = conn.execute(
                    'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date=?',
                    ('recurring', rec['id'], d)).fetchone()
            elif rec['cycle_type'] in ('weekly', 'biweekly'):
                dt_obj = _g_dt_now.strptime(d, '%Y-%m-%d')
                iso = dt_obj.isocalendar()
                week_start = (dt_obj - _g_td(days=iso[2]-1)).strftime('%Y-%m-%d')
                week_end = (dt_obj + _g_td(days=7-iso[2])).strftime('%Y-%m-%d')
                exists = conn.execute(
                    'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date>=? AND date<=?',
                    ('recurring', rec['id'], week_start, week_end)).fetchone()
            else:
                month_start = d[:7] + '-01'
                import calendar as _cal
                y, m = int(d[:4]), int(d[5:7])
                month_end = "{}-{}".format(d[:7], _cal.monthrange(y, m)[1])
                exists = conn.execute(
                    'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date>=? AND date<=?',
                    ('recurring', rec['id'], month_start, month_end)).fetchone()
            if exists: continue
            for i, piece in enumerate(pattern):
                piece_date = _advance_workdays(d, piece['day_offset'])
                piece_start = piece['start']
                piece_end = piece['end']
                is_ot = 1 if _g_dt_now.strptime(piece_end, '%H:%M') > _g_dt_now.strptime('18:30', '%H:%M') else 0
                conn.execute(
                    "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, split_index, split_total, time_locked) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, ?, ?, 1)",
                    ('recurring', rec['id'], rec['executor_id'], piece_date, piece_start, piece_end, is_ot, i+1, split_total))
    except Exception:
        pass


@work_mgmt_bp.route('/api/calendar/compact', methods=['POST'])
def api_calendar_compact():
    """Compact all locked recurring instances for a given executor and date."""
    data = request.get_json() or {}
    executor_id = data.get('executor_id')
    date = data.get('date')
    if not executor_id or not date:
        return jsonify({'success': False, 'message': '缺少executor_id或date'}), 400
    conn = get_db()
    try:
        _compact_locked_instances(executor_id, date, conn)
        conn.commit()
        return jsonify({'success': True, 'message': '紧凑排列完成'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()

@work_mgmt_bp.route('/api/calendar/holidays', methods=['GET'])
def api_calendar_holidays():
    """查询日期范围内的假日信息（从dws_dim_date表）"""
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    if not start or not end:
        return jsonify({'success': False, 'message': '缺少日期参数'}), 400
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, holiday_type FROM dws_dim_date WHERE date >= ? AND date <= ?",
            (start, end)
        ).fetchall()
        data = [{'date': r['date'], 'holiday_type': r['holiday_type']} for r in rows]
        return jsonify({'success': True, 'data': data})
    finally:
        conn.close()

# ============ 选项 ============

@work_mgmt_bp.route('/api/options', methods=['GET'])
def api_options():
    conn = get_db()
    try:
        types = [r[0] for r in conn.execute(
            "SELECT DISTINCT type FROM recurring_tasks WHERE type != '' ORDER BY type").fetchall()]
        owners = conn.execute(
            "SELECT id, display_name FROM users WHERE is_active=1 ORDER BY display_name"
        ).fetchall()
        owner_list = [{'id': r['id'], 'name': r['display_name']} for r in owners]
        executors = conn.execute(
            "SELECT id, display_name FROM users WHERE is_active=1 ORDER BY display_name").fetchall()
        executor_list = [{'id': r['id'], 'name': r['display_name']} for r in executors]
        cycle_types = [r[0] for r in conn.execute('SELECT DISTINCT cycle_type FROM recurring_tasks WHERE cycle_type IS NOT NULL AND cycle_type != "" ORDER BY cycle_type').fetchall()]
        return jsonify({'success': True, 'types': types, 'cycle_types': cycle_types, 'owners': owner_list, 'executors': executor_list})
    finally:
        conn.close()



def _parse_day_range(day_str, year, month):
    import calendar as _cal
    max_day = _cal.monthrange(year, month)[1]
    days = []
    for part in day_str.split(','):
        part = part.strip()
        if '~' in part:
            bounds = part.split('~')
            if len(bounds) == 2:
                lo = max(int(bounds[0]), 1)
                hi = min(int(bounds[1]), max_day)
                days.extend(range(lo, hi + 1))
        elif part.isdigit():
            days.append(min(int(part), max_day))
    return days


def _first_workday_in_month(year, month):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT date FROM dws_dim_date WHERE year=? AND month=? AND holiday_type IN ('\u5de5\u4f5c\u65e5','\u5de5\u4f5c\u65e5-\u8865\u73ed') ORDER BY date LIMIT 1",
            (year, month)).fetchone()
        return row['date'] if row else None
    finally:
        pass



def _first_workday_in_range(year, month, day_range_str):
    """Find the first workday in a date range like '5~10' or '7~12' or '10'.
    Returns date string 'YYYY-MM-DD' or None."""
    import calendar as _cal
    max_day = _cal.monthrange(year, month)[1]
    days = _parse_day_range(day_range_str, year, month)
    if not days:
        return None
    # Query dws_dim_date for workdays in this range
    conn = get_db()
    try:
        day_conditions = ' OR '.join([f"date = '{year}-{month:02d}-{d:02d}'" for d in days])
        row = conn.execute(
            f"SELECT date FROM dws_dim_date WHERE ({day_conditions}) AND holiday_type IN ('\u5de5\u4f5c\u65e5','\u5de5\u4f5c\u65e5-\u8865\u73ed') ORDER BY date LIMIT 1"
        ).fetchone()
        return row['date'] if row else None
    finally:
        pass


def _expand_dates(task, start_date, end_date):
    """Expand a recurring task into concrete dates within [start_date, end_date].
    
    Field reference (each field stores ONE dimension only):
      cycle_type:        'daily'/'weekly'/'biweekly'/'monthly'/'bimonthly'/'quarterly'/'yearly'/'on_demand'
      cycle_weekdays:    weekday numbers 1-7, comma-separated. Used by: weekly, biweekly
      cycle_week_parity: 'even'/'odd'/NULL. ISO week parity. Used by: biweekly
      cycle_target_months: absolute month numbers 1-12, comma-separated. Used by: bimonthly, quarterly, yearly
      cycle_month_days:  day or day-range within month. 3 syntaxes:
                         - "10"      = single day (1 instance, pick workday)
                         - "5~10"    = day range / window (1 instance, pick first workday in range)
                         - "5,7,10"  = discrete multi-day (1 instance per specified day)
                         Used by: monthly, bimonthly, quarterly, yearly
      cycle_rule:        human-readable description only, NOT used for logic
    """
    from datetime import date as _date
    cycle_type = task['cycle_type'] or 'weekly'
    cycle_weekdays = str(task['cycle_weekdays'] or '').strip()
    cycle_month_days = str(task['cycle_month_days'] or '').strip()
    cycle_target_months = str(task['cycle_target_months'] if 'cycle_target_months' in task.keys() else '').strip()
    cycle_week_parity = str(task['cycle_week_parity'] if 'cycle_week_parity' in task.keys() else '').strip()
    sd = _g_dt_now.strptime(start_date, '%Y-%m-%d').date()
    ed = _g_dt_now.strptime(end_date, '%Y-%m-%d').date()
    dates = []
    def _add(d):
        ds = d.strftime('%Y-%m-%d')
        if ds not in dates: dates.append(ds)

    def _is_range_mode(day_str):
        """True = window mode (pick 1 workday). False = multi-day mode (each day gets instance)."""
        if '~' in day_str: return True
        if ',' in day_str: return False
        return True  # single number = pick 1 workday

    def _parse_months(months_str):
        """Parse comma-separated month numbers into sorted list of ints."""
        if not months_str: return []
        result = []
        for p in months_str.split(','):
            p = p.strip()
            if p.isdigit() and 1 <= int(p) <= 12:
                result.append(int(p))
        return sorted(set(result))

    def _expand_days_in_month(year, month, day_str):
        """Generate dates for a specific month based on cycle_month_days syntax."""
        if not day_str:
            fw = _first_workday_in_month(year, month)
            if fw:
                fd = _g_dt_now.strptime(fw, '%Y-%m-%d').date()
                if sd <= fd <= ed: _add(fd)
            return
        if _is_range_mode(day_str):
            fw = _first_workday_in_range(year, month, day_str)
            if fw:
                fd = _g_dt_now.strptime(fw, '%Y-%m-%d').date()
                if sd <= fd <= ed: _add(fd)
        else:
            day_list = _parse_day_range(day_str, year, month)
            for dy in day_list:
                try:
                    fd = _date(year, month, dy)
                    if sd <= fd <= ed: _add(fd)
                except ValueError:
                    pass

    if cycle_type == 'on_demand':
        return dates
    elif cycle_type == 'daily':
        d = sd
        while d <= ed:
            _add(d); d += _g_td(days=1)
    elif cycle_type in ('weekly', 'biweekly'):
        # Parse weekdays
        wd_set = set()
        if cycle_weekdays:
            if '~' in cycle_weekdays:
                parts = cycle_weekdays.split('~')
                if len(parts) == 2:
                    for w in range(int(parts[0]), int(parts[1]) + 1): wd_set.add(int(w))
            elif ',' in cycle_weekdays:
                for w in cycle_weekdays.split(','):
                    w = w.strip()
                    if w.isdigit(): wd_set.add(int(w))
            elif cycle_weekdays.isdigit(): wd_set.add(int(cycle_weekdays))
        if not wd_set: wd_set = {1}
        # Biweekly: filter by ISO week parity
        is_even_week = cycle_week_parity == 'even'
        is_odd_week = cycle_week_parity == 'odd'
        d = sd
        while d <= ed:
            our_wd = d.weekday() + 1
            if our_wd in wd_set:
                if cycle_type == 'weekly':
                    _add(d)
                else:
                    if is_even_week or is_odd_week:
                        iso_week = d.isocalendar()[1]
                        if (is_even_week and iso_week % 2 == 0) or (is_odd_week and iso_week % 2 == 1):
                            _add(d)
                    else:
                        _add(d)  # fallback: no parity filter
            d += _g_td(days=1)
    elif cycle_type == 'monthly':
        d = sd
        while d <= ed:
            year, month = d.year, d.month
            _expand_days_in_month(year, month, cycle_month_days)
            if month == 12: d = _date(year + 1, 1, 1)
            else: d = _date(year, month + 1, 1)
    elif cycle_type == 'bimonthly':
        target_months = _parse_months(cycle_target_months)
        d = sd
        while d <= ed:
            year, month = d.year, d.month
            if not target_months or month in target_months:
                _expand_days_in_month(year, month, cycle_month_days)
            if month == 12: d = _date(year + 1, 1, 1)
            else: d = _date(year, month + 1, 1)
    elif cycle_type == 'quarterly':
        target_months = _parse_months(cycle_target_months)
        d = sd
        while d <= ed:
            year, month = d.year, d.month
            if target_months and month in target_months:
                _expand_days_in_month(year, month, cycle_month_days)
            if month == 12: d = _date(year + 1, 1, 1)
            else: d = _date(year, month + 1, 1)
    elif cycle_type == 'yearly':
        target_months = _parse_months(cycle_target_months)
        d = sd
        while d <= ed:
            year, month = d.year, d.month
            if target_months and month in target_months:
                _expand_days_in_month(year, month, cycle_month_days)
            if month == 12: d = _date(year + 1, 1, 1)
            else: d = _date(year, month + 1, 1)
    # Filter: keep only workdays
    if dates:
        conn = get_db()
        try:
            ph = ','.join(['?']*len(dates))
            rows = conn.execute(
                "SELECT date FROM dws_dim_date WHERE date IN ({}) AND holiday_type IN ('\u5de5\u4f5c\u65e5','\u5de5\u4f5c\u65e5-\u8865\u73ed')".format(ph), dates).fetchall()
            workday_set = {r['date'] for r in rows}
            dates = [d for d in dates if d in workday_set]
        finally: pass
    return dates


def _calc_freq_per_month(cycle_type, cycle_weekdays, cycle_month_days, cycle_interval, manual_freq):
    """Calculate frequency per month for a recurring task."""
    if manual_freq and float(manual_freq) > 0:
        return float(manual_freq)
    try:
        if cycle_type == 'daily': return 22
        elif cycle_type == 'weekly':
            if cycle_weekdays:
                wd = str(cycle_weekdays).strip()
                if wd.startswith('['):
                    days = json.loads(wd)
                    return round(4 * len(days) / cycle_interval, 1)
                if ',' in wd:
                    return round(4 * len(wd.split(',')) / cycle_interval, 1)
                return round(4 / cycle_interval, 1)
            return round(4 / cycle_interval, 1)
        elif cycle_type == 'biweekly':
            if cycle_weekdays:
                wd = str(cycle_weekdays).strip()
                if wd.startswith('['):
                    days = json.loads(wd)
                    return round(2 * len(days) / cycle_interval, 1)
                if ',' in wd:
                    return round(2 * len(wd.split(',')) / cycle_interval, 1)
                return round(2 / cycle_interval, 1)
            return 2
        elif cycle_type == 'monthly':
            if cycle_month_days:
                md = str(cycle_month_days).strip()
                if ',' in md: return len(md.split(','))
                return 1
            return 1
        elif cycle_type == 'bimonthly':
            return 0.5
        elif cycle_type == 'quarterly':
            return 0.33
        elif cycle_type == 'yearly':
            return 0.08
        elif cycle_type == 'on_demand': return 0
        else: return 0
    except: return 0

def _next_available_slot(executor_id, date, duration_minutes, conn, after_time=None):
    """Find next non-overlapping time slot for executor on given date.
    Returns (start_time_str, end_time_str, is_overtime) or None if no room."""
    # Get all existing instances for this executor on this date, ordered by start_time
    existing = conn.execute(
        "SELECT start_time, end_time FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' ORDER BY start_time",
        (executor_id, date)).fetchall()
    work_start = _g_dt_now.strptime('09:00', '%H:%M')
    work_end = _g_dt_now.strptime('20:00', '%H:%M')
    sched_end = _g_dt_now.strptime('18:30', '%H:%M')
    lunch_s = _g_dt_now.strptime('12:30', '%H:%M')
    lunch_e = _g_dt_now.strptime('13:30', '%H:%M')
    dur = _g_td(minutes=duration_minutes)

    cursor = _g_dt_now.strptime(after_time.strftime('%H:%M'), '%H:%M') if after_time else work_start

    # Build occupied intervals list
    occupied = []
    # Treat lunch break as an occupied slot
    occupied.append((lunch_s, lunch_e))
    for r in existing:
        if r['start_time'] and r['end_time']:
            occupied.append((
                _g_dt_now.strptime(r['start_time'], '%H:%M'),
                _g_dt_now.strptime(r['end_time'], '%H:%M')
            ))
    occupied.sort(key=lambda x: x[0])

    # Find gap
    for occ_s, occ_e in occupied:
        if cursor + dur <= occ_s:
            break  # fits before this occupied slot
        if cursor < occ_e:
            cursor = occ_e

    # Check if fits within work hours
    if cursor + dur > work_end:
        return None  # no room today

    is_ot = 1 if cursor + dur > sched_end else 0
    return (cursor.strftime('%H:%M'), (cursor + dur).strftime('%H:%M'), is_ot)


def _find_task_slot(executor_id, expected_end_str, duration_minutes, conn):
    """Find available slot for a task, scheduling BACKWARDS from deadline.
    Returns dict with ideal, conflicts, suggested slots."""
    dt = _g_dt_now.strptime(expected_end_str.replace('T',' '), '%Y-%m-%d %H:%M')
    date_str = dt.strftime('%Y-%m-%d')
    deadline = _g_dt_now.strptime(dt.strftime('%H:%M'), '%H:%M')
    WORK_START = _g_dt_now.strptime('09:00', '%H:%M')
    WORK_END   = _g_dt_now.strptime('20:00', '%H:%M')
    SCHED_END  = _g_dt_now.strptime('18:30', '%H:%M')
    LUNCH_S    = _g_dt_now.strptime('12:30', '%H:%M')
    LUNCH_E    = _g_dt_now.strptime('13:30', '%H:%M')
    dur = _g_td(minutes=duration_minutes)
    existing = conn.execute(
        "SELECT start_time, end_time, source_type, source_id FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' ORDER BY start_time",
        (executor_id, date_str)).fetchall()
    occupied = [(LUNCH_S, LUNCH_E)]
    conflict_details = []
    for r in existing:
        if r['start_time'] and r['end_time']:
            s = _g_dt_now.strptime(r['start_time'], '%H:%M')
            e = _g_dt_now.strptime(r['end_time'], '%H:%M')
            occupied.append((s, e))
            name = ''
            if r['source_type'] == 'recurring' and r['source_id']:
                rec = conn.execute('SELECT name FROM recurring_tasks WHERE id=?', (r['source_id'],)).fetchone()
                name = rec['name'] if rec else '\u5468\u671f\u6027\u5de5\u4f5c'
            elif r['source_type'] == 'task' and r['source_id']:
                t = conn.execute('SELECT title FROM tasks WHERE id=?', (r['source_id'],)).fetchone()
                name = t['title'] if t else '\u4efb\u52a1'
            conflict_details.append({
                'start': s.strftime('%H:%M'), 'end': e.strftime('%H:%M'),
                'type': r['source_type'], 'name': name
            })
    occupied.sort(key=lambda x: x[0])
    merged = []
    for s, e in occupied:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    result = {
        'date': date_str, 'deadline': deadline.strftime('%H:%M'),
        'duration_minutes': duration_minutes,
        'has_conflict': False, 'conflicts': [], 'suggested': []
    }
    ideal_start = deadline - dur
    ideal_end = deadline
    if ideal_start < WORK_START:
        ideal_start = WORK_START
    has_conflict = False
    for s, e in merged:
        if ideal_start < e and ideal_end > s:
            has_conflict = True
            break
    if not has_conflict and ideal_end <= WORK_END:
        is_ot = 1 if ideal_end > SCHED_END else 0
        result['ideal_start'] = ideal_start.strftime('%H:%M')
        result['ideal_end'] = ideal_end.strftime('%H:%M')
        result['best'] = {
            'date': date_str, 'start': ideal_start.strftime('%H:%M'),
            'end': ideal_end.strftime('%H:%M'), 'is_overtime': is_ot, 'type': 'ideal'
        }
        return result
    result['has_conflict'] = True
    result['ideal_start'] = ideal_start.strftime('%H:%M')
    result['ideal_end'] = ideal_end.strftime('%H:%M')
    for cd in conflict_details:
        cs = _g_dt_now.strptime(cd['start'], '%H:%M')
        ce = _g_dt_now.strptime(cd['end'], '%H:%M')
        if ideal_start < ce and ideal_end > cs:
            result['conflicts'].append(cd)
    # Find latest gap before deadline
    gaps = []
    cursor = WORK_START
    for s, e in merged:
        if s > cursor and s <= deadline:
            gap_end = min(s, deadline)
            if gap_end - cursor >= dur:
                gaps.append((cursor, gap_end))
        cursor = max(cursor, e)
    if cursor < deadline and deadline - cursor >= dur:
        gaps.append((cursor, deadline))
    for gs, ge in reversed(gaps):
        slot_start = ge - dur
        slot_end = ge
        if slot_start >= WORK_START:
            is_ot = 1 if slot_end > SCHED_END else 0
            result['suggested'].append({
                'date': date_str, 'start': slot_start.strftime('%H:%M'),
                'end': slot_end.strftime('%H:%M'), 'is_overtime': is_ot,
                'type': 'same_day_earlier',
                'desc': '\u5f53\u65e5 ' + slot_start.strftime('%H:%M') + '-' + slot_end.strftime('%H:%M')
            })
            break
    # Try after deadline (overtime)
    if not result['suggested']:
        slot = _next_available_slot(executor_id, date_str, duration_minutes, conn, after_time=deadline)
        if slot:
            st, et, is_ot = slot
            result['suggested'].append({
                'date': date_str, 'start': st, 'end': et,
                'is_overtime': is_ot, 'type': 'overtime',
                'desc': '\u5f53\u65e5\u52a0\u73ed ' + st + '-' + et
            })
    # Try next workdays
    if not result['suggested']:
        nd = _next_workday(date_str)
        for _ in range(5):
            if not nd: break
            slot = _next_available_slot(executor_id, nd, duration_minutes, conn)
            if slot:
                st, et, is_ot = slot
                result['suggested'].append({
                    'date': nd, 'start': st, 'end': et,
                    'is_overtime': is_ot, 'type': 'next_workday',
                    'desc': nd + ' ' + st + '-' + et
                })
                break
            nd = _next_workday(nd)
    result['best'] = result['suggested'][0] if result['suggested'] else None
    return result


def _generate_instances(start_date, end_date, executor_id=None):
    """Generate calendar_instances. Existing instances are NEVER overwritten.
    Uses _next_available_slot per insert for correct lunch break + no overlap."""
    conn = get_db()
    try:
        sql = 'SELECT * FROM recurring_tasks WHERE is_active=1'
        params = []
        if executor_id:
            sql += ' AND executor_id=?'
            params.append(executor_id)
        tasks = conn.execute(sql, params).fetchall()
        created = 0; skipped = 0; errors = []
        from collections import defaultdict
        groups = defaultdict(list)
        for task in tasks:
            try:
                task_dates = _expand_dates(task, start_date, end_date)
                for d in task_dates:
                    # Period-level check: if user moved the event within the same period, don't regenerate
                    if task['cycle_type'] in ('daily',):
                        exists = conn.execute(
                            'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date=?',
                            ('recurring', task['id'], d)).fetchone()
                    elif task['cycle_type'] in ('weekly', 'biweekly'):
                        # Same ISO week
                        dt_obj = _g_dt_now.strptime(d, '%Y-%m-%d')
                        iso = dt_obj.isocalendar()
                        week_start = (dt_obj - _g_td(days=iso[2]-1)).strftime('%Y-%m-%d')
                        week_end = (dt_obj + _g_td(days=7-iso[2])).strftime('%Y-%m-%d')
                        exists = conn.execute(
                            'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date>=? AND date<=?',
                            ('recurring', task['id'], week_start, week_end)).fetchone()
                    else:
                        # monthly/bimonthly/quarterly/yearly: same month
                        month_start = d[:7] + '-01'
                        import calendar as _cal
                        y, m = int(d[:4]), int(d[5:7])
                        month_end = f"{d[:7]}-{_cal.monthrange(y, m)[1]:02d}"
                        exists = conn.execute(
                            'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=? AND date>=? AND date<=?',
                            ('recurring', task['id'], month_start, month_end)).fetchone()
                    if exists:
                        skipped += 1; continue
                    groups[(d, task['executor_id'])].append((task['id'], task['duration_minutes'] or 30))
            except Exception as e:
                errors.append(f"Recurring {task['id']}({task['name']}): {str(e)}")
        for (d, eid), items in groups.items():
            items.sort(key=lambda x: x[1], reverse=True)
            # Pre-load fixed_start_time and split_pattern from recurring_tasks
            fixed_cache = {}
            split_cache = {}
            for tid, dur in items:
                rec = conn.execute(
                    "SELECT fixed_start_time, fixed_end_time, split_pattern FROM recurring_tasks WHERE id=?",
                    (tid,)).fetchone()
                if rec:
                    if rec['fixed_start_time']:
                        fixed_cache[tid] = (rec['fixed_start_time'], rec['fixed_end_time'])
                    if rec['split_pattern'] if 'split_pattern' in rec.keys() else None:
                        import json as _json_sp
                        try: split_cache[tid] = _json_sp.loads(rec['split_pattern'])
                        except: pass
            for tid, dur in items:
                # Split pattern takes priority over fixed_start_time
                if tid in split_cache:
                    pattern = split_cache[tid]
                    for i, piece in enumerate(pattern):
                        piece_date = _advance_workdays(d, piece['day_offset'])
                        piece_start = piece['start']
                        piece_end = piece['end']
                        conflict = conn.execute(
                            "SELECT 1 FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' AND start_time < ? AND end_time > ?",
                            (eid, piece_date, piece_end, piece_start)).fetchone()
                        if not conflict:
                            is_ot = 1 if _g_dt_now.strptime(piece_end, '%H:%M') > _g_dt_now.strptime('18:30', '%H:%M') else 0
                            conn.execute(
                                "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, split_index, split_total, time_locked) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, ?, ?, 1)",
                                ('recurring', tid, eid, piece_date, piece_start, piece_end, is_ot, i+1, len(pattern)))
                            created += 1
                    continue
                if tid in fixed_cache:
                    # Use fixed time from recurring_tasks
                    lst, let = fixed_cache[tid]
                    # Check if locked slot is available on this date
                    conflict = conn.execute(
                        "SELECT 1 FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' AND start_time=? AND end_time=?",
                        (eid, d, lst, let)).fetchone()
                    if not conflict:
                        is_ot = 1 if _g_dt_now.strptime(let, '%H:%M') > _g_dt_now.strptime('18:30', '%H:%M') else 0
                        conn.execute(
                            "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, time_locked) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, 1)",
                            ('recurring', tid, eid, d, lst, let, is_ot))
                        created += 1
                        continue
                slot = _next_available_slot(eid, d, dur, conn)
                if slot:
                    st, et, is_ot = slot
                    conn.execute(
                        "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                        ('recurring', tid, eid, d, st, et, is_ot))
                    created += 1
                else:
                    # Overflow: try next workdays
                    nd = _next_workday(d)
                    for _ in range(3):
                        if not nd: break
                        slot = _next_available_slot(eid, nd, dur, conn)
                        if slot:
                            st, et, is_ot = slot
                            conn.execute(
                                "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                                ('recurring', tid, eid, nd, st, et, is_ot))
                            created += 1
                            break
                        nd = _next_workday(nd)
                    else:
                        skipped += 1
        # Also book active one-time tasks (backward scheduling from deadline)
        task_sql = """SELECT t.id, t.executor_id, t.expected_end, t.estimated_minutes, t.status, t.task_no
                      FROM tasks t WHERE t.status IN ('pending','in_progress','pending_review')
                      AND t.expected_end IS NOT NULL"""
        task_params = []
        if executor_id:
            task_sql += ' AND t.executor_id=?'
            task_params.append(executor_id)
        active_tasks = conn.execute(task_sql, task_params).fetchall()
        for at in active_tasks:
            if not at['expected_end']: continue
            try:
                # Check if task already has any instance (date may differ from expected_end due to backward scheduling)
                exists = conn.execute(
                    'SELECT 1 FROM calendar_instances WHERE source_type=? AND source_id=?',
                    ('task', at['id'])).fetchone()
                if exists: skipped += 1; continue
                dur = at['estimated_minutes'] or 30
                # Use backward scheduling via _find_task_slot
                result = _find_task_slot(at['executor_id'], at['expected_end'], dur, conn)
                if result.get('best'):
                    best = result['best']
                    # Check if the scheduled date falls within the requested range
                    if best['date'] < start_date or best['date'] > end_date:
                        skipped += 1; continue
                    conn.execute(
                        "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                        ('task', at['id'], at['executor_id'], best['date'], best['start'], best['end'], best.get('is_overtime', 0)))
                    created += 1
                else:
                    errors.append(f"Task {at['task_no']}: no available slot before deadline")
            except Exception as e:
                errors.append(f"Task {at['task_no']}: {str(e)}")
        conn.commit()
        return {'created': created, 'skipped': skipped, 'errors': errors[:10]}
    except Exception as e:
        conn.rollback()
        return {'created': 0, 'skipped': 0, 'errors': [str(e)]}



def _next_workday(date_str):
    """Find next workday after date_str. Returns date string 'YYYY-MM-DD'."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT date FROM dws_dim_date WHERE date > ? AND holiday_type IN ('\u5de5\u4f5c\u65e5','\u5de5\u4f5c\u65e5-\u8865\u73ed') ORDER BY date LIMIT 1",
            (date_str,)).fetchone()
        return row['date'] if row else None
    finally:
        pass


def _compact_locked_instances(executor_id, date, conn):
    """Auto-compact locked recurring instances for executor on given date.
    Removes gaps between consecutive locked recurring tasks, keeping their order."""
    from datetime import datetime as _dt_c, timedelta as _td_c
    LUNCH_S = _dt_c.strptime('12:30', '%H:%M')
    LUNCH_E = _dt_c.strptime('13:30', '%H:%M')
    SCHED_END = _dt_c.strptime('18:30', '%H:%M')
    
    locked = conn.execute(
        "SELECT id, source_id, start_time, end_time FROM calendar_instances "
        "WHERE executor_id=? AND date=? AND source_type='recurring' AND time_locked=1 "
        "AND status != 'leave' ORDER BY start_time",
        (executor_id, date)).fetchall()
    
    if len(locked) < 2:
        return  # Nothing to compact
    
    # Find the earliest start - this is where we begin packing
    cursor = _dt_c.strptime(locked[0]['start_time'], '%H:%M')
    
    for inst in locked:
        st = _dt_c.strptime(inst['start_time'], '%H:%M')
        et = _dt_c.strptime(inst['end_time'], '%H:%M')
        dur = et - st
        if dur.total_seconds() <= 0:
            dur = _td_c(minutes=30)
        
        new_st = cursor
        # Skip over lunch break
        if new_st < LUNCH_E and new_st + dur > LUNCH_S:
            new_st = LUNCH_E
        new_et = new_st + dur
        
        new_st_str = new_st.strftime('%H:%M')
        new_et_str = new_et.strftime('%H:%M')
        is_ot = 1 if new_et > SCHED_END else 0
        
        # Update calendar instance
        conn.execute(
            "UPDATE calendar_instances SET start_time=?, end_time=?, is_overtime=?, updated_at=datetime('now','localtime') WHERE id=?",
            (new_st_str, new_et_str, is_ot, inst['id']))
        
        # Update recurring_tasks fixed time
        rec_id = inst['source_id']
        if rec_id:
            conn.execute(
                "UPDATE recurring_tasks SET fixed_start_time=?, fixed_end_time=?, updated_at=datetime('now','localtime') WHERE id=?",
                (new_st_str, new_et_str, rec_id))
        
        cursor = new_et


def _book_task_instance(task_id, conn, confirmed_slot=None):
    """Book a one-time task into calendar. Schedules BACKWARDS from deadline.
    If confirmed_slot is provided (dict with date/start/end/is_overtime), use it directly.
    Otherwise auto-find best slot using _find_task_slot."""
    try:
        t = conn.execute('SELECT id, executor_id, expected_end, estimated_minutes, status, start_time FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not t or not t['expected_end']: return
        if t['status'] not in ('pending','in_progress','pending_review'): return
        conn.execute("DELETE FROM calendar_instances WHERE source_type='task' AND source_id=?", (task_id,))
        dur = t['estimated_minutes'] or 30
        if confirmed_slot:
            conn.execute(
                "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                ('task', t['id'], t['executor_id'], confirmed_slot['date'], confirmed_slot['start'], confirmed_slot['end'], confirmed_slot.get('is_overtime', 0)))
            # If task has start_time, sync with confirmed slot
            if t['start_time'] if 'start_time' in t.keys() else None:
                conn.execute('UPDATE tasks SET start_time=?, expected_end=?, updated_at=datetime("now","localtime") WHERE id=?',
                             (confirmed_slot['date'] + ' ' + confirmed_slot['start'], confirmed_slot['date'] + ' ' + confirmed_slot['end'], task_id))
            return
        result = _find_task_slot(t['executor_id'], t['expected_end'], dur, conn)
        if result.get('best'):
            best = result['best']
            conn.execute(
                "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                ('task', t['id'], t['executor_id'], best['date'], best['start'], best['end'], best.get('is_overtime', 0)))
            # If task has start_time, sync with scheduled slot
            if t['start_time'] if 'start_time' in t.keys() else None:
                conn.execute('UPDATE tasks SET start_time=?, expected_end=?, updated_at=datetime("now","localtime") WHERE id=?',
                             (best['date'] + ' ' + best['start'], best['date'] + ' ' + best['end'], task_id))
    except Exception:
        pass


def _book_recurring_instance(recurring_id, conn):
    """Book a recurring task for next 14 days. Uses _next_available_slot.
    Overflow to next workday if no room. Called on recurring create/update."""
    try:
        task = conn.execute('SELECT * FROM recurring_tasks WHERE id=? AND is_active=1', (recurring_id,)).fetchone()
        if not task: return
        # If split_pattern exists, use dedicated regeneration
        if task['split_pattern'] if 'split_pattern' in task.keys() else None:
            _regenerate_split_instances(recurring_id, conn)
            return
        fst = task['fixed_start_time']
        fet = task['fixed_end_time']
        # If fixed_start_time is set, update ALL existing locked instances to new time
        if fst:
            conn.execute(
                "UPDATE calendar_instances SET start_time=?, end_time=? WHERE source_type='recurring' AND source_id=? AND ifnull(time_locked,0)=1",
                (fst, fet, recurring_id))
        conn.execute("DELETE FROM calendar_instances WHERE source_type='recurring' AND source_id=? AND ifnull(time_locked,0)=0", (recurring_id,))
        for d in task_dates:
            dur = task['duration_minutes'] or 30
            if fst and fet:
                # Use fixed_start_time/fixed_end_time (same as _generate_instances)
                conflict = conn.execute(
                    "SELECT 1 FROM calendar_instances WHERE executor_id=? AND date=? AND status != 'leave' AND start_time < ? AND end_time > ?",
                    (task['executor_id'], d, fet, fst)).fetchone()
                if not conflict:
                    is_ot_f = 1 if _g_dt_now.strptime(fet, '%H:%M') > _g_dt_now.strptime('18:30', '%H:%M') else 0
                    conn.execute(
                        "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime, time_locked) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?, 1)",
                        ('recurring', task['id'], task['executor_id'], d, fst, fet, is_ot_f))
                    continue
            # No fixed time or conflict: auto-find slot
            max_overflow = 3
            for _ in range(max_overflow):
                slot = _next_available_slot(task['executor_id'], d, dur, conn)
                if slot:
                    st, et, is_ot = slot
                    conn.execute(
                        "INSERT INTO calendar_instances (source_type, source_id, executor_id, date, start_time, end_time, status, is_overtime) VALUES (?, ?, ?, ?, ?, ?, 'normal', ?)",
                        ('recurring', task['id'], task['executor_id'], d, st, et, is_ot))
                    break
                nd = _next_workday(d)
                if not nd: break
                d = nd
    except Exception:
        pass


# ============ AI System Prompts ============

TASK_MGMT_SYSTEM_PROMPT = """你是「早点下班」工作管理AI助手，理性温和专业，数据洞察决策。

## 职责
1. 整理工作需求为结构化任务
2. 回答进度/工时/类型分析问题（引用具体数据）
3. 估算任务工时（参考历史同类数据，说明依据）

## 任务字段(严格按以下格式)
- title: 任务标题，≤30字
- executor: 执行人，每条任务仅允许一人，从系统账号中选取。多人执行时为每人分别生成一条任务。未指定时推荐并说明理由，不替用户决定
- description: 任务描述，简洁说明内容和要求
- start_time: 排定开始时间，可选，格式 YYYY-MM-DD HH:MM（如 2026-08-17 15:00）。当用户明确提到具体执行时间（如下午3点17:00明天上午10点）时必须填写，表示任务计划何时开始；未提具体时间则留空不填
- expected_end: 截止时间，必须为 YYYY-MM-DD HH:MM 格式（如 2026-08-17 12:00），根据今日日期计算出具体日期时间，禁止使用"明天""下周"等相对词，禁止使用T分隔符
- estimated_minutes: 预估工时，整数，单位分钟（如2小时=120）

## 任务状态流转
待办 → 进行中 → 待验收 → 已完成

## 规则
- 用数据说话，先结论后依据，简洁无套话
- 不编造数据，推断须标注
- 信息足时输出JSON代码块，每条任务一个代码块：
```json
{"title":"","executor":"","description":"","start_time":"","expected_end":"","estimated_minutes":0}
```
- 多人执行时，为每人分别输出一个JSON代码块，每个代码块仅包含一个执行人，不可将多人写在同一个executor字段
- 信息不足先追问
- 今日日期在系统上下文中提供，据此计算expected_end的具体日期
- 更改截止时间时也必须使用 YYYY-MM-DD HH:MM 格式，禁止使用相对词，禁止T分隔符，并输出完整的JSON代码块
## 排期验证
创建/修改任务时，系统会自动验证排期：
- 理想时段 = 截止时间 - 预估工时，如截欢18:30工时60min则理想时段17:30-18:30
- 若理想时段有冲突（周期性工作/午休/其他任务），系统会建议最近可用时段
- 建议顺序：当日空挡(靠近截止时间) → 当日加班 → 下一工作日
- 用户确认建议时段后才最终创建，如不满意可自行调整截止时间


## 修改任务
当用户要求修改已有任务时，从活跃任务明细中找到对应工单号，输出修改JSON代码块：
```json
{"action":"update","task_no":"WK20260816-001","title":"","executor":"","description":"","start_time":"","expected_end":"","estimated_minutes":0}
```
task_no为必填项，填写活跃任务明细中的工单号(如WK20260816-001)；仅需包含需要修改的字段，未修改的字段保持原值。expected_end必须为 YYYY-MM-DD HH:MM 格式。"""

RECURRING_SYSTEM_PROMPT = """你是「早点下班」周期性工作AI助手，理性温和专业，数据洞察决策。

## 职责
1. 分析周期性工作工时分布、负荷均衡、异常识别
2. 创建/修改/停用周期性工作（含批量操作）
3. 优化建议：基于工时标准，识别异常高工时项目，提出改善方向

## 工时标准
- 月基准: 22工作日\u00d78h=176h
- 周期性工作占比上限40%=70h/月(8.8人天)
- 专项工作30%=53h, 临时任务30%=53h
- 单项月均>20h视为异常高工时，需评估优化

## 字段
- name(名称)、type(类型)、cycle_type、freq_per_month(月频次)、executor(执行人:从系统账号中选取)、duration_minutes(单次时长min)、has_sop(有否SOP:y/n)、is_active(1启用/0停用)、fixed_start_time(固定开始时间,格式HH:MM如16:00,非必填,仅输入开始时间,结束时间由工时自动算)
- split_pattern(拆分模式):将单次工时拆为多片执行,JSON数组[{"day_offset":0,"start":"09:00","end":"10:00"},...],day_offset=第几天(0=当天),每片start/end定义时间段。未拆分时为null。拆分后fixed_start_time由split_pattern[0]推导,无需单独设置

## 周期类型与字段填写基准（严格按此填写，禁止混用）

### cycle_type 枚举
daily / weekly / biweekly / monthly / bimonthly / quarterly / yearly / on_demand

### 各类型必填字段对照

| cycle_type | cycle_weekdays | cycle_week_parity | cycle_target_months | cycle_month_days | 说明 |
|---|---|---|---|---|---|
| daily | - | - | - | - | 每个工作日 |
| weekly | \u2713 | - | - | - | 每周指定星期 |
| biweekly | \u2713 | \u2713 | - | - | 双周/单周指定星期 |
| monthly | - | - | - | \u2713 | 每月指定日/日范围 |
| bimonthly | - | - | \u2713 | \u2713 | 指定月份+指定日/日范围 |
| quarterly | - | - | \u2713 | \u2713 | 指定月份+指定日/日范围 |
| yearly | - | - | \u2713 | \u2713 | 指定月份+指定日/日范围 |
| on_demand | - | - | - | - | 不定期，不自动排期 |

### 字段格式严格规范

**cycle_weekdays** (星期几，1=周一 7=周日)
- 单日: "1" (每周一)
- 多日: "1,3,5" (每周一三五)

**cycle_week_parity** (ISO周奇偶，仅biweekly使用)
- "even" = 双周(偶数ISO周)
- "odd" = 单周(奇数ISO周)

**cycle_target_months** (绝对月份1~12，逗号分隔)
- bimonthly偶数月: "2,4,6,8,10,12"
- bimonthly奇数月: "1,3,5,7,9,11"
- quarterly第2月: "2,5,8,11"
- quarterly第3月: "3,6,9,12"
- yearly指定月: "2,8" (2月和8月) / "10,11,12" (10~12月)

**cycle_month_days** (月内日/日范围，三种语法)
- "10" = 单日窗口，取10号附近第一个工作日(1条实例)
- "5~10" = 日期范围窗口，取5~10号内第一个工作日(1条实例)
- "5,7,10" = 离散多日，5号7号10号各排1条(3条实例)

\u26a0\ufe0f 重要区别：
- "5~10" = 窗口模式，整个范围只选1天排1条，可被任务调剂到范围内其他工作日
- "5,7,10" = 多日模式，每天各1条，不可调剂
- "10" = 等同于"10~10"的简写，窗口模式，1条实例

### 填写示例
- 每周一: cycle_type=weekly, cycle_weekdays="1"
- 双周三: cycle_type=biweekly, cycle_weekdays="3", cycle_week_parity="even"
- 每月5~10号: cycle_type=monthly, cycle_month_days="5~10"
- 偶数月1~7号: cycle_type=bimonthly, cycle_target_months="2,4,6,8,10,12", cycle_month_days="1~7"
- 每季度第3月15~25号: cycle_type=quarterly, cycle_target_months="3,6,9,12", cycle_month_days="15~25"
- 每年2月和8月1~28号: cycle_type=yearly, cycle_target_months="2,8", cycle_month_days="1~28"

## 规则
- 用数据说话，先结论后依据，简洁无套话
- 不编造数据，推断须标注
- 创建: 信息足时输出JSON代码块:
```json
{"action":"create","name":"","type":"","cycle_type":"weekly","cycle_weekdays":"","cycle_week_parity":"","cycle_target_months":"","cycle_month_days":"","freq_per_month":0,"executor":"","owner":"","duration_minutes":0,"has_sop":"n","fixed_start_time":""}
```
⚠️ 创建前必须检查以下字段，缺失任一则先追问不可直接创建：
- name(名称): 必填
- type(类型): 必填，从已有数据选或合理推断
- executor(执行人): 必填，必须是可选人名之一
- owner(Owner): 必填，必须是可选人名之一
- fixed_start_time: 如果用户提到具体时间(如"17:30""下午5点")，必须填入HH:MM格式；没提则留空
- 修改: 输出JSON代码块:
```json
{"action":"update","ids":[1,2],"changes":{"duration_minutes":360}}
```
- 批量停用:
```json
{"action":"deactivate","ids":[1,2,3]}
```
- 拆分(将单次工时拆为多片均分执行):
```json
{"action":"split","ids":[1,2],"pieces":3}
```
- 清除拆分(合并回单条):
```json
{"action":"clear_split","ids":[1]}
```
- 信息不足先追问"""

def _build_name_map(conn):
    users = conn.execute("SELECT id, display_name, username FROM users WHERE is_active=1").fetchall()
    name_to_code = {}
    code_to_name = {}
    for i, u in enumerate(users, 1):
        real = u['display_name'] or u['username']
        code = "员工{}".format(i)
        name_to_code[real] = code
        code_to_name[code] = real
    return name_to_code, code_to_name

def _desensitize(text, name_map):
    for real, code in name_map.items():
        text = text.replace(real, code)
    return text

def _restore(text, code_map):
    for code, real in code_map.items():
        text = text.replace(code, real)
    return text

@work_mgmt_bp.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    """AI对话代理接口 - 含用户上下文与数据分析"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': '请求数据解析失败: ' + str(e)}), 400

    try:
        messages = data.get('messages', [])
        current_user_id = session.get('user_id') or data.get('current_user_id')
        ai_module = data.get('module', 'tasks')  # tasks or recurring
        if not messages:
            return jsonify({'success': False, 'message': '消息不能为空'}), 400

        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not api_key:
            return jsonify({'success': False, 'message': 'AI服务未配置'}), 500
        from datetime import datetime as _dt_now
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')

        # 意图分类: 判断是否需要数据上下文
        last_msg = messages[-1]['content'] if messages else ''
        _ANALYSIS_KW = ('进度','分析','工时','耗时','统计','概览','多少','最忙','分布','类型','完成','待办','进行','验收','花多少','月均','谁','排名','趋势','对比','修改','创建','改','巡','查','找','调')
        need_data = any(k in last_msg for k in _ANALYSIS_KW) or ai_module == 'tasks'

        ctx = ""
        conn = get_db()
        _name_map, _code_map = {}, {}
        try:
            _name_map, _code_map = _build_name_map(conn)
            # 始终注入: 当前用户(极短)
            if current_user_id:
                u = conn.execute('SELECT id,display_name,username FROM users WHERE id=?', (current_user_id,)).fetchone()
                if u:
                    ctx += "\n用户:{}({})".format(u['display_name'] or u['username'], u['id'])

            if need_data:
                # 任务概况
                ts = conn.execute('SELECT status,COUNT(*) as cnt FROM tasks GROUP BY status').fetchall()
                if ts:
                    sm = {'pending':'待办','in_progress':'进行中','pending_review':'待验收','completed':'已完成'}
                    ctx += "\n## 任务概况\n" + "、".join(["{}:{}".format(sm.get(r['status'],r['status']),r['cnt']) for r in ts])
                # 近期待办
                up = conn.execute("SELECT t.title,u.display_name as en,t.expected_end,t.status,t.estimated_minutes FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress') ORDER BY t.expected_end LIMIT 8").fetchall()
                if up:
                    ctx += "\n## 待办\n" + "\n".join(["- {}|{}|截止{}|{}min|{}".format(r['title'],r['en'] or '?',r['expected_end'] or '无',r['estimated_minutes'] or 0,r['status']) for r in up])
                # 活跃任务明细(供AI检索和修改,tasks模块)
                td = conn.execute("SELECT t.id,t.task_no,t.title,u.display_name as en,t.status,t.expected_end,t.estimated_minutes FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress','pending_review') ORDER BY t.expected_end").fetchall()
                if td:
                    sm2 = {'pending':'待办','in_progress':'进行中','pending_review':'待验收'}
                    ctx += "\n## 活跃任务明细\n" + "\n".join(["- {}|{}|{}|{}|截止{}|{}min".format(r['task_no'] or ('#'+str(r['id'])),r['title'],r['en'] or '?',sm2.get(r['status'],r['status']),r['expected_end'] or '?',r['estimated_minutes'] or 0) for r in td])
                # 已完成(含耗时)
                done = conn.execute("SELECT t.title,u.display_name as en,t.estimated_minutes,t.started_at,t.submitted_at FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status='completed' AND t.started_at AND t.submitted_at ORDER BY t.submitted_at DESC LIMIT 10").fetchall()
                if done:
                    rows = []
                    for r in done:
                        try:
                            from datetime import datetime
                            actual = int((datetime.strptime(r['submitted_at'],'%Y-%m-%d %H:%M:%S') - datetime.strptime(r['started_at'],'%Y-%m-%d %H:%M:%S')).total_seconds()/60)
                            rows.append("- {}|{}|预估{}min|实际{}min".format(r['title'],r['en'] or '?',r['estimated_minutes'] or 0,actual))
                        except:
                            rows.append("- {}|{}|预估{}min".format(r['title'],r['en'] or '?',r['estimated_minutes'] or 0))
                    ctx += "\n## 已完成\n" + "\n".join(rows)
                # 周期性工作分布
                cyc = conn.execute("SELECT type,COUNT(*) as cnt,ROUND(SUM(avg_monthly_hours),1) as hrs FROM recurring_tasks WHERE is_active=1 GROUP BY type ORDER BY hrs DESC").fetchall()
                if cyc:
                    ctx += "\n## 周期性工作\n" + "\n".join(["- {}:{}项,月均{}h".format(r['type'],r['cnt'],r['hrs']) for r in cyc[:8]])
                # 综合工时: 周期性工作 + 任务管理待办
                ex = conn.execute("SELECT u.display_name as n,ROUND(SUM(r.avg_monthly_hours),1) as h,COUNT(*) as c FROM recurring_tasks r LEFT JOIN users u ON r.executor_id=u.id WHERE r.is_active=1 GROUP BY r.executor_id ORDER BY h DESC").fetchall()
                # 任务管理各执行人待办数
                tp = conn.execute("SELECT u.display_name as n,COUNT(*) as c,GROUP_CONCAT(CASE WHEN t.status='pending' THEN '待办' WHEN t.status='in_progress' THEN '进行中' WHEN t.status='pending_review' THEN '待验收' END) as sts FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress','pending_review') GROUP BY t.executor_id").fetchall()
                if ex or tp:
                    ctx += "\n## 综合工时(周期性+任务管理)\n"
                    all_names = set()
                    recur_map = {}
                    for r in ex or []:
                        recur_map[r['n'] or '?'] = (r['c'], r['h'])
                        all_names.add(r['n'] or '?')
                    task_map = {}
                    for r in tp or []:
                        task_map[r['n'] or '?'] = (r['c'], r['sts'] or '')
                        all_names.add(r['n'] or '?')
                    for name in sorted(all_names):
                        rc, rh = recur_map.get(name, (0, 0))
                        tc, ts = task_map.get(name, (0, ''))
                        parts = ["周期性{}项/月均{}h".format(rc, rh)] if rc else ["无周期性工作"]
                        if tc:
                            parts.append("待办任务{}项".format(tc))
                        ctx += "\n- {}: ".format(name) + "|".join(parts)
            # 周期性工作明细(tasks模块也看)
            if need_data:
                ritems = conn.execute("SELECT r.name,r.type,u.display_name as en,r.freq_per_month,r.duration_minutes,r.avg_monthly_hours FROM recurring_tasks r LEFT JOIN users u ON r.executor_id=u.id WHERE r.is_active=1 ORDER BY r.type,r.name LIMIT 20").fetchall()
                if ritems:
                    ctx += "\n## 周期性工作明细\n" + "\n".join(["- {}|{}|{}|{}次/月|{}min|月均{}h".format(r['name'],r['type'],r['en'] or '?',r['freq_per_month'],r['duration_minutes'],r['avg_monthly_hours']) for r in ritems])
            # 周期性工作明细(仅recurring模块)
            if ai_module == 'recurring' and need_data:
                items = conn.execute("SELECT r.id,r.name,r.type,r.cycle_type,r.freq_per_month,r.duration_minutes,r.avg_monthly_hours,r.has_sop,r.is_active,r.fixed_start_time,r.split_pattern,u.display_name as en FROM recurring_tasks r LEFT JOIN users u ON r.executor_id=u.id WHERE r.is_active=1 ORDER BY r.type,r.name").fetchall()
                if items:
                    ctx += "\n## 周期性工作明细\n" + "\n".join(["- #{}|{}|{}|{}|{}次/月|{}min|月均{}h|SOP:{}|{}|固定:{}|{}".format(r['id'],r['name'],r['type'],r['en'] or '?',r['freq_per_month'],r['duration_minutes'],r['avg_monthly_hours'],r['has_sop'] or 'n','启用' if r['is_active'] else '停用',r['fixed_start_time'] or '无',str(len(__import__('json').loads(r['split_pattern'])))+'片' if r['split_pattern'] else '未拆') for r in items])
                # 异常检测
                anomalies = []
                for r in items or []:
                    if r['avg_monthly_hours'] and r['avg_monthly_hours'] > 20:
                        anomalies.append("{}月均{}h(>20h异常高)".format(r['name'], r['avg_monthly_hours']))
                    if not r['has_sop'] or r['has_sop'] == 'n':
                        anomalies.append("{}无SOP".format(r['name']))
                    if not r['freq_per_month'] or r['freq_per_month'] == 0:
                        anomalies.append("{}频次=0(数据缺失)".format(r['name']))
                # 负荷预警
                ex_load = conn.execute("SELECT u.display_name as n,ROUND(SUM(r.avg_monthly_hours),1) as h FROM recurring_tasks r LEFT JOIN users u ON r.executor_id=u.id WHERE r.is_active=1 GROUP BY r.executor_id ORDER BY h DESC").fetchall()
                for r in ex_load or []:
                    if r['h'] and r['h'] > 70:
                        anomalies.append("{}周期性月均{}h(>70h占比超40%)".format(r['n'], r['h']))
                if anomalies:
                    ctx += "\n## 异常/预警\n" + "\n".join(["- "+a for a in anomalies[:15]])
                # 任务管理概况
                ts = conn.execute('SELECT status,COUNT(*) as cnt FROM tasks GROUP BY status').fetchall()
                if ts:
                    sm = {'pending':'待办','in_progress':'进行中','pending_review':'待验收','completed':'已完成'}
                    ctx += "\n## 任务管理概况\n" + "、".join(["{}:{}".format(sm.get(r['status'],r['status']),r['cnt']) for r in ts])
                # 活跃任务明细(供AI检索和修改)
                td = conn.execute("SELECT t.id,t.task_no,t.title,u.display_name as en,t.status,t.expected_end,t.estimated_minutes FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress','pending_review') ORDER BY t.expected_end").fetchall()
                if td:
                    sm2 = {'pending':'待办','in_progress':'进行中','pending_review':'待验收'}
                    ctx += "\n## 活跃任务明细\n" + "\n".join(["- {}|{}|{}|{}|截止{}|{}min".format(r['task_no'] or ('#'+str(r['id'])),r['title'],r['en'] or '?',sm2.get(r['status'],r['status']),r['expected_end'] or '?',r['estimated_minutes'] or 0) for r in td])
                tp = conn.execute("SELECT u.display_name as n,COUNT(*) as c FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress','pending_review') GROUP BY t.executor_id").fetchall()
                if tp:
                    ctx += "\n## 任务管理待办\n" + "\n".join(["- {}: {}条待办".format(r['n'] or '?',r['c']) for r in tp])
                # 综合工时(周期性+任务管理)
                ex = conn.execute("SELECT u.display_name as n,ROUND(SUM(r.avg_monthly_hours),1) as h,COUNT(*) as c FROM recurring_tasks r LEFT JOIN users u ON r.executor_id=u.id WHERE r.is_active=1 GROUP BY r.executor_id ORDER BY h DESC").fetchall()
                tp2 = conn.execute("SELECT u.display_name as n,COUNT(*) as c FROM tasks t LEFT JOIN users u ON t.executor_id=u.id WHERE t.status IN ('pending','in_progress','pending_review') GROUP BY t.executor_id").fetchall()
                if ex or tp2:
                    ctx += "\n## 综合工时(周期性+任务管理)\n"
                    all_names = set()
                    recur_map = {}
                    for r in ex or []:
                        recur_map[r['n'] or '?'] = (r['c'], r['h'])
                        all_names.add(r['n'] or '?')
                    task_map = {}
                    for r in tp2 or []:
                        task_map[r['n'] or '?'] = r['c']
                        all_names.add(r['n'] or '?')
                    for name in sorted(all_names):
                        rc, rh = recur_map.get(name, (0, 0))
                        tc = task_map.get(name, 0)
                        parts = ["周期性{}项/月均{}h".format(rc, rh)] if rc else ["无周期性工作"]
                        if tc:
                            parts.append("待办任务{}项".format(tc))
                        ctx += "\n- {}: ".format(name) + "|".join(parts)
            else:
                # 创建类: 只给执行人列表
                ctx += "\n可选执行人:" + "/".join(_name_map.values())
        finally:
            conn.close()

        # 注入今日日期
        ctx = "\n今日日期:" + _g_dt_now.now().strftime("%Y-%m-%d %H:%M") + ctx
        # 脱敏: 发给AI前替换真实人名
        ctx = _desensitize(ctx, _name_map)
        system_content = (RECURRING_SYSTEM_PROMPT if ai_module == 'recurring' else TASK_MGMT_SYSTEM_PROMPT) + ctx
        # 消息窗口: 只取最近8轮
        recent = messages[-8:] if len(messages) > 8 else messages
        # 脱敏: 用户消息中的人名也替换
        recent_d = [{'role': m['role'], 'content': _desensitize(m['content'], _name_map)} for m in recent]
        full_messages = [{'role': 'system', 'content': system_content}] + recent_d

        response = client.chat.completions.create(
            model='deepseek-v4-flash',
            messages=full_messages,
            stream=False,
            max_tokens=2048
        )

        reply = response.choices[0].message.content
        # 还原: AI回复中的代号还原为真实人名
        reply = _restore(reply, _code_map)
        # 持久化对话记录
        if current_user_id:
            try:
                conn = get_db()
                for m in messages[-3:]:
                    conn.execute('INSERT INTO ai_chat_messages(user_id,role,content,module) VALUES(?,?,?,?)', (current_user_id, m['role'], _restore(m['content'], _code_map), ai_module))
                conn.execute('INSERT INTO ai_chat_messages(user_id,role,content,module) VALUES(?,?,?,?)', (current_user_id, 'assistant', reply, ai_module))
                conn.commit()
                conn.close()
            except:
                pass
        return jsonify({'success': True, 'reply': reply})
    except Exception as e:
        import traceback as _tb; _tb.print_exc(); open('/tmp/ai_error.log','a').write(_tb.format_exc() + '\n')
        return jsonify({'success': False, 'message': 'AI调用失败: ' + str(e)}), 500


@work_mgmt_bp.route('/api/ai/chat/history', methods=['GET'])
def api_ai_chat_history():
    """获取当前用户AI对话历史"""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'success': True, 'messages': []})
    conn = get_db()
    try:
        mod = request.args.get('module', 'tasks')
        rows = conn.execute('SELECT role,content,created_at FROM ai_chat_messages WHERE user_id=? AND module=? ORDER BY id ASC', (uid, mod)).fetchall()
        return jsonify({'success': True, 'messages': [{'role': r['role'], 'content': r['content'], 'created_at': r['created_at']} for r in rows]})
    finally:
        conn.close()


@work_mgmt_bp.route('/api/ai/chat/clear', methods=['DELETE'])
def api_ai_chat_clear():
    """清空当前用户AI对话历史"""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'success': False, 'message': '未登录'}), 400
    conn = get_db()
    try:
        mod = request.args.get('module', 'tasks')
        conn.execute('DELETE FROM ai_chat_messages WHERE user_id=? AND module=?', (uid, mod))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()
