import math
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    agents_limit_pagination_keyboard,
    agents_limit_keyboard,
    cancel_keyboard,
    delete_confirm_keyboard,
    delete_clients_keyboard,
    delete_clients_pagination_keyboard,
    delete_agents_keyboard,
    delete_agents_pagination_keyboard,
    main_menu,
    owner_report_pagination_keyboard,
    owner_agents_menu,
)
from app.bot.states import AddAgentState, DeleteClientState, LimitAgentState
from app.config import get_settings
from app.db.session import SessionLocal
from app.remnawave.client import RemnawaveClient
from app.services.agent_service import (
    get_agent_by_id,
    get_agent_by_telegram_id,
    get_agent_by_username,
    get_or_create_agent,
    list_agents,
    delete_agent_by_id,
)
from app.services.client_service import (
    get_client_by_id,
    get_client_by_tg_any,
    get_client_by_username_any,
    delete_client_by_id,
    list_clients_with_agents,
)
from app.services.notify_service import list_expiring_clients, notify_expiring_clients
from app.services.sync_service import sync_all_clients_with_remnawave

from .common import _agent_display, _is_cancel, _is_start, _t
from .menu import (
    _edit_or_send,
    _render_error_prompt,
    _render_menu_text,
    _show_start_menu,
    _show_status_then_menu,
)


router = Router()


def _is_owner_or_admin(user_id: int) -> bool:
    settings = get_settings()
    return user_id == settings.owner_telegram_id or user_id in settings.admin_id_set


async def _notify_expiring_send(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    is_owner: bool,
) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        count = await notify_expiring_clients(session, bot)
    status_text = (
        _t(settings.text_expiry_notify_done, count=count)
        if count
        else _t(settings.text_expiry_notify_none)
    )
    await _show_status_then_menu(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        name=name,
        is_owner=is_owner,
        status_text=status_text,
    )


async def _notify_expiring_preview(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    is_owner: bool,
) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        rows = await list_expiring_clients(session)
    if not rows:
        status_text = _t(settings.text_expiry_notify_preview_empty, days=settings.expiry_notify_days)
        await _show_status_then_menu(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            name=name,
            is_owner=is_owner,
            status_text=status_text,
        )
        return
    lines = [_t(settings.text_expiry_notify_preview_title, days=settings.expiry_notify_days)]
    now = datetime.utcnow()
    for client, _agent in rows:
        days_left = max(0, math.ceil((client.expires_at - now).total_seconds() / 86400))
        expires_at = client.expires_at.strftime("%d.%m.%Y")
        lines.append(
            _t(
                settings.text_expiry_notify_preview_line,
                username=client.username,
                expires_at=expires_at,
                days_left=days_left,
            )
        )
    await _show_status_then_menu(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        name=name,
        is_owner=is_owner,
        status_text="\n".join(lines),
    )


@router.message(Command("notify_expiring"))
async def notify_expiring_command(message: Message) -> None:
    settings = get_settings()
    user_id = message.from_user.id
    if user_id != settings.owner_telegram_id and user_id not in settings.admin_id_set:
        await message.answer(_t(settings.text_no_access_message))
        return
    await _notify_expiring_send(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        name=message.from_user.full_name,
        is_owner=user_id == settings.owner_telegram_id,
    )


@router.message(Command("notify_expiring_preview"))
async def notify_expiring_preview_command(message: Message) -> None:
    settings = get_settings()
    user_id = message.from_user.id
    if user_id != settings.owner_telegram_id and user_id not in settings.admin_id_set:
        await message.answer(_t(settings.text_no_access_message))
        return
    await _notify_expiring_preview(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        name=message.from_user.full_name,
        is_owner=user_id == settings.owner_telegram_id,
    )


