"""Generator JPK_V7M (Jednolity Plik Kontrolny — deklaracja VAT).

Struktura: JPK_V7M(2) — miesięczna deklaracja VAT z ewidencją.
Źródło schematów: https://jpk.info.pl/wysylka-jpk/struktura-xml-plikow-jpk/
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.expenses.models import Expense
from jdg_ksiegowy.invoice.models import Invoice

# Namespaces JPK_V7M
TNS = "http://crd.gov.pl/wzor/2021/12/27/11148/"
ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2021/06/08/eD/DefinicjeTypy/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    "tns": TNS,
    "etd": ETD,
    "xsi": XSI,
}

# Mapowanie stawki VAT -> (pole podstawy K_, pole podatku K_) w SprzedazWiersz JPK_V7M(2).
# Brak K_ dla podatku przy stawkach 0% i zwolnionych (tylko podstawa).
VAT_RATE_TO_K_FIELDS: dict[Decimal, tuple[str, str | None]] = {
    Decimal("23"): ("K_19", "K_20"),
    Decimal("22"): ("K_19", "K_20"),
    Decimal("8"): ("K_17", "K_18"),
    Decimal("7"): ("K_17", "K_18"),
    Decimal("5"): ("K_15", "K_16"),
    Decimal("0"): ("K_13", None),
}


def generate_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    correction: int = 0,
    expenses: list[Expense] | None = None,
) -> str:
    """Wygeneruj JPK_V7M XML za dany miesiąc.

    Args:
        invoices: Lista faktur sprzedażowych za dany miesiąc
        month: Miesiąc (1-12)
        year: Rok
        correction: 0 = pierwotny, 1+ = korekta
        expenses: Lista faktur zakupu (kosztow). VAT naliczony idzie do odliczenia.

    Returns:
        XML string gotowy do wysyłki
    """
    if expenses is None:
        expenses = []
    seller = settings.seller
    now = datetime.now()

    root = etree.Element("{%s}JPK" % TNS, nsmap=NSMAP)

    # --- Nagłówek ---
    naglowek = etree.SubElement(root, "{%s}Naglowek" % TNS)

    kod = etree.SubElement(naglowek, "{%s}KodFormularza" % TNS)
    kod.text = "JPK_VAT"
    kod.set("kodSystemowy", "JPK_V7M (2)")
    kod.set("wersjaSchemy", "1-0E")

    etree.SubElement(naglowek, "{%s}WariantFormularza" % TNS).text = "2"
    etree.SubElement(naglowek, "{%s}DataWytworzeniaJPK" % TNS).text = now.isoformat()[:19]
    etree.SubElement(naglowek, "{%s}NazwaSystemu" % TNS).text = "JDG-Ksiegowy/1.0"

    cel = etree.SubElement(naglowek, "{%s}CelZlozenia" % TNS)
    cel.text = str(correction + 1)  # 1 = złożenie, 2+ = korekta
    cel.set("poz", "P_7")

    if not seller.tax_office_code:
        raise ValueError("SELLER_TAX_OFFICE_CODE wymagany do generowania JPK (np. 1471)")
    etree.SubElement(naglowek, "{%s}KodUrzedu" % TNS).text = seller.tax_office_code
    etree.SubElement(naglowek, "{%s}Rok" % TNS).text = str(year)
    etree.SubElement(naglowek, "{%s}Miesiac" % TNS).text = str(month)

    # --- Podmiot (podatnik) ---
    podmiot = etree.SubElement(root, "{%s}Podmiot1" % TNS)
    osoba = etree.SubElement(podmiot, "{%s}OsobaFizyczna" % TNS)

    if not seller.first_name or not seller.last_name:
        raise ValueError("SELLER_FIRST_NAME i SELLER_LAST_NAME wymagane do generowania JPK")
    if not seller.birth_date:
        raise ValueError("SELLER_BIRTH_DATE wymagana do generowania JPK (format: YYYY-MM-DD)")

    etree.SubElement(osoba, "{%s}NIP" % TNS).text = seller.nip
    etree.SubElement(osoba, "{%s}ImiePierwsze" % TNS).text = seller.first_name
    etree.SubElement(osoba, "{%s}Nazwisko" % TNS).text = seller.last_name
    etree.SubElement(osoba, "{%s}DataUrodzenia" % TNS).text = seller.birth_date
    etree.SubElement(osoba, "{%s}Email" % TNS).text = seller.email

    # --- Deklaracja (podsumowanie) ---
    deklaracja = etree.SubElement(root, "{%s}Deklaracja" % TNS)
    nagl_dek = etree.SubElement(deklaracja, "{%s}Naglowek" % TNS)
    etree.SubElement(nagl_dek, "{%s}KodFormularzaDek" % TNS).text = "VAT-7"
    etree.SubElement(nagl_dek, "{%s}WariantFormularzaDek" % TNS).text = "22"

    poz = etree.SubElement(deklaracja, "{%s}PozycjeSzczegolowe" % TNS)

    # Oblicz sumy (Decimal-safe, dziala przy pustej liscie)
    total_net = sum((inv.total_net for inv in invoices), Decimal("0"))
    total_vat = sum((inv.total_vat for inv in invoices), Decimal("0"))

    # Sumy zakupow z odliczalnym VAT (np. paliwo do auta osobowego ma vat_deductible=False)
    deductible = [e for e in expenses if e.vat_deductible]
    total_exp_net = sum((e.total_net for e in deductible), Decimal("0"))
    total_exp_vat = sum((e.total_vat for e in deductible), Decimal("0"))

    # Kwota VAT do wplaty po odliczeniu naliczonego (>=0)
    vat_to_pay = max(total_vat - total_exp_vat, Decimal("0"))

    # P_10 — Podstawa opodatkowania (dostawa towarów/usług krajowa)
    etree.SubElement(poz, "{%s}P_10" % TNS).text = f"{total_net:.2f}"
    # P_11 — Podatek należny
    etree.SubElement(poz, "{%s}P_11" % TNS).text = f"{total_vat:.2f}"
    # P_38 — Razem podstawa opodatkowania
    etree.SubElement(poz, "{%s}P_38" % TNS).text = f"{total_net:.2f}"
    # P_39 — Razem podatek należny
    etree.SubElement(poz, "{%s}P_39" % TNS).text = f"{total_vat:.2f}"

    # Sekcja zakupow (jesli sa odliczalne)
    if deductible:
        # P_41 — Wartosc netto nabyc krajowych innych niz ST
        etree.SubElement(poz, "{%s}P_41" % TNS).text = f"{total_exp_net:.2f}"
        # P_42 — VAT naliczony do odliczenia z nabyc krajowych innych niz ST
        etree.SubElement(poz, "{%s}P_42" % TNS).text = f"{total_exp_vat:.2f}"
        # P_43 — Razem VAT naliczony do odliczenia
        etree.SubElement(poz, "{%s}P_43" % TNS).text = f"{total_exp_vat:.2f}"

    # P_49 — Roznica VAT do wplaty (P_38 - P_43, nie mniej niz 0)
    etree.SubElement(poz, "{%s}P_49" % TNS).text = f"{vat_to_pay:.2f}"
    # P_51 — Kwota do wpłaty
    etree.SubElement(poz, "{%s}P_51" % TNS).text = f"{vat_to_pay:.2f}"

    etree.SubElement(deklaracja, "{%s}Pouczenia" % TNS).text = "1"

    # --- Ewidencja (szczegółowe wiersze) ---
    ewidencja = etree.SubElement(root, "{%s}Ewidencja" % TNS)

    for lp, inv in enumerate(invoices, start=1):
        wiersz = etree.SubElement(ewidencja, "{%s}SprzedazWiersz" % TNS)

        etree.SubElement(wiersz, "{%s}LpSprzedazy" % TNS).text = str(lp)
        etree.SubElement(wiersz, "{%s}KodKrajuNadaniaTIN" % TNS).text = inv.buyer.country_code
        etree.SubElement(wiersz, "{%s}NrKontrahenta" % TNS).text = inv.buyer.nip
        etree.SubElement(wiersz, "{%s}NazwaKontrahenta" % TNS).text = inv.buyer.name
        etree.SubElement(wiersz, "{%s}DowodSprzedazy" % TNS).text = inv.number
        etree.SubElement(wiersz, "{%s}DataWystawienia" % TNS).text = inv.issue_date.isoformat()
        etree.SubElement(wiersz, "{%s}DataSprzedazy" % TNS).text = inv.sale_date.isoformat()

        # Pogrupuj pozycje wg stawki -> osobne pola K_ per stawka
        for vat_rate, (net_sum, vat_sum) in inv.totals_by_vat_rate().items():
            mapping = VAT_RATE_TO_K_FIELDS.get(vat_rate)
            if mapping is None:
                raise ValueError(
                    f"Faktura {inv.number}: nieobslugiwana stawka VAT {vat_rate}% "
                    f"(dozwolone: {sorted(VAT_RATE_TO_K_FIELDS.keys())})"
                )
            net_field, vat_field = mapping
            etree.SubElement(wiersz, "{%s}%s" % (TNS, net_field)).text = f"{net_sum:.2f}"
            if vat_field is not None:
                etree.SubElement(wiersz, "{%s}%s" % (TNS, vat_field)).text = f"{vat_sum:.2f}"

    # Podsumowanie sprzedaży
    ctrl_sprz = etree.SubElement(ewidencja, "{%s}SprzedazCtrl" % TNS)
    etree.SubElement(ctrl_sprz, "{%s}LiczbaWierszySprzedazy" % TNS).text = str(len(invoices))
    etree.SubElement(ctrl_sprz, "{%s}PodatekNalezny" % TNS).text = f"{total_vat:.2f}"

    # Ewidencja zakupow (ZakupWiersz per faktura zakupu)
    for lp, exp in enumerate(deductible, start=1):
        wiersz = etree.SubElement(ewidencja, "{%s}ZakupWiersz" % TNS)
        etree.SubElement(wiersz, "{%s}LpZakupu" % TNS).text = str(lp)
        etree.SubElement(wiersz, "{%s}KodKrajuNadaniaTIN" % TNS).text = exp.seller_country
        etree.SubElement(wiersz, "{%s}NrDostawcy" % TNS).text = exp.seller_nip
        etree.SubElement(wiersz, "{%s}NazwaDostawcy" % TNS).text = exp.seller_name
        etree.SubElement(wiersz, "{%s}DowodZakupu" % TNS).text = exp.document_number
        etree.SubElement(wiersz, "{%s}DataZakupu" % TNS).text = exp.issue_date.isoformat()
        etree.SubElement(wiersz, "{%s}DataWplywu" % TNS).text = exp.receive_date.isoformat()
        # K_42 — wartosc netto nabyc krajowych innych niz ST
        etree.SubElement(wiersz, "{%s}K_42" % TNS).text = f"{exp.total_net:.2f}"
        # K_43 — VAT naliczony przy nabyciach krajowych innych niz ST
        etree.SubElement(wiersz, "{%s}K_43" % TNS).text = f"{exp.total_vat:.2f}"

    # Podsumowanie zakupow
    ctrl_zak = etree.SubElement(ewidencja, "{%s}ZakupCtrl" % TNS)
    etree.SubElement(ctrl_zak, "{%s}LiczbaWierszyZakupow" % TNS).text = str(len(deductible))
    etree.SubElement(ctrl_zak, "{%s}PodatekNaliczony" % TNS).text = f"{total_exp_vat:.2f}"

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    ).decode("utf-8")


def save_jpk_v7m(
    invoices: list[Invoice],
    month: int,
    year: int,
    output_path: Path,
    correction: int = 0,
    expenses: list[Expense] | None = None,
) -> Path:
    """Wygeneruj i zapisz JPK_V7M do pliku."""
    xml = generate_jpk_v7m(invoices, month, year, correction, expenses=expenses)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
