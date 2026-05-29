from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Float, Boolean
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
    created_at = Column(DateTime, default=datetime.utcnow)


class Manager(Base):
    __tablename__ = "managers"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), default="")
    telegram_id = Column(String(50), default="")
    is_leader = Column(Boolean, default=False)  # Руководитель проектов
    photo = Column(String(200), default="")     # путь к фото relative to static/
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
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("Manager", back_populates="tasks")
