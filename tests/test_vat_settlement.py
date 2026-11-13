"""Regresje: szacunek VAT (dashboard, skill jpk) musi zgadzac sie z deklaracja P_51.

Bug: reverse charge (import uslug) byl tylko odejmowany jako naliczony, bez dodania
samonaliczonego VAT naleznego — dashboard i kalendarz zanizaly zobowiazanie.
"""

from datetime import date
from decimal import Decimal

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.tax.jpk import deductible_vat, period_fields, settle_vat


def _expense(*, net, vat, country="DE", reverse_charge=False, pct=Decimal("100")):
    return Expense(
        id=f"e-{net}-{country}-{reverse_charge}",
        seller_name="Dostawca",
        seller_nip="DE123456789",
        seller_country=country,
        document_number="FV/1",
        issue_date=date(2026, 5, 10),
        receive_date=date(2026, 5, 10),
        category=ExpenseCategory.USLUGI_OBCE,
        total_net=Decimal(net),
        total_vat=Decimal(vat),
        vat_deduction_pct=pct,
        reverse_charge=reverse_charge,
    )


SALES = {"K_19": Decimal("10000"), "K_20": Decimal("2300")}


def _settle(sales: dict[str, Decimal], expenses) -> object:
    fields = dict(sales)
    for field, value in period_fields([], expenses).items():
        fields[field] = fields.get(field, Decimal("0")) + value
    return settle_vat(fields, expenses)


def test_reverse_charge_is_vat_neutral():
    """Import uslug z pelnym odliczeniem: nalezny i naliczony sie znosza."""
    s = _settle(SALES, [_expense(net="1000", vat="230", reverse_charge=True)])
    assert s.nalezny == Decimal("2530")  # 2300 sprzedaz + 230 samonaliczony
    assert s.naliczony == Decimal("230")
    assert s.to_pay == Decimal("2300")  # bez zmian wzgledem samej sprzedazy


def test_reverse_charge_without_deduction_increases_liability():
    """Brak prawa do odliczenia: samonaliczony VAT nalezny zostaje do zaplaty."""
    s = _settle(SALES, [_expense(net="1000", vat="230", reverse_charge=True, pct=Decimal("0"))])
    assert s.nalezny == Decimal("2530")
    assert s.naliczony == Decimal("0")
    assert s.to_pay == Decimal("2530")


def test_domestic_expense_only_reduces_liability():
    s = _settle(SALES, [_expense(net="1000", vat="230", country="PL")])
    assert s.nalezny == Decimal("2300")
    assert s.to_pay == Decimal("2070")


def test_partial_deduction_rounds_half_up_per_invoice():
    """50% z 23.03 = 11.515 -> 11.52 (HALF_UP), nie 11.51; w deklaracji pelne zlote."""
    expenses = [_expense(net="100", vat="23.03", country="PL", pct=Decimal("50"))]
    assert deductible_vat(expenses) == Decimal("11.52")
    assert settle_vat({"K_20": Decimal("100")}, expenses).naliczony == Decimal("12")


def test_declaration_totals_are_sums_of_rounded_fields():
    """P_38 = P_16 + P_20 (juz zaokraglone), P_51 = P_38 - P_48 — kontrole logiczne MF."""
    fields = {"K_16": Decimal("10.40"), "K_20": Decimal("20.40")}  # P_16 = 10, P_20 = 20
    s = settle_vat(fields, [_expense(net="219.57", vat="50.50", country="PL")])
    assert s.nalezny == Decimal("30")  # nie round(30.80) = 31
    assert (s.naliczony, s.to_pay) == (Decimal("51"), Decimal("0"))
    assert s.nadwyzka == Decimal("21")
    s = settle_vat({"K_20": Decimal("100.49")}, [_expense(net="219.57", vat="50.50", country="PL")])
    assert (s.nalezny, s.naliczony, s.to_pay) == (Decimal("100"), Decimal("51"), Decimal("49"))


def test_nadwyzka_when_input_exceeds_output():
    s = settle_vat({"K_20": Decimal("100")}, [_expense(net="1000", vat="230", country="PL")])
    assert s.to_pay == Decimal("0")
    assert s.nadwyzka == Decimal("130")


def test_dashboard_estimate_matches_declaration(isolated_db):
    """Szacunek z dashboardu == P_51 z wygenerowanego JPK_V7M (ten sam okres)."""
    from jdg_ksiegowy.status.dashboard import Dashboard
    from tests.helpers import ExpenseRow, InvoiceRow, save_expense, save_invoice

    save_invoice(
        InvoiceRow(
            id="i1",
            number="A1/05/2026",
            issue_date=date(2026, 5, 31),
            sale_date=date(2026, 5, 31),
            payment_due=date(2026, 6, 14),
            buyer_name="Klient",
            buyer_nip="5260250274",
            total_net=Decimal("10000"),
            total_vat=Decimal("2300"),
            total_gross=Decimal("12300"),
            vat_rate=Decimal("23"),
        )
    )
    save_expense(
        ExpenseRow(
            id="e1",
            seller_name="AWS EMEA",
            seller_nip="IE9692928F",
            seller_country="IE",
            document_number="EU-1",
            issue_date=date(2026, 5, 10),
            receive_date=date(2026, 5, 10),
            category="uslugi_obce",
            total_net=Decimal("1000"),
            total_vat=Decimal("230"),
            total_gross=Decimal("1230"),
            vat_rate=Decimal("23"),
            vat_deduction_pct=Decimal("0"),  # brak odliczenia -> VAT zostaje do zaplaty
            reverse_charge=True,
        )
    )

    snap = Dashboard(today=date(2026, 6, 7)).snapshot()
    vat_reminder = next(r for r in snap.reminders if r.key == "vat_jpk-2026-05")
    # 2300 sprzedaz + 230 samonaliczony, zero odliczenia.
    assert vat_reminder.amount == Decimal("2530")
