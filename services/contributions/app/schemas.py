import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(v: str) -> str:
    return _CTRL.sub("", v).strip()


Name = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(_clean)]
Message = Annotated[str, Field(max_length=300), AfterValidator(_clean)]


class StkIn(BaseModel):
    phone: str = Field(max_length=20)
    amount: int
    name: Name
    message: Message = ""
    show_name: bool = True
    website: str = Field(default="", max_length=200)


class StatusOut(BaseModel):
    id: str
    status: str
    message: str


class ManualIn(BaseModel):
    method: Literal["cash", "bank", "mpesa_manual"]
    amount: int = Field(gt=0, le=10_000_000)
    name: Name
    message: Message = ""
    show_name: bool = True
    reference: Annotated[str, Field(max_length=80), AfterValidator(_clean)] = ""


class ReviewIn(BaseModel):
    to: Literal["confirmed", "void"]
    note: Annotated[str, Field(min_length=5, max_length=500), AfterValidator(_clean)]


class ContributorOut(BaseModel):
    name: str
    amount: int | None = None
    message: str = ""


class SummaryOut(BaseModel):
    giving_open: bool
    total: int
    count: int
    currency: str = "KES"
    contributors: list[ContributorOut]
    paybill: str = ""
    account: str = ""
    min_amount: int
    max_amount: int


class EventOut(BaseModel):
    at: datetime
    from_status: str
    to_status: str
    actor: str
    note: str


class LedgerRow(BaseModel):
    id: str
    created_at: datetime
    method: str
    status: str
    amount_requested: int
    amount_received: int | None
    contributor_name: str
    message: str
    show_name: bool
    phone_masked: str
    mpesa_receipt: str | None
    reference: str
    result_desc: str
    confirmed_at: datetime | None


class LedgerOut(BaseModel):
    rows: list[LedgerRow]
    total_confirmed: int
    by_status: dict[str, int]


class LedgerDetail(LedgerRow):
    events: list[EventOut]
