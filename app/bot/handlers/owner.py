import math
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import agents_limit_keyboard, cancel_keyboard, main_menu, owner_agents_menu
from app.bot.states import AddAgentState, LimitAgentState
from app.config import get_settings
from app.db.session import SessionLocal
from app.remnawave.client import RemnawaveClient
from app.services.agent_service import (
    get_agent_by_id,
    get_agent_by_username,
    get_or_create_agent,
    list_agents,
)
from app.services.notify_service import list_expiring_clients, notify_expiring_clients
from app.services.sync_service import sync_all_clients_with_remnawave

from .common import _agent_display, _is_cancel, _is_start, _t
from .menu import _edit_or_send, _render_error_prompt, _show_start_menu, _show_status_then_menu


router = Router()


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
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _edit_or_send(call, _t(settings.text_owner_agents_title), reply_markup=owner_agents_menu(), is_menu=True)
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:limit")
async def owner_limit_menu(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    async with SessionLocal() as session:
        agents_with_counts = await list_agents(session)
    if not agents_with_counts:
        await _edit_or_send(call, _t(settings.text_owner_limit_no_agents), reply_markup=owner_agents_menu(), is_menu=True)
        await call.answer()
        return
    rows = []
    for agent, _ in agents_with_counts:
        limit_label = "∞" if agent.credit_limit <= 0 else f"{agent.credit_limit} ₽"
        rows.append((agent.id, _agent_display(agent), limit_label))
    await _edit_or_send(
        call,
        _t(settings.text_owner_limit_choose_agent),
        reply_markup=agents_limit_keyboard(rows),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("owner:limit:pick:"))
async def owner_limit_pick(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id:
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
    if call.from_user.id != settings.owner_telegram_id:
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
    if message.from_user.id != settings.owner_telegram_id:
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
    if message.from_user.id != settings.owner_telegram_id:
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
    if call.from_user.id != settings.owner_telegram_id:
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
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    async with SessionLocal() as session:
        agents_with_counts = await list_agents(session)

    if not agents_with_counts:
        await _edit_or_send(call, _t(settings.text_owner_report_no_agents), reply_markup=owner_agents_menu(), is_menu=True)
        await call.answer()
        return

    lines = [_t(settings.text_owner_report_header)]
    for agent, client_count in agents_with_counts:
        status = "✅" if agent.is_active else "🚫"
        limit = _t(settings.text_limit_infinite) if agent.credit_limit <= 0 else f"{agent.credit_limit} ₽"
        lines.append(
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
    await _edit_or_send(call, "\n".join(lines), reply_markup=owner_agents_menu(), is_menu=True)
    await call.answer()


@router.callback_query(lambda call: call.data == "owner:back")
async def owner_back(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    await _edit_or_send(
        call,
        _t(settings.text_main_menu_prompt),
        reply_markup=main_menu(is_owner=True),
        is_menu=True,
    )
    await call.answer()
