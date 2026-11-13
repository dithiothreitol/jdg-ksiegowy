"""Przypadki uzycia: JPK_V7M / JPK_EWP — budowa, walidacja, wysylka do bramki MF, status.

Wysylka jest dwufazowa i zostawia slad w tabeli `filings` (numer referencyjny,
status, UPO), wiec po przekroczeniu czasu albo restarcie procesu `jpk status`
dokonczy sprawdzanie bez ponownej wysylki.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import ClassVar, Literal

from lxml import etree
from pydantic import BaseModel

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.confirm import require_confirmation, sha256_hex, with_change
from jdg_ksiegowy.app.errors import (
    ConfigMissingError,
    ConflictError,
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)
from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
from jdg_ksiegowy.mf_gateway.client import MFGatewayClient, SubmitResult
from jdg_ksiegowy.registry.repository import (
    ExpenseRepository,
    Filing,
    FilingRepository,
    InvoiceRepository,
)
from jdg_ksiegowy.tax.ewp import save_jpk_ewp
from jdg_ksiegowy.tax.jpk import (
    SellerDataMissingError,
    period_fields,
    save_jpk_v7m,
    settle_vat,
)
from jdg_ksiegowy.tax.validation import schema_name, validate_jpk
from jdg_ksiegowy.tax.vat_period import VatLedger, previous

Form = Literal["JPK_V7M", "JPK_EWP"]
JPK_DIR_NAME = "jpk"
STATUS_WAIT_DEFAULT = 600


class JpkBuildResult(BaseModel):
    form: Form
    year: int
    month: int | None
    purpose: int  # 1 = zlozenie, 2 = korekta
    correction_no: int
    file_path: str
    invoice_count: int
    expense_count: int
    sales_net: Decimal
    sales_vat: Decimal
    vat_carry_forward: Decimal | None = None  # P_39
    vat_due: Decimal | None = None  # P_38
    vat_deductible: Decimal | None = None  # P_48
    vat_to_pay: Decimal | None = None  # P_51
    vat_surplus: Decimal | None = None  # P_62
    revenue: Decimal | None = None  # JPK_EWP: suma przychodow
    xsd_valid: bool
    xsd_errors: list[str]


def _jpk_dir() -> Path:
    return DATA_DIR / JPK_DIR_NAME


def _next_correction_path(stem: str) -> tuple[int, Path]:
    """Kolejny wolny numer korekty: _K1, _K2... — zlozony oryginal zostaje jako dowod."""
    taken = [int(p.stem.rsplit("_K", 1)[1]) for p in _jpk_dir().glob(f"{stem}_K*.xml")]
    n = max(taken, default=0) + 1
    return n, _jpk_dir() / f"{stem}_K{n}.xml"


def build_v7m(
    year: int, month: int, *, correction: bool = False, reason: str | None = None
) -> JpkBuildResult:
    """Wygeneruj JPK_V7M za miesiac z rejestru i zwaliduj go wzgledem XSD MF."""
    if reason and not correction:
        raise InvalidInputError(
            "Uzasadnienie (P_ORDZU) dotyczy tylko korekty", hint="Dodaj --correction."
        )
    invoices = InvoiceRepository().list(year=year, month=month, by="sale_date")
    expenses = ExpenseRepository().list(year=year, month=month)
    stem = f"JPK_V7M_{year}_{month:02d}"
    number, path = _next_correction_path(stem) if correction else (0, _jpk_dir() / f"{stem}.xml")
    carry = VatLedger.load().carry_forward((year, month))
    with _domain_errors():
        save_jpk_v7m(
            invoices,
            month,
            year,
            path,
            correction=number,
            expenses=expenses,
            correction_reason=reason,
            carry_forward=carry,
        )
    sales_vat = sum((i.total_vat for i in invoices), Decimal("0"))
    settlement = settle_vat(period_fields(invoices, expenses), expenses, carry)
    check = validate_jpk(path.read_bytes())
    audit("jpk.build", str(path.name), "ok" if check.valid else "error", {"valid": check.valid})
    return JpkBuildResult(
        form="JPK_V7M",
        year=year,
        month=month,
        purpose=2 if correction else 1,
        correction_no=number,
        file_path=str(path),
        invoice_count=len(invoices),
        expense_count=len(expenses),
        sales_net=sum((i.total_net for i in invoices), Decimal("0")),
        sales_vat=sales_vat,
        vat_carry_forward=carry,
        vat_due=settlement.nalezny,
        vat_deductible=settlement.naliczony,
        vat_to_pay=settlement.to_pay,
        vat_surplus=settlement.nadwyzka,
        xsd_valid=check.valid,
        xsd_errors=check.errors[:10],
    )


@contextmanager
def _domain_errors() -> Iterator[None]:
    """Bledy generatora JPK -> bledy aplikacji: brak danych w .env albo dane rejestru."""
    try:
        yield
    except SellerDataMissingError as e:
        raise ConfigMissingError(str(e), hint="Uzupełnij dane podatnika SELLER_* w .env.") from e
    except ValueError as e:
        raise InvalidInputError(str(e)) from e


def build_ewp(
    year: int, *, ryczalt_rate: Decimal | None = None, correction: bool = False
) -> JpkBuildResult:
    """Wygeneruj roczna ewidencje przychodow JPK_EWP (rok wg daty uzyskania przychodu)."""
    invoices = InvoiceRepository().list(year=year, by="income")
    stem = f"JPK_EWP_{year}"
    number, path = _next_correction_path(stem) if correction else (0, _jpk_dir() / f"{stem}.xml")
    with _domain_errors():
        save_jpk_ewp(invoices, year, path, ryczalt_rate=ryczalt_rate, correction=number)
    check = validate_jpk(path.read_bytes())
    revenue = sum((i.total_net for i in invoices), Decimal("0"))
    return JpkBuildResult(
        form="JPK_EWP",
        year=year,
        month=None,
        purpose=2 if correction else 1,
        correction_no=number,
        file_path=str(path),
        invoice_count=len(invoices),
        expense_count=0,
        sales_net=revenue,
        sales_vat=sum((i.total_vat for i in invoices), Decimal("0")),
        revenue=revenue,
        xsd_valid=check.valid,
        xsd_errors=check.errors[:10],
    )


class ValidationView(BaseModel):
    file_path: str
    schema_name: str
    valid: bool
    errors: list[str]


def validate_file(path: Path) -> ValidationView:
    if not path.exists():
        raise NotFoundError(f"Plik nie istnieje: {path}")
    xml = path.read_bytes()
    try:
        name = schema_name(xml)
        result = validate_jpk(xml, name)
    except (ValueError, etree.XMLSyntaxError) as e:
        raise InvalidInputError(f"To nie jest poprawny plik JPK: {e}") from e
    return ValidationView(
        file_path=str(path), schema_name=name, valid=result.valid, errors=result.errors[:10]
    )


# --- Wysylka i status ------------------------------------------------------------


class FilingView(BaseModel):
    table_columns: ClassVar[tuple[str, ...]] = (
        "period",
        "form",
        "purpose",
        "env",
        "status",
        "reference_number",
    )

    id: int
    form: str
    period: str
    purpose: int
    env: str
    status: str
    reference_number: str | None
    status_code: int | None
    upo_path: str | None
    error: str | None
    file_path: str
    submitted_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def of(cls, f: Filing) -> FilingView:
        return cls(
            id=f.id,
            form=f.form,
            period=_period(f.year, f.month),
            purpose=f.purpose,
            env=f.env,
            status=f.status,
            reference_number=f.reference_number,
            status_code=f.status_code,
            upo_path=f.upo_path,
            error=f.error,
            file_path=f.file_path,
            submitted_at=f.submitted_at,
            updated_at=f.updated_at,
        )


class _JpkFacts(BaseModel):
    form: Form
    year: int
    month: int | None
    purpose: int
    totals: dict[str, str]


def _facts(xml: bytes) -> _JpkFacts:
    root = etree.fromstring(xml)
    form: Form = "JPK_EWP" if schema_name(xml).startswith("JPK_EWP") else "JPK_V7M"
    purpose = int(root.findtext(".//{*}Naglowek/{*}CelZlozenia") or "1")
    if form == "JPK_V7M":
        year = int(root.findtext(".//{*}Naglowek/{*}Rok") or 0)
        month: int | None = int(root.findtext(".//{*}Naglowek/{*}Miesiac") or 0)
        totals = {
            tag: root.findtext(f".//{{*}}PozycjeSzczegolowe/{{*}}{tag}") or "0"
            for tag in ("P_38", "P_48", "P_51", "P_62")
        }
    else:
        year = int((root.findtext(".//{*}Naglowek/{*}DataOd") or "0")[:4])
        month = None
        totals = {"SumaPrzychodow": root.findtext(".//{*}EWPCtrl/{*}SumaPrzychodow") or "0"}
    return _JpkFacts(form=form, year=year, month=month, purpose=purpose, totals=totals)


def _period(year: int, month: int | None) -> str:
    return f"{year}-{month:02d}" if month else str(year)


def _compared(repo: FilingRepository, facts: _JpkFacts, env: str) -> dict[str, str] | str:
    """Obowiazujaca deklaracja do porownania: korygowana (korekta) albo za poprzedni okres."""
    if facts.purpose == 2:
        year, month = facts.year, facts.month
    elif facts.month:
        year, month = previous((facts.year, facts.month))
    else:
        year, month = facts.year - 1, None
    accepted = [
        f
        for f in repo.list(form=facts.form, year=year, month=month)
        if f.env == env and f.status == "accepted"
    ]
    if not accepted:
        return f"brak przyjętej deklaracji za {_period(year, month)}"
    filing = accepted[0]  # lista od najnowszych: obowiazuje ostatnia przyjeta
    path = Path(filing.file_path)
    if not path.exists():
        return f"brak pliku przyjętej deklaracji za {_period(year, month)}: {path}"
    before = _facts(path.read_bytes()).totals
    kind = " (korekta)" if filing.purpose == 2 else ""
    filed = filing.submitted_at or filing.created_at
    return {
        "deklaracja": f"{_period(year, month)}{kind}, złożona {filed:%Y-%m-%d}",
        **{
            tag: with_change(Decimal(before[tag]), Decimal(now))
            for tag, now in facts.totals.items()
        },
    }


def _registry_note(facts: _JpkFacts) -> str | None:
    """Rozbieznosc kwot pliku z rejestrem, np. deklaracja zerowa mimo faktur za okres."""
    if facts.month is None:  # JPK_EWP: tylko porownanie z poprzednim rokiem
        return None
    s = VatLedger.load().settlement((facts.year, facts.month))
    expected = {"P_38": s.nalezny, "P_48": s.naliczony, "P_51": s.to_pay, "P_62": s.nadwyzka}
    diffs = [
        f"{tag} {facts.totals[tag]} zamiast {value}"
        for tag, value in expected.items()
        if Decimal(facts.totals[tag]) != value
    ]
    if not diffs:
        return None
    return (
        f"Kwoty w pliku różnią się od rejestru za {_period(facts.year, facts.month)}: "
        f"{', '.join(diffs)}. Przebuduj plik (`jdg jpk build`) albo uzupełnij rejestr."
    )


def _authorization() -> AuthorizationData:
    s, mf = settings.seller, settings.mf
    missing = [
        name
        for name, value in (
            ("MF_PESEL", mf.pesel),
            ("SELLER_NIP", s.nip),
            ("SELLER_FIRST_NAME", s.first_name),
            ("SELLER_LAST_NAME", s.last_name),
            ("SELLER_BIRTH_DATE", s.birth_date),
        )
        if not value
    ]
    if missing:
        raise ConfigMissingError(
            f"Brak danych autoryzujących bramki MF: {', '.join(missing)}",
            hint="Uzupełnij .env; MF_PRIOR_INCOME = przychód z PIT za rok N-2 (0 gdy brak).",
        )
    return AuthorizationData(
        nip=s.nip,
        pesel=mf.pesel,
        first_name=s.first_name,
        last_name=s.last_name,
        birth_date=date.fromisoformat(s.birth_date),
        prior_year_income=mf.prior_income,
    )


def _finalize(repo: FilingRepository, filing: Filing, result: SubmitResult) -> Filing:
    """Zapisz wynik statusu MF w `filings` (i UPO na dysk przy przyjeciu)."""
    if result.pending:
        return repo.update(filing.id, status="submitted", status_code=result.status_code)
    if result.success:
        upo_path = None
        if result.upo_base64 and filing.reference_number:
            path = DATA_DIR / "upo" / f"UPO_{filing.reference_number}.xml"
            MFGatewayClient.save_upo(result.upo_base64, path)
            upo_path = str(path)
        audit("jpk.accepted", filing.reference_number, "ok", {"form": filing.form})
        return repo.update(
            filing.id, status="accepted", status_code=result.status_code, upo_path=upo_path
        )
    audit("jpk.rejected", filing.reference_number, "error", {"error": result.error})
    return repo.update(
        filing.id, status="rejected", status_code=result.status_code, error=result.error
    )


def submit(
    path: Path, *, confirm: str | None = None, wait_seconds: int = STATUS_WAIT_DEFAULT
) -> FilingView:
    """Wyslij plik JPK do bramki MF — nieodwracalne, wymaga potwierdzenia."""
    check = validate_file(path)
    if not check.valid:
        raise InvalidInputError(
            f"{path.name} nie przechodzi walidacji XSD — bramka MF odrzuciłaby plik",
            details={"errors": check.errors},
        )
    xml = path.read_bytes()
    digest = sha256_hex(xml)
    facts = _facts(xml)
    repo = FilingRepository()
    env = settings.mf.env
    previous = [
        f for f in repo.list(form=facts.form, year=facts.year, month=facts.month) if f.env == env
    ]
    if any(f.sha256 == digest and f.status in ("submitted", "accepted") for f in previous):
        raise ConflictError(
            f"Ten plik ({path.name}) został już wysłany", hint="Sprawdź `jdg jpk status`."
        )
    if facts.purpose == 1 and any(f.status == "accepted" for f in previous):
        raise ConflictError(
            "Deklaracja za ten okres została już przyjęta przez MF",
            hint="Zbuduj korektę: `jdg jpk build ... --correction --reason ...`.",
        )
    auth = _authorization()

    note = _registry_note(facts)
    require_confirmation(
        action="jpk.submit",
        target=path.name,
        payload_digest=digest,
        env=env,
        summary={
            "formularz": facts.form,
            "okres": _period(facts.year, facts.month),
            "cel": "korekta" if facts.purpose == 2 else "złożenie",
            **facts.totals,
            "poprzednio": _compared(repo, facts, env),
            **({"uwaga": note} if note else {}),
            "plik": str(path),
        },
        confirm=confirm,
    )
    filing = repo.create(
        form=facts.form,
        year=facts.year,
        month=facts.month,
        purpose=facts.purpose,
        file_path=str(path),
        sha256=digest,
        env=env,
    )
    client = MFGatewayClient()
    uploaded = asyncio.run(client.upload(xml.decode("utf-8"), auth, xml_filename=path.name))
    if not uploaded.success or not uploaded.reference_number:
        repo.update(
            filing.id,
            status="error",
            error=uploaded.error,
            reference_number=uploaded.reference_number,
        )
        audit("jpk.submit", path.name, "error", {"env": env, "error": uploaded.error})
        raise ExternalServiceError(
            f"Wysyłka do bramki MF nie powiodła się: {uploaded.error}",
            details={"filing_id": filing.id},
        )
    filing = repo.update(filing.id, status="submitted", reference_number=uploaded.reference_number)
    audit("jpk.submit", path.name, "ok", {"env": env, "reference": uploaded.reference_number})
    result = asyncio.run(
        client.wait_for_status(uploaded.reference_number, timeout_sec=wait_seconds)
    )
    return FilingView.of(_finalize(repo, filing, result))


def status(
    *,
    reference: str | None = None,
    form: str | None = None,
    year: int | None = None,
    month: int | None = None,
    wait_seconds: int = 0,
) -> list[FilingView]:
    """Status zlozonych deklaracji; niezakonczone dopytuje w bramce MF."""
    repo = FilingRepository()
    if reference:
        found = repo.get_by_reference(reference)
        if found is None:
            raise NotFoundError(f"Brak deklaracji o numerze referencyjnym {reference}")
        filings = [found]
    else:
        filings = repo.list(form=form, year=year, month=month)
    client = MFGatewayClient()
    out = []
    for f in filings:
        if f.status == "submitted" and f.reference_number:
            result = asyncio.run(
                client.wait_for_status(f.reference_number, timeout_sec=wait_seconds)
                if wait_seconds
                else client.check_status(f.reference_number)
            )
            f = _finalize(repo, f, result)
        out.append(FilingView.of(f))
    return out
