from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from database import Base
from datetime import datetime


class ReconStageStatus(Base):
    """Отметки выполнения этапов реконструкции (не сбрасываются при re-import Excel)."""
    __tablename__ = "recon_stage_statuses"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stage_key = Column(String(30), nullable=False)
    is_done = Column(Boolean, default=False)
    done_by = Column(String(100), default="")
    done_at = Column(DateTime, nullable=True)
    __table_args__ = (
        Index("ix_recon_stage_proj_key", "project_id", "stage_key", unique=True),
    )
