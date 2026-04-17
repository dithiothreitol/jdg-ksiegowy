"""Klient bramki Ministerstwa Finansow dla JPK_V7M i JPK_EWP.

Bramka REST: https://e-dokumenty.mf.gov.pl (prod), test-e-dokumenty.mf.gov.pl (test).
Autoryzacja: dane autoryzujace (NIP+PESEL+imiona+data ur+kwota przychodu z PIT N-2)
LUB podpis kwalifikowany (nieobslugiwane przez ten klient).

UWAGA: Implementacja MVP. Zalecane: testowac wylacznie na bramce test PRZED prod.
Klucz publiczny MF aktualizowany okresowo (ostatnio 18.07.2025).
"""

from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
from jdg_ksiegowy.mf_gateway.client import MFGatewayClient, SubmitResult
from jdg_ksiegowy.mf_gateway.public_key import MFPublicKeyRegistry, PublicKeyInfo

__all__ = [
    "AuthorizationData",
    "MFGatewayClient",
    "MFPublicKeyRegistry",
    "PublicKeyInfo",
    "SubmitResult",
]
