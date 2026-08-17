#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P032 餐厅数字化改革 - 数据库初始化"""

import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _migrate_columns(cursor, table, columns):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    for col_name, col_type in columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            print(f"  迁移: {table} + {col_name}")

def init_database():
    conn = get_db()
    cursor = conn.cursor()

    # ============ 用户与认证 ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'admin',
            must_change_password INTEGER DEFAULT 1,
            login_attempts INTEGER DEFAULT 0,
            locked_until TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            module TEXT,
            target_id TEXT,
            detail TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')

    # ============ 工作管理 ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recurring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT,
            cycle_rule TEXT,
            cycle_weekdays TEXT,
            cycle_month_days TEXT,
            cycle_type TEXT DEFAULT 'weekly',
            cycle_interval INTEGER DEFAULT 1,
            freq_per_month REAL,
            owner_id INTEGER REFERENCES users(id),
            executor_id INTEGER REFERENCES users(id),
            duration_minutes INTEGER NOT NULL DEFAULT 0,
            has_sop TEXT DEFAULT '否',
            avg_monthly_hours REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            fixed_start_time TEXT DEFAULT NULL,
            fixed_end_time TEXT DEFAULT NULL,
            cycle_target_months TEXT DEFAULT NULL,
            cycle_week_parity TEXT DEFAULT NULL,
            split_pattern TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_recurring_owner ON recurring_tasks(owner_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_recurring_executor ON recurring_tasks(executor_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_recurring_type ON recurring_tasks(type)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calendar_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL DEFAULT 'recurring',
            source_id INTEGER,
            executor_id INTEGER REFERENCES users(id),
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            status TEXT DEFAULT 'normal',
            transfer_to_id INTEGER REFERENCES users(id),
            priority INTEGER DEFAULT 0,
            is_overtime INTEGER DEFAULT 0,
            time_locked INTEGER DEFAULT 0,
            split_index INTEGER DEFAULT 1,
            split_total INTEGER DEFAULT 1,
            completed_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cal_executor_date ON calendar_instances(executor_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cal_date ON calendar_instances(date)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            executor_id INTEGER REFERENCES users(id),
            description TEXT,
            materials_json TEXT,
            estimated_minutes INTEGER DEFAULT 0,
            expected_end TEXT,
            status TEXT DEFAULT 'pending',
            calendar_instance_id INTEGER REFERENCES calendar_instances(id),
            completed_at TEXT,
            created_by_ai INTEGER DEFAULT 0,
            raw_input TEXT,
            created_by INTEGER REFERENCES users(id),
            result_text TEXT DEFAULT '',
            started_at TEXT DEFAULT NULL,
            submitted_at TEXT DEFAULT NULL,
            task_no TEXT DEFAULT NULL,
            reject_count INTEGER DEFAULT 0,
            last_reject_reason TEXT DEFAULT '',
            pending_result_snapshot TEXT DEFAULT '',
            pending_attach_snapshot TEXT DEFAULT '',
            start_time TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_executor ON tasks(executor_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_task_no ON tasks(task_no) WHERE task_no IS NOT NULL')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT NOT NULL,
            status TEXT DEFAULT 'approved',
            transfer_instructions TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_leave_staff_date ON leaves(staff_id, date)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            file_type TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            attach_type TEXT DEFAULT 'material',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            module TEXT DEFAULT 'tasks',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # ============ 初始管理员 ============
    admin = cursor.execute('SELECT 1 FROM users WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        pw_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        cursor.execute('INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)',
                       ('admin', pw_hash, '管理员', 'admin'))
        print('  初始管理员: admin / admin123')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_database()
    print('数据库初始化完成')
