from aiogram.fsm.state import State, StatesGroup


class NewClientState(StatesGroup):
    waiting_username = State()
    waiting_tg_id = State()
    waiting_tariff = State()
    waiting_price = State()


class RenewState(StatesGroup):
    waiting_username = State()
    waiting_days = State()
    waiting_tariff = State()
    waiting_amount = State()


class PayDebtState(StatesGroup):
    waiting_amount = State()


class AddAgentState(StatesGroup):
    waiting_tg_id = State()


class LimitAgentState(StatesGroup):
    waiting_limit = State()


class DeleteClientState(StatesGroup):
    waiting_username = State()
    confirm = State()
