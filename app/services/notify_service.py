import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import back_to_menu_keyboard
from app.config import get_settings
from app.models import Agent, Client


def _t(value: str, **kwargs) -> str:
    text = value.replace("\\n", "\n")
    return text.format(**kwargs) if kwargs else text


async def notify_expiring_clients(session: AsyncSession, bot) -> int:
    settings = get_settings()
    now = datetime.utcnow()
    notify_until = now + timedelta(days=settings.expiry_notify_days)

    stmt = (
        select(Client, Agent)
        .join(Agent, Client.agent_id == Agent.id)
        .where(
            Client.expires_at.isnot(None),
            Client.expires_at > now,
            Client.expires_at <= notify_until,
            or_(
                Client.expires_notified_for.is_(None),
                Client.expires_notified_for != Client.expires_at,
            ),
        )
    )
    rows = (await session.execute(stmt)).all()
    notified = 0

    for client, agent in rows:
        if not agent.is_active:
            continue
        days_left = max(
            0, math.ceil((client.expires_at - now).total_seconds() / 86400)
        )
        expires_at = client.expires_at.strftime("%d.%m.%Y")
        text = _t(
            settings.text_subscription_expiring,
            username=client.username,
            days_left=days_left,
            expires_at=expires_at,
        )
        try:
            await bot.send_message(agent.telegram_id, text, reply_markup=back_to_menu_keyboard())
        except Exception as exc:
            logging.warning("Expiry notify failed for agent %s: %s", agent.telegram_id, exc)
            continue

        client.expires_notified_for = client.expires_at
        await session.commit()
        notified += 1

    return notified


async def list_expiring_clients(session: AsyncSession) -> list[tuple[Client, Agent]]:
    settings = get_settings()
    now = datetime.utcnow()
    notify_until = now + timedelta(days=settings.expiry_notify_days)

    stmt = (
        select(Client, Agent)
        .join(Agent, Client.agent_id == Agent.id)
        .where(
            Client.expires_at.isnot(None),
            Client.expires_at > now,
            Client.expires_at <= notify_until,
            or_(
                Client.expires_notified_for.is_(None),
                Client.expires_notified_for != Client.expires_at,
            ),
        )
        .order_by(Client.expires_at.asc(), Client.username.asc())
    )
    return (await session.execute(stmt)).all()
