"""E2E test bramki MF z mockiem httpx wg Specyfikacji JPK v5.4.

Używa respx do mockowania endpointów sandboxu (https://test-e-dokumenty.mf.gov.pl).
Weryfikuje: XML body dla InitUpload, JSON body dla FinishUpload, pełny pipeline.
Nie wykonuje żadnych prawdziwych wywołań sieciowych.
"""

import base64
import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from lxml import etree

from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
from jdg_ksiegowy.mf_gateway.client import MFGatewayClient
from jdg_ksiegowy.mf_gateway.crypto import EncryptedPayload

TEST_BASE = "https://test-e-dokumenty.mf.gov.pl"
BLOB_URL = "https://taxdocumentstorage09tst.blob.core.windows.net/REF123/BLOB1?sas=xxx"
BLOB_NAME = "8377ed3d-1b05-4c76-b718-6fddd46fd298"

# Minimalny JPK XML z KodFormularza (wymagane przez extract_jpk_form_code)
SAMPLE_JPK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<JPK xmlns="http://crd.gov.pl/wzor/2025/06/18/06181/">
  <Naglowek>
    <KodFormularza kodSystemowy="JPK_V7M (3)" wersjaSchemy="1-0E">JPK_VAT</KodFormularza>
  </Naglowek>
</JPK>"""


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
    """Klient z zamockowanym szyfrowaniem (nie ładujemy prawdziwego klucza RSA)."""
    client = MFGatewayClient(base_url=TEST_BASE)
    payload = EncryptedPayload(
        ciphertext=b"ENCRYPTED_JPK_CONTENT",
        iv=b"0123456789abcdef",
        encrypted_aes_key=b"RSA_ENCRYPTED_AES",
        aes_key=b"0" * 32,
        plaintext=SAMPLE_JPK_XML.encode("utf-8"),
        plaintext_size=len(SAMPLE_JPK_XML),
        zip_size=400,
    )
    client._encrypt = MagicMock(return_value=payload)
    return client


def _init_response(ref_num: str = "REF123") -> dict:
    return {
        "ReferenceNumber": ref_num,
        "TimeoutInSec": 900,
        "RequestToUploadFileList": [
            {
                "BlobName": BLOB_NAME,
                "FileName": "JPK.xml.zip.001.aes",
                "Url": BLOB_URL,
                "Method": "PUT",
                "HeaderList": [
                    {"Key": "Content-MD5", "Value": "eXkPLHMM+dHB5GCFoeAvsA=="},
                    {"Key": "x-ms-blob-type", "Value": "BlockBlob"},
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_full_flow_success(respx_mock, auth):
    """Init -> Upload -> Finish -> Poll (200 OK) — zwraca UPO."""
    upo_b64 = base64.b64encode(b"UPO_XML_CONTENT").decode()

    init_route = respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response())
    )
    upload_route = respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    finish_route = respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200)
    )
    status_route = respx_mock.get(f"{TEST_BASE}/api/Storage/Status/REF123").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": upo_b64})
    )

    client = _build_client()
    result = await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)

    assert init_route.called
    assert upload_route.called
    assert finish_route.called
    assert status_route.called
    assert result.success is True
    assert result.reference_number == "REF123"
    assert result.upo_base64 == upo_b64


@pytest.mark.asyncio
async def test_init_sends_xml_body_with_auth_and_metadata(respx_mock, auth):
    """Body POST /InitUploadSigned: application/xml z wymaganymi elementami."""
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response())
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(return_value=httpx.Response(200))
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/REF123").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": "YQ=="})
    )

    client = _build_client()
    await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)

    init_call = respx_mock.routes[0].calls.last
    assert init_call.request.headers["content-type"] == "application/xml"

    from jdg_ksiegowy.mf_gateway.metadata import INIT_NS

    ns = f"{{{INIT_NS}}}"

    root = etree.fromstring(init_call.request.content)
    assert root.tag == f"{ns}InitUpload"
    assert root.find(f"{ns}DocumentType").text == "JPK"
    assert root.find(f"{ns}Version").text == "01.02.01.20160617"

    enc_key = root.find(f"{ns}EncryptionKey")
    assert enc_key.get("algorithm") == "RSA"
    assert enc_key.get("padding") == "PKCS#1"

    document = root.find(f"{ns}DocumentList/{ns}Document")
    form_code = document.find(f"{ns}FormCode")
    assert form_code.get("systemCode") == "JPK_V7M (3)"
    assert form_code.get("schemaVersion") == "1-0E"
    assert form_code.text == "JPK_VAT"

    # IV wewnatrz AES (wg przykladu MF), nie jako rodzenstwo
    aes = document.find(f"{ns}FileSignatureList/{ns}Encryption/{ns}AES")
    assert aes.find(f"{ns}IV") is not None

    file_sig = document.find(f"{ns}FileSignatureList/{ns}FileSignature")
    assert file_sig.find(f"{ns}FileName").text.endswith(".zip")
    assert file_sig.find(f"{ns}HashValue").get("algorithm") == "MD5"

    # AuthData jest zaszyfrowany (base64), nie plain text
    auth_data = root.find(f"{ns}AuthData").text
    assert auth_data
    assert "Kowalski" not in auth_data


@pytest.mark.asyncio
async def test_init_failure_propagates_error(respx_mock, auth):
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(
            400, json={"Code": 120, "Message": "Podpis negatywnie zweryfikowany"}
        )
    )

    client = _build_client()
    result = await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)
    assert result.success is False
    assert "init_failed" in result.error


@pytest.mark.asyncio
async def test_finish_upload_body_contains_blob_names(respx_mock, auth):
    """POST /FinishUpload wysyla JSON z ReferenceNumber + AzureBlobNameList."""
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response())
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    finish_route = respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(
        return_value=httpx.Response(200)
    )
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/REF123").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": "YQ=="})
    )

    client = _build_client()
    await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)

    finish_body = json.loads(finish_route.calls.last.request.content)
    assert finish_body["ReferenceNumber"] == "REF123"
    assert finish_body["AzureBlobNameList"] == [BLOB_NAME]


@pytest.mark.asyncio
async def test_status_error_returns_error(respx_mock, auth):
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response("R1"))
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(return_value=httpx.Response(200))
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/R1").mock(
        return_value=httpx.Response(
            200,
            json={
                "Code": 401,
                "Description": "Dane autoryzujące niepoprawne",
            },
        )
    )

    client = _build_client()
    result = await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)
    assert result.success is False
    assert result.status_code == 401
    assert "niepoprawne" in result.error


@pytest.mark.asyncio
async def test_timeout_after_repeated_inprogress(respx_mock, auth):
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response("SLOW"))
    )
    respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(return_value=httpx.Response(200))
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/SLOW").mock(
        return_value=httpx.Response(200, json={"Code": 300})
    )

    client = _build_client()
    result = await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=0)
    assert result.success is False
    assert "timeout" in result.error


@pytest.mark.asyncio
async def test_upload_uses_headers_from_init_response(respx_mock, auth):
    """PUT Azure Blob wysyła headery zwrócone z InitUpload (Content-MD5, x-ms-blob-type)."""
    respx_mock.post(f"{TEST_BASE}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(200, json=_init_response())
    )
    upload_route = respx_mock.put(BLOB_URL).mock(return_value=httpx.Response(201))
    respx_mock.post(f"{TEST_BASE}/api/Storage/FinishUpload").mock(return_value=httpx.Response(200))
    respx_mock.get(f"{TEST_BASE}/api/Storage/Status/REF123").mock(
        return_value=httpx.Response(200, json={"Code": 200, "Upo": "YQ=="})
    )

    client = _build_client()
    await client.submit(SAMPLE_JPK_XML, auth, poll_interval=0, timeout_sec=5)

    put_req = upload_route.calls.last.request
    assert put_req.headers["content-md5"] == "eXkPLHMM+dHB5GCFoeAvsA=="
    assert put_req.headers["x-ms-blob-type"] == "BlockBlob"
