import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from monitoring_service.db.models import (
    ImportJob,
    ImportJobStatus,
    ImportJobType,
    Product,
)
from monitoring_service.db.models.rabbitmq_inbox import RabbitMqInbox
from monitoring_service.db.repositories.import_job import ImportJobRepository
from monitoring_service.db.repositories.product import ProductRepository
from monitoring_service.db.repositories.rabbitmq_inbox import InboxRepository
from tests.postgres_helpers import backend_pid, wait_for_blocker

pytestmark = pytest.mark.asyncio


def make_job(organization_id: UUID, url: str) -> ImportJob:
    return ImportJob(
        id=uuid4(),
        organization_id=organization_id,
        job_type=ImportJobType.OWN_PRODUCT_IMPORT,
        status=ImportJobStatus.PENDING,
        url=url,
        normalized_url=url,
    )


@pytest.mark.parametrize("first_commits", [True, False])
async def test_concurrent_active_import_inserts(
    engine: AsyncEngine, first_commits: bool
) -> None:
    organization_id = uuid4()
    url = "https://example.com/import"
    first_job = make_job(organization_id, url)
    second_job = make_job(organization_id, url)

    async with AsyncSession(engine) as first, AsyncSession(engine) as second:
        first_pid = await backend_pid(first)
        second_pid = await backend_pid(second)
        created = await ImportJobRepository(first).create_own_if_absent(first_job)
        assert created is not None
        assert created.id == first_job.id

        waiting = asyncio.create_task(
            ImportJobRepository(second).create_own_if_absent(second_job)
        )
        try:
            await wait_for_blocker(first, first_pid, second_pid)
            if first_commits:
                await first.commit()
            else:
                await first.rollback()
            result = await asyncio.wait_for(waiting, timeout=5)
            if first_commits:
                assert result is None
            else:
                assert result is not None and result.id == second_job.id
            await second.commit()
        finally:
            if not waiting.done():
                waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async with AsyncSession(engine) as reader:
        ids = await reader.scalars(
            select(ImportJob.id).where(ImportJob.organization_id == organization_id)
        )
        assert ids.all() == [first_job.id if first_commits else second_job.id]


async def test_duplicate_job_id_is_a_primary_key_error(engine: AsyncEngine) -> None:
    organization_id = uuid4()
    original = make_job(organization_id, "https://example.com/first")
    duplicate = make_job(organization_id, "https://example.com/second")
    duplicate.id = original.id

    async with AsyncSession(engine) as session:
        repository = ImportJobRepository(session)
        assert await repository.create_own_if_absent(original) is not None
        with pytest.raises(IntegrityError, match="import_jobs_pkey"):
            await repository.create_own_if_absent(duplicate)


async def test_inbox_deduplicates_event_delivered_concurrently(
    engine: AsyncEngine,
) -> None:
    event_id = uuid4()
    event_type = "collection.completed"
    async with AsyncSession(engine) as first, AsyncSession(engine) as second:
        first_pid = await backend_pid(first)
        second_pid = await backend_pid(second)
        assert await InboxRepository(first).try_add(event_id, event_type) is True
        waiting = asyncio.create_task(
            InboxRepository(second).try_add(event_id, event_type)
        )
        try:
            await wait_for_blocker(first, first_pid, second_pid)
            await first.commit()
            assert await asyncio.wait_for(waiting, timeout=5) is False
            await second.commit()
        finally:
            if not waiting.done():
                waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async with AsyncSession(engine) as reader:
        assert await InboxRepository(reader).try_add(event_id, event_type) is False
        count = await reader.scalar(
            select(func.count())
            .select_from(RabbitMqInbox)
            .where(RabbitMqInbox.event_id == event_id)
        )
        assert count == 1


async def test_product_and_import_searches_are_tenant_scoped(
    engine: AsyncEngine,
) -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    url = "https://example.com/product"
    product = Product(
        id=uuid4(),
        organization_id=organization_id,
        name="Test product",
        url=url,
        normalized_url=url,
        price=Decimal("10.00"),
        currency="RUB",
    )
    async with AsyncSession(engine) as session:
        products = ProductRepository(session)
        jobs = ImportJobRepository(session)
        products.add(product)
        await session.flush()
        assert await products.get_by_id(organization_id, product.id) is product
        assert await products.get_by_normalized_url(organization_id, url) is product
        assert await products.get_by_id(other_organization_id, product.id) is None
        assert await products.get_by_normalized_url(other_organization_id, url) is None

        job = make_job(organization_id, url)
        job.status = ImportJobStatus.FAILED
        competitor = make_job(organization_id, url)
        competitor.job_type = ImportJobType.COMPETITOR_OFFER_IMPORT
        competitor.target_product_id = product.id
        completed = make_job(organization_id, url)
        completed.status = ImportJobStatus.COMPLETED
        completed.created_product_id = product.id
        session.add_all(
            [job, competitor, completed, make_job(other_organization_id, url)]
        )
        assert await jobs.get_active_own_by_url(organization_id, url) is None

        job.status = ImportJobStatus.READY_FOR_REVIEW
        assert await jobs.get_active_own_by_url(organization_id, url) is job
        assert (
            await jobs.get_by_id_for_organization(other_organization_id, job.id) is None
        )
        assert (
            await jobs.get_by_id_for_update_for_organization(
                other_organization_id, job.id
            )
            is None
        )


async def test_locked_import_read_refreshes_cached_status(engine: AsyncEngine) -> None:
    organization_id = uuid4()
    job = make_job(organization_id, "https://example.com/status")
    job_id = job.id
    async with AsyncSession(engine) as reader, AsyncSession(engine) as writer:
        writer.add(job)
        await writer.commit()
        jobs = ImportJobRepository(reader)
        loaded = await jobs.get_by_id_for_organization(organization_id, job_id)
        assert loaded is not None
        assert loaded.status == ImportJobStatus.PENDING

        await writer.execute(
            update(ImportJob)
            .where(ImportJob.id == loaded.id)
            .values(status=ImportJobStatus.READY_FOR_REVIEW)
        )
        await writer.commit()

        refreshed = await jobs.get_by_id_for_update_for_organization(
            organization_id, loaded.id
        )
        assert refreshed is loaded
        assert refreshed.status == ImportJobStatus.READY_FOR_REVIEW

        reader_pid = await backend_pid(reader)
        writer_pid = await backend_pid(writer)
        waiting = asyncio.create_task(
            ImportJobRepository(writer).get_by_id_for_update(job_id)
        )
        try:
            await wait_for_blocker(reader, reader_pid, writer_pid)
            await reader.rollback()
            locked_by_writer = await asyncio.wait_for(waiting, timeout=5)
            assert locked_by_writer is not None and locked_by_writer.id == job_id
        finally:
            if not waiting.done():
                waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
