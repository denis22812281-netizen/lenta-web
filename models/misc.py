from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Manager(Base):
    __tablename__ = "managers"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), default="")
    telegram_id = Column(String(50), default="")
    is_leader = Column(Boolean, default=False)
    photo = Column(String(200), default="")
    position = Column(String(150), default="")
    projects = relationship("Project", back_populates="manager")
    tasks = relationship("Task", back_populates="assignee")


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


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    sender_name = Column(String(100), nullable=False)
    receiver_name = Column(String(100), default="")
    text = Column(Text, nullable=False)
    photo_path = Column(String(300), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    __table_args__ = (
        Index("ix_chat_receiver",    "receiver_name"),
        Index("ix_chat_is_read",     "is_read"),
        Index("ix_chat_sender_name", "sender_name"),
    )


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"
    id = Column(Integer, primary_key=True)
    user_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    provider = Column(String(30), default="groq")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_ai_chat_user_name", "user_name"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id         = Column(Integer, primary_key=True)
    user_name  = Column(String(100), default="")
    user_phone = Column(String(20),  default="")
    path       = Column(String(300), default="")
    method     = Column(String(10),  default="GET")
    ip         = Column(String(50),  default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_audit_user",    "user_name"),
        Index("ix_audit_created", "created_at"),
    )
