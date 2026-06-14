"""DB schema migrations — safe to run on every startup (IF NOT EXISTS / IF EXISTS)."""
import logging
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_POSTGRES_MIGRATIONS = [
    "ALTER TABLE projects ALTER COLUMN city TYPE TEXT",
    "ALTER TABLE projects ALTER COLUMN stage TYPE TEXT",
    "ALTER TABLE project_stages ALTER COLUMN name TYPE TEXT",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS format_type VARCHAR(50) DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS open_status VARCHAR(100) DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS delay_reason TEXT DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS photo VARCHAR(200) DEFAULT ''",
    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS position VARCHAR(150) DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completion_comment TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP",
    """CREATE TABLE IF NOT EXISTS task_notifications (
        id SERIAL PRIMARY KEY,
        recipient_name VARCHAR(100) NOT NULL,
        task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
        message TEXT NOT NULL,
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "ALTER TABLE vpk_report_items ADD COLUMN IF NOT EXISTS comment TEXT DEFAULT ''",
    "ALTER TABLE vpk_report_items ADD COLUMN IF NOT EXISTS photo_path VARCHAR(300) DEFAULT ''",
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS photo_path VARCHAR(300) DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS ai_chat_messages (
        id SERIAL PRIMARY KEY,
        user_name VARCHAR(100) NOT NULL,
        role VARCHAR(20) NOT NULL,
        text TEXT NOT NULL,
        provider VARCHAR(30) DEFAULT 'groq',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS vpk_report_reads (
        id SERIAL PRIMARY KEY,
        report_id INTEGER REFERENCES vpk_reports(id) ON DELETE CASCADE NOT NULL,
        reader_name VARCHAR(100) NOT NULL,
        read_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(report_id, reader_name)
    )""",
    """CREATE TABLE IF NOT EXISTS task_photos (
        id SERIAL PRIMARY KEY,
        task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,
        photo_path VARCHAR(300) NOT NULL,
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_chat_sender_name ON chat_messages (sender_name)",
    "CREATE INDEX IF NOT EXISTS ix_vpk_report_submitted_at ON vpk_reports (submitted_at)",
    "CREATE INDEX IF NOT EXISTS ix_ai_chat_user_name ON ai_chat_messages (user_name)",
    "ALTER TABLE smr_tasks ADD COLUMN IF NOT EXISTS notified_date DATE",
    "ALTER TABLE smr_tasks ADD COLUMN IF NOT EXISTS reject_comment TEXT DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS smr_contacts (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(200) NOT NULL,
        position VARCHAR(150) DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS smr_schedules (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS smr_tasks (
        id SERIAL PRIMARY KEY,
        schedule_id INTEGER REFERENCES smr_schedules(id) ON DELETE CASCADE NOT NULL,
        name TEXT NOT NULL,
        "order" INTEGER DEFAULT 0,
        start_plan DATE,
        end_plan DATE,
        is_milestone BOOLEAN DEFAULT FALSE,
        status VARCHAR(30) DEFAULT 'Запланировано',
        notify_email1 VARCHAR(200) DEFAULT '',
        notify_email2 VARCHAR(200) DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS smr_confirmations (
        id SERIAL PRIMARY KEY,
        task_id INTEGER REFERENCES smr_tasks(id) ON DELETE CASCADE NOT NULL,
        token VARCHAR(64) UNIQUE NOT NULL,
        email VARCHAR(200) DEFAULT '',
        action VARCHAR(20) DEFAULT '',
        responded_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        user_name  VARCHAR(100) DEFAULT '',
        user_phone VARCHAR(20)  DEFAULT '',
        path       VARCHAR(300) DEFAULT '',
        method     VARCHAR(10)  DEFAULT 'GET',
        ip         VARCHAR(50)  DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    # Расширенные этапы реконструкции
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS mp_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS mp_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tp_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tp_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS visualization_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS visualization_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS pjf_approval_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS pjf_approval_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS ds_signing_date DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tz_start DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tz_end DATE",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS status_comment TEXT DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS recon_stage_statuses (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
        stage_key VARCHAR(30) NOT NULL,
        is_done BOOLEAN DEFAULT FALSE,
        done_by VARCHAR(100) DEFAULT '',
        done_at TIMESTAMP,
        UNIQUE(project_id, stage_key)
    )""",
    """CREATE TABLE IF NOT EXISTS project_comments (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        author_name VARCHAR(100) DEFAULT '',
        text TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS pre_vpk_reports (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        vpk_type INTEGER DEFAULT 1,
        submitted_by VARCHAR(100) DEFAULT '',
        submitted_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS pre_vpk_report_items (
        id SERIAL PRIMARY KEY,
        report_id INTEGER REFERENCES pre_vpk_reports(id) ON DELETE CASCADE,
        criterion_id INTEGER REFERENCES vpk_criteria(id) ON DELETE SET NULL,
        criterion_name VARCHAR(300) DEFAULT '',
        status VARCHAR(20) DEFAULT 'not_checked',
        comment TEXT DEFAULT '',
        photo_path VARCHAR(500) DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS opening_photos (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        photo_path VARCHAR(500) DEFAULT '',
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT NOW()
    )""",
    "ALTER TABLE opening_photos ADD COLUMN IF NOT EXISTS is_featured BOOLEAN DEFAULT FALSE",
    # Производительность: индексы часто используемых запросов
    "CREATE INDEX IF NOT EXISTS ix_projects_tk_number      ON projects (tk_number)",
    "CREATE INDEX IF NOT EXISTS ix_projects_manager_id     ON projects (manager_id)",
    "CREATE INDEX IF NOT EXISTS ix_projects_project_type   ON projects (project_type)",
    "CREATE INDEX IF NOT EXISTS ix_opening_photos_proj     ON opening_photos (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_vpk_reports_project     ON vpk_reports (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_created      ON audit_logs (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_user         ON audit_logs (user_name)",
    "CREATE INDEX IF NOT EXISTS ix_smr_tasks_schedule      ON smr_tasks (schedule_id)",
    "CREATE INDEX IF NOT EXISTS ix_smr_tasks_end_plan      ON smr_tasks (end_plan)",
    """CREATE TABLE IF NOT EXISTS adaptation_cards (
        id SERIAL PRIMARY KEY,
        tk_number VARCHAR(50) DEFAULT '',
        created_by VARCHAR(100) DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        status VARCHAR(20) DEFAULT 'draft',
        sent_at TIMESTAMP,
        recipient_email VARCHAR(200) DEFAULT '',
        data JSONB DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS ix_adaptation_tk ON adaptation_cards (tk_number)",
    "CREATE INDEX IF NOT EXISTS ix_adaptation_created_by ON adaptation_cards (created_by)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE",
    """CREATE TABLE IF NOT EXISTS project_history (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        changed_by VARCHAR(100) DEFAULT '',
        field_label VARCHAR(100) DEFAULT '',
        old_value TEXT DEFAULT '',
        new_value TEXT DEFAULT '',
        changed_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_project_history_project_id ON project_history (project_id)",
    """CREATE TABLE IF NOT EXISTS project_attachments (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        original_name VARCHAR(300) DEFAULT '',
        file_url VARCHAR(500) DEFAULT '',
        file_type VARCHAR(20) DEFAULT 'file',
        file_size INTEGER DEFAULT 0,
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_proj_attach_project_id ON project_attachments (project_id)",
    """CREATE TABLE IF NOT EXISTS push_subscriptions (
        id SERIAL PRIMARY KEY,
        user_name VARCHAR(100) DEFAULT '',
        endpoint TEXT UNIQUE NOT NULL,
        p256dh TEXT DEFAULT '',
        auth_key TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_push_sub_user ON push_subscriptions (user_name)",
    """CREATE TABLE IF NOT EXISTS adaptation_photos (
        id SERIAL PRIMARY KEY,
        card_id INTEGER REFERENCES adaptation_cards(id) ON DELETE CASCADE,
        photo_url VARCHAR(500) DEFAULT '',
        original_name VARCHAR(300) DEFAULT '',
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_adapt_photos_card ON adaptation_photos (card_id)",
]

_SQLITE_MIGRATIONS = [
    "ALTER TABLE managers ADD COLUMN photo VARCHAR(200) DEFAULT ''",
    "ALTER TABLE managers ADD COLUMN position VARCHAR(150) DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN format_type VARCHAR(50) DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN open_status VARCHAR(100) DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN delay_reason TEXT DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN updated_at TIMESTAMP",
    "ALTER TABLE tasks ADD COLUMN completion_comment TEXT DEFAULT ''",
    "ALTER TABLE vpk_report_items ADD COLUMN comment TEXT DEFAULT ''",
    "ALTER TABLE vpk_report_items ADD COLUMN photo_path VARCHAR(300) DEFAULT ''",
    "ALTER TABLE chat_messages ADD COLUMN photo_path VARCHAR(300) DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS vpk_report_reads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        reader_name VARCHAR(100) NOT NULL,
        read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(report_id, reader_name)
    )""",
    """CREATE TABLE IF NOT EXISTS task_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        photo_path VARCHAR(300) NOT NULL,
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS ix_chat_sender_name ON chat_messages (sender_name)",
    "CREATE INDEX IF NOT EXISTS ix_vpk_report_submitted_at ON vpk_reports (submitted_at)",
    "CREATE INDEX IF NOT EXISTS ix_ai_chat_user_name ON ai_chat_messages (user_name)",
    "ALTER TABLE projects ADD COLUMN mp_start DATE",
    "ALTER TABLE projects ADD COLUMN mp_end DATE",
    "ALTER TABLE projects ADD COLUMN tp_start DATE",
    "ALTER TABLE projects ADD COLUMN tp_end DATE",
    "ALTER TABLE projects ADD COLUMN visualization_start DATE",
    "ALTER TABLE projects ADD COLUMN visualization_end DATE",
    "ALTER TABLE projects ADD COLUMN audit_start DATE",
    "ALTER TABLE projects ADD COLUMN audit_end DATE",
    "ALTER TABLE projects ADD COLUMN pjf_approval_start DATE",
    "ALTER TABLE projects ADD COLUMN pjf_approval_end DATE",
    "ALTER TABLE projects ADD COLUMN ds_signing_date DATE",
    "ALTER TABLE projects ADD COLUMN tz_start DATE",
    "ALTER TABLE projects ADD COLUMN tz_end DATE",
    "ALTER TABLE projects ADD COLUMN status_comment TEXT DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS recon_stage_statuses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        stage_key VARCHAR(30) NOT NULL,
        is_done BOOLEAN DEFAULT 0,
        done_by VARCHAR(100) DEFAULT '',
        done_at TIMESTAMP,
        UNIQUE(project_id, stage_key)
    )""",
    """CREATE TABLE IF NOT EXISTS project_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        author_name VARCHAR(100) DEFAULT '',
        text TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS pre_vpk_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        vpk_type INTEGER DEFAULT 1,
        submitted_by VARCHAR(100) DEFAULT '',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS pre_vpk_report_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        criterion_id INTEGER,
        criterion_name VARCHAR(300) DEFAULT '',
        status VARCHAR(20) DEFAULT 'not_checked',
        comment TEXT DEFAULT '',
        photo_path VARCHAR(500) DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS opening_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        photo_path VARCHAR(500) DEFAULT '',
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE opening_photos ADD COLUMN is_featured INTEGER DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS adaptation_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tk_number VARCHAR(50) DEFAULT '',
        created_by VARCHAR(100) DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR(20) DEFAULT 'draft',
        sent_at TIMESTAMP,
        recipient_email VARCHAR(200) DEFAULT '',
        data TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS project_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        changed_by VARCHAR(100) DEFAULT '',
        field_label VARCHAR(100) DEFAULT '',
        old_value TEXT DEFAULT '',
        new_value TEXT DEFAULT '',
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS project_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        original_name VARCHAR(300) DEFAULT '',
        file_url VARCHAR(500) DEFAULT '',
        file_type VARCHAR(20) DEFAULT 'file',
        file_size INTEGER DEFAULT 0,
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name VARCHAR(100) DEFAULT '',
        endpoint TEXT UNIQUE NOT NULL,
        p256dh TEXT DEFAULT '',
        auth_key TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS adaptation_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER REFERENCES adaptation_cards(id) ON DELETE CASCADE,
        photo_url VARCHAR(500) DEFAULT '',
        original_name VARCHAR(300) DEFAULT '',
        uploaded_by VARCHAR(100) DEFAULT '',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]


def run_postgres_migrations(engine: Engine) -> None:
    try:
        with engine.begin() as conn:
            for sql in _POSTGRES_MIGRATIONS:
                try:
                    conn.exec_driver_sql(sql)
                except Exception as e:
                    logger.debug("pg migration skipped: %s", e)
    except Exception as e:
        logger.warning("postgres migrations error: %s", e)


def run_sqlite_migrations(engine: Engine) -> None:
    try:
        with engine.begin() as conn:
            for sql in _SQLITE_MIGRATIONS:
                try:
                    conn.exec_driver_sql(sql)
                except Exception:
                    pass
    except Exception as e:
        logger.warning("sqlite migration error: %s", e)
