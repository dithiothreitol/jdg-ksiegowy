"""Klient KSeF 2.0 na ksef2 SDK (>=1.3).

Wysylka w sesji online:
1. Client(Environment) -> uwierzytelnienie (token KSeF albo certyfikat testowy)
2. online_session(form_code=FA3) — SDK generuje klucze AES/RSA
3. session.send_invoice(xml) -> InvoiceSubmission (numer referencyjny wysylki)
4. submission.wait() -> status z NUMEREM KSeF i data przyjecia
5. submission.download_upo() -> UPO faktury (XML)

Numer referencyjny wysylki i numer KSeF to dwa rozne identyfikatory — do JPK
trafia wylacznie numer KSeF.
"""

from __future__ import annotations

import calendar
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal

from jdg_ksiegowy.config import settings

if TYPE_CHECKING:
    from ksef2.clients import AuthenticatedClient, InvoiceSubmission
    from ksef2.models import InvoiceMetadata

logger = logging.getLogger(__name__)

InvoiceType = Literal["vat", "zal", "roz", "kor", "kor_zal", "kor_roz"]

# Limit zakresu dat zapytania o metadane KSeF — dluzsze okresy dzielimy na okna.
_MAX_QUERY_MONTHS = 2
_SUBMIT_TIMEOUT_SEC = 120.0


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _month_windows(date_from: date, date_to: date) -> Iterator[tuple[datetime, datetime]]:
    """Podziel [date_from, date_to] na okna <= _MAX_QUERY_MONTHS (granice datetime)."""
    cursor = date_from
    while cursor <= date_to:
        window_end = min(date_to, _add_months(cursor, _MAX_QUERY_MONTHS) - timedelta(days=1))
        yield datetime.combine(cursor, time.min), datetime.combine(window_end, time.max)
        cursor = window_end + timedelta(days=1)


@dataclass(frozen=True)
class KSeFResult:
    """Wynik wysylki faktury do KSeF."""

    success: bool
    env: str
    reference_number: str | None = None
    ksef_number: str | None = None
    acquired_at: datetime | None = None
    upo: bytes | None = None
    error: str | None = None
    rejected: bool = False  # KSeF odrzucil tresc — po poprawce fakture mozna wyslac ponownie


def _download_upo(submission: InvoiceSubmission) -> bytes | None:
    """UPO po nadaniu numeru KSeF; jego chwilowy brak nie cofa przyjecia faktury."""
    from ksef2 import KSeFException

    try:
        return submission.download_upo()
    except KSeFException as e:
        logger.warning("UPO jeszcze niedostepne (%s) — numer KSeF jest juz nadany", e)
        return None


class KSeFClient:
    """Klient KSeF 2.0 zbudowany na ksef2 SDK."""

    def __init__(self) -> None:
        self.env = settings.ksef.env
        self.nip = settings.ksef.nip or settings.seller.nip
        self.token = settings.ksef.token
        self._authed: AuthenticatedClient | None = None

    def _authenticated_client(self) -> AuthenticatedClient:
        """Zaloguj sie (raz na instancje): test bez tokena -> certyfikat testowy."""
        if self._authed is None:
            from ksef2 import Client, Environment

            env_map = {
                "prod": Environment.PRODUCTION,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }
            client = Client(env_map[self.env])
            if self.env == "test" and not self.token:
                self._authed = client.authentication.with_test_certificate(nip=self.nip)
            else:
                self._authed = client.authentication.with_token(ksef_token=self.token, nip=self.nip)
        return self._authed

    def send_invoice(self, xml_content: str) -> KSeFResult:
        """Wyslij fakture FA(3), poczekaj na nadanie numeru KSeF i pobierz UPO.

        Po przyjeciu wysylki wynik zawsze niesie numer referencyjny — rowniez gdy KSeF nie
        zdazyl nadac numeru — zeby rejestr mogl zablokowac ponowna wysylke tej faktury.
        """
        from ksef2 import FormSchema, KSeFException, KSeFInvoiceRejectedError

        reference: str | None = None
        try:
            authed = self._authenticated_client()
            with authed.online_session(form_code=FormSchema.FA3) as session:
                submission = session.send_invoice(xml_content.encode("utf-8"))
                reference = submission.reference_number
                status = submission.wait(timeout=_SUBMIT_TIMEOUT_SEC)
                upo = _download_upo(submission)
        except KSeFInvoiceRejectedError as e:
            logger.error("KSeF odrzucil fakture: %s", e)
            return KSeFResult(
                success=False, env=self.env, reference_number=reference, rejected=True, error=str(e)
            )
        except KSeFException as e:  # blad API/sieci albo przekroczony czas przetwarzania
            logger.error("Blad wysylki do KSeF: %s", e)
            return KSeFResult(success=False, env=self.env, reference_number=reference, error=str(e))

        if not status.ksef_number:
            return KSeFResult(
                success=False,
                env=self.env,
                reference_number=reference,
                error="KSeF nie nadal jeszcze numeru (faktura w toku)",
            )
        logger.info("Faktura przyjeta w KSeF: %s", status.ksef_number)
        return KSeFResult(
            success=True,
            env=self.env,
            reference_number=reference,
            ksef_number=status.ksef_number,
            acquired_at=status.acquisition_date,
            upo=upo,
        )

    def query_metadata(
        self,
        date_from: date,
        date_to: date,
        *,
        role: Literal["buyer", "seller"] = "buyer",
        include_corrections: bool = False,
        seller_nip: str | None = None,
    ) -> list[InvoiceMetadata]:
        """Metadane faktur z KSeF (domyslnie zakupowe — rola nabywcy).

        Zakres dluzszy niz _MAX_QUERY_MONTHS dzielony na okna; wyniki
        deduplikowane po numerze KSeF.
        """
        from ksef2.models import InvoicesFilter

        invoice_types: list[InvoiceType] = ["vat", "zal", "roz"]
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
                amount_type="brutto",
                seller_nip=seller_nip,
            )
            for meta in invoices.all_metadata(filters=filters):
                if meta.ksef_number not in seen:
                    seen.add(meta.ksef_number)
                    result.append(meta)
        return result

    def download_invoice_xml(self, ksef_number: str) -> bytes:
        """Pobierz XML faktury po numerze KSeF."""
        return self._authenticated_client().invoices.download_invoice(ksef_number=ksef_number)

    def is_configured(self) -> bool:
        """Test akceptuje certyfikat testowy (sam NIP); pozostale srodowiska wymagaja tokena."""
        if not self.nip:
            return False
        return self.env == "test" or bool(self.token)
