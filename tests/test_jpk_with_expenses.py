"""Testy JPK_V7M z sekcja zakupowa (faktury kosztowe)."""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.jpk import TNS, generate_jpk_v7m


def _ns(t: str) -> str:
    return f"{{{TNS}}}{t}"


def _invoice(net: Decimal, vat_rate: Decimal = Decimal("23")) -> Invoice:
    return Invoice(
        number=f"S/{net}",
        issue_date=date(2026, 4, 1),
        sale_date=date(2026, 4, 1),
        payment_due=date(2026, 4, 15),
        buyer=Buyer(name="Klient", nip="1111111111", address="ul. X 1"),
        items=[LineItem(description="usl", unit_price_net=net, vat_rate=vat_rate)],
    )


def _expense(net: Decimal, vat: Decimal, deductible: bool = True) -> Expense:
    return Expense(
        seller_name="Dostawca",
        seller_nip="2222222222",
        document_number=f"K/{net}",
        issue_date=date(2026, 4, 5),
        receive_date=date(2026, 4, 7),
        category=ExpenseCategory.USLUGI_OBCE,
        total_net=net,
        total_vat=vat,
        vat_deductible=deductible,
    )


def test_jpk_includes_zakup_section_when_expenses_provided():
    inv = _invoice(Decimal("1000"))  # VAT nalezny: 230
    exp = _expense(Decimal("500"), Decimal("115"))  # VAT naliczony do odliczenia
    xml = generate_jpk_v7m([inv], month=4, year=2026, expenses=[exp])
    root = etree.fromstring(xml.encode("utf-8"))

    # ZakupWiersz powinien istniec
    zakup = root.find(f".//{_ns('ZakupWiersz')}")
    assert zakup is not None
    assert zakup.find(_ns("K_42")).text == "500.00"
    assert zakup.find(_ns("K_43")).text == "115.00"

    # P_41/P_42/P_43 w deklaracji
    poz = root.find(f".//{_ns('PozycjeSzczegolowe')}")
    assert poz.find(_ns("P_41")).text == "500.00"
    assert poz.find(_ns("P_42")).text == "115.00"
    assert poz.find(_ns("P_43")).text == "115.00"

    # P_49 (do wplaty) = VAT nalezny - VAT naliczony = 230 - 115 = 115
    assert poz.find(_ns("P_49")).text == "115.00"

    # ZakupCtrl
    ctrl = root.find(f".//{_ns('ZakupCtrl')}")
    assert ctrl.find(_ns("LiczbaWierszyZakupow")).text == "1"
    assert ctrl.find(_ns("PodatekNaliczony")).text == "115.00"


def test_jpk_no_zakup_section_when_no_expenses():
    inv = _invoice(Decimal("1000"))
    xml = generate_jpk_v7m([inv], month=4, year=2026)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find(f".//{_ns('ZakupWiersz')}") is None
    # Ale ZakupCtrl wciaz musi byc (z zerami) - obecna implementacja: pokazuje 0/0.00
    ctrl = root.find(f".//{_ns('ZakupCtrl')}")
    assert ctrl.find(_ns("LiczbaWierszyZakupow")).text == "0"


def test_jpk_excludes_non_deductible_expenses_from_section():
    inv = _invoice(Decimal("1000"))
    deductible = _expense(Decimal("500"), Decimal("115"), deductible=True)
    not_deductible = _expense(Decimal("200"), Decimal("46"), deductible=False)
    xml = generate_jpk_v7m([inv], month=4, year=2026, expenses=[deductible, not_deductible])
    root = etree.fromstring(xml.encode("utf-8"))
    zakup_wiersze = root.findall(f".//{_ns('ZakupWiersz')}")
    assert len(zakup_wiersze) == 1
    assert zakup_wiersze[0].find(_ns("K_42")).text == "500.00"


def test_vat_to_pay_clamped_at_zero():
    """Gdy VAT naliczony > naleznego, P_49 powinien byc 0 (nie ujemny)."""
    inv = _invoice(Decimal("100"))  # VAT nalezny: 23
    exp = _expense(Decimal("1000"), Decimal("230"))  # VAT naliczony: 230
    xml = generate_jpk_v7m([inv], month=4, year=2026, expenses=[exp])
    root = etree.fromstring(xml.encode("utf-8"))
    poz = root.find(f".//{_ns('PozycjeSzczegolowe')}")
    assert poz.find(_ns("P_49")).text == "0.00"
