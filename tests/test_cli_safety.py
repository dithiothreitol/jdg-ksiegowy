"""Bezpieczenstwo czynnosci nieodwracalnych: bez waznego tokena zero wywolan na zewnatrz."""

import base64
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from jdg_ksiegowy.app.errors import ExitCode
from jdg_ksiegowy.cli.main import cli
from jdg_ksiegowy.cli.output import STATE
from jdg_ksiegowy.ksef.client import KSeFClient, KSeFResult

runner = CliRunner()
MF = "https://test-e-dokumenty.mf.gov.pl"
BLOB = "https://blob.example.test/REF1/B1?sas=x"
KSEF_NUMBER = "1234567890-20261110-0A1B2C-3D4E5F-6A"


def jdg(*args: str) -> tuple[int, dict]:
    result = runner.invoke(cli, list(args))
    return result.exit_code, json.loads(result.stdout)


@pytest.fixture(autouse=True)
def _setup(isolated_db, monkeypatch):
    from jdg_ksiegowy.config import settings

    STATE.json = None
    monkeypatch.setattr(settings.ksef, "env", "test")
    monkeypatch.setattr(settings.ksef, "nip", "1234567890")
    monkeypatch.setattr(settings.mf, "env", "test")
    monkeypatch.setattr(settings.mf, "pesel", "44051401458")
    monkeypatch.setattr(settings.mf, "cert_path", None)
    monkeypatch.setattr(settings.mf, "cert_url", None)


