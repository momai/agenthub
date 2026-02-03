import logging
import math
from datetime import datetime

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    back_to_menu_keyboard,
    cancel_keyboard,
    clients_keyboard,
    renew_clients_keyboard,
    renew_days_keyboard,
    tariffs_keyboard,
)
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
    _calc_amount_by_days,
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

_RENEW_PAGE_SIZE = 8


@router.callback_query(lambda call: call.data == "client:renew")
async def renew_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    await state.set_state(RenewState.waiting_username)
    await _render_renew_list(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("renew:list:page:"))
async def renew_list_page(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(get_settings().text_page_invalid), show_alert=True)
        return
    await _render_renew_list(call, page=page)
    await call.answer()


def _days_left_int(expires_at: datetime | None) -> int:
    if not expires_at:
        return 0
    now = datetime.utcnow()
    return max(0, math.ceil((expires_at - now).total_seconds() / 86400))


def _format_expires_short(expires_at: datetime | None) -> str:
    if not expires_at:
        return "—"
    return f"{_days_left_int(expires_at)}д"


async def _render_renew_list(call: CallbackQuery, page: int) -> None:
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    async with SessionLocal() as session:
        if is_owner or is_admin:
            client_rows = await list_clients_with_agents(session)
            items = [
                (
                    client.id,
                    f"{client.username} ({agent.name})",
                    client.monthly_price,
                )
                for client, agent in client_rows
                if client.username
            ]
            if not items:
                await _edit_or_send(
                    call,
                    _t(settings.text_clients_none),
                    reply_markup=back_to_menu_keyboard(),
                    is_menu=True,
                )
                return
            total_pages = max(1, math.ceil(len(items) / _RENEW_PAGE_SIZE))
            page = max(1, min(page, total_pages))
            start = (page - 1) * _RENEW_PAGE_SIZE
            end = start + _RENEW_PAGE_SIZE
            page_rows = items[start:end]
            reply_markup = (
                clients_keyboard(page_rows, include_cancel=True)
                if total_pages == 1
                else renew_clients_keyboard(page_rows, page, total_pages, include_cancel=True)
            )
            await _edit_or_send(
                call,
                _t(settings.text_renew_pick_prompt_owner),
                reply_markup=reply_markup,
                is_menu=True,
            )
            logging.info("Renew list for owner/admin: %s", [c[0] for c in items])
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
            return
        clients = await list_clients_by_agent(session, agent.id)
        clients = [client for client in clients if client.username]
        if not clients:
            await _edit_or_send(
                call,
                _t(settings.text_clients_none),
                reply_markup=back_to_menu_keyboard(),
                is_menu=True,
            )
            return
        items = [
            (
                client.id,
                client.username,
                client.monthly_price,
            )
            for client in clients
        ]
        total_pages = max(1, math.ceil(len(items) / _RENEW_PAGE_SIZE))
        page = max(1, min(page, total_pages))
        start = (page - 1) * _RENEW_PAGE_SIZE
        end = start + _RENEW_PAGE_SIZE
        page_rows = items[start:end]
        reply_markup = (
            clients_keyboard(page_rows, include_cancel=True)
            if total_pages == 1
            else renew_clients_keyboard(page_rows, page, total_pages, include_cancel=True)
        )
        await _edit_or_send(
            call,
            _t(settings.text_renew_pick_prompt_agent),
            reply_markup=reply_markup,
            is_menu=True,
        )
        logging.info("Renew list for agent %s: %s", agent.id, [c.username for c in clients])


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

    days_left_int = _days_left_int(picked.expires_at)
    if days_left_int > settings.renew_min_days_left:
        await _edit_or_send(
            call,
            _t(
                settings.text_renew_too_early,
                min_days=settings.renew_min_days_left,
                days_left=days_left_int,
            ),
            reply_markup=back_to_menu_keyboard(),
            is_menu=True,
        )
        await call.answer()
        return
    # Формируем карточку клиента
    tariff_name = picked.tariff_name or _t(settings.text_client_tariff_default)
    base_price = picked.tariff_base_price or settings.base_subscription_price
    days_left = _format_expires_short(picked.expires_at)
    days_left_int = _days_left_int(picked.expires_at)
    price = f"{picked.monthly_price}₽" if picked.monthly_price else "—"
    client_price_display = f"{picked.monthly_price} ₽/мес" if picked.monthly_price else "—"

    await state.update_data(
        username=picked.username,
        client_id=picked.id,
        agent_id=picked.agent_id,
        renew_old_tariff=tariff_name,
        renew_old_base_price=base_price,
        renew_client_price=client_price_display,
        renew_client_price_value=picked.monthly_price,
        renew_days_left=days_left_int,
    )
    await state.set_state(RenewState.waiting_days)

    card_text = _t(
        settings.text_renew_client_card,
        username=picked.username,
        tariff=tariff_name,
        base_price=base_price,
        days_left=days_left,
        price=price,
    )
    await _edit_or_send(
        call,
        card_text,
        reply_markup=renew_days_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "renew:back")
