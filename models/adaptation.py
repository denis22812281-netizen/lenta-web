from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


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
    photos = relationship("AdaptationPhoto", back_populates="card",
                          cascade="all, delete-orphan",
                          order_by="AdaptationPhoto.uploaded_at")


class AdaptationPhoto(Base):
    __tablename__ = "adaptation_photos"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey("adaptation_cards.id", ondelete="CASCADE"))
    photo_url = Column(String(500), default="")
    original_name = Column(String(300), default="")
    uploaded_by = Column(String(100), default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    card = relationship("AdaptationCard", back_populates="photos")
