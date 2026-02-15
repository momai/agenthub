import logging
from datetime import datetime

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    amount_presets_keyboard,
    back_to_menu_keyboard,
    cancel_keyboard,
    clients_list_pagination_keyboard,
    clients_keyboard,
    new_client_confirm_keyboard,
    new_client_days_keyboard,
    skip_keyboard,
    tariffs_keyboard,
)
from app.bot.states import NewClientState, RenewState
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.agent_service import get_agent_by_id, get_or_create_agent
from app.services.client_service import (
    add_days,
    create_client,
    get_client_by_id,
    get_client_by_username,
    get_client_by_username_any,
    list_clients_by_agent,
    list_clients_with_agents,
)
from app.services.debt_service import increase_debt
from app.services.remnawave_service import create_user_only, username_exists

from .common import (
    _amount_presets,
    _agent_display,
    USERNAME_PATTERN,
    _calc_amount_by_days,
    _calc_base_debt,
    _credit_limit_exceeded,
    _format_traffic,
    _is_agent_allowed,
    _is_cancel,
    _is_skip,
    _is_start,
    _t,
    _tariffs_for_user,
)
from .menu import _edit_or_send, _render_error_prompt, _render_menu_text, _show_start_menu, _show_status_then_menu


router = Router()


@router.callback_query(lambda call: call.data == "client:new")
async def new_client_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    if not settings.tariffs():
        async with SessionLocal() as session:
            agent = await get_or_create_agent(
                session,
                call.from_user.id,
                call.from_user.full_name,
                call.from_user.username,
            )
            if _credit_limit_exceeded(agent, settings.base_subscription_price):
                await _show_status_then_menu(
                    bot=call.bot,
                    chat_id=call.message.chat.id,
                    user_id=call.from_user.id,
                    name=call.from_user.full_name,
                    is_owner=call.from_user.id == settings.owner_telegram_id,
                    status_text=_t(
                        settings.text_limit_reached_create,
                        current=agent.current_debt,
                        limit=agent.credit_limit,
                    ),
                )
                await call.answer()
                return
    await state.set_state(NewClientState.waiting_username)
    await _edit_or_send(
        call,
        _t(settings.text_new_client_username_prompt),
        reply_markup=cancel_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "tariff:back")
async def tariff_back(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    current_state = await state.get_state()
    target_agent_id = data.get("agent_id")
    target_telegram_id = call.from_user.id
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
            _t(settings.text_tariffs_empty),
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await call.answer()
        return
    if current_state == NewClientState.waiting_price.state:
        await state.set_state(NewClientState.waiting_tariff)
    elif current_state == RenewState.waiting_amount.state:
        await state.set_state(RenewState.waiting_tariff)
    await _edit_or_send(
        call,
        _t(settings.text_tariff_pick_prompt),
        reply_markup=tariffs_keyboard(tariffs, label_mode="price"),
        is_menu=True,
    )
    await call.answer()


@router.message(NewClientState.waiting_username)
async def new_client_username(message: Message, state: FSMContext) -> None:
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
    if not USERNAME_PATTERN.match(username):
        settings = get_settings()
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_username_invalid),
            prompt_text=_t(settings.text_new_client_username_prompt),
        )
        return
    settings = get_settings()
    try:
        if await username_exists(username):
            await _render_error_prompt(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                name=message.from_user.full_name,
                error_text=_t(settings.text_username_taken_panel, username=username),
                prompt_text=_t(settings.text_new_client_username_prompt),
                reply_markup=cancel_keyboard(),
            )
            return
    except Exception as exc:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(settings.text_create_error, error=exc),
            prompt_text=_t(settings.text_new_client_username_prompt),
        )
        return

    await state.update_data(username=username)
    await state.set_state(NewClientState.waiting_days)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(get_settings().text_new_client_days_prompt),
        reply_markup=new_client_days_keyboard(),
        force_new=True,
    )


