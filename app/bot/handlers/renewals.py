import logging
import math
from datetime import datetime

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import cancel_keyboard, clients_keyboard, skip_keyboard, tariffs_keyboard
from app.bot.states import RenewState
from app.config import get_settings
from app.db.session import SessionLocal
from app.models import Renewal
from app.services.agent_service import get_agent_by_id, get_or_create_agent
from app.services.client_service import (
    add_days,
    get_client_by_id,
    get_client_by_username,
    get_client_by_username_any,
    list_clients_by_agent,
    list_clients_with_agents,
)
from app.services.debt_service import increase_debt
from app.services.remnawave_service import create_or_extend_user

from .common import (
    _calc_base_debt,
    _credit_limit_exceeded,
    _is_agent_allowed,
    _is_cancel,
    _is_skip,
    _is_start,
    _t,
    _tariffs_for_user,
)
from .menu import _edit_or_send, _render_error_prompt, _render_menu_text, _show_start_menu, _show_status_then_menu
from .clients import _format_client_meta


router = Router()


@router.callback_query(lambda call: call.data == "client:renew")
async def renew_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    await state.set_state(RenewState.waiting_username)
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set

    async with SessionLocal() as session:
        if is_owner or is_admin:
            client_rows = await list_clients_with_agents(session)
            buttons = [
                (
                    client.id,
                    f"{client.username} ({agent.name})",
                    _format_client_meta(client.expires_at, client.last_payment_amount),
                )
                for client, agent in client_rows
                if client.username
            ]
            if not buttons:
                await _edit_or_send(call, _t(settings.text_clients_none), is_menu=True)
                await call.answer()
                return
            await _edit_or_send(
                call,
                _t(settings.text_renew_pick_prompt_owner),
                reply_markup=clients_keyboard(buttons, include_cancel=True),
                is_menu=True,
            )
            logging.info("Renew list for owner/admin: %s", [c[0] for c in buttons])
            await call.answer()
            return

        agent = await get_or_create_agent(
            session,
            call.from_user.id,
            call.from_user.full_name,
            call.from_user.username,
        )
        if _credit_limit_exceeded(agent, 0):
            await _show_status_then_menu(
                bot=call.bot,
                chat_id=call.message.chat.id,
                user_id=call.from_user.id,
                name=call.from_user.full_name,
                is_owner=False,
                status_text=_t(
                    settings.text_limit_reached_renew,
                    current=agent.current_debt,
                    limit=agent.credit_limit,
                ),
            )
            await call.answer()
            return
        clients = await list_clients_by_agent(session, agent.id)
        clients = [client for client in clients if client.username]
        if not clients:
            await _edit_or_send(call, _t(settings.text_clients_none), is_menu=True)
            await call.answer()
            return
        buttons = [
            (
                client.id,
                client.username,
                _format_client_meta(client.expires_at, client.last_payment_amount),
            )
            for client in clients
        ]
        await _edit_or_send(
            call,
            _t(settings.text_renew_pick_prompt_agent),
            reply_markup=clients_keyboard(buttons, include_cancel=True),
            is_menu=True,
        )
        logging.info("Renew list for agent %s: %s", agent.id, [c.username for c in clients])
        await call.answer()


@router.callback_query(lambda call: call.data.startswith("renew:pick:"))
async def renew_pick_client(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    client_id = int(call.data.split(":")[-1])
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set

    async with SessionLocal() as session:
        if is_owner or is_admin:
            picked = await get_client_by_id(session, client_id)
        else:
            agent = await get_or_create_agent(
                session,
                call.from_user.id,
                call.from_user.full_name,
                call.from_user.username,
            )
            clients = await list_clients_by_agent(session, agent.id)
            picked = next((c for c in clients if c.id == client_id), None)
    if not picked:
        await call.answer(_t(get_settings().text_client_not_found_alert), show_alert=True)
        return
    await state.update_data(username=picked.username, client_id=picked.id, agent_id=picked.agent_id)
    await state.set_state(RenewState.waiting_days)
    await _edit_or_send(
        call,
        _t(get_settings().text_renew_days_prompt),
        reply_markup=skip_keyboard("days"),
        is_menu=True,
    )
    await call.answer()


@router.message(RenewState.waiting_username)
async def renew_username(message: Message, state: FSMContext) -> None:
    if not await _is_agent_allowed(message.from_user.id):
        await message.answer(_t(get_settings().text_no_access_message))
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
    username = (message.text or "").strip()

    await state.update_data(username=username)
    await state.set_state(RenewState.waiting_days)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(get_settings().text_renew_days_prompt),
        reply_markup=skip_keyboard("days"),
        force_new=True,
    )


