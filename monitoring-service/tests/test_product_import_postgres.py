import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from monitoring_service.contracts.collection import (
    AvailabilityStatus,
    CollectionCompletedPayloadV1,
    CollectionFailedErrorV1,
    CollectionFailedV1,
    CollectionSucceededV1,
)
from monitoring_service.db.models import (
    ImportJob,
    ImportJobStatus,
    Product,
    RabbitMqInbox,
    RabbitMqOutbox,
)
from monitoring_service.db.repositories.import_job import ImportJobRepository
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    ImportJobImpossibleUpdateError,
    ImportJobNotFoundError,
    ProductUrlAlreadyExists,
)
from monitoring_service.services.product_import import (
    ConfirmOwnProductCommand,
    ProductImportService,
)
from tests.postgres_helpers import backend_pid, wait_for_blocker

pytestmark = pytest.mark.asyncio
URL = "https://example.com/item"
COMMAND = ConfirmOwnProductCommand(name="Edited item", price=Decimal("12.3400"))


def success(
    job_id: UUID,
    *,
    currency: str | None = "RUB",
    availability: AvailabilityStatus = "AVAILABLE",
) -> CollectionSucceededV1:
    return CollectionSucceededV1(
        message_id=uuid4(),
        contract_version=1,
        job_id=job_id,
        job_kind="IMPORT_JOB",
        completed_at=datetime.now(UTC),
        status="SUCCESS",
        data=CollectionCompletedPayloadV1(
            name="Collected item",
            price=Decimal("10.00") if currency is not None else None,
            currency=currency,
            availability_status=availability,
        ),
        error=None,
    )


def failure(job_id: UUID) -> CollectionFailedV1:
    return CollectionFailedV1(
        message_id=uuid4(),
        contract_version=1,
        job_id=job_id,
        job_kind="IMPORT_JOB",
        completed_at=datetime.now(UTC),
        status="FAILED",
        data=None,
        error=CollectionFailedErrorV1(
            code="PRICE_NOT_FOUND", message="Price not found"
        ),
    )


