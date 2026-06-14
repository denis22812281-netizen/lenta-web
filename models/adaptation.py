from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from database import Base
from datetime import datetime


class AdaptationCard(Base):
    __tablename__ = "adaptation_cards"
    id = Column(Integer, primary_key=True)
    tk_number = Column(String(50), default="")
    created_by = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(20), default="draft")  # draft / sent
    sent_at = Column(DateTime, nullable=True)
    recipient_email = Column(String(200), default="")
    data = Column(JSON, default=dict)  # {cell_ref: value}
