"""Szyfrowanie pliku JPK przed wysylka do bramki MF.

Algorytm wg Specyfikacji Interfejsow Uslug JPK v5.4 (sekcja 1.2, 1.3):
- Klucz AES-256 losowy (32 bajty), IV losowy (16 bajtow)
- XML -> ZIP (deflate) -> AES-256-CBC/PKCS#7 -> upload
- Klucz AES: szyfrowany RSA/ECB/PKCS#1v15 kluczem publicznym MF
- AuthData: XML SIG-2008 -> AES-256-CBC tym samym kluczem+IV -> base64

Metadane wymagane do InitUpload:
- SHA-256(xml) Base64 (HashValue dokumentu)
- MD5(ciphertext) Base64 (HashValue pliku + Content-MD5 Put Blob)
"""

from __future__ import annotations

import base64
import hashlib
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
    """Wynik szyfrowania pliku JPK do wysylki na bramke MF.

    Klucz AES i IV sa zachowane, zeby mozna bylo zaszyfrowac tym samym
    kluczem element AuthData (wymog spec 5.4 sekcja 1.3.2).
    """

    ciphertext: bytes             # zaszyfrowany ZIP (do uploadu na Azure Blob)
    encrypted_aes_key: bytes      # klucz AES zaszyfrowany RSA kluczem publicznym MF
    iv: bytes                     # 16 bajtow
    aes_key: bytes                # 32 bajty — do szyfrowania AuthData
    plaintext: bytes              # oryginalny XML (do liczenia SHA-256)
    plaintext_size: int           # rozmiar oryginalu
    zip_size: int                 # rozmiar po ZIP (przed AES)


def zip_xml(xml_content: bytes, inner_filename: str = "jpk.xml") -> bytes:
    """Spakuj XML do ZIP-a (deflate) — wymagane przed szyfrowaniem."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_filename, xml_content)
    return buffer.getvalue()


def load_mf_public_key(cert_path: Path | str) -> RSAPublicKey:
    """Wczytaj klucz publiczny MF z PEM/DER (certyfikat X.509 lub raw public key)."""
    raw = Path(cert_path).read_bytes()
    if raw.startswith(b"-----BEGIN"):
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


def aes_encrypt_cbc(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-256-CBC z PKCS#7 padding. Zwraca ciphertext (bez IV prepended)."""
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def sha256_b64(data: bytes) -> str:
    """SHA-256 bytes -> Base64 (dla HashValue dokumentu XML)."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def md5_b64(data: bytes) -> str:
    """MD5 bytes -> Base64 (dla HashValue pliku zaszyfrowanego + Content-MD5)."""
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")


def encrypt_jpk(
    xml_content: bytes,
    mf_public_key: RSAPublicKey,
    inner_filename: str = "jpk.xml",
) -> EncryptedPayload:
    """Spakuj + zaszyfruj JPK do wysylki na bramke MF.

    Pipeline: xml_content -> zip_xml(deflate) -> aes_encrypt_cbc(AES-256/CBC/PKCS#7).
    Klucz AES szyfrowany RSA/ECB/PKCS#1v15 kluczem publicznym MF.
    """
    zipped = zip_xml(xml_content, inner_filename)
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    ciphertext = aes_encrypt_cbc(zipped, aes_key, iv)

    encrypted_aes_key = mf_public_key.encrypt(
        aes_key,
        asym_padding.PKCS1v15(),
    )

    return EncryptedPayload(
        ciphertext=ciphertext,
        encrypted_aes_key=encrypted_aes_key,
        iv=iv,
        aes_key=aes_key,
        plaintext=xml_content,
        plaintext_size=len(xml_content),
        zip_size=len(zipped),
    )
