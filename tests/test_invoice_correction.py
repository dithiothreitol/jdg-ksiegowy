"""Testy faktur korygujących FA KOR (3)."""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.invoice.generator_xml import FA3_NS, generate_correction_xml
from jdg_ksiegowy.invoice.models import (
    Buyer,
    CorrectionReason,
    InvoiceCorrection,
    LineItem,
)


def _fa3(tag: str) -> str:
    return f"{{{FA3_NS}}}{tag}"


def _buyer() -> Buyer:
    return Buyer(name="Klient Sp. z o.o.", nip="5260250274", address="ul. X 1, Warszawa")


def _correction(**kwargs) -> InvoiceCorrection:
    defaults = dict(
        number="AK1/04/2026",
        original_number="A1/04/2026",
        issue_date=date(2026, 4, 15),
        correction_date=date(2026, 4, 15),
        buyer=_buyer(),
        items=[
            LineItem(
                description="Usługa IT (korekta)",
                unit_price_net=Decimal("-200"),
                vat_rate=Decimal("23"),
            )
        ],
        reason=CorrectionReason.PRICE_CHANGE,
        reason_description="Rabat 20%",
    )
    defaults.update(kwargs)
    return InvoiceCorrection(**defaults)


class TestCorrectionModel:
    def test_total_net_negative_for_price_reduction(self):
        c = _correction()
        assert c.total_net == Decimal("-200")
        assert c.total_vat == Decimal("-46.00")
        assert c.total_gross == Decimal("-246.00")

    def test_reason_enum_values(self):
        assert CorrectionReason.PRICE_CHANGE.value == "01"
        assert CorrectionReason.RETURN_GOODS.value == "02"
        assert CorrectionReason.OTHER.value == "99"


class TestCorrectionXML:
    def _root(self, correction: InvoiceCorrection):
        xml = generate_correction_xml(correction)
        return etree.fromstring(xml.encode())

    def test_rodzaj_faktury_is_kor(self):
        root = self._root(_correction())
        assert root.find(f".//{_fa3('RodzajFaktury')}").text == "KOR"

    def test_nr_fa_korygowanej_present(self):
        root = self._root(_correction())
        dane = root.find(f".//{_fa3('DaneFaKorygowanej')}")
        assert dane is not None
        assert dane.find(_fa3("NrFaKorygowanej")).text == "A1/04/2026"

    def test_ksef_reference_in_fa_korygowana(self):
        c = _correction(original_ksef_reference="KSEF-2026-04-01-ABC")
        root = self._root(c)
        dane = root.find(f".//{_fa3('DaneFaKorygowanej')}")
        assert dane.find(_fa3("NrKSeFFaKorygowanej")).text == "KSEF-2026-04-01-ABC"

    def test_no_ksef_reference_skips_element(self):
        root = self._root(_correction(original_ksef_reference=None))
        dane = root.find(f".//{_fa3('DaneFaKorygowanej')}")
        assert dane.find(_fa3("NrKSeFFaKorygowanej")) is None

    def test_przyczyna_korekty_text_contains_description(self):
        """FA(3): PrzyczynaKorekty to pojedyncze pole tekstowe."""
        root = self._root(_correction(reason_description="Rabat 20%"))
        powod = root.find(f".//{_fa3('PrzyczynaKorekty')}")
        assert powod.text == "Rabat 20%"

    def test_negative_p11_in_wiersz(self):
        root = self._root(_correction())
        p11 = root.find(f".//{_fa3('P_11')}")
        assert p11.text == "-200.00"

    def test_p15_is_negative_gross(self):
        root = self._root(_correction())
        p15 = root.find(f".//{_fa3('P_15')}")
        assert p15.text == "-246.00"

    def test_buyer_nip_in_podmiot2(self):
        root = self._root(_correction())
        podmiot2 = root.find(_fa3("Podmiot2"))
        dane2 = podmiot2.find(_fa3("DaneIdentyfikacyjne"))
        assert dane2.find(_fa3("NIP")).text == "5260250274"

    def test_correction_number_in_p2(self):
        """FA(3): numer faktury idzie do pola P_2."""
        root = self._root(_correction())
        assert root.find(f".//{_fa3('P_2')}").text == "AK1/04/2026"

    def test_eu_buyer_uses_nrvatue_in_correction(self):
        eu_buyer = Buyer(
            name="DE GmbH",
            nip="",
            country_code="DE",
            eu_vat_number="DE987654321",
            address="Berlin 1",
        )
        c = _correction(buyer=eu_buyer)
        root = self._root(c)
        podmiot2 = root.find(_fa3("Podmiot2"))
        dane2 = podmiot2.find(_fa3("DaneIdentyfikacyjne"))
        assert dane2.find(_fa3("KodUE")).text == "DE"
        assert dane2.find(_fa3("NrVatUE")).text == "987654321"
