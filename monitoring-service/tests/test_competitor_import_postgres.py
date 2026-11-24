import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from monitoring_service.db.models import (
    ImportJob,
    ImportJobStatus,
    ImportJobType,
    PriceObservation,
    Product,
    RabbitMqOutbox,
)
from monitoring_service.db.models.competitor_offer import (
    CompetitorAvailabilityStatus,
    CompetitorOffer,
)
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    CompetitorUrlAlreadyExists,
    ProductNotFoundError,
)
from monitoring_service.services.competitor_import import (
    CompetitorImportService,
    ConfirmCompetitorCommand,
)
from monitoring_service.services.product_import import ProductImportService
from tests.test_product_import_postgres import success

pytestmark = pytest.mark.asyncio
URL = "https://example.com/item"
COMMAND = ConfirmCompetitorCommand(name="Confirmed offer", current_price=Decimal("120.00"))


@pytest_asyncio.fixture
async def targets(engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    organization_id, product_a, product_b = uuid4(), uuid4(), uuid4()
    async with AsyncSession(engine) as session, session.begin():
        for product_id in (product_a, product_b):
            session.add(
                Product(
                    id=product_id,
                    organization_id=organization_id,
                    name="Target",
                    price=Decimal(10),
                    currency="RUB",
                )
            )
    return organization_id, product_a, product_b


@pytest.mark.parametrize("foreign", [False, True])
async def test_missing_or_foreign_target_creates_no_import(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID], foreign: bool
) -> None:
    owner, product_id, _ = targets
    organization_id, target_id = (uuid4(), product_id) if foreign else (owner, uuid4())
    sessions = async_sessionmaker(engine)
    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    url = f"{URL}/{uuid4()}"

    with pytest.raises(ProductNotFoundError) as raised:
        await service.start_competitor_import(organization_id, target_id, url)
    assert raised.value.product_id == target_id
    async with sessions() as reader:
        assert (
            await reader.scalar(select(ImportJob.id).where(ImportJob.url == url))
            is None
        )
        assert (
            await reader.scalar(
                select(RabbitMqOutbox.event_id).where(
                    RabbitMqOutbox.payload["url"].astext == url
                )
            )
            is None
        )


async def test_existing_offer_error_returns_offer_id(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID]
) -> None:
    organization_id, product_id, _ = targets
    offer_id = uuid4()
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(
            CompetitorOffer(
                id=offer_id,
                organization_id=organization_id,
                product_id=product_id,
                name="Existing offer",
                url=URL,
                normalized_url=URL,
                current_price=Decimal(10),
                currency="RUB",
                availability_status=CompetitorAvailabilityStatus.AVAILABLE,
                last_checked_at=datetime.now(UTC),
            )
        )

    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    with pytest.raises(CompetitorUrlAlreadyExists) as raised:
        await service.start_competitor_import(organization_id, product_id, URL)
    assert raised.value.competitor_offer_id == offer_id


async def test_concurrent_start_deduplicates_only_for_same_target(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID]
) -> None:
    organization_id, product_a, product_b = targets
    sessions = async_sessionmaker(engine)
    service = CompetitorImportService(lambda: UnitOfWork(sessions))

    first, duplicate, other = await asyncio.gather(
        service.start_competitor_import(organization_id, product_a, URL),
        service.start_competitor_import(organization_id, product_a, URL),
        service.start_competitor_import(organization_id, product_b, URL),
    )
    assert first == duplicate
    assert first.job_id != other.job_id

    async with sessions() as reader:
        jobs = (
            await reader.scalars(
                select(ImportJob).where(ImportJob.organization_id == organization_id)
            )
        ).all()
        assert {(job.target_product_id, job.job_type) for job in jobs} == {
            (product_a, ImportJobType.COMPETITOR_OFFER_IMPORT),
            (product_b, ImportJobType.COMPETITOR_OFFER_IMPORT),
        }
        assert len(jobs) == 2
        events = (
            await reader.scalars(
                select(RabbitMqOutbox).where(
                    RabbitMqOutbox.aggregate_id.in_([first.job_id, other.job_id])
                )
            )
        ).all()
        assert len(events) == 2
        assert {event.aggregate_id for event in events} == {first.job_id, other.job_id}
        assert all(event.payload["url"] == URL for event in events)


