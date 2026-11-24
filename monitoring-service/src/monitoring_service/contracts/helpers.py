
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

def require_integer_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError("contract_version must be a JSON integer")
    return value


def parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("timestamp must be an ISO 8601 string")


ContractVersionV1 = Annotated[Literal[1], BeforeValidator(require_integer_version)]
WireTimestamp = Annotated[AwareDatetime, BeforeValidator(parse_timestamp)]