@router.callback_query(lambda call: call.data == "client:new:back")
async def new_client_days_back(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    await state.set_state(NewClientState.waiting_username)
    await _edit_or_send(
        call,
        _t(settings.text_new_client_username_prompt),
        reply_markup=cancel_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("client:new:days:"))
async def new_client_pick_days(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    try:
        days = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(get_settings().text_page_invalid), show_alert=True)
        return
    await state.update_data(days=days, telegram_id=None)
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    tariffs = _tariffs_for_user(settings, call.from_user.id, show_all=is_owner or is_admin)
    if not tariffs:
        await _edit_or_send(
            call,
            text=f"{_t(settings.text_tariffs_empty)}\n\n{_t(settings.text_new_client_price_prompt)}",
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(NewClientState.waiting_price)
        await call.answer()
        return
    await state.set_state(NewClientState.waiting_tariff)
    await _edit_or_send(
        call,
        text=_t(settings.text_tariff_pick_prompt),
        reply_markup=tariffs_keyboard(tariffs, label_mode="price"),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "skip:tg")
async def new_client_skip_tg(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    data = await state.get_data()
    username = data.get("username")
    if not username:
        await call.answer(_t(get_settings().text_enter_username_first), show_alert=True)
        return
    await state.update_data(telegram_id=None)
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    tariffs = _tariffs_for_user(settings, call.from_user.id, show_all=is_owner or is_admin)
    if not tariffs:
        await _edit_or_send(
            call,
            f"{_t(settings.text_tariffs_empty)}\n\n{_t(settings.text_new_client_price_prompt)}",
            reply_markup=cancel_keyboard(),
            is_menu=True,
        )
        await state.update_data(tariff_base_price=settings.base_subscription_price, tariff_remnawave={})
        await state.set_state(NewClientState.waiting_price)
        await call.answer()
        return
    await state.set_state(NewClientState.waiting_tariff)
    await _edit_or_send(
        call,
        _t(settings.text_tariff_pick_prompt),
        reply_markup=tariffs_keyboard(tariffs, label_mode="price"),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("tariff:pick:"))
async def tariff_pick(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    try:
        tariff_id = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    data = await state.get_data()
    current_state = await state.get_state()
    target_agent_id = data.get("agent_id")
    target_telegram_id = call.from_user.id
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    if target_agent_id:
        async with SessionLocal() as session:
            agent = await get_agent_by_id(session, target_agent_id)
            if agent:
                target_telegram_id = agent.telegram_id
    visible_tariffs = _tariffs_for_user(
        settings,
        target_telegram_id,
        show_all=not target_agent_id and (is_owner or is_admin),
    )
    tariff = next((t for t in visible_tariffs if t.get("id") == tariff_id), None)
    if not tariff:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    base_price = tariff.get("base_price") or settings.base_subscription_price
    await state.update_data(tariff_id=tariff_id, tariff_base_price=base_price, tariff_name=tariff.get("name"))
    await state.update_data(tariff_remnawave=tariff.get("remnawave") or {})
    traffic = _format_traffic((tariff.get("remnawave") or {}).get("traffic_limit_gb"))
    desc = (tariff.get("desc") or "").strip()
    desc_line = f"Описание: {desc}" if desc else ""

    if current_state == NewClientState.waiting_tariff.state:
        async with SessionLocal() as session:
            agent = await get_or_create_agent(
                session,
                call.from_user.id,
                call.from_user.full_name,
                call.from_user.username,
            )
            if _credit_limit_exceeded(agent, base_price):
                await _show_status_then_menu(
                    bot=call.bot,
                    chat_id=call.message.chat.id,
                    user_id=call.from_user.id,
                    name=call.from_user.full_name,
                    is_owner=call.from_user.id == settings.owner_telegram_id,
                    status_text=_t(
                        settings.text_limit_reached_create,
                        current=agent.current_debt,
                        limit=agent.credit_limit,
                    ),
                )
                await state.clear()
                await call.answer()
                return
        await state.set_state(NewClientState.waiting_price)
        presets = _amount_presets(base_price)
        price_prompt = f"{_t(settings.text_new_client_price_prompt)}\n\n{_t(settings.text_amount_choose_hint)}"
        await _edit_or_send(
            call,
            _t(
                settings.text_tariff_selected,
                name=tariff.get("name"),
                price=base_price,
                traffic=traffic,
                desc=desc_line,
                prompt=price_prompt,
            ),
            reply_markup=amount_presets_keyboard("amount:new", presets),
            is_menu=True,
        )
        await call.answer()
        return

    if current_state == RenewState.waiting_tariff.state:
        days = data.get("days") or settings.default_renew_days
        old_tariff = data.get("renew_old_tariff") or _t(settings.text_client_tariff_default)
        old_base_price = data.get("renew_old_base_price") or settings.base_subscription_price
        client_price = data.get("renew_client_price") or "—"
        old_monthly_value = data.get("renew_client_price_value") or 0
        days_left = data.get("renew_days_left") or 0
        async with SessionLocal() as session:
            if target_agent_id:
                target_agent = await get_agent_by_id(session, target_agent_id)
            else:
                target_agent = await get_or_create_agent(
                    session,
                    call.from_user.id,
                    call.from_user.full_name,
                    call.from_user.username,
                )
            if not target_agent:
                await call.answer(_t(settings.text_target_agent_not_found), show_alert=True)
                await state.clear()
                return
            owner_share = _calc_base_debt(settings, days, base_price)
            projected = target_agent.current_debt + owner_share
            if target_agent.credit_limit > 0 and projected > target_agent.credit_limit:
                await _show_status_then_menu(
                    bot=call.bot,
                    chat_id=call.message.chat.id,
                    user_id=call.from_user.id,
                    name=call.from_user.full_name,
                    is_owner=call.from_user.id == settings.owner_telegram_id,
                    status_text=_t(
                        settings.text_limit_reached_renew,
                        current=target_agent.current_debt,
                        limit=target_agent.credit_limit,
                    ),
                )
                await state.clear()
                await call.answer()
                return
        await state.set_state(RenewState.waiting_amount)
        amount_prompt = _t(settings.text_renew_amount_prompt_with_prev, prev=client_price)
        upgrade_note = ""
        if days_left > 0 and (tariff.get("base_price") or settings.base_subscription_price) > old_base_price:
            extra = _calc_base_debt(settings, days_left, (tariff.get("base_price") or settings.base_subscription_price) - old_base_price)
            upgrade_note = _t(settings.text_renew_upgrade_note, days_left=days_left, extra=extra)
        profit_label = f"{old_monthly_value - base_price} ₽/мес" if old_monthly_value else "—"
        prompt_text = _t(
            settings.text_renew_amount_context,
            old_tariff=old_tariff,
            old_base_price=old_base_price,
            new_tariff=tariff.get("name"),
            new_base_price=base_price,
            client_price=client_price,
            prompt=f"{upgrade_note}{amount_prompt}",
        )
        prompt_with_hint = f"{prompt_text}\n\n{_t(settings.text_amount_choose_hint)}"
        await state.update_data(renew_amount_prompt=prompt_with_hint)
        presets = _amount_presets(base_price, old_monthly_value)
        await _edit_or_send(
            call,
            _t(
                settings.text_renew_tariff_selected,
                name=tariff.get("name"),
                price=base_price,
                traffic=traffic,
                desc=desc_line,
                profit=profit_label,
                prompt=prompt_with_hint,
            ),
            reply_markup=amount_presets_keyboard("amount:renew", presets),
            is_menu=True,
        )
        await call.answer()
        return

    await call.answer()


@router.message(NewClientState.waiting_price)
async def new_client_price(message: Message, state: FSMContext) -> None:
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
        price = int((message.text or "").strip())
    except ValueError:
        data = await state.get_data()
        base_price = data.get("tariff_base_price") or get_settings().base_subscription_price
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_invalid_example),
            prompt_text=f"{_t(get_settings().text_new_client_price_prompt)}\n\n{_t(get_settings().text_amount_choose_hint)}",
            reply_markup=amount_presets_keyboard("amount:new", _amount_presets(base_price)),
        )
        return
    if price <= 0:
        data = await state.get_data()
        base_price = data.get("tariff_base_price") or get_settings().base_subscription_price
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_positive),
            prompt_text=f"{_t(get_settings().text_new_client_price_prompt)}\n\n{_t(get_settings().text_amount_choose_hint)}",
            reply_markup=amount_presets_keyboard("amount:new", _amount_presets(base_price)),
        )
        return

    data = await state.get_data()
    username = data.get("username")
    telegram_id = data.get("telegram_id")
    days = data.get("days") or get_settings().default_renew_days
    settings = get_settings()
    base_price = data.get("tariff_base_price") or settings.base_subscription_price
    tariff_name = data.get("tariff_name")
    tariff_remnawave = data.get("tariff_remnawave") or {}

    amount_total = _calc_amount_by_days(settings, price, days)
    owner_share = _calc_base_debt(settings, days, base_price)
    profit = amount_total - owner_share
    await state.update_data(new_client_amount_monthly=price)
    await state.set_state(NewClientState.waiting_confirm)
    await _render_menu_text(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        text=_t(
            settings.text_new_client_confirm,
            username=username,
            tariff=tariff_name or _t(settings.text_client_tariff_default),
            base_price=base_price,
            days=days,
            amount_monthly=price,
            amount_total=amount_total,
            owner_share=owner_share,
            profit=profit,
        ),
        reply_markup=new_client_confirm_keyboard(),
        force_new=True,
    )
    return


