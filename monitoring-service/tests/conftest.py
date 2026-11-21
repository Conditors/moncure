import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from monitoring_service.config import get_settings


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    database = os.getenv("MONITORING_TEST_POSTGRES_DB")
    if not database:
        pytest.skip("Set MONITORING_TEST_POSTGRES_DB to a migrated disposable database")
    if not database.startswith("monitoring_test_"):
        pytest.fail("The disposable database name must start with monitoring_test_")

    engine = create_async_engine(get_settings().postgres_url.set(database=database))
    try:
        yield engine
    finally:
        await engine.dispose()
