import re
import math

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.agent_service import get_agent_by_telegram_id


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,36}$")
_SKIP_TOKENS = {"/skip", "skip", "пропустить"}
_CANCEL_TOKENS = {"/cancel", "cancel", "отмена", "стоп"}


def _t(value: str, **kwargs) -> str:
    text = value.replace("\\n", "\n")
    return text.format(**kwargs) if kwargs else text


def _tariffs_for_user(settings, telegram_id: int, show_all: bool = False) -> list[dict]:
    if show_all:
        return settings.tariffs()
    return settings.visible_tariffs(telegram_id)


def _format_tariffs_block(settings, tariffs: list[dict]) -> str:
    if not tariffs:
        return _t(settings.text_tariffs_empty)
    lines = []
    for tariff in tariffs:
        desc = tariff.get("desc") or ""
        desc_part = f" · {desc}" if desc else ""
        traffic = _format_traffic((tariff.get("remnawave") or {}).get("traffic_limit_gb"))
        lines.append(
            _t(
                settings.text_tariffs_line,
                name=tariff.get("name"),
                price=tariff.get("base_price"),
                traffic=traffic,
                desc=desc_part,
            )
        )
    header = _t(settings.text_tariffs_header)
    if header:
        return "\n".join([header, *lines])
    return "\n".join(lines)


def _calc_base_debt(settings, days: int, base_price: int | None = None) -> int:
    base_price = base_price or settings.base_subscription_price
    if settings.default_renew_days <= 0:
        return base_price
    return max(0, math.ceil((base_price * days) / settings.default_renew_days))


def _calc_amount_by_days(settings, amount_monthly: int, days: int) -> int:
    if settings.default_renew_days <= 0:
        return max(1, amount_monthly)
    return max(1, math.ceil((amount_monthly * days) / settings.default_renew_days))


def _amount_presets(base_price: int, current_price: int | None = None) -> list[int]:
    values: list[int] = []
    if current_price and current_price > 0:
        values.append(int(current_price))
    for value in [base_price, base_price + 30, base_price + 80, base_price * 2]:
        if value > 0 and value not in values:
            values.append(int(value))
    return values[:4]


def _format_traffic(limit_gb: int | None) -> str:
    if not limit_gb or limit_gb <= 0:
        return "безлимит"
    return f"{limit_gb} ГБ"


def _credit_limit_exceeded(agent, add_amount: int) -> bool:
    if agent.credit_limit <= 0:
        return False
    return (agent.current_debt + add_amount) > agent.credit_limit


async def _is_agent_allowed(user_id: int) -> bool:
    settings = get_settings()
    if user_id == settings.owner_telegram_id or user_id in settings.admin_id_set:
        return True
    async with SessionLocal() as session:
        agent = await get_agent_by_telegram_id(session, user_id)
        return bool(agent and agent.is_active)


def _is_skip(text: str | None) -> bool:
    return (text or "").strip().lower() in _SKIP_TOKENS


def _is_cancel(text: str | None) -> bool:
    return (text or "").strip().lower() in _CANCEL_TOKENS


def _is_start(text: str | None) -> bool:
    return (text or "").strip().lower() == "/start"


def _agent_display(agent) -> str:
    if getattr(agent, "telegram_username", None):
        return f"@{agent.telegram_username}"
    if getattr(agent, "name", None):
        return agent.name
    telegram_id = getattr(agent, "telegram_id", "")
    return str(telegram_id) if telegram_id else ""
