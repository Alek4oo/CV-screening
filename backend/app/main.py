"""Входна точка на FastAPI приложението."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import candidates, health
from app.core.config import settings
from app.core.db import Base, engine
from app.models import *  # noqa: F401,F403  регистрира таблиците в Base.metadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Временно решение за разработка. Замества се с Alembic — create_all не
        # мигрира съществуваща схема, само създава липсващи таблици.
        logger.warning("AUTO_CREATE_TABLES=1: създавам схемата през create_all")
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.include_router(health.router)
app.include_router(candidates.router)