@router.message(RenewState.waiting_days)
async def renew_days(message: Message, state: FSMContext) -> None:
    if not await _is_agent_allowed(message.from_user.id):
        await message.answer(_t(get_settings().text_no_access_message))
        await state.clear()
        return

    settings = get_settings()
    if _is_start(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    if _is_cancel(message.text):
        await state.clear()
        await _show_start_menu(message)
        return
    if _is_skip(message.text):
        days = settings.default_renew_days
    else:
        try:
            days = int((message.text or "").strip())
        except ValueError:
            await _render_error_prompt(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                error_text=_t(settings.text_days_invalid),
                prompt_text=_t(settings.text_renew_days_prompt),
                reply_markup=skip_keyboard("days"),
            )
            return
        if days <= 0:
            await _render_error_prompt(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                error_text=_t(settings.text_days_positive),
                prompt_text=_t(settings.text_renew_days_prompt),
                reply_markup=skip_keyboard("days"),
            )
            return

    await state.update_data(days=days)
    data = await state.get_data()
    target_telegram_id = message.from_user.id
    target_agent_id = data.get("agent_id")
    is_owner = message.from_user.id == settings.owner_telegram_id
    is_admin = message.from_user.id in settings.admin_id_set
    if target_agent_id:
        async with SessionLocal() as session:
            agent = await get_agent_by_id(session, target_agent_id)
            if agent:
                target_telegram_id = agent.telegram_id
    tariffs = _tariffs_for_user(
        settings,
        target_telegram_id,
        show_all=not target_agent_id and (is_owner or is_admin),
    )
    if not tariffs:
        await _render_menu_text(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            text=f"{_t(settings.text_tariffs_empty)}\n\n{_t(settings.text_renew_amount_prompt)}",
            reply_markup=cancel_keyboard(),
            force_new=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(RenewState.waiting_amount)
        return
    await state.set_state(RenewState.waiting_tariff)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(settings.text_tariff_pick_prompt),
        reply_markup=tariffs_keyboard(tariffs),
        force_new=True,
    )


@router.callback_query(lambda call: call.data == "skip:days")
async def renew_skip_days(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    await state.update_data(days=settings.default_renew_days)
    data = await state.get_data()
    target_telegram_id = call.from_user.id
    target_agent_id = data.get("agent_id")
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    if target_agent_id:
        async with SessionLocal() as session:
            agent = await get_agent_by_id(session, target_agent_id)
            if agent:
                target_telegram_id = agent.telegram_id
    tariffs = _tariffs_for_user(
        settings,
        target_telegram_id,
        show_all=not target_agent_id and (is_owner or is_admin),
    )
    if not tariffs:
        await _edit_or_send(
            call,
            f"{_t(settings.text_tariffs_empty)}\n\n{_t(settings.text_renew_amount_prompt)}",
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(RenewState.waiting_amount)
        await call.answer()
        return
    await state.set_state(RenewState.waiting_tariff)
    await _edit_or_send(
        call,
        _t(settings.text_tariff_pick_prompt),
        reply_markup=tariffs_keyboard(tariffs),
        is_menu=True,
    )
    await call.answer()


@router.message(RenewState.waiting_amount)
async def renew_amount(message: Message, state: FSMContext) -> None:
    if not await _is_agent_allowed(message.from_user.id):
        await message.answer(_t(get_settings().text_no_access_message))
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
        amount = int((message.text or "").strip())
    except ValueError:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_invalid),
            prompt_text=_t(get_settings().text_renew_amount_prompt),
            reply_markup=cancel_keyboard(),
        )
        return
    if amount <= 0:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_positive),
            prompt_text=_t(get_settings().text_renew_amount_prompt),
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    username = data.get("username")
    days = data.get("days")
    client_id = data.get("client_id")
    base_price = data.get("tariff_base_price")
    tariff_remnawave = data.get("tariff_remnawave") or {}
    settings = get_settings()
    is_owner = message.from_user.id == settings.owner_telegram_id
    is_admin = message.from_user.id in settings.admin_id_set

    logging.info(
        "Renew flow: caller=%s username=%s client_id=%s days=%s amount=%s owner=%s admin=%s",
        message.from_user.id,
        username,
        client_id,
        days,
        amount,
        is_owner,
        is_admin,
    )
    async with SessionLocal() as session:
        caller_agent = await get_or_create_agent(
            session,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )
        if not (is_owner or is_admin) and not caller_agent.is_active:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_agent_blocked),
            )
            await state.clear()
            return

        if is_owner or is_admin:
            if client_id:
                client = await get_client_by_id(session, client_id)
            else:
                client = await get_client_by_username_any(session, username)
        else:
            client = await get_client_by_username(session, caller_agent.id, username)
        if not client:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_client_not_found),
            )
            await state.clear()
            return
        logging.info(
            "Renew target client: id=%s username=%s agent_id=%s",
            client.id,
            client.username,
            client.agent_id,
        )

        target_agent = (
            await get_agent_by_id(session, client.agent_id) if (is_owner or is_admin) else caller_agent
        )
        if not target_agent:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_target_agent_not_found),
            )
            await state.clear()
            return
        if not target_agent.is_active:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_target_agent_blocked),
            )
            await state.clear()
            return

        base_price = base_price or settings.base_subscription_price
        owner_share = max(
            0,
            math.ceil((base_price * days) / max(settings.default_renew_days, 1)),
        )
        projected = target_agent.current_debt + owner_share
        logging.info(
            "Renew debt calc: agent_id=%s debt=%s owner_share=%s projected=%s limit=%s",
            target_agent.id,
            target_agent.current_debt,
            owner_share,
            projected,
            target_agent.credit_limit,
        )
        if target_agent.credit_limit > 0 and projected > target_agent.credit_limit:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(
                    settings.text_limit_reached_renew_inline,
                    current=target_agent.current_debt,
                    limit=target_agent.credit_limit,
                ),
            )
            await state.clear()
            return

        try:
            result = await create_or_extend_user(
                username=client.username,
                days=days,
                description=f"agent:{target_agent.telegram_id}",
                telegram_id=client.telegram_id,
                overrides=tariff_remnawave,
            )
            logging.info("Renew Remnawave result: %s", result)
        except Exception as exc:
            logging.exception("Renew Remnawave error")
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_renew_error, error=exc),
            )
            await state.clear()
            return

        client.expires_at = result.get("expires_at") or add_days(client.expires_at, days)
        client.subscription_link = result.get("subscription_url") or client.subscription_link
        client.monthly_price = amount
        client.last_payment_amount = amount
        client.last_payment_at = datetime.utcnow()
        client.tariff_base_price = base_price
        client.tariff_name = data.get("tariff_name") or _t(settings.text_client_tariff_default)
        session.add(
            Renewal(
                agent_id=target_agent.id,
                client_id=client.id,
                days=days,
                debt_amount=owner_share,
                payment_amount=amount,
            )
        )
        await session.commit()

        await increase_debt(
            session,
            target_agent,
            owner_share,
            f"Продление {days} дней для {client.username}",
        )
        profit = amount - owner_share
        await _show_status_then_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            is_owner=message.from_user.id == settings.owner_telegram_id,
            status_text=_t(
                settings.text_renew_success,
                days=days,
                profit=profit,
                amount=amount,
                owner_share=owner_share,
                payable=target_agent.current_debt,
            ),
        )
    await state.clear()
