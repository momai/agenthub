from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Renewal(Base):
    __tablename__ = "renewals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))

    days: Mapped[int] = mapped_column(Integer)
    debt_amount: Mapped[int] = mapped_column(Integer)
    payment_amount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="renewals")
