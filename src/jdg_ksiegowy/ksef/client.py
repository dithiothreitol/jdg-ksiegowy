"""Klient KSeF 2.0 oparty o ksef2 SDK (>=0.11, OpenAPI 2.3.0).

Pipeline sesji online:
1. Client(Environment) -> Authentication (test-cert albo token KSeF)
2. auth.online_session(form_code=FormSchema.FA3) — SDK generuje klucze AES/RSA
3. session.send_invoice(invoice_xml=...) -> SendInvoiceResponse.reference_number
4. session.wait_for_invoice_ready(invoice_reference_number=ref)
5. session.get_invoice_upo_by_reference(ref) -> UPO (bytes/dict)
"""

from __future__ import annotations

import calendar
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from jdg_ksiegowy.config import settings

if TYPE_CHECKING:
    from ksef2.domain.models.invoices import InvoiceMetadata

logger = logging.getLogger(__name__)

# Limit zakresu dat zapytania o metadane KSeF — dzielimy dluzsze okresy na okna.
_MAX_QUERY_MONTHS = 2


def _add_months(d: date, months: int) -> date:
    """Dodaj `months` miesiecy do daty, przycinajac dzien do konca miesiaca."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_windows(date_from: date, date_to: date) -> Iterator[tuple[datetime, datetime]]:
    """Podziel [date_from, date_to] na okna <= _MAX_QUERY_MONTHS, jako granice datetime.

    KSeF ogranicza zakres pojedynczego zapytania o metadane — chunkujemy defensywnie.
    Zwraca granice datetime (poczatek dnia .. koniec dnia), bo InvoicesFilter
    oczekuje datetime, nie date.
    """
    cursor = date_from
    while cursor <= date_to:
        window_end = min(date_to, _add_months(cursor, _MAX_QUERY_MONTHS) - timedelta(days=1))
        yield datetime.combine(cursor, time.min), datetime.combine(window_end, time.max)
        cursor = window_end + timedelta(days=1)


@dataclass
class KSeFResult:
    """Wynik operacji KSeF."""

    success: bool
    reference_number: str | None = None
    error: str | None = None
    details: dict = field(default_factory=dict)


class KSeFClient:
    """Klient KSeF 2.0 API zbudowany na ksef2 SDK."""

    def __init__(self):
        self.env = settings.ksef.env
        self.nip = settings.ksef.nip
        self.token = settings.ksef.token
        self._authed = None  # AuthenticatedClient — leniwie, reuse w obrebie instancji

    def _authenticated_client(self):
        """Zaloguj sie do KSeF i zwroc AuthenticatedClient (synchronicznie).

        test env bez tokena -> certyfikat testowy (tylko NIP); inaczej token KSeF.
        Wynik cache'owany na instancji, by nie powtarzac handshake przy kolejnych
        operacjach (query_inbox + wielokrotne download_invoice_xml).
        """
        if self._authed is None:
            from ksef2 import Client, Environment

            env_map = {
                "prod": Environment.PRODUCTION,
                "production": Environment.PRODUCTION,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }
            client = Client(env_map[self.env])
            if self.env == "test" and not self.token:
                self._authed = client.authentication.with_test_certificate(nip=self.nip)
            else:
                self._authed = client.authentication.with_token(
                    ksef_token=self.token,
                    nip=self.nip,
                )
        return self._authed

    async def send_invoice(self, xml_content: str) -> KSeFResult:
        """Wyslij fakture XML FA(3) do KSeF i poczekaj na UPO.

        W KSeF 2.0 UPO pobiera sie w kontekscie otwartej sesji online — dlatego
        wysylka, oczekiwanie i pobranie UPO odbywaja sie jednym wywolaniem.
        """
        try:
            from ksef2 import FormSchema

            authed = self._authenticated_client()

            with authed.online_session(form_code=FormSchema.FA3) as session:
                result = session.send_invoice(invoice_xml=xml_content.encode("utf-8"))
                ref = result.reference_number

                session.wait_for_invoice_ready(invoice_reference_number=ref)
                upo = session.get_invoice_upo_by_reference(invoice_reference_number=ref)

                logger.info("Faktura wyslana do KSeF: %s", ref)

                return KSeFResult(
                    success=True,
                    reference_number=ref,
                    details={"env": self.env, "upo": upo},
                )

        except ImportError:
            logger.error("Biblioteka ksef2 nie jest zainstalowana: pip install ksef2")
            return KSeFResult(
                success=False,
                error="ksef2 nie zainstalowany. Uruchom: pip install ksef2",
            )
        except Exception as e:
            logger.error("Blad wysylki do KSeF: %s", e)
            return KSeFResult(success=False, error=str(e))

    def query_inbox(
        self,
        date_from: date,
        date_to: date,
        *,
        role: str = "buyer",
        include_corrections: bool = False,
        seller_nip: str | None = None,
    ) -> list[InvoiceMetadata]:
        """Pobierz metadane faktur z KSeF (domyslnie zakupowe — rola nabywcy).

        Zwraca surowe modele InvoiceMetadata z SDK (mapowanie domenowe poza klientem).
        Zakres dluzszy niz _MAX_QUERY_MONTHS dzielony na okna; wyniki deduplikowane
        po ksef_number (okna sa rozlaczne, ale to tani bezpiecznik).

        Synchroniczne — metody zapytan w ksef2 nie sa korutynami (inaczej niz
        wysylka, ktora wymaga online_session).
        """
        from ksef2.domain.models.invoices import InvoicesFilter

        invoice_types = ["vat", "zal", "roz"]
        if include_corrections:
            invoice_types += ["kor", "kor_zal", "kor_roz"]

        invoices = self._authenticated_client().invoices
        seen: set[str] = set()
        result: list[InvoiceMetadata] = []
        for window_from, window_to in _month_windows(date_from, date_to):
            filters = InvoicesFilter(
                role=role,
                date_type="invoicing_date",
                date_from=window_from,
                date_to=window_to,
                invoice_types=invoice_types,
                amount_type="brutto",  # wymagane przez SDK; bez amount_min/max nie filtruje
                seller_nip=seller_nip,
            )
            for meta in invoices.all_metadata(filters=filters):
                if meta.ksef_number in seen:
                    continue
                seen.add(meta.ksef_number)
                result.append(meta)
        return result

    def download_invoice_xml(self, ksef_number: str) -> bytes:
        """Pobierz XML faktury (FA) po numerze KSeF."""
        return self._authenticated_client().invoices.download_invoice(ksef_number=ksef_number)

    def is_configured(self) -> bool:
        """KSeF test akceptuje test-certificate (tylko NIP). Pozostale env wymagaja tokena."""
        if not self.nip:
            return False
        if self.env == "test":
            return True
        return bool(self.token)