@router.callback_query(lambda call: call.data.startswith("amount:new:"))
async def new_client_amount_preset(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    token = call.data.split(":")[-1]
    try:
        price = int(token)
    except ValueError:
        await call.answer(_t(settings.text_amount_invalid), show_alert=True)
        return
    if price <= 0:
        await call.answer(_t(settings.text_amount_positive), show_alert=True)
        return

    data = await state.get_data()
    username = data.get("username")
    days = data.get("days") or settings.default_renew_days
    base_price = data.get("tariff_base_price") or settings.base_subscription_price
    tariff_name = data.get("tariff_name")
    amount_total = _calc_amount_by_days(settings, price, days)
    owner_share = _calc_base_debt(settings, days, base_price)
    profit = amount_total - owner_share
    await state.update_data(new_client_amount_monthly=price)
    await state.set_state(NewClientState.waiting_confirm)
    await _edit_or_send(
        call,
        _t(
            settings.text_new_client_confirm,
            username=username,
            tariff=tariff_name or _t(settings.text_client_tariff_default),
            base_price=base_price,
            days=days,
            amount_monthly=price,
            amount_total=amount_total,
            owner_share=owner_share,
            profit=profit,
        ),
        reply_markup=new_client_confirm_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "client:new:confirm")
async def new_client_confirm(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    data = await state.get_data()
    amount_monthly = data.get("new_client_amount_monthly")
    if not amount_monthly:
        await call.answer(_t(get_settings().text_amount_invalid), show_alert=True)
        return
    await _create_client_in_remnawave(
        actor_id=call.from_user.id,
        actor_name=call.from_user.full_name,
        actor_username=call.from_user.username,
        message=call.message,
        username=data.get("username"),
        telegram_id=data.get("telegram_id"),
        days=data.get("days") or get_settings().default_renew_days,
        monthly_price=int(amount_monthly),
        base_price=data.get("tariff_base_price"),
        tariff_name=data.get("tariff_name"),
        tariff_remnawave=data.get("tariff_remnawave") or {},
    )
    await state.clear()
    await call.answer()


@router.callback_query(lambda call: call.data == "client:new:confirm:back")
async def new_client_confirm_back(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    settings = get_settings()
    data = await state.get_data()
    base_price = data.get("tariff_base_price") or settings.base_subscription_price
    await state.set_state(NewClientState.waiting_price)
    await _edit_or_send(
        call,
        f"{_t(settings.text_new_client_price_prompt)}\n\n{_t(settings.text_amount_choose_hint)}",
        reply_markup=amount_presets_keyboard("amount:new", _amount_presets(base_price)),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "client:list")
async def clients_list(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    await state.clear()
    await _render_clients_list(call, page=1)
    await call.answer()


@router.callback_query(lambda call: call.data.startswith("client:list:page:"))
async def clients_list_page(call: CallbackQuery) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    try:
        page = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer(_t(get_settings().text_page_invalid), show_alert=True)
        return
    await _render_clients_list(call, page=page, edit=True)
    await call.answer()


async def _create_client_in_remnawave(
    actor_id: int,
    actor_name: str,
    actor_username: str | None,
    message: Message,
    username: str,
    telegram_id: int | None,
    days: int,
    monthly_price: int,
    base_price: int | None = None,
    tariff_name: str | None = None,
    tariff_remnawave: dict | None = None,
) -> None:
    async with SessionLocal() as session:
        agent = await get_or_create_agent(session, actor_id, actor_name, actor_username)
        if not agent.is_active:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=actor_id,
                name=actor_name,
                is_owner=actor_id == get_settings().owner_telegram_id,
                status_text=_t(get_settings().text_agent_blocked),
            )
            return
        settings = get_settings()
        base_price = base_price or settings.base_subscription_price
        days = int(days) if days and int(days) > 0 else settings.default_renew_days
        tariff_name = tariff_name or _t(settings.text_client_tariff_default)
        owner_share = _calc_base_debt(settings, days, base_price)
        projected = agent.current_debt + owner_share
        if agent.credit_limit > 0 and projected > agent.credit_limit:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=actor_id,
                name=actor_name,
                is_owner=actor_id == settings.owner_telegram_id,
                status_text=_t(
                    settings.text_limit_reached_create,
                    current=agent.current_debt,
                    limit=agent.credit_limit,
                ),
            )
            return
        logging.info(
            "Create client: actor_id=%s agent_id=%s username=%s telegram_id=%s price=%s days=%s",
            actor_id,
            agent.id,
            username,
            telegram_id,
            monthly_price,
            days,
        )
        existing = await get_client_by_username(session, agent.id, username)
        if existing:
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=actor_id,
                name=actor_name,
                is_owner=actor_id == settings.owner_telegram_id,
                status_text=_t(settings.text_client_exists),
            )
            logging.info("Client already exists in DB: agent_id=%s username=%s id=%s", agent.id, username, existing.id)
            return

        try:
            result = await create_user_only(
                username=username,
                days=days,
                description=f"agent:{agent.telegram_id}",
                telegram_id=telegram_id,
                overrides=(tariff_remnawave or {}),
            )
        except Exception as exc:
            logging.exception("Create Remnawave error")
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=actor_id,
                name=actor_name,
                is_owner=actor_id == settings.owner_telegram_id,
                status_text=_t(settings.text_create_error, error=exc),
            )
            return
        if result.get("exists"):
            await _show_status_then_menu(
                bot=message.bot,
                chat_id=message.chat.id,
                user_id=actor_id,
                name=actor_name,
                is_owner=actor_id == settings.owner_telegram_id,
                status_text=_t(settings.text_username_taken_panel, username=username),
            )
            return

        expires_at = result.get("expires_at")
        subscription_link = result.get("subscription_url")
        amount_total = _calc_amount_by_days(settings, monthly_price, days)
        await create_client(
            session,
            agent_id=agent.id,
            username=username,
            telegram_id=telegram_id,
            expires_at=expires_at,
            subscription_link=subscription_link,
            monthly_price=monthly_price,
            last_payment_amount=amount_total,
            last_payment_at=datetime.utcnow(),
            tariff_name=tariff_name,
            tariff_base_price=base_price,
        )
        logging.info(
            "Client created in DB after Remnawave: agent_id=%s username=%s",
            agent.id,
            username,
        )
        await increase_debt(session, agent, owner_share, f"Создание клиента {username}")
        profit = amount_total - owner_share
        await _show_status_then_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=actor_id,
            name=actor_name,
            is_owner=actor_id == settings.owner_telegram_id,
            status_text=_t(
                settings.text_create_success,
                username=username,
                days=days,
                profit=profit,
                amount=amount_total,
                base_price=owner_share,
                payable=agent.current_debt,
            ),
            extra_text=(
                _t(settings.text_subscription_link, link=subscription_link) if subscription_link else None
            ),
        )


