import logging
import typing
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker, close_all_sessions
from app.store.database import db

if typing.TYPE_CHECKING:
    from app.web.app import Application


class Database:
    def __init__(self, app: "Application"):
        self.app = app
        self._engine: Optional[AsyncEngine] = None
        self._db: Optional[declarative_base] = None
        self.session: Optional[sessionmaker] = None

    async def connect(self, *_: list, **__: dict) -> None:
        self._db = db
        self._engine = create_async_engine(
            "postgresql+asyncpg://{}:{}@{}/{}".format(
                self.app.config.database.user,
                self.app.config.database.password,
                self.app.config.database.host,
                self.app.config.database.database
            ),
            echo=True
        )

        self.session = sessionmaker(self._engine, expire_on_commit=False, autoflush=True, class_=AsyncSession)

    async def disconnect(self, *_: list, **__: dict) -> None:
        try:
            session = AsyncSession(self._engine)
            for table in self.app.database._db.metadata.tables:
                await session.execute(text(f"TRUNCATE {table} CASCADE"))
                await session.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))

            await session.commit()
        except Exception as err:
            logging.warning(err)

        close_all_sessions()
