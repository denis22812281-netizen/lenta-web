from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Float, Boolean, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class PhoneWhitelist(Base):
    __tablename__ = "phone_whitelist"
    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, nullable=False)   # +79991234567
    display_name = Column(String(100), default="")            # Имя сотрудника
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, nullable=False)   # привязан к телефону
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)        # NULL = пароль ещё не создан
    display_name = Column(String(100))
    is_admin = Column(Boolean, default=False)
    session_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class Manager(Base):
    __tablename__ = "managers"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), default="")
    telegram_id = Column(String(50), default="")
    is_leader = Column(Boolean, default=False)  # Руководитель проектов
    photo = Column(String(200), default="")     # путь к фото relative to static/
    position = Column(String(150), default="")  # должность
    projects = relationship("Project", back_populates="manager")
    tasks = relationship("Task", back_populates="assignee")


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    tk_number = Column(String(50), default="")
    city = Column(Text, default="")
    project_type = Column(String(50), default="")
    manager_id = Column(Integer, ForeignKey("managers.id"), nullable=True)
    status = Column(String(50), default="Активный")
    stage = Column(Text, default="")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    address = Column(String(300), default="")   # Полный адрес объекта
    description = Column(Text, default="")
    budget = Column(Float, nullable=True)
    area = Column(Float, nullable=True)           # Площадь, м²
    pjf_code = Column(String(50), default="")     # Код PJF

    format_type = Column(String(50), default="")    # Тип формата: SM, HM, Utkonos и т.д.
    open_status = Column(String(100), default="")   # Статус открытия из Excel
    delay_reason = Column(Text, default="")          # Чья вина при задержке открытия

    # Ключевые этапы (из Excel)
    sid_start = Column(Date, nullable=True)       # Сбор исходных данных - начало
    sid_end = Column(Date, nullable=True)         # Сбор исходных данных - окончание
    zoning_start = Column(Date, nullable=True)    # Зонирование - начало
    zoning_end = Column(Date, nullable=True)      # Зонирование - окончание
    closure_date = Column(Date, nullable=True)    # Старт закрытие (дата)
    vpk_date = Column(Date, nullable=True)        # ВПК1 / ВПК (дата)
    opening_date = Column(Date, nullable=True)    # Дата открытия

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    manager = relationship("Manager", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    stages = relationship("ProjectStage", back_populates="project", cascade="all, delete-orphan",
                          order_by="ProjectStage.order")
    __table_args__ = (
        Index("ix_project_manager_id",  "manager_id"),
        Index("ix_project_status",      "status"),
        Index("ix_project_type",        "project_type"),
        Index("ix_project_end_date",    "end_date"),
    )


class ProjectStage(Base):
    __tablename__ = "project_stages"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(Text)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(50), default="Запланировано")
    order = Column(Integer, default=0)
    project = relationship("Project", back_populates="stages")


class SyncConfig(Base):
    __tablename__ = "sync_configs"
    id = Column(Integer, primary_key=True)
    project_type = Column(String(50), unique=True)
    file_path = Column(String(500), default="")
    auto_sync = Column(Boolean, default=False)
    sync_interval_minutes = Column(Integer, default=60)
    last_synced = Column(DateTime, nullable=True)
    last_status = Column(String(200), default="")


class VpkCriterion(Base):
    __tablename__ = "vpk_criteria"
    id = Column(Integer, primary_key=True)
    vpk_type = Column(Integer, default=1)   # 1 = ВПК1, 2 = ВПК2
    name = Column(String(300), nullable=False)
    order = Column(Integer, default=0)


class VpkReport(Base):
    __tablename__ = "vpk_reports"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    vpk_type = Column(Integer, default=1)
    submitted_by = Column(String(100), default="")
    submitted_at = Column(DateTime, default=datetime.utcnow)
    read_gavrin = Column(Boolean, default=False)   # оставлено для совместимости
    read_mesmer = Column(Boolean, default=False)   # оставлено для совместимости
    project = relationship("Project")
    items = relationship("VpkReportItem", back_populates="report",
                         cascade="all, delete-orphan")
    reads = relationship("VpkReportRead", back_populates="report",
                         cascade="all, delete-orphan")
    __table_args__ = (Index("ix_vpk_report_submitted_at", "submitted_at"),)


class VpkReportRead(Base):
    """Кто и когда прочитал ВПК-отчёт. Заменяет хардкод read_gavrin/read_mesmer."""
    __tablename__ = "vpk_report_reads"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("vpk_reports.id", ondelete="CASCADE"), nullable=False)
    reader_name = Column(String(100), nullable=False)
    read_at = Column(DateTime, default=datetime.utcnow)
    report = relationship("VpkReport", back_populates="reads")
    __table_args__ = (
        Index("ix_vpk_reads_report_reader", "report_id", "reader_name", unique=True),
    )