def _format_date(value: datetime | None) -> str:
    settings = get_settings()
    if not value:
        return _t(settings.text_date_none)
    today = datetime.utcnow().date()
    days_left = (value.date() - today).days
    if days_left < 0:
        return _t(settings.text_date_expired)
    return _t(settings.text_days_left, days=days_left)


def _format_client_meta(value: datetime | None, last_payment: int | None) -> str:
    date_part = _format_date(value)
    if last_payment is None:
        return date_part
    return _t(get_settings().text_client_meta, date=date_part, payment=last_payment)


def _format_client_line(client, agent_name: str | None) -> str:
    settings = get_settings()
    date_part = _format_date(client.expires_at)
    tariff_price = client.tariff_base_price or settings.base_subscription_price
    tariff_name = client.tariff_name or _t(settings.text_client_tariff_default)
    tariff_part = (
        _t(
            settings.text_client_tariff,
            name=tariff_name,
            price=tariff_price,
        )
        if tariff_price
        else _t(settings.text_client_tariff_none)
    )
    price_part = (
        _t(settings.text_client_price, price=client.monthly_price)
        if client.monthly_price
        else _t(settings.text_client_price_none)
    )
    paid_part = (
        _t(settings.text_client_paid, amount=client.last_payment_amount)
        if client.last_payment_amount is not None
        else _t(settings.text_client_paid_none)
    )
    agent_part = f" • {agent_name}" if agent_name else ""
    return _t(
        settings.text_client_line,
        username=client.username,
        agent_part=agent_part,
        date=date_part,
        tariff=tariff_part,
        price=price_part,
        paid=paid_part,
    )


