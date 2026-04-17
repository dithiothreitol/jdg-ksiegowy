"""Generator DRA (Deklaracja Rozliczeniowa) dla ZUS — format KEDU v5.05.

DRA to miesięczna deklaracja składana przez przedsiębiorcę do 20-go
następnego miesiąca. Dla JDG bez pracowników: składa tylko sam za siebie
(ubezpieczenie zdrowotne + ewentualnie społeczne).

Format XML: KEDU v5.05 obowiązujący od 2022-01-01.
XSD: https://www.zus.pl/firmy/kedu (do pobrania z portalu PUE ZUS)

UWAGA: PUE ZUS nie ma publicznego REST API dla automatycznego składania.
Generator wypluwa XML KEDU — import ręczny przez płatnika PUE lub Płatnik 10.

Dla JDG na ryczałcie zdrowotne 2026:
- próg I (przychód ≤ 60k rocznie): ok. 360 PLN/mies.
- próg II (60k–300k): ok. 600 PLN/mies.
- próg III (> 300k): ok. 1080 PLN/mies.
Źródło: jdg_ksiegowy.tax.zus.get_zus_tier()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.tax.zus import (
    ZUSSocialMode,
    get_current_social_mode,
    get_social_contribution,
    get_zus_tier,
)

KEDU_NS = "http://www.zus.pl/kedu_v5"
NSMAP = {None: KEDU_NS}


@dataclass(frozen=True)
class DRARequest:
    """Dane wejściowe dla DRA jednoosobowej (JDG bez pracowników)."""

    month: int
    year: int
    annual_prior_income: Decimal  # przychód z poprzedniego roku → próg zdrowotny
    include_social: bool = False  # czy naliczać składki społeczne (wg trybu z .env)
    social_mode: ZUSSocialMode | None = None  # override trybu społecznych
    voluntary_sickness: bool = False  # dobrowolna chorobowa


@dataclass(frozen=True)
class DRAResult:
    xml: str
    health_contribution: Decimal
    social_contribution: Decimal
    total: Decimal


def _ns(tag: str) -> str:
    return f"{{{KEDU_NS}}}{tag}"


def _mode_from_settings_override(raw: str) -> ZUSSocialMode | None:
    """Zamien wartosc z .env (np. 'auto', 'full') na ZUSSocialMode lub None dla auto."""
    if not raw or raw == "auto":
        return None
    return ZUSSocialMode(raw)


def _el(parent, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, _ns(tag) if parent is not None and parent.tag != tag else tag)
    if text is not None:
        el.text = text
    return el


def generate_dra_xml(req: DRARequest) -> DRAResult:
    """Wygeneruj XML KEDU dla DRA miesięcznej.

    Zwraca obiekt z XML + kwotami składek. Użytkownik importuje XML przez PUE ZUS.
    """
    seller = settings.seller
    tier = get_zus_tier(req.annual_prior_income)
    health = tier.monthly_contribution

    if req.include_social:
        override = req.social_mode or _mode_from_settings_override(seller.zus_social_mode)
        biz_start = date.fromisoformat(seller.business_start_date) if seller.business_start_date else None
        mode = get_current_social_mode(
            today=date(req.year, req.month, 1),
            business_start=biz_start,
            employment_above_min=seller.employment_gross_above_min,
            override=override,
        )
        sickness = req.voluntary_sickness or seller.zus_voluntary_sickness
        social = get_social_contribution(mode, voluntary_sickness=sickness)
    else:
        social = Decimal("0")
    total = health + social

    root = etree.Element(_ns("KEDU"), nsmap=NSMAP)
    naglowek = etree.SubElement(root, _ns("naglowek"))
    etree.SubElement(naglowek, _ns("typ_dokumentu")).text = "DRA"
    etree.SubElement(naglowek, _ns("wersja_schematu")).text = "5.05"
    etree.SubElement(naglowek, _ns("data_wytworzenia")).text = datetime.now().isoformat(timespec="seconds")

    # DRA: pozycje
    dra = etree.SubElement(root, _ns("DRA"))
    nagl_dra = etree.SubElement(dra, _ns("naglowek_DRA"))
    etree.SubElement(nagl_dra, _ns("identyfikator")).text = f"01.{req.month:02d}.{req.year}"
    etree.SubElement(nagl_dra, _ns("okres_od")).text = f"{req.year}-{req.month:02d}-01"

    # Dane płatnika
    platnik = etree.SubElement(dra, _ns("platnik"))
    etree.SubElement(platnik, _ns("NIP")).text = seller.nip
    etree.SubElement(platnik, _ns("nazwa")).text = seller.name

    # Składki
    skladki = etree.SubElement(dra, _ns("skladki"))
    skl_zdrow = etree.SubElement(skladki, _ns("zdrowotne"))
    etree.SubElement(skl_zdrow, _ns("podstawa")).text = f"{tier.monthly_basis:.2f}"
    etree.SubElement(skl_zdrow, _ns("kwota")).text = f"{health:.2f}"
    if req.include_social:
        skl_spol = etree.SubElement(skladki, _ns("spoleczne"))
        etree.SubElement(skl_spol, _ns("kwota")).text = f"{social:.2f}"
    etree.SubElement(skladki, _ns("razem")).text = f"{total:.2f}"

    xml = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    ).decode("utf-8")

    return DRAResult(
        xml=xml, health_contribution=health,
        social_contribution=social, total=total,
    )


def dra_deadline(month: int, year: int) -> date:
    """Termin płatności/złożenia DRA: do 20-tego następnego miesiąca."""
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    return date(next_y, next_m, 20)
