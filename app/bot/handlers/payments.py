import logging
from datetime import datetime

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import cancel_keyboard, transfer_confirm_keyboard
from app.bot.states import PayDebtState
from app.config import get_settings
from app.db.session import SessionLocal
from app.models import TransferRequest
from app.services.agent_service import get_agent_by_id, get_or_create_agent
from app.services.debt_service import decrease_debt

from .common import _agent_display, _is_agent_allowed, _is_cancel, _is_start, _t
from .menu import _edit_or_send, _render_error_prompt, _show_start_menu, _show_status_then_menu


router = Router()


@router.callback_query(lambda call: call.data == "debt:pay")
async def debt_pay_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_agent_allowed(call.from_user.id):
        await call.answer(_t(get_settings().text_no_access_alert), show_alert=True)
        return
    await state.set_state(PayDebtState.waiting_amount)
    await _edit_or_send(
        call,
        _t(get_settings().text_debt_pay_prompt),
        reply_markup=cancel_keyboard(),
        is_menu=True,
    )
    await call.answer()


@router.message(PayDebtState.waiting_amount)
async def debt_pay_message(message: Message, state: FSMContext) -> None:
    if not await _is_agent_allowed(message.from_user.id):
        await _show_status_then_menu(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            is_owner=False,
            status_text=_t(get_settings().text_no_access_message),
        )
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
            prompt_text=_t(get_settings().text_debt_pay_prompt),
        )
        return
    if amount <= 0:
        await _render_error_prompt(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            name=message.from_user.full_name,
            error_text=_t(get_settings().text_amount_positive),
            prompt_text=_t(get_settings().text_debt_pay_prompt),
        )
        return

    async with SessionLocal() as session:
        agent = await get_or_create_agent(
            session,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )
        request = TransferRequest(agent_id=agent.id, amount=amount)
        session.add(request)
        await session.commit()
        await session.refresh(request)

    settings = get_settings()
    if settings.owner_telegram_id:
        try:
            await message.bot.send_message(
                settings.owner_telegram_id,
                _t(
                    settings.text_transfer_request_owner,
                    agent_name=_agent_display(agent),
                    amount=amount,
                ),
                reply_markup=transfer_confirm_keyboard(request.id),
            )
        except Exception:
            logging.exception("Failed to send transfer request to owner")
    await state.clear()
    await _show_status_then_menu(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.from_user.full_name,
        is_owner=message.from_user.id == settings.owner_telegram_id,
        status_text=_t(settings.text_transfer_request_sent, amount=amount),
    )


@router.callback_query(lambda call: call.data.startswith("transfer:confirm:"))
async def transfer_confirm(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    request_id = int(call.data.split(":")[-1])
    async with SessionLocal() as session:
        request = await session.get(TransferRequest, request_id)
        if not request or request.status != "pending":
            await call.answer(_t(settings.text_transfer_already_processed), show_alert=True)
            return
        agent = await get_agent_by_id(session, request.agent_id)
        if not agent:
            await call.answer(_t(settings.text_agent_not_found), show_alert=True)
            return
        request.status = "approved"
        request.decided_at = datetime.utcnow()
        await session.commit()
        await decrease_debt(session, agent, request.amount, "Подтверждённый перевод")

    await _show_status_then_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=True,
        status_text=_t(settings.text_transfer_confirm_owner, amount=request.amount),
    )
    await call.answer(_t(settings.text_transfer_confirm_answer))
    try:
        await call.message.delete()
    except Exception:
        pass
    if agent.telegram_id != call.from_user.id:
        try:
            await _show_status_then_menu(
                bot=call.bot,
                chat_id=agent.telegram_id,
                user_id=agent.telegram_id,
                name=agent.name,
                is_owner=False,
                status_text=_t(settings.text_transfer_confirm_agent, amount=request.amount),
            )
        except Exception:
            logging.exception("Failed to notify agent about approved transfer")


@router.callback_query(lambda call: call.data.startswith("transfer:reject:"))
async def transfer_reject(call: CallbackQuery) -> None:
    settings = get_settings()
    if call.from_user.id != settings.owner_telegram_id:
        await call.answer(_t(settings.text_no_access_alert), show_alert=True)
        return
    request_id = int(call.data.split(":")[-1])
    async with SessionLocal() as session:
        request = await session.get(TransferRequest, request_id)
        if not request or request.status != "pending":
            await call.answer(_t(settings.text_transfer_already_processed), show_alert=True)
            return
        request.status = "rejected"
        request.decided_at = datetime.utcnow()
        await session.commit()
        agent = await get_agent_by_id(session, request.agent_id)

    await _show_status_then_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        name=call.from_user.full_name,
        is_owner=True,
        status_text=_t(settings.text_transfer_reject_owner, amount=request.amount),
    )
    await call.answer(_t(settings.text_transfer_reject_answer))
    try:
        await call.message.delete()
    except Exception:
        pass
    if agent and agent.telegram_id != call.from_user.id:
        try:
            await _show_status_then_menu(
                bot=call.bot,
                chat_id=agent.telegram_id,
                user_id=agent.telegram_id,
                name=agent.name,
                is_owner=False,
                status_text=_t(settings.text_transfer_reject_agent, amount=request.amount),
            )
        except Exception:
            logging.exception("Failed to notify agent about rejected transfer")
