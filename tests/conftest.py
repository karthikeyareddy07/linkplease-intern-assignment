"""Shared fixtures for pytest."""
import asyncio
import pytest_asyncio
from app.db import db


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    await db.init_db()
    await db.reset()
    yield
    await db.reset()
