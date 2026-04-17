"""Modul kosztow (faktur zakupu).

Na ryczalcie koszty NIE pomniejszaja podatku, ale:
- musisz przechowywac dowody zakupu (art. 15 ust. 1 ustawy o ryczalcie)
- VAT naliczony idzie do JPK_V7M (sekcja zakupowa) jesli jestes VAT-owcem
"""

from jdg_ksiegowy.expenses.models import Expense, ExpenseCategory
from jdg_ksiegowy.expenses.ocr import (
    ClaudeOCR,
    ExpenseOCR,
    ExtractedExpense,
    FallbackOCR,
    OCRError,
    OllamaOCR,
    build_default_ocr,
)

__all__ = [
    "ClaudeOCR",
    "Expense",
    "ExpenseCategory",
    "ExpenseOCR",
    "ExtractedExpense",
    "FallbackOCR",
    "OCRError",
    "OllamaOCR",
    "build_default_ocr",
]
