"""Wspolne fixtures + ustawianie minimalnych SELLER_* przed importem config."""

import os

# Musi byc PRZED importem jdg_ksiegowy.config — pydantic-settings czyta env przy instancjacji.
os.environ.setdefault("SELLER_NAME", "Test Sp. z o.o.")
os.environ.setdefault("SELLER_NIP", "1234567890")
os.environ.setdefault("SELLER_ADDRESS", "ul. Testowa 1, 00-001 Warszawa")
os.environ.setdefault("SELLER_BANK_ACCOUNT", "42 1140 0000 0000 0000 0000 0000")
os.environ.setdefault("SELLER_BANK_NAME", "mBank")
os.environ.setdefault("SELLER_FIRST_NAME", "Jan")
os.environ.setdefault("SELLER_LAST_NAME", "Kowalski")
os.environ.setdefault("SELLER_BIRTH_DATE", "1990-01-01")
os.environ.setdefault("SELLER_TAX_OFFICE_CODE", "1471")
os.environ.setdefault("SELLER_EMAIL", "test@example.com")
os.environ.setdefault("MF_ENV", "test")
os.environ.setdefault("MF_PESEL", "")
os.environ.setdefault("MF_PRIOR_INCOME", "0")
