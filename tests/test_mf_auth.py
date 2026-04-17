"""Testy danych autoryzujacych dla bramki MF."""

from datetime import date
from decimal import Decimal

from jdg_ksiegowy.mf_gateway.auth import AuthorizationData, build_authorization_xml


def _auth() -> AuthorizationData:
    return AuthorizationData(
        nip="1234567890",
        pesel="90010100000",
        first_name="Jan",
        last_name="Kowalski",
        birth_date=date(1990, 1, 1),
        prior_year_income=Decimal("125000.50"),
    )


def test_authorization_xml_contains_required_fields():
    xml = build_authorization_xml(_auth())
    assert "<Identyfikator>1234567890</Identyfikator>" in xml
    assert "<Pesel>90010100000</Pesel>" in xml
    assert "<ImiePierwsze>Jan</ImiePierwsze>" in xml
    assert "<Nazwisko>Kowalski</Nazwisko>" in xml
    assert "<DataUrodzenia>1990-01-01</DataUrodzenia>" in xml
    assert "<KwotaPrzychodu>125000.50</KwotaPrzychodu>" in xml


def test_fingerprint_does_not_leak_pesel_or_amount():
    auth = _auth()
    fp = auth.fingerprint()
    assert auth.pesel not in fp
    assert "125000" not in fp
    assert fp.startswith("sha256:")
