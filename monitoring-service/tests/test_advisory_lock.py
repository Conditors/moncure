import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from monitoring_service.config import get_settings
from monitoring_service.db.repositories.advisory_lock import PostgresAdvisoryLock
from tests.postgres_helpers import backend_pid, wait_for_blocker

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("MONITORING_TEST_POSTGRES") != "1",
        reason="Set MONITORING_TEST_POSTGRES=1 to run against configured PostgreSQL",
    ),
]


@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_same_product_url_waits_until_transaction_ends(finish: str) -> None:
    engine = create_async_engine(get_settings().postgres_url)
    organization_id = uuid4()
    url = "https://example.com/product"

    try:
        async with AsyncSession(engine) as first, AsyncSession(engine) as second:
            await PostgresAdvisoryLock(first).acquire_product_url(organization_id, url)
            first_pid = await backend_pid(first)
            second_pid = await backend_pid(second)

            waiting = asyncio.create_task(
                PostgresAdvisoryLock(second).acquire_product_url(organization_id, url)
            )
            try:
                await wait_for_blocker(first, first_pid, second_pid)
                if finish == "commit":
                    await first.commit()
                else:
                    await first.rollback()

                await asyncio.wait_for(waiting, timeout=5)
            finally:
                if not waiting.done():
                    waiting.cancel()
                await asyncio.gather(waiting, return_exceptions=True)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("different_organization", [False, True])
async def test_different_product_url_key_does_not_wait(
    different_organization: bool,
) -> None:
    engine = create_async_engine(get_settings().postgres_url)
    organization_id = uuid4()
    url = "https://example.com/product"

    try:
        async with AsyncSession(engine) as first, AsyncSession(engine) as second:
            await PostgresAdvisoryLock(first).acquire_product_url(organization_id, url)
            await second.execute(text("SET LOCAL lock_timeout = '1s'"))

            other_organization_id = (
                uuid4() if different_organization else organization_id
            )
            other_url = url if different_organization else "https://example.com/other"
            await PostgresAdvisoryLock(second).acquire_product_url(
                other_organization_id, other_url
            )
    finally:
        await engine.dispose()
