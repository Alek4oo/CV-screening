"""Входна точка на FastAPI приложението.

Приложението не създава схема. Тя се движи единствено през Alembic:

    cd backend && alembic upgrade head

Стартиране срещу немигрирана база дава грешка от базата при първата заявка —
нарочно. Мълчаливо създадена таблица е по-лошото от двете.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import candidates, health, rankings, roles, rulesets
from app.core.config import settings
from app.models import *  # noqa: F401,F403  регистрира таблиците в Base.metadata

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version=settings.app_version)

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
