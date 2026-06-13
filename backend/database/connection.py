from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from ..core.config import settings

connect_args = {"check_same_thread": False} if settings.environment == "development" else {}
engine = create_async_engine(settings.database_url, echo=False, connect_args=connect_args)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session