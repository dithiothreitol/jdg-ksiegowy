"""Testy danych autoryzujacych dla bramki MF (SIG-2008_v2-0)."""

from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.mf_gateway.auth import SIG_NS, AuthorizationData, build_authorization_xml


def _auth(*, pesel: str = "44051401458") -> AuthorizationData:
    # NIP 5260250274 (ZUS, publiczny); PESEL 44051401458 (suma=102, R=8)
    return AuthorizationData(
        nip="5260250274",
        pesel=pesel,
        first_name="Jan",
        last_name="Kowalski",
        birth_date=date(1990, 1, 1),
        prior_year_income=Decimal("125000.50"),
    )


def _el(root, tag: str):
    return root.find(f"{{{SIG_NS}}}{tag}")


def test_authorization_xml_structure_pesel_variant():
    xml = build_authorization_xml(_auth())
    root = etree.fromstring(xml)
    assert etree.QName(root).localname == "DaneAutoryzujace"
    assert etree.QName(root).namespace == SIG_NS
    # xs:choice: PESEL gdy podany
    assert _el(root, "PESEL").text == "44051401458"
    assert _el(root, "NIP") is None
    assert _el(root, "ImiePierwsze").text == "Jan"
    assert _el(root, "Nazwisko").text == "Kowalski"
    assert _el(root, "DataUrodzenia").text == "1990-01-01"
    assert _el(root, "Kwota").text == "125000.50"


def test_authorization_xml_structure_nip_variant():
    """Gdy PESEL pusty — uzywamy NIP jako identyfikatora."""
    xml = build_authorization_xml(_auth(pesel=""))
    root = etree.fromstring(xml)
    assert _el(root, "NIP").text == "5260250274"
    assert _el(root, "PESEL") is None


def test_authorization_xml_has_declaration_and_utf8():
    xml = build_authorization_xml(_auth())
    assert xml.startswith(b'<?xml version')
    assert b"UTF-8" in xml[:60]


def test_fingerprint_does_not_leak_pesel_or_amount():
    auth = _auth()
    fp = auth.fingerprint()
    assert auth.pesel not in fp
    assert "125000" not in fp
    assert fp.startswith("sha256:")
