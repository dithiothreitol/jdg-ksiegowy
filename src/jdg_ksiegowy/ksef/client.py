"""Klient KSeF 2.0 oparty o ksef2 SDK (>=0.11, OpenAPI 2.3.0).

Pipeline sesji online:
1. Client(Environment) -> Authentication (test-cert albo token KSeF)
2. auth.online_session(form_code=FormSchema.FA3) — SDK generuje klucze AES/RSA
3. session.send_invoice(invoice_xml=...) -> SendInvoiceResponse.reference_number
4. session.wait_for_invoice_ready(invoice_reference_number=ref)
5. session.get_invoice_upo_by_reference(ref) -> UPO (bytes/dict)
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
    error: str | None = None
    details: dict = field(default_factory=dict)


class KSeFClient:
    """Klient KSeF 2.0 API zbudowany na ksef2 SDK."""

    def __init__(self):
        self.env = settings.ksef.env
        self.nip = settings.ksef.nip
        self.token = settings.ksef.token

    async def send_invoice(self, xml_content: str) -> KSeFResult:
        """Wyslij fakture XML FA(3) do KSeF i poczekaj na UPO.

        W KSeF 2.0 UPO pobiera sie w kontekscie otwartej sesji online — dlatego
        wysylka, oczekiwanie i pobranie UPO odbywaja sie jednym wywolaniem.
        """
        try:
            from ksef2 import Client, Environment, FormSchema

            env_map = {
                "prod": Environment.PRODUCTION,
                "production": Environment.PRODUCTION,
                "test": Environment.TEST,
                "demo": Environment.DEMO,
            }

            client = Client(env_map[self.env])

            if self.env == "test" and not self.token:
                auth = client.authentication.with_test_certificate(nip=self.nip)
            else:
                auth = client.authentication.with_token(
                    ksef_token=self.token,
                    nip=self.nip,
                )

            with auth.online_session(form_code=FormSchema.FA3) as session:
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

    def is_configured(self) -> bool:
        """KSeF test akceptuje test-certificate (tylko NIP). Pozostale env wymagaja tokena."""
        if not self.nip:
            return False
        if self.env == "test":
            return True
        return bool(self.token)
