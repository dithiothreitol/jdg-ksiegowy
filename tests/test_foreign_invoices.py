"""Testy faktur zagranicznych: NrVatUE, BrakID, K_11 w JPK, FA(3) XML."""

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.invoice.generator_xml import generate_invoice_xml, FA3_NS
from jdg_ksiegowy.tax.jpk import TNS, generate_jpk_v7m


def _ns(tag: str) -> str:
    return f"{{{TNS}}}{tag}"


def _fa3(tag: str) -> str:
    return f"{{{FA3_NS}}}{tag}"


def _invoice(buyer: Buyer, items: list[LineItem]) -> Invoice:
    return Invoice(
        number="Z1/04/2026",
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=buyer,
        items=items,
    )


# ─── Buyer model ──────────────────────────────────────────────────────────────

class TestBuyerIdentifier:
    def test_pl_buyer_returns_nip(self):
        b = Buyer(name="PL Firma", nip="5260250274", address="ul. A 1")
        assert b.identifier_for_xml() == ("NIP", "5260250274")
        assert b.best_identifier() == "5260250274"

    def test_eu_buyer_with_vat_returns_nrvat_ue(self):
        b = Buyer(name="DE Firma", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin 1")
        assert b.identifier_for_xml() == ("NrVatUE", "DE123456789")
        assert b.best_identifier() == "DE123456789"

    def test_non_eu_buyer_returns_brak_id(self):
        b = Buyer(name="US Firma", nip="", country_code="US", address="New York 1")
        assert b.identifier_for_xml() == ("BrakID", "")
        assert b.best_identifier() == "BRAK"

    def test_eu_buyer_without_vat_returns_brak_id(self):
        b = Buyer(name="FR Klient", nip="", country_code="FR", address="Paris 1")
        assert b.identifier_for_xml() == ("BrakID", "")

    def test_nip_validator_allows_foreign_identifiers(self):
        """Niepolski NIP (np. EORI/inne) powinien przejść walidację."""
        b = Buyer(name="X", nip="DE12345678", country_code="DE", address="Berlin")
        assert b.nip == "DE12345678"

    def test_nip_validator_rejects_wrong_polish_nip(self):
        with pytest.raises(Exception, match="NIP"):
            Buyer(name="X", nip="5260250270", address="ul. A 1")


# ─── FA(3) XML ────────────────────────────────────────────────────────────────

class TestForeignInvoiceXML:
    def _podmiot2_dane(self, xml: str):
        root = etree.fromstring(xml.encode())
        # Podmiot2 to drugi Podmiot* w dokumencie — Podmiot1 to sprzedawca
        podmiot2 = root.find(_fa3("Podmiot2"))
        return podmiot2.find(_fa3("DaneIdentyfikacyjne"))

    def test_eu_buyer_uses_nrvatue(self):
        buyer = Buyer(
            name="ACME GmbH", nip="", country_code="DE",
            eu_vat_number="DE123456789", address="Berlin 1",
        )
        inv = _invoice(buyer, [
            LineItem(description="Usługa IT", unit_price_net=Decimal("1000"), vat_rate=Decimal("0"), vat_code="NP"),
        ])
        dane2 = self._podmiot2_dane(generate_invoice_xml(inv))
        # FA(3) rozdziela prefix kraju (KodUE) od samego numeru (NrVatUE).
        assert dane2.find(_fa3("KodUE")).text == "DE"
        assert dane2.find(_fa3("NrVatUE")).text == "123456789"
        assert dane2.find(_fa3("NIP")) is None

    def test_non_eu_buyer_uses_brak_id(self):
        buyer = Buyer(name="US Corp", nip="", country_code="US", address="New York")
        inv = _invoice(buyer, [
            LineItem(description="Usługa", unit_price_net=Decimal("1000"), vat_rate=Decimal("0"), vat_code="NP"),
        ])
        dane2 = self._podmiot2_dane(generate_invoice_xml(inv))
        assert dane2.find(_fa3("BrakID")) is not None
        assert dane2.find(_fa3("NrVatUE")) is None
        assert dane2.find(_fa3("NIP")) is None

    def test_pl_buyer_uses_nip(self):
        buyer = Buyer(name="PL Sp. z o.o.", nip="5260250274", address="ul. X 1")
        inv = _invoice(buyer, [
            LineItem(description="Usługa", unit_price_net=Decimal("1000")),
        ])
        dane2 = self._podmiot2_dane(generate_invoice_xml(inv))
        assert dane2.find(_fa3("NIP")).text == "5260250274"

    def test_np_vat_code_in_p12(self):
        """W FA(3) P_12 dla NP zawiera marker 'np' (builder moze dopisac klasyfikator)."""
        buyer = Buyer(name="DE GmbH", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin")
        item = LineItem(description="Usługa", unit_price_net=Decimal("1000"), vat_rate=Decimal("0"), vat_code="NP")
        inv = _invoice(buyer, [item])
        xml = generate_invoice_xml(inv)
        root = etree.fromstring(xml.encode())
        p12 = root.find(f".//{_fa3('P_12')}")
        assert "np" in p12.text.lower()

    def test_np_line_has_no_vat_amount(self):
        """Dla NP wiersz nie ma kwoty VAT (P_11Vat)."""
        buyer = Buyer(name="DE GmbH", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin")
        inv = _invoice(buyer, [
            LineItem(description="Usługa", unit_price_net=Decimal("2000"), vat_rate=Decimal("0"), vat_code="NP"),
        ])
        xml = generate_invoice_xml(inv)
        root = etree.fromstring(xml.encode())
        wiersz = root.find(f".//{_fa3('FaWiersz')}")
        assert wiersz.find(_fa3("P_11")).text == "2000.00"
        assert wiersz.find(_fa3("P_11Vat")) is None


# ─── JPK V7M — K_11 ───────────────────────────────────────────────────────────

class TestJPKForeignServices:
    def test_np_item_goes_to_k11(self):
        buyer = Buyer(name="DE GmbH", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin")
        inv = _invoice(buyer, [
            LineItem(description="Usługa IT", unit_price_net=Decimal("5000"), vat_rate=Decimal("0"), vat_code="NP"),
        ])
        xml = generate_jpk_v7m([inv], month=4, year=2026)
        root = etree.fromstring(xml.encode())
        wiersz = root.find(f".//{_ns('SprzedazWiersz')}")
        assert wiersz.find(_ns("K_11")).text == "5000.00"
        assert wiersz.find(_ns("K_19")) is None   # brak krajowych 23%

    def test_mixed_domestic_and_foreign(self):
        buyer_pl = Buyer(name="PL Firma", nip="5260250274", address="Warszawa")
        buyer_de = Buyer(name="DE GmbH", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin")
        inv_pl = Invoice(
            number="A1/04/2026", issue_date=date(2026, 4, 1),
            sale_date=date(2026, 4, 1), payment_due=date(2026, 4, 15),
            buyer=buyer_pl,
            items=[LineItem(description="Usługa", unit_price_net=Decimal("1000"))],
        )
        inv_de = Invoice(
            number="Z1/04/2026", issue_date=date(2026, 4, 1),
            sale_date=date(2026, 4, 1), payment_due=date(2026, 4, 15),
            buyer=buyer_de,
            items=[LineItem(description="Usługa", unit_price_net=Decimal("2000"),
                            vat_rate=Decimal("0"), vat_code="NP")],
        )
        xml = generate_jpk_v7m([inv_pl, inv_de], month=4, year=2026)
        root = etree.fromstring(xml.encode())
        wiersze = root.findall(f".//{_ns('SprzedazWiersz')}")
        pl_wiersz = next(w for w in wiersze if w.find(_ns("DowodSprzedazy")).text == "A1/04/2026")
        de_wiersz = next(w for w in wiersze if w.find(_ns("DowodSprzedazy")).text == "Z1/04/2026")
        assert pl_wiersz.find(_ns("K_19")).text == "1000.00"
        assert de_wiersz.find(_ns("K_11")).text == "2000.00"

    def test_nrkontrahenta_uses_best_identifier(self):
        buyer = Buyer(name="DE GmbH", nip="", country_code="DE", eu_vat_number="DE123456789", address="Berlin")
        inv = _invoice(buyer, [
            LineItem(description="X", unit_price_net=Decimal("100"), vat_rate=Decimal("0"), vat_code="NP"),
        ])
        xml = generate_jpk_v7m([inv], month=4, year=2026)
        root = etree.fromstring(xml.encode())
        nr = root.find(f".//{_ns('NrKontrahenta')}")
        assert nr.text == "DE123456789"
