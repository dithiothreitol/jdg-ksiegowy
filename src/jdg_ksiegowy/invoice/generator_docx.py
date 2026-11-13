"""Generator faktur w formacie DOCX (python-docx)."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.invoice.models import Invoice, InvoiceKind
from jdg_ksiegowy.ksef.qr import qr_png

NBSP = " "
# A4 z marginesami 1,5 cm: 18 cm szerokosci na tabele.
PAGE_MARGIN = Cm(1.5)
PARTY_WIDTHS = [Cm(9), Cm(9)]
ITEM_COLUMNS = [
    ("Lp", Cm(0.8)),
    ("Opis", Cm(5.2)),
    ("Ilość", Cm(1.3)),
    ("J.m.", Cm(1.1)),
    ("Cena netto", Cm(2.1)),
    ("Wart. netto", Cm(2.2)),
    ("VAT %", Cm(1.2)),
    ("Kwota VAT", Cm(1.9)),
    ("Wart. brutto", Cm(2.2)),
]


def _amount(value: Decimal) -> str:
    """Zapis polski: twarda spacja tysiecy (kwota sie nie lamie) i przecinek dziesietny."""
    return f"{value:,.2f}".replace(",", NBSP).replace(".", ",")


def _format_pln(amount: Decimal) -> str:
    return f"{_amount(amount)}{NBSP}PLN"


def _set_widths(table, widths) -> None:
    """LibreOffice (PDF dla klienta) czyta siatke tabeli (w:gridCol), Word komorki (w:tcW)."""
    table.autofit = False
    for column, width in zip(table.columns, widths, strict=True):
        column.width = width
    for row in table.rows:
        for cell, width in zip(row.cells, widths, strict=True):
            cell.width = width


def _format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _set_cell_text(cell, text: str, bold: bool = False, align: str = "left", size: int = 9):
    """Ustaw tekst komorki tabeli."""
    cell.text = ""
    p = cell.paragraphs[0]
    if align == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold


def generate_invoice_docx(invoice: Invoice, output_path: Path, qr_url: str | None = None) -> Path:
    """Wizualizacja faktury (VAT lub korekty) w DOCX.

    Z numerem KSeF i `qr_url` dokument zawiera kod QR weryfikacji (KOD I) — wymagany, gdy
    fakture ustrukturyzowana przekazuje sie nabywcy poza KSeF (np. PDF mailem).
    """
    seller = settings.seller
    doc = Document()

    # --- Strona A4 (szablon python-docx ma domyslnie format Letter) ---
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = PAGE_MARGIN
    section.top_margin = section.bottom_margin = PAGE_MARGIN

    # --- Styl dokumentu ---
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    # --- Naglowek: FAKTURA VAT ---
    title = "FAKTURA KORYGUJĄCA" if invoice.kind is InvoiceKind.KOR else "FAKTURA VAT"
    heading = doc.add_heading(f"{title} nr {invoice.number}", level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0, 0, 0)

    # --- Daty ---
    dates_para = doc.add_paragraph()
    dates_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    dates_para.add_run(f"Data wystawienia: {_format_date(invoice.issue_date)}\n").font.size = Pt(9)
    dates_para.add_run(f"Data sprzedaży: {_format_date(invoice.sale_date)}\n").font.size = Pt(9)
    dates_para.add_run(f"Termin płatności: {_format_date(invoice.payment_due)}").font.size = Pt(9)

    if invoice.period_from and invoice.period_to:
        dates_para.add_run(
            f"\nOkres: {_format_date(invoice.period_from)} - {_format_date(invoice.period_to)}"
        ).font.size = Pt(9)

    if invoice.kind is InvoiceKind.KOR:
        corr = doc.add_paragraph()
        original = f"Korekta faktury nr {invoice.corrected_number}"
        if invoice.corrected_issue_date:
            original += f" z dnia {_format_date(invoice.corrected_issue_date)}"
        if invoice.corrected_ksef_number:
            original += f" (KSeF: {invoice.corrected_ksef_number})"
        corr.add_run(original + "\n").bold = True
        corr.add_run(f"Przyczyna korekty: {invoice.correction_reason or '-'}")

    # --- Sprzedawca / Nabywca (tabela 2 kolumny) ---
    parties_table = doc.add_table(rows=1, cols=2)
    parties_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Sprzedawca
    seller_cell = parties_table.cell(0, 0)
    seller_cell.text = ""
    p = seller_cell.paragraphs[0]
    p.add_run("SPRZEDAWCA\n").bold = True
    p.add_run(f"{seller.name}\n")
    p.add_run(f"{seller.address}\n")
    p.add_run(f"NIP: {seller.nip}\n")
    p.add_run(f"Bank: {seller.bank_name}\n")
    p.add_run(f"Nr konta: {seller.bank_account}")

    # Nabywca
    buyer_cell = parties_table.cell(0, 1)
    buyer_cell.text = ""
    p = buyer_cell.paragraphs[0]
    p.add_run("NABYWCA\n").bold = True
    p.add_run(f"{invoice.buyer.name}\n")
    p.add_run(f"{invoice.buyer.address}\n")
    id_type, id_value = invoice.buyer.identifier_for_xml()
    p.add_run({"NIP": f"NIP: {id_value}", "NrVatUE": f"VAT UE: {id_value}"}.get(id_type, ""))
    _set_widths(parties_table, PARTY_WIDTHS)

    doc.add_paragraph()  # spacer

    # --- Tabela pozycji ---
    headers = [name for name, _ in ITEM_COLUMNS]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Naglowki
    for i, h in enumerate(headers):
        _set_cell_text(table.rows[0].cells[i], h, bold=True, align="center", size=8)

    # Pozycje
    for idx, item in enumerate(invoice.items, 1):
        row = table.add_row()
        cells = row.cells
        _set_cell_text(cells[0], str(idx), align="center")
        _set_cell_text(cells[1], item.description)
        _set_cell_text(cells[2], f"{item.quantity.normalize():f}".replace(".", ","), align="center")
        _set_cell_text(cells[3], item.unit, align="center")
        _set_cell_text(cells[4], _amount(item.unit_price_net), align="right")
        _set_cell_text(cells[5], _amount(item.net_value), align="right")
        rate = item.vat_code.lower() if item.vat_code else f"{item.vat_rate.normalize():f}%"
        _set_cell_text(cells[6], rate, align="center")
        _set_cell_text(cells[7], _amount(item.vat_amount), align="right")
        _set_cell_text(cells[8], _amount(item.gross_value), align="right")

    # Wiersz podsumowania
    summary_row = table.add_row()
    _set_cell_text(summary_row.cells[0], "")
    _set_cell_text(summary_row.cells[1], "RAZEM", bold=True, align="right")
    _set_cell_text(summary_row.cells[2], "")
    _set_cell_text(summary_row.cells[3], "")
    _set_cell_text(summary_row.cells[4], "")
    _set_cell_text(summary_row.cells[5], _amount(invoice.total_net), bold=True, align="right")
    _set_cell_text(summary_row.cells[6], "")
    _set_cell_text(summary_row.cells[7], _amount(invoice.total_vat), bold=True, align="right")
    _set_cell_text(summary_row.cells[8], _amount(invoice.total_gross), bold=True, align="right")
    _set_widths(table, [width for _, width in ITEM_COLUMNS])

    doc.add_paragraph()  # spacer

    # --- Podsumowanie kwot ---
    summary = doc.add_paragraph()
    summary.add_run(f"Do zapłaty: {_format_pln(invoice.total_gross)}\n").bold = True
    summary.add_run("Forma płatności: przelew bankowy\n")
    summary.add_run(f"Nr konta: {seller.bank_account}\n")
    summary.add_run(f"Termin płatności: {_format_date(invoice.payment_due)}")

    if invoice.notes:
        doc.add_paragraph()
        doc.add_paragraph(f"Uwagi: {invoice.notes}")

    if invoice.ksef_number:
        doc.add_paragraph()
        ksef = doc.add_paragraph()
        ksef.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if qr_url:
            ksef.add_run().add_picture(io.BytesIO(qr_png(qr_url)), width=Cm(3.5))
            ksef.add_run("\n")
        ksef.add_run(f"Numer KSeF: {invoice.ksef_number}").bold = True

    # --- Stopka ---
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("Dokument wygenerowany elektronicznie — nie wymaga podpisu")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(128, 128, 128)

    # Zapisz
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path