@router.callback_query(lambda call: call.data == "owner:notify:preview")
async def owner_notify_preview(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id and call.from_user.id not in settings.admin_id_set:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _notify_expiring_preview(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=call.from_user.id == settings.owner_telegram_id,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:notify:send")
async def owner_notify_send(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id and call.from_user.id not in settings.admin_id_set:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _notify_expiring_send(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=call.from_user.id == settings.owner_telegram_id,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:agents")
async def owner_agents(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _edit_or_send(call, _t(settings.text_owner_agents_title), reply_markup=owner_agents_menu(), is_menu=True)
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:limit")
async def owner_limit_menu(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _render_owner_limit_menu(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("owner:limit:page:"))
async def owner_limit_page(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    await _render_owner_limit_menu(call, page=page)
    await call.answer()


async def _render_owner_limit_menu(call: CallbackQuery, page: int) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        agents_with_counts = await list_agents(session)
    if not agents_with_counts:
        await _edit_or_send(call, _t(settings.text_owner_limit_no_agents), reply_markup=owner_agents_menu(), is_menu=True)
        return
    rows = []
    for agent, _ in agents_with_counts:
        limit_label = "∞" if agent.credit_limit <= 0 else f"{agent.credit_limit} ₽"
        rows.append((agent.id, _agent_display(agent), limit_label))
    page_size = 8
    total_pages = max(1, math.ceil(len(rows) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    reply_markup = (
        agents_limit_keyboard(page_rows)
        if total_pages == 1
        else agents_limit_pagination_keyboard(page_rows, page, total_pages)
    )
    await _edit_or_send(
        call,
        _t(settings.text_owner_limit_choose_agent),
        reply_markup=reply_markup,
        is_menu=True,
    )


@router.callback_query(lambda call: call.data.startswith("owner:limit:pick:"))
async def owner_limit_pick(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    agent_id = int(call.data.split(":")[-1])
    await state.update_data(agent_id=agent_id)
    await state.set_state(LimitAgentState.waiting_limit)
    await _edit_or_send(
        call,
        _t(settings.text_owner_limit_prompt),
        reply_markup=cancel_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:add_agent")
async def owner_add_agent(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await state.set_state(AddAgentState.waiting_tg_id)
    await _edit_or_send(
        call,
        _t(settings.text_owner_add_agent_prompt),
        reply_markup=cancel_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.message(AddAgentState.waiting_tg_id)
async def owner_add_agent_message(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(message.from_user.id):
        await message.answer(_t(settings.text_no_access_message))
        await state.clear()
        return
    if _is_start(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    if _is_cancel(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    forward_user = message.forward_from
    raw = (message.text or "").strip()
    async with SessionLocal() as session:
        agent = None
        if forward_user:
            agent = await get_or_create_agent(
                session,
                forward_user.id,
                forward_user.full_name,
                forward_user.username,
            )
        else:
            if message.forward_date or message.forward_sender_name or message.forward_from_chat:
                await _render_error_prompt(
                    bot=message.bot,
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    name=message.from_user.full_name,
                    error_text=_t(settings.text_owner_add_agent_forward_failed),
                    prompt_text=_t(settings.text_owner_add_agent_prompt),
                )
                return
            raw = raw.lstrip("@")
            if raw.isdigit():
                agent = await get_or_create_agent(session, int(raw), str(raw))
            else:
                agent = await get_agent_by_username(session, raw)
                if not agent:
                    try:
                        chat = await message.bot.get_chat(f"@{raw}")
                    except Exception:
                        chat = None
                    if chat and getattr(chat, "id", None):
                        first = getattr(chat, "first_name", None)
                        last = getattr(chat, "last_name", None)
                        name = " ".join([part for part in [first, last] if part]) or getattr(
                            chat, "title", None
                        ) or raw
                        agent = await get_or_create_agent(
                            session,
                            chat.id,
                            name,
                            getattr(chat, "username", None),
                        )
    if not agent:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_agent_not_found),
            prompt_text=_t(settings.text_owner_add_agent_prompt),
        )
        return
    await state.clear()
    await _show_status_then_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        is_owner=True,
        status_text=_t(settings.text_owner_add_agent_done),
    )


@router.message(LimitAgentState.waiting_limit)
async def owner_limit_set(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(message.from_user.id):
        await message.answer(_t(settings.text_no_access_message))
        await state.clear()
        return
    if _is_start(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    if _is_cancel(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    try:
        limit = int((message.text or "").strip())
    except ValueError:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_limit_invalid),
            prompt_text=_t(settings.text_owner_limit_prompt),
        )
        return
    if limit < 0:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_limit_negative),
            prompt_text=_t(settings.text_owner_limit_prompt),
        )
        return
    data = await state.get_data()
    agent_id = data.get("agent_id")
    async with SessionLocal() as session:
        agent = await get_agent_by_id(session, agent_id)
        if not agent:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=True,
                status_text=_t(settings.text_agent_not_found),
            )
            await state.clear()
            return
        agent.credit_limit = limit
        await session.commit()
    await state.clear()
    limit_text = _t(settings.text_limit_none) if limit == 0 else f"{limit} ₽"
    await _show_status_then_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        is_owner=True,
        status_text=_t(settings.text_owner_limit_done, agent_name=_agent_display(agent), limit=limit_text),
    )


@router.callback_query(lambda call: call.data == "owner:sync")
async def owner_sync(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return

    await _edit_or_send(call, _t(settings.text_owner_sync_start), is_menu=True)
    async with SessionLocal() as session:
        client = RemnawaveClient(
            settings.remnawave_api_url,
            settings.remnawave_api_key,
            settings.remnawave_mode,
            settings.remnawave_caddy_token,
        )
        removed, updated = await sync_all_clients_with_remnawave(session, client)
    await _edit_or_send(
        call,
        _t(settings.text_owner_sync_done, removed=removed, updated=updated),
        reply_markup=owner_agents_menu(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:report")
async def owner_report(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _render_owner_report(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("owner:report:page:"))
async def owner_report_page(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    await _render_owner_report(call, page=page)
    await call.answer()


async def _render_owner_report(call: CallbackQuery, page: int) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        agents_with_counts = await list_agents(session)

    if not agents_with_counts:
        await _edit_or_send(call, _t(settings.text_owner_report_no_agents), reply_markup=owner_agents_menu(), is_menu=True)
        return

    total_agents = len(agents_with_counts)
    total_active = sum(1 for agent, _ in agents_with_counts if agent.is_active)
    total_clients = sum(count for _, count in agents_with_counts)
    total_debt = sum(agent.current_debt for agent, _ in agents_with_counts)
    limit_sum = sum(agent.credit_limit for agent, _ in agents_with_counts if agent.credit_limit > 0)
    limit_infinite = sum(1 for agent, _ in agents_with_counts if agent.credit_limit <= 0)
    if limit_infinite and limit_sum:
        limit_total = f"∞ + {limit_sum} ₽"
    elif limit_infinite:
        limit_total = _t(settings.text_limit_infinite)
    else:
        limit_total = f"{limit_sum} ₽"

    page_size = 6
    total_pages = max(1, math.ceil(len(agents_with_counts) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = agents_with_counts[start:end]

    header = _t(settings.text_owner_report_header)
    summary = _t(
        settings.text_owner_report_summary,
        agents=total_agents,
        active=total_active,
        clients=total_clients,
        debt=total_debt,
        limit=limit_total,
    )
    cards = []
    for agent, client_count in page_rows:
        status = "✅" if agent.is_active else "🚫"
        limit = _t(settings.text_limit_infinite) if agent.credit_limit <= 0 else f"{agent.credit_limit} ₽"
        cards.append(
            _t(
                settings.text_owner_report_line,
                status=status,
                name=_agent_display(agent),
                id=agent.telegram_id,
                payable=agent.current_debt,
                limit=limit,
                clients=client_count,
            )
        )
    text = "\n\n".join([part for part in [header, summary, *cards] if part.strip()])
    await _edit_or_send(
        call,
        text,
        reply_markup=owner_report_pagination_keyboard(page, total_pages),
        is_menu=True,
    )


@router.callback_query(lambda call: call.data == "owner:delete:client")
async def owner_delete_client(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await state.set_state(DeleteClientState.waiting_username)
    await _render_owner_delete_client_menu(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("owner:delete:client:page:"))
async def owner_delete_client_page(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await state.set_state(DeleteClientState.waiting_username)
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    await _render_owner_delete_client_menu(call, page=page)
    await call.answer()


async def _render_owner_delete_client_menu(call: CallbackQuery, page: int) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        pairs = await list_clients_with_agents(session)
    if not pairs:
        await _edit_or_send(call, _t(settings.text_clients_none), reply_markup=owner_agents_menu(), is_menu=True)
        return
    rows = [(client.id, f"{client.username} · {_agent_display(agent)}") for client, agent in pairs]
    page_size = 8
    total_pages = max(1, math.ceil(len(rows) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    reply_markup = (
        delete_clients_keyboard(page_rows)
        if total_pages == 1
        else delete_clients_pagination_keyboard(page_rows, page, total_pages)
    )
    await _edit_or_send(
        call,
        _t(settings.text_owner_delete_client_prompt),
        reply_markup=reply_markup,
        is_menu=True,
    )


@router.message(DeleteClientState.waiting_username)
async def owner_delete_client_message(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(message.from_user.id):
        await message.answer(_t(settings.text_no_access_message))
        await state.clear()
        return
    if _is_start(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    if _is_cancel(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    forward_user = message.forward_from
    raw = (message.text or "").strip().lstrip("@")
    async with SessionLocal() as session:
        client = None
        if forward_user:
            client = await get_client_by_tg_any(session, telegram_id=forward_user.id)
        else:
            client = await get_client_by_username_any(session, raw)
    if not client:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_owner_delete_not_found),
            prompt_text=_t(settings.text_owner_delete_client_prompt),
        )
        return
    await state.update_data(delete_client_id=client.id, delete_client_username=client.username)
    await state.set_state(DeleteClientState.confirm)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(settings.text_owner_delete_client_confirm, username=client.username),
        reply_markup=delete_confirm_keyboard(f"owner:delete:client:confirm:{client.id}"),
        force_new=True,
    )


@router.callback_query(lambda call: call.data.startswith("owner:delete:client:pick:"))
async def owner_delete_client_pick(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        client_id = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    async with SessionLocal() as session:
        client = await get_client_by_id(session, client_id)
    if not client:
        await call.answer(_t(settings.text_owner_delete_not_found), show_alert=True)
        return
    await state.update_data(delete_client_id=client.id, delete_client_username=client.username)
    await state.set_state(DeleteClientState.confirm)
    await _edit_or_send(
        call,
        _t(settings.text_owner_delete_client_confirm, username=client.username),
        reply_markup=delete_confirm_keyboard(f"owner:delete:client:confirm:{client.id}"),
        is_menu=True,
    )


@router.callback_query(lambda call: call.data.startswith("owner:delete:client:confirm:"))
async def owner_delete_client_confirm(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        client_id = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        deleted = await delete_client_by_id(session, client_id)
    await state.clear()
    username = data.get("delete_client_username") if deleted else None
    status_text = (
        _t(settings.text_owner_delete_client_done, username=username or str(client_id))
        if deleted
        else _t(settings.text_owner_delete_not_found)
    )
    await _show_status_then_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=_is_owner_or_admin(call.from_user.id),
        status_text=status_text,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:delete:agent")
async def owner_delete_agent(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _render_owner_delete_agent_menu(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("owner:delete:agent:page:"))
async def owner_delete_agent_page(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    await _render_owner_delete_agent_menu(call, page=page)
    await call.answer()


async def _render_owner_delete_agent_menu(call: CallbackQuery, page: int) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        agents_with_counts = await list_agents(session)
    if not agents_with_counts:
        await _edit_or_send(call, _t(settings.text_owner_report_no_agents), reply_markup=owner_agents_menu(), is_menu=True)
        return
    rows = [(agent.id, _agent_display(agent)) for agent, _ in agents_with_counts]
    page_size = 8
    total_pages = max(1, math.ceil(len(rows) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    reply_markup = (
        delete_agents_keyboard(page_rows)
        if total_pages == 1
        else delete_agents_pagination_keyboard(page_rows, page, total_pages)
    )
    await _edit_or_send(
        call,
        _t(settings.text_owner_delete_agent_pick),
        reply_markup=reply_markup,
        is_menu=True,
    )


@router.callback_query(lambda call: call.data.startswith("owner:delete:agent:pick:"))
async def owner_delete_agent_pick(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        agent_id = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    async with SessionLocal() as session:
        agent = await get_agent_by_id(session, agent_id)
    if not agent:
        await call.answer(_t(settings.text_owner_delete_not_found), show_alert=True)
        return
    await _edit_or_send(
        call,
        _t(settings.text_owner_delete_agent_confirm, name=_agent_display(agent)),
        reply_markup=delete_confirm_keyboard(f"owner:delete:agent:confirm:{agent.id}"),
        is_menu=True,
    )




@router.callback_query(lambda call: call.data.startswith("owner:delete:agent:confirm:"))
async def owner_delete_agent_confirm(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    try:
        agent_id = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_page_invalid), show_alert=True)
        return
    async with SessionLocal() as session:
        agent, clients_deleted = await delete_agent_by_id(session, agent_id)
    await state.clear()
    status_text = (
        _t(settings.text_owner_delete_agent_done, name=_agent_display(agent), clients=clients_deleted)
        if agent
        else _t(settings.text_owner_delete_not_found)
    )
    await _show_status_then_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=_is_owner_or_admin(call.from_user.id),
        status_text=status_text,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:back")
async def owner_back(call: CallbackQuery) -> None:
    settings = get_settings()
    if not _is_owner_or_admin(call.from_user.id):
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _edit_or_send(
        call,
        _t(settings.text_main_menu_prompt),
        reply_markup=main_menu(is_owner=True),
        is_menu=True,
    )
    await call.answer()
