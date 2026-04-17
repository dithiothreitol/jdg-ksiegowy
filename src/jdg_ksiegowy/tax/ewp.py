"""Generator JPK_EWP(4) — Ewidencja Przychodow ryczaltowca.

Schemat: JPK_EWP(4), TNS http://jpk.mf.gov.pl/wzor/2024/10/30/10301/
Obowiazuje: od 01.01.2026 dla podatnikow z miesiecznym JPK_V7M;
dla pozostalych od 01.01.2027. Pierwsze zlozenie 2026 -> do 30.04.2027.

Struktura wiersza EWP(4): K_1 (lp), K_2 (data wpisu), K_3 (data przychodu),
K_4 (nr dowodu), K_5 (NrKSeF), K_6 (kod kraju), K_7 (NIP kontrahenta),
K_8 (kwota), K_9 (stawka), K_10 (uwagi).

Zrodlo: https://www.gov.pl/attachment/67b55c59-e05c-42f0-be4c-28afcca460b6
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Invoice

TNS = "http://jpk.mf.gov.pl/wzor/2024/10/30/10301/"
ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {"tns": TNS, "etd": ETD, "xsi": XSI}

# TStawkaPodatku enumeration (z XSD JPK_EWP(4))
RYCZALT_STAWKI: frozenset[Decimal] = frozenset(
    Decimal(v) for v in ("17", "15", "14", "12.5", "12", "10", "8.5", "5.5", "3")
)


def _ns(tag: str) -> str:
    return f"{{{TNS}}}{tag}"


def _etd(tag: str) -> str:
    """Namespace etd (DefinicjeTypy MF) — uzywany dla pol identyfikacyjnych
    osoby fizycznej (NIP, imie, nazwisko, data urodzenia)."""
    return f"{{{ETD}}}{tag}"


def _stawka_str(rate: Decimal) -> str:
    """Stawka jako string bez zbednych zer (XSD: enumeration "17"|"15"|...|"12.5")."""
    normalized = rate.normalize()
    # Decimal("12.00").normalize() -> "1.2E+1"; przywroc do plain
    s = format(normalized, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def generate_jpk_ewp(
    invoices: list[Invoice],
    year: int,
    ryczalt_rate: Decimal | None = None,
    correction: int = 0,
) -> str:
    """Wygeneruj JPK_EWP(4) XML za rok podatkowy.

    Args:
        invoices: faktury sprzedazowe za caly rok
        year: rok podatkowy
        ryczalt_rate: stawka ryczaltu (domyslnie z settings.seller.ryczalt_rate)
        correction: 0 = pierwotny, 1+ = korekta
    """
    seller = settings.seller
    rate = ryczalt_rate if ryczalt_rate is not None else seller.ryczalt_rate
    if rate not in RYCZALT_STAWKI:
        raise ValueError(
            f"Stawka ryczaltu {rate}% nie jest w slowniku MF (dozwolone: {sorted(RYCZALT_STAWKI)})"
        )
    if not seller.first_name or not seller.last_name:
        raise ValueError("SELLER_FIRST_NAME i SELLER_LAST_NAME wymagane dla JPK_EWP")
    if not seller.tax_office_code:
        raise ValueError("SELLER_TAX_OFFICE_CODE wymagany dla JPK_EWP")

    now = datetime.now()
    root = etree.Element(_ns("JPK"), nsmap=NSMAP)

    # --- Naglowek (wg XSD: KodFormularza, WariantFormularza, CelZlozenia,
    # DataWytworzeniaJPK, DataOd, DataDo, KodUrzedu — w tej kolejnosci) ---
    naglowek = etree.SubElement(root, _ns("Naglowek"))
    kod = etree.SubElement(naglowek, _ns("KodFormularza"))
    kod.text = "JPK_EWP"
    kod.set("kodSystemowy", "JPK_EWP (4)")
    kod.set("wersjaSchemy", "1-0")
    etree.SubElement(naglowek, _ns("WariantFormularza")).text = "4"
    etree.SubElement(naglowek, _ns("CelZlozenia")).text = str(correction + 1)
    etree.SubElement(naglowek, _ns("DataWytworzeniaJPK")).text = now.isoformat()[:19]
    etree.SubElement(naglowek, _ns("DataOd")).text = date(year, 1, 1).isoformat()
    etree.SubElement(naglowek, _ns("DataDo")).text = date(year, 12, 31).isoformat()
    etree.SubElement(naglowek, _ns("KodUrzedu")).text = seller.tax_office_code

    # --- Podmiot1 (atrybut rola="Podatnik" wymagany przez XSD) ---
    podmiot = etree.SubElement(root, _ns("Podmiot1"), rola="Podatnik")
    osoba = etree.SubElement(podmiot, _ns("OsobaFizyczna"))
    # Pola identyfikacyjne idd z namespace etd (DefinicjeTypy)
    etree.SubElement(osoba, _etd("NIP")).text = seller.nip
    etree.SubElement(osoba, _etd("ImiePierwsze")).text = seller.first_name
    etree.SubElement(osoba, _etd("Nazwisko")).text = seller.last_name
    if seller.birth_date:
        etree.SubElement(osoba, _etd("DataUrodzenia")).text = seller.birth_date
    if seller.email:
        etree.SubElement(osoba, _ns("Email")).text = seller.email
    # Kasowy_PIT ma minOccurs=0 i enum=[1] (znacznik "tak"). Domyslnie pomijamy
    # (= podatnik nie rozlicza metoda kasowa)

    # --- EWPWiersze (per faktura) ---
    sorted_inv = sorted(invoices, key=lambda i: i.issue_date)
    total_revenue = Decimal("0")
    rate_str = _stawka_str(rate)

    for lp, inv in enumerate(sorted_inv, start=1):
        wiersz = etree.SubElement(root, _ns("EWPWiersz"))
        etree.SubElement(wiersz, _ns("K_1")).text = str(lp)
        etree.SubElement(wiersz, _ns("K_2")).text = inv.issue_date.isoformat()
        etree.SubElement(wiersz, _ns("K_3")).text = inv.sale_date.isoformat()
        etree.SubElement(wiersz, _ns("K_4")).text = inv.number
        if inv.ksef_reference:
            etree.SubElement(wiersz, _ns("K_5")).text = inv.ksef_reference
        etree.SubElement(wiersz, _ns("K_6")).text = inv.buyer.country_code
        etree.SubElement(wiersz, _ns("K_7")).text = inv.buyer.nip
        etree.SubElement(wiersz, _ns("K_8")).text = f"{inv.total_net:.2f}"
        etree.SubElement(wiersz, _ns("K_9")).text = rate_str
        total_revenue += inv.total_net

    # --- EWPCtrl ---
    ctrl = etree.SubElement(root, _ns("EWPCtrl"))
    etree.SubElement(ctrl, _ns("LiczbaWierszy")).text = str(len(sorted_inv))
    etree.SubElement(ctrl, _ns("SumaPrzychodow")).text = f"{total_revenue:.2f}"

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
    """Wygeneruj i zapisz JPK_EWP(4) do pliku."""
    xml = generate_jpk_ewp(invoices, year, ryczalt_rate, correction)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
