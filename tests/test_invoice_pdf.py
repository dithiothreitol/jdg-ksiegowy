"""Testy konwersji DOCX -> PDF (mock subprocess)."""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def pdf_module():
    from jdg_ksiegowy.invoice import pdf

    return pdf


def test_raises_when_docx_missing(pdf_module, tmp_path):
    with pytest.raises(FileNotFoundError):
        pdf_module.docx_to_pdf(tmp_path / "missing.docx")


def test_raises_when_libreoffice_not_found(pdf_module, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_module.settings, "libreoffice_bin", "")
    docx = tmp_path / "f.docx"
    docx.write_bytes(b"PK")  # fake DOCX

    with patch.object(pdf_module.shutil, "which", return_value=None):
        with pytest.raises(pdf_module.PDFConversionError, match="LibreOffice nie znaleziony"):
            pdf_module.docx_to_pdf(docx)


def test_uses_libreoffice_bin_override(pdf_module, tmp_path, monkeypatch):
    fake_bin = tmp_path / "soffice"
    fake_bin.write_text("#!/bin/bash\nexit 0\n")
    monkeypatch.setattr(pdf_module.settings, "libreoffice_bin", str(fake_bin))

    docx = tmp_path / "f.docx"
    docx.write_bytes(b"PK")

    with patch.object(pdf_module.subprocess, "run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = ""
        # Symuluj utworzenie PDF
        (tmp_path / "f.pdf").write_bytes(b"%PDF")

        result = pdf_module.docx_to_pdf(docx)

    assert result == (tmp_path / "f.pdf").resolve()
    assert run_mock.call_args.args[0][0] == str(fake_bin)


def test_raises_when_soffice_returncode_nonzero(pdf_module, tmp_path, monkeypatch):
    fake_bin = tmp_path / "soffice"
    fake_bin.write_text("#!/bin/bash\nexit 1\n")
    monkeypatch.setattr(pdf_module.settings, "libreoffice_bin", str(fake_bin))

    docx = tmp_path / "f.docx"
    docx.write_bytes(b"PK")

    with patch.object(pdf_module.subprocess, "run") as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = "error parsing"

        with pytest.raises(pdf_module.PDFConversionError, match="exit 1"):
            pdf_module.docx_to_pdf(docx)
