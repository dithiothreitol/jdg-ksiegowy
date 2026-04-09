"""Generator XML FA(3) dla KSeF — faktura ustrukturyzowana.

Schema: FA(3) obowiazujaca od 1.02.2026
Zrodlo: https://ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/wsparcie-dla-integratorow
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Invoice

# Namespace FA(3) — schemat Ministerstwa Finansow
FA3_NS = "http://crd.gov.pl/wzor/2023/06/29/12648/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    None: FA3_NS,
    "xsi": XSI_NS,
}


def _el(parent: etree._Element, tag: str, text: str | None = None, **attribs) -> etree._Element:
    """Helper — dodaj element XML."""
    elem = etree.SubElement(parent, tag, **attribs)
    if text is not None:
        elem.text = str(text)
    return elem


def generate_invoice_xml(invoice: Invoice) -> str:
    """Wygeneruj XML FA(3) dla KSeF z danych faktury."""
    seller = settings.seller

    root = etree.Element("{%s}Faktura" % FA3_NS, nsmap=NSMAP)

    # --- Naglowek ---
    naglowek = _el(root, "Naglowek")
    kod = _el(naglowek, "KodFormularza", "FA")
    kod.set("kodSystemowy", "FA (3)")
    kod.set("wersjaSchemy", "1-0E")
    _el(naglowek, "WariantFormularza", "3")
    _el(naglowek, "DataWytworzeniaFa", f"{invoice.issue_date.isoformat()}T00:00:00")
    _el(naglowek, "SystemInfo", "JDG-Ksiegowy/1.0")

    # --- Podmiot1 (Sprzedawca) ---
    podmiot1 = _el(root, "Podmiot1")
    dane1 = _el(podmiot1, "DaneIdentyfikacyjne")
    _el(dane1, "NIP", seller.nip)
    _el(dane1, "Nazwa", seller.name)
    adres1 = _el(podmiot1, "Adres")
    _el(adres1, "KodKraju", "PL")
    # Rozdziel adres na linie
    address_parts = seller.address.rsplit(", ", 1)
    _el(adres1, "AdresL1", address_parts[0])
    if len(address_parts) > 1:
        _el(adres1, "AdresL2", address_parts[1])

    # --- Podmiot2 (Nabywca) ---
    podmiot2 = _el(root, "Podmiot2")
    dane2 = _el(podmiot2, "DaneIdentyfikacyjne")
    _el(dane2, "NIP", invoice.buyer.nip)
    _el(dane2, "Nazwa", invoice.buyer.name)
    adres2 = _el(podmiot2, "Adres")
    _el(adres2, "KodKraju", invoice.buyer.country_code)
    _el(adres2, "AdresL1", invoice.buyer.address)

    # --- Fa (tresc faktury) ---
    fa = _el(root, "Fa")
    _el(fa, "KodWaluty", "PLN")
    _el(fa, "DataWystawienia", invoice.issue_date.isoformat())
    _el(fa, "DataSprzedazy", invoice.sale_date.isoformat())
    _el(fa, "NrFaUzytkownika", invoice.number)
    _el(fa, "RodzajFaktury", "VAT")

    # Okres
    if invoice.period_from and invoice.period_to:
        daty = _el(fa, "DatySzczegolowe")
        okres = _el(daty, "OkresFa")
        _el(okres, "DataOd", invoice.period_from.isoformat())
        _el(okres, "DataDo", invoice.period_to.isoformat())

    # Wiersze faktury
    for idx, item in enumerate(invoice.items, 1):
        wiersz = _el(fa, "FaWiersz")
        _el(wiersz, "NrWierszaFa", str(idx))
        _el(wiersz, "UU_ID", str(uuid.uuid4()))

        desc = item.description
        if invoice.period_from and invoice.period_to:
            desc += f" — okres: {invoice.period_from.strftime('%d.%m.%Y')}-{invoice.period_to.strftime('%d.%m.%Y')}"
        _el(wiersz, "P_7", desc)
        _el(wiersz, "P_8A", item.unit)
        _el(wiersz, "P_8B", str(item.quantity))
        _el(wiersz, "P_9A", f"{item.unit_price_net:.2f}")
        _el(wiersz, "P_11", f"{item.net_value:.2f}")
        _el(wiersz, "P_12", str(int(item.vat_rate)))

    # Rozliczenie
    rozliczenie = _el(fa, "Rozliczenie")
    stawki = _el(rozliczenie, "Stawki")
    stawka = _el(stawki, "Stawka")
    _el(stawka, "P_12_XII", str(int(invoice.items[0].vat_rate)))
    _el(stawka, "P_13_XII", f"{invoice.total_net:.2f}")
    _el(stawka, "P_14_XII", f"{invoice.total_vat:.2f}")
    _el(rozliczenie, "P_15", f"{invoice.total_gross:.2f}")

    # Platnosc
    platnosc = _el(fa, "Platnosc")
    _el(platnosc, "Zaplacono", "false")
    termin = _el(platnosc, "TerminPlatnosci")
    _el(termin, "Termin", invoice.payment_due.isoformat())
    _el(platnosc, "FormaPlatnosci", "6")  # 6 = przelew
    rachunek = _el(platnosc, "RachunekBankowy")
    _el(rachunek, "NrRB", seller.bank_account_raw)
    _el(rachunek, "NazwaBanku", seller.bank_name)

    # Serializacja
    xml_str = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    ).decode("utf-8")

    return xml_str


def save_invoice_xml(invoice: Invoice, output_path: Path) -> Path:
    """Wygeneruj i zapisz XML FA(3) do pliku."""
    xml_content = generate_invoice_xml(invoice)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")
    return output_path


def validate_xml_against_xsd(xml_path: Path, xsd_path: Path) -> tuple[bool, list[str]]:
    """Waliduj XML faktury wobec schematu XSD FA(3).

    Returns:
        (is_valid, list_of_errors)
    """
    try:
        xsd_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(xsd_doc)
        xml_doc = etree.parse(str(xml_path))
        is_valid = schema.validate(xml_doc)
        errors = [str(e) for e in schema.error_log]
        return is_valid, errors
    except etree.XMLSyntaxError as e:
        return False, [f"XML syntax error: {e}"]
