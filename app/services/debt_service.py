from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, DebtEvent


async def increase_debt(session: AsyncSession, agent: Agent, amount: int, reason: str) -> None:
    agent.current_debt += amount
    session.add(DebtEvent(agent_id=agent.id, amount=amount, reason=reason))
    await session.commit()


async def decrease_debt(session: AsyncSession, agent: Agent, amount: int, reason: str) -> None:
    agent.current_debt = max(0, agent.current_debt - amount)
    session.add(DebtEvent(agent_id=agent.id, amount=-amount, reason=reason))
    await session.commit()
