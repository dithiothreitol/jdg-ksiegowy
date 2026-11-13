"""Przypadki uzycia: kontrakty cykliczne i platnosci (wyciag z banku)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.errors import NotFoundError
from jdg_ksiegowy.contracts.runner import run_contracts
from jdg_ksiegowy.invoice.models import Buyer, Contract
from jdg_ksiegowy.registry.payments import match_payments, parse_bank_csv
from jdg_ksiegowy.registry.repository import ContractRepository, InvoiceRepository


class ContractView(BaseModel):
    id: str
    buyer_name: str
    buyer_nip: str
    description: str
    net: Decimal
    vat_rate: Decimal
    day_of_month: int
    active: bool

    @classmethod
    def of(cls, c: Contract) -> ContractView:
        return cls(
            id=c.id,
            buyer_name=c.buyer.name,
            buyer_nip=c.buyer.nip,
            description=c.description,
            net=c.net_amount,
            vat_rate=c.vat_rate,
            day_of_month=c.day_of_month,
            active=c.active,
        )


class AddContractInput(BaseModel):
    buyer_name: str
    buyer_nip: str
    buyer_address: str
    description: str
    net: Decimal
    vat_rate: Decimal = Decimal("23")
    buyer_email: str | None = None
    day_of_month: int = Field(default=-1, ge=-1, le=28)  # -1 = ostatni dzien roboczy


def add_contract(inp: AddContractInput) -> ContractView:
    contract = Contract(
        buyer=Buyer(
            name=inp.buyer_name, nip=inp.buyer_nip, address=inp.buyer_address, email=inp.buyer_email
        ),
        description=inp.description,
        net_amount=inp.net,
        vat_rate=inp.vat_rate,
        day_of_month=inp.day_of_month,
    )
    ContractRepository().save(contract)
    audit("contract.add", contract.id, "ok", {"buyer": inp.buyer_name, "net": str(inp.net)})
    return ContractView.of(contract)


class ContractList(BaseModel):
    contracts: list[ContractView]


def list_contracts() -> ContractList:
    return ContractList(contracts=[ContractView.of(c) for c in ContractRepository().active()])


class ContractRun(BaseModel):
    date: date
    generated: list[str]
    skipped_count: int


def run(today: date | None = None) -> ContractRun:
    today = today or date.today()
    result = run_contracts(today=today)
    if result.generated:
        audit("contract.run", today.isoformat(), "ok", {"generated": result.generated})
    return ContractRun(date=today, generated=result.generated, skipped_count=len(result.skipped))


class PaymentMatch(BaseModel):
    invoice: str
    amount: Decimal
    date: date
    description: str
    marked_paid: bool


class PaymentImport(BaseModel):
    matched: list[PaymentMatch]
    unmatched_bank_rows: int
    unmatched_invoices: list[str]


def import_bank_csv(path: Path, *, auto_mark: bool = False) -> PaymentImport:
    """Dopasuj wplywy z wyciagu CSV do niezaplaconych faktur; opcjonalnie oznacz zaplate."""
    if not path.exists():
        raise NotFoundError(f"Plik nie istnieje: {path}")
    repo = InvoiceRepository()
    match = match_payments(parse_bank_csv(path), repo.list())
    matched = []
    for row, inv in match.matched:
        if auto_mark:
            repo.mark_paid(inv.number, datetime.combine(row.transaction_date, datetime.min.time()))
            audit("invoice.mark_paid", inv.number, "ok", {"source": path.name})
        matched.append(
            PaymentMatch(
                invoice=inv.number,
                amount=row.amount,
                date=row.transaction_date,
                description=row.description[:80],
                marked_paid=auto_mark,
            )
        )
    return PaymentImport(
        matched=matched,
        unmatched_bank_rows=len(match.unmatched_bank),
        unmatched_invoices=[i.number for i in match.unmatched_invoices],
    )
