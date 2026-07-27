from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


def create_background_session() -> async_sessionmaker[AsyncSession]:
    """Create an independent engine+session for background threads.

    Background threads run their own asyncio event loop via asyncio.run(),
    so they cannot share the main event loop's engine/connection pool.
    """
    bg_engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return async_sessionmaker(bg_engine, class_=AsyncSession, expire_on_commit=False)