async def _render_clients_list(call: CallbackQuery, page: int, edit: bool = False) -> None:
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set

    async with SessionLocal() as session:
        if is_owner or is_admin:
            client_rows = await list_clients_with_agents(session)
            lines = [
                _format_client_line(client, _agent_display(agent))
                for client, agent in client_rows
                if client.username
            ]
        else:
            agent = await get_or_create_agent(
                session,
                call.from_user.id,
                call.from_user.full_name,
                call.from_user.username,
            )
            clients = await list_clients_by_agent(session, agent.id)
            lines = [
                _format_client_line(client, None)
                for client in clients
                if client.username
            ]

    if not lines:
        await _edit_or_send(call, _t(settings.text_clients_list_empty), reply_markup=back_to_menu_keyboard(), is_menu=True)
        return

    page_size = 5
    total_pages = max(1, (len(lines) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    header = (
        _t(settings.text_clients_list_header_owner)
        if is_owner or is_admin
        else _t(settings.text_clients_list_header_agent)
    )
    separator = _t(settings.text_client_list_separator)
    page_lines = lines[start_idx:end_idx]
    body = f"\n{separator}\n".join(page_lines) if separator else "\n\n".join(page_lines)
    status_text = f"{header} · {page}/{total_pages}\n\n{body}"

    if edit:
        await _edit_or_send(
            call,
            status_text,
            reply_markup=clients_list_pagination_keyboard(page, total_pages),
            is_menu=True,
        )
        return
    await _edit_or_send(
        call,
        status_text,
        reply_markup=clients_list_pagination_keyboard(page, total_pages),
        is_menu=True,
    )