class VpkReportItem(Base):
    __tablename__ = "vpk_report_items"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("vpk_reports.id"))
    criterion_id = Column(Integer, ForeignKey("vpk_criteria.id"), nullable=True)
    criterion_name = Column(String(300), default="")
    done = Column(Boolean, default=False)
    comment = Column(Text, default="")
    photo_path = Column(String(300), default="")
    report = relationship("VpkReport", back_populates="items")
    criterion = relationship("VpkCriterion")


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"
    id = Column(Integer, primary_key=True)
    user_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)   # "user" или "assistant"
    text = Column(Text, nullable=False)
    provider = Column(String(30), default="groq")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_ai_chat_user_name", "user_name"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    sender_name = Column(String(100), nullable=False)
    receiver_name = Column(String(100), default="")  # "" = общий чат
    text = Column(Text, nullable=False)
    photo_path = Column(String(300), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    __table_args__ = (
        Index("ix_chat_receiver",    "receiver_name"),
        Index("ix_chat_is_read",     "is_read"),
        Index("ix_chat_sender_name", "sender_name"),
    )


class KsoObject(Base):
    __tablename__ = "kso_objects"
    id = Column(Integer, primary_key=True)
    tk_number = Column(String(50), default="")
    address = Column(Text, default="")
    manager_id = Column(Integer, ForeignKey("managers.id"), nullable=True)
    done = Column(Boolean, default=False)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    manager = relationship("Manager")


class KsoSchedule(Base):
    __tablename__ = "kso_schedules"
    id = Column(Integer, primary_key=True)
    original_name = Column(String(200), default="")
    filename = Column(String(200), nullable=False)
    description = Column(Text, default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(String(100), default="")


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    assignee_id = Column(Integer, ForeignKey("managers.id"), nullable=True)
    deadline = Column(Date, nullable=True)
    priority = Column(String(20), default="Средний")
    status = Column(String(50), default="Открытая")
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default="")
    completion_comment = Column(Text, default="")
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("Manager", back_populates="tasks")
    __table_args__ = (
        Index("ix_task_project_id",  "project_id"),
        Index("ix_task_assignee_id", "assignee_id"),
        Index("ix_task_status",      "status"),
        Index("ix_task_deadline",    "deadline"),
    )


class WebAuthnCredential(Base):
    """Хранит зарегистрированные биометрические ключи пользователя (Face ID / Touch ID)."""
    __tablename__ = "webauthn_credentials"
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_id = Column(Text, unique=True, nullable=False)  # base64url
    public_key    = Column(Text, nullable=False)               # base64 COSE
    sign_count    = Column(Integer, default=0)
    device_name   = Column(String(150), default="")            # "iPhone 15", "MacBook" и т.д.
    created_at    = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")


class TaskPhoto(Base):
    """Фотоотчёт к завершённой задаче."""
    __tablename__ = "task_photos"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    photo_path = Column(String(300), nullable=False)
    uploaded_by = Column(String(100), default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    task = relationship("Task")


class TaskNotification(Base):
    __tablename__ = "task_notifications"
    id = Column(Integer, primary_key=True)
    recipient_name = Column(String(100), nullable=False)  # кому
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    task = relationship("Task")


class SmrContact(Base):
    """База контактов для уведомлений по графику СМР."""
    __tablename__ = "smr_contacts"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), nullable=False)   # Фамилия Имя
    email      = Column(String(200), nullable=False)
    position   = Column(String(150), default="")       # Должность / роль
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_smr_contact_name", "name"),)


class SmrSchedule(Base):
    """График СМР — привязан к одному проекту."""
    __tablename__ = "smr_schedules"
    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project    = relationship("Project")
    tasks      = relationship("SmrTask", back_populates="schedule",
                              cascade="all, delete-orphan", order_by="SmrTask.order")


class SmrTask(Base):
    """Одна задача/веха в графике СМР."""
    __tablename__ = "smr_tasks"
    id           = Column(Integer, primary_key=True)
    schedule_id  = Column(Integer, ForeignKey("smr_schedules.id", ondelete="CASCADE"), nullable=False)
    name         = Column(Text, nullable=False)
    order        = Column(Integer, default=0)
    start_plan   = Column(Date, nullable=True)
    end_plan     = Column(Date, nullable=True)
    is_milestone = Column(Boolean, default=False)   # ключевая веха (ВПК 1, ВПК 2, Открытие)
    status       = Column(String(30), default="Запланировано")  # Запланировано / В работе / Выполнено / Просрочено
    notify_email1 = Column(String(200), default="")  # email ответственного 1
    notify_email2 = Column(String(200), default="")  # email ответственного 2
    notified_date = Column(Date, nullable=True)       # дата последней автоотправки
    reject_comment = Column(Text, default="")         # комментарий при отклонении
    schedule     = relationship("SmrSchedule", back_populates="tasks")
    confirmations = relationship("SmrConfirmation", back_populates="task",
                                 cascade="all, delete-orphan")
    __table_args__ = (Index("ix_smr_task_schedule", "schedule_id"),)


class SmrConfirmation(Base):
    """Подтверждение/отклонение вехи по email-ссылке."""
    __tablename__ = "smr_confirmations"
    id         = Column(Integer, primary_key=True)
    task_id    = Column(Integer, ForeignKey("smr_tasks.id", ondelete="CASCADE"), nullable=False)
    token      = Column(String(64), unique=True, nullable=False)
    email      = Column(String(200), default="")
    action     = Column(String(20), default="")   # "confirmed" / "rejected"
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    task       = relationship("SmrTask", back_populates="confirmations")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id         = Column(Integer, primary_key=True)
    user_name  = Column(String(100), default="")   # display_name пользователя
    user_phone = Column(String(20),  default="")   # телефон
    path       = Column(String(300), default="")   # URL страницы
    method     = Column(String(10),  default="GET")
    ip         = Column(String(50),  default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_audit_user",    "user_name"),
        Index("ix_audit_created", "created_at"),
    )
