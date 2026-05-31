"""Testy importu usług / odwrotnego obciążenia w JPK_V7M.

Dostawca z UE -> K_29/K_30 (art. 28b), spoza UE -> K_27/K_28. Samonaliczony VAT
należny wchodzi też do odliczenia (K_42/K_43) -> dla działalności opodatkowanej
efekt netto = 0 (P_51 bez zmian).
"""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem
from jdg_ksiegowy.tax.jpk import TNS, generate_jpk_v7m


def _ns(t: str) -> str:
    return f"{{{TNS}}}{t}"


def _invoice(net: Decimal) -> Invoice:
    return Invoice(
        number="A1/05/2026",
        issue_date=date(2026, 5, 1),
        sale_date=date(2026, 5, 1),
        payment_due=date(2026, 5, 15),
        buyer=Buyer(name="Klient", nip="5260250274", address="ul. X 1"),
        items=[LineItem(description="usl", unit_price_net=net, vat_rate=Decimal("23"))],
    )


def _rc_expense(
    *,
    country: str,
    nip: str,
    net: Decimal,
    vat: Decimal,
    deduction: Decimal = Decimal("100"),
) -> Expense:
    return Expense(
        seller_name=f"Dostawca {country}",
        seller_nip=nip,
        seller_country=country,
        document_number=f"R/{country}/{net}",
        issue_date=date(2026, 5, 10),
        receive_date=date(2026, 5, 10),
        category=ExpenseCategory.USLUGI_OBCE,
        total_net=net,
        total_vat=vat,
        vat_rate=Decimal("23"),
        vat_deduction_pct=deduction,
        reverse_charge=True,
    )


def _poz(xml: str):
    root = etree.fromstring(xml.encode())
    return root, root.find(f".//{_ns('PozycjeSzczegolowe')}")


def _txt(parent, tag):
    el = parent.find(_ns(tag))
    return el.text if el is not None else None


# --- dostawca spoza UE -> K_27/K_28, P_27/P_28 ---


def test_non_eu_supplier_goes_to_k27_k28():
    exp = _rc_expense(country="US", nip="", net=Decimal("765.92"), vat=Decimal("176.16"))
    xml = generate_jpk_v7m([], month=5, year=2026, expenses=[exp])
    root, poz = _poz(xml)

    wiersz = next(
        w for w in root.findall(f".//{_ns('SprzedazWiersz')}") if w.find(_ns("K_27")) is not None
    )
    assert wiersz.find(_ns("K_27")).text == "765.92"
    assert wiersz.find(_ns("K_28")).text == "176.16"
    assert wiersz.find(_ns("NrKontrahenta")).text == "BRAK"  # US bez VAT-ID
    assert _txt(poz, "P_27") == "766"
    assert _txt(poz, "P_28") == "176"
    assert poz.find(_ns("P_29")) is None  # brak pozycji UE


# --- dostawca z UE -> K_29/K_30, P_29/P_30 ---


def test_eu_supplier_goes_to_k29_k30():
    exp = _rc_expense(country="DE", nip="DE812871812", net=Decimal("100"), vat=Decimal("23"))
    xml = generate_jpk_v7m([], month=5, year=2026, expenses=[exp])
    root, poz = _poz(xml)

    wiersz = next(
        w for w in root.findall(f".//{_ns('SprzedazWiersz')}") if w.find(_ns("K_29")) is not None
    )
    assert wiersz.find(_ns("K_29")).text == "100.00"
    assert wiersz.find(_ns("K_30")).text == "23.00"
    assert wiersz.find(_ns("NrKontrahenta")).text == "DE812871812"
    assert _txt(poz, "P_29") == "100"
    assert _txt(poz, "P_30") == "23"
    assert poz.find(_ns("P_27")) is None


# --- efekt netto zero przy 100% odliczenia ---


def test_reverse_charge_is_net_zero_when_fully_deductible():
    inv = _invoice(Decimal("1000"))  # VAT należny krajowy: 230
    exp = _rc_expense(country="US", nip="", net=Decimal("765.92"), vat=Decimal("176.16"))
    xml = generate_jpk_v7m([inv], month=5, year=2026, expenses=[exp])
    _, poz = _poz(xml)

    # samonaliczony 176.16 jest i w należnym (P_39) i w naliczonym (P_43) -> znosi się
    assert _txt(poz, "P_51") == "230"  # do zaplaty = tylko VAT od krajowej sprzedazy


def test_reverse_charge_appears_in_both_registers():
    exp = _rc_expense(country="DE", nip="DE812871812", net=Decimal("100"), vat=Decimal("23"))
    xml = generate_jpk_v7m([_invoice(Decimal("1000"))], month=5, year=2026, expenses=[exp])
    root, _ = _poz(xml)

    # 1 faktura sprzedazy + 1 wiersz importu usług
    assert len(root.findall(f".//{_ns('SprzedazWiersz')}")) == 2
    # import usług jest też nabyciem -> 1 wiersz zakupu (K_42/K_43)
    zakup = root.findall(f".//{_ns('ZakupWiersz')}")
    assert len(zakup) == 1
    assert zakup[0].find(_ns("K_43")).text == "23.00"


# --- import usług nieodliczalny: należny bez naliczonego ---


def test_non_deductible_reverse_charge_still_creates_nalezny():
    # np. usługa zwiazana ze sprzedaza zwolniona -> 0% odliczenia, ale VAT nalezny i tak due
    exp = _rc_expense(
        country="US", nip="", net=Decimal("1000"), vat=Decimal("230"), deduction=Decimal("0")
    )
    xml = generate_jpk_v7m([], month=5, year=2026, expenses=[exp])
    root, poz = _poz(xml)

    assert _txt(poz, "P_28") == "230"  # nalezny samonaliczony
    assert len(root.findall(f".//{_ns('ZakupWiersz')}")) == 0  # brak odliczenia -> brak wiersza
    assert _txt(poz, "P_51") == "230"  # VAT do zaplaty (nieodliczalny import usług)
