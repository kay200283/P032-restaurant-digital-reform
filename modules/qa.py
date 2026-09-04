#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P032 QA管理模块"""

from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, send_from_directory
from init_db import get_db
from modules.auth import login_required
import os, uuid, re, json
from datetime import datetime

qa_bp = Blueprint('qa', __name__, url_prefix='/qa')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'qa_attachments')
ALLOWED_EXT = {'png','jpg','jpeg','gif','bmp','webp','pdf','doc','docx','xls','xlsx','ppt','pptx','txt','csv','zip','rar'}
IMG_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}


def _gen_qa_no(conn):
    """生成QA编号: QA + 年月 + 4位流水"""
    now = datetime.now()
    prefix = f"QA{now.strftime('%y%m')}"
    row = conn.execute(
        "SELECT qa_no FROM qa_items WHERE qa_no LIKE ? ORDER BY qa_no DESC LIMIT 1",
        (prefix + '%',)
    ).fetchone()
    if row:
        seq = int(row['qa_no'][-4:]) + 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def _extract_keywords(text):
    """从文本提取关键词(简单实现: jieba不可用时用正则分词)"""
    if not text:
        return ''
    try:
        import jieba
        import jieba.analyse
        tags = jieba.analyse.extract_tags(text, topK=6, withWeight=False)
        return ','.join(tags)
    except ImportError:
        # fallback: 用正则提取中文词和英文词
        cn = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        en = re.findall(r'[a-zA-Z]{3,}', text)
        words = cn[:5] + en[:3]
        return ','.join(words)


# ============ 页面 ============
@qa_bp.route('/')
@login_required
def qa_page():
    return render_template('qa.html')


# ============ API: 列表 ============
@qa_bp.route('/api/qa', methods=['GET'])
@login_required
def api_qa_list():
    conn = get_db()
    status_filter = request.args.get('status', '')
    cat_filter = request.args.get('cat1', '')
    kw = request.args.get('keyword', '').strip()

    sql = '''SELECT id, qa_no, cat1, cat2, cat3, cat4, question,
             author, version, status, keywords, manual_keywords,
             created_at, updated_at
             FROM qa_items WHERE 1=1'''
    params = []
    if status_filter:
        sql += ' AND status=?'
        params.append(status_filter)
    if cat_filter:
        sql += ' AND cat1=?'
        params.append(cat_filter)
    if kw:
        sql += ' AND (question LIKE ? OR answer LIKE ? OR keywords LIKE ? OR manual_keywords LIKE ? OR qa_no LIKE ?)'
        params.extend([f'%{kw}%'] * 5)
    sql += ' ORDER BY id DESC'

    rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # 合并自动+手动关键词
        auto_kw = d.get('keywords', '').split(',') if d.get('keywords') else []
        manual_kw = d.get('manual_keywords', '').split(',') if d.get('manual_keywords') else []
        d['all_keywords'] = list(dict.fromkeys([k.strip() for k in auto_kw + manual_kw if k.strip()]))
        result.append(d)
    conn.close()
    return jsonify(result)


# ============ API: 单条 ============
@qa_bp.route('/api/qa/<int:qa_id>', methods=['GET'])
@login_required
def api_qa_detail(qa_id):
    conn = get_db()
    r = conn.execute('SELECT * FROM qa_items WHERE id=?', (qa_id,)).fetchone()
    if not r:
        conn.close()
        return jsonify({'success': False, 'message': '未找到'}), 404
    d = dict(r)
    # 附件
    atts = conn.execute('SELECT * FROM qa_attachments WHERE qa_id=? ORDER BY id', (qa_id,)).fetchall()
    d['attachments_list'] = [dict(a) for a in atts]
    # 版本历史
    vers = conn.execute('SELECT * FROM qa_versions WHERE qa_id=? ORDER BY version DESC', (qa_id,)).fetchall()
    d['versions'] = [dict(v) for v in vers]
    # 合并关键词
    auto_kw = d.get('keywords', '').split(',') if d.get('keywords') else []
    manual_kw = d.get('manual_keywords', '').split(',') if d.get('manual_keywords') else []
    d['all_keywords'] = list(dict.fromkeys([k.strip() for k in auto_kw + manual_kw if k.strip()]))
    conn.close()
    return jsonify(d)


