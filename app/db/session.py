from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from app.config import get_settings


def create_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


engine = create_engine()
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
