"""Generator JPK_EWP — Ewidencja Przychodow ryczaltowca.

Schemat: JPK_EWP(4) (od 1.01.2026, dodano stawki 12% i 14%).
Wysylka: roczna do 30.04 nastepnego roku, kanalem REST jak JPK_V7M
(e-dokumenty.mf.gov.pl).

Zrodlo: gov.pl/web/kas/struktury-jpk-w-podatkach-dochodowych
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Invoice

# Namespaces JPK_EWP — do potwierdzenia po pobraniu XSD od MF (struktura analogiczna do JPK_V7M)
TNS = "http://crd.gov.pl/wzor/2025/12/15/12999/"  # placeholder do potwierdzenia
ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2021/06/08/eD/DefinicjeTypy/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {"tns": TNS, "etd": ETD, "xsi": XSI}

# Stawki ryczaltu wg rozporzadzenia (slownik MF dla JPK_EWP) -> (kod_pola, label).
# Pole zachowuje surowa stawke jako string z kropka dziesietna.
RYCZALT_STAWKI: list[Decimal] = [
    Decimal("17"),
    Decimal("15"),
    Decimal("14"),
    Decimal("12.5"),
    Decimal("12"),
    Decimal("10"),
    Decimal("8.5"),
    Decimal("5.5"),
    Decimal("3"),
]


def generate_jpk_ewp(
    invoices: list[Invoice],
    year: int,
    ryczalt_rate: Decimal | None = None,
    correction: int = 0,
) -> str:
    """Wygeneruj JPK_EWP XML za caly rok podatkowy.

    Args:
        invoices: faktury sprzedazowe za rok (na ryczalcie wszystkie idą do EWP)
        year: rok podatkowy
        ryczalt_rate: stawka ryczaltu (domyslnie z settings.seller.ryczalt_rate)
        correction: 0 = pierwotny, 1+ = korekta
    """
    seller = settings.seller
    rate = ryczalt_rate or seller.ryczalt_rate
    if rate not in RYCZALT_STAWKI:
        raise ValueError(
            f"Stawka ryczaltu {rate}% nie jest w slowniku MF "
            f"(dozwolone: {sorted(RYCZALT_STAWKI)})"
        )
    if not seller.first_name or not seller.last_name:
        raise ValueError("SELLER_FIRST_NAME i SELLER_LAST_NAME wymagane dla JPK_EWP")

    now = datetime.now()
    root = etree.Element("{%s}JPK" % TNS, nsmap=NSMAP)

    # --- Naglowek ---
    naglowek = etree.SubElement(root, "{%s}Naglowek" % TNS)
    kod = etree.SubElement(naglowek, "{%s}KodFormularza" % TNS)
    kod.text = "JPK_EWP"
    kod.set("kodSystemowy", "JPK_EWP (4)")
    kod.set("wersjaSchemy", "1-0E")

    etree.SubElement(naglowek, "{%s}WariantFormularza" % TNS).text = "4"
    etree.SubElement(naglowek, "{%s}DataWytworzeniaJPK" % TNS).text = now.isoformat()[:19]
    etree.SubElement(naglowek, "{%s}NazwaSystemu" % TNS).text = "JDG-Ksiegowy/1.0"

    cel = etree.SubElement(naglowek, "{%s}CelZlozenia" % TNS)
    cel.text = str(correction + 1)
    cel.set("poz", "P_7")

    if not seller.tax_office_code:
        raise ValueError("SELLER_TAX_OFFICE_CODE wymagany dla JPK_EWP")
    etree.SubElement(naglowek, "{%s}KodUrzedu" % TNS).text = seller.tax_office_code
    etree.SubElement(naglowek, "{%s}DataOd" % TNS).text = date(year, 1, 1).isoformat()
    etree.SubElement(naglowek, "{%s}DataDo" % TNS).text = date(year, 12, 31).isoformat()

    # --- Podmiot1 (osoba fizyczna) ---
    podmiot = etree.SubElement(root, "{%s}Podmiot1" % TNS)
    osoba = etree.SubElement(podmiot, "{%s}OsobaFizyczna" % TNS)
    etree.SubElement(osoba, "{%s}NIP" % TNS).text = seller.nip
    etree.SubElement(osoba, "{%s}ImiePierwsze" % TNS).text = seller.first_name
    etree.SubElement(osoba, "{%s}Nazwisko" % TNS).text = seller.last_name
    if seller.birth_date:
        etree.SubElement(osoba, "{%s}DataUrodzenia" % TNS).text = seller.birth_date

    # --- Wiersze ewidencji ---
    sorted_inv = sorted(invoices, key=lambda i: i.issue_date)
    total_revenue = Decimal("0")

    for lp, inv in enumerate(sorted_inv, start=1):
        wiersz = etree.SubElement(root, "{%s}EWPWiersz" % TNS)
        etree.SubElement(wiersz, "{%s}LpEWPWiersza" % TNS).text = str(lp)
        etree.SubElement(wiersz, "{%s}DataWpisu" % TNS).text = inv.issue_date.isoformat()
        etree.SubElement(wiersz, "{%s}DataUzyskaniaPrzychodu" % TNS).text = inv.sale_date.isoformat()
        etree.SubElement(wiersz, "{%s}NrDowoduKsiegowego" % TNS).text = inv.number
        etree.SubElement(wiersz, "{%s}OpisZdarzenia" % TNS).text = (
            inv.items[0].description if inv.items else "Sprzedaz"
        )
        # Pole dla stawki (struktura placeholder — do potwierdzenia po publikacji XSD JPK_EWP(4))
        etree.SubElement(wiersz, "{%s}Stawka" % TNS).text = str(rate)
        # Przychod opodatkowany dana stawka (na ryczalcie = total_net = total_gross gdy zwolniony z VAT,
        # lub total_net gdy VAT-owiec).
        kwota = inv.total_net
        etree.SubElement(wiersz, "{%s}KwotaPrzychodu" % TNS).text = f"{kwota:.2f}"
        total_revenue += kwota

    # --- Podsumowanie kontrolne ---
    ctrl = etree.SubElement(root, "{%s}EWPCtrl" % TNS)
    etree.SubElement(ctrl, "{%s}LiczbaWierszyEWP" % TNS).text = str(len(sorted_inv))
    etree.SubElement(ctrl, "{%s}SumaPrzychodow" % TNS).text = f"{total_revenue:.2f}"

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    ).decode("utf-8")


def save_jpk_ewp(
    invoices: list[Invoice],
    year: int,
    output_path: Path,
    ryczalt_rate: Decimal | None = None,
    correction: int = 0,
) -> Path:
    """Wygeneruj i zapisz JPK_EWP do pliku."""
    xml = generate_jpk_ewp(invoices, year, ryczalt_rate, correction)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
