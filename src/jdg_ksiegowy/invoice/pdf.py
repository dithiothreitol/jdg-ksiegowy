"""Konwersja DOCX -> PDF przez LibreOffice headless.

LibreOffice jest cross-platform, darmowy i nie wymaga Worda. Na Oracle Cloud
(ARM) dziala z paczki `libreoffice`. Alternatywy (Word / docx2pdf) wymagaja
MS Office i nie nadaja sie do serwera.

Wymagania:
- LibreOffice >= 7.x
- `soffice` albo `libreoffice` w PATH (lub ustaw LIBREOFFICE_BIN w .env)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class PDFConversionError(Exception):
    """LibreOffice nie zdolal skonwertowac dokumentu."""


def _find_soffice() -> str:
    """Zwroc sciezke do `soffice` (linux/mac) lub `soffice.exe` (windows)."""
    override = os.environ.get("LIBREOFFICE_BIN")
    if override and Path(override).exists():
        return override
    for cmd in ("soffice", "libreoffice", "soffice.exe"):
        found = shutil.which(cmd)
        if found:
            return found
    raise PDFConversionError(
        "LibreOffice nie znaleziony. Zainstaluj (libreoffice package) "
        "albo ustaw LIBREOFFICE_BIN w .env."
    )


def docx_to_pdf(docx_path: Path, output_dir: Path | None = None) -> Path:
    """Skonwertuj DOCX do PDF. Zwroc sciezke wygenerowanego pliku.

    Args:
        docx_path: plik DOCX do konwersji
        output_dir: folder docelowy (domyslnie obok docx_path)
    """
    docx_path = docx_path.resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX nie istnieje: {docx_path}")

    output_dir = (output_dir or docx_path.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    soffice = _find_soffice()
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise PDFConversionError(
            f"soffice exit {result.returncode}: {result.stderr.strip() or result.stdout.strip()}"
        )

    pdf_path = output_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise PDFConversionError(
            f"soffice nie utworzyl PDF-a w {output_dir} (oczekiwano {pdf_path.name})"
        )
    return pdf_path
