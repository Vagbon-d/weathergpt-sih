"""
Lightweight persistence layer for WeatherGPT IVR/SMS channel.

Uses SQLite via SQLAlchemy (async) so it fits alongside the existing
FastAPI/Uvicorn stack without introducing a separate DB process.

Schema:
  caller_profiles — one row per phone number; stores home location and language
                    preference so repeat callers don't have to spell their district
                    every time they call in.
"""

from __future__ import annotations

import os
from sqlalchemy import Column, String, Float, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typing import AsyncGenerator

# Honour DATABASE_URL from .env; default to a SQLite file next to main.py
_DEFAULT_DB = "sqlite+aiosqlite:///./weathergpt_callers.db"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class CallerProfile(Base):
    """
    Stores a feature-phone caller's home location and preference.
    Primary key is the E.164 phone number string (e.g. '+919876543210').
    """
    __tablename__ = "caller_profiles"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    home_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="hi")
    user_type: Mapped[str] = mapped_column(String(32), default="farmer")  # farmer | fisherman | general
    district: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


async def init_db() -> None:
    """Create all tables on first startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
