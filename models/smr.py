from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class SmrContact(Base):
    """База контактов для уведомлений по графику СМР."""
    __tablename__ = "smr_contacts"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), nullable=False)
    email      = Column(String(200), nullable=False)
    position   = Column(String(150), default="")
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
    is_milestone = Column(Boolean, default=False)
    status       = Column(String(30), default="Запланировано")
    notify_email1 = Column(String(200), default="")
    notify_email2 = Column(String(200), default="")
    notified_date = Column(Date, nullable=True)
    reject_comment = Column(Text, default="")
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
    action     = Column(String(20), default="")
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    task       = relationship("SmrTask", back_populates="confirmations")
