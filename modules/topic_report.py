#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课题报告模块 - 工作管理二级模块（参考 P029 课题报告机制移植）"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from modules.auth import login_required
from init_db import get_db
import os
from datetime import date

topic_report_bp = Blueprint('topic_report', __name__, url_prefix='/work-mgmt/topic-report')

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')


def _ensure_topic_reports_table():
    """确保topic_reports表存在"""
    conn = get_db()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS topic_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            scope TEXT DEFAULT '',
            template_name TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0
        )''')
        conn.commit()
    finally:
        conn.close()


def _is_admin():
    return (session.get('role') or '') == 'admin'


def _today():
    return date.today().isoformat()


@topic_report_bp.route('')
@login_required
def topic_report_list():
    """课题报告列表页"""
    _ensure_topic_reports_table()
    conn = get_db()
    try:
        rows = conn.execute('SELECT * FROM topic_reports ORDER BY sort_order, id').fetchall()
        report_list = [dict(r) for r in rows]
    finally:
        conn.close()
    return render_template('work_topic_report.html', report_list=report_list, is_admin=_is_admin())


@topic_report_bp.route('/<int:topic_id>')
@login_required
def view_topic_report(topic_id):
    """查看课题报告（读取 templates 下报告模板文件）"""
    _ensure_topic_reports_table()
    conn = get_db()
    try:
        report = conn.execute('SELECT * FROM topic_reports WHERE id = ?', (topic_id,)).fetchone()
    finally:
        conn.close()
    if not report or not report['template_name']:
        return redirect(url_for('topic_report.topic_report_list'))
    tpl_path = os.path.join(TEMPLATES_DIR, report['template_name'])
    if not os.path.exists(tpl_path):
        return redirect(url_for('topic_report.topic_report_list'))

    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl_html = f.read()

    # 模板自带编辑工具栏或编辑器时原样返回
    has_own_edit = ('id="toolbar"' in tpl_html or 'id="edit-toolbar"' in tpl_html
                    or 'id="_rpt_toolbar"' in tpl_html or 'tinymce' in tpl_html.lower())
    if has_own_edit or not _is_admin():
        return tpl_html

    # 管理员：注入轻量编辑工具栏（contenteditable 就地编辑，保存写回模板文件）
    _tid = str(topic_id)
    toolbar = ('<div id="_rpt_toolbar" style="position:fixed;top:8px;right:12px;z-index:9999;display:flex;gap:6px;align-items:center;">'
        '<button onclick="_rptEdit()" style="padding:4px 12px;border:1px solid #2D4A3E;border-radius:4px;background:#2D4A3E;color:#fff;cursor:pointer;font-size:13px;"><i class="fa-solid fa-pen" style="margin-right:4px"></i>编辑</button>'
        '<button id="_rptSaveBtn" onclick="_rptSave()" style="padding:4px 12px;border:1px solid #2D4A3E;border-radius:4px;background:#fff;color:#2D4A3E;cursor:pointer;font-size:13px;display:none;"><i class="fa-solid fa-floppy-disk" style="margin-right:4px"></i>保存</button>'
        '<button id="_rptCancelBtn" onclick="_rptCancel()" style="padding:4px 12px;border:1px solid #999;border-radius:4px;background:#fff;color:#999;cursor:pointer;font-size:13px;display:none;">取消</button>'
        '<span id="_rptStatus" style="font-size:12px;color:#999;"></span></div>'
        '<script>'
        'var _rptEditing=false,_rptTopicId='+_tid+';document.body.contentEditable=false;var _d=document.getElementById("doc");if(_d)_d.contentEditable=false;'
        'function _rptEdit(){document.body.contentEditable=true;var _d=document.getElementById("doc");if(_d)_d.contentEditable=true;_rptEditing=true;document.getElementById("_rptSaveBtn").style.display="";document.getElementById("_rptCancelBtn").style.display="";document.getElementById("_rptStatus").textContent="编辑模式";document.body.style.outline="2px dashed #2D4A3E"}'
        'function _rptCancel(){document.body.contentEditable=false;var _d=document.getElementById("doc");if(_d)_d.contentEditable=false;_rptEditing=false;document.getElementById("_rptSaveBtn").style.display="none";document.getElementById("_rptCancelBtn").style.display="none";document.getElementById("_rptStatus").textContent="";document.body.style.outline="";location.reload()}'
        'function _rptSave(){if(!_rptEditing)return;var h=document.documentElement.outerHTML;document.getElementById("_rptStatus").textContent="保存中...";fetch("/work-mgmt/topic-report/"+_rptTopicId+"/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({html:h,full_html:true})}).then(r=>r.json()).then(d=>{if(d.success){document.body.contentEditable=false;var _d=document.getElementById("doc");if(_d)_d.contentEditable=false;_rptEditing=false;document.getElementById("_rptSaveBtn").style.display="none";document.getElementById("_rptCancelBtn").style.display="none";document.getElementById("_rptStatus").textContent="已保存";document.body.style.outline="";setTimeout(()=>{document.getElementById("_rptStatus").textContent=""},2000)}else{alert(d.message||"保存失败");document.getElementById("_rptStatus").textContent=""}}).catch(e=>{alert("保存出错");document.getElementById("_rptStatus").textContent=""})}'
        '</script>')
    import re as _re
    tpl_html = _re.sub(r'\s*contenteditable="true"', '', tpl_html, flags=_re.IGNORECASE)
    tpl_html = _re.sub(r'<div[^>]*id="toolbar"[^>]*>.*?</div>', '', tpl_html, flags=_re.DOTALL | _re.IGNORECASE)
    tpl_html = _re.sub(r'<div[^>]*id="_rpt_toolbar"[^>]*>.*?</div>', '', tpl_html, flags=_re.DOTALL | _re.IGNORECASE)
    tpl_html = _re.sub(r'<script>var _rptEditing=.*?</script>', '', tpl_html, flags=_re.DOTALL)
    if '</body>' in tpl_html:
        tpl_html = tpl_html.replace('</body>', toolbar + '</body>')
    return tpl_html


@topic_report_bp.route('/<int:topic_id>/save', methods=['POST'])
@login_required
def save_topic_report(topic_id):
    """保存课题报告编辑内容（全量写回模板文件，仅管理员）"""
    if not _is_admin():
        return jsonify({'success': False, 'message': '仅管理员可编辑报告'}), 403
    data = request.get_json(silent=True)
    if not data or 'html' not in data:
        return jsonify({'success': False, 'message': '缺少html参数'})

    conn = get_db()
    try:
        row = conn.execute('SELECT template_name FROM topic_reports WHERE id = ?', (topic_id,)).fetchone()
    finally:
        conn.close()
    if not row or not row['template_name']:
        return jsonify({'success': False, 'message': '报告不存在'})
    template_path = os.path.join(TEMPLATES_DIR, row['template_name'])
    if not os.path.exists(template_path):
        return jsonify({'success': False, 'message': '报告文件不存在'})

    import re as _re
    _cleaned = data['html']
    # 剥离运行时注入，防止写回模板
    _cleaned = _re.sub(r'<div[^>]*id="_rpt_toolbar"[^>]*>.*?</div>', '', _cleaned, flags=_re.DOTALL | _re.IGNORECASE)
    _cleaned = _re.sub(r'<script>var _rptEditing=.*?</script>', '', _cleaned, flags=_re.DOTALL)
    _cleaned = _re.sub(r'\s*contenteditable="true"', '', _cleaned, flags=_re.IGNORECASE)
    _cleaned = _re.sub(r'(<body[^>]*?)\s+contenteditable="true"', r'\1', _cleaned, flags=_re.IGNORECASE)
    _cleaned = _re.sub(r'(<body[^>]*?)\s+style="outline:\s*rgb\(45,\s*74,\s*62\)\s+dashed\s*2px;?"', r'\1', _cleaned, flags=_re.IGNORECASE)

    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(_cleaned)

    conn = get_db()
    try:
        conn.execute('UPDATE topic_reports SET updated_at = ? WHERE id = ?', (_today(), topic_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'message': '保存成功'})


@topic_report_bp.route('/api/report', methods=['POST'])
@login_required
def create_report():
    """新增报告登记（仅管理员，模板文件需已存在于 templates/）"""
    if not _is_admin():
        return jsonify({'success': False, 'message': '仅管理员可操作'}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'message': '请填写报告名称'})
    template_name = (data.get('template_name') or '').strip()
    if template_name and ('/' in template_name or '..' in template_name or not template_name.endswith('.html')):
        return jsonify({'success': False, 'message': '模板文件名不合法'})
    if template_name and not os.path.exists(os.path.join(TEMPLATES_DIR, template_name)):
        return jsonify({'success': False, 'message': '模板文件不存在，请先将报告 HTML 上传至 templates/ 目录'}), 400
    try:
        sort_order = int(data.get('sort_order') or 0)
    except (TypeError, ValueError):
        sort_order = 0
    created_at = (data.get('created_at') or _today()).strip()
    updated_at = (data.get('updated_at') or created_at).strip()
    conn = get_db()
    try:
        conn.execute('''INSERT INTO topic_reports
            (title, description, scope, template_name, created_by, created_at, updated_at, sort_order)
            VALUES (?,?,?,?,?,?,?,?)''', (
            title, (data.get('description') or '').strip(), (data.get('scope') or '').strip(),
            template_name, (data.get('created_by') or session.get('display_name') or session.get('user') or '').strip(),
            created_at, updated_at, sort_order))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'message': '报告登记成功'})


@topic_report_bp.route('/api/report/<int:report_id>', methods=['PUT'])
@login_required
def update_report(report_id):
    """编辑报告登记信息（仅管理员）"""
    if not _is_admin():
        return jsonify({'success': False, 'message': '仅管理员可操作'}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'message': '请填写报告名称'})
    template_name = (data.get('template_name') or '').strip()
    if template_name and ('/' in template_name or '..' in template_name or not template_name.endswith('.html')):
        return jsonify({'success': False, 'message': '模板文件名不合法'})
    if template_name and not os.path.exists(os.path.join(TEMPLATES_DIR, template_name)):
        return jsonify({'success': False, 'message': '模板文件不存在，请先将报告 HTML 上传至 templates/ 目录'}), 400
    try:
        sort_order = int(data.get('sort_order') or 0)
    except (TypeError, ValueError):
        sort_order = 0
    conn = get_db()
    try:
        cur = conn.execute('''UPDATE topic_reports SET title=?, description=?, scope=?, template_name=?,
            created_by=?, created_at=?, updated_at=?, sort_order=? WHERE id=?''', (
            title, (data.get('description') or '').strip(), (data.get('scope') or '').strip(),
            template_name, (data.get('created_by') or '').strip(),
            (data.get('created_at') or '').strip(), (data.get('updated_at') or '').strip(), sort_order, report_id))
        if cur.rowcount == 0:
            return jsonify({'success': False, 'message': '报告不存在'}), 404
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'message': '保存成功'})


@topic_report_bp.route('/api/report/<int:report_id>', methods=['DELETE'])
@login_required
def delete_report(report_id):
    """删除报告登记（仅管理员，报告模板文件保留）"""
    if not _is_admin():
        return jsonify({'success': False, 'message': '仅管理员可操作'}), 403
    conn = get_db()
    try:
        cur = conn.execute('DELETE FROM topic_reports WHERE id = ?', (report_id,))
        if cur.rowcount == 0:
            return jsonify({'success': False, 'message': '报告不存在'}), 404
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'message': '删除成功（报告模板文件已保留）'})
