import asyncio
import logging

from app.bot.app import create_bot, create_dispatcher
from app.config import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal, engine
from app.remnawave.client import RemnawaveClient
from app.services.notify_service import notify_expiring_clients
from app.services.sync_service import sync_all_clients_with_remnawave


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    bot = create_bot(settings.bot_token)
    dp = create_dispatcher()

    await init_db(engine)
    asyncio.create_task(run_sync_loop())
    asyncio.create_task(run_expiry_notify_loop(bot))
    await dp.start_polling(bot)


async def run_sync_loop() -> None:
    settings = get_settings()
    remnawave_client = RemnawaveClient(
        settings.remnawave_api_url,
        settings.remnawave_api_key,
        settings.remnawave_mode,
        settings.remnawave_caddy_token,
    )
    while True:
        try:
            async with SessionLocal() as session:
                removed, updated = await sync_all_clients_with_remnawave(session, remnawave_client)
            logging.info("Sync finished. Removed=%s Updated=%s", removed, updated)
        except Exception as exc:
            logging.error("Sync failed: %s", exc)
        await asyncio.sleep(settings.sync_interval_seconds)


async def run_expiry_notify_loop(bot) -> None:
    settings = get_settings()
    while True:
        try:
            async with SessionLocal() as session:
                notified = await notify_expiring_clients(session, bot)
            if notified:
                logging.info("Expiry notify: sent=%s", notified)
        except Exception as exc:
            logging.error("Expiry notify failed: %s", exc)
        await asyncio.sleep(settings.expiry_notify_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
