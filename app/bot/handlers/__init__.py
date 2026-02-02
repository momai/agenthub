from aiogram import Router

from .clients import router as clients_router
from .menu import router as menu_router
from .owner import router as owner_router
from .payments import router as payments_router
from .renewals import router as renewals_router

router = Router()
router.include_router(menu_router)
router.include_router(clients_router)
router.include_router(renewals_router)
router.include_router(payments_router)
router.include_router(owner_router)
