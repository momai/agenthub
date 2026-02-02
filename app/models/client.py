from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))

    username: Mapped[str] = mapped_column(String(128))
    subscription_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    monthly_price: Mapped[int] = mapped_column(Integer, default=200)
    last_payment_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tariff_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tariff_base_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_notified_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="clients")
    renewals = relationship("Renewal", back_populates="client")
