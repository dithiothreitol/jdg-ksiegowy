"""Szyfrowanie pliku JPK przed wysylka do bramki MF.

Algorytm wg Specyfikacji Interfejsow Uslug JPK v4.2:
- Klucz AES-256: losowy (32 bajty)
- IV: losowy (16 bajtow)
- Plik: ZIP -> AES-256-CBC z PKCS#7 -> Base64 do uploadu
- Klucz AES: szyfrowany RSA/ECB/PKCS#1 kluczem publicznym MF

Klucz publiczny MF pobierasz z https://www.podatki.gov.pl/...
Aktualizowany okresowo, ostatnio 18.07.2025.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


@dataclass(frozen=True)
class EncryptedPayload:
    """Wynik szyfrowania pliku JPK do wysylki."""

    ciphertext: bytes  # zaszyfrowany ZIP
    encrypted_aes_key: bytes  # klucz AES zaszyfrowany RSA kluczem publicznym MF
    iv: bytes  # 16 bajtow
    plaintext_size: int  # rozmiar oryginalu (przed kompresja) - wymagane w metadanych
    zip_size: int  # rozmiar po kompresji ZIP


def zip_xml(xml_content: bytes, inner_filename: str = "jpk.xml") -> bytes:
    """Spakuj XML do ZIP-a (wymagane przed szyfrowaniem)."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_filename, xml_content)
    return buffer.getvalue()


def load_mf_public_key(cert_path: Path | str) -> RSAPublicKey:
    """Wczytaj klucz publiczny MF z PEM/DER."""
    raw = Path(cert_path).read_bytes()
    if raw.startswith(b"-----BEGIN"):
        # PEM — moze byc certyfikat lub sam klucz publiczny
        if b"CERTIFICATE" in raw:
            from cryptography import x509

            cert = x509.load_pem_x509_certificate(raw)
            key = cert.public_key()
        else:
            key = serialization.load_pem_public_key(raw)
    else:
        key = serialization.load_der_public_key(raw)
    if not isinstance(key, RSAPublicKey):
        raise ValueError("Klucz publiczny MF musi byc RSA")
    return key


def encrypt_jpk(
    xml_content: bytes,
    mf_public_key: RSAPublicKey,
    inner_filename: str = "jpk.xml",
) -> EncryptedPayload:
    """Spakuj + zaszyfruj JPK do wysylki na bramke MF."""
    plaintext_size = len(xml_content)
    zipped = zip_xml(xml_content, inner_filename)

    aes_key = os.urandom(32)
    iv = os.urandom(16)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(zipped) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    encrypted_aes_key = mf_public_key.encrypt(
        aes_key,
        asym_padding.PKCS1v15(),
    )

    return EncryptedPayload(
        ciphertext=ciphertext,
        encrypted_aes_key=encrypted_aes_key,
        iv=iv,
        plaintext_size=plaintext_size,
        zip_size=len(zipped),
    )
