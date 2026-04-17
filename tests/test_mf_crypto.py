"""Testy szyfrowania pliku JPK przed wysylka do MF (round-trip).

Generujemy lokalny klucz RSA, szyfrujemy JPK, deszyfrujemy z powrotem,
sprawdzamy ze ZIP zawiera oryginalny XML.
"""

import zipfile
from io import BytesIO

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from jdg_ksiegowy.mf_gateway.crypto import encrypt_jpk, zip_xml


def test_zip_xml_creates_valid_archive():
    raw = zip_xml(b"<JPK>x</JPK>", "test.xml")
    with zipfile.ZipFile(BytesIO(raw)) as zf:
        assert "test.xml" in zf.namelist()
        assert zf.read("test.xml") == b"<JPK>x</JPK>"


def test_encrypt_jpk_roundtrip():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()

    original = b"<JPK><Naglowek/></JPK>"
    payload = encrypt_jpk(original, public)

    # Odzyskaj klucz AES
    aes_key = private.decrypt(payload.encrypted_aes_key, asym_padding.PKCS1v15())
    assert len(aes_key) == 32
    assert len(payload.iv) == 16

    # Deszyfracja AES
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(payload.iv))
    dec = cipher.decryptor()
    padded = dec.update(payload.ciphertext) + dec.finalize()

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    zipped = unpadder.update(padded) + unpadder.finalize()

    # Rozpakuj ZIP i sprawdz zawartosc
    with zipfile.ZipFile(BytesIO(zipped)) as zf:
        assert zf.read("jpk.xml") == original

    assert payload.plaintext_size == len(original)