@pytest.fixture
def no_network():
    """Kazde nieoczekiwane zadanie HTTP konczy test bledem."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
def sent(monkeypatch) -> list[str]:
    calls: list[str] = []

    def fake_send(self, xml_content):
        calls.append(xml_content)
        return KSeFResult(
            success=True,
            env="test",
            reference_number="20261110-EE-REF",
            ksef_number=KSEF_NUMBER,
            upo=b"<UPO/>",
        )

    monkeypatch.setattr(KSeFClient, "send_invoice", fake_send)
    return calls


def _issue() -> str:
    code, payload = jdg(
        "invoice",
        "issue",
        "--buyer-nip",
        "5260250274",
        "--buyer-name",
        "Klient",
        "--buyer-address",
        "ul. X 1, 00-001 Warszawa",
        "--net",
        "1000",
        "--description",
        "Usluga",
        "--issue-date",
        "2026-11-10",
    )
    assert code == 0, payload
    return payload["data"]["number"]


def _audit_outcomes(action: str) -> list[str]:
    from jdg_ksiegowy.app.audit import recent

    return [r.outcome for r in reversed(recent()) if r.action == action]


# --- KSeF ----------------------------------------------------------------------------


def test_ksef_send_requires_token_and_sends_nothing(sent, no_network):
    number = _issue()
    code, payload = jdg("ksef", "send", number)

    assert code == ExitCode.CONFIRMATION
    err = payload["error"]
    assert err["code"] == "CONFIRMATION_REQUIRED"
    assert err["details"]["summary"]["env"] == "test"
    assert err["details"]["summary"]["brutto"] == "1230.00"
    assert sent == [] and no_network.calls.call_count == 0


def test_ksef_send_wrong_token_is_refused(sent):
    number = _issue()
    code, payload = jdg("ksef", "send", number, "--confirm", "deadbeef0000")
    assert code == ExitCode.CONFIRMATION
    assert "nieaktualny" in payload["error"]["message"]
    assert sent == []
    assert _audit_outcomes("ksef.send") == ["refused"]


def test_ksef_send_with_token_sends_once_and_records(sent):
    number = _issue()
    _, prepared = jdg("ksef", "send", number)
    token = prepared["error"]["details"]["token"]

    code, payload = jdg("ksef", "send", number, "--confirm", token)

    assert code == 0, payload
    assert payload["data"]["ksef_number"] == KSEF_NUMBER
    assert Path(payload["data"]["upo_path"]).read_bytes() == b"<UPO/>"
    assert len(sent) == 1
    assert _audit_outcomes("ksef.send") == ["pending", "ok"]

    code, payload = jdg("ksef", "send", number, "--confirm", token)  # ponowna wysylka
    assert code == ExitCode.DOMAIN and payload["error"]["code"] == "CONFLICT"
    assert len(sent) == 1


def test_token_bound_to_file_content(sent):
    """Zmiana pliku po pokazaniu podsumowania uniewaznia token."""
    number = _issue()
    _, prepared = jdg("ksef", "send", number)
    token = prepared["error"]["details"]["token"]
    _, shown = jdg("invoice", "show", number)
    xml = Path(shown["data"]["xml_path"])
    xml.write_text(xml.read_text(encoding="utf-8").replace("Usluga", "Inna usluga"), "utf-8")

    code, _ = jdg("ksef", "send", number, "--confirm", token)
    assert code == ExitCode.CONFIRMATION and sent == []


def test_token_bound_to_environment(sent, monkeypatch):
    """Token wydany dla srodowiska test nie zadziala po przelaczeniu na prod."""
    from jdg_ksiegowy.config import settings

    number = _issue()
    _, prepared = jdg("ksef", "send", number)
    monkeypatch.setattr(settings.ksef, "env", "prod")
    monkeypatch.setattr(settings.ksef, "token", "x")

    code, payload = jdg("ksef", "send", number, "--confirm", prepared["error"]["details"]["token"])
    assert code == ExitCode.CONFIRMATION
    assert payload["error"]["details"]["summary"]["env"] == "prod"
    assert sent == []


# --- bramka MF ------------------------------------------------------------------------


def _build_jpk() -> Path:
    _issue_october()
    code, payload = jdg("jpk", "build", "--year", "2026", "--month", "10")
    assert code == 0 and payload["data"]["xsd_valid"], payload
    return Path(payload["data"]["file_path"])


def _issue_october() -> None:
    jdg(
        "invoice",
        "issue",
        "--buyer-nip",
        "5260250274",
        "--buyer-name",
        "Klient",
        "--buyer-address",
        "ul. X 1, 00-001 Warszawa",
        "--net",
        "500",
        "--description",
        "Usluga",
        "--issue-date",
        "2026-10-20",
    )


def _mock_gateway(router: respx.MockRouter, status_code: int = 200) -> None:
    router.post(f"{MF}/api/Storage/InitUploadSigned").mock(
        return_value=httpx.Response(
            200,
            json={
                "ReferenceNumber": "REF1",
                "RequestToUploadFileList": [
                    {"BlobName": "B1", "Url": BLOB, "Method": "PUT", "HeaderList": []}
                ],
            },
        )
    )
    router.put(BLOB).mock(return_value=httpx.Response(201))
    router.post(f"{MF}/api/Storage/FinishUpload").mock(return_value=httpx.Response(200))
    upo = base64.b64encode(b"<UPO>REF1</UPO>").decode()
    router.get(f"{MF}/api/Storage/Status/REF1").mock(
        return_value=httpx.Response(200, json={"Code": status_code, "Upo": upo})
    )


def test_jpk_submit_without_token_touches_no_network(no_network):
    path = _build_jpk()
    code, payload = jdg("jpk", "submit", str(path))
    assert code == ExitCode.CONFIRMATION
    summary = payload["error"]["details"]["summary"]
    assert summary["formularz"] == "JPK_V7M" and summary["okres"] == "2026-10"
    assert summary["P_51"] == "115"
    assert no_network.calls.call_count == 0


def test_jpk_submit_rejects_invalid_xsd(no_network, tmp_path):
    path = _build_jpk()
    broken = tmp_path / "zly.xml"
    broken.write_text(
        path.read_text(encoding="utf-8")
        .replace("<tns:P_51>", "<tns:P_99>")
        .replace("</tns:P_51>", "</tns:P_99>"),
        encoding="utf-8",
    )
    code, payload = jdg("jpk", "submit", str(broken))
    assert code == ExitCode.DOMAIN and payload["error"]["code"] == "INVALID_INPUT"
    assert no_network.calls.call_count == 0


def test_jpk_submit_full_flow_and_duplicate_guards():
    path = _build_jpk()
    _, prepared = jdg("jpk", "submit", str(path))
    token = prepared["error"]["details"]["token"]
    with respx.mock(assert_all_mocked=True) as router:
        _mock_gateway(router)
        code, payload = jdg("jpk", "submit", str(path), "--confirm", token, "--wait", "0")
    assert code == 0, payload
    filing = payload["data"]
    assert (filing["status"], filing["reference_number"], filing["period"]) == (
        "accepted",
        "REF1",
        "2026-10",
    )
    assert Path(filing["upo_path"]).read_text(encoding="utf-8") == "<UPO>REF1</UPO>"

    code, payload = jdg("jpk", "submit", str(path), "--confirm", token)
    assert code == ExitCode.DOMAIN and "juz wyslany" in payload["error"]["message"]

    rebuilt = _build_jpk()  # nowy plik zlozenia za ten sam okres
    code, payload = jdg("jpk", "submit", str(rebuilt))
    assert code == ExitCode.DOMAIN
    assert "korekte" in payload["error"]["hint"]


def test_jpk_status_resumes_after_timeout():
    path = _build_jpk()
    _, prepared = jdg("jpk", "submit", str(path))
    with respx.mock(assert_all_mocked=True) as router:
        _mock_gateway(router, status_code=300)  # MF jeszcze przetwarza
        code, payload = jdg(
            "jpk",
            "submit",
            str(path),
            "--confirm",
            prepared["error"]["details"]["token"],
            "--wait",
            "0",
        )
    assert code == 0 and payload["data"]["status"] == "submitted"

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        _mock_gateway(router)
        code, payload = jdg("jpk", "status", "--reference", "REF1")
        assert router.calls.call_count == 1  # tylko status, bez ponownej wysylki
    assert code == 0
    assert payload["data"]["filings"][0]["status"] == "accepted"


def test_correction_build_numbers_files_and_validates():
    _issue_october()
    first = jdg(
        "jpk",
        "build",
        "--year",
        "2026",
        "--month",
        "10",
        "--correction",
        "--reason",
        "Korekta testowa",
    )[1]["data"]
    second = jdg("jpk", "build", "--year", "2026", "--month", "10", "--correction")[1]["data"]
    assert first["purpose"] == 2 and first["xsd_valid"]
    assert Path(second["file_path"]).name.endswith(f"_K{first['correction_no'] + 1}.xml")


def test_mail_requires_confirmation(monkeypatch):
    from jdg_ksiegowy.config import settings

    for field, value in (("host", "smtp.test"), ("username", "u"), ("password", "p")):
        monkeypatch.setattr(settings.smtp, field, value)
    sent_mail = []
    monkeypatch.setattr(
        "jdg_ksiegowy.app.invoices.send_invoice_email", lambda **kw: sent_mail.append(kw)
    )
    number = _issue()
    code, payload = jdg("invoice", "mail", number, "--to", "klient@example.com")
    assert code == ExitCode.CONFIRMATION
    assert payload["error"]["details"]["summary"]["do"] == "klient@example.com"
    assert sent_mail == []


def test_dry_run_expense_add_writes_nothing():
    code, payload = jdg(
        "expense",
        "add",
        "--seller-name",
        "X",
        "--seller-nip",
        "5260250274",
        "--document-number",
        "F/1",
        "--issue-date",
        "2026-10-01",
        "--net",
        "100",
        "--vat",
        "23",
        "--dry-run",
    )
    assert code == 0 and payload["data"]["deductible_vat"] == "23.00"
    assert jdg("expense", "list")[1]["data"]["count"] == 0


def test_issue_requires_description_for_new_buyer():
    code, payload = jdg(
        "invoice", "issue", "--buyer-nip", "5260250274", "--buyer-name", "K", "--net", "10"
    )
    assert code == ExitCode.DOMAIN
    assert "--description" in payload["error"]["hint"]


def test_status_today_default_works():
    code, payload = jdg("status")
    assert code == 0 and payload["data"]["today"] == date.today().isoformat()
    assert isinstance(payload["data"]["reminders"], list)
    assert Decimal(payload["data"]["month_sales_net"]) >= 0