async def renew_back(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    await state.set_state(RenewState.waiting_username)
    await _render_renew_list(call, page=1)
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
    settings = get_settings()
    is_owner = message.from_user.id == settings.owner_telegram_id
    is_admin = message.from_user.id in settings.admin_id_set
    async with SessionLocal() as session:
        if is_owner or is_admin:
            picked = await get_client_by_username_any(session, username)
        else:
            agent = await get_or_create_agent(
                session,
                message.from_user.id,
                message.from_user.full_name,
                message.from_user.username,
            )
            picked = await get_client_by_username(session, agent.id, username)
    if not picked:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_client_not_found),
            prompt_text=_t(settings.text_renew_pick_prompt_agent),
            reply_markup=cancel_keyboard(),
        )
        return
    days_left_int = _days_left_int(picked.expires_at)
    if days_left_int > settings.renew_min_days_left:
        await _render_menu_text(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            text=_t(
                settings.text_renew_too_early,
                min_days=settings.renew_min_days_left,
                days_left=days_left_int,
            ),
            reply_markup=back_to_menu_keyboard(),
            force_new=True,
        )
        return

    tariff_name = picked.tariff_name or _t(settings.text_client_tariff_default)
    base_price = picked.tariff_base_price or settings.base_subscription_price
    price = f"{picked.monthly_price}₽" if picked.monthly_price else "—"
    client_price_display = f"{picked.monthly_price} ₽/мес" if picked.monthly_price else "—"

    await state.update_data(
        username=picked.username,
        client_id=picked.id,
        agent_id=picked.agent_id,
        renew_old_tariff=tariff_name,
        renew_old_base_price=base_price,
        renew_client_price=client_price_display,
        renew_client_price_value=picked.monthly_price,
        renew_days_left=days_left_int,
    )
    await state.set_state(RenewState.waiting_days)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(settings.text_renew_days_prompt),
        reply_markup=renew_days_keyboard(),
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
    await _render_error_prompt(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        error_text=_t(settings.text_renew_days_buttons_only),
        prompt_text=_t(settings.text_renew_days_prompt),
        reply_markup=renew_days_keyboard(),
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
        old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
        old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
        client_price = data.get("renew_client_price") or "—"
        amount_prompt = _t(settings.text_renew_amount_prompt_with_prev, prev=client_price)
        prompt_text = _t(
            settings.text_renew_amount_context,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            new_tariff=old_tariff,
            new_base_price=settings.base_subscription_price,
            client_price=client_price,
            prompt=amount_prompt,
        )
        await state.update_data(renew_amount_prompt=prompt_text)
        await _render_menu_text(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            text=f"{_t(settings.text_tariffs_empty)}\n\n{prompt_text}",
            reply_markup=cancel_keyboard(),
            force_new=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(RenewState.waiting_amount)
        return
    await state.set_state(RenewState.waiting_tariff)
    old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
    old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
    client_price = data.get("renew_client_price") or "—"
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(
            settings.text_renew_tariff_pick_prompt,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            client_price=client_price,
        ),
        reply_markup=tariffs_keyboard(
            tariffs,
            include_back=True,
            back_callback="renew:tariff:back",
            label_mode="price",
            top_button=(_t(settings.btn_renew_same), "renew:same"),
        ),
        force_new=True,
    )


async def _renew_select_days(call: CallbackQuery, state: FSMContext, days: int) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    await state.update_data(days=days)
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
        old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
        old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
        client_price = data.get("renew_client_price") or "—"
        amount_prompt = _t(settings.text_renew_amount_prompt_with_prev, prev=client_price)
        prompt_text = _t(
            settings.text_renew_amount_context,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            new_tariff=old_tariff,
            new_base_price=settings.base_subscription_price,
            client_price=client_price,
            prompt=amount_prompt,
        )
        await state.update_data(renew_amount_prompt=prompt_text)
        await _edit_or_send(
            call,
            f"{_t(settings.text_tariffs_empty)}\n\n{prompt_text}",
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(RenewState.waiting_amount)
        await call.answer()
        return
    await state.set_state(RenewState.waiting_tariff)
    old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
    old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
    client_price = data.get("renew_client_price") or "—"
    await _edit_or_send(
        call,
        _t(
            settings.text_renew_tariff_pick_prompt,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            client_price=client_price,
        ),
        reply_markup=tariffs_keyboard(
            tariffs,
            include_back=True,
            back_callback="renew:tariff:back",
            label_mode="price",
            top_button=(_t(settings.btn_renew_same), "renew:same"),
        ),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "skip:days")
async def renew_skip_days(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    await _renew_select_days(call, state, settings.default_renew_days)


@router.callback_query(lambda call: call.data.startswith("renew:days:"))
async def renew_pick_days(call: CallbackQuery, state: FSMContext) -> None:
    try:
        days = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(get_settings().text_page_invalid), show_alert=True)
        return
    await _renew_select_days(call, state, days)


@router.callback_query(lambda call: call.data == "renew:tariff:back")
async def renew_tariff_back(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    data = await state.get_data()
    client_id = data.get("client_id")
    settings = get_settings()
    if not client_id:
        await _render_renew_list(call, page=1)
        await call.answer()
        return

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

    await state.set_state(RenewState.waiting_days)
    tariff_name = picked.tariff_name or _t(settings.text_client_tariff_default)
    base_price = picked.tariff_base_price or settings.base_subscription_price
    days_left = _format_expires_short(picked.expires_at)
    price = f"{picked.monthly_price}₽" if picked.monthly_price else "—"
    card_text = _t(
        settings.text_renew_client_card,
        username=picked.username,
        tariff=tariff_name,
        base_price=base_price,
        days_left=days_left,
        price=price,
    )
    await _edit_or_send(
        call,
        card_text,
        reply_markup=renew_days_keyboard(),
        is_menu=True,
    )
    await call.answer()


async def _process_renewal(
    *,
    bot,
    chat_id: int,
    user_id: int,
    full_name: str,
    username: str | None,
    is_owner: bool,
    is_admin: bool,
    state: FSMContext,
    amount_monthly: int,
) -> None:
    data = await state.get_data()
    username_target = data.get("username")
    days = data.get("days")
    client_id = data.get("client_id")
    base_price = data.get("tariff_base_price")
    tariff_remnawave = data.get("tariff_remnawave") or {}
    settings = get_settings()
    if not days:
        days = settings.default_renew_days
    else:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = settings.default_renew_days
    if days <= 0:
        days = settings.default_renew_days

    amount_total = _calc_amount_by_days(settings, amount_monthly, days)
    old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
    old_monthly_price = data.get("renew_client_price_value") or 0
    days_left = data.get("renew_days_left") or 0
    # если тариф/цена выросли — переносим остаток и добавляем к сумме
    if amount_monthly > old_monthly_price and days_left > 0:
        amount_total += _calc_amount_by_days(settings, amount_monthly - old_monthly_price, days_left)
    logging.info(
        "Renew flow: caller=%s username=%s client_id=%s days=%s amount_monthly=%s amount_total=%s owner=%s admin=%s",
        user_id,
        username_target,
        client_id,
        days,
        amount_monthly,
        amount_total,
        is_owner,
        is_admin,
    )
    async with SessionLocal() as session:
        caller_agent = await get_or_create_agent(session, user_id, full_name, username)
        if not (is_owner or is_admin) and not caller_agent.is_active:
            await _show_status_then_menu(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_agent_blocked),
            )
            await state.clear()
            return

        if is_owner or is_admin:
            if client_id:
                client = await get_client_by_id(session, client_id)
            else:
                client = await get_client_by_username_any(session, username_target)
        else:
            client = await get_client_by_username(session, caller_agent.id, username_target)
        if not client:
            await _show_status_then_menu(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
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

        target_agent = await get_agent_by_id(session, client.agent_id) if (is_owner or is_admin) else caller_agent
        if not target_agent:
            await _show_status_then_menu(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_target_agent_not_found),
            )
            await state.clear()
            return
        if not target_agent.is_active:
            await _show_status_then_menu(
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_target_agent_blocked),
            )
            await state.clear()
            return

        base_price = base_price or settings.base_subscription_price
        owner_share = _calc_base_debt(settings, days, base_price)
        if base_price > old_base_price and days_left > 0:
            owner_share += _calc_base_debt(settings, days_left, base_price - old_base_price)
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
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
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
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                name=full_name,
                is_owner=is_owner,
                status_text=_t(settings.text_renew_error, error=exc),
            )
            await state.clear()
            return

        client.expires_at = result.get("expires_at") or add_days(client.expires_at, days)
        client.subscription_link = result.get("subscription_url") or client.subscription_link
        client.monthly_price = amount_monthly
        client.last_payment_amount = amount_total
        client.last_payment_at = datetime.utcnow()
        client.tariff_base_price = base_price
        client.tariff_name = data.get("tariff_name") or _t(settings.text_client_tariff_default)
        session.add(
            Renewal(
                agent_id=target_agent.id,
                client_id=client.id,
                days=days,
                debt_amount=owner_share,
                payment_amount=amount_total,
            )
        )
        await session.commit()

        await increase_debt(
            session,
            target_agent,
            owner_share,
            f"Продление {days} дней для {client.username}",
        )
        await session.refresh(target_agent)
        profit = amount_total - owner_share
        await _show_status_then_menu(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            name=full_name,
            is_owner=is_owner,
            status_text=_t(
                settings.text_renew_success,
                days=days,
                profit=profit,
                amount=amount_total,
                owner_share=owner_share,
                payable=target_agent.current_debt,
            ),
        )
    await state.clear()


