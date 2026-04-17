"""Testy walidacji NIP, PESEL, REGON.

Wartości testowe — obliczone ręcznie:
  NIP 1234563218: wagi*cyfry = 6+10+21+8+15+24+15+12+7 = 118, 118%11=8, ok
  NIP 5260250274: (NIP ZUS, publiczny)  169%11=4, ok
  NIP 9876543210: 54+40+49+12+15+16+15+12+7=220, 220%11=0, ok
  PESEL 44051401458: 4+12+0+45+1+12+0+9+4+15=102, (10-2)%10=8, ok
  PESEL 49040501580: 4+27+0+36+0+15+0+9+5+24=120, (10-0)%10=0, ok
  PESEL 80010112340: 8+0+0+9+0+3+7+18+3+12=60, (10-0)%10=0, ok
  REGON 016298263: 0+9+12+6+36+40+12+42=157, 157%11=3, ok (PKO Bank, publiczny)
"""

import pytest

from jdg_ksiegowy.validators import validate_nip, validate_pesel, validate_regon, normalize_nip


class TestNIP:
    VALID = [
        "1234563218",
        "5260250274",   # ZUS (publiczny)
        "9876543210",
    ]
    INVALID = [
        "1234567890",   # sum%11=10 → brak cyfry kontrolnej
        "5260250270",   # ostatnia cyfra zmieniona (4→0)
        "0000000000",   # same zera
        "123456789",    # za krótki
        "12345678901",  # za długi
        "123456789X",   # litera
    ]

    def test_valid_nips(self):
        for nip in self.VALID:
            assert validate_nip(nip), f"Powinien byc poprawny: {nip}"

    def test_invalid_nips(self):
        for nip in self.INVALID:
            assert not validate_nip(nip), f"Powinien byc niepoprawny: {nip}"

    def test_strips_separators(self):
        assert validate_nip("526-025-02-74")
        assert validate_nip("526 025 02 74")
        assert validate_nip("526-025-0274")

    def test_normalize_nip_removes_dashes(self):
        assert normalize_nip("526-025-02-74") == "5260250274"

    def test_normalize_nip_raises_on_wrong_length(self):
        with pytest.raises(ValueError, match="10 cyfr"):
            normalize_nip("12345")

    def test_buyer_model_validates_nip(self):
        from jdg_ksiegowy.invoice.models import Buyer
        with pytest.raises(Exception):
            Buyer(name="Test", nip="5260250270", address="ul. Testowa 1")

    def test_buyer_model_accepts_valid_nip(self):
        from jdg_ksiegowy.invoice.models import Buyer
        b = Buyer(name="Test", nip="5260250274", address="ul. Testowa 1")
        assert b.nip == "5260250274"

    def test_buyer_model_normalizes_nip_dashes(self):
        from jdg_ksiegowy.invoice.models import Buyer
        b = Buyer(name="Test", nip="526-025-02-74", address="ul. Testowa 1")
        assert b.nip == "5260250274"


class TestPESEL:
    VALID = [
        "44051401458",  # sum=102, R=8
        "49040501580",  # sum=120, R=0
        "80010112340",  # sum=60, R=0
    ]
    INVALID = [
        "44051401457",  # ostatnia cyfra zmieniona (8→7)
        "90010175827",  # sum=129, R=1, ostatnia=7
        "1234567890",   # za krótki (10)
        "123456789012", # za długi (12)
    ]

    def test_valid_pesels(self):
        for pesel in self.VALID:
            assert validate_pesel(pesel), f"Powinien byc poprawny: {pesel}"

    def test_invalid_pesels(self):
        for pesel in self.INVALID:
            assert not validate_pesel(pesel), f"Powinien byc niepoprawny: {pesel}"

    def test_authorization_data_validates_pesel(self):
        from datetime import date
        from decimal import Decimal
        from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
        with pytest.raises(ValueError, match="PESEL"):
            AuthorizationData(
                nip="5260250274",
                pesel="44051401457",  # zła suma kontrolna
                first_name="Jan",
                last_name="Kowalski",
                birth_date=date(1990, 1, 1),
                prior_year_income=Decimal("0"),
            )

    def test_authorization_data_accepts_valid_pesel(self):
        from datetime import date
        from decimal import Decimal
        from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
        auth = AuthorizationData(
            nip="5260250274",
            pesel="44051401458",
            first_name="Jan",
            last_name="Kowalski",
            birth_date=date(1990, 1, 1),
            prior_year_income=Decimal("0"),
        )
        assert auth.pesel == "44051401458"

    def test_authorization_data_empty_pesel_skips_validation(self):
        """Pusty PESEL (autoryzacja NIPem) — nie walidujemy."""
        from datetime import date
        from decimal import Decimal
        from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
        auth = AuthorizationData(
            nip="5260250274",
            pesel="",
            first_name="Jan",
            last_name="Kowalski",
            birth_date=date(1990, 1, 1),
            prior_year_income=Decimal("0"),
        )
        assert auth.pesel == ""


class TestREGON:
    # PKO Bank Polski — publiczny, REGON 016298263
    # 0*8+1*9+6*2+2*3+9*4+8*5+2*6+6*7 = 0+9+12+6+36+40+12+42=157, 157%11=3 ok
    VALID_9 = ["016298263"]
    INVALID_9 = [
        "016298260",   # zmieniona cyfra kontrolna (3→0)
        "000000000",   # same zera
        "12345678",    # za krótki
    ]

    def test_valid_regon_9(self):
        for r in self.VALID_9:
            assert validate_regon(r), f"Powinien byc poprawny: {r}"

    def test_invalid_regon_9(self):
        for r in self.INVALID_9:
            assert not validate_regon(r), f"Powinien byc niepoprawny: {r}"

    def test_invalid_format(self):
        assert not validate_regon("01629826X")   # litera
        assert not validate_regon("0162982631")  # 10 cyfr (nie 9 ani 14)
