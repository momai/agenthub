from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client
from app.remnawave.client import RemnawaveClient


def _parse_expire(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


async def sync_clients_with_remnawave(
    session: AsyncSession,
    agent_id: int,
    remnawave_client: RemnawaveClient,
) -> tuple[int, int]:
    result = await session.execute(select(Client).where(Client.agent_id == agent_id))
    clients = list(result.scalars().all())

    if not clients:
        return 0, 0

    removed = 0
    updated = 0
    for client in clients:
        username = client.username
        if not username:
            continue
        response = await remnawave_client.get_user_by_username(username)
        users = response.get("response") or []
        if isinstance(users, dict):
            users = [users]
        if not users:
            await session.execute(delete(Client).where(Client.id == client.id))
            removed += 1
            continue

        panel_user = users[0]
        expire_at = _parse_expire(panel_user.get("expireAt"))
        subscription_url = panel_user.get("subscriptionUrl")
        if expire_at and expire_at != client.expires_at:
            client.expires_at = expire_at
            updated += 1
        if subscription_url and subscription_url != client.subscription_link:
            client.subscription_link = subscription_url
            updated += 1

    if removed or updated:
        await session.commit()
    return removed, updated


async def sync_all_clients_with_remnawave(
    session: AsyncSession,
    remnawave_client: RemnawaveClient,
) -> tuple[int, int]:
    result = await session.execute(select(Client))
    clients = list(result.scalars().all())
    if not clients:
        return 0, 0

    removed = 0
    updated = 0
    for client in clients:
        username = client.username
        if not username:
            continue
        response = await remnawave_client.get_user_by_username(username)
        users = response.get("response") or []
        if isinstance(users, dict):
            users = [users]
        if not users:
            await session.execute(delete(Client).where(Client.id == client.id))
            removed += 1
            continue

        panel_user = users[0]
        expire_at = _parse_expire(panel_user.get("expireAt"))
        subscription_url = panel_user.get("subscriptionUrl")
        if expire_at and expire_at != client.expires_at:
            client.expires_at = expire_at
            updated += 1
        if subscription_url and subscription_url != client.subscription_link:
            client.subscription_link = subscription_url
            updated += 1

    if removed or updated:
        await session.commit()
    return removed, updated
