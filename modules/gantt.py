from flask import Blueprint, render_template, request, jsonify, session, redirect
import sqlite3
from functools import wraps

gantt_bp = Blueprint('gantt', __name__, url_prefix='/work-mgmt/gantt')

DB_PATH = '/var/www/apps/P032-restaurant-digital-reform/database.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

# ========== Page ==========
@gantt_bp.route('/')
@require_login
def gantt_page():
    return render_template('work_gantt.html')

# ========== Modules CRUD ==========
@gantt_bp.route('/api/modules', methods=['GET'])
def api_modules_list():
    conn = get_db()
    rows = conn.execute('SELECT * FROM gantt_modules ORDER BY sort_order, id').fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

@gantt_bp.route('/api/modules', methods=['POST'])
def api_modules_create():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO gantt_modules (name, color_index, sort_order) VALUES (?, ?, ?)',
                   (data.get('name', ''), data.get('color_index', 0), data.get('sort_order', 0)))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@gantt_bp.route('/api/modules/<int:module_id>', methods=['PUT'])
def api_modules_update(module_id):
    data = request.get_json()
    conn = get_db()
    conn.execute('UPDATE gantt_modules SET name=?, color_index=?, sort_order=?, updated_at=datetime("now","localtime") WHERE id=?',
                 (data.get('name', ''), data.get('color_index', 0), data.get('sort_order', 0), module_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@gantt_bp.route('/api/modules/<int:module_id>', methods=['DELETE'])
def api_modules_delete(module_id):
    conn = get_db()
    conn.execute('DELETE FROM gantt_modules WHERE id=?', (module_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== Projects CRUD ==========
@gantt_bp.route('/api/projects', methods=['GET'])
def api_projects_list():
    conn = get_db()
    rows = conn.execute('SELECT * FROM gantt_projects ORDER BY module_id, sort_order, id').fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

@gantt_bp.route('/api/projects', methods=['POST'])
def api_projects_create():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO gantt_projects (module_id, name, description, sort_order) VALUES (?, ?, ?, ?)',
                   (data.get('module_id'), data.get('name', ''), data.get('description', ''), data.get('sort_order', 0)))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@gantt_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
def api_projects_update(project_id):
    data = request.get_json()
    conn = get_db()
    conn.execute('UPDATE gantt_projects SET module_id=?, name=?, description=?, sort_order=?, updated_at=datetime("now","localtime") WHERE id=?',
                 (data.get('module_id'), data.get('name', ''), data.get('description', ''), data.get('sort_order', 0), project_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@gantt_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
def api_projects_delete(project_id):
    conn = get_db()
    conn.execute('DELETE FROM gantt_projects WHERE id=?', (project_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== Tasks CRUD ==========
@gantt_bp.route('/api/tasks', methods=['GET'])
def api_tasks_list():
    conn = get_db()
    rows = conn.execute('SELECT * FROM gantt_tasks ORDER BY project_id, sort_order, id').fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

@gantt_bp.route('/api/tasks', methods=['POST'])
def api_tasks_create():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO gantt_tasks (project_id, name, start_date, end_date, is_milestone, progress, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (data.get('project_id'), data.get('name', ''), data.get('start_date', ''), data.get('end_date', ''),
                    data.get('is_milestone', 0), data.get('progress', 0), data.get('sort_order', 0)))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@gantt_bp.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_tasks_update(task_id):
    data = request.get_json()
    conn = get_db()
    # actual_completion_date 仅在 payload 显式提供时才更新，
    # 避免编辑保存时因前端匹配失败把已填的实际完成日期误清空
    if 'actual_completion_date' in data:
        conn.execute('''UPDATE gantt_tasks SET project_id=?, name=?, start_date=?, end_date=?, 
                        is_milestone=?, progress=?, sort_order=?, actual_completion_date=?, updated_at=datetime("now","localtime") WHERE id=?''',
                     (data.get('project_id'), data.get('name', ''), data.get('start_date', ''), data.get('end_date', ''),
                      data.get('is_milestone', 0), data.get('progress', 0), data.get('sort_order', 0), 
                      data.get('actual_completion_date'), task_id))
    else:
        conn.execute('''UPDATE gantt_tasks SET project_id=?, name=?, start_date=?, end_date=?, 
                        is_milestone=?, progress=?, sort_order=?, updated_at=datetime("now","localtime") WHERE id=?''',
                     (data.get('project_id'), data.get('name', ''), data.get('start_date', ''), data.get('end_date', ''),
                      data.get('is_milestone', 0), data.get('progress', 0), data.get('sort_order', 0), task_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@gantt_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_tasks_delete(task_id):
    conn = get_db()
    conn.execute('DELETE FROM gantt_tasks WHERE id=?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== Task Completion ==========
@gantt_bp.route('/api/tasks/<int:task_id>/complete', methods=['PUT'])
def api_tasks_complete(task_id):
    data = request.get_json()
    conn = get_db()
    actual_date = data.get('actual_completion_date')  # null to clear, date string to set
    conn.execute('UPDATE gantt_tasks SET actual_completion_date=?, progress=?, updated_at=datetime("now","localtime") WHERE id=?',
                 (actual_date, 100 if actual_date else 0, task_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== Batch save (for text format parsing) ==========
@gantt_bp.route('/api/batch-save', methods=['POST'])
def api_batch_save():
    """Save the entire gantt data structure from the text format.

    Diff-by-name strategy: existing rows are matched by (name [+ parent]) and
    UPDATED in place so primary keys stay stable across saves; only genuinely
    new rows are INSERTed and rows missing from the text are DELETEd.
    actual_completion_date is never touched here, keeping completion checks safe.
    """
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    existing_modules = {r['name']: r['id'] for r in
                        cursor.execute('SELECT id, name FROM gantt_modules').fetchall()}
    existing_projects = {(r['module_id'], r['name']): r['id'] for r in
                         cursor.execute('SELECT id, module_id, name FROM gantt_projects').fetchall()}
    existing_tasks = {}
    for r in cursor.execute('SELECT id, project_id, name, start_date FROM gantt_tasks').fetchall():
        existing_tasks.setdefault(r['project_id'], {})[(r['name'], r['start_date'])] = r['id']

    seen_mod_ids, seen_proj_ids, seen_task_ids = set(), set(), set()

    for order_m, mod in enumerate(data.get('modules', [])):
        m_name = mod.get('name', '')
        if m_name in existing_modules:
            m_id = existing_modules[m_name]
            cursor.execute('UPDATE gantt_modules SET color_index=?, sort_order=? WHERE id=?',
                           (mod.get('color_index', 0), order_m, m_id))
        else:
            cursor.execute('INSERT INTO gantt_modules (name, color_index, sort_order) VALUES (?, ?, ?)',
                           (m_name, mod.get('color_index', 0), order_m))
            m_id = cursor.lastrowid
            existing_modules[m_name] = m_id
        seen_mod_ids.add(m_id)

        for order_p, proj in enumerate(mod.get('projects', [])):
            p_key = (m_id, proj.get('name', ''))
            if p_key in existing_projects:
                p_id = existing_projects[p_key]
                cursor.execute('UPDATE gantt_projects SET description=?, sort_order=? WHERE id=?',
                               (proj.get('description', ''), order_p, p_id))
            else:
                cursor.execute('INSERT INTO gantt_projects (module_id, name, description, sort_order) VALUES (?, ?, ?, ?)',
                               (m_id, proj.get('name', ''), proj.get('description', ''), order_p))
                p_id = cursor.lastrowid
                existing_projects[p_key] = p_id
            seen_proj_ids.add(p_id)

            ptasks = existing_tasks.setdefault(p_id, {})
            for order_t, task in enumerate(proj.get('tasks', [])):
                t_key = (task.get('name', ''), task.get('start_date', ''))
                if t_key in ptasks:
                    t_id = ptasks[t_key]
                    cursor.execute('UPDATE gantt_tasks SET end_date=?, is_milestone=?, progress=?, sort_order=? WHERE id=?',
                                   (task.get('end_date', ''), task.get('is_milestone', 0),
                                    task.get('progress', 0), order_t, t_id))
                else:
                    cursor.execute('INSERT INTO gantt_tasks (project_id, name, start_date, end_date, is_milestone, progress, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
                                   (p_id, task.get('name', ''), task.get('start_date', ''), task.get('end_date', ''),
                                    task.get('is_milestone', 0), task.get('progress', 0), order_t))
                    t_id = cursor.lastrowid
                    ptasks[t_key] = t_id
                seen_task_ids.add(t_id)

    # Delete rows that no longer exist in the text (tasks first, then projects, then modules)
    all_task_ids = {r['id'] for r in cursor.execute('SELECT id FROM gantt_tasks').fetchall()}
    cursor.executemany('DELETE FROM gantt_tasks WHERE id=?',
                       [(i,) for i in all_task_ids - seen_task_ids])
    all_proj_ids = {r['id'] for r in cursor.execute('SELECT id FROM gantt_projects').fetchall()}
    cursor.executemany('DELETE FROM gantt_projects WHERE id=?',
                       [(i,) for i in all_proj_ids - seen_proj_ids])
    all_mod_ids = {r['id'] for r in cursor.execute('SELECT id FROM gantt_modules').fetchall()}
    cursor.executemany('DELETE FROM gantt_modules WHERE id=?',
                       [(i,) for i in all_mod_ids - seen_mod_ids])

    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ========== Export Excel ==========
@gantt_bp.route('/api/export-excel', methods=['GET'])
def api_export_excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO
    from flask import send_file
    
    conn = get_db()
    modules = conn.execute('SELECT * FROM gantt_modules ORDER BY sort_order, id').fetchall()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '项目进度日程'
    
    headers = ['模块', '项目', '任务', '开始日期', '结束日期', '里程碑', '进度(%)', '实际完成日期']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(1, col, h)
        cell.font = Font(name='Noto Sans SC', bold=True, color='FFFFFF', size=11)
        cell.fill = PatternFill(start_color='2D4A3E', end_color='2D4A3E', fill_type='solid')
    
    row_idx = 2
    for mod in modules:
        projects = conn.execute('SELECT * FROM gantt_projects WHERE module_id=? ORDER BY sort_order, id', (mod['id'],)).fetchall()
        for proj in projects:
            tasks = conn.execute('SELECT * FROM gantt_tasks WHERE project_id=? ORDER BY sort_order, id', (proj['id'],)).fetchall()
            if not tasks:
                ws.cell(row_idx, 1, mod['name'])
                ws.cell(row_idx, 2, proj['name'])
                row_idx += 1
            for task in tasks:
                ws.cell(row_idx, 1, mod['name'])
                ws.cell(row_idx, 2, proj['name'])
                ws.cell(row_idx, 3, task['name'])
                ws.cell(row_idx, 4, task['start_date'])
                ws.cell(row_idx, 5, task['end_date'])
                ws.cell(row_idx, 6, '是' if task['is_milestone'] else '否')
                ws.cell(row_idx, 7, task['progress'])
                ws.cell(row_idx, 8, task['actual_completion_date'] or '')
                row_idx += 1
    
    for col in range(1, len(headers) + 1):
        max_len = max(len(str(ws.cell(r, col).value or '')) for r in range(1, row_idx))
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = min(max_len + 2, 40)
    
    conn.close()
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='项目进度日程.xlsx')
