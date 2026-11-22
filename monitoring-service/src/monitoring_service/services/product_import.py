from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from pydantic import TypeAdapter

from monitoring_service.contracts.collection import (
    CollectionCompletedV1,
    CollectionRequestedPayloadV1,
    ImportDraftV1,
    Price,
)
from monitoring_service.db.models.import_job import (
    ImportJob,
    ImportJobStatus,
    ImportJobType,
)
from monitoring_service.db.models.products import Product
from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    ImportJobImpossibleUpdateError,
    ImportJobNotFoundError,
    ImportTypeSupportedError,
    ProductUrlAlreadyExists,
)
from monitoring_service.url_normalization import normalize_product_url


@dataclass(frozen=True)
class ImportJobResult:
    job_id: UUID
    status: ImportJobStatus


@dataclass(frozen=True)
class ImportJobDetails:
    job_id: UUID
    status: ImportJobStatus
    draft_data: ImportDraftV1 | None = None
    error_code: str | None = None
    created_product_id: UUID | None = None


_price_adapter = TypeAdapter[Decimal](Price)


@dataclass(frozen=True)
class ConfirmOwnProductCommand:
    name: str
    price: Decimal
    article: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        _price_adapter.validate_python(self.price, strict=True)

        for label, value, limit in (
            ("Name", self.name, 128),
            ("Article", self.article, 55),
            ("Source", self.source, 50),
        ):
            if value is not None and (
                not value.strip() or "\x00" in value or len(value) > limit
            ):
                raise ValueError(
                    f"{label} must be non-blank, contain no NUL characters, "
                    f"and be at most {limit} characters."
                )
        if self.article is not None and self.source is None:
            raise ValueError("Source is required when article is provided.")


class ProductImportService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def start_own_product(
        self, organization_id: UUID, url: str
    ) -> ImportJobResult:
        normalized_url = normalize_product_url(url)

        async with self._uow_factory() as work:
            await work.advisory_lock.acquire_product_url(
                organization_id, normalized_url
            )

            product = await work.products.get_by_normalized_url(
                organization_id, normalized_url
            )
            if product is not None:
                raise ProductUrlAlreadyExists(product.id)

            candidate = ImportJob(
                organization_id=organization_id,
                url=url,
                normalized_url=normalized_url,
            )

            created_job = await work.import_jobs.create_own_if_absent(candidate)

            if created_job is None:
                active_job = await work.import_jobs.get_active_own_by_url(
                    organization_id, normalized_url
                )
                if active_job is not None:
                    return ImportJobResult(
                        job_id=active_job.id, status=active_job.status
                    )

                created_job = await work.import_jobs.create_own_if_absent(candidate)
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

    async def apply_collection_result(self, event: CollectionCompletedV1) -> bool:

        if event.job_kind != "IMPORT_JOB":
            raise ValueError("Expected IMPORT_JOB result")

        async with self._uow_factory() as work:
            is_new = await work.inbox.try_add(
                event_id=event.message_id, event_type="collection.completed"
            )

            if not is_new:
                return False

            existed_job = await work.import_jobs.get_by_id_for_update(event.job_id)
            if existed_job is None:
                raise ImportJobNotFoundError(event.job_id)

            if existed_job.status != ImportJobStatus.PENDING:
                await work.commit()
                return False

            if event.status == "FAILED":
                existed_job.error_code = event.error.code
                existed_job.error_message = event.error.message
                existed_job.status = ImportJobStatus.FAILED

            elif event.data.availability_status != "AVAILABLE":
                existed_job.error_code = "product_unavailable"
                existed_job.status = ImportJobStatus.FAILED

            elif event.data.currency != "RUB":
                existed_job.error_code = "unsupported_currency"
                existed_job.status = ImportJobStatus.FAILED

            else:
                draft_data = ImportDraftV1(
                    name=event.data.name,
                    price=event.data.price,
                    currency=event.data.currency,
                    article=event.data.article,
                    source=event.data.source,
                )
                existed_job.status = ImportJobStatus.READY_FOR_REVIEW
                existed_job.draft_data = draft_data.model_dump(mode="json")
                existed_job.result_observed_at = event.completed_at

            await work.commit()
            return True

    async def get(self, job_id: UUID, organization_id: UUID) -> ImportJobDetails:
        async with self._uow_factory() as work:
            job = await work.import_jobs.get_by_id_for_organization(
                organization_id=organization_id, job_id=job_id
            )

            if job is None:
                raise ImportJobNotFoundError(job_id)

            match job.status:
                case ImportJobStatus.PENDING | ImportJobStatus.PROCESSING:
                    return ImportJobDetails(
                        job_id=job.id,
                        status=job.status,
                    )

                case ImportJobStatus.READY_FOR_REVIEW:
                    return ImportJobDetails(
                        job_id=job.id,
                        status=job.status,
                        draft_data=ImportDraftV1.model_validate(job.draft_data),
                    )

                case ImportJobStatus.COMPLETED:
                    return ImportJobDetails(
                        job_id=job.id,
                        status=job.status,
                        created_product_id=job.created_product_id,
                    )

                case ImportJobStatus.FAILED:
                    return ImportJobDetails(
                        job_id=job.id,
                        status=job.status,
                        error_code=job.error_code,
                    )

    async def confirm(
        self,
        organization_id: UUID,
        job_id: UUID,
        command: ConfirmOwnProductCommand,
    ) -> UUID:
        async with self._uow_factory() as work:
            job = await work.import_jobs.get_by_id_for_organization(
                organization_id=organization_id,
                job_id=job_id,
            )

            if job is None:
                raise ImportJobNotFoundError(job_id)

            await work.advisory_lock.acquire_product_url(
                job.organization_id, job.normalized_url
            )

            job_for_update = (
                await work.import_jobs.get_by_id_for_update_for_organization(
                    organization_id=job.organization_id,
                    job_id=job.id,
                )
            )

            if job_for_update is None:
                raise ImportJobNotFoundError(job_id)

            elif job_for_update.job_type != ImportJobType.OWN_PRODUCT_IMPORT:
                raise ImportTypeSupportedError(
                    job_id=job_id,
                    import_type=job_for_update.job_type,
                    trigger_type=ImportJobType.OWN_PRODUCT_IMPORT,
                )

            elif job_for_update.status == ImportJobStatus.COMPLETED:
                created_product_id = job_for_update.created_product_id
                if created_product_id is None:
                    raise RuntimeError(
                        f"Completed import {job_id} has no created_product_id"
                    )
                return created_product_id

            if job_for_update.status != ImportJobStatus.READY_FOR_REVIEW:
                raise ImportJobImpossibleUpdateError(job_id)

            draft_data = ImportDraftV1.model_validate(job_for_update.draft_data)
            currency = draft_data.currency

            if currency != "RUB":
                raise ValueError("Only RUB is supported for product imports.")

            product = Product(
                organization_id=job_for_update.organization_id,
                name=command.name,
                url=job_for_update.url,
                normalized_url=job_for_update.normalized_url,
                article=command.article,
                source=command.source,
                price=command.price,
                currency=currency,
            )

            work.products.add(product)

            await work.flush()

            product_id = product.id
            job_for_update.created_product_id = product_id
            job_for_update.status = ImportJobStatus.COMPLETED

            await work.commit()
            return product_id
