"""Klient REST bramki MF dla JPK_V7M / JPK_EWP.

Flow wg Specyfikacji Interfejsow Uslug JPK v5.4 (sekcja 2.2):

1. Przygotowanie payloadu (crypto.encrypt_jpk):
   XML -> ZIP(deflate) -> AES-256-CBC/PKCS#7 -> ciphertext
   klucz AES -> RSA-ECB-PKCS#1v15 kluczem publicznym MF

2. Przygotowanie AuthData (dla JDG bez podpisu kwalifikowanego):
   DaneAutoryzujace XML (SIG-2008) -> AES-256-CBC tym samym kluczem+IV -> base64

3. POST application/xml -> /api/Storage/InitUploadSigned
   Body: InitUpload XML z EncryptionKey, DocumentList, AuthData
   Response: {ReferenceNumber, TimeoutInSec, RequestToUploadFileList: [{Url, Method, HeaderList}]}

4. PUT ciphertext na Azure Blob (URL + headery z RequestToUploadFileList)

5. POST application/json -> /api/Storage/FinishUpload
   Body: {ReferenceNumber, AzureBlobNameList}

6. Polling GET /api/Storage/Status/{ReferenceNumber}
   az status 200 (OK + UPO Base64) lub 4xx (blad)
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import httpx

from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.mf_gateway.auth import AuthorizationData, build_authorization_xml
from jdg_ksiegowy.mf_gateway.crypto import (
    EncryptedPayload,
    aes_encrypt_cbc,
    encrypt_jpk,
    load_mf_public_key,
    md5_b64,
    sha256_b64,
)
from jdg_ksiegowy.mf_gateway.metadata import (
    DocumentMetadata,
    build_init_upload_xml,
    encrypted_filename_for,
    extract_jpk_form_code,
)
from jdg_ksiegowy.mf_gateway.public_key import MFPublicKeyRegistry

STATUS_POLL_INTERVAL_SEC = 15
STATUS_TIMEOUT_SEC = 600  # max 10 min na przetworzenie


@dataclass
class SubmitResult:
    success: bool
    reference_number: str | None = None
    upo_base64: str | None = None
    status_code: int | None = None
    error: str | None = None


@dataclass
class _UploadTarget:
    """Jeden plik do uploadu na Azure Blob (z InitUpload response)."""
    blob_name: str
    url: str
    method: str
    headers: dict[str, str]


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
        if self.cert_path:
            return load_mf_public_key(self.cert_path)
        return self._registry.get().key

    def _encrypt(self, xml: str, inner_filename: str) -> EncryptedPayload:
        return encrypt_jpk(xml.encode("utf-8"), self._public_key(), inner_filename)

    def _build_init_upload_body(
        self, payload: EncryptedPayload, auth: AuthorizationData, xml_filename: str,
    ) -> bytes:
        """Zbuduj kompletny dokument InitUpload XML z zaszyfrowanym AuthData."""
        form_code, system_code, schema_version = extract_jpk_form_code(payload.plaintext)

        # AuthData: DaneAutoryzujace XML -> AES-CBC tym samym kluczem i IV co JPK
        # (spec 5.4 sekcja 1.3.2: "ten sam klucz"; IV nie-prepended bo IV jest
        # juz zadeklarowany w metadanych InitUpload/Encryption/AES/IV)
        auth_xml = build_authorization_xml(auth)
        auth_encrypted = aes_encrypt_cbc(auth_xml, payload.aes_key, payload.iv)
        auth_data_b64 = base64.b64encode(auth_encrypted).decode("ascii")

        doc = DocumentMetadata(
            form_code=form_code,
            system_code=system_code,
            schema_version=schema_version,
            filename=xml_filename,
            content_length=payload.plaintext_size,
            hash_sha256_b64=sha256_b64(payload.plaintext),
            encrypted_filename=encrypted_filename_for(xml_filename),
            encrypted_length=len(payload.ciphertext),
            encrypted_md5_b64=md5_b64(payload.ciphertext),
        )
        return build_init_upload_xml(
            doc=doc,
            encrypted_aes_key_b64=base64.b64encode(payload.encrypted_aes_key).decode("ascii"),
            iv_b64=base64.b64encode(payload.iv).decode("ascii"),
            auth_data_b64=auth_data_b64,
        )

    async def submit(
        self,
        xml: str,
        auth: AuthorizationData,
        xml_filename: str = "jpk.xml",
        poll_interval: int = STATUS_POLL_INTERVAL_SEC,
        timeout_sec: int = STATUS_TIMEOUT_SEC,
    ) -> SubmitResult:
        """Pelny flow: encrypt -> init -> upload -> finish -> poll.

        Args:
            xml: tresc pliku JPK (pelny XML)
            auth: DaneAutoryzujace (NIP/PESEL + kwota przychodu)
            xml_filename: nazwa pliku XML (np. "JPK_V7M_2026_03.xml")
                          uzywane w metadanych i FileName bloba
        """
        try:
            payload = self._encrypt(xml, xml_filename)
            init_body = self._build_init_upload_body(payload, auth, xml_filename)
        except Exception as e:
            return SubmitResult(success=False, error=f"encrypt_failed: {e}")

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as http:
            try:
                ref_num, targets = await self._init_upload(http, init_body)
            except Exception as e:
                return SubmitResult(success=False, error=f"init_failed: {e}")

            if not targets:
                return SubmitResult(
                    success=False, reference_number=ref_num,
                    error="init_returned_no_upload_targets",
                )

            try:
                for target in targets:
                    await self._upload_blob(target, payload.ciphertext)
            except Exception as e:
                return SubmitResult(
                    success=False, reference_number=ref_num, error=f"upload_failed: {e}",
                )

            try:
                blob_names = [t.blob_name for t in targets]
                await self._finish_upload(http, ref_num, blob_names)
            except Exception as e:
                return SubmitResult(
                    success=False, reference_number=ref_num, error=f"finish_failed: {e}",
                )

            return await self._poll_status(http, ref_num, poll_interval, timeout_sec)

    async def _init_upload(
        self, http: httpx.AsyncClient, init_body: bytes,
    ) -> tuple[str, list[_UploadTarget]]:
        """POST XML -> ReferenceNumber + lista URL-i do Azure Blob."""
        resp = await http.post(
            "/api/Storage/InitUploadSigned",
            content=init_body,
            headers={"Content-Type": "application/xml"},
        )
        if resp.status_code >= 400:
            # MF zwraca JSON z Code + Message + RequestId — wyciagaj czytelny error
            try:
                err = resp.json()
                raise RuntimeError(
                    f"HTTP {resp.status_code} Code={err.get('Code')}: "
                    f"{err.get('Message')} (RequestId={err.get('RequestId')})"
                )
            except ValueError:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        ref_num = data["ReferenceNumber"]
        targets = []
        for item in data.get("RequestToUploadFileList", []):
            headers = {h["Key"]: h["Value"] for h in item.get("HeaderList", [])}
            targets.append(_UploadTarget(
                blob_name=item["BlobName"],
                url=item["Url"],
                method=item.get("Method", "PUT"),
                headers=headers,
            ))
        return ref_num, targets

    async def _upload_blob(self, target: _UploadTarget, ciphertext: bytes) -> None:
        """PUT zaszyfrowanego pliku na Azure Blob z headerami z InitUpload response."""
        async with httpx.AsyncClient(timeout=self.timeout) as blob_http:
            resp = await blob_http.request(
                target.method, target.url, content=ciphertext, headers=target.headers,
            )
            resp.raise_for_status()

    async def _finish_upload(
        self, http: httpx.AsyncClient, reference_number: str, blob_names: list[str],
    ) -> None:
        resp = await http.post(
            "/api/Storage/FinishUpload",
            json={
                "ReferenceNumber": reference_number,
                "AzureBlobNameList": blob_names,
            },
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
    def save_upo(upo_content: str, output_path: Path) -> Path:
        """Zapisz UPO zwrocone przez MF na dysk.

        MF zwraca UPO jako gotowy XML z podpisem XAdES (zweryfikowane w praktyce
        2026-04-17). Pole nazywa sie 'Upo' w JSON odpowiedzi Status endpoint.
        Jesli content zaczyna sie od '<?xml' — zapisz bezposrednio;
        w innym przypadku sprobuj zdekodowac base64 (zgodnosc wsteczna).
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stripped = upo_content.lstrip()
        if stripped.startswith("<?xml") or stripped.startswith("<"):
            output_path.write_text(upo_content, encoding="utf-8")
        else:
            cleaned = "".join(upo_content.split())
            output_path.write_bytes(base64.b64decode(cleaned.encode("ascii", "ignore")))
        return output_path