@router.callback_query(lambda call: call.data == "renew:same")
async def renew_same_tariff(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    data = await state.get_data()
    old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
    old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
    client_price_value = data.get("renew_client_price_value")
    client_price = data.get("renew_client_price") or "—"
    days = data.get("days")
    target_agent_id = data.get("agent_id")
    target_telegram_id = call.from_user.id
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set

    if not days:
        await _edit_or_send(
            call,
            _t(settings.text_renew_days_prompt),
            reply_markup=renew_days_keyboard(),
            is_menu=True,
        )
        await call.answer()
        return
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = None
    if not days or days <= 0:
        await _edit_or_send(
            call,
            _t(settings.text_renew_days_prompt),
            reply_markup=renew_days_keyboard(),
            is_menu=True,
        )
        await call.answer()
        return

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
    matched = next((t for t in tariffs if (t.get("name") or "") == old_tariff), None)
    base_price = (matched or {}).get("base_price") or old_base_price
    await state.update_data(
        tariff_base_price=base_price,
        tariff_name=old_tariff,
        tariff_remnawave=(matched or {}).get("remnawave") or {},
    )

    if not client_price_value or client_price_value <= 0:
        amount_prompt = _t(settings.text_renew_amount_prompt_with_prev, prev=client_price)
        prompt_text = _t(
            settings.text_renew_amount_context,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            new_tariff=old_tariff,
            new_base_price=base_price,
            client_price=client_price,
            prompt=amount_prompt,
        )
        await state.update_data(renew_amount_prompt=prompt_text)
        await _edit_or_send(
            call,
            prompt_text,
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await state.set_state(RenewState.waiting_amount)
        await call.answer()
        return

    await state.set_state(RenewState.waiting_amount)
    await _process_renewal(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        full_name=call.from_user.full_name,
        username=call.from_user.username,
        is_owner=is_owner,
        is_admin=is_admin,
        state=state,
        amount_monthly=client_price_value,
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
    settings = get_settings()
    data = await state.get_data()
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        prompt_text = data.get("renew_amount_prompt") or _t(settings.text_renew_amount_prompt)
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_invalid),
            prompt_text=prompt_text,
            reply_markup=cancel_keyboard(),
        )
        return
    if amount <= 0:
        prompt_text = data.get("renew_amount_prompt") or _t(settings.text_renew_amount_prompt)
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_positive),
            prompt_text=prompt_text,
            reply_markup=cancel_keyboard(),
        )
        return

    await _process_renewal(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        is_owner=message.from_user.id == settings.owner_telegram_id,
        is_admin=message.from_user.id in settings.admin_id_set,
        state=state,
        amount_monthly=amount,
    )
