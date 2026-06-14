from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, inspect
import os
import logging

logger = logging.getLogger(__name__)

os.makedirs("backend/data", exist_ok=True)

engine = create_async_engine("sqlite+aiosqlite:///./backend/data/netops.db", echo=False)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    from backend.database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_schema(conn)
    logger.info("Database tables created/verified")


async def _migrate_schema(conn):
    migrations = {
        "intents": [
            ("execution_status", "ALTER TABLE intents ADD COLUMN execution_status VARCHAR DEFAULT 'not_started'"),
            ("execution_result", "ALTER TABLE intents ADD COLUMN execution_result JSON"),
            ("conflict_detected", "ALTER TABLE intents ADD COLUMN conflict_detected BOOLEAN DEFAULT 0"),
            ("conflict_details", "ALTER TABLE intents ADD COLUMN conflict_details TEXT"),
            ("sla_conditions", "ALTER TABLE intents ADD COLUMN sla_conditions JSON"),
            ("sla_status", "ALTER TABLE intents ADD COLUMN sla_status VARCHAR DEFAULT 'UNKNOWN'"),
            ("last_evaluation_time", "ALTER TABLE intents ADD COLUMN last_evaluation_time DATETIME"),
        ]
    }
    for table_name, columns in migrations.items():
        try:
            existing = set()
            def _get_columns(connection):
                insp = inspect(connection)
                return [c["name"] for c in insp.get_columns(table_name)]
            existing = set(await conn.run_sync(_get_columns))
            for col_name, alter_sql in columns:
                if col_name not in existing:
                    await conn.execute(text(alter_sql))
                    logger.info(f"Migration: added column {col_name} to {table_name}")
        except Exception as e:
            logger.warning(f"Migration check for {table_name}: {e}")


async def get_db_session():
    async with async_session_maker() as session:
        yield session