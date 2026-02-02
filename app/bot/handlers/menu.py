import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import back_to_menu_keyboard, main_menu
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.agent_service import get_agent_by_telegram_id, get_or_create_agent

from .common import _format_tariffs_block, _t


router = Router()

_LAST_MENU_MESSAGE_ID: dict[int, int] = {}


async def _store_menu_message_id(user_id: int, name: str, message_id: int | None) -> None:
    async with SessionLocal() as session:
        agent = await get_or_create_agent(session, user_id, name)
        agent.menu_message_id = message_id
        await session.commit()


async def _delete_menu(bot, chat_id: int, user_id: int, name: str) -> None:
    message_id = _LAST_MENU_MESSAGE_ID.get(user_id)
    if not message_id:
        async with SessionLocal() as session:
            agent = await get_or_create_agent(session, user_id, name)
            message_id = agent.menu_message_id
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
    _LAST_MENU_MESSAGE_ID.pop(user_id, None)
    await _store_menu_message_id(user_id, name, None)


async def _edit_or_send(
    call: CallbackQuery, text: str, reply_markup=None, is_menu: bool = False, **kwargs
) -> None:
    try:
        await call.message.edit_text(text, reply_markup=reply_markup, **kwargs)
        if is_menu:
            _LAST_MENU_MESSAGE_ID[call.from_user.id] = call.message.message_id
            await _store_menu_message_id(call.from_user.id, call.from_user.full_name, call.message.message_id)
    except Exception:
        sent = await call.message.answer(text, reply_markup=reply_markup, **kwargs)
        if is_menu:
            _LAST_MENU_MESSAGE_ID[call.from_user.id] = sent.message_id
            await _store_menu_message_id(call.from_user.id, call.from_user.full_name, sent.message_id)


async def _edit_menu_for_user(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    text: str,
    reply_markup=None,
    **kwargs,
) -> None:
    message_id = _LAST_MENU_MESSAGE_ID.get(user_id)
    if not message_id:
        async with SessionLocal() as session:
            agent = await get_or_create_agent(session, user_id, name)
            message_id = agent.menu_message_id
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )
            _LAST_MENU_MESSAGE_ID[user_id] = message_id
            await _store_menu_message_id(user_id, name, message_id)
            return
        except Exception:
            pass
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, **kwargs)
    _LAST_MENU_MESSAGE_ID[user_id] = sent.message_id
    await _store_menu_message_id(user_id, name, sent.message_id)


async def _render_menu_text(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    text: str,
    reply_markup=None,
    force_new: bool = True,
    **kwargs,
) -> None:
    if force_new:
        await _delete_menu(bot=bot, chat_id=chat_id, user_id=user_id, name=name)
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, **kwargs)
    _LAST_MENU_MESSAGE_ID[user_id] = sent.message_id
    await _store_menu_message_id(user_id, name, sent.message_id)


async def _render_error_prompt(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    error_text: str,
    prompt_text: str | None = None,
    reply_markup=None,
) -> None:
    text = error_text if not prompt_text else f"{error_text}\n\n{prompt_text}"
    await _render_menu_text(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        name=name,
        text=text,
        reply_markup=reply_markup,
        force_new=True,
    )


async def _render_menu(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    is_owner: bool,
    text: str,
    force_new: bool = False,
) -> None:
    balance, limit = await _get_balance(user_id, name)
    reply_markup = main_menu(is_owner=is_owner, balance=balance, credit_limit=limit)
    message_id = _LAST_MENU_MESSAGE_ID.get(user_id)
    if not message_id:
        async with SessionLocal() as session:
            agent = await get_or_create_agent(session, user_id, name)
            message_id = agent.menu_message_id
    if message_id and not force_new:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            _LAST_MENU_MESSAGE_ID[user_id] = message_id
            await _store_menu_message_id(user_id, name, message_id)
            return
        except Exception:
            pass
    if force_new:
        await _delete_menu(bot=bot, chat_id=chat_id, user_id=user_id, name=name)
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    _LAST_MENU_MESSAGE_ID[user_id] = sent.message_id
    await _store_menu_message_id(user_id, name, sent.message_id)


async def _show_status_then_menu(
    bot,
    chat_id: int,
    user_id: int,
    name: str,
    is_owner: bool,
    status_text: str,
    extra_text: str | None = None,
) -> None:
    settings = get_settings()
    await _delete_menu(bot=bot, chat_id=chat_id, user_id=user_id, name=name)
    await bot.send_message(chat_id=chat_id, text=status_text)
    if extra_text:
        await bot.send_message(chat_id=chat_id, text=extra_text)
    await _render_menu(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        name=name,
        is_owner=is_owner,
        text=_t(settings.text_main_menu_prompt),
        force_new=True,
    )