# ============ API: 新建 ============
@qa_bp.route('/api/qa', methods=['POST'])
@login_required
def api_qa_create():
    conn = get_db()
    body = request.json
    qa_no = _gen_qa_no(conn)
    author = session.get('display_name', session.get('user', ''))
    author_id = session.get('user_id')

    question = body.get('question', '').strip()
    if not question:
        conn.close()
        return jsonify({'success': False, 'message': '问题不能为空'}), 400

    answer = body.get('answer', '').strip()
    cat1 = body.get('cat1', '').strip()
    cat2 = body.get('cat2', '').strip()
    cat3 = body.get('cat3', '').strip()
    cat4 = body.get('cat4', '').strip()
    manual_keywords = body.get('manual_keywords', '').strip()

    # 自动提取关键词
    combined_text = f"{question} {answer} {cat1} {cat2} {cat3} {cat4}"
    auto_keywords = _extract_keywords(combined_text)

    cur = conn.execute('''INSERT INTO qa_items
        (qa_no, cat1, cat2, cat3, cat4, question, answer, author, author_id, version, status, keywords, manual_keywords)
        VALUES (?,?,?,?,?,?,?,?,?,1,'草稿',?,?)''',
        (qa_no, cat1, cat2, cat3, cat4, question, answer, author, author_id, auto_keywords, manual_keywords))
    new_id = cur.lastrowid

    # V1版本记录
    conn.execute('''INSERT INTO qa_versions (qa_id, version, question, answer, change_note, author)
        VALUES (?,1,?,?,?,?)''', (new_id, question, answer, '初始创建', author))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id, 'qa_no': qa_no})


