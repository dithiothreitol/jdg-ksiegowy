"""Klient REST bramki MF dla JPK_V7M / JPK_EWP.

Flow (wg Specyfikacji Interfejsow Uslug JPK v4.2):
1. zaszyfruj XML (AES-256-CBC + RSA dla klucza)
2. POST /api/Storage/InitUploadSigned (z metadanymi i danymi autoryzujacymi)
   -> ReferenceNumber + SAS URL-e do Azure Blob
3. PUT zaszyfrowanego pliku na SAS URL
4. POST /api/Storage/FinishUpload
5. polling GET /api/Storage/Status/{ReferenceNumber} co 10-30s
   az status 200 (OK + UPO Base64) lub 4xx (blad)

UWAGA: do potwierdzenia na sandboxie MF:
- dokladna nazwa endpointu dla danych autoryzujacych (vs. podpis kwal.)
- format metadanych XML (osobny schemat InitUpload-Document)
- czy SAS-y oddzielne dla pliku/metadanych/podpisu
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path

from datetime import timedelta

import httpx

from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.mf_gateway.auth import AuthorizationData, build_authorization_xml
from jdg_ksiegowy.mf_gateway.crypto import EncryptedPayload, encrypt_jpk, load_mf_public_key
from jdg_ksiegowy.mf_gateway.public_key import MFPublicKeyRegistry
from jdg_ksiegowy.tax.validation import JPKValidator, XSDValidationError

STATUS_POLL_INTERVAL_SEC = 15
STATUS_TIMEOUT_SEC = 600  # max 10 min na przetworzenie


@dataclass
class SubmitResult:
    success: bool
    reference_number: str | None = None
    upo_base64: str | None = None
    status_code: int | None = None
    error: str | None = None


class MFGatewayClient:
    """Klient bramki MF (REST) dla JPK_V7M i JPK_EWP."""

    def __init__(
        self,
        base_url: str | None = None,
        cert_path: str | None = None,
        cert_url: str | None = None,
        timeout: float = 60.0,
        registry: MFPublicKeyRegistry | None = None,
    ):
        cfg = settings.mf
        self.base_url = base_url or cfg.base_url
        self.cert_path = cert_path or cfg.cert_path
        self.timeout = timeout
        self._registry = registry or MFPublicKeyRegistry(
            cache_dir=DATA_DIR / "mf_cert",
            env=cfg.env,
            cert_url=cert_url or cfg.cert_url,
            ttl=timedelta(days=cfg.cert_ttl_days),
        )

    def _public_key(self):
        # Override: lokalny plik PEM/DER przez MF_CERT_PATH ma pierwszenstwo
        if self.cert_path:
            return load_mf_public_key(self.cert_path)
        # Domyslnie: auto-pobieranie z cache + TTL
        return self._registry.get().key

    def _encrypt(self, xml: str, inner_filename: str) -> EncryptedPayload:
        return encrypt_jpk(xml.encode("utf-8"), self._public_key(), inner_filename)

    async def submit(
        self,
        xml: str,
        auth: AuthorizationData,
        inner_filename: str = "jpk.xml",
        poll_interval: int = STATUS_POLL_INTERVAL_SEC,
        timeout_sec: int = STATUS_TIMEOUT_SEC,
    ) -> SubmitResult:
        """Pelny flow: encrypt -> init -> upload -> finish -> poll."""
        try:
            payload = self._encrypt(xml, inner_filename)
        except Exception as e:
            return SubmitResult(success=False, error=f"encrypt_failed: {e}")

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as http:
            try:
                ref_num, blob_url = await self._init_upload(http, payload, auth)
            except Exception as e:
                return SubmitResult(success=False, error=f"init_failed: {e}")

            try:
                await self._upload_blob(http, blob_url, payload.ciphertext)
            except Exception as e:
                return SubmitResult(
                    success=False, reference_number=ref_num, error=f"upload_failed: {e}"
                )

            try:
                await self._finish_upload(http, ref_num)
            except Exception as e:
                return SubmitResult(
                    success=False, reference_number=ref_num, error=f"finish_failed: {e}"
                )

            return await self._poll_status(http, ref_num, poll_interval, timeout_sec)

    async def _init_upload(
        self,
        http: httpx.AsyncClient,
        payload: EncryptedPayload,
        auth: AuthorizationData,
    ) -> tuple[str, str]:
        """POST init -> ReferenceNumber + SAS URL.

        Body wg spec v4.2: metadane dokumentu (rozmiar, hash) + zaszyfrowany klucz AES + IV
        + dane autoryzujace. Format: JSON z polami Base64 dla blob danych.
        """
        body = {
            "DocumentMetadata": {
                "DocumentSize": payload.plaintext_size,
                "DocumentZipSize": payload.zip_size,
                "EncryptedKey": base64.b64encode(payload.encrypted_aes_key).decode("ascii"),
                "IV": base64.b64encode(payload.iv).decode("ascii"),
            },
            "Authorization": build_authorization_xml(auth),
        }
        resp = await http.post("/api/Storage/InitUploadSigned", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["ReferenceNumber"], data["BlobUploadUrl"]

    async def _upload_blob(
        self, http: httpx.AsyncClient, blob_url: str, ciphertext: bytes
    ) -> None:
        """PUT zaszyfrowanego pliku na Azure Blob Storage przez SAS."""
        async with httpx.AsyncClient(timeout=self.timeout) as blob_http:
            resp = await blob_http.put(
                blob_url,
                content=ciphertext,
                headers={"x-ms-blob-type": "BlockBlob"},
            )
            resp.raise_for_status()

    async def _finish_upload(self, http: httpx.AsyncClient, reference_number: str) -> None:
        resp = await http.post(
            "/api/Storage/FinishUpload",
            json={"ReferenceNumber": reference_number},
        )
        resp.raise_for_status()

    async def _poll_status(
        self,
        http: httpx.AsyncClient,
        reference_number: str,
        poll_interval: int,
        timeout_sec: int,
    ) -> SubmitResult:
        elapsed = 0
        while elapsed < timeout_sec:
            resp = await http.get(f"/api/Storage/Status/{reference_number}")
            if resp.status_code != 200:
                return SubmitResult(
                    success=False,
                    reference_number=reference_number,
                    status_code=resp.status_code,
                    error=f"status_http_{resp.status_code}",
                )
            data = resp.json()
            code = data.get("Code")
            if code == 200:
                return SubmitResult(
                    success=True,
                    reference_number=reference_number,
                    status_code=200,
                    upo_base64=data.get("Upo"),
                )
            if code is not None and code >= 400:
                return SubmitResult(
                    success=False,
                    reference_number=reference_number,
                    status_code=code,
                    error=data.get("Description") or f"mf_error_{code}",
                )
            # 100 / 300 — w toku
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return SubmitResult(
            success=False,
            reference_number=reference_number,
            error=f"timeout_after_{timeout_sec}s",
        )

    @staticmethod
    def save_upo(upo_base64: str, output_path: Path) -> Path:
        """Zapisz UPO (PDF lub XML zwrocony przez MF) na dysk."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(upo_base64))
        return output_path
