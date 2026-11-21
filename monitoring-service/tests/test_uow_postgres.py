from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from monitoring_service.db.models import ImportJob, RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork

pytestmark = pytest.mark.asyncio


async def stage_import(
    work: UnitOfWork, job_id: UUID, event_id: UUID, *, schema_version: int = 1
) -> None:
    url = "https://example.com/product"
    job = await work.import_jobs.create_own_if_absent(
        ImportJob(id=job_id, organization_id=uuid4(), url=url, normalized_url=url)
    )
    assert job is not None and job.id == job_id

    work.outbox.add(
        RabbitMqOutbox(
            event_id=event_id,
            aggregate_type="import_job",
            aggregate_id=job_id,
            event_type="collection.requested",
            schema_version=schema_version,
            payload={"url": url},
        )
    )


async def test_commit_persists_import_and_outbox(engine: AsyncEngine) -> None:
    job_id, event_id = uuid4(), uuid4()
    async with UnitOfWork(async_sessionmaker(engine)) as work:
        await stage_import(work, job_id, event_id)
        await work.commit()

    async with AsyncSession(engine) as reader:
        assert await reader.get(ImportJob, job_id) is not None
        event = await reader.get(RabbitMqOutbox, event_id)
        assert event is not None and event.aggregate_id == job_id


@pytest.mark.parametrize("raise_after_flush", [False, True])
async def test_exit_without_commit_rolls_back_both_records(
    engine: AsyncEngine, raise_after_flush: bool
) -> None:
    job_id, event_id = uuid4(), uuid4()
    try:
        async with UnitOfWork(async_sessionmaker(engine)) as work:
            await stage_import(work, job_id, event_id)
            await work.flush()
            if raise_after_flush:
                raise RuntimeError("service failed after flush")
    except RuntimeError as error:
        assert raise_after_flush and str(error) == "service failed after flush"
    else:
        assert not raise_after_flush, "The exception must propagate out of the UoW"

    async with AsyncSession(engine) as reader:
        assert await reader.get(ImportJob, job_id) is None
        assert await reader.get(RabbitMqOutbox, event_id) is None


async def test_outbox_insert_failure_rolls_back_import(engine: AsyncEngine) -> None:
    job_id, event_id = uuid4(), uuid4()
    with pytest.raises(IntegrityError, match="ck_rabbitmq_outbox_schema_version"):
        async with UnitOfWork(async_sessionmaker(engine)) as work:
            await stage_import(work, job_id, event_id, schema_version=0)
            await work.flush()

    async with AsyncSession(engine) as reader:
        assert await reader.get(ImportJob, job_id) is None
        assert await reader.get(RabbitMqOutbox, event_id) is None
