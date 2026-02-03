from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import get_settings


def _t(value: str, **kwargs) -> str:
    text = value.replace("\\n", "\n")
    return text.format(**kwargs) if kwargs else text


def main_menu(
    is_owner: bool = False, balance: int | None = None, credit_limit: int | None = None
) -> InlineKeyboardMarkup:
    settings = get_settings()
    balance_label = _t(settings.btn_balance)
    if balance is not None:
        limit_text = _t(settings.text_limit_infinite)
        if credit_limit is not None and credit_limit > 0:
            limit_text = f"{credit_limit} ₽"
        balance_label = _t(settings.btn_balance_with_limit, balance=balance, limit=limit_text)
    rows = [
        [InlineKeyboardButton(text=_t(settings.btn_vpn_info), callback_data="vpn:info")],
        [InlineKeyboardButton(text=_t(settings.btn_tariffs), callback_data="tariffs:info")],
        [InlineKeyboardButton(text=_t(settings.btn_new_client), callback_data="client:new")],
        [InlineKeyboardButton(text=_t(settings.btn_renew), callback_data="client:renew")],
        [InlineKeyboardButton(text=_t(settings.btn_clients), callback_data="client:list")],
        [InlineKeyboardButton(text=_t(settings.btn_pay), callback_data="debt:pay")],
        [InlineKeyboardButton(text=balance_label, callback_data="balance:refresh")],
    ]
    if is_owner:
        rows.append([InlineKeyboardButton(text=_t(settings.btn_owner_agents), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def owner_agents_menu() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            # Управление агентами
            [InlineKeyboardButton(text=_t(settings.btn_owner_add_agent), callback_data="owner:add_agent")],
            [
                InlineKeyboardButton(text=_t(settings.btn_owner_limit), callback_data="owner:limit"),
                InlineKeyboardButton(text=_t(settings.btn_owner_report), callback_data="owner:report"),
            ],
            # Уведомления
            [
                InlineKeyboardButton(
                    text=_t(settings.btn_owner_notify_preview), callback_data="owner:notify:preview"
                ),
                InlineKeyboardButton(
                    text=_t(settings.btn_owner_notify_send), callback_data="owner:notify:send"
                ),
            ],
            # Удаление
            [
                InlineKeyboardButton(
                    text=_t(settings.btn_owner_delete_client), callback_data="owner:delete:client"
                ),
                InlineKeyboardButton(
                    text=_t(settings.btn_owner_delete_agent), callback_data="owner:delete:agent"
                ),
            ],
            # Служебное
            [InlineKeyboardButton(text=_t(settings.btn_owner_sync), callback_data="owner:sync")],
            [InlineKeyboardButton(text=_t(settings.btn_owner_back), callback_data="owner:back")],
        ]
    )


def skip_keyboard(action: str) -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(settings.btn_skip), callback_data=f"skip:{action}")],
            [InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")],
        ]
    )


def renew_days_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_t(settings.btn_renew_default_days), callback_data="renew:days:30"),
                InlineKeyboardButton(text=_t(settings.btn_renew_90_days), callback_data="renew:days:90"),
            ],
            [
                InlineKeyboardButton(text=_t(settings.btn_renew_180_days), callback_data="renew:days:180"),
                InlineKeyboardButton(text=_t(settings.btn_renew_365_days), callback_data="renew:days:365"),
            ],
            [InlineKeyboardButton(text=_t(settings.btn_back), callback_data="renew:back")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")],
        ]
    )


def delete_confirm_keyboard(confirm_cb: str) -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(settings.btn_delete_confirm), callback_data=confirm_cb)],
            [InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(settings.btn_back_to_menu), callback_data="menu")],
        ]
    )