async def _get_balance(user_id: int, name: str) -> tuple[int, int]:
    async with SessionLocal() as session:
        agent = await get_or_create_agent(session, user_id, name)
        return agent.current_debt, agent.credit_limit


async def _show_start_menu(message: Message) -> None:
    settings = get_settings()
    is_owner = message.from_user.id == settings.owner_telegram_id
    tariffs = settings.visible_tariffs(message.from_user.id)
    base_price = tariffs[0]["base_price"] if tariffs else settings.base_subscription_price
    example_total = base_price + 150
    await _render_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        is_owner=is_owner,
        text=_t(
            settings.text_start,
            base_price=base_price,
            example_total=example_total,
            example_profit=example_total - base_price,
        ),
        force_new=True,
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    settings = get_settings()
    user_id = message.from_user.id
    is_owner = user_id == settings.owner_telegram_id
    is_admin = user_id in settings.admin_id_set
    is_agent = False

    async with SessionLocal() as session:
        if is_owner or is_admin:
            await get_or_create_agent(
                session,
                user_id,
                message.from_user.full_name,
                message.from_user.username,
            )
        else:
            agent = await get_agent_by_telegram_id(session, user_id)
            is_agent = bool(agent and agent.is_active)
            if is_agent:
                await get_or_create_agent(
                    session,
                    user_id,
                    message.from_user.full_name,
                    message.from_user.username,
                )

    if not (is_owner or is_admin or is_agent):
        await message.answer(_t(settings.text_access_denied))
        return

    await _show_start_menu(message)


@router.message(Command("ping"))
async def ping(message: Message) -> None:
    settings = get_settings()
    await message.answer(_t(settings.text_ping))


@router.callback_query(lambda call: call.data == "cancel")
async def cancel_callback(call: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    await state.clear()
    await _render_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=call.from_user.id == settings.owner_telegram_id,
        text=_t(settings.text_main_menu_prompt),
        force_new=False,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "menu")
async def menu_callback(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    settings = get_settings()
    await _render_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=call.from_user.id == settings.owner_telegram_id,
        text=_t(settings.text_main_menu_prompt),
        force_new=False,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "vpn:info")
async def vpn_info(call: CallbackQuery) -> None:
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    if is_owner or is_admin:
        tariffs = settings.tariffs()
    else:
        tariffs = settings.visible_tariffs(call.from_user.id)
    base_price = tariffs[0]["base_price"] if tariffs else settings.base_subscription_price
    tariffs_block = _format_tariffs_block(settings, tariffs)
    await _edit_or_send(
        call,
        _t(
            settings.text_vpn_info,
            base_price=base_price,
            example_total=base_price + 150,
            example_profit=(base_price + 150) - base_price,
            tariffs_block=tariffs_block,
        ),
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "tariffs:info")
async def tariffs_info(call: CallbackQuery) -> None:
    settings = get_settings()
    is_owner = call.from_user.id == settings.owner_telegram_id
    is_admin = call.from_user.id in settings.admin_id_set
    if is_owner or is_admin:
        tariffs = settings.tariffs()
    else:
        tariffs = settings.visible_tariffs(call.from_user.id)
    tariffs_block = _format_tariffs_block(settings, tariffs)
    text = "\n".join(
        [
            _t(settings.text_tariffs_screen_title),
            _t(settings.text_tariffs_screen_subtitle),
            "",
            tariffs_block,
        ]
    )
    await _edit_or_send(
        call,
        text,
        reply_markup=back_to_menu_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.callback_query(lambda call: call.data == "balance:refresh")
async def balance_refresh(call: CallbackQuery) -> None:
    settings = get_settings()
    balance, limit = await _get_balance(call.from_user.id, call.from_user.full_name)
    try:
        await call.message.edit_reply_markup(
            reply_markup=main_menu(
                is_owner=call.from_user.id == settings.owner_telegram_id,
                balance=balance,
                credit_limit=limit,
            )
        )
        _LAST_MENU_MESSAGE_ID[call.from_user.id] = call.message.message_id
        await _store_menu_message_id(call.from_user.id, call.from_user.full_name, call.message.message_id)
        await call.answer(_t(settings.text_balance_updated))
    except Exception as exc:
        message = str(exc).lower()
        if "message is not modified" in message or "not modified" in message:
            await call.answer(_t(settings.text_balance_actual))
            return
        await call.answer(_t(settings.text_balance_failed), show_alert=False)
        logging.warning("Balance refresh failed: %s", exc)
