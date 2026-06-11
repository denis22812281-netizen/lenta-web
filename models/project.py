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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    manager = relationship("Manager", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    stages = relationship("ProjectStage", back_populates="project", cascade="all, delete-orphan",
                          order_by="ProjectStage.order")
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


class SyncConfig(Base):
    __tablename__ = "sync_configs"
    id = Column(Integer, primary_key=True)
    project_type = Column(String(50), unique=True)
    file_path = Column(String(500), default="")
    auto_sync = Column(Boolean, default=False)
    sync_interval_minutes = Column(Integer, default=60)
    last_synced = Column(DateTime, nullable=True)
    last_status = Column(String(200), default="")
