from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import re
from typing import Any

from app.config import get_settings
from app.remnawave.client import RemnawaveClient


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _unwrap_response(payload: Any) -> Any:
    if payload is None:
        return None
    if hasattr(payload, "response"):
        return payload.response
    if isinstance(payload, dict) and "response" in payload:
        return payload["response"]
    return payload


def _normalize_users(payload: Any) -> list[dict[str, Any]]:
    users = _unwrap_response(payload) or []
    if isinstance(users, dict):
        return [users]
    if isinstance(users, list):
        return [item for item in users if isinstance(item, dict)]
    return []


def _get_value(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _traffic_limit_bytes(limit_gb: int) -> int:
    if limit_gb <= 0:
        return 0
    return int(limit_gb) * 1024 * 1024 * 1024


def _calculate_new_expire(current: datetime | None, days: int) -> datetime:
    now = datetime.now(timezone.utc)
    if not current or current < now:
        return now + timedelta(days=days)
    return current + timedelta(days=days)


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        cleaned[key] = value
    return cleaned


def _normalize_tag(tag: str | None) -> str | None:
    if not tag or not tag.strip():
        return None
    normalized = tag.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]+", normalized):
        return None
    return normalized


def _normalize_uuid(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    return value.strip() if _UUID_PATTERN.match(value.strip()) else None


def _normalize_uuid_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        cleaned = _normalize_uuid(value)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _build_base_payload(
    *,
    settings,
    description: str | None,
    telegram_id: int | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    overrides = overrides or {}
    traffic_limit_gb = overrides.get("traffic_limit_gb")
    if traffic_limit_gb is None:
        traffic_limit_gb = settings.remnawave_traffic_limit_gb
    traffic_limit = _traffic_limit_bytes(traffic_limit_gb)
    traffic_reset_strategy = overrides.get("traffic_reset_strategy") or settings.remnawave_traffic_reset_strategy
    hwid_device_limit = overrides.get("hwid_device_limit")
    if hwid_device_limit is None:
        hwid_device_limit = settings.remnawave_hwid_device_limit
    internal_squads_raw = overrides.get("internal_squads") or settings.remnawave_internal_squads
    external_squad_raw = overrides.get("external_squad") or settings.remnawave_external_squad
    tag_raw = overrides.get("tag") or settings.remnawave_tag

    internal_squads_list = (
        _normalize_uuid_list([value.strip() for value in internal_squads_raw.split(",") if value.strip()])
        if internal_squads_raw
        else _normalize_uuid_list(settings.internal_squads_set)
    )
    external_squad = _normalize_uuid(external_squad_raw)

    return _clean_payload(
        {
            "status": "ACTIVE",
            "trafficLimitBytes": traffic_limit,
            "trafficLimitStrategy": traffic_reset_strategy,
            "description": description,
            "tag": _normalize_tag(tag_raw),
            "telegramId": telegram_id,
            "hwidDeviceLimit": hwid_device_limit,
            "activeInternalSquads": internal_squads_list,
            "externalSquadUuid": external_squad,
        }
    )


async def username_exists(username: str) -> bool:
    settings = get_settings()
    client = RemnawaveClient(
        settings.remnawave_api_url,
        settings.remnawave_api_key,
        settings.remnawave_mode,
        settings.remnawave_caddy_token,
    )
    try:
        users_payload = await client.get_user_by_username(username)
    except Exception as exc:
        logging.error("Remnawave username_exists failed: %s", exc)
        raise
    users = _normalize_users(users_payload)
    return bool(users)


async def create_user_only(
    username: str,
    days: int,
    description: str | None,
    telegram_id: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    logging.info(
        "Remnawave create_user_only: username=%s days=%s telegram_id=%s",
        username,
        days,
        telegram_id,
    )
    client = RemnawaveClient(
        settings.remnawave_api_url,
        settings.remnawave_api_key,
        settings.remnawave_mode,
        settings.remnawave_caddy_token,
    )

    if settings.remnawave_internal_squads and not _normalize_uuid_list(settings.internal_squads_set):
        logging.warning("REMNAWAVE_INTERNAL_SQUADS ignored: not UUIDs")
    if settings.remnawave_external_squad and not _normalize_uuid(settings.remnawave_external_squad):
        logging.warning("REMNAWAVE_EXTERNAL_SQUAD ignored: invalid UUID")

    try:
        users_payload = await client.get_user_by_username(username)
    except Exception as exc:
        logging.error("Remnawave get_user_by_username failed: %s", exc)
        raise
    users = _normalize_users(users_payload)
    existing = users[0] if users else None
    logging.info("Remnawave user lookup: username=%s found=%s", username, bool(existing))
    if existing:
        return {"exists": True}

    new_expire = _calculate_new_expire(None, days)
    base_payload = _build_base_payload(
        settings=settings,
        description=description,
        telegram_id=telegram_id,
        overrides=overrides,
    )
    payload = _clean_payload(
        {
            **base_payload,
            "username": username,
            "expireAt": _to_iso(new_expire),
        }
    )
    logging.info("Remnawave create_user payload: %s", payload)
    try:
        response = await client.create_user(payload)
    except Exception as exc:
        logging.error("Remnawave create_user failed: %s", exc)
        raise
    unwrapped = _unwrap_response(response)
    logging.info("Remnawave create_user response: %s", unwrapped)
    return {
        "response": unwrapped,
        "expires_at": _to_naive_utc(new_expire),
        "subscription_url": _get_value(unwrapped, "subscriptionUrl", "subscription_url"),
    }


_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


async def create_or_extend_user(
    username: str,
    days: int,
    description: str | None,
    telegram_id: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    logging.info(
        "Remnawave create_or_extend_user: username=%s days=%s telegram_id=%s",
        username,
        days,
        telegram_id,
    )
    client = RemnawaveClient(
        settings.remnawave_api_url,
        settings.remnawave_api_key,
        settings.remnawave_mode,
        settings.remnawave_caddy_token,
    )

    if settings.remnawave_internal_squads and not _normalize_uuid_list(settings.internal_squads_set):
        logging.warning("REMNAWAVE_INTERNAL_SQUADS ignored: not UUIDs")
    if settings.remnawave_external_squad and not _normalize_uuid(settings.remnawave_external_squad):
        logging.warning("REMNAWAVE_EXTERNAL_SQUAD ignored: invalid UUID")

    try:
        users_payload = await client.get_user_by_username(username)
    except Exception as exc:
        logging.error("Remnawave get_user_by_username failed: %s", exc)
        raise
    users = _normalize_users(users_payload)
    existing = users[0] if users else None
    logging.info("Remnawave user lookup: username=%s found=%s", username, bool(existing))

    current_expire = _parse_dt(_get_value(existing, "expireAt", "expire_at")) if existing else None
    new_expire = _calculate_new_expire(current_expire, days)
    base_payload = _build_base_payload(
        settings=settings,
        description=description,
        telegram_id=telegram_id,
        overrides=overrides,
    )

    if existing:
        payload = _clean_payload(
            {
                **base_payload,
                "uuid": _get_value(existing, "uuid"),
                "expireAt": _to_iso(new_expire),
            }
        )
        logging.info("Remnawave update_user payload: %s", payload)
        try:
            response = await client.update_user(payload)
        except Exception as exc:
            logging.error("Remnawave update_user failed: %s", exc)
            raise
        unwrapped = _unwrap_response(response)
        logging.info("Remnawave update_user response: %s", unwrapped)
        return {
            "response": unwrapped,
            "expires_at": _to_naive_utc(new_expire),
            "subscription_url": _get_value(unwrapped, "subscriptionUrl", "subscription_url"),
        }

    payload = _clean_payload(
        {
            **base_payload,
            "username": username,
            "expireAt": _to_iso(new_expire),
        }
    )
    logging.info("Remnawave create_user payload: %s", payload)
    try:
        response = await client.create_user(payload)
    except Exception as exc:
        logging.error("Remnawave create_user failed: %s", exc)
        raise
    unwrapped = _unwrap_response(response)
    logging.info("Remnawave create_user response: %s", unwrapped)
    return {
        "response": unwrapped,
        "expires_at": _to_naive_utc(new_expire),
        "subscription_url": _get_value(unwrapped, "subscriptionUrl", "subscription_url"),
    }
