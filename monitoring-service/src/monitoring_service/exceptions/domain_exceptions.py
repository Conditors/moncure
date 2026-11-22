from uuid import UUID

from monitoring_service.db.models.import_job import ImportJobType


class ProductUrlAlreadyExists(Exception):
    def __init__(
        self,
        product_id: UUID,
    ) -> None:
        self.product_id = product_id

        super().__init__("A product with this URL already exists.")


class ProductNotFoundError(Exception):
    def __init__(self, product_id: UUID) -> None:
        self.product_id = product_id
        super().__init__("Target product was not found.")


class CompetitorUrlAlreadyExists(Exception):
    def __init__(self, competitor_offer_id: UUID) -> None:
        self.competitor_offer_id = competitor_offer_id
        super().__init__("A competitor offer with this URL already exists.")


class ImportJobNotFoundError(Exception):
    def __init__(
        self,
        job_id: UUID,
    ):
        self.job_id = job_id

        super().__init__(f"A job with id={job_id} was not found.")


class ImportJobImpossibleUpdateError(Exception):
    def __init__(self, job_id: UUID):
        self.job_id = job_id

        super().__init__(f"job with id={job_id} cannot be update")


class ImportTypeSupportedError(Exception):
    def __init__(
        self, job_id: UUID, import_type: ImportJobType, trigger_type: ImportJobType
    ):
        self.job_id = job_id
        self.import_type = import_type
        self.trigger_type = trigger_type

        super().__init__(
            f"Type {import_type} not supported in this import for import with id={job_id} type must be {trigger_type}"
        )
