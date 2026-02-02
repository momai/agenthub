from __future__ import annotations

from datetime import datetime, timezone, timedelta

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Agent


async def get_client_by_tg(session: AsyncSession, agent_id: int, telegram_id: int) -> Client | None:
    result = await session.execute(
        select(Client).where(Client.agent_id == agent_id, Client.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_client_by_username(session: AsyncSession, agent_id: int, username: str) -> Client | None:
    result = await session.execute(
        select(Client).where(Client.agent_id == agent_id, Client.username == username)
    )
    return result.scalar_one_or_none()


async def get_client_by_username_any(session: AsyncSession, username: str) -> Client | None:
    result = await session.execute(select(Client).where(Client.username == username))
    return result.scalar_one_or_none()


async def get_client_by_id(session: AsyncSession, client_id: int) -> Client | None:
    result = await session.execute(
        select(Client).options(selectinload(Client.agent)).where(Client.id == client_id)
    )
    return result.scalar_one_or_none()


async def create_client(
    session: AsyncSession,
    agent_id: int,
    username: str,
    telegram_id: int | None,
    expires_at: datetime | None = None,
    subscription_link: str | None = None,
    monthly_price: int = 200,
    last_payment_amount: int | None = None,
    last_payment_at: datetime | None = None,
    tariff_name: str | None = None,
    tariff_base_price: int | None = None,
) -> Client:
    client = Client(
        agent_id=agent_id,
        telegram_id=telegram_id,
        username=username,
        expires_at=expires_at,
        subscription_link=subscription_link,
        monthly_price=monthly_price,
        last_payment_amount=last_payment_amount,
        last_payment_at=last_payment_at,
        tariff_name=tariff_name,
        tariff_base_price=tariff_base_price,
    )
    session.add(client)
    await session.commit()
    await session.refresh(client)
    logging.info("Client saved in DB: agent_id=%s username=%s id=%s", agent_id, username, client.id)
    return client


async def list_clients_by_agent(session: AsyncSession, agent_id: int) -> list[Client]:
    result = await session.execute(select(Client).where(Client.agent_id == agent_id).order_by(Client.username))
    return list(result.scalars().all())


async def list_clients_with_agents(session: AsyncSession) -> list[tuple[Client, Agent]]:
    result = await session.execute(
        select(Client, Agent)
        .join(Agent, Agent.id == Client.agent_id)
        .order_by(Agent.name, Client.username)
    )
    return list(result.all())


def add_days(current: datetime | None, days: int) -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not current or current < now:
        return now + timedelta(days=days)
    if current.tzinfo is not None:
        current = current.astimezone(timezone.utc).replace(tzinfo=None)
    return current + timedelta(days=days)
