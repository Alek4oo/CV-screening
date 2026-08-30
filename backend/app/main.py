"""Входна точка на FastAPI приложението."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import candidates, health, rankings, roles, rulesets
from app.core.config import settings
from app.core.db import Base, engine
from app.models import *  # noqa: F401,F403  регистрира таблиците в Base.metadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Временно решение за разработка. Замества се с Alembic — create_all не
        # мигрира съществуваща схема, само създава липсващи таблици.
        logger.warning("AUTO_CREATE_TABLES=1: creating the schema via create_all")
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# React изгледът се сервира от друг произход (порт 3000/5173), затова браузърът
# иска изричното разрешение тук. Списъкът е изброен, не "*" — с credentials "*"
# и без това не работи, а и произходите са известни.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(candidates.router)
app.include_router(roles.router)
app.include_router(rulesets.router)
app.include_router(rankings.router)
