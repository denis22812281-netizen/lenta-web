from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Float, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


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
    address = Column(String(300), default="")
    description = Column(Text, default="")
    budget = Column(Float, nullable=True)
    area = Column(Float, nullable=True)
    pjf_code = Column(String(50), default="")

    format_type = Column(String(50), default="")
    open_status = Column(String(100), default="")
    delay_reason = Column(Text, default="")

    # Ключевые этапы (из Excel)
    sid_start = Column(Date, nullable=True)
    sid_end = Column(Date, nullable=True)
    zoning_start = Column(Date, nullable=True)
    zoning_end = Column(Date, nullable=True)
    closure_date = Column(Date, nullable=True)
    vpk_date = Column(Date, nullable=True)
    opening_date = Column(Date, nullable=True)

    # Расширенные этапы реконструкции (из Excel)
    mp_start = Column(Date, nullable=True)
    mp_end = Column(Date, nullable=True)
    tp_start = Column(Date, nullable=True)
    tp_end = Column(Date, nullable=True)
    visualization_start = Column(Date, nullable=True)
    visualization_end = Column(Date, nullable=True)
    audit_start = Column(Date, nullable=True)
    audit_end = Column(Date, nullable=True)
    pjf_approval_start = Column(Date, nullable=True)
    pjf_approval_end = Column(Date, nullable=True)
    ds_signing_date = Column(Date, nullable=True)
    tz_start = Column(Date, nullable=True)
    tz_end = Column(Date, nullable=True)
    status_comment = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    manager = relationship("Manager", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    stages = relationship("ProjectStage", back_populates="project", cascade="all, delete-orphan",
                          order_by="ProjectStage.order")
    comments = relationship("ProjectComment", back_populates="project", cascade="all, delete-orphan",
                            order_by="ProjectComment.created_at")
    opening_photos = relationship("OpeningPhoto", back_populates="project", cascade="all, delete-orphan",
                                  order_by="OpeningPhoto.uploaded_at")
    attachments = relationship("ProjectAttachment", back_populates="project", cascade="all, delete-orphan",
                               order_by="ProjectAttachment.uploaded_at.desc()")
    history = relationship("ProjectHistory", back_populates="project", cascade="all, delete-orphan",
                           order_by="ProjectHistory.changed_at.desc()")
    __table_args__ = (
        Index("ix_project_manager_id", "manager_id"),
        Index("ix_project_status",     "status"),
        Index("ix_project_type",       "project_type"),
        Index("ix_project_end_date",   "end_date"),
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


class ProjectComment(Base):
    __tablename__ = "project_comments"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    author_name = Column(String(100), default="")
    text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    project = relationship("Project", back_populates="comments")


class OpeningPhoto(Base):
    """Фото открытия магазина — загружаются менеджером в день открытия."""
    __tablename__ = "opening_photos"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    photo_path = Column(String(500), default="")
    uploaded_by = Column(String(100), default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    is_featured = Column(Boolean, default=False)
    project = relationship("Project", back_populates="opening_photos")


class ProjectAttachment(Base):
    """Файлы и фото, прикреплённые к проекту."""
    __tablename__ = "project_attachments"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    original_name = Column(String(300), default="")
    file_url = Column(String(500), default="")
    file_type = Column(String(20), default="file")  # image | pdf | xls | doc | file
    file_size = Column(Integer, default=0)
    uploaded_by = Column(String(100), default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    project = relationship("Project", back_populates="attachments")


class ProjectHistory(Base):
    """Журнал изменений полей проекта."""
    __tablename__ = "project_history"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    changed_by = Column(String(100), default="")
    field_label = Column(String(100), default="")
    old_value = Column(Text, default="")
    new_value = Column(Text, default="")
    changed_at = Column(DateTime, default=datetime.utcnow)
    project = relationship("Project", back_populates="history")


class SyncConfig(Base):
    __tablename__ = "sync_configs"
    id = Column(Integer, primary_key=True)
    project_type = Column(String(50), unique=True)
    file_path = Column(String(500), default="")
    auto_sync = Column(Boolean, default=False)
    sync_interval_minutes = Column(Integer, default=60)
    last_synced = Column(DateTime, nullable=True)
    last_status = Column(String(200), default="")
