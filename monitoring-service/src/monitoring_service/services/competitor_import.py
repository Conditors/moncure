from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from monitoring_service.contracts.collection import CollectionRequestedPayloadV1, ImportDraftV1
from monitoring_service.contracts.competitor_prices import CompetitorPricesUpdatedPayloadV1
from monitoring_service.db.models.competitor_offer import CompetitorAvailabilityStatus, CompetitorOffer
from monitoring_service.db.models.import_job import ImportJob, ImportJobStatus, ImportJobType
from monitoring_service.db.models.price_observations import PriceObservation
from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    CompetitorUrlAlreadyExists,
    ImportJobImpossibleUpdateError,
    ImportJobNotFoundError,
    ImportTypeSupportedError,
    ProductNotFoundError,
)
from monitoring_service.services.import_dto import ImportJobResult
from monitoring_service.url_normalization import normalize_product_url

@dataclass(frozen=True)
class ConfirmCompetitorCommand:
    name: str
    current_price: Decimal
    article: str | None = None
    source: str | None = None

class CompetitorImportService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def start_competitor_import(
        self,
        organization_id: UUID,
        target_product_id: UUID,
        url: str,
    ) -> ImportJobResult:
        normalized_url = normalize_product_url(url)

        async with self._uow_factory() as work:
            target_product = await work.products.get_by_id(
                organization_id=organization_id, product_id=target_product_id
            )
            if target_product is None:
                raise ProductNotFoundError(target_product_id)

            await work.advisory_lock.acquire_competitor_offer_url(
                organization_id=organization_id,
                target_product_id=target_product_id,
                normalized_url=normalized_url,
            )

            competitor = await work.competitors.get_by_normalized_url(
                organization_id=organization_id,
                product_id=target_product_id,
                normalized_url=normalized_url,
            )

            if competitor is not None:
                raise CompetitorUrlAlreadyExists(competitor.id)

            candidate = ImportJob(
                organization_id=organization_id,
                target_product_id=target_product_id,
                url=url,
                normalized_url=normalized_url,
            )

            created_job = await work.import_jobs.create_competitor_if_absent(candidate)

            if created_job is None:
                active_job = await work.import_jobs.get_active_competitor_by_url(
                    organization_id=organization_id,
                    target_product_id=target_product_id,
                    normalized_url=normalized_url,
                )
                if active_job is not None:
                    return ImportJobResult(
                        job_id=active_job.id, status=active_job.status
                    )

                created_job = await work.import_jobs.create_competitor_if_absent(
                    candidate
                )
                if created_job is None:
                    raise RuntimeError("Could not create or find an active import job")

            payload = CollectionRequestedPayloadV1(
                job_id=created_job.id,
                job_kind="IMPORT_JOB",
                url=created_job.normalized_url,
            )

            work.outbox.add(
                RabbitMqOutbox(
                    aggregate_type="import_job",
                    aggregate_id=created_job.id,
                    event_type="collection.requested",
                    schema_version=1,
                    payload=payload.model_dump(mode="json"),
                )
            )

            result = ImportJobResult(job_id=created_job.id, status=created_job.status)
            await work.commit()
            return result

    async def confirm(
        self,
        organization_id: UUID,
        job_id: UUID,
        command: ConfirmCompetitorCommand,
    ) -> UUID:
        async with self._uow_factory() as work:
            job = await work.import_jobs.get_by_id_for_organization(
                organization_id=organization_id,
                job_id=job_id,
            )

            if job is None:
                raise ImportJobNotFoundError(job_id)

            if job.job_type != ImportJobType.COMPETITOR_OFFER_IMPORT:
                raise ImportTypeSupportedError(
                    job_id=job_id,
                    import_type=job.job_type,
                    trigger_type=ImportJobType.COMPETITOR_OFFER_IMPORT,
                )

            target_product_id = job.target_product_id
            if target_product_id is None:
                raise RuntimeError(f"Competitor import {job_id} has no target_product_id")

            await work.advisory_lock.acquire_competitor_offer_url(
                organization_id=job.organization_id,
                target_product_id=target_product_id,
                normalized_url=job.normalized_url,
            )

            job_for_update = await work.import_jobs.get_by_id_for_update_for_organization(
                organization_id=job.organization_id,
                job_id=job.id,
            )

            if job_for_update is None:
                raise ImportJobNotFoundError(job_id)

            if job_for_update.status == ImportJobStatus.COMPLETED:
                created_competitor_offer_id = job_for_update.created_competitor_offer_id
                if created_competitor_offer_id is None:
                    raise RuntimeError(
                        f"Completed import {job_id} has no created_competitor_offer_id"
                    )
                return created_competitor_offer_id

            if job_for_update.status != ImportJobStatus.READY_FOR_REVIEW:
                raise ImportJobImpossibleUpdateError(job_id)

            draft_data = ImportDraftV1.model_validate(job_for_update.draft_data)
            currency = draft_data.currency

            if currency != "RUB":
                raise ValueError("Only RUB is supported for product imports.")

            result_observed_at = job_for_update.result_observed_at
            if result_observed_at is None:
                raise RuntimeError(f"Competitor import {job_id} has no result_observed_at")

            offer = CompetitorOffer(
                organization_id=job_for_update.organization_id,
                product_id=target_product_id,
                name=command.name,
                url=job_for_update.url,
                normalized_url=job_for_update.normalized_url,
                article=command.article,
                source=command.source,
                current_price=command.current_price,
                current_price_version=1,
                currency=currency,
                availability_status=CompetitorAvailabilityStatus.AVAILABLE,
                last_checked_at=result_observed_at,
            )
            work.competitors.add(offer)

            await work.flush()

            competitor_offer_id = offer.id
            job_for_update.created_competitor_offer_id = competitor_offer_id
            job_for_update.status = ImportJobStatus.COMPLETED

            new_version = await work.products.change_competitor_price_version(
                organization_id=offer.organization_id,
                product_id=offer.product_id
            )

            observation = PriceObservation(
                organization_id=offer.organization_id,
                competitor_offer_id=competitor_offer_id,
                collection_job_id=None,
                price=offer.current_price,
                currency=offer.currency,
                availability_status=offer.availability_status,
                price_version=offer.current_price_version,
                observed_at=datetime.now(UTC),
            )

            work.price_observation.add(observation)

            payload = CompetitorPricesUpdatedPayloadV1(
                organization_id=offer.organization_id,
                product_id=offer.product_id,
                prices_version=new_version,
            )

            work.outbox.add(
                RabbitMqOutbox(
                    aggregate_type="product",
                    aggregate_id=offer.product_id,
                    event_type="product.competitor_prices_updated",
                    schema_version=1,
                    payload=payload.model_dump(mode="json"),
                )
            )

            await work.commit()
            return competitor_offer_id
