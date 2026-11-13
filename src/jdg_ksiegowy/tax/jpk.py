"""Generator JPK_V7M(3) — miesieczna deklaracja VAT z ewidencja.

Schemat: JPK_V7M(3), TNS http://crd.gov.pl/wzor/2025/12/19/14090/ (od 01.02.2026).
Kazdy wiersz ma oznaczenie NrKSeF / OFF / BFK / DI.

Jedna klasyfikacja pozycji (`classify_item`) zasila wiersze ewidencji (K_*) i pola
deklaracji (P_*), wiec ewidencja i deklaracja nie moga sie rozjechac.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Protocol

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Invoice, InvoiceKind, LineItem, is_article_100_service
from jdg_ksiegowy.tax.rounding import round_pln
from jdg_ksiegowy.validators import EU_COUNTRY_CODES

ZERO = Decimal("0")

TNS = "http://crd.gov.pl/wzor/2025/12/19/14090/"  # CRWDE 19.12.2025, od 01.02.2026
ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP = {"tns": TNS, "etd": ETD, "xsi": XSI}

# Stawka VAT -> (pole podstawy, pole podatku) w ewidencji sprzedazy
VAT_RATE_TO_K_FIELDS: dict[Decimal, tuple[str, str]] = {
    Decimal("23"): ("K_19", "K_20"),
    Decimal("22"): ("K_19", "K_20"),
    Decimal("8"): ("K_17", "K_18"),
    Decimal("7"): ("K_17", "K_18"),
    Decimal("5"): ("K_15", "K_16"),
}
# Kod pozycji (LineItem.vat_code) -> pole ewidencji sprzedazy bez podatku nalezenego
VAT_CODE_FIELD: dict[str, str] = {
    "ZW": "K_10",  # zwolnione
    "NP": "K_11",  # poza terytorium kraju (+ K_12 dla uslug art. 28b dla podatnika z UE)
    "0": "K_13",  # krajowe 0%
    "0_WDT": "K_21",  # wewnatrzwspolnotowa dostawa towarow
    "0_EXP": "K_22",  # eksport towarow
}
# Pola wiersza sprzedazy wypisywane zawsze (0.00 gdy nieaktywne) — jak w zlozonych plikach.
ALWAYS_SALES_FIELDS = ("K_10", "K_11", "K_12", "K_13", "K_14")
PAIR_FIELDS = ("K_15", "K_16", "K_17", "K_18", "K_19", "K_20")
MID_FIELDS = ("K_21", "K_22")
RC_FIELDS = ("K_27", "K_28", "K_29", "K_30")
POST_FIELDS = ("K_33", "K_34", "K_35", "K_36", "K_360")
# Podstawy wchodzace do P_37 (P_12 i P_14 to "w tym" — nie sumujemy) i podatki do P_38
BASE_FIELDS = ("10", "11", "13", "15", "17", "19", "21", "22", "27", "29")
TAX_FIELDS = ("16", "18", "20", "28", "30")


class SellerDataMissingError(ValueError):
    """Brak danych podatnika wymaganych w JPK (SELLER_* w .env)."""


def _is_eu(country_code: str | None) -> bool:
    """Import uslug (art. 28b): dostawca z UE -> K_29/K_30, spoza UE -> K_27/K_28."""
    return (country_code or "").upper() in EU_COUNTRY_CODES | {"PL"}


class ExpenseLike(Protocol):
    total_vat: Decimal
    vat_deduction_pct: Decimal
    reverse_charge: bool


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VatSettlement:
    """Rozliczenie VAT okresu — pola deklaracji w pelnych zlotych.

    Sumy powstaja z juz zaokraglonych pol, tak jak sprawdza je MF: P_38 = P_16 + P_18 + P_20
    + P_28 + P_30, P_48 = P_39 + P_43, P_51 = P_38 - P_48, P_53 = P_48 - P_38.
    """

    nalezny: Decimal  # P_38
    naliczony: Decimal  # P_48 (z przeniesiona nadwyzka P_39)
    to_pay: Decimal  # P_51
    nadwyzka: Decimal  # P_53 = P_62 (bez zwrotu na rachunek)
    carry_forward: Decimal = ZERO  # P_39
    purchases_vat: Decimal = ZERO  # P_43


def deductible_vat(expenses: Iterable[ExpenseLike]) -> Decimal:
    """VAT naliczony do odliczenia (w groszach): odliczenie czesciowe zaokraglane per faktura."""
    return sum(
        (
            _cents(_dec(e.total_vat) * _dec(e.vat_deduction_pct) / 100)
            for e in expenses
            if _dec(e.vat_deduction_pct) > 0
        ),
        ZERO,
    )


def settle_vat(
    fields: Mapping[str, Decimal], expenses: Iterable[ExpenseLike], carry_forward: Decimal = ZERO
) -> VatSettlement:
    """Pola P_38..P_62 z sum ewidencji (`period_fields`) i faktur zakupu okresu.

    Import uslug (odwrotne obciazenie) jest juz w `fields` jako VAT nalezny (K_28/K_30);
    po stronie zakupow odlicza sie tylko czesc podlegajaca odliczeniu.
    """
    nalezny = sum((round_pln(fields.get(f"K_{n}", ZERO)) for n in TAX_FIELDS), ZERO)
    p39 = round_pln(carry_forward)
    p43 = round_pln(deductible_vat(expenses))
    naliczony = p39 + p43
    return VatSettlement(
        nalezny=nalezny,
        naliczony=naliczony,
        to_pay=max(nalezny - naliczony, ZERO),
        nadwyzka=max(naliczony - nalezny, ZERO),
        carry_forward=p39,
        purchases_vat=p43,
    )


def classify_item(item: LineItem, buyer_country: str) -> dict[str, Decimal]:
    """Pola ewidencji sprzedazy (K_*) dla pozycji faktury."""
    code = (item.vat_code or "").upper()
    if code:
        field = VAT_CODE_FIELD.get(code)
        if field is None:
            raise ValueError(f"Nieobslugiwany kod VAT {item.vat_code!r} (znane: {VAT_CODE_FIELD})")
        out = {field: item.net_value}
        if code == "NP" and is_article_100_service(buyer_country):
            out["K_12"] = item.net_value  # uslugi art. 100 ust. 1 pkt 4 (VAT-UE), FA(3) "np II"
        return out
    if item.vat_rate not in VAT_RATE_TO_K_FIELDS:
        raise ValueError(
            f"Nieobslugiwana stawka VAT {item.vat_rate}% (dozwolone: "
            f"{sorted(VAT_RATE_TO_K_FIELDS)} albo kod {sorted(VAT_CODE_FIELD)})"
        )
    net_field, vat_field = VAT_RATE_TO_K_FIELDS[item.vat_rate]
    return {net_field: item.net_value, vat_field: item.vat_amount}


def invoice_fields(inv: Invoice) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for item in inv.items:
        for field, value in classify_item(item, inv.buyer.country_code).items():
            totals[field] += value
    return dict(totals)


def import_fields(exp: Expense) -> dict[str, Decimal]:
    """Import uslug: samonaliczony VAT nalezny po stronie sprzedazy."""
    net_f, vat_f = ("K_29", "K_30") if _is_eu(exp.seller_country) else ("K_27", "K_28")
    return {net_f: exp.total_net, vat_f: exp.total_vat}


def period_fields(invoices: Iterable[Invoice], expenses: Iterable[Expense]) -> dict[str, Decimal]:
    """Sumy pol K_* ewidencji sprzedazy okresu: faktury i import uslug (odwrotne obciazenie)."""
    rows = [invoice_fields(i) for i in invoices]
    rows += [import_fields(e) for e in expenses if e.reverse_charge]
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        for field, value in row.items():
            totals[field] += value
    return dict(totals)


def _ns(tag: str) -> str:
    return f"{{{TNS}}}{tag}"


def _etd(tag: str) -> str:
    return f"{{{ETD}}}{tag}"


def generate_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    correction: int = 0,
    expenses: list[Expense] | None = None,
    correction_reason: str | None = None,
    carry_forward: Decimal = ZERO,
) -> str:
    """JPK_V7M(3) za miesiac.

    Args:
        invoices: faktury sprzedazy okresu (VAT i korygujace).
        correction: 0 = zlozenie, >=1 = korekta (w XML zawsze CelZlozenia=2).
        expenses: faktury zakupu okresu (wg daty wplywu).
        correction_reason: uzasadnienie korekty (P_ORDZU).
        carry_forward: nadwyzka z poprzedniej deklaracji (P_39).
    """
    expenses = expenses or []
    seller = settings.seller
    _require_seller_fields(seller)

    sales_rows = [invoice_fields(inv) for inv in invoices]
    rc = [e for e in expenses if e.reverse_charge]
    rc_rows = [import_fields(e) for e in rc]
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO, period_fields(invoices, expenses))
    settlement = settle_vat(totals, expenses, carry_forward)
    deductible = [e for e in expenses if e.vat_deduction_pct > 0]
    purchases_net = sum((e.deductible_net for e in deductible), ZERO)

    root = etree.Element(_ns("JPK"), nsmap=NSMAP)
    _append_naglowek(root, seller, datetime.now(), month, year, correction)
    _append_podmiot(root, seller)

    deklaracja = etree.SubElement(root, _ns("Deklaracja"))
    nagl = etree.SubElement(deklaracja, _ns("Naglowek"))
    kod = etree.SubElement(nagl, _ns("KodFormularzaDekl"))
    kod.text = "VAT-7"
    kod.set("kodSystemowy", "VAT-7 (23)")
    kod.set("kodPodatku", "VAT")
    kod.set("rodzajZobowiazania", "Z")
    kod.set("wersjaSchemy", "1-0E")
    etree.SubElement(nagl, _ns("WariantFormularzaDekl")).text = "23"

    poz = etree.SubElement(deklaracja, _ns("PozycjeSzczegolowe"))
    # Pola deklaracji w kolejnosci XSD; TKwotaC = pelne zlote; zerowe opcjonalne pomijamy.
    for n in ("10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22",
              "27", "28", "29", "30"):  # fmt: skip
        if totals[f"K_{n}"]:
            _add_int(poz, f"P_{n}", totals[f"K_{n}"])
    # P_37 i P_38 to sumy juz zaokraglonych pol (kontrola logiczna MF)
    _add_int(poz, "P_37", sum((round_pln(totals[f"K_{n}"]) for n in BASE_FIELDS), ZERO))
    _add_int(poz, "P_38", settlement.nalezny)
    if settlement.carry_forward:
        _add_int(poz, "P_39", settlement.carry_forward)
    if deductible:
        _add_int(poz, "P_40", ZERO)  # nabycie srodkow trwalych — nieobslugiwane
        _add_int(poz, "P_41", ZERO)
        _add_int(poz, "P_42", purchases_net)
        _add_int(poz, "P_43", settlement.purchases_vat)
    _add_int(poz, "P_48", settlement.naliczony)
    _add_int(poz, "P_51", settlement.to_pay)
    if settlement.nadwyzka:
        _add_int(poz, "P_53", settlement.nadwyzka)
        _add_int(poz, "P_62", settlement.nadwyzka)  # bez zwrotu — cala nadwyzka przechodzi
    if correction_reason:
        etree.SubElement(poz, _ns("P_ORDZU")).text = correction_reason
    etree.SubElement(deklaracja, _ns("Pouczenia")).text = "1"

    ewidencja = etree.SubElement(root, _ns("Ewidencja"))
    lp = 0
    for lp, (inv, fields) in enumerate(zip(invoices, sales_rows, strict=True), start=1):
        _append_sprzedaz_wiersz(ewidencja, lp, inv, fields)
    for exp, fields in zip(rc, rc_rows, strict=True):
        lp += 1
        _append_import_uslug_wiersz(ewidencja, lp, exp, fields)
    ctrl = etree.SubElement(ewidencja, _ns("SprzedazCtrl"))
    etree.SubElement(ctrl, _ns("LiczbaWierszySprzedazy")).text = str(lp)
    # Sumy kontrolne ewidencji sa w groszach (suma pol wierszy), nie w pelnych zlotych.
    _add_decimal(ctrl, "PodatekNalezny", sum((totals[f"K_{n}"] for n in TAX_FIELDS), ZERO))

    for lp_zakupu, exp in enumerate(deductible, start=1):
        _append_zakup_wiersz(ewidencja, lp_zakupu, exp)
    ctrl_zak = etree.SubElement(ewidencja, _ns("ZakupCtrl"))
    etree.SubElement(ctrl_zak, _ns("LiczbaWierszyZakupow")).text = str(len(deductible))
    _add_decimal(ctrl_zak, "PodatekNaliczony", deductible_vat(deductible))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode(
        "utf-8"
    )


def _require_seller_fields(seller) -> None:
    if not seller.tax_office_code:
        raise SellerDataMissingError("SELLER_TAX_OFFICE_CODE wymagany (np. 1471)")
    if not seller.first_name or not seller.last_name:
        raise SellerDataMissingError("SELLER_FIRST_NAME i SELLER_LAST_NAME wymagane")
    if not seller.birth_date:
        raise SellerDataMissingError("SELLER_BIRTH_DATE wymagana (YYYY-MM-DD)")


def _append_naglowek(root, seller, now, month, year, correction) -> None:
    naglowek = etree.SubElement(root, _ns("Naglowek"))
    kod = etree.SubElement(naglowek, _ns("KodFormularza"))
    kod.text = "JPK_VAT"
    kod.set("kodSystemowy", "JPK_V7M (3)")
    kod.set("wersjaSchemy", "1-0E")
    etree.SubElement(naglowek, _ns("WariantFormularza")).text = "3"
    etree.SubElement(naglowek, _ns("DataWytworzeniaJPK")).text = now.isoformat()[:19]
    etree.SubElement(naglowek, _ns("NazwaSystemu")).text = "JDG-Ksiegowy/1.0"
    cel = etree.SubElement(naglowek, _ns("CelZlozenia"))
    cel.text = "2" if correction else "1"  # TCelZlozenia: 1 = zlozenie, 2 = korekta
    cel.set("poz", "P_7")
    etree.SubElement(naglowek, _ns("KodUrzedu")).text = seller.tax_office_code
    etree.SubElement(naglowek, _ns("Rok")).text = str(year)
    etree.SubElement(naglowek, _ns("Miesiac")).text = str(month)


def _append_podmiot(root, seller) -> None:
    podmiot = etree.SubElement(root, _ns("Podmiot1"), rola="Podatnik")
    osoba = etree.SubElement(podmiot, _ns("OsobaFizyczna"))
    etree.SubElement(osoba, _etd("NIP")).text = seller.nip
    etree.SubElement(osoba, _etd("ImiePierwsze")).text = seller.first_name
    etree.SubElement(osoba, _etd("Nazwisko")).text = seller.last_name
    etree.SubElement(osoba, _etd("DataUrodzenia")).text = seller.birth_date
    if seller.email:
        etree.SubElement(osoba, _ns("Email")).text = seller.email


def _append_ksef_marker(wiersz, ksef_number: str | None) -> None:
    """Wybor XSD NrKSeF | OFF | BFK | DI: z numerem KSeF — NrKSeF, bez — BFK."""
    if ksef_number:
        etree.SubElement(wiersz, _ns("NrKSeF")).text = ksef_number
    else:
        etree.SubElement(wiersz, _ns("BFK")).text = "1"


def _write_fields(wiersz, fields: dict[str, Decimal]) -> None:
    for f in ALWAYS_SALES_FIELDS:
        _add_decimal(wiersz, f, fields.get(f, ZERO))
    for f in PAIR_FIELDS:
        if f in fields:
            _add_decimal(wiersz, f, fields[f])
    for f in MID_FIELDS:
        _add_decimal(wiersz, f, fields.get(f, ZERO))
    for f in RC_FIELDS:
        if f in fields:
            _add_decimal(wiersz, f, fields[f])
    for f in POST_FIELDS:
        _add_decimal(wiersz, f, ZERO)


def _append_sprzedaz_wiersz(ewidencja, lp: int, inv: Invoice, fields: dict[str, Decimal]) -> None:
    wiersz = etree.SubElement(ewidencja, _ns("SprzedazWiersz"))
    etree.SubElement(wiersz, _ns("LpSprzedazy")).text = str(lp)
    etree.SubElement(wiersz, _ns("KodKrajuNadaniaTIN")).text = inv.buyer.country_code
    etree.SubElement(wiersz, _ns("NrKontrahenta")).text = inv.buyer.best_identifier()
    etree.SubElement(wiersz, _ns("NazwaKontrahenta")).text = inv.buyer.name
    etree.SubElement(wiersz, _ns("DowodSprzedazy")).text = inv.number
    etree.SubElement(wiersz, _ns("DataWystawienia")).text = inv.issue_date.isoformat()
    if inv.kind is InvoiceKind.VAT:
        etree.SubElement(wiersz, _ns("DataSprzedazy")).text = inv.sale_date.isoformat()
    _append_ksef_marker(wiersz, inv.ksef_number)
    for gtu in sorted({i.gtu for i in inv.items if i.gtu}):
        etree.SubElement(wiersz, _ns(gtu)).text = "1"
    _write_fields(wiersz, fields)


def _append_import_uslug_wiersz(
    ewidencja, lp: int, exp: Expense, fields: dict[str, Decimal]
) -> None:
    wiersz = etree.SubElement(ewidencja, _ns("SprzedazWiersz"))
    etree.SubElement(wiersz, _ns("LpSprzedazy")).text = str(lp)
    etree.SubElement(wiersz, _ns("KodKrajuNadaniaTIN")).text = exp.seller_country
    etree.SubElement(wiersz, _ns("NrKontrahenta")).text = exp.seller_nip or "BRAK"
    etree.SubElement(wiersz, _ns("NazwaKontrahenta")).text = exp.seller_name
    etree.SubElement(wiersz, _ns("DowodSprzedazy")).text = exp.document_number
    etree.SubElement(wiersz, _ns("DataWystawienia")).text = exp.issue_date.isoformat()
    etree.SubElement(wiersz, _ns("DataSprzedazy")).text = exp.issue_date.isoformat()
    _append_ksef_marker(wiersz, None)  # faktura zagraniczna — poza KSeF
    _write_fields(wiersz, fields)


def _append_zakup_wiersz(ewidencja, lp: int, exp: Expense) -> None:
    wiersz = etree.SubElement(ewidencja, _ns("ZakupWiersz"))
    etree.SubElement(wiersz, _ns("LpZakupu")).text = str(lp)
    etree.SubElement(wiersz, _ns("KodKrajuNadaniaTIN")).text = exp.seller_country
    etree.SubElement(wiersz, _ns("NrDostawcy")).text = exp.seller_nip or "BRAK"
    etree.SubElement(wiersz, _ns("NazwaDostawcy")).text = exp.seller_name
    etree.SubElement(wiersz, _ns("DowodZakupu")).text = exp.document_number
    etree.SubElement(wiersz, _ns("DataZakupu")).text = exp.issue_date.isoformat()
    etree.SubElement(wiersz, _ns("DataWplywu")).text = exp.receive_date.isoformat()
    _append_ksef_marker(wiersz, exp.ksef_number)
    # K_42/K_43 proporcjonalne do odliczenia (np. 50% dla auta uzywanego mieszanie).
    _add_decimal(wiersz, "K_42", exp.deductible_net)
    _add_decimal(wiersz, "K_43", exp.deductible_vat)
    for f in ("K_44", "K_45", "K_46", "K_47"):
        _add_decimal(wiersz, f, ZERO)


def _add_decimal(parent, tag: str, value: Decimal) -> None:
    """TKwotowy — kwota z groszami (wiersze ewidencji)."""
    etree.SubElement(parent, _ns(tag)).text = f"{value:.2f}"


def _add_int(parent, tag: str, value: Decimal) -> None:
    """TKwotaC — pelne zlote (pola deklaracji)."""
    etree.SubElement(parent, _ns(tag)).text = str(int(round_pln(value)))


def save_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    output_path: Path,
    correction: int = 0,
    expenses: list[Expense] | None = None,
    correction_reason: str | None = None,
    carry_forward: Decimal = ZERO,
) -> Path:
    xml = generate_jpk_v7m(
        invoices,
        month,
        year,
        correction,
        expenses=expenses,
        correction_reason=correction_reason,
        carry_forward=carry_forward,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
