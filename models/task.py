from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


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
    recipient_name = Column(String(100), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    task = relationship("Task")
