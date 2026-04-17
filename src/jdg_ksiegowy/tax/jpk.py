"""Generator JPK_V7M(3) — miesieczna deklaracja VAT z ewidencja.

Schemat: JPK_V7M(3), TNS http://crd.gov.pl/wzor/2025/06/18/06181/
Obowiazuje od 01.02.2026 (dopasowanie do KSeF 2.0). Dodaje oznaczenia
NrKSeF/OFF/BFK/DI (exclusive choice) na kazdy wiersz sprzedazy.

Zrodlo XSD: https://www.podatki.gov.pl/media/qord0r0j/schemat_jpk_v7m-3-_v1-0e.xsd
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Invoice

TNS = "http://crd.gov.pl/wzor/2025/12/19/14090/"  # CRWDE 19.12.2025, obowiązuje od 01.02.2026
ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {"tns": TNS, "etd": ETD, "xsi": XSI}

# Stawka VAT -> (pole podstawy, pole podatku). None = brak pola podatku.
VAT_RATE_TO_K_FIELDS: dict[Decimal, tuple[str, str | None]] = {
    Decimal("23"): ("K_19", "K_20"),
    Decimal("22"): ("K_19", "K_20"),
    Decimal("8"): ("K_17", "K_18"),
    Decimal("7"): ("K_17", "K_18"),
    Decimal("5"): ("K_15", "K_16"),
}

# Kody VAT które idą do K_11 (poza terytorium kraju / art. 28b)
# zamiast do standardowych par stawek
VAT_CODE_K11 = {"NP"}
# Kody VAT które idą do K_13 (dostawy 0% wewnątrzwspólnotowe)
VAT_CODE_K13 = {"0_WDT", "0"}
# Kody VAT dla eksportu towarów K_14
VAT_CODE_K14 = {"0_EXP"}

# Pary stawek w kolejnosci wymaganej przez XSD: K_15/K_16, K_17/K_18, K_19/K_20.
RATE_PAIRS_ORDER = [
    (Decimal("5"), "K_15", "K_16"),
    (Decimal("8"), "K_17", "K_18"),
    (Decimal("23"), "K_19", "K_20"),
]

# Pola wiersza sprzedazy przed parami stawek (zawsze "0.00" gdy nieaktywne).
PRE_RATE_FIELDS = ["K_10", "K_11", "K_12", "K_13", "K_14"]
# Pola miedzy parami stawek a dalszymi parami (K_23-K_32).
MID_FIELDS = ["K_21", "K_22"]
# Pola po parach stawek (zawsze "0.00" gdy nieaktywne).
POST_RATE_FIELDS = ["K_33", "K_34", "K_35", "K_36", "K_360"]


def _ns(tag: str) -> str:
    return f"{{{TNS}}}{tag}"


def _etd(tag: str) -> str:
    """Namespace etd (DefinicjeTypy MF) — pola identyfikacyjne osoby fizycznej."""
    return f"{{{ETD}}}{tag}"


def generate_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    correction: int = 0,
    expenses: list[Expense] | None = None,
) -> str:
    """Wygeneruj JPK_V7M(3) XML za dany miesiac.

    Args:
        invoices: Faktury sprzedazowe za miesiac
        month: 1-12
        year: Rok
        correction: 0 = pierwotny, 1+ = korekta
        expenses: Faktury zakupu (koszty). VAT naliczony idzie do odliczenia.
    """
    expenses = expenses or []
    seller = settings.seller
    now = datetime.now()

    _require_seller_fields(seller)

    root = etree.Element(_ns("JPK"), nsmap=NSMAP)

    _append_naglowek(root, seller, now, month, year, correction)
    _append_podmiot(root, seller)

    # --- Deklaracja ---
    deklaracja = etree.SubElement(root, _ns("Deklaracja"))
    nagl_dek = etree.SubElement(deklaracja, _ns("Naglowek"))
    kod_dek = etree.SubElement(nagl_dek, _ns("KodFormularzaDekl"))
    kod_dek.text = "VAT-7"
    kod_dek.set("kodSystemowy", "VAT-7 (23)")
    kod_dek.set("kodPodatku", "VAT")
    kod_dek.set("rodzajZobowiazania", "Z")
    kod_dek.set("wersjaSchemy", "1-0E")
    etree.SubElement(nagl_dek, _ns("WariantFormularzaDekl")).text = "23"

    poz = etree.SubElement(deklaracja, _ns("PozycjeSzczegolowe"))

    total_net = sum((inv.total_net for inv in invoices), Decimal("0"))
    total_vat = sum((inv.total_vat for inv in invoices), Decimal("0"))
    deductible = [e for e in expenses if e.vat_deductible]
    exp_net = sum((e.total_net for e in deductible), Decimal("0"))
    exp_vat = sum((e.total_vat for e in deductible), Decimal("0"))
    vat_to_pay = max(total_vat - exp_vat, Decimal("0"))

    # Pozycje deklaracji VAT-7(23) — typ TKwotaC: integer (pelne zlote)
    # Kolejnosc i grupowanie wg XSD JPK_V7M(3). Pola w sekwencjach min=0
    # musza isc razem (P_40+P_41 jedna grupa, P_42+P_43 druga, itd.)
    _add_int(poz, "P_10", total_net)  # dostawa krajowa, opt
    _add_int(poz, "P_38", total_net)  # razem podstawa, REQ
    _add_int(poz, "P_39", total_vat)  # razem VAT nalezny
    if deductible:
        _add_int(poz, "P_40", Decimal("0"))  # nabycia ST netto
        _add_int(poz, "P_41", exp_net)  # nabycia inne netto
        _add_int(poz, "P_42", Decimal("0"))  # VAT od nabyc ST
        _add_int(poz, "P_43", exp_vat)  # VAT od nabyc innych
    _add_int(poz, "P_51", vat_to_pay)  # do zaplaty, REQ

    etree.SubElement(deklaracja, _ns("Pouczenia")).text = "1"

    # --- Ewidencja ---
    ewidencja = etree.SubElement(root, _ns("Ewidencja"))
    for lp, inv in enumerate(invoices, start=1):
        _append_sprzedaz_wiersz(ewidencja, lp, inv)

    ctrl_sprz = etree.SubElement(ewidencja, _ns("SprzedazCtrl"))
    etree.SubElement(ctrl_sprz, _ns("LiczbaWierszySprzedazy")).text = str(len(invoices))
    _add_decimal(ctrl_sprz, "PodatekNalezny", total_vat)

    for lp, exp in enumerate(deductible, start=1):
        _append_zakup_wiersz(ewidencja, lp, exp)

    ctrl_zak = etree.SubElement(ewidencja, _ns("ZakupCtrl"))
    etree.SubElement(ctrl_zak, _ns("LiczbaWierszyZakupow")).text = str(len(deductible))
    _add_decimal(ctrl_zak, "PodatekNaliczony", exp_vat)

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    ).decode("utf-8")


def _require_seller_fields(seller) -> None:
    if not seller.tax_office_code:
        raise ValueError("SELLER_TAX_OFFICE_CODE wymagany (np. 1471)")
    if not seller.first_name or not seller.last_name:
        raise ValueError("SELLER_FIRST_NAME i SELLER_LAST_NAME wymagane")
    if not seller.birth_date:
        raise ValueError("SELLER_BIRTH_DATE wymagana (YYYY-MM-DD)")


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
    cel.text = str(correction + 1)
    cel.set("poz", "P_7")

    etree.SubElement(naglowek, _ns("KodUrzedu")).text = seller.tax_office_code
    etree.SubElement(naglowek, _ns("Rok")).text = str(year)
    etree.SubElement(naglowek, _ns("Miesiac")).text = str(month)


def _append_podmiot(root, seller) -> None:
    podmiot = etree.SubElement(root, _ns("Podmiot1"), rola="Podatnik")
    osoba = etree.SubElement(podmiot, _ns("OsobaFizyczna"))
    # Pola identyfikacyjne idd z namespace etd (DefinicjeTypy)
    etree.SubElement(osoba, _etd("NIP")).text = seller.nip
    etree.SubElement(osoba, _etd("ImiePierwsze")).text = seller.first_name
    etree.SubElement(osoba, _etd("Nazwisko")).text = seller.last_name
    etree.SubElement(osoba, _etd("DataUrodzenia")).text = seller.birth_date
    if seller.email:
        etree.SubElement(osoba, _ns("Email")).text = seller.email


def _append_sprzedaz_wiersz(ewidencja, lp: int, inv: Invoice) -> None:
    wiersz = etree.SubElement(ewidencja, _ns("SprzedazWiersz"))
    etree.SubElement(wiersz, _ns("LpSprzedazy")).text = str(lp)
    etree.SubElement(wiersz, _ns("KodKrajuNadaniaTIN")).text = inv.buyer.country_code
    etree.SubElement(wiersz, _ns("NrKontrahenta")).text = inv.buyer.best_identifier()
    etree.SubElement(wiersz, _ns("NazwaKontrahenta")).text = inv.buyer.name
    etree.SubElement(wiersz, _ns("DowodSprzedazy")).text = inv.number
    etree.SubElement(wiersz, _ns("DataWystawienia")).text = inv.issue_date.isoformat()
    etree.SubElement(wiersz, _ns("DataSprzedazy")).text = inv.sale_date.isoformat()

    # Choice: NrKSeF | OFF | BFK | DI (dokladnie jedno)
    if inv.ksef_reference:
        etree.SubElement(wiersz, _ns("NrKSeF")).text = inv.ksef_reference
    else:
        etree.SubElement(wiersz, _ns("BFK")).text = "1"

    # Oblicz sumy wg kodu VAT pozycji
    k11_net = Decimal("0")  # poza terytorium (art. 28b / NP)
    k13_net = Decimal("0")  # WDT / 0%
    k14_net = Decimal("0")  # eksport towarów
    domestic_buckets: dict[Decimal, tuple[Decimal, Decimal]] = {}

    for item in inv.items:
        code = item.vat_code
        net, vat_a = item.net_value, item.vat_amount
        if code in VAT_CODE_K11:
            k11_net += net
        elif code in VAT_CODE_K14:
            k14_net += net
        elif code in VAT_CODE_K13:
            k13_net += net
        else:
            if item.vat_rate not in VAT_RATE_TO_K_FIELDS:
                raise ValueError(
                    f"Faktura {inv.number}: nieobslugiwana stawka VAT {item.vat_rate}% "
                    f"(dozwolone: {sorted(VAT_RATE_TO_K_FIELDS.keys())} lub kod NP/0_WDT/0_EXP)"
                )
            n, v = domestic_buckets.get(item.vat_rate, (Decimal("0"), Decimal("0")))
            domestic_buckets[item.vat_rate] = (n + net, v + vat_a)

    # K_10-K_14 w kolejnosci XSD
    _add_decimal(wiersz, "K_10", Decimal("0"))
    _add_decimal(wiersz, "K_11", k11_net)
    _add_decimal(wiersz, "K_12", Decimal("0"))
    _add_decimal(wiersz, "K_13", k13_net)
    _add_decimal(wiersz, "K_14", k14_net)

    # Pary K_15/K_16 (5%), K_17/K_18 (8%), K_19/K_20 (23%)
    for rate_key, net_field, vat_field in RATE_PAIRS_ORDER:
        rates_matching = [r for r in domestic_buckets if VAT_RATE_TO_K_FIELDS[r][0] == net_field]
        if not rates_matching:
            continue
        net_sum = sum((domestic_buckets[r][0] for r in rates_matching), Decimal("0"))
        vat_sum = sum((domestic_buckets[r][1] for r in rates_matching), Decimal("0"))
        _add_decimal(wiersz, net_field, net_sum)
        _add_decimal(wiersz, vat_field, vat_sum)

    # K_21, K_22 (wewnatrzwspolnotowe dostawy)
    for f in MID_FIELDS:
        _add_decimal(wiersz, f, Decimal("0"))

    # K_33-K_36, K_360 (korekty VAT)
    for f in POST_RATE_FIELDS:
        _add_decimal(wiersz, f, Decimal("0"))


def _append_zakup_wiersz(ewidencja, lp: int, exp: Expense) -> None:
    wiersz = etree.SubElement(ewidencja, _ns("ZakupWiersz"))
    etree.SubElement(wiersz, _ns("LpZakupu")).text = str(lp)
    etree.SubElement(wiersz, _ns("KodKrajuNadaniaTIN")).text = exp.seller_country
    etree.SubElement(wiersz, _ns("NrDostawcy")).text = exp.seller_nip
    etree.SubElement(wiersz, _ns("NazwaDostawcy")).text = exp.seller_name
    etree.SubElement(wiersz, _ns("DowodZakupu")).text = exp.document_number
    etree.SubElement(wiersz, _ns("DataZakupu")).text = exp.issue_date.isoformat()
    etree.SubElement(wiersz, _ns("DataWplywu")).text = exp.receive_date.isoformat()

    # Choice: NrKSeF | OFF | BFK | DI (faktura papierowa/elektroniczna -> BFK)
    etree.SubElement(wiersz, _ns("BFK")).text = "1"

    # K_42/K_43: nabycia krajowe inne niz ST (netto + VAT)
    _add_decimal(wiersz, "K_42", exp.total_net)
    _add_decimal(wiersz, "K_43", exp.total_vat)

    # K_44-K_47: korekty VAT naliczonego — zawsze wymagane (0.00 gdy brak)
    for f in ("K_44", "K_45", "K_46", "K_47"):
        _add_decimal(wiersz, f, Decimal("0"))


def _add_decimal(parent, tag: str, value: Decimal) -> None:
    """Kwota z groszami (TKwotowy) — uzywane w wierszach ewidencji K_*."""
    etree.SubElement(parent, _ns(tag)).text = f"{value:.2f}"


def _add_int(parent, tag: str, value: Decimal) -> None:
    """Kwota w pelnych zlotych (TKwotaC) — uzywane w deklaracji P_*.
    Zaokraglenie: pol w gore."""
    rounded = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    etree.SubElement(parent, _ns(tag)).text = str(rounded)


def save_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    output_path: Path,
    correction: int = 0,
    expenses: list[Expense] | None = None,
) -> Path:
    """Wygeneruj i zapisz JPK_V7M(3) do pliku."""
    xml = generate_jpk_v7m(invoices, month, year, correction, expenses=expenses)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
