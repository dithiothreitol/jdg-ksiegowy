"""Wizualizacja faktury DOCX, z ktorej LibreOffice robi PDF dla klienta.

LibreOffice bierze szerokosci kolumn z siatki tabeli (w:gridCol), a nie z komorek, wiec bez niej
kolumny wychodza rowne i kwoty lamia sie w polowie ("1230.0 / 0").
"""

from datetime import date
from decimal import Decimal

import pytest
from docx import Document
from docx.shared import Cm

from jdg_ksiegowy.invoice.generator_docx import ITEM_COLUMNS, generate_invoice_docx
from jdg_ksiegowy.invoice.models import Buyer, Invoice, LineItem

NBSP = " "


@pytest.fixture
def docx(tmp_path):
    invoice = Invoice(
        number="A1/11/2026",
        issue_date=date(2026, 11, 13),
        sale_date=date(2026, 11, 13),
        payment_due=date(2026, 11, 27),
        buyer=Buyer(name="Firma Przykładowa", nip="5260250274", address="ul. Testowa 5"),
        items=[
            LineItem(description="Usługa doradcza", unit="szt", unit_price_net=Decimal("12000"))
        ],
    )
    return Document(str(generate_invoice_docx(invoice, tmp_path / "f.docx")))


def _cm(emu) -> float:
    # Word zapisuje wymiary w twipsach, wiec odczyt rozni sie od Cm(...) o ulamek milimetra.
    return round(int(emu) / int(Cm(1)), 2)


def test_page_is_a4(docx):
    section = docx.sections[0]
    assert (_cm(section.page_width), _cm(section.page_height)) == (21.0, 29.7)


def test_item_table_grid_carries_column_widths(docx):
    grid = [_cm(col.w) for col in docx.tables[1]._tbl.tblGrid.gridCol_lst]
    assert grid == [_cm(width) for _, width in ITEM_COLUMNS]
    assert sum(grid) == pytest.approx(18.0, abs=0.02)


def test_polish_labels_and_amounts(docx):
    text = "\n".join(p.text for p in docx.paragraphs)
    cells = [cell.text for row in docx.tables[1].rows for cell in row.cells]
    assert "Data sprzedaży: 13.11.2026" in text and "Termin płatności: 27.11.2026" in text
    assert f"Do zapłaty: 14{NBSP}760,00{NBSP}PLN" in text
    assert "Ilość" in cells
    assert f"12{NBSP}000,00" in cells and f"2{NBSP}760,00" in cells and f"14{NBSP}760,00" in cells
