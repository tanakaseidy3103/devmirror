"""
DevMirror - データベース設定
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy ベースモデル"""
    pass


# Base 定義後にモデルを登録する（循環 import を避ける）
from app.db import models as _models  # noqa: E402,F401

# 非同期エンジンの作成
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

# セッションファクトリー
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """データベーステーブルの初期化"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """データベースセッションの依存性注入"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