# ============ API: 编辑 ============
@qa_bp.route('/api/qa/<int:qa_id>', methods=['PUT'])
@login_required
def api_qa_update(qa_id):
    conn = get_db()
    r = conn.execute('SELECT * FROM qa_items WHERE id=?', (qa_id,)).fetchone()
    if not r:
        conn.close()
        return jsonify({'success': False, 'message': '未找到'}), 404

    body = request.json
    action = body.get('action', 'save')

    if action == 'submit':
        # 提交审核
        if r['status'] != '草稿':
            conn.close()
            return jsonify({'success': False, 'message': '只有草稿状态可提交审核'}), 400
        conn.execute("UPDATE qa_items SET status='待审核', updated_at=datetime('now','localtime') WHERE id=?", (qa_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    elif action == 'approve':
        # 审核通过
        if r['status'] != '待审核':
            conn.close()
            return jsonify({'success': False, 'message': '只有待审核状态可审核通过'}), 400
        conn.execute("UPDATE qa_items SET status='生效', updated_at=datetime('now','localtime') WHERE id=?", (qa_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    elif action == 'reject':
        # 退回到草稿
        if r['status'] != '待审核':
            conn.close()
            return jsonify({'success': False, 'message': '只有待审核状态可退回'}), 400
        conn.execute("UPDATE qa_items SET status='草稿', updated_at=datetime('now','localtime') WHERE id=?", (qa_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    elif action == 'disable':
        # 停用
        if r['status'] != '生效':
            conn.close()
            return jsonify({'success': False, 'message': '只有生效状态可停用'}), 400
        conn.execute("UPDATE qa_items SET status='停用', updated_at=datetime('now','localtime') WHERE id=?", (qa_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    elif action == 'reenable':
        # 重新启用 → 草稿
        if r['status'] != '停用':
            conn.close()
            return jsonify({'success': False, 'message': '只有停用状态可重新启用'}), 400
        new_ver = r['version'] + 1
        conn.execute("UPDATE qa_items SET status='草稿', version=?, updated_at=datetime('now','localtime') WHERE id=?",
                      (new_ver, qa_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    else:
        # save: 编辑内容
        if r['status'] not in ('草稿', '待审核'):
            conn.close()
            return jsonify({'success': False, 'message': '当前状态不可编辑'}), 400

        question = body.get('question', r['question']).strip()
        answer = body.get('answer', r['answer']).strip()
        cat1 = body.get('cat1', r['cat1']).strip()
        cat2 = body.get('cat2', r['cat2']).strip()
        cat3 = body.get('cat3', r['cat3']).strip()
        cat4 = body.get('cat4', r['cat4']).strip()
        manual_keywords = body.get('manual_keywords', r['manual_keywords']).strip()
        change_note = body.get('change_note', '').strip()

        # 自动提取关键词
        combined_text = f"{question} {answer} {cat1} {cat2} {cat3} {cat4}"
        auto_keywords = _extract_keywords(combined_text)

        is_new_version = (r['status'] == '待审核') or (change_note and r['version'] >= 1)
        new_ver = r['version'] + 1 if is_new_version and change_note else r['version']
        new_status = '待审核' if is_new_version and change_note else r['status']

        # 如果是生效状态被编辑(不应该到这里，但防御)
        if r['status'] == '生效':
            new_ver = r['version'] + 1
            new_status = '草稿'
            if not change_note:
                change_note = f'V{new_ver}编辑'

        author = session.get('display_name', session.get('user', ''))

        conn.execute('''UPDATE qa_items SET cat1=?, cat2=?, cat3=?, cat4=?, question=?, answer=?,
            keywords=?, manual_keywords=?, version=?, status=?, updated_at=datetime('now','localtime')
            WHERE id=?''',
            (cat1, cat2, cat3, cat4, question, answer, auto_keywords, manual_keywords, new_ver, new_status, qa_id))

        # 记录版本
        if is_new_version and change_note:
            conn.execute('''INSERT INTO qa_versions (qa_id, version, question, answer, change_note, author)
                VALUES (?,?,?,?,?,?)''', (qa_id, new_ver, question, answer, change_note, author))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'version': new_ver, 'status': new_status})


# ============ API: 删除(仅草稿) ============
@qa_bp.route('/api/qa/<int:qa_id>', methods=['DELETE'])
@login_required
def api_qa_delete(qa_id):
    conn = get_db()
    r = conn.execute('SELECT status FROM qa_items WHERE id=?', (qa_id,)).fetchone()
    if not r:
        conn.close()
        return jsonify({'success': False, 'message': '未找到'}), 404
    if r['status'] != '草稿':
        conn.close()
        return jsonify({'success': False, 'message': '只有草稿状态可删除'}), 400
    # 删除附件文件
    atts = conn.execute('SELECT filepath FROM qa_attachments WHERE qa_id=?', (qa_id,)).fetchall()
    for a in atts:
        fp = os.path.join(UPLOAD_FOLDER, '..', a['filepath'])
        if os.path.exists(fp):
            os.remove(fp)
    conn.execute('DELETE FROM qa_attachments WHERE qa_id=?', (qa_id,))
    conn.execute('DELETE FROM qa_versions WHERE qa_id=?', (qa_id,))
    conn.execute('DELETE FROM qa_items WHERE id=?', (qa_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============ API: 上传附件 ============
@qa_bp.route('/api/qa/upload', methods=['POST'])
@login_required
def api_qa_upload():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'success': False, 'message': 'Empty filename'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'success': False, 'message': f'不支持文件类型: {ext}'}), 400

    fname = f.filename
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    is_img = ext in IMG_EXT

    if is_img:
        try:
            from PIL import Image
            img = Image.open(f.stream)
            original_mode = img.mode
            if original_mode in ('RGBA', 'P', 'LA', 'PA'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if original_mode == 'P':
                    img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            max_dim = 1200
            w, h = img.size
            if max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            unique_name = f"{uuid.uuid4().hex[:8]}.jpg"
            save_path = os.path.join(UPLOAD_FOLDER, unique_name)
            img.save(save_path, 'JPEG', quality=80, optimize=True)
        except Exception:
            f.stream.seek(0)
            unique_name = f"{uuid.uuid4().hex[:8]}.{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, unique_name)
            f.save(save_path)
    else:
        unique_name = f"{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, unique_name)
        f.save(save_path)

    url = f"/uploads/qa_attachments/{unique_name}"
    return jsonify({'success': True, 'url': url, 'filename': fname, 'is_image': is_img})


# ============ API: 绑定附件到QA ============
@qa_bp.route('/api/qa/<int:qa_id>/attachments', methods=['POST'])
@login_required
def api_qa_attach(qa_id):
    conn = get_db()
    body = request.json
    fname = body.get('filename', '')
    fpath = body.get('filepath', '')
    ftype = body.get('file_type', '')
    fsize = body.get('file_size', 0)
    is_img = body.get('is_image', 0)
    conn.execute('''INSERT INTO qa_attachments (qa_id, filename, filepath, file_type, file_size, is_image)
        VALUES (?,?,?,?,?,?)''', (qa_id, fname, fpath, ftype, fsize, is_img))
    conn.commit()
    att_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'id': att_id})


# ============ API: 删除附件 ============
@qa_bp.route('/api/qa/attachments/<int:att_id>', methods=['DELETE'])
@login_required
def api_qa_att_delete(att_id):
    conn = get_db()
    r = conn.execute('SELECT * FROM qa_attachments WHERE id=?', (att_id,)).fetchone()
    if r:
        fp = os.path.join(UPLOAD_FOLDER, '..', r['filepath'])
        if os.path.exists(fp):
            os.remove(fp)
        conn.execute('DELETE FROM qa_attachments WHERE id=?', (att_id,))
        conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============ API: 分类统计 ============
@qa_bp.route('/api/qa/stats', methods=['GET'])
@login_required
def api_qa_stats():
    conn = get_db()
    # 状态统计
    status_rows = conn.execute('SELECT status, COUNT(*) as cnt FROM qa_items GROUP BY status').fetchall()
    status_stats = {r['status']: r['cnt'] for r in status_rows}
    # 一级分类
    cat_rows = conn.execute('SELECT cat1, COUNT(*) as cnt FROM qa_items GROUP BY cat1 ORDER BY cnt DESC').fetchall()
    cat_stats = [{'cat': r['cat1'] or '未分类', 'cnt': r['cnt']} for r in cat_rows]
    conn.close()
    return jsonify({'status': status_stats, 'categories': cat_stats})
