"""Klient KSeF oparty o ksef2 SDK.

Wrapper upraszczajacy integracje z KSeF API 2.0.
Obsluguje: sesje, wysylke faktur, sprawdzanie statusu, pobieranie UPO.

Wymaga: pip install ksef2
Dokumentacja ksef2: https://github.com/artpods56/ksef2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from jdg_ksiegowy.config import settings

logger = logging.getLogger(__name__)


@dataclass
class KSeFResult:
    """Wynik operacji KSeF."""

    success: bool
    reference_number: str | None = None
    session_token: str | None = None
    error: str | None = None
    details: dict = field(default_factory=dict)


class KSeFClient:
    """Klient KSeF API zbudowany na ksef2 SDK."""

    def __init__(self):
        self.env = settings.ksef.env
        self.nip = settings.ksef.nip
        self.token = settings.ksef.token
        self._session = None

    async def send_invoice(self, xml_content: str) -> KSeFResult:
        """Wyslij fakture XML do KSeF.

        Pipeline:
        1. Inicjalizacja sesji (token auth)
        2. Wyslanie faktury (base64-encoded XML)
        3. Pobranie numeru referencyjnego KSeF
        4. Zamkniecie sesji
        """
        try:
            from ksef2 import Client, Environment

            env_map = {
                "prod": Environment.PROD,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }

            client = Client(env_map[self.env])

            # Autentykacja tokenem
            if self.env == "test":
                auth = client.authentication.with_test_certificate(nip=self.nip)
            else:
                auth = client.authentication.with_token(
                    nip=self.nip,
                    token=self.token,
                )

            # Otworz sesje i wyslij
            with auth.online_session() as session:
                result = session.send_invoice(invoice_xml=xml_content.encode("utf-8"))
                ref_number = getattr(result, "element_reference_number", None) or str(result)

                logger.info("Faktura wyslana do KSeF: %s", ref_number)

                return KSeFResult(
                    success=True,
                    reference_number=ref_number,
                    details={"env": self.env},
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

    async def check_invoice_status(self, reference_number: str) -> KSeFResult:
        """Sprawdz status faktury w KSeF."""
        try:
            from ksef2 import Client, Environment

            env_map = {
                "prod": Environment.PROD,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }

            client = Client(env_map[self.env])
            status = client.invoice.get_status(reference_number)

            return KSeFResult(
                success=True,
                reference_number=reference_number,
                details={"status": str(status)},
            )
        except Exception as e:
            return KSeFResult(success=False, error=str(e))

    async def get_upo(self, reference_number: str) -> KSeFResult:
        """Pobierz UPO (Urzedowe Poswiadczenie Odbioru) dla faktury."""
        try:
            from ksef2 import Client, Environment

            env_map = {
                "prod": Environment.PROD,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }

            client = Client(env_map[self.env])

            auth = client.authentication.with_token(nip=self.nip, token=self.token)
            with auth.online_session() as session:
                upo = session.get_upo(reference_number)

                return KSeFResult(
                    success=True,
                    reference_number=reference_number,
                    details={"upo": str(upo)},
                )
        except Exception as e:
            return KSeFResult(success=False, error=str(e))

    def is_configured(self) -> bool:
        """Sprawdz czy KSeF jest skonfigurowany."""
        return bool(self.token) or self.env == "test"
