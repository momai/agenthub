from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    database_url: str
    owner_telegram_id: int
    admin_ids: Optional[str] = None

    remnawave_api_url: str
    remnawave_api_key: str
    remnawave_mode: str = "remote"
    remnawave_caddy_token: Optional[str] = None
    remnawave_inbound_uuids: Optional[str] = None
    remnawave_internal_squads: Optional[str] = None
    remnawave_external_squad: Optional[str] = None
    remnawave_tag: Optional[str] = None
    remnawave_traffic_limit_gb: int = 0
    remnawave_traffic_reset_strategy: str = "MONTH"
    remnawave_hwid_device_limit: int = 0

    log_level: str = "INFO"

    default_renew_days: int = 30
    default_credit_limit: int = 0
    default_owner_share_percent: int = 100
    sync_interval_seconds: int = 300
    expiry_notify_days: int = 3
    expiry_notify_interval_seconds: int = 3600
    base_subscription_price: int = 200
    tariff_1_name: Optional[str] = None
    tariff_1_base_price: Optional[str] = None
    tariff_1_desc: Optional[str] = None
    tariff_1_agent_ids: Optional[str] = None
    tariff_1_internal_squads: Optional[str] = None
    tariff_1_external_squad: Optional[str] = None
    tariff_1_traffic_limit_gb: Optional[str] = None
    tariff_1_traffic_reset_strategy: Optional[str] = None
    tariff_1_hwid_device_limit: Optional[str] = None
    tariff_1_tag: Optional[str] = None
    tariff_2_name: Optional[str] = None
    tariff_2_base_price: Optional[str] = None
    tariff_2_desc: Optional[str] = None
    tariff_2_agent_ids: Optional[str] = None
    tariff_2_internal_squads: Optional[str] = None
    tariff_2_external_squad: Optional[str] = None
    tariff_2_traffic_limit_gb: Optional[str] = None
    tariff_2_traffic_reset_strategy: Optional[str] = None
    tariff_2_hwid_device_limit: Optional[str] = None
    tariff_2_tag: Optional[str] = None
    tariff_3_name: Optional[str] = None
    tariff_3_base_price: Optional[str] = None
    tariff_3_desc: Optional[str] = None
    tariff_3_agent_ids: Optional[str] = None
    tariff_3_internal_squads: Optional[str] = None
    tariff_3_external_squad: Optional[str] = None
    tariff_3_traffic_limit_gb: Optional[str] = None
    tariff_3_traffic_reset_strategy: Optional[str] = None
    tariff_3_hwid_device_limit: Optional[str] = None
    tariff_3_tag: Optional[str] = None
    tariff_4_name: Optional[str] = None
    tariff_4_base_price: Optional[str] = None
    tariff_4_desc: Optional[str] = None
    tariff_4_agent_ids: Optional[str] = None
    tariff_4_internal_squads: Optional[str] = None
    tariff_4_external_squad: Optional[str] = None
    tariff_4_traffic_limit_gb: Optional[str] = None
    tariff_4_traffic_reset_strategy: Optional[str] = None
    tariff_4_hwid_device_limit: Optional[str] = None
    tariff_4_tag: Optional[str] = None

    # ─── Главный экран ────────────────────────────────────────────
    text_start: str = (
        "👋 <b>Привет!</b>\\n\\n"
        "Это бот для подключения клиентов к VPN.\\n"
        "Продавай подписки по своей цене и зарабатывай.\\n\\n"
        "<b>Как это работает:</b>\\n"
        "• Продаёшь подписку по своей цене\\n"
        "• <b>{base_price} ₽</b> с каждого → владельцу\\n"
        "• Остальное — твоё 💰\\n\\n"
        "<i>Пример: продал за {example_total} ₽ → {example_profit} ₽ твои</i>\\n\\n"
        "💳 Способ оплаты → @support"
    )
    text_main_menu_prompt: str = "Выбери действие:"
    text_access_denied: str = "🔒 Нет доступа. Обратись к владельцу."
    text_ping: str = "pong"

    # ─── Доступ и ошибки ──────────────────────────────────────────
    text_no_access_alert: str = "Нет доступа"
    text_no_access_message: str = "⛔ Нет доступа"
    text_enter_username_first: str = "Сначала введи имя клиента"

    # ─── Создание клиента ─────────────────────────────────────────
    text_new_client_username_prompt: str = "📝 <b>Username клиента</b>\\n\\n<i>Латиница, цифры, _ или -\\nОт 3 до 36 символов</i>"
    text_username_invalid: str = "❌ Неверный формат\\n\\n<i>Допустимо: латиница, цифры, _ или -\\nПример:</i> <code>ivan_2024</code>"
    text_username_invalid_short: str = "❌ Неверный формат username"
    text_new_client_tg_id_prompt: str = "📱 <b>Telegram ID клиента</b>\\n\\n<i>Если не знаешь — пропусти</i>"
    text_tg_id_invalid: str = "❌ Это должно быть число"
    text_tg_id_invalid_short: str = "❌ ID должен быть числом"
    text_new_client_price_prompt: str = "💵 <b>Цена подписки</b>\\n\\n<i>Сколько берёшь с клиента за месяц?</i>"

    # ─── Валидация сумм ───────────────────────────────────────────
    text_amount_invalid_example: str = "❌ Введи число, например <code>300</code>"
    text_amount_invalid: str = "❌ Введи число"
    text_amount_positive: str = "❌ Сумма должна быть больше нуля"

    # ─── Клиенты ──────────────────────────────────────────────────
    text_clients_none: str = "📭 Клиентов пока нет"
    text_client_not_found_alert: str = "Клиент не найден"
    text_client_not_found: str = "❌ Клиент не найден"
    text_client_exists: str = "ℹ️ Клиент уже есть — используй <b>Продлить</b>"
    text_username_taken_panel: str = "❌ Имя <code>{username}</code> уже занято в панели. Введи другое."

    # ─── Продление ────────────────────────────────────────────────
    renew_min_days_left: int = 10
    text_renew_pick_prompt_owner: str = "🔄 <b>Продление подписки</b>\\n\\nВыбери клиента или введи username:"
    text_renew_pick_prompt_agent: str = "🔄 <b>Продление подписки</b>\\n\\nВыбери клиента или введи username:"
    text_renew_tariff_pick_prompt: str = (
        "📦 <b>Выбери тариф</b>\\n\\n"
        "Текущий тариф: <b>{old_tariff}</b> ({old_base_price} ₽)\\n"
        "Цена клиента: <b>{client_price}</b>\\n\\n"
        "<i>От тарифа зависит цена для владельца</i>"
    )
    text_renew_client_card: str = (
        "👤 <b>{username}</b>\\n\\n"
        "📦 Тариф: <b>{tariff}</b> ({base_price} ₽)\\n"
        "⏳ Осталось: <b>{days_left}</b>\\n"
        "💵 Цена клиента: <b>{price}/мес</b>\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "📅 <b>Срок продления</b>"
    )
    text_renew_days_prompt: str = "📅 <b>Срок продления</b>\\n\\n<i>Выбери срок кнопками ниже</i>"
    text_renew_days_buttons_only: str = "ℹ️ Используй кнопки ниже для выбора срока"
    text_renew_amount_prompt_with_prev: str = "💵 <b>Сколько берёшь с клиента?</b> (была {prev})"
    text_renew_amount_context: str = (
        "📌 Было: <b>{old_tariff}</b> ({old_base_price} ₽)\\n"
        "🆕 Будет: <b>{new_tariff}</b> ({new_base_price} ₽)\\n"
        "💵 Цена клиента: <b>{client_price}</b>\\n\\n"
        "{prompt}"
    )
    text_renew_upgrade_note: str = (
        "⚠️ Тариф выше: остаток {days_left}д перенесётся и добавится к сумме: <b>+{extra} ₽</b>\\n"
    )
    text_renew_too_early: str = (
        "⏳ Продление доступно, когда осталось ≤ {min_days} дней.\\n"
        "Сейчас: {days_left}д"
    )
    text_renew_tariff_selected: str = (
        "✅ <b>Тариф:</b> {name}\\n\\n"
        "💰 Цена владельцу: <b>{price} ₽</b>\\n"
        "📶 Трафик: <b>{traffic}</b>\\n"
        "{desc}\\n\\n"
        "{prompt}"
    )
    text_days_invalid: str = "❌ Введи число дней"
    text_days_positive: str = "❌ Дней должно быть больше нуля"
    text_page_invalid: str = "Неверная страница"
    text_renew_amount_prompt: str = "💵 <b>Цена продления</b>\\n\\n<i>Сколько берёшь с клиента?</i>"
    text_agent_blocked: str = "⛔ Аккаунт заблокирован"
    text_target_agent_not_found: str = "❌ Агент не найден"
    text_target_agent_blocked: str = "⛔ Агент заблокирован"

    # ─── Лимиты ───────────────────────────────────────────────────
    text_limit_reached_create: str = "⚠️ <b>Достигнут лимит</b>\\n\\nК оплате: <b>{current} ₽</b> из {limit} ₽\\nПереведи сумму, чтобы продолжить"
    text_limit_reached_renew: str = "⚠️ <b>Достигнут лимит</b>\\n\\nК оплате: <b>{current} ₽</b> из {limit} ₽\\nПереведи сумму, чтобы продолжить"
    text_limit_reached_renew_inline: str = "⚠️ Лимит достигнут ({current}/{limit} ₽)"
    text_limit_none: str = "без лимита"
    text_limit_infinite: str = "∞"

    # ─── Результаты операций ──────────────────────────────────────
    text_create_error: str = "❌ <b>Ошибка</b>\\n\\n<i>{error!r}</i>"
    text_create_success: str = "✅ <b>Клиент подключён</b>\\n\\n👤 <code>{username}</code> · {days} дней\\n\\n💰 Заработок: <b>{profit} ₽</b>\\n<i>{amount} ₽ − {base_price} ₽ владельцу</i>\\n\\n📊 К оплате: <b>{payable} ₽</b>"
    text_subscription_link: str = "🔗 <b>Ссылка для клиента:</b>\\n<code>{link}</code>"

    text_renew_error: str = "❌ <b>Ошибка продления</b>\\n\\n<i>{error!r}</i>"
    text_renew_success: str = "✅ <b>Подписка продлена</b>\\n\\n📅 +{days} дней\\n\\n💰 Заработок: <b>{profit} ₽</b>\\n<i>{amount} ₽ − {owner_share} ₽ владельцу</i>\\n\\n📊 К оплате: <b>{payable} ₽</b>"
    text_subscription_expiring: str = (
        "⏳ <b>Скоро закончится подписка</b>\\n\\n"
        "Клиент: <b>{username}</b>\\n"
        "Осталось: <b>{days_left} д.</b>\\n"
        "Дата окончания: <b>{expires_at}</b>\\n\\n"
        "👉 Если нужно — продли подписку"
    )
    text_expiry_notify_done: str = "🔔 Уведомления отправлены: <b>{count}</b>"
    text_expiry_notify_none: str = "✅ Нет клиентов с окончанием в ближайшие дни"
    text_expiry_notify_preview_title: str = "🔔 <b>Кому придёт уведомление</b>\\n\\n<i>Ближайшие {days} дн.</i>"
    text_expiry_notify_preview_line: str = "• <b>{username}</b> · до {expires_at} · {days_left} дн."
    text_expiry_notify_preview_empty: str = "✅ В ближайшие {days} дн. никому не придёт уведомление"

    # ─── Переводы ─────────────────────────────────────────────────
    text_debt_pay_prompt: str = "💸 <b>Сумма перевода</b>\\n\\nСпособ оплаты уточняй у @support\\n\\n<i>Сколько переводишь?</i>"
    text_transfer_request_owner: str = "💸 <b>Запрос на перевод</b>\\n\\nОт: <b>{agent_name}</b>\\nСумма: <b>{amount} ₽</b>"
    text_transfer_request_sent: str = "✅ Запрос отправлен\\n\\n<i>Владелец проверит и подтвердит</i>"
    text_transfer_already_processed: str = "Уже обработано"
    text_transfer_confirm_owner: str = "✅ Перевод <b>{amount} ₽</b> подтверждён"
    text_transfer_confirm_agent: str = "🎉 <b>Перевод подтверждён!</b>\\n\\nСумма: <b>{amount} ₽</b>"
    text_transfer_confirm_answer: str = "Подтверждено"
    text_transfer_reject_owner: str = "❌ Перевод <b>{amount} ₽</b> отклонён"
    text_transfer_reject_agent: str = "❌ <b>Перевод не подтверждён</b>\\n\\nСумма: {amount} ₽\\n<i>Свяжись с владельцем</i>"
    text_transfer_reject_answer: str = "Отклонено"

    # ─── Информация о VPN ─────────────────────────────────────────
    text_vpn_info: str = (
        "📡 <b>О сервисе</b>\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "🤝 <b>Как это работает</b>\\n\\n"
        "Подключаешь знакомых к VPN, берёшь с них сколько договоришься.\\n\\n"
        "• Клиент платит <b>тебе</b> — любым удобным вам способом\\n"
        "• <b>{base_price} ₽</b> с каждого клиента → владельцу\\n"
        "• Остальное — твоё\\n\\n"
        "💡 <i>Пример: продал за {example_total} ₽ → {base_price} ₽ владельцу, <b>{example_profit} ₽</b> твои</i>\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "📊 <b>Как работает учёт</b>\\n\\n"
        "Бот просто ведёт записи — никаких платёжек.\\n\\n"
        "1. Подключил клиента → накопилась сумма «к оплате»\\n"
        "2. Когда удобно — переводишь @support\\n"
        "3. Он подтверждает → сумма обнуляется\\n\\n"
        "<i>Деньги с клиентов принимаешь сам — как договоришься.</i>\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "{tariffs_block}\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "🌍 <b>Что получает клиент</b>\\n\\n"
        "• 4 локации: 🇳🇱 NL · 🇺🇸 USA · 🇷🇺 RU · 🇩🇪 DE\\n"
        "• RU — низкий пинг, YouTube, Instagram и т.п.\\n\\n"
        "━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        "🛠 <b>Поддержка</b>\\n\\n"
        "Настройкой клиентам помогаю я (@support) —\\n"
        "приложения, ТВ, роутеры. Тебе с этим не нужно.\\n\\n"
        '🔗 <a href="https://example.com/vpn">example.com/vpn</a>'
    )
    text_tariff_pick_prompt: str = "📦 <b>Выбери тариф</b>\\n\\n<i>От тарифа зависит цена для владельца</i>"
    text_tariff_selected: str = "✅ <b>Тариф:</b> {name}\\n\\n💰 Цена владельцу: <b>{price} ₽</b>\\n📶 Трафик: <b>{traffic}</b>\\n{desc}\\n\\n{prompt}"
    text_tariffs_empty: str = "Тарифы пока не настроены."
    text_tariffs_header: str = "📦 <b>Доступные тарифы</b>\\n<i>Условия и цены для клиентов:</i>\\n"
    text_tariffs_line: str = "\\n◆ <b>{name}</b> — <b>{price} ₽</b>\\n   📶 {traffic}{desc}"
    text_tariffs_screen_title: str = ""
    text_tariffs_screen_subtitle: str = ""

    # ─── Управление агентами (владелец) ───────────────────────────
    text_owner_agents_title: str = "⚙️ <b>Управление агентами</b>"
    text_owner_limit_no_agents: str = "📭 Агентов пока нет"
    text_owner_limit_choose_agent: str = "👤 <b>Выбери агента</b>"
    text_owner_limit_prompt: str = "💳 <b>Лимит агента</b>\\n\\n<i>0 = без лимита</i>"
    text_owner_add_agent_prompt: str = "📱 <b>Telegram ID агента</b>\\n\\n<i>или перешли его сообщение сюда</i>"
    text_owner_add_agent_done: str = "✅ Агент добавлен"
    text_owner_add_agent_forward_failed: str = "❌ Не удалось определить отправителя\\n\\nПришли его <b>Telegram ID</b>"
    text_owner_delete_client_prompt: str = "🗑 <b>Удалить клиента</b>\\n\\nВведи username или перешли сообщение клиента"
    text_owner_delete_agent_prompt: str = "🗑 <b>Удалить агента</b>\\n\\nВведи Telegram ID, @username или перешли сообщение"
    text_owner_delete_agent_pick: str = "🗑 <b>Выбери агента для удаления</b>"
    text_owner_delete_client_confirm: str = "⚠️ Удалить клиента <b>{username}</b>?\\nЭто действие необратимо."
    text_owner_delete_agent_confirm: str = (
        "⚠️ Удалить агента <b>{name}</b>?\\n"
        "Будут удалены его клиенты и связанные данные."
    )
    text_owner_delete_client_done: str = "✅ Клиент удалён: <b>{username}</b>"
    text_owner_delete_agent_done: str = "✅ Агент удалён: <b>{name}</b>\\nУдалено клиентов: {clients}"
    text_owner_delete_not_found: str = "❌ Не найдено"
    text_limit_invalid: str = "❌ Введи число"
    text_limit_negative: str = "❌ Лимит не может быть отрицательным"
    text_agent_not_found: str = "❌ Агент не найден"
    text_owner_limit_done: str = "✅ Лимит: <b>{agent_name}</b> → {limit}"
    text_owner_sync_start: str = "🔄 Синхронизация..."
    text_owner_sync_done: str = "✅ <b>Синхронизация завершена</b>\\n\\nУдалено: {removed}\\nОбновлено: {updated}"
    text_owner_report_no_agents: str = "📭 Агентов пока нет"
    text_owner_report_header: str = "📊 <b>Отчёт по агентам</b>\\n"
    text_owner_report_line: str = "{status} <b>{name}</b>\\n  💰 {payable} ₽ · лимит {limit} · клиентов {clients}"

    # ─── Общие ────────────────────────────────────────────────────
    text_cancelled: str = "👌 Отменено"
    text_balance_updated: str = "Обновлено"
    text_balance_actual: str = "Актуально"
    text_balance_failed: str = "Ошибка"

    # ─── Форматирование списков ───────────────────────────────────
    text_date_none: str = "—"
    text_date_expired: str = "<i>просрочено</i>"
    text_days_left: str = "{days}д"
    text_client_meta: str = "{date} · {payment}₽"
    text_client_price: str = "{price}₽"
    text_client_price_none: str = "—"
    text_client_tariff: str = "📦 {name} ({price}₽)"
    text_client_tariff_default: str = "Базовый"
    text_client_tariff_none: str = "—"
    text_client_paid: str = "{amount}₽"
    text_client_paid_none: str = "—"
    text_client_line: str = (
        "▸ <b>{username}</b>{agent_part}\\n"
        "  {tariff} · {date} · агентская {price}/мес"
    )
    text_client_list_separator: str = ""
    text_clients_list_empty: str = "📭 <b>Клиентов пока нет</b>\\n\\n<i>Подключи первого через «+ Подключить»</i>"
    text_clients_list_header_agent: str = "📋 <b>Твои клиенты</b>\\n"
    text_clients_list_header_owner: str = "📋 <b>Все клиенты</b>\\n"
    text_client_button_label: str = "{username} · {meta}"
    text_agent_limit_button: str = "{name} · {limit}"

    # ─── Кнопки ───────────────────────────────────────────────────
    btn_vpn_info: str = "📡 О сервисе"
    btn_balance: str = "💰 К оплате"
    btn_balance_with_limit: str = "💰 {balance} ₽ (лимит {limit})"
    btn_new_client: str = "➕ Подключить"
    btn_renew: str = "🔄 Продлить"
    btn_clients: str = "📋 Клиенты"
    btn_pay: str = "💸 Внести оплату"
    btn_owner_agents: str = "⚙️ Управление агентами"
    btn_owner_add_agent: str = "➕ Добавить агента"
    btn_owner_limit: str = "💳 Лимиты агентов"
    btn_owner_report: str = "📊 Отчёт по агентам"
    btn_owner_sync: str = "🔄 Синхронизация"
    btn_owner_notify_preview: str = "👀 Кто получит уведомления"
    btn_owner_notify_send: str = "📨 Отправить уведомления"
    btn_owner_delete_client: str = "🗑️ Удалить клиента"
    btn_owner_delete_agent: str = "🗑️ Удалить агента"
    btn_owner_back: str = "← Назад"
    btn_skip: str = "Пропустить →"
    btn_renew_default_days: str = "30 дней"
    btn_renew_90_days: str = "90 дней"
    btn_renew_180_days: str = "180 дней"
    btn_renew_365_days: str = "365 дней"
    btn_renew_same: str = "✅ Продлить как есть"
    btn_back: str = "← Назад"
    btn_cancel: str = "✕ Отмена"
    btn_back_to_menu: str = "← Меню"
    btn_prev: str = "←"
    btn_next: str = "→"
    btn_transfer_confirm: str = "✓ Получил"
    btn_transfer_reject: str = "✕ Не получал"
    btn_tariff_back: str = "← К тарифам"
    btn_tariffs: str = "📦 Тарифы"
    btn_delete_confirm: str = "🗑 Удалить"

    def _parse_base_price(self, raw: Optional[str]) -> Optional[int]:
        if raw is None:
            return None
        if isinstance(raw, int):
            value = raw
        else:
            text = str(raw).strip()
            if not text:
                return None
            try:
                value = int(text)
            except ValueError:
                return None
        if value <= 0:
            return None
        return value

    def _parse_int(self, raw: Optional[str]) -> Optional[int]:
        if raw is None:
            return None
        if isinstance(raw, int):
            return raw
        text = str(raw).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _parse_agent_ids(self, raw: Optional[str]) -> set[int]:
        if not raw:
            return set()
        ids: set[int] = set()
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ids.add(int(item))
            except ValueError:
                continue
        return ids

    def tariffs(self) -> list[dict]:
        tariffs: list[dict] = []
        for idx in range(1, 5):
            name = getattr(self, f"tariff_{idx}_name", None)
            base_raw = getattr(self, f"tariff_{idx}_base_price", None)
            desc = getattr(self, f"tariff_{idx}_desc", None) or ""
            agent_ids_raw = getattr(self, f"tariff_{idx}_agent_ids", None)
            internal_squads = getattr(self, f"tariff_{idx}_internal_squads", None)
            external_squad = getattr(self, f"tariff_{idx}_external_squad", None)
            traffic_limit_gb_raw = getattr(self, f"tariff_{idx}_traffic_limit_gb", None)
            traffic_reset_strategy = getattr(self, f"tariff_{idx}_traffic_reset_strategy", None)
            hwid_device_limit_raw = getattr(self, f"tariff_{idx}_hwid_device_limit", None)
            tag = getattr(self, f"tariff_{idx}_tag", None)
            base_price = self._parse_base_price(base_raw)
            if base_price is None:
                continue
            label = (name or "").strip() or f"Тариф {idx}"
            tariffs.append(
                {
                    "id": idx,
                    "name": label,
                    "base_price": base_price,
                    "desc": desc.strip(),
                    "agent_ids": self._parse_agent_ids(agent_ids_raw),
                    "remnawave": {
                        "internal_squads": internal_squads,
                        "external_squad": external_squad,
                        "traffic_limit_gb": self._parse_int(traffic_limit_gb_raw),
                        "traffic_reset_strategy": (traffic_reset_strategy or "").strip() or None,
                        "hwid_device_limit": self._parse_int(hwid_device_limit_raw),
                        "tag": (tag or "").strip() or None,
                    },
                }
            )
        return tariffs

    def visible_tariffs(self, telegram_id: int) -> list[dict]:
        visible: list[dict] = []
        for tariff in self.tariffs():
            agent_ids: set[int] = tariff.get("agent_ids", set())
            if not agent_ids or telegram_id in agent_ids:
                visible.append(tariff)
        return visible

    @property
    def inbound_uuid_set(self) -> set[str]:
        if not self.remnawave_inbound_uuids:
            return set()
        return {value.strip() for value in self.remnawave_inbound_uuids.split(",") if value.strip()}

    @property
    def internal_squads_set(self) -> list[str]:
        if not self.remnawave_internal_squads:
            return []
        return [value.strip() for value in self.remnawave_internal_squads.split(",") if value.strip()]

    @property
    def admin_id_set(self) -> set[int]:
        if not self.admin_ids:
            return set()
        return {int(value.strip()) for value in self.admin_ids.split(",") if value.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
