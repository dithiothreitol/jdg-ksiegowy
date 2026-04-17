"""E2E test bramki MF z mockiem httpx — pełny flow init/upload/finish/poll.

Używa respx do mockowania endpointów sandboxu (https://test-e-dokumenty.mf.gov.pl).
Nie wykonuje żadnych prawdziwych wywołań sieciowych.
"""

import base64
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
from jdg_ksiegowy.mf_gateway.client import MFGatewayClient
from jdg_ksiegowy.mf_gateway.crypto import EncryptedPayload


TEST_BASE = "https://test-e-dokumenty.mf.gov.pl"
BLOB_URL = "https://azure-blob.example.com/jpk/upload?sas=xxx"


@pytest.fixture
def auth() -> AuthorizationData:
    return AuthorizationData(
        nip="5260250274",
        pesel="44051401458",
        first_name="Jan",
        last_name="Kowalski",
        birth_date=date(1990, 1, 1),
        prior_year_income=Decimal("100000"),
    )


def _build_client() -> MFGatewayClient:
    """Klient z zamockowanym kluczem publicznym (pomijamy prawdziwe ładowanie)."""
    client = MFGatewayClient(base_url=TEST_BASE)
    # Zamockuj szyfrowanie — nie chcemy ładować prawdziwego klucza RSA
    payload = EncryptedPayload(
        ciphertext=b"ENCRYPTED_JPK_CONTENT",
        iv=b"0123456789abcdef",
        encrypted_aes_key=b"RSA_ENCRYPTED_AES",
        plaintext_size=1000,
        zip_size=400,
    )
    client._encrypt = MagicMock(return_value=payload)
    return client


@pytest.mark.asyncio
async def test_full_flow_success(respx_mock, auth):
    """Init -> Upload -> Finish -> Poll (200 OK) — zwraca UPO."""
    upo_b64 = base64.b64encode(b"UPO_XML_CONTENT").decode()

    init_route = respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json={
            "ReferenceNumber": "REF123456789",
            "BlobUploadUrl": BLOB_URL,
        })
    )
    upload_route = respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    finish_route = respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200, json={"Status": "InProgress"})
    )
    status_route = respx_mock.get(f"{TEST_BASE}/api/Storage/Status/REF123456789").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": upo_b64})
    )

    client = _build_client()
    result = await client.submit("<JPK/>", auth, poll_interval=0, timeout_sec=5)

    assert init_route.called
    assert upload_route.called
    assert finish_route.called
    assert status_route.called

    assert result.success is True
    assert result.reference_number == "REF123456789"
    assert result.upo_base64 == upo_b64
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_init_sends_authorization_xml(respx_mock, auth):
    """POST /InitUploadSigned zawiera sekcję Authorization z danymi osoby fiz."""
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json={
            "ReferenceNumber": "X", "BlobUploadUrl": BLOB_URL,
        })
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/X").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": "YQ=="})
    )

    client = _build_client()
    await client.submit("<JPK/>", auth, poll_interval=0, timeout_sec=5)

    init_call = respx_mock.routes[0].calls.last
    body = init_call.request.content.decode()
    assert "5260250274" in body        # NIP
    assert "44051401458" in body       # PESEL
    assert "ImiePierwsze>Jan" in body
    assert "DocumentMetadata" in body


@pytest.mark.asyncio
async def test_init_failure_propagates_error(respx_mock, auth):
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(500, text="Internal Error")
    )

    client = _build_client()
    result = await client.submit("<JPK/>", auth, poll_interval=0, timeout_sec=5)
    assert result.success is False
    assert "init_failed" in result.error


@pytest.mark.asyncio
async def test_status_error_returns_error(respx_mock, auth):
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json={
            "ReferenceNumber": "R1", "BlobUploadUrl": BLOB_URL,
        })
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/R1").mock(
        return_value=httpx.Response(200, json={
            "Code": 401, "Description": "Dane autoryzujące niepoprawne",
        })
    )

    client = _build_client()
    result = await client.submit("<JPK/>", auth, poll_interval=0, timeout_sec=5)
    assert result.success is False
    assert result.status_code == 401
    assert "niepoprawne" in result.error


@pytest.mark.asyncio
async def test_timeout_after_repeated_inprogress(respx_mock, auth):
    """Gdy status = 300 (w toku) kilkukrotnie → timeout."""
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json={
            "ReferenceNumber": "SLOW", "BlobUploadUrl": BLOB_URL,
        })
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/SLOW").mock(
        return_value=httpx.Response(200, json={"Code": 300})
    )

    client = _build_client()
    result = await client.submit("<JPK/>", auth, poll_interval=0, timeout_sec=0)
    # timeout_sec=0 → nie loopuje, od razu kończy
    assert result.success is False
    assert "timeout" in result.error
