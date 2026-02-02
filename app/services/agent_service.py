from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Agent, Client


async def get_or_create_agent(
    session: AsyncSession, telegram_id: int, name: str, username: str | None = None
) -> Agent:
    normalized_username = (username or "").lstrip("@").strip().lower() or None
    result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
    agent = result.scalar_one_or_none()
    if agent:
        if normalized_username and agent.telegram_username != normalized_username:
            agent.telegram_username = normalized_username
            await session.commit()
        return agent

    settings = get_settings()
    agent = Agent(
        telegram_id=telegram_id,
        name=name or str(telegram_id),
        telegram_username=normalized_username,
        credit_limit=settings.default_credit_limit,
        owner_share_percent=settings.default_owner_share_percent,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def get_agent_by_telegram_id(session: AsyncSession, telegram_id: int) -> Agent | None:
    result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_agent_by_username(session: AsyncSession, username: str) -> Agent | None:
    normalized_username = (username or "").lstrip("@").strip().lower()
    result = await session.execute(
        select(Agent).where(func.lower(Agent.telegram_username) == normalized_username)
    )
    return result.scalar_one_or_none()


async def get_agent_by_id(session: AsyncSession, agent_id: int) -> Agent | None:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def list_agents(session: AsyncSession) -> list[tuple[Agent, int]]:
    result = await session.execute(select(Agent).order_by(Agent.created_at))
    agents = list(result.scalars().all())
    output: list[tuple[Agent, int]] = []
    for agent in agents:
        count_result = await session.execute(
            select(Client.id).where(Client.agent_id == agent.id)
        )
        client_count = len(count_result.scalars().all())
        output.append((agent, client_count))
    return output
