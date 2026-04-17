"""Testy generatora DRA ZUS (KEDU v5.05)."""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.zus.dra import DRARequest, dra_deadline, generate_dra_xml, KEDU_NS


def _ns(tag: str) -> str:
    return f"{{{KEDU_NS}}}{tag}"


class TestDRADeadline:
    def test_deadline_within_year(self):
        assert dra_deadline(3, 2026) == date(2026, 4, 20)

    def test_deadline_december_rolls_to_january(self):
        assert dra_deadline(12, 2026) == date(2027, 1, 20)


class TestGenerateDRA:
    def test_health_only_for_tier_i(self):
        # przychód ≤ 60k → próg I (~ 360 PLN zdrowotnej)
        req = DRARequest(month=3, year=2026, annual_prior_income=Decimal("50000"))
        result = generate_dra_xml(req)
        assert result.health_contribution > Decimal("0")
        assert result.social_contribution == Decimal("0")
        assert result.total == result.health_contribution

    def test_include_social_adds_social_tier(self):
        req = DRARequest(
            month=3, year=2026, annual_prior_income=Decimal("200000"),
            include_social=True,
        )
        result = generate_dra_xml(req)
        assert result.social_contribution > Decimal("0")
        assert result.total == result.health_contribution + result.social_contribution

    def test_higher_income_higher_health_contribution(self):
        low = generate_dra_xml(DRARequest(month=3, year=2026, annual_prior_income=Decimal("50000")))
        high = generate_dra_xml(DRARequest(month=3, year=2026, annual_prior_income=Decimal("400000")))
        assert high.health_contribution > low.health_contribution

    def test_xml_has_kedu_namespace_and_header(self):
        result = generate_dra_xml(DRARequest(month=3, year=2026, annual_prior_income=Decimal("100000")))
        root = etree.fromstring(result.xml.encode())
        assert root.tag == _ns("KEDU")
        assert root.find(f"{_ns('naglowek')}/{_ns('typ_dokumentu')}").text == "DRA"
        assert root.find(f"{_ns('naglowek')}/{_ns('wersja_schematu')}").text == "5.05"

    def test_xml_contains_platnik_nip(self):
        result = generate_dra_xml(DRARequest(month=3, year=2026, annual_prior_income=Decimal("100000")))
        root = etree.fromstring(result.xml.encode())
        nip = root.find(f".//{_ns('platnik')}/{_ns('NIP')}")
        assert nip is not None
        # z conftest SELLER_NIP
        assert len(nip.text) == 10

    def test_xml_contains_period(self):
        result = generate_dra_xml(DRARequest(month=3, year=2026, annual_prior_income=Decimal("100000")))
        root = etree.fromstring(result.xml.encode())
        okres = root.find(f".//{_ns('naglowek_DRA')}/{_ns('okres_od')}")
        assert okres.text == "2026-03-01"

    def test_xml_contains_skladki_razem(self):
        result = generate_dra_xml(DRARequest(
            month=3, year=2026, annual_prior_income=Decimal("200000"), include_social=True,
        ))
        root = etree.fromstring(result.xml.encode())
        razem = root.find(f".//{_ns('skladki')}/{_ns('razem')}")
        expected = result.health_contribution + result.social_contribution
        assert Decimal(razem.text) == expected

    def test_xml_social_element_absent_when_not_included(self):
        result = generate_dra_xml(DRARequest(
            month=3, year=2026, annual_prior_income=Decimal("100000"),
        ))
        root = etree.fromstring(result.xml.encode())
        assert root.find(f".//{_ns('skladki')}/{_ns('spoleczne')}") is None
