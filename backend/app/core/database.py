"""
MongoDB connection and Beanie ODM initialisation.

Beanie sits on top of Motor (the async MongoDB driver) and lets us define
collections as Pydantic models. Because the rest of the app already speaks
Pydantic, models and API schemas share the same validation layer.
"""

import logging
from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


def get_database() -> AsyncIOMotorDatabase:
    """Raw database handle, used for aggregation pipelines on the dashboard."""
    if _database is None:
        raise RuntimeError("Database not initialised - call connect_to_mongo() first")
    return _database


async def connect_to_mongo(database=None) -> None:
    """
    Open the connection pool and register every Beanie document model.

    `database` can be injected for tests (mongomock) so the test suite doesn't
    need a running MongoDB server.
    """
    global _client, _database

    from app.models.audit_log import AuditLog
    from app.models.document import Document
    from app.models.report import ParsedReport
    from app.models.user import User

    if database is None:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=50,
            minPoolSize=5,
        )
        _database = _client[settings.MONGODB_DB_NAME]
        # Fail fast and loudly at startup rather than on the first request.
        await _client.admin.command("ping")
        logger.info("Connected to MongoDB database '%s'", settings.MONGODB_DB_NAME)
    else:
        _database = database

    await init_beanie(
        database=_database,
        document_models=[User, Document, ParsedReport, AuditLog],
    )
    logger.info("Beanie initialised with 4 collections")


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")