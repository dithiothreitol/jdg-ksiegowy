"""Reguly podatkowe 1.0: terminy robocze, mikrorachunek, prog zdrowotnej, przeniesienie VAT."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from lxml import etree

from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.registry.repository import TaxPayment
from jdg_ksiegowy.tax.deadlines import annual_deadlines, monthly_deadlines, next_business_day
from jdg_ksiegowy.tax.jpk import generate_jpk_v7m
from jdg_ksiegowy.tax.microaccount import is_valid_nrb, microaccount
from jdg_ksiegowy.tax.obligations import monthly_contributions, ryczalt
from jdg_ksiegowy.tax.validation import validate_jpk
from jdg_ksiegowy.tax.zus import MissingTaxParamsError, ZUSSocialMode, params_for
from tests.helpers import InvoiceRow

# --- terminy -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("month", "year", "ryczalt_due", "vat_due"),
    [
        (10, 2026, date(2026, 11, 20), date(2026, 11, 25)),  # bez przesuniec
        (11, 2026, date(2026, 12, 21), date(2026, 12, 28)),  # nd -> pn; 25-27.12 wolne -> 28.12
        (12, 2026, date(2027, 1, 20), date(2027, 1, 25)),  # ryczalt za grudzien do 20.01
        (2, 2027, date(2027, 3, 22), date(2027, 3, 25)),  # sob 20.03 -> pn 22.03
        (3, 2027, date(2027, 4, 20), date(2027, 4, 26)),  # nd 25.04 -> pn 26.04
        (4, 2026, date(2026, 5, 20), date(2026, 5, 25)),
    ],
)
def test_monthly_deadlines_shift_to_business_day(month, year, ryczalt_due, vat_due):
    d = monthly_deadlines(month, year)
    assert (d["ryczalt"], d["zus"], d["vat_jpk"]) == (ryczalt_due, ryczalt_due, vat_due)


def test_holidays_and_annual_deadline():
    assert next_business_day(date(2026, 12, 24)) == date(2026, 12, 28)  # Wigilia wolna od 2025
    assert next_business_day(date(2026, 11, 11)) == date(2026, 11, 12)
    assert annual_deadlines(2026)["pit28"] == date(2027, 4, 30)
    assert annual_deadlines(2027)["pit28"] == date(2028, 5, 2)  # 30.04 nd, 1.05 swieto


# --- mikrorachunek -----------------------------------------------------------------


def test_microaccount_structure_and_checksum():
    acc = microaccount("5260250274")
    assert len(acc) == 26 and acc[2:13] == "10100071222" and acc[13] == "2"
    assert acc[14:24] == "5260250274" and acc.endswith("00")
    assert is_valid_nrb(acc)
    with pytest.raises(ValueError):
        microaccount("1234567890")  # zla suma kontrolna NIP


# --- skladki i ryczalt --------------------------------------------------------------


def _inv(month: int, net: str) -> Invoice:
    return InvoiceRow(
        number=f"A1/{month:02d}/2026",
        issue_date=date(2026, month, 28),
        total_net=Decimal(net),
        buyer_nip="5260250274",
    ).to_domain()


def test_health_tier_uses_cumulative_revenue_and_switches_on_crossing():
    invoices = [_inv(m, "25000") for m in (1, 2, 3)]
    kw = {"social_mode": ZUSSocialMode.EMPLOYMENT, "voluntary_sickness": False}
    assert monthly_contributions(invoices, [], 2026, 2, **kw).health == Decimal("498.35")
    # marzec: 75 000 narastajaco > 60 000 -> wyzszy prog od miesiaca przekroczenia
    march = monthly_contributions(invoices, [], 2026, 3, **kw)
    assert (march.revenue_ytd, march.health) == (Decimal("75000"), Decimal("830.58"))


def test_social_contributions_paid_reduce_threshold_basis():
    invoices = [_inv(m, "20500") for m in (1, 2, 3)]  # 61 500 narastajaco
    paid = [
        TaxPayment(
            "zus_social", 2026, m, Decimal("1788.29"), date(2026, m + 1, 20), datetime(2026, m, 15)
        )
        for m in (1, 2, 3)
    ]
    march = monthly_contributions(
        invoices, paid, 2026, 3, social_mode=ZUSSocialMode.FULL, voluntary_sickness=False
    )
    assert march.revenue_ytd == Decimal("56135.13")
    assert march.health == Decimal("498.35")


def test_ryczalt_rounding_to_full_zloty():
    r = ryczalt(Decimal("10833.33"), Decimal("415.29"), Decimal("12"))
    assert (r.base, r.tax) == (Decimal("10418"), Decimal("1250"))  # 1250.16 -> 1250


def test_missing_year_params_is_explicit():
    assert params_for(2026).year == 2026
    with pytest.raises(MissingTaxParamsError, match="2027"):
        params_for(2027)


# --- JPK: przeniesienie nadwyzki i klasyfikacja pozycji ---------------------------------


@pytest.fixture
def seller(monkeypatch):
    from jdg_ksiegowy.config import SellerConfig, settings

    monkeypatch.setenv("SELLER_NIP", "5260250274")
    monkeypatch.setattr(settings, "seller", SellerConfig())


def _fields(xml: str, *tags: str) -> dict[str, str | None]:
    root = etree.fromstring(xml.encode())
    return {t: root.findtext(f".//{{*}}PozycjeSzczegolowe/{{*}}{t}") for t in tags}


def _invoice(buyer: Buyer, items: list[LineItem]) -> Invoice:
    return Invoice(
        number="A1/10/2026",
        issue_date=date(2026, 10, 5),
        sale_date=date(2026, 10, 5),
        payment_due=date(2026, 10, 19),
        buyer=buyer,
        items=items,
    )


def test_carry_forward_reduces_vat_and_surplus_is_declared(seller):
    small = _invoice(
        Buyer(name="K", nip="5260250274", address="ul. X 1"),
        [LineItem(description="x", unit_price_net=Decimal("100"))],
    )
    xml = generate_jpk_v7m([small], 10, 2026, carry_forward=Decimal("500"))
    assert validate_jpk(xml).valid
    assert _fields(xml, "P_38", "P_39", "P_48", "P_51", "P_53", "P_62") == {
        "P_38": "23",
        "P_39": "500",
        "P_48": "500",
        "P_51": "0",
        "P_53": "477",
        "P_62": "477",
    }


def test_sale_classification_k12_k21_k22_zw_and_gtu(seller):
    def item(code: str, net: str, gtu: str | None = None) -> LineItem:
        return LineItem(description=code, unit_price_net=Decimal(net), vat_code=code, gtu=gtu)

    eu = _invoice(
        Buyer(name="DE GmbH", address="Berlin", country_code="DE", eu_vat_number="DE811569869"),
        [
            item("NP", "1000", "GTU_12"),
            item("0_WDT", "300"),
            item("0_EXP", "200"),
            item("ZW", "50"),
        ],
    )
    xml = generate_jpk_v7m([eu], 10, 2026)
    result = validate_jpk(xml)
    assert result.valid, result.errors[:3]
    assert _fields(xml, "P_10", "P_11", "P_12", "P_21", "P_22", "P_37", "P_38") == {
        "P_10": "50",
        "P_11": "1000",
        "P_12": "1000",
        "P_21": "300",
        "P_22": "200",
        "P_37": "1550",
        "P_38": "0",
    }
    row = etree.fromstring(xml.encode()).find(".//{*}SprzedazWiersz")
    assert row.findtext("{*}GTU_12") == "1"
    assert eu.total_vat == Decimal("0")  # kody bez VAT naleznego zeruja stawke


def test_invalid_gtu_rejected():
    with pytest.raises(ValueError, match="GTU"):
        LineItem(description="x", unit_price_net=Decimal("1"), gtu="GTU_14")


@pytest.mark.parametrize(
    ("country", "code", "p_12", "fields"),
    [
        ("DE", "np", "np II", {"K_11", "K_12"}),  # usluga dla podatnika z UE: art. 100
        ("US", "np", "np I", {"K_11"}),
        ("DE", "0_wdt", "0 WDT", {"K_21"}),
        ("US", "0_exp", "0 EX", {"K_22"}),
        ("PL", "zw", "zw", {"K_10"}),
        ("PL", None, "0 KR", {"K_13"}),  # stawka 0 bez kodu = krajowe 0%
    ],
)
def test_fa3_marker_and_jpk_fields_agree(seller, country, code, p_12, fields):
    from jdg_ksiegowy.invoice.generator_xml import generate_invoice_xml
    from jdg_ksiegowy.tax.jpk import invoice_fields

    if country == "PL":
        buyer = Buyer(name="K", nip="5260250274", address="ul. X 1, 00-001 Warszawa")
    else:
        buyer = Buyer(name="Kunde", address="Hauptstr. 1, Berlin", country_code=country)
    item = LineItem(description="x", unit_price_net=Decimal("100"), vat_code=code, vat_rate=0)
    invoice = _invoice(buyer, [item])
    xml = etree.fromstring(generate_invoice_xml(invoice).encode())
    assert [e.text for e in xml.iter("{*}P_12")] == [p_12]
    assert set(invoice_fields(invoice)) == fields


def test_unknown_vat_code_is_rejected_at_input():
    with pytest.raises(ValueError, match="kod VAT"):
        LineItem(description="x", unit_price_net=Decimal("1"), vat_code="0_KR")
