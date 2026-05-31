"""Mapowanie metadanych faktur z KSeF -> rekord kosztu (ExpenseRecord).

Czysta logika domenowa: zero sieci, zero DB. Wejscie to surowy InvoiceMetadata
z ksef2; wyjscie to ExpenseRecord gotowy do save_expense().

Decyzje (patrz plan):
- receive_date = data przyjecia w KSeF (decyduje o miesiacu JPK_V7M),
- vat_deduction_pct = 100 domyslnie (NIE auto-50 dla paliwa — user dopytywany),
- vat_rate liczona z agregatow (informacyjna; JPK liczy z kwot, nie ze stawki).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from jdg_ksiegowy.expenses.models import ExpenseCategory
from jdg_ksiegowy.registry.db import ExpenseRecord

if TYPE_CHECKING:
    from ksef2.domain.models.invoices import InvoiceMetadata

# Stacje paliw -> kategoria PALIWO (heurystyka po nazwie sprzedawcy).
_FUEL_SELLERS = (
    "shell",
    "orlen",
    "bp ",
    "circle k",
    "circlek",
    "moya",
    "amic",
    "lotos",
    "petrolis",
)
# Typowe stawki VAT w PL — odchylenie sygnalizuje fakture wielostawkowa.
_KNOWN_VAT_RATES = {Decimal("0"), Decimal("5"), Decimal("8"), Decimal("23")}

_CENT = Decimal("0.01")


def _dec(value: float) -> Decimal:
    """float (agregaty z SDK) -> Decimal zaokraglony do groszy."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _infer_category(seller_name: str) -> ExpenseCategory:
    low = seller_name.casefold()
    if any(tag in low for tag in _FUEL_SELLERS):
        return ExpenseCategory.PALIWO
    return ExpenseCategory.INNE


def needs_manual_review(meta: InvoiceMetadata) -> str | None:
    """Powod, dla ktorego faktury NIE nalezy auto-zapisywac (albo None).

    Korekty (rezim okresu in minus), waluty obce (przeliczenie kursu) oraz
    samofakturowanie wymagaja swiadomej decyzji uzytkownika.
    """
    if meta.invoice_type.startswith("kor"):
        return "korekta (rezim okresu in minus — obsluz recznie)"
    if (meta.currency or "PLN") != "PLN":
        return f"waluta {meta.currency} (wymaga przeliczenia na PLN)"
    if meta.is_self_invoicing:
        return "samofakturowanie (czy to koszt?)"
    return None


def metadata_to_record(
    meta: InvoiceMetadata,
    *,
    xml_path: str | None = None,
    category: ExpenseCategory | None = None,
    vat_deduction_pct: Decimal = Decimal("100"),
) -> ExpenseRecord:
    """Zmapuj metadane faktury KSeF na ExpenseRecord (bez zapisu do DB)."""
    net = _dec(meta.net_amount)
    vat = _dec(meta.vat_amount)
    gross = _dec(meta.gross_amount)

    # Efektywna stawka z agregatow; guard na fakture zerowa (np. zaliczkowa 0 netto).
    vat_rate = (
        Decimal("0")
        if net == 0
        else (vat / net * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    cat = category if category is not None else _infer_category(meta.seller.name or "")
    seller_nip = meta.seller.nip or ""

    notes: list[str] = []
    if vat_rate not in _KNOWN_VAT_RATES:
        notes.append(f"multi-rate?: efektywna stawka {vat_rate}% — zweryfikuj XML")
    if cat in (ExpenseCategory.PALIWO, ExpenseCategory.SAMOCHOD) and vat_deduction_pct == Decimal(
        "100"
    ):
        notes.append("auto osobowe? rozwaz --vat-deduction-pct 50")

    # id wg konwencji add.py; fallback na ksef_number gdy sprzedawca bez NIP (zagraniczny).
    record_id = f"{seller_nip}-{meta.invoice_number}" if seller_nip else meta.ksef_number

    return ExpenseRecord(
        id=record_id,
        seller_name=meta.seller.name or "",
        seller_nip=seller_nip,
        seller_country="PL",
        document_number=meta.invoice_number,
        issue_date=meta.issue_date,
        receive_date=meta.acquisition_date.date(),  # wplyw do KSeF -> miesiac JPK
        description="",
        category=cat.value,
        total_net=net,
        total_vat=vat,
        total_gross=gross,
        vat_rate=vat_rate,
        vat_deduction_pct=vat_deduction_pct,
        file_path=xml_path,
        notes="; ".join(notes) or None,
        ksef_number=meta.ksef_number,
    )
