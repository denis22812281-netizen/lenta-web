from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class VpkCriterion(Base):
    __tablename__ = "vpk_criteria"
    id = Column(Integer, primary_key=True)
    vpk_type = Column(Integer, default=1)
    name = Column(String(300), nullable=False)
    order = Column(Integer, default=0)


class VpkReport(Base):
    __tablename__ = "vpk_reports"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    vpk_type = Column(Integer, default=1)
    submitted_by = Column(String(100), default="")
    submitted_at = Column(DateTime, default=datetime.utcnow)
    read_gavrin = Column(Boolean, default=False)
    read_mesmer = Column(Boolean, default=False)
    project = relationship("Project")
    items = relationship("VpkReportItem", back_populates="report",
                         cascade="all, delete-orphan")
    reads = relationship("VpkReportRead", back_populates="report",
                         cascade="all, delete-orphan")
    __table_args__ = (Index("ix_vpk_report_submitted_at", "submitted_at"),)


class VpkReportRead(Base):
    """Кто и когда прочитал ВПК-отчёт."""
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