def clients_keyboard(
    client_rows: list[tuple[int, str | None, int | None]],
    include_cancel: bool = False,
) -> InlineKeyboardMarkup:
    """
    client_rows: list of (client_id, username, monthly_price)
    """
    settings = get_settings()
    rows = []
    for client_id, username, price in client_rows:
        label = username or f"client-{client_id}"
        price_part = f" · {price}₽" if price else ""
        label = f"{label}{price_part}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"renew:pick:{client_id}")])
    rows.append([InlineKeyboardButton(text=_t(settings.btn_back_to_menu), callback_data="menu")])
    if include_cancel:
        rows.append([InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariffs_keyboard(
    tariffs: list[dict],
    include_back: bool = False,
    back_callback: str = "cancel",
    include_cancel: bool = True,
    label_mode: str = "traffic",
    top_button: tuple[str, str] | None = None,
) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    if top_button:
        top_text, top_callback = top_button
        rows.append([InlineKeyboardButton(text=top_text, callback_data=top_callback)])
    for tariff in tariffs:
        name = tariff.get("name") or "Тариф"
        if label_mode == "price":
            base_price = tariff.get("base_price") or settings.base_subscription_price
            label = f"{name} — {base_price} ₽"
        else:
            traffic_gb = (tariff.get("remnawave") or {}).get("traffic_limit_gb")
            traffic = "безлимит" if not traffic_gb or traffic_gb <= 0 else f"{traffic_gb} ГБ"
            label = f"{name} — {traffic}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"tariff:pick:{tariff['id']}")])
    if include_back:
        rows.append([InlineKeyboardButton(text=_t(settings.btn_back), callback_data=back_callback)])
    if include_cancel:
        rows.append([InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariff_actions_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(settings.btn_tariff_back), callback_data="tariff:back")],
            [InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")],
        ]
    )


def clients_list_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_prev), callback_data=f"client:list:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_next), callback_data=f"client:list:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_t(settings.btn_back_to_menu), callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def agents_limit_keyboard(agent_rows: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    for agent_id, name, limit_label in agent_rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(settings.text_agent_limit_button, name=name, limit=limit_label),
                    callback_data=f"owner:limit:pick:{agent_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=_t(settings.btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_agents_keyboard(agent_rows: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = []
    for agent_id, name in agent_rows:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"owner:delete:agent:pick:{agent_id}")])
    rows.append([InlineKeyboardButton(text=_t(get_settings().btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_clients_keyboard(client_rows: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = []
    for client_id, label in client_rows:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"owner:delete:client:pick:{client_id}")])
    rows.append([InlineKeyboardButton(text=_t(get_settings().btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_clients_pagination_keyboard(
    client_rows: list[tuple[int, str]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    for client_id, label in client_rows:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"owner:delete:client:pick:{client_id}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_prev), callback_data=f"owner:delete:client:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_next), callback_data=f"owner:delete:client:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_t(settings.btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_agents_pagination_keyboard(
    agent_rows: list[tuple[int, str]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    for agent_id, name in agent_rows:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"owner:delete:agent:pick:{agent_id}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_prev), callback_data=f"owner:delete:agent:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_next), callback_data=f"owner:delete:agent:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_t(settings.btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def agents_limit_pagination_keyboard(
    agent_rows: list[tuple[int, str, str]], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows = []
    for agent_id, name, limit_label in agent_rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(settings.text_agent_limit_button, name=name, limit=limit_label),
                    callback_data=f"owner:limit:pick:{agent_id}",
                )
            ]
        )
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_prev), callback_data=f"owner:limit:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_next), callback_data=f"owner:limit:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_t(settings.btn_owner_back), callback_data="owner:agents")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_clients_keyboard(
    client_rows: list[tuple[int, str | None, int | None]],
    page: int,
    total_pages: int,
    include_cancel: bool = False,
) -> InlineKeyboardMarkup:
    """
    client_rows: list of (client_id, username, monthly_price)
    """
    settings = get_settings()
    rows = []
    for client_id, username, price in client_rows:
        label = username or f"client-{client_id}"
        price_part = f" · {price}₽" if price else ""
        label = f"{label}{price_part}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"renew:pick:{client_id}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_prev), callback_data=f"renew:list:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text=_t(settings.btn_next), callback_data=f"renew:list:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_t(settings.btn_back_to_menu), callback_data="menu")])
    if include_cancel:
        rows.append([InlineKeyboardButton(text=_t(settings.btn_cancel), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def transfer_confirm_keyboard(request_id: int) -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(settings.btn_transfer_confirm),
                    callback_data=f"transfer:confirm:{request_id}",
                ),
                InlineKeyboardButton(
                    text=_t(settings.btn_transfer_reject),
                    callback_data=f"transfer:reject:{request_id}",
                ),
            ]
        ]
    )
