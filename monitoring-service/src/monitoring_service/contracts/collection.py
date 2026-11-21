"""Сообщения между Monitoring Service и Collector."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from monitoring_service.url_normalization import MAX_NORMALIZED_URL_BYTES

JobKind = Literal["IMPORT_JOB", "COLLECTION_JOB"]
AvailabilityStatus = Literal["AVAILABLE", "OUT_OF_STOCK", "UNAVAILABLE"]
Price = Annotated[Decimal, Field(gt=0, max_digits=19, decimal_places=4)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]



class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ImportDraftV1(ContractModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128)
    price: Price
    currency: Currency
    article: str | None = Field(default=None, min_length=1, max_length=55)
    source: str | None = Field(default=None, min_length=1, max_length=50)

class CollectionRequestedPayloadV1(ContractModel):
    job_id: UUID
    job_kind: JobKind
    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def check_url_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_NORMALIZED_URL_BYTES:
            raise ValueError("URL exceeds 2000 bytes")
        return value


class CollectionRequestedV1(CollectionRequestedPayloadV1):
    message_id: UUID
    contract_version: Literal[1]
    requested_at: AwareDatetime


class CollectionCompletedPayloadV1(ContractModel):
    name: str = Field(min_length=1, max_length=128)
    price: Price | None
    currency: Currency | None
    availability_status: AvailabilityStatus
    article: str | None = Field(default=None, min_length=1, max_length=55)
    source: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("price", mode="before")
    @classmethod
    def check_price_type(cls, value: object) -> object:
        if value is not None and not isinstance(value, (str, Decimal)):
            raise ValueError("price must be a decimal string")
        return value

    @field_validator("name", "article", "source", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_related_fields(self) -> Self:
        if (self.price is None) != (self.currency is None):
            raise ValueError("price and currency must be provided together")
        if self.availability_status == "AVAILABLE" and self.price is None:
            raise ValueError("available products require price and currency")
        if self.article is not None and self.source is None:
            raise ValueError("article requires source")
        return self


class CollectionFailedErrorV1(ContractModel):
    code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CollectionResultEnvelopeV1(ContractModel):
    message_id: UUID
    contract_version: Literal[1]
    job_id: UUID
    job_kind: JobKind
    completed_at: AwareDatetime


class CollectionSucceededV1(CollectionResultEnvelopeV1):
    status: Literal["SUCCESS"]
    data: CollectionCompletedPayloadV1
    error: None


class CollectionFailedV1(CollectionResultEnvelopeV1):
    status: Literal["FAILED"]
    data: None
    error: CollectionFailedErrorV1


CollectionCompletedV1 = Annotated[
    CollectionSucceededV1 | CollectionFailedV1, Field(discriminator="status")
]
