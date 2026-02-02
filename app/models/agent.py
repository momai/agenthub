from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    credit_limit: Mapped[int] = mapped_column(Integer, default=0)
    current_debt: Mapped[int] = mapped_column(Integer, default=0)
    owner_share_percent: Mapped[int] = mapped_column(Integer, default=100)
    menu_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clients = relationship("Client", back_populates="agent")
    debt_events = relationship("DebtEvent", back_populates="agent")
