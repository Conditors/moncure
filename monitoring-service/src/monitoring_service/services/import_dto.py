from dataclasses import dataclass
from uuid import UUID

from monitoring_service.contracts.collection import ImportDraftV1
from monitoring_service.db.models.import_job import ImportJobStatus


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