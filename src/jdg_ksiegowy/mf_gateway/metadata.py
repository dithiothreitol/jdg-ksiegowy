"""Budowa dokumentu metadanych InitUpload dla bramki MF.

Format: XML zgodny ze schematem InitUpload.xsd wydawanym przez MF
(wersja REST API: 01.02.01.20160617).

Struktura (spec 5.4 sekcja 2.2.1):

  <InitUpload>
    <DocumentType>JPK</DocumentType>
    <Version>01.02.01.20160617</Version>
    <EncryptionKey algorithm="RSA" mode="ECB" padding="PKCS#1" encoding="Base64">
      ...base64 RSA-encrypted AES key...
    </EncryptionKey>
    <DocumentList>
      <Document>
        <FormCode kodSystemowy="..." wersjaSchemy="...">JPK_VAT</FormCode>
        <FileName>...xml</FileName>
        <ContentLength>...</ContentLength>
        <HashValue algorithm="SHA-256" encoding="Base64">...</HashValue>
        <FileSignatureList filesNumber="1">
          <Packaging>
            <SplitZip type="split" mode="zip"/>
          </Packaging>
          <Encryption>
            <AES size="256" block="16" mode="CBC" padding="PKCS#7"/>
            <IV bytes="16" encoding="Base64">...</IV>
          </Encryption>
          <FileSignature>
            <OrdinalNumber>1</OrdinalNumber>
            <FileName>...xml.zip.001.aes</FileName>
            <ContentLength>...</ContentLength>
            <HashValue algorithm="MD5" encoding="Base64">...</HashValue>
          </FileSignature>
        </FileSignatureList>
      </Document>
    </DocumentList>
    <AuthData>...base64 AES-CBC encrypted DaneAutoryzujace XML...</AuthData>
  </InitUpload>
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

REST_API_VERSION = "01.02.01.20160617"
INIT_NS = "http://e-dokumenty.mf.gov.pl"


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadane dokumentu JPK do InitUpload."""

    # Atrybuty FormCode — z <KodFormularza> w JPK XML
    form_code: str  # zawartosc: np. "JPK_VAT"
    system_code: str  # kodSystemowy: np. "JPK_V7M (3)"
    schema_version: str  # wersjaSchemy: np. "1-0E"

    # Nazwa pliku i metadane
    filename: str  # np. "JPK_V7M_2026_03.xml"
    content_length: int  # rozmiar oryginalnego XML
    hash_sha256_b64: str  # SHA-256 oryginalu, Base64

    # Metadane pliku zaszyfrowanego (trafia na Azure Blob)
    encrypted_filename: str  # np. "JPK_V7M_2026_03.xml.zip.001.aes"
    encrypted_length: int  # rozmiar ciphertext (po ZIP+AES)
    encrypted_md5_b64: str  # MD5 ciphertext, Base64


def encrypted_filename_for(xml_filename: str) -> str:
    """Zbuduj nazwe pliku zaszyfrowanego wg konwencji z przykladu MF: jpk.xml -> jpk1.zip."""
    base = xml_filename.removesuffix(".xml")
    return f"{base}1.zip"


def _ns(tag: str) -> str:
    return f"{{{INIT_NS}}}{tag}"


def build_init_upload_xml(
    doc: DocumentMetadata,
    encrypted_aes_key_b64: str,
    iv_b64: str,
    auth_data_b64: str,
    document_type: str = "JPK",
) -> bytes:
    """Zbuduj kompletny dokument InitUpload XML.

    Args:
        doc: Metadane dokumentu (hasze, rozmiary, form code)
        encrypted_aes_key_b64: Klucz AES zaszyfrowany RSA, Base64
        iv_b64: IV 16 bajtow, Base64
        auth_data_b64: DaneAutoryzujace XML zaszyfrowane AES-CBC tym samym kluczem, Base64
        document_type: "JPK" | "JPKAH" | "XML" (default: JPK)
    """
    # NS: default namespace http://e-dokumenty.mf.gov.pl wg przykladu MF
    # (initupload-jpk_v7m-3.xml na podatki.gov.pl)
    root = etree.Element(_ns("InitUpload"), nsmap={None: INIT_NS})

    etree.SubElement(root, _ns("DocumentType")).text = document_type
    etree.SubElement(root, _ns("Version")).text = REST_API_VERSION

    enc_key = etree.SubElement(
        root,
        _ns("EncryptionKey"),
        algorithm="RSA",
        mode="ECB",
        padding="PKCS#1",
        encoding="Base64",
    )
    enc_key.text = encrypted_aes_key_b64

    doc_list = etree.SubElement(root, _ns("DocumentList"))
    document = etree.SubElement(doc_list, _ns("Document"))

    form_code = etree.SubElement(
        document,
        _ns("FormCode"),
        systemCode=doc.system_code,
        schemaVersion=doc.schema_version,
    )
    form_code.text = doc.form_code

    etree.SubElement(document, _ns("FileName")).text = doc.filename
    etree.SubElement(document, _ns("ContentLength")).text = str(doc.content_length)

    hash_val = etree.SubElement(
        document,
        _ns("HashValue"),
        algorithm="SHA-256",
        encoding="Base64",
    )
    hash_val.text = doc.hash_sha256_b64

    file_sig_list = etree.SubElement(
        document,
        _ns("FileSignatureList"),
        filesNumber="1",
    )

    packaging = etree.SubElement(file_sig_list, _ns("Packaging"))
    etree.SubElement(packaging, _ns("SplitZip"), type="split", mode="zip")

    # Wazne: IV jest WEWNATRZ AES (wg przykladu MF), nie jako rodzenstwo
    encryption = etree.SubElement(file_sig_list, _ns("Encryption"))
    aes_el = etree.SubElement(
        encryption,
        _ns("AES"),
        size="256",
        block="16",
        mode="CBC",
        padding="PKCS#7",
    )
    iv_el = etree.SubElement(aes_el, _ns("IV"), bytes="16", encoding="Base64")
    iv_el.text = iv_b64

    file_sig = etree.SubElement(file_sig_list, _ns("FileSignature"))
    etree.SubElement(file_sig, _ns("OrdinalNumber")).text = "1"
    etree.SubElement(file_sig, _ns("FileName")).text = doc.encrypted_filename
    etree.SubElement(file_sig, _ns("ContentLength")).text = str(doc.encrypted_length)
    enc_hash = etree.SubElement(
        file_sig,
        _ns("HashValue"),
        algorithm="MD5",
        encoding="Base64",
    )
    enc_hash.text = doc.encrypted_md5_b64

    etree.SubElement(root, _ns("AuthData")).text = auth_data_b64

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=False,
    )


def extract_jpk_form_code(xml_content: bytes) -> tuple[str, str, str]:
    """Wyciagnij (form_code, system_code, schema_version) z naglowka JPK XML.

    Szuka elementu KodFormularza w namespacie JPK i jego atrybutow.
    """
    root = etree.fromstring(xml_content)
    # KodFormularza moze byc w namespacie — szukamy po local-name
    for el in root.iter():
        tag = etree.QName(el).localname
        if tag == "KodFormularza":
            return (
                el.text or "",
                el.get("kodSystemowy", ""),
                el.get("wersjaSchemy", ""),
            )
    raise ValueError("Nie znaleziono KodFormularza w XML JPK")