async def test_own_import_full_flow_and_tenant_scope(engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id, other_organization_id = uuid4(), uuid4()
    original_url = "HTTPS://Example.COM:443/item#fragment"

    first, second = await asyncio.gather(
        service.start_own_product(organization_id, original_url),
        service.start_own_product(organization_id, URL),
    )
    assert first == second
    assert first.status is ImportJobStatus.PENDING
    assert (
        await service.start_own_product(organization_id, URL)
    ).job_id == first.job_id
    with pytest.raises(ImportJobImpossibleUpdateError):
        await service.confirm(organization_id, first.job_id, COMMAND)
    with pytest.raises(ImportJobNotFoundError):
        await service.get(first.job_id, other_organization_id)
    with pytest.raises(ImportJobNotFoundError):
        await service.confirm(other_organization_id, first.job_id, COMMAND)

    other = await service.start_own_product(other_organization_id, URL)
    assert other.job_id != first.job_id

    event = success(first.job_id)
    assert await service.apply_collection_result(event) is True
    assert await service.apply_collection_result(event) is False
    details = await service.get(first.job_id, organization_id)
    assert details.status is ImportJobStatus.READY_FOR_REVIEW
    assert details.draft_data is not None and details.draft_data.price == Decimal(10)

    product_id, repeated = await asyncio.gather(
        service.confirm(organization_id, first.job_id, COMMAND),
        service.confirm(organization_id, first.job_id, COMMAND),
    )
    assert product_id == repeated
    assert (
        await service.get(first.job_id, organization_id)
    ).created_product_id == product_id
    with pytest.raises(ProductUrlAlreadyExists):
        await service.start_own_product(organization_id, URL)

    async with sessions() as reader:
        product = await reader.get(Product, product_id)
        assert product is not None
        assert product.price == COMMAND.price and product.name == COMMAND.name
        assert product.normalized_url == URL and product.currency == "RUB"
        assert (
            await reader.scalars(
                select(Product.id).where(Product.organization_id == organization_id)
            )
        ).all() == [product_id]
        outbox = (
            await reader.scalars(
                select(RabbitMqOutbox).where(
                    RabbitMqOutbox.aggregate_id == first.job_id
                )
            )
        ).one()
        assert outbox.payload == {
            "job_id": str(first.job_id),
            "job_kind": "IMPORT_JOB",
            "url": URL,
        }


async def test_start_keeps_distinct_idna_hosts_separate(engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()

    unicode_job = await service.start_own_product(
        organization_id, "https://faß.de/item"
    )
    ascii_job = await service.start_own_product(
        organization_id, "https://xn--fa-hia.de/item"
    )
    other_job = await service.start_own_product(organization_id, "https://fass.de/item")

    assert unicode_job.job_id == ascii_job.job_id
    assert unicode_job.job_id != other_job.job_id
    async with sessions() as reader:
        events = await reader.scalars(
            select(RabbitMqOutbox).where(
                RabbitMqOutbox.aggregate_id.in_([unicode_job.job_id, other_job.job_id])
            )
        )
        requested_urls = [event.payload["url"] for event in events]
        assert len(requested_urls) == 2
        assert set(requested_urls) == {
            "https://fass.de/item",
            "https://xn--fa-hia.de/item",
        }


@pytest.mark.parametrize("duplicate", [False, True])
async def test_concurrent_delivery_only_applies_one_result(
    engine: AsyncEngine, duplicate: bool
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    job_id = (await service.start_own_product(organization_id, URL)).job_id
    first = success(job_id)
    second = first if duplicate else failure(job_id)

    applied_first, applied_second = await asyncio.gather(
        service.apply_collection_result(first),
        service.apply_collection_result(second),
    )
    assert applied_first != applied_second

    async with sessions() as reader:
        assert await reader.get(RabbitMqInbox, first.message_id) is not None
        assert await reader.get(RabbitMqInbox, second.message_id) is not None
        job = await reader.get(ImportJob, job_id)
        assert job is not None
        if duplicate or applied_first:
            assert job.status is ImportJobStatus.READY_FOR_REVIEW
            assert (
                job.draft_data is not None
                and job.result_observed_at == first.completed_at
            )
            assert job.error_code is None
        else:
            assert (
                job.status is ImportJobStatus.FAILED
                and job.error_code == "PRICE_NOT_FOUND"
            )
            assert job.draft_data is None


@pytest.mark.parametrize(
    ("currency", "availability", "error_code"),
    [
        ("USD", "AVAILABLE", "unsupported_currency"),
        (None, "OUT_OF_STOCK", "product_unavailable"),
    ],
)
async def test_nonconfirmable_result_fails_and_allows_a_new_start(
    engine: AsyncEngine,
    currency: str | None,
    availability: AvailabilityStatus,
    error_code: str,
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    first = await service.start_own_product(organization_id, URL)
    assert await service.apply_collection_result(
        success(first.job_id, currency=currency, availability=availability)
    )
    details = await service.get(first.job_id, organization_id)
    assert details.status is ImportJobStatus.FAILED
    assert details.error_code == error_code and details.draft_data is None
    with pytest.raises(ImportJobImpossibleUpdateError):
        await service.confirm(organization_id, first.job_id, COMMAND)
    assert (
        await service.start_own_product(organization_id, URL)
    ).job_id != first.job_id


async def test_unknown_job_rolls_back_new_inbox_record(engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    event = success(uuid4())
    with pytest.raises(ImportJobNotFoundError):
        await service.apply_collection_result(event)
    async with sessions() as reader:
        assert await reader.get(RabbitMqInbox, event.message_id) is None


async def test_start_waits_for_confirm_and_cannot_create_redundant_import(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    job_id = (await service.start_own_product(organization_id, URL)).job_id
    assert await service.apply_collection_result(success(job_id))
    ready_to_commit: asyncio.Future[int] = asyncio.Future()
    started: asyncio.Future[int] = asyncio.Future()
    release_commit = asyncio.Event()

    class PausedConfirm(UnitOfWork):
        async def commit(self) -> None:
            await self.flush()
            ready_to_commit.set_result(await backend_pid(self._session))
            await release_commit.wait()
            await super().commit()

    class ObservedStart(UnitOfWork):
        async def __aenter__(self) -> Self:
            await super().__aenter__()
            started.set_result(await backend_pid(self._session))
            return self

    confirming = ProductImportService(lambda: PausedConfirm(sessions))
    starting = ProductImportService(lambda: ObservedStart(sessions))
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        confirm_task = tasks.create_task(
            confirming.confirm(organization_id, job_id, COMMAND)
        )
        blocker_pid = await ready_to_commit

        async def start_during_confirm() -> ProductUrlAlreadyExists:
            with pytest.raises(ProductUrlAlreadyExists) as raised:
                await starting.start_own_product(organization_id, URL)
            return raised.value

        start_task = tasks.create_task(start_during_confirm())
        waiter_pid = await started
        async with sessions() as observer:
            await wait_for_blocker(observer, blocker_pid, waiter_pid)
        release_commit.set()
    assert start_task.result().product_id == confirm_task.result()
    async with sessions() as reader:
        assert (
            await reader.scalars(
                select(ImportJob.id).where(ImportJob.organization_id == organization_id)
            )
        ).all() == [job_id]


async def test_confirmation_failure_rolls_back_flushed_product(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    job_id = (await service.start_own_product(organization_id, URL)).job_id
    assert await service.apply_collection_result(success(job_id))

    class FailingCommit(UnitOfWork):
        async def commit(self) -> None:
            await self.flush()
            raise RuntimeError("injected failure after flush")

    failing = ProductImportService(lambda: FailingCommit(sessions))
    with pytest.raises(RuntimeError, match="injected failure after flush"):
        await failing.confirm(organization_id, job_id, COMMAND)

    async with sessions() as reader:
        assert (
            await reader.scalar(
                select(Product.id).where(Product.organization_id == organization_id)
            )
            is None
        )
        job = await reader.get(ImportJob, job_id)
        assert job is not None and job.status is ImportJobStatus.READY_FOR_REVIEW
        assert job.created_product_id is None


async def test_start_retries_when_conflicting_import_failed_before_lookup(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    first = await service.start_own_product(organization_id, URL)

    class ImportFailsBeforeLookup(ImportJobRepository):
        async def get_active_own_by_url(
            self, organization_id: UUID, normalized_url: str
        ) -> ImportJob | None:
            assert await service.apply_collection_result(failure(first.job_id))
            return await super().get_active_own_by_url(organization_id, normalized_url)

    class RacingStart(UnitOfWork):
        async def __aenter__(self) -> Self:
            await super().__aenter__()
            self.import_jobs = ImportFailsBeforeLookup(self._session)
            return self

    starting = ProductImportService(lambda: RacingStart(sessions))
    async with asyncio.timeout(5):
        second = await starting.start_own_product(organization_id, URL)
    assert second.job_id != first.job_id
    assert second.status is ImportJobStatus.PENDING
    assert (
        await service.get(first.job_id, organization_id)
    ).status is ImportJobStatus.FAILED

    async with sessions() as reader:
        outbox = await reader.scalars(
            select(RabbitMqOutbox.aggregate_id).where(
                RabbitMqOutbox.aggregate_id.in_([first.job_id, second.job_id])
            )
        )
        assert sorted(outbox.all()) == sorted([first.job_id, second.job_id])


async def test_collector_result_can_be_retried_after_rollback(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine)
    service = ProductImportService(lambda: UnitOfWork(sessions))
    organization_id = uuid4()
    job_id = (await service.start_own_product(organization_id, URL)).job_id
    event = success(job_id)

    class FailingCommit(UnitOfWork):
        async def commit(self) -> None:
            await self.flush()
            raise RuntimeError("injected failure after flush")

    failing = ProductImportService(lambda: FailingCommit(sessions))
    with pytest.raises(RuntimeError, match="injected failure after flush"):
        await failing.apply_collection_result(event)

    async with sessions() as reader:
        assert await reader.get(RabbitMqInbox, event.message_id) is None
    assert (
        await service.get(job_id, organization_id)
    ).status is ImportJobStatus.PENDING
    assert await service.apply_collection_result(event)
    assert (
        await service.get(job_id, organization_id)
    ).status is ImportJobStatus.READY_FOR_REVIEW
