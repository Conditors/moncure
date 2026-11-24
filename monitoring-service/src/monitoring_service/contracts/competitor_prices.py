from uuid import UUID
from pydantic import Field

from monitoring_service.contracts.helpers import ContractModel, ContractVersionV1, WireTimestamp



class CompetitorPricesUpdatedPayloadV1(ContractModel):
    organization_id: UUID
    product_id: UUID
    prices_version: int = Field(gt=0)

class CompetitorPricesUpdatedV1(CompetitorPricesUpdatedPayloadV1):
    message_id: UUID
    contract_version: ContractVersionV1
    occurated_at: WireTimestamp

