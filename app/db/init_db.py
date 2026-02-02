from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TABLE clients ALTER COLUMN telegram_id DROP NOT NULL"))
        except Exception:
            pass
        try:
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS monthly_price INTEGER DEFAULT 200")
            )
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_payment_amount INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_payment_at TIMESTAMP")
            )
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS tariff_name VARCHAR(128)")
            )
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS tariff_base_price INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS expires_notified_for TIMESTAMP")
            )
        except Exception:
            pass
        try:
            await conn.execute(
                text("ALTER TABLE renewals ADD COLUMN IF NOT EXISTS payment_amount INTEGER DEFAULT 0")
            )
        except Exception:
            pass
        try:
            await conn.execute(
                text("ALTER TABLE agents ADD COLUMN IF NOT EXISTS menu_message_id BIGINT")
            )
        except Exception:
            pass
        try:
            await conn.execute(
                text("ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)")
            )
        except Exception:
            pass