async def ready_import(
    sessions: async_sessionmaker[AsyncSession],
    organization_id: UUID,
    product_id: UUID,
    url: str,
) -> tuple[UUID, datetime]:
    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    result = await service.start_competitor_import(organization_id, product_id, url)
    event = success(result.job_id)
    collector_results = ProductImportService(lambda: UnitOfWork(sessions))
    assert await collector_results.apply_collection_result(event)
    return result.job_id, event.completed_at


@pytest.mark.parametrize("distinct_jobs", [False, True])
async def test_concurrent_confirm_persists_history_and_product_versions(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID], distinct_jobs: bool
) -> None:
    organization_id, product_id, _ = targets
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.competitor_prices_version = 7

    first_job, first_observed = await ready_import(sessions, organization_id, product_id, URL)
    second_job, second_observed = first_job, first_observed
    if distinct_jobs:
        second_job, second_observed = await ready_import(
            sessions, organization_id, product_id, f"{URL}/other"
        )

    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    first_offer, second_offer = await asyncio.wait_for(
        asyncio.gather(
            service.confirm(organization_id, first_job, COMMAND),
            service.confirm(organization_id, second_job, COMMAND),
        ),
        timeout=10,
    )
    assert (first_offer != second_offer) == distinct_jobs
    offers = {first_offer: first_observed, second_offer: second_observed}
    async with sessions() as reader:
        product = await reader.get(Product, product_id)
        assert product is not None
        assert product.competitor_prices_version == 7 + len(offers)
        saved_offers = (
            await reader.scalars(
                select(CompetitorOffer).where(CompetitorOffer.product_id == product_id)
            )
        ).all()
        assert {offer.id for offer in saved_offers} == set(offers)
        for offer in saved_offers:
            assert offer.current_price == COMMAND.current_price
            assert offer.last_checked_at == offers[offer.id]
        for job_id, offer_id in [(first_job, first_offer), (second_job, second_offer)]:
            job = await reader.get(ImportJob, job_id)
            assert job is not None and job.status is ImportJobStatus.COMPLETED
            assert job.created_competitor_offer_id == offer_id
        observations = (
            await reader.scalars(
                select(PriceObservation).where(PriceObservation.organization_id == organization_id)
            )
        ).all()
        assert len(observations) == len(offers)
        assert {row.competitor_offer_id for row in observations} == set(offers)
        for row in observations:
            assert row.price == COMMAND.current_price
            assert row.price_version == 1
            assert row.collection_job_id is None
        events = (
            await reader.scalars(
                select(RabbitMqOutbox).where(
                    RabbitMqOutbox.aggregate_id == product_id,
                    RabbitMqOutbox.event_type == "product.competitor_prices_updated",
                )
            )
        ).all()
        assert sorted(event.payload["prices_version"] for event in events) == list(
            range(8, product.competitor_prices_version + 1)
        )


async def test_competitor_confirm_failure_rolls_back_all_writes(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID]
) -> None:
    organization_id, product_id, _ = targets
    sessions = async_sessionmaker(engine)
    job_id, _ = await ready_import(sessions, organization_id, product_id, URL)

    class FailingCommit(UnitOfWork):
        async def commit(self) -> None:
            await self.flush()
            raise RuntimeError("injected failure after flush")

    service = CompetitorImportService(lambda: FailingCommit(sessions))
    with pytest.raises(RuntimeError, match="injected failure after flush"):
        await service.confirm(organization_id, job_id, COMMAND)

    async with sessions() as reader:
        job = await reader.get(ImportJob, job_id)
        assert job is not None and job.status is ImportJobStatus.READY_FOR_REVIEW
        assert job.created_competitor_offer_id is None
        product = await reader.get(Product, product_id)
        assert product is not None and product.competitor_prices_version == 0
        assert await reader.scalar(
            select(CompetitorOffer.id).where(CompetitorOffer.product_id == product_id)
        ) is None
        assert await reader.scalar(
            select(PriceObservation.id).where(PriceObservation.organization_id == organization_id)
        ) is None
        assert await reader.scalar(
            select(RabbitMqOutbox.event_id).where(
                RabbitMqOutbox.aggregate_id == product_id,
                RabbitMqOutbox.event_type == "product.competitor_prices_updated",
            )
        ) is